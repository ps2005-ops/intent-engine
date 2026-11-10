"""The PAPER_CONTROL contract — every clause asserted, not intended.

These tests exist because a control is the most plausible route by which a
failed strategy could quietly acquire the appearance of alpha. Most of them
assert a REFUSAL.
"""
import json

import pytest

from intent_engine.market import competition as COMP
from intent_engine.market import intelligence_export as IX
from intent_engine.market import paper_engine as PE
from intent_engine.market import strategy as ST


# --- 1. LABEL ---------------------------------------------------------------
def test_the_label_is_one_string_used_everywhere():
    assert PE.CONTROL_LABEL == "PAPER_CONTROL — NO ALPHA CLAIM"


def test_every_entry_and_resolution_carries_the_label():
    e = PE.Entry("s.v1", "AAPL", "2026-01-05", "long", 100.0, 5,
                 "2026-01-12", 0.1, "r")
    r = PE.Resolution("s.v1", "AAPL", "2026-01-05", "2026-01-12", "long",
                      100.0, 101.0, 0.01, 0.001, 0.009, 5, True)
    assert e.as_dict()["label"] == PE.CONTROL_LABEL
    assert r.as_dict()["label"] == PE.CONTROL_LABEL
    assert e.as_dict()["alpha_claim"] is False
    assert r.as_dict()["alpha_claim"] is False


# --- 3. NO PROMOTION CONTAMINATION -----------------------------------------
def test_control_is_not_a_lifecycle_state():
    assert PE.PAPER_CONTROL not in ST.STATES


def test_controls_are_stripped_before_any_alpha_computation():
    rows = [{"mode": PE.PAPER_CONTROL, "label": PE.CONTROL_LABEL,
             "alpha_claim": False, "net_return": 0.9},
            {"mode": "PAPER_CHALLENGER", "alpha_claim": True,
             "net_return": 0.01}]
    kept = PE.excluded_from_alpha(rows)
    assert len(kept) == 1
    assert kept[0]["mode"] == "PAPER_CHALLENGER"


def test_a_control_cannot_be_promoted_through_the_lifecycle(tmp_path):
    """It is not a state, so there is no edge into champion from it."""
    for state in ST.STATES:
        assert PE.PAPER_CONTROL not in ST._TRANSITIONS[state]


# --- 4. CALIBRATION SEPARATION ---------------------------------------------
def _res(n=5, **kw):
    base = dict(security="AAPL", opened_at="2026-01-05",
                resolved_at="2026-01-12", cost=0.001, net_return=0.01,
                benchmark_return=0.005)
    base.update(kw)
    return [dict(base, security=f"S{i}") for i in range(n)]


def test_engine_calibration_validates_mechanics_only():
    out = PE.engine_calibration(_res())
    assert out["kind"] == PE.ENGINE_CALIBRATION
    assert out["cost_accounting_coverage"] == 1.0
    assert out["benchmark_coverage"] == 1.0
    assert "signal quality" in out["does_not_validate"]


def test_strategy_calibration_refuses_control_data():
    """The function a future reader is most likely to misuse."""
    out = PE.strategy_calibration("baseline_momentum.v1", False, _res(500))
    assert out["measurable"] is False
    assert out["eligible"] is False
    assert "not the signal" in out["reason"]


def test_strategy_calibration_opens_only_after_the_gates_pass():
    out = PE.strategy_calibration("x.v1", True, _res(50))
    assert out["eligible"] is True


# --- 5. CAPACITY PROTECTION -------------------------------------------------
def test_capacity_constants_exist_and_are_bounded():
    assert PE.MAX_AGGREGATE_CONTROL_POSITIONS < 100
    assert PE.MAX_CONTROL_NOTIONAL <= PE.STARTING_EQUITY / 2
    assert PE.MAX_PER_SECTOR < PE.MAX_CONCURRENT_PER_STRATEGY


