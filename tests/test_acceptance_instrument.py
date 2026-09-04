"""The instrument that scored Meta green, and the controls that prove it now.

An acceptance instrument is only worth what its controls are worth. The
previous one searched `/full` for the literal string "Limited analysis",
so the page that actually rendered --

    "Analysis could not be completed"

-- was scored a PASS on two deployed builds. Every test below therefore comes
in pairs: a capture that MUST fail and a capture that MUST pass, so a rule
that has stopped measuring anything shows up as a control that no longer
fails rather than as a wave of good news.
"""
import json

import pytest

from intent_engine.pre100 import verdict as V
from intent_engine.webapp import outcome as O

GOOD = ("Meta Platforms, Inc. resells attention to advertisers. Revenue is "
        "an auction price per impression, multiplied by impressions served. "
        "The engine is engagement, and the question worth arguing about is "
        "how much of that attention to convert into inventory, and where. "
        "Margin follows infrastructure intensity and headcount, and capital "
        "follows the data-centre build. ") * 12

FAILURE_PAGE = ("Analysis could not be completed. This analysis did not "
                "produce a report: not enough of what it needed could be "
                "retrieved. ")


def _write(tmp_path, *, name="Meta Platforms, Inc.", outcome=O.FULL_ANALYSIS,
           bodies=None, qa=None, manifest_extra=None):
    d = tmp_path / "meta_platforms_inc"
    d.mkdir(exist_ok=True)
    bodies = dict(bodies or {})
    routes = {}
    for route in V.REQUIRED_ROUTES:
        text = bodies.get(route, GOOD)
        (d / f"{route}.txt").write_text(text, "utf-8")
        (d / f"{route}.html").write_text(f"<html>{text}</html>", "utf-8")
        routes[route] = {"status": 200, "chars": len(text),
                         "outcome": outcome}
    answers = qa if qa is not None else [
        {"question": f"q{i}", "answer": f"Answer {i}. " + GOOD[:400 + i * 30],
         "status": 200} for i in range(V.QUESTIONS)]
    (d / "qa.json").write_text(json.dumps(answers), "utf-8")
    manifest = {"company": name, "deployed_sha": "test123",
                "status": "READY", "cik": "0001326801",
                # A FINISHED walk. Without this every fixture reads as a
                # capture still being written, and every rule below is
                # suppressed -- which is how the in-flight guard would have
                # quietly disabled the whole instrument.
                "qa_complete": True,
                "entry_domain": "meta.com", "seconds": 120,
                "routes": routes, "progress": [], "outcome": outcome,
                "outcome_by_route": {r: outcome for r in routes},
                "outcome_disagreement": []}
    manifest.update(manifest_extra or {})
    (d / "manifest.json").write_text(json.dumps(manifest), "utf-8")
    return d


# --- the negative control: a genuinely good capture must pass -------------

def test_a_complete_analysis_passes(tmp_path):
    """THE CONTROL THAT MATTERS MOST. Every rule below is a rule that can
    fail everything; this is what proves none of them does."""
    result = V.verdict(_write(tmp_path))
    assert result["passed"], result["failures"]
    assert result["outcome"] == O.FULL_ANALYSIS


# --- the exact capture that was scored green ------------------------------

def test_the_meta_failure_page_is_not_a_pass(tmp_path):
    """755 characters of "could not be completed" on the one route named
    full analysis, over six surfaces that rendered real analysis."""
    d = _write(tmp_path, bodies={"full": FAILURE_PAGE})
    result = V.verdict(d)
    assert not result["passed"]
    codes = {f["code"] for f in result["failures"]}
    assert "FAILURE_PAGE" in codes, codes
    assert "THIN_ROUTE" in codes, codes


def test_the_old_rule_would_have_passed_it(tmp_path):
    """THE INSTRUMENT DEFECT, PINNED. Kept as an executable statement of what
    was wrong, so "we search for the right string now" cannot quietly become
    "we search for one string again"."""
    d = _write(tmp_path, bodies={"full": FAILURE_PAGE})
    old_rule_says_limited = "Limited analysis" in (d / "full.txt").read_text()
    assert old_rule_says_limited is False
    assert not V.verdict(d)["passed"]


def test_one_run_may_not_state_two_outcomes(tmp_path):
    """Meta's run, as a field: six surfaces said one thing and /full said
    another, and nothing on disk recorded the disagreement."""
    d = _write(tmp_path, manifest_extra={
        "outcome_disagreement": [O.FULL_ANALYSIS,
                                 O.RETRIEVAL_TEMPORARILY_UNAVAILABLE]})
    codes = {f["code"] for f in V.verdict(d)["failures"]}
    assert "OUTCOME_DISAGREEMENT" in codes


