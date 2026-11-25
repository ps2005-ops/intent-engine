"""Price-outcome resolution for the signal audit: append-only, idempotent.

WHAT THIS REPLACES
------------------
`resolve_outcomes_step` used to count eligible audit records and return
`"resolved": 0` unconditionally. Nothing was ever graded.

WHAT IS GRADED, AND BY WHICH RULE
---------------------------------
Every record in `reports/market/signal_audit.jsonl` is graded by the rule
that was in force when it was written: `signal_opportunity.v1`. The horizon
end is `as_of + horizon_days` (calendar days). Entry is the last close on or
before `as_of`, and exit is the last close on or before the horizon end. The
decision-time label (`opportunity_state`) is never recomputed. This module
does not change that rule. It adds the data-integrity refusals the rule
lacked:

* **The exit must be a real later bar.** The old grader would take the entry
  bar as the exit when no later bar existed (delisting, a dead feed), which
  fabricates a 0.0% return. A resolution now needs an exit bar dated after
  `as_of` and no more than `MAX_EXIT_STALENESS_DAYS` before the horizon end.
  Holidays and weekends fit inside that allowance.
* **The entry must be a decision-time bar,** dated no more than
  `MAX_ENTRY_STALENESS_DAYS` before `as_of`.
* **Missing data is a state, not an outcome.** A provider failure or a feed
  that has not reached the horizon end yet is `PENDING` (retryable). It
  becomes terminal `UNRESOLVABLE` only after `final_date = horizon_end +
  FINAL_GRACE_DAYS`, and the event records the reason.

These records are not forecasts. The only signal (`baseline_momentum.v1`)
never fired, so no record carries a direction or a probability. Brier scores
and trade returns are undefined for them, and the summary says so instead of
reporting a number.

STORAGE
-------
Outcomes are appended to `reports/market/signal_outcomes.jsonl`. The audit
file is never rewritten. Each event is keyed by `record_key` (a hash of the
record's identity fields). A key with a terminal event is never graded again,
and PENDING events are only appended when the state changes, so restarting
or rerunning a cycle produces identical results.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
from datetime import date, timedelta
from typing import Callable, Dict, Iterable, List, Optional

from intent_engine.market import signal_opportunity as SO
from intent_engine.market.signals import MIN_ABS_RETURN

CONTRACT = "signal_outcome_resolution.v1"
OUTCOMES_FILE = "reports/market/signal_outcomes.jsonl"
PRICE_BASIS = "yahoo_chart_close:split_adjusted,not_dividend_adjusted"

MAX_EXIT_STALENESS_DAYS = 5    # long weekend + holiday fits; a dead feed does not
MAX_ENTRY_STALENESS_DAYS = 5
FINAL_GRACE_DAYS = 15          # feed lag allowance before PENDING turns terminal

RESOLVED = "RESOLVED"
PENDING = "PENDING"
UNRESOLVABLE = "UNRESOLVABLE"
NOT_MATURE = "NOT_MATURE"
TERMINAL = (RESOLVED, UNRESOLVABLE)

IDENTITY_FIELDS = ("cycle_id", "company_id", "instrument", "signal",
                   "signal_version", "as_of")


def record_key(row: dict) -> str:
    ident = "|".join(str(row.get(f, "")) for f in IDENTITY_FIELDS)
    return hashlib.sha256(ident.encode()).hexdigest()[:20]


def decision_key(row: dict) -> tuple:
    """Two cycles on the same day grade the same decision: one sample, not two."""
    return (row.get("as_of", "")[:10], row.get("instrument"),
            row.get("signal"), row.get("signal_version"))


def _d(s: str) -> date:
    return date.fromisoformat(s[:10])


def grade(row: dict, closes: Optional[Dict[str, float]], *, today: str,
          provider_error: str = "") -> dict:
    """Grade one audit row. Pure: no I/O, no clock. Returns an outcome event."""
    horizon = int((row.get("opportunity") or {}).get(
        "horizon_days", SO.HORIZON_DAYS))
    end = SO.horizon_end(row["as_of"], horizon)
    final = (_d(end) + timedelta(days=FINAL_GRACE_DAYS)).isoformat()
    base = {"contract": CONTRACT, "record_key": record_key(row),
            "decision_key": list(decision_key(row)),
            "as_of": row["as_of"][:10], "instrument": row.get("instrument"),
            "company_id": row.get("company_id"), "signal": row.get("signal"),
            "signal_version": row.get("signal_version"),
            "rule": SO.DEFINITION, "horizon_days": horizon,
            "horizon_end": end, "final_date": final,
            "opportunity_state": row.get("opportunity_state"),
            "fired": bool(row.get("fired")), "processed_on": today[:10],
            "price_basis": PRICE_BASIS}

    if end >= today[:10]:   # the horizon-end close is final only once that day has passed
        return {**base, "state": NOT_MATURE, "reason": "horizon not elapsed"}

    def open_or_final(reason: str) -> dict:
        if today[:10] > final:
            return {**base, "state": UNRESOLVABLE, "reason": reason}
        return {**base, "state": PENDING, "reason": reason,
                "next_attempt_on": (_d(today) + timedelta(days=1)).isoformat()}

    if provider_error or not closes:
        return open_or_final(f"no price data: {provider_error or 'empty series'}")

    bars = sorted((d[:10], v) for d, v in closes.items() if v)
    as_of = row["as_of"][:10]
    entry = [(d, v) for d, v in bars if d <= as_of]
    if not entry or (_d(as_of) - _d(entry[-1][0])).days > MAX_ENTRY_STALENESS_DAYS:
        return {**base, "state": UNRESOLVABLE,
                "reason": "no decision-time entry bar within "
                          f"{MAX_ENTRY_STALENESS_DAYS} days of as_of"}
    exit_ = [(d, v) for d, v in bars if as_of < d <= end]
    last_bar = bars[-1][0]
    if not exit_ or (_d(end) - _d(exit_[-1][0])).days > MAX_EXIT_STALENESS_DAYS:
        if last_bar < end:
            # The series stops before the horizon end: lag, or delisting.
            return open_or_final(f"series ends {last_bar}, before horizon end {end}")
        return {**base, "state": UNRESOLVABLE,
                "reason": f"no bar within {MAX_EXIT_STALENESS_DAYS} days before "
                          f"horizon end {end} although the series continues"}

    e_date, e_px = entry[-1]
    x_date, x_px = exit_[-1]
    ret = round((x_px - e_px) / e_px, 6)
    out = {**base, "state": RESOLVED, "entry_date": e_date,
           "entry_close": e_px, "exit_date": x_date, "exit_close": x_px,
           "realized_return": ret,
           "late": today[:10] > final, "days_late": max(
               0, (_d(today) - _d(end)).days)}
    if row.get("opportunity_state") == SO.MISSED_OPPORTUNITY_CANDIDATE:
        out["confirmed_miss"] = abs(ret) >= MIN_ABS_RETURN
    return out


def read_outcomes(root) -> List[dict]:
    path = pathlib.Path(root) / OUTCOMES_FILE
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def latest_by_key(events: Iterable[dict]) -> Dict[str, dict]:
    """Terminal events win and are never superseded by a later event."""
    latest: Dict[str, dict] = {}
    for ev in events:
        k = ev.get("record_key")
        prev = latest.get(k)
        if prev and prev.get("state") in TERMINAL:
            continue
        latest[k] = ev
    return latest


def resolve(audit_rows: List[dict], *, root, today: str,
            series_fn: Callable[[str], Dict[str, float]],
            write: bool = True) -> dict:
    """Grade every audit row that is mature and not yet terminal.

    One fetch per instrument per call, so the entry and exit of every record
    share the same price basis even across a split.
    """
    prior = latest_by_key(read_outcomes(root))
    cache: Dict[str, tuple] = {}
    new_events: List[dict] = []
    counts = {"inspected": len(audit_rows), RESOLVED: 0, PENDING: 0,
              UNRESOLVABLE: 0, NOT_MATURE: 0, "already_terminal": 0,
              "unchanged_pending": 0}
    seen_this_run = set()
    counts["duplicate_rows"] = 0
    for row in audit_rows:
        key = record_key(row)
        if key in seen_this_run:      # a cycle that was run twice wrote it twice
            counts["duplicate_rows"] += 1
            continue
        seen_this_run.add(key)
        if prior.get(key, {}).get("state") in TERMINAL:
            counts["already_terminal"] += 1
            continue
        end = SO.horizon_end(row["as_of"], int(
            (row.get("opportunity") or {}).get("horizon_days", SO.HORIZON_DAYS)))
        if end >= today[:10]:   # the horizon-end close is final only once that day has passed
            counts[NOT_MATURE] += 1
            continue
        sym = row.get("instrument")
        if sym not in cache:
            try:
                cache[sym] = (series_fn(sym) or {}, "")
            except Exception as exc:  # provider failure is a state, not a crash
                cache[sym] = ({}, f"{type(exc).__name__}: {exc}"[:160])
        closes, err = cache[sym]
        ev = grade(row, closes, today=today, provider_error=err)
        counts[ev["state"]] += 1
        p = prior.get(key)
        if (ev["state"] == PENDING and p and p.get("state") == PENDING
                and p.get("reason") == ev["reason"]):
            counts["unchanged_pending"] += 1
            continue
        new_events.append(ev)
    if write and new_events:
        path = pathlib.Path(root) / OUTCOMES_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            for ev in new_events:
                fh.write(json.dumps(ev, sort_keys=True) + "\n")
    return {"counts": counts, "appended": len(new_events) if write else 0,
            "would_append": len(new_events), "events": new_events}


def summarise(events: Iterable[dict]) -> dict:
    """Decision-level statistics over terminal outcomes. Duplicates collapse.

    No Brier score: none of these records carries a probability.
    """
    latest = latest_by_key(events)
    by_decision: Dict[tuple, dict] = {}
    for ev in latest.values():
        if ev.get("state") == RESOLVED:
            by_decision.setdefault(tuple(ev["decision_key"]), ev)
    resolved = list(by_decision.values())
    cands = [e for e in resolved if "confirmed_miss" in e]
    by_inst: Dict[str, dict] = {}
    for e in cands:
        b = by_inst.setdefault(e["instrument"], {"candidates": 0, "confirmed": 0})
        b["candidates"] += 1
        b["confirmed"] += int(e["confirmed_miss"])
    states: Dict[str, int] = {}
    for ev in latest.values():
        states[ev["state"]] = states.get(ev["state"], 0) + 1
    rets = [abs(e["realized_return"]) for e in resolved]
    return {"contract": CONTRACT, "records_by_state": states,
            "distinct_decisions_resolved": len(resolved),
            "duplicate_records_collapsed": sum(
                1 for e in latest.values() if e.get("state") == RESOLVED)
            - len(resolved),
            "fired_decisions": sum(1 for e in resolved if e["fired"]),
            "missed_candidates_resolved": len(cands),
            "confirmed_misses": sum(int(e["confirmed_miss"]) for e in cands),
            "confirmed_miss_rate": (round(sum(int(e["confirmed_miss"])
                                              for e in cands) / len(cands), 3)
                                    if cands else None),
            "median_abs_21d_move": (sorted(rets)[len(rets) // 2]
                                    if rets else None),
            "by_instrument": by_inst,
            "brier": None,
            "brier_note": "undefined: no record carries a probability",
            "trade_return": None,
            "trade_return_note": "undefined: no record fired, so no position "
                                 "or direction exists to score"}
