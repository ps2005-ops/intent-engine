"""The headline strategic decision must come from the company, not a default.

MEASURED LIVE on 56921bce. Synopsys (EDA software), Emerson Electric
(industrial automation) and Lowe's Companies (home-improvement retail) each
received the byte-identical headline decision:

    "Whether a supply commitment should be treated as fixed or renegotiable."

That is `implications[0]` of the `capacity_ahead_of_demand` scaffold, whose
own `excluded_model_classes` names SUBSCRIPTION_SOFTWARE and SCALE_RETAIL.
The exclusion could not fire, because the gate was only ever told UNKNOWN.

THE SEAM: `_registrant_for` read `meta["cik"]`, which is populated ONLY when
a filer is typed with no website. Every domain-entry run -- the ordinary case
-- carried "", so no registrant was fetched, `profile_for` answered UNKNOWN,
and UNKNOWN takes the whole library.
"""
from __future__ import annotations

import inspect
import pathlib
import tempfile

import pytest

from intent_engine.company_ingestion.service import CompanyIngestionService
from intent_engine.executive.company_profile import profile_for
from intent_engine.strategic_intelligence.patterns import (
    PATTERN_LIBRARY, patterns_for,
)

CAPACITY = "capacity_ahead_of_demand"

#: (name, domain, SEC industry code, expected class, may the capacity
#: scaffold legitimately apply?)
COMPANIES = [
    ("Synopsys Inc", "synopsys.com", "7372", "SUBSCRIPTION_SOFTWARE", False),
    ("Emerson Electric Co", "emerson.com", "3823",
     "DESIGN_AND_MANUFACTURE", True),
    ("Lowes Companies Inc", "lowes.com", "5211", "SCALE_RETAIL", False),
    ("BlackRock, Inc.", "blackrock.com", "6282",
     "BALANCE_SHEET_OR_NETWORK", False),
]


def _class_for(name, domain, sic):
    return profile_for(name=name, domain=domain,
                       registrant={"sic": sic}).business_model_class


# --- the gate itself --------------------------------------------------------

def test_the_regulators_industry_code_classifies_an_unseen_company():
    """None of these are in the curated manifest; the SIC is what resolves
    them, and without it every one answers UNKNOWN."""
    for name, domain, sic, expected, _ok in COMPANIES:
        assert profile_for(name=name, domain=domain).business_model_class \
            == "UNKNOWN", f"{name} was expected to be outside the manifest"
        assert _class_for(name, domain, sic) == expected, name


def test_an_unclassified_company_takes_the_whole_library():
    """This is WHY the seam mattered: UNKNOWN is not a small failure, it
    disables the gate entirely."""
    assert len(patterns_for("UNKNOWN")) == len(PATTERN_LIBRARY)
    assert any(p.pattern_id == CAPACITY for p in patterns_for("UNKNOWN"))


def test_the_capacity_thesis_is_refused_where_it_does_not_belong():
    """NEGATIVE CONTROL. Software, retail and an asset manager must not be
    offered a semiconductor-style capacity commitment."""
    for name, domain, sic, _expected, may_apply in COMPANIES:
        got = patterns_for(_class_for(name, domain, sic))
        has = any(p.pattern_id == CAPACITY for p in got)
        assert has == may_apply, (
            f"{name}: capacity scaffold present={has}, expected={may_apply}")


def test_two_unrelated_businesses_do_not_receive_the_same_library():
    """Different mechanisms must produce different candidate sets."""
    software = {p.pattern_id for p in patterns_for(
        _class_for("Synopsys Inc", "synopsys.com", "7372"))}
    industrial = {p.pattern_id for p in patterns_for(
        _class_for("Emerson Electric Co", "emerson.com", "3823"))}
    assert software != industrial, (
        "an EDA vendor and an industrial manufacturer were offered an "
        "identical set of strategic readings")


def test_the_same_mechanism_may_still_reach_the_same_thesis():
    """POSITIVE CONTROL. The rule is SAME THESIS REQUIRES SAME MECHANISM --
    not that every company must differ. Two capital-intensive manufacturers
    are allowed the same reading."""
    a = {p.pattern_id for p in patterns_for("DESIGN_AND_MANUFACTURE")}
    b = {p.pattern_id for p in patterns_for("DESIGN_AND_MANUFACTURE")}
    assert a == b and CAPACITY in a


# --- the call site, which is where the repair actually lives ---------------

def test_the_registrant_lookup_resolves_the_subject_not_the_typed_cik():
    """`meta["cik"]` is empty for every run started from a website.

    `sufficiency.py` documents this same mistake being repaired in its own
    guard; the repair had not reached the pattern gate, so it is pinned at
    the call site rather than trusted to a comment.
    """
    from intent_engine.company_ingestion.service import CompanyIngestionService
    src = inspect.getsource(CompanyIngestionService._registrant_for)
    assert "self.subject_cik(meta)" in src, (
        "the registrant is resolved from meta['cik'], which is empty on "
        "every domain-entry run, so the pattern gate is never told who the "
        "company is")
    classification = inspect.getsource(
        CompanyIngestionService.classification_inputs)
    assert "self.subject_cik(meta)" in classification, (
        "the subject's own filing text is selected by a CIK the run does "
        "not carry")


