"""The analyst's output contract, and the result states a run can end in.

The schema is deliberately demanding. Every field on an insight exists because
its absence was a specific complaint about the old reports: no economics, no
comparison, no second-order thinking, no disagreement, unexplained confidence
labels. A model asked for prose returns prose; a model asked for THIS returns
an argument that can be checked field by field.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

# Bump when the prompt or schema changes in a way that invalidates cached
# analyses. The cache key includes this, so a bump re-runs every company.
PROMPT_VERSION = "sa2-2026-07-28"

ECONOMIC_LEVERS = (
    "revenue", "revenue_mix", "gross_margin", "operating_leverage",
    "pricing_power", "capital_intensity", "capital_allocation",
    "customer_acquisition", "retention", "switching_costs", "distribution",
    "network_effects", "content_economics", "regulatory_cost",
    "competitive_moat",
)


class ResultState:
    """What actually happened, stated so a reader can act on it.

    PARTIAL used to mean "the pipeline ran but the intelligence is weak",
    which is indistinguishable from "the intelligence is fine" on the page.
    These states each imply a different next action, and each one decides for
    itself whether a presentation and brief should be shown at all.
    """
    COMPLETE = "COMPLETE"
    EVIDENCE_LIMITED = "EVIDENCE_LIMITED"
    ENTITY_AMBIGUOUS = "ENTITY_AMBIGUOUS"
    RETRIEVAL_BLOCKED = "RETRIEVAL_BLOCKED"
    STRATEGICALLY_INSUFFICIENT = "STRATEGICALLY_INSUFFICIENT"
    FAILED = "FAILED"

    ALL = (COMPLETE, EVIDENCE_LIMITED, ENTITY_AMBIGUOUS, RETRIEVAL_BLOCKED,
           STRATEGICALLY_INSUFFICIENT, FAILED)

    #: states in which a strategic presentation/brief may be shown
    PRESENTABLE = (COMPLETE,)

    EXPLANATION = {
        COMPLETE:
            "Enough independent evidence was retrieved to support a strategic "
            "reading, and every claim below cites it.",
        EVIDENCE_LIMITED:
            "Real evidence was retrieved, but not enough of it, or not from "
            "enough independent vantage points, to support a strategic "
            "conclusion. What was learned is shown; no strategy is asserted.",
        ENTITY_AMBIGUOUS:
            "More than one company matches this name, and the evidence spans "
            "more than one of them. Choosing the entity is required before "
            "any conclusion is meaningful.",
        RETRIEVAL_BLOCKED:
            "The sources that would answer this could not be reached. This is "
            "a retrieval failure, not a finding about the company.",
        STRATEGICALLY_INSUFFICIENT:
            "Pages were retrieved and read, but they are descriptive rather "
            "than strategic -- they say what the company sells, not what it "
            "is deciding. A confident-looking report here would be invented.",
        FAILED:
            "The analysis did not complete. No conclusions should be drawn.",
    }


class AnalysisRejected(Exception):
    """The critic refused the analyst's output. Carries the findings."""

    def __init__(self, findings):
        self.findings = list(findings)
        super().__init__("; ".join(f.message for f in self.findings)
                         or "analysis rejected")


@dataclass
class StrategicAnalysis:
    entity_scope: dict = field(default_factory=dict)
    business_model: str = ""
    insights: list = field(default_factory=list)
    evidence_gaps: list = field(default_factory=list)
    sufficient: bool = False
    insufficiency_reason: str = ""
    #: provenance of the reasoning itself, not of the evidence
    model: str = ""
    prompt_version: str = PROMPT_VERSION
    usage: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


