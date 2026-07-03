"""End-to-end test against the real Anthropic API.

Skipped automatically if ANTHROPIC_API_KEY isn't set, since it costs real API calls.
This checks output SHAPE — it does not (and can't) assert exact wording, since the
model's reasoning isn't deterministic. Use scripts/run_examples.py to actually read
the audits and judge quality by eye.

Latency: <10s is the TYPICAL-case target (see PROGRESS.md), not a per-call gate.
Multi-run testing (20 calls across all 5 fixtures) showed ~5% of individual calls
spike to 11-13s from API-side variance independent of content length or which
fixture -- a fixture that looked perfectly safe on 3 runs spiked on the 4th, while
a fixture that spiked once came back clean on 4 repeats. Content trimming can't fix
this. SANITY_CEILING_SECONDS below is a generous backstop against genuine
regressions/hangs, not a target -- print the actual time on every run so trends are
visible without treating normal variance as a failure.
"""

import json
import os
from pathlib import Path

import pytest

from intent_engine.simulator.context_schema import BusinessContext
from intent_engine.simulator.pipeline import run_premortem

FIXTURES_PATH = Path(__file__).parent / "fixtures" / "business_decisions.json"

TYPICAL_LATENCY_SECONDS = 10
SANITY_CEILING_SECONDS = 20

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
    assert result.risk_audit.narrative_summary
    assert result.intent.decision_summary
    assert result.scenario_set.primary_priority in ("growth", "profitability", "survival", "optionality")
    assert [s.name for s in result.scenario_set.scenarios] == ["upside", "base", "downside"]
    over_typical = " (over typical ~10s target, within normal variance)" if result.elapsed_seconds > TYPICAL_LATENCY_SECONDS else ""
    print(f"\n{fixture['id']}: {result.elapsed_seconds:.1f}s{over_typical}")
    assert result.elapsed_seconds < SANITY_CEILING_SECONDS, (
        f"{fixture['id']} took {result.elapsed_seconds:.1f}s, exceeding the {SANITY_CEILING_SECONDS}s "
        "sanity ceiling -- this is well beyond normal variance and likely a real regression"
    )
