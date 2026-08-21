"""The pre-synthesis readiness gate.

WHY A GATE, NOT A WARNING
-------------------------
Synthesis is willing. Given one filing it will still produce a thesis, three
hypotheses, blind spots and leadership questions — laid out exactly like a
report built on twenty sources. The reader cannot tell the difference, because
the SHAPE of the output carries no information about how much was behind it.
That is how "SEC 6-K is shifting where demand is captured" reaches a human
being: not a synthesis bug, but synthesis being asked a question it had no
business answering.

So the decision to synthesize is made BEFORE synthesis, on the evidence alone,
and it is a gate rather than a warning: a warning still renders the report, and
a rendered report is what does the damage.

`coverage.assess` already measures evidence spread and stays as-is — other
callers depend on it. This is the stricter, decision-making layer on top: it
adds identity, dated evidence, presentable material and a retry plan, and it
returns one of five states that the caller must branch on.

Pure and deterministic. It reads documents and identity; it never fetches,
never invents, and never upgrades a state to be helpful.
"""
from __future__ import annotations

import re

from intent_engine.company_ingestion.coverage import (
    COMMERCIAL, CUSTOMERS, IDENTITY, INDEPENDENT, INVESTOR, PRODUCT, STRATEGY,
    family_of,
)

READINESS_VERSION = "ci_readiness.v1"

# --- states ------------------------------------------------------------------
READY_FOR_FULL_REPORT = "READY_FOR_FULL_REPORT"
READY_FOR_LIMITED_REPORT = "READY_FOR_LIMITED_REPORT"
RETRYABLE_EVIDENCE_GAP = "RETRYABLE_EVIDENCE_GAP"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
IDENTITY_UNRESOLVED = "IDENTITY_UNRESOLVED"

READINESS_STATES = (READY_FOR_FULL_REPORT, READY_FOR_LIMITED_REPORT,
                    RETRYABLE_EVIDENCE_GAP, INSUFFICIENT_EVIDENCE,
                    IDENTITY_UNRESOLVED)

# --- thresholds --------------------------------------------------------------
MIN_SOURCES_FULL = 5
MIN_FAMILIES_FULL = 3
# One family may not carry a report. 70% is deliberately tighter than the
# advisory 75% in coverage.assess, because this number decides whether a full
# strategic dashboard is rendered at all.
MAX_FAMILY_SHARE = 0.70
MIN_SLIDE_UNITS = 5
# A limited report is still worth showing; below this there is nothing to say.
# All three must hold: two documents from one family agreeing with themselves
# is a single viewpoint, and three subjects is the floor for a page that reads
# as an analysis rather than a stub.
MIN_SOURCES_LIMITED = 2
MIN_FAMILIES_LIMITED = 2
MIN_SLIDE_UNITS_LIMITED = 3
# Deterministic retry budget. One targeted second pass, then stop — an
# unbounded retry loop is how a "still trying" spinner becomes the product.
MAX_DISCOVERY_ATTEMPTS = 2

# Families that can satisfy each mandatory role.
_OFFICIAL_IDENTITY_ROLE = (IDENTITY, PRODUCT)
_DIRECTION_ROLE = (STRATEGY, INVESTOR)
_MARKET_ROLE = (CUSTOMERS, INDEPENDENT, COMMERCIAL)

_MONTHS = ("january", "february", "march", "april", "may", "june", "july",
           "august", "september", "october", "november", "december")
_YEAR = re.compile(r"\b(19|20)\d{2}\b")
_ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_QUARTER = re.compile(r"\bq[1-4]\b|\bquarter\b|\bfiscal year\b|\bfy\d{2,4}\b")


def usable_documents(documents) -> list:
    """Documents that actually carry readable text, counted once each.

    A 403 with a status line is not evidence, and neither is an empty 200 —
    and neither are nine copies of the same page. A misconfigured site that
    serves its homepage for every path produced nine "sources" across seven
    "families", which every coverage gate read as breadth. It is one document
    wearing seven hats, and a report built on it says one thing seven times.

    Deduplicated on the text itself rather than on a content hash, because the
    same page served under nine URLs differs in its canonical tag and its
    hash, and is identical in the only respect that matters.
    """
    seen, out = set(), []
    for document in documents:
        if document.get("retrieval_status") != "OK":
            continue
        text = (document.get("text_content") or "").strip()
        if len(text) < 40:
            continue
        fingerprint = " ".join(text.lower().split())[:400]
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        out.append(document)
    return out