# The forced tool-call schema. `required` is doing real work: a model that
# cannot supply a counterargument or an economic mechanism for a claim should
# fail to produce the claim, rather than produce it without them.
_INSIGHT_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {
            "type": "string",
            "description": "One sentence, stated about THIS company using its "
                           "own products, segments or markets by name. It must "
                           "be false or meaningless if applied to a different "
                           "company. Never use the words platform, ecosystem, "
                           "digital transformation, synergy or leverage as the "
                           "substance of the claim.",
        },
        "what_is_changing": {"type": "string"},
        "why_now": {
            "type": "string",
            "description": "The specific evidence making this timely, with "
                           "its date where known.",
        },
        "tension": {
            "type": "object",
            "properties": {
                "side_a": {"type": "string"},
                "side_b": {"type": "string"},
                "why_it_exists": {"type": "string"},
                "decision_owner": {"type": "string"},
                "what_would_resolve_it": {"type": "string"},
            },
            "required": ["side_a", "side_b", "why_it_exists",
                         "what_would_resolve_it"],
        },
        "economics": {
            "type": "object",
            "properties": {
                "mechanism": {
                    "type": "string",
                    "description": "How this reaches the financial "
                                   "statements. No invented figures -- cite a "
                                   "number only if it appears in the evidence.",
                },
                "levers": {"type": "array",
                           "items": {"type": "string",
                                     "enum": list(ECONOMIC_LEVERS)}},
            },
            "required": ["mechanism", "levers"],
        },
        "competitive": {
            "type": "object",
            "properties": {
                "compared_to": {"type": "array", "items": {"type": "string"},
                                "description": "Named, relevant competitors "
                                               "or substitutes."},
                "how_this_company_differs": {"type": "string"},
                "likely_responder": {"type": "string"},
                "second_order_effect": {"type": "string"},
            },
            "required": ["compared_to", "how_this_company_differs",
                         "second_order_effect"],
        },
        "counterargument": {
            "type": "object",
            "properties": {
                "strongest_case_against": {"type": "string"},
                "what_would_disprove_this": {"type": "string"},
            },
            "required": ["strongest_case_against", "what_would_disprove_this"],
        },
        "decision_affected": {
            "type": "string",
            "description": "A decision leadership actually faces, phrased so "
                           "the reader can tell what changes depending on it.",
        },
        "monitor": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "string",
                       "enum": ["low", "moderate", "high"]},
        "confidence_rationale": {
            "type": "string",
            "description": "Plain language, naming the evidence. e.g. "
                           "'Low -- three company-owned pages, no filing or "
                           "independent reporting.' Never a bare label.",
        },
        "citations": {
            "type": "array",
            "items": {"type": "string"},
            "description": "observation_id values from the evidence pack that "
                           "support this insight. Every material claim must be "
                           "traceable to one.",
        },
    },
    "required": ["headline", "what_is_changing", "why_now", "tension",
                 "economics", "competitive", "counterargument",
                 "decision_affected", "confidence", "confidence_rationale",
                 "citations"],
}

ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "entity_scope": {
            "type": "object",
            "properties": {
                "analysed_entity": {"type": "string"},
                "is_subsidiary": {"type": "boolean"},
                "parent": {"type": "string"},
                "scope_note": {
                    "type": "string",
                    "description": "If the evidence mixes parent-level and "
                                   "subsidiary-level facts, say so here. Never "
                                   "silently attribute a group-level fact to a "
                                   "subsidiary.",
                },
            },
            "required": ["analysed_entity", "is_subsidiary"],
        },
        "business_model": {
            "type": "string",
            "description": "One sentence: what it sells, to whom, and how the "
                           "money is actually made.",
        },
        "sufficient_for_strategic_analysis": {
            "type": "boolean",
            "description": "False when the evidence is descriptive rather than "
                           "strategic. Answering false is a correct and "
                           "expected outcome; inventing a thesis is not.",
        },
        "insufficiency_reason": {"type": "string"},
        "insights": {
            "type": "array", "items": _INSIGHT_SCHEMA,
            "description": "At most three. One well-evidenced insight is "
                           "better than three weak ones. Empty is correct when "
                           "the evidence supports nothing non-obvious.",
        },
        "evidence_gaps": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["entity_scope", "business_model",
                 "sufficient_for_strategic_analysis", "insights",
                 "evidence_gaps"],
}
