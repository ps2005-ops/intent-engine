#!/usr/bin/env python3
"""The 50-company PRE-100 qualification, paced around the demo quota.

THE QUOTA IS SCHEDULING, NOT A STOPPING CONDITION. The preview allows ten
analyses per IP per rolling hour and the cohort is fifty, so this resumes
across windows instead of terminating: results accumulate in one file, a
company already recorded is never re-run, and a 429 makes the driver wait for
the window rather than abandoning the cohort.

THE COHORT IS FROZEN. It comes from `perf_progressive_matrix.QUALIFY_50`,
preregistered before any of it was run. Nothing here may reorder it, replace
a failure, or re-run only the companies that went well.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from perf_progressive_matrix import QUALIFY_50                  # noqa: E402
from pre100_live_qualification import qualify, summarise        # noqa: E402

#: Companies sampled for live Q&A during the run (§6 of the closure spec).
QA_SAMPLE = {"Apple Inc.", "Microsoft", "NVIDIA", "JPMorgan Chase",
             "Caterpillar", "Olo Inc"}

#: How long to wait after a 429 before trying the next company. The window is
#: an hour long and rolling, so a short probe wastes nothing and a long sleep
#: would idle through capacity that has already come back.
QUOTA_RETRY_S = 420.0


def load(path):
    if path.exists():
        try:
            return json.loads(path.read_text())
        except ValueError:
            pass
    return {"rows": []}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="reports/perf/pre100_qualify50.json")
    ap.add_argument("--budget", type=float, default=300.0)
    ap.add_argument("--max-waits", type=int, default=40)
    a = ap.parse_args()

    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    state = load(out)
    done = {r["company"] for r in state["rows"]
            if r.get("status") not in (None, "", "QUOTA_EXHAUSTED")}
    print(f"cohort={len(QUALIFY_50)} already_done={len(done)}")

    waits = 0
    for name, domain in QUALIFY_50:
        if name in done:
            continue
        while True:
            row = qualify(name, domain, budget_s=a.budget,
                          with_qa=(name in QA_SAMPLE))
            if row.get("status") != "QUOTA_EXHAUSTED":
                break
            waits += 1
            wait_s = row.get("retry_after_s") or QUOTA_RETRY_S
            if waits > a.max_waits:
                print("  ! wait budget spent — stopping with partial cohort")
                state["rows"] = [r for r in state["rows"]
                                 if r.get("status") != "QUOTA_EXHAUSTED"]
                state["summary"] = summarise(state["rows"])
                out.write_text(json.dumps(state, indent=1))
                return 1
            print(f"  … quota full, waiting {wait_s/60:.0f}m before {name} "
                  f"(wait {waits}, service-stated)", flush=True)
            time.sleep(wait_s)
        state["rows"] = [r for r in state["rows"]
                         if r.get("company") != name] + [row]
        state["summary"] = summarise(state["rows"])
        out.write_text(json.dumps(state, indent=1))
        print(f"  {row.get('status','?'):14s} {name:26s} "
              f"core={row.get('core_ready_seconds')} "
              f"usable={row.get('usable_seconds')} "
              f"docs={row.get('blocking_documents')}/"
              f"{row.get('deferred_documents')}/{row.get('final_documents')} "
              f"qa={row.get('questions_ok')} "
              f"{'ENUM_LEAK' if row.get('enum_leak') else ''}", flush=True)

    state["summary"] = summarise(state["rows"])
    out.write_text(json.dumps(state, indent=1))
    print("\n" + json.dumps(state["summary"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
