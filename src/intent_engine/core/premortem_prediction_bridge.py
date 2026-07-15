"""Task 5 of the overnight execution plan (2026-07-15): the premortem ->
prediction-ledger bridge.

After a real premortem run, derives 1-3 RESOLVABLE predictions from its
real risk-audit failure modes via one isolated LLM drafting call. Model
drafts, code decides: the drafting tool's schema has ONLY
claim_text/probability/resolve_by fields -- no id/include/record field
exists for the model to see or set, the same "model drafts, code decides"
discipline as Stage 2's source_record_ids and the digest gate's inclusion
decision (checked directly by a test, not just asserted here).

SCOPE WALL, per Task 5's own spec: no auto-resolution, no scoring display,
no backfill. Renders nothing new to the user -- pure substrate, same as
Task 1.

Path note, taken per the plan's own explicit fallback (Tasks 1, 4 depended
on; "if 4 parked, this may still proceed against plain premortem output"):
Task 4 (wiring mechanisms into simulator rendering) PARKED tonight (see
reports/overnight_trace.md) on its own reliability gate, so this bridges
against PLAIN premortem output (RiskAudit.failure_modes) only -- no
mechanism-section enrichment, since that section doesn't exist yet.
"""

from datetime import date, datetime, timezone
from pathlib import Path
from typing import List, Optional, Union

from ..core.schemas import RiskAudit
from .llm_client import LLMClient
from .prediction_ledger import DEFAULT_LEDGER_PATH, Prediction, record_prediction

FAST_MODEL = "claude-haiku-4-5-20251001"

BRIDGE_SYSTEM_PROMPT = """You are converting a business risk audit's failure modes into a small \
number of concrete, RESOLVABLE predictions -- claims specific enough that someone could check \
in the real world, on the stated date, whether they happened or not.

Rules:
- Derive 1-3 predictions, no more. Fewer, sharper predictions are better than more, vaguer ones.
- Each claim must be checkable against a real, observable fact (a number crossing a threshold, an \
event happening or not) -- never a vague feeling ("things go poorly") or something unfalsifiable.
- Ground every prediction directly in the stated failure modes -- do not invent a new risk not \
implied by what's given.
- probability is your real, honest estimate that the claim happens, 0 to 1 -- not a rounded 0.5 \
by default.
- resolve_by must be a real future date, close enough that it's still a meaningful check (a few \
months to about a year out), not so far off it's unfalsifiable in practice."""

BRIDGE_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "predictions": {
            "type": "array",
            "minItems": 1,
            "maxItems": 3,
            "items": {
                "type": "object",
                "properties": {
                    "claim_text": {"type": "string", "maxLength": 300},
                    "probability": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    "resolve_by": {"type": "string", "description": "ISO-8601 date, e.g. 2027-01-15"},
                },
                "required": ["claim_text", "probability", "resolve_by"],
            },
        },
    },
    "required": ["predictions"],
}


def derive_predictions_from_premortem(
    entity_id: str,
    risk_audit: RiskAudit,
    client: Optional[LLMClient] = None,
    ledger_path: Union[str, Path] = DEFAULT_LEDGER_PATH,
) -> List[Prediction]:
    """Drafts 1-3 predictions from a real RiskAudit's failure_modes and
    records them to the ledger with source="premortem" -- recording is
    entirely code (record_prediction() is called here directly on the
    model's drafted fields); the model has no field in its own schema
    that could record anything itself."""
    client = client or LLMClient(model=FAST_MODEL)

    failure_modes_text = "\n".join(
        f"{i + 1}. [{fm.likelihood}] {fm.description} -- {fm.rationale}"
        for i, fm in enumerate(risk_audit.failure_modes)
    )
    # Real bug found in this task's own live verification, fixed here (not
    # deferred): the model has no notion of "today" from training data
    # alone and drafted resolve_by dates already in the past relative to
    # the real session date. Stating today's real date explicitly is the
    # fix -- and it's backstopped by a real code-level check below, not
    # trusted on the prompt instruction alone.
    today_str = datetime.now(timezone.utc).date().isoformat()
    user_message = (
        f"Today's real date is {today_str}.\n\n"
        f"Real risk-audit failure modes for this decision:\n{failure_modes_text}\n\nDraft the predictions."
    )

    result = client.call_tool(
        system=BRIDGE_SYSTEM_PROMPT,
        user_message=user_message,
        tool_name="record_candidate_predictions",
        tool_description="Record candidate resolvable predictions drafted from the failure modes.",
        input_schema=BRIDGE_TOOL_SCHEMA,
        max_tokens=600,
    )

    today = datetime.now(timezone.utc).date()
    predictions = []
    for candidate in result["predictions"]:
        try:
            resolve_by_date = date.fromisoformat(candidate["resolve_by"])
        except ValueError:
            continue  # malformed date -- skip rather than persist garbage
        if resolve_by_date <= today:
            continue  # code-level backstop: never persist a non-future resolve_by, even if the model drafted one
        p = record_prediction(
            source="premortem",
            entity_id=entity_id,
            claim_text=candidate["claim_text"],
            probability=candidate["probability"],
            resolve_by=candidate["resolve_by"],
            path=ledger_path,
        )
        predictions.append(p)
    return predictions
