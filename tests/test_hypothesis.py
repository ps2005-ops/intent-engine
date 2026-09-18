"""Hypotheses — the unit that accumulates, and the axis decision quality
cannot express.

The load-bearing cases are the two MIXED outcomes: a correct hypothesis with a
losing decision, and a refuted hypothesis with a winning one. Those are the
whole reason the decision record was insufficient.
"""
from intent_engine.market.hypothesis import (
    BASELINE_HYPOTHESIS,
    INCONCLUSIVE,
    REFUTED,
    SUPPORTED,
    Hypothesis,
    assess_hypothesis,
    expected_information_gain,
    rank_by_information,
    revise,
    should_retire,
)


def _h(**kw):
    base = dict(hypothesis_id="h1", statement="a claim", confidence=0.5)
    base.update(kw)
    return Hypothesis(**base)


# --- the distinction the decision record could not make ----------------------
def test_a_correct_hypothesis_with_a_losing_decision_is_a_timing_problem():
    """Three losing BUYs whose reasoning was right is a timing problem. Three
    whose reasoning was refuted is a reasoning problem. Opposite responses."""
    q = assess_hypothesis(_h(), decision_correct=False,
                          predicted_observable_occurred=True)
    assert q.verdict == SUPPORTED and q.decision_correct is False
    assert "timing or execution" in q.diagnosis


def test_being_right_for_the_wrong_reason_is_named_as_such():
    """The most dangerous outcome: counting it as a success rewards bad
    reasoning."""
    q = assess_hypothesis(_h(), decision_correct=True,
                          predicted_observable_occurred=False)
    assert q.verdict == REFUTED and q.decision_correct is True
    assert "right for the wrong reason" in q.diagnosis


def test_the_hypothesis_observable_decides_when_it_names_one():
    """A trade can pay for reasons the hypothesis never claimed, so the
    observable outranks the outcome."""
    supported = assess_hypothesis(_h(), decision_correct=False,
                                  predicted_observable_occurred=True)
    refuted = assess_hypothesis(_h(), decision_correct=True,
                                predicted_observable_occurred=False)
    assert supported.verdict == SUPPORTED
    assert refuted.verdict == REFUTED


def test_without_an_outcome_it_is_inconclusive_not_a_guess():
    assert assess_hypothesis(_h(), decision_correct=None).verdict \
        == INCONCLUSIVE


# --- belief revision ---------------------------------------------------------
def test_confidence_moves_and_records_what_moved_it():
    """The engine must not merely accumulate outcomes; it must say what changed
    its mind and by how much."""
    h = revise(_h(), SUPPORTED, at="2026-07-30", evidence="price rose")
    assert h.confidence > 0.5 and h.tested == 1 and h.supported == 1
    revision = h.revisions[-1]
    assert revision.confidence_before == 0.5
    assert revision.confidence_after == h.confidence
    assert revision.reason and revision.evidence == "price rose"


def test_refutation_lowers_confidence():
    h = revise(_h(), REFUTED, at="2026-07-30")
    assert h.confidence < 0.5 and h.refuted == 1


def test_confidence_never_reaches_certainty():
    """A hypothesis that cannot be moved by evidence has stopped being one."""
    h = _h(confidence=0.5)
    for _ in range(50):
        h = revise(h, SUPPORTED, at="d")
    assert h.confidence <= 0.95
    for _ in range(100):
        h = revise(h, REFUTED, at="d")
    assert h.confidence >= 0.05


def test_an_inconclusive_test_counts_as_tested_but_moves_nothing():
    h = revise(_h(), INCONCLUSIVE, at="d")
    assert h.tested == 1 and h.confidence == 0.5 and h.revisions == ()


# --- retirement --------------------------------------------------------------
def test_a_hypothesis_is_not_retired_on_a_losing_streak():
    """Retirement claims the idea is wrong and needs the sample size any other
    claim would. Killing a correct hypothesis after three unlucky outcomes is
    the failure this guards."""
    h = _h()
    for _ in range(3):
        h = revise(h, REFUTED, at="d")
    assert h.support_rate == 0.0
    assert should_retire(h) is False


def test_a_hypothesis_is_retired_on_sustained_evidence():
    h = _h()
    for _ in range(12):
        h = revise(h, REFUTED, at="d")
    assert should_retire(h) is True


# --- expected information gain ----------------------------------------------
def test_an_uncertain_hypothesis_is_worth_more_than_a_settled_one():
    """A prediction can be worth making while being a coin flip."""
    assert expected_information_gain(_h(confidence=0.5)) > \
        expected_information_gain(_h(confidence=0.9))


def test_the_first_test_of_an_idea_is_worth_more_than_the_fortieth():
    assert expected_information_gain(_h(tested=0)) > \
        expected_information_gain(_h(tested=40))


def test_a_retired_hypothesis_is_worth_nothing_to_test():
    assert expected_information_gain(_h(retired=True)) == 0.0


def test_ranking_prefers_the_untested_over_the_repeated():
    """With sample size binding, this is the difference between reaching n=30
    usefully and reaching it thirty times over on one idea."""
    fresh = _h(hypothesis_id="fresh", tested=0)
    worn = _h(hypothesis_id="worn", tested=25)
    prior = [{"hypothesis_id": "worn"} for _ in range(25)]
    assert rank_by_information([worn, fresh], prior)[0].hypothesis_id == "fresh"


# --- the baseline's hypothesis, stated out loud ------------------------------
def test_the_baseline_signal_carries_an_explicit_hypothesis():
    """It was always asserting one; leaving it implicit is what made "was the
    trade wrong or the idea wrong?" unanswerable."""
    assert BASELINE_HYPOTHESIS.statement
    assert BASELINE_HYPOTHESIS.prediction
    assert 0.5 <= BASELINE_HYPOTHESIS.confidence <= 0.6
