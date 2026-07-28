"""Company-specificity gate.

The sentence that motivated this: "SEC 6-K is shifting where demand is
captured." Every word is one an analyst might use, it parses, and it is not
about anything. A form type became the actor because the pipeline had a
document and needed a subject.
"""
import pytest

from intent_engine.strategic_intelligence.specificity import (
    ACCEPT, DOWNGRADE, REJECT, distinctive_terms, evaluate_claim,
    evaluate_report_claims, has_concrete_referent, missing_anatomy,
    substitution_survives,
)

COMPANY = "Brightlake"

DOCUMENTS = [
    {"title": "Brightlake routing platform",
     "text_content": "The Brightlake RouteIQ platform plans multi-stop "
                     "delivery routes for mid-market distributors. Northwind "
                     "Freight cut planning time by 34% in 2026. Pricing "
                     "starts at $400 per month on the Standard tier."},
    {"title": "Brightlake newsroom",
     "text_content": "In June 2026 Brightlake opened a Rotterdam operations "
                     "hub and signed a reseller agreement with Meridian "
                     "Logistics."},
]
TERMS = distinctive_terms(DOCUMENTS, company=COMPANY)


def _verdict(text, **kw):
    return evaluate_claim(text, company=COMPANY, evidence_terms=TERMS,
                          **kw)["verdict"]


def _codes(text, **kw):
    return {f["code"] for f in
            evaluate_claim(text, company=COMPANY, evidence_terms=TERMS,
                           **kw)["findings"]}


# --- the exact incident ------------------------------------------------------
def test_a_filing_type_cannot_be_the_actor_in_a_business_claim():
    assert _verdict("SEC 6-K is shifting where demand is captured") == REJECT
    assert "artefact_as_subject" in _codes(
        "SEC 6-K is shifting where demand is captured")


@pytest.mark.parametrize("subject", [
    "SEC 10-K", "Form 20-F", "The press release", "The sitemap",
    "This document", "The annual report", "The homepage",
])
def test_no_document_type_may_act(subject):
    assert _verdict(f"{subject} is expanding into new markets") == REJECT


# --- the quieter siblings ----------------------------------------------------
def test_demand_is_shifting_without_saying_what_or_where():
    assert _verdict("Demand is shifting") == REJECT
    assert "movement_without_direction" in _codes("Demand is shifting")


def test_distribution_is_changing_without_naming_the_channel():
    assert _verdict("Distribution is changing") == REJECT


def test_the_same_movement_claim_passes_once_it_names_the_channel():
    claim = ("Brightlake's distribution is moving from direct sales to a "
             "reseller channel, with the Meridian Logistics agreement signed "
             "in June 2026")
    assert _verdict(claim) == ACCEPT


def test_advice_without_evidence_is_refused():
    assert _verdict("Leadership should consider entering Europe") == REJECT
    assert "recommendation_without_evidence" in _codes(
        "Leadership should consider entering Europe")


def test_advice_with_evidence_is_allowed():
    result = evaluate_claim(
        {"statement": "Leadership should consider a Rotterdam expansion",
         "evidence": ["src-1"]},
        company=COMPANY, evidence_terms=TERMS)
    assert "recommendation_without_evidence" not in {
        f["code"] for f in result["findings"]}


def test_strategy_talk_without_a_named_decision_is_refused():
    assert _verdict("This affects strategy") == REJECT
    assert "strategy_without_decision" in _codes("This affects strategy")


def test_strategy_talk_with_a_named_decision_is_allowed():
    result = evaluate_claim(
        {"statement": "The Rotterdam hub has strategic implications",
         "decision": "whether to staff a European support team in Q4"},
        company=COMPANY, evidence_terms=TERMS)
    assert "strategy_without_decision" not in {f["code"]
                                               for f in result["findings"]}


# --- the substitution test ---------------------------------------------------
def test_a_claim_carried_only_by_the_company_name_does_not_survive():
    assert substitution_survives(
        "Brightlake is investing in its future growth",
        company=COMPANY, evidence_terms=TERMS)


def test_a_claim_anchored_in_evidence_does_not_survive_substitution():
    assert not substitution_survives(
        "Brightlake's RouteIQ platform cut Northwind Freight planning time "
        "by 34%", company=COMPANY, evidence_terms=TERMS)


def test_swapping_the_company_name_leaves_a_generic_claim_intact():
    generic = "Brightlake is well positioned for continued growth"
    assert _verdict(generic) in (REJECT, DOWNGRADE)
    assert "survives_substitution" in _codes(generic)


def test_repeating_the_company_name_does_not_make_a_claim_specific():
    # The name is stripped before the test precisely so this cannot work.
    assert substitution_survives(
        "Brightlake believes Brightlake is a leader in the Brightlake market",
        company=COMPANY, evidence_terms=TERMS)


def test_distinctive_terms_come_from_the_run_not_a_global_list():
    assert "routeiq" in TERMS
    assert "northwind" in TERMS
    assert "meridian" in TERMS
    # generic business vocabulary is never distinctive
    for generic in ("company", "market", "growth", "platform", "strategy"):
        assert generic not in TERMS
    # nor is the company's own name
    assert "brightlake" not in TERMS


def test_figures_and_dates_count_as_concrete_referents():
    assert has_concrete_referent("revenue rose 34% in 2026", set())
    assert not has_concrete_referent("revenue is improving", set())


# --- title-only evidence ------------------------------------------------------
def test_a_document_title_alone_cannot_support_a_claim():
    result = evaluate_claim(
        "Brightlake is expanding its RouteIQ platform in Rotterdam",
        company=COMPANY, evidence_terms=TERMS,
        evidence_is_title_only=True)
    assert result["verdict"] == REJECT
    assert "title_only_evidence" in {f["code"] for f in result["findings"]}


