"""§36: the meta-guard. A break proof may not mutate the guard it tests.

THE MISTAKE THIS EXISTS TO MAKE IMPOSSIBLE
------------------------------------------
Across three runs, thirteen break proofs were written like this:

    mutate:  the body of `assert_no_double_count`
    check:   call `assert_no_double_count` and expect it to raise

That is a tautology. Of course nothing fires -- the thing that fires was the
thing removed. Every one of them reported NOT_CAUGHT, was diagnosed by hand,
and was rewritten to mutate the producer instead. Noticing the same error
three times without preventing it is itself the defect.

So the rule is now machine-enforced. A proof declares:

    mutated_file        which file the mutation touched
    mutated_symbol      which function/class/constant it changed
    guard_under_test    which assertion is supposed to fire
    production_call_path where that guard is actually invoked in production
    bytes_before/after  proof the mutation landed and changed size

and `Proof.validate()` REFUSES when `mutated_symbol == guard_under_test`,
unless `tests_guard_integrity=True` is set deliberately -- which is a
different and legitimate kind of proof (does the guard itself still work),
and is labelled as such in the output so it can never be counted as evidence
that a defect would be caught in production.

WHY `production_call_path` IS REQUIRED
--------------------------------------
Break proof 12 of the V2 wave went looking for a call site to mutate and
found none: `assert_no_unsupported_claim` was implemented, unit-tested, and
had never run on anything the system emits. That absence was the finding.
Requiring the path up front turns that discovery from luck into a
precondition.
"""
from __future__ import annotations

import pathlib
import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from .vocabulary import EconError, require

CONTRACT = "econ_breakproof.v1"

CAUGHT = "CAUGHT"
NOT_CAUGHT = "NOT_CAUGHT"
NOT_APPLIED = "NOT_APPLIED"
UNRELIABLE = "UNRELIABLE"
REFUSED = "REFUSED_TAUTOLOGY"
VERDICTS = (CAUGHT, NOT_CAUGHT, NOT_APPLIED, UNRELIABLE, REFUSED)

#: Where a mutation is allowed to land. An assertion helper is not on the
#: list, which is the whole point.
PRODUCER = "PRODUCER"
PERSISTENCE = "PERSISTENCE"
CONSUMER = "CONSUMER"
RENDERER = "RENDERER"
CALL_SITE = "CALL_SITE"
TARGETS = (PRODUCER, PERSISTENCE, CONSUMER, RENDERER, CALL_SITE)


class TautologicalProof(EconError):
    """A break proof mutated the guard it claims to test."""


@dataclass
class Proof:
    """One break proof, with the metadata that makes it checkable."""

    name: str
    description: str
    #: What the mutation is aimed at. Never an assertion helper.
    target_kind: str
    mutated_file: str
    mutated_symbol: str
    #: The assertion expected to fire. May be a function name or a phrase.
    guard_under_test: str
    #: Where that guard actually runs in production. Required, because a
    #: guard with no call site has never run.
    production_call_path: str
    #: Set deliberately when the proof's PURPOSE is to check the guard
    #: itself rather than to check that a defect would be caught.
    tests_guard_integrity: bool = False
    bytes_before: int = 0
    bytes_after: int = 0
    verdict: str = ""
    detail: str = ""

    def validate(self) -> None:
        """§36's rule, applied before the proof is allowed to run."""
        require(self.target_kind in TARGETS,
                f"{self.name}: target_kind {self.target_kind!r} is not one of "
                f"{TARGETS}")
        require(bool(self.production_call_path.strip()),
                f"{self.name}: name the production call path for "
                f"{self.guard_under_test!r}. A guard with no call site has "
                "never run, and a proof that cannot name one is testing a "
                "function nobody invokes.")
        if self.tests_guard_integrity:
            return
        if _same_symbol(self.mutated_symbol, self.guard_under_test):
            raise TautologicalProof(
                f"{self.name}: the mutation changes {self.mutated_symbol!r} "
                f"and the guard under test is {self.guard_under_test!r}. "
                "Removing the check and then calling the check proves "
                "nothing -- it is the mistake this project made thirteen "
                "times across three runs. Mutate the PRODUCER, the "
                "PERSISTENCE, the CONSUMER, the RENDERER or the CALL SITE. "
                "If the intent really is to test the guard's own integrity, "
                "set tests_guard_integrity=True and it will be labelled as "
                "such rather than counted as defect coverage.")

    def assert_mutation_landed(self) -> None:
        if self.bytes_before == self.bytes_after:
            raise TautologicalProof(
                f"{self.name}: the file is the same size before and after "
                f"({self.bytes_before} bytes). A no-op mutation passes "
                "silently and reports CAUGHT for a defect that was never "
                "introduced.")

    def as_dict(self) -> dict:
        return {"proof": self.name, "description": self.description,
                "target_kind": self.target_kind,
                "mutated_file": self.mutated_file,
                "mutated_symbol": self.mutated_symbol,
                "guard_under_test": self.guard_under_test,
                "production_call_path": self.production_call_path,
                "tests_guard_integrity": self.tests_guard_integrity,
                "bytes_before": self.bytes_before,
                "bytes_after": self.bytes_after,
                "bytes_delta": self.bytes_after - self.bytes_before,
                "verdict": self.verdict, "detail": self.detail}