def test_a_challenger_takes_priority_over_a_control(tmp_path):
    """A control must never be the reason a genuine challenger cannot trade."""
    from tests.test_paper_engine import _sec, _series
    from intent_engine.market import strategy_library as LIB
    book = PE.PaperBook("baseline_momentum.v1", root=str(tmp_path))
    s = _series()
    many = [_sec(f"S{i}") for i in range(40)]
    hungry = PE.open_entries(
        strategy_key="baseline_momentum.v1", signal_fn=LIB.baseline_momentum,
        primary_horizon=5, securities=many, series_for=lambda x: s,
        as_of=sorted(s)[60], book=book,
        aggregate_open=0, challenger_demand=PE.MAX_AGGREGATE_CONTROL_POSITIONS)
    assert hungry == [], "a control must yield all capacity to a challenger"


def test_the_aggregate_cap_binds_across_strategies(tmp_path):
    from tests.test_paper_engine import _sec, _series
    from intent_engine.market import strategy_library as LIB
    book = PE.PaperBook("mean_reversion.v1", root=str(tmp_path))
    s = _series()
    out = PE.open_entries(
        strategy_key="mean_reversion.v1", signal_fn=LIB.baseline_momentum,
        primary_horizon=5, securities=[_sec(f"S{i}") for i in range(40)],
        series_for=lambda x: s, as_of=sorted(s)[60], book=book,
        aggregate_open=PE.MAX_AGGREGATE_CONTROL_POSITIONS - 2)
    assert len(out) <= 2


def test_correlated_sector_exposure_is_capped(tmp_path):
    from tests.test_paper_engine import _series
    from intent_engine.market import strategy_library as LIB
    from intent_engine.market import universe_tiers as UT
    book = PE.PaperBook("s.v1", root=str(tmp_path))
    s = _series()
    tech = [UT.Security(symbol=f"T{i}", security_type=UT.EQUITY,
                        sector="Technology") for i in range(30)]
    out = PE.open_entries(strategy_key="s.v1",
                          signal_fn=LIB.baseline_momentum, primary_horizon=5,
                          securities=tech, series_for=lambda x: s,
                          as_of=sorted(s)[60], book=book)
    assert len(out) <= PE.MAX_PER_SECTOR


def test_a_graduated_control_drops_to_canary_size(tmp_path):
    from tests.test_paper_engine import _sec, _series
    from intent_engine.market import strategy_library as LIB
    book = PE.PaperBook("s.v1", root=str(tmp_path))
    s = _series()
    out = PE.open_entries(strategy_key="s.v1",
                          signal_fn=LIB.baseline_momentum, primary_horizon=5,
                          securities=[_sec(f"S{i}") for i in range(30)],
                          series_for=lambda x: s, as_of=sorted(s)[60],
                          book=book, canary=True)
    assert len(out) <= PE.CANARY_MAX_POSITIONS


# --- 7. BENCHMARK -----------------------------------------------------------
def test_benchmark_uses_the_identical_window():
    series = {"2026-01-05": 100.0, "2026-01-12": 110.0}
    assert PE.benchmark_return(series, "2026-01-05", "2026-01-12") == \
        pytest.approx(0.1)


def test_a_missing_benchmark_endpoint_is_none_not_zero():
    """A zero would turn 'we could not measure it' into 'it did not move',
    which flatters every excess return computed from it."""
    assert PE.benchmark_return({"2026-01-05": 100.0}, "2026-01-05",
                               "2026-01-12") is None
    assert PE.benchmark_return({}, "a", "b") is None


# --- 9. GRADUATION ----------------------------------------------------------
def test_a_fresh_control_has_not_graduated():
    g = PE.graduation_status([])
    assert g["graduated"] is False
    assert g["mode"] == PE.PAPER_CONTROL
    assert g["unmet"]


