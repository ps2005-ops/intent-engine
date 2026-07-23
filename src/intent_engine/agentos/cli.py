"""AgentOS CLI (T022) — reads only.

    PYTHONPATH=src python -m intent_engine.agentos registry
    PYTHONPATH=src python -m intent_engine.agentos permissions [<agent>]
    PYTHONPATH=src python -m intent_engine.agentos telemetry <agent> [--path P]
    PYTHONPATH=src python -m intent_engine.agentos budget <agent> [--path P]

The kernel is infrastructure, not an agent: there is no run, no execute,
no schedule command. Every subcommand is a read.
"""
from __future__ import annotations

import argparse
import json
import sys

from intent_engine.agentos.budgeting import model_budget
from intent_engine.agentos.registry import (
    get_agent, get_permissions, list_agents,
)
from intent_engine.agentos.telemetry import store_telemetry

_STORES = {
    "research": ("intent_engine.research.store", "ResearchStore"),
    "product": ("intent_engine.product.store", "ProductStore"),
    "executive": ("intent_engine.executive.store", "ExecutiveStore"),
}


def _dump(value) -> None:
    print(json.dumps(value, sort_keys=True, default=str))


def _open_store(agent: str, path: str | None):
    import importlib
    module_name, cls_name = _STORES[agent]
    cls = getattr(importlib.import_module(module_name), cls_name)
    return cls(path) if path else cls()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="intent_engine.agentos")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("registry")
    pm = sub.add_parser("permissions")
    pm.add_argument("agent", nargs="?", default=None)
    for name in ("telemetry", "budget"):
        p = sub.add_parser(name)
        p.add_argument("agent", choices=sorted(_STORES))
        p.add_argument("--path", default=None)

    args = ap.parse_args(argv)

    if args.cmd == "registry":
        _dump(list_agents())
    elif args.cmd == "permissions":
        if args.agent:
            _dump(get_permissions(args.agent).as_dict())
        else:
            _dump({name: get_permissions(name).as_dict()
                   for name in sorted(_STORES)})
    elif args.cmd == "telemetry":
        _dump({"agent": args.agent,
               **store_telemetry(_open_store(args.agent, args.path))})
    elif args.cmd == "budget":
        _dump({"agent": args.agent,
               **model_budget(_open_store(args.agent, args.path))})
    else:                                                    # pragma: no cover
        ap.error(f"unknown command {args.cmd!r}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
