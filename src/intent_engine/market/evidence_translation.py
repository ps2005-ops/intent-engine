"""Turn retrieved observations into MicroEvidence — or refuse, and say why.

WHERE THE EVIDENCE COMES FROM
-----------------------------
`market.evidence` wires Founder Intelligence's ingestion into the daily sweep:
it discovers public sources, retrieves them, and derives dated observations
carrying a source class. That pipeline is production-verified and this module
does not duplicate it.

WHY THE UNIT IS A SENTENCE
--------------------------
It used to be the whole excerpt. `classify_type` matched one blob as one
observation, so a document containing an event and four paragraphs of
boilerplate classified as whatever the blob looked like on average — which is
nothing. Measured on Microsoft's real Q4 earnings exhibit: scanning the blob
found no event; scanning the same text sentence by sentence found
EARNINGS_SURPRISE on "we exceeded expectations across revenue, operating
income and earnings per share".

So the excerpt is segmented by the canonical extractor, each sentence is
classified independently, and the sentence that carried the type becomes the
evidence `fact`. A fact is now a thing a document actually said, in its own
words, with an offset pointing at where it said it — not a 280-character
prefix that happened to contain a keyword.

CLASSIFICATION IS STILL CONSERVATIVE
------------------------------------
An observation becomes a typed evidence item only when a sentence in it
actually carries the event. Everything else is rejected WITH A REASON.
Guessing a type from the source class would put `EARNINGS_SURPRISE` on a blog
post, and a mistyped item is worse than a missing one because it updates the
wrong belief at full confidence.

CONTRADICTION ROLE IS NEVER GUESSED
-----------------------------------
Whether an item supports or contradicts a belief depends on the belief, not on
the item. `translate` returns NEUTRAL unless a caller supplies the mapping,
and `beliefs.update` ignores NEUTRAL items. An engine that inferred "this
sounds negative, so it contradicts" would be doing sentiment analysis and
calling it inference.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from intent_engine.strategic_intelligence import evidence_text as EText

from . import event_patterns as EP
from . import micro_evidence as ME

TRANSLATION_VERSION = "evidence_translation.v2"

# Founder Intelligence source classes → the independence roles this layer
# scores with. Mirrors `market.evidence._SOURCE_CLASS_TO_KIND` so an item does
# not get reclassified on the way through.
_SOURCE_CLASS_TO_ROLE = {
    "investor_material": "regulatory_filing",
    "executive_statement": "executive_statement",
    "independent_reporting": "independent_reporting",
    "analyst_coverage": "analyst_coverage",
    "customer_voice": "customer_voice",
    "competitor_statement": "competitor_statement",
    "company_owned": "company_owned",
    "government_statistic": "government_statistic",
}

# Hosted evidence `kind` → source class, for rows that carry a kind instead.
# `market.daily._KIND_TO_SOURCE_CLASS` is the same mapping; duplicated here
# rather than imported because `daily` imports the hosted budget and the
# predictions package, and the translator must stay loadable without them.
_KIND_TO_SOURCE_CLASS = {
    "filing": "investor_material", "earnings": "investor_material",
    "investor": "investor_material", "news": "independent_reporting",
    "press_coverage": "independent_reporting", "analyst": "analyst_coverage",
    "review": "customer_voice", "customer": "customer_voice",
    "competitor": "competitor_statement", "product": "company_owned",
}

#: at most this many typed items from one observation. A press release can
#: legitimately state six events; a scraped index page that slipped the
#: furniture gate must not become forty.
MAX_ITEMS_PER_OBSERVATION = 6


@dataclass
class TranslationStats:
    """What the translator saw, kept and threw away — and why.

    Counts, never bodies. The operator needs to know that 100% of candidates
    were dropped as furniture; they do not need the furniture.
    """
    observations: int = 0
    candidates: int = 0
    translated: int = 0
    furniture_rejected: int = 0
    duplicates: int = 0
    unclassifiable: int = 0
    build_rejected: int = 0
    subject_mismatch: int = 0
    by_type: Dict[str, int] = field(default_factory=dict)
    by_reason: Dict[str, int] = field(default_factory=dict)

    def note_reason(self, reason: str) -> None:
        self.by_reason[reason] = self.by_reason.get(reason, 0) + 1

    @property
    def translation_rate(self) -> float:
        if not self.candidates:
            return 0.0
        return round(self.translated / float(self.candidates), 4)

    def merge(self, other: "TranslationStats") -> None:
        self.observations += other.observations
        self.candidates += other.candidates
        self.translated += other.translated
        self.furniture_rejected += other.furniture_rejected
        self.duplicates += other.duplicates
        self.unclassifiable += other.unclassifiable
        self.build_rejected += other.build_rejected
        self.subject_mismatch += other.subject_mismatch
        for key, value in other.by_type.items():
            self.by_type[key] = self.by_type.get(key, 0) + value
        for key, value in other.by_reason.items():
            self.by_reason[key] = self.by_reason.get(key, 0) + value

    def as_dict(self) -> dict:
        return {"observations": self.observations,
                "candidate_sentences": self.candidates,
                "translated": self.translated,
                "furniture_rejected": self.furniture_rejected,
                "duplicates": self.duplicates,
                "unclassifiable": self.unclassifiable,
                "build_rejected": self.build_rejected,
                "subject_mismatch": self.subject_mismatch,
                "translation_rate": self.translation_rate,
                "by_type": dict(sorted(self.by_type.items())),
                "by_reason": dict(sorted(self.by_reason.items()))}


def evidence_text_of(obs: Any) -> str:
    """The text this observation actually EVIDENCES, not how it was read.

    Order matters and is the second half of the measured defect.
    `_observation_rows` sends both a `summary` — the strategic reading, a
    template sentence that can never contain an event — and `evidence_text`,
    the document's own words. Reading `summary` first, which the old `_field`
    order did, meant every observation was structurally unclassifiable however
    good the classifier got.
    """
    return _field(obs, "evidence_text", "excerpt", "body", "text_content",
                  "fact", "text", "summary", "content")


def extract_candidates(obs: Any, *, stats: Optional[TranslationStats] = None
                       ) -> List[EText.Candidate]:
    """Bounded candidate sentences from one observation, with lineage.

    Segmentation, furniture suppression and deduplication all come from the
    canonical extractor, so the market translator and the founder surfaces
    cannot disagree about what a document said.
    """
    text = evidence_text_of(obs)
    if not text:
        return []
    source_id = _field(obs, "source", "url", "source_url", "citation",
                       "source_id")
    origin = _field(obs, "origin", "final_url") or source_id
    out: List[EText.Candidate] = []
    seen = set()
    for offset, sentence in EText.split_sentences(text):
        clean = " ".join(sentence.split())
        reason = EText.furniture_reason(clean)
        if reason:
            if stats is not None:
                stats.furniture_rejected += 1
                stats.note_reason(reason)
            continue
        key = EText._dedupe_key(clean)
        if key in seen:
            if stats is not None:
                stats.duplicates += 1
                stats.note_reason("duplicate_sentence")
            continue
        seen.add(key)
        out.append(EText.Candidate(text=clean, offset=offset, index=len(out),
                                   source_id=source_id, origin=origin))
    return out


def classify_type(text: str) -> Optional[str]:
    """The evidence type this text evidences, or None.

    Kept as the module's public name because the founder side and the tests
    call it, but it now delegates to the pattern families and, for a multi-
    sentence blob, returns the type of the FIRST sentence that carries one
    rather than trying to characterise the whole passage.
    """
    blob = " ".join((text or "").split())
    if not blob:
        return None
    direct = EP.classify_sentence(blob)
    if direct:
        return direct
    for _, sentence in EText.split_sentences(blob):
        etype = EP.classify_sentence(" ".join(sentence.split()))
        if etype:
            return etype
    return None


def _mentions_subject(text: str, aliases: Sequence[str]) -> bool:
    low = (text or "").lower()
    return any(a for a in aliases if a and a.lower() in low)


def translate(observations: Sequence[Any], *, subject_company: str,
              as_of: str, default_type: Optional[str] = None,
              roles: Optional[Dict[str, str]] = None,
              stats: Optional[TranslationStats] = None,
              subject_aliases: Sequence[str] = ()
              ) -> Tuple[List[ME.MicroEvidence], List[str]]:
    """Convert observations into evidence. Returns (evidence, rejections).

    Rejections are returned rather than logged and forgotten: a sweep that
    silently drops nine observations in ten looks identical to a sweep that
    found nothing, and those are very different problems.

    `subject_aliases` is the company's own names. When supplied, a document
    that never names the subject cannot produce evidence about it. That guard
    is not theoretical: discovery for "Linear" resolved to a lithium
    exploration registrant, and its filings yielded six perfectly-classified
    joint ventures and option agreements — real events, real sources, real
    sentences, all attributed to a software company that had nothing to do
    with any of them. Correct extraction plus wrong subject is still a
    fabricated claim, and it is the most credible kind because every
    individual part of it checks out.
    """
    out: List[ME.MicroEvidence] = []
    rejected: List[str] = []
    stats = stats if stats is not None else TranslationStats()
    seen_facts = set()
    aliases = [a for a in subject_aliases if a]

    for obs in observations:
        stats.observations += 1
        if aliases and not _mentions_subject(evidence_text_of(obs), aliases):
            stats.subject_mismatch += 1
            stats.note_reason("subject_not_named_in_source")
            rejected.append(
                f"subject not named in source: {_field(obs, 'source')[:70]!r}")
            continue
        source = _field(obs, "source", "url", "source_url", "citation")
        observed = _field(obs, "observed_at", "date", "published_at",
                          "as_of") or as_of
        source_class = _source_class_of(obs)
        author = _field(obs, "source_author", "author", "publisher")
        role = (roles or {}).get(source_class) or _SOURCE_CLASS_TO_ROLE.get(
            source_class, "independent_reporting")

        candidates = extract_candidates(obs, stats=stats)
        stats.candidates += len(candidates)
        kept = 0
        for candidate in candidates:
            if kept >= MAX_ITEMS_PER_OBSERVATION:
                break
            etype = EP.classify_sentence(candidate.text) or default_type
            if etype is None:
                stats.unclassifiable += 1
                stats.note_reason("no_commercial_event")
                rejected.append(f"unclassifiable: {candidate.text[:60]!r}")
                continue
            key = (etype, EText._dedupe_key(candidate.text))
            if key in seen_facts:
                stats.duplicates += 1
                stats.note_reason("duplicate_fact")
                continue
            seen_facts.add(key)
            try:
                item = ME.build(
                    subject_company=subject_company, actor=subject_company,
                    evidence_type=etype,
                    observed_at=_date_or(observed, as_of),
                    available_at=_date_or(observed, as_of),
                    source=source or candidate.origin or candidate.source_id,
                    fact=candidate.text, source_author=author,
                    source_role=role, reliability=_reliability(role),
                    relevance=0.6, contradiction_role=ME.NEUTRAL,
                    limitations=(f"single sentence at offset "
                                 f"{candidate.offset} of the source "
                                 f"document",))
            except ME.EvidenceRejected as exc:
                stats.build_rejected += 1
                stats.note_reason("evidence_rejected")
                rejected.append(str(exc))
                continue
            out.append(item)
            kept += 1
            stats.translated += 1
            stats.by_type[etype] = stats.by_type.get(etype, 0) + 1

        if not candidates:
            stats.note_reason("no_candidate_sentence")
            rejected.append(
                f"no candidate sentence: {evidence_text_of(obs)[:60]!r}")
    return out, rejected


def translate_with_stats(observations: Sequence[Any], **kwargs
                         ) -> Tuple[List[ME.MicroEvidence], List[str],
                                    TranslationStats]:
    """`translate`, plus the counts an operator needs to see the drop rate."""
    stats = TranslationStats()
    items, rejected = translate(observations, stats=stats, **kwargs)
    return items, rejected, stats


def _source_class_of(obs: Any) -> str:
    explicit = _field(obs, "source_class", "class")
    if explicit:
        return explicit
    kind = _field(obs, "kind").lower()
    return _KIND_TO_SOURCE_CLASS.get(kind, "company_owned" if kind
                                     else "independent_reporting")


def _field(obj: Any, *names: str) -> str:
    """Read the first present attribute or key.

    Tries several names because the two stores disagree: retrieved documents
    carry `text_content` while observations carry `text`. That exact mismatch
    made both founder extractors blind to a retrieved 10-Q last cycle, so the
    lookup is deliberately tolerant rather than assuming one shape.
    """
    for name in names:
        value = None
        if isinstance(obj, dict):
            value = obj.get(name)
        else:
            value = getattr(obj, name, None)
        if value:
            return str(value)
    return ""


def _reliability(role: str) -> float:
    return {"regulatory_filing": 0.9, "government_statistic": 0.9,
            "independent_reporting": 0.75, "analyst_coverage": 0.6,
            "customer_voice": 0.6, "competitor_statement": 0.55,
            "supplier_statement": 0.55, "executive_statement": 0.5,
            "company_owned": 0.45}.get(role, 0.5)


def _date_or(value: str, fallback: str) -> str:
    from datetime import date
    try:
        date.fromisoformat((value or "")[:10])
        return value[:10]
    except (TypeError, ValueError):
        return fallback[:10]