# Function words and letters that belong to a language this analysis cannot
# read. The test looks for these RATHER than for English markers, and the
# difference matters: a first attempt tested for the presence of English words
# and declared a perfectly ordinary English company unreadable, because short
# marketing prose ("Northwind Freight operates a temperature-controlled road
# network") happens to contain almost no function words. Refusing a real
# company is far worse than the silence it was meant to replace, so the burden
# of proof sits on the accusation.
_FOREIGN_MARKERS = (
    " der ", " die ", " das ", " und ", " für ", " mit ", " von ", " ist ",
    " eine ", " einen ", " sich ", " nicht ", " werden ",       # de
    " le ", " la ", " les ", " des ", " est ", " sont ", " pour ", " dans ",
    " nous ", " sur ",                                          # fr
    " el ", " los ", " las ", " una ", " para ", " con ", " son ", " nuestra ",
    " nuestro ",                                                # es
    " il ", " lo ", " gli ", " per ", " con ", " sono ", " nostra ",   # it
    " de ", " het ", " een ", " voor ", " zijn ",               # nl
)
_FOREIGN_LETTERS = "äöüßàâçéèêëîïôùûñõáíóúåæø"
#: Foreign function words per THOUSAND WORDS at which a document stops being
#: readable English. German and French prose run far above this; English
#: financial prose carrying "per share", "de minimis" and "El Paso" runs far
#: below it at any length. Calibrated against real documents, not chosen:
#: MEASURED, on real documents, through this product's own extractor:
#:
#:     Cloudflare 10-Q   0.50 markers / 1000 words   (71,377 words)
#:     Cloudflare 10-K   0.56                        (85,567 words)
#:     German page     371.08
#:     French page     443.90
#:
#: A 600x separation. The bar is set at 40 -- eighty times the measured
#: English rate and a ninth of the measured foreign rate -- so neither side
#: is anywhere near it and a document has to be substantially foreign to
#: cross. Chosen from the distribution above rather than picked.
_FOREIGN_MARKER_DENSITY = 40.0
#: Accented characters per thousand characters. Same idea: a German page is
#: dense in umlauts; an English filing that names one French subsidiary is not.
#: Both real filings measure 0.00.
_FOREIGN_ACCENT_DENSITY = 5.0
# Below this share of documents, the evidence is not in a language this
# analysis can read. Set above a half deliberately: at exactly half, a report
# would be built on the readable pages while silently ignoring as much again.
MIN_ENGLISH_SHARE = 0.6


def _densities(text: str, accented: int) -> tuple:
    """The two numbers the language wall decides on. ONE producer.

    Read by `is_english` to decide and by `readiness_inputs` to report, so a
    document listed as language-rejected carries the same densities that
    rejected it rather than a second opinion about them.
    """
    words = max(1, text.count(" "))
    occurrences = sum(text.count(m) for m in _FOREIGN_MARKERS)
    return (occurrences * 1000.0 / words,
            accented * 1000.0 / max(1, len(text)))


def _language_text(document: dict) -> tuple:
    """Exactly the text and accent count `is_english` judges on."""
    text = " " + " ".join((document.get("text_content") or "").lower().split()) \
        + " "
    return text, sum(1 for ch in text if ch in _FOREIGN_LETTERS)


def _foreign_marker_density(document: dict) -> float:
    return _densities(*_language_text(document))[0]


def _accent_density(document: dict) -> float:
    return _densities(*_language_text(document))[1]


