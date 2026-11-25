"""The daily job for the forward shadow ledger: resolve, check for overdue, log.

WHY A DAILY JOB AND NOT ONE ON 12-11
------------------------------------
`forward.resolve_open` scores only on scheduled sessions and leaves anything
whose data has not arrived OPEN. That makes it safe to run every day, and
running it every day is what makes a sleeping Mac harmless: the first run
after wake resolves every forecast whose exit session has passed, however
many runs were missed. Nothing here can move a due date.

WHAT IT ADDS
------------
* `overdue`: an open forecast whose scheduled exit is more than
  `DATA_GRACE_DAYS` in the past. It should have resolved or voided by then,
  so it is an alert, never a silent wait.
* `missed_runs`: the calendar days since the last logged run, minus one. A
  gap is reported every time, so a scheduler that stopped is visible.
* An append-only run log, `reports/paper_validation/daily_runs.jsonl`, one
  row per run, including failed runs.

It never registers forecasts. Registration is a separate decision.
"""
from __future__ import annotations

import datetime as _dt
import json
import pathlib
from typing import Callable, Dict, Optional

from intent_engine.paper_validation import forward as FW
from intent_engine.paper_validation import ledger as LG
from intent_engine.paper_validation import schedule as SCH
from intent_engine.paper_validation import universe as U

RUN_LOG = FW.ROOT / "daily_runs.jsonl"


def overdue(ledger: LG.Ledger, today: str) -> list:
    out = []
    limit = _dt.date.fromisoformat(today) - _dt.timedelta(days=FW.DATA_GRACE_DAYS)
    for st in ledger.open_forecasts():
        _entry, exit_, _cal = SCH.schedule_of(st.registration)
        if _dt.date.fromisoformat(exit_) < limit:
            out.append({"forecast_id": st.forecast_id, "scheduled_exit": exit_})
    return out


def _last_run(log_path: pathlib.Path) -> Optional[str]:
    if not log_path.exists():
        return None
    last = None
    for line in log_path.read_text(encoding="utf-8").splitlines():
        try:
            last = json.loads(line).get("ny_date") or last
        except json.JSONDecodeError:
            continue
    return last


def run(*, now: _dt.datetime, ledger_path=FW.FORWARD_LEDGER,
        log_path: pathlib.Path = RUN_LOG,
        bars_fn: Optional[Callable] = None,
        clock: Callable[[], _dt.datetime] = LG._now) -> dict:
    today = LG.ny_date(now)
    prev = _last_run(log_path)
    missed = (max(0, (_dt.date.fromisoformat(today)
                      - _dt.date.fromisoformat(prev)).days - 1)
              if prev else None)
    row: Dict = {"ny_date": today, "ran_at": now.isoformat(timespec="seconds"),
                 "previous_run": prev, "missed_runs": missed}
    try:
        led = LG.Ledger(ledger_path, LG.FORWARD_SHADOW, clock=clock)
        syms = sorted({s.registration["instrument"]
                       for s in led.open_forecasts()} | {U.BENCHMARK})
        due_any = any(SCH.schedule_of(s.registration)[1] < today
                      for s in led.open_forecasts())
        if due_any:
            fetch = bars_fn or (lambda ss: FW.forward_bars(ss, now=now))
            bars, failed = fetch(syms)
            res = FW.resolve_open(led, bars, now=now)
            row.update(res, price_failures=failed)
        else:
            row.update(resolved=0, voided=0, fetched=False,
                       still_open=len(led.open_forecasts()))
        od = overdue(LG.Ledger(ledger_path, LG.FORWARD_SHADOW, clock=clock), today)
        row["overdue"] = len(od)
        row["overdue_ids"] = [o["forecast_id"] for o in od[:20]]
        row["due_schedule"] = LG.due_schedule(
            LG.Ledger(ledger_path, LG.FORWARD_SHADOW, clock=clock))
        row["alerts"] = ([f"{len(od)} forecast(s) overdue past the "
                          f"{FW.DATA_GRACE_DAYS}-day data grace"] if od else []) + (
            [f"{missed} daily run(s) missed since {prev}"] if missed else [])
        row["status"] = "ALERT" if row["alerts"] else "OK"
    except Exception as exc:          # a failed run is logged, never silent
        row.update(status="FAILED", error=f"{type(exc).__name__}: {exc}"[:300])
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True, default=str) + "\n")
    return row
