"""Which code produced this artifact, captured when the process starts.

WHY THIS EXISTS
---------------
This project has confused "the code exists" with "the code ran" repeatedly
enough that the confusion is now a named failure class:

  * a producer was committed, green, and never executed, while a retention
    check read HEALTHY;
  * a store gained a write path that no cycle called;
  * report.py gained the V4 projections at 21:31 and the run that was cited as
    proof of them had been written at 20:28;
  * the next cycle emitted two projections as empty objects, because the
    process had imported the module revision from before the commit that
    fills them.

Every one of those was diagnosed by hand, hours or days later, by comparing a
file's mtime against a commit timestamp. None of them had to be: the running
process knows exactly what it is, and the artifact it writes is the only place
that knowledge is useful.

CAPTURED AT IMPORT, NOT AT WRITE
--------------------------------
The SHA is read once, when this module is first imported, and cached. Reading
it at report time would report the state of the CHECKOUT when the report was
written, not the code the process is running — and those differ precisely in
the case this module exists to catch, where a long cycle is still running
while the branch moves underneath it.

NEVER GUESSED
-------------
An unavailable SHA is reported as "unknown". A fabricated provenance is worse
than none, because the whole point is that a downstream reader can trust it.
"""
from __future__ import annotations

import datetime as _dt
import os
import pathlib
import subprocess

CONTRACT = "runtime_provenance.v1"

UNKNOWN = "unknown"


def _source_root() -> pathlib.Path:
    """The directory the running `intent_engine` package was imported from."""
    import intent_engine

    return pathlib.Path(intent_engine.__file__).resolve().parent.parent


def _git(args, cwd) -> str:
    try:
        out = subprocess.run(["git"] + list(args), cwd=str(cwd),
                             capture_output=True, text=True, timeout=10)
    except Exception:  # noqa: BLE001 - provenance must never fail a cycle
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


def _capture() -> dict:
    root = _source_root()
    sha = (os.environ.get("MARKET_RUNTIME_SHA")
           or _git(["rev-parse", "HEAD"], root) or UNKNOWN)
    ref = _git(["rev-parse", "--abbrev-ref", "HEAD"], root) or UNKNOWN
    toplevel = _git(["rev-parse", "--show-toplevel"], root) or str(root)
    dirty = _git(["status", "--short", "--untracked-files=no"], root)
    return {
        "contract": CONTRACT,
        "runtime_git_sha": sha,
        "runtime_ref": ref,
        # The tree the RUNNING package was imported from. The market venv
        # symlinks to the Founder environment, so with PYTHONPATH unset
        # `intent_engine` resolves to a checkout with no `market` subpackage
        # at all. When it resolves somewhere unexpected, this is the field
        # that says so.
        "runtime_source_root": str(root),
        "runtime_repo_root": toplevel,
        "runtime_tree_dirty": bool(dirty),
        "execution_started_at": _dt.datetime.now(
            _dt.timezone.utc).isoformat(),
    }


#: Captured once, at first import — which is process start for a cycle.
PROVENANCE: dict = _capture()


def provenance() -> dict:
    return dict(PROVENANCE)


def ran_at_or_after(artifact: dict, sha: str, *, repo_root: str = "") -> bool:
    """Did the process that wrote `artifact` include commit `sha`?

    THE RELEASE GATE. A feature may not be called live-verified unless the
    artifact's runtime SHA contains that feature's commit. Ancestry is asked
    of git rather than assumed from equality, so a descendant counts.

    Returns False when the SHA is unknown or ancestry cannot be established.
    Fails closed: "we could not tell" and "yes" must never be the same answer.
    """
    got = str((artifact or {}).get("runtime_git_sha") or "")
    if not got or got == UNKNOWN or not sha:
        return False
    if got == sha:
        return True
    root = repo_root or str((artifact or {}).get("runtime_repo_root") or "")
    if not root:
        return False
    try:
        out = subprocess.run(
            ["git", "merge-base", "--is-ancestor", sha, got],
            cwd=root, capture_output=True, text=True, timeout=10)
    except Exception:  # noqa: BLE001
        return False
    return out.returncode == 0


def imports_resolve_under(expected_root) -> bool:
    """Is the running `intent_engine.market` the one in `expected_root`?

    The market venv's python symlinks into the Founder repository's
    environment. With PYTHONPATH unset, `import intent_engine` succeeds and
    resolves to the OTHER repository — which has no `market` subpackage, so
    the failure surfaces as a confusing ModuleNotFoundError deep inside an
    unrelated call rather than as "you are running the wrong tree".
    """
    from intent_engine.market import __file__ as market_file

    try:
        resolved = pathlib.Path(market_file).resolve()
        expected = pathlib.Path(expected_root).resolve()
    except OSError:
        return False
    return expected in resolved.parents