def is_english(document: dict) -> bool:
    """Whether this document is readable by the analysis.

    True unless there is positive evidence otherwise — an unreadable document
    stops a report, so the test must be one that fires on foreign text and not
    on terse English.
    """
    text = " " + " ".join((document.get("text_content") or "").lower().split()) \
        + " "
    if len(text) < 120:
        return True                     # too short to judge; do not accuse it
    foreign_words = sum(1 for m in _FOREIGN_MARKERS if m in text)
    accented = sum(1 for ch in text if ch in _FOREIGN_LETTERS)

    # PRESENCE IS NOT EVIDENCE IN A LONG DOCUMENT.
    #
    # `foreign_words` counts how many of the ~40 markers appear AT LEAST ONCE.
    # That number can only rise as a document gets longer, and English
    # financial prose contains several of them outright: " per " (per share),
    # " de " (de minimis, de facto), " el " (El Paso), " la ", " il ", " lo ".
    #
    # Measured on Cloudflare's own 10-Q, through this product's extractor:
    #
    #      5,000 chars -> 1 marker      200,000 chars -> 1 marker
    #     50,000 chars -> 1 marker      400,000 chars -> 2 markers
    #    100,000 chars -> 1 marker      465,969 chars -> 3 markers
    #
    # An English SEC filing arrives at 3 against a threshold of 4. Nothing
    # about the language changed between those rows; only the length did. The
    # cost of crossing that line is not cosmetic -- a set-aside filing is
    # evidence the analysis never sees, and a run that loses its 10-Q drops
    # below the source floor and renders a Limited analysis. Cloudflare, the
    # standing regression control, did exactly that live on 8397d67 with its
    # 10-Q listed under "Sources found but not used".
    #
    # So a LONG document has to show foreign text DENSELY, not merely once.
    # Short documents keep the original absolute test unchanged: a 300-word
    # German blog post cannot reach a density threshold built for filings,
    # and that is the case this check was written for.
    #
    # This can only move a document from foreign to English, never the other
    # way -- the scaled thresholds are >= the originals for every length. A
    # genuinely foreign document is dense in markers at any size.
    # DENSITY, AND IT MUST BE COUNTED IN OCCURRENCES.
    #
    # A first version of this scaled the thresholds by length and kept
    # counting DISTINCT markers. That was wrong in the dangerous direction and
    # a positive control caught it: `foreign_words` can never exceed the ~40
    # markers in the table, so a 280,000-character German document could not
    # reach a bar of 56 and was reclassified ENGLISH -- the exact case this
    # check exists for, broken by the repair.
    #
    # Occurrences scale with length; distinct markers saturate. So the measure
    # is how much of the text is foreign, per thousand words, which is a
    # property of the LANGUAGE rather than of the length.
    marker_density, accent_density = _densities(text, accented)
    return not (marker_density >= _FOREIGN_MARKER_DENSITY
                or accent_density >= _FOREIGN_ACCENT_DENSITY
                or (marker_density >= _FOREIGN_MARKER_DENSITY / 2
                    and accent_density >= _FOREIGN_ACCENT_DENSITY / 2))


def english_share(documents) -> float:
    """How much of this evidence is in a language the analysis can read.

    A company that publishes only in German produced four usable sources, no
    brief, no hypothesis and no slide, and said nothing about why. Retrieval
    worked perfectly; the analysis simply had nothing to match on. Silence is
    the wrong answer to that — "we could not read this company's evidence" is
    a finding, and a reader can act on it.
    """
    documents = list(documents or ())
    if not documents:
        return 1.0
    return sum(1 for d in documents if is_english(d)) / len(documents)


def is_dated(document: dict) -> bool:
    """Whether a document can support a claim about *recent change*.

    "What changed recently" is the single most load-bearing section of an
    outside-in brief and the easiest to fabricate: undated marketing copy reads
    exactly like a current announcement. A document earns the right to support
    a timing claim only if it says when.
    """
    text = ((document.get("text_content") or "") + " " +
            (document.get("title") or "")).lower()
    return bool(_ISO_DATE.search(text) or _YEAR.search(text)
                or _QUARTER.search(text)
                or any(month in text for month in _MONTHS))


def slide_units(documents) -> list:
    """The distinct, presentable subjects this evidence can actually support.

    Shared with the presentation layer on purpose: the gate must not promise
    five slides that the renderer then cannot fill, and the renderer must not
    invent a sixth. Source lists, disclaimers and limitations are deliberately
    NOT units — padding the count with them is how an empty deck passes a
    length check.
    """
    usable = usable_documents(documents)
    families = {family_of(d) for d in usable}
    units = []
    if families & {IDENTITY}:
        units.append("company_overview")
    if families & {PRODUCT}:
        units.append("products")
    if families & {CUSTOMERS, INDEPENDENT}:
        units.append("customers_and_market")
    if families & {INVESTOR, STRATEGY}:
        units.append("strategic_direction")
    if families & {COMMERCIAL}:
        units.append("commercial_model")
    if any(is_dated(d) for d in usable):
        units.append("what_changed")
    # A tension needs two vantage points to hold it up; one family agreeing
    # with itself is not a tension.
    if len(families) >= 2:
        units.append("tension_or_risk")
    if len(families) >= 3:
        units.append("opportunity")
    return units


