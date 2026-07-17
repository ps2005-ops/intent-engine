from intent_engine.core.diagnosis_registry import (
    REGISTRY,
    check_discrimination_bar,
    diagnose,
)


def test_registry_covers_exactly_the_seven_signatures_plus_the_disambiguation_row():
    """8 rows: 7 signatures, but unstable_across_reruns gets 2 rows (its
    real disambiguation), so REGISTRY itself has 8 entries covering 7
    distinct signatures."""
    signatures = {entry.signature for entry in REGISTRY}
    assert signatures == {
        "unstable_across_reruns", "anchors_on_offered_context", "bound_violated",
        "cross_field_incoherent", "citation_unresolvable",
        "stable_but_non_discriminating", "novelty_or_scope_gap",
    }
    assert len(REGISTRY) == 8


def test_every_registry_entry_has_a_real_rationale():
    """Not a bare lookup table -- every row states WHY, for auditability."""
    for entry in REGISTRY:
        assert len(entry.rationale) > 20


def test_diagnose_unstable_across_reruns_free_text_selects_closed_taxonomy():
    assert diagnose("unstable_across_reruns", "free_text") == "closed_taxonomy_extraction"


def test_diagnose_unstable_across_reruns_unknown_shape_defaults_to_closed_taxonomy():
    """The more foundational fix is tried first when shape isn't stated --
    not left undefined."""
    assert diagnose("unstable_across_reruns", "unknown") == "closed_taxonomy_extraction"
    assert diagnose("unstable_across_reruns") == "closed_taxonomy_extraction"


def test_diagnose_unstable_across_reruns_closed_taxonomy_selects_self_consistency_voting():
    assert diagnose("unstable_across_reruns", "closed_taxonomy") == "self_consistency_voting"


def test_diagnose_anchors_on_offered_context_selects_information_hiding():
    assert diagnose("anchors_on_offered_context") == "information_hiding"


def test_anchoring_rationale_documents_both_failure_shapes():
    """T003: the replay's episode-4 finding -- anchors_on_offered_context
    matched via a genuinely different mechanism (generation-leak/imitation,
    the prefix leak) than the signature's original description
    (classification bias). The documented rationale must explicitly cover
    BOTH shapes, so a future triager doesn't reject the signature on a
    generation-leak case because the docs only describe classification."""
    entry = next(
        e for e in REGISTRY if e.signature == "anchors_on_offered_context"
    )
    rationale = entry.rationale.lower()
    # generation/imitation shape (episode 4)
    assert "generat" in rationale
    assert "imitat" in rationale
    # classification-bias shape (episode 3) still documented
    assert "classification" in rationale
    assert "bias" in rationale


def test_diagnose_bound_violated_selects_deterministic_bounded_composition():
    assert diagnose("bound_violated") == "deterministic_bounded_composition"


def test_diagnose_cross_field_incoherent_selects_cross_field_coherence_check():
    assert diagnose("cross_field_incoherent") == "cross_field_coherence_check"


def test_diagnose_citation_unresolvable_selects_citation_computed_in_code():
    assert diagnose("citation_unresolvable") == "citation_computed_in_code"


def test_diagnose_novelty_or_scope_gap_always_escalates():
    assert diagnose("novelty_or_scope_gap") == "no_fix_escalate"


def test_diagnose_fails_closed_on_an_unrecognized_signature():
    """A signature outside the closed taxonomy (e.g. a genuinely novel
    failure this registry has never seen) must escalate, never guess."""
    assert diagnose("some_signature_not_in_the_registry") == "no_fix_escalate"


def test_diagnose_stable_but_non_discriminating_requires_design_level_fix():
    """T004: the 7th signature (backtest v1's degenerate classifier,
    out-of-sample-confirmed by the job-agent top_n=10 degeneracy) maps to
    design_level_fix_required -- never a mechanical retry."""
    assert diagnose("stable_but_non_discriminating") == "design_level_fix_required"


def _backtest_v1_real_fixture():
    """The real backtest-v1 numbers as a regression fixture, not synthetic.

    18 real cited historical cases: 11 failures, 7 successes. The
    degenerate classifier flagged 17/18 as risky ('failure'): all 11 real
    failures correct, 6 of 7 real successes wrong, 1 correct -- 12/18 =
    66.7% accuracy, 1/7 = 14.3% specificity, exactly the documented
    backtest-v1 results. Baseline: always-predict-failure = 11/18 = 61.1%.
    """
    ground_truth = ["failure"] * 11 + ["success"] * 7
    degenerate = ["failure"] * 11 + ["failure"] * 6 + ["success"]
    baseline = ["failure"] * 18
    return degenerate, ground_truth, baseline


def test_discrimination_bar_flags_the_real_backtest_v1_degenerate_classifier():
    """66.7% vs. 61.1% must FLAG (True): a 5.6pp raw edge over
    always-predict-the-majority-class, achieved by flagging 17/18 risky,
    is base-rate riding, not discrimination."""
    degenerate, ground_truth, baseline = _backtest_v1_real_fixture()
    accuracy = sum(p == g for p, g in zip(degenerate, ground_truth)) / 18
    baseline_accuracy = sum(b == g for b, g in zip(baseline, ground_truth)) / 18
    assert round(accuracy, 3) == round(12 / 18, 3)          # 66.7%, the real number
    assert round(baseline_accuracy, 3) == round(11 / 18, 3)  # 61.1%, the real number
    assert check_discrimination_bar(degenerate, ground_truth, baseline) is True


def test_discrimination_bar_passes_a_genuinely_baseline_beating_predictor():
    """Same real ground truth (11/7 split from backtest v1), a predictor
    that actually discriminates: all 11 failures right AND 6 of 7
    successes right (17/18 = 94.4%) clears baseline+margin -> False (no
    flag). The predictions are constructed; the ground-truth distribution
    and baseline are the real ones."""
    _, ground_truth, baseline = _backtest_v1_real_fixture()
    discriminating = ["failure"] * 11 + ["success"] * 6 + ["failure"]
    assert check_discrimination_bar(discriminating, ground_truth, baseline) is False


def test_discrimination_bar_rejects_mismatched_or_empty_inputs():
    import pytest

    with pytest.raises(ValueError):
        check_discrimination_bar([], [], [])
    with pytest.raises(ValueError):
        check_discrimination_bar(["a"], ["a", "b"], ["a", "b"])
