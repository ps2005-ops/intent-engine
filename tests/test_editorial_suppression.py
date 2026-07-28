"""Empty-section suppression and editorial deduplication.

What the tester actually saw: a page of headings with a dash under each one.
"Likely leadership discussions: —". "Decisions affected: —". The report had run,
the sections had rendered, and every one was a small typographic apology.

The mirror image: the same six-source evidence block under every hypothesis, so
scrolling produced the identical citations four times.
"""
import re

import pytest

from intent_engine.strategic_intelligence.editorial import (
    MAX_DUPLICATION_RATIO, consolidate_limitations, deduplicate,
    duplication_metrics, find_duplicates, is_meaningful, meaningful_items,
    merge_overlapping, render_sections, section, shared_evidence, similarity,
)
from intent_engine.strategic_intelligence.render import render_strategic_report


# --- what counts as nothing --------------------------------------------------
@pytest.mark.parametrize("value", [
    "", "   ", "-", "--", "—", "–", "N/A", "n/a", "None", "none detected",
    "None detected", "Not available", "NOT APPLICABLE", "unknown", "TBD",
    " — ", "...", None, [], {},
])
def test_placeholders_are_not_content(value):
    assert not is_meaningful(value)


@pytest.mark.parametrize("value", [
    "Shopify is moving upmarket", "0", "34%", ["a finding"],
    {"k": "a finding"},
])
def test_real_content_is_content(value):
    assert is_meaningful(value)


def test_none_detected_is_never_shown_as_a_result():
    """To a business reader "None detected" says the analysis looked and found
    nothing. It usually means it never had the evidence to look with."""
    assert not is_meaningful("None detected")
    assert meaningful_items(["None detected", "Not available", "—"]) == []


# --- the rendering contract --------------------------------------------------
def test_a_section_with_nothing_in_it_does_not_exist():
    assert section("Blind spots", []) is None
    assert section("Blind spots", ["—", "None detected"]) is None


def test_one_item_is_one_card_not_a_list_of_one():
    s = section("Blind spots", ["A real tension"])
    assert s["single"] is True
    assert s["count"] == 1


def test_two_or_more_items_are_ranked():
    s = section("Findings", [{"t": "b", "n": 2}, {"t": "a", "n": 1}],
                key="t", rank=lambda x: x["n"])
    assert [i["t"] for i in s["items"]] == ["a", "b"]


def test_render_sections_drops_the_absent_ones():
    kept = render_sections([section("A", ["real"]), section("B", []),
                            section("C", ["also real"])])
    assert [s["title"] for s in kept] == ["A", "C"]


# --- deduplication -----------------------------------------------------------
def test_the_same_claim_twice_is_one_claim():
    items = ["Shopify is moving upmarket into enterprise commerce",
             "Shopify is moving upmarket into enterprise commerce"]
    assert len(deduplicate(items)) == 1


def test_near_duplicates_differing_only_in_wording_are_merged():
    items = ["Shopify is moving upmarket into enterprise commerce.",
             "Shopify is moving upmarket, into enterprise commerce!"]
    assert len(deduplicate(items)) == 1


def test_genuinely_different_claims_both_survive():
    items = ["Shopify is moving upmarket into enterprise commerce",
             "Shopify's payments attach rate is rising among existing "
             "merchants"]
    assert len(deduplicate(items)) == 2


def test_the_first_statement_of_an_idea_is_the_one_that_survives():
    items = ["The original phrasing of the finding about enterprise",
             "The original phrasing of the finding about enterprise too"]
    kept = deduplicate(items)
    assert kept[0] == items[0]


def test_duplicate_detection_does_not_chain():
    # B duplicates A, C duplicates B — C must map to A, not be kept because B
    # was already removed.
    items = ["enterprise commerce upmarket motion",
             "enterprise commerce upmarket motion",
             "enterprise commerce upmarket motion"]
    assert len(deduplicate(items)) == 1


def test_similarity_is_symmetric_and_bounded():
    a, b = "shopify moves upmarket", "shopify moves downmarket"
    assert similarity(a, b) == similarity(b, a)
    assert 0.0 <= similarity(a, b) <= 1.0
    assert similarity(a, a) == 1.0


# --- overlapping hypotheses --------------------------------------------------
def test_hypotheses_sharing_a_mechanism_and_decision_are_one_hypothesis():
    hypotheses = [
        {"statement": "Upmarket push", "mechanism": "enterprise motion",
         "decision": "pricing", "evidence_count": 2, "evidence": ["e1"]},
        {"statement": "Enterprise focus", "mechanism": "enterprise motion",
         "decision": "pricing", "evidence_count": 5, "evidence": ["e2"]},
    ]
    merged = merge_overlapping(hypotheses)
    assert len(merged) == 1
    # the better-supported one survives...
    assert merged[0]["statement"] == "Enterprise focus"
    # ...and absorbs the other's evidence rather than losing a citation
    assert set(merged[0]["evidence"]) == {"e1", "e2"}
    assert "Upmarket push" in merged[0]["merged_from"]


def test_different_mechanisms_are_kept_apart():
    hypotheses = [
        {"statement": "A", "mechanism": "enterprise motion",
         "decision": "pricing", "evidence_count": 2},
        {"statement": "B", "mechanism": "payments attach",
         "decision": "pricing", "evidence_count": 2},
    ]
    assert len(merge_overlapping(hypotheses)) == 2


def test_hypotheses_without_a_mechanism_are_never_merged_blindly():
    hypotheses = [{"statement": "A", "evidence_count": 1},
                  {"statement": "B", "evidence_count": 1}]
    assert len(merge_overlapping(hypotheses)) == 2