def _share(counts: dict, total: int) -> tuple:
    if not counts or not total:
        return (None, 0.0)
    dominant = max(counts, key=lambda f: counts[f])
    return (dominant, counts[dominant] / total)


def _check(name, ok, detail, *, required_for_full=True):
    return {"name": name, "ok": bool(ok), "detail": detail,
            "required_for_full": required_for_full}


def observations_as_documents(observations) -> list:
    """Curated StrategicObservations, viewed as evidence the gate can count.

    Evidence does not stop being evidence because it arrived through the
    explicit add-source hook rather than through retrieval — that hook is how a
    tailored, pre-researched company is prepared before a meeting. A gate that
    counted only fetched pages would refuse to report on exactly the runs that
    were most carefully assembled.
    """
    out = []
    for observation in observations or ():
        excerpt = (getattr(observation, "excerpt", "") or
                   getattr(observation, "text", "") or "")
        date = getattr(observation, "date", "") or ""
        out.append({
            "source_type": "pasted",
            "source_class": getattr(observation, "source_class",
                                    "company_owned"),
            # the date travels in the text so `is_dated` sees it, exactly as it
            # would in a retrieved page
            "text_content": f"{excerpt} {date}".strip(),
            "title": getattr(observation, "source_title", "") or "",
            "retrieval_status": "OK",
        })
    return out


def readiness_inputs(documents, verdict, *, attempt: int = 1) -> dict:
    """WHAT THE GATE WAS LOOKING AT, counted over the set it judged.

    ONE READER, BECAUSE TWO DRIFTED. The four `dropped_*` counters used to be
    computed at first composition while `documents_at_compose` and
    `usable_at_compose` were later overwritten by the re-gate. The header
    then described two different document sets at once, and its arithmetic
    stopped closing:

        UnitedHealth, 743df06:  compose=13 usable=9 dropped=0/0/2/0

    Thirteen minus two is eleven, not nine. Two documents disappeared into a
    gap between two measurements of different things -- which is exactly the
    confusion the breakdown was added to end. Both callers now come here.
    """
    documents = list(documents)
    ok = [d for d in documents if d.get("retrieval_status") == "OK"]
    texted = [d for d in ok if (d.get("text_content") or "").strip()]
    deduped = usable_documents(documents)
    english = [d for d in deduped if is_english(d)]
    inputs = {
        "dropped_not_ok": len(documents) - len(ok),
        "dropped_empty": len(ok) - len(texted),
        "dropped_duplicate": max(0, len(texted) - len(deduped)),
        "dropped_language": max(0, len(deduped) - len(english)),
        "documents_at_compose": len(documents),
        "usable_at_compose": verdict.get("document_count"),
        "families_at_compose": list(verdict.get("families") or []),
        "source_ids": [d.get("source_id") for d in documents][:40],
        "attempt": attempt,
    }
    # THE COUNTERS MUST CLOSE, and when they do not that is the finding.
    # `usable` is the gate's own number; anything it dropped that these four
    # filters do not name is attrition nobody has instrumented yet, and it is
    # reported as its own quantity rather than left to be inferred from a
    # subtraction that does not work.
    # WHICH DOCUMENTS THE LANGUAGE WALL TOOK, not just how many.
    #
    # MEASURED on 8fd6c82, NVIDIA: `dropped=0/0/0/8` -- eight of twelve
    # refused by `is_english` alone. "Eight" cannot say whether they were
    # genuinely localised pages discovery should never have proposed, or
    # English pages the density heuristic misreads, and those are opposite
    # repairs. Naming them costs one pass over text already in memory.
    inputs["language_rejected"] = [
        {"source_id": d.get("source_id"),
         "url": (d.get("final_url") or d.get("original_url") or "")[:160],
         "chars": len((d.get("text_content") or "")),
         "marker_density": round(_foreign_marker_density(d), 2),
         "accent_density": round(_accent_density(d), 2)}
        for d in deduped if d not in english][:12]
    named = (inputs["dropped_not_ok"] + inputs["dropped_empty"]
             + inputs["dropped_duplicate"] + inputs["dropped_language"])
    usable = inputs["usable_at_compose"]
    if isinstance(usable, int):
        inputs["dropped_unexplained"] = len(documents) - named - usable
    return inputs


