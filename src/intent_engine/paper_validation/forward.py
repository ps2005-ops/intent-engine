"""Forward SHADOW registration and resolution, and the rehearsal that proves them.

REGISTRATION
------------
`register` decides with the same observation builder and the same policies
as the replay, with the information cutoff at the last COMPLETE session, and
writes one record per (policy, instrument) -- abstentions included, because
a record that only contains the trades we chose to take is a track record
with its losers pre-filtered. The entry is the open of the first session
after the decision's New York date, which has not happened when the record
is written; the ledger refuses a backdated forward record outright.

RESOLUTION
----------
`resolve_open` is the ONLY resolver, used by the forward ledger and the
rehearsal ledger alike. It resolves a forecast only when the exit session's
bar exists and that session is over; everything else stays OPEN. An outcome
that has not happened is never recorded -- the ledger refuses it too, so
this is two walls, not one.

REHEARSAL
---------
A forward resolver nobody has exercised is discovered to be wrong on the day
the first answer arrives, and fixing it then destroys the one property that
makes a forward record worth having ([[prove-the-resolver-before-it-is-needed]]).
So `rehearse` writes BACKDATED records (2024-25) through the same record
builder into a separate REHEARSAL ledger, with FIXED-CONSTANT probabilities
(LONG at 0.55; every fifth instrument abstains), and resolves them with the
same resolver. It proves the machinery. It is never evidence about a model,
and every record in it says REHEARSAL.
"""
from __future__ import annotations

import datetime as _dt
import json
import pathlib
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from intent_engine.paper_validation import bars as BR
from intent_engine.paper_validation import ledger as LG
from intent_engine.paper_validation import leakage as LK
from intent_engine.paper_validation import macro as M
from intent_engine.paper_validation import observations as OB
from intent_engine.paper_validation import policies as PL
from intent_engine.paper_validation import schedule as SCH
from intent_engine.paper_validation import universe as U
from intent_engine.paper_validation.protocol import (BORROW_BPS_YEAR,
                                                     HORIZON, PROTOCOL,
                                                     declaration_hash)

ROOT = pathlib.Path("reports/paper_validation")
FORWARD_LEDGER = ROOT / "forward_shadow_ledger.jsonl"
REHEARSAL_LEDGER = ROOT / "rehearsal_ledger.jsonl"
FORWARD_PRICES = ROOT / "forward_prices"
FORWARD_KEEP_FROM = "2024-06-01"
CONTRACT = "paper_validation_forecast.v1"

ENTRY_RULE = ("buy (LONG) or sell short (SHORT) at the open of the first "
              "NYSE session after decision_date; company forecasts take the "
              "opposite position in SPY at the same open")
EXIT_RULE = (f"close the position at the open of the session {HORIZON} "
             "sessions after entry; no stop, no target, no early exit")


def _slip() -> float:
    from intent_engine.market.costs import DEFAULT
    return DEFAULT.slippage_bps_per_side + DEFAULT.commission_bps


def expected_cost_bps(universe: str, direction: str) -> float:
    if direction == "ABSTAIN":
        return 0.0
    legs = PROTOCOL["execution"]["company_legs"] if universe == U.COMPANY else 1
    borrow = BORROW_BPS_YEAR * 30 / 365.0
    shorted = universe == U.COMPANY or direction == "SHORT"
    return round(2 * _slip() * legs + (borrow if shorted else 0.0), 3)


def forecast_id(policy_id: str, symbol: str, decision_date: str,
                kind: str) -> str:
    tag = {"FORWARD_SHADOW": "fwd", "REHEARSAL": "reh"}.get(kind, "rpl")
    return f"pv1-{tag}:{policy_id}:{symbol}:{decision_date}"


