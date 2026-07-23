"""Personal AI Workspace CLI (T023) — reads only, with a safe mode.

    PYTHONPATH=src python -m intent_engine.personal brief [--as-of ISO]
    PYTHONPATH=src python -m intent_engine.personal report <profile>
    PYTHONPATH=src python -m intent_engine.personal ask "<question>"
    PYTHONPATH=src python -m intent_engine.personal memory [--safe]
    PYTHONPATH=src python -m intent_engine.personal capabilities

The workspace holds no authority: there is no send, publish, execute, or
schedule command. `--safe` omits founder-authored private notes from
diagnostic output.
"""
from __future__ import annotations

import argparse
import json
import sys

from intent_engine.personal.records import FIELD_FOUNDER_AUTHORED
from intent_engine.personal.router import supported_capabilities
from intent_engine.personal.service import PersonalService
from intent_engine.personal.store import DEFAULT_PERSONAL_PATH

_DEFAULT_AS_OF = "9999-12-31T00:00:00+00:00"


def _dump(value) -> None:
    print(json.dumps(value, sort_keys=True, default=str))


def _redact(memory: dict) -> dict:
    """Safe mode: drop founder-authored free text (notes/goals prose),
    keeping references and structure."""
    redacted = json.loads(json.dumps(memory, default=str))
    for pins in redacted.get("pins", {}).values():
        if pins.get("note"):
            pins["note"] = "[omitted in safe mode]"
    for goal in redacted.get("goals", {}).values():
        if goal.get("goal"):
            goal["goal"] = "[omitted in safe mode]"
    return redacted


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="intent_engine.personal")
    ap.add_argument("--path", default=str(DEFAULT_PERSONAL_PATH))
    ap.add_argument("--as-of", default=_DEFAULT_AS_OF)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("brief")
    rp = sub.add_parser("report")
    rp.add_argument("profile")
    aq = sub.add_parser("ask")
    aq.add_argument("question")
    mem = sub.add_parser("memory")
    mem.add_argument("--safe", action="store_true")
    sub.add_parser("capabilities")

    args = ap.parse_args(argv)
    svc = PersonalService(args.path)

    if args.cmd == "brief":
        _dump(svc.morning_brief(as_of=args.as_of, record=False))
    elif args.cmd == "report":
        _dump(svc.report(args.profile, as_of=args.as_of, record=False))
    elif args.cmd == "ask":
        # a read: build the claim set + deterministic answer, no turn recorded
        from intent_engine.personal.conversation import answer
        _dump(answer(args.question, adapters=svc._adapters(args.as_of)))
    elif args.cmd == "memory":
        memory = svc.durable_memory()
        _dump(_redact(memory) if args.safe else memory)
    elif args.cmd == "capabilities":
        _dump({"supported": supported_capabilities()})
    else:                                                    # pragma: no cover
        ap.error(f"unknown command {args.cmd!r}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
