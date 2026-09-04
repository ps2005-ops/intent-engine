"""The zero-Anthropic executive read.

The wall this file defends: the wording a sentence may use is a function of
the standing of the evidence under it, and no branch of the composer can
reach a stronger verb than its standing allows.
"""
from __future__ import annotations

import json

import pytest

from intent_engine.demo_dossier import (assemble, founder_unavailable,
                                        read_market_snapshot)
from intent_engine.executive import decision_synthesis as DS
from intent_engine.strategic_intelligence.decision import (
    DECISION_READY, INVESTIGATION_REQUIRED, WITHHELD)

CONTRACT = "market_demo_snapshot.v1"


def _ref(count=0, ids=(), state="AVAILABLE", **extra):
    block = {"state": state, "ids": list(ids), "count": count, "note": ""}
    block.update(extra)
    return block


def _dossier(**over):
    payload = {
        "contract_version": CONTRACT, "company_id": "acme-corp",
        "canonical_name": "Acme Corp", "snapshot_id": "ms-1",
        "availability": "AVAILABLE", "unavailable_reason": "",
        "generated_at": "2026-08-13", "known_at": "2026-08-13",
        "evidence_cutoff": "2026-08-13", "market_population": "REAL_MARKET",
    }
    payload.update(over)
    market = read_market_snapshot(payload, expected_company="acme-corp",
                                  today="2026-08-14")
    return assemble(market,
                    founder_unavailable("no founder run",
                                        company_id="acme-corp"),
                    cohort="", manifest_version="", now="2026-08-14",
                    previous=None)


def _compose(**over):
    return DS.compose(_dossier(**over))


# --- standing governs wording ------------------------------------------------

@pytest.mark.parametrize("standing,verb", [
    (DS.SUPPORTED, "supports"),
    (DS.BOUNDED, "is consistent with"),
    (DS.UNMEASURABLE, "cannot yet determine"),
    (DS.REFUSED, "should not infer"),
])
def test_each_standing_has_exactly_one_permitted_verb(standing, verb):
    assert DS.verb_for(standing) == verb


def test_an_unknown_standing_gets_the_weakest_wording_not_the_strongest():
    # The safe direction. A standing added later that this table has never
    # seen must not reach for "supports".
    assert DS.verb_for("SOMETHING_NEW") == DS.verb_for(DS.REFUSED)


def test_evidence_without_a_belief_cannot_reach_supported():
    # Documents nobody formed a position over are a pile of documents. The
    # read may describe them; it may not recommend from them.
    d = _compose(evidence_reference_ids=_ref(9, ["e1"]),
                 belief_refs=_ref(0))
    assert d.standing == DS.BOUNDED
    assert "is consistent with" in d.current_read
    assert "supports" not in d.current_read


def test_a_refused_causal_question_holds_the_reading_at_bounded():
    # This is the live state for every company that asked one. A reading
    # cannot be SUPPORTED while the question it turns on is unanswered.
    d = _compose(evidence_reference_ids=_ref(9, ["e1"]),
                 belief_refs=_ref(3, ["b1"]),
                 causal_result_refs=_ref(6, ["r1"],
                                         states={"PANEL_UNAVAILABLE": 6}))
    assert d.standing == DS.BOUNDED
    assert d.readiness == INVESTIGATION_REQUIRED


def test_an_answered_causal_question_can_reach_supported():
    # The negative control: the gate must not refuse everything. A guard that
    # never passes is indistinguishable from one that always refuses.
    d = _compose(evidence_reference_ids=_ref(9, ["e1"]),
                 belief_refs=_ref(3, ["b1"]),
                 causal_result_refs=_ref(2, ["r1"],
                                         states={"ESTIMATE_SUPPORTED": 2}))
    assert d.standing == DS.SUPPORTED
    assert d.readiness == DECISION_READY
    assert "supports" in d.current_read


def test_no_evidence_is_unmeasurable_not_a_negative_finding():
    d = _compose(evidence_reference_ids=_ref(0), belief_refs=_ref(0))
    assert d.standing == DS.UNMEASURABLE
    assert "cannot yet determine" in d.current_read


def test_a_refused_snapshot_withholds_rather_than_reads():
    d = DS.compose(_dossier(company_id="somebody-else"))
    assert d.standing == DS.REFUSED
    assert d.readiness == WITHHELD


# --- §9: a refusal becomes a next move ---------------------------------------