def build_record(*, kind: str, policy: PL.Policy, obs: OB.Obs,
                 decision: PL.Decision, decision_ts: str, decision_date: str,
                 n_in_universe: int, data_vintage: dict,
                 cash_rate: Optional[float],
                 info_as_of: str = "", calendar=None) -> dict:
    cal = calendar or SCH.DEFAULT
    entry, exit_ = SCH.scheduled_window(decision_date, HORIZON, cal)
    # Each record carries ITS OWN inputs' vintage (its instrument and SPY);
    # the full batch vintage is written once, beside the ledger.
    dv = dict(data_vintage)
    if isinstance(dv.get("prices"), dict):
        dv["prices"] = {s: dv["prices"][s] for s in (obs.symbol, U.BENCHMARK)
                        if s in dv["prices"]}
    target = ("excess return vs SPY (stock minus SPY, adjusted opens)"
              if obs.universe == U.COMPANY else
              "excess return vs cash (adjusted opens minus fed funds "
              "act/360)")
    return {
        "contract": CONTRACT,
        "forecast_id": forecast_id(policy.policy_id, obs.symbol,
                                   decision_date, kind),
        "ledger_kind": kind,
        "decision_ts": decision_ts,
        "decision_date": decision_date,
        "information_cutoff": info_as_of or obs.decision_date,
        "price_cutoff": obs.decision_date,
        "instrument": obs.symbol,
        "universe": obs.universe,
        "family": obs.family,
        "signal_scope": obs.signal_scope,
        "business_model_class": obs.business_model_class,
        "target": target,
        "direction": decision.direction,
        "probability": (None if decision.probability is None
                        else round(float(decision.probability), 6)),
        "horizon_sessions": HORIZON,
        "scheduled_entry_session": entry,
        "scheduled_exit_session": exit_,
        "schedule_calendar": cal.calendar_id,
        "entry_rule": ENTRY_RULE,
        "exit_rule": EXIT_RULE,
        "risk_budget": {"fraction_of_book": round(1.0 / n_in_universe, 6),
                        "max_gross_exposure": 1.0, "leverage": 0},
        "invalidation_condition": {
            "thesis_invalidated_if": policy.invalidation,
            "forecast_voided_if": "the entry or exit session has no bar for "
                                  "this instrument (halt, delisting)"},
        "expected_cost_bps": expected_cost_bps(obs.universe,
                                               decision.direction),
        "cash_rate_at_decision": cash_rate,
        "evidence_ids": sorted(set(decision.evidence_ids)),
        "thesis": policy.thesis,
        "causal_mechanism": policy.mechanism,
        "competing_hypotheses": list(policy.competing),
        "rationale": decision.rationale,
        "abstention_reason": decision.abstention_reason,
        "policy_id": policy.policy_id,
        "policy_version": policy.version,
        "provenance": policy.provenance,
        "feature_set": policy.feature_set,
        "model_version": decision.model_version or
                         f"{policy.policy_id}:{policy.version}",
        "data_vintage": dv,
        "protocol_hash": declaration_hash(),
        "regime_at_decision": list(obs.regimes),
        "regime_label": obs.regime_label,
    }


def decide_records(*, kind: str, policies: Sequence[PL.Policy],
                   rows: Sequence[OB.Obs], history, bars, decision_ts: str,
                   decision_date: str, data_vintage: dict,
                   cash_rate: Optional[float],
                   calendar=None) -> List[dict]:
    out = []
    for uni in (U.ETF, U.COMPANY):
        urows = [o for o in rows if o.universe == uni]
        if not urows:
            continue
        for p in policies:
            if not p.applies(uni):
                continue
            if isinstance(p, PL.IEMarketMomentum):
                p.bind(bars)
            for o, dec in zip(urows, p.decide_date(urows, history)):
                # Walled at the DECISION date: price evidence is at or before
                # the price cutoff, macro at or before the decision itself.
                LK.check_evidence(dec.evidence_ids, decision_date)
                out.append(build_record(
                    kind=kind, policy=p, obs=o, decision=dec,
                    decision_ts=decision_ts, decision_date=decision_date,
                    n_in_universe=len(urows), data_vintage=data_vintage,
                    cash_rate=cash_rate, info_as_of=decision_date,
                    calendar=calendar))
    return out


# --- resolution ------------------------------------------------------------------

#: How long a delisted or halted instrument is waited for, after its scheduled
#: exit, before the forecast is voided. A benchmark that has not caught up is
#: waited for indefinitely: that is a fetch that has not happened yet, and a
#: fetch failure must never close a forecast.
DATA_GRACE_DAYS = 7


