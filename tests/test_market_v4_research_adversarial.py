"""Attacks on the research-observability layer, one per way it could flatter itself.

J-ADV-001. The 27 attacks in `test_market_v4_adversarial.py` are on the
economic layers — whether a story that looks like a finding is promoted. These
are on the layer that measures the ENGINE: the log of what it chose to look up,
what came back, and what that was worth.

That layer has a distinctive failure mode. Every one of these attacks makes the
engine look BETTER than it was, and every one of them does so by removing
information rather than by adding a false claim — an empty result omitted, a
menu rebuilt after the fact, an unmeasured term recorded as a measured zero. A
rate computed over a log with the failures missing is not a slightly optimistic
rate; it is a rate about a different population.
"""
from __future__ import annotations

import pytest

from intent_engine.market import economic_thesis as ET
from intent_engine.market import internal_state as IS
from intent_engine.market import knowledge_effect as KE
from intent_engine.market import research_decision as RD
from intent_engine.market import research_policy as RP


def candidate(family="edgar", **kw):
    return RD.CandidateAction(source_family=family, **kw)


def decision(**kw):
    base = dict(subject="ACME", question_type="exposure",
                chosen_action="edgar", candidates=(candidate(),),
                selection_policy="voi", chosen_at="2026-08-09")
    base.update(kw)
    return RD.ResearchDecision(**base)


def record(outcome, *, action_cost=1.0, reconstructed=False):
    return RP.ResearchRecord(
        action=RP.ResearchAction(source_family="regulatory_filing",
                                 subject="ACME", cost=action_cost),
        outcome=outcome, at="2026-08-09", reconstructed=reconstructed)


# --- 28. the empty result that never gets logged ----------------------------

def test_an_action_that_found_nothing_cannot_be_called_a_success():
    """THE CENTRAL ONE. An acquisition that retrieved documents and accepted
    no evidence is NO_RESULT. Recording it as SUCCESS is how the yield rate
    becomes a statement about the actions that happened to work."""
    with pytest.raises(RD.DecisionRejected):
        RD.DecisionOutcome(decision_id="d1", status=RD.SUCCESS,
                           documents_retrieved=4, accepted_evidence=0)


def test_an_empty_handed_action_is_still_a_row():
    """It must be loggable — the defect is calling it a success, not
    recording it. A layer that refused the row entirely would drop the
    failures just as effectively."""
    got = RD.DecisionOutcome(decision_id="d1", status=RD.NO_RESULT,
                             documents_retrieved=4, accepted_evidence=0)
    assert got.empty_handed


def test_a_failure_must_name_its_kind():
    """An unrecognised failure is the only information a failed action
    carries, and a blank one is indistinguishable from a quiet source."""
    with pytest.raises(RD.DecisionRejected):
        RD.DecisionOutcome(decision_id="d1", status=RD.FAILED)


# --- 29. the choice set rebuilt after the outcome ---------------------------

def test_a_decision_with_no_menu_is_refused():
    """A choice nobody can check. Without the options, "it picked the best
    one" is unfalsifiable."""
    with pytest.raises(RD.DecisionRejected):
        decision(candidates=())


def test_an_excluded_family_must_say_why_it_was_excluded():
    """An unexplained exclusion is indistinguishable from a family the
    planner never thought of, and those score very differently."""
    with pytest.raises(RD.DecisionRejected):
        RD.CandidateAction(source_family="edgar", eligible=False)


def test_a_family_cannot_be_eligible_and_refused_at_once():
    with pytest.raises(RD.DecisionRejected):
        RD.CandidateAction(source_family="edgar", eligible=False,
                           refusal_reason="")


def test_a_reconstructed_record_cannot_claim_to_know_the_menu():
    """A log rebuilt from surviving evidence cannot know what else was
    available — the actions that produced nothing left no trace to rebuild
    from."""
    got = RP.ResearchRecord(
        action=RP.ResearchAction(source_family="regulatory_filing",
                                 subject="ACME"),
        outcome=RP.ResearchOutcome(outcome=RP.USED), at="2026-08-09",
        reconstructed=True)
    assert got.reconstructed
    assert not got.eligible_options


# --- 30. the invented propensity --------------------------------------------