def test_panel_unavailable_is_routed_not_dead_ended():
    d = _compose(evidence_reference_ids=_ref(4, ["e1"]),
                 belief_refs=_ref(2, ["b1"]),
                 causal_result_refs=_ref(6, ["r1"],
                                         states={"PANEL_UNAVAILABLE": 6}))
    assert d.causal_status == "CAUSAL_UNMEASURABLE"
    assert d.information_gaps and "comparable control panel" \
        in d.information_gaps[0]
    assert d.minimum_data_requests           # what would resolve it
    assert d.value_of_information            # what that is worth
    assert d.guardrails                      # what to do meanwhile
    # And it must never read as "we looked and there is no effect".
    assert "not a finding that the effect is absent" in d.causal_note


def test_a_causal_refusal_is_never_reported_as_the_subsystem_not_running():
    refused = _compose(causal_result_refs=_ref(
        6, ["r1"], states={"PANEL_UNAVAILABLE": 6}))
    absent = _compose(causal_result_refs=_ref(0, state="UNAVAILABLE"))
    assert refused.causal_status == "CAUSAL_UNMEASURABLE"
    assert absent.causal_status == "CAUSAL_NOT_RUN"
    assert refused.causal_status != absent.causal_status


def test_a_company_with_no_refusal_gets_no_invented_gap():
    # The negative control for the router: it must not manufacture an
    # information gap for a company that never asked a causal question.
    d = _compose(evidence_reference_ids=_ref(4, ["e1"]),
                 belief_refs=_ref(2, ["b1"]))
    assert d.information_gaps == ()
    assert d.minimum_data_requests == ()
    assert d.guardrails == ()


# --- the hidden state --------------------------------------------------------

def test_a_uniform_posterior_is_named_not_rendered_as_a_posture():
    # The live shape for 22 of 26 companies: real evidence and beliefs, and a
    # posture the engine tracks but cannot yet call.
    d = _compose(evidence_reference_ids=_ref(6, ["e1"]),
                 belief_refs=_ref(5, ["b1"]),
                 hidden_state_refs=_ref(0, unidentified=1))
    assert d.hidden_state == "TRACKED_NO_IDENTIFIED_STATE"
    assert "not yet distinguishable from the prior" in d.current_read
    # And the posture name itself must never appear as though it were read.
    assert "GROWING" not in d.current_read


def test_an_identified_posture_is_shown():
    d = _compose(evidence_reference_ids=_ref(2, ["e1"]),
                 belief_refs=_ref(1, ["b1"]),
                 hidden_state_refs=_ref(1, ["PLATFORM_EXPANDING"]))
    assert d.hidden_state == "PLATFORM_EXPANDING"
    assert "PLATFORM_EXPANDING" in d.current_read


def test_a_hidden_state_that_never_ran_is_not_a_tracked_zero():
    d = _compose(hidden_state_refs=_ref(0, state="UNAVAILABLE"))
    assert d.hidden_state == "HIDDEN_STATE_NOT_RUN"


# --- what changed ------------------------------------------------------------

def test_a_first_reading_does_not_claim_a_change():
    d = _compose(evidence_reference_ids=_ref(4, ["e1"]))
    assert "no earlier one" in d.what_changed[0]


def test_an_identical_second_reading_reports_no_change():
    first = _dossier(evidence_reference_ids=_ref(4, ["e1"]),
                     belief_refs=_ref(2, ["b1"]))
    second = _dossier(evidence_reference_ids=_ref(4, ["e1"]),
                      belief_refs=_ref(2, ["b1"]))
    d = DS.compose(second, previous=first)
    assert d.what_changed == ("Nothing in the published market record "
                              "changed since the previous reading.",)


def test_a_real_change_is_reported_with_both_numbers():
    first = _dossier(evidence_reference_ids=_ref(4, ["e1"]))
    second = _dossier(evidence_reference_ids=_ref(9, ["e1"]))
    d = DS.compose(second, previous=first)
    assert any("evidence rows: 4 -> 9" in c for c in d.what_changed)


# --- the walls ---------------------------------------------------------------

@pytest.mark.parametrize("phrase", ["zero risk", "no risk", "risk free",
                                    "risk-free", "guaranteed"])
def test_the_composer_refuses_to_emit_a_no_risk_claim(phrase):
    with pytest.raises(DS.SynthesisRefused):
        DS._assert_clean(f"this move carries {phrase} for the company")


