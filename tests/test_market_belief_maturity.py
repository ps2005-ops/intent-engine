"""Belief maturity — and the distinction that must never collapse.

STALE means time passed and nothing argued either way. WEAKENING means later
evidence argued against it. They call for opposite responses: one needs a
test, the other has already had one.
"""
import pytest
from intent_engine.market import belief_maturity as BM


def _rows(confirmations=0, contradictions=0, subjects=None, declared="2026-08-01"):
    subjects = subjects or ["acme"] * (confirmations + contradictions)
    rows = [{"record": "belief", "belief_id": "b1", "subject": "acme",
             "proposition": "demand is strengthening", "last_updated": declared,
             "lifecycle_state": "ACTIVE"},
            {"record": "expectation", "expectation_id": "e1",
             "hypothesis_id": "b1", "subject": "acme", "metric": "demand_strengthening",
             "expected_event": "the next reported revenue figure",
             "preregistered_at": declared}]
    outcomes = ["CONFIRMED"] * confirmations + ["CONTRADICTED"] * contradictions
    for i, o in enumerate(outcomes):
        rows.append({"record": "reconciliation", "expectation_id": "e1",
                     "hypothesis_id": "b1", "outcome": o,
                     "subject": subjects[i], "evaluated_at": "2026-08-06"})
    return rows


def _one(**kw):
    return BM.classify(_rows(**kw), as_of="2026-08-08")[0]


def test_stale_and_weakening_are_never_merged():
    stale = _one(declared="2026-01-01")
    weak = _one(contradictions=1)
    assert stale.state == BM.STALE
    assert weak.state == BM.WEAKENING
    assert "nothing argued" in stale.reason or "never tested" in stale.reason
    assert "argued against" in weak.reason


def test_a_tested_belief_is_never_stale_however_old():
    """Something argued about it; that is the opposite of nothing happening."""
    assert _one(confirmations=1, declared="2020-01-01").state != BM.STALE


def test_age_alone_never_promotes():
    assert _one(declared="2020-01-01").state == BM.STALE


def test_one_subject_agreeing_with_itself_is_not_repeated_support():
    assert _one(confirmations=3, subjects=["acme"] * 3).state == BM.SUPPORTED


def test_independent_subjects_earn_repeated_support():
    assert _one(confirmations=2, subjects=["acme", "wayne"]).state == \
        BM.REPEATEDLY_SUPPORTED


def test_both_directions_is_contested():
    assert _one(confirmations=1, contradictions=1).state == BM.CONTESTED


def test_an_untested_recent_belief_is_a_candidate():
    assert _one().state == BM.CANDIDATE


def test_a_retired_belief_stays_retired():
    rows = _rows(confirmations=2, subjects=["a", "b"])
    rows[0]["lifecycle_state"] = "RETIRED"
    assert BM.classify(rows, as_of="2026-08-08")[0].state == BM.RETIRED


def test_maturity_vocabulary_is_closed():
    for kw in ({}, {"confirmations": 1}, {"contradictions": 5},
               {"declared": "2019-01-01"}):
        assert _one(**kw).state in BM.STATES


def test_every_belief_says_what_would_revalidate_it():
    assert _one().what_would_revalidate