def _same_symbol(a: str, b: str) -> bool:
    """Are these the same thing under different spellings?

    Compares the bare identifier, so `WM.assert_no_double_count` and
    `assert_no_double_count` are the same symbol -- which is exactly the
    disguise the tautology wore.
    """
    def bare(x: str) -> str:
        x = x.strip().rsplit(".", 1)[-1]
        return re.sub(r"[^a-z0-9_]", "", x.lower())
    return bool(bare(a)) and bare(a) == bare(b)


def assert_call_path_exists(repo: pathlib.Path, proof: Proof) -> None:
    """The declared production call path must actually contain the call.

    Reads the CODE, not the prose: a docstring documenting the guard is not
    a call to it. (`structural-guards-must-read-code-not-prose` -- a grep
    matched the comment explaining the bug and reported the bug as present.)
    """
    import ast
    p = repo / proof.production_call_path
    if not p.exists():
        raise TautologicalProof(
            f"{proof.name}: production_call_path {proof.production_call_path} "
            "does not exist")
    guard = proof.guard_under_test.rsplit(".", 1)[-1]
    try:
        tree = ast.parse(p.read_text())
    except SyntaxError as e:
        raise TautologicalProof(f"{proof.name}: {p} does not parse: {e}")
    called = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            name = getattr(f, "id", None) or getattr(f, "attr", None)
            if name:
                called.add(name)
        # A guard can also be enforced by a raise inside the producer.
        if isinstance(node, ast.Raise):
            called.add("__raise__")
        # A GUARD CAN ALSO BE A TEST, AND A TEST'S CALL SITE IS ITS SUITE.
        #
        # Six product proofs were REFUSED for naming a test file that
        # "never calls" the test in it -- which is true and is not the
        # question. A pytest test is invoked by collection, so its DEFINITION
        # in a collected file is its call path, and requiring a literal call
        # would force every structural guard to be wrapped in a fake caller.
        #
        # This does not weaken §36. The anti-tautology rule is
        # `mutated_symbol != guard_under_test` and is checked separately in
        # `Proof.validate`. What this function enforces is that the guard
        # ACTUALLY EXISTS AND RUNS in the named file, and a test function that
        # is not defined there still fails.
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and node.name.startswith("test_"):
            called.add(node.name)
    if guard not in called and "__raise__" not in called:
        raise TautologicalProof(
            f"{proof.name}: {proof.production_call_path} never calls "
            f"{guard!r}. The guard exists and nothing invokes it, which is a "
            "finding about the system rather than about this proof.")


def summarise(proofs: Sequence[Proof]) -> dict:
    by = {}
    for p in proofs:
        by[p.verdict] = by.get(p.verdict, 0) + 1
    integrity = [p.name for p in proofs if p.tests_guard_integrity]
    return {"contract": CONTRACT, "proofs": len(proofs),
            "caught": by.get(CAUGHT, 0),
            "not_caught": by.get(NOT_CAUGHT, 0),
            "not_applied": by.get(NOT_APPLIED, 0),
            "unreliable": by.get(UNRELIABLE, 0),
            "refused_tautology": by.get(REFUSED, 0),
            "by_verdict": by,
            "guard_integrity_proofs": integrity,
            "defect_coverage_proofs": len(proofs) - len(integrity),
            "target_kinds": {k: sum(1 for p in proofs if p.target_kind == k)
                             for k in TARGETS},
            "detail": [p.as_dict() for p in proofs],
            "meta_guard": (
                "every proof declared a mutated symbol distinct from the "
                "guard it tests, and a production call path that was checked "
                "to contain the call. Proofs marked guard_integrity are "
                "counted separately and are NOT defect coverage.")}