def test_a_deterministic_choice_may_not_record_a_propensity():
    """1.0 is not "certainly chosen"; it is the claim that this log can feed
    an inverse-propensity estimator, and it cannot."""
    with pytest.raises(RD.DecisionRejected):
        decision(selection_probability=1.0,
                 selection_probability_status=RD.DETERMINISTIC)


def test_a_known_propensity_needs_a_real_number():
    with pytest.raises(RD.DecisionRejected):
        decision(selection_probability=None,
                 selection_probability_status=RD.KNOWN)
    with pytest.raises(RD.DecisionRejected):
        decision(selection_probability=0.0,
                 selection_probability_status=RD.KNOWN)


def test_reconstructed_and_prospective_are_never_pooled():
    """A causal estimate over a mixed log is an estimate about neither."""
    rows = [decision(provenance=RD.PROSPECTIVE),
            decision(provenance=RD.RECONSTRUCTED)]
    split = RD.split_by_provenance(rows)
    assert len(split[RD.PROSPECTIVE]) == 1
    assert len(split[RD.RECONSTRUCTED]) == 1
    standing = RD.evaluation_standing(rows)
    assert standing["reconstructed"] == 1
    assert standing["prospective"] == 1


# --- 31. the volume hack ----------------------------------------------------

def test_duplicates_cannot_be_farmed_into_a_better_score():
    """Re-fetching a fact already held is the cheapest way to raise a count,
    so the reward has to price it below doing nothing."""
    fresh = RP.reward(record(RP.ResearchOutcome(
        outcome=RP.USED, independent=True, resolved_open_question=True)))
    repeat = RP.reward(record(RP.ResearchOutcome(
        outcome=RP.USED, independent=True, resolved_open_question=True,
        duplicate=True)))
    assert repeat < fresh


def test_one_discriminating_answer_beats_a_pile_of_agreeing_ones():
    """The term a confirmation-seeking policy cannot farm."""
    discriminating = RP.reward(record(RP.ResearchOutcome(
        outcome=RP.USED, discriminating=True)))
    agreeing = RP.reward(record(RP.ResearchOutcome(outcome=RP.USED)))
    assert discriminating > agreeing


# --- 32. the expensive source that answers nothing --------------------------

def test_cost_is_priced_even_when_the_action_succeeds():
    cheap = RP.reward(record(RP.ResearchOutcome(outcome=RP.USED),
                             action_cost=1.0))
    dear = RP.reward(record(RP.ResearchOutcome(outcome=RP.USED),
                            action_cost=10.0))
    assert dear < cheap


def test_a_failed_expensive_action_is_worse_than_a_failed_cheap_one():
    cheap = RP.reward(record(RP.ResearchOutcome(outcome=RP.FAILED),
                             action_cost=1.0))
    dear = RP.reward(record(RP.ResearchOutcome(outcome=RP.FAILED),
                            action_cost=10.0))
    assert dear < cheap


# --- 33. the easy source that only confirms ---------------------------------

def test_an_unmeasured_discriminating_term_earns_nothing():
    """None is UNMEASURED. Coercing it to False would make "we cannot tell"
    indistinguishable from "we checked and it did not", and coercing it to
    True would pay for a measurement nobody made."""
    unmeasured = RP.reward(record(RP.ResearchOutcome(
        outcome=RP.USED, discriminating=None)))
    negative = RP.reward(record(RP.ResearchOutcome(
        outcome=RP.USED, discriminating=False)))
    assert unmeasured == negative


def test_a_dependent_source_is_not_a_second_opinion():
    """Three outlets repeating one press release is one source, and the
    independence term is what a cheap-source policy would otherwise farm."""
    independent = RP.reward(record(RP.ResearchOutcome(
        outcome=RP.USED, independent=True)))
    dependent = RP.reward(record(RP.ResearchOutcome(
        outcome=RP.USED, independent=False)))
    assert independent > dependent


# --- 34. the effect attributed to an unrelated hypothesis -------------------

