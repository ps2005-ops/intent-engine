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

from . import demand_extraction as DX
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

#: Where a source class this table does not recognise lands. The least
#: independent role, deliberately: under-weighting a document whose publisher
#: we cannot name costs a little corroboration, and over-weighting one costs
#: the independence count that decides whether a thesis may be asserted.
UNKNOWN_PUBLISHER_ROLE = "company_owned"

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
    provenance_only: int = 0
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
        self.provenance_only += other.provenance_only
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
                "provenance_only": self.provenance_only,
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


#: a corporate entity named in the body, used to tell "this document is about
#: somebody else" apart from "this document names nobody"
_OTHER_ENTITY = re.compile(
    r"\b([A-Z][A-Za-z&.\-]*(?:\s+[A-Z][A-Za-z&.\-]*){0,3})\s+"
    r"(?:Inc|Corp|Corporation|Ltd|Limited|LLC|PLC|N\.V\.|S\.A\.)\b")

#: corporate suffixes, stripped before two names are compared as the same
#: company. "Caterpillar" and "Caterpillar Inc." are one subject.
_SUFFIX = re.compile(
    r"\b(inc|corp|corporation|company|co|ltd|limited|llc|plc|sa|s\.a|nv|n\.v|"
    r"ag|gmbh|holdings|group)\b\.?", re.I)

NAMED = "named"                  # the document names the subject
UNNAMED = "unnamed"              # the document names no company at all
OTHER_NAMED = "other_named"      # it names other companies and not this one


def _stem(name: str) -> str:
    """A company name reduced to what makes it that company."""
    return " ".join(_SUFFIX.sub(" ", name or "").split()).strip(" ,.").lower()


def subject_binding(text: str, aliases: Sequence[str]) -> str:
    """How firmly this document is bound to the subject.

    THREE ANSWERS, NOT TWO, and the middle one cost real evidence to learn.
    A first pass rejected any document that did not name the subject, and the
    first thing it threw away was Caterpillar's Q2 earnings exhibit — the
    single most valuable document in the corpus — because a tables-only
    exhibit names no company anywhere in 13,000 characters. It states
    "Second-quarter 2026 sales and revenues increased 24% to $20.5 billion"
    and never says whose.

    So a document that names NOBODY is attributed on retrieval provenance and
    carries that as a stated limitation. Only a document that names other
    corporate entities while never naming the subject is refused, because
    that is the shape of a mis-resolved registrant rather than of a terse
    exhibit.

    A SUBSTRING IS NOT A NAMING, AND THAT IS HOW THE GUARD WAS BEATEN
    ----------------------------------------------------------------
    This check was added because discovery for "Linear" resolved to a mining
    registrant, and it did not work: the registrant is "Linear Minerals
    Corp.", the alias "Linear" occurs in it twenty-six times, and every one of
    those occurrences satisfied a plain substring test. So the filing was
    accepted as being about the software company, and produced two beliefs —
    partnerships and contract awards — that were correctly extracted, properly
    cited, and about a different company entirely.

    No rule about neighbouring words can fix that on its own, because the
    filing is not being coy: it introduces "Linear Minerals Corp." and then
    says "Linear" for the rest of forty thousand characters — "the Linear
    shareholders", "Linear transferred the assets". Those are real, standalone
    uses of the subject's exact name, referring to a different company.

    What separates the two cases is whether the subject is present as a
    COMPANY. A document that names "Microsoft Corporation" has named the
    subject however many product names begin with the word Microsoft. A
    document that names "Linear Minerals Corp." and never "Linear" as a
    corporate entity has introduced a longer-named company that the bare word
    now most plausibly refers to, and attributing its events to the subject is
    the fabrication this guard exists to stop. So a name collision is refused
    rather than resolved — the same choice the founder side makes when two
    dossiers claim one company.
    """
    body = text or ""
    stems = {s for s in (_stem(a) for a in aliases if a) if s}
    entities = [_stem(m.group(1)) for m in _OTHER_ENTITY.finditer(body)]

    collision = False
    for entity in entities:
        if _is_subject(entity, stems):
            return NAMED           # named as a company, in its own right
        collision = collision or _extends(entity, stems)
    if collision:
        return OTHER_NAMED

    # No collision, so a plain naming is a naming. The boundaries matter and
    # a bare substring did not have them: "Linear" should not be found inside
    # "linearity", and the short-alias floor in `_aliases_for` was carrying
    # that on its own.
    for alias in aliases:
        if alias and re.search(r"\b" + re.escape(alias) + r"\b", body, re.I):
            return NAMED
    return OTHER_NAMED if entities else UNNAMED


