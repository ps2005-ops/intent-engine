"""What the analyst must produce, and the result states a run can end in.

The shape changed once, deliberately. The first version asked for INSIGHTS,
and got insights: true, well-evidenced, and shaped like analysis. A founder
does not need analysis. They need to know what to do on Monday, what it costs
to wait, and what a competitor might do first.

So the top-level unit is a DECISION, and every field on it exists because a
founder would ask for it out loud. A model that cannot say what would
invalidate a decision, or what is lost by waiting, should fail to produce the
decision rather than produce it without them.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

# Bump when the prompt or schema changes in a way that invalidates cached
# analyses. The cache key includes this, so a bump re-runs every company.
PROMPT_VERSION = "fi-five-insights-2026-07-28"

URGENCY = ("decide_now", "this_quarter", "this_year", "watch_only")

# What a founder should actually DO about a decision. "It depends" is not on
# this list and never will be: a recommendation that does not resolve to one of
# these has not been made.
VERDICTS = ("do_now", "monitor", "research", "wait", "ignore")

IMPACT = ("high", "medium", "low")

# Reversibility is the single most useful decision property a founder can be
# told, and the one generic advice never supplies. A one-way door deserves
# weeks of deliberation; an easily reversible call deserves a day.
REVERSIBILITY = ("one_way_door", "costly_to_reverse", "easily_reversible")

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
    business_model: dict = field(default_factory=dict)
    the_insight: dict = field(default_factory=dict)
    decisions: list = field(default_factory=list)
    competitive: dict = field(default_factory=dict)
    questions: list = field(default_factory=list)
    mental_model: dict = field(default_factory=dict)
    assumptions: list = field(default_factory=list)
    blind_spots: dict = field(default_factory=dict)
    scenarios: dict = field(default_factory=dict)
    strongest_case_we_are_wrong: str = ""
    evidence_gaps: list = field(default_factory=list)
    sufficient: bool = False
    insufficiency_reason: str = ""
    #: provenance of the reasoning itself, not of the evidence
    model: str = ""
    prompt_version: str = PROMPT_VERSION
    usage: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


_BUSINESS_MODEL_SCHEMA = {
    "type": "object",
    "description": "Reconstruct how the money actually works before inferring "
                   "any strategy. Where these differ from each other is "
                   "usually where the interesting question is.",
    "properties": {
        "one_line": {"type": "string",
                     "description": "What it sells, to whom, and how it is "
                                    "actually paid."},
        "where_profit_comes_from": {"type": "string"},
        "where_value_leaks": {
            "type": "string",
            "description": "Where the business creates value it does not "
                           "capture, or spends money that does not become "
                           "advantage.",
        },
        "what_customers_actually_buy": {
            "type": "string",
            "description": "The job being paid for, which is often not the "
                           "product the company describes.",
        },
        "the_game_they_are_playing": {
            "type": "string",
            "description": "Not what they sell -- what they are actually "
                           "competing to win, and on what timescale. Two "
                           "companies selling the same thing often play "
                           "different games.",
        },
    },
    "required": ["one_line", "where_profit_comes_from", "where_value_leaks",
                 "what_customers_actually_buy", "the_game_they_are_playing"],
}

# Part of the audit's finding: the most valuable inferences about leadership
# were spread across a business-model field and a blind-spot field, and NEITHER
# reached the deck. They belong together, phrased the way an operator would say
# them out loud.
_MENTAL_MODEL_SCHEMA = {
    "type": "object",
    "description": "An outside-in reconstruction of how leadership appears to "
                   "see its own situation. Inference from public behaviour "
                   "only -- never a claim to know what anyone thinks.",
    "properties": {
        "they_believe": {"type": "string"},
        "they_are_protecting": {"type": "string"},
        "they_are_sacrificing": {
            "type": "string",
            "description": "What they have accepted losing. If nothing is "
                           "being given up, it is not a strategy.",
        },
        "they_will_not_compromise_on": {"type": "string"},
        "where_this_could_blind_them": {"type": "string"},
    },
    "required": ["they_believe", "they_are_protecting", "they_are_sacrificing",
                 "where_this_could_blind_them"],
}

_THE_INSIGHT_SCHEMA = {
    "type": "object",
    "description": "The one thing worth remembering. If a reader keeps only "
                   "one sentence from the whole analysis, this is it.",
    "properties": {
        "sentence": {
            "type": "string",
            "description": "One sentence. It must be specific enough that it "
                           "would be false or meaningless about any other "
                           "company, and non-obvious enough that a competent "
                           "executive would not already have said it.",
        },
        "paragraph": {
            "type": "string",
            "description": "Why it is true and why it changes something. No "
                           "hedging, no restating the sentence.",
        },
        "why_now": {"type": "string"},
        "tension": {
            "type": "object",
            "description": "The trade-off leadership is actually managing. "
                           "Strategy is what a company gives up.",
            "properties": {
                "side_a": {"type": "string"},
                "side_b": {"type": "string"},
                "why_it_exists": {"type": "string"},
            },
            "required": ["side_a", "side_b", "why_it_exists"],
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
        "consequence_chain": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Three to five links, each following from the last: "
                           "first-order effect, then what that causes, then "
                           "what THAT causes. Stop where the evidence stops "
                           "supporting the chain rather than inventing a "
                           "fourth link.",
        },
        "citations": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["sentence", "paragraph", "why_now", "tension", "economics",
                 "consequence_chain", "citations"],
}

_DECISION_SCHEMA = {
    "type": "object",
    "properties": {
        "decision": {
            "type": "string",
            "description": "The choice itself, phrased the way a CEO would say "
                           "it out loud. Not a topic and not an area to "
                           "explore -- a fork with two real sides.",
        },
        "why_it_matters": {"type": "string"},
        "urgency": {"type": "string", "enum": list(URGENCY)},
        "cost_of_waiting": {
            "type": "string",
            "description": "What is lost or foreclosed by deciding six months "
                           "from now instead of now. If waiting is cheap, say "
                           "so plainly -- that is useful too.",
        },
        "what_a_competitor_may_do_first": {"type": "string"},
        "upside": {"type": "string"},
        "downside": {"type": "string"},
        "what_would_invalidate_it": {"type": "string"},
        "what_to_watch": {
            "type": "string",
            "description": "The specific observable that would change this "
                           "decision -- a filing line, a pricing page, a "
                           "competitor launch.",
        },
        "business_impact": {
            "type": "string", "enum": list(IMPACT),
            "description": "How much of the business outcome actually turns "
                           "on this. Most decisions are not high.",
        },
        "reversibility": {
            "type": "string", "enum": list(REVERSIBILITY),
            "description": "A one-way door deserves weeks; an easily "
                           "reversible call deserves a day.",
        },
        "verdict": {
            "type": "string", "enum": list(VERDICTS),
            "description": "What the founder should do about it TODAY. "
                           "'ignore' and 'wait' are real answers and are "
                           "better than false urgency.",
        },
        "cheapest_experiment": {
            "type": "string",
            "description": "The least expensive way to learn which side of "
                           "this is right, if one exists.",
        },
        "confidence": {"type": "string",
                       "enum": ["low", "moderate", "high"]},
        "confidence_rationale": {
            "type": "string",
            "description": "Plain language naming the evidence. Never a bare "
                           "label.",
        },
        "missing_evidence": {"type": "string"},
        "citations": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["decision", "why_it_matters", "urgency", "business_impact",
                 "reversibility", "verdict", "cost_of_waiting",
                 "what_a_competitor_may_do_first", "upside", "downside",
                 "what_would_invalidate_it", "what_to_watch", "confidence",
                 "confidence_rationale", "citations"],
}

_ASSUMPTION_SCHEMA = {
    "type": "object",
    "description": "What this whole reading rests on. A founder who knows "
                   "which belief is load-bearing knows what to watch.",
    "properties": {
        "assumption": {"type": "string"},
        "why_we_believe_it": {"type": "string"},
        "what_would_break_it": {"type": "string"},
        "how_load_bearing": {"type": "string", "enum": list(IMPACT)},
        "confidence": {"type": "string",
                       "enum": ["low", "moderate", "high"]},
    },
    "required": ["assumption", "why_we_believe_it", "what_would_break_it",
                 "how_load_bearing", "confidence"],
}

_BLIND_SPOTS_SCHEMA = {
    "type": "object",
    "description": "The most valuable part of an outside view: what the room "
                   "is not saying.",
    "properties": {
        "everyone_is_discussing": {"type": "string"},
        "almost_nobody_is_discussing": {
            "type": "string",
            "description": "The thing that matters and is absent from the "
                           "public conversation. If nothing qualifies, say so "
                           "rather than inventing one.",
        },
    },
    "required": ["everyone_is_discussing", "almost_nobody_is_discussing"],
}

_SCENARIOS_SCHEMA = {
    "type": "object",
    "description": "Reasoning, not prediction. No probabilities and no dates "
                   "unless the evidence carries them.",
    "properties": {
        "upside_case": {"type": "string"},
        "downside_case": {"type": "string"},
        "wild_card": {
            "type": "string",
            "description": "Low likelihood, high consequence, and not what "
                           "anyone is planning for.",
        },
        "leading_indicators": {
            "type": "array", "items": {"type": "string"},
            "description": "What would be observable FIRST if a case is "
                           "playing out.",
        },
    },
    "required": ["upside_case", "downside_case", "leading_indicators"],
}

_COMPETITIVE_SCHEMA = {
    "type": "object",
    "description": "Not a list of competitors. Who is applying the pressure, "
                   "and who has to do something about it.",
    "properties": {
        "who_is_forcing_the_change": {"type": "string"},
        "who_benefits": {"type": "string"},
        "who_loses": {"type": "string"},
        "who_must_respond": {"type": "string"},
        "if_nobody_responds": {"type": "string"},
        "what_rivals_should_fear": {
            "type": "string",
            "description": "The one capability or position this company has "
                           "that a competitor cannot easily copy or answer. "
                           "If there is not one, say so -- that is the more "
                           "important finding.",
        },
    },
    "required": ["who_is_forcing_the_change", "who_benefits", "who_loses",
                 "who_must_respond", "if_nobody_responds",
                 "what_rivals_should_fear"],
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
                                   "subsidiary-level facts, say so. Never "
                                   "silently attribute a group-level fact to "
                                   "a subsidiary.",
                },
            },
            "required": ["analysed_entity", "is_subsidiary"],
        },
        "business_model": _BUSINESS_MODEL_SCHEMA,
        "sufficient_for_strategic_analysis": {
            "type": "boolean",
            "description": "False when the evidence is descriptive rather "
                           "than strategic. Answering false is a correct and "
                           "expected outcome; inventing a thesis is not.",
        },
        "insufficiency_reason": {"type": "string"},
        "the_insight": _THE_INSIGHT_SCHEMA,
        "mental_model": _MENTAL_MODEL_SCHEMA,
        "decisions": {
            "type": "array", "items": _DECISION_SCHEMA, "maxItems": 3,
            "description": "At most THREE. A founder with five minutes cannot "
                           "hold more, and the fourth is always the weakest.",
        },
        "competitive": _COMPETITIVE_SCHEMA,

        "strongest_case_we_are_wrong": {
            "type": "string",
            "description": "The best argument against this entire reading, "
                           "made properly rather than as a disclaimer.",
        },
        "assumptions": {"type": "array", "items": _ASSUMPTION_SCHEMA,
                        "maxItems": 2,
                        "description": "At most TWO -- the beliefs this "
                                       "reading would not survive without. "
                                       "A list of eight assumptions is a list "
                                       "of none."},
        "blind_spots": _BLIND_SPOTS_SCHEMA,
        "scenarios": _SCENARIOS_SCHEMA,
        "questions": {
            "type": "array", "items": {"type": "string"}, "maxItems": 3,
            "description": "At most three, phrased the way a board member "
                           "would actually ask them out loud. About this "
                           "company's own fragile assumptions -- 'what "
                           "assumption breaks this?' is the shape, 'what are "
                           "our goals?' is not.",
        },
        "evidence_gaps": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["entity_scope", "business_model", "mental_model",
                 "sufficient_for_strategic_analysis", "the_insight",
                 "decisions", "competitive", "questions", "assumptions",
                 "blind_spots", "scenarios",
                 "strongest_case_we_are_wrong", "evidence_gaps"],
}
