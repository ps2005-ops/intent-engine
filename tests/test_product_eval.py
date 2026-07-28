"""The product-evaluation harness must itself be trustworthy.

A gate that cannot see a failure is worse than no gate, because it converts
"nobody checked" into "it passed". The first test here is the one that
matters: it pins the defect the harness originally missed — an analysis that
produced no brief, no hypothesis and no slide was scored PRODUCT_READY, and
44% of the suite was silently passing on empty output.
"""
import pytest

from intent_engine.product_eval.harness import (
    EVAL_SET_VERSION, build_cases, run_cases,
)
from intent_engine.product_eval.personas import PERSONAS, SCENARIOS
from intent_engine.product_eval.scorecard import (
    INSUFFICIENT_EVIDENCE, PRODUCT_READY, THRESHOLDS,
    duplication_ratio, evidence_reuse_ratio, jargon_density, score_report,
    thesis_is_generic,
)
from intent_engine.strategic_intelligence.reasoning import (
    MAX_DISPLAYED_HYPOTHESES, select_portfolio,
)


# --- the gate must see emptiness ---------------------------------------------
def test_an_empty_analysis_is_never_product_ready():
    """Retrieved evidence plus no output is a FAILURE, not a limitation."""
    score = score_report(brief=None, slides=[], report={"hypotheses": []},
                         documents=[{"source_type": "about",
                                     "source_class": "company_owned"}])
    assert not score.ok, score.as_dict()
    assert any("empty result" in f for f in score.failures), score.failures


def test_no_evidence_at_all_is_insufficient_not_failure():
    score = score_report(brief=None, slides=[], report={}, documents=[])
    assert score.outcome == INSUFFICIENT_EVIDENCE


# --- the metrics measure what customers complained about ----------------------
def test_duplication_ratio_catches_the_same_paragraph_twice():
    para = ("the company is expanding its platform surface across several "
            "adjacent products and services this year")
    assert duplication_ratio([para]) == 0.0
    assert duplication_ratio([para, para]) > 0.4


def test_evidence_reuse_ratio_counts_recited_sources():
    # four citations, two of which the reader has already seen -> 0.5
    hyps = [{"evidence": ["a", "b"]}, {"evidence": ["a", "b"]}]
    assert evidence_reuse_ratio(hyps) == 0.5
    assert evidence_reuse_ratio([{"evidence": ["a"]}, {"evidence": ["c"]}]) == 0.0


def test_jargon_is_measured_not_guessed():
    assert jargon_density("we will leverage synergy to move the needle") > 0
    assert jargon_density("the company sells software to hospitals") == 0.0


def test_a_thesis_true_of_any_company_is_flagged():
    assert thesis_is_generic("Acme is a leading provider of solutions")
    assert not thesis_is_generic(
        "Acme appears to be converting its implementation work into a product")


# --- portfolio discipline -----------------------------------------------------
class _H:
    def __init__(self, pid, conf, support, decision="d", counter=()):
        self.pattern_id = pid
        self.confidence = conf
        self.supporting_observation_ids = support
        self.counter_observation_ids = counter
        self.decision_implications = [decision]


def test_portfolio_is_capped_so_the_strongest_is_not_buried():
    hyps = [_H(f"p{i}", "moderate", [f"o{i}"], decision=f"d{i}")
            for i in range(6)]
    chosen = select_portfolio(hyps)
    assert len(chosen) == MAX_DISPLAYED_HYPOTHESES


def test_a_restatement_is_suppressed():
    """Same evidence AND same decision is one hypothesis printed twice."""
    a = _H("a", "high", ["o1", "o2"], decision="raise prices")
    b = _H("b", "moderate", ["o1", "o2"], decision="raise prices")
    chosen = select_portfolio([a, b])
    assert [h.pattern_id for h in chosen] == ["a"]


def test_shared_evidence_alone_does_not_suppress():
    """Two real forces may rest on the same facts and still differ."""
    a = _H("a", "high", ["o1", "o2"], decision="raise prices")
    b = _H("b", "moderate", ["o1", "o2"], decision="hire a compliance lead")
    chosen = select_portfolio([a, b])
    assert len(chosen) == 2


def test_the_primary_thesis_is_the_best_supported():
    weak = _H("weak", "speculative", ["o1"], decision="d1")
    strong = _H("strong", "high", ["o1", "o2", "o3"], decision="d2")
    assert select_portfolio([weak, strong])[0].pattern_id == "strong"


# --- the case set -------------------------------------------------------------
def test_every_persona_and_scenario_is_exercised():
    cases = build_cases()
    covered_personas = {c["persona"] for c in cases}
    covered_scenarios = {c["scenario"] for c in cases}
    missing_p = {p.key for p in PERSONAS} - covered_personas
    assert not missing_p, f"personas never evaluated: {sorted(missing_p)}"
    # Scenarios are allowed to be aspirational; personas are not.
    assert len(covered_scenarios) >= 10


def test_at_least_fifty_cases_and_a_versioned_set():
    assert len(build_cases()) >= 50
    assert EVAL_SET_VERSION


def test_case_ids_are_unique_and_stable():
    a = [c["case_id"] for c in build_cases()]
    b = [c["case_id"] for c in build_cases()]
    assert a == b
    assert len(set(a)) == len(a)


# --- the suite runs, and its result is a fact not a vibe ----------------------

def test_the_suite_runs_and_reports_per_persona():
    out = run_cases(build_cases())
    assert out["total_cases"] >= 50
    assert set(out["by_persona"])                    # per-persona, not averaged
    assert 0.0 <= out["pass_rate"] <= 1.0
    # A regression gate needs a floor. This is the measured floor as of the
    # iteration that introduced domain-neutral patterns and portfolio
    # discipline; raising it is progress, lowering it needs a reason.
    assert out["pass_rate"] >= 0.80, out["failure_clusters"]


def test_thresholds_are_declared_in_one_place():
    for key in ("brief_words_max", "max_displayed_hypotheses",
                "duplication_ratio_max"):
        assert key in THRESHOLDS
