"""Batch 16: the gate that decides whether Wave 30 opens.

Every previous gate verdict in this programme was written by hand, and one was
wrong in a way nobody could see for two batches: criterion 10 was recorded
MET-as-BLOCKED_EXTERNAL_CREDITS while the producer it depended on did not
exist, so "restore credits and it passes" was false.

A hand-maintained verdict drifts from the code it describes. This one is
derived from it — which makes the gate itself load-bearing, and the most
expensive defect available is a gate that opens a wave on checks nobody ran.
"""
import importlib.util
import pathlib

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "v5_wave30_gate",
    pathlib.Path(__file__).resolve().parent.parent
    / "scripts" / "v5_wave30_gate.py")
gate = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(gate)


def _adjudicate(verdicts):
    """Calls the GATE'S OWN adjudication, never a copy of it.

    An earlier version of this helper reimplemented the rule locally, so
    mutating the gate could not make any of these tests fail — a test that
    cannot fail, protecting the decision that opens a wave.
    """
    return gate.adjudicate(
        [gate._result(f"c{i}", v, "") for i, v in enumerate(verdicts)])


def test_a_blocked_criterion_never_opens_the_wave():
    """BLOCKED IS NOT A SOFT PASS.

    A criterion nobody could evaluate is the one most likely to be assumed,
    and assuming it is how a wave opens on unverified ground.
    """
    assert _adjudicate([gate.PASS] * 11 + [gate.BLOCKED]) == gate.BLOCKED


def test_a_failing_criterion_closes_the_wave():
    assert _adjudicate([gate.PASS] * 11 + [gate.FAIL]) == gate.FAIL


def test_a_failure_outranks_a_block():
    """A FAIL is a defect; a BLOCK is an absence. The defect is reported."""
    assert _adjudicate([gate.PASS, gate.BLOCKED, gate.FAIL]) == gate.FAIL


def test_all_pass_opens_the_wave():
    """NEGATIVE CONTROL. A gate that can never open measures nothing."""
    assert _adjudicate([gate.PASS] * 12) == gate.PASS


# --- the checks themselves --------------------------------------------------
def test_the_cohort_check_pins_the_frozen_ten():
    verdict, detail = gate._cohort_unchanged()
    assert verdict == gate.PASS, detail


def test_the_inflation_check_requires_one_effect_per_moved_component():
    verdict, detail = gate._effect_inflation_invariant()
    assert verdict == gate.PASS, detail


def test_the_no_producer_check_requires_real_callers():
    verdict, detail = gate._temporal_seam_has_callers()
    assert verdict == gate.PASS, detail


def test_the_independence_check_rejects_syndication_and_self_report():
    verdict, detail = gate._origin_independence_enforced()
    assert verdict == gate.PASS, detail


def test_the_wall_check_requires_alphabet_to_pass_and_alpha_to_fail():
    verdict, detail = gate._trading_wall_precision()
    assert verdict == gate.PASS, detail


def test_the_empty_effects_check_scans_real_call_sites_not_comments():
    """The literal appears in docstrings that EXPLAIN the defect; an AST-based
    check must not confuse describing a bug with committing one."""
    verdict, detail = gate._no_empty_effects_literal()
    assert verdict == gate.PASS, detail


@pytest.mark.parametrize("state", ["NO_CHANGE", "FIRST_OBSERVATION",
                                   "UNMEASURABLE", "REFUSED"])
def test_the_four_non_changing_states_stay_distinct(state):
    from intent_engine.company_ingestion import learning_attribution as la
    assert getattr(la, state) in la.NON_CHANGING
    assert getattr(la, state) not in la.CHANGING