def _bar_problem(b, day: str, spy, today: str) -> Optional[str]:
    """None if `b` has a bar on `day`; "WAIT" if the data may still arrive;
    otherwise the reason the session will never have a bar."""
    if b is None:
        return "WAIT"
    if b.index_of(day) is not None:
        return None
    if b.dates and b.dates[-1] > day:
        return f"no {b.symbol} bar on scheduled session {day}"
    # The series ends before the scheduled session. If the benchmark has
    # moved past it, this instrument stopped trading; otherwise the fetch is
    # simply behind.
    bench_past = spy is not None and spy.dates and spy.dates[-1] > day
    late = (_dt.date.fromisoformat(today)
            > _dt.date.fromisoformat(day) + _dt.timedelta(days=DATA_GRACE_DAYS))
    if bench_past and late and b is not spy:
        return (f"{b.symbol} has no bars after {b.dates[-1] if b.dates else 'ever'}"
                f" (halted or delisted); scheduled session {day}")
    return "WAIT"


def resolve_open(ledger: LG.Ledger, bars: Dict[str, BR.Bars], *,
                 now: _dt.datetime) -> dict:
    """Resolve what has happened; leave the rest OPEN. Returns counts.

    Entry and exit are the SCHEDULED sessions (`schedule.schedule_of`), never
    "the 21st bar in today's feed". A bar that is missing makes the forecast
    wait or, once the gap is certain, void with the reason. It is never
    scored on a different session, so nothing here can postpone a forecast.
    """
    today = LG.ny_date(now)
    spy = bars.get(U.BENCHMARK)
    resolutions, voids = [], []
    waiting = 0
    for st in ledger.open_forecasts():
        reg = st.registration
        entry, exit_, cal = SCH.schedule_of(reg)
        if exit_ >= today:
            waiting += 1
            continue
        b = bars.get(reg["instrument"])
        problems = [_bar_problem(x, day, spy, today)
                    for x in (spy, b) for day in (entry, exit_)]
        if "WAIT" in problems:
            waiting += 1
            continue
        reasons = [p for p in problems if p]
        if reasons:
            voids.append({"forecast_id": st.forecast_id,
                          "reason": "; ".join(dict.fromkeys(reasons)) +
                                    ". The due date is never moved.",
                          "scheduled_entry_session": entry,
                          "scheduled_exit_session": exit_,
                          "resolved_at": now.isoformat(timespec="seconds")})
            continue
        si, sx = spy.index_of(entry), spy.index_of(exit_)
        ie, ix = b.index_of(entry), b.index_of(exit_)
        ret = b.open_adj[ix] / b.open_adj[ie] - 1.0
        if reg["universe"] == U.COMPANY:
            bench = spy.open_adj[sx] / spy.open_adj[si] - 1.0
            excess = ret - bench
        else:
            days = (_dt.date.fromisoformat(exit_)
                    - _dt.date.fromisoformat(entry)).days
            rate = reg.get("cash_rate_at_decision") or 0.0
            bench = rate * days / 360.0
            excess = ret - bench
        y = 1 if excess > 0 else 0
        pos = {"LONG": 1, "SHORT": -1}.get(reg["direction"], 0)
        resolutions.append({
            "forecast_id": st.forecast_id, "entry_date": entry,
            "exit_date": exit_, "schedule_calendar": cal,
            "benchmark_sessions_elapsed": sx - si,
            "entry_open_adj": round(b.open_adj[ie], 6),
            "exit_open_adj": round(b.open_adj[ix], 6),
            "instrument_return": round(ret, 6),
            "benchmark_return": round(bench, 6),
            "excess_return": round(excess, 6), "outcome": y,
            "net_position_return": round(
                pos * excess - reg["expected_cost_bps"] * 1e-4, 6),
            "price_vintage": {"source": b.source, "sha256": b.sha256[:16],
                              "retrieved_at": b.retrieved_at},
            "resolved_at": now.isoformat(timespec="seconds")})
    n_res = ledger.resolve(resolutions) if resolutions else 0
    n_void = ledger.void(voids) if voids else 0
    return {"resolved": n_res, "voided": n_void, "still_open": waiting,
            "clock_ny_date": today}


