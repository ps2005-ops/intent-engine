"""30 market-day operational replay — drives the REAL hosted jobs, hard.

This is a diagnostic harness, not a product feature. It runs the actual
`intent_engine.hosted.jobs` over 30 market days (historical replay + forward
paper) through the durable store and the FakeAlpacaPaperBroker, injecting
realistic adversity so real defects surface:

  * a scheduler MISS (after-close skipped one day) -> must catch up next day
  * a DOUBLE-FIRED generation+submit (idempotency)  -> must not double-trade
  * a TRANSIENT missing price on a resolve day       -> must not crash; recover
  * a broker REJECT                                  -> must reconcile, not fill
  * a market HOLIDAY (all jobs skipped)              -> gap, then resume
  * a persistent DUOL downtrend                      -> losing book -> candidate
  * a FUTURE-dated evidence every day                -> leakage must be blocked

Then it AUDITS the durable state for invariant violations (reconciliation +
dashboard consistency) and writes a JSON ledger. `python scripts/ops_replay_30d.py`.
"""
from __future__ import annotations

import json
import math
import sys
import tempfile
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from intent_engine.hosted.candidates import CandidateStore
from intent_engine.hosted.context import HostedContext
from intent_engine.hosted.dashboard import assemble
from intent_engine.hosted.jobs import JOBS
from intent_engine.hosted.records import run_job
from intent_engine.paper.broker import FakeAlpacaPaperBroker
from intent_engine.predictions.resolution import OUTCOME_STREAM
from intent_engine.storage.durable import DurableStore
from intent_engine.universe.companies import default_universe

START = date(2026, 1, 2)
N_MARKET_DAYS = 30


# --- market days (business days) --------------------------------------------
def market_days(start: date, n: int):
    days, d = [], start
    while len(days) < n:
        if d.weekday() < 5:            # Mon-Fri
            days.append(d.isoformat())
        d += timedelta(days=1)
    return days


DAYS = market_days(START, N_MARKET_DAYS)
_SPAN_END = date.fromisoformat(DAYS[-1]) + timedelta(days=5)


# --- deterministic calendar-day price series (weekends have prices too) -----
def _price_series():
    series = defaultdict(dict)
    d = START
    i = 0
    while d <= _SPAN_END:
        iso = d.isoformat()
        series["SHOP"][iso] = round(100.0 * (1.004 ** i), 4)       # uptrend -> hits
        series["NET"][iso] = round(60.0 + 6.0 * math.sin(i / 2.0), 4)  # choppy
        series["DUOL"][iso] = round(250.0 * (0.997 ** i), 4)       # downtrend -> misses
        series["IPAY"][iso] = round(40.0 + 0.1 * i, 4)
        d += timedelta(days=1)
        i += 1
    return series


PRICES = _price_series()
_MISSING = {("NET", None)}      # set at runtime for a transient miss
_price_attempts = defaultdict(int)


class Ledger:
    def __init__(self):
        self.job_runs = []
        self.failures = []
        self.skipped_jobs = []
        self.scheduler_misses = []
        self.reconciliation_issues = []
        self.prediction_errors = []
        self.dashboard_inconsistencies = []
        self.learning_candidates = []
        self.leakage_blocked = 0
        self.notes = []

    def as_dict(self):
        return {k: v for k, v in self.__dict__.items()}


def build_ctx():
    store = DurableStore(f"sqlite:///{tempfile.mkdtemp()}/ops30.db")
    return HostedContext(
        store=store, broker=FakeAlpacaPaperBroker(equity=100_000),
        universe=default_universe(), predict_fn=_predict, price_at=_price_at,
        research_fn=_research, regime="calm")


def _price_at(symbol, day):
    key = (symbol, day[:10])
    if key in _transient_missing and _price_attempts[key] == 0:
        _price_attempts[key] += 1
        raise RuntimeError(f"transient: no price for {symbol} at {day[:10]}")
    try:
        return PRICES[symbol][day[:10]]
    except KeyError:
        raise RuntimeError(f"no price for {symbol} at {day[:10]}")


