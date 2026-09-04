"""Belief learning: contracts, arithmetic, and the guards that must hold.

Every test named `test_break_*` is a deliberate break proof — it drives the
failure the design exists to prevent and asserts the intended gate fires.
"""
from __future__ import annotations

import pytest

from intent_engine.market import beliefs as B
from intent_engine.market import expectation as EXP
from intent_engine.market import hidden_state as HS
from intent_engine.market import micro_evidence as ME
from intent_engine.market import strategic_interaction as SI


# ---------------------------------------------------------------- helpers
def ev(fact="a fact", source="https://example.com/a",
       role="independent_reporting", crole=ME.CONTRADICTING,
       observed="2026-08-01", available="", reliability=0.8, relevance=0.9,
       subject="PLTR", etype=ME.PRICING_SIGNAL):
    return ME.build(subject_company=subject, actor=subject,
                    evidence_type=etype, observed_at=observed,
                    available_at=available, source=source, fact=fact,
                    source_role=role, contradiction_role=crole,
                    reliability=reliability, relevance=relevance)


def belief(prior=0.60, speed=B.MEDIUM):
    return B.create(belief_id="b1", proposition="a proposition",
                    subject="PLTR", prior=prior, at="2026-07-01",
                    learning_speed=speed)


# ------------------------------------------------------------ MicroEvidence
def test_evidence_requires_a_source():
    with pytest.raises(ME.EvidenceRejected, match="provenance"):
        ev(source="")


def test_evidence_requires_a_fact():
    with pytest.raises(ME.EvidenceRejected):
        ev(fact="")


def test_evidence_rejects_unknown_type():
    with pytest.raises(ME.EvidenceRejected, match="evidence_type"):
        ME.build(subject_company="X", actor="X", evidence_type="VIBES",
                 observed_at="2026-08-01", source="s", fact="f")


def test_identical_fact_gets_identical_id():
    assert ev().evidence_id == ev().evidence_id


def test_reformatting_does_not_mint_a_new_id():
    assert ev(fact="Price   cut\n15%").evidence_id == \
           ev(fact="price cut 15%").evidence_id


def test_different_source_is_a_different_row():
    assert ev(source="https://a.com").evidence_id != \
           ev(source="https://b.com").evidence_id


def test_available_at_defaults_to_observed_at():
    assert ev(observed="2026-08-01").available_at == "2026-08-01"


def test_break_available_before_observed_is_refused():
    """Evidence cannot have been knowable before it happened."""
    with pytest.raises(ME.EvidenceRejected, match="precedes"):
        ev(observed="2026-08-01", available="2026-07-01")


def test_break_hindsight_leakage_into_decision_time_evidence():
    """A March filing must not be visible to a February decision."""
    march = ev(observed="2026-03-15")
    assert march.visible_at("2026-02-01") is False
    assert ME.visible_subset([march], "2026-02-01") == ()
    assert ME.visible_subset([march], "2026-04-01") == (march,)


def test_visible_subset_reads_available_not_observed():
    late = ev(observed="2026-01-31", available="2026-03-15")
    assert late.visible_at("2026-02-15") is False


def test_self_authored_sources_are_flagged():
    assert ev(role="company_owned").self_authored is True
    assert ev(role="executive_statement").self_authored is True
    assert ev(role="independent_reporting").self_authored is False


def test_deduplicate_preserves_first_seen_order():
    a, b = ev(fact="one"), ev(fact="two")
    assert ME.deduplicate([a, b, a, b, a]) == (a, b)


# ----------------------------------------------------------- Expectations
def test_break_expectation_without_falsifier_is_refused():
    with pytest.raises(EXP.ExpectationRejected, match="falsifier"):
        EXP.preregister(hypothesis_id="h", subject="PLTR",
                        expected_event="shares rise",
                        expected_direction=EXP.UP,
                        preregistered_at="2026-07-01",
                        evaluation_window_ends="2026-08-01", falsifier="")


