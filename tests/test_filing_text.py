"""Filing extraction, quality classification and section-aware retention.

The corpus is written, not downloaded: these assert the SHAPE of real filings
(inline-XBRL div/span layout, hidden fact regions, continuation facts, item
ordering) rather than pinning a specific issuer's wording. The live corpus was
measured separately -- Datadog, Microsoft, Caterpillar, NVIDIA, Amazon, Shopify
and a 2007 pre-XBRL Caterpillar 10-K -- and the numbers those runs produced are
recorded in the module docstring of `filing_text`.
"""
from __future__ import annotations

import pytest

from intent_engine.company_ingestion import filing_text as FT
from intent_engine.company_ingestion.parsing import parse_html
from intent_engine.strategic_intelligence import filing_sections as FS


# --- corpus builders ----------------------------------------------------------

def _para(text, *, style="margin-top:12pt"):
    """A paragraph the way a filing agent writes one: div wrapping a span."""
    return (f'<div style="{style}"><span style="font-size:10pt">'
            f'{text}</span></div>')


def _heading(text):
    return (f'<div style="margin-top:18pt"><span '
            f'style="font-weight:700">{text}</span></div>')


def _ixbrl_head():
    """The hidden machinery every inline-XBRL filing carries up front."""
    return (
        '<ix:header><ix:hidden>'
        '<ix:nonNumeric name="dei:EntityRegistrantName" '
        'contextRef="c-1">HIDDEN REGISTRANT FACT</ix:nonNumeric>'
        '</ix:hidden><ix:references><link:schemaRef '
        'xlink:href="http://fasb.org/us-gaap/2025"/></ix:references>'
        '<ix:resources><xbrli:context id="c-1"><xbrli:entity>'
        '<xbrli:identifier scheme="http://www.sec.gov/CIK">'
        '0001561550</xbrli:identifier></xbrli:entity></xbrli:context>'
        '</ix:resources></ix:header>'
    )


def _cover(form="10-K"):
    return (
        '<table><tr><td>UNITED STATES</td></tr>'
        '<tr><td>SECURITIES AND EXCHANGE COMMISSION</td></tr>'
        f'<tr><td>FORM {form}</td></tr>'
        '<tr><td>&#9746;</td><td>ANNUAL REPORT PURSUANT TO SECTION 13 OR '
        '15(d) OF THE SECURITIES EXCHANGE ACT OF 1934</td></tr>'
        '<tr><td>Delaware</td><td>27-2825503</td></tr>'
        '<tr><td>Commission File Number 001-39051</td></tr></table>'
    )


def _contents():
    return ('<table>'
            '<tr><td>Item 1.</td><td>Business</td><td>4</td></tr>'
            '<tr><td>Item 1A.</td><td>Risk Factors</td><td>12</td></tr>'
            '<tr><td>Item 7.</td><td>Management&#8217;s Discussion and '
            'Analysis of Financial Condition and Results of Operations</td>'
            '<td>47</td></tr>'
            '<tr><td>Item 8.</td><td>Financial Statements and Supplementary '
            'Data</td><td>60</td></tr></table>')


BUSINESS = (
    "We provide a subscription platform that lets engineering teams observe "
    "the behaviour of software they run in production, sold to enterprises "
    "through a direct sales force and a self-service motion. ")
RISK = (
    "The market for our platform is intensely competitive and we face "
    "competitors with substantially greater resources than we have, which "
    "may force us to reduce prices to win or retain customers. ")
MDNA = (
    "Revenue increased 26% to $3.1 billion for the year, driven by expansion "
    "within existing customers who purchased additional products. Gross "
    "margin decreased to 79% from 81% as data center costs rose. ")
FINANCIALS = (
    "Cash and cash equivalents were $4.2 billion at year end, and remaining "
    "performance obligations totalled $2.6 billion at the same date. ")


def build_filing(*, form="10-K", ixbrl=True, business=40, risk=40, mdna=40,
                 financials=10, contents=True, tail=""):
    """A filing shaped like the real thing: div/span prose, table furniture."""
    parts = ["<html><head><title>ddog-20251231</title></head><body>"]
    if ixbrl:
        parts.append(_ixbrl_head())
    parts.append(_cover(form))
    if contents:
        parts.append(_contents())
    parts.append(_heading("Item 1. Business"))
    parts += [_para(BUSINESS + f"Paragraph {i} of the business description "
                    "describes how the offering reaches its buyers.")
              for i in range(business)]
    parts.append(_heading("Item 1A. Risk Factors"))
    parts += [_para(RISK + f"Risk {i} concerns concentration in our supply of "
                    "compute capacity.") for i in range(risk)]
    parts.append(_heading("Item 7. Management&#8217;s Discussion and Analysis "
                          "of Financial Condition and Results of Operations"))
    parts += [_para(MDNA + f"Period {i} commentary on the drivers management "
                    "identifies for the reported change.") for i in range(mdna)]
    parts.append(_heading("Item 8. Financial Statements and Supplementary "
                          "Data"))
    parts += [_para(FINANCIALS + f"Note {i} to the consolidated financial "
                    "statements sets out the basis of preparation.")
              for i in range(financials)]
    parts.append(tail)
    parts.append('<div>SIGNATURES</div><table><tr><td>/s/ A Director</td>'
                 '<td>Chief Executive Officer</td></tr></table>')
    parts.append("</body></html>")
    return "".join(parts)


