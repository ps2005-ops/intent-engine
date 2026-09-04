"""Learning: new vs duplicate evidence, zero-trade, promotion, retirement,
vintage replay, attacks, and the research queue.

Section 32's learning block.
"""
from __future__ import annotations

import pytest

from intent_engine.econ import acceleration as AC
from intent_engine.econ import attacks as AT
from intent_engine.econ import belief as B
from intent_engine.econ import evidence as EV
from intent_engine.econ import promotion as PR
from intent_engine.econ import replay as RP
from intent_engine.econ import voi as VOI
from intent_engine.econ import zero_trade as ZT
from intent_engine.econ import vocabulary as V


def a_node(statement="rising: we added staff", at="2026-06-01",
           available=None, subject="acme", publisher="Acme Inc"):
    return EV.node(node_class=V.COMPANY, kind="hiring", subject=subject,
                   standing=V.OBSERVED, occurred_at=at,
                   available_at=available or at, publisher=publisher,
                   statement=statement, producer="test")


def a_belief(**kw):
    base = dict(proposition="hiring is slowing across the panel",
                probability=0.6, mechanism="a stated path",
                falsifier="three quarters of accelerating hiring",
                expected_observations=("hiring reported down at four firms",),
                at="2026-06-01")
    base.update(kw)
    return B.declare(**base)


# --- new vs duplicate evidence ---------------------------------------------
def test_re_reading_an_unchanged_document_produces_no_new_fact():
    graph = EV.EvidenceGraph()
    first = graph.add(a_node())
    again = graph.add(a_node())
    assert len(graph) == 1
    assert first.node_id == again.node_id


def test_the_id_does_not_include_the_date_it_was_read():
    """The measured defect: a content hash that included the sweep date made
    every nightly re-read a new fact, and the corpus grew forever."""
    monday = a_node(); monday_id = monday.node_id
    tuesday = EV.node(node_class=V.COMPANY, kind="hiring", subject="acme",
                      standing=V.OBSERVED, occurred_at="2026-06-01",
                      available_at="2026-06-01", publisher="Acme Inc",
                      statement="rising: we added staff", producer="test",
                      retrieved_at="2026-08-24")
    assert tuesday.node_id == monday_id


def test_a_changed_statement_is_a_new_fact():
    graph = EV.EvidenceGraph([a_node()])
    graph.add(a_node(statement="falling: we reduced headcount"))
    assert len(graph) == 2


def test_a_revision_appends_and_keeps_the_prior_reading():
    first = a_node(statement="rising: hiring up 2%")
    revised = EV.revise(first, statement="rising: hiring up 1.4%",
                        available_at="2026-09-15")
    assert revised.revisions[-1].statement == "rising: hiring up 2%"
    assert revised.available_at == "2026-09-15"


# --- vintage ----------------------------------------------------------------
def test_a_fact_is_invisible_before_it_was_available():
    late = a_node(at="2026-06-30", available="2026-07-15")
    assert not late.visible_at("2026-07-01")
    assert late.visible_at("2026-07-15")


def test_a_node_cannot_be_available_before_it_occurred():
    with pytest.raises(V.EconError, match="before it happens"):
        a_node(at="2026-07-01", available="2026-06-01")


def test_knowable_at_returns_the_vintage_not_the_latest_value():
    first = a_node(statement="rising: hiring up 2%", at="2026-06-30",
                   available="2026-07-15")
    revised = EV.revise(first, statement="rising: hiring up 1.4%",
                        available_at="2026-09-15")
    at_july = RP.knowable_at([revised], "2026-08-01")
    assert len(at_july) == 1
    assert at_july[0].statement == "rising: hiring up 2%", (
        "the September revision was visible in August; a replay reading it "
        "has given the engine two months of foresight")


def test_a_replay_reading_its_own_future_is_refused():
    late = a_node(at="2026-09-01", available="2026-09-01")
    with pytest.raises(RP.VintageViolation, match="the present, wearing"):
        RP.assert_vintage([late], when="2026-07-01", where="a replay")