def test_an_effect_that_changed_nothing_is_refused_as_a_change():
    """An object the evidence was merely ABOUT has not been changed by it,
    and the honest record is NO_CHANGE. This is the attribution that inflates
    every knowledge-yield number in the engine."""
    with pytest.raises(KE.NotAChange):
        KE.KnowledgeEffect(
            evidence_id="ev1", target_type=KE.HYPOTHESIS, target_id="h1",
            effect_type=KE.SUPPORTED, before_state="SUPPORTED",
            after_state="SUPPORTED", reason="the filing mentions it")


def test_a_change_must_name_the_object_it_changed():
    with pytest.raises(KE.EffectRejected):
        KE.KnowledgeEffect(
            evidence_id="ev1", target_type=KE.HYPOTHESIS, target_id="",
            effect_type=KE.SUPPORTED, before_state="PROPOSED",
            after_state="SUPPORTED", reason="a filing")


def test_an_effect_must_name_the_evidence_that_caused_it():
    """Without it the effect cannot price a research action, which is the
    only reason the record exists."""
    with pytest.raises(KE.EffectRejected):
        KE.KnowledgeEffect(
            evidence_id="", target_type=KE.HYPOTHESIS, target_id="h1",
            effect_type=KE.SUPPORTED, before_state="PROPOSED",
            after_state="SUPPORTED", reason="a filing")


def test_an_unexplained_attribution_cannot_be_audited():
    with pytest.raises(KE.EffectRejected):
        KE.KnowledgeEffect(
            evidence_id="ev1", target_type=KE.HYPOTHESIS, target_id="h1",
            effect_type=KE.SUPPORTED, before_state="PROPOSED",
            after_state="SUPPORTED", reason="   ")


def test_no_change_is_a_first_class_record():
    """The counterpart. If NO_CHANGE were unloggable the only way to record
    reading a document would be to claim it changed something."""
    got = KE.no_change("ev1", reason="the filing repeats a known fact")
    assert got.effect_type == KE.NO_CHANGE


# --- 35. synthetic and live, mixed --------------------------------------

def test_a_demonstration_figure_cannot_join_a_real_conclusion():
    """A synthetic record is harmless while it is labelled and sitting in a
    demo. It becomes a fabrication the moment it shares a briefing with a
    real company's real economics."""
    with pytest.raises(IS.SyntheticLeak):
        IS.assert_no_synthetic(IS.synthetic_enterprise(),
                               context="a live briefing")


def test_the_synthetic_company_is_named_so_it_cannot_be_mistaken():
    assert "SYNTHETIC" in IS.SYNTHETIC_COMPANY


# --- 36. trading P&L validating a mechanism ---------------------------------

def test_a_correct_outcome_does_not_validate_the_reasoning():
    """The most expensive confusion available to this engine: a position that
    paid does not mean the mechanism was right, and a thesis credited for a
    lucky outcome will be wrong again the same way."""
    mech = ET.Mechanism(description="tariffs raise landed cost",
                        falsifier="landed cost does not move in 90 days",
                        key="k")
    alt = ET.Mechanism(description="the exposure was hedged",
                       falsifier="the company states a hedge", key="a")
    thesis = ET.EconomicThesis(
        subject="ACME", question="do costs rise?", claim="costs rise",
        leading_mechanism=mech, alternatives=(alt,), as_of="2026-08-09",
        standing=ET.PROPOSED, supporting_evidence=("ev1",))
    score = ET.score(thesis, outcome_matched=True,
                     mechanism_matched=False)
    assert score.verdict == ET.RIGHT_FOR_THE_WRONG_REASON
    assert score.verdict != "CORRECT"


def test_an_unchecked_mechanism_is_not_a_confirmed_one():
    mech = ET.Mechanism(description="tariffs raise landed cost",
                        falsifier="landed cost does not move in 90 days",
                        key="k")
    alt = ET.Mechanism(description="the exposure was hedged",
                       falsifier="the company states a hedge", key="a")
    thesis = ET.EconomicThesis(
        subject="ACME", question="do costs rise?", claim="costs rise",
        leading_mechanism=mech, alternatives=(alt,), as_of="2026-08-09",
        standing=ET.PROPOSED, supporting_evidence=("ev1",))
    score = ET.score(thesis, outcome_matched=True,
                     mechanism_matched=None)
    assert score.verdict == "OUTCOME_ONLY"