def test_a_stated_success_over_a_failure_page_is_a_defect(tmp_path):
    """The producer can be wrong too. If the service says FULL_ANALYSIS while
    a customer surface apologises, that contradiction is the finding -- this
    is the check that can catch the NEXT Meta without knowing its sentence."""
    d = _write(tmp_path, outcome=O.FULL_ANALYSIS,
               bodies={"story": FAILURE_PAGE + GOOD})
    codes = {f["code"] for f in V.verdict(d)["failures"]}
    assert "STATED_SUCCESS_OVER_FAILURE_PAGE" in codes


# --- outcome classes ------------------------------------------------------

def test_scarcity_is_a_failure_for_a_registrant_with_a_domain(tmp_path):
    """§6. A bounded page for an information-rich public company is not
    honest degradation; it is a false statement about the company."""
    d = _write(tmp_path, outcome=O.TRUE_EVIDENCE_SCARCITY)
    codes = {f["code"] for f in V.verdict(d)["failures"]}
    assert "FALSE_SCARCITY" in codes


def test_scarcity_is_allowed_for_a_company_with_neither_cik_nor_domain(tmp_path):
    """...and the same rule must NOT fail a genuinely sparse private company,
    or "make Limited rare" becomes "call every Limited a bug"."""
    d = _write(tmp_path, name="Harbourline Fabrication LLC",
               outcome=O.TRUE_EVIDENCE_SCARCITY,
               manifest_extra={"cik": "", "entry_domain": ""})
    codes = {f["code"] for f in V.verdict(d)["failures"]}
    assert "FALSE_SCARCITY" not in codes, codes


def test_an_operational_failure_is_never_a_pass(tmp_path):
    d = _write(tmp_path, outcome=O.RETRIEVAL_TEMPORARILY_UNAVAILABLE)
    codes = {f["code"] for f in V.verdict(d)["failures"]}
    assert "OPERATIONAL_FAILURE" in codes


def test_a_run_that_never_settled_is_never_a_pass(tmp_path):
    d = _write(tmp_path, outcome=O.WORKING)
    codes = {f["code"] for f in V.verdict(d)["failures"]}
    assert "NEVER_SETTLED" in codes


# --- the other customer-visible defects -----------------------------------

def test_a_lost_run_is_a_failure(tmp_path):
    d = _write(tmp_path, manifest_extra={"run_lost_after_routes": True})
    assert "LOST_RUN" in {f["code"] for f in V.verdict(d)["failures"]}


def test_a_redirect_loop_is_a_failure(tmp_path):
    d = _write(tmp_path, manifest_extra={
        "progress": [{"t": 36.0, "text": "", "status": 303}]})
    assert "REDIRECT_LOOP" in {f["code"] for f in V.verdict(d)["failures"]}


def test_a_progress_page_with_text_is_not_a_loop(tmp_path):
    """The negative control for the loop rule."""
    d = _write(tmp_path, manifest_extra={
        "progress": [{"t": 4.0, "text": "Reading evidence", "status": 200}]})
    assert "REDIRECT_LOOP" not in {f["code"] for f in V.verdict(d)["failures"]}


def test_a_raw_dataclass_in_an_answer_is_a_failure(tmp_path):
    qa = [{"question": f"q{i}", "answer": GOOD[:500] + str(i), "status": 200}
          for i in range(V.QUESTIONS)]
    qa[3]["answer"] = ("MarketBelief(belief_id='mb_f3a52cac10', "
                       "proposition='that the trough is cyclical')")
    d = _write(tmp_path, qa=qa)
    assert "RAW_REPR_IN_QA" in {f["code"] for f in V.verdict(d)["failures"]}


def test_ordinary_prose_with_brackets_is_not_a_repr(tmp_path):
    """The negative control. A pattern that eats "Revenue (net) rose 12%"
    reports leaks in every company and stops being evidence of anything."""
    assert V.REPR.search("MarketBelief(belief_id='x'")
    assert V.REPR.search("link(frm='a', to='b')")
    assert not V.REPR.search("Revenue (net) rose 12% year over year.")
    assert not V.REPR.search("hold this decision (for now) and test it")


def test_nine_answers_is_not_ten(tmp_path):
    qa = [{"question": f"q{i}", "answer": GOOD[:500] + str(i), "status": 200}
          for i in range(9)]
    d = _write(tmp_path, qa=qa)
    assert "QA_INCOMPLETE" in {f["code"] for f in V.verdict(d)["failures"]}


def test_the_wrong_company_is_a_failure(tmp_path):
    d = _write(tmp_path, name="Oklo Inc.")
    assert "WRONG_IDENTITY" in {f["code"] for f in V.verdict(d)["failures"]}