#: Families whose actor is, by definition, the company whose results these
#: are. Everything else may legitimately have a third party as the actor of
#: the sentence while still being evidence about the subject — a law firm
#: represents a company in ITS bond issuance, a regulator schedules a hearing
#: about ITS merger — so the check below is not applied to them. Widening it
#: would refuse real evidence to fix a narrower problem.
OWN_RESULTS_FAMILIES = frozenset({ME.EARNINGS_SURPRISE, ME.GUIDANCE_REVISION})


def reports_own_results(text: str, action: str, aliases: Sequence[str]) -> bool:
    """Whether the SUBJECT is the one whose results this sentence reports.

    NAMING THE SUBJECT IS NOT THE SAME AS BEING ABOUT IT
    -----------------------------------------------------
    `subject_binding` answers "does this document name the company", and it
    has to, because a document that names nobody cannot be attributed. It
    cannot answer "is the company the one this event happened to", and the
    difference produced a live belief:

        "PayPal tops Q2 estimates and raises full-year forecast amid Stripe
         takeover bid"

    filed under `stripe`, typed GUIDANCE_REVISION. Stripe IS named, so binding
    passed. But the estimates topped and the forecast raised are PayPal's;
    Stripe is the object of a takeover bid mentioned afterwards. The engine
    recorded a guidance revision for a company that had not issued one.

    THE TEST IS POSITION, AND ONLY FOR RESULTS
    -------------------------------------------
    A company reporting its own numbers is named before the verb that reports
    them. So for the results families the subject must appear BEFORE the
    action span; if it appears only after, the numbers belong to whoever came
    first and this sentence is about them.

    Deliberately not applied to the action families. "A&O Shearman represents
    Sasol Limited in its USD750 million bond issuance" puts the subject after
    the verb and is still real evidence about Sasol's financing — refusing it
    would be a worse error than the one being fixed. Nor is the rule "the
    first company named wins", which would throw away "regulators set a
    hearing for the Dominion Energy, NextEra merger", where NextEra is a
    genuine party to the event.
    """
    if not action:
        return True
    body = text or ""
    lowered = body.lower()
    at = lowered.find(action.lower())
    if at < 0:
        return True
    named = False
    for alias in aliases:
        if not alias:
            continue
        if re.search(r"\b" + re.escape(alias) + r"\b", body[:at], re.I):
            return True
        named = named or bool(
            re.search(r"\b" + re.escape(alias) + r"\b", body, re.I))
    # The subject appears nowhere in the sentence, so there is no position to
    # test and this function has learned nothing. Fails OPEN, like a missing
    # action span: on the live path `subject_binding` has already established
    # that the document names the subject, so this only arises for a caller
    # working from a name it could not match -- an accented or multi-word
    # form reconstructed from a slug, say -- and refusing on that would drop
    # evidence over a spelling.
    return not named


def _is_subject(entity: str, stems: set) -> bool:
    """Whether a corporate name found in the body IS the subject.

    Matched on the TAIL, because `_OTHER_ENTITY` may capture up to four
    capitalised words before the name itself — a press release datelined
    "SANTA CLARA, Calif. — NVIDIA Corporation" yields "Calif NVIDIA", which is
    still NVIDIA. The tail is the company; what precedes it is context.
    """
    words = entity.split()
    return any(entity == s or words[-len(s.split()):] == s.split()
               for s in stems if s and len(s.split()) <= len(words))


