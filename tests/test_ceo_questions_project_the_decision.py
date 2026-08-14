"""CEO Q&A projects the FounderDecision. It never re-reads the evidence.

Two derivations of one strategy is how a product tells a founder one thing on
a page and another in a chat.
"""
from __future__ import annotations

import pytest

from intent_engine.demo_dossier import (assemble, founder_unavailable,
                                        read_market_snapshot)
from intent_engine.executive import ceo_questions as Q
from intent_engine.executive import decision_synthesis as DS

CONTRACT = "market_demo_snapshot.v1"


def _ref(count=0, ids=(), state="AVAILABLE", **extra):
    b = {"state": state, "ids": list(ids), "count": count, "note": ""}
    b.update(extra)
    return b


def _decision(**over):
    payload = {"contract_version": CONTRACT, "company_id": "acme-corp",
               "canonical_name": "Acme Corp", "snapshot_id": "ms-1",
               "availability": "AVAILABLE", "unavailable_reason": "",
               "generated_at": "2026-08-13", "known_at": "2026-08-13",
               "evidence_cutoff": "2026-08-13",
               "market_population": "REAL_MARKET"}
    payload.update(over)
    market = read_market_snapshot(payload, expected_company="acme-corp",
                                  today="2026-08-14")
    d = assemble(market, founder_unavailable("no run", company_id="acme-corp"),
                 cohort="", manifest_version="", now="2026-08-14",
                 previous=None)
    return DS.compose(d)


@pytest.mark.parametrize("question", Q.REQUIRED_QUESTIONS)
def test_every_required_question_is_recognised(question):
    assert Q.classify(question) != Q.UNSUPPORTED


def test_an_unknown_question_is_refused_not_nearest_matched():
    d = _decision(evidence_reference_ids=_ref(3, ["e1"]))
    a = Q.answer("What is our cash runway?", d)
    assert a.question_class == Q.UNSUPPORTED
    assert a.supported is False
    # It must not answer with the closest available topic.
    assert "runway" not in a.answer.lower()


def test_the_three_mind_questions_are_never_confused():
    # Different sources: what moved, what recorded a move, what would move it.
    assert Q.classify("What changed?") == Q.WHAT_CHANGED
    assert Q.classify("What changed your mind?") == Q.CHANGED_YOUR_MIND
    assert (Q.classify("What would change your mind?")
            == Q.WOULD_CHANGE_YOUR_MIND)


def test_a_recommendation_never_exceeds_the_decision_standing():
    d = _decision(evidence_reference_ids=_ref(9, ["e1"]),
                  belief_refs=_ref(3, ["b1"]),
                  causal_result_refs=_ref(6, ["r1"],
                                          states={"PANEL_UNAVAILABLE": 6}))
    a = Q.answer("What do you recommend?", d)
    assert d.standing == DS.BOUNDED
    assert a.standing == DS.BOUNDED
    assert "No action is recommended" in a.answer
    assert "supports" not in a.answer


def test_a_supported_reading_may_recommend():
    d = _decision(evidence_reference_ids=_ref(9, ["e1"]),
                  belief_refs=_ref(3, ["b1"]),
                  causal_result_refs=_ref(2, ["r1"],
                                          states={"ESTIMATE_SUPPORTED": 2}))
    a = Q.answer("What do you recommend?", d)
    assert d.standing == DS.SUPPORTED
    assert "No action is recommended" not in a.answer


def test_changed_your_mind_is_never_inferred_from_the_current_view():
    d = _decision(evidence_reference_ids=_ref(4, ["e1"]),
                  belief_refs=_ref(2, ["b1"]))
    a = Q.answer("What changed your mind?", d)
    assert a.supported is False
    assert "not the same as" in a.answer


def test_no_prior_decision_is_named_not_invented():
    d = _decision(evidence_reference_ids=_ref(4, ["e1"]))
    a = Q.answer("What did we decide before?", d)
    assert "NO_DECISION_RECORDED" in a.answer
    assert a.supported is False


def test_risk_and_falsifier_do_not_return_the_same_sentence():
    # Both draw on the same unresolved question. Answering them identically
    # makes the product look like it has one thought.
    d = _decision(evidence_reference_ids=_ref(4, ["e1"]),
                  belief_refs=_ref(2, ["b1"]),
                  causal_result_refs=_ref(6, ["r1"],
                                          states={"PANEL_UNAVAILABLE": 6}))
    assert (Q.answer("What is the biggest risk?", d).answer
            != Q.answer("What would change your mind?", d).answer)


def test_every_answer_carries_standing_and_provenance():
    d = _decision(evidence_reference_ids=_ref(4, ["e1"]),
                  belief_refs=_ref(2, ["b1"]))
    for question in Q.REQUIRED_QUESTIONS:
        a = Q.answer(question, d)
        assert a.standing, question
        assert a.provenance, question


def test_an_absent_competitor_model_says_thesis_not_formed():
    d = _decision(evidence_reference_ids=_ref(4, ["e1"]),
                  belief_refs=_ref(2, ["b1"]))
    a = Q.answer("What could a competitor do?", d)
    assert "THESIS_NOT_FORMED" in a.answer
    assert a.supported is False


def test_answers_come_from_the_decision_not_a_second_reading():
    # The evidence ids on the answer must be the decision's own, so a chat
    # answer and the screen cannot cite different rows.
    d = _decision(evidence_reference_ids=_ref(2, ["e1", "e2"]),
                  belief_refs=_ref(1, ["b1"]))
    a = Q.answer("Show me the source.", d)
    assert a.evidence_ids == d.supporting_evidence_ids


def test_no_decision_at_all_is_refused_rather_than_answered():
    a = Q.answer("What do you recommend?", None)
    assert a.supported is False
    assert a.question_class == Q.UNSUPPORTED