def assess_readiness(*, documents, identity=None, failures=(),
                     extra_observations=(), attempt: int = 1,
                     mode=None) -> dict:
    """Decide whether this evidence may become a report, and if not, what next.

    `identity` is the persisted `ci.entity_identified` payload, or None.
    `failures` are this run's retrieval failures, used to build a retry plan
    that avoids ground already known to be barren.
    `extra_observations` are curated observations added through the explicit
    source-addition hook; they count as evidence like any other.
    `attempt` is 1-based; the retry budget is spent when it reaches
    MAX_DISCOVERY_ATTEMPTS.
    `mode` is the research mode to hold this company to. When omitted it is
    inferred from the evidence. The public-company numbers below are the
    defaults, so a run that infers `public_company` is assessed exactly as it
    was before modes existed.
    """
    from intent_engine.company_ingestion.research_modes import (
        expectations_for, infer_mode,
    )
    documents = list(documents) + observations_as_documents(extra_observations)
    retrieved = usable_documents(documents)
    # A page we cannot read is not evidence, so it is set aside rather than
    # counted and then held against the run.
    #
    # Figma reported "not enough public evidence" after reading EIGHT sources
    # across four families. Half were German blog tag pages: they counted as
    # usable, dragged the readable share under the threshold, and voided a run
    # whose four English sources were perfectly good. Retrieval had done its
    # job; the arithmetic was wrong.
    #
    # The share is still measured over everything retrieved, so "we could not
    # read some of this company's evidence" remains a finding the reader is
    # told rather than something quietly dropped.
    readable = english_share(retrieved)
    usable = [d for d in retrieved if is_english(d)] or retrieved
    unreadable_count = len(retrieved) - len(usable)
    counts: dict = {}
    for document in usable:
        family = family_of(document)
        counts[family] = counts.get(family, 0) + 1
    families = sorted(counts)
    total = len(usable)
    dominant, dominant_share = _share(counts, total)
    units = slide_units(documents)
    dated = [d for d in usable if is_dated(d)]

    # Identity is a precondition, not a check: a report about nobody in
    # particular has nothing to be right or wrong about.
    identity_ok = _identity_is_resolved(identity)

    # Which evidence model this company is held to. Inferred from the evidence
    # rather than declared, because a user who could classify their own target
    # correctly would not need the product.
    inferred = infer_mode(usable, identity=identity)
    research_mode = mode or inferred["mode"]
    expects = expectations_for(research_mode)
    min_sources = expects["min_sources_full"]
    min_families = expects["min_families_full"]
    min_units = expects["min_slide_units"]

    checks = [
        _check("identity_resolved", identity_ok,
               "the company this report is about is established"
               if identity_ok else
               "the company could not be identified confidently"),
        _check("source_count", total >= min_sources,
               f"{total} usable source(s); {min_sources} needed for a "
               f"full report"),
        _check("evidence_families", len(families) >= min_families,
               f"{len(families)} kind(s) of evidence "
               f"({', '.join(families) or 'none'}); {min_families} "
               f"needed"),
        _check("official_identity_or_product",
               bool(set(families) & set(_OFFICIAL_IDENTITY_ROLE)),
               "an official page describing the company or its products"),
        # A private company has no investor family and a corner shop has no
        # strategy page. Demanding them reports only that the company is not
        # public, which is not a finding.
        _check("direction_source",
               bool(set(families) & set(_DIRECTION_ROLE)),
               "a strategy, investor, or leadership source showing where the "
               "company says it is going",
               required_for_full=expects["requires_direction_source"]),
        _check("market_source",
               bool(set(families) & set(_MARKET_ROLE)),
               "a customer, use-case, partnership, or independent market "
               "source, as a check on the company's own account",
               required_for_full=expects["requires_market_source"]),
        _check("dated_evidence", bool(dated),
               f"{len(dated)} dated source(s), needed before anything can be "
               f"called a recent change"),
        _check("presentable_material", len(units) >= min_units,
               f"{len(units)} distinct subject(s) with real material; "
               f"{min_units} needed for a presentation"),
        _check("no_dominant_family",
               total == 0 or dominant_share <= MAX_FAMILY_SHARE,
               (f"{int(dominant_share * 100)}% of the evidence is "
                f"'{dominant}'" if dominant else "no evidence")),
        _check("readable_language", readable >= MIN_ENGLISH_SHARE,
               "this company publishes in a language this analysis cannot "
               "read, so its evidence was retrieved but not understood"
               if readable < MIN_ENGLISH_SHARE else
               "the evidence is in a language this analysis can read"),
    ]
    # A check this mode does not require cannot block a full report. It is
    # still reported, because "no investor material" is worth knowing about a
    # private company even though it is not a defect in one.
    unmet = [c for c in checks if not c["ok"]]
    failed = [c for c in unmet if c["required_for_full"]]
    missing_families = _missing_families(counts)
    retry_plan = _retry_plan(missing_families, failures, attempt)

    material = _material_level(total=total, families=families, units=units,
                               failed=failed, expects=expects,
                               readable=readable)
    state = _decide(identity_ok=identity_ok, material=material,
                    retry_plan=retry_plan)

    return {
        "state": state,
        "readiness_version": READINESS_VERSION,
        "attempt": attempt,
        "checks": checks,
        "failed_checks": [c["name"] for c in failed],
        "unmet_checks": [c["name"] for c in unmet],
        "research_mode": research_mode,
        "research_mode_label": inferred["label"]
        if research_mode == inferred["mode"] else research_mode,
        "research_mode_why": inferred["why"],
        "research_mode_expectation": inferred["expectation"]
        if research_mode == inferred["mode"] else "",
        "requires_hypothesis": expects["requires_hypothesis"],
        "expects_financial_disclosure": expects["expects_financial_disclosure"],
        "document_count": total,
        "families": families,
        "family_counts": counts,
        "dominant_family": dominant,
        "dominant_share": round(dominant_share, 3),
        "dated_source_count": len(dated),
        "readable_share": round(readable, 3),
        "set_aside_unreadable": unreadable_count,
        "slide_units": units,
        "missing_families": missing_families,
        "retry_plan": retry_plan,
        "material_level": material,
        # Whether ANYTHING may be synthesized, and whether the FULL strategic
        # dashboard may be. These are separate questions: a run can have enough
        # for an honest limited view while still being worth one more look.
        "may_synthesize": identity_ok and material in ("limited", "full"),
        "full_report_allowed": identity_ok and material == "full",
    }