def prereg(**kw):
    base = dict(hypothesis_id="h", subject="PLTR",
                expected_event="shares outperform the benchmark",
                expected_direction=EXP.UP, preregistered_at="2026-07-01",
                evaluation_window_ends="2026-08-01",
                falsifier="shares underperform over the window")
    base.update(kw)
    return EXP.preregister(**base)


def test_contradicted_when_direction_is_opposite():
    r = EXP.reconcile(prereg(), as_of="2026-08-04", observed_value=-0.07,
                      observed_at="2026-08-01")
    assert r.outcome == EXP.CONTRADICTED
    assert r.informative is True


def test_confirmed_when_direction_matches():
    r = EXP.reconcile(prereg(), as_of="2026-08-04", observed_value=0.07,
                      observed_at="2026-08-01")
    assert r.outcome == EXP.CONFIRMED


def test_partially_confirmed_when_magnitude_misses_the_range():
    r = EXP.reconcile(prereg(expected_range=(0.10, 0.20)), as_of="2026-08-04",
                      observed_value=0.03, observed_at="2026-08-01")
    assert r.outcome == EXP.PARTIALLY_CONFIRMED


def test_flat_move_is_uninformative_not_a_refutation():
    r = EXP.reconcile(prereg(), as_of="2026-08-04", observed_value=0.002,
                      observed_at="2026-08-01")
    assert r.outcome == EXP.UNINFORMATIVE
    assert r.informative is False


def test_open_window_without_observation_is_too_early():
    r = EXP.reconcile(prereg(), as_of="2026-07-15")
    assert r.outcome == EXP.TOO_EARLY
    assert r.informative is False


def test_closed_window_without_observation_is_unmeasurable_not_refuted():
    """Absence of an observation must never be scored as a refutation."""
    r = EXP.reconcile(prereg(), as_of="2026-09-01")
    assert r.outcome == EXP.UNMEASURABLE
    assert r.informative is False


def test_break_retrodiction_is_refused():
    """Scoring against an observation older than the commitment is refused."""
    r = EXP.reconcile(prereg(), as_of="2026-08-04", observed_value=0.30,
                      observed_at="2026-06-01")
    assert r.outcome == EXP.UNMEASURABLE
    assert "retrodiction" in r.rationale


def test_summarise_counts_informative_separately():
    rs = [EXP.reconcile(prereg(), as_of="2026-08-04", observed_value=v,
                        observed_at="2026-08-01")
          for v in (0.07, -0.07, 0.001)]
    s = EXP.summarise(rs)
    assert s["evaluated"] == 3 and s["informative"] == 2


# ---------------------------------------------------------------- Beliefs
def test_belief_learns_with_no_trade_involved():
    """THE central proof: a preregistered miss revises a belief, no trade."""
    r = EXP.reconcile(prereg(), as_of="2026-08-04", observed_value=-0.07,
                      observed_at="2026-08-01")
    before = belief(0.62)
    after, changed = B.update_from_reconciliation(
        before, r.outcome, at="2026-08-04", rationale=r.rationale,
        expectation_id=r.expectation_id)
    assert changed is True
    assert after.posterior_probability < before.posterior_probability
    assert after.history[-1].direction == "WEAKENED"
    assert B.summarise([before], [after])["belief_knowledge_gain"] == 1


def test_break_duplicate_evidence_updates_twice():
    """The same evidence applied twice must move the posterior once."""
    e = ev()
    first, c1 = B.update(belief(), [e], at="2026-08-02")
    second, c2 = B.update(first, [e], at="2026-08-03")
    assert c1 is True and c2 is False
    assert second.posterior_probability == first.posterior_probability


def test_break_missing_evidence_weakens_a_belief():
    """Absence must not move a posterior. Only decay does, toward 0.5."""
    b = belief()
    after, changed = B.update(b, [], at="2026-08-05")
    assert changed is False
    assert after.posterior_probability == b.posterior_probability


