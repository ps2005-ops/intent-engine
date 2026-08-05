"""A filing is read from its sections, not its first 280 characters."""
from __future__ import annotations

import pytest

from intent_engine.strategic_intelligence import filing_sections as FS

COVER = ("ANNUAL REPORT PURSUANT TO SECTION 13 OR 15(d) OF THE SECURITIES "
         "EXCHANGE ACT OF 1934. Commission File Number 001-38480. Delaware. "
         "27-2825503. ")
TOC = ("TABLE OF CONTENTS Item 1. Business 3 Item 1A. Risk Factors 12 "
       "Item 7. Management's Discussion and Analysis 40 ")
ITEM1 = ("Item 1. Business We are a monitoring and security platform for "
         "cloud applications. Our platform brings infrastructure monitoring, "
         "application performance monitoring and log management into a single "
         "product. We sell through a self-service motion that expands into "
         "enterprise agreements over time. ")
ITEM1A = ("Item 1A. Risk Factors If we are unable to attract new customers, "
          "our revenue growth could be harmed and our results of operations "
          "would suffer materially. ")
ITEM7 = ("Item 7. Management's Discussion and Analysis Revenue increased 26% "
         "to $2.68 billion in fiscal 2025, driven primarily by expansion "
         "within our existing customer base. Customers with annual recurring "
         "revenue of $100,000 or more grew to 3,610 from 3,390. ")

FULL = COVER + TOC + ITEM1 + ITEM1A + ITEM7


def test_a_filing_is_recognised():
    assert FS.looks_like_filing(FULL)


def test_a_marketing_page_is_not_a_filing():
    assert not FS.looks_like_filing(
        "Try Datadog free. See metrics from all of your apps in one place.")


def test_item_1_is_extracted():
    assert "item_1" in FS.find_sections(FULL)


def test_item_1a_is_extracted():
    assert "item_1a" in FS.find_sections(FULL)


def test_item_7_is_extracted():
    assert "item_7" in FS.find_sections(FULL)


def test_navigation_is_not_mistaken_for_body():
    """Every 10-K prints its headings twice. The contents page must lose."""
    sections = FS.find_sections(FULL)
    assert "Risk Factors 12" not in sections.get("item_1", "")
    for body in sections.values():
        assert "TABLE OF CONTENTS" not in body


def test_a_contents_page_alone_yields_nothing():
    excerpt, section = FS.best_excerpt(COVER + TOC)
    assert excerpt == "" and section == ""


def test_mda_is_preferred_when_present():
    """Item 7 carries the numbers a reader needs."""
    excerpt, section = FS.best_excerpt(FULL)
    assert "Item 7" in section
    assert "Revenue increased 26%" in excerpt


def test_business_is_used_when_there_is_no_mda():
    excerpt, section = FS.best_excerpt(COVER + TOC + ITEM1)
    assert "Item 1 (Business)" == section
    assert "monitoring and security platform" in excerpt


def test_a_missing_section_is_not_invented():
    sections = FS.find_sections(COVER + TOC + ITEM1)
    assert "item_7" not in sections
    assert "item_1a" not in sections


def test_the_cover_page_never_becomes_the_excerpt():
    excerpt, _ = FS.best_excerpt(FULL)
    assert "PURSUANT TO SECTION" not in excerpt
    assert "27-2825503" not in excerpt
    for glyph in "☐☒":
        assert glyph not in excerpt


def test_a_malformed_document_fails_closed():
    for junk in ("", "   ", "<<<>>>", "\x00\x01"):
        assert FS.best_excerpt(junk) == ("", "")


def test_extraction_is_bounded():
    excerpt, _ = FS.best_excerpt(COVER + TOC + ITEM7 * 40)
    assert len(excerpt) <= 600


def test_provenance_names_the_section():
    _, section = FS.best_excerpt(COVER + TOC + ITEM1A)
    assert "Item 1A" in section


@pytest.mark.parametrize("heading", [
    "ITEM 1. BUSINESS", "Item 1 - Business", "Item 1: Business",
    "item 1. business",
])
def test_heading_formats_vary_across_filings(heading):
    doc = COVER + TOC + heading + (
        " We are a monitoring and security platform for cloud applications "
        "and we sell to engineering teams through a self-service motion "
        "that expands over time into enterprise agreements. ")
    assert "item_1" in FS.find_sections(doc)


