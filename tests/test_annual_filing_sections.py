"""Annual filing section extraction, and the truncation honesty around it.

Fixtures are trimmed from the real 2026 10-K text of the companies named, so
the shapes the parser has to survive — a table of contents that repeats every
heading, page furniture welded into the prose, entity-reference bullets — are
the real ones rather than ones invented to pass.
"""
from __future__ import annotations

import pytest

from intent_engine.external_intel import annual_filing as AF
from intent_engine.external_intel import competitor_finder as CFD


# A contents page (every heading, each followed by a page number), then the
# body. This is the exact shape that made a fixed front-zone cutoff wrong:
# on the real Palantir filing the contents sit at char 27,000.
FILING = (
    "PALANTIR TECHNOLOGIES INC. Annual Report on Form 10-K "
    + ("cover page boilerplate " * 40) +
    "Item 1. Business 4 Item 1A. Risk Factors 12 Item 1B. Unresolved Staff "
    "Comments 60 Item 2. Properties 61 Item 3. Legal Proceedings 62 "
    "ITEM 1. BUSINESS Overview We build software that empowers organizations "
    "to integrate their data. " + ("Our platforms are described here. " * 20) +
    "10 Table of Contents Competition We are fundamentally competing with "
    "the internal software development efforts of our potential customers. "
    "Organizations frequently attempt to build their own data platforms "
    "before turning to buy ours. In trying to build something on their own, "
    "they generally rely on a patchwork of custom solutions, outside "
    "consultants, IT services companies, packaged enterprise and open source "
    "software. In addition, our competitors include large enterprise "
    "software companies, government contractors, and system integrators. "
    "The principal competitive factors in the markets in which we operate "
    "include: platform capabilities and product functionality; data "
    "security and privacy; product innovation. "
    "Human Capital We employ many people. " + ("More on people. " * 20) +
    "Item 1A. Risk Factors Investing in our stock involves risk. "
    + ("A risk factor. " * 40)
)


def sections(truncated=False, text=FILING):
    return AF.extract(text, form="10-K", filed_at="2026-02-17",
                      truncated=truncated,
                      source_url="https://www.sec.gov/Archives/x.htm")


def test_business_section_is_the_body_not_the_contents_line():
    s = sections()
    business = s.section("business")
    assert business is not None
    assert "Overview We build software" in business.text
    assert "Item 1A. Risk Factors 12" not in business.text


def test_competition_section_is_found_inside_item_1():
    c = sections().competition
    assert c is not None
    assert c.text.startswith("Competition")
    assert "internal software development efforts" in c.text


def test_competition_stops_at_the_next_subsection():
    c = sections().competition
    assert "Human Capital" not in c.text
    assert "Investing in our stock" not in c.text


def test_a_prose_mention_of_competition_is_not_a_heading():
    """The word appears in prose long before any competitive discussion."""
    text = FILING.replace(
        "Competition We are fundamentally",
        "raise the barriers to entry for competition. Separately we are")
    c = sections(text=text).competition
    # Either nothing is found, or what is found is not the prose sentence.
    assert c is None or not c.text.lower().startswith("competition.")


def test_untruncated_filing_reports_itself_complete():
    s = sections(truncated=False)
    assert s.truncated is False
    assert "full 10-K primary document was retrieved" in s.completeness_note


def test_break_truncation_treated_as_complete():
    """A truncated filing must never be described as a full one."""
    s = sections(truncated=True)
    assert s.truncated is True
    note = s.completeness_note
    assert "exceeded the retrieval cap" in note
    assert "limit of retrieval, not a finding about the company" in note

    with pytest.raises(ValueError, match="completeness"):
        AF.assert_not_presented_as_complete(
            s, "The full annual report lists three competitors.")


def test_completeness_guard_permits_honest_phrasing():
    s = sections(truncated=True)
    AF.assert_not_presented_as_complete(
        s, "The Competition section that was retrieved names three "
           "categories of alternative.")


def test_completeness_guard_is_inert_on_a_complete_filing():
    AF.assert_not_presented_as_complete(
        sections(truncated=False), "The full annual report lists them.")


def test_item_running_to_the_cut_is_marked_incomplete():
    """The item the truncation lands in is the one that must be flagged.

    Not simply the last section by position: `competition` is a subsection
    inside Item 1 and ends at its own marker, so it can be COMPLETE while the
    item containing it is not.
    """
    truncated_text = FILING[:FILING.index("Item 1A. Risk Factors Investing")]
    s = AF.extract(truncated_text, form="10-K", truncated=True)
    business = s.section("business")
    assert business.status == AF.INCOMPLETE
    assert "past the retrieval cut" in business.note
    assert s.competition is not None, (
        "a subsection that closed at its own marker is still usable")


def test_to_text_preserves_word_boundaries_across_tags():
    """Deleting tags welds cells together and hides company names."""
    assert "Palantir" in AF.to_text("<td>rivals</td><td>Palantir</td>")
    assert "rivalsPalantir" not in AF.to_text(
        "<td>rivals</td><td>Palantir</td>")


# ------------------------------------------------- feeding the finder
def _docs():
    c = sections(truncated=True).competition
    return [{"text_content": c.text, "observation_id": "obs_1",
             "source_title": "Palantir 10-K",
             "source_class": "investor_material", "date": "2026-02-17"}]


def test_extracted_competition_yields_the_internal_build_alternative():
    """The phrasing that made this invisible on the real filing."""
    found = CFD.find_competitors(_docs(), subject="Palantir",
                                 today="2026-08-05")
    internal = [c for c in found if c.relationship == CFD.INTERNAL_BUILD]
    assert internal, "the in-house alternative must be found"
    assert internal[0].evidence_ids == ("obs_1",)


def test_category_alternatives_are_found_when_no_company_is_named():
    cats = [c["category"] for c in CFD.category_alternatives(_docs())]
    assert "large enterprise software companies" in cats
    assert "government contractors" in cats


def test_category_alternatives_strip_leading_conjunctions():
    cats = [c["category"] for c in CFD.category_alternatives(_docs())]
    assert not any(c.startswith("and ") for c in cats)
    assert "system integrators" in cats


def test_break_a_competitive_factor_becomes_an_alternative():
    """A factor is not something a buyer can purchase instead."""
    cats = [c["category"] for c in CFD.category_alternatives(_docs())]
    for factor in ("platform capabilities and product functionality",
                   "data security and privacy", "product innovation"):
        assert factor not in cats


def test_category_alternatives_carry_their_limitation():
    for cat in CFD.category_alternatives(_docs()):
        assert "no company is identified" in cat["limitation"]
        assert cat["evidence_id"]


def test_capitalised_names_do_not_leak_into_categories():
    docs = [{"text_content":
             "Our competitors include Snowflake Inc., Databricks Inc. and "
             "large enterprise software companies.",
             "observation_id": "obs_2", "source_title": "t",
             "source_class": "investor_material", "date": "2026-02-17"}]
    cats = [c["category"] for c in CFD.category_alternatives(docs)]
    assert not any("Snowflake" in c or "Databricks" in c for c in cats)