def test_break_company_release_treated_as_independent_corroboration():
    """Self-authored evidence must move a belief far less than independent."""
    own = B.update(belief(), [ev(role="company_owned")], at="2026-08-02")[0]
    ind = B.update(belief(), [ev(role="independent_reporting")],
                   at="2026-08-02")[0]
    own_move = abs(own.posterior_probability - 0.60)
    ind_move = abs(ind.posterior_probability - 0.60)
    assert own_move < ind_move / 3


def test_correlated_evidence_gets_a_design_effect_penalty():
    correlated = [ev(fact=f"outlet {i} rewrote the release",
                     source=f"https://o{i}.com", role="company_owned")
                  for i in range(6)]
    diverse = [ev(fact="a", source="https://a.com",
                  role="independent_reporting"),
               ev(fact="b", source="https://b.com", role="analyst_coverage"),
               ev(fact="c", source="https://c.com", role="customer_voice"),
               ev(fact="d", source="https://d.com",
                  role="government_statistic"),
               ev(fact="e", source="https://e.com", role="regulatory_filing"),
               ev(fact="f", source="https://f.com",
                  role="market_observation")]
    assert B.design_effect(correlated) < B.design_effect(diverse) / 4


def test_balanced_evidence_records_a_test_without_moving():
    sup = ev(fact="supports", crole=ME.SUPPORTING,
             source="https://a.com", role="analyst_coverage")
    con = ev(fact="contradicts", crole=ME.CONTRADICTING,
             source="https://b.com", role="analyst_coverage")
    b = belief()
    after, changed = B.update(b, [sup, con], at="2026-08-02")
    assert changed is True
    assert after.posterior_probability == b.posterior_probability
    assert after.history[-1].direction == "UNCHANGED"


def test_neutral_evidence_does_not_update():
    after, changed = B.update(belief(), [ev(crole=ME.NEUTRAL)],
                              at="2026-08-02")
    assert changed is False


def test_break_empirical_bayes_without_a_measured_likelihood():
    """Precise-looking arithmetic must not run on an unmeasured likelihood."""
    with pytest.raises(ValueError, match="likelihood_ratio"):
        B.update(belief(), [ev()], at="2026-08-02",
                 method=B.EMPIRICAL_BAYES)


def test_empirical_bayes_updates_when_a_likelihood_is_supplied():
    after, changed = B.update(belief(), [ev(crole=ME.SUPPORTING)],
                              at="2026-08-02", method=B.EMPIRICAL_BAYES,
                              likelihood_ratio=3.0)
    assert changed is True
    assert after.posterior_probability > 0.60
    assert after.history[-1].method == B.EMPIRICAL_BAYES


def test_qualitative_update_records_direction_without_claiming_magnitude():
    b = belief()
    after, changed = B.update(b, [ev(crole=ME.SUPPORTING)], at="2026-08-02",
                              method=B.QUALITATIVE)
    assert changed is True
    assert after.posterior_probability == b.posterior_probability
    assert "magnitude deliberately not claimed" in after.history[-1].basis


def test_slow_beliefs_resist_fast_evidence():
    """A noisy fast signal must not rewrite structural knowledge."""
    fast_on_slow = B.update(belief(speed=B.SLOW), [ev()], at="2026-08-02",
                            evidence_speed=B.FAST)[0]
    fast_on_fast = B.update(belief(speed=B.FAST), [ev()], at="2026-08-02",
                            evidence_speed=B.FAST)[0]
    assert abs(fast_on_slow.posterior_probability - 0.60) < \
           abs(fast_on_fast.posterior_probability - 0.60)


def test_belief_never_reaches_certainty():
    b = belief(0.97)
    for i in range(40):
        b = B.update(b, [ev(fact=f"support {i}", crole=ME.SUPPORTING,
                            source=f"https://s{i}.com")],
                     at="2026-08-02")[0]
    assert b.posterior_probability <= 0.98


