"""A founder must never be shown "invented_number x20"."""
from intent_engine.strategic_intelligence import withheld_explanation as WX

NUMERIC = [{"check": "invented_number", "severity": "reject", "message": "x"},
           {"check": "unsupported_numeric_claim", "severity": "reject",
            "message": "y"}]
THIN = [{"check": "no_decision", "severity": "reject", "message": "z"}]


def test_the_cause_is_the_figures_not_a_generic_description_complaint():
    ex = WX.explain(findings=NUMERIC, document_count=6, numeric_facts=67)
    assert ex["cause"] == "unsupported_figures"
    assert "financial figures" in ex["why_withheld"]
    # NOT the generic "descriptive rather than strategic" reason
    assert "descriptive rather than strategic" not in ex["why_withheld"]


def test_no_internal_vocabulary_reaches_the_reader():
    for findings in (NUMERIC, THIN, []):
        text = WX.render_text(WX.explain(findings=findings, document_count=4))
        low = text.lower()
        for internal in ("invented_number", "unsupported_numeric_claim",
                         "critic", "check", "severity", "reject",
                         "strategically_insufficient", "schema", "prompt",
                         "traceback", "anthropic", "claude", "token"):
            assert internal not in low, (internal, text)


def test_all_four_parts_are_present_and_specific():
    ex = WX.explain(findings=NUMERIC, families=["company_owned"],
                    independent_sources=0, document_count=6, numeric_facts=67)
    assert ex["what_was_available"] and ex["what_was_missing"]
    assert ex["why_withheld"] and ex["what_would_help"]
    missing = " ".join(ex["what_was_missing"]).lower()
    assert "someone other than the company" in missing


def test_zero_independent_sources_is_named_as_the_gap():
    ex = WX.explain(findings=[], independent_sources=0, document_count=5,
                    numeric_facts=3)
    assert any("other than the company" in m for m in ex["what_was_missing"])


def test_no_figures_available_is_named_as_the_gap():
    ex = WX.explain(findings=[], independent_sources=2, document_count=5,
                    numeric_facts=0)
    assert any("figure we could quote" in m for m in ex["what_was_missing"])


def test_the_explanation_never_asserts_a_strategic_reading():
    text = WX.render_text(WX.explain(findings=NUMERIC, document_count=6)).lower()
    for revived in ("is shifting", "is moving toward", "is repositioning",
                    "strategy is", "we recommend", "the company is becoming"):
        assert revived not in text


def test_a_thin_run_gets_the_decision_reason_not_the_figures_reason():
    ex = WX.explain(findings=THIN, document_count=4, numeric_facts=2)
    assert ex["cause"] == "no_decision_supported"
    assert "decision" in ex["why_withheld"].lower()


def test_every_cause_has_a_concrete_next_step():
    for findings in (NUMERIC, THIN, []):
        ex = WX.explain(findings=findings, document_count=3)
        assert len(str(ex["what_would_help"])) > 40
