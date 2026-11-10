"""An action is not an objective, and one response is not a habit.

Both modules exist to refuse a specific promotion. Objectives refuse turning
an observed action into a stated motive; response memory refuses turning one
episode into a behavioural trait.
"""
from __future__ import annotations

import pytest

from intent_engine.market import actor_response_memory as ARM
from intent_engine.market import strategic_objectives as SO


def objective(**overrides):
    kwargs = dict(
        actor="Shopify", objective="taking share from Magento in mid-market",
        action="published a migration case study naming Magento",
        affected_actor="Magento",
        alternative_objectives=(
            "ordinary marketing with no competitive intent",
            "recruiting agencies rather than merchants"),
        falsifier="no further migration content, and Magento merchants are "
                  "not targeted in the next campaign",
        expected_next_action="further named-competitor migration content "
                             "within two quarters")
    kwargs.update(overrides)
    return SO.hypothesise(**kwargs)


# --- an action is not an objective ---------------------------------------

def test_one_alternative_is_not_enough():
    with pytest.raises(SO.ObjectiveRejected, match="asserts a motive"):
        objective(alternative_objectives=("marketing",))


def test_an_objective_that_predicts_nothing_is_refused():
    with pytest.raises(SO.ObjectiveRejected, match="cannot be wrong"):
        objective(expected_next_action="  ")


def test_an_objective_with_no_observed_action_is_a_guess():
    with pytest.raises(SO.ObjectiveRejected, match="guess about a company"):
        objective(action="")


def test_every_hypothesis_is_born_weak():
    assert objective().standing == SO.WEAK


def test_there_is_no_argument_that_opens_one_higher():
    import inspect
    assert "standing" not in inspect.signature(SO.hypothesise).parameters


def test_the_record_says_the_reason_is_not_observed():
    assert "the reason is not" in objective().as_dict()["caution"]


# --- promotion is by the preregistered next action ------------------------

def test_a_held_prediction_makes_it_plausible_then_supported():
    got = SO.score(objective(), held=True, evidence_id="ev_1")
    assert got.standing == SO.PLAUSIBLE
    assert SO.score(got, held=True, evidence_id="ev_2").standing == SO.SUPPORTED


def test_a_broken_prediction_leaves_it_weak_and_records_the_evidence():
    got = SO.score(objective(), held=False, evidence_id="ev_bad")
    assert got.standing == SO.WEAK
    assert got.contradicting_evidence == ("ev_bad",)


def test_evidence_on_both_sides_is_contested():
    got = SO.score(objective(), held=True, evidence_id="ev_1")
    assert SO.score(got, held=False, evidence_id="ev_2").standing == \
        SO.CONTESTED


# --- one response is not a habit ------------------------------------------

def episode(response=ARM.MATCHED, context="mid-market ecommerce",
            delay=30, evidence=("ev_1",)):
    return ARM.observe(actor="Shopify", trigger_type="rival price cut",
                       response_type=response, delay_days=delay,
                       outcome="price held", evidence=evidence,
                       context=context)


def test_one_episode_is_a_candidate_and_says_its_count():
    got = episode()
    assert got.standing == ARM.CANDIDATE
    assert got.repeat_count == 1
    assert "one episode is a CANDIDATE" in got.as_dict()["caution"]


def test_a_response_with_no_delay_is_unfalsifiable_and_refused():
    with pytest.raises(ARM.PatternRejected, match="unfalsifiable"):
        episode(delay=None)


def test_a_non_response_needs_no_delay_because_it_is_still_evidence():
    got = ARM.observe(actor="Shopify", trigger_type="rival price cut",
                      response_type=ARM.NO_OBSERVED_RESPONSE, delay_days=None,
                      outcome="nothing observed", evidence=("ev_1",),
                      context="mid-market")
    assert got.standing == ARM.CANDIDATE


def test_a_response_with_no_evidence_is_a_recollection():
    with pytest.raises(ARM.PatternRejected, match="recollection"):
        episode(evidence=())


def test_two_comparable_episodes_are_only_emerging():
    got = ARM.merge(episode(), episode(context="enterprise",
                                       evidence=("ev_2",)))
    assert got.standing == ARM.EMERGING
    assert got.repeat_count == 2


def test_a_pattern_needs_three_episodes_across_two_contexts():
    got = ARM.merge(episode(), episode(context="enterprise",
                                       evidence=("ev_2",)))
    got = ARM.merge(got, episode(context="enterprise", evidence=("ev_3",)))
    assert got.standing == ARM.PATTERN
    assert len(got.contexts) == 2


def test_three_episodes_in_one_context_do_not_make_a_pattern():
    got = episode()
    for i in (2, 3):
        got = ARM.merge(got, episode(evidence=(f"ev_{i}",)))
    assert got.repeat_count == 3
    assert got.standing == ARM.EMERGING


def test_a_different_response_contradicts_rather_than_accumulates():
    """Matched once, countered once: that is not a habit, it is noise."""
    got = ARM.merge(episode(ARM.MATCHED),
                    episode(ARM.COUNTERED, evidence=("ev_2",)))
    assert got.standing == ARM.CONTRADICTED
    assert got.repeat_count == 1


def test_incomparable_episodes_are_refused():
    other = ARM.observe(actor="Stripe", trigger_type="rival price cut",
                        response_type=ARM.MATCHED, delay_days=10,
                        outcome="x", evidence=("ev_2",), context="payments")
    with pytest.raises(ARM.PatternRejected, match="not comparable"):
        ARM.merge(episode(), other)


def test_only_promoted_patterns_are_counted_as_usable():
    got = ARM.summarise([episode()])
    assert got["usable_patterns"] == 0
    assert got["by_standing"][ARM.CANDIDATE] == 1