@pytest.fixture(scope="module")
def annual():
    # Sized like the real thing: every filing in the live corpus extracted
    # between 97,845 and 428,519 characters, so a fixture below the retention
    # budget would exercise none of the paths that matter.
    return build_filing(business=220, risk=220, mdna=200, financials=60)


@pytest.fixture(scope="module")
def parsed(annual):
    return FT.parse_filing_html(
        annual, url="https://www.sec.gov/Archives/edgar/data/1/ddog.htm",
        form="10-K")


# --- 1-2. the whole document is traversed, and it is materially bigger --------

def test_div_based_filing_prose_survives_both_parsers(annual):
    """REWRITTEN AT THE UNIFICATION. Read the whole docstring before editing.

    This was a NEGATIVE CONTROL: it asserted that the general page parser
    LOSES a div-based filing, which is why `extract_filing_text` had to exist.
    It can no longer fail in that form, and the reason is not a regression --
    it is that the two lineages independently repaired the same defect from
    opposite ends. The founder side wrote this extractor; the market side
    added `div` and `section` to `parsing._BLOCK` after measuring that
    Caterpillar's Q2 exhibit kept 13,462 of 64,547 characters and lost every
    sentence of narrative.

    Measured after the merge: 35,836 characters from the general parser
    against 35,795 from the extractor. Keeping `len(new) > 5 * len(old)`
    would be asserting that a fixed parser is still broken.

    So the control is inverted to the property that actually matters and can
    still fail: the MD&A prose of a div-laid-out filing must be recoverable,
    by both paths. If either regresses to tag-limited extraction, this goes
    red.
    """
    old = parse_html(annual)["text"]
    new = FT.extract_filing_text(annual)["text"]
    for name, text in (("parse_html", old), ("extract_filing_text", new)):
        assert MDNA[:40] in text, (
            f"{name} lost the MD&A prose of a div-based filing; this is the "
            "defect both parsers were repaired for")
    # And the extractor must not have become the WEAKER of the two while
    # nobody was looking: it may not lose material the general parser keeps.
    assert len(new) >= 0.9 * len(old), (
        f"extract_filing_text kept {len(new)} characters where the general "
        f"parser kept {len(old)}")


def test_full_dom_is_traversed(annual):
    extracted = FT.extract_filing_text(annual)
    text = extracted["text"]
    assert BUSINESS[:40] in text          # front
    assert MDNA[:40] in text              # middle
    assert "SIGNATURES" in text           # very end
    assert extracted["node_count"] > 100


def test_span_only_prose_survives():
    """No <p>, no <li>, no heading tags -- the exact shape that was lost.

    The second assertion used to be `not in parse_html(...)`. See
    `test_div_based_filing_prose_survives_both_parsers`: the general parser
    was repaired independently on the market lineage, so requiring it to
    still fail would be pinning a fixed defect open. Both must now keep it.
    """
    html = "<html><body>" + _para(
        "The company sells a subscription platform to enterprise buyers and "
        "recognises that revenue over the contract term.") + "</body></html>"
    assert "subscription platform" in FT.extract_filing_text(html)["text"]
    assert "subscription platform" in parse_html(html)["text"]


# --- 3-5. sections ------------------------------------------------------------

def test_item_1_1a_and_7_are_all_detected(annual):
    sections = FS.find_sections(FT.extract_filing_text(annual)["text"])
    assert "item_1" in sections
    assert "item_1a" in sections
    assert "item_7" in sections


def test_item_7_detected_where_present_and_absent_where_not():
    with_mdna = build_filing()
    assert "item_7" in FS.find_sections(
        FT.extract_filing_text(with_mdna)["text"])
    without = build_filing(mdna=0)
    sections = FS.find_sections(FT.extract_filing_text(without)["text"])
    assert "item_7" not in sections
    assert "item_1" in sections           # the rest still reads


