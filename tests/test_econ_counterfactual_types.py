"""§12/§24/§30: a counterfactual cannot overclaim causality.

The three required break-proof outcomes from §30 are the three tests at the
top of this file: a scenario relabelled causal must be RED, a simulation
relabelled causal must be RED, and a missing label must be RED.
"""
from __future__ import annotations

import pytest

from intent_engine.econ import counterfactual as CF
from intent_engine.econ.causal import CAUSAL_LANGUAGE_FLOOR
from intent_engine.econ.vocabulary import EconError


# =============================================================================
# §30's three required mutations
# =============================================================================

def test_a_scenario_cannot_be_relabelled_causal():
    s = CF.scenario(question="what if rates had stayed at 2%?",
                    intervention="the policy rate stayed at 2%",
                    outcome="housing turnover", direction=CF.UP, as_of="d")
    c = CF.causal(question="what if rates had stayed at 2%?",
                  intervention="the policy rate stayed at 2%",
                  outcome="housing turnover", direction=CF.UP, as_of="d",
                  identification="unanticipated announcement, flat pre-trends",
                  evidence_level=4)
    with pytest.raises(CF.MislabelledCounterfactual):
        CF.assert_no_upgrade(s, c)


def test_a_simulation_cannot_be_relabelled_causal():
    sim = CF.simulation(question="q", intervention="i", outcome="o",
                        direction=CF.UP, as_of="d",
                        assumptions=("spread constant",))
    c = CF.causal(question="q", intervention="i", outcome="o",
                  direction=CF.UP, as_of="d",
                  identification="a natural experiment", evidence_level=4)
    with pytest.raises(CF.MislabelledCounterfactual):
        CF.assert_no_upgrade(sim, c)


def test_counterfactual_prose_with_no_label_is_refused():
    with pytest.raises(CF.UnlabelledCounterfactual):
        CF.assert_labelled(
            "Had rates stayed at 2%, turnover would have been higher.")


def test_labelled_prose_is_accepted():
    """Positive control. Without it the test above passes for a checker that
    refuses everything."""
    sim = CF.simulation(question="q", intervention="rates stayed at 2%",
                        outcome="turnover", direction=CF.UP, as_of="d",
                        assumptions=("spread constant",))
    CF.assert_labelled(sim.statement())


def test_non_counterfactual_prose_is_left_alone():
    """The wall must not fire on ordinary sentences, or callers will route
    around it."""
    CF.assert_labelled("Household delinquency rose to 2.85% in April.")
    CF.assert_labelled("The engine declined to trade.")


# =============================================================================
# There is no default type
# =============================================================================

def test_there_is_no_default_counterfactual_type():
    with pytest.raises(TypeError):
        CF.Counterfactual(question="q", intervention="i", outcome="o",
                          direction=CF.UP, as_of="d")


def test_an_unknown_type_is_refused():
    with pytest.raises(EconError):
        CF.Counterfactual(question="q", intervention="i", outcome="o",
                          direction=CF.UP, cf_type="PROBABLY_CAUSAL",
                          as_of="d")


# =============================================================================
# The strongest label is the hardest to obtain
# =============================================================================

def test_causal_requires_an_identification_strategy():
    with pytest.raises(EconError) as e:
        CF.causal(question="q", intervention="i", outcome="o",
                  direction=CF.UP, as_of="d", identification="",
                  evidence_level=4)
    assert "identification" in str(e.value)


def test_causal_requires_evidence_at_or_above_the_ladder_floor():
    with pytest.raises(EconError) as e:
        CF.causal(question="q", intervention="i", outcome="o",
                  direction=CF.UP, as_of="d",
                  identification="a lagged association", evidence_level=1)
    assert str(CAUSAL_LANGUAGE_FLOOR) in str(e.value)


def test_a_simulation_must_list_its_assumptions():
    with pytest.raises(EconError) as e:
        CF.simulation(question="q", intervention="i", outcome="o",
                      direction=CF.UP, as_of="d", assumptions=())
    assert "assumptions" in str(e.value)


def test_a_scenario_may_not_carry_a_magnitude():
    """A hypothesis nobody measured, stated to a decimal place, is the most
    misleading object this package can produce."""
    with pytest.raises(EconError) as e:
        CF.Counterfactual(question="q", intervention="i", outcome="o",
                          direction=CF.UP, cf_type=CF.SCENARIO_ASSUMPTION,
                          as_of="d", magnitude=18.0)
    assert "magnitude" in str(e.value)


def test_a_scenario_may_not_carry_an_evidence_level():
    with pytest.raises(EconError):
        CF.Counterfactual(question="q", intervention="i", outcome="o",
                          direction=CF.UP, cf_type=CF.SCENARIO_ASSUMPTION,
                          as_of="d", evidence_level=3)


# =============================================================================
# Only an identified effect licenses acting on the cause
# =============================================================================

def test_only_a_causal_estimate_may_inform_an_intervention():
    s = CF.scenario(question="q", intervention="i", outcome="o",
                    direction=CF.UP, as_of="d")
    sim = CF.simulation(question="q", intervention="i", outcome="o",
                        direction=CF.UP, as_of="d", assumptions=("a",))
    c = CF.causal(question="q", intervention="i", outcome="o",
                  direction=CF.UP, as_of="d", identification="an experiment",
                  evidence_level=4)
    assert not s.may_inform_intervention
    assert not sim.may_inform_intervention
    assert c.may_inform_intervention


def test_every_type_renders_its_marker_inline_not_as_a_suffix():
    """A suffix is what a renderer trims when the line is too long."""
    for cf in (
        CF.scenario(question="q", intervention="rates held", outcome="o",
                    direction=CF.UP, as_of="d"),
        CF.simulation(question="q", intervention="rates held", outcome="o",
                      direction=CF.UP, as_of="d", assumptions=("a",)),
        CF.causal(question="q", intervention="rates held", outcome="o",
                  direction=CF.UP, as_of="d", identification="x",
                  evidence_level=3),
    ):
        st = cf.statement()
        assert st.startswith(cf.marker), (
            f"{cf.cf_type} renders its marker at {st.index(cf.marker)}; it "
            "must lead the sentence so trimming the tail cannot remove it")
        CF.assert_labelled(st)


def test_an_unchanged_direction_never_renders_a_magnitude():
    c = CF.simulation(question="q", intervention="i", outcome="o",
                      direction=CF.UNCHANGED, as_of="d",
                      assumptions=("a",), magnitude=5, magnitude_unit="%")
    assert "5" not in c.statement()


def test_summarise_counts_what_may_inform_a_decision():
    cfs = [
        CF.scenario(question="q1", intervention="i", outcome="o",
                    direction=CF.UP, as_of="d"),
        CF.causal(question="q2", intervention="i", outcome="o",
                  direction=CF.UP, as_of="d", identification="x",
                  evidence_level=5),
    ]
    s = CF.summarise(cfs)
    assert s["by_type"][CF.SCENARIO_ASSUMPTION] == 1
    assert s["by_type"][CF.CAUSAL_ESTIMATE] == 1
    assert s["may_inform_intervention"] == 1