def test_the_four_way_verdict_separates_luck_from_mechanism():
    b = a_belief()
    e = B.preregister(belief=b, quantity="hiring", direction=B.DOWN,
                      confidence=0.6, resolution_rule="a rule",
                      at="2026-06-01", information_cutoff="2026-05-28",
                      horizon_days=30, expires_at="2026-07-01")
    lucky = RP.score(e, outcome_correct=True, mechanism_held=False,
                     basis="the mechanism's own observable did not move",
                     nodes=[a_node()])
    assert lucky.verdict == RP.RIGHT_FOR_WRONG_REASON
    assert not lucky.belief_update_allowed, (
        "a right call through a mechanism that did not hold was allowed to "
        "raise confidence in that mechanism")
    earned = RP.score(e, outcome_correct=True, mechanism_held=True,
                      basis="the observable moved as stated",
                      nodes=[a_node()])
    assert earned.verdict == RP.RIGHT_FOR_RIGHT_REASON
    assert earned.belief_update_allowed


def test_the_summary_exposes_the_lucky_share():
    b = a_belief()
    e = B.preregister(belief=b, quantity="h", direction=B.DOWN,
                      confidence=0.6, resolution_rule="r", at="2026-06-01",
                      information_cutoff="2026-05-28", horizon_days=30,
                      expires_at="2026-07-01")
    verdicts = ([RP.score(e, outcome_correct=True, mechanism_held=True,
                          basis="b", nodes=[])] * 3
                + [RP.score(e, outcome_correct=True, mechanism_held=False,
                            basis="b", nodes=[])])
    got = RP.summarise(verdicts)
    assert got["correct"] == 4
    assert got["lucky_share"] == pytest.approx(0.25)
    assert got["blocked_from_updating_beliefs"] == 1


# --- zero-trade -------------------------------------------------------------
def test_a_rejection_must_name_the_gate():
    with pytest.raises(V.EconError, match="names the gate"):
        ZT.rejected(subject="acme", as_of="2026-08-01", gate="",
                    reason="something")


def test_a_declined_signal_that_was_right_to_decline_is_learning():
    r = ZT.rejected(subject="acme", as_of="2026-08-01",
                    gate="independence floor: one origin",
                    reason="the only source was the company's own release")
    done = ZT.resolve(r, verdict=ZT.CORRECTLY_DECLINED, at="2026-09-01",
                      subsequent="the claim was not repeated by any "
                                 "independent source and no move followed")
    assert done.verdict == ZT.CORRECTLY_DECLINED
    assert not done.actionable


def test_a_structurally_invisible_miss_is_a_source_problem_not_a_threshold():
    a = ZT.absent(subject="acme", as_of="2026-08-01",
                  what_moved="the stock fell 9% on a supplier failure",
                  reason="no signal fired")
    done = ZT.resolve(a, verdict=ZT.STRUCTURALLY_INVISIBLE, at="2026-09-01",
                      subsequent="the supplier's filing named the failure "
                                 "three weeks later",
                      missing_evidence="private supplier capacity data",
                      obtainable=False)
    assert done.coverage_gap
    assert not done.actionable
    summary = ZT.summarise([done])
    assert summary["coverage_gaps"][0]["missing"]
    assert "source problem" in summary["note"]


def test_structurally_invisible_must_state_that_it_was_unobtainable():
    a = ZT.absent(subject="acme", as_of="2026-08-01", what_moved="a move",
                  reason="no signal")
    with pytest.raises(V.EconError, match="completely different finding"):
        ZT.resolve(a, verdict=ZT.STRUCTURALLY_INVISIBLE, at="2026-09-01",
                   subsequent="something", obtainable=None)


