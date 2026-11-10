"""Six empty evidence families and no reason for any of them.

MEASURED ON THE DEPLOYED PRODUCT. Caterpillar's executive brief listed all six
source families as "— none" and explained none of them. The reason existed and
had been recorded by the run: caterpillar.com answers HTTP 403 to automated
requests. Silence there reads as "this company has published nothing", which
is a claim about the company rather than about our access to it -- the same
error as a bare independent-origin zero, one layer up.

Worse, the consequence sentence for an absent `company_owned` family read
"Everything here is the company describing itself", which describes the
OPPOSITE situation. Every string in `_FAMILIES` renders only when its family
is ABSENT, so that one was wrong from the day it was written and stayed
invisible until a run finally retrieved nothing at all.
"""
from intent_engine.founder_brief.dossier import evidence_families

_EMPTY = {"source_class_coverage": {}}


def _by_key(report, key):
    return [f for f in evidence_families(report) if f["key"] == key][0]


def test_an_absent_family_never_describes_evidence_being_present():
    """The sentence renders on ABSENCE, so it must be true of absence."""
    said = _by_key(_EMPTY, "company_owned")["consequence"]
    assert "Everything here is the company describing itself" not in said
    assert "could not read anything the company publishes" in said


def test_a_site_that_refused_us_is_not_a_company_that_published_nothing():
    """MEASURED LIVE ON CATERPILLAR."""
    said = _by_key(dict(_EMPTY, retrieval_failures={"http_status": 6}),
                   "company_owned")["consequence"]
    assert "not an absence of publishing" in said
    assert "refused automated access" in said


def test_a_javascript_only_site_says_so_specifically():
    said = _by_key(dict(_EMPTY, retrieval_failures={"javascript_only": 3}),
                   "company_owned")["consequence"]
    assert "only to a full browser" in said


def test_no_recorded_failure_never_claims_we_were_blocked():
    """NEGATIVE CONTROL. When nothing refused us, the absence really is an
    absence, and inventing a blocker would excuse a genuine retrieval gap."""
    said = _by_key(_EMPTY, "company_owned")["consequence"]
    assert "refused automated access" not in said
    assert "full browser" not in said


def test_a_blocked_site_never_explains_a_third_party_family():
    """A competitor's filing is not missing because the SUBJECT's website said
    no. Attaching one reason to every gap is how a page stops being read."""
    families = evidence_families(
        dict(_EMPTY, retrieval_failures={"http_status": 6}))
    for key in ("competitor", "independent_reporting", "customer_voice"):
        said = [f for f in families if f["key"] == key][0]["consequence"]
        assert "refused automated access" not in said


def test_a_present_family_carries_no_consequence_at_all():
    families = evidence_families({"source_class_coverage": {"company_owned": 5},
                                  "retrieval_failures": {"http_status": 6}})
    assert [f for f in families
            if f["key"] == "company_owned"][0]["consequence"] == ""


def test_the_run_carries_its_failures_to_the_report():
    """PRODUCER -> REPORT -> SURFACE, the seam this codebase keeps dropping."""
    from intent_engine.strategic_intelligence.reasoning import (
        build_strategic_report,
    )
    report = build_strategic_report(
        company_name="Caterpillar Inc.", observations=[],
        retrieval_failures={"http_status": 6})
    assert report.as_dict()["retrieval_failures"] == {"http_status": 6}


def test_a_report_with_no_failures_carries_an_empty_summary():
    """NEGATIVE CONTROL for the carry."""
    from intent_engine.strategic_intelligence.reasoning import (
        build_strategic_report,
    )
    report = build_strategic_report(company_name="X", observations=[])
    assert report.as_dict()["retrieval_failures"] == {}


# --- D6: the subject is normalised once, at the producer ----------------------


def test_no_decision_sentence_can_carry_an_empty_subject():
    """MEASURED LIVE. Caterpillar's brief opened "what has published is not
    enough to read a strategy from" -- a hole where the company belongs, in
    the product's single most-read line.

    Fixed at `compose_decision`, which builds the one decision object the
    X-Ray, brief, deck and Q&A all render, so no surface can print the hole
    from the same input.
    """
    from intent_engine.strategic_intelligence.decision import compose_decision
    for blank in ("", "   ", None):
        decision = compose_decision(blank, None, ())
        text = " ".join(str(v) for v in vars(decision).values()
                        if isinstance(v, str))
        assert "What  has" not in text
        assert " has published" not in text or "this company has published" in text


def test_a_real_subject_is_never_replaced_by_the_placeholder():
    """NEGATIVE CONTROL: the fallback must not swallow a name that arrived."""
    from intent_engine.strategic_intelligence.decision import compose_decision
    decision = compose_decision("Caterpillar Inc.", None, ())
    assert "Caterpillar Inc." in decision.unsafe_because
    assert "this company" not in decision.unsafe_because
