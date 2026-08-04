"""The market contract reaching the founder UI.

THREE DEAD LINKS IN ONE CHAIN, each of which alone guaranteed the market
module never appeared. The first two were found by opening the dashboard and
reading "Market trajectory: Unavailable" on a company whose snapshot was on
disk; the third by looking for the disk it was supposedly on.

  1. both call sites read `self.config.data_dir`; AppConfig has no such field,
     so every lookup raised AttributeError into a bare `except Exception`;
  2. both read `identity["ticker"]`; the identity record carries
     `listings: [{"exchange": ..., "ticker": ...}]` and no `ticker` key;
  3. nothing was WRITING an export, so once the path and the ticker were both
     right there was still no file to read.

The export file was never the problem, and then it was the only problem.
"""
import dataclasses
import datetime
import json

from intent_engine.external_intel import market_producer as MP
from intent_engine.webapp.app import WebApp
from intent_engine.webapp.config import AppConfig

TODAY = datetime.date.today().isoformat()


def _app(tmp):
    cfg = AppConfig(env="test", secret="s" * 40, demo_mode=True,
                    web_store_path=tmp / "w.jsonl",
                    fi_store_path=tmp / "fi.jsonl",
                    ci_store_path=tmp / "ci.jsonl")
    return WebApp(cfg, resolver=False)


def _closes(n=300, start=100.0, step=0.25):
    out, day, price = {}, datetime.date.today() - datetime.timedelta(days=1), start
    while len(out) < n:
        if day.weekday() < 5:
            out[day.isoformat()] = round(price, 4)
            price += step
        day -= datetime.timedelta(days=1)
    return out


def _publish(app, ticker="PLTR"):
    payload = MP.build_export(
        ticker=ticker, closes=_closes(), benchmark_closes=_closes(start=400.0),
        as_of=TODAY, exchange="NASDAQ", currency="USD")
    return MP.write_export(payload, app._runtime_root)


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


def test_a_published_snapshot_is_actually_read(tmp_path, monkeypatch):
    app = _app(tmp_path)
    _publish(app)
    monkeypatch.setattr(app, "_listing_for",
                        lambda run_id: _Listing("PLTR", "NASDAQ"))
    context = app._market_snapshot("run-1")
    assert context["available"] is True, context
    assert context.get("modules")
    assert context["ticker"] == "PLTR"


def test_a_v1_export_is_refused_rather_than_best_efforted(tmp_path,
                                                          monkeypatch):
    """v1 and v2 disagree about units -- v1 stored 0.021 for 2.1%.

    Reading a v1 file with v2's code would render "the shares rose 0.0%" from
    a real 2.1% move. Refusing is the only safe answer to a version it does
    not understand.
    """
    app = _app(tmp_path)
    export = app._runtime_root / "reports" / "market" / "export"
    export.mkdir(parents=True, exist_ok=True)
    (export / "PLTR.json").write_text(json.dumps({
        "export_version": "market_intel_export.v1", "ticker": "PLTR",
        "latest_completed_market_date": "2026-07-31",
        "price_change": {"1m": {"value": -0.021, "status": "observed"}}}))
    monkeypatch.setattr(app, "_listing_for",
                        lambda run_id: _Listing("PLTR", "NASDAQ"))
    context = app._market_snapshot("run-1")
    assert context["available"] is False
    assert not context["modules"]


def test_a_missing_snapshot_says_so_without_pretending_it_failed(tmp_path,
                                                                 monkeypatch):
    app = _app(tmp_path)
    monkeypatch.setattr(app, "_listing_for",
                        lambda run_id: _Listing("NOSUCH", ""))
    context = app._market_snapshot("run-1")
    assert context["available"] is False
    assert "no market snapshot" in context.get("reason", "").lower()


def test_a_company_with_no_listing_says_that_rather_than_no_snapshot(
        tmp_path, monkeypatch):
    """A private company and a failed lookup are different facts."""
    app = _app(tmp_path)
    monkeypatch.setattr(app, "_listing_for", lambda run_id: _Listing("", ""))
    context = app._market_snapshot("run-1")
    assert context["available"] is False
    assert "no ticker" in context.get("reason", "").lower()


def test_market_context_never_reports_engine_trading_performance(
        tmp_path, monkeypatch):
    """The contract's allowlist bans these upstream; the founder side must not
    reintroduce them, and the release gate fails the page if it does."""
    app = _app(tmp_path)
    _publish(app)
    monkeypatch.setattr(app, "_listing_for",
                        lambda run_id: _Listing("PLTR", "NASDAQ"))
    rendered = json.dumps(app._market_snapshot("run-1")).lower()
    for banned in ("win_rate", "win rate", "sharpe", "alpha", "expectancy",
                   "strategy_key", "target_price", "signal_fired",
                   "positions_opened", "paper_control"):
        assert banned not in rendered, banned


def test_rendering_a_page_can_never_start_a_network_fetch(tmp_path,
                                                          monkeypatch):
    """The refresh policy, asserted at the boundary that enforces it.

    A founder opening a brief must not be able to trigger a market download;
    only the analysis path may fetch.
    """
    app = _app(tmp_path)
    monkeypatch.setattr(app, "_listing_for",
                        lambda run_id: _Listing("PLTR", "NASDAQ"))

    def explode(*a, **k):  # pragma: no cover - must never be called
        raise AssertionError("a page render attempted a network fetch")

    monkeypatch.setattr("intent_engine.external_intel.prices._http_get",
                        explode)
    context = app._market_snapshot("run-1")
    assert context["available"] is False


class _Listing:
    """The shape `_listing_for` returns, narrowed to what these tests use."""

    def __init__(self, ticker, exchange, status="PUBLIC", is_public=True):
        self.ticker = ticker
        self.exchange = exchange
        self.status = status
        self.is_public = is_public
