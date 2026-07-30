"""The hosted daily/weekly/monthly cycle as discrete GitHub-Actions jobs.

Every job is a plain function of (ctx, as_of) that connects, does bounded work,
persists to the durable store, and returns a detail dict. They are:

  * IDEMPOTENT — safe to run twice (durable idem keys collapse duplicates);
  * CATCH-UP — each reconcile/resolve processes ALL outstanding records, so a
    delayed or skipped run is recovered by the next (no lost/duplicated order);
  * BUDGET-AWARE — LLM/research work stops safely at the configured caps and
    persists the skipped work.

The JOBS registry maps a workflow's job name to its function; the CLI
(hosted/__main__.py) wraps each in `records.run_job` for a durable execution log.
"""
from __future__ import annotations

from typing import Callable, Dict

from intent_engine.hosted.budget import record_skip
from intent_engine.hosted.candidates import (
    CandidateStore,
    candidate_from_company_state,
)
from intent_engine.hosted.reports import write_daily_report
from intent_engine.market.daily import daily_opportunity_sweep
from intent_engine.paper.reconciliation import (
    close_resolved_positions,
    mark_positions,
    reconcile_orders,
    snapshot_equity,
)
from intent_engine.predictions.generation import (
    build_prediction,
    intents_for_predictions,
)
from intent_engine.predictions.resolution import (
    outcomes_for_company,
    resolve_due,
)
from intent_engine.universe.learning import (
    compute_company_state,
    cross_company_candidates,
    persist_cross_company,
)
from intent_engine.universe.research import all_states, refresh_company

INTENT_STREAM = "paper_intent"

# rough per-call CAD estimate for budget accounting (conservative placeholder)
_CAD_PER_CALL = 0.02


# --- A: company intelligence refresh ----------------------------------------
def company_intelligence_refresh(ctx, as_of: str) -> Dict:
    cap = ctx.budget.max_companies_per_daily_refresh
    refreshed = leaked = skipped = 0
    for company in ctx.universe.prediction_companies()[:cap]:
        ok, why = ctx.budget_ledger.can_spend(as_of, calls=1, cad=_CAD_PER_CALL)
        if not ok:
            record_skip(ctx.store, as_of, item=f"refresh:{company.company_id}",
                        reason=why, company_id=company.company_id)
            skipped += 1
            continue
        r = refresh_company(company, ctx.research_fn, ctx.store, as_of)
        ctx.budget_ledger.record(as_of, calls=1, cad=_CAD_PER_CALL,
                                 kind="research", company_id=company.company_id)
        refreshed += 1
        leaked += len(r["leaked"])
    return {"refreshed": refreshed, "leaked_evidence_blocked": leaked,
            "skipped": skipped}


# --- B: daily prediction generation -----------------------------------------
def daily_prediction_generation(ctx, as_of: str) -> Dict:
    if not ctx.budget.prediction_generation_enabled:
        record_skip(ctx.store, as_of, item="prediction_generation",
                    reason="PREDICTION_GENERATION_ENABLED is off")
        return {"generated": 0, "disabled": True}
    states = all_states(ctx.store)
    cap = ctx.budget.max_companies_per_daily_refresh
    # Idempotent per (company, day): a double-fired generation job must NOT
    # create a second prediction for a company on the same day (which would
    # become a second, duplicate paper order). Skip any company that already
    # has a prediction dated today.
    already_today = {p.entity_id for p in ctx.predictions.all_latest()
                     if (p.created_at or "")[:10] == as_of[:10]}
    generated = 0
    skipped_dupe = 0
    for company in ctx.universe.prediction_companies()[:cap]:
        if company.company_id in already_today:
            skipped_dupe += 1
            continue
        ok, why = ctx.budget_ledger.can_spend(as_of, calls=1, cad=_CAD_PER_CALL)
        if not ok:
            record_skip(ctx.store, as_of, item=f"predict:{company.company_id}",
                        reason=why, company_id=company.company_id)
            continue
        signal = ctx.predict_fn(company, states.get(company.company_id, {}), as_of)
        ctx.budget_ledger.record(as_of, calls=1, cad=_CAD_PER_CALL,
                                 kind="predict", company_id=company.company_id)
        if not signal:
            continue
        ctx.predictions.add(build_prediction(company, signal, as_of))
        generated += 1
    return {"generated": generated, "skipped_already_generated_today": skipped_dupe}


