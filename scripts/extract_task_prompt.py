#!/usr/bin/env python
"""Extracts one task's full markdown block from ROADMAP.md (its `## T<id> —`
header through the line before the next `## ` header) -- this becomes the
core of the self-contained prompt nightly_agent.sh hands to `claude -p`.
Deliberately extracts the REAL, already-written text (title, status, size,
source, files in scope, definition of done) rather than reconstructing or
summarizing it, so the agent sees exactly what a human reviewing ROADMAP.md
would see -- no paraphrase-introduced drift between the spec and the prompt.

Usage: python scripts/extract_task_prompt.py <path-to-ROADMAP.md> <task-id>
"""

import re
import sys
from pathlib import Path

TASK_HEADER_RE = re.compile(r"^##\s+(T\d+)\s+—")


def extract_task_block(text: str, task_id: str) -> str:
    lines = text.splitlines()
    start = None
    end = len(lines)

    for i, line in enumerate(lines):
        match = TASK_HEADER_RE.match(line)
        if match:
            if start is not None:
                end = i
                break
            if match.group(1) == task_id:
                start = i

    if start is None:
        raise ValueError(f"Task {task_id!r} not found in ROADMAP.md")

    return "\n".join(lines[start:end]).strip()


def main():
    if len(sys.argv) != 3:
        print("Usage: extract_task_prompt.py <path-to-ROADMAP.md> <task-id>", file=sys.stderr)
        sys.exit(1)

    text = Path(sys.argv[1]).read_text()
    print(extract_task_block(text, sys.argv[2]))


if __name__ == "__main__":
    main()