def test_http_200_on_an_empty_page_is_not_a_pass(tmp_path):
    """"A route existing is not success." Every route returns 200 here."""
    d = _write(tmp_path, bodies={r: "Next  Back" for r in V.REQUIRED_ROUTES})
    result = V.verdict(d)
    assert not result["passed"]
    assert sum(1 for f in result["failures"] if f["code"] == "THIN_ROUTE") \
        == len(V.REQUIRED_ROUTES)


def test_a_batch_tallies_outcomes_and_failure_codes(tmp_path):
    _write(tmp_path)
    batch = V.verdict_batch(tmp_path)
    assert batch["total"] == 1 and batch["passed"] == 1
    assert batch["by_outcome"][O.FULL_ANALYSIS] == 1


def test_scarcity_is_caught_for_a_registrant_the_capture_forgot_to_record(
        tmp_path):
    """THE SECOND INSTRUMENT DEFECT, and it is the same shape as the first.

    `expected_full` originally asked the capture manifest for a CIK. The
    harness never writes one, and Meta has no domain on record either -- so
    the rule written specifically to catch Meta answered False FOR META, and
    the live capture on 5d43053 would have been scored a PASS while the
    customer read "Limited analysis of Meta Platforms, Inc.".

    A rule that cannot see the case it exists for is not a weaker rule. It is
    not a rule.
    """
    d = _write(tmp_path, outcome=O.TRUE_EVIDENCE_SCARCITY,
               manifest_extra={"cik": "", "entry_domain": ""})
    assert V.expected_full({"company": "Meta Platforms, Inc."}) is True
    codes = {f["code"] for f in V.verdict(d)["failures"]}
    assert "FALSE_SCARCITY" in codes, codes


def test_a_company_outside_the_universe_is_still_allowed_to_be_sparse(
        tmp_path):
    """The negative control for the lookup: an unknown private company gets
    no CIK from anywhere, and a bounded page for it is honest."""
    d = _write(tmp_path, name="Some Private Holdings LLC",
               outcome=O.TRUE_EVIDENCE_SCARCITY,
               manifest_extra={"cik": "", "entry_domain": ""})
    assert V.expected_full({"company": "Some Private Holdings LLC"}) is False
    codes = {f["code"] for f in V.verdict(d)["failures"]}
    assert "FALSE_SCARCITY" not in codes, codes


def test_a_capture_still_being_written_is_not_scored(tmp_path):
    """THE IN-FLIGHT GUARD, and the control that keeps it honest.

    `qa.json` is flushed after every answer, so a company read mid-walk shows
    four answers and seven distinct ones -- an incomplete Q&A and a collapse,
    both artefacts of reading too early. Microsoft was scored exactly that way
    during Wave 1.

    But "fewer than ten answers means still capturing" would make
    QA_INCOMPLETE a rule that can never fire, so the test is the manifest's
    own completion flag, with a recency fallback for captures written before
    that flag existed.
    """
    qa = [{"question": f"q{i}", "answer": GOOD[:500] + str(i), "status": 200}
          for i in range(4)]
    d = _write(tmp_path, qa=qa, manifest_extra={"qa_complete": False})
    result = V.verdict(d)
    assert result["capturing"] is True
    assert result["passed"] is None
    assert result["failures"] == []


def test_a_finished_capture_with_four_answers_is_still_a_failure(tmp_path):
    """...and the negative control: completion is what suppresses the rule,
    not the answer count."""
    qa = [{"question": f"q{i}", "answer": GOOD[:500] + str(i), "status": 200}
          for i in range(4)]
    d = _write(tmp_path, qa=qa)
    result = V.verdict(d)
    assert not result.get("capturing")
    assert "QA_INCOMPLETE" in {f["code"] for f in result["failures"]}


def test_two_successful_outcomes_are_one_story_told_twice(tmp_path):
    """Microsoft settled from refreshing to complete part-way through the
    walk. Both states say a readable analysis exists; flagging that would
    report the intended behaviour as a defect on every company that finishes
    mid-capture."""
    d = _write(tmp_path, manifest_extra={"outcome_disagreement": [
        O.FULL_ANALYSIS, O.FULL_ANALYSIS_REFRESHING]})
    codes = {f["code"] for f in V.verdict(d)["failures"]}
    assert "OUTCOME_DISAGREEMENT" not in codes, codes


def test_a_success_beside_a_failure_is_two_stories(tmp_path):
    """...and the boundary the rule actually guards."""
    d = _write(tmp_path, manifest_extra={"outcome_disagreement": [
        O.FULL_ANALYSIS, O.RETRIEVAL_TEMPORARILY_UNAVAILABLE]})
    codes = {f["code"] for f in V.verdict(d)["failures"]}
    assert "OUTCOME_DISAGREEMENT" in codes
