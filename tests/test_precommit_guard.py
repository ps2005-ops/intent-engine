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


# Git variables git sets for hooks. In a LINKED WORKTREE these are ABSOLUTE and
# point at the real repo/index — if a fixture's git command inherits them it
# operates on the REAL repository instead of the tmp fixture. That is exactly
# how the 2026-07-26 incident happened: this test ran inside the pre-commit
# hook's suite check, and its `git add -A` clobbered the real index (repo-wide
# staged deletions) while `git init` flipped the common config's core.bare.
# Stripping them makes every fixture command resolve from `cwd`, never the env.
_GIT_ENV_VARS = (
    "GIT_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE", "GIT_COMMON_DIR",
    "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_NAMESPACE",
    "GIT_PREFIX", "GIT_CONFIG", "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM",
)


def _clean_env(**extra):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(extra)
    return env


def _git(cwd, *args):
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=False,
        env=_clean_env(),
    )


def _run_guard(cwd):
    return subprocess.run(
        ["bash", str(GUARD)], cwd=cwd, capture_output=True, text=True,
        env=_clean_env(GUARD_SKIP_PYTEST="1"),
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


def test_fixture_git_env_is_sanitized_against_a_real_repo(tmp_path, monkeypatch):
    """REGRESSION for the 2026-07-26 linked-worktree incident: even with
    GIT_DIR/GIT_INDEX_FILE set to a real repo (as a worktree hook sets them,
    absolute), this test's git commands must NOT touch it. Without _clean_env
    the fixture's `git add -A` clobbered the real index and `git init` flipped
    core.bare — this test fails loudly if that regresses."""
    sentinel = tmp_path / "sentinel"
    sentinel.mkdir()
    _git(sentinel, "init", "-q")
    _git(sentinel, "config", "user.email", "s@s")
    _git(sentinel, "config", "user.name", "s")
    (sentinel / "keep_a.txt").write_text("a\n")
    (sentinel / "keep_b.txt").write_text("b\n")
    _git(sentinel, "add", "keep_a.txt", "keep_b.txt")
    _git(sentinel, "commit", "-q", "-m", "sentinel base")
    files_before = _git(sentinel, "ls-files").stdout
    bare_before = _git(sentinel, "config", "--get", "core.bare").stdout.strip()

    # arm the hostile environment a worktree hook produces
    monkeypatch.setenv("GIT_DIR", str(sentinel / ".git"))
    monkeypatch.setenv("GIT_INDEX_FILE", str(sentinel / ".git" / "index"))

    fixture = tmp_path / "fixture"
    fixture.mkdir()
    (fixture / "only_fixture.txt").write_text("x\n")
    _git(fixture, "init", "-q")
    _git(fixture, "add", "-A")            # would clobber sentinel without the fix

    monkeypatch.delenv("GIT_DIR", raising=False)
    monkeypatch.delenv("GIT_INDEX_FILE", raising=False)
    assert _git(sentinel, "ls-files").stdout == files_before      # index untouched
    assert _git(sentinel, "config", "--get", "core.bare").stdout.strip() == bare_before


def test_guard_runs_clean_from_a_linked_worktree(tmp_path):
    """§4: the guard must work FROM a linked worktree and mutate nothing."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    for rel in SYNTH_FILES:
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("c\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    wt = tmp_path / "wt"
    _git(repo, "worktree", "add", "-q", str(wt), "-b", "wtb", "HEAD")
    bare_before = _git(repo, "config", "--get", "core.bare").stdout.strip()
    files_before = _git(repo, "ls-files").stdout

    result = _run_guard(wt)              # tree check from the LINKED worktree
    assert result.returncode == 0, result.stderr
    # and nothing about the real repo changed
    assert _git(repo, "config", "--get", "core.bare").stdout.strip() == bare_before
    assert _git(repo, "ls-files").stdout == files_before
