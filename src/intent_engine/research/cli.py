"""Research CLI (T019) — reads and idempotent consumption only.

    PYTHONPATH=src python -m intent_engine.research request-show <id>
    PYTHONPATH=src python -m intent_engine.research plan-show <id> [--version N]
    PYTHONPATH=src python -m intent_engine.research sources <id> [--as-of ISO]
    PYTHONPATH=src python -m intent_engine.research package <id> <package_id>
    PYTHONPATH=src python -m intent_engine.research contradictions <id> <package_id>
    PYTHONPATH=src python -m intent_engine.research lineage <id> <evidence_id>
    PYTHONPATH=src python -m intent_engine.research pending-reviews
    PYTHONPATH=src python -m intent_engine.research consume

No approve command, no promote command, and no fetch/crawl command:
plan approval and review are human acts performed through
ResearchService, and acquisition is never autonomous.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys

from intent_engine.research.service import ResearchService
from intent_engine.research.store import DEFAULT_RESEARCH_PATH

_DEFAULT_AS_OF = "9999-12-31T00:00:00+00:00"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="intent_engine.research")
    ap.add_argument("--path", default=str(DEFAULT_RESEARCH_PATH))
    ap.add_argument("--as-of", default=_DEFAULT_AS_OF)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("request-show", "sources"):
        p = sub.add_parser(name)
        p.add_argument("request_id")
    ps = sub.add_parser("plan-show")
    ps.add_argument("request_id")
    ps.add_argument("--version", type=int, default=None)
    for name in ("package", "contradictions"):
        p = sub.add_parser(name)
        p.add_argument("request_id")
        p.add_argument("package_id")
    ln = sub.add_parser("lineage")
    ln.add_argument("request_id")
    ln.add_argument("evidence_id")
    sub.add_parser("pending-reviews")
    cm = sub.add_parser("consume")
    cm.add_argument("--events-dir", default="events")

    args = ap.parse_args(argv)
    svc = ResearchService(args.path)

    if args.cmd == "request-show":
        print(json.dumps(dataclasses.asdict(svc.get_state(args.request_id)),
                         sort_keys=True, default=str))
    elif args.cmd == "plan-show":
        print(json.dumps(svc.get_plan(args.request_id, args.version),
                         sort_keys=True, default=str))
    elif args.cmd == "sources":
        index = svc.get_index(args.request_id, as_of=args.as_of)
        print(json.dumps(
            {sid: {"class": s.get("source_class"),
                   "quality": s.get("source_quality"),
                   "freshness": s.get("freshness", {}).get("freshness"),
                   "independence_group": s.get("independence_group")}
             for sid, s in sorted(index.sources.items())},
            sort_keys=True, default=str))
    elif args.cmd == "package":
        print(json.dumps(svc.get_package(args.request_id, args.package_id),
                         sort_keys=True, default=str))
    elif args.cmd == "contradictions":
        package = svc.get_package(args.request_id, args.package_id)
        print(json.dumps({"contradictions": package["contradictions"],
                          "coverage": package["coverage"]["totals"],
                          "research_debt": package["research_debt"]},
                         sort_keys=True, default=str))
    elif args.cmd == "lineage":
        print(json.dumps(svc.lineage(args.request_id, args.evidence_id,
                                     as_of=args.as_of),
                         sort_keys=True, default=str))
    elif args.cmd == "pending-reviews":
        print(json.dumps(svc.list_pending_reviews(), sort_keys=True))
    else:
        from intent_engine.events import CompanyEventBus, drain
        from intent_engine.research.consumer import ResearchCompanyEventConsumer
        bus = CompanyEventBus(args.events_dir)
        consumer = ResearchCompanyEventConsumer(svc)
        rep = drain(bus, consumer)
        out = dict(rep.__dict__)
        out.update(suggested=consumer.suggested, skipped=consumer.skipped)
        print(json.dumps(out, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
