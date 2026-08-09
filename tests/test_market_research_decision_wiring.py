"""The decision reaches disk, and a process that did not write it can read it.

A-RD-007. This file exists because of two recorded failures where the API was
correct and nothing called it: a store with no write path for relationships,
and a trust producer that was green and unrun. Testing the dataclass proves
neither. What has to be proven is that the CYCLE writes, and that the bytes
survive the process that produced them.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap

import pytest

from intent_engine.market import learning_store as LS
from intent_engine.market import research_decision as RD
from intent_engine.market import steps


class _Report:
    """A counterparty Yield, reduced to the fields the outcome reads."""

    def __init__(self, **kw):
        self.family = kw.get("family", "customer_case_study")
        self.documents_attempted = kw.get("attempted", 3)
        self.documents_retrieved = kw.get("retrieved", 3)
        self.relationships_accepted = kw.get("accepted", 0)
        self.relationships_refused = kw.get("refused", 0)
        self.duplicates = kw.get("duplicates", 0)
        self.latency_seconds = kw.get("latency", 0.5)
        self.errors = kw.get("errors", [])


# --- the classifier keeps the empty-handed cases apart -------------------------

def test_a_family_that_reached_nothing_and_errored_is_a_failure():
    got = steps._acquisition_status(
        _Report(retrieved=0, errors=["acme: TimeoutError"]), integrated=False)
    assert got == RD.FAILED


def test_a_family_that_was_reached_and_held_nothing_is_no_result():
    got = steps._acquisition_status(_Report(retrieved=0), integrated=False)
    assert got == RD.NO_RESULT


def test_documents_whose_relationships_were_all_already_held():
    got = steps._acquisition_status(
        _Report(retrieved=4, accepted=0, duplicates=4), integrated=False)
    assert got == RD.NO_NEW_INFORMATION


def test_documents_whose_relationships_were_all_refused():
    got = steps._acquisition_status(
        _Report(retrieved=4, accepted=0, refused=4), integrated=False)
    assert got == RD.REFUSED


def test_accepted_relationships_that_did_not_reach_integrate_are_not_success():
    """A family below the measured verdict contributed nothing to the ledger."""
    got = steps._acquisition_status(
        _Report(retrieved=4, accepted=2), integrated=False)
    assert got != RD.SUCCESS


def test_integrated_acceptances_are_success():
    got = steps._acquisition_status(
        _Report(retrieved=4, accepted=2), integrated=True)
    assert got == RD.SUCCESS


# --- the two vocabularies stay apart ------------------------------------------

def test_every_acquisition_family_maps_to_an_evidence_role():
    from intent_engine.market import counterparty_sources as CS
    from intent_engine.market import research_policy as RP

    for family in (CS.GOVERNMENT_AWARD, CS.PARTNERSHIP_RELEASE,
                   CS.CUSTOMER_CASE_STUDY):
        assert family in RD.RP_FAMILY_FOR, (
            f"{family} has no evidence-role mapping, so a decision logged for "
            "it cannot be projected into the policy log")
        assert RD.RP_FAMILY_FOR[family] in RP.SOURCE_FAMILIES


def test_a_company_published_family_is_not_recorded_as_independent():
    """The mapping is what stops a vendor's own case study scoring as a witness."""
    from intent_engine.market import research_policy as RP

    assert RD.RP_FAMILY_FOR["customer_case_study"] == RP.COMPANY_OWNED
    assert RD.RP_FAMILY_FOR["partnership_release"] == RP.COMPANY_OWNED


# --- the store refuses the rows that would reintroduce the bias ---------------

def test_an_outcome_without_a_prior_decision_is_refused(tmp_path):
    store = LS.LearningStore(tmp_path / "ledger.jsonl")
    outcome = RD.DecisionOutcome(decision_id="rd_never_written",
                                 status=RD.NO_RESULT)
    with pytest.raises(ValueError) as err:
        store.record_research_outcome(outcome)
    assert "must be durable BEFORE the call" in str(err.value)


def test_a_decision_is_written_once(tmp_path):
    store = LS.LearningStore(tmp_path / "ledger.jsonl")
    decision = RD.ResearchDecision(
        subject="ALL", question_type="NEEDS_COUNTERPARTY",
        chosen_action="customer_case_study",
        candidates=(RD.CandidateAction(source_family="customer_case_study"),),
        selection_policy="CADENCE_GATED_SWEEP", chosen_at="2026-08-09")
    assert store.record_research_decision(decision) is True
    assert store.record_research_decision(decision) is False
    assert len(store.research_decisions()) == 1


