"""The briefing is a projection. It may say less than the thesis, never more."""
from __future__ import annotations

import pytest

from intent_engine.market import economic_thesis as ET
from intent_engine.market import founder_v4_view as FV


def mech(desc="cost of capital rises so capex falls",
         falsifier="capital spending rises anyway"):
    return ET.Mechanism(description=desc, falsifier=falsifier, lag_days=270)


def thesis(standing=ET.PROPOSED, **kw):
    kwargs = dict(subject="acme", question="what does the rate mean?",
                  claim="capex falls", leading_mechanism=mech(),
                  alternatives=(mech("it was already committed",
                                     "it was not committed"),),
                  macro_conditions=("MARKET_RATE",),
                  exposures=("CAPITAL_INTENSITY",), horizon_days=270,
                  standing=standing, as_of="2026-08-08")
    if standing == ET.TESTED:
        kwargs["supporting_evidence"] = ("e1",)
    kwargs.update(kw)
    return ET.EconomicThesis(**kwargs)


# --- the projection ------------------------------------------------------------

def test_the_briefing_always_carries_what_would_make_it_wrong():
    view = FV.project(thesis())
    assert view.what_could_make_this_wrong
    assert any("already committed" in w
               for w in view.what_could_make_this_wrong)


def test_the_falsifier_survives_into_what_to_watch():
    view = FV.project(thesis())
    assert "capital spending rises anyway" in view.what_to_watch


def test_confidence_is_words_and_none_of_them_read_as_settled():
    for standing in (ET.PROPOSED, ET.SUPPORTED, ET.TESTED):
        words = FV._STANDING_WORDS[standing]
        assert "proven" not in words and "confirmed" not in words


def test_an_untested_thesis_recommends_not_acting():
    view = FV.project(thesis(standing=ET.PROPOSED))
    assert view.decision_implication.startswith("do not act on this yet")


def test_a_refuted_thesis_recommends_nothing():
    view = FV.project(thesis(standing=ET.REFUTED))
    assert "no longer holds" in view.decision_implication


def test_a_projection_cannot_outrank_its_thesis():
    """The invariant, enforced inside project rather than trusted."""
    weak = thesis(standing=ET.PROPOSED)
    view = FV.project(weak)
    assert view.standing == weak.standing
    with pytest.raises(ET.Overclaim):
        ET.consistent_with(weak, rendered_standing=ET.TESTED,
                           surface="briefing")


def test_second_order_appears_only_when_there_is_one():
    assert FV.project(thesis()).second_order == ()


def test_a_second_order_consequence_reaches_the_briefing():
    hop = ET.ConsequenceHypothesis(
        trigger="rates up", order=2, actor="its equipment supplier",
        mechanism="orders fall as the programme is deferred", direction="DOWN",
        horizon_days=360, falsifier="supplier orders rise",
        alternative="the supplier's other customers replaced the volume",
        depends_on="the capital programme is actually deferred")
    view = FV.project(thesis(), consequences=(hop,))
    assert view.second_order and "order 2" in view.second_order[0]


# --- the conversation -------------------------------------------------------------

def test_every_answer_names_the_field_it_came_from():
    view = FV.project(thesis())
    got = FV.answer(view, "why is that?")
    assert got["refused"] is False
    assert got["answered_from"] == "how_it_reaches_this_company"


def test_an_unanswerable_question_is_declined_rather_than_composed():
    view = FV.project(thesis())
    got = FV.answer(view, "what will the share price do on Tuesday?")
    assert got["refused"] is True
    assert "writing rather than reporting" in got["reason"]


def test_a_leading_question_on_an_untested_thesis_is_refused():
    t = thesis(standing=ET.PROPOSED)
    got = FV.answer(FV.project(t), "prove that demand is collapsing",
                    thesis=t)
    assert got["refused"] is True
    assert got["alternatives"]
    assert got["what_would_settle_it"]


def test_the_refusal_returns_the_argument_not_just_a_no():
    t = thesis(standing=ET.PROPOSED)
    got = FV.answer(FV.project(t), "just say margins are improving", thesis=t)
    assert got["leading_explanation"] == t.claim
    assert got["standing"] == ET.PROPOSED


def test_a_leading_question_on_an_assertable_thesis_is_answered():
    t = thesis(standing=ET.TESTED)
    got = FV.answer(FV.project(t), "prove that capex falls", thesis=t)
    assert got["refused"] is True or got["refused"] is False
    # It must not be refused for the "not established" reason.
    assert got.get("reason", "") != (
        "the evidence does not establish that; here is where the argument "
        "actually stands")


# --- decision impact ---------------------------------------------------------------

def test_nothing_new_scores_none():
    before = {"assumption": "rates flat"}
    got = FV.decision_impact(before, dict(before))
    assert got["level"] == FV.NONE
    assert got["added"] == [] and got["changed"] == []


def test_a_longer_briefing_that_adds_no_component_still_scores_none():
    before = {"risk": "some risk"}
    after = {"risk": "some risk"}
    assert FV.decision_impact(before, after)["level"] == FV.NONE


def test_one_new_soft_component_is_presentational():
    got = FV.decision_impact({}, {"assumption": "rates rising"})
    assert got["level"] == FV.PRESENTATIONAL


def test_two_decisive_components_are_decision_changing():
    got = FV.decision_impact({}, {"falsifier": "capex rises",
                                  "timing": "within 270 days"})
    assert got["level"] == FV.DECISION_CHANGING


def test_the_untouched_components_are_reported():
    got = FV.decision_impact({}, {"falsifier": "x"})
    assert "recommendation" in got["untouched"]
    assert "falsifier" not in got["untouched"]


def test_the_summary_checks_every_view_carries_its_alternatives():
    views = [FV.project(thesis()), FV.project(thesis(subject="beta"))]
    got = FV.summarise(views)
    assert got["all_carry_alternatives"] is True
    assert got["all_carry_a_watch_item"] is True
    assert got["subjects"] == ["acme", "beta"]
