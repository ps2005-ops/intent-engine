"""Tests for core/regime_report.py (Task M7, market-engine-execution-
plan.md). Plumbing only, mocked -- the real end-to-end verification
(bars a/b/c) is a real live run, recorded in reports/market_engine_trace.md,
not reproducible offline.
"""

from unittest.mock import MagicMock

import pytest

from intent_engine.core.mechanism_library import RankedMechanism, load_mechanisms
from intent_engine.core.prediction_ledger import _read_all
from intent_engine.core.macro_data import FredSeries
from intent_engine.core.regime_report import (
    DRAFT_TOOL_SCHEMA,
    assert_language_walls,
    draft_market_predictions,
    fetch_current_series_data,
    render_calibration_footer,
    render_mechanisms_section,
    render_snapshot_numbers_for_extraction,
    render_snapshot_table,
)


def _fake_client(predictions):
    client = MagicMock()
    client.call_tool.return_value = {"predictions": predictions}
    return client


# --- house pattern: model drafts, code decides ------------------------------


def test_draft_tool_schema_has_no_record_include_field():
    """Same Stage-2-citation-style check as premortem_prediction_bridge's
    own test: the schema the model sees literally cannot express "record
    this" or "here's my id" for anything."""
    item_schema = DRAFT_TOOL_SCHEMA["properties"]["predictions"]["items"]["properties"]
    assert set(item_schema.keys()) == {"claim_text", "probability", "resolve_by", "resolution_rule"}
    for forbidden in ("id", "include", "record", "source", "entity_id"):
        assert forbidden not in item_schema


def test_draft_market_predictions_records_valid_predictions(tmp_path):
    path = tmp_path / "ledger.db"
    client = _fake_client([
        {"claim_text": "SPY possibly rises 2%+ within 60 days", "probability": 0.55, "resolve_by": "2026-12-31",
         "resolution_rule": {"type": "pct_change", "symbol": "SPY", "op": ">=", "value": 0.02, "window_days": 60}},
    ])
    predictions = draft_market_predictions("macro-watch", "snapshot text", "mechanisms text", client=client, ledger_path=path)
    assert len(predictions) == 1
    assert predictions[0].source == "market"
    assert predictions[0].resolution_rule.symbol == "SPY"
    rows = _read_all(path)
    assert len(rows) == 1


def test_draft_market_predictions_skips_malformed_resolution_rule(tmp_path):
    path = tmp_path / "ledger.db"
    client = _fake_client([
        {"claim_text": "bad rule", "probability": 0.5, "resolve_by": "2026-12-31",
         "resolution_rule": {"type": "pct_change", "op": ">="}},  # missing symbol/value/window_days
        {"claim_text": "good one", "probability": 0.4, "resolve_by": "2026-12-31",
         "resolution_rule": {"type": "level", "series": "UNRATE", "op": ">=", "value": 4.5, "by": "2026-12-31"}},
    ])
    predictions = draft_market_predictions("macro-watch", "snapshot text", "mechanisms text", client=client, ledger_path=path)
    assert len(predictions) == 1  # only the well-formed one persisted
    assert predictions[0].claim_text == "good one"


def test_draft_market_predictions_skips_non_future_resolve_by(tmp_path):
    path = tmp_path / "ledger.db"
    client = _fake_client([
        {"claim_text": "already past", "probability": 0.5, "resolve_by": "2020-01-01",
         "resolution_rule": {"type": "pct_change", "symbol": "SPY", "op": ">=", "value": 0.02, "window_days": 60}},
    ])
    from datetime import date
    predictions = draft_market_predictions(
        "macro-watch", "snapshot text", "mechanisms text", client=client, ledger_path=path, as_of=date(2026, 7, 17),
    )
    assert predictions == []
    assert not path.exists()


# --- mechanisms section rendering -------------------------------------------


def test_render_mechanisms_section_renders_correct_silence_on_empty():
    text = render_mechanisms_section([])
    assert "none matched" in text.lower()
    assert "no forced match" in text.lower()


def test_render_mechanisms_section_renders_tier_conditions_and_instance():
    bank_run = next(m for m in load_mechanisms() if m.mechanism_id == "bank_run_maturity_mismatch")
    ranked = [RankedMechanism(mechanism=bank_run, overlap_count=2, matched_conditions=["curve_inverted", "interconnected_counterparty_exposure"])]
    text = render_mechanisms_section(ranked)
    assert "Bank-run maturity mismatch" in text
    assert "well_documented" in text
    assert "curve_inverted" in text
    assert "Silicon Valley Bank" in text  # the real historical instance


# --- snapshot table rendering (handles unavailable fields honestly) --------


