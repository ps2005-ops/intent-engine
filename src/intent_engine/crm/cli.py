"""Operator CLI for the CRM (T014).

    PYTHONPATH=src python -m intent_engine.crm show <entity-or-ref>
    PYTHONPATH=src python -m intent_engine.crm history <entity-or-ref>
    PYTHONPATH=src python -m intent_engine.crm health <entity-or-ref>
    PYTHONPATH=src python -m intent_engine.crm conversion <entity-or-ref>
    PYTHONPATH=src python -m intent_engine.crm consume [--events-dir events]
    PYTHONPATH=src python -m intent_engine.crm replay --from-offset 0

Reads are safe; consume/replay use the T013 drain (checkpointed,
idempotent); nothing sends anything, and there is no destructive reset.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys

from intent_engine.crm.consumer import CRMCompanyEventConsumer
from intent_engine.crm.service import DEFAULT_CRM_PATH, CRMService


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="intent_engine.crm")
    ap.add_argument("--crm-path", default=str(DEFAULT_CRM_PATH))
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("show", "history", "health", "conversion"):
        p = sub.add_parser(name)
        p.add_argument("entity")
    c = sub.add_parser("consume", help="drain new company events into the CRM")
    c.add_argument("--events-dir", default="events")
    r = sub.add_parser("replay", help="re-deliver company events (idempotent)")
    r.add_argument("--events-dir", default="events")
    r.add_argument("--from-offset", type=int, default=0)
    r.add_argument("--dry-run", action="store_true")

    args = ap.parse_args(argv)
    crm = CRMService(args.crm_path)

    if args.cmd in ("show", "history", "health", "conversion"):
        entity_id = crm.get_entity(args.entity)
        if entity_id is None:
            raise SystemExit(f"no CRM entity matches {args.entity!r}")
        if args.cmd == "show":
            print(json.dumps(dataclasses.asdict(
                crm.get_current_state(entity_id)), sort_keys=True))
        elif args.cmd == "history":
            for ev in crm.get_history(entity_id):
                print(ev.to_json())
        elif args.cmd == "health":
            print(json.dumps(crm.get_health(entity_id), sort_keys=True))
        else:
            print(json.dumps(crm.get_conversion_signal(entity_id),
                             sort_keys=True))
        return 0

    from intent_engine.events import CompanyEventBus, drain, replay
    bus = CompanyEventBus(args.events_dir)
    consumer = CRMCompanyEventConsumer(crm)
    if args.cmd == "consume":
        rep = drain(bus, consumer)
    else:
        rep = replay(bus, consumer, from_offset=args.from_offset,
                     dry_run=args.dry_run)
    out = dict(rep.__dict__)
    out["skipped_no_identity"] = consumer.skipped_no_identity
    print(json.dumps(out, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
