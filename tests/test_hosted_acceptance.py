"""SECTION 18 ACCEPTANCE TEST — the full hosted flow, injected fakes, no network.

Drives three structurally different PUBLIC companies (Shopify / Cloudflare /
Duolingo) through the entire cycle:

    research -> updated company state -> timestamp-valid prediction ->
    eligible paper intent -> Alpaca paper submission -> fill reconciliation ->
    after-close outcome -> company-specific scoring -> daily candidate ->
    weekly evaluation status

...and one PRIVATE company (Stripe): researched + learned from, NO direct paper
order, a labelled proxy, and its failure space available to Synthetic Worlds.

Everything runs against the FakeAlpacaPaperBroker and injected fake research /
prediction / price functions. No real network call is made.
"""
import tempfile

from intent_engine.hosted.candidates import CandidateStore
from intent_engine.hosted.context import HostedContext
from intent_engine.hosted.jobs import JOBS
from intent_engine.hosted.reports import latest_report
from intent_engine.paper.broker import FakeAlpacaPaperBroker
from intent_engine.storage.durable import DurableStore
from intent_engine.universe.companies import default_universe
from intent_engine.universe.research import evidence_for

DAYS = ["2026-07-06", "2026-07-07", "2026-07-08", "2026-07-09", "2026-07-10"]
SETTLE = "2026-07-11"
ALL_DAYS = DAYS + [SETTLE, "2026-07-12"]
_IDX = {d: i for i, d in enumerate(ALL_DAYS)}

# SHOP & NET drift UP (an "up" call hits); DUOL drifts DOWN (an "up" call misses)
_BASE = {"SHOP": 100.0, "NET": 50.0, "DUOL": 200.0}
_DRIFT = {"SHOP": 2.0, "NET": 1.0, "DUOL": -5.0}


def _price_at(symbol, day):
    return _BASE[symbol] + _DRIFT[symbol] * _IDX[day[:10]]


def _research_fn(company, as_of):
    # one valid, dated piece of evidence + one FUTURE-dated piece that MUST be
    # dropped by the leakage check.
    return {
        "thesis": f"{company.canonical_name}: bounded thesis as of {as_of}",
        "priorities": list(company.strategic_priorities) or ["growth"],
        "evidence": [
            {"kind": "filing", "summary": "quarterly filing",
             "source": "10-Q", "published_at": as_of, "confidence": 0.7},
            {"kind": "rumor", "summary": "future leak (must be blocked)",
             "source": "blog", "published_at": "2027-01-01", "confidence": 0.2},
        ],
    }


def _predict_up(company, state, as_of):
    return {"direction": "up", "probability": 0.72, "horizon_days": 1,
            "claim_text": f"{company.canonical_name} up over 1d"}


def _build_ctx():
    tmp = tempfile.mkdtemp()
    store = DurableStore(f"sqlite:///{tmp}/acceptance.db")
    return HostedContext(
        store=store, broker=FakeAlpacaPaperBroker(equity=100_000),
        universe=default_universe(), predict_fn=_predict_up,
        price_at=_price_at, research_fn=_research_fn, regime="calm")