def test_the_gate_is_consulted_by_the_production_composer():
    """A gate with no caller is the defect this repair exists to remove."""
    from intent_engine.company_ingestion.service import CompanyIngestionService
    src = inspect.getsource(CompanyIngestionService._strategic_report)
    assert "_patterns_for_company(" in src
    marker = src.index("_patterns_for_company(")
    after = src[marker:marker + 400]
    assert "registrant=" in after and "evidence_text=" in after, (
        "the composer calls the gate without the two inputs that classify a "
        "company outside the curated manifest")


# --- THE SIBLING: the same empty CIK, one producer upstream ----------------
#
# `_registrant_for` was not the only place the run failed to say who it was
# about. `_strategic_report` decides DOCUMENT OWNERSHIP from the subject's
# CIK, and read it off `meta` too -- so on every domain-entry run
# `subject_documents` was handed "" and skipped its `/data/<cik>/` filter
# entirely. Another registrant's 10-K could then supply the signals that
# qualify a pattern, and a pattern qualifies at a threshold of two.


def test_a_third_partys_filing_cannot_describe_the_subject():
    """WHY THE EMPTY CIK MATTERED, stated as behaviour rather than as a
    comment. With a subject, a foreign filer's document is refused; without
    one, it is kept -- which is what every website-started run did."""
    from intent_engine.strategic_intelligence.observations import (
        subject_documents,
    )
    own = {"final_url": "https://www.sec.gov/Archives/edgar/data/19617/a.htm",
           "source_class": "investor_material"}
    theirs = {"final_url":
              "https://www.sec.gov/Archives/edgar/data/72971/b.htm",
              "source_class": "investor_material"}
    kept = subject_documents([own, theirs], subject_cik="19617")
    assert kept == [own], "another registrant's filing described the subject"
    assert subject_documents([own, theirs], subject_cik="") == [own, theirs], (
        "the documented degradation changed; if an unknown subject now "
        "filters, this test is asserting the wrong thing")


def test_document_ownership_resolves_the_subject_not_the_typed_cik():
    """THE CALL SITE, READ FROM THE RUNNING CODE. A comment saying the
    subject decides ownership is not the same as the subject being asked."""
    from intent_engine.company_ingestion.service import CompanyIngestionService
    src = inspect.getsource(CompanyIngestionService._strategic_report)
    head = src[:src.index("if trace is not None")]
    assert "self.subject_cik(" in head, (
        "the ownership gate resolves the subject from meta['cik'], which is "
        "empty on every run started from a website")
    assert 'get("cik")' not in head, (
        "meta['cik'] is still read where the subject is required")


def test_the_subject_lookup_is_resolved_once_per_name():
    """The fallback reads the SEC's whole ticker table. This repair adds
    callers to it, so the answer is kept -- and a resolver called twice for
    one name is a latency regression the cohort would pay ten times over."""
    calls = []

    def transport(url, timeout, max_bytes=None):
        calls.append(url)
        body = b'{"0": {"cik_str": 320193, "ticker": "AAPL", ' \
               b'"title": "Apple Inc."}}'
        return (200, {"Content-Type": "application/json"}, body, False)

    with tempfile.TemporaryDirectory() as tmp:
        ci = CompanyIngestionService(pathlib.Path(tmp) / "ci.jsonl",
                                     resolver=False, transport=transport)
        meta = {"cik": "", "company_name": "Apple Inc."}
        first = ci.subject_cik(meta)
        second = ci.subject_cik(meta)
        assert first == second == "320193"
        assert len(calls) == 1, f"the ticker table was read {len(calls)} times"


def test_a_failed_lookup_is_not_remembered_as_an_answer():
    """SEC answers 429 to this product under load. Caching that as "this
    company has no CIK" would pin the whole run at UNKNOWN -- which is the
    outcome the repair exists to remove."""
    state = {"n": 0}

    def transport(url, timeout, max_bytes=None):
        state["n"] += 1
        if state["n"] == 1:
            raise TimeoutError("SEC said not now")
        return (200, {}, b'{"0": {"cik_str": 320193, "ticker": "AAPL", '
                          b'"title": "Apple Inc."}}', False)

    with tempfile.TemporaryDirectory() as tmp:
        ci = CompanyIngestionService(pathlib.Path(tmp) / "ci.jsonl",
                                     resolver=False, transport=transport)
        meta = {"cik": "", "company_name": "Apple Inc."}
        assert ci.subject_cik(meta) == ""
        assert ci.subject_cik(meta) == "320193", (
            "a transient refusal was cached as a permanent answer")


# --- THE AUDIT TRAIL: four defects wear one symptom -----------------------