def test_graduation_requires_every_preregistered_condition():
    plenty = [dict(security=f"S{i%40}", opened_at=f"2026-01-{(i%28)+1:02d}",
                   resolved_at="2026-02-01", cost=0.001, net_return=0.01,
                   benchmark_return=0.004) for i in range(250)]
    assert PE.graduation_status(plenty)["graduated"] is True
    # one integrity incident is enough to withhold graduation
    assert PE.graduation_status(plenty, integrity_incidents=1)["graduated"] \
        is False


def test_a_graduated_control_does_not_become_a_challenger():
    plenty = [dict(security=f"S{i%40}", opened_at=f"2026-01-{(i%28)+1:02d}",
                   resolved_at="2026-02-01", cost=0.001, net_return=0.01,
                   benchmark_return=0.004) for i in range(250)]
    g = PE.graduation_status(plenty)
    assert g["mode"] == "CANARY"
    assert "does NOT become a challenger" in g["note"]
    assert g["mode"] not in ST.STATES


# --- A6. SANITIZED EXPORT ---------------------------------------------------
def _closes(n=300, base=100.0, step=0.3, start="2025-01-02"):
    from datetime import date, timedelta
    d, out, i = date.fromisoformat(start), {}, 0
    while len(out) < n:
        if d.weekday() < 5:
            out[d.isoformat()] = base + step * i
            i += 1
        d += timedelta(days=1)
    return out


def test_the_export_emits_no_forbidden_key():
    payload = IX.export_company(ticker="AAPL", closes=_closes(),
                                benchmark_closes=_closes(),
                                as_of="2026-01-30")
    text = json.dumps(payload).lower()
    for banned in ("win_rate", "strategy_key", "sharpe", "api_key",
                   "checkpoint", "paper_control"):
        assert banned not in text, banned


def test_the_export_fails_closed_with_no_data():
    payload = IX.export_company(ticker="NADA", closes={},
                                benchmark_closes={}, as_of="2026-01-30")
    assert payload["latest_completed_market_date"] is None
    for window in ("1m", "3m", "1y"):
        assert payload["price_change"][window]["status"] == IX.UNMEASURABLE
        assert payload["price_change"][window]["value"] is None
    assert payload["limitations"]


def test_the_export_never_fabricates_fundamentals():
    payload = IX.export_company(ticker="AAPL", closes=_closes(),
                                as_of="2026-01-30")
    assert payload["fundamentals"]["status"] == IX.UNMEASURABLE
    assert payload["earnings_events"]["status"] == IX.UNMEASURABLE


def test_the_export_marks_observed_versus_inferred():
    payload = IX.export_company(ticker="AAPL", closes=_closes(),
                                benchmark_closes=_closes(),
                                as_of="2026-01-30")
    assert payload["price_change"]["1m"]["status"] == IX.OBSERVED
    assert payload["volatility"]["status"] == IX.INFERRED
    assert "assuming" in payload["volatility"]["note"]


def test_the_export_carries_lineage_and_freshness():
    payload = IX.export_company(ticker="AAPL", closes=_closes(),
                                as_of="2026-01-30")
    assert payload["lineage"]["method"].startswith("point-in-time")
    assert payload["freshness"]["status"] == IX.OBSERVED
    assert "age_days" in payload["freshness"]


def test_benchmark_relative_is_unmeasurable_without_a_benchmark():
    payload = IX.export_company(ticker="AAPL", closes=_closes(),
                                benchmark_closes={}, as_of="2026-01-30")
    assert payload["benchmark_relative"]["1m"]["status"] == IX.UNMEASURABLE


def test_the_export_states_what_may_and_may_not_be_said():
    payload = IX.export_company(ticker="AAPL", closes=_closes(),
                                as_of="2026-01-30")
    assert payload["disclaimer"]
    assert any("recommendation" in s
               for s in payload["interpretation_forbidden"])
    assert any("engine trading performance" in s
               for s in payload["interpretation_forbidden"])


def test_a_leaked_internal_field_raises():
    with pytest.raises(IX.ExportLeak):
        IX._assert_sanitized({"ok": 1, "nested": {"win_rate": 0.61}})
