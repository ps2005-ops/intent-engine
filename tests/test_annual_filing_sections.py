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


# ------------------------------------------------ the retrieval wiring
def test_annual_and_quarterly_are_separate_candidate_families():
    """Sharing one family meant the 10-Q always won and the 10-K never ran."""
    from intent_engine.company_ingestion import edgar
    assert edgar._FORM_FAMILY["10-K"] != edgar._FORM_FAMILY["10-Q"]
    assert edgar._FAMILY_ORDER.index("annual") < \
           edgar._FAMILY_ORDER.index("quarterly")


def test_the_annual_report_wins_a_slot_against_a_filers_usual_mix():
    """A filer publishes many 8-Ks; the annual report must still be proposed."""
    from intent_engine.company_ingestion import edgar
    forms = ["8-K", "8-K", "10-Q", "8-K", "10-K", "8-K", "DEF 14A"]
    dates = ["2026-08-01"] * len(forms)
    order = edgar._spread_by_family(list(range(len(forms))), forms, dates,
                                    today="2026-08-05")
    chosen = [forms[i] for i in order[:edgar.MAX_EDGAR_CANDIDATES]]
    assert "10-K" in chosen, chosen
    assert "10-Q" in chosen, chosen


def test_only_annual_forms_are_retrieved_truncated():
    from intent_engine.company_ingestion import edgar
    assert "10-K" in edgar.TRUNCATABLE_FORMS
    assert "20-F" in edgar.TRUNCATABLE_FORMS
    assert "10-Q" not in edgar.TRUNCATABLE_FORMS
    assert "8-K" not in edgar.TRUNCATABLE_FORMS


def _transport(body: bytes, exceeded: bool):
    def tx(url, timeout):
        return 200, {"content-type": "text/html"}, body, exceeded
    return tx


def test_over_cap_response_is_still_discarded_by_default():
    """The general retrieval path is unchanged: an over-cap page is refused."""
    from intent_engine.company_ingestion.fetch import safe_fetch
    result = safe_fetch("https://example.com/big",
                        transport=_transport(b"<html>x</html>", True),
                        resolver=False)
    assert result["ok"] is False
    assert result["failure_type"] == "too_large"


def test_over_cap_annual_filing_is_kept_and_marked_truncated():
    from intent_engine.company_ingestion.fetch import safe_fetch
    result = safe_fetch("https://www.sec.gov/Archives/x.htm",
                        transport=_transport(b"<html>Item 1. Business</html>",
                                             True),
                        resolver=False, accept_truncated=True)
    assert result["ok"] is True
    assert result["truncated"] is True
    assert "Item 1. Business" in result["body"]


def test_an_under_cap_response_is_never_marked_truncated():
    from intent_engine.company_ingestion.fetch import safe_fetch
    result = safe_fetch("https://www.sec.gov/Archives/x.htm",
                        transport=_transport(b"<html>ok</html>", False),
                        resolver=False, accept_truncated=True)
    assert result["ok"] is True and result["truncated"] is False


# ------------------------------- the raw-filing fabrication this prevents
def test_break_raw_filing_fabricates_competitors_from_its_own_boilerplate():
    """Mining a whole 10-K names the company's own CEO as a competitor.

    Measured against the real Palantir 10-K: passing the raw 550,000-character
    document to the finder returned five "competitors" — Alexander Karp
    (Palantir's own CEO), Palantir Foundry (its own product), "Founder Voting
    Agreement", "Intellectual Property", and the HTML entity fragment "O&amp".
    Every one of them was captured from risk-factor and exhibit boilerplate
    that mentions competition without naming a rival.

    Narrowing to the extracted Competition section is what stops it.
    """
    from intent_engine.webapp.app import _with_annual_filing_sections

    raw = (FILING +
           " Our founder Alexander Karp controls a majority of voting power "
           "under the Founder Voting Agreement. We face competition from "
           "emerging companies. Intellectual Property We have registered "
           "trademarks for Palantir Foundry and our corporate logo.")
    docs = [{"source_title": "SEC 10-K (2026-02-17)", "text_content": raw,
             "observation_id": "obs_1", "source_class": "investor_material",
             "date": "2026-02-17", "truncated": True}]

    narrowed = _with_annual_filing_sections(docs)
    assert len(narrowed[0]["text_content"]) < len(raw) / 2
    assert narrowed[0]["filing_completeness"]

    names = {c.name for c in CFD.find_competitors(
        narrowed, subject="Palantir", today="2026-08-05")}
    for fabrication in ("Alexander Karp", "Founder Voting Agreement",
                        "Intellectual Property", "Palantir Foundry"):
        assert fabrication not in names, fabrication
    assert "The buyer's own engineering team" in names


def test_non_annual_documents_pass_through_untouched():
    from intent_engine.webapp.app import _with_annual_filing_sections
    docs = [{"source_title": "SEC 10-Q (2026-08-04)",
             "text_content": "quarterly body", "observation_id": "o1"}]
    assert _with_annual_filing_sections(docs)[0]["text_content"] == \
           "quarterly body"


def test_an_unparseable_filing_keeps_its_original_text():
    """This may only ever add evidence, never drop a document from a run."""
    from intent_engine.webapp.app import _with_annual_filing_sections
    docs = [{"source_title": "SEC 10-K (2026-02-17)",
             "text_content": "no statutory headings here at all",
             "observation_id": "o1"}]
    assert _with_annual_filing_sections(docs)[0]["text_content"] == \
           "no statutory headings here at all"
