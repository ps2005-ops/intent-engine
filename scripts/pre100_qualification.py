"""The frozen 50-company PRE-100 qualification, paced to the preview's quota.

WHY A SEPARATE RUNNER. `perf_progressive_matrix` submits as fast as it can,
and the preview allows TEN analyses per IP per rolling hour. Firing 50 at it
returns 40 rows of QUOTA_EXHAUSTED, which measures the quota rather than the
product. This paces submissions under the cap and treats a 429 as "wait", not
as a result.

EVERY ROW IS PERSISTED AS IT LANDS. A five-hour cohort that writes its output
at the end loses everything to one interruption, and a partial cohort that
survives is still evidence. The file is rewritten after each company.

THE COHORT IS FROZEN. It is `perf_progressive_matrix.QUALIFY_50`, chosen
before any of it was run, and this runner may not reorder or trim it: a cohort
edited after seeing results measures the chooser.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from live_recovery_matrix import analyse                    # noqa: E402
from perf_progressive_matrix import QUALIFY_50              # noqa: E402

#: Ten per rolling hour is the cap; 6.6 minutes between SUBMISSIONS keeps the
#: rate at ~9.1/hour with headroom for clock skew on the server's window.
PACE_S = 396.0
#: How long to wait when the server says the window is full anyway.
QUOTA_BACKOFF_S = 420.0
MAX_QUOTA_WAITS = 6


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--budget", type=float, default=300.0)
    ap.add_argument("--pace", type=float, default=PACE_S)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    cohort = QUALIFY_50[args.start:]
    if args.limit:
        cohort = cohort[:args.limit]
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    rows, began = [], time.monotonic()
    print(f"PRE-100 qualification: {len(cohort)} companies, "
          f"pace {args.pace}s\n", flush=True)
    for index, (name, domain) in enumerate(cohort, 1):
        submitted_at = time.monotonic()
        row, waits = None, 0
        while True:
            row = analyse(name, domain, budget_s=args.budget)
            if row.get("outcome") != "QUOTA_EXHAUSTED":
                break
            waits += 1
            if waits > MAX_QUOTA_WAITS:
                break
            print(f"    quota window full; waiting "
                  f"{int(QUOTA_BACKOFF_S)}s ({waits})", flush=True)
            time.sleep(QUOTA_BACKOFF_S)
        row["index"] = index
        rows.append(row)
        # PERSISTED NOW, not at the end.
        out.write_text(json.dumps(rows, indent=2), "utf-8")
        elapsed = (time.monotonic() - began) / 60.0
        print(f"[{index:>2}/{len(cohort)}] {name[:24]:<25}"
              f"submit={str(row.get('submit_s')):>6} "
              f"core={str(row.get('core_open_s')):>6} "
              f"{row.get('outcome',''):<20} docs={row.get('documents')} "
              f"{row.get('abstention','')} ({elapsed:.0f}m)", flush=True)
        if index < len(cohort):
            rest = args.pace - (time.monotonic() - submitted_at)
            if rest > 0:
                time.sleep(rest)

    terminal = sum(1 for r in rows if r.get("core_open_s") is not None)
    usable = sum(1 for r in rows if r.get("outcome") == "USABLE_REPORT")
    abstain = sum(1 for r in rows if r.get("outcome") == "BOUNDED_ABSTENTION")
    cores = sorted(r["core_open_s"] for r in rows
                   if r.get("core_open_s") is not None)

    def pct(p):
        return cores[min(len(cores) - 1, int(len(cores) * p))] if cores else None
    print(f"\nattempted {len(rows)}  terminal {terminal}  usable {usable}  "
          f"bounded abstention {abstain}")
    if cores:
        print(f"CORE p50 {pct(0.5)}s  p90 {pct(0.9)}s  p95 {pct(0.95)}s  "
              f"<=120s {sum(1 for c in cores if c <= 120)}/{len(cores)}")
    print(f"-> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
