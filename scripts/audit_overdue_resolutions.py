#!/usr/bin/env python
"""Audit-only resolution of overdue predictions in the July prediction ledger.

Reads the live ledger READ-ONLY (sqlite `mode=ro`), grades every overdue
level-rule prediction with the ledger's own, unchanged grader
(`market_resolution.resolve_level_rule`) against FRED responses fetched on the
audit date, and writes the result to a SEPARATE append-only audit file.

It never writes to the ledger, never changes a prediction, its deadline or its
rule, and never touches the live FRED cache. The live ledger already holds a
terminal `unresolvable` row for each of these predictions; whether to supersede
those rows is a decision for a human, not for this script.

Usage:
    PYTHONPATH=src python scripts/audit_overdue_resolutions.py \
        --ledger /Users/prathamsharma/intent-engine/data/prediction_ledger.db \
        --responses reports/forecast_audit/fred_responses_2026-11-10.json \
        --context reports/forecast_audit/fred_context_2026-11-10.json \
        --out reports/forecast_audit/overdue_resolutions_2026-11-10.jsonl
"""
import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from intent_engine.core.macro_data import _parse_response
from intent_engine.core.market_resolution import resolve_level_rule
from intent_engine.core.prediction_ledger import LevelRule

CONTRACT = "forecast_audit_resolution.v1"


def _ledger_rows(path: str):
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    rows = con.execute(
        "select rowid, id, data from predictions order by rowid").fetchall()
    con.close()
    return rows


def _first_release(raw: dict, obs_date: str):
    for o in (raw or {}).get("observations", []):
        if o["date"] == obs_date and o["value"] != ".":
            return float(o["value"]), o.get("realtime_start")
    return None, None


def _flags(pid: str, reg: dict, ctx: dict, obs_value) -> list:
    """Defects in the REGISTERED forecast, recorded beside the outcome. They
    never change the outcome: the rule is graded exactly as written."""
    out = []
    rule = reg["resolution_rule"]
    if rule["series"] == "UNRATE" and rule["op"] == ">=":
        known = [o for o in ctx["UNRATE_as_of_2026-07-20"]["observations"]
                 if o["value"] != "."]
        last = known[-1]
        if float(last["value"]) >= rule["value"]:
            out.append(
                f"DEGENERATE_ALREADY_TRUE: the last UNRATE known at creation "
                f"({last['date']}={last['value']}, vintage 2026-07-20) already "
                f"satisfied >= {rule['value']}; the claim says 'rises to' but "
                "nothing had to rise")
    if rule["series"] == "BAMLH0A0HYM2":
        out.append(
            f"UNIT_MISMATCH: the series is in percent (about 2.7 at creation) "
            f"and the threshold is {rule['value']}; read as basis points the "
            "intended threshold is 3.10%. The registered rule could not be "
            "met; under the 3.10% reading the outcome is the same "
            f"(observed {obs_value})")
    if rule["series"] == "T10Y2Y" and "remain" in reg["claim_text"].lower():
        path = [(o["date"], float(o["value"]))
                for o in ctx["T10Y2Y_path"]["observations"]
                if o["value"] != "." and reg["created_at"][:10] <= o["date"] <= rule["by"]]
        low = min(path, key=lambda x: x[1])
        held = low[1] >= rule["value"]
        out.append(
            "CLAIM_RULE_MISMATCH: the claim says 'remains above' (every day) "
            "but the rule checks one observation at the due date. Under the "
            f"every-day reading the minimum was {low[1]} on {low[0]}, so the "
            f"claim {'held' if held else 'did NOT hold'}")
    if rule["series"] == "UNRATE" and pid.startswith("2d44806f"):
        out.append(
            "LATE_PUBLICATION: the first observation on/after the due date is "
            "the October 2026 value, first published 2026-11-06; the resolver "
            "ran on 2026-10-09, when no such value existed")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--responses", required=True)
    ap.add_argument("--context", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--as-of", default=date.today().isoformat())
    a = ap.parse_args(argv)

    responses = json.loads(Path(a.responses).read_text())
    context = json.loads(Path(a.context).read_text())
    resp_sha = hashlib.sha256(Path(a.responses).read_bytes()).hexdigest()

    # The ledger is append-only by row: a resolution is a second row with the
    # same id. Registration = first row; current state = last row.
    first, last = {}, {}
    for rowid, pid, data in _ledger_rows(a.ledger):
        d = json.loads(data)
        first.setdefault(pid, (rowid, d))
        last[pid] = (rowid, d)

    out_path = Path(a.out)
    if out_path.exists():
        print(f"refusing to overwrite {out_path}; audit files are append-once",
              file=sys.stderr)
        return 2
    written_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    records = []
    for pid, (reg_row, reg) in first.items():
        rule = reg.get("resolution_rule")
        cur_row, cur = last[pid]
        due = reg["resolve_by"] <= a.as_of
        if not due:
            continue
        short = pid[:8]
        base = {
            "contract": CONTRACT, "prediction_id": pid,
            "registration_row": reg_row, "current_row": cur_row,
            "original": {k: reg.get(k) for k in (
                "created_at", "resolve_by", "probability", "claim_text",
                "resolution_rule", "resolution_source", "source")},
            "ledger_state": {"outcome": cur.get("outcome"),
                             "resolved_at": cur.get("resolved_at"),
                             "note": cur.get("resolution_note")},
            "audit_as_of": a.as_of, "written_at": written_at,
            "writes_to_ledger": False,
        }
        if rule is None:
            base.update(audit_outcome="NOT_MACHINE_RESOLVABLE",
                        reason="no resolution_rule was registered; a human "
                               "must judge it against its own claim")
            records.append(base)
            continue
        if cur.get("outcome") in ("happened", "did_not_happen"):
            continue                       # already scored; reviewed separately
        if rule.get("type") != "level":
            base.update(audit_outcome="NOT_ATTEMPTED",
                        reason="only level rules failed for lack of data")
            records.append(base)
            continue
        raw = responses.get(f"{short}:latest")
        series = _parse_response(raw, rule["series"])
        result = resolve_level_rule(
            LevelRule(**rule), fred_fetcher=lambda *_a, **_k: series)
        obs = result.note.split("=", 1)[1].split(" on ")
        obs_value, obs_date = float(obs[0]), obs[1].split(" ")[0]
        fr_value, fr_published = _first_release(
            responses.get(f"{short}:first_release"), obs_date)
        p = float(reg["probability"])
        y = 1 if result.outcome == "happened" else 0
        base.update(
            audit_outcome=result.outcome,
            grader="intent_engine.core.market_resolution.resolve_level_rule (unchanged)",
            grader_note=result.note,
            observation={"date": obs_date, "value_latest": obs_value,
                         "value_first_release": fr_value,
                         "first_published": fr_published or
                         "not in ALFRED (daily market series, not revised)"},
            first_release_agrees=(fr_value is None or fr_value == obs_value),
            brier_under_registered_rule=round((p - y) ** 2, 6),
            source_responses_sha256=resp_sha[:16],
            flags=_flags(pid, reg, context, obs_value),
        )
        records.append(base)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "x", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, sort_keys=True) + "\n")
    for r in records:
        print(r["prediction_id"][:8], r["original"]["resolve_by"],
              r["ledger_state"]["outcome"], "->", r["audit_outcome"],
              r.get("brier_under_registered_rule", ""),
              "| flags:", len(r.get("flags", [])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