def test_render_snapshot_table_handles_all_unavailable():
    snapshot = {
        "snapshot_date": "2026-07-17",
        "curve_inversion": "unavailable",
        "credit_spread_percentile": "unavailable",
        "inflation_trend": "unavailable",
        "unemployment_momentum": "unavailable",
        "drawdown_state": "unavailable",
    }
    table = render_snapshot_table(snapshot)
    assert table.count("unavailable") == 5
    assert "2026-07-17" in table


def test_render_snapshot_table_includes_real_provenance_when_present():
    from intent_engine.core.regime_engine import curve_inversion
    result = curve_inversion([("2026-07-15", -0.5)])
    snapshot = {
        "snapshot_date": "2026-07-17",
        "curve_inversion": result,
        "credit_spread_percentile": "unavailable",
        "inflation_trend": "unavailable",
        "unemployment_momentum": "unavailable",
        "drawdown_state": "unavailable",
    }
    table = render_snapshot_table(snapshot)
    assert "inverted" in table
    assert "T10Y2Y" in table
    assert "2026-07-15" in table


# --- calibration footer: read-only, honest about "no resolutions yet" ------


def test_calibration_footer_reports_no_resolutions_yet(tmp_path):
    path = tmp_path / "ledger.db"
    footer = render_calibration_footer(path)
    assert "no resolutions yet" in footer.lower()


def test_calibration_footer_reports_real_counts_once_resolved(tmp_path):
    from intent_engine.core.prediction_ledger import record_prediction, resolve_prediction
    path = tmp_path / "ledger.db"
    p = record_prediction("market", "macro-watch", "claim", 0.6, "2026-12-31", path=path)
    resolve_prediction(p.id, "happened", path=path)
    footer = render_calibration_footer(path)
    assert "market: 1 resolved" in footer
    assert "baseline: no resolutions yet" in footer.lower()


# --- language walls, a real code-level backstop -----------------------------


def test_assert_language_walls_raises_on_will_happen():
    with pytest.raises(ValueError, match="will happen"):
        assert_language_walls("This will happen by December.")


def test_assert_language_walls_raises_on_buy():
    with pytest.raises(ValueError):
        assert_language_walls("Consider whether to buy SPY here.")


def test_assert_language_walls_passes_clean_research_language():
    assert_language_walls("Consistent with elevated credit spreads, P=0.55 by 2026-12-31.")


# --- fetch resilience: a real per-series gap (e.g. a market-holiday "."   --
# --- guard-raise from M1) must omit that series, never crash the report --


def test_fetch_current_series_data_omits_a_series_whose_fetch_raises(capsys):
    def flaky_fred_fetcher(series_id, start, end):
        if series_id == "T10Y2Y":
            raise ValueError("FRED series 'T10Y2Y' has a missing/NaN observation at date='2026-06-19'")
        return FredSeries(series_id=series_id, realtime_date=end, observations=[(end, 1.0)])

    def fake_price_fetcher(symbol, start, end):
        from intent_engine.core.market_resolution import TiingoSeries
        return TiingoSeries(symbol=symbol, observations=[(end, 100.0)])

    from datetime import date
    series_data, price_series = fetch_current_series_data(
        date(2026, 7, 17), fred_fetcher=flaky_fred_fetcher, price_fetcher=fake_price_fetcher,
    )
    assert "T10Y2Y" not in series_data  # omitted, not a crash
    assert "BAMLH0A0HYM2" in series_data  # the other 3 series still fetched fine
    assert "CPIAUCSL" in series_data
    assert "UNRATE" in series_data
    captured = capsys.readouterr()
    assert "T10Y2Y" in captured.out and "WARNING" in captured.out  # never silent


def test_fetch_current_series_data_omits_price_series_on_failure(capsys):
    def fred_fetcher(series_id, start, end):
        return FredSeries(series_id=series_id, realtime_date=end, observations=[(end, 1.0)])

    def flaky_price_fetcher(symbol, start, end):
        raise RuntimeError("Tiingo API returned 503")

    from datetime import date
    series_data, price_series = fetch_current_series_data(
        date(2026, 7, 17), fred_fetcher=fred_fetcher, price_fetcher=flaky_price_fetcher,
    )
    assert price_series == ("SPY", [])
    captured = capsys.readouterr()
    assert "WARNING" in captured.out


def test_render_snapshot_numbers_handles_a_missing_series_gracefully():
    """The rendering function must not KeyError when fetch_current_series_data
    legitimately omitted a series."""
    from datetime import date
    series_data = {
        "BAMLH0A0HYM2": FredSeries(series_id="BAMLH0A0HYM2", realtime_date="2026-07-17", observations=[("2026-07-17", 3.0)]),
    }
    text = render_snapshot_numbers_for_extraction(series_data, ("SPY", []), date(2026, 7, 17))
    assert "T10Y2Y" not in text  # correctly absent, not a crash
    assert "BAMLH0A0HYM2" in text
