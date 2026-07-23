"""Shared budgeting (T022) — model-call accounting, no pricing.

Every agent already records which rows a model produced (the provenance
`model_version`) and, where a model ran, a `usage` block. `model_budget`
DERIVES the model-call accounting from those existing rows: how many model
calls a store contains, grouped by prompt version, and the recorded usage
if any.

There is deliberately **no pricing and no billing** here. This subsystem
answers "how much model work has this agent's log recorded?", not "what
did it cost?" — cost needs a price table this repository does not hold, and
inventing one is the kind of number that later gets quoted as measured.
"""
from __future__ import annotations

BUDGET_VERSION = "agentos_budget.v1"


def model_budget(store) -> dict:
    """Model-call accounting derived from the append-only rows. Read-only,
    deterministic, no pricing."""
    rows = store.read_all()
    by_prompt = {}
    usage_rows = 0
    for row in rows:
        provenance = getattr(row, "provenance", None) or {}
        if provenance.get("model_version"):
            prompt = provenance.get("prompt_version", "unknown")
            by_prompt[prompt] = by_prompt.get(prompt, 0) + 1
        payload = getattr(row, "payload", None) or {}
        if payload.get("usage"):
            usage_rows += 1
    return {
        "budget_version": BUDGET_VERSION,
        "model_calls": sum(by_prompt.values()),
        "model_calls_by_prompt_version": dict(sorted(by_prompt.items())),
        "rows_with_usage": usage_rows,
        "pricing": "not computed — this repository holds no price table, "
                   "and a fabricated cost is not recorded",
    }
