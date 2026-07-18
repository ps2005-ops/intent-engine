"""Offline end-to-end tests for scripts/daily_market_predictions.py —
fake client + fake fetchers, tmp ledger, tmp spend log. The live
end-to-end (real FRED/Tiingo + real model calls) happens on the Mac's
first cron run, same convention as M7's live verification."""

import json
import sys
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import daily_market_predictions as runner  # noqa: E402

from intent_engine.core import daily_prediction_policy as policy  # noqa: E402
from intent_engine.core.macro_data import FredSeries  # noqa: E402
from intent_engine.core.market_resolution import TiingoSeries  # noqa: E402
from intent_engine.core.prediction_ledger import list_predictions  # noqa: E402

AS_OF = date(2026, 7, 20)  # Monday


def _dates_back(n, end=AS_OF):
    return [(end - timedelta(days=n - 1 - i)).isoformat() for i in range(n)]


def _fake_fred(series_id, start, end):
    n = 400
    if series_id == "T10Y2Y":
        obs = [(d, 0.45) for d in _dates_back(12)]
    elif series_id == "BAMLH0A0HYM2":
        obs = [(d, 3.5) for d in _dates_back(3650)]
    elif series_id == "CPIAUCSL":
        base = 300.0
        obs = [(d, base * (1.003 ** i)) for i, d in enumerate(_dates_back(30 * 26))][-780:]
    elif series_id == "UNRATE":
        obs = [(d, 4.3) for d in _dates_back(n)]
    else:  # DGS10 / VIXCLS rotating extra
        obs = [(d, 4.1) for d in _dates_back(90)]
    return FredSeries(series_id=series_id, realtime_date=AS_OF.isoformat(), observations=obs)


def _fake_tiingo(symbol, start, end):
    obs = [(d, 500.0 + i * 0.1) for i, d in enumerate(_dates_back(260))]
    obs = [(d, v) for d, v in obs if start <= d <= end]
    return TiingoSeries(symbol=symbol, observations=obs)


def _fake_client(draft_predictions):
    client = MagicMock()
    client.call_tool.side_effect = [
        {"trigger_conditions": []},           # extraction call
        {"predictions": draft_predictions},   # drafting call
    ]
    return client


def _cand(symbol, days, op=">=", value=0.02):
    return {
        "claim_text": f"{symbol} moves {op}{value} within {days}d (P=0.60 by then)",
        "probability": 0.6,
        "resolve_by": (AS_OF + timedelta(days=days)).isoformat(),
        "resolution_rule": {"type": "pct_change", "symbol": symbol, "op": op,
                            "value": value, "window_days": days},
    }


def _run(tmp_path, monkeypatch, drafts, as_of=AS_OF, spend_rows=None):
    ledger = tmp_path / "ledger.db"
    monkeypatch.setattr(runner, "SPEND_LOG_PATH", tmp_path / "spend.jsonl")
    summary = runner.run_daily(
        "test-entity", as_of=as_of, ledger_path=ledger,
        client=_fake_client(drafts),
        fred_fetcher=_fake_fred, price_fetcher=_fake_tiingo,
        spend_rows=spend_rows if spend_rows is not None else [],
    )
    return summary, ledger, tmp_path / "spend.jsonl"


def test_records_within_cap_and_writes_spend_row(tmp_path, monkeypatch):
    drafts = [_cand("SPY", 14), _cand("SPY", 30), _cand("SPY", 60, op="<=", value=-0.05)]
    summary, ledger, spend_log = _run(tmp_path, monkeypatch, drafts)
    assert summary["status"] == "ok"
    assert summary["recorded"] == 3
    assert summary["model_calls"] == 2 and summary["data_calls"] == 6
    market = list_predictions(source="market", path=ledger)
    assert len(market) == 3
    assert all(p.horizon_days is not None and p.direction is not None for p in market)
    rows = [json.loads(l) for l in spend_log.read_text().splitlines()]
    assert rows[-1]["status"] == "ok" and rows[-1]["model_calls"] == 2


def test_baselines_unconditional_daily_pair(tmp_path, monkeypatch):
    # 2026-07-18 amendment (option 1): pair recorded regardless of buckets used.
    summary, ledger, _ = _run(tmp_path, monkeypatch, [_cand("SPY", 60)])
    assert summary["baselines"] == policy.BASELINE_DAILY_CAP
    assert len(list_predictions(source="baseline", path=ledger)) == policy.BASELINE_DAILY_CAP

    (tmp_path / "b").mkdir()
    summary2, ledger2, _ = _run(tmp_path / "b", monkeypatch, [_cand("SPY", 30)])
    assert summary2["baselines"] == policy.BASELINE_DAILY_CAP
    assert len(list_predictions(source="baseline", path=ledger2)) == policy.BASELINE_DAILY_CAP


def test_baseline_cap_holds_across_double_run_same_day(tmp_path, monkeypatch):
    ledger = tmp_path / "ledger.db"
    monkeypatch.setattr(runner, "SPEND_LOG_PATH", tmp_path / "spend.jsonl")

    def go():
        return runner.run_daily(
            "test-entity", as_of=AS_OF, ledger_path=ledger,
            client=_fake_client([_cand("SPY", 30)]),
            fred_fetcher=_fake_fred, price_fetcher=_fake_tiingo, spend_rows=[],
        )

    first = go()
    assert first["baselines"] == policy.BASELINE_DAILY_CAP
    second = go()
    assert second["baselines"] == 0  # cap already consumed today
    assert len(list_predictions(source="baseline", path=ledger)) == policy.BASELINE_DAILY_CAP


def test_policy_rejections_surface_in_summary(tmp_path, monkeypatch):
    drafts = [_cand("TSLA", 30), _cand("SPY", 5)]  # off-allowlist + below floor
    summary, ledger, _ = _run(tmp_path, monkeypatch, drafts)
    assert summary["recorded"] == 0
    assert len(summary["rejected"]) == 2
    assert list_predictions(source="market", path=ledger) == []


def test_parks_on_spend_ceiling_without_any_calls(tmp_path, monkeypatch):
    over = [{"date": AS_OF.replace(day=1).isoformat(), "model_calls": 2}] * 349
    summary, ledger, spend_log = _run(tmp_path, monkeypatch, [_cand("SPY", 30)], spend_rows=over)
    assert summary["status"] == "PARKED-spend-ceiling"
    assert summary["model_calls"] == 0 and summary["data_calls"] == 0
    assert list_predictions(path=ledger) == []
    rows = [json.loads(l) for l in spend_log.read_text().splitlines()]
    assert rows[-1]["status"] == "PARKED-spend-ceiling"


def test_non_trading_day_is_a_no_op(tmp_path, monkeypatch):
    saturday = date(2026, 7, 18)
    summary, ledger, spend_log = _run(tmp_path, monkeypatch, [_cand("SPY", 30)], as_of=saturday)
    assert summary["status"] == "skipped-non-trading-day"
    assert not spend_log.exists()
    assert list_predictions(path=ledger) == []


def test_drafting_schema_has_no_record_field_and_cap_matches_policy():
    props = runner.DAILY_DRAFT_TOOL_SCHEMA["properties"]["predictions"]
    assert props["maxItems"] == policy.DAILY_CAP
    item_fields = set(props["items"]["properties"].keys())
    assert item_fields == {"claim_text", "probability", "resolve_by", "resolution_rule"}