_transient_missing = set()      # populated during the run for the miss injection


def _research(company, as_of):
    return {"thesis": f"{company.canonical_name} thesis @ {as_of}",
            "priorities": list(company.strategic_priorities) or ["growth"],
            "evidence": [
                {"kind": "filing", "summary": "q filing", "source": "10-Q",
                 "published_at": as_of, "confidence": 0.7},
                # a FUTURE-dated leak that MUST be blocked every day:
                {"kind": "rumor", "summary": "future leak", "source": "blog",
                 "published_at": "2099-01-01", "confidence": 0.1}]}


def _predict(company, state, as_of):
    return {"direction": "up", "probability": 0.72, "horizon_days": 1,
            "claim_text": f"{company.canonical_name} up 1d"}


def _run(ctx, ledger, job, as_of):
    rec = run_job(ctx.store, job, lambda: JOBS[job](ctx, as_of), as_of=as_of)
    ledger.job_runs.append({"day": as_of, "job": job, "status": rec["status"]})
    if rec["status"] == "failed":
        ledger.failures.append({"day": as_of, "job": job,
                                "error": rec.get("error")})
    return rec


def simulate(ledger: Ledger):
    ctx = build_ctx()
    holiday_idx = 19
    miss_idx = 11
    double_fire_idx = 9
    reject_idx = 14
    skip_afterclose_idx = 6

    for i, day in enumerate(DAYS):
        if i == holiday_idx:
            ledger.skipped_jobs.append({"day": day, "reason": "market holiday "
                                        "(all jobs skipped)"})
            ledger.scheduler_misses.append({"day": day, "kind": "holiday"})
            continue

        # arm the transient missing price for NET on this day's resolves
        if i == miss_idx:
            for d in DAYS[:i + 1]:
                _transient_missing.add(("NET", (date.fromisoformat(d)
                                                + timedelta(days=1)).isoformat()))

        # pre-market research + generation
        r = _run(ctx, ledger, "company-intelligence-refresh", day)
        ledger.leakage_blocked += (r.get("detail", {}) or {}).get(
            "leaked_evidence_blocked", 0)
        _run(ctx, ledger, "daily-prediction-generation", day)
        if i == double_fire_idx:                 # GitHub Actions fires twice
            _run(ctx, ledger, "daily-prediction-generation", day)

        # open: submit (double-fire on the injected day)
        _run(ctx, ledger, "paper-order-submit", day)
        if i == double_fire_idx:
            _run(ctx, ledger, "paper-order-submit", day)

        # intraday fills (Alpaca fills during the session) + optional reject
        open_orders = ctx.orders.open_orders()
        for o in open_orders:
            if i == reject_idx and o.instrument == "SHOP":
                ctx.broker.simulate_reject(o.client_order_id, "paper reject test")
            else:
                try:
                    px = _price_at(o.instrument, day)
                    ctx.broker.simulate_fill(o.client_order_id, price=px)
                except RuntimeError:
                    pass
        _run(ctx, ledger, "intraday-paper-reconciliation", day)

        # after-close E (skip once to force a scheduler miss) + evening resolve F
        if i == skip_afterclose_idx:
            ledger.skipped_jobs.append({"day": day, "job":
                                        "after-close-reconciliation-and-learning",
                                        "reason": "injected scheduler miss"})
            ledger.scheduler_misses.append({"day": day, "kind": "after_close_skip"})
        else:
            _run(ctx, ledger, "after-close-reconciliation-and-learning", day)
        _run(ctx, ledger, "prediction-resolution", day)

        # weekly cadence every 5 market days; synthetic daily
        _run(ctx, ledger, "synthetic-daily", day)
        if (i + 1) % 5 == 0:
            _run(ctx, ledger, "weekly-evaluation", day)

    _run(ctx, ledger, "monthly-promotion-review", DAYS[-1])
    return ctx


