"""Attacks on the V4 layers, one per way this engine could fool itself.

Each test states an economic story that LOOKS like a finding and is not, and
asserts that the layer responsible declines to promote it. A layer that only
handles the honest case is untested; these are the cases that pay.
"""
from __future__ import annotations

import datetime

import pytest

from intent_engine.market import economic_thesis as ET
from intent_engine.market import founder_v4_view as FV
from intent_engine.market import internal_state as IS
from intent_engine.market import macro_expectation as ME
from intent_engine.market import macro_state as MS
from intent_engine.market import research_policy as RP
from intent_engine.market import unsupervised as U


def obs(value, *, series="S", period="2026-06-01", published="2026-07-01",
        kind=MS.INFLATION, area=MS.CA, standing=MS.OBSERVED):
    return MS.MacroObservation(
        state_kind=kind, area=area, series_id=series, label=series,
        value=float(value), unit="index", reference_period=period,
        published_at=published, publication_basis=MS.ASSUMED_LAG,
        standing=standing, source="t")


def mech(desc="m", falsifier="f"):
    return ET.Mechanism(description=desc, falsifier=falsifier)


# --- 1. revenue up from an acquisition, not from demand ------------------------

def test_a_thesis_cannot_be_asserted_while_the_acquisition_story_is_alive():
    """Revenue rose. So would it have if they had simply bought a company."""
    with pytest.raises(ET.ThesisRejected):
        ET.EconomicThesis(
            subject="acme", question="why did revenue rise?",
            claim="underlying demand strengthened",
            leading_mechanism=mech("demand strengthened",
                                   "organic revenue is flat"),
            alternatives=(), standing=ET.SUPPORTED, as_of="2026-08-08")


# --- 2. margin up from layoffs, not from pricing --------------------------------

def test_two_explanations_of_one_margin_move_leave_no_leader():
    pricing = ET.EconomicThesis(
        subject="acme", question="why did margin improve?",
        claim="pricing power", leading_mechanism=mech("prices rose",
                                                      "realised price flat"),
        alternatives=(mech("headcount fell", "headcount flat"),),
        standing=ET.SUPPORTED, as_of="2026-08-08")
    cuts = ET.EconomicThesis(
        subject="acme", question="why did margin improve?",
        claim="cost reduction", leading_mechanism=mech("headcount fell",
                                                       "headcount flat"),
        alternatives=(mech("prices rose", "realised price flat"),),
        standing=ET.SUPPORTED, as_of="2026-08-08")
    comp = ET.Competition(question="why did margin improve?", subject="acme",
                          theses=(pricing, cuts))
    assert comp.leader is None and comp.contested is True


# --- 3. FX translation is not an economic move ----------------------------------

def test_a_currency_is_not_a_national_condition():
    """A cross rate marked CA would read as a fact about Canada's economy."""
    assert (MS.US, MS.CURRENCY) not in MS.TRACKED_CONDITIONS
    assert (MS.CA, MS.CURRENCY) not in MS.TRACKED_CONDITIONS
    assert (MS.GLOBAL, MS.CURRENCY) in MS.TRACKED_CONDITIONS


# --- 4/5. a commodity shock, and rates falling in a recession -------------------

def test_a_statistic_refuses_to_say_what_it_means_for_anyone():
    state = MS.state_of(MS.ENERGY_PRICE, [obs(200, kind=MS.ENERGY_PRICE,
                                              area=MS.GLOBAL)],
                        as_of="2026-08-01", area=MS.GLOBAL)
    with pytest.raises(MS.CausalOverreach):
        MS.consequence_of(state, "acme")


def test_two_companies_moving_together_is_not_a_transmission():
    """A common cause produces the same correlation a mechanism would.

    The engine's protection is that a transmission needs a documented exposure
    at the company end; correlation across a panel cannot manufacture one, and
    a cluster of co-moving companies has no route to becoming a fact.
    """
    found = U.Discovery(kind=U.EXPOSURE_CLUSTER, method=U.KMEANS,
                        label="CLUSTER_1", members=("a", "b"),
                        research_question="do their filings say so?")
    with pytest.raises(U.NotEvidence):
        found.as_fact()


# --- 6. the share price disagrees with the business ------------------------------

def test_an_outcome_can_be_right_while_the_reason_is_wrong():
    thesis = ET.EconomicThesis(
        subject="acme", question="q", claim="margins improve",
        leading_mechanism=mech("pricing power", "realised price flat"),
        alternatives=(mech("layoffs", "headcount flat"),),
        as_of="2026-08-08")
    got = ET.score(thesis, outcome_matched=True, mechanism_matched=False)
    assert got.verdict == ET.RIGHT_FOR_THE_WRONG_REASON


# --- 7. backlog up while demand weakens -------------------------------------------

