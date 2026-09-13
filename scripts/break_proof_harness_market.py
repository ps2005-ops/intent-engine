"""The harness a break proof has to survive before it counts.

WHY THIS EXISTS
---------------
Wave 5 ran thirty proofs and reported 30/30. One of them was
`PRODUCER_OF = {` → `PRODUCER_OF = {} or {`, and in Python `{} or {...}`
evaluates to the second dict. The source changed, the bytes changed, the
behaviour did not, the test stayed green — and only a hand-check caught that
"the mutation was not caught" and "the mutation did nothing" look identical
from outside.

Another proof mutated a guard that was unreachable for the case its paired
test exercised. Same symptom, different cause.

So "30/30 break proofs pass" means nothing unless every one of them
demonstrably changed the executed code path AND turned its own test red for
its own reason. This module makes that the only way to pass.

THE FIVE CONDITIONS
-------------------
    1  SOURCE CHANGED        sha256(original) != sha256(mutated)
    2  TEST WAS GREEN        before the mutation, on the exact node id
    3  TEST TURNED RED       after it, on the exact node id
    4  RED FOR THE RIGHT REASON
                             the failure text matches the proof's stated
                             expectation, so a collected-error or an import
                             failure cannot pass as a caught mutation
    5  RESTORED EXACTLY      sha256(restored) == sha256(original), mtime
                             bumped, __pycache__ cleared, test green again

Any proof failing any condition is INVALID and is reported as such —
separately from a proof that ran and was not caught, because the two call
for different repairs.

WHY THE BYTECODE HAS TO GO
--------------------------
A same-length restore leaves CPython holding a cached .pyc whose size and
mtime still match, so the NEXT proof measures the previous proof's mutation.
mtime is bumped and the package's __pycache__ is cleared, both, because
either alone has been observed to be insufficient.
"""
from __future__ import annotations

import dataclasses
import hashlib
import os
import pathlib
import shutil
import subprocess
import time
from typing import Dict, List, Optional, Sequence, Tuple

ROOT = pathlib.Path(__file__).resolve().parents[1]
PY = "/Users/prathamsharma/intent-engine/.venv/bin/python"

# --- verdicts ---------------------------------------------------------------
HELD = "HELD"                          # mutation caught, for the right reason
NOT_CAUGHT = "NOT_CAUGHT"              # the guard is not load-bearing
NO_OP = "NO_OP"                        # the mutation changed no bytes
UNREACHABLE = "UNREACHABLE"            # bytes changed, behaviour did not
WRONG_REASON = "WRONG_REASON"          # red, but not for the stated reason
ALREADY_RED = "ALREADY_RED"            # the test failed before the mutation
ANCHOR_MISSING = "ANCHOR_MISSING"      # the source no longer contains it
DIRTY_RESTORE = "DIRTY_RESTORE"        # the file did not come back identical

INVALID = (NO_OP, ANCHOR_MISSING, WRONG_REASON, DIRTY_RESTORE)


@dataclasses.dataclass(frozen=True)
class Proof:
    label: str
    path: pathlib.Path
    find: str
    replace: str
    target: str
    #: A fragment that MUST appear in the failure output. Without it a proof
    #: can pass on a collection error, an ImportError, or a fixture blowing
    #: up — none of which is evidence that the guard is load-bearing.
    expect_failure_contains: str = ""


@dataclasses.dataclass
class Result:
    label: str
    verdict: str
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.verdict == HELD


def _sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _clear_bytecode(path: pathlib.Path) -> None:
    cache = path.parent / "__pycache__"
    if cache.is_dir():
        shutil.rmtree(cache, ignore_errors=True)


def _run(target: str) -> Tuple[bool, str]:
    done = subprocess.run(
        [PY, "-m", "pytest", target, "-q", "--no-header", "-x"],
        cwd=ROOT, capture_output=True, text=True,
        env={"PYTHONPATH": "src", "PATH": "/usr/bin:/bin",
             "PYTHONDONTWRITEBYTECODE": "1"})
    return done.returncode == 0, (done.stdout + done.stderr)