def test_item_7_late_in_the_document_still_survives_retention():
    """A filing whose MD&A sits past a very long Item 1."""
    html = build_filing(business=400, risk=200, mdna=30)
    out = FT.parse_filing_html(html, form="10-K")
    assert out["filing"]["full_text_chars"] > FT.RETENTION_BUDGET
    assert "item_7" in FS.find_sections(out["text"])


def test_a_cross_reference_is_not_a_section_heading():
    """"see Part I, Item 1A" inside MD&A must not start Risk Factors."""
    html = build_filing(
        tail=_para("For further discussion see Part I, Item 1A. Risk Factors "
                   "of this Annual Report, which is incorporated here by "
                   "reference in its entirety for the reader's convenience."))
    text = FT.extract_filing_text(html)["text"]
    spans = {s["key"]: s for s in FS.section_spans(text)}
    assert spans["item_1a"]["body_start"] < spans["item_7"]["body_start"]


# --- 6-9. hidden metadata, visible facts, duplicates ---------------------------

def test_hidden_xbrl_metadata_is_excluded(annual):
    text = FT.extract_filing_text(annual)["text"]
    assert "HIDDEN REGISTRANT FACT" not in text
    assert "0001561550" not in text
    assert "fasb.org" not in text
    assert "xbrli" not in text


def test_visible_inline_xbrl_facts_are_retained():
    html = ("<html><body><div><span>Revenue for the period was "
            '<ix:nonFraction name="us-gaap:Revenues" contextRef="c-1" '
            'scale="6" decimals="-5">3,102.4</ix:nonFraction> million, an '
            "increase over the prior year.</span></div></body></html>")
    text = FT.extract_filing_text(html)["text"]
    assert "3,102.4" in text
    assert "Revenue for the period was 3,102.4 million" in text


def test_continuation_facts_are_kept():
    """`ix:continuation` carries displayed text and must not be dropped."""
    html = ("<html><body><div><span>"
            '<ix:nonNumeric name="x" continuedAt="c2">The agreement runs '
            "for three years</ix:nonNumeric>"
            '<ix:continuation id="c2"> and renews automatically unless '
            "either party objects.</ix:continuation>"
            "</span></div></body></html>")
    text = FT.extract_filing_text(html)["text"]
    assert "renews automatically" in text


def test_hidden_style_regions_are_excluded():
    html = ('<html><body><div style="display:none"><span>SHOULD NOT APPEAR'
            "</span></div>" + _para("Visible business commentary about how "
                                    "the company earns its revenue.")
            + "</body></html>")
    text = FT.extract_filing_text(html)["text"]
    assert "SHOULD NOT APPEAR" not in text
    assert "Visible business commentary" in text


def test_repeated_page_furniture_is_bounded_but_headings_survive():
    body = "".join("<div>Table of Contents</div>" + _para(
        f"Substantive paragraph number {i} describing the operations of the "
        "business in ordinary prose.") for i in range(12))
    text = FT.extract_filing_text("<html><body>" + body + "</body></html>")["text"]
    assert text.lower().count("table of contents") == 1
    assert text.count("Substantive paragraph number") == 12


def test_table_rows_are_read_as_rows():
    html = ("<html><body><table><tr><td>Revenue</td><td>$</td>"
            "<td>3,102</td><td>$</td><td>2,463</td></tr></table></body></html>")
    assert "Revenue $ 3,102 $ 2,463" in FT.extract_filing_text(html)["text"]


def test_script_and_style_are_dropped():
    html = ("<html><body><script>var secret = 1;</script>"
            "<style>.a{color:red}</style>"
            + _para("The only readable sentence in this document.")
            + "</body></html>")
    text = FT.extract_filing_text(html)["text"]
    assert "var secret" not in text and "color:red" not in text
    assert "only readable sentence" in text


# --- 10-13. quality verdicts ---------------------------------------------------

def test_full_body_is_confirmed(parsed):
    assert parsed["filing"]["extraction_quality"] == FT.FULL_BODY_CONFIRMED
    assert parsed["filing"]["diagnostics"]["late_sections"]


def test_front_only_is_detected():
    """A large response yielding almost no text is the measured 10-K failure."""
    verdict = FT.classify_extraction(
        text="Cover page.\nDelaware.\n27-2825503.\n" + "Item 1. Business.\n",
        raw_chars=2_086_014, form="10-K", sections={})
    assert verdict["quality"] == FT.FRONT_ONLY
    assert not verdict["usable"]