def test_no_number_appears_that_was_not_in_the_inputs():
    d = _compose(evidence_reference_ids=_ref(6, ["e1"]),
                 belief_refs=_ref(5, ["b1"]))
    blob = json.dumps(d.as_dict(), default=str)
    # 6 and 5 are real counts. A percentage or a confidence score is not
    # computable from anything here, so none may appear.
    assert "%" not in blob
    assert "confidence" not in blob.lower()


def test_composition_makes_no_model_call(monkeypatch):
    """The point of the whole module, asserted rather than intended."""
    import intent_engine.strategic_intelligence.analyst.runner as runner

    def _boom(*a, **k):
        raise AssertionError("the executive read made a model call")
    monkeypatch.setattr(runner, "default_client", _boom, raising=False)
    d = _compose(evidence_reference_ids=_ref(6, ["e1"]),
                 belief_refs=_ref(5, ["b1"]))
    assert d.current_read
    assert d.derived_from == "market_dossier"


def test_the_decision_names_its_provenance():
    d = _compose(evidence_reference_ids=_ref(6, ["e1"]))
    joined = " ".join(d.provenance)
    assert "market snapshot" in joined
    assert "evidence cutoff" in joined


def test_an_answered_causal_question_still_needs_a_belief_to_be_supported():
    # The case that makes the belief guard load-bearing. With the causal
    # question answered, the ONLY thing standing between a pile of documents
    # and a SUPPORTED recommendation is that nobody formed a position.
    d = _compose(evidence_reference_ids=_ref(9, ["e1"]),
                 belief_refs=_ref(0),
                 causal_result_refs=_ref(2, ["r1"],
                                         states={"ESTIMATE_SUPPORTED": 2}))
    assert d.standing == DS.BOUNDED
    assert "supports" not in d.current_read


# --- economic state: four answers, and the common one is a finding ----------

def test_a_transmitted_condition_is_named_on_the_read():
    d = _compose(evidence_reference_ids=_ref(4, ["e1"]),
                 belief_refs=_ref(2, ["b1"]),
                 economic_state_refs=_ref(1, ["GLOBAL:CURRENCY"]))
    assert d.economic_state == DS.ECONOMIC_AVAILABLE
    assert d.economic_context == ("GLOBAL:CURRENCY",)
    assert "GLOBAL:CURRENCY" in d.current_read


def test_a_measured_economy_that_reaches_nobody_is_a_finding_not_a_gap():
    # The live answer for 22 of 26 companies. It must not read as NOT_RUN:
    # one sends you to the scheduler, the other to this company's documents.
    d = _compose(evidence_reference_ids=_ref(4, ["e1"]),
                 belief_refs=_ref(2, ["b1"]),
                 economic_state_refs=_ref(0))
    assert d.economic_state == DS.ECONOMIC_NO_EXPOSURE
    assert "none of it reaches this company" in d.current_read


def test_an_economy_that_never_ran_is_not_a_no_exposure_finding():
    d = _compose(evidence_reference_ids=_ref(4, ["e1"]),
                 belief_refs=_ref(2, ["b1"]),
                 economic_state_refs=_ref(0, state="UNAVAILABLE"))
    assert d.economic_state == DS.ECONOMIC_NOT_RUN
    assert "none of it reaches" not in d.current_read


def test_unreadable_economic_rows_are_unmeasurable_not_no_exposure():
    d = _compose(evidence_reference_ids=_ref(4, ["e1"]),
                 belief_refs=_ref(2, ["b1"]),
                 economic_state_refs={"state": "AVAILABLE", "ids": [],
                                      "count": 0,
                                      "note": "3 economic state(s) present "
                                              "and none carried a state "
                                              "kind; this is a wiring "
                                              "defect, not an absence"})
    assert d.economic_state == DS.ECONOMIC_UNMEASURABLE


def test_two_companies_do_not_share_an_economic_exposure_by_default():
    # The sector-table failure: the same macro line on every dossier. Only a
    # company whose own evidence establishes an exposure gets a condition.
    exposed = _compose(evidence_reference_ids=_ref(4, ["e1"]),
                       belief_refs=_ref(2, ["b1"]),
                       economic_state_refs=_ref(1, ["GLOBAL:CURRENCY"]))
    other = _compose(evidence_reference_ids=_ref(4, ["e2"]),
                     belief_refs=_ref(2, ["b2"]),
                     economic_state_refs=_ref(0))
    assert exposed.economic_context and not other.economic_context
    assert exposed.current_read != other.current_read
