#!/usr/bin/env python
"""Parses ROADMAP.md and prints the task_id of the lowest-priority RUNNABLE
task, or nothing (empty stdout) if none exists. Used by nightly_agent.sh --
kept as a separate, testable script rather than inline bash regex, matching
this project's own convention (real Python for anything non-trivial, not
ad-hoc shell parsing).

A task is only picked if it has ALL of: a `## T<id> —` header, a
`- **Status**: RUNNABLE` line, and a `- **Priority**: <int>` line. A
malformed entry (missing either field) is silently excluded from
consideration rather than crashing the nightly run over a documentation
formatting slip -- but see test_pick_next_task.py for the corresponding
"never silently picks a NEEDS-SPEC task" guarantee.

Usage: python scripts/pick_next_task.py <path-to-ROADMAP.md>
"""

import re
import sys
from pathlib import Path
from typing import List, NamedTuple, Optional

TASK_HEADER_RE = re.compile(r"^##\s+(T\d+)\s+—")
STATUS_RE = re.compile(r"^-\s+\*\*Status\*\*:\s*(\S+)")
PRIORITY_RE = re.compile(r"^-\s+\*\*Priority\*\*:\s*(\d+)")


class Task(NamedTuple):
    task_id: str
    status: str
    priority: Optional[int]


def parse_roadmap(text: str) -> List[Task]:
    tasks = []
    current_id = None
    current_status = None
    current_priority = None

    def _flush():
        if current_id and current_status and current_priority is not None:
            tasks.append(Task(current_id, current_status, current_priority))

    for line in text.splitlines():
        header_match = TASK_HEADER_RE.match(line)
        if header_match:
            _flush()
            current_id = header_match.group(1)
            current_status = None
            current_priority = None
            continue

        if current_id is None:
            continue

        status_match = STATUS_RE.match(line)
        if status_match:
            current_status = status_match.group(1)
            continue

        priority_match = PRIORITY_RE.match(line)
        if priority_match:
            current_priority = int(priority_match.group(1))
            continue

    _flush()
    return tasks


def pick_next_runnable(tasks: List[Task]) -> Optional[str]:
    runnable = [t for t in tasks if t.status == "RUNNABLE"]
    if not runnable:
        return None
    return min(runnable, key=lambda t: t.priority).task_id


def main():
    if len(sys.argv) != 2:
        print("Usage: pick_next_task.py <path-to-ROADMAP.md>", file=sys.stderr)
        sys.exit(1)

    text = Path(sys.argv[1]).read_text()
    tasks = parse_roadmap(text)
    picked = pick_next_runnable(tasks)
    if picked:
        print(picked)


if __name__ == "__main__":
    main()
