#!/usr/bin/env python
"""Audit-only outcome attachment for the market runtime's signal audit records.

The production `resolve_outcomes` step counts records whose 21-day horizon has
elapsed and attaches nothing. This script runs the runtime's OWN grader,
`market.signal_opportunity.resolve_outcome` (byte-identical to the deployed
copy), over a READ-ONLY copy of the audit records, and writes the graded rows
to a separate file. It never writes to the runtime's root.

These records are not forecasts: none fired, none carries a direction or a
probability. Grading them answers one question only -- was a "missed
opportunity candidate" a real miss (|21-day move| >= the noise floor)?

Usage:
    PYTHONPATH=src python scripts/audit_signal_outcomes.py \
        --audit /Users/prathamsharma/intent-engine-market/reports/market/signal_audit.jsonl \
        --bars-dir <dir with SYMBOL.json.gz> [--bars-dir <another>] \
        --today 2026-11-10 --out reports/forecast_audit/signal_outcomes_2026-11-10.jsonl
"""
import argparse
import collections
import dataclasses
import json
import sys
from pathlib import Path

from intent_engine.market import signal_opportunity as SO
from intent_engine.paper_validation import bars as BR

CONTRACT = "forecast_audit_signal_outcome.v1"


def _closes(symbol, dirs):
    for d in dirs:
        doc = BR.read_cache(symbol, d)
        if doc:
            b = BR.to_bars(doc)
            return dict(zip(b.dates, b.close_adj)), b.dates[-1], doc.get(
                "retrieved_at", ""), doc.get("sha256", "")[:16]
    return None, None, None, None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--audit", required=True)
    ap.add_argument("--bars-dir", action="append", required=True)
    ap.add_argument("--today", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)

    out = Path(a.out)
    if out.exists():
        print(f"refusing to overwrite {out}", file=sys.stderr)
        return 2
    fields = {f.name for f in dataclasses.fields(SO.AuditRecord)}
    rows = [json.loads(l) for l in open(a.audit, encoding="utf-8")]
    cache = {}
    tally = collections.Counter()
    graded = []
    for r in rows:
        end = SO.horizon_end(r["as_of"], r["opportunity"].get(
            "horizon_days", SO.HORIZON_DAYS))
        if end > a.today:
            tally["NOT_YET_DUE"] += 1
            continue
        sym = r["instrument"]
        if sym not in cache:
            cache[sym] = _closes(sym, a.bars_dir)
        closes, last_bar, retrieved, sha = cache[sym]
        rec = {"contract": CONTRACT, "cycle_id": r["cycle_id"],
               "company_id": r["company_id"], "instrument": sym,
               "as_of": r["as_of"], "horizon_end": end,
               "opportunity_state": r["opportunity_state"],
               "fired": r["fired"], "writes_to_runtime": False}
        if closes is None:
            rec.update(audit_state="UNRESOLVABLE",
                       reason=f"no price history available for {sym}")
        elif last_bar < end:
            # resolve_outcome would take the last close BEFORE the horizon end
            # as the exit; refuse instead of grading on a short window.
            rec.update(audit_state="WAITING_FOR_DATA",
                       reason=f"bars end {last_bar}, horizon ends {end}")
        else:
            src = SO.AuditRecord(**{k: v for k, v in r.items() if k in fields})
            res = SO.resolve_outcome(src, closes, today=a.today)
            if res.outcome_state != SO.RESOLVED:
                rec.update(audit_state="UNRESOLVABLE",
                           reason="grader refused: no close at or before "
                                  "as_of or horizon end")
            else:
                miss = SO.confirmed_miss(res)
                rec.update(audit_state="RESOLVED",
                           realized_return=res.realized_return,
                           confirmed_miss=miss,
                           price_vintage={"source": BR.SOURCE,
                                          "retrieved_at": retrieved,
                                          "sha256": sha, "last_bar": last_bar})
        tally[rec["audit_state"]] += 1
        if rec.get("confirmed_miss") is not None:
            tally[f"confirmed_miss={rec['confirmed_miss']}"] += 1
        graded.append(rec)
    with open(out, "x", encoding="utf-8") as fh:
        for rec in graded:
            fh.write(json.dumps(rec, sort_keys=True) + "\n")
    print(json.dumps(dict(tally), indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
