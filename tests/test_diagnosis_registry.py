from intent_engine.core.diagnosis_registry import REGISTRY, diagnose


def test_registry_covers_exactly_the_six_signatures_plus_the_disambiguation_row():
    """7 rows: 6 signatures, but unstable_across_reruns gets 2 rows (its
    real disambiguation), so REGISTRY itself has 7 entries covering 6
    distinct signatures."""
    signatures = {entry.signature for entry in REGISTRY}
    assert signatures == {
        "unstable_across_reruns", "anchors_on_offered_context", "bound_violated",
        "cross_field_incoherent", "citation_unresolvable", "novelty_or_scope_gap",
    }
    assert len(REGISTRY) == 7


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
