"""A company named by an ordinary word is not every use of that word.

Measured on prospect-100 round 5: Pigment (planning software) was credited
with two independent origins and a decision-grade reading from titanium-
dioxide and lead-pigment manufacturers' 10-Ks.
"""
from __future__ import annotations

from intent_engine.company_ingestion import relevance as REL
from intent_engine.company_ingestion.third_party_filings import (
    assess_filing_mention,
)

KRONOS = (
    "Kronos Worldwide, Inc. is a leading global producer and marketer of "
    "value-added titanium dioxide pigments, a base industrial product. We "
    "compete with other producers of TiO2 Pigment in Europe and North "
    "America, and our customers buy pigment for coatings and plastics. "
) * 30


def _verdict(text, name="Pigment", domain=""):
    return REL.adjudicate({"text_content": text}, subject_name=name,
                          subject_domain=domain)


def test_a_filing_about_the_material_is_not_about_the_company():
    v = _verdict(KRONOS)
    assert v["state"] == REL.IRRELEVANT
    assert "ordinary word" in v["reason"]


def test_the_company_named_properly_in_that_filing_still_counts():
    """POSITIVE CONTROL inside the ambiguous document."""
    text = KRONOS + (" Pigment SAS, a planning software company, competes "
                     "with Anaplan and Workday Adaptive Planning for finance "
                     "teams. Pigment SAS expanded into the United States in "
                     "2024 and now sells to large enterprises. ")
    assert _verdict(text)["state"] != REL.IRRELEVANT


def test_a_proper_noun_company_is_untouched():
    """POSITIVE CONTROL: a filing that never lowercases the name."""
    text = ("We compete with Brex and Ramp in corporate cards, and we entered "
            "a reseller agreement with Brex for our customers. ") * 30
    assert _verdict(text, name="Brex")["state"] != REL.IRRELEVANT


def test_the_domain_qualifies_a_mention():
    text = KRONOS + (" The planning vendor at pigment.com competes with "
                     "Anaplan for finance teams. The company behind "
                     "pigment.com expanded into the United States in 2024 "
                     "and now sells to large enterprises. ")
    assert _verdict(text, domain="pigment.com")["state"] != REL.IRRELEVANT


def test_the_caller_reads_the_filing_through_the_rule():
    """THE CALLER: the third-party filing channel's own assessment."""
    html = f"<html><body><p>{KRONOS}</p></body></html>"
    assert assess_filing_mention(html=html, company_name="Pigment",
                                 author_name="Kronos Worldwide, Inc."
                                 )["relevance"] == REL.IRRELEVANT