def test_decline_precision_is_over_scored_rejections_only():
    """A rate over ALL rejections counts every open window as correct, which
    is how a gate proves itself right by being recent."""
    scored = ZT.resolve(
        ZT.rejected(subject="a", as_of="2026-08-01", gate="g", reason="r1"),
        verdict=ZT.CORRECTLY_DECLINED, at="2026-09-01", subsequent="s")
    still_open = ZT.rejected(subject="b", as_of="2026-08-01", gate="g",
                             reason="r2")
    got = ZT.summarise([scored, still_open])
    assert got["rejections_scored"] == 1
    assert got["decline_precision"] == 1.0


def test_no_precision_is_reported_when_nothing_has_been_scored():
    got = ZT.summarise([ZT.rejected(subject="a", as_of="2026-08-01",
                                    gate="g", reason="r")])
    assert got["decline_precision"] is None


# --- promotion --------------------------------------------------------------
def a_candidate():
    return PR.propose(candidate_id="c1", claim="a claim",
                      mechanism="a stated mechanism", at="2026-01-01")


def test_a_candidate_cannot_jump_to_promoted():
    with pytest.raises(V.EconError, match="not a declared transition"):
        PR.move(a_candidate(), to=PR.PROMOTED, at="2026-02-01",
                reason="the backtest looked good")


def test_replication_needs_distinct_subjects_and_distinct_regimes():
    c = a_candidate()
    c = PR.move(c, to=PR.OBSERVED, at="2026-02-01", reason="seen")
    c = PR.move(c, to=PR.TESTED, at="2026-03-01", reason="resolved")
    for _ in range(4):
        c = PR.confirm(c, subject="acme", regime="tightening", at="2026-03-01")
    with pytest.raises(PR.PromotionRefused, match="counted more than once"):
        PR.replicate(c, at="2026-04-01")

    c = PR.confirm(c, subject="beta", regime="tightening", at="2026-04-01")
    c = PR.confirm(c, subject="gamma", regime="tightening", at="2026-04-01")
    with pytest.raises(PR.PromotionRefused, match="description of those"):
        PR.replicate(c, at="2026-05-01")

    c = PR.confirm(c, subject="delta", regime="easing", at="2026-05-01")
    assert PR.replicate(c, at="2026-05-01").state == PR.REPLICATED


def _replicated():
    c = a_candidate()
    c = PR.move(c, to=PR.OBSERVED, at="2026-02-01", reason="seen")
    c = PR.move(c, to=PR.TESTED, at="2026-03-01", reason="resolved")
    for subject, regime in (("acme", "tightening"), ("beta", "easing"),
                            ("gamma", "easing"), ("delta", "tightening")):
        c = PR.confirm(c, subject=subject, regime=regime, at="2026-04-01")
    return PR.replicate(c, at="2026-05-01")


def full_defences(**kw):
    base = dict(holdout_period="2026-H1 held out",
                walk_forward="quarterly refit, 6 folds",
                parameter_sensitivity="stable over lag 3-9 days",
                regime_stability="holds in both regimes tested",
                tests_considered=6, null_baseline="a shuffled-label null",
                turnover_and_friction="12% annual turnover at 4bp")
    base.update(kw)
    return PR.Defences(**base)


def test_promotion_refuses_without_every_defence():
    c = _replicated()
    with pytest.raises(PR.PromotionRefused, match="invisible when absent"):
        PR.promote(c, at="2026-06-01",
                   defences=full_defences(null_baseline=""))


def test_promotion_refuses_without_a_multiple_testing_count():
    c = _replicated()
    with pytest.raises(PR.PromotionRefused, match="tests_considered"):
        PR.promote(c, at="2026-06-01", defences=full_defences(
            tests_considered=0))


def test_the_bar_rises_with_the_size_of_the_family():
    c = _replicated()
    assert PR.promote(c, at="2026-06-01",
                      defences=full_defences()).state == PR.PROMOTED
    with pytest.raises(PR.PromotionRefused, match="pass on noise"):
        PR.promote(c, at="2026-06-01",
                   defences=full_defences(tests_considered=40))