# ------------------------------------------------------------------ Decay
def test_break_stale_belief_never_decays():
    b = belief(0.82)
    after, changed = B.decay(b, at="2026-11-01")
    assert changed is True
    assert after.posterior_probability < b.posterior_probability


def test_decay_moves_toward_uncertainty_not_toward_false():
    """A belief below 0.5 must decay UPWARD, toward 0.5."""
    low = B.create(belief_id="b2", proposition="p", subject="S", prior=0.20,
                   at="2026-01-01")
    after, changed = B.decay(low, at="2026-11-01")
    assert changed is True
    assert after.posterior_probability > low.posterior_probability
    assert after.posterior_probability <= 0.5


def test_decay_is_recorded_separately_from_contradicting_evidence():
    after, _ = B.decay(belief(0.82), at="2026-11-01")
    assert after.history[-1].method == B.DECAY
    assert after.history[-1].evidence_ids == ()
    assert "NOT toward false" in after.history[-1].basis


def test_fresh_belief_does_not_decay():
    assert B.decay(belief(), at="2026-07-15")[1] is False


def test_timeless_beliefs_are_exempt_from_decay():
    fixed = B.create(belief_id="b3", proposition="arithmetic holds",
                     subject="-", prior=0.99, at="2026-01-01",
                     decay_eligible=False)
    assert B.decay(fixed, at="2027-01-01")[1] is False


# ----------------------------------------------------------- Hidden states
def test_break_hidden_state_asserted_as_certain():
    """A single-state likelihood claims certainty and must be refused."""
    b = HS.uniform("MSFT", at="2026-08-01")
    with pytest.raises(HS.HiddenStateError, match="certainty"):
        HS.observe(b, action="cut price", at="2026-08-02",
                   likelihoods={HS.MARKET_SHARE_SEEKING: 5.0})


def test_break_competitor_price_cut_treated_as_proven_motive():
    """A price cut must leave rival postures alive, never elect one."""
    b = HS.seeded("MSFT", at="2026-08-01",
                  prior={HS.MARKET_SHARE_SEEKING: 0.31,
                         HS.MARGIN_PROTECTING: 0.42,
                         HS.CAPACITY_CONSTRAINED: 0.27})
    after = HS.observe(b, action="cut list price 15%", at="2026-08-02",
                       likelihoods={HS.MARKET_SHARE_SEEKING: 3.2,
                                    HS.MARGIN_PROTECTING: 0.35,
                                    HS.CAPACITY_CONSTRAINED: 1.1},
                       evidence_ids=["ev_1"])
    lead, p = after.leading
    assert lead == HS.MARKET_SHARE_SEEKING
    assert p < 0.9, "no posture may be asserted as certain"
    assert len(after.history[-1].alternative_states) >= 2
    HS.assert_uncertain(after)


def test_hidden_state_posterior_moves_on_evidence():
    b = HS.seeded("MSFT", at="2026-08-01",
                  prior={HS.MARKET_SHARE_SEEKING: 0.31,
                         HS.MARGIN_PROTECTING: 0.42, HS.DEFENDING: 0.27})
    after = HS.observe(b, action="cut price while expanding capacity",
                       at="2026-08-02",
                       likelihoods={HS.MARKET_SHARE_SEEKING: 3.2,
                                    HS.MARGIN_PROTECTING: 0.35,
                                    HS.DEFENDING: 1.0},
                       evidence_ids=["ev_1"])
    assert after.as_map[HS.MARKET_SHARE_SEEKING] > b.as_map[
        HS.MARKET_SHARE_SEEKING]
    assert after.as_map[HS.MARGIN_PROTECTING] < b.as_map[HS.MARGIN_PROTECTING]
    assert after.entropy < b.entropy