def _extends(entity: str, stems: set) -> bool:
    """Whether a corporate name is the subject's name plus more of its own.

    "Linear Minerals" extends "Linear". "Microsoft Corporation" does not
    extend "Microsoft" — the suffix is already gone by the time we compare.
    """
    words = entity.split()
    return any(len(s.split()) < len(words)
               and words[:len(s.split())] == s.split()
               for s in stems if s)




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
        binding = (subject_binding(evidence_text_of(obs), aliases)
                   if aliases else NAMED)
        if binding == OTHER_NAMED:
            stats.subject_mismatch += 1
            stats.note_reason("subject_not_named_in_source")
            rejected.append(
                f"subject not named in source: {_field(obs, 'source')[:70]!r}")
            continue
        if binding == UNNAMED:
            stats.provenance_only += 1
        source = _field(obs, "source", "url", "source_url", "citation")
        observed = _field(obs, "observed_at", "date", "published_at",
                          "as_of") or as_of
        source_class = _source_class_of(obs)
        author = _field(obs, "source_author", "author", "publisher")
        # AN UNRECOGNISED CLASS FAILS TOWARDS THE COMPANY, NOT AWAY FROM IT.
        # This defaulted to `independent_reporting` — the most independent
        # role in the table, and the one carrying the highest reliability.
        # A class this map has not seen is not evidence of independence; it is
        # evidence that we do not know who published it, and treating the two
        # alike is how a company's own document acquires a third party's
        # weight and inflates the corroboration count behind a thesis.
        role = (roles or {}).get(source_class) or _SOURCE_CLASS_TO_ROLE.get(
            source_class, UNKNOWN_PUBLISHER_ROLE)

        candidates = extract_candidates(obs, stats=stats)
        stats.candidates += len(candidates)
        kept = 0
        for candidate in candidates:
            if kept >= MAX_ITEMS_PER_OBSERVATION:
                break
            etype, action, _obj = EP.explain(candidate.text)
            demand = None
            if etype is None:
                # THE DEMAND SECOND OPINION. The commercial-event families
                # model an ACTION on an OBJECT, and a demand sentence often
                # has neither in that shape: "Strong order rates and a
                # growing backlog reflect broadening momentum" states a
                # commercial fact and no family can express it.
                #
                # `demand_extraction` asks a different set of questions —
                # object, standing, subject, role — and refuses with the
                # reason that applies, so a wrong-role sentence ("we placed
                # orders for new equipment") is refused as WRONG_ROLE rather
                # than admitted as customer demand. Its refusal reason is
                # recorded here instead of `no_commercial_event`, which is
                # what 1,059 candidates a cycle used to collapse into.
                demand = DX.read(candidate.text, aliases=aliases)
                if demand.admitted:
                    etype = ME.DEMAND_SIGNAL
            etype = etype or default_type
            if etype is None:
                stats.unclassifiable += 1
                stats.note_reason(
                    f"demand_{demand.reason.lower()}" if demand is not None
                    and demand.reason else "no_commercial_event")
                rejected.append(f"unclassifiable: {candidate.text[:60]!r}")
                continue
            # Naming the subject got this far; being the company the results
            # belong to is a second question, and only the results families
            # can answer it from word order. See `reports_own_results`.
            if (aliases and etype in OWN_RESULTS_FAMILIES
                    and not reports_own_results(candidate.text, action,
                                                aliases)):
                stats.subject_mismatch += 1
                stats.note_reason("results_belong_to_another_company")
                rejected.append(
                    f"results are another company's: {candidate.text[:60]!r}")
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
                    limitations=_limitations(candidate, binding))
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


def _limitations(candidate, binding: str) -> Tuple[str, ...]:
    """What a reader has to know about this fact to weigh it correctly.

    The provenance note is the honest half of the three-way binding above.
    When a document never names the company, the claim that it is ABOUT that
    company rests on the retrieval that fetched it — which is a real basis and
    a weaker one, and the reader is told so rather than left to assume the
    document said it.
    """
    out = [f"single sentence at offset {candidate.offset} of the source "
           f"document"]
    if binding == UNNAMED:
        out.append("the source document does not name the subject anywhere; "
                   "attribution rests on retrieval provenance, not on the "
                   "document's own words")
    return tuple(out)


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
