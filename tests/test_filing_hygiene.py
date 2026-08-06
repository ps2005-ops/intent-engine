"""Filing furniture must not reach an executive surface.

The first case is verbatim from the deployed preview (commit 16dc4b8,
Datadog, 2026-08-05), slide 1 of 7.
"""
from __future__ import annotations

import pytest

from intent_engine.strategic_intelligence import filing_hygiene as FH

# Verbatim from the live slide.
DATADOG_SLIDE_1 = (
    "☒. ANNUAL REPORT PURSUANT TO SECTION 13 OR 15(d) OF THE SECURITIES "
    "EXCHANGE ACT OF 1934. ☐. TRANSITION REPORT PURSUANT TO SECTION 13 "
    "OR 15(d) OF THE SECURITIES EXCHANGE ACT OF 1934. Delaware. 27-2825503. "
    "(State or other jurisdiction ofincorporation or organization). (I.R.S. "
    "Emplo."
)


@pytest.mark.parametrize("text", [
    DATADOG_SLIDE_1,
    # other filing layouts -- not only Datadog
    "☐ QUARTERLY REPORT PURSUANT TO SECTION 13 OR 15(d) OF THE "
    "SECURITIES EXCHANGE ACT OF 1934",
    "For the fiscal year ended December 31, 2025",
    "Commission File Number 001-38480",
    "Indicate by check mark whether the registrant is a well-known seasoned "
    "issuer, as defined in Rule 405 of the Securities Act.",
    "Large accelerated filer ☒ Accelerated filer ☐",
    "Emerging growth company ☐",
    "Securities registered pursuant to Section 12(b) of the Act:",
    "Title of each class",
    "Name of each exchange on which registered",
    "Address of principal executive offices",
    "I.R.S. Employer Identification No.",
    "TABLE OF CONTENTS",
    "Exhibit Index",
    "See accompanying notes to consolidated financial statements.",
    "The accompanying notes are an integral part of these financial "
    "statements.",
    "Pursuant to the requirements of the Securities Exchange Act of 1934, "
    "the registrant has duly caused this report to be signed on its behalf.",
    "Actual results could differ materially from those projected.",
    "Inline XBRL data is contained in Exhibit 101.",
    "Delaware. 27-2825503.",
    "",
    "   ",
])
def test_filing_furniture_is_refused(text):
    assert FH.is_filing_furniture(text)


@pytest.mark.parametrize("text", [
    # real, commercially meaningful filing prose -- must survive
    "Revenue increased 26% to $2.68 billion in fiscal 2025, driven by "
    "expansion within existing customers.",
    "We had 3,610 customers with annual recurring revenue of $100,000 or "
    "more, up from 3,390 a year earlier.",
    "No single customer accounted for more than 10% of our revenue in any "
    "period presented.",
    "Our largest customers are increasingly consolidating observability "
    "spend onto a single platform, which lengthens our sales cycle but "
    "raises contract value.",
    "We face intense competition from both established software vendors and "
    "the native monitoring tools offered by cloud providers.",
    "If we are unable to attract new customers, our revenue growth could be "
    "harmed and our results of operations would suffer.",
])
def test_real_filing_content_survives(text):
    """The control. Refusing these would delete the filing's value, which is
    the opposite of the fix."""
    assert not FH.is_filing_furniture(text)


def test_checkbox_glyphs_never_reach_executive_text():
    out = FH.executive_safe([DATADOG_SLIDE_1,
                             "Revenue rose 26% to $2.68 billion."])
    joined = " ".join(out)
    for glyph in FH.CHECKBOX_GLYPHS:
        assert glyph not in joined


def test_the_live_defect_leaves_the_real_fact_as_the_first_candidate():
    """Slide 1 took candidate[0]. Before the fix that was the cover page."""
    out = FH.executive_safe([
        DATADOG_SLIDE_1,
        "Commission File Number 001-38480",
        "Revenue increased 26% to $2.68 billion in fiscal 2025.",
    ])
    assert out
    assert out[0].startswith("Revenue increased 26%")


