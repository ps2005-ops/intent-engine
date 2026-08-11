"""The operator CLI must name the tree it is reading.

THE DEFECT. `--root` defaulted to the relative string `data`, while launchd
passes an absolute runtime tree. `python -m intent_engine.market runs` typed
from any other directory therefore resolved to an empty `./data` and printed
"no cycle has run yet" -- the same sentence a genuinely idle engine prints.
An operator asking whether the night cycle ran got a confident, wrong "no".

This is the missing-versus-zero collapse in its operator-facing form, which is
why it gets a test rather than a comment.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from intent_engine.market import cycle as C
from intent_engine.market.__main__ import (
    FALLBACK_ROOT, ROOT_ENV, build_parser, main, resolve_root,
)


def _args(argv):
    return build_parser().parse_args(argv)


def _seed(root, row):
    """One run record, written the way RunStore reads it back.

    Deliberately not via `RunStore.append`, which takes a live CycleResult:
    this test is about what `runs` REPORTS from the store, so it seeds the
    store's own on-disk shape and leaves the producer out of it.
    """
    store = C.RunStore(root)
    store.path.parent.mkdir(parents=True, exist_ok=True)
    with open(store.path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")


# =============================================================================
# resolve_root -- precedence, and always absolute
# =============================================================================
def test_an_explicit_root_wins_over_the_environment(monkeypatch, tmp_path):
    monkeypatch.setenv(ROOT_ENV, str(tmp_path / "from-env"))
    assert resolve_root(str(tmp_path / "explicit")) == tmp_path / "explicit"


def test_the_environment_supplies_the_root_when_the_flag_is_absent(
        monkeypatch, tmp_path):
    monkeypatch.setenv(ROOT_ENV, str(tmp_path / "from-env"))
    assert resolve_root(None) == tmp_path / "from-env"


def test_the_fallback_is_still_the_old_default(monkeypatch, tmp_path):
    """Unchanged behaviour for anyone relying on it -- but absolute."""
    monkeypatch.delenv(ROOT_ENV, raising=False)
    monkeypatch.chdir(tmp_path)
    assert resolve_root(None) == (tmp_path / FALLBACK_ROOT).resolve()


def test_a_resolved_root_is_always_absolute(monkeypatch, tmp_path):
    """A relative root is what made the answer depend on the operator's cwd."""
    monkeypatch.delenv(ROOT_ENV, raising=False)
    monkeypatch.chdir(tmp_path)
    for value in (None, "data", "./data", FALLBACK_ROOT):
        assert resolve_root(value).is_absolute()


def test_the_flag_no_longer_carries_a_relative_default(monkeypatch):
    """The parser default itself must not be the relative string: that is the
    value that silently reached RunStore before."""
    monkeypatch.delenv(ROOT_ENV, raising=False)
    for command in ("runs", "status", "night"):
        assert _args([command]).root is None


# =============================================================================
# the reading commands name their tree, on BOTH branches
# =============================================================================
def test_an_empty_result_says_which_root_it_read(monkeypatch, tmp_path,
                                                 capsys):
    monkeypatch.delenv(ROOT_ENV, raising=False)
    assert main(["runs", "--root", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert str(tmp_path) in out
    assert "no cycle has run yet" in out


def test_a_non_empty_result_also_says_which_root_it_read(monkeypatch,
                                                        tmp_path, capsys):
    """The NEGATIVE CONTROL. Without it, a `runs` that printed the root only on
    the empty branch would pass the test above while still leaving the operator
    guessing on every real answer."""
    _seed(tmp_path, {"run_id": "night-2026-08-10.1", "status": "COMPLETE",
                     "steps": [{"name": "s", "status": "ok"}]})
    assert main(["runs", "--root", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert str(tmp_path) in out
    assert "night-2026-08-10.1" in out
    assert "no cycle has run yet" not in out


def test_runs_reads_the_environment_root_when_no_flag_is_given(
        monkeypatch, tmp_path, capsys):
    """The whole point: the operator types four words and reads the tree
    launchd actually writes."""
    _seed(tmp_path, {"run_id": "night-from-env.1", "status": "COMPLETE",
                     "steps": []})
    monkeypatch.setenv(ROOT_ENV, str(tmp_path))
    monkeypatch.chdir(tmp_path.parent)
    assert main(["runs"]) == 0
    out = capsys.readouterr().out
    assert "night-from-env.1" in out
