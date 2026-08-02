"""The market engine's intelligence reaching the founder UI.

TWO DEAD LINKS IN ONE CHAIN, both found by opening the dashboard and reading
"Market trajectory: Unavailable" on a company whose snapshot was on disk:

  1. both call sites read `self.config.data_dir`; AppConfig has no such field,
     so every lookup raised AttributeError into a bare `except Exception`;
  2. both read `identity["ticker"]`; the identity record carries
     `listings: [{"exchange": ..., "ticker": ...}]` and no `ticker` key.

Either alone was enough to guarantee the market module never appeared. The
export file was never the problem.
"""
import dataclasses
import json
import pathlib
import tempfile

from intent_engine.webapp.app import WebApp
from intent_engine.webapp.config import AppConfig


def _app(tmp):
    cfg = AppConfig(env="test", secret="s" * 40, demo_mode=True,
                    web_store_path=tmp / "w.jsonl",
                    fi_store_path=tmp / "fi.jsonl",
                    ci_store_path=tmp / "ci.jsonl")
    return WebApp(cfg, resolver=False)


def test_appconfig_still_has_no_data_dir_so_nothing_may_read_one():
    """The field the old code read does not exist. If someone adds one, this
    test should be deleted deliberately -- not discovered by a blank panel."""
    names = {f.name for f in dataclasses.fields(AppConfig)}
    assert "data_dir" not in names


def test_the_ticker_comes_from_listings_not_a_ticker_key():
    identity = {"listings": [{"exchange": "NASDAQ", "ticker": "PLTR"}]}
    assert WebApp._ticker_of(identity) == "PLTR"
    assert WebApp._ticker_of({"ticker": "SHOP"}) == "SHOP"   # legacy shape
    assert WebApp._ticker_of({}) == ""
    assert WebApp._ticker_of({"listings": []}) == ""


def test_a_published_snapshot_is_actually_read(tmp_path):
    app = _app(tmp_path)
    export = (app._runtime_root / "reports" / "market" / "export")
    export.mkdir(parents=True, exist_ok=True)
    (export / "PLTR.json").write_text(json.dumps({
        "export_version": "market_intel_export.v1", "ticker": "PLTR",
        "latest_completed_market_date": "2026-07-31",
        "freshness": {"age_days": 1},
        "price_change": {"1m": {"value": -0.021, "status": "observed"}},
        "benchmark_relative": {"1y": {"value": -0.41, "status": "observed"}},
        "volatility": {"value": 0.47, "status": "observed"},
        "fundamentals": {"status": "unmeasurable"},
        "signal": {"state": "quiet"}}))
    context = app._market_snapshot("PLTR")
    assert context["available"] is True, context
    assert context.get("modules")


def test_a_missing_snapshot_says_so_without_pretending_it_failed(tmp_path):
    context = _app(tmp_path)._market_snapshot("NOSUCH")
    assert context["available"] is False
    assert "no market snapshot" in (context.get("reason", "")
                                    + context.get("unavailable_reason", "")
                                    ).lower()


def test_market_context_never_reports_engine_trading_performance(tmp_path):
    """The export's own FORBIDDEN_KEYS bans these upstream; the founder side
    must not reintroduce them, and the release gate fails the page if it does.
    """
    app = _app(tmp_path)
    export = (app._runtime_root / "reports" / "market" / "export")
    export.mkdir(parents=True, exist_ok=True)
    (export / "PLTR.json").write_text(json.dumps({
        "export_version": "market_intel_export.v1", "ticker": "PLTR",
        "latest_completed_market_date": "2026-07-31",
        "freshness": {"age_days": 1},
        "price_change": {"1m": {"value": -0.021, "status": "observed"}},
        "signal": {"state": "quiet"}}))
    rendered = json.dumps(app._market_snapshot("PLTR")).lower()
    for banned in ("win_rate", "win rate", "sharpe", "alpha", "expectancy",
                   "strategy_key", "target_price", "forecast"):
        assert banned not in rendered, banned