# --- the integration that actually closes the live defect -------------------
def test_an_observation_excerpt_comes_from_a_section_not_the_cover_page():
    from intent_engine.strategic_intelligence import observations as O
    docs = [{
        "final_url": "https://www.sec.gov/Archives/edgar/data/1/ddog-10k.htm",
        "title": "Datadog 10-K",
        "text_content": FULL,
        "source_class": "investor_material",
        "content_hash": "h1",
    }]
    out = O.derive_observations(docs, company="Datadog")
    for o in out:
        assert "PURSUANT TO SECTION" not in o.excerpt
        assert "27-2825503" not in o.excerpt


def test_a_web_page_still_uses_its_meta_description():
    """The fallback must not regress: only filings change behaviour."""
    from intent_engine.strategic_intelligence import observations as O
    docs = [{
        "final_url": "https://www.datadoghq.com/",
        "title": "Datadog",
        "meta_description": "Monitor infrastructure metrics and logs in one "
                            "unified platform with Datadog.",
        "text_content": "Some other body text entirely.",
        "source_class": "company_owned",
        "content_hash": "h2",
    }]
    for o in O.derive_observations(docs, company="Datadog"):
        assert "Some other body text" not in o.excerpt


# --- found live, not in a fixture -------------------------------------------
CURLY_MDA = (
    "ANNUAL REPORT PURSUANT TO SECTION 13 OR 15(d) OF THE SECURITIES "
    "EXCHANGE ACT OF 1934. Commission File Number 001-38480. "
    "TABLE OF CONTENTS Item 1. Business 3 Item 7. Management’s Discussion 40 "
    "Item 7. Management’s Discussion and Analysis of Financial Condition "
    "and Results of Operations. "
    "Revenue increased 26% to $2.68 billion in fiscal 2025, driven primarily "
    "by expansion within our existing customer base. Customers with annual "
    "recurring revenue of $100,000 or more grew to 3,610 from 3,390."
)


def test_the_section_title_is_not_the_excerpt():
    """Measured live on the deployed preview: "What was verified" read
    "management's Discussion and Analysis of Financial Condition and Results
    of Operations." -- the heading, not the section. The filing writes a CURLY
    apostrophe, so a straight-quote pattern never consumed the title."""
    excerpt, section = FS.best_excerpt(CURLY_MDA)
    assert "Item 7" in section
    assert excerpt.startswith("Revenue increased 26%")
    for fragment in ("Discussion and Analysis", "Financial Condition",
                     "Results of Operations"):
        assert fragment not in excerpt


def test_a_curly_apostrophe_does_not_hide_a_section():
    assert "item_7" in FS.find_sections(CURLY_MDA)


ITEM5_BLEED = (
    "ANNUAL REPORT PURSUANT TO SECTION 13 OR 15(d) OF THE SECURITIES "
    "EXCHANGE ACT OF 1934. Commission File Number 001-38480. "
    "TABLE OF CONTENTS Item 1. Business 3 Item 7. MD&A 40 "
    "Item 1. Business We are a monitoring and security platform for cloud "
    "applications sold to engineering teams worldwide. "
    "Item 5. Market for Registrant's Common Equity, Related Stockholder "
    "Matters and Issuer Purchases of Equity Securities. "
    "Item 7. Management’s Discussion and Analysis of Financial Condition and "
    "Results of Operations. "
    "Revenue increased 26% to $2.68 billion in fiscal 2025, driven primarily "
    "by expansion within our existing customer base."
)


def test_an_unextracted_item_still_ends_the_previous_section():
    """Measured live: only five Items were recognised, so Item 5's heading sat
    inside Item 1's body, was long enough to pass the prose check, and became
    "What was verified". A section ends where the NEXT section starts, not
    where the next interesting one does."""
    excerpt, section = FS.best_excerpt(ITEM5_BLEED)
    assert excerpt.startswith("Revenue increased 26%")
    for fragment in ("Registrant", "Stockholder", "Issuer Purchases"):
        assert fragment not in excerpt
    assert fragment not in FS.find_sections(ITEM5_BLEED).get("item_1", "")


def test_item_1_body_stops_at_item_5():
    body = FS.find_sections(ITEM5_BLEED).get("item_1", "")
    assert "monitoring and security platform" in body
    assert "Common Equity" not in body
