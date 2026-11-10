"""The harness must reject the proof that nearly passed in wave 5.

`PRODUCER_OF = {` → `PRODUCER_OF = {} or {` changed the source, changed the
bytes, and changed nothing that runs, because `{} or {...}` evaluates to the
second dict. It was reported as a passing break proof.

A suite that says "30/30 break proofs pass" is only worth reading if every
one of those proofs demonstrably changed the executed code path and turned
its own test red for its own reason.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]
                       / "scripts"))

from break_proof_harness import (  # noqa: E402
    ANCHOR_MISSING, HELD, INVALID, NO_OP, NOT_CAUGHT, Proof, ROOT,
    WRONG_REASON, verify)

TARGET = ("tests/test_market_self_test_contamination.py"
          "::test_every_class_carries_a_producer")
SOURCE = ROOT / "src/intent_engine/market/observation_binding.py"


def test_a_byte_identical_replacement_is_rejected_as_a_no_op():
    got = verify(Proof(
        label="no-op", path=SOURCE, find="PRODUCER_OF = {",
        replace="PRODUCER_OF = {", target=TARGET))
    assert got.verdict == NO_OP
    assert not got.ok
    assert "byte-identical" in got.detail


def test_a_missing_anchor_is_invalid_not_merely_uncaught():
    got = verify(Proof(
        label="missing", path=SOURCE,
        find="this string is not in the file anywhere at all",
        replace="x", target=TARGET))
    assert got.verdict == ANCHOR_MISSING
    assert got.verdict in INVALID


def test_a_real_mutation_that_is_caught_holds():
    got = verify(Proof(
        label="real", path=SOURCE,
        find='    LEGITIMATE_LATER_OBSERVATION: "not a self-test; admitted",',
        replace='    LEGITIMATE_LATER_OBSERVATION: "",',
        target=TARGET, expect_failure_contains="assert"))
    assert got.verdict == HELD


def test_a_mutation_that_changes_bytes_and_not_behaviour_is_not_caught():
    """A comment is a byte change and never a behaviour change."""
    got = verify(Proof(
        label="comment", path=SOURCE, find="PRODUCER_OF = {",
        replace="PRODUCER_OF = {  # a comment changes bytes, not behaviour",
        target=TARGET))
    assert got.verdict == NOT_CAUGHT
    assert "not load-bearing" in got.detail


def test_red_for_the_wrong_reason_does_not_count():
    """An ImportError is red and is not evidence a guard is load-bearing."""
    got = verify(Proof(
        label="wrong reason", path=SOURCE,
        find="PRODUCER_OF = {",
        replace="import nonexistent_module_xyz\nPRODUCER_OF = {",
        target=TARGET,
        expect_failure_contains="AssertionError"))
    assert got.verdict == WRONG_REASON


def test_the_file_is_always_restored_exactly():
    before = SOURCE.read_bytes()
    for replacement in ("PRODUCER_OF = {}\nif False:\n    PRODUCER_OF = {",
                        "import nonexistent_module_xyz\nPRODUCER_OF = {"):
        verify(Proof(label="x", path=SOURCE, find="PRODUCER_OF = {",
                     replace=replacement, target=TARGET))
    assert SOURCE.read_bytes() == before
