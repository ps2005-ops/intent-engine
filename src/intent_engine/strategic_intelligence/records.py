"""V1.2 strategic-intelligence records.

These are structured objects, deliberately NOT flattened into generic
strings. Each carries the reasoning and provenance a serious reader needs to
judge whether a conclusion is defensible.

Every human-facing conclusion is typed by how strongly it is warranted:

    direct_observation   — stated plainly in an approved source
    supported_inference  — a small, defensible step from observation(s)
    strategic_hypothesis — an outside-in bet that evidence supports but does
                            not prove
    comparable_pattern   — a historical/market analogue and its mechanism
    counter_evidence     — evidence pointing the other way
    evidence_gap         — what is unknown and what would resolve it
    decision_implication — the decision the uncertainty actually affects
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

EVIDENCE_KINDS = (
    "direct_observation", "supported_inference", "strategic_hypothesis",
    "comparable_pattern", "counter_evidence", "evidence_gap",
    "decision_implication",
)

# How a source that fed an observation is classified. The report must show
# which class(es) support each inference so a one-sided read is visible.
SOURCE_CLASSES = (
    "company_owned", "executive_statement", "investor_material",
    "customer_voice", "competitor", "independent_reporting",
    "historical_pattern", "unavailable_or_failed",
)

OBSERVATION_TYPES = (
    "messaging", "product_surface", "buyer_segment", "channel_distribution",
    "infrastructure_platform", "monetization_ecosystem", "organizational",
    "market_context",
)

CONFIDENCE_LEVELS = ("speculative", "low", "moderate", "high")

# How a claim is known. Deliberately written the way a person would say it,
# because these reach the page: a reader deciding what to do with a claim needs
# to know whether the company asserted it, someone outside observed it, or the
# analysis inferred it from a historical pattern. Ordered weakest to strongest.
PROVENANCE_LEVELS = (
    "pattern-supported",        # a historical analogue, not this company
    "inferred",                 # combined from evidence, stated by nobody
    "company-stated",           # the company said it about itself
    "customer-observed",        # its customers described it
    "independently corroborated",   # someone outside the company observed it
)

# How a piece of evidence relates to a hypothesis. Assigned per hypothesis, so
# the same observation can support one and contradict another — but it may not
# be BOTH support and contradiction for a single hypothesis without an explicit
# dual-role explanation.
EVIDENCE_ROLES = (
    "direct_support", "indirect_support", "contradiction",
    "alternative_explanation", "contextual_only", "weak_or_irrelevant",
    "duplicate", "stale", "unresolved",
)


class StrategicError(ValueError):
    """A strategic record violated its contract."""


def _require(cond, message):
    if not cond:
        raise StrategicError(message)


@dataclass
class StrategicObservation:
    """Something an approved source actually says (or a small, explicit
    inference from it). ``directly_observed`` distinguishes the two."""
    observation_id: str
    text: str
    observation_type: str
    source_refs: list = field(default_factory=list)   # provenance dicts
    confidence: str = "moderate"
    freshness: str = "CURRENT"
    directly_observed: bool = True
    # controlled-vocabulary signal tags this observation carries; the reasoning
    # engine matches these against pattern qualifying/disconfirming signals.
    signals: tuple = ()
    source_class: str = "company_owned"
    # human-facing evidence payload (faithful paraphrase or short excerpt)
    excerpt: str = ""
    source_title: str = ""
    origin: str = ""
    date: str = ""
    # strategic-quality metadata (filled by extraction)
    strategic_signal: str = ""      # one-line strategic meaning, not a title
    relevance: str = ""             # why this matters to the analysis
    entity: str = ""                # linked product/project/entity
    weak: bool = False              # title-only / generic marketing → weak
    evidence_quality: str = "strong"  # strong | weak
    #: signal -> the sentence IN THIS DOCUMENT that evidenced it.
    #:
    #: `excerpt` is one passage chosen for the whole document, so on a source
    #: carrying many signals it is the right evidence for at most one of them.
    #: A reading that qualified on signal X must be able to quote the words
    #: that produced X, not the document's opening. See
    #: `observations.signal_spans` for the measured case this comes from.
    signal_spans: dict = field(default_factory=dict)

    def validate(self) -> None:
        _require(self.observation_type in OBSERVATION_TYPES,
                 f"unknown observation_type {self.observation_type!r}")
        _require(self.source_class in SOURCE_CLASSES,
                 f"unknown source_class {self.source_class!r}")
        _require(self.confidence in CONFIDENCE_LEVELS,
                 f"unknown confidence {self.confidence!r}")
        _require(bool(self.text.strip()), "observation text is required")

    @property
    def kind(self) -> str:
        return "direct_observation" if self.directly_observed \
            else "supported_inference"

    def as_dict(self) -> dict:
        d = asdict(self)
        d["signals"] = list(self.signals)
        d["kind"] = self.kind
        return d


@dataclass
class ComparablePattern:
    """A curated, sourced historical/market transition and its mechanism.
    Loaded from the auditable library — never invented at report time."""
    pattern_id: str
    name: str
    description: str
    mechanism: str
    historical_examples: list          # [{name, note, source}]
    when_it_applies: str
    when_it_does_not_apply: str
    source_refs: list = field(default_factory=list)
    confidence: str = "moderate"
    qualifying_signals: tuple = ()
    #: Signals WITHOUT WHICH THIS PATTERN MAY NOT FIRE, whatever the threshold.
    #: A qualifying signal is evidence that a reading is plausible; a required
    #: one is the reading's subject. `services_to_product` needs
    #: `services_motion` in the same way "services → product" needs services:
    #: matching two of three let an API page and a product page assert that a
    #: company "delivers work alongside customers", which no evidence in the
    #: run had said. Empty for every pattern whose qualifying signals are
    #: genuinely interchangeable.
    required_signals: tuple = ()
    #: AT LEAST ONE of these must be present. Where `required_signals` names a
    #: single subject the reading is about, this names a set of alternative
    #: CAUSAL MECHANISMS, any one of which would make the reading true — the
    #: reading may not fire on vocabulary alone when none of them is observed.
    #:
    #: `buyer_concentration_exposure` needs one in the way "depends on
    #: regulated buyers" needs a reason to be true: a separate estate built for
    #: those buyers, an authorization that gates the purchase, a procurement
    #: vehicle, or a disclosed exposure. Without this, "regulated industries"
    #: copy plus a case-studies page was enough, and HubSpot and Snowflake —
    #: one of which has no public-sector mechanism at all — were handed the
    #: same conclusion.
    required_any_signals: tuple = ()
    disconfirming_signals: tuple = ()
    #: Disconfirming signals strong enough that this reading may not be
    #: the PRIMARY one while they are present. It stays in the portfolio
    #: as a secondary hypothesis. Must be a subset of
    #: `disconfirming_signals`, so a pattern cannot be blocked by
    #: something it never declared as arguing against it.
    blocking_signals: tuple = ()
    limitations: str = ""

    def validate(self) -> None:
        _require(bool(self.pattern_id), "pattern_id required")
        _require(bool(self.mechanism.strip()), "pattern mechanism required")
        _require(len(self.historical_examples) >= 1,
                 f"pattern {self.pattern_id} needs >=1 cited example")
        _require(bool(self.qualifying_signals),
                 f"pattern {self.pattern_id} needs qualifying signals")
        for signal in self.required_signals:
            _require(signal in self.qualifying_signals,
                     f"pattern {self.pattern_id} requires {signal!r}, which is "
                     "not one of its qualifying signals")
        for signal in self.required_any_signals:
            _require(signal in self.qualifying_signals,
                     f"pattern {self.pattern_id} requires one of "
                     f"{signal!r}, which is not one of its qualifying "
                     "signals")
        for signal in self.blocking_signals:
            _require(signal in self.disconfirming_signals,
                     f"pattern {self.pattern_id} is blocked by {signal!r}, "
                     "which is not one of its disconfirming signals")

    def as_dict(self) -> dict:
        d = asdict(self)
        d["qualifying_signals"] = list(self.qualifying_signals)
        d["required_signals"] = list(self.required_signals)
        d["required_any_signals"] = list(self.required_any_signals)
        d["disconfirming_signals"] = list(self.disconfirming_signals)
        d["blocking_signals"] = list(self.blocking_signals)
        return d


@dataclass
class MechanismEvidence:
    """The words that caused a reading, and where they came from.

    ONE OBJECT, EVERY SURFACE. A reading asserts a structural force —
    "switching cost rises", "the record moved" — and until now no surface
    could show what established it. Each surface had the hypothesis and the
    observation list and had to guess which excerpt was relevant; measured
    live, all of them guessed the document's opening paragraph.

    This is built once, where the pattern qualifies and the matched signal is
    still known, and read everywhere. A surface that renders a mechanism claim
    without rendering this is asserting something the reader cannot check.
    """
    signal: str            #: the mechanism signal that qualified the pattern
    label: str             #: what having it means, in a reader's words
    quote: str             #: the sentence in the source that evidenced it
    observation_id: str
    source_title: str = ""
    origin: str = ""
    source_class: str = "company_owned"

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class StrategicHypothesis:
    """An outside-in strategic bet. Carries the full reasoning apparatus a
    reader needs to accept, weaken, or reject it."""
    hypothesis_id: str
    title: str
    statement: str
    reasoning: str
    supporting_observation_ids: list
    counter_observation_ids: list
    alternative_explanations: list
    confidence: str
    confidence_reasons: list
    evidence_gaps: list
    decision_implications: list
    falsification_questions: list
    pattern_id: str = ""
    source_classes: tuple = ()
    why_now: str = ""                      # timeliness from recent evidence
    signal_trace: str = ""                 # internal signal detail (appendix)
    strongest_support_ids: tuple = ()      # curated, not the full dump
    strongest_counter_ids: tuple = ()
    comparables: tuple = ()                # comparison company names
    evidence_roles: tuple = ()             # [(observation_id, role), ...]
    # HOW this claim is known, in a reader's words. Confidence says how much to
    # trust it; provenance says what kind of thing it is. A reader who cannot
    # tell "the company says so" from "someone outside the company observed it"
    # cannot judge either one, and the two were previously indistinguishable on
    # the page.
    provenance: str = "company-stated"
    #: The mechanism(s) this reading qualified on, each with the sentence that
    #: evidenced it. Empty only for a pattern that declares no mechanism gate
    #: — those are the recorded debt, not a licence to hide reasoning.
    mechanism_evidence: tuple = ()

    def validate(self) -> None:
        _require(self.confidence in CONFIDENCE_LEVELS,
                 f"unknown confidence {self.confidence!r}")
        _require(self.provenance in PROVENANCE_LEVELS,
                 f"unknown provenance {self.provenance!r}")
        _require(bool(self.reasoning.strip()),
                 f"hypothesis {self.hypothesis_id} has no reasoning")
        _require(len(self.supporting_observation_ids) >= 1,
                 f"hypothesis {self.hypothesis_id} has no supporting evidence")
        _require(len(self.alternative_explanations) >= 1,
                 f"hypothesis {self.hypothesis_id} has no alternative "
                 "explanation")
        _require(len(self.confidence_reasons) >= 1,
                 f"hypothesis {self.hypothesis_id} has no confidence reasons")
        _require(len(self.decision_implications) >= 1,
                 f"hypothesis {self.hypothesis_id} has no decision implication")
        _require(len(self.falsification_questions) >= 1,
                 f"hypothesis {self.hypothesis_id} has no falsification test")
        # a single observation may not be BOTH support and contradiction for the
        # same hypothesis (the wholesale-copy failure); dual roles must be made
        # explicit via evidence_roles, never by listing an id in both.
        overlap = (set(self.supporting_observation_ids)
                   & set(self.counter_observation_ids))
        _require(not overlap, f"hypothesis {self.hypothesis_id}: observations "
                 f"{sorted(overlap)} appear as both support and contradiction")

    def as_dict(self) -> dict:
        d = asdict(self)
        for k in ("source_classes", "strongest_support_ids",
                  "strongest_counter_ids", "comparables", "evidence_roles"):
            d[k] = list(getattr(self, k))
        # `asdict` already recursed into these; restate as a list so every
        # surface reads the same shape whether it was handed the object or
        # its dict.
        d["mechanism_evidence"] = [
            m.as_dict() if hasattr(m, "as_dict") else dict(m)
            for m in self.mechanism_evidence]
        return d


@dataclass
class StrategicQuestion:
    """A founder-level question. Never a bare one-liner: it always carries why
    it matters, what triggered it, and which decision it affects."""
    question: str
    why_it_matters: str
    evidence_that_triggered_it: list
    possible_answer_paths: list
    decision_affected: str
    source_refs: list = field(default_factory=list)

    def validate(self) -> None:
        _require(bool(self.question.strip()), "question text required")
        _require(bool(self.why_it_matters.strip()),
                 "every question must explain why it matters")
        _require(bool(self.decision_affected.strip()),
                 "every question must name the decision it affects")

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class BlindSpot:
    """A responsible outside-in blind-spot hypothesis built from an observed
    tension — not a placeholder for missing private data."""
    blind_spot_id: str
    observed_tension: str
    why_it_may_matter: str
    counter_explanation: str
    evidence_needed: list
    decision_affected: str
    supporting_observation_ids: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class StrategicReport:
    """The composed strategic view. ``status`` is set by the quality gate."""
    company_name: str
    status: str
    thesis: dict                       # {view, transition, tension, why_care}
    shifts: list                       # [{title, evidence, date, source_class}]
    hypotheses: list                   # [StrategicHypothesis]
    patterns: list                     # [ComparablePattern]
    blind_spots: list                  # [BlindSpot]
    questions: list                    # [StrategicQuestion]
    evidence_gaps: list                # [str]
    decision_implications: list        # [{decision, options, evidence, watch}]
    observations: list                 # [StrategicObservation]
    source_class_coverage: dict = field(default_factory=dict)
    quality_findings: list = field(default_factory=list)
    limited_scope_accepted: bool = False
    evidence_graph: dict = field(default_factory=dict)
    agenda: list = field(default_factory=list)          # likely leadership items
    timeline: list = field(default_factory=list)        # chronological events
    source_library: dict = field(default_factory=dict)  # all sources, grouped
    analytics_events: list = field(default_factory=list)
    mental_model: dict = field(default_factory=dict)    # persistent company model
    surprises: list = field(default_factory=list)       # strategic surprises
    opportunities: list = field(default_factory=list)
    vulnerabilities: list = field(default_factory=list)
    underexamined_questions: list = field(default_factory=list)
    what_changed: list = field(default_factory=list)    # vs previous model
    feed: list = field(default_factory=list)            # intelligence feed

    def observation(self, obs_id: str):
        for o in self.observations:
            if o.observation_id == obs_id:
                return o
        return None

    def pattern(self, pattern_id: str):
        for p in self.patterns:
            if p.pattern_id == pattern_id:
                return p
        return None

    def as_dict(self) -> dict:
        return {
            "company_name": self.company_name, "status": self.status,
            "thesis": self.thesis, "shifts": self.shifts,
            "hypotheses": [h.as_dict() for h in self.hypotheses],
            "patterns": [p.as_dict() for p in self.patterns],
            "blind_spots": [b.as_dict() for b in self.blind_spots],
            "questions": [q.as_dict() for q in self.questions],
            "evidence_gaps": list(self.evidence_gaps),
            "decision_implications": list(self.decision_implications),
            "observations": [o.as_dict() for o in self.observations],
            "source_class_coverage": self.source_class_coverage,
            "quality_findings": list(self.quality_findings),
            "limited_scope_accepted": self.limited_scope_accepted,
            "evidence_graph": self.evidence_graph,
            "agenda": list(self.agenda),
            "timeline": list(self.timeline),
            "source_library": self.source_library,
            "analytics_events": list(self.analytics_events),
            "mental_model": self.mental_model,
            "surprises": list(self.surprises),
            "opportunities": list(self.opportunities),
            "vulnerabilities": list(self.vulnerabilities),
            "underexamined_questions": list(self.underexamined_questions),
            "what_changed": list(self.what_changed),
            "feed": list(self.feed),
        }