# --- inputs for the forward path --------------------------------------------------

def forward_bars(symbols: Sequence[str], *, now: _dt.datetime,
                 log=print) -> Tuple[Dict[str, BR.Bars], Dict[str, str]]:
    """Fresh bars for forward use, kept in their own cache directory so the
    replay's committed inputs never change underneath it."""
    out, failed = {}, {}
    FORWARD_PRICES.mkdir(parents=True, exist_ok=True)
    for sym in symbols:
        try:
            doc = BR.fetch(sym, now=now)
        except Exception as exc:                        # noqa: BLE001
            failed[sym] = str(exc)
            log(f"forward price {sym}: FAILED {exc}")
            continue
        doc["rows"] = [r for r in doc["rows"] if r[0] >= FORWARD_KEEP_FROM]
        doc["sha256"] = BR._content_sha(doc["rows"])
        BR.write_cache(doc, FORWARD_PRICES)
        out[sym] = BR.to_bars(doc)
        import time
        time.sleep(0.5)
    return out, failed


def _history_rows(inp, bars, through: str, log):
    """Every historical observation resolved by `through`, built with the
    replay's own builder, so forward models learn from exactly the replay's
    rows."""
    spy = bars[U.BENCHMARK]
    dates = [s for s in OB.schedule(spy, anchor=PROTOCOL["replay"]["anchor"])
             if s[3] and s[3] <= through]
    rows, _ = OB.build(bars=bars, instruments=inp["etfs"] + inp["companies"],
                       panel=inp["panel"], dates=dates,
                       profiles=inp["profiles"], log=log)
    return [o for o in rows if o.resolved]


def register(inp: dict, *, now: _dt.datetime, fresh_bars: Dict[str, BR.Bars],
             panel_vintage: dict, ledger_path=FORWARD_LEDGER,
             log=print) -> dict:
    from intent_engine.paper_validation.replay import History
    spy = fresh_bars[U.BENCHMARK]
    cutoff = spy.last_date
    decision_date = LG.ny_date(now)
    if cutoff > decision_date:
        raise LG.LedgerViolation("a bar dated after the decision exists")
    # history: the long replay bars, extended by the fresh ones
    merged = dict(inp["bars"])
    hist = _history_rows(inp, merged, cutoff, log)
    history = History(hist)
    rows, voids = OB.build(bars=fresh_bars,
                           instruments=inp["etfs"] + inp["companies"],
                           panel=inp["panel"], dates=[(0, cutoff, "", "")],
                           profiles=inp["profiles"],
                           macro_as_of=decision_date, log=log)
    cell, _ = M._latest(inp["panel"], "DFF", decision_date)
    cash_rate = float(cell.value) / 100.0 if cell else None
    vint = {"prices": BR.vintage(fresh_bars), "macro": panel_vintage,
            "history_rows": len(hist), "history_resolved_through":
                max(o.exit_date for o in hist) if hist else ""}
    recs = decide_records(kind=LG.FORWARD_SHADOW, policies=PL.registry(),
                          rows=rows, history=history, bars=fresh_bars,
                          decision_ts=now.isoformat(timespec="seconds"),
                          decision_date=decision_date, data_vintage=vint,
                          cash_rate=cash_rate)
    led = LG.Ledger(ledger_path, LG.FORWARD_SHADOW)
    known = set(led.states())
    new = [r for r in recs if r["forecast_id"] not in known]
    n = led.register(new) if new else 0
    batch = pathlib.Path(ledger_path).parent / "forward_batches" / \
        f"{decision_date}.json"
    batch.parent.mkdir(parents=True, exist_ok=True)
    if not batch.exists():
        batch.write_text(json.dumps({"decision_date": decision_date,
                                     "decision_ts": now.isoformat(
                                         timespec="seconds"),
                                     "registered": n, "data_vintage": vint},
                                    indent=1, sort_keys=True),
                         encoding="utf-8")
    return {"registered": n, "skipped_existing": len(recs) - len(new),
            "information_cutoff": cutoff, "decision_date": decision_date,
            "voided_rows": voids, "ledger": str(ledger_path)}


