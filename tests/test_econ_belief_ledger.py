"""Preregistration, no hindsight rewrite, falsifiers, decay, calibration.

Section 32's belief block, plus Section 37's refusal to report an accuracy
figure before the declared minimum sample.
"""
from __future__ import annotations

import pytest

from intent_engine.econ import belief as B
from intent_engine.econ import calibration as CAL
from intent_engine.econ.vocabulary import EconError


def a_belief(**kw):
    base = dict(
        proposition="US enterprise software demand is becoming more "
                    "price-sensitive as real rates remain restrictive",
        probability=0.6,
        mechanism="restrictive real rates raise the hurdle rate on software "
                  "purchases that pay back over years",
        falsifier="two consecutive quarters of accelerating net expansion "
                  "across the tracked vendors while real yields stay above "
                  "1.5%",
        expected_observations=("net revenue retention falling across at "
                               "least four tracked vendors",),
        at="2026-06-01")
    base.update(kw)
    return B.declare(**base)


# --- what a belief must carry ----------------------------------------------
def test_a_belief_with_no_falsifier_is_refused():
    with pytest.raises(EconError, match="not a belief"):
        a_belief(falsifier="")


def test_a_belief_with_no_mechanism_is_a_mood():
    with pytest.raises(EconError, match="a mood"):
        a_belief(mechanism="")


def test_a_belief_must_say_what_would_be_observed_before_looking():
    with pytest.raises(EconError, match="every observation confirms it"):
        a_belief(expected_observations=())


# --- append-only ------------------------------------------------------------
def test_a_revision_records_prior_basis_and_posterior():
    b = a_belief()
    moved = B.revise(b, to=0.72, basis="three vendors reported falling net "
                                       "retention", at="2026-07-01",
                     evidence_nodes=("en-1", "en-2"))
    assert moved.probability == 0.72
    assert moved.status == B.STRENGTHENED
    rev = moved.revisions[-1]
    assert (rev.prior, rev.posterior) == (0.6, 0.72)
    assert rev.basis
    # the original object is untouched
    assert b.probability == 0.6 and b.revisions == ()


def test_a_revision_without_a_basis_is_refused():
    with pytest.raises(EconError, match="states its basis"):
        B.revise(a_belief(), to=0.7, basis="  ", at="2026-07-01")


def test_the_whole_chain_survives_repeated_revision():
    b = a_belief()
    for i, p in enumerate((0.65, 0.7, 0.55)):
        b = B.revise(b, to=p, basis=f"round {i}", at=f"2026-0{7+i}-01")
    assert len(b.revisions) == 3
    assert [r.prior for r in b.revisions] == [0.6, 0.65, 0.7]
    assert b.status == B.WEAKENED


# --- preregistration --------------------------------------------------------
def an_expectation(belief=None, **kw):
    b = belief or a_belief()
    base = dict(belief=b, quantity="net_revenue_retention", direction=B.DOWN,
                confidence=0.6,
                resolution_rule="median net revenue retention across the "
                                "tracked vendors, from reported figures, at "
                                "the next quarterly close",
                at="2026-06-01", information_cutoff="2026-05-28",
                horizon_days=90, expires_at="2026-08-29")
    base.update(kw)
    return B.preregister(**base)


def test_a_prediction_cannot_use_evidence_that_arrived_after_it():
    with pytest.raises(EconError, match="after it was made"):
        an_expectation(information_cutoff="2026-06-15")


def test_a_prediction_inherits_its_mechanism_from_its_belief():
    b = a_belief()
    e = an_expectation(b)
    assert e.mechanism == b.mechanism
    assert e.falsifier == b.falsifier


def test_a_prediction_with_no_resolution_rule_is_refused():
    with pytest.raises(EconError, match="cannot be scored"):
        an_expectation(resolution_rule="")


def test_an_outcome_is_written_once():
    e = an_expectation()
    done = B.resolve(e, observed_direction=B.DOWN, at="2026-08-29")
    assert done.outcome == B.CORRECT
    with pytest.raises(EconError, match="already"):
        B.resolve(done, observed_direction=B.UP, at="2026-09-01")


def test_the_original_expectation_object_is_never_mutated():
    e = an_expectation()
    B.resolve(e, observed_direction=B.UP, at="2026-08-29")
    assert e.outcome == B.OPEN, (
        "resolving an expectation changed the object that recorded what was "
        "predicted; the ledger would hold the last opinion, not the first")


