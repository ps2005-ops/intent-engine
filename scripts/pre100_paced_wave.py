#!/usr/bin/env python3
"""Run a wave one company at a time, with a gap, because bursts get throttled.

WHY PACING IS THE FIX AND NOT PATIENCE. Measured 2026-08-18: a seven-company
back-to-back wave returned "no approved source could be retrieved — HTTP 429"
for five of them, and the SAME company on the SAME deployed SHA succeeded on
a single re-run twenty minutes later. The same primary-document URLs answer
200 from a laptop with the same production User-Agent throughout.

So SEC's fair-access limit is triggered by the GAUNTLET'S OWN CADENCE — three
or four EDGAR documents per analysis, eight analyses with no gap — and not by
the product, the User-Agent, or the demo quota. A wave that paces itself is
the difference between six unscoreable companies in eight and a measurable
distribution.

The default gap is also, deliberately, the demo quota: ten runs per IP per
rolling hour is one run per six minutes.

Usage:
  python scripts/pre100_paced_wave.py OUTDIR GAP_SECONDS "Name:CIK:TICKER" ...
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def main() -> int:
    if len(sys.argv) < 4:
        print(__doc__)
        return 2
    outdir, gap = sys.argv[1], int(sys.argv[2])
    targets = sys.argv[3:]
    os.makedirs(outdir, exist_ok=True)
    summary = []
    for i, target in enumerate(targets):
        if i:
            print(f"... pacing {gap}s before {target.split(':')[0]}",
                  flush=True)
            time.sleep(gap)
        print(f"=== {target.split(':')[0]}", flush=True)
        subprocess.run(
            [sys.executable, os.path.join(HERE, "pre100_batch_journey.py"),
             outdir, target],
            cwd=os.path.dirname(HERE))
        # Read what the journey just wrote, so the wave's own log carries the
        # verdict rather than only the per-company directory.
        slug = target.split(":")[0].lower()
        slug = "".join(c if c.isalnum() else "_" for c in slug).strip("_")
        run_path = os.path.join(outdir, slug, "run.json")
        row = {"company": target.split(":")[0], "captured": False}
        if os.path.exists(run_path):
            run = json.load(open(run_path))
            row = {"company": run.get("company"),
                   "captured": True,
                   "run_id": run.get("run_id", ""),
                   "seconds": run.get("seconds"),
                   "auto_advanced": run.get("auto_advanced"),
                   "claimed_failure": run.get("claimed_failure"),
                   "blocked_external": run.get("blocked_external")}
        summary.append(row)
        print(json.dumps(row), flush=True)
        with open(os.path.join(outdir, "paced_wave.json"), "w") as fh:
            json.dump(summary, fh, indent=2)
    ok = sum(1 for r in summary
             if r.get("captured") and not r.get("blocked_external"))
    print(f"\nRETRIEVED {ok}/{len(summary)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
