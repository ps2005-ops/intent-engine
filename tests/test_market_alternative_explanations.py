"""An LLM may propose. The engine owns everything else.

The safety property under test is narrow and absolute: nothing a model
suggested can be presented as an alternative until the engine has validated
it. Every other test here is about the four things a string could never do —
identity, accumulation, testing, retirement.
"""
from __future__ import annotations

import pytest

from intent_engine.market import alternative_explanations as AE


def proposal(**overrides):
    kwargs = dict(
        subject="acme", claim="a sector-wide shift moved both",
        applies_to=("causal_episode",),
        expected_observations=("the same movement at unrelated companies",),
        falsifier="the movement is confined to this company")
    kwargs.update(overrides)
    return AE.propose(**kwargs)


# --- an alternative must predict -----------------------------------------

def test_an_alternative_that_predicts_nothing_is_refused():
    with pytest.raises(AE.AlternativeRejected, match="offered forever"):
        proposal(expected_observations=())


def test_an_alternative_with_no_falsifier_is_refused():
    with pytest.raises(AE.AlternativeRejected, match="would break it"):
        proposal(falsifier="  ")


def test_an_alternative_that_restates_its_rival_is_refused():
    with pytest.raises(AE.AlternativeRejected, match="restates"):
        proposal(claim="demand is strengthening",
                 competes_with="Demand is strengthening.")


def test_an_alternative_expecting_its_rivals_claim_is_refused():
    with pytest.raises(AE.AlternativeRejected, match="separate them"):
        proposal(competes_with="revenue rises again",
                 expected_observations=("revenue rises again",))


# --- the safety property --------------------------------------------------

def test_a_proposal_is_never_born_validated():
    assert proposal().validation_status == AE.PROPOSED
    assert proposal().is_offerable is False


def test_an_unvalidated_llm_proposal_is_never_offered():
    store = AE.AlternativeStore()
    raw = proposal(source=AE.LLM_PROPOSED)
    assert raw.validation_status == AE.PROPOSED
    assert store.offerable() == ()          # never stored, never offered
    assert len(store) == 0


def test_validation_is_the_only_route_to_being_offerable():
    store = AE.AlternativeStore()
    got = AE.accept_llm_proposal(
        store, subject="acme", claim="a currency effect moved the figure",
        applies_to=("causal_episode",),
        expected_observations=("constant-currency growth is flat",),
        falsifier="the move persists in constant currency",
        model="test-model")
    assert got.validation_status == AE.VALIDATED
    assert got.source == AE.LLM_PROPOSED
    assert got.provenance["proposed_by"] == "test-model"
    assert [r.explanation_id for r in store.offerable()] == \
        [got.explanation_id]


def test_a_retired_alternative_is_not_offered_however_validated():
    store = AE.AlternativeStore()
    got = store.validate(proposal())
    for _ in range(AE.RETIRE_AFTER_RULED_OUT):
        store.record_test(got.explanation_id, survived=False)
    assert store.get(got.explanation_id).standing == AE.RETIRED
    assert store.offerable() == ()


# --- identity: the same idea is the same record --------------------------

def test_two_wordings_of_one_claim_are_one_record():
    a = proposal(claim="A sector-wide shift moved both.")
    b = proposal(claim="both were moved by a shift that was sector wide")
    assert a.explanation_id == b.explanation_id


def test_a_second_proposal_of_a_held_claim_is_superseded_not_stored_twice():
    store = AE.AlternativeStore()
    store.validate(proposal(applies_to=("causal_episode",)))
    again = store.validate(proposal(applies_to=("economic_chain",),
                                    source=AE.LLM_PROPOSED))
    assert again.validation_status == AE.SUPERSEDED
    assert len(store) == 1
    # And the context accumulates onto the record that was already held.
    held = store.all()[0]
    assert set(held.applies_to) == {"causal_episode", "economic_chain"}


# --- testing and retirement are by evidence, never by assertion ----------

def test_standing_moves_only_through_recorded_tests():
    store = AE.AlternativeStore()
    got = store.validate(proposal())
    assert got.standing == AE.UNTESTED
    store.record_test(got.explanation_id, survived=True, evidence_id="ev_1")
    assert store.get(got.explanation_id).standing == AE.SURVIVING
    store.record_test(got.explanation_id, survived=False, evidence_id="ev_2")
    assert store.get(got.explanation_id).standing == AE.CONTESTED


def test_evidence_lands_on_the_side_that_earned_it():
    store = AE.AlternativeStore()
    got = store.validate(proposal())
    store.record_test(got.explanation_id, survived=True, evidence_id="ev_up")
    store.record_test(got.explanation_id, survived=False,
                      evidence_id="ev_down")
    held = store.get(got.explanation_id)
    assert held.supporting_evidence == ("ev_up",)
    assert held.contradicting_evidence == ("ev_down",)


def test_one_failure_is_an_exception_and_two_is_a_refutation():
    store = AE.AlternativeStore()
    got = store.validate(proposal())
    store.record_test(got.explanation_id, survived=False, subject="a")
    assert store.get(got.explanation_id).standing == AE.RULED_OUT
    store.record_test(got.explanation_id, survived=False, subject="b")
    assert store.get(got.explanation_id).standing == AE.RETIRED


def test_there_is_no_way_to_set_a_standing_directly():
    import inspect
    signature = inspect.signature(AE.AlternativeStore.record_test)
    assert "standing" not in signature.parameters
    assert set(signature.parameters) == {
        "self", "explanation_id", "survived", "evidence_id", "subject"}


# --- the migration --------------------------------------------------------

def test_the_engines_own_string_constants_become_records():
    from intent_engine.market import causal_episodes as CE

    store = AE.AlternativeStore()
    migrated = [store.validate(p) for p in AE.from_engine_constants()]
    assert len(migrated) == 2
    assert all(m.source == AE.ENGINE for m in migrated)
    claims = {m.claim for m in migrated}
    assert CE.COMMON_CAUSE in claims and CE.REPORTING_ARTEFACT in claims
    # Each now predicts something, which the constants never did.
    assert all(m.expected_observations and m.falsifier for m in migrated)
    assert len(store.offerable(context="causal_episode")) == 2
    assert len(store.offerable(context="counterfactual_memory")) == 1


def test_the_summary_separates_proposed_from_offerable():
    store = AE.AlternativeStore()
    for p in AE.from_engine_constants():
        store.validate(p)
    AE.accept_llm_proposal(
        store, subject="acme", claim="an inventory build inflated the figure",
        applies_to=("economic_chain",),
        expected_observations=("inventory days rise in the same period",),
        falsifier="inventory days are flat")
    got = store.summarise()
    assert got["alternatives"] == 3
    assert got["by_source"] == {AE.ENGINE: 2, AE.LLM_PROPOSED: 1}
    assert got["by_validation"] == {AE.VALIDATED: 3}
    assert got["offerable"] == 3
    assert got["llm_proposed_not_yet_validated"] == 0
