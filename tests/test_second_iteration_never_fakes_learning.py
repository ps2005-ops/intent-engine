"""Running the same analysis twice must not manufacture a learning curve.

The flattering error here is specific and easy: credit the system for
re-reading its own library. So the replay wall gets the most tests, and
evidence identity is the CONTENT HASH -- never the URL, never the retrieval
date, both of which change on a re-read of the same page.

The second trap is treating CHANGE as the definition of learning. A belief
that new evidence TESTED and did not move is a stronger position than one
nothing has challenged, and a system rewarded only for changing its mind will
change it.
"""
from intent_engine.strategic_intelligence import second_iteration as SI

_Q = "Where is the competitive position most exposed?"


def _decision(**over):
    base = {"decision_question": _Q, "standing": "SUPPORTED",
            "recommended_next_move": "Hold pricing through Q3",
            "current_read": "Position is defensible"}
    base.update(over)
    return base


def _docs(*hashes):
    return [{"content_hash": h} for h in hashes]


# --- the replay wall -----------------------------------------------------------


def test_an_exact_replay_reports_no_learning():
    """RUN 3. The identical evidence, the identical answer."""
    got = SI.compare(previous_decision=_decision(), current_decision=_decision(),
                     previous_documents=_docs("a", "b"),
                     current_documents=_docs("a", "b"))
    assert got["state"] == SI.NO_NEW_INFORMATION
    assert got["represents_learning"] is False
    assert got["new_evidence"] == 0


def test_a_re_read_is_not_a_new_observation():
    """Identity is the content hash. A page fetched twice is ONE source."""
    got = SI.compare(previous_decision=_decision(), current_decision=_decision(),
                     previous_documents=_docs("a"),
                     current_documents=_docs("a", "a"))
    assert got["new_evidence"] == 0
    assert got["reobserved_evidence"] == 1


def test_the_same_url_with_changed_content_is_genuinely_new():
    """NEGATIVE CONTROL for the rule above: hashing must not make the wall so
    strict that a genuinely updated page stops counting."""
    got = SI.compare(previous_decision=_decision(), current_decision=_decision(),
                     previous_documents=_docs("v1"),
                     current_documents=_docs("v2"))
    assert got["new_evidence"] == 1


def test_a_moved_reading_with_no_new_evidence_is_not_learning():
    """The most dangerous row: the answer changed and nothing arrived. That is
    instability, and reporting it as learning would hide it."""
    got = SI.compare(
        previous_decision=_decision(),
        current_decision=_decision(recommended_next_move="Cut pricing now"),
        previous_documents=_docs("a"), current_documents=_docs("a"))
    assert got["state"] == SI.INCOMPARABLE
    assert got["represents_learning"] is False
    assert "change in us" in got["statement"]


# --- change is not the definition of learning ----------------------------------


def test_a_belief_that_was_tested_and_held_is_a_gain():
    got = SI.compare(previous_decision=_decision(),
                     current_decision=_decision(),
                     previous_documents=_docs("a"),
                     current_documents=_docs("a", "new"),
                     tested_claims=["pricing power is intact"])
    assert got["state"] == SI.NEW_INFORMATION_CONFIRMED_VIEW
    assert got["represents_learning"] is True
    assert got["recommendation_changed"] is False


def test_a_re_read_that_retested_a_claim_is_also_a_gain():
    got = SI.compare(previous_decision=_decision(),
                     current_decision=_decision(),
                     previous_documents=_docs("a", "b"),
                     current_documents=_docs("a", "b"),
                     tested_claims=["pricing power is intact"])
    assert got["state"] == SI.REOBSERVATION_TESTED_AND_HELD
    assert got["represents_learning"] is True


def test_new_evidence_that_moved_the_recommendation_is_reported_as_such():
    got = SI.compare(
        previous_decision=_decision(),
        current_decision=_decision(recommended_next_move="Cut pricing now"),
        previous_documents=_docs("a"), current_documents=_docs("a", "new"))
    assert got["state"] == SI.NEW_INFORMATION_CHANGED_VIEW
    assert got["recommendation_changed"] is True
    assert "recommended_next_move" in got["changed_fields"]


def test_new_evidence_that_bears_on_nothing_is_not_a_gain():
    got = SI.compare(previous_decision=_decision(),
                     current_decision=_decision(),
                     previous_documents=_docs("a"),
                     current_documents=_docs("a", "new"))
    assert got["state"] == SI.NEW_INFORMATION_NOT_DECISION_RELEVANT
    assert got["represents_learning"] is False


# --- comparability -------------------------------------------------------------


def test_a_first_run_is_not_a_comparison():
    got = SI.compare(previous_decision=None, current_decision=_decision(),
                     current_documents=_docs("a"))
    assert got["state"] == SI.FIRST_OBSERVATION
    assert got["represents_learning"] is False


def test_two_different_questions_are_incomparable():
    got = SI.compare(
        previous_decision=_decision(),
        current_decision=_decision(decision_question="Should we acquire?"),
        previous_documents=_docs("a"), current_documents=_docs("a", "new"))
    assert got["state"] == SI.INCOMPARABLE
    assert got["represents_learning"] is False


def test_every_state_is_classified_as_gain_or_not_exactly_once():
    """A state in neither set would render as an unexplained blank."""
    assert SI.REPRESENTS_LEARNING.isdisjoint(SI.NO_GAIN)
    covered = SI.REPRESENTS_LEARNING | SI.NO_GAIN | {SI.FIRST_OBSERVATION}
    assert set(SI.ITERATION_STATES) == covered


# --- the hero card -------------------------------------------------------------


def test_the_hero_card_says_the_recommendation_held():
    card = SI.hero(SI.compare(
        previous_decision=_decision(), current_decision=_decision(),
        previous_documents=_docs("a"), current_documents=_docs("a", "new"),
        tested_claims=["pricing power is intact"]))
    assert card["what_held"] == "the reading"
    assert card["decision_effect"] == "the recommendation is unchanged"
    assert "pricing power" in card["what_it_tested"]


def test_the_hero_card_never_claims_a_test_that_did_not_happen():
    card = SI.hero(SI.compare(
        previous_decision=_decision(), current_decision=_decision(),
        previous_documents=_docs("a"), current_documents=_docs("a")))
    assert card["what_held"] == ""
    assert card["what_it_tested"] == "nothing that bore on the decision"
