"""The choice written before the call: the menu, the propensity, the ordering."""
from __future__ import annotations

import pytest

from intent_engine.market import research_decision as RD
from intent_engine.market import research_policy as RP


def candidate(family=RP.INDEPENDENT_REPORTING, *, eligible=True, reason="",
              voi=0.5, cost=1.0, latency=0.0, strategy="newsroom_sweep"):
    return RD.CandidateAction(
        source_family=family, query_strategy=strategy, estimated_cost=cost,
        estimated_latency=latency, expected_voi=voi, eligible=eligible,
        refusal_reason=reason)


def decision(chosen=RP.INDEPENDENT_REPORTING, *, candidates=None,
             policy="FIXED", at="2026-08-09T00:00:00", probability=None,
             status=RD.DETERMINISTIC, provenance=RD.PROSPECTIVE,
             subject="acme", qtype="NEEDS_COMPETITOR"):
    if candidates is None:
        candidates = (candidate(RP.INDEPENDENT_REPORTING),
                      candidate(RP.REGULATORY_FILING, voi=0.9))
    return RD.ResearchDecision(
        subject=subject, question_type=qtype, chosen_action=chosen,
        candidates=tuple(candidates), selection_policy=policy,
        chosen_at=at, selection_probability=probability,
        selection_probability_status=status, provenance=provenance)


def outcome(decision_id, status=RD.SUCCESS, *, started="2026-08-09T00:00:01",
            accepted=1, failure=""):
    return RD.DecisionOutcome(
        decision_id=decision_id, status=status, started_at=started,
        accepted_evidence=accepted, failure_type=failure)


# --- the choice-set wall -------------------------------------------------------

def test_a_chosen_action_must_be_in_its_own_candidate_set():
    with pytest.raises(RD.DecisionRejected) as err:
        decision(chosen=RP.GOVERNMENT_DATA)
    assert "not in its own candidate set" in str(err.value)


def test_a_chosen_action_recorded_as_ineligible_is_refused():
    """The menu assembled after the fact so it contains the winner."""
    with pytest.raises(RD.DecisionRejected) as err:
        decision(chosen=RP.REGULATORY_FILING,
                 candidates=(candidate(RP.INDEPENDENT_REPORTING),
                             candidate(RP.REGULATORY_FILING, eligible=False,
                                       reason="not due today")))
    assert "recorded as ineligible" in str(err.value)


def test_a_decision_with_no_candidates_is_refused():
    with pytest.raises(RD.DecisionRejected) as err:
        decision(candidates=())
    assert "no candidate set" in str(err.value)


def test_a_decision_where_nothing_was_eligible_is_not_a_decision():
    with pytest.raises(RD.DecisionRejected) as err:
        RD.ResearchDecision(
            subject="acme", question_type="Q", chosen_action="",
            candidates=(candidate(RP.REGULATORY_FILING, eligible=False,
                                  reason="cadence"),),
            selection_policy="FIXED")
    assert "no candidate was eligible" in str(err.value)


def test_an_excluded_candidate_must_say_why():
    with pytest.raises(RD.DecisionRejected) as err:
        candidate(RP.REGULATORY_FILING, eligible=False)
    assert "without a stated reason" in str(err.value)


def test_an_eligible_candidate_may_not_also_carry_a_refusal():
    with pytest.raises(RD.DecisionRejected) as err:
        candidate(RP.REGULATORY_FILING, eligible=True, reason="cadence")
    assert "eligible and also carries a refusal reason" in str(err.value)


def test_the_forgone_arm_is_what_was_eligible_and_not_taken():
    got = decision()
    assert got.eligible_families == (RP.INDEPENDENT_REPORTING,
                                     RP.REGULATORY_FILING)
    assert got.forgone == (RP.REGULATORY_FILING,)


def test_an_ineligible_option_is_not_forgone():
    """A cadence-blocked family was not a road not taken; it was closed."""
    got = decision(candidates=(
        candidate(RP.INDEPENDENT_REPORTING),
        candidate(RP.REGULATORY_FILING, eligible=False,
                  reason="not due today")))
    assert got.forgone == ()
    assert len(got.candidates) == 2, "the closed road is still recorded"