def test_a_standing_contradiction_blocks_promotion():
    c = PR.contradict(_replicated(), subject="eps", regime="easing",
                      at="2026-05-15")
    with pytest.raises(PR.PromotionRefused, match="filtered record"):
        PR.promote(c, at="2026-06-01", defences=full_defences())


def test_a_promoted_candidate_can_be_weakened_and_retired():
    c = PR.promote(_replicated(), at="2026-06-01", defences=full_defences())
    c = PR.move(c, to=PR.WEAKENED, at="2026-07-01", reason="two failures")
    c = PR.move(c, to=PR.RETIRED, at="2026-08-01", reason="withdrawn")
    assert c.state == PR.RETIRED
    assert PR.TRANSITIONS[PR.RETIRED] == ()


# --- attacks ----------------------------------------------------------------
def a_proposal(**kw):
    base = dict(kind=AT.CONTRARIAN, claim="inference efficiency outruns "
                                          "compute demand",
                mechanism="a stated path", evidence="nothing observed yet",
                contradiction="the incumbent belief says demand compounds",
                observable_test="tokens served per dollar of capex, "
                                "quarterly, across three hyperscalers",
                probability=0.9,
                decision_implication="defer capacity commitments a quarter")
    base.update(kw)
    return base


def test_an_attack_missing_any_of_the_six_fields_is_refused():
    for field in ("claim", "mechanism", "contradiction", "observable_test",
                  "decision_implication"):
        with pytest.raises(AT.AttackRejected, match="a mood|refused"):
            AT.accept_proposal(a_belief(), a_proposal(**{field: ""}),
                               category=AT.SUBSTITUTION_CATEGORY,
                               at="2026-08-24")


def test_an_authored_attack_cannot_open_above_the_unevidenced_cap():
    got = AT.accept_proposal(a_belief(), a_proposal(),
                             category=AT.SUBSTITUTION_CATEGORY,
                             at="2026-08-24")
    assert got.probability == AT.MAX_UNEVIDENCED_PROBABILITY


def test_an_untested_attack_says_so_in_its_own_sentence():
    got = AT.accept_proposal(a_belief(), a_proposal(),
                             category=AT.SUBSTITUTION_CATEGORY,
                             at="2026-08-24")
    assert got.status == AT.UNTESTED
    assert "UNTESTED HYPOTHESIS" in got.sentence()
    assert "test:" in got.sentence()


def test_an_attack_cannot_be_marked_tested_without_an_observation():
    got = AT.accept_proposal(a_belief(), a_proposal(),
                             category=AT.SUBSTITUTION_CATEGORY,
                             at="2026-08-24")
    with pytest.raises(V.EconError, match="names the observations"):
        AT.observe(got, consistent=True, at="2026-09-01", observations=())


def test_no_attacks_are_produced_without_an_author():
    """There is no template. An empty slot is reported, never filled."""
    assert AT.for_belief(a_belief(), at="2026-08-24") == []


def test_slots_are_filled_only_for_categories_that_can_be_formed():
    macro = AT.applicable_categories(a_belief(), company_scoped=False)
    company = AT.applicable_categories(a_belief(), company_scoped=True)
    assert set(macro) < set(company)
    assert AT.CUSTOMER_INVERSION not in macro


def test_the_most_dangerous_attack_weighs_the_stake_not_only_the_odds():
    weak_belief = a_belief(probability=0.51)
    strong_belief = a_belief(probability=0.95,
                             proposition="a different proposition")
    attack_kw = dict(category=AT.SUBSTITUTION_CATEGORY, at="2026-08-24")
    a1 = AT.accept_proposal(weak_belief, a_proposal(), **attack_kw)
    a2 = AT.accept_proposal(strong_belief, a_proposal(), **attack_kw)
    assert AT.most_dangerous([a1], weak_belief).probability * \
        weak_belief.probability < \
        AT.most_dangerous([a2], strong_belief).probability * \
        strong_belief.probability