# --- limitations --------------------------------------------------------------
def test_the_same_caveat_appears_once_not_six_times():
    limitations = consolidate_limitations(
        ["No independent source corroborates this"],
        ["No independent source corroborates this."],
        ["No independent source corroborates this!"],
        ["Pricing evidence is missing entirely"])
    assert len(limitations) == 2


def test_placeholder_limitations_are_dropped():
    assert consolidate_limitations(["—", "None", ""], ["A real gap exists"]) \
        == ["A real gap exists"]


# --- evidence reuse -----------------------------------------------------------
def test_evidence_used_under_every_claim_is_detected():
    blocks = [["s1", "s2", "s3"], ["s1", "s2", "s3"], ["s1", "s2", "s3"]]
    reused = shared_evidence(blocks)
    assert set(reused) == {"s1", "s2", "s3"}
    assert all(count == 3 for count in reused.values())


def test_evidence_cited_once_is_not_flagged_as_reused():
    assert shared_evidence([["s1"], ["s2"], ["s3"]]) == {}


# --- metrics and thresholds ---------------------------------------------------
def test_a_repetitive_report_fails_the_release_thresholds():
    statements = ["Shopify is moving upmarket into enterprise commerce"] * 4
    metrics = duplication_metrics(
        statements=statements,
        evidence_blocks=[["s1", "s2", "s3", "s4", "s5", "s6"]] * 4,
        limitations=["No independent source"] * 3)
    assert not metrics["passes"]
    assert metrics["duplication_ratio"] > MAX_DUPLICATION_RATIO
    assert metrics["evidence_reuse_ratio"] > 0.5
    assert metrics["failures"]


def test_a_varied_report_passes():
    metrics = duplication_metrics(
        statements=[
            "Shopify is moving upmarket into enterprise commerce",
            "Payments attach rate is rising among existing merchants",
            "International expansion depends on local payment rails",
            "Developer platform investment signals ecosystem lock-in",
        ],
        evidence_blocks=[["s1"], ["s2"], ["s3"], ["s4"]],
        limitations=["No independent corroboration of pricing"])
    assert metrics["passes"], metrics["failures"]
    assert metrics["unique_insight_ratio"] == 1.0


def test_metrics_are_stable_on_an_empty_report():
    metrics = duplication_metrics()
    assert metrics["duplication_ratio"] == 0.0
    assert metrics["passes"]


# --- through the real renderer ------------------------------------------------
def _bare_report():
    """A report whose optional sections are all genuinely empty."""
    return {
        "company_name": "Thinlake",
        "status": "PARTIAL_STRATEGIC_EVIDENCE",
        "thesis": {"view": "Thinlake appears to be moving toward vertical "
                           "logistics software", "why_care": "",
                   "transition": ""},
        "hypotheses": [], "patterns": [], "observations": [],
        "blind_spots": [], "questions": [], "shifts": [],
        "decision_implications": [], "surprises": [], "opportunities": [],
        "vulnerabilities": [], "underexamined_questions": [], "agenda": [],
        "timeline": [], "evidence_gaps": [], "quality_findings": [],
        "what_changed": [], "feed": [], "mental_model": {}, "source_library": {},
        "source_class_coverage": {},
    }


def test_the_rendered_page_contains_no_standalone_dashes():
    html = render_strategic_report(_bare_report())
    # a dash alone inside any element is the exact artefact the tester saw
    assert not re.search(r">\s*[—–-]\s*<", html)


def test_empty_sections_are_absent_not_blank():
    html = render_strategic_report(_bare_report())
    for heading in ("Strategic surprises", "Strategic hypotheses",
                    "Strategic opportunities", "Possible blind spots",
                    "Questions for leadership",
                    "Questions that may be underexamined"):
        assert f">{heading}<" not in html, \
            f"empty section still rendered a heading: {heading}"


def test_none_detected_never_reaches_the_page():
    html = render_strategic_report(_bare_report())
    for marker in ("None detected", "Not available", "N/A"):
        assert marker not in html


def test_jump_links_never_point_at_a_section_that_was_suppressed():
    html = render_strategic_report(_bare_report())
    for anchor in re.findall(r'href="#([a-z]+)"', html):
        assert f'id="{anchor}"' in html, \
            f"jump link to #{anchor} has no target"


def test_suppression_does_not_hide_sections_that_have_content():
    """The gate must remove the empty, not the thin — a single real finding is
    still a finding and must survive."""
    report = _bare_report()
    report["blind_spots"] = [{
        "observed_tension": "Hiring for enterprise sales while marketing to "
                            "solo merchants",
        "why_it_may_matter": "The two motions need different pricing",
        "counter_explanation": "Job posts lag strategy by months",
        "decision_affected": "which segment Q4 pricing targets"}]
    report["questions"] = [{
        "question": "Which segment does the new pricing tier target?",
        "why_it_matters": "It decides where the sales motion goes",
        "decision_affected": "Q4 pricing"}]
    html = render_strategic_report(report)
    assert ">Possible blind spots<" in html
    assert ">Questions for leadership<" in html
    assert "Hiring for enterprise sales" in html


def test_limitations_are_consolidated_into_one_section():
    report = _bare_report()
    report["evidence_gaps"] = ["No pricing evidence", "No pricing evidence."]
    report["quality_findings"] = [{"message": "No independent corroboration"}]
    html = render_strategic_report(report)
    assert html.count("What this analysis cannot tell you") == 1
    # The summary preview and the detailed section are progressive disclosure,
    # not duplication — but neither may list the same caveat twice.
    limitations_block = html.split("What this analysis cannot tell you")[1]
    assert limitations_block.count("No pricing evidence") == 1
    summary_block = html.split("Major uncertainties")[1].split("</div>")[0]
    assert summary_block.count("No pricing evidence") == 1
