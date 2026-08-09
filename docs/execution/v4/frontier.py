#!/usr/bin/env python3
"""Compute the runnable frontier from TASK_GRAPH.yaml.

The point of this script is that the frontier is DERIVED, not remembered. A
session that reads the graph and decides for itself what is next has
reintroduced the planner-in-the-model failure this directory exists to fix.

    python3 docs/execution/v4/frontier.py           # the frontier
    python3 docs/execution/v4/frontier.py --all     # every node, by status

A node is READY when every dependency is COMPLETE. Nodes are ranked by
priority (1 is highest), then by how many other nodes they unblock — a node
that parks eight descendants outranks a leaf of equal priority.
"""
from __future__ import annotations

import collections
import pathlib
import sys

import yaml

GRAPH = pathlib.Path(__file__).with_name("TASK_GRAPH.yaml")

TERMINAL = {"COMPLETE", "INVALIDATED", "BLOCKED_DATA", "BLOCKED_EXTERNAL",
            "BLOCKED_OWNER", "NOT_APPLICABLE"}
#: Only COMPLETE satisfies a dependency. A BLOCKED node is terminal, but it
#: did not deliver the thing its dependents needed, so it parks them.
SATISFIES = {"COMPLETE"}


def load(path=GRAPH):
    return yaml.safe_load(path.read_text(encoding="utf-8"))["tasks"]


def unblocks(tasks):
    """How many nodes each node parks, transitively."""
    children = collections.defaultdict(set)
    for task in tasks:
        for dep in task.get("dependencies") or ():
            children[dep].add(task["id"])
    reach, seen = {}, {}

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

    for task in tasks:
        reach[task["id"]] = len(walk(task["id"]))
    return reach


def frontier(tasks):
    done = {t["id"] for t in tasks if t["status"] in SATISFIES}
    out = []
    for task in tasks:
        if task["status"] in TERMINAL or task["status"] == "IN_PROGRESS":
            continue
        deps = task.get("dependencies") or ()
        if all(d in done for d in deps):
            out.append(task)
    return out


def main(argv):
    tasks = load()
    reach = unblocks(tasks)
    if "--all" in argv:
        by_status = collections.defaultdict(list)
        for task in tasks:
            by_status[task["status"]].append(task["id"])
        for status in sorted(by_status):
            print(f"{status:20s} {len(by_status[status]):3d}  "
                  f"{' '.join(sorted(by_status[status]))}")
        return 0

    ready = frontier(tasks)
    ready.sort(key=lambda t: (t.get("priority", 9), -reach[t["id"]], t["id"]))
    counts = collections.Counter(t["status"] for t in tasks)
    print(f"{len(tasks)} nodes  "
          + "  ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    print()
    if not ready:
        print("NO READY NODES. Check stop conditions in AGENT_PROTOCOL.md "
              "before concluding the program is finished.")
        return 0
    print("RUNNABLE FRONTIER (highest value first)")
    for task in ready:
        print(f"  p{task.get('priority', 9)}  {task['id']:<14} "
              f"unblocks {reach[task['id']]:>2}  {task['title']}")
    print()
    print(f"NEXT: {ready[0]['id']}  {ready[0]['title']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