# --- the propensity wall -------------------------------------------------------

def test_a_deterministic_policy_may_not_claim_a_propensity():
    with pytest.raises(RD.DecisionRejected) as err:
        decision(probability=1.0, status=RD.DETERMINISTIC)
    assert "misrepresent the log as explored" in str(err.value)


def test_an_unavailable_propensity_may_not_carry_a_number():
    with pytest.raises(RD.DecisionRejected):
        decision(probability=0.5, status=RD.UNAVAILABLE)


def test_a_known_propensity_needs_an_actual_probability():
    with pytest.raises(RD.DecisionRejected) as err:
        decision(probability=None, status=RD.KNOWN)
    assert "needs a probability" in str(err.value)


def test_a_known_propensity_outside_the_unit_interval_is_refused():
    for bad in (0.0, -0.1, 1.5):
        with pytest.raises(RD.DecisionRejected):
            decision(probability=bad, status=RD.KNOWN)


def test_a_randomising_policy_records_its_probability():
    got = decision(probability=0.25, status=RD.KNOWN)
    assert got.selection_probability == 0.25


# --- outcomes, including the empty ones ----------------------------------------

def test_no_result_is_a_first_class_outcome():
    got = outcome("rd_x", RD.NO_RESULT, accepted=0)
    assert got.empty_handed is True
    assert got.status in RD.STATUSES


def test_success_with_no_accepted_evidence_is_refused():
    """The rename that turns an empty action into a productive one."""
    with pytest.raises(RD.DecisionRejected) as err:
        outcome("rd_x", RD.SUCCESS, accepted=0)
    assert "how an empty action becomes a productive one" in str(err.value)


def test_a_failure_must_name_its_kind():
    with pytest.raises(RD.DecisionRejected) as err:
        outcome("rd_x", RD.FAILED, accepted=0)
    assert "only information a failed action carries" in str(err.value)


def test_an_outcome_without_a_decision_is_refused():
    with pytest.raises(RD.DecisionRejected) as err:
        RD.DecisionOutcome(decision_id="", status=RD.NO_RESULT)
    assert "observation with no choice attached" in str(err.value)


# --- ordering: the thing that makes the log prospective ------------------------

def test_an_outcome_may_not_start_before_its_decision_was_written():
    got = decision(at="2026-08-09T12:00:00")
    early = outcome(got.decision_id, RD.NO_RESULT,
                    started="2026-08-09T11:59:59", accepted=0)
    with pytest.raises(RD.DecisionRejected) as err:
        RD.pair([got], [early])
    assert "choice was recorded after the result" in str(err.value)


def test_a_decision_with_no_outcome_is_reported_not_dropped():
    got = decision()
    joined, orphan_decisions, orphan_outcomes = RD.pair([got], [])
    assert joined == []
    assert orphan_decisions == [got]
    assert orphan_outcomes == []


def test_pairing_joins_on_decision_id():
    got = decision()
    joined, orphans, _ = RD.pair([got], [outcome(got.decision_id)])
    assert len(joined) == 1 and orphans == []


# --- the provenance wall -------------------------------------------------------

def test_a_reconstructed_row_keeps_its_mark_through_the_bridge():
    got = decision(provenance=RD.RECONSTRUCTED)
    record = RD.to_research_record(got, outcome(got.decision_id))
    assert record.reconstructed is True


def test_a_prospective_row_is_not_marked_reconstructed():
    got = decision()
    record = RD.to_research_record(got, outcome(got.decision_id))
    assert record.reconstructed is False


def test_no_new_information_projects_as_a_duplicate():
    got = decision()
    record = RD.to_research_record(
        got, outcome(got.decision_id, RD.NO_NEW_INFORMATION, accepted=0))
    assert record.outcome.duplicate is True


def test_no_result_projects_as_empty_not_used():
    got = decision()
    record = RD.to_research_record(
        got, outcome(got.decision_id, RD.NO_RESULT, accepted=0))
    assert record.outcome.outcome == RP.EMPTY