def test_front_only_is_detected_from_sections_alone():
    line = ("The business description continues in ordinary prose for a "
            "further clause so that the line reads as a paragraph. ") * 3
    verdict = FT.classify_extraction(
        text="\n".join([line] * 60), raw_chars=60_000, form="10-K",
        sections={"item_1": "y" * 900, "item_1a": "z" * 900})
    assert verdict["quality"] == FT.FRONT_ONLY


def test_index_only_is_detected():
    verdict = FT.classify_extraction(
        text="Document Format Files\nSeq Description Document Type Size\n"
             "1 10-K ddog-20251231.htm 2086014",
        raw_chars=12_540, form="10-K", sections={})
    assert verdict["quality"] == FT.INDEX_ONLY


def test_cover_only_is_detected():
    verdict = FT.classify_extraction(
        text="FORM 10-K.\nDelaware.\n27-2825503.\nCommission File Number.",
        raw_chars=4_000, form="10-K", sections={})
    assert verdict["quality"] == FT.COVER_ONLY


def test_xbrl_machinery_is_not_mistaken_for_a_filing():
    verdict = FT.classify_extraction(
        text="Entity Registrant Name\nDocument Fiscal Year Focus",
        raw_chars=62_312, form="10-K", sections={},
        mime_type="application/xml",
        raw_head='<?xml version="1.0"?><xsd:schema xmlns:xsd="x">')
    assert verdict["quality"] == FT.XBRL_METADATA_ONLY


def test_sec_block_page_is_detected():
    verdict = FT.classify_extraction(
        text="Your Request Originated from an Undeclared Automated Tool",
        raw_chars=900, form="10-K", sections={}, status_code=403)
    assert verdict["quality"] == FT.SEC_BLOCKED
    assert not verdict["usable"]


def test_malformed_filing_fails_safely():
    """Broken markup yields a verdict, never an exception."""
    html = "<html><body><div><span>unclosed" + "<div>" * 200
    extracted = FT.extract_filing_text(html)
    verdict = FT.classify_extraction(
        text=extracted["text"], raw_chars=len(html), form="10-K", sections={})
    assert verdict["quality"] in FT.QUALITY_STATES
    empty = FT.classify_extraction(text="", raw_chars=5_000, form="10-K",
                                   sections={})
    assert empty["quality"] == FT.MALFORMED


def test_unsupported_content_type_is_named():
    verdict = FT.classify_extraction(
        text="anything", raw_chars=10, form="10-K", sections={},
        mime_type="application/pdf")
    assert verdict["quality"] == FT.UNSUPPORTED


def test_amendment_without_standard_items_is_not_called_a_cover_page():
    """Measured on Shopify's 10-K/A, which carries only Part III."""
    prose = ("The compensation committee reviews the peer group annually and "
             "sets targets against it, and the following table sets out the "
             "amounts awarded to each named executive officer. ") * 60
    verdict = FT.classify_extraction(
        text=prose, raw_chars=len(prose) * 5, form="10-K/A", sections={})
    assert verdict["quality"] == FT.SUBSTANTIVE_PARTIAL_BODY


def test_a_current_report_is_not_required_to_have_items():
    """An 8-K has no Item 1 or Item 7 by design; demanding them reports every
    current report as broken. Measured on a real Datadog 8-K: 4,417 chars."""
    body = "\n".join([
        "On June 15, 2026 the registrant announced financial results for its "
        "first quarter ended March 31, 2026, and a copy of the press release "
        "is furnished as Exhibit 99.1 to this Current Report on Form 8-K.",
        "The information in this Item 2.02, including the exhibit attached "
        "hereto, is furnished and shall not be deemed filed for purposes of "
        "Section 18 of the Securities Exchange Act of 1934, as amended.",
    ])
    verdict = FT.classify_extraction(
        text=body, raw_chars=53_455, form="8-K", sections={})
    assert verdict["quality"] == FT.FULL_BODY_CONFIRMED

    cover_sheet = "FORM 8-K.\nDelaware.\nCommission File Number 001-39051."
    assert FT.classify_extraction(
        text=cover_sheet, raw_chars=53_455, form="8-K",
        sections={})["quality"] == FT.COVER_ONLY


def test_truncated_response_cannot_be_confirmed_full():
    sections = {"item_1": "a" * 200, "item_7": "b" * 200}
    line = ("Management discusses the drivers of the reported change in "
            "revenue and the costs that moved against it in the period. ") * 2
    text = "\n".join([line] * 400)
    assert FT.classify_extraction(
        text=text, raw_chars=len(text) * 2, form="10-K", sections=sections,
        truncated=True)["quality"] == FT.SUBSTANTIVE_PARTIAL_BODY


# --- 14-16. section-aware retention -------------------------------------------

def test_retention_is_bounded(parsed):
    assert len(parsed["text"]) <= FT.RETENTION_BUDGET


