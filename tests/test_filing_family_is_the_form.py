"""A filing's family is what it says, not where it was filed.

MEASURED on 743df06 across the 50-company gauntlet: twelve companies whose
only reachable evidence was SEC EDGAR composed as

    compose=3 usable=3 families=investor

-- one family every time. `MIN_FAMILIES_LIMITED` is 2, so those runs were
refused before retrieval had a chance to matter. The decision was taken in
`family_of`, which read `source_class == "investor_material"` and returned
INVESTOR for a 10-K, an 8-K and a proxy alike.
"""
from intent_engine.company_ingestion.coverage import (
    IDENTITY, INDEPENDENT, INVESTOR, STRATEGY, TALENT, assess, family_of,
)
from intent_engine.company_ingestion.readiness import assess_readiness


#: Distinct prose per form. The dedup fingerprint is the FIRST 400
#: characters, so fixtures that share an opening are one document wearing
#: three hats -- which is a dedup test, not a family test.
_PROSE = {
    "10-K": "Item 1. Business. The registrant operates a Class I railroad "
            "moving bulk, intermodal and industrial freight. ",
    "10-Q": "Condensed consolidated statements of income for the quarter "
            "ended June 30, with freight revenue and operating ratio. ",
    "8-K": "On February 1 the registrant announced a change of chief "
           "executive and a revised capital allocation framework. ",
    "DEF 14A": "Notice of annual meeting of shareholders, director "
               "nominees, and the compensation discussion and analysis. ",
}


def _filing(form, *, title=None, text=None):
    body = text or _PROSE.get(form, f"An ordinary {form} filing. ")
    return {"source_id": f"sec-{form}", "source_type": "external_approved",
            "source_class": "investor_material", "retrieval_status": "OK",
            "title": title or f"SEC {form} (2026-03-02)",
            "text_content": (body + f"({form}) ") * 12,
            "filing": {"form": form, "periodic": form.startswith("10-K")}}


def test_the_annual_report_is_the_company_describing_itself():
    assert family_of(_filing("10-K")) == IDENTITY
    assert family_of(_filing("20-F")) == IDENTITY


def test_a_material_event_is_a_statement_of_direction():
    assert family_of(_filing("8-K")) == STRATEGY


def test_the_proxy_is_governance_and_people():
    assert family_of(_filing("DEF 14A")) == TALENT


def test_the_quarterly_is_still_investor_material():
    assert family_of(_filing("10-Q")) == INVESTOR


def test_an_exhibit_is_the_business_content_it_wraps():
    assert family_of(_filing("8-K", title="SEC 8-K exhibit (2026-02-01)")) \
        == STRATEGY


def test_an_unknown_form_is_not_promoted():
    """The default may not become a way to invent a family."""
    assert family_of(_filing("S-8")) == INVESTOR
    assert family_of(_filing("")) == INVESTOR


def test_a_document_that_is_not_a_filing_is_untouched():
    assert family_of({"source_type": "homepage", "source_class": "company_owned",
                      "retrieval_status": "OK"}) == IDENTITY
    assert family_of({"source_type": "external_approved",
                      "source_class": "independent_reporting",
                      "retrieval_status": "OK"}) == INDEPENDENT


def test_sec_only_evidence_can_now_reach_more_than_one_family():
    """THE DEFECT, END TO END.

    Three filings a real company files every year. Before this, `families`
    was `['investor']` and the run could not clear the two-family floor no
    matter how many filings were read.
    """
    docs = [_filing("10-K"), _filing("10-Q"), _filing("8-K")]
    coverage = assess(docs)
    assert len(coverage["families"]) >= 3, coverage["families"]
    assert IDENTITY in coverage["families"]
    assert STRATEGY in coverage["families"]


def test_the_readiness_gate_sees_the_wider_evidence():
    docs = [_filing("10-K"), _filing("10-Q"), _filing("8-K"),
            _filing("DEF 14A")]
    identity = {"entity_resolved": True,
                "company_name": "Union Pacific Corporation",
                "cik": "0000100885"}
    verdict = assess_readiness(documents=docs, identity=identity)
    assert len(verdict["families"]) >= 3, verdict["families"]
    assert verdict["may_synthesize"], verdict["failed_checks"]

    # THE CONTROL. The same four documents, read the way the deployed build
    # read them, refuse the run -- so this test can fail.
    import intent_engine.company_ingestion.coverage as cov
    before = dict(cov._FILING_FAMILY)
    try:
        cov._FILING_FAMILY.clear()
        blind = assess_readiness(documents=docs, identity=identity)
    finally:
        cov._FILING_FAMILY.update(before)
    assert blind["families"] == ["investor"], blind["families"]
    assert not blind["may_synthesize"]


def test_independence_is_not_manufactured_by_this():
    """Content breadth is not voice breadth, and this may never blur them."""
    docs = [_filing("10-K"), _filing("10-Q"), _filing("8-K")]
    assert INDEPENDENT not in assess(docs)["families"]
