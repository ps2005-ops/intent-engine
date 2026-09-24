"""The learning session, its store, its policies and its sanitized export.

The centrepiece is `test_zero_trade_cycle_produces_real_knowledge_gain`: the
measured defect this cycle exists to fix.
"""
from __future__ import annotations

import copy
import pathlib

import pytest

from intent_engine.market import beliefs as B
from intent_engine.market import causal as C
from intent_engine.market import counterfactual as CF
from intent_engine.market import expectation as EXP
from intent_engine.market import hidden_state as HS
from intent_engine.market import information_value as IV
from intent_engine.market import learning_cycle as LC
from intent_engine.market import learning_store as LS
from intent_engine.market import micro_evidence as ME
from intent_engine.market import shadow_policies as SP
from intent_engine.market import strategic_export as SE
from intent_engine.market import strategic_interaction as SI


@pytest.fixture()
def store(tmp_path) -> LS.LearningStore:
    return LS.LearningStore(tmp_path / "learning.jsonl")


def ev(fact="a sourced fact", source="https://reuters.com/a",
       observed="2026-08-01", subject="PLTR", crole=ME.CONTRADICTING,
       role="independent_reporting"):
    return ME.build(subject_company=subject, actor=subject,
                    evidence_type=ME.PRICING_SIGNAL, observed_at=observed,
                    source=source, fact=fact, source_role=role,
                    contradiction_role=crole, reliability=0.8, relevance=0.9)


def seed(store, *, prior=0.62, window_end="2026-08-01"):
    b = B.create(belief_id="h_rates", proposition="a testable proposition",
                 subject="PLTR", prior=prior, at="2026-07-01")
    store.declare_belief(b)
    e = EXP.preregister(
        hypothesis_id="h_rates", subject="PLTR",
        expected_event="shares outperform the benchmark",
        expected_direction=EXP.UP, preregistered_at="2026-07-01",
        evaluation_window_ends=window_end,
        falsifier="shares underperform over the window")
    store.record_expectation(e)
    return b, e


# ------------------------------------------------------ THE CENTRAL PROOF
def test_zero_trade_cycle_produces_real_knowledge_gain(store):
    """The measured defect, fixed: learning that never touches a trade."""
    _, e = seed(store)
    result = LC.run(
        as_of="2026-08-04", store=store, trades_opened=0,
        observations={e.expectation_id: {"observed_value": -0.07,
                                         "observed_at": "2026-08-01"}})
    assert result.trades_opened == 0
    assert result.knowledge_gain > 0
    assert result.learned_without_trading is True

    after = store.beliefs()[0]
    assert after.posterior_probability < 0.62
    assert after.history[-1].direction == "WEAKENED"


def test_break_no_trade_cycle_produces_no_learning(store):
    """Drive the original defect: contradicting evidence, zero trades.

    Before this cycle the only path to a revision ran through a resolved
    trade, so this scenario produced net_knowledge_gain 0. It must not now.
    """
    seed(store, window_end="2026-12-01")
    result = LC.run(as_of="2026-08-04", store=store, trades_opened=0,
                    evidence=[ev()])
    assert result.trades_opened == 0
    assert result.knowledge_gain > 0, (
        "contradicting evidence with no trade must still move a belief")