def sessions_since_last_registration(spy: BR.Bars,
                                     ledger_path=FORWARD_LEDGER) -> Optional[int]:
    """Completed SPY sessions after the latest registered decision date.

    None when nothing has been registered. Used by `register --if-due`, so a
    daily scheduler registers on the protocol's 21-session cadence and never
    in between (overlapping windows would be counted as independent).
    """
    p = pathlib.Path(ledger_path)
    if not p.exists():
        return None
    led = LG.Ledger(p, LG.FORWARD_SHADOW)
    dates = [s.registration["decision_date"] for s in led.states().values()]
    if not dates:
        return None
    last = max(dates)
    return sum(1 for d in spy.dates if d > last)


# --- the rehearsal -----------------------------------------------------------------

class RehearsalConstant(PL.Policy):
    """FIXED CONSTANTS, never model output: LONG at 0.55, every fifth
    instrument abstains so the abstention path is exercised too."""

    def decide(self, o, history):
        if sum(map(ord, o.symbol)) % 5 == 0:
            return PL.Decision("ABSTAIN", None, list(o.ev_price), "",
                               "rehearsal: abstention path")
        return PL.Decision("LONG", 0.55, list(o.ev_price),
                           "rehearsal constant (not a forecast)")


def rehearsal_policy() -> PL.Policy:
    return RehearsalConstant(
        "rehearsal_constant", "v1", PL.CONTROL, (U.ETF,), "-",
        "REHEARSAL: exercises registration, resolution and learning. Not a "
        "forecast.", "none", ("this is not a forecast",), "never evaluated")


def rehearse(inp: dict, *, now: _dt.datetime, ledger_path=REHEARSAL_LEDGER,
             start: str = "2024-01-02", log=print) -> dict:
    """Backdated REHEARSAL records through the real builder and resolver."""
    bars = inp["bars"]
    spy = bars[U.BENCHMARK]
    dates = [s for s in OB.schedule(spy, anchor=start)
             if s[1] < "2026-01-01"]
    rows, _ = OB.build(bars=bars, instruments=inp["etfs"], panel=inp["panel"],
                       dates=[(k, d, "", "") for k, d, _e, _x in dates],
                       profiles=None)
    pol = rehearsal_policy()
    by_date: Dict[str, List[OB.Obs]] = {}
    for o in rows:
        by_date.setdefault(o.decision_date, []).append(o)
    registered = 0
    rolling = 0             # earlier windows closing as the clock advances
    same_step = 0           # MUST stay 0: resolved in the step it was made
    led_path = pathlib.Path(ledger_path)
    for d in sorted(by_date):
        stamp = _dt.datetime.fromisoformat(d + "T21:30:00+00:00")
        led = LG.Ledger(led_path, LG.REHEARSAL, clock=lambda s=stamp: s)
        known = set(led.states()) if led_path.exists() else set()
        cell, _ = M._latest(inp["panel"], "DFF", d)
        recs = decide_records(
            kind=LG.REHEARSAL, policies=[pol], rows=by_date[d], history=None,
            bars=bars, decision_ts=stamp.isoformat(timespec="seconds"),
            decision_date=d, data_vintage={"prices": "replay cache",
                                           "label": "REHEARSAL"},
            cash_rate=float(cell.value) / 100.0 if cell else None)
        recs = [r for r in recs if r["forecast_id"] not in known]
        if recs:
            registered += led.register(recs)
        new_ids = {r["forecast_id"] for r in recs}
        # The resolver, run with the clock AT registration, may close older
        # windows but must not touch anything registered in this step.
        clocked = LG.Ledger(led_path, LG.REHEARSAL, clock=lambda s=stamp: s)
        before = {k for k, v in clocked.states().items()
                  if v.status == LG.OPEN}
        early = resolve_open(clocked, bars, now=stamp)
        after = {k for k, v in clocked.states().items()
                 if v.status == LG.OPEN}
        rolling += early["resolved"]
        same_step += len((before - after) & new_ids)
    led = LG.Ledger(led_path, LG.REHEARSAL, clock=lambda: now)
    res = resolve_open(led, bars, now=now)
    return {"registered": registered, "dates": len(by_date),
            "resolved_as_clock_advanced": rolling,
            "resolved_in_the_step_registered": same_step,
            "final": res, "summary": LG.summary(led)}


