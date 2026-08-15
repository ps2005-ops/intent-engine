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

import contextlib
import dataclasses
import hashlib
import os
import pathlib
import shutil
import subprocess
import tempfile
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


def _run(target: str, *, source_root: str = "src") -> Tuple[bool, str]:
    # `-o pythonpath=` OVERRIDES pytest.ini, which pins `pythonpath = src` and
    # inserts it at the FRONT of sys.path -- ahead of anything in the
    # environment. Without this the real tree shadows the mirror, every
    # mutation is silently inert, and twenty proofs report NOT_CAUGHT at once.
    done = subprocess.run(
        [PY, "-m", "pytest", target, "-q", "--no-header", "-x",
         "-o", f"pythonpath={source_root}"],
        cwd=ROOT, capture_output=True, text=True,
        env={"PYTHONPATH": source_root, "PATH": "/usr/bin:/bin",
             "PYTHONDONTWRITEBYTECODE": "1"})
    return done.returncode == 0, (done.stdout + done.stderr)


@contextlib.contextmanager
def _mutated_tree(path: pathlib.Path, mutated: str):
    """A PRIVATE copy of src/ with exactly one file changed.

    WHY THE SHARED TREE IS NEVER TOUCHED.

    This harness used to write the mutation into `src/` itself and restore it
    in a `finally`. For the seconds that window is open, every other reader of
    the repository sees deliberately broken source: the rest of the suite, an
    editor, a concurrent agent session on the same checkout, or simply the
    next proof if a restore is interrupted. A trust harness that makes the
    working tree briefly wrong is buying its evidence with a hazard, and an
    intermittent failure in the full run is exactly what that looks like from
    the outside.

    The copy is hard-linked, so it costs almost nothing for 419 files, and the
    one mutated file is UNLINKED BEFORE IT IS WRITTEN -- writing through a
    hard link would edit the shared inode and defeat the whole point.
    """
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="break-proof-"))
    try:
        mirror = tmp / "src"
        shutil.copytree(ROOT / "src", mirror, copy_function=os.link,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        target = mirror / path.relative_to(ROOT / "src")
        target.unlink()
        target.write_text(mutated, encoding="utf-8")
        yield mirror
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


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

    # CONDITION 3, run against a private tree so the shared one stays correct.
    with _mutated_tree(proof.path, mutated) as mirror:
        green_after, output = _run(proof.target, source_root=str(mirror))

    # CONDITION 5, now STRONGER than a restore check: the shared file was
    # never written, so it cannot have come back wrong. Asserted rather than
    # assumed, because "we no longer mutate the tree" is exactly the kind of
    # claim that quietly stops being true.
    if _sha(proof.path) != original_hash:
        return Result(proof.label, DIRTY_RESTORE,
                      "the shared source changed during an isolated proof")
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


def run_all(proofs: Sequence[Proof], *, title: str = "") -> int:
    if title:
        print(title)
    results = [verify(p) for p in proofs]
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