def test_a_near_miss_needs_a_tolerance_declared_in_advance():
    strict = an_expectation()
    got = B.resolve(strict, observed_direction=B.UP, at="2026-08-29",
                    miss_size=0.001)
    assert got.outcome == B.INCORRECT, (
        "a miss inside an undeclared tolerance was forgiven; the tolerance "
        "has to be preregistered or it can be chosen after the fact")
    lenient = an_expectation(tolerance=0.01)
    got = B.resolve(lenient, observed_direction=B.UP, at="2026-08-29",
                    miss_size=0.005)
    assert got.outcome == B.NEAR_MISS


def test_a_void_is_not_a_failure():
    e = an_expectation()
    got = B.void(e, at="2026-08-29", reason="the vendor stopped disclosing "
                                            "net retention")
    assert got.outcome == B.VOID
    assert got.outcome not in B.RESOLVED


def test_an_orphan_expectation_cannot_enter_the_ledger():
    ledger = B.BeliefLedger()
    with pytest.raises(EconError, match="orphan prediction"):
        ledger.add(an_expectation())


# --- fragility and decay ----------------------------------------------------
def test_fragility_is_not_the_inverse_of_probability():
    """A 0.95 belief on one source is fragile; a 0.55 on forty is not."""
    thin = a_belief(probability=0.95, evidence_for=("en-1",))
    thick = a_belief(probability=0.55,
                     evidence_for=tuple(f"en-{i}" for i in range(40)))
    assert thin.fragility > thick.fragility


def test_a_belief_past_its_decay_window_is_flagged_not_silently_moved():
    b = a_belief(decay_days=30)
    assert b.due_for_review("2026-08-01")
    assert b.probability == 0.6, (
        "the probability moved on its own; a decayed belief is FLAGGED, "
        "because silently decaying it invents a movement nobody made")


# --- calibration ------------------------------------------------------------
def _resolved(n, correct, confidence=0.7):
    b = a_belief()
    out = []
    for i in range(n):
        e = B.preregister(
            belief=b, quantity=f"q{i}", direction=B.DOWN,
            confidence=confidence,
            resolution_rule="a stated rule", at="2026-06-01",
            information_cutoff="2026-05-28", horizon_days=30,
            expires_at="2026-07-01")
        out.append(B.resolve(
            e, observed_direction=B.DOWN if i < correct else B.UP,
            at="2026-07-01"))
    return out


def test_no_accuracy_is_reported_before_the_minimum_sample():
    rep = CAL.report(_resolved(10, 7))
    assert rep.status == CAL.PRE_CALIBRATION
    assert rep.brier is None and rep.directional_accuracy is None
    assert "PRE-CALIBRATION" in rep.headline()
    assert "10" in rep.headline() and "30" in rep.headline()
    assert "%" not in rep.headline()


def test_the_minimum_is_named_in_the_output_not_buried_in_a_constant():
    rep = CAL.report(_resolved(5, 3))
    assert rep.minimum_required == CAL.MIN_RESOLVED
    assert str(CAL.MIN_RESOLVED) in rep.headline()


def test_a_sufficient_sample_reports_brier_with_a_baseline():
    rep = CAL.report(_resolved(40, 28))
    assert rep.status == CAL.CALIBRATED
    assert rep.brier is not None
    assert rep.brier_always_half is not None
    assert rep.brier_base_rate is not None
    assert rep.directional_accuracy == pytest.approx(0.7)


def test_voids_are_excluded_from_the_denominator_and_counted():
    b = a_belief()
    e = B.preregister(belief=b, quantity="q", direction=B.DOWN,
                      confidence=0.6, resolution_rule="r", at="2026-06-01",
                      information_cutoff="2026-05-28", horizon_days=30,
                      expires_at="2026-07-01")
    rep = CAL.report(_resolved(30, 20) + [B.void(e, at="2026-07-01",
                                                 reason="feed dark")])
    assert rep.resolved == 30, "a void entered the scored denominator"
    assert rep.voided == 1


def test_prose_claiming_accuracy_is_refused_before_calibration():
    rep = CAL.report(_resolved(5, 4))
    with pytest.raises(ValueError, match="PRE_CALIBRATION"):
        CAL.assert_no_unsupported_claim(
            "our directional accuracy has been strong this quarter", rep)


def test_the_same_prose_is_permitted_once_the_sample_supports_it():
    rep = CAL.report(_resolved(40, 28))
    CAL.assert_no_unsupported_claim("directional accuracy 70%", rep)
