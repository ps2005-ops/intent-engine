"""The venue does not determine the author.

A five-company study reported "EDGAR supplied 10 independent sources". EDGAR
is a primary regulatory VENUE; the 10-Qs it hosts are written BY the company.
The counter treated every class except `company_owned` and
`executive_statement` as independent, and filings carry `investor_material`.
"""
import pytest

from intent_engine.strategic_intelligence import source_semantics as S

EDGAR = "https://www.sec.gov/Archives/edgar/data/796343/000079634326000109/x.htm"


def test_a_company_filing_is_authoritative_but_not_independent():
    assert S.authority("investor_material", EDGAR) == S.PRIMARY_REGULATORY_RECORD
    assert S.authorship("investor_material") == S.COMPANY
    assert not S.is_independent_of_subject("investor_material")


def test_the_regulatory_venue_never_rewrites_authorship():
    """Same class, hosted two ways: authority may change, authorship may not."""
    for url in (EDGAR, "https://investors.example.com/10q.htm", ""):
        assert S.authorship("investor_material") == S.COMPANY
    assert S.authority("investor_material", EDGAR) != \
        S.authority("investor_material", "https://investors.example.com/q.htm")


def test_a_syndicated_company_release_stays_company_authored():
    """A press release does not become independent by appearing in a feed."""
    assert not S.is_independent_of_subject("company_owned")
    assert S.authorship("company_owned") == S.COMPANY


def test_third_party_and_customer_authors_are_independent():
    for cls in ("independent_reporting", "competitor", "customer_voice"):
        assert S.is_independent_of_subject(cls), cls


def test_executive_statements_are_not_independent():
    assert S.authorship("executive_statement") == S.EXECUTIVE
    assert not S.is_independent_of_subject("executive_statement")


def test_company_filings_cannot_satisfy_an_independent_corroboration_gate():
    """The exact false reading, as an assertion: a run whose every source is a
    company filing has ZERO independent vantage points."""
    filings = ["investor_material"] * 10
    assert S.independent_count(filings) == 0
    mixed = filings + ["independent_reporting", "customer_voice"]
    assert S.independent_count(mixed) == 2


def test_unknown_classes_are_never_independent_by_default():
    for cls in ("", None, "made_up_class", "unavailable_or_failed"):
        assert not S.is_independent_of_subject(cls)


def test_describe_keeps_the_four_answers_separate():
    d = S.describe("investor_material", EDGAR)
    assert d["authorship"] == S.COMPANY
    assert d["authority"] == S.PRIMARY_REGULATORY_RECORD
    assert d["independent_of_subject"] is False
    assert d["venue_host"] == "www.sec.gov"


def test_the_reasoning_layer_and_this_module_agree():
    """reasoning.py had the correct set all along; nothing may drift from it."""
    from intent_engine.strategic_intelligence.reasoning import _provenance
    for cls in ("company_owned", "executive_statement", "investor_material"):
        assert _provenance([cls]) == "company-stated"
        assert not S.is_independent_of_subject(cls)
    assert _provenance(["independent_reporting"]) == "independently corroborated"
    assert S.is_independent_of_subject("independent_reporting")