def test_short_filing_is_retained_whole():
    html = build_filing(business=2, risk=2, mdna=2, financials=1)
    out = FT.parse_filing_html(html, form="10-K")
    assert out["filing"]["retention_status"] == "COMPLETE"
    assert out["filing"]["retained_chars"] == out["filing"]["full_text_chars"]


def test_mdna_cannot_be_displaced_by_a_huge_early_section():
    """The retention contract, stated as the failure it prevents.

    Front truncation at 120,000 on a real Datadog 10-K stored Business and
    stopped before MD&A. An enormous Item 1 must not be able to do that.
    """
    html = build_filing(business=900, risk=20, mdna=20)
    out = FT.parse_filing_html(html, form="10-K")
    assert out["filing"]["full_text_chars"] > 2 * FT.RETENTION_BUDGET
    retained = {s["key"] for s in out["filing"]["sections_retained"]}
    assert "item_7" in retained
    assert "item_1a" in retained
    assert MDNA[:40] in out["text"]
    # and the front-truncated store, which is what this replaced, would not
    full = FT.extract_filing_text(html)["text"]
    assert MDNA[:40] not in full[:FT.RETENTION_BUDGET]


def test_multiple_priority_sections_are_retained(parsed):
    keys = {s["key"] for s in parsed["filing"]["sections_retained"]}
    assert len(keys) >= 3


def test_no_single_section_can_take_the_whole_budget():
    html = build_filing(business=900, risk=900, mdna=900)
    out = FT.parse_filing_html(html, form="10-K")
    for span in out["filing"]["sections_retained"]:
        assert span["retained_chars"] <= FT.MAX_SECTION_CHARS


def test_retained_spans_carry_provenance(parsed):
    full = FT.extract_filing_text(
        build_filing(business=220, risk=220, mdna=200, financials=60))["text"]
    for span in parsed["filing"]["sections_retained"]:
        assert span["source_end"] > span["source_start"] >= 0
        assert span["source_end"] <= len(full) + 1
        assert len(span["excerpt_hash"]) == 16
        assert span["name"]


def test_retained_text_is_still_section_readable(parsed):
    """Downstream re-derives sections from the stored blob; it must work."""
    sections = FS.find_sections(parsed["text"])
    assert "item_7" in sections
    excerpt, label = FS.best_excerpt(parsed["text"])
    assert "Item 7" in label
    assert len(excerpt) > 80


def test_retention_falls_back_bounded_when_nothing_is_recognisable():
    text = ("This document contains ordinary prose and no item headings at "
            "all, repeated until it exceeds the retention budget. ") * 2000
    result = FT.retain_filing_text(text)
    assert result["status"] == "FALLBACK_FRONT"
    assert len(result["text"]) <= FT.RETENTION_BUDGET


def test_identity_is_always_retained(parsed):
    assert "FORM 10-K" in parsed["text"][:FT.IDENTITY_CHARS + 200]


# --- 17. everything that is not a filing is untouched --------------------------

def test_non_filing_extraction_is_unchanged():
    page = ("<html><head><title>About</title>"
            '<meta name="description" content="We build tools."></head>'
            "<body><main><h1>About us</h1><p>We sell software to teams that "
            "run production systems.</p><ul><li>Fast</li></ul></main>"
            "</body></html>")
    before = parse_html(page)
    assert before["text"].startswith("About us.")
    assert "We sell software" in before["text"]
    assert before["extraction_mode"] == "body"


def test_only_filing_urls_take_the_filing_path():
    assert FT.is_filing_document(url="https://www.sec.gov/Archives/x.htm")
    assert FT.is_filing_document(url="https://example.com/x", form="10-K")
    assert not FT.is_filing_document(url="https://example.com/about")
    assert not FT.is_filing_document(url="https://blog.example.com/sec-filing")


# --- bounds -------------------------------------------------------------------

def test_extraction_is_deterministic(annual):
    assert (FT.extract_filing_text(annual)["text"]
            == FT.extract_filing_text(annual)["text"])


def test_a_very_large_filing_stays_bounded():
    html = build_filing(business=3000, risk=1500, mdna=1500, financials=500)
    assert len(html) > 2_000_000
    out = FT.parse_filing_html(html, form="10-K")
    assert len(out["text"]) <= FT.RETENTION_BUDGET
    assert out["filing"]["extraction_quality"] == FT.FULL_BODY_CONFIRMED


def test_empty_and_none_input_do_not_raise():
    for value in ("", None):
        result = FT.extract_filing_text(value)
        assert result["text"] == ""
    assert FT.parse_filing_html("")["text"] == ""