def test_a_backlog_growing_into_weak_demand_demands_an_explanation():
    flagged = ET.check_consistency(ET.Scenario(
        kind=ET.BASE, direction="DOWN",
        assumptions=("demand DOWN across the segment",
                     "backlog UP quarter on quarter")))
    assert flagged.inconsistencies
    assert "supply constraint" in flagged.inconsistencies[0]


# --- 8. a beat against an expectation that was lowered ----------------------------

def test_a_surprise_is_measured_against_the_expectation_that_preceded_it():
    """Lowering the bar first is exactly what the temporal wall refuses."""
    history = [obs(10, period="2026-01-01", published="2026-02-01"),
               obs(10, period="2026-02-01", published="2026-03-01"),
               obs(10, period="2026-03-01", published="2026-04-01"),
               obs(2, period="2026-04-01", published="2026-05-01")]
    late = ME.forecast(history, series_id="S", target_period="2026-04-01",
                       made_at="2026-06-01", method=ME.RANDOM_WALK)
    with pytest.raises(ME.Foresight):
        ME.reconcile(late, history, as_of="2026-07-01")


# --- 9/10. common cause, and the wrong lag -----------------------------------------

def test_a_consequence_past_the_first_hop_must_name_its_dependency():
    with pytest.raises(ET.ThesisRejected):
        ET.ConsequenceHypothesis(
            trigger="rates up", order=2, actor="supplier",
            mechanism="orders fall", direction="DOWN", horizon_days=180,
            falsifier="orders rise", alternative="other customers replaced it",
            depends_on="")


def test_a_broken_first_hop_voids_the_second_rather_than_weakening_it():
    def hop(order, standing, depends=""):
        return ET.ConsequenceHypothesis(
            trigger="t", order=order, actor="a", mechanism=f"hop{order}",
            direction="DOWN", horizon_days=90, falsifier="f",
            alternative="alt", depends_on=depends, standing=standing)
    got = ET.propagate([hop(1, ET.REFUTED), hop(2, ET.SUPPORTED, "hop1")])
    assert got["standing"] == ET.REFUTED


# --- 11. a regime that reverses ------------------------------------------------------

def test_a_partition_that_does_not_survive_a_holdout_says_so():
    """Instability is reported, not smoothed away."""
    score = U.DiscoveryScore(method=U.KMEANS, groups=3, separation=0.8,
                             coherence=2.0, stability=0.11, utility=None)
    assert score.stability < 0.5
    assert score.economically_useful is False


# --- 12/13. similarity and analogy are not evidence ------------------------------------

def test_a_regime_membership_cannot_become_a_fact():
    found = U.Discovery(kind=U.REGIME, method=U.GAUSSIAN_MIXTURE,
                        label="REGIME_2", members=("2026-03",),
                        research_question="what happened that month?")
    with pytest.raises(U.NotEvidence):
        found.as_fact()


def test_a_historical_analogy_carries_a_question_not_a_conclusion():
    got = U.find_anomalies(
        [obs(5, period=f"2025-{m:02d}-01", published=f"2025-{m:02d}-28")
         for m in range(1, 10)]
        + [obs(80, period="2025-10-01", published="2025-10-28")]
        + [obs(5, period=f"2025-{m:02d}-01", published=f"2025-{m:02d}-28")
           for m in range(11, 13)], as_of="2026-12-31")
    assert all(d["research_question"] for d in got["discoveries"])
    assert "revision" in got["note"]


# --- 14/16. reward hacking and confirmation bias ------------------------------------------

def test_a_policy_that_only_asks_the_subject_about_itself_scores_negative():
    log = [RP.ResearchRecord(
        action=RP.ResearchAction(source_family=RP.COMPANY_OWNED,
                                 subject="acme"),
        outcome=RP.ResearchOutcome(outcome=RP.USED, independent=False,
                                   duplicate=True)) for _ in range(40)]
    got = RP.evaluate_offline(log, RP.FixedPolicy(RP.COMPANY_OWNED))
    assert got.mean_reward < 0


def test_volume_is_worth_less_than_one_discriminating_answer():
    many = sum(RP.reward(RP.ResearchRecord(
        action=RP.ResearchAction(source_family=RP.COMPANY_OWNED,
                                 subject="a"),
        outcome=RP.ResearchOutcome(outcome=RP.USED, independent=False,
                                   duplicate=True))) for _ in range(25))
    one = RP.reward(RP.ResearchRecord(
        action=RP.ResearchAction(source_family=RP.REGULATORY_FILING,
                                 subject="a"),
        outcome=RP.ResearchOutcome(outcome=RP.USED, independent=True,
                                   discriminating=True, resolved_open_question=True,
                                   decision_relevant=True)))
    assert one > many


def test_a_policy_cannot_reach_a_non_research_action():
    with pytest.raises(RP.OutsideResearch):
        RP.guard_action("deploy")


# --- 15/17. revision lookahead and future leakage ------------------------------------------