def audit(ctx, ledger: Ledger):
    orders = ctx.orders.all_latest()
    preds = {p.id for p in ctx.predictions.all_latest()}
    universe = ctx.universe
    private_ids = {c.company_id for c in universe.private()}

    # R1: no order for any private company
    for o in orders:
        if o.company_id in private_ids:
            ledger.reconciliation_issues.append(
                {"kind": "private_company_order", "order": o.client_order_id,
                 "company": o.company_id})

    # R2: every order references an existing prediction
    for o in orders:
        if o.prediction_id not in preds:
            ledger.reconciliation_issues.append(
                {"kind": "orphan_order", "order": o.client_order_id,
                 "prediction": o.prediction_id})

    # R3: at most one OPEN order per prediction
    open_by_pred = defaultdict(int)
    for o in ctx.orders.open_orders():
        open_by_pred[o.prediction_id] += 1
    for pid, n in open_by_pred.items():
        if n > 1:
            ledger.reconciliation_issues.append(
                {"kind": "multiple_open_orders_same_prediction",
                 "prediction": pid, "count": n})

    # R4: duplicate SAME-DAY exposure per company (catches double-fire trading).
    # Only OPENING orders count — a horizon-exit close legitimately lands on the
    # same trading day as a fresh open for the same company.
    by_company_day = defaultdict(list)
    for o in orders:
        if not o.action.startswith("open_"):
            continue
        by_company_day[(o.company_id, o.trading_date)].append(o.client_order_id)
    for (cid, d), ids in by_company_day.items():
        if len(ids) > 1:
            ledger.reconciliation_issues.append(
                {"kind": "duplicate_same_day_exposure", "company": cid,
                 "day": d, "orders": ids})

    # R6: exposure hygiene, measured against the true invariant.
    #  (a) at most one UNRESOLVED filled open per instrument (no duplicate
    #      simultaneous exposure);
    #  (b) every filled OPEN whose prediction has resolved MUST have a close
    #      order (the horizon exit). A resolved open with no close is a
    #      genuinely stranded position — the reliability defect the 30-day
    #      replay surfaced (paper buying power consumed without bound).
    pred_outcome = {p.id: p.outcome for p in ctx.predictions.all_latest()}
    close_preds = {o.prediction_id for o in orders
                   if o.action.startswith("close_")}
    open_by_instrument = defaultdict(int)
    stranded = []
    for o in orders:
        if not (o.is_filled and o.action.startswith("open_")):
            continue
        if pred_outcome.get(o.prediction_id) is None:
            open_by_instrument[o.instrument] += 1        # legit open exposure
        elif o.prediction_id not in close_preds:
            stranded.append(o.client_order_id)           # resolved, never closed
    for inst, n in open_by_instrument.items():
        if n > 1:
            ledger.reconciliation_issues.append(
                {"kind": "simultaneous_instrument_exposure", "instrument": inst,
                 "count": n})
    for coid in stranded:
        ledger.reconciliation_issues.append(
            {"kind": "position_held_after_resolution", "order": coid})

    # broker-level breakdown (evidence, not a pass/fail): why any net position
    # is still held at the broker at end-of-run.
    resolved_ids = {pid for pid, oc in pred_outcome.items() if oc is not None}
    filled_close_preds = {o.prediction_id for o in orders
                          if o.action.startswith("close_") and o.is_filled}
    live_open_exposure = close_pending = 0
    for o in orders:
        if not (o.is_filled and o.action.startswith("open_")):
            continue
        if o.prediction_id not in resolved_ids:
            live_open_exposure += 1
        elif o.prediction_id not in filled_close_preds:
            close_pending += 1        # close submitted; fills next session
    ledger.notes.append(
        {"broker_positions": len(ctx.broker.list_positions()),
         "live_open_exposure": live_open_exposure,
         "close_submitted_not_yet_filled": close_pending,
         "stranded_after_resolution": len(stranded),
         "note": "net broker exposure explained: live (unresolved) + "
                 "close-pending (resolved, exit order placed, fills next "
                 "session) + stranded (defect: must be 0)"})

    # R5: resolved predictions == outcome records
    resolved = [p for p in ctx.predictions.all_latest()
                if p.outcome in ("happened", "did_not_happen")]
    outcomes = ctx.store.latest(OUTCOME_STREAM)
    if len(resolved) != len(outcomes):
        ledger.reconciliation_issues.append(
            {"kind": "resolved_outcome_count_mismatch",
             "resolved": len(resolved), "outcome_records": len(outcomes)})

    # prediction errors (misses) are normal signal to record
    for p in resolved:
        if p.outcome == "did_not_happen":
            ledger.prediction_errors.append(
                {"prediction": p.id, "company": p.entity_id,
                 "instrument": p.instrument, "probability": p.probability})

    # D1: dashboard assembles without error and its counts match the store
    try:
        data = assemble(ctx.store, as_of=DAYS[-1])
        if len(data["universe"]) != len(universe.companies):
            ledger.dashboard_inconsistencies.append(
                {"kind": "universe_count", "dashboard": len(data["universe"]),
                 "store": len(universe.companies)})
        filled_actual = len([o for o in orders if o.is_filled])
        if data["reconciliation"]["filled_orders"] != filled_actual:
            ledger.dashboard_inconsistencies.append(
                {"kind": "filled_count", "dashboard":
                 data["reconciliation"]["filled_orders"], "actual": filled_actual})
        if not data["database_health"]["ok"]:
            ledger.dashboard_inconsistencies.append({"kind": "db_health_not_ok"})
    except Exception as exc:  # noqa: BLE001
        ledger.dashboard_inconsistencies.append(
            {"kind": "assemble_crashed", "error": f"{type(exc).__name__}: {exc}"})

    # D2: equity snapshot present for each non-skipped, non-holiday after-close
    from intent_engine.paper.reconciliation import EQUITY_STREAM
    eq_days = {r.record_id for r in ctx.store.latest(EQUITY_STREAM)}
    for i, day in enumerate(DAYS):
        if i in (6, 19):        # skipped after-close / holiday: gap EXPECTED
            continue
        if day not in eq_days:
            ledger.dashboard_inconsistencies.append(
                {"kind": "missing_equity_snapshot", "day": day})

    # learning candidates
    for c in CandidateStore(ctx.store).all_latest():
        ledger.learning_candidates.append(
            {"id": c.id, "company": c.company_id, "status": c.status,
             "sample_size": c.sample_size, "statement": c.statement})

    return ctx


