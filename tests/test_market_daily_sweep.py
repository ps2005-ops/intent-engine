"""The daily sweep, end to end against the real hosted wiring.

The property under test is the one the whole phase turns on: a daily cycle now
LEAVES A RECORD for every company it looked at, including the ones it declined.
Before this job, `predict_fn` returned None unconditionally and a full day's run
stored nothing at all — no prediction, no outcome, nothing to learn from.

Injected fakes and a temp sqlite file; no network.
"""
import tempfile

from intent_engine.hosted.context import HostedContext
from intent_engine.hosted.jobs import JOBS
from intent_engine.market.daily import OPPORTUNITY_STREAM
from intent_engine.market.opportunity import (
    NO_MARKET_EVIDENCE,
    NOT_TRADABLE,
)
from intent_engine.paper.broker import FakeAlpacaPaperBroker
from intent_engine.storage.durable import DurableStore
from intent_engine.universe.companies import default_universe

DAY = "2026-07-30"


def _research_fn(company, as_of):
    return {"thesis": f"{company.canonical_name}: bounded thesis",
            "priorities": ["growth"],
            "evidence": [{"kind": "filing", "summary": "quarterly filing",
                          "source": "10-Q", "published_at": as_of,
                          "confidence": 0.7}]}


def _never_predicts(company, state, as_of):
    """The production default: the placeholder adapter that returns nothing.

    Kept deliberately, so this test measures what the SWEEP contributes rather
    than borrowing a fake predictor's output.
    """
    return None


def _ctx():
    tmp = tempfile.mkdtemp()
    return HostedContext(
        store=DurableStore(f"sqlite:///{tmp}/sweep.db"),
        broker=FakeAlpacaPaperBroker(equity=100_000),
        universe=default_universe(), predict_fn=_never_predicts,
        price_at=lambda s, d: 100.0, research_fn=_research_fn, regime="calm")


def _stored(ctx):
    return list(ctx.store.latest(OPPORTUNITY_STREAM))


def test_a_days_run_records_a_decision_for_every_company():
    ctx = _ctx()
    JOBS["company-intelligence-refresh"](ctx, DAY)
    result = JOBS["daily-opportunity-sweep"](ctx, DAY)

    assert result["evaluated"] > 0, "a daily cycle that evaluates nothing"
    rows = _stored(ctx)
    assert len(rows) == result["evaluated"]
    # every stored row carries the reason, not just the verdict
    for row in rows:
        payload = row.payload if hasattr(row, "payload") else row["payload"]
        assert payload["classification"]
        assert payload["rationale"].strip()


def test_the_rejections_are_kept_because_they_are_the_training_data():
    ctx = _ctx()
    JOBS["company-intelligence-refresh"](ctx, DAY)
    result = JOBS["daily-opportunity-sweep"](ctx, DAY)
    counts = result["by_classification"]
    # nothing is traded on this evidence, and that is the correct outcome --
    # what matters is that the decisions still exist afterwards
    assert sum(counts.values()) == result["evaluated"]
    assert result["evaluated"] == len(_stored(ctx))


def test_the_private_company_is_recorded_as_untradable_not_skipped():
    ctx = _ctx()
    JOBS["company-intelligence-refresh"](ctx, DAY)
    JOBS["daily-opportunity-sweep"](ctx, DAY)
    payloads = [(r.payload if hasattr(r, "payload") else r["payload"])
                for r in _stored(ctx)]
    untradable = [p for p in payloads if NOT_TRADABLE in p["blocked_by"]]
    assert untradable, "a private company vanished instead of being recorded"
    assert all(p["classification"] == "NO_TRADE" for p in untradable)


def test_the_sweep_names_what_stopped_it_so_the_backlog_can_be_ranked():
    """The daily system review has to answer "what blocked us this month?".
    That question is only answerable if the gate is on the record."""
    ctx = _ctx()
    JOBS["company-intelligence-refresh"](ctx, DAY)
    result = JOBS["daily-opportunity-sweep"](ctx, DAY)
    assert result["blocked_by"], "no gate was recorded"
    # with no market-evidence adapter wired, that is the honest headline
    assert NO_MARKET_EVIDENCE in result["blocked_by"] or \
        NOT_TRADABLE in result["blocked_by"]


def test_running_the_day_twice_records_one_opinion_per_company():
    ctx = _ctx()
    JOBS["company-intelligence-refresh"](ctx, DAY)
    first = JOBS["daily-opportunity-sweep"](ctx, DAY)
    second = JOBS["daily-opportunity-sweep"](ctx, DAY)
    assert first["evaluated"] == second["evaluated"]
    assert len(_stored(ctx)) == first["evaluated"], \
        "a re-fired workflow doubled the day's opinions"


def test_no_position_is_opened_without_market_evidence():
    """The guard that keeps the loop honest while the market adapter is
    missing: a full day may run and legitimately open nothing."""
    ctx = _ctx()
    JOBS["company-intelligence-refresh"](ctx, DAY)
    result = JOBS["daily-opportunity-sweep"](ctx, DAY)
    assert result["predictions_generated"] == 0
    assert result["by_classification"].get("BUY", 0) == 0
    assert result["by_classification"].get("SELL", 0) == 0