def test_full_hosted_acceptance_flow():
    ctx = _build_ctx()

    first_refresh = None
    for i, day in enumerate(DAYS):
        if i > 0:
            JOBS["prediction-resolution"](ctx, day)         # resolve yesterday
        r = JOBS["company-intelligence-refresh"](ctx, day)
        first_refresh = first_refresh or r
        JOBS["daily-prediction-generation"](ctx, day)
        JOBS["paper-order-submit"](ctx, day)
        # Alpaca "fills" the day's orders during the session
        for o in ctx.orders.open_orders():
            ctx.broker.simulate_fill(o.client_order_id,
                                     price=_price_at(o.instrument, day))
        JOBS["intraday-paper-reconciliation"](ctx, day)

    # settle: resolve the final day + run after-close learning, weekly, synthetic
    JOBS["prediction-resolution"](ctx, SETTLE)
    after = JOBS["after-close-reconciliation-and-learning"](ctx, SETTLE)
    weekly = JOBS["weekly-evaluation"](ctx, SETTLE)
    synth = JOBS["synthetic-daily"](ctx, SETTLE)
    JOBS["monthly-promotion-review"](ctx, SETTLE)

    # --- 1. research updated company state + LEAKAGE blocked ------------------
    assert first_refresh["leaked_evidence_blocked"] >= 1
    from intent_engine.universe.research import company_state
    assert company_state(ctx.store, "shopify").thesis.startswith("Shopify")
    # the future-dated evidence never entered the store
    shop_ev = evidence_for(ctx.store, "shopify")
    assert shop_ev and all(e["published_at"][:4] <= "2026" for e in shop_ev)

    # --- 2. timestamp-valid predictions for the 3 public companies -----------
    for cid in ("shopify", "cloudflare", "duolingo"):
        preds = ctx.predictions.by_company(cid)
        assert preds and all(p.instrument for p in preds)

    # --- 3. eligible intents -> Alpaca submission -> fills -------------------
    filled = [o for o in ctx.orders.all_latest() if o.is_filled]
    assert {o.instrument for o in filled} == {"SHOP", "NET", "DUOL"}
    assert all(o.company_id in ("shopify", "cloudflare", "duolingo")
               for o in filled)

    # --- 4. after-close outcomes + per-company scoring -----------------------
    # per-day resolution already resolved everything, so after-close correctly
    # finds nothing left to resolve (idempotent catch-up). Outcomes accumulated:
    from intent_engine.predictions.resolution import outcomes as all_outcomes
    assert len(all_outcomes(ctx.store)) >= 9          # 3 companies x >=3 days
    assert after["report_written_for"] == SETTLE
    duol = ctx.learning_store.get("duolingo")
    shop = ctx.learning_store.get("shopify")
    assert duol.resolved_count >= 3 and shop.resolved_count >= 3
    assert duol.paper_pnl < 0 < shop.paper_pnl        # DUOL lost, SHOP won
    assert duol.directional_accuracy == 0.0           # every "up" call missed

    # --- 5. daily candidate (company-specific, sample-backed) ----------------
    cands = CandidateStore(ctx.store).all_latest()
    duol_cands = [c for c in cands if c.company_id == "duolingo"]
    assert duol_cands, "expected a company candidate from Duolingo's losses"
    assert all(c.sample_size >= 3 for c in duol_cands)

    # --- 6. weekly evaluation status (human-gated, out-of-sample) ------------
    assert weekly["evaluated"] >= 1
    assert CandidateStore(ctx.store).get(duol_cands[0].id).status == "evaluated"

    # --- 7. nightly report was actually created ------------------------------
    report = latest_report(ctx.store)
    assert report["as_of"] == SETTLE
    assert any(row["company_id"] == "duolingo" for row in report["company"])

    # --- 8. PRIVATE company: researched, NO order, labelled proxy, synthetic -
    assert ctx.orders.by_company("stripe") == []      # never a stock order
    assert not any(o.company_id == "stripe" for o in ctx.orders.all_latest())
    stripe_preds = ctx.predictions.by_company("stripe")
    assert stripe_preds and all(p.instrument is None for p in stripe_preds)  # strategic
    proxy = ctx.universe.by_id("stripe_proxy_ipay")
    assert proxy.proxy_of == "stripe" and proxy.proxy_instrument == "IPAY"
    # Duolingo's real failure feeds Synthetic Worlds; it proves nothing about P&L
    assert synth["scenarios"] >= 1
    assert synth["proves_market_profitability"] is False


def test_no_live_endpoint_and_promotion_stays_human_gated():
    ctx = _build_ctx()
    # the broker is the paper fake; there is no live surface anywhere
    from intent_engine.paper.broker import assert_paper_only, LiveTradingRejected
    import pytest
    with pytest.raises(LiveTradingRejected):
        assert_paper_only("https://api.alpaca.markets")
    # a monthly review PREPARES a packet but promotes nothing
    result = JOBS["monthly-promotion-review"](ctx, SETTLE)
    assert result["promoted"] == 0 and result["human_gated"] is True