# --- value of information ---------------------------------------------------
def test_every_voi_term_actually_moves_the_ranking():
    """The named-heuristic-that-computes-nothing control."""
    base = dict(question="q", belief_id="b", subject="US",
                observation="a stated observable", obtainability=VOI.OBTAINABLE,
                decision_impact=0.5, latency_days=30, belief_probability=0.5)
    baseline = VOI.Priority(**base).score
    assert VOI.Priority(**dict(base, decision_impact=0.9)).score > baseline
    assert VOI.Priority(**dict(base, obtainability=VOI.ROUTINE)).score > baseline
    assert VOI.Priority(**dict(base, latency_days=5)).score > baseline
    assert VOI.Priority(**dict(base, cost=4.0)).score < baseline
    assert VOI.Priority(**dict(base, belief_probability=0.95)).score < baseline


def test_a_near_certain_belief_is_barely_worth_observing():
    base = dict(question="q", belief_id="b", subject="US",
                observation="o", obtainability=VOI.ROUTINE,
                decision_impact=1.0, latency_days=1)
    certain = VOI.Priority(**dict(base, belief_probability=0.99))
    open_question = VOI.Priority(**dict(base, belief_probability=0.5))
    assert certain.score < open_question.score / 10


def test_an_unobtainable_priority_is_reported_rather_than_vanishing():
    p = VOI.Priority(question="what is dealer gamma", belief_id="b",
                     subject="US", observation="aggregate dealer gamma",
                     obtainability=VOI.UNOBTAINABLE, decision_impact=0.9,
                     latency_days=1, belief_probability=0.5)
    got = VOI.summarise([p])
    assert p.score == 0.0
    assert got["unobtainable"][0]["question"].startswith("what is dealer")


def test_a_priority_phrased_as_a_topic_is_refused():
    with pytest.raises(V.EconError, match="cannot be answered or closed"):
        VOI.Priority(question="q", belief_id="b", subject="US",
                     observation="", obtainability=VOI.ROUTINE,
                     decision_impact=0.5, latency_days=1,
                     belief_probability=0.5)


# --- learning acceleration --------------------------------------------------
def cycles(n, ingested, movement, start=1):
    return [AC.CycleCounts(cycle_id=f"c{i}", at=f"2026-06-{i:02d}",
                           evidence_ingested=ingested, evidence_new=ingested,
                           belief_movement=movement)
            for i in range(start, start + n)]


def test_a_short_history_reports_insufficient_and_names_the_shortfall():
    got = AC.window_report(cycles(2, 10, 1.0), name="30d", size=30)
    assert got.status == AC.INSUFFICIENT_HISTORY
    assert "2 cycle" in got.reason and "30" in got.reason


def test_more_work_and_less_movement_reads_as_plateauing_not_accelerating():
    """The shape that is invisible if you only watch throughput."""
    history = cycles(4, 10, 2.0) + cycles(4, 40, 2.2, start=5)
    got = AC.window_report(history, name="7d", size=7)
    assert got.status == AC.PLATEAUING
    assert "working harder and learning less" in got.reason


def test_the_same_work_and_more_movement_reads_as_accelerating():
    history = cycles(4, 10, 1.0) + cycles(4, 10, 3.0, start=5)
    assert AC.window_report(history, name="7d", size=7).status == AC.ACCELERATING


def test_volume_alone_cannot_produce_acceleration():
    history = cycles(4, 10, 2.0) + cycles(4, 100, 2.0, start=5)
    assert AC.window_report(history, name="7d",
                            size=7).status != AC.ACCELERATING


def test_the_headline_is_the_longest_window_that_can_speak():
    got = AC.report(cycles(8, 10, 1.0))
    assert got["headline_window"] == "7d"
    assert got["windows"]["90d"]["status"] == AC.INSUFFICIENT_HISTORY


def test_duplicate_evidence_is_computed_not_assumed():
    c = AC.CycleCounts(cycle_id="c1", at="2026-06-01", evidence_ingested=50,
                       evidence_new=12)
    assert c.duplicate_evidence == 38
    assert c.novelty == pytest.approx(0.24)