def test_unnamed_states_keep_residual_mass():
    """A posture nobody listed is the one that turns out to be right."""
    b = HS.seeded("X", at="2026-08-01", prior={HS.GROWING: 1.0})
    assert b.as_map[HS.PREPARING_ACQUISITION] > 0


def test_describe_keeps_the_rival_visible():
    b = HS.seeded("X", at="2026-08-01",
                  prior={HS.GROWING: 0.5, HS.DEFENDING: 0.3})
    assert "though" in HS.describe(b)


def test_assert_uncertain_fires_on_a_forced_certainty():
    forced = HS.HiddenStateBelief(
        subject="X", distribution=(("GROWING", 0.999), ("DEFENDING", 0.001)),
        last_updated="2026-08-01")
    with pytest.raises(HS.HiddenStateError, match="certain"):
        HS.assert_uncertain(forced)


# ------------------------------------------------- Strategic interactions
def test_break_actor_response_is_fabricated():
    """An interaction with no evidence is a story and must be refused."""
    with pytest.raises(SI.InteractionRejected, match="evidence"):
        SI.record(focal_actor="A", responding_actor="B",
                  initial_action="cut price", at="2026-08-01",
                  response="matched", response_at="2026-08-05")


def test_break_inferred_motive_without_alternatives():
    with pytest.raises(SI.InteractionRejected, match="alternative"):
        SI.record(focal_actor="A", responding_actor="B",
                  initial_action="cut price", at="2026-08-01",
                  inferred_objective="seeking share", evidence_ids=["ev_1"])


def test_response_requires_its_own_date():
    with pytest.raises(SI.InteractionRejected, match="date"):
        SI.record(focal_actor="A", responding_actor="B",
                  initial_action="cut price", at="2026-08-01",
                  response="matched", evidence_ids=["ev_1"])


def test_interaction_records_a_sequence_with_lag():
    i = SI.record(focal_actor="A", responding_actor="B",
                  initial_action="cut list price 15%", at="2026-08-01",
                  response="matched the cut", response_at="2026-08-08",
                  payoff_change=SI.WORSENED,
                  inferred_objective="defend share",
                  alternative_explanations=("clearing inventory",
                                            "punishing a defector"),
                  evidence_ids=["ev_1", "ev_2"])
    assert i.response_lag_days == 7
    assert i.status == SI.RESPONDED


def test_actor_feasible_action_set_bounds_responses():
    rival = SI.actor(name="B", kind=SI.COMPETITORS,
                     available_actions=("match price", "bundle"))
    assert rival.can("match price") is True
    assert rival.can("expand capacity") is False


def test_pattern_match_reports_missing_preconditions():
    m = SI.match_pattern("pat_price_war",
                         present_conditions=["low switching costs",
                                             "spare capacity"])
    assert m.verdict == "CANDIDATE"
    assert m.missing
    assert m.falsifier


def test_break_historical_analog_becomes_a_conclusion():
    """A name match with no mechanism must not read as a finding."""
    m = SI.match_pattern("pat_price_war", present_conditions=[])
    assert m.verdict == "WEAK_MATCH"
    assert m.coverage == 0.0
    assert len(m.missing) == 4


def test_full_precondition_match_is_still_not_a_certainty():
    pattern = SI.PATTERNS_BY_ID["pat_price_war"]
    m = SI.match_pattern("pat_price_war",
                         present_conditions=list(pattern.preconditions))
    assert m.verdict == "MECHANISM_PRESENT"
    assert m.falsifier, "even a full match must carry its falsifier"


def test_sequence_orders_an_episode_by_time():
    a = SI.record(focal_actor="A", responding_actor="B",
                  initial_action="cut", at="2026-08-01",
                  evidence_ids=["e1"])
    b = SI.record(focal_actor="B", responding_actor="C",
                  initial_action="match", at="2026-07-01",
                  evidence_ids=["e2"])
    assert SI.sequence([a, b])[0].at == "2026-07-01"