def _identity_is_resolved(identity) -> bool:
    """A run knows who it is about if the registry resolved it, or if the user
    supplied a name and a domain that agree well enough to name a subject.

    An unregistered company is the normal case, not a failure — the registry is
    small by design. What is NOT acceptable is having neither.
    """
    if not identity:
        return False
    if identity.get("entity_resolved"):
        return True
    return identity.get("status") == "UNKNOWN" and bool(
        identity.get("fallback_subject"))


def _missing_families(counts: dict) -> list:
    """Which mandatory roles have nothing behind them, in repair priority."""
    missing = []
    if not set(counts) & set(_OFFICIAL_IDENTITY_ROLE):
        missing.append(IDENTITY)
    if not set(counts) & set(_DIRECTION_ROLE):
        missing.append(STRATEGY)
    if not set(counts) & set(_MARKET_ROLE):
        missing.append(CUSTOMERS)
    if PRODUCT not in counts:
        missing.append(PRODUCT)
    return missing


_FAMILY_SEARCH_HINTS = {
    IDENTITY: ("about", "company", "corporate information"),
    PRODUCT: ("products", "platform", "solutions", "documentation"),
    CUSTOMERS: ("customers", "case studies", "partners", "success stories"),
    INVESTOR: ("investor relations", "earnings", "annual report"),
    STRATEGY: ("newsroom", "press", "blog", "leadership"),
}


def _retry_plan(missing_families, failures, attempt) -> dict:
    """One targeted second pass at the specific gap — never a blind re-run.

    Re-running discovery unchanged fails identically; that is the definition of
    the same input. A retry is only worth a user's time if it looks somewhere
    new, so the plan names the missing family and excludes every URL that has
    already failed.
    """
    exhausted = attempt >= MAX_DISCOVERY_ATTEMPTS
    avoid = sorted({f.get("url") or f.get("candidate_id", "")
                    for f in failures if (f.get("url") or
                                          f.get("candidate_id"))})
    return {
        "available": bool(missing_families) and not exhausted,
        "exhausted": exhausted,
        "attempt": attempt,
        "max_attempts": MAX_DISCOVERY_ATTEMPTS,
        "target_families": list(missing_families),
        "look_for": [hint for family in missing_families
                     for hint in _FAMILY_SEARCH_HINTS.get(family, ())],
        "avoid_urls": avoid,
    }