# --- CLI ----------------------------------------------------------------------------

def add_commands(sub, load_inputs) -> None:
    def _now():
        return _dt.datetime.now(_dt.timezone.utc)

    def cmd_register(args):
        now = _now()
        stamp = LG.ny_date(now)
        inp = load_inputs()
        syms = [i.symbol for i in inp["etfs"] + inp["companies"]]
        if args.if_due:
            spy_now, _f = forward_bars([U.BENCHMARK], now=now)
            gap = sessions_since_last_registration(spy_now[U.BENCHMARK])
            if gap is not None and gap < PROTOCOL["execution"][
                    "cadence_sessions"]:
                print(json.dumps({"registered": 0, "due": False,
                                  "sessions_since_last": gap}))
                return 0
        fresh, failed = forward_bars(syms, now=now)
        snap = M.build_forward_snapshot(inp["panel"], retrieved=now,
                                        log=print)
        snap_path = M.FORWARD_DIR / f"{stamp}.jsonl"
        snap.write(snap_path)
        panel, pvint = M.load_panel(forward_snapshot=snap_path)
        inp["panel"] = panel
        inp["etfs"] = [e for e in inp["etfs"] if e.symbol in fresh]
        inp["companies"] = [c for c in inp["companies"] if c.symbol in fresh]
        out = register(inp, now=now, fresh_bars=fresh, panel_vintage=pvint)
        out["price_failures"] = failed
        print(json.dumps(out, indent=1, default=str))
        return 0

    def cmd_resolve(args):
        now = _now()
        led = LG.Ledger(FORWARD_LEDGER, LG.FORWARD_SHADOW)
        syms = sorted({s.registration["instrument"]
                       for s in led.open_forecasts()} | {U.BENCHMARK})
        if args.offline:
            bars = {s: BR.to_bars(BR.read_cache(s, FORWARD_PRICES))
                    for s in syms if BR.read_cache(s, FORWARD_PRICES)}
        else:
            bars, _f = forward_bars(syms, now=now)
        print(json.dumps(resolve_open(led, bars, now=now), indent=1))
        return 0

    def cmd_rehearse(args):
        inp = load_inputs()
        print(json.dumps(rehearse(inp, now=_now()), indent=1, default=str))
        return 0

    def cmd_status(args):
        for path, kind in ((FORWARD_LEDGER, LG.FORWARD_SHADOW),
                           (REHEARSAL_LEDGER, LG.REHEARSAL)):
            if pathlib.Path(path).exists():
                print(json.dumps(LG.summary(LG.Ledger(path, kind)), indent=1))
        return 0

    def cmd_learn(args):
        from intent_engine.paper_validation import learning_loop as LL
        kind = LG.REHEARSAL if args.rehearsal else LG.FORWARD_SHADOW
        path = REHEARSAL_LEDGER if args.rehearsal else FORWARD_LEDGER
        print(json.dumps(LL.run(LG.Ledger(path, kind)), indent=1,
                         default=str))
        return 0

    p = sub.add_parser("register")
    p.add_argument("--if-due", action="store_true",
                   help="register only when >= 21 sessions have completed "
                        "since the last registration (for a daily job)")
    p.set_defaults(fn=cmd_register)
    p = sub.add_parser("resolve")
    p.add_argument("--offline", action="store_true")
    p.set_defaults(fn=cmd_resolve)
    p = sub.add_parser("rehearse")
    p.set_defaults(fn=cmd_rehearse)

    def cmd_daily(args):
        from intent_engine.paper_validation import daily as D
        row = D.run(now=_now())
        print(json.dumps(row, indent=1, default=str))
        return 1 if row.get("status") == "FAILED" else 0
    p = sub.add_parser("daily", help="resolve what is due, alert on overdue "
                       "and missed runs; never registers")
    p.set_defaults(fn=cmd_daily)
    p = sub.add_parser("status")
    p.set_defaults(fn=cmd_status)
    p = sub.add_parser("learn")
    p.add_argument("--rehearsal", action="store_true")
    p.set_defaults(fn=cmd_learn)
