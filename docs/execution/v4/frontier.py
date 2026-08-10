#!/usr/bin/env python3
"""Compute the runnable frontier from TASK_GRAPH.yaml.

The frontier is DERIVED, not remembered. A session that reads the graph and
decides for itself what is next has reintroduced the planner-in-the-model
failure this directory exists to fix.

    python3 docs/execution/v4/frontier.py           # the frontier
    python3 docs/execution/v4/frontier.py --all     # every node, by status
    python3 docs/execution/v4/frontier.py --check   # drift check, exit 1 on drift

WHAT CHANGED, AND WHY IT HAD TO
-------------------------------
The first version ranked on dependencies alone. It promoted three policy nodes
to READY whose data gate stood at 2 against a required 100, and a human had to
notice and set them back to BLOCKED_DATA by hand. A planner that needs manual
correction every session is not a planner; it is a document that happens to be
executable.

Now a node is runnable only when its dependencies are COMPLETE **and** every
data gate it declares is satisfied by a real measurement. The gate mechanism is
generic — it reads `minimum_data` as {metric: required} and compares against
METRICS.json. There are no task IDs in this file.

DERIVED STATE IS NOT STORED
---------------------------
`status:` in TASK_GRAPH is authoritative only for states a measurement cannot
establish: COMPLETE, INVALIDATED, NOT_APPLICABLE, BLOCKED_OWNER,
BLOCKED_EXTERNAL, NEEDS_REPAIR, IN_PROGRESS. Everything else — READY,
WAITING_DEPENDENCY, BLOCKED_DATA — is COMPUTED here and never written back.
That removes the whole class of drift where TASK_GRAPH says READY while
BLOCKERS.yaml says blocked: there is now one place each fact lives.

A MISSING MEASUREMENT BLOCKS
----------------------------
An unmeasurable gate yields BLOCKED_DATA with current=None. "We looked and
there are none" and "we could not look" are different claims, and only the
first is evidence. Neither makes a node runnable.
"""
from __future__ import annotations

import collections
import pathlib
import sys

import yaml

HERE = pathlib.Path(__file__).resolve().parent
GRAPH = HERE / "TASK_GRAPH.yaml"

#: Declared states this file will not overrule. Everything else is derived.
DECLARED = {"COMPLETE", "INVALIDATED", "NOT_APPLICABLE", "BLOCKED_OWNER",
            "BLOCKED_EXTERNAL", "NEEDS_REPAIR", "IN_PROGRESS"}
#: Only COMPLETE satisfies a dependency. A blocked node is terminal for itself
#: but it did not deliver what its dependents needed, so it still parks them.
SATISFIES = {"COMPLETE"}
TERMINAL = {"COMPLETE", "INVALIDATED", "BLOCKED_DATA", "BLOCKED_EXTERNAL",
            "BLOCKED_OWNER", "NOT_APPLICABLE"}


def load_graph(path=GRAPH):
    return yaml.safe_load(path.read_text(encoding="utf-8"))["tasks"]


def load_metrics():
    sys.path.insert(0, str(HERE))
    import metrics as M

    return M.load().get("metrics", {}) or {}


def gate_report(task, measured):
    """Evaluate one node's data gates. Returns (satisfied, [detail, ...])."""
    required = task.get("minimum_data")
    if not required or not isinstance(required, dict):
        return True, []
    details, ok = [], True
    for metric, need in sorted(required.items()):
        current = measured.get(metric)
        satisfied = current is not None and current >= need
        ok = ok and satisfied
        details.append({"metric": metric, "current": current,
                        "required": need, "satisfied": satisfied})
    return ok, details


def effective(tasks, measured):
    """Derive each node's status. Declared terminal states are respected."""
    declared = {t["id"]: t.get("status", "") for t in tasks}
    done = {i for i, s in declared.items() if s in SATISFIES}
    out = {}
    for task in tasks:
        tid = task["id"]
        if declared[tid] in DECLARED:
            out[tid] = (declared[tid], [])
            continue
        deps = task.get("dependencies") or ()
        if not all(d in done for d in deps):
            out[tid] = ("WAITING_DEPENDENCY", [])
            continue
        ok, details = gate_report(task, measured)
        out[tid] = ("READY" if ok else "BLOCKED_DATA", details)
    return out