def test_break_trade_outcome_required_before_belief_revision(store):
    """The learning path must not be able to reach the trading engine.

    Checked on the module's IMPORT statements rather than on its text: the
    docstring names paper_engine when explaining what it deliberately does
    not touch, and a substring check would fail on the explanation itself.
    """
    import ast
    tree = ast.parse(pathlib.Path(LC.__file__).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.update(a.name for a in node.names)
            imported.add(node.module or "")
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
    assert not {"paper_engine", "signals", "strategy"} & imported
    assert "beliefs" in imported, "sanity: the module was actually parsed"


def test_quiet_session_reports_zero_with_its_working(store):
    """§22: a zero must explain what was observed and why nothing moved."""
    seed(store, window_end="2026-12-01")
    result = LC.run(as_of="2026-08-04", store=store, trades_opened=0)
    assert result.knowledge_gain == 0
    why = result.why_nothing_moved()
    assert "still inside their evaluation window" in why
    assert "not an absence of work" in why


def test_every_session_attempts_all_thirteen_steps(store):
    seed(store)
    result = LC.run(as_of="2026-08-04", store=store,
                    shadow_registry=SP.ShadowRegistry())
    names = [s.name for s in result.steps]
    assert names == list(LC.STEPS)
    assert all(s.status == LC.ATTEMPTED for s in result.steps)


def test_reconciliation_runs_before_belief_revision(store):
    """Order matters: score against the observation, not a moved posterior."""
    steps = list(LC.STEPS)
    assert steps.index("expected_vs_observed_reconciliation") < \
           steps.index("belief_revision")


def test_decay_runs_after_revision(store):
    """A belief validated this session must not be decayed in the same breath."""
    steps = list(LC.STEPS)
    assert steps.index("knowledge_decay") > steps.index("belief_revision")


def test_evidence_ingested_once_across_sessions(store):
    seed(store, window_end="2026-12-01")
    item = ev()
    first = LC.run(as_of="2026-08-04", store=store, evidence=[item])
    second = LC.run(as_of="2026-08-05", store=store, evidence=[item])
    assert first.observations_ingested == 1
    assert second.steps[0].changed == 0
    assert "already held" in second.steps[0].note
    assert len(store.evidence()) == 1
    # Same fact, same date: the sighting did not advance, so there is
    # nothing new to record. A replay must leave the ledger byte-identical.
    assert store.re_observations() == ()


def test_the_same_fact_read_on_a_later_sweep_is_not_a_new_observation(store):
    """The defect that drove the self-test rate to 0.8.

    `observed_at` is the date the SWEEP ran. Hashing it into the evidence id
    minted a fresh id for an unchanged page every night, so 84 of 249 real
    ledger rows were re-reads that `observation_binding` then had to catch
    one at a time as self-tests.
    """
    seed(store, window_end="2026-12-01")
    monday = ev(observed="2026-08-04")
    friday = ev(observed="2026-08-08")
    assert monday.fact == friday.fact
    assert monday.evidence_id == friday.evidence_id
    LC.run(as_of="2026-08-04", store=store, evidence=[monday])
    LC.run(as_of="2026-08-08", store=store, evidence=[friday])
    assert len(store.evidence()) == 1
    # The later sighting IS recorded — "the page still said this on Friday"
    # is information — as a sighting, never as a second observation.
    assert [r["seen_at"] for r in store.re_observations()] == ["2026-08-08"]


def test_hidden_state_guard_failure_does_not_fail_the_cycle(store):
    """A refused observation is a guard firing, not an outage."""
    seed(store)
    result = LC.run(
        as_of="2026-08-04", store=store,
        hidden_states=[HS.uniform("PLTR", at="2026-08-01")],
        hidden_state_observations=[{"subject": "PLTR", "action": "x",
                                    "likelihoods": {HS.GROWING: 5.0}}])
    assert result.steps[3].status == LC.ATTEMPTED
    assert result.steps[3].changed == 0


# ------------------------------------------------------------------ store
def test_store_folds_updates_into_current_posterior(store):
    b, _ = seed(store)
    updated, _ = B.update(b, [ev()], at="2026-08-02")
    store.record_update(b.belief_id, updated.history[-1])
    assert store.beliefs()[0].posterior_probability == \
           updated.posterior_probability


def test_store_skips_a_corrupt_line_and_counts_it(store):
    seed(store)
    with store.path.open("a", encoding="utf-8") as handle:
        handle.write("{not json\n")
    assert len(store.beliefs()) == 1
    assert store.health()["corrupt_lines_skipped"] == 1


def test_informative_reconciliation_closes_an_expectation(store):
    _, e = seed(store)
    assert len(store.open_expectations(as_of="2026-08-04")) == 1
    LC.run(as_of="2026-08-04", store=store,
           observations={e.expectation_id: {"observed_value": -0.07,
                                            "observed_at": "2026-08-01"}})
    assert store.open_expectations(as_of="2026-08-05") == ()


def test_too_early_reconciliation_leaves_an_expectation_open(store):
    seed(store, window_end="2026-12-01")
    LC.run(as_of="2026-08-04", store=store)
    assert len(store.open_expectations(as_of="2026-08-05")) == 1


# --------------------------------------------------- counterfactual/regret
def test_break_every_missed_winner_labelled_regret():
    """A refusal on thin evidence is not a miscalibration."""
    cf = CF.record_decision(subject="X", decided_at="2026-06-01",
                            chosen_action="NO_TRADE", all_evidence=[])
    out = CF.resolve(cf, resolved_at="2026-09-01", chosen_outcome=0.0,
                     counterfactual_outcome=0.45)
    assert out.verdict == CF.CORRECT_REFUSAL
    assert out.regret_cause == CF.UNAVOIDABLE
    assert out.actionable is False


def test_no_trade_regret_is_measured_when_evidence_was_adequate():
    good = [ev(fact=f"strong evidence {i}", source=f"https://s{i}.com",
               observed="2026-05-01") for i in range(4)]
    cf = CF.record_decision(subject="X", decided_at="2026-06-01",
                            chosen_action="NO_TRADE", all_evidence=good,
                            threshold_distance=-0.02)
    out = CF.resolve(cf, resolved_at="2026-09-01", chosen_outcome=0.0,
                     counterfactual_outcome=0.45)
    assert out.verdict == CF.FALSE_NEGATIVE
    assert out.regret_cause == CF.THRESHOLD
    assert out.actionable is True


def test_break_hindsight_enters_decision_time_evidence():
    later = ev(observed="2026-08-01")
    cf = CF.record_decision(subject="X", decided_at="2026-06-01",
                            chosen_action="NO_TRADE", all_evidence=[later])
    assert cf.decision_evidence_ids == (), "later evidence must be filtered"

    forged = CF.Counterfactual(
        record_id="cf_x", subject="X", decided_at="2026-06-01",
        chosen_action="NO_TRADE", rejected_alternatives=(), rank=None,
        threshold_distance=None,
        decision_evidence_ids=(later.evidence_id,),
        evidence_quality_at_decision=0.9)
    with pytest.raises(CF.HindsightLeak):
        CF.resolve(forged, resolved_at="2026-09-01", chosen_outcome=0.0,
                   counterfactual_outcome=0.4, all_evidence=[later])


def test_risk_adjustment_changes_the_verdict():
    good = [ev(fact=f"e{i}", source=f"https://s{i}.com", observed="2026-05-01")
            for i in range(4)]
    cf = CF.record_decision(subject="X", decided_at="2026-06-01",
                            chosen_action="NO_TRADE", all_evidence=good,
                            threshold_distance=-0.02)
    unadjusted = CF.resolve(cf, resolved_at="2026-09-01", chosen_outcome=0.0,
                            counterfactual_outcome=0.45)
    assert unadjusted.verdict == CF.FALSE_NEGATIVE

    # The same alternative, thirty times the risk, is no longer the better
    # decision — its adjusted edge falls inside the materiality floor.
    risky = CF.resolve(cf, resolved_at="2026-09-01", chosen_outcome=0.0,
                       counterfactual_outcome=0.45, risk_adjustment=30.0)
    assert risky.verdict == CF.CORRECT_REFUSAL
    assert risky.regret == 0.0


def test_break_threshold_lowered_on_a_thin_cluster():
    """Three near misses must not produce a threshold recommendation."""
    misses = [CF.NearMiss(subject=f"C{i}", at="2026-06-01", gate="volatility",
                          threshold=0.30, observed=0.29, later_outcome=0.2)
              for i in range(3)]
    finding = CF.analyse_near_misses(misses)["findings"][0]
    assert finding["recommendation"] == "INSUFFICIENT_EVIDENCE"


def test_stable_near_miss_cluster_recommends_human_review_only():
    misses = [CF.NearMiss(subject=f"C{i}", at="2026-06-01", gate="volatility",
                          threshold=0.30, observed=0.29, later_outcome=0.2)
              for i in range(10)]
    finding = CF.analyse_near_misses(misses)["findings"][0]
    assert finding["recommendation"] == "REVIEW_THRESHOLD"
    assert "HUMAN review" in finding["note"]


def test_gate_holding_when_near_misses_were_noise():
    misses = [CF.NearMiss(subject=f"C{i}", at="2026-06-01", gate="volatility",
                          threshold=0.30, observed=0.29,
                          later_outcome=-0.1 if i % 2 else 0.1)
              for i in range(12)]
    assert CF.analyse_near_misses(misses)["findings"][0][
        "recommendation"] == "GATE_HOLDING"


def test_summary_reports_no_trade_regret_separately():
    cf = CF.record_decision(subject="X", decided_at="2026-06-01",
                            chosen_action="NO_TRADE", all_evidence=[])
    out = CF.resolve(cf, resolved_at="2026-09-01", chosen_outcome=0.0,
                     counterfactual_outcome=0.45)
    s = CF.summarise([out])
    assert s["no_trade_decisions_scored"] == 1
    assert s["correct_refusals"] == 1


# --------------------------------------------------------- value of info
def test_information_gain_is_highest_for_an_open_question():
    open_q = IV.expected_information_gain(0.5)
    settled = IV.expected_information_gain(0.95)
    assert open_q > settled


def test_observation_after_the_deadline_is_worth_nothing():
    b = B.create(belief_id="b", proposition="p", subject="S", prior=0.5,
                 at="2026-08-01")
    late = IV.prioritise(b, candidate_observation="annual filing",
                         observation_kind="ANNUAL_FILING",
                         expected_date="2026-12-01", as_of="2026-08-04",
                         decision_deadline="2026-09-01")
    assert late.priority == 0.0
    assert "after the" in late.limitation


def test_agenda_names_the_highest_value_next_observation():
    b = B.create(belief_id="b", proposition="p", subject="S", prior=0.5,
                 at="2026-08-01")
    near = IV.prioritise(b, candidate_observation="earnings",
                         observation_kind="EARNINGS_RELEASE",
                         expected_date="2026-08-20", as_of="2026-08-04")
    far = IV.prioritise(b, candidate_observation="customer interviews",
                        observation_kind="CUSTOMER_COMMENT",
                        expected_date="2027-02-01", as_of="2026-08-04")
    a = IV.agenda([far, near])
    assert a["highest_value_next_observation"][
        "candidate_observation"] == "earnings"
    assert "Entropy measures indecision, not correctness" in a["assumption"]


# ------------------------------------------------------- shadow policies
def test_break_shadow_policy_promoted_without_evidence():
    reg = SP.ShadowRegistry()
    book = reg.book(SP.HIDDEN_STATE)
    for i in range(5):
        book.decide(subject=f"C{i}", at="2026-08-01", action="BUY")
        book.resolve(subject=f"C{i}", at="2026-09-01", outcome=0.5)
    out = SP.promote(reg, SP.HIDDEN_STATE)
    assert out["recommendation"] == "REJECT"
    assert out["promoted"] is False


def test_promotion_never_happens_automatically():
    reg = SP.ShadowRegistry()
    book = reg.book(SP.HIDDEN_STATE)
    for i in range(40):
        book.decide(subject=f"C{i}", at="2026-08-01", action="BUY")
        book.resolve(subject=f"C{i}", at="2026-09-01", outcome=0.5)
    out = SP.promote(reg, SP.HIDDEN_STATE)
    assert out["promoted"] is False
    assert out["requires_human_approval"] is True
    assert SP.APPROVED_POLICY == SP.STRICT


def test_break_shadow_policy_leaks_into_the_principal_book():
    reg = SP.ShadowRegistry()
    foreign = SP.PolicyDecision(policy=SP.AGGRESSIVE, subject="X",
                                at="2026-08-01", action="BUY")
    reg.book(SP.STRICT)._decisions.append(foreign)
    with pytest.raises(SP.PolicyError, match="isolation breach"):
        reg.assert_isolated()


def test_only_the_approved_policy_affects_the_principal_book():
    reg = SP.ShadowRegistry()
    affecting = [b.summary()["policy"] for b in reg.all_books()
                 if b.summary()["affects_principal_book"]]
    assert affecting == [SP.APPROVED_POLICY]


def test_comparison_refuses_below_the_evidence_floor():
    reg = SP.ShadowRegistry()
    out = reg.compare()
    assert out["eligible_for_comparison"] == 0
    assert all(r["verdict"] == "INSUFFICIENT_EVIDENCE" for r in out["rows"])


def test_comparison_states_the_multiple_comparisons_problem():
    reg = SP.ShadowRegistry()
    for policy in (SP.STRICT, SP.HIDDEN_STATE):
        book = reg.book(policy)
        for i in range(35):
            book.decide(subject=f"C{i}", at="2026-08-01", action="BUY")
            book.resolve(subject=f"C{i}", at="2026-09-01", outcome=0.1)
    out = reg.compare()
    assert out["eligible_for_comparison"] == 2
    assert "multiple-comparisons correction" in out["note"]


# ------------------------------------------------------- sanitized export
def an_export():
    b = B.create(belief_id="b1", proposition="A competitor is buying share",
                 subject="PLTR", prior=0.4, at="2026-08-01")
    return SE.build_export(company_id="pltr", as_of="2026-08-04",
                           beliefs=[b])


def test_break_unknown_field_bypasses_the_allowlist():
    bad = dict(an_export())
    bad["internal_calibration"] = {"sharpe": 1.4}
    with pytest.raises(SE.ExportLeak, match="not in the allowlist"):
        SE.assert_sanitized(bad)


def test_break_unknown_field_nested_inside_a_list_item():
    bad = copy.deepcopy(an_export())
    bad["strategic_beliefs"][0]["win_rate"] = 0.61
    with pytest.raises(SE.ExportLeak, match="strategic_beliefs\\[0\\]"):
        SE.assert_sanitized(bad)


def test_break_internal_metric_leaks_inside_permitted_free_text():
    bad = copy.deepcopy(an_export())
    bad["limitations"] = ["the strategy win rate was 61% this quarter"]
    with pytest.raises(SE.ExportLeak, match="trading internal"):
        SE.assert_sanitized(bad)


def test_break_nested_object_under_a_leaf_field():
    bad = copy.deepcopy(an_export())
    bad["limitations"] = [{"sharpe": 1.4}]
    with pytest.raises(SE.ExportLeak, match="nested structure"):
        SE.assert_sanitized(bad)


def test_export_carries_no_trading_vocabulary_in_its_data():
    """Whole words, and over the DATA only.

    Two traps, both hit while writing this. 'position' is a substring of
    'proposition', so the scan must be word-boundaried. And the fixed
    advisory text legitimately contains 'investment position' precisely
    because it is disclaiming one — scanning it flags the disclaimer for
    disclaiming, which is the same false positive the market-context work
    hit last cycle on 'is not a forecast'.
    """
    import re
    payload = dict(an_export())
    for advisory in ("disclaimer", "interpretation_allowed",
                     "interpretation_forbidden"):
        payload.pop(advisory)
    text = str(payload).lower()
    for banned in ("sharpe", "win_rate", "alpha", "position", "positions",
                   "signal", "strategy_key", "expectancy", "drawdown"):
        assert not re.search(rf"\b{re.escape(banned)}\b", text), banned
    for phrase in ("win rate", "paper book", "signal fired",
                   "profit factor"):
        assert phrase not in text


def test_only_informative_mismatches_cross():
    e = EXP.preregister(hypothesis_id="h", subject="PLTR",
                        expected_event="ev", expected_direction=EXP.UP,
                        preregistered_at="2026-07-01",
                        evaluation_window_ends="2026-12-01", falsifier="f")
    too_early = EXP.reconcile(e, as_of="2026-08-04")
    hit = EXP.reconcile(e, as_of="2026-08-04", observed_value=-0.07,
                        observed_at="2026-08-01")
    payload = SE.build_export(company_id="pltr", as_of="2026-08-04",
                              reconciliations=[too_early, hit])
    assert len(payload["expectation_mismatches"]) == 1
    assert payload["expectation_mismatches"][0]["outcome"] == EXP.CONTRADICTED


def test_export_collects_evidence_ids_from_every_depth():
    i = SI.record(focal_actor="A", responding_actor="B",
                  initial_action="cut price", at="2026-08-01",
                  response="matched", response_at="2026-08-08",
                  evidence_ids=["ev_deep_1"])
    payload = SE.build_export(company_id="pltr", as_of="2026-08-04",
                              interactions=[i])
    assert "ev_deep_1" in payload["evidence_ids"]


def test_hidden_state_export_carries_its_certainty_note():
    h = HS.seeded("PLTR", at="2026-08-01",
                  prior={HS.GROWING: 0.6, HS.DEFENDING: 0.4})
    payload = SE.build_export(company_id="pltr", as_of="2026-08-04",
                              hidden_states=[h])
    assert "never certain" in payload["hidden_states"][0]["certainty_note"]
    assert payload["hidden_states"][0]["alternatives"]
