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
    disconfirming_signals: tuple = ()
    limitations: str = ""

    def validate(self) -> None:
        _require(bool(self.pattern_id), "pattern_id required")
        _require(bool(self.mechanism.strip()), "pattern mechanism required")
        _require(len(self.historical_examples) >= 1,
                 f"pattern {self.pattern_id} needs >=1 cited example")
        _require(bool(self.qualifying_signals),
                 f"pattern {self.pattern_id} needs qualifying signals")

    def as_dict(self) -> dict:
        d = asdict(self)
        d["qualifying_signals"] = list(self.qualifying_signals)
        d["disconfirming_signals"] = list(self.disconfirming_signals)
        return d


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

    def validate(self) -> None:
        _require(self.confidence in CONFIDENCE_LEVELS,
                 f"unknown confidence {self.confidence!r}")
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

    def as_dict(self) -> dict:
        d = asdict(self)
        d["source_classes"] = list(self.source_classes)
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
        }