# --- repetition ---------------------------------------------------------------
def test_the_same_sentence_under_a_second_heading_is_not_a_second_insight():
    statement = ("Brightlake's RouteIQ platform serves mid-market "
                 "distributors")
    result = evaluate_claim(statement, company=COMPANY, evidence_terms=TERMS,
                            seen_statements=[statement])
    assert "repeated_statement" in {f["code"] for f in result["findings"]}


def test_repetition_detection_ignores_punctuation_and_case():
    result = evaluate_claim(
        "Brightlake's RouteIQ platform serves mid-market distributors!",
        company=COMPANY, evidence_terms=TERMS,
        seen_statements=["brightlake's routeiq platform serves mid-market "
                         "distributors"])
    assert "repeated_statement" in {f["code"] for f in result["findings"]}


# --- claim anatomy ------------------------------------------------------------
def test_a_complete_claim_has_every_required_part():
    claim = {"statement": "Brightlake is moving to a reseller channel",
             "signal": "Meridian Logistics reseller agreement, June 2026",
             "evidence": ["src-newsroom"],
             "implication": "lower gross margin per seat, wider reach",
             "decision": "whether to keep scaling the direct sales team",
             "confidence": "moderate",
             "limitation": "one agreement is not yet a channel strategy"}
    assert missing_anatomy(claim) == []


def test_missing_parts_are_named_in_plain_language():
    missing = missing_anatomy({"statement": "Brightlake is expanding"})
    assert "the business implication" in missing
    assert "the decision it is relevant to" in missing
    assert "a limitation or counterpoint" in missing
    # not a field name in sight
    assert not any("_" in m for m in missing)


# --- report level -------------------------------------------------------------
def test_a_report_of_generic_claims_is_almost_entirely_rejected():
    claims = ["Demand is shifting",
              "SEC 6-K is shifting where demand is captured",
              "This affects strategy",
              "Brightlake is investing in innovation"]
    summary = evaluate_report_claims(claims, company=COMPANY,
                                     evidence_terms=TERMS)
    assert summary["accepted"] == []
    assert summary["accepted_ratio"] == 0.0
    assert len(summary["rejected"]) >= 3


def test_a_report_of_grounded_claims_is_accepted():
    claims = [
        "Brightlake's RouteIQ platform cut Northwind Freight planning time "
        "by 34% in 2026",
        "Brightlake opened a Rotterdam hub in June 2026, its first outside "
        "North America",
        "Brightlake signed a reseller agreement with Meridian Logistics, "
        "its first indirect channel",
    ]
    summary = evaluate_report_claims(claims, company=COMPANY,
                                     evidence_terms=TERMS)
    assert summary["accepted_ratio"] == 1.0


def test_claim_order_is_preserved_so_callers_can_drop_in_place():
    claims = ["Demand is shifting",
              "Brightlake opened a Rotterdam hub in June 2026"]
    summary = evaluate_report_claims(claims, company=COMPANY,
                                     evidence_terms=TERMS)
    assert [r["statement"] for r in summary["results"]] == claims


# --- through the real report-quality gate ------------------------------------
def test_the_incident_sentence_hard_fails_the_real_quality_gate():
    """Not a unit check on the validator: the gate that actually runs in
    compose must refuse to publish this."""
    from intent_engine.company_ingestion.quality import (
        REPORT_QUALITY_FAIL, assess,
    )
    result = {
        "sections": [],
        "strategic_report": {
            "company_name": COMPANY,
            "thesis": {"view": "SEC 6-K is shifting where demand is "
                               "captured"},
            "hypotheses": [], "surprises": [], "opportunities": [],
        },
    }
    assessment = assess(result, DOCUMENTS, company_name=COMPANY)
    assert assessment["outcome"] == REPORT_QUALITY_FAIL
    assert any("not about this company" in rule
               for rule in assessment["hard_rules"])


def test_more_evidence_cannot_rescue_an_unspecific_claim():
    """It is a HARD rule, not a retryable one — a sixth source does not make
    a filing into a business actor."""
    from intent_engine.company_ingestion.quality import (
        REPORT_QUALITY_FAIL, assess,
    )
    result = {
        "sections": [],
        "strategic_report": {
            "company_name": COMPANY,
            "thesis": {"view": "Brightlake's RouteIQ platform is expanding "
                               "in Rotterdam as of June 2026"},
            "hypotheses": [{"statement": "Demand is shifting"}],
            "surprises": [], "opportunities": [],
        },
    }
    assessment = assess(result, DOCUMENTS * 10, company_name=COMPANY)
    assert assessment["outcome"] == REPORT_QUALITY_FAIL


def test_a_grounded_report_is_not_hard_failed_by_the_specificity_rule():
    from intent_engine.company_ingestion.quality import assess
    result = {
        "sections": [],
        "strategic_report": {
            "company_name": COMPANY,
            "thesis": {"view": "Brightlake is moving from direct sales to a "
                               "reseller channel, signing Meridian Logistics "
                               "in June 2026"},
            "hypotheses": [{"statement": "Brightlake's RouteIQ platform cut "
                                         "Northwind Freight planning time by "
                                         "34%"}],
            "surprises": [], "opportunities": [],
        },
    }
    assessment = assess(result, DOCUMENTS, company_name=COMPANY)
    assert not any("not about this company" in rule
                   for rule in assessment["hard_rules"])


def test_a_run_with_no_strategic_report_is_not_penalised():
    from intent_engine.company_ingestion.quality import assess
    assessment = assess({"sections": [], "strategic_report": None},
                        DOCUMENTS, company_name=COMPANY)
    assert assessment["metrics"]["unspecific_claims"] == []
