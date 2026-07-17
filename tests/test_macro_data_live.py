"""Live smoke test for core/macro_data.py's real FRED wiring (Task M1 bar b).

Skipped automatically when FRED_API_KEY is absent from the environment --
same "skip cleanly so the main suite stays green regardless of what this
environment allows" discipline as test_calendar_live.py /
test_scrap_estimate_live.py. Asserts SHAPE only (real provenance, real
float values, ascending dates) -- not any claim about what the numbers mean
(that's M2's job).
"""

import os

import pytest
from dotenv import load_dotenv

load_dotenv()

pytestmark = pytest.mark.skipif(
    not os.environ.get("FRED_API_KEY"),
    reason="FRED_API_KEY not set in the environment -- see market-engine-execution-plan.md Phase 0.",
)


def test_real_fetch_of_two_series_returns_well_shaped_data(tmp_path):
    from intent_engine.core.macro_data import get_series

    for series_id in ("DFF", "UNRATE"):
        series = get_series(series_id, "2024-01-01", "2024-02-01", cache_dir=tmp_path / "fred_cache")
        assert series.series_id == series_id
        assert series.realtime_date  # non-empty provenance string
        assert len(series.observations) >= 1
        dates = [d for d, _ in series.observations]
        assert dates == sorted(dates)
        for observed_date, value in series.observations:
            assert isinstance(observed_date, str) and len(observed_date) == 10
            assert isinstance(value, float)