def test_a_sentence_keeps_its_meaning_when_a_glyph_is_stripped():
    assert FH.strip_checkboxes("Revenue rose 26% ✓") == "Revenue rose 26%"


def test_everything_furniture_yields_nothing_rather_than_a_bad_first_line():
    """An empty list is honest; a cover page presented as a finding is not."""
    assert FH.executive_safe([DATADOG_SLIDE_1, "TABLE OF CONTENTS"]) == []


def test_the_producer_filters_before_the_three_item_cap():
    """The cover page sorts first in the document, so filtering after the cap
    would leave the slide empty."""
    from intent_engine.strategic_intelligence import decision as D
    report = {
        "company_name": "Acme",
        "hypotheses": [],
        "observations": [
            {"excerpt": DATADOG_SLIDE_1},
            {"excerpt": "Commission File Number 001-38480"},
            {"excerpt": "TABLE OF CONTENTS"},
            {"excerpt": "Revenue increased 26% to $2.68 billion."},
        ],
    }
    d = D.decision_of(report)
    assert d.verified
    assert "Revenue increased 26%" in d.verified[0]
    assert not any("PURSUANT TO SECTION" in v for v in d.verified)


def test_the_chokepoint_every_surface_renders_is_filtered():
    """Filtering only `decision_of` was not enough: the live decision page and
    slide 1 still showed the cover page, because the surfaces render whatever
    `compose_decision` built. Pinned at the convergence point."""
    from intent_engine.strategic_intelligence import decision as D
    d = D.compose_decision("Acme", None, verified=(
        DATADOG_SLIDE_1,
        "TABLE OF CONTENTS",
        "Revenue increased 26% to $2.68 billion.",
    ))
    assert not any("PURSUANT TO SECTION" in v for v in d.verified)
    for glyph in FH.CHECKBOX_GLYPHS:
        assert not any(glyph in v for v in d.verified)
    assert any("Revenue increased 26%" in v for v in d.verified)


def test_a_decision_stored_before_this_rule_is_cleaned_on_rehydration():
    from intent_engine.strategic_intelligence import decision as D
    d = D.decision_from_dict({
        "verified": [DATADOG_SLIDE_1, "Revenue increased 26%."]})
    assert not any("PURSUANT TO SECTION" in v for v in d.verified)
    assert d.verified


# =============================================================================
# Safe-harbour boilerplate, measured on the deployed preview
#
# A Stripe run cited another registrant's 10-K and showed, as the evidence:
# "Readers of this report are advised that this document contains both
# statements of historical facts and forward-looking statements." The existing
# rule required "statements ... within the meaning", and the plural in
# "historical facts" defeated the singular pattern that was meant to catch it.
# =============================================================================

@pytest.mark.parametrize("boilerplate", [
    "Readers of this report are advised that this document contains both "
    "statements of historical facts and forward-looking statements.",
    "All statements other than statements of historical fact are "
    "forward-looking statements.",
    "Forward-looking statements are subject to certain risks and "
    "uncertainties, which could cause actual results to differ.",
    "This discussion contains forward-looking statements that involve risks "
    "and uncertainties.",
])
def test_safe_harbour_boilerplate_is_furniture(boilerplate):
    assert FH.is_filing_furniture(boilerplate)


@pytest.mark.parametrize("real", [
    "Stripe is a financial services platform that helps businesses accept "
    "payments and manage money movement.",
    "Total sales and revenues for 2025 were $67.589 billion, an increase of "
    "$2.780 billion, or 4 percent, compared with 2024.",
    "We derive substantially all of our revenue from subscriptions to our "
    "platform, which we sell on an annual basis.",
])
def test_real_disclosure_is_not_furniture(real):
    assert not FH.is_filing_furniture(real)
