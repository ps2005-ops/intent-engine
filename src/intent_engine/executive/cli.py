"""Executive CLI (T021) — reads and idempotent consumption only.

    PYTHONPATH=src python -m intent_engine.executive queue [--as-of ISO]
    PYTHONPATH=src python -m intent_engine.executive dashboard [--as-of ISO]
    PYTHONPATH=src python -m intent_engine.executive candidate-show <id>
    PYTHONPATH=src python -m intent_engine.executive package-show <id> [--version N]
    PYTHONPATH=src python -m intent_engine.executive lineage <package_id>
    PYTHONPATH=src python -m intent_engine.executive trace <package_id>
    PYTHONPATH=src python -m intent_engine.executive conflicts <candidate_id>
    PYTHONPATH=src python -m intent_engine.executive review-queue
    PYTHONPATH=src python -m intent_engine.executive snapshot <id> [--json]
    PYTHONPATH=src python -m intent_engine.executive consume

There is no accept command, no apply command, and no schedule command:
review is a founder act performed through ExecutiveService, and this
subsystem executes nothing.
"""
from __future__ import annotations

import argparse
import json
import sys

from intent_engine.executive.service import ExecutiveService
from intent_engine.executive.store import DEFAULT_EXECUTIVE_PATH

_DEFAULT_AS_OF = "9999-12-31T00:00:00+00:00"


def _dump(value) -> None:
    print(json.dumps(value, sort_keys=True, default=str))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="intent_engine.executive")
    ap.add_argument("--path", default=str(DEFAULT_EXECUTIVE_PATH))
    ap.add_argument("--as-of", default=_DEFAULT_AS_OF)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("queue")
    sub.add_parser("dashboard")
    sub.add_parser("review-queue")
    for name in ("candidate-show", "lineage", "trace", "conflicts"):
        p = sub.add_parser(name)
        p.add_argument("subject_id")
    pk = sub.add_parser("package-show")
    pk.add_argument("package_id")
    pk.add_argument("--version", type=int, default=None)
    sn = sub.add_parser("snapshot")
    sn.add_argument("subject_id")
    sn.add_argument("--scope", default="portfolio",
                    choices=("portfolio", "package"))
    sn.add_argument("--json", action="store_true")
    cm = sub.add_parser("consume")
    cm.add_argument("--events-dir", default="events")

    args = ap.parse_args(argv)
    svc = ExecutiveService(args.path)

    if args.cmd == "queue":
        _dump(svc.triage_queues(as_of=args.as_of))
    elif args.cmd == "dashboard":
        _dump(svc.health_dashboard(as_of=args.as_of))
    elif args.cmd == "candidate-show":
        index = svc.get_index()
        candidate = index.candidates.get(args.subject_id)
        if candidate is None:
            print(f"no such candidate: {args.subject_id}", file=sys.stderr)
            return 1
        _dump({**candidate,
               "conflicts": index.conflicts_for(args.subject_id),
               "open_debt": [i for i in index.debt.get(args.subject_id, [])
                             if not i["cleared"]]})
    elif args.cmd == "package-show":
        _dump(svc.get_package(args.package_id, args.version))
    elif args.cmd == "lineage":
        _dump(svc.lineage(args.subject_id))
    elif args.cmd == "trace":
        _dump(svc.trace(args.subject_id))
    elif args.cmd == "conflicts":
        _dump(svc.get_index().conflicts_for(args.subject_id))
    elif args.cmd == "review-queue":
        _dump(svc.list_review_queue())
    elif args.cmd == "snapshot":
        from intent_engine.executive.snapshots import capture_snapshot
        snapshot = capture_snapshot(svc, args.subject_id, as_of=args.as_of,
                                    scope=args.scope)
        _dump(snapshot) if args.json else _dump(
            {k: v for k, v in snapshot.items()
             if k in ("snapshot_id", "as_of", "computed_at", "versions",
                      "source_high_watermarks")})
    else:
        from intent_engine.events import CompanyEventBus, drain
        from intent_engine.executive.consumer import (
            ExecutiveCompanyEventConsumer,
        )
        bus = CompanyEventBus(args.events_dir)
        consumer = ExecutiveCompanyEventConsumer(svc)
        report = drain(bus, consumer)
        out = dict(report.__dict__)
        out.update(candidates=consumer.candidates, skipped=consumer.skipped)
        _dump(out)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
