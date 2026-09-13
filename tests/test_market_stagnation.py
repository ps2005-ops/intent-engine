"""Working hard and learning nothing — five questions, never averaged.

The central test is `test_an_unmeasurable_check_is_not_a_passing_grade`. This
project has shipped a metric that could only ever return a positive, and the
lesson was that a measurement which cannot come back negative is not a
measurement. The inverse matters just as much: a ratio nobody could compute
must not be reported in the same column as one that came back fine.
"""
from __future__ import annotations

import pytest

from intent_engine.market import stagnation as ST


def evaluate(**kw):
    return {c.name: c for c in ST.evaluate(**kw)}


# --- the five are separate --------------------------------------------------

def test_there_are_five_and_each_means_something_different():
    assert len(ST.CHECKS) == 5
    meanings = {ST.CHECK_MEANING[c] for c in ST.CHECKS}
    assert len(meanings) == 5


def test_every_check_names_who_would_act_on_it():
    for name in ST.CHECKS:
        assert ST.CHECK_MEANING[name].strip()
        assert name in ST.MIN_ACTIVITY and name in ST.THRESHOLD


def test_one_missing_input_does_not_cost_the_other_answers():
    """A caller short of one term gets UNMEASURABLE for that check and real
    answers for the rest, not a single score silently missing a term."""
    got = evaluate(evidence_rows=500, knowledge_effects=2,
                   theses=None, theses_resolved=None)
    assert got[ST.EVIDENCE_WITHOUT_EFFECT].outcome == ST.FIRING
    assert got[ST.THESES_WITHOUT_RESOLUTION].outcome == ST.UNMEASURABLE


# --- each of the five fires on its own condition ----------------------------

def test_evidence_without_effect_fires():
    got = evaluate(evidence_rows=500, knowledge_effects=2)
    assert got[ST.EVIDENCE_WITHOUT_EFFECT].outcome == ST.FIRING


def test_theses_without_resolution_fires():
    got = evaluate(theses=40, theses_resolved=1)
    assert got[ST.THESES_WITHOUT_RESOLUTION].outcome == ST.FIRING


def test_spend_without_value_fires():
    got = evaluate(research_cost=100, realised_value=2)
    assert got[ST.SPEND_WITHOUT_VALUE].outcome == ST.FIRING


def test_discovery_without_validation_fires():
    got = evaluate(discoveries=20, discoveries_validated=1)
    assert got[ST.DISCOVERY_WITHOUT_VALIDATION].outcome == ST.FIRING


def test_analysis_without_impact_fires():
    got = evaluate(analyses=200, decision_impacts=0)
    assert got[ST.ANALYSIS_WITHOUT_IMPACT].outcome == ST.FIRING


# --- and each can report the negative ---------------------------------------

def test_a_healthy_ratio_reports_clear_rather_than_silence():
    """A check that only ever fires is an alarm, not a measurement."""
    got = evaluate(evidence_rows=500, knowledge_effects=200,
                   theses=40, theses_resolved=20,
                   research_cost=100, realised_value=60,
                   discoveries=20, discoveries_validated=15,
                   analyses=200, decision_impacts=40)
    assert {c.outcome for c in got.values()} == {ST.CLEAR}


def test_every_check_can_reach_every_outcome():
    """Each of the three answers is reachable for each of the five, or the
    vocabulary is bigger than the behaviour."""
    firing = evaluate(evidence_rows=500, knowledge_effects=2,
                      theses=40, theses_resolved=1,
                      research_cost=100, realised_value=2,
                      discoveries=20, discoveries_validated=1,
                      analyses=200, decision_impacts=0)
    clear = evaluate(evidence_rows=500, knowledge_effects=400,
                     theses=40, theses_resolved=30,
                     research_cost=100, realised_value=80,
                     discoveries=20, discoveries_validated=18,
                     analyses=200, decision_impacts=100)
    unmeasurable = evaluate()
    for name in ST.CHECKS:
        assert firing[name].outcome == ST.FIRING, name
        assert clear[name].outcome == ST.CLEAR, name
        assert unmeasurable[name].outcome == ST.UNMEASURABLE, name


# --- unmeasurable is not a pass ---------------------------------------------

def test_an_unmeasurable_check_is_not_a_passing_grade():
    got = evaluate()
    for check in got.values():
        assert check.outcome == ST.UNMEASURABLE
        assert check.ratio is None
        assert "absence of a rate" in check.detail


def test_a_quiet_period_is_not_a_stalled_one():
    """Two evidence rows producing no effects is a quiet night, not a defect,
    and firing on it would train the operator to ignore the alert."""
    got = evaluate(evidence_rows=2, knowledge_effects=0)
    check = got[ST.EVIDENCE_WITHOUT_EFFECT]
    assert check.outcome == ST.UNMEASURABLE
    assert "quiet period" in check.detail


def test_the_activity_floor_is_per_check_rather_than_shared():
    """Fifty evidence rows and five theses are different amounts of activity;
    one shared floor would either silence the theses check or make the
    evidence check fire on noise."""
    assert len(set(ST.MIN_ACTIVITY.values())) > 1


def test_zero_activity_never_divides():
    got = evaluate(evidence_rows=0, knowledge_effects=0)
    assert got[ST.EVIDENCE_WITHOUT_EFFECT].outcome == ST.UNMEASURABLE


# --- the summary ------------------------------------------------------------

def test_the_summary_separates_unmeasurable_from_clear():
    checks = ST.evaluate(evidence_rows=500, knowledge_effects=2,
                         theses=40, theses_resolved=30)
    got = ST.summarise(checks)
    assert got["firing"] == [ST.EVIDENCE_WITHOUT_EFFECT]
    assert ST.THESES_WITHOUT_RESOLUTION not in got["unmeasurable"]
    assert set(got["unmeasurable"]) == {
        ST.SPEND_WITHOUT_VALUE, ST.DISCOVERY_WITHOUT_VALIDATION,
        ST.ANALYSIS_WITHOUT_IMPACT}
    assert got["by_outcome"][ST.UNMEASURABLE] == 3


def test_no_overall_stagnation_score_is_produced():
    """Five causes averaged into one number is a number nobody can act on."""
    got = ST.summarise(ST.evaluate(evidence_rows=500, knowledge_effects=2))
    flat = " ".join(str(k) for k in got).lower()
    for banned in ("score", "overall", "stagnation_level", "index"):
        assert banned not in flat


def test_an_unknown_check_name_is_refused():
    with pytest.raises(ValueError):
        ST.Check(name="PROBABLY_FINE", outcome=ST.CLEAR)


def test_an_unknown_outcome_is_refused():
    with pytest.raises(ValueError):
        ST.Check(name=ST.EVIDENCE_WITHOUT_EFFECT, outcome="OK")
