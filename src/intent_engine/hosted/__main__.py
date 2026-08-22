"""Hosted runtime CLI — the entrypoint every GitHub-Actions workflow calls.

    python -m intent_engine.hosted <job> [--as-of YYYY-MM-DD]
    python -m intent_engine.hosted db-health
    python -m intent_engine.hosted scheduler-health

Each <job> builds the production context from the environment (durable DB from
DATABASE_URL, real Alpaca PAPER broker, Tiingo prices), runs the job inside a
durable execution record, prints the result as JSON, and exits non-zero on
failure. No always-on process; the runner connects, works, and exits — so Render
free sleeping never interrupts anything.
"""
from __future__ import annotations

import argparse
import json
import sys

from intent_engine.hosted.jobs import JOBS
from intent_engine.hosted.records import latest_executions, run_job


def _today() -> str:
    from intent_engine.runtime.market_calendar import today_ny
    return today_ny().isoformat()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="intent_engine.hosted", description=__doc__)
    ap.add_argument("job", choices=list(JOBS) + ["db-health", "scheduler-health"])
    ap.add_argument("--as-of", default=None)
    args = ap.parse_args(argv)
    as_of = args.as_of or _today()

    if args.job == "db-health":
        from intent_engine.storage.health import check_health
        rep = check_health()
        print(json.dumps(rep, indent=2, default=str))
        return 0 if rep.get("ok") else 1

    if args.job == "scheduler-health":
        from intent_engine.storage.durable import DurableStore
        store = DurableStore()
        print(json.dumps(latest_executions(store), indent=2, default=str))
        return 0

    # a real job: build the production context and run it durably
    from intent_engine.hosted.context import HostedContext
    ctx = HostedContext.from_env()
    record = run_job(ctx.store, args.job, lambda: JOBS[args.job](ctx, as_of),
                     as_of=as_of)
    print(json.dumps(record, indent=2, default=str))
    return 0 if record.get("status") == "succeeded" else 1


if __name__ == "__main__":
    sys.exit(main())