def test_a_delayed_outcome_never_rewrites_the_immediate_one(tmp_path):
    store = LS.LearningStore(tmp_path / "ledger.jsonl")
    decision = RD.ResearchDecision(
        subject="ALL", question_type="NEEDS_COUNTERPARTY",
        chosen_action="customer_case_study",
        candidates=(RD.CandidateAction(source_family="customer_case_study"),),
        selection_policy="P", chosen_at="2026-08-09")
    store.record_research_decision(decision)
    store.record_research_outcome(RD.DecisionOutcome(
        decision_id=decision.decision_id, status=RD.SUCCESS,
        accepted_evidence=2, immediate_reward=1.0))
    store.record_research_delayed_outcome(RD.DelayedOutcome(
        decision_id=decision.decision_id, outcome_type="BELIEF_RESOLVED",
        target_id="b_1", reward_delta=2.0, observed_at="2026-09-01"))

    immediate = store.research_outcomes()
    assert len(immediate) == 1
    assert immediate[0]["immediate_reward"] == 1.0, (
        "the delayed record must not have folded back into the first")
    assert len(store.research_delayed_outcomes()) == 1


# --- the bytes survive the process that wrote them ----------------------------

def test_a_fresh_process_reads_back_what_this_one_wrote(tmp_path):
    """The claim 'it persisted' is only ever true across a process boundary."""
    ledger = tmp_path / "ledger.jsonl"
    store = LS.LearningStore(ledger)
    decision = RD.ResearchDecision(
        subject="ALL", question_type="NEEDS_COUNTERPARTY",
        chosen_action="government_award",
        candidates=(RD.CandidateAction(source_family="government_award"),
                    RD.CandidateAction(source_family="customer_case_study",
                                       eligible=False,
                                       refusal_reason="cadence 3d")),
        selection_policy="CADENCE_GATED_SWEEP", chosen_at="2026-08-09",
        policy_family="government_data")
    store.record_research_decision(decision)
    store.record_research_outcome(RD.DecisionOutcome(
        decision_id=decision.decision_id, status=RD.NO_RESULT,
        started_at="2026-08-09T00:00:01", documents_attempted=26))

    script = textwrap.dedent(f"""
        from intent_engine.market import learning_store as LS
        store = LS.LearningStore({str(ledger)!r})
        decisions = store.research_decisions()
        outcomes = store.research_outcomes()
        print(__import__("json").dumps({{
            "decisions": len(decisions),
            "outcomes": len(outcomes),
            "chosen": decisions[0]["chosen_action"],
            "candidates": len(decisions[0]["candidate_actions"]),
            "eligible": decisions[0]["eligible_families"],
            "provenance": decisions[0]["provenance"],
            "status": outcomes[0]["status"],
        }}))
    """)
    # THE SOURCE ROOT IS PASSED EXPLICITLY, not inherited. pytest puts `src`
    # on this process's path from config, and a subprocess does not get that.
    # Worse, with nothing set, `intent_engine` resolves to the OTHER repo's
    # checkout — which has no `market` subpackage — so the child would fail
    # for a reason that has nothing to do with what is being tested. Derived
    # from the imported package so it follows the worktree rather than naming
    # a path.
    import intent_engine
    source_root = os.path.dirname(os.path.dirname(
        os.path.abspath(intent_engine.__file__)))
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [source_root] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
    proc = subprocess.run([sys.executable, "-c", script],
                          capture_output=True, text=True, timeout=120, env=env)
    assert proc.returncode == 0, proc.stderr
    got = json.loads(proc.stdout.strip().splitlines()[-1])
    assert got["decisions"] == 1 and got["outcomes"] == 1
    assert got["chosen"] == "government_award"
    assert got["candidates"] == 2, "the cadence-blocked option survived too"
    assert got["eligible"] == ["government_award"]
    assert got["provenance"] == RD.PROSPECTIVE
    assert got["status"] == RD.NO_RESULT, (
        "an action that found nothing is the row a reconstructed log cannot "
        "hold; it must survive the process that wrote it")
