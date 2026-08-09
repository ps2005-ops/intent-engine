"""A CEO answer comes from the record, or it is refused.

The distinction this file exists to hold is between two questions that sound
alike and are the whole product:

    WHAT CHANGED            new evidence, new economic state
    WHAT CHANGED YOUR MIND  a recorded thesis transition, and its cause

New evidence can arrive and change nothing. A system that answers the second
with the first is describing its own activity and calling it learning.
"""
from __future__ import annotations

import pytest

from intent_engine.external_intel import ceo_answers as CA
from intent_engine.external_intel import decision_impact as di


class Intel:
    def __init__(self, theses=(), revisions=(), history=None, beliefs=(),
                 limitations=(), source_health=None):
        self.economic_theses = tuple(theses)
        self.thesis_revisions = tuple(revisions)
        self.thesis_history = history
        self.beliefs = tuple(beliefs)
        self.limitations = tuple(limitations)
        self.source_health = source_health


def thesis(**kwargs) -> dict:
    row = {"thesis_id": "th_1", "claim": "input costs are rising",
           "standing": "PROPOSED", "question": "q",
           "macro_conditions": ["US:INFLATION"], "exposures": ["INPUT_COST"],
           "mechanism": "tariffs raise landed cost",
           "falsifier": "landed cost per unit falls two quarters running",
           "alternatives": ["the mix shifted toward cheaper products"],
           "decision_implication": "hold pricing until Q3",
           "evidence_ids": ["ev_1"]}
    row.update(kwargs)
    return row


# --- classification ---------------------------------------------------------

@pytest.mark.parametrize("question,expected", [
    ("What is happening?", CA.CURRENT_STATE),
    ("Why is that?", CA.WHY),
    ("Why should I care?", CA.WHY_IT_MATTERS),
    ("What changed?", CA.WHAT_CHANGED),
    ("What changed your mind?", CA.WHAT_CHANGED_YOUR_MIND),
    ("What's the strongest alternative?", CA.STRONGEST_ALTERNATIVE),
    ("What would falsify this?", CA.FALSIFIER),
    ("What should I monitor?", CA.MONITOR),
    ("What should I not conclude?", CA.WHAT_NOT_TO_CONCLUDE),
    ("How confident are you?", CA.CONFIDENCE),
])
def test_questions_route_to_their_class(question, expected):
    assert CA.classify(question) == expected


def test_an_unrecognised_question_is_not_guessed():
    """A default class is a claim about what was asked."""
    got = CA.plan("What is the capital of France?", Intel())
    assert got.question_class == CA.UNKNOWN_QUESTION
    assert got.supported is False


# --- the two questions that must not merge ----------------------------------

def test_what_changed_is_not_what_changed_your_mind():
    """New evidence with no transition: the answer must say both halves."""
    intel = Intel(theses=[thesis()], beliefs=[{"proposition": "x"}] * 3,
                  history={"status": di.HISTORY_AVAILABLE_NO_MOVEMENT},
                  revisions=[{"transition": "CREATED",
                              "revision_id": "r1"}])
    changed = CA.plan("What changed?", intel)
    mind = CA.plan("What changed your mind?", intel)

    assert "did not change" in changed.direct_answer
    assert "Nothing has changed this view yet" in mind.direct_answer
    assert changed.direct_answer != mind.direct_answer


def test_missing_history_never_reads_as_a_settled_view():
    """The defect the transport was built to close, at the answer layer."""
    got = CA.plan("What changed your mind?",
                  Intel(theses=[thesis()], history=None))
    assert got.standing == di.HISTORY_UNAVAILABLE
    assert got.supported is False
    assert "not enough revision history" in got.direct_answer
    assert any("not the same as the view never having changed" in limit
               for limit in got.limitations)


def test_a_real_transition_is_answered_from_the_record():
    got = CA.plan("What changed your mind?", Intel(
        theses=[thesis()],
        history={"status": di.HISTORY_AVAILABLE_MOVED},
        revisions=[{"transition": "WEAKENED", "revision_id": "r2",
                    "changed_at": "2026-08-09",
                    "previous_standing": "SUPPORTED",
                    "new_standing": "CONTESTED",
                    "reason": "two filings disagreed",
                    "knowledge_effect_ids": ["ke_1"],
                    "triggering_evidence": ["ev_9"]}]))
    assert got.supported is True
    assert got.effect_ids == ("ke_1",)
    assert got.evidence_ids == ("ev_9",)
    assert got.revision_ids == ("r2",)


def test_no_movement_still_warns_against_reading_it_as_settled():
    got = CA.plan("What changed your mind?", Intel(
        theses=[thesis()],
        history={"status": di.HISTORY_AVAILABLE_NO_MOVEMENT}))
    assert any("nothing has tested it yet" in item
               for item in got.must_not_conclude)


# --- gaps are named, never bridged ------------------------------------------

