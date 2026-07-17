"""Live smoke test for core/market_resolution.py's real Tiingo wiring
(Task M6 bar c). Skipped automatically when TIINGO_API_KEY is absent --
same discipline as test_macro_data_live.py / test_calendar_live.py.
"""

import os

import pytest
from dotenv import load_dotenv

load_dotenv()

pytestmark = pytest.mark.skipif(
    not os.environ.get("TIINGO_API_KEY"),
    reason="TIINGO_API_KEY not set in the environment -- see market-engine-execution-plan.md Phase 0.",
)


def test_real_fetch_of_spy_prices_returns_well_shaped_data(tmp_path):
    from intent_engine.core.market_resolution import get_prices

    series = get_prices("SPY", "2024-01-01", "2024-02-01", cache_dir=tmp_path / "tiingo_cache")
    assert series.symbol == "SPY"
    assert len(series.observations) >= 1
    dates = [d for d, _ in series.observations]
    assert dates == sorted(dates)
    for observed_date, value in series.observations:
        assert isinstance(observed_date, str) and len(observed_date) == 10
        assert isinstance(value, float)
        assert value > 0


def test_real_end_to_end_pct_change_resolution_against_real_spy_data():
    """Real Tiingo data through the actual resolve_pct_change_rule path --
    a wide, near-certain-to-pass threshold (SPY moving >= 0.01% in a
    known historical month) so this asserts the WIRING works, not a
    market-timing claim."""
    from intent_engine.core.market_resolution import resolve_pct_change_rule
    from intent_engine.core.prediction_ledger import PctChangeRule

    rule = PctChangeRule(type="pct_change", symbol="SPY", op=">=", value=0.0001, window_days=20)
    result = resolve_pct_change_rule(rule, "2024-01-02", "2024-02-01")
    assert result.outcome in ("happened", "did_not_happen")  # real data reached a real, non-unresolvable verdict
    assert result.note  # a real, populated explanation
