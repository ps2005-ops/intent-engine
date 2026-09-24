#!/usr/bin/env python3
"""Compute the runnable V5 frontier. Same engine as V4, different graph.

    python3 docs/execution/v5/frontier.py           # the frontier
    python3 docs/execution/v5/frontier.py --all     # every node, by status
    python3 docs/execution/v5/frontier.py --check   # integrity, exit 1 on drift
    python3 docs/execution/v5/frontier.py --debt    # live-verification debt

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

AND WHAT BATCH 2 ADDS: THE VERIFICATION AXIS
--------------------------------------------
Batch 1 finished with five capability-complete nodes and ZERO live-verified
ones, and the graph could not say so -- because `status` has one COMPLETE and
it was being asked to mean two different things: "dependents may build on this"
and "this runs in production". Those two came apart, and the graph reported the
first while every reader took the second.

So `verification` is a SECOND, ORTHOGONAL field:

    IMPLEMENTED           the code exists
    CAPABILITY_VERIFIED   proven by its own suite and its break proofs
    LIVE_VERIFIED         a real run in the real runtime produced its live
                          proof, and `live_evidence` names that run
    BLOCKED_DATA          the live proof is unreachable on current data, and
                          the measurement establishing that exists

`status: COMPLETE` keeps its old, narrow meaning -- the dependency edge is
satisfied, dependents may proceed -- because collapsing the two axes again in
the other direction would stall the entire graph behind a runtime that runs
twice a day.

THE DEBT IS THE POINT. `--debt` lists every COMPLETE node that is not
LIVE_VERIFIED, which is the number Batch 1 could not see. Capability velocity
and operationalization velocity are different measurements and only the second
one is the product.
"""
from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ENGINE = HERE.parent / "v4"

sys.path.insert(0, str(ENGINE))
import frontier as engine  # noqa: E402

#: Ordered weakest to strongest; the order is the ladder a node climbs.
IMPLEMENTED = "IMPLEMENTED"
CAPABILITY_VERIFIED = "CAPABILITY_VERIFIED"
LIVE_VERIFIED = "LIVE_VERIFIED"
BLOCKED_DATA = "BLOCKED_DATA"
VERIFICATION_STATES = (IMPLEMENTED, CAPABILITY_VERIFIED, LIVE_VERIFIED,
                       BLOCKED_DATA)


def _tasks():
    import yaml

    graph = yaml.safe_load((HERE / "TASK_GRAPH.yaml").read_text())
    return graph["tasks"]


def check_verification(tasks) -> list:
    """Every way the verification axis can be written dishonestly.

    Returns a list of problems; empty is the pass. The rules are deliberately
    few, and each one names something this program has actually done:

      1. a COMPLETE node with no verification -- the Batch 1 state, where
         COMPLETE was read as live by every reader including the report;
      2. a verification outside the vocabulary -- a status invented at the
         keyboard to avoid writing a smaller one;
      3. LIVE_VERIFIED with no `live_evidence` naming the run that produced it.
         A live claim that cannot name its run is prose, and this is the rule
         that would have caught a capability being written up as running in
         production while `grep synthetic_control steps.py` returned nothing.
    """
    problems = []
    for task in tasks:
        tid = task["id"]
        verification = task.get("verification")
        if task.get("status") == "COMPLETE" and not verification:
            problems.append(
                f"{tid}: COMPLETE with no `verification`; COMPLETE means the "
                f"dependency edge is satisfied and says nothing about whether "
                f"this has ever run")
        if verification and verification not in VERIFICATION_STATES:
            problems.append(
                f"{tid}: unknown verification {verification!r}; expected one "
                f"of {', '.join(VERIFICATION_STATES)}")
        if verification == LIVE_VERIFIED and not str(
                task.get("live_evidence") or "").strip():
            problems.append(
                f"{tid}: LIVE_VERIFIED with no `live_evidence`; a live claim "
                f"that cannot name the run that produced it is prose")
    return problems


def debt(tasks) -> list:
    """COMPLETE nodes that have never been proven in the real runtime."""
    return [t for t in tasks
            if t.get("status") == "COMPLETE"
            and t.get("verification") != LIVE_VERIFIED]


def _report_debt(tasks) -> int:
    rows = debt(tasks)
    complete = [t for t in tasks if t.get("status") == "COMPLETE"]
    live = [t for t in complete if t.get("verification") == LIVE_VERIFIED]
    print(f"COMPLETE {len(complete)}   LIVE_VERIFIED {len(live)}   "
          f"DEBT {len(rows)}")
    for task in rows:
        print(f"  {task['id']:<14} "
              f"{task.get('verification') or 'UNSTATED':<20} "
              f"{task.get('title', '')[:54]}")
    if not rows:
        print("  (none)")
    return 0


if __name__ == "__main__":
    argv = sys.argv[1:]
    if "--debt" in argv:
        sys.exit(_report_debt(_tasks()))
    code = engine.main(argv + ["--dir", str(HERE)])
    if "--check" in argv:
        problems = check_verification(_tasks())
        if problems:
            print("\nVERIFICATION AXIS:")
            for problem in problems:
                print(f"  {problem}")
            code = code or 1
        else:
            print("verification axis: ok")
    sys.exit(code)
