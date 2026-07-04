"""Luck Test: a fully separate, opt-in analysis -- NOT part of PremortemAnalyzer's
combined call. Weeks 1-4's latency profile stays completely untouched regardless of
whether this is ever invoked; this is an additive capability, not a modification to
the core pipeline (same reasoning as Stage C's stub actors being wired only when
explicitly triggered, never on the default premortem path).

diversification_signal is computed DETERMINISTICALLY in code from
entity_memory.read_records(), never asked of the LLM. This is a deliberate,
load-bearing distinction from demand_durability/timing_confidence: whether prior
records show multiple distinct bets is a fact about accumulated history the model
isn't even shown in full, not a judgment call about ambiguous evidence in the
current decision text -- it should never be an LLM guess.

demand_durability/timing_confidence ARE asked of the model, in a minimal, focused,
standalone call -- deliberately NOT folded into PremortemAnalyzer's combined call.
This isn't just an architectural preference: a real isolation test (5 real runs,
same maximally-explicit no-leverage decision text that twice returned a non-honest
leverage_type inside the 20-field combined call) showed the model reliably gives
the honest "no signal" answer when asked in a small, focused call, but not when the
same question competes for attention against 15+ other extraction demands in one
combined prompt. Kept the SYSTEM_PROMPT below short and single-purpose for exactly
this reason, not just for organization.
"""

from typing import Optional, Union
from pathlib import Path

from pydantic import BaseModel

try:
    from typing import Literal
except ImportError:  # pragma: no cover
    from typing_extensions import Literal

from ..core.entity_memory import DEFAULT_PATH, EntityMemoryRecord, read_records
from ..core.llm_client import LLMClient
from ..core.pipeline import Stage

FAST_MODEL = "claude-haiku-4-5-20251001"


class LuckTestAssessment(BaseModel):
    demand_durability: Literal["structural", "cyclical_hype", "unclear"]
    diversification_signal: Literal["single_bet", "multiple_bets", "insufficient_history"]
    timing_confidence: Literal["low", "medium", "high"]
    rationale: str


SYSTEM_PROMPT = """You are assessing the Luck Test component of a pre-mortem analysis: \
whether this decision's success would be attributable to controllable, durable factors, \
or to luck/timing/market conditions that could just as easily reverse.

demand_durability: is the demand this decision relies on structural (a durable, ongoing \
need independent of any one moment) or cyclical_hype (a temporary spike, fad, or hype \
cycle likely to fade)? Base this ONLY on evidence actually stated in the decision text \
-- customer commitments, a stated trend, repeat-usage evidence, or an explicit mention \
of a fad/hype cycle. If the decision text does not state or clearly imply why THIS \
demand would persist or fade, you MUST answer "unclear" -- do not substitute general \
category knowledge about the industry or product type for evidence that isn't actually \
in the text. A category that is often durable in general (e.g. "people always need X") \
is not the same as this specific decision providing evidence that ITS demand is durable. \
"unclear" is the correct, honest answer whenever the text is silent on this, not a \
fallback to avoid.

timing_confidence: how confident is a reasonable observer that THIS is the right moment \
for this decision, based only on what's in the text? "low" if the text gives little or \
no basis to judge timing at all -- this is the honest answer when evidence is thin, not \
only when timing looks bad. "medium" if there's some signal but real uncertainty \
remains. "high" only if the text gives clear, specific evidence supporting the timing.

rationale: one or two sentences explaining the demand_durability and timing_confidence \
judgments, grounded in what's actually stated in the decision text -- not generic \
reasoning that could apply to any decision."""

TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "demand_durability": {"type": "string", "enum": ["structural", "cyclical_hype", "unclear"]},
        "timing_confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "rationale": {"type": "string", "maxLength": 300},
    },
    "required": ["demand_durability", "timing_confidence", "rationale"],
}


def _bets_clearly_differ(a: EntityMemoryRecord, b: EntityMemoryRecord) -> bool:
    """Two records count as distinct bets if EITHER their primary_priority differs
    (both present and unequal) OR their goals share no overlap at all -- a
    deterministic, inspectable stand-in for "clearly different," not a fuzzy
    similarity score. Any shared goal wording is treated as the same underlying
    bet reiterated, not a second one."""
    if a.primary_priority and b.primary_priority and a.primary_priority != b.primary_priority:
        return True
    a_goals = {g.strip().lower() for g in a.goals}
    b_goals = {g.strip().lower() for g in b.goals}
    if a_goals and b_goals and not (a_goals & b_goals):
        return True
    return False


def compute_diversification_signal(
    entity_id: str, path: Union[str, Path] = DEFAULT_PATH
) -> Literal["single_bet", "multiple_bets", "insufficient_history"]:
    """Deterministic, code-only -- see module docstring for why this is never an
    LLM guess. "insufficient_history": zero prior records, nothing to judge from.
    "single_bet": one or more records, but no pair of them clearly differs.
    "multiple_bets": at least one pair of records clearly differs (see
    _bets_clearly_differ)."""
    records = read_records(entity_id, path=path)
    if not records:
        return "insufficient_history"

    for i in range(len(records)):
        for j in range(i + 1, len(records)):
            if _bets_clearly_differ(records[i], records[j]):
                return "multiple_bets"
    return "single_bet"


class LuckTestAnalyzer(Stage):
    """Separate Claude API call from PremortemAnalyzer. Runs only when explicitly
    invoked -- never part of the default premortem path. Additive capability, not
    a modification to the core pipeline."""

    name = "luck_test_analyzer"

    def __init__(self, client: Optional[LLMClient] = None, entity_memory_path: Union[str, Path] = DEFAULT_PATH):
        self.client = client or LLMClient(model=FAST_MODEL)
        self.entity_memory_path = entity_memory_path

    def run(self, decision_text: str, entity_id: str) -> LuckTestAssessment:
        diversification_signal = compute_diversification_signal(entity_id, path=self.entity_memory_path)

        result = self.client.call_tool(
            system=SYSTEM_PROMPT,
            user_message=f"Decision: {decision_text}",
            tool_name="record_luck_test",
            tool_description="Record the Luck Test assessment.",
            input_schema=TOOL_SCHEMA,
            max_tokens=256,
        )

        return LuckTestAssessment(
            demand_durability=result["demand_durability"],
            diversification_signal=diversification_signal,
            timing_confidence=result["timing_confidence"],
            rationale=result["rationale"],
        )
