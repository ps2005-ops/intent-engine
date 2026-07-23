"""V2.0 Growth Studio CLI — reads and fixture only. There is no publish,
send, post, or deploy command, deliberately.

    PYTHONPATH=src python -m intent_engine.growth_studio fixture
    PYTHONPATH=src python -m intent_engine.growth_studio portfolio [--path P]
    PYTHONPATH=src python -m intent_engine.growth_studio briefing DATE [--path P]
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile

from intent_engine.growth_studio.store import DEFAULT_STUDIO_PATH, StudioStore


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="intent_engine.growth_studio")
    ap.add_argument("--path", default=str(DEFAULT_STUDIO_PATH))
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("fixture")
    sub.add_parser("portfolio")
    br = sub.add_parser("briefing")
    br.add_argument("date")

    args = ap.parse_args(argv)

    if args.cmd == "fixture":
        from intent_engine.growth_studio.fixtures import build_fixture
        built = build_fixture(tempfile.mktemp(suffix=".jsonl"))
        summary = dict(built["summary"])
        summary.pop("service", None)
        print(json.dumps(summary, sort_keys=True, default=str))
        return 0
    store = StudioStore(args.path)
    if args.cmd == "portfolio":
        print(json.dumps(store.items(), sort_keys=True, default=str))
    elif args.cmd == "briefing":
        briefings = {k: v for k, v in store.briefings().items()
                     if v.get("as_of_date") == args.date}
        print(json.dumps(briefings, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
