"""The scheduled resolver for the econ forward ledger.

WHY THIS EXISTS
---------------
`forward_engine.resolve_one` and `forward_ledger.append` were production
grade, and nothing called them: the only caller of `resolve_one` was a break
proof. The first expectation (PERMIT, DOWN, p=0.55) comes due on 2026-12-25,
and on that day it would have stayed OPEN forever. This module is the caller.

WHAT IT DOES, ONCE PER RUN
--------------------------
1. Reads the CURRENT state of every expectation (`forward_ledger.by_id`).
2. For each one whose horizon has arrived and that is not terminal, builds a
   vintage panel for its series from ALFRED, bounded to `at` -- the run's own
   date. Nothing published after `at` can enter, so a run can never backdate.
3. Asks `forward_engine.state_of` where it stands, and:
     ELIGIBLE  -> `resolve_one`, appended (a NEW line; the original stays)
     EXPIRED   -> a terminal EXPIRED_UNRESOLVED line, with the reason
     BLOCKED   -> nothing appended; the run log says why. A provider failure
                  is BLOCKED, never a resolution and never terminal.
4. Appends one row to the run log, including missed days since the last
   run, so a sleeping Mac is visible and harmless: the next run catches up.

It never opens, edits or re-scores an expectation. `forward_ledger.append`
refuses any change to the immutable core.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import pathlib
import urllib.parse
import urllib.request
from typing import Callable, Dict, List, Optional

from . import forward_engine as FE
from . import forward_ledger as FL
from .panel import Cell, Panel

CONTRACT = "econ_resolve_job.v1"
TERMINAL = (FE.RESOLVED, FE.EXPIRED, FE.INVALIDATED, "CORRECT", "INCORRECT")
ALFRED = "https://api.stlouisfed.org/fred/series/observations"


def alfred_rows(series_id: str, start: str, at: str) -> List[dict]:
    """Every vintage of every period from `start`, as known on `at`."""
    key = os.environ.get("FRED_API_KEY")
    if not key:
        from dotenv import load_dotenv      # same convention as macro_data
        load_dotenv()
        key = os.environ.get("FRED_API_KEY")
    if not key:
        raise RuntimeError("FRED_API_KEY is not set")
    q = {"series_id": series_id, "api_key": key, "file_type": "json",
         "observation_start": start, "realtime_start": start,
         "realtime_end": at}
    with urllib.request.urlopen(f"{ALFRED}?{urllib.parse.urlencode(q)}",
                                timeout=30) as r:
        return json.load(r)["observations"]


def panel_for(series_id: str, rows: List[dict]) -> Panel:
    p = Panel()
    for o in rows:
        if o.get("value") in (None, ".", ""):
            continue
        p.add(Cell(series_id=series_id, observed_at=o["date"],
                   vintage_at=o["realtime_start"], value=float(o["value"]),
                   source="ALFRED", revision_state="PUBLISHER_VINTAGE"))
    return p.finalise()


def _last_run(log: pathlib.Path) -> Optional[str]:
    if not log.exists():
        return None
    last = None
    for line in log.read_text(encoding="utf-8").splitlines():
        try:
            last = json.loads(line).get("at") or last
        except json.JSONDecodeError:
            continue
    return last


def run(*, at: str, ledger_path: pathlib.Path, log_path: pathlib.Path,
        fetch: Callable[[str, str, str], List[dict]] = alfred_rows,
        write: bool = True) -> dict:
    prev = _last_run(log_path)
    missed = (max(0, (_dt.date.fromisoformat(at)
                      - _dt.date.fromisoformat(prev)).days - 1)
              if prev else None)
    row: Dict = {"contract": CONTRACT, "at": at, "previous_run": prev,
                 "missed_runs": missed, "dry_run": not write,
                 "resolved": [], "expired": [], "blocked": [], "open": 0,
                 "terminal": 0}
    try:
        current = FL.by_id(ledger_path)
        appends = []
        for eid, rec in sorted(current.items()):
            if rec.get("outcome") in TERMINAL:
                row["terminal"] += 1
                continue
            if at < rec.get("expires_at", "9999"):
                row["open"] += 1
                continue
            con = FE.contract_from(rec)
            panel, err = None, ""
            if con is not None:
                try:
                    panel = panel_for(con.series_id,
                                      fetch(con.series_id, con.baseline_period, at))
                except Exception as exc:     # a provider failure is a state
                    err = f"{type(exc).__name__}: {exc}"[:200]
            if err:
                row["blocked"].append({"id": eid, "reason": err})
                continue
            st = FE.state_of(rec, at=at, panel=panel)
            if st == FE.ELIGIBLE:
                out = FE.resolve_one(rec, panel=panel, at=at)
                if out is None:          # baseline period missing from panel
                    row["blocked"].append({"id": eid, "reason":
                                           "baseline period not readable"})
                    continue
                out["resolved_by"] = CONTRACT
                appends.append(out)
                row["resolved"].append({"id": eid, "correct": out["correct"],
                                        "squared_error": out["squared_error"]})
            elif st == FE.EXPIRED:
                appends.append({**rec, "outcome": FE.EXPIRED, "resolved_at": at,
                                "resolved_by": CONTRACT, "resolution_note":
                                f"horizon period of {con.series_id if con else '?'} "
                                f"never published within {FE.GRACE_DAYS} days"})
                row["expired"].append({"id": eid})
            else:
                row["blocked"].append({"id": eid, "reason": f"state {st}: "
                                       "resolving figure not yet published"})
        if write and appends:
            FL.append(appends, path=ledger_path)
        row["appended"] = len(appends) if write else 0
        row["would_append"] = len(appends)
        row["status"] = "ALERT" if (missed or any(
            "Error" in b["reason"] for b in row["blocked"])) else "OK"
    except Exception as exc:
        row.update(status="FAILED", error=f"{type(exc).__name__}: {exc}"[:300])
    if write:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True, default=str) + "\n")
    return row


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="python -m intent_engine.econ.resolve_job")
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--log", required=True)
    ap.add_argument("--at", help="defaults to today; a past date is refused")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    today = _dt.date.today().isoformat()
    at = a.at or today
    if at > today or (at < today and not a.dry_run):
        ap.error("--at may differ from today only in a dry run, and never "
                 "lie in the future")
    row = run(at=at, ledger_path=pathlib.Path(a.ledger),
              log_path=pathlib.Path(a.log), write=not a.dry_run)
    print(json.dumps(row, indent=1, default=str))
    return 1 if row.get("status") == "FAILED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
