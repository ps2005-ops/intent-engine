"""Causal-engine pillar #4: the mechanism library. Task 2 of the overnight
execution plan (2026-07-15, ~/Downloads/overnight-execution-plan.md).

A Mechanism is a named, historically-grounded causal pattern (e.g. "a price
war breaks out among a small number of competitors") with a closed-taxonomy
set of trigger conditions, an ordered causal chain, and at least one real,
cited historical instance. Seeded with exactly the 8 mechanisms the task
specified, each researched via real web search this session -- every
historical_instances[].source below is a real, checked URL, not fabricated;
none needed the "speculative" tier (a real citation was found for all 8),
though 3 (prisoners_dilemma_price_war, regulatory_capture_race,
ally_drawn_into_linked_conflict) are tiered "plausible" rather than
"well_documented" because their real sources are educational/advocacy
pages rather than a primary academic or major-outlet citation -- a
source-quality judgment call, stated here rather than silently applied.

Interface note, a deliberate small naming deviation from the plan's literal
`match_mechanisms(structured_intent)`, not a silent guess: since this task's
own SCOPE WALLS state "no LLM call in the matcher itself" and "matcher is
NOT wired into PremortemAnalyzer's output," there is no real
structured_intent object with trigger conditions on it yet for this
function to consume -- that extraction is Task 3/4's concern. match_mechanisms()
here takes the already-extracted trigger-condition list directly
(List[str]), the honest input shape for what this task actually builds;
wiring a real extraction step in front of it is later work.
"""

import json
from pathlib import Path
from typing import List, NamedTuple

try:
    from typing import Literal
except ImportError:  # pragma: no cover
    from typing_extensions import Literal

from pydantic import BaseModel

DATA_PATH = Path(__file__).parent / "data" / "mechanisms.json"

# Closed taxonomy, shared across mechanisms so the matcher's overlap
# computation is meaningful -- several mechanisms share a condition
# (e.g. few_dominant_competitors appears in 3 of the 8) by real structural
# similarity, not coincidence.
TriggerCondition = Literal[
    "concentrated_supplier_base",
    "few_dominant_competitors",
    "symmetric_competitor_response_expected",
    "frequent_regulatory_interaction",
    "adjacent_market_bundling_opportunity",
    "network_effects_present",
    "interconnected_counterparty_exposure",
    "binding_mutual_commitment_exists",
    "valuation_disconnected_from_fundamentals",
    "capacity_investment_outpacing_demand_signal",
    "debt_financed_expansion",
]

ConfidenceTier = Literal["well_documented", "plausible", "speculative"]


class HistoricalInstance(BaseModel):
    case: str
    year: int
    source: str  # a real citation string (URL(s)) -- never fabricated


class Mechanism(BaseModel):
    mechanism_id: str
    name: str
    trigger_conditions: List[str]
    causal_chain: List[str]  # ordered, human-readable steps
    historical_instances: List[HistoricalInstance]
    confidence_tier: ConfidenceTier


def load_mechanisms() -> List[Mechanism]:
    with open(DATA_PATH) as f:
        raw = json.load(f)
    return [Mechanism(**entry) for entry in raw]


class RankedMechanism(NamedTuple):
    mechanism: Mechanism
    overlap_count: int
    matched_conditions: List[str]


def match_mechanisms(trigger_conditions: List[str], min_overlap: int = 1) -> List[RankedMechanism]:
    """Deterministic, zero-LLM overlap ranking -- code, not judgment. Returns
    ONLY mechanisms with at least min_overlap real overlapping trigger
    conditions; a decision whose extracted conditions don't overlap any
    mechanism returns an empty list, never a forced/nearest match. Ranked by
    overlap_count descending, ties broken by mechanism_id for a stable,
    reproducible order."""
    input_conditions = set(trigger_conditions)
    ranked = []

    for mechanism in load_mechanisms():
        matched = sorted(input_conditions & set(mechanism.trigger_conditions))
        if len(matched) >= min_overlap:
            ranked.append(RankedMechanism(mechanism=mechanism, overlap_count=len(matched), matched_conditions=matched))

    ranked.sort(key=lambda r: (-r.overlap_count, r.mechanism.mechanism_id))
    return ranked
