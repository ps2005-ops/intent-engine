#!/usr/bin/env python3
"""Compute the runnable V5 frontier. Same engine as V4, different graph.

    python3 docs/execution/v5/frontier.py           # the frontier
    python3 docs/execution/v5/frontier.py --all     # every node, by status
    python3 docs/execution/v5/frontier.py --check   # integrity, exit 1 on drift

WHY A SHIM AND NOT A COPY
-------------------------
Two copies of a planner is how the planner and the plan came apart the first
time. The engine lives in docs/execution/v4/frontier.py and takes `--dir`; a
program is a directory holding TASK_GRAPH.yaml, METRICS.json and metrics.py.
Fixes to the engine reach both programs, and the V5 graph gets the duplicate-id
check, the duplicate-key check and the gate arithmetic without inheriting a
second implementation of any of them.

WHAT V5 ADDS TO --check
-----------------------
The V5 graph sets `requires_vertical: true`, so a node must name its producer,
persistence, reload, consumer, surface, telemetry, failure states, live proof,
adversarial proof and mutation target before it can pass integrity. That is the
mechanical form of the rule the V4 protocol stated in prose while the program
shipped four capabilities with no production callers.
"""
from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ENGINE = HERE.parent / "v4"

sys.path.insert(0, str(ENGINE))
import frontier as engine  # noqa: E402


if __name__ == "__main__":
    sys.exit(engine.main(sys.argv[1:] + ["--dir", str(HERE)]))