def main():
    ledger = Ledger()
    ctx = simulate(ledger)
    audit(ctx, ledger)
    summary = {
        "market_days": len(DAYS), "job_runs": len(ledger.job_runs),
        "failures": len(ledger.failures),
        "skipped_jobs": len(ledger.skipped_jobs),
        "scheduler_misses": len(ledger.scheduler_misses),
        "reconciliation_issues": len(ledger.reconciliation_issues),
        "prediction_errors": len(ledger.prediction_errors),
        "dashboard_inconsistencies": len(ledger.dashboard_inconsistencies),
        "learning_candidates": len(ledger.learning_candidates),
        "leakage_blocked": ledger.leakage_blocked,
    }
    out = {"summary": summary, "ledger": ledger.as_dict()}
    dest = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("ops30_ledger.json")
    dest.write_text(json.dumps(out, indent=2, default=str))
    print(json.dumps(summary, indent=2))
    print("\n--- reconciliation issues ---")
    print(json.dumps(ledger.reconciliation_issues, indent=2, default=str))
    print("\n--- dashboard inconsistencies ---")
    print(json.dumps(ledger.dashboard_inconsistencies, indent=2, default=str))
    print("\n--- failures ---")
    print(json.dumps(ledger.failures, indent=2, default=str))
    print(f"\nfull ledger -> {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
