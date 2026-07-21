"""Growth CLI (T018) — reads and idempotent consumption only.

    PYTHONPATH=src python -m intent_engine.growth experiment-show <id>
    PYTHONPATH=src python -m intent_engine.growth experiment-history <id>
    PYTHONPATH=src python -m intent_engine.growth result <id>
    PYTHONPATH=src python -m intent_engine.growth funnel <id>
    PYTHONPATH=src python -m intent_engine.growth registration <id>
    PYTHONPATH=src python -m intent_engine.growth pending-reviews
    PYTHONPATH=src python -m intent_engine.growth consume [--events-dir events]
    [--namespace production|synthetic]

There is deliberately NO start, stop, approve, review, or rollout
command: every one of those is a human act performed through
GrowthService with an explicit human actor. There is no rollout API at
all, at any layer.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys

from intent_engine.growth.records import NAMESPACE_PRODUCTION, NAMESPACES
from intent_engine.growth.service import GrowthService


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="intent_engine.growth")
    ap.add_argument("--dir", default="data")
    ap.add_argument("--namespace", default=NAMESPACE_PRODUCTION,
                    choices=sorted(NAMESPACES))
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("experiment-show", "experiment-history", "result", "funnel",
                 "registration"):
        p = sub.add_parser(name)
        p.add_argument("experiment_id")
    sub.add_parser("pending-reviews")
    c = sub.add_parser("consume")
    c.add_argument("--events-dir", default="events")

    args = ap.parse_args(argv)
    svc = GrowthService(args.dir, args.namespace)

    if args.cmd == "experiment-show":
        print(json.dumps(dataclasses.asdict(svc.get_state(args.experiment_id)),
                         sort_keys=True, default=str))
    elif args.cmd == "experiment-history":
        for row in svc.get_history(args.experiment_id):
            print(row.to_json())
    elif args.cmd == "result":
        print(json.dumps(svc.get_result(args.experiment_id), sort_keys=True,
                         default=str))
    elif args.cmd == "funnel":
        print(json.dumps(svc.get_funnel(args.experiment_id), sort_keys=True))
    elif args.cmd == "registration":
        print(json.dumps(svc.get_registration(args.experiment_id),
                         sort_keys=True, default=str))
    elif args.cmd == "pending-reviews":
        print(json.dumps(svc.list_pending_reviews(), sort_keys=True))
    else:
        from intent_engine.events import CompanyEventBus, drain
        from intent_engine.growth.consumer import GrowthCompanyEventConsumer
        bus = CompanyEventBus(args.events_dir)
        consumer = GrowthCompanyEventConsumer(svc)
        rep = drain(bus, consumer)
        out = dict(rep.__dict__)
        out.update(observed=consumer.observed, skipped=consumer.skipped,
                   consumer=consumer.consumer_name)
        print(json.dumps(out, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
