"""Operator CLI for the company event log (T013).

    python -m intent_engine.events drain --consumer log [--dry-run]
    python -m intent_engine.events replay --consumer log --from-offset 0 \
        [--to-offset N] [--dry-run] [--rewind]
    python -m intent_engine.events dead-letters
    python -m intent_engine.events redrive --consumer log --event-id <ULID>

Default behavior respects checkpoints; rewinding requires the explicit
--rewind flag. Nothing here is destructive: the log, the dead-letter file,
and redrive outcomes are all append-only.
"""
from __future__ import annotations

import argparse
import json
import sys

from intent_engine.events.consumer import drain, redrive, replay
from intent_engine.events.publisher import DEFAULT_EVENTS_DIR, CompanyEventBus


class LogConsumer:
    """The one built-in consumer: prints event ids/types. Real business
    consumers (CRM, analytics, knowledge) arrive in their own sessions."""
    consumer_name = "log"

    def handles(self, event_type: str) -> bool:
        return True

    def process(self, event) -> None:
        print(f"{event.event_id}  {event.event_type}  "
              f"subject={event.subject_type}:{event.subject_id}")


CONSUMERS = {"log": LogConsumer}


def _consumer(name: str):
    if name not in CONSUMERS:
        raise SystemExit(f"unknown consumer {name!r}; known: "
                         f"{sorted(CONSUMERS)}")
    return CONSUMERS[name]()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="intent_engine.events")
    ap.add_argument("--dir", default=str(DEFAULT_EVENTS_DIR))
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("drain", help="deliver new events to a consumer")
    d.add_argument("--consumer", required=True)
    d.add_argument("--dry-run", action="store_true")

    r = sub.add_parser("replay", help="re-deliver existing events (never republishes)")
    r.add_argument("--consumer", required=True)
    r.add_argument("--from-offset", type=int, default=0)
    r.add_argument("--to-offset", type=int, default=None)
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--rewind", action="store_true",
                   help="EXPLICITLY move the consumer checkpoint back to "
                        "--from-offset, then drain")

    sub.add_parser("dead-letters", help="list dead-letter entries")

    rd = sub.add_parser("redrive", help="explicitly re-deliver one dead-lettered event")
    rd.add_argument("--consumer", required=True)
    rd.add_argument("--event-id", required=True)

    args = ap.parse_args(argv)
    bus = CompanyEventBus(args.dir)

    if args.cmd == "drain":
        rep = drain(bus, _consumer(args.consumer), dry_run=args.dry_run)
        print(json.dumps(rep.__dict__, default=str))
    elif args.cmd == "replay":
        rep = replay(bus, _consumer(args.consumer),
                     from_offset=args.from_offset, to_offset=args.to_offset,
                     dry_run=args.dry_run, rewind_checkpoint=args.rewind)
        print(json.dumps(rep.__dict__, default=str))
    elif args.cmd == "dead-letters":
        for entry in bus.store.read_dead_letters():
            print(json.dumps(entry, sort_keys=True))
    elif args.cmd == "redrive":
        print(redrive(bus, _consumer(args.consumer), args.event_id))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
