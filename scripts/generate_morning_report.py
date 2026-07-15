#!/usr/bin/env python
"""Regenerates MORNING_REPORT.md from one nightly_agent.sh run's real,
collected data -- never fabricated. Overwrites the file each run (the report
describes last night, not an accumulating log; run history lives in
logs/*.json for anyone who wants the full trail).

Usage (called from nightly_agent.sh, not typically by hand):
  --no-task                          Nothing RUNNABLE was found.
  --task-id / --branch / --result-json / --baseline-tests / --final-tests /
  --diff-stats / --pr-note           A real attempted run's collected data.
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
ROADMAP_PATH = REPO_ROOT / "ROADMAP.md"
REPORT_PATH = REPO_ROOT / "MORNING_REPORT.md"

NEEDS_SPEC_ITEM_RE = re.compile(r"^-\s+\*\*(.+?)\*\*\s+—\s+(.+)$")


def _extract_needs_spec_items() -> list:
    """Real parse of ROADMAP.md's NEEDS-SPEC section -- not a static copy,
    so the report always reflects whatever's actually in ROADMAP.md tonight,
    not whatever was true when this script was written."""
    if not ROADMAP_PATH.exists():
        return []
    text = ROADMAP_PATH.read_text()
    if "## NEEDS-SPEC" not in text:
        return []
    section = text.split("## NEEDS-SPEC", 1)[1]
    items = []
    for line in section.splitlines():
        match = NEEDS_SPEC_ITEM_RE.match(line.strip())
        if match:
            items.append(match.group(1))
    return items


def _parse_test_summary(pytest_tail: str) -> str:
    """Pulls pytest's own real one-line summary (e.g. '344 passed, 1
    skipped') out of the tail of its output, rather than re-deriving pass
    counts by hand -- the summary line IS the real evidence."""
    if not pytest_tail:
        return "(no output captured)"
    for line in reversed(pytest_tail.strip().splitlines()):
        if "passed" in line or "failed" in line or "error" in line:
            return line.strip()
    return pytest_tail.strip().splitlines()[-1] if pytest_tail.strip() else "(no output captured)"


def _load_result_json(path: str) -> dict:
    try:
        raw = Path(path).read_text().strip()
        return json.loads(raw)
    except Exception as exc:  # real run output can be malformed if the invocation itself errored
        return {"status": "unknown", "result": f"(could not parse result JSON: {exc})", "total_cost_usd": None}


def render_no_task_report(now: str) -> str:
    needs_spec = _extract_needs_spec_items()
    lines = [
        "# Morning report",
        "",
        f"Run: {now}",
        "",
        "**No RUNNABLE task was found in ROADMAP.md.** Nothing was attempted tonight.",
        "",
    ]
    lines.extend(_needs_spec_section(needs_spec))
    return "\n".join(lines) + "\n"


def _needs_spec_section(needs_spec: list) -> list:
    if not needs_spec:
        return ["## Flagged NEEDS-SPEC (none currently)", ""]
    lines = ["## Flagged NEEDS-SPEC — needs your input before these can run", ""]
    for item in needs_spec:
        lines.append(f"- {item}")
    lines.append("")
    return lines


def render_report(args, now: str) -> str:
    result = _load_result_json(args.result_json)
    baseline_summary = _parse_test_summary(args.baseline_tests)
    final_summary = _parse_test_summary(args.final_tests)
    status = result.get("status", "unknown")
    cost = result.get("total_cost_usd")
    cost_str = f"${cost:.4f}" if isinstance(cost, (int, float)) else "(unknown -- result JSON did not include total_cost_usd)"

    outcome = "DONE" if status == "success" and "failed" not in final_summary else "PARTIAL/BLOCKED"

    lines = [
        "# Morning report",
        "",
        f"Run: {now}",
        f"Task attempted: **{args.task_id}**",
        f"Branch: `{args.branch}`",
        f"Result: **{outcome}**" + (f" ({status})" if status != "success" else ""),
        "",
        "## Tests",
        f"- Before: {baseline_summary}",
        f"- After: {final_summary}",
        "",
        "## Cost",
        f"- {cost_str}",
        "",
        "## Diff stats",
        "```",
        args.diff_stats.strip() or "(no diff captured)",
        "```",
        "",
        "## Delivery",
        f"- {args.pr_note}",
        "",
        "## Agent's own final message",
        "```",
        (result.get("result") or "(no result text)").strip(),
        "```",
        "",
    ]
    lines.extend(_needs_spec_section(_extract_needs_spec_items()))
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-task", action="store_true")
    parser.add_argument("--task-id")
    parser.add_argument("--branch")
    parser.add_argument("--result-json")
    parser.add_argument("--baseline-tests", default="")
    parser.add_argument("--final-tests", default="")
    parser.add_argument("--diff-stats", default="")
    parser.add_argument("--pr-note", default="")
    args = parser.parse_args()

    now = datetime.now(timezone.utc).isoformat()

    if args.no_task:
        REPORT_PATH.write_text(render_no_task_report(now))
    else:
        if not args.task_id or not args.result_json:
            print("Error: --task-id and --result-json are required unless --no-task", file=sys.stderr)
            sys.exit(1)
        REPORT_PATH.write_text(render_report(args, now))

    print(f"Wrote {REPORT_PATH}")


if __name__ == "__main__":
    main()
