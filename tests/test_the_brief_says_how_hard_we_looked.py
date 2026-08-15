"""A bare zero on the surface a chief executive actually reads.

FOUND BY DRIVING THE DEPLOYED PRODUCT, not by a test. The live Cloudflare
brief rendered:

    Another registrant's filing — none

with no coverage state anywhere on the page: no DISCOVERY_*, no "failed to
find", no "found none". The measured coverage existed and reached only the
provenance drawer, which is not what a chief executive opens first.

`dossier.render_families` states the requirement in its own docstring -- "a
reader who cannot tell 'no competitor said this' from 'no competitor was
asked' cannot judge the analysis at all" -- and the surface did exactly the
thing that docstring forbids. This is the seam defect this codebase keeps
shipping: a correct producer, one consumer wired, and the primary surface
reading a field nobody passed it.
"""
from intent_engine.company_ingestion import relevance as REL
from intent_engine.founder_brief.dossier import evidence_families
from intent_engine.strategic_intelligence.reasoning import (
    build_strategic_report,
)

_NO_COMPETITOR = {"source_class_coverage": {"company_owned": 5}}


def _competitor(report: dict) -> str:
    return [f["consequence"] for f in evidence_families(report)
            if f["key"] == "competitor"][0]


def test_a_zero_without_a_search_is_a_limit_of_our_retrieval():
    """NO PRODUCER. The absence is about us, and must read that way."""
    said = _competitor(_NO_COMPETITOR)
    assert "not evidence that no independent coverage exists" in said
    assert "finding about the company" not in said


def test_an_exhausted_search_may_call_the_zero_a_finding():
    """The stronger sentence, licensed only by a search that read everything
    it considered."""
    said = _competitor(dict(_NO_COMPETITOR, discovery_coverage={
        "coverage": REL.DISCOVERY_EXHAUSTED,
        "candidates_considered": 5, "candidates_fetched": 5}))
    assert "found none that bears on this question" in said
    assert "read 5 in full" in said


def test_a_blocked_channel_never_becomes_a_finding():
    """NEGATIVE CONTROL. A channel we could not reach is the one case most
    likely to be read as good news."""
    said = _competitor(dict(_NO_COMPETITOR, discovery_coverage={
        "coverage": REL.DISCOVERY_BLOCKED}))
    assert "not evidence that no independent coverage exists" in said


def test_stopping_at_the_budget_never_becomes_a_finding():
    said = _competitor(dict(_NO_COMPETITOR, discovery_coverage={
        "coverage": REL.DISCOVERY_PARTIAL,
        "candidates_considered": 20, "candidates_fetched": 12}))
    assert "not evidence that no independent coverage exists" in said
    assert "looked at 20" in said


def test_a_family_that_was_found_says_nothing_about_the_search():
    """The sentence belongs to an ABSENCE. A present family must not carry it."""
    present = evidence_families({
        "source_class_coverage": {"competitor": 3},
        "discovery_coverage": {"coverage": REL.DISCOVERY_EXHAUSTED}})
    assert [f["consequence"] for f in present if f["key"] == "competitor"] == [""]


def test_the_report_carries_the_search_to_the_brief():
    """PRODUCER -> REPORT -> SURFACE. A field the report drops is a field the
    brief will render as a bare zero, which is where this started."""
    report = build_strategic_report(
        company_name="Cloudflare, Inc.", observations=[],
        discovery_coverage={"coverage": REL.DISCOVERY_EXHAUSTED,
                            "candidates_considered": 5,
                            "candidates_fetched": 5})
    assert report.as_dict()["discovery_coverage"]["coverage"] == (
        REL.DISCOVERY_EXHAUSTED)


def test_a_report_built_without_a_search_carries_an_empty_one():
    """NEGATIVE CONTROL for the carry: absent must stay absent, never a
    default state the reasoning layer invented."""
    report = build_strategic_report(company_name="X", observations=[])
    assert report.as_dict()["discovery_coverage"] == {}


# --- D1: a validation error is not a fault on our side ------------------------


def test_a_missing_consent_is_not_reported_as_our_fault():
    """MEASURED LIVE. Submitting the form without ticking consent produced
    "Something went wrong on our side ... This is a fault in the product, not
    in what you entered", which is the opposite of the truth and leaves the
    reader with nothing to do but repeat the mistake."""
    from intent_engine.webapp import failures as F
    assert F.classify("consent is required") == F.INPUT_INCOMPLETE
    title, what_failed, why, next_step, _ = F._COPY[F.INPUT_INCOMPLETE]
    assert "went wrong on our side" not in title.lower()
    assert "fault in the product" not in why.lower()
    assert "tick" in next_step.lower()


def test_an_unrecognised_message_still_defaults_to_our_fault():
    """NEGATIVE CONTROL. The repair is to RECOGNISE one message, never to
    soften the default -- an unrecognised failure is ours until shown
    otherwise, and that default is load-bearing."""
    from intent_engine.webapp import failures as F
    assert F.classify("some unrecognised explosion") == F.INTERNAL_FAILURE