def test_an_empty_log_is_not_evaluable():
    standing = RD.evaluation_standing([])
    assert standing["standing"] == "NOT_EVALUABLE"
    assert "biased toward success" in standing["why"]


def test_reconstructed_rows_alone_are_not_evaluable():
    rows = [decision(provenance=RD.RECONSTRUCTED, at=f"2026-08-0{i}")
            for i in range(1, 8)]
    standing = RD.evaluation_standing(rows)
    assert standing["standing"] == "NOT_EVALUABLE"
    assert standing["prospective"] == 0
    assert standing["reconstructed"] == 7


def test_a_deterministic_prospective_log_is_replay_only():
    rows = [decision(at=f"2026-08-0{i}") for i in range(1, 8)]
    standing = RD.evaluation_standing(rows)
    assert standing["standing"] == "REPLAY_ONLY"
    assert "cannot estimate what an unchosen option would have returned" \
        in standing["why"]


def test_a_randomised_log_becomes_offline_evaluable():
    rows = [decision(at=f"2026-08-0{i}", probability=0.5, status=RD.KNOWN)
            for i in range(1, 8)]
    standing = RD.evaluation_standing(rows)
    assert standing["standing"] == "OFFLINE_EVALUABLE"


def test_a_prospective_log_with_no_forgone_option_is_not_evaluable():
    """One eligible family is not a choice, however many rows there are."""
    rows = [decision(at=f"2026-08-0{i}",
                     candidates=(candidate(RP.INDEPENDENT_REPORTING),))
            for i in range(1, 8)]
    standing = RD.evaluation_standing(rows)
    assert standing["standing"] == "NOT_EVALUABLE"
    assert "no alternative to compare against" in standing["why"]


def test_standing_is_never_deployable_from_this_module():
    rows = [decision(at=f"2026-08-0{i}", probability=0.5, status=RD.KNOWN)
            for i in range(1, 40)]
    assert RD.evaluation_standing(rows)["deployable"] is False


# --- delayed reward ------------------------------------------------------------

def test_a_delayed_outcome_does_not_touch_the_immediate_reward():
    got = decision()
    immediate = RD.DecisionOutcome(
        decision_id=got.decision_id, status=RD.SUCCESS, accepted_evidence=1,
        immediate_reward=1.5)
    later = RD.DelayedOutcome(
        decision_id=got.decision_id, outcome_type="BELIEF_RESOLVED",
        target_id="b_1", reward_delta=2.0, observed_at="2026-09-01")
    assert immediate.immediate_reward == 1.5, "the original stands"
    assert later.reward_delta == 2.0
    assert later.delayed_id.startswith("dl_")


def test_a_delayed_outcome_needs_its_decision():
    with pytest.raises(RD.DecisionRejected):
        RD.DelayedOutcome(decision_id="", outcome_type="BELIEF_RESOLVED",
                          target_id="b_1", reward_delta=1.0)


# --- the snapshot --------------------------------------------------------------

def test_the_snapshot_id_is_content_keyed():
    one = RD.StateSnapshot(as_of="2026-08-09", open_hypotheses=7)
    same = RD.StateSnapshot(as_of="2026-08-09", open_hypotheses=7)
    other = RD.StateSnapshot(as_of="2026-08-09", open_hypotheses=8)
    assert one.snapshot_id == same.snapshot_id
    assert one.snapshot_id != other.snapshot_id


# --- the summary a reader checks the claims against ----------------------------

def test_the_summary_counts_the_rows_a_reconstruction_cannot_have():
    one = decision(at="2026-08-09T01:00:00")
    two = decision(at="2026-08-09T02:00:00", subject="beta")
    outcomes = [outcome(one.decision_id, RD.SUCCESS,
                        started="2026-08-09T01:00:05"),
                outcome(two.decision_id, RD.NO_RESULT, accepted=0,
                        started="2026-08-09T02:00:05")]
    got = RD.summarise([one, two], outcomes)
    assert got["decisions"] == 2 and got["paired"] == 2
    assert got["empty_handed"] == 1
    assert got["by_status"][RD.NO_RESULT] == 1
    assert got["decisions_with_a_forgone_option"] == 2
    assert got["mean_choice_set"] == 2.0