# --- C: paper order submit --------------------------------------------------
def paper_order_submit(ctx, as_of: str) -> Dict:
    trading_date = as_of[:10]
    # a prediction is traded at most once: only those with an instrument, still
    # unresolved, and with NO existing order (the deterministic client_order_id
    # additionally guards a twice-fired submit within a day).
    preds = [p for p in ctx.predictions.unresolved()
             if p.instrument and not ctx.orders.by_prediction(p.id)]
    intents, results = intents_for_predictions(
        preds, ctx.universe, order_repo=ctx.orders, regime=ctx.regime,
        as_of=as_of)

    # Portfolio rule (section 11: "no duplicate exposure exists"): at most ONE
    # open position per instrument. An instrument is occupied while it has an
    # open order, or a filled order whose prediction is still unresolved.
    # Resolution frees it (the prediction gets an outcome), so positions rotate
    # one-at-a-time per instrument instead of stacking duplicate exposure — the
    # defect the 30-day replay surfaced when a late-submitted prediction landed
    # on the same day as a fresh one.
    pred_outcome = {p.id: p.outcome for p in ctx.predictions.all_latest()}
    occupied = set()
    for o in ctx.orders.all_latest():
        unresolved = pred_outcome.get(o.prediction_id) is None
        if (o.is_open or o.is_filled) and unresolved:
            occupied.add(o.instrument)
    deduped = []
    for intent in intents:
        if intent.instrument in occupied:
            ctx.execution.record_rejection(
                prediction_id=intent.prediction_id, instrument=intent.instrument,
                reason=f"instrument {intent.instrument} already has an open "
                       "position (one position per instrument)",
                rule="duplicate_instrument_exposure")
            continue
        occupied.add(intent.instrument)      # also dedupes within this batch
        deduped.append(intent)
    intents = deduped

    by_id = {p.id: p for p in preds}
    for res in results:                       # persist ALL rejection reasons
        if not res.eligible:
            pred = by_id.get(res.prediction_id)
            ctx.execution.record_rejection(
                prediction_id=res.prediction_id,
                instrument=(pred.instrument if pred else "?"),
                reason=res.reason or "ineligible", rule=res.rule or "ineligible")
    for intent in intents:                    # persist the intents (audit trail)
        ctx.store.append(INTENT_STREAM,
                         f"{intent.prediction_id}:{trading_date}",
                         {"prediction_id": intent.prediction_id,
                          "instrument": intent.instrument,
                          "direction": intent.direction,
                          "confidence": intent.confidence,
                          "trading_date": trading_date},
                         status="eligible", ref_id=intent.prediction_id,
                         idem_key=f"intent:{intent.prediction_id}:{trading_date}")

    placed = ctx.execution.submit_many(intents, trading_date=trading_date,
                                       price_at=ctx.price_at)
    return {"eligible": len(intents), "submitted": len(placed),
            "refused": len(intents) - len(placed),
            "ineligible": len([r for r in results if not r.eligible])}


# --- D: intraday reconciliation ---------------------------------------------
def intraday_paper_reconciliation(ctx, as_of: str) -> Dict:
    return reconcile_orders(ctx.broker, ctx.orders)


# --- F: prediction resolution -----------------------------------------------
def prediction_resolution(ctx, as_of: str) -> Dict:
    return resolve_due(ctx.predictions, ctx.price_at, as_of, store=ctx.store,
                       order_repo=ctx.orders)


# --- scoring helper (per + cross company) -----------------------------------
def _score_companies(ctx, as_of: str):
    states = []
    for company in ctx.universe.prediction_companies():
        outs = outcomes_for_company(ctx.store, company.company_id)
        state = compute_company_state(company.company_id, outs,
                                      peer_group=company.peer_group)
        ctx.learning_store.save(state)
        states.append(state)
    cstore = CandidateStore(ctx.store)
    proposed = []
    for s in states:
        cand = candidate_from_company_state(s)
        if cand and cstore.propose(cand):
            proposed.append(cand.id)
    cross = cross_company_candidates(states)
    persist_cross_company(ctx.store, cross)
    return states, proposed, cross


# --- E: after-close reconciliation AND learning -----------------------------
def after_close_reconciliation_and_learning(ctx, as_of: str) -> Dict:
    r_orders = reconcile_orders(ctx.broker, ctx.orders)
    marks = mark_positions(ctx.broker, ctx.store, as_of=as_of,
                           price_at=ctx.price_at, universe=ctx.universe)
    eq = snapshot_equity(ctx.broker, ctx.store, as_of=as_of)
    # resolve (catch-up) so learning sees fresh outcomes even if F was skipped
    res = resolve_due(ctx.predictions, ctx.price_at, as_of, store=ctx.store,
                      order_repo=ctx.orders)
    # exit (flatten) every position whose prediction has now resolved — otherwise
    # paper buying power is consumed without bound. Catch-up + idempotent, so a
    # skipped/holiday after-close is fully recovered by the next run.
    closed = close_resolved_positions(ctx.broker, ctx.orders, ctx.predictions,
                                      as_of=as_of)
    _states, proposed, cross = _score_companies(ctx, as_of)
    report = write_daily_report(ctx, as_of)
    return {"orders_updated": r_orders["updated_count"],
            "positions_marked": marks["positions"],
            "equity": eq["equity"], "resolved": res["resolved_count"],
            "positions_closed": closed["closed"],
            "company_candidates": proposed,
            "cross_company_candidates": [c.id for c in cross],
            "report_written_for": report["as_of"]}


# --- G: synthetic daily (from real company failures) ------------------------
def synthetic_daily(ctx, as_of: str) -> Dict:
    from intent_engine.hosted.synthetic import run_synthetic_from_failures
    return run_synthetic_from_failures(ctx, as_of)


# --- H: weekly evaluation (walk-forward, human-gated) -----------------------
def weekly_evaluation(ctx, as_of: str) -> Dict:
    from intent_engine.hosted.evaluation import weekly_evaluate
    return weekly_evaluate(ctx, as_of)


# --- I: monthly promotion review (prepare packet ONLY; human promotes) ------
def monthly_promotion_review(ctx, as_of: str) -> Dict:
    from intent_engine.hosted.evaluation import prepare_promotion_packet
    return prepare_promotion_packet(ctx, as_of)


JOBS: Dict[str, Callable] = {
    "company-intelligence-refresh": company_intelligence_refresh,
    # Classifies every eligible company and stores every result, including the
    # rejections. Runs BEFORE prediction generation: it is the job that decides
    # what is worth a position, and the one that produces the records the whole
    # learning loop is measured on.
    "daily-opportunity-sweep": daily_opportunity_sweep,
    "daily-prediction-generation": daily_prediction_generation,
    "paper-order-submit": paper_order_submit,
    "intraday-paper-reconciliation": intraday_paper_reconciliation,
    "after-close-reconciliation-and-learning":
        after_close_reconciliation_and_learning,
    "prediction-resolution": prediction_resolution,
    "synthetic-daily": synthetic_daily,
    "weekly-evaluation": weekly_evaluation,
    "monthly-promotion-review": monthly_promotion_review,
}