def _material_level(*, total, families, units, failed, expects=None,
                    readable=1.0) -> str:
    """How much this evidence can honestly carry: 'full', 'limited', 'none'.

    Deliberately independent of whether a retry is worth running. Those are
    different questions, and conflating them is a real trap: treating "worth
    one more look" as "refuse to say anything" would suppress a genuinely
    useful three-family view, which is its own kind of dishonesty.
    """
    # Evidence that was retrieved but not understood cannot carry a report at
    # any level. Producing nothing and saying nothing is the failure this
    # replaces: the reader deserves "we could not read this company's
    # evidence", which is a finding they can act on.
    if readable < MIN_ENGLISH_SHARE:
        return "none"
    if not failed:
        return "full"
    # A small business genuinely has fewer distinct subjects to present, so the
    # limited floor moves with the mode too — otherwise the mode would relax
    # the full standard and then refuse at the limited one, which is the same
    # refusal wearing a different number.
    min_units_limited = MIN_SLIDE_UNITS_LIMITED
    if expects and expects.get("min_slide_units", MIN_SLIDE_UNITS) < \
            MIN_SLIDE_UNITS:
        min_units_limited = min(MIN_SLIDE_UNITS_LIMITED,
                                expects["min_slide_units"] - 1)
    if (total >= MIN_SOURCES_LIMITED
            and len(families) >= MIN_FAMILIES_LIMITED
            and len(units) >= min_units_limited):
        return "limited"
    return "none"


def _decide(*, identity_ok, material, retry_plan) -> str:
    if not identity_ok:
        return IDENTITY_UNRESOLVED
    if material == "full":
        return READY_FOR_FULL_REPORT
    # Short of a full report and there is somewhere new to look: say so, so the
    # caller retries against the specific gap rather than re-running blind.
    if retry_plan["available"]:
        return RETRYABLE_EVIDENCE_GAP
    return (READY_FOR_LIMITED_REPORT if material == "limited"
            else INSUFFICIENT_EVIDENCE)


# --- reader-facing explanation ------------------------------------------------
_STATE_HEADLINE = {
    READY_FOR_FULL_REPORT: "There is enough public evidence for a full "
                           "briefing.",
    READY_FOR_LIMITED_REPORT: "There is enough public evidence for a limited "
                              "briefing, but not a full one.",
    RETRYABLE_EVIDENCE_GAP: "Some kinds of evidence are missing, and there "
                            "are places left to look.",
    INSUFFICIENT_EVIDENCE: "There is not enough public evidence to build a "
                           "briefing on this company.",
    IDENTITY_UNRESOLVED: "The company could not be identified confidently "
                         "enough to analyse.",
}

_FAMILY_LABEL = {
    IDENTITY: "official company description",
    PRODUCT: "product or platform pages",
    CUSTOMERS: "customers, use cases or partnerships",
    INVESTOR: "investor or earnings material",
    STRATEGY: "strategy, newsroom or leadership statements",
    INDEPENDENT: "independent or third-party coverage",
    COMMERCIAL: "pricing or commercial terms",
}


def explain(assessment: dict) -> dict:
    """Plain-language findings for a business reader.

    Deliberately free of family identifiers, state names and check names — a
    reader needs to know what was found, what was missing, and what to do, not
    the vocabulary the gate uses internally.
    """
    found = [_FAMILY_LABEL.get(f, f) for f in assessment["families"]]
    missing = [_FAMILY_LABEL.get(f, f) for f in assessment["missing_families"]]
    blockers = [c["detail"] for c in assessment["checks"]
                if not c["ok"] and c["name"] not in ("identity_resolved",)]
    return {
        "headline": _STATE_HEADLINE[assessment["state"]],
        "found": found,
        "missing": missing,
        "blockers": blockers,
        "source_count": assessment["document_count"],
        "can_retry": assessment["retry_plan"]["available"],
    }