def _composed_audit(tmp, *, cik="19617"):
    text = ("Our platform helps merchants sell online. Demand capture runs "
            "through the marketplace and the shop app, which set how "
            "merchants reach shoppers and checkout. We are committing "
            "capital to capacity ahead of the demand for it.")
    doc = {"final_url":
           "https://www.sec.gov/Archives/edgar/data/19617/jpm.htm",
           "source_class": "investor_material", "source_id": "jpm",
           "title": "SEC 10-K", "text": text, "text_content": text,
           "content_hash": "jpm", "retrieved_at": "2026-02-24"}
    ci = CompanyIngestionService(pathlib.Path(tmp) / "ci.jsonl",
                                 resolver=False)
    run = ci.create_run(company_name="JPMorgan Chase & Co.", website="",
                        user_id="u", as_of="2026-08-20T00:00:00+00:00",
                        cik=cik)
    payload = ci._strategic_report("JPMorgan Chase & Co.", [doc], [],
                                   run_id=run["run_id"], deep=False)
    return payload.get("pattern_audit")


def test_a_run_records_which_classification_gated_its_reading():
    """A thesis whose classification was never recorded cannot be told apart
    from one whose gate was wrong."""
    with tempfile.TemporaryDirectory() as tmp:
        audit = _composed_audit(tmp)
    assert audit, "the run published a reading and no account of it"
    for key in ("business_model", "eligible_pattern_ids",
                "excluded_pattern_ids", "chosen_pattern", "chosen_thesis",
                "company_specific_mechanism", "supporting_observation_ids",
                "alternative", "reason_chosen", "fired_pattern_ids"):
        assert key in audit, f"the audit cannot answer '{key}'"
    assert audit["business_model"], "an empty classification is not UNKNOWN"


def test_the_audit_accounts_for_every_pattern_in_the_library():
    """Eligible plus excluded IS the library. A gate that quietly drops a
    pattern from both sides is invisible in a count of what fired."""
    with tempfile.TemporaryDirectory() as tmp:
        audit = _composed_audit(tmp)
    every = {p.pattern_id for p in PATTERN_LIBRARY}
    assert set(audit["eligible_pattern_ids"]) | \
        set(audit["excluded_pattern_ids"]) == every
    assert not (set(audit["eligible_pattern_ids"])
                & set(audit["excluded_pattern_ids"]))
    assert audit["library_size"] == len(PATTERN_LIBRARY)


def test_the_chosen_reading_was_one_the_gate_admitted():
    """RANKING vs ELIGIBILITY. If the winner is not in the eligible set, the
    defect is downstream of the gate and the gate is not the thing to fix."""
    with tempfile.TemporaryDirectory() as tmp:
        audit = _composed_audit(tmp)
    if audit["chosen_pattern"]:
        assert audit["chosen_pattern"] in audit["eligible_pattern_ids"]
        assert audit["reason_chosen"]
    for fired in audit["fired_pattern_ids"]:
        assert fired in audit["eligible_pattern_ids"], (
            f"{fired} fired although the gate excluded it")


def test_the_diagnostic_says_when_nothing_was_recorded():
    """A silent empty object reads as "the gate admitted everything". A run
    composed before this existed must say which it is."""
    from intent_engine.webapp.app import WebApp

    class _Run:
        def _strategic_report_for(self, run_id):
            return {}

    got = WebApp._thesis_diagnostics(_Run(), "r1")
    assert "error" in got and "no pattern audit" in got["error"]


def test_the_diagnostic_carries_the_recorded_audit_unchanged():
    from intent_engine.webapp.app import WebApp

    class _Run:
        def _strategic_report_for(self, run_id):
            return {
                "pattern_audit": {"business_model": "SCALE_RETAIL",
                                  "chosen_pattern": "seller_becomes_supplier"},
                "reasoning_provenance": "verified_analyst",
                "result_state": "READY", "deep_status": "COMPLETE"}

    got = WebApp._thesis_diagnostics(_Run(), "r1")
    assert got["business_model"] == "SCALE_RETAIL"
    assert got["chosen_pattern"] == "seller_becomes_supplier"
    assert got["reasoning_provenance"] == "verified_analyst"
    assert got["deep_status"] == "COMPLETE"


def test_the_telemetry_surface_publishes_it():
    """IMPLEMENTED IS NOT INSTRUMENTED. A producer with no route has
    repeatedly meant "built, green, and never once read in production"."""
    from intent_engine.webapp.app import WebApp
    src = inspect.getsource(WebApp._telemetry_json)
    assert "_thesis_diagnostics(run_id)" in src
    # AND THAT IT READS THE REAL RUN. `_result` recomputes the synthetic demo
    # analysis for an unknown id, so a diagnostic built on it can answer with
    # another company's reading -- and manufacture one to do it.
    diag = inspect.getsource(WebApp._thesis_diagnostics)
    assert "_strategic_report_for(run_id)" in diag
    assert "self._result(" not in diag
