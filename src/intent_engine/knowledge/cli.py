"""Knowledge CLI (T016).

    PYTHONPATH=src python -m intent_engine.knowledge feedback-show <id>
    PYTHONPATH=src python -m intent_engine.knowledge insights-pending
    PYTHONPATH=src python -m intent_engine.knowledge knowledge-list
    PYTHONPATH=src python -m intent_engine.knowledge mechanisms-pending
    PYTHONPATH=src python -m intent_engine.knowledge consume [--events-dir events]
    PYTHONPATH=src python -m intent_engine.knowledge replay --from-offset 0

Reads are safe; consume/replay are idempotent; validation/promotion are
NOT exposed here without an explicit human actor id (use the service).
"""
from __future__ import annotations

import argparse
import json
import sys

from intent_engine.knowledge.consumer import KnowledgeCompanyEventConsumer
from intent_engine.knowledge.service import KnowledgeService


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="intent_engine.knowledge")
    ap.add_argument("--feedback-path", default="data/feedback.jsonl")
    ap.add_argument("--knowledge-path", default="knowledge/knowledge.jsonl")
    sub = ap.add_subparsers(dest="cmd", required=True)
    fs = sub.add_parser("feedback-show")
    fs.add_argument("feedback_id")
    sub.add_parser("insights-pending")
    kl = sub.add_parser("knowledge-list")
    kl.add_argument("--category", default=None)
    mp = sub.add_parser("mechanisms-pending")
    c = sub.add_parser("consume")
    c.add_argument("--events-dir", default="events")
    r = sub.add_parser("replay")
    r.add_argument("--events-dir", default="events")
    r.add_argument("--from-offset", type=int, default=0)
    r.add_argument("--dry-run", action="store_true")

    args = ap.parse_args(argv)
    svc = KnowledgeService(args.feedback_path, args.knowledge_path)

    if args.cmd == "feedback-show":
        for row in svc.get_feedback(args.feedback_id):
            print(row.to_json())
    elif args.cmd == "insights-pending":
        print(json.dumps(svc.list_pending_validations()))
    elif args.cmd == "knowledge-list":
        print(json.dumps(svc.search_knowledge(category=args.category),
                         sort_keys=True, default=str))
    elif args.cmd == "mechanisms-pending":
        print(json.dumps(svc.list_mechanism_proposals(status="proposed"),
                         sort_keys=True, default=str))
    else:
        from intent_engine.events import CompanyEventBus, drain, replay
        bus = CompanyEventBus(args.events_dir)
        consumer = KnowledgeCompanyEventConsumer(svc)
        rep = (drain(bus, consumer) if args.cmd == "consume"
               else replay(bus, consumer, from_offset=args.from_offset,
                           dry_run=args.dry_run))
        print(json.dumps(rep.__dict__, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