def test_a_missing_hop_stops_the_causal_statement():
    got = CA.plan("Why is that?",
                  Intel(theses=[thesis(mechanism="", exposures=[])]))
    assert "COMPANY_EXPOSURE" in got.missing_information
    assert "MECHANISM" in got.missing_information
    assert "no further" in got.direct_answer


def test_a_complete_chain_reports_no_missing_hops():
    got = CA.plan("Why is that?", Intel(theses=[thesis()]))
    assert got.missing_information == ()
    assert [h.standing for h in got.hops].count(CA.MISSING) == 0


def test_an_absent_falsifier_is_a_gap_not_a_strength():
    got = CA.plan("What would falsify this?",
                  Intel(theses=[thesis(falsifier="")]))
    assert got.supported is False
    assert "not currently stated in a way that evidence could overturn" in \
        got.direct_answer


def test_an_absent_alternative_is_not_consensus():
    got = CA.plan("What's the strongest alternative?",
                  Intel(theses=[thesis(alternatives=[])]))
    assert got.supported is False
    assert "gap in the analysis rather than evidence the view is" in \
        got.direct_answer


# --- challenge mode ---------------------------------------------------------

@pytest.mark.parametrize("question", [
    "Prove demand is collapsing.",
    "Tell me why this strategy will definitely work.",
    "We should cut prices immediately.",
    "Ignore the downside and give me the upside.",
    "Assume the competitor won't respond.",
    "Give me the strongest possible case for expanding.",
])
def test_a_leading_question_is_challenged(question):
    got = CA.plan(question, Intel(theses=[thesis()]))
    assert got.question_class == CA.CHALLENGE
    assert got.premise_challenged
    assert "can't answer that as asked" in got.direct_answer


def test_a_challenge_still_reports_what_the_evidence_shows():
    """Refusing the premise is not refusing the question."""
    got = CA.plan("Prove demand is collapsing.", Intel(theses=[thesis()]))
    assert "input costs are rising" in got.direct_answer
    assert got.alternatives
    assert got.falsifiers


def test_a_plain_question_is_not_challenged():
    assert CA.plan("What is happening?",
                   Intel(theses=[thesis()])).premise_challenged == ""


# --- the certainty wall -----------------------------------------------------

def test_a_renderer_may_not_upgrade_the_standing():
    got = CA.plan("What is happening?", Intel(theses=[thesis()]))
    bad = "This definitely proves input costs are rising."
    assert CA.violates_certainty_wall(bad, got)


def test_an_observed_standing_may_speak_plainly():
    got = CA.plan("What is happening?",
                  Intel(theses=[thesis(standing="OBSERVED")]))
    assert CA.violates_certainty_wall("This proves the cost rose.", got) == ()


def test_a_measured_answer_passes_the_wall():
    got = CA.plan("What is happening?", Intel(theses=[thesis()]))
    assert CA.violates_certainty_wall(
        "Input costs appear to be rising, on current evidence.", got) == ()


# --- source health ----------------------------------------------------------

def test_a_degraded_source_reduces_visibility_not_activity():
    got = CA.plan("What is happening?", Intel(
        theses=[thesis()],
        source_health={"impaired_families": ["bureau_of_labor_statistics"]}))
    assert got.source_constraints
    assert "not evidence that nothing happened" in got.source_constraints[0]


def test_healthy_sources_add_no_caveat():
    got = CA.plan("What is happening?", Intel(
        theses=[thesis()], source_health={"impaired_families": []}))
    assert got.source_constraints == ()


# --- the plan is a bounded object -------------------------------------------

def test_every_plan_is_serialisable_and_declares_support():
    for question in ("What is happening?", "What changed your mind?",
                     "Prove demand is collapsing.", "Nonsense question"):
        got = CA.plan(question, Intel(theses=[thesis()])).as_dict()
        assert got["contract"] == CA.CONTRACT
        assert got["question_class"] in CA.QUESTION_CLASSES
        assert isinstance(got["supported"], bool)


def test_an_empty_dossier_answers_nothing_confidently():
    for question in ("What is happening?", "Why?", "What changed?"):
        assert CA.plan(question, Intel()).supported is False


# --- defects the live corpus surfaced ---------------------------------------

def test_a_missing_first_hop_does_not_wrap_to_the_last():
    """`hops[index - 1]` wrapped and produced "I can trace that as far as
    decision consequence ... evidence is not recorded"."""
    got = CA.plan("Why is that?",
                  Intel(theses=[thesis(evidence_ids=[])]))
    assert "cannot trace that back at all" in got.direct_answer
    assert "as far as decision consequence" not in got.direct_answer


def test_a_blank_alternative_is_not_an_alternative():
    """A Mechanism with no description arrives as "" and rendered as
    "The strongest recorded alternative is: "."""
    got = CA.plan("What's the strongest alternative?",
                  Intel(theses=[thesis(alternatives=["", "  "])]))
    assert got.supported is False
    assert got.direct_answer.rstrip().endswith("uncontested.")