def test_a_revision_cannot_be_read_before_it_was_published():
    first = obs(2.1, period="2026-03-01", published="2026-04-30")
    revised = MS.revise(first, value=1.4, published_at="2026-07-30")
    at_may = MS.as_known_at([first, revised], "2026-05-15")
    assert len(at_may) == 1 and at_may[0].value == 2.1
    at_august = MS.as_known_at([first, revised], "2026-08-15")
    assert at_august[0].value == 1.4


def test_a_revision_cannot_predate_the_figure_it_revises():
    first = obs(2.1, period="2026-03-01", published="2026-04-30")
    with pytest.raises(MS.MacroRejected):
        MS.revise(first, value=1.4, published_at="2026-01-01")


def test_a_backtest_origin_never_sees_the_answer():
    values = [obs(float(i), period=f"2025-{i:02d}-01",
                  published=f"2025-{i:02d}-28") for i in range(1, 13)]
    got = ME.backtest(values, series_id="S", min_history=6)
    assert got["scored"] > 0
    walk = next(s for s in got["scores"] if s["method"] == ME.RANDOM_WALK)
    # A random walk on a perfect +1 ramp is wrong by exactly 1 every time. If
    # the origin could see the target it would be wrong by zero.
    assert abs(walk["rmse"] - 1.0) < 1e-9


# --- 18. synthetic data leaking into a live conclusion --------------------------------------

def test_synthetic_internals_cannot_reach_a_real_companys_briefing():
    facts = [f for f in IS.synthetic_enterprise()]
    relabelled = [__import__("dataclasses").replace(f, company_id="acme")
                  for f in facts]
    thesis = ET.EconomicThesis(
        subject="acme", question="q", claim="c",
        leading_mechanism=mech(), as_of="2026-08-08")
    with pytest.raises(IS.SyntheticLeak):
        IS.combined_picture(thesis, relabelled, for_company="acme")


def test_the_synthetic_company_may_use_its_own_synthetic_facts():
    thesis = ET.EconomicThesis(
        subject=IS.SYNTHETIC_COMPANY, question="q", claim="c",
        leading_mechanism=mech(), as_of="2026-08-08")
    got = IS.combined_picture(thesis, IS.synthetic_enterprise(),
                              for_company=IS.SYNTHETIC_COMPANY)
    assert got["provenance"] == IS.SYNTHETIC
    assert got["internal_recorded"]


def test_one_companys_internals_are_never_read_for_another():
    facts = IS.synthetic_enterprise()
    assert IS.readable(facts, for_company="someone_else") == ()
    with pytest.raises(IS.PermissionRefused):
        IS.readable(facts, for_company="")


def test_a_pipeline_is_never_firm():
    pipeline = [f for f in IS.synthetic_enterprise()
                if f.kind == IS.PIPELINE and f.standing == IS.FORECAST]
    assert pipeline and all(not f.firm for f in pipeline)


# --- 19/20. the CEO leads, the slide overstates -----------------------------------------------

def test_a_leading_question_does_not_get_the_conclusion_it_asked_for():
    thesis = ET.EconomicThesis(
        subject="acme", question="q", claim="capex falls",
        leading_mechanism=mech(), alternatives=(mech("committed", "not"),),
        as_of="2026-08-08")
    got = FV.answer(FV.project(thesis), "prove that demand is collapsing",
                    thesis=thesis)
    assert got["refused"] is True
    assert got["alternatives"] and got["what_would_settle_it"]


def test_a_slide_cannot_upgrade_a_proposed_thesis():
    thesis = ET.EconomicThesis(
        subject="acme", question="q", claim="c", leading_mechanism=mech(),
        as_of="2026-08-08")
    with pytest.raises(ET.Overclaim):
        ET.consistent_with(thesis, rendered_standing=ET.TESTED,
                           surface="board slide")


def test_a_deck_cannot_quietly_drop_the_alternative():
    thesis = ET.EconomicThesis(
        subject="acme", question="q", claim="c", leading_mechanism=mech(),
        alternatives=(mech("the other story", "it was not"),),
        standing=ET.SUPPORTED, as_of="2026-08-08")
    with pytest.raises(ET.Overclaim):
        ET.consistent_with(thesis, rendered_standing=ET.SUPPORTED,
                           drops_alternatives=True, surface="deck")


# --- and the one that is easiest to forget -------------------------------------------------

def test_an_unmeasured_condition_never_reads_as_a_calm_one():
    state = MS.unknown(MS.CONSUMER_DEMAND)
    assert state.moved == MS.FLAT
    assert state.known is False
    # FLAT is the field default; `known` is what a reader must branch on, and
    # the summary reports the condition as a blind spot rather than as steady.
    got = MS.summarise([state])
    assert MS.CONSUMER_DEMAND in got["unknown_kinds"]
    assert got["moved"] == {}
