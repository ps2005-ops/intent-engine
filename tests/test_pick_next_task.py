import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from pick_next_task import Task, parse_roadmap, pick_next_runnable  # noqa: E402


def test_parse_roadmap_extracts_runnable_tasks_with_priority():
    text = """
## T001 — First task

- **Status**: RUNNABLE
- **Priority**: 2
- **Size**: S

## T002 — Second task

- **Status**: RUNNABLE
- **Priority**: 1
- **Size**: M
"""
    tasks = parse_roadmap(text)
    assert tasks == [Task("T001", "RUNNABLE", 2), Task("T002", "RUNNABLE", 1)]


def test_pick_next_runnable_picks_lowest_priority_number():
    tasks = [Task("T001", "RUNNABLE", 2), Task("T002", "RUNNABLE", 1), Task("T003", "RUNNABLE", 3)]
    assert pick_next_runnable(tasks) == "T002"


def test_pick_next_runnable_never_picks_needs_spec():
    tasks = [Task("T001", "NEEDS-SPEC", 1), Task("T002", "RUNNABLE", 5)]
    assert pick_next_runnable(tasks) == "T002"


def test_pick_next_runnable_never_picks_done_or_in_progress():
    tasks = [Task("T001", "DONE", 1), Task("T002", "IN-PROGRESS", 2), Task("T003", "RUNNABLE", 3)]
    assert pick_next_runnable(tasks) == "T003"


def test_pick_next_runnable_returns_none_when_nothing_runnable():
    tasks = [Task("T001", "NEEDS-SPEC", 1), Task("T002", "DONE", 2)]
    assert pick_next_runnable(tasks) is None


def test_pick_next_runnable_returns_none_for_empty_roadmap():
    assert pick_next_runnable([]) is None


def test_parse_roadmap_skips_a_task_missing_priority():
    """A malformed entry (e.g. a human forgot the Priority line) is
    excluded rather than crashing the nightly run -- verified directly,
    not assumed."""
    text = """
## T001 — Missing priority

- **Status**: RUNNABLE

## T002 — Complete

- **Status**: RUNNABLE
- **Priority**: 1
"""
    tasks = parse_roadmap(text)
    assert [t.task_id for t in tasks] == ["T002"]


def test_parse_real_roadmap_file_has_the_expected_runnable_tasks():
    """Real end-to-end check against this repo's actual ROADMAP.md, not a
    synthetic fixture only."""
    roadmap_path = Path(__file__).parent.parent / "ROADMAP.md"
    tasks = parse_roadmap(roadmap_path.read_text())
    runnable_ids = {t.task_id for t in tasks if t.status == "RUNNABLE"}
    # T001 completed 2026-07-15 via the real nightly_agent.sh rehearsal
    # (commit 8e0dbac); T002 completed 2026-07-16 (rename commit b7ecf34);
    # T003 and T004 completed 2026-07-17 (commits 25cb4b5, 5342fec);
    # T010-T017 (Decision Record + wiring; report 2A/2B; Company Event
    # System; CRM; analytics; knowledge promotion; marketing C3-C8)
    # completed 2026-07-20/21. The current queue is T018 (growth platform
    # and experiments). NEEDS-SPEC items are still never auto-promoted.
    assert runnable_ids == {"T018"}
    # The nightly loop must pick T018 (the only RUNNABLE task), never a
    # NEEDS-SPEC item.
    assert pick_next_runnable(tasks) == "T018"
