"""The product scorecard — measurable proxies for "would a person use this".

Every metric here is computed from the report structure, never sampled from a
model, so the same report always scores the same. Where a dimension genuinely
cannot be measured deterministically (does this insight feel novel?) it is
absent rather than faked: a number that is really a guess is worse than an
acknowledged gap, because it gets averaged into a release decision.

A backend COMPLETE never implies PRODUCT_READY. They answer different
questions — one is "did retrieval and synthesis finish", the other is "should
a stranger be shown this".
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

SCORECARD_VERSION = "product-scorecard.v1"

# --- outcomes ----------------------------------------------------------------
PRODUCT_READY = "PRODUCT_READY"
PRODUCT_READY_WITH_LIMITATIONS = "PRODUCT_READY_WITH_LIMITATIONS"
TAILORED_DEMO_ONLY = "TAILORED_DEMO_ONLY"
EXPLORATORY_ONLY = "EXPLORATORY_ONLY"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
FAILED_PRODUCT_QUALITY = "FAILED_PRODUCT_QUALITY"

PRODUCT_OUTCOMES = (PRODUCT_READY, PRODUCT_READY_WITH_LIMITATIONS,
                    TAILORED_DEMO_ONLY, EXPLORATORY_ONLY,
                    INSUFFICIENT_EVIDENCE, FAILED_PRODUCT_QUALITY)

DIMENSIONS = ("evidence", "intelligence", "communication", "experience",
              "commercial")

# --- thresholds --------------------------------------------------------------
# One place, one version. Changing a number here to make a build pass is a
# decision that shows up in a diff with a reason attached — which is the point.
THRESHOLDS = {
    "brief_words_max": 500,
    "brief_words_min": 120,
    "slide_words_max": 90,
    "min_meaningful_slides": 5,
    "duplication_ratio_max": 0.25,
    "repeated_phrase_ratio_max": 0.15,
    "evidence_reuse_ratio_max": 0.50,
    "max_displayed_hypotheses": 3,
    "min_independent_share_for_high_confidence": 0.20,
    "jargon_per_100_words_max": 4.0,
    "long_sentence_share_max": 0.30,
}

#: The floor BELOW which a deck is not a presentation at all, whatever the
#: evidence supported. Taken from the renderer's own `deck_is_presentable` so
#: the eval and the product cannot drift apart on what "presentable" means —
#: they already had, by one slide, and the gap was only visible when a run
#: legitimately produced four.
from intent_engine.strategic_intelligence.slides import (  # noqa: E402
    MIN_MEANINGFUL_SLIDES as _PRESENTABLE_FLOOR,
)

# Words that mean nothing to a reader who did not write them.
JARGON = (
    "leverage", "synergy", "paradigm", "holistic", "utilise", "utilize",
    "ideate", "operationalise", "operationalize", "bandwidth", "north star",
    "value-add", "best-in-class", "mission-critical", "low-hanging",
    "move the needle", "boil the ocean", "circle back", "double-click",
    "table stakes", "core competency", "vertical integration play",
)

# Phrases that signal a claim with nothing behind it.
GENERIC_THESIS_MARKERS = (
    "is a leading", "is well positioned", "continues to innovate",
    "is a major player", "has a strong presence", "is transforming",
    "is revolutionising", "is revolutionizing", "leverages technology",
)


def _words(text: str) -> list:
    return re.findall(r"[A-Za-z][A-Za-z'-]*", text or "")


def _sentences(text: str) -> list:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text or "")
            if s.strip()]


def _shingles(text: str, n: int = 6) -> set:
    words = [w.lower() for w in _words(text)]
    return {" ".join(words[i:i + n]) for i in range(max(0, len(words) - n + 1))}


def duplication_ratio(blocks) -> float:
    """Share of six-word sequences that have already appeared.

    Six words is long enough that a collision is real repetition rather than a
    shared idiom, and short enough to catch a paraphrase that a reader would
    still experience as being told the same thing twice.
    """
    seen, repeated, total = set(), 0, 0
    for block in blocks:
        for shingle in _shingles(block):
            total += 1
            if shingle in seen:
                repeated += 1
            else:
                seen.add(shingle)
    return round(repeated / total, 3) if total else 0.0


def evidence_reuse_ratio(hypotheses) -> float:
    """Share of evidence citations that appear under more than one hypothesis.

    The observed complaint was not that evidence was reused — sometimes it must
    be — but that the reader could not tell they had already read it.
    """
    seen, reused, total = set(), 0, 0
    for h in hypotheses or ():
        for ref in (h.get("evidence") or ()):
            total += 1
            if ref in seen:
                reused += 1
            else:
                seen.add(ref)
    return round(reused / total, 3) if total else 0.0


def jargon_density(text: str) -> float:
    low = " " + (text or "").lower() + " "
    hits = sum(low.count(j) for j in JARGON)
    words = max(1, len(_words(text)))
    return round(100.0 * hits / words, 2)


def long_sentence_share(text: str, limit: int = 32) -> float:
    sents = _sentences(text)
    if not sents:
        return 0.0
    long = sum(1 for s in sents if len(_words(s)) > limit)
    return round(long / len(sents), 3)


def reading_seconds(text: str, wpm: int = 220) -> int:
    return int(round(60.0 * len(_words(text)) / wpm)) if text else 0


def thesis_is_generic(thesis: str) -> bool:
    low = (thesis or "").lower()
    return any(m in low for m in GENERIC_THESIS_MARKERS)


@dataclass
class ProductScore:
    outcome: str = FAILED_PRODUCT_QUALITY
    dimensions: dict = field(default_factory=dict)
    metrics: dict = field(default_factory=dict)
    failures: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    scorecard_version: str = SCORECARD_VERSION

    def as_dict(self) -> dict:
        return asdict(self)

    @property
    def ok(self) -> bool:
        return self.outcome in (PRODUCT_READY, PRODUCT_READY_WITH_LIMITATIONS)


def score_report(*, brief=None, slides=(), report=None, documents=(),
                 quality=None, readiness=None) -> ProductScore:
    """Score one composed analysis as a PRODUCT, not as a pipeline result."""
    score = ProductScore()
    metrics, failures, warnings = {}, [], []
    report = report or {}
    quality = quality or {}

    # --- communication -------------------------------------------------------
    brief_text = ""
    if brief is not None:
        parts = [getattr(brief, "thesis", ""), getattr(brief, "counterpoint", ""),
                 getattr(brief, "tension", ""), getattr(brief, "decision", ""),
                 getattr(brief, "limitation", "")]
        parts += [s.get("text", "") for s in getattr(brief, "signals", ())]
        parts += list(getattr(brief, "questions", ()))
        brief_text = "\n".join(p for p in parts if p)
    metrics["brief_words"] = len(_words(brief_text))
    metrics["brief_reading_seconds"] = reading_seconds(brief_text)
    metrics["jargon_per_100_words"] = jargon_density(brief_text)
    metrics["long_sentence_share"] = long_sentence_share(brief_text)

    if metrics["brief_words"] > THRESHOLDS["brief_words_max"]:
        failures.append(f"brief is {metrics['brief_words']} words; the "
                        f"standard is {THRESHOLDS['brief_words_max']}")
    if brief_text and metrics["brief_words"] < THRESHOLDS["brief_words_min"]:
        warnings.append(f"brief is only {metrics['brief_words']} words — "
                        "likely too thin to answer the standard questions")
    if metrics["jargon_per_100_words"] > THRESHOLDS["jargon_per_100_words_max"]:
        failures.append("brief is dense with business jargon")

    # --- repetition ----------------------------------------------------------
    hypotheses = report.get("hypotheses") or []
    blocks = [h.get("statement", "") for h in hypotheses]
    blocks += [h.get("reasoning", "") for h in hypotheses]
    blocks += [brief_text]
    metrics["duplication_ratio"] = duplication_ratio([b for b in blocks if b])
    metrics["evidence_reuse_ratio"] = evidence_reuse_ratio(hypotheses)
    if metrics["duplication_ratio"] > THRESHOLDS["duplication_ratio_max"]:
        failures.append(f"{int(100 * metrics['duplication_ratio'])}% of the "
                        "report repeats text the reader has already seen")
    if metrics["evidence_reuse_ratio"] > THRESHOLDS["evidence_reuse_ratio_max"]:
        failures.append("the same evidence is re-cited across most hypotheses "
                        "without being marked as already seen")

    # --- intelligence --------------------------------------------------------
    thesis = (report.get("thesis") or {}).get("view", "")
    metrics["hypothesis_count"] = len(hypotheses)
    metrics["thesis_generic"] = thesis_is_generic(thesis)
    if metrics["hypothesis_count"] > THRESHOLDS["max_displayed_hypotheses"]:
        failures.append(f"{metrics['hypothesis_count']} hypotheses shown; a "
                        f"reader can hold "
                        f"{THRESHOLDS['max_displayed_hypotheses']}")
    if metrics["thesis_generic"]:
        failures.append("the central thesis would be true of any company")

    counter = sum(1 for h in hypotheses if h.get("counter_evidence"))
    metrics["hypotheses_with_counter_evidence"] = counter
    if hypotheses and counter == 0:
        warnings.append("no hypothesis shows evidence against it")

    # --- evidence ------------------------------------------------------------
    docs = list(documents or ())
    independent = [d for d in docs if d.get("source_class") in
                   ("independent_reporting", "customer_voice", "competitor")]
    metrics["document_count"] = len(docs)
    metrics["independent_share"] = (round(len(independent) / len(docs), 3)
                                    if docs else 0.0)
    metrics["families"] = sorted({d.get("source_type", "") for d in docs} - {""})
    metrics["metadata_only_documents"] = sum(
        1 for d in docs if d.get("extraction_mode") == "metadata")

    confidences = [str(h.get("confidence", "")).lower() for h in hypotheses]
    metrics["high_confidence_count"] = sum(1 for c in confidences
                                           if c.startswith("high"))
    if (metrics["high_confidence_count"] and
            metrics["independent_share"] <
            THRESHOLDS["min_independent_share_for_high_confidence"]):
        failures.append("a hypothesis is high-confidence on company-owned "
                        "evidence alone")

    # Every displayed claim declares how it is known, and the declaration has
    # to agree with the evidence behind it. A claim marked as corroborated
    # outside the company while every source is the company's own page is
    # worse than an unlabelled one: it is a false assurance in the exact place
    # a careful reader looks.
    provenances = [str(h.get("provenance", "")).strip() for h in hypotheses]
    metrics["provenance"] = sorted(set(p for p in provenances if p))
    metrics["unlabelled_claims"] = sum(1 for p in provenances if not p)
    if hypotheses and metrics["unlabelled_claims"]:
        failures.append(f"{metrics['unlabelled_claims']} claim(s) do not say "
                        "how they are known")
    outside = ("independently corroborated", "customer-observed")
    if any(p in outside for p in provenances) and \
            metrics["independent_share"] == 0:
        failures.append("a claim says it is corroborated outside the company "
                        "while every source is the company's own")

    # --- presentation --------------------------------------------------------
    slides = list(slides or ())
    metrics["slide_count"] = len(slides)
    empty = [s for s in slides if not (s.get("bullets") or s.get("body"))]
    metrics["empty_slides"] = len(empty)
    overfull = [s for s in slides
                if len(_words(" ".join(b.get("text", "")
                                       for b in s.get("bullets", []))))
                > THRESHOLDS["slide_words_max"]]
    metrics["overfull_slides"] = len(overfull)
    if empty:
        failures.append(f"{len(empty)} slide(s) have no content")
    if overfull:
        failures.append(f"{len(overfull)} slide(s) exceed "
                        f"{THRESHOLDS['slide_words_max']} words")
    # A deck that got past the readiness gate promised a presentation. Four
    # slides is a paragraph with arrows, and the release standard names five as
    # the floor — so it has to be a failure here, not a band in a dimension
    # nobody gates on.
    #
    # BUT A DECK MAY NOT REACH THE FLOOR BY ASSERTING SOMETHING THE EVIDENCE
    # DOES NOT SUPPORT, and for a while it did. `services_to_product` qualified
    # on any two of three signals, so an API page and a products page were
    # enough to tell Brightledger — self-serve reconciliation software that
    # PUBLISHES ITS PRICING, which is that pattern's own disconfirming signal —
    # that it "converts what it learned delivering work alongside customers
    # into products". Requiring the services signal removed that slide and this
    # gate then failed the run for being one short, which is the floor asking
    # for the fabrication back.
    #
    # So the shortfall is a failure when COMPOSITION lost the slides, and a
    # warning when the run simply did not support that many findings — the same
    # treatment, and for the same reason, as "no strategic view could be
    # supported" below: it stays visible so the pressure to find more does not
    # quietly disappear, but it never demands an invented finding.
    if brief_text and metrics["slide_count"] < THRESHOLDS[
            "min_meaningful_slides"]:
        thin = len(hypotheses or ()) <= 1
        short = f"only {metrics['slide_count']} meaningful slide(s); " \
                f"{THRESHOLDS['min_meaningful_slides']} is the floor " \
                f"for a presentation"
        if thin and metrics["slide_count"] >= _PRESENTABLE_FLOOR:
            warnings.append(
                short + " — the evidence supported "
                f"{len(hypotheses or ())} finding(s), so the deck is short "
                "rather than padded")
        else:
            failures.append(short)

    # A brief with no hypothesis behind it is a summary wearing an analysis's
    # clothes. Sony reached six sources, four evidence families and a rendered
    # brief with ZERO hypotheses, and every gate passed it.
    #
    # Except for a business where a strategic hypothesis would have to be
    # invented rather than observed. A dental practice with a services page,
    # published prices and reviews has a complete public footprint; demanding a
    # thesis from it produces a manufactured one, which is worse than none.
    metrics["research_mode"] = (readiness or {}).get("research_mode", "")
    metrics["view_withheld"] = bool(getattr(brief, "view_withheld", False))
    hypothesis_required = (readiness or {}).get("requires_hypothesis", True)
    if brief_text and not hypotheses and hypothesis_required:
        if metrics["view_withheld"]:
            # Saying "the evidence supports no view" is a legitimate product
            # answer, but never a good outcome — it stays a limitation so the
            # pressure to find one does not quietly disappear.
            warnings.append("no strategic view could be supported by this "
                            "evidence, and the brief says so")
        else:
            failures.append("a brief was produced with no strategic "
                            "hypothesis behind it — the reader is told what "
                            "the company says, not what it means")

    # --- outcome -------------------------------------------------------------
    score.metrics = metrics
    score.failures = failures
    score.warnings = warnings
    score.dimensions = {
        "evidence": _band(metrics["independent_share"] > 0
                          and metrics["document_count"] >= 3,
                          metrics["document_count"] >= 1),
        "intelligence": _band(bool(hypotheses) and not metrics["thesis_generic"],
                              bool(thesis)),
        "communication": _band(
            not failures and metrics["brief_words"] <=
            THRESHOLDS["brief_words_max"],
            bool(brief_text)),
        "experience": _band(metrics["slide_count"] >=
                            THRESHOLDS["min_meaningful_slides"]
                            and not metrics["empty_slides"],
                            metrics["slide_count"] > 0),
        "commercial": _band(bool(report.get("decision_implications")),
                            bool(hypotheses)),
    }

    # An EMPTY report is not a passing report. This has to come before every
    # other rule: a report with no thesis, no hypotheses and no slides
    # generates no failures at all, so a gate that only looks at failures
    # scores it as ready. That is exactly how the product could return nothing
    # for Palantir, Linear and Notion while the scorecard said
    # PRODUCT_READY_WITH_LIMITATIONS.
    #
    # But there are two ways to show a reader nothing, and only one of them is
    # a defect. Declining on purpose — the readiness gate looked at the
    # evidence and said this may not become a report — is the product working:
    # the reader gets an explanation instead of a confident-looking page built
    # on one source. Producing nothing *after* passing that gate is the bug.
    # Scoring them the same made a correct refusal read as a quality failure,
    # and left the real defect sharing a bucket with it.
    declined_on_purpose = (readiness or {}).get("may_synthesize") is False
    produced_nothing = not hypotheses and not brief_text and not slides
    if produced_nothing and docs and not declined_on_purpose:
        failures.append("evidence was retrieved but no brief, hypothesis or "
                        "slide was produced — the reader gets an empty result")
        score.failures = failures

    if not docs or declined_on_purpose:
        score.outcome = INSUFFICIENT_EVIDENCE
    elif failures:
        score.outcome = FAILED_PRODUCT_QUALITY
    elif metrics["independent_share"] == 0 or warnings:
        score.outcome = PRODUCT_READY_WITH_LIMITATIONS
    else:
        score.outcome = PRODUCT_READY
    return score


def _band(good: bool, adequate: bool) -> str:
    return "good" if good else ("adequate" if adequate else "poor")