def unblocks(tasks):
    children = collections.defaultdict(set)
    for task in tasks:
        for dep in task.get("dependencies") or ():
            children[dep].add(task["id"])
    seen = {}

    def walk(node):
        if node in seen:
            return seen[node]
        seen[node] = set()
        out = set()
        for child in children.get(node, ()):
            out.add(child)
            out |= walk(child)
        seen[node] = out
        return out

    return {t["id"]: len(walk(t["id"])) for t in tasks}


def main(argv):
    tasks = load_graph()
    measured = load_metrics()
    status = effective(tasks, measured)
    reach = unblocks(tasks)
    by_id = {t["id"]: t for t in tasks}
    counts = collections.Counter(s for s, _ in status.values())

    # A DUPLICATE ID IS NOT A COSMETIC PROBLEM. `by_id` keeps the last entry,
    # so a node whose id another node reused disappears from the frontier
    # entirely — it is never scheduled, never blocked, never reported. That
    # happened to H-CEO-002 (CEO challenge mode) when a later session gave the
    # thesis-history transport the same id: the challenge-mode node was
    # invisible for the whole of its life. This runs on every invocation, not
    # only under --check, because a planner that silently loses a node is
    # worse than one that refuses to start.
    seen = collections.Counter(t["id"] for t in tasks)
    duplicates = sorted(i for i, n in seen.items() if n > 1)
    if duplicates:
        print("DUPLICATE TASK IDS — each of these hides an earlier node "
              "completely; the frontier cannot see it:")
        for tid in duplicates:
            print(f"  {tid} appears {seen[tid]} times")
        return 1

    if "--check" in argv:
        # DERIVED is the marker meaning "this node's state is computed, and is
        # deliberately not stored". Drift is a node whose graph entry names a
        # CONCRETE derivable state — READY, WAITING_DEPENDENCY, BLOCKED_DATA —
        # because that is a fact written in two places, which is how
        # TASK_GRAPH and BLOCKERS came to disagree.
        drift = [(tid, by_id[tid].get("status"), got)
                 for tid, (got, _) in status.items()
                 if by_id[tid].get("status") not in DECLARED
                 and by_id[tid].get("status") != "DERIVED"]
        if drift:
            print("STATUS DRIFT — TASK_GRAPH declares a derivable state that "
                  "does not match the measurement:")
            for tid, was, now in drift:
                print(f"  {tid:<14} declared {was:<20} derived {now}")
            print("\nFix: remove the declared status from TASK_GRAPH for these "
                  "nodes. Derived states must not be stored.")
            return 1
        print(f"no drift; {len(tasks)} nodes")
        return 0

    if "--all" in argv:
        grouped = collections.defaultdict(list)
        for tid, (got, _) in status.items():
            grouped[got].append(tid)
        for state in sorted(grouped):
            print(f"{state:20s} {len(grouped[state]):3d}  "
                  f"{' '.join(sorted(grouped[state]))}")
        return 0

    ready = [by_id[t] for t, (s, _) in status.items() if s == "READY"]
    ready.sort(key=lambda t: (t.get("priority", 9), -reach[t["id"]], t["id"]))
    print(f"{len(tasks)} nodes  "
          + "  ".join(f"{k}={v}" for k, v in sorted(counts.items())))

    blocked = [(t, d) for t, (s, d) in status.items()
               if s == "BLOCKED_DATA" and d]
    if blocked:
        print("\nBLOCKED_DATA (gate measured, not asserted)")
        for tid, details in sorted(blocked):
            for row in details:
                if not row["satisfied"]:
                    cur = "UNMEASURED" if row["current"] is None \
                        else row["current"]
                    print(f"  {tid:<14} {row['metric']:<30} "
                          f"{cur} / {row['required']}")
    print()
    if not ready:
        print("NO READY NODES. Check the stop conditions in "
              "AGENT_PROTOCOL.md before concluding the program is finished.")
        return 0
    print("RUNNABLE FRONTIER (highest value first)")
    for task in ready:
        print(f"  p{task.get('priority', 9)}  {task['id']:<14} "
              f"unblocks {reach[task['id']]:>2}  {task['title']}")
    print(f"\nNEXT: {ready[0]['id']}  {ready[0]['title']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