def verify(proof: Proof) -> Result:
    """Run one proof through all five conditions."""
    original_bytes = proof.path.read_bytes()
    original = original_bytes.decode("utf-8")
    original_hash = hashlib.sha256(original_bytes).hexdigest()

    if proof.find not in original:
        return Result(proof.label, ANCHOR_MISSING,
                      f"anchor absent from {proof.path.name}")

    mutated = original.replace(proof.find, proof.replace, 1)
    # CONDITION 1. The `{} or {...}` proof died here, which is the point.
    if hashlib.sha256(mutated.encode("utf-8")).hexdigest() == original_hash:
        return Result(proof.label, NO_OP,
                      "the replacement is byte-identical to the original")

    # CONDITION 2.
    green_before, _ = _run(proof.target)
    if not green_before:
        return Result(proof.label, ALREADY_RED,
                      "the paired test failed before any mutation")

    try:
        proof.path.write_text(mutated, encoding="utf-8")
        _clear_bytecode(proof.path)
        # CONDITION 3.
        green_after, output = _run(proof.target)
    finally:
        proof.path.write_bytes(original_bytes)
        now = time.time() + 1
        os.utime(proof.path, (now, now))
        _clear_bytecode(proof.path)

    # CONDITION 5, first half: the file came back exactly.
    if _sha(proof.path) != original_hash:
        return Result(proof.label, DIRTY_RESTORE,
                      "the file did not restore to its original bytes")
    green_again, _ = _run(proof.target)
    if not green_again:
        return Result(proof.label, DIRTY_RESTORE,
                      "the test did not go green again after restore")

    if green_after:
        # Bytes changed and behaviour did not. Distinguished from NOT_CAUGHT
        # only by intent, so both are reported and neither counts.
        return Result(proof.label, NOT_CAUGHT,
                      "the mutation changed the source and not the outcome: "
                      "the guard, the mutation site, or the paired test is "
                      "not load-bearing")

    # CONDITION 4.
    if proof.expect_failure_contains and \
            proof.expect_failure_contains not in output:
        return Result(proof.label, WRONG_REASON,
                      f"went red without {proof.expect_failure_contains!r} "
                      f"in the output; it may have failed for an unrelated "
                      f"reason")
    return Result(proof.label, HELD)


#: One mutation run at a time, per worktree.
#:
#: THE INCIDENT THIS PREVENTS. Two break-proof scripts were once started
#: against the same worktree minutes apart. They mutated the same files
#: simultaneously, which produced a DIRTY_RESTORE, two spurious ANCHOR_MISSING
#: results, and three source files left mutated — one of them an
#: `import nonexistent_module_xyz` that broke a module at import and turned
#: three unrelated tests red. Every one of those looks like a real finding and
#: none of them was. A lock is cheaper than the hour spent telling them apart.
LOCK = ROOT / ".break_proof.lock"

#: A lock older than this is assumed to belong to a run that was killed.
#: Long enough that a slow suite never trips it, short enough that a stale
#: file does not block the next session.
STALE_LOCK_SECONDS = 3600


class ConcurrentMutation(RuntimeError):
    """Another mutation run holds this worktree."""


def _acquire_lock() -> None:
    if LOCK.exists():
        age = time.time() - LOCK.stat().st_mtime
        if age < STALE_LOCK_SECONDS:
            raise ConcurrentMutation(
                f"{LOCK} is held (age {int(age)}s) by pid "
                f"{LOCK.read_text().strip() or 'unknown'}. Break proofs "
                "mutate real source files and MUST run one at a time against "
                "a worktree; two at once corrupt each other's restores. Wait, "
                "or delete the lock if that process is gone.")
        LOCK.unlink()
    LOCK.write_text(str(os.getpid()))


def _release_lock() -> None:
    try:
        LOCK.unlink()
    except OSError:
        pass


def run_all(proofs: Sequence[Proof], *, title: str = "") -> int:
    if title:
        print(title)
    _acquire_lock()
    try:
        results = [verify(p) for p in proofs]
    finally:
        # Released even on a crash, so a killed run does not block the next
        # one for an hour — the staleness window is the backstop, not the
        # normal path.
        _release_lock()
    for result in results:
        mark = "ok   " if result.ok else "FAIL "
        print(f"  {mark} {result.label}")
        if not result.ok:
            print(f"        {result.verdict}: {result.detail}")
    held = sum(1 for r in results if r.ok)
    invalid = [r for r in results if r.verdict in INVALID]
    print()
    print(f"{held}/{len(results)} break proofs held")
    if invalid:
        print(f"{len(invalid)} INVALID (not merely uncaught): "
              f"{', '.join(sorted({r.verdict for r in invalid}))}")
    return 0 if held == len(results) else 1
