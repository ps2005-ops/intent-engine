"""End-to-end test against the real Anthropic API.

Skipped automatically if ANTHROPIC_API_KEY isn't set, since it costs real API calls.
This checks output SHAPE and the <10s latency budget from the Week 1 spec — it does
not (and can't) assert exact wording, since the model's reasoning isn't deterministic.
Use scripts/run_examples.py to actually read the audits and judge quality by eye.
"""

import json
import os
from pathlib import Path

import pytest

from intent_engine.simulator.context_schema import BusinessContext
from intent_engine.simulator.pipeline import run_premortem

FIXTURES_PATH = Path(__file__).parent / "fixtures" / "business_decisions.json"

pytestmark = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set; skipping live API end-to-end test.",
)


def _load_fixtures():
    with open(FIXTURES_PATH) as f:
        return json.load(f)


@pytest.mark.parametrize("fixture", _load_fixtures(), ids=lambda fx: fx["id"])
def test_premortem_end_to_end(fixture):
    context = BusinessContext(**fixture["context"])
    result = run_premortem(fixture["decision_text"], context)

    assert 3 <= len(result.risk_audit.failure_modes) <= 5
    assert result.risk_audit.recommended_stress_tests
    assert result.risk_audit.key_sensitivity
    assert result.intent.decision_summary
    assert result.elapsed_seconds < 10, (
        f"{fixture['id']} took {result.elapsed_seconds:.1f}s, exceeding the 10s budget"
    )
