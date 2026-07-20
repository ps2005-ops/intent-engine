"""B2 (PLAN_2026-07-21): prove the pre-commit guard actually triggers.

The guard's tree check must (a) block a commit when a synthetic-worlds file is
staged-deleted or untracked — the exact loose end B1 cleaned up — and (b) pass
on a clean tree. The suite check is skipped via GUARD_SKIP_PYTEST=1 to avoid
running pytest recursively; the suite leg is the same command the repo already
runs before every commit, so the tree check is the new behavior under test.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
GUARD = REPO_ROOT / "scripts" / "precommit_guard.sh"

SYNTH_FILES = [
    "src/intent_engine/core/synthetic_worlds.py",
    "scripts/run_synthetic_world_eval.py",
    "tests/test_synthetic_worlds.py",
    "tests/test_premortem_ledger_wiring.py",
    "reports/synthetic_worlds_eval.json",
    "reports/synthetic_worlds_eval.md",
    "reports/synthetic_worlds_eval_live.json",
    "reports/synthetic_worlds_eval_live.md",
    "reports/synthetic_worlds_run_history.jsonl",
]


def _git(cwd, *args):
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=False
    )


def _run_guard(cwd):
    env = dict(os.environ, GUARD_SKIP_PYTEST="1")
    return subprocess.run(
        ["bash", str(GUARD)], cwd=cwd, capture_output=True, text=True, env=env
    )


@pytest.fixture()
def fixture_repo(tmp_path):
    """A minimal repo containing the tracked synthetic-worlds file set."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "guard-test")
    for rel in SYNTH_FILES:
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("fixture content\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "fixture baseline")
    return repo


def test_guard_passes_on_clean_tree(fixture_repo):
    result = _run_guard(fixture_repo)
    assert result.returncode == 0, result.stderr


def test_guard_blocks_staged_rm_cached(fixture_repo):
    """The B1 failure mode: git rm --cached leaves D-in-index + untracked."""
    _git(fixture_repo, "rm", "-q", "--cached", "src/intent_engine/core/synthetic_worlds.py")
    result = _run_guard(fixture_repo)
    assert result.returncode == 1
    assert "GUARD FAIL (tree)" in result.stderr


def test_guard_blocks_untracked_report(fixture_repo):
    """A new run artifact left untracked must block the commit, not vanish."""
    stray = fixture_repo / "reports" / "synthetic_worlds_runs" / "live_x.json"
    stray.parent.mkdir(parents=True, exist_ok=True)
    stray.write_text("{}\n")
    result = _run_guard(fixture_repo)
    assert result.returncode == 1
    assert "untracked" in result.stderr


def test_guard_blocks_missing_tracked_file(fixture_repo):
    """Deleting a core file from disk+index entirely must also block."""
    _git(fixture_repo, "rm", "-q", "reports/synthetic_worlds_run_history.jsonl")
    result = _run_guard(fixture_repo)
    assert result.returncode == 1
    assert "GUARD FAIL (tree)" in result.stderr
