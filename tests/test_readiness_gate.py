"""The pre-synthesis readiness gate.

The failure this prevents: synthesis given one filing still produces a thesis,
hypotheses and leadership questions, laid out exactly like a report built on
twenty sources. The reader cannot tell them apart. So the decision to
synthesize is made before synthesis, on the evidence alone.
"""
import pytest

from intent_engine.company_ingestion.readiness import (
    IDENTITY_UNRESOLVED, INSUFFICIENT_EVIDENCE, MAX_DISCOVERY_ATTEMPTS,
    MIN_SLIDE_UNITS, READY_FOR_FULL_REPORT, READY_FOR_LIMITED_REPORT,
    RETRYABLE_EVIDENCE_GAP, assess_readiness, explain, is_dated, slide_units,
)

RESOLVED_IDENTITY = {"entity_resolved": True,
                     "canonical_legal_name": "Sony Group Corporation"}
UNREGISTERED_IDENTITY = {"entity_resolved": False, "status": "UNKNOWN",
                         "fallback_subject": "Brightlake",
                         "fallback_domain": "brightlake.example"}


def _doc(source_type="product", source_class="company_owned",
         text=None, status="OK"):
    # Distinct text per source type. The default used to be one sentence
    # shared by every document, which made "three sources" in a test mean
    # three copies of the same sentence — and the gate now counts that as the
    # one piece of evidence it is. The tests meant three DIFFERENT sources.
    if text is None:
        text = (f"Brightlake's {source_type} page: Brightlake sells a "
                f"warehouse routing platform to mid-market distributors, "
                f"updated in March 2026.")
    return {"source_type": source_type, "source_class": source_class,
            "text_content": text, "retrieval_status": status,
            "title": f"{source_type} page"}


def _full_evidence():
    """Six usable sources spanning identity, product, customers, investor and
    strategy — what a real full report rests on."""
    return [
        _doc("homepage", text="Brightlake is a logistics software company "
                              "founded in 2019 and based in Toronto."),
        _doc("product", text="The Brightlake routing platform plans "
                             "multi-stop delivery routes. Released May 2026."),
        _doc("customers", text="Northwind Freight cut planning time using "
                               "Brightlake in 2026."),
        _doc("about", "investor_material",
             text="Fiscal year 2026 revenue grew on subscription expansion."),
        _doc("blog", "executive_statement",
             text="In June 2026 our CEO set out the automation roadmap."),
        _doc("pricing", text="Plans start at $400 per month, updated 2026."),
    ]


# --- the happy path ----------------------------------------------------------
def test_broad_evidence_is_ready_for_a_full_report():
    a = assess_readiness(documents=_full_evidence(),
                         identity=RESOLVED_IDENTITY)
    assert a["state"] == READY_FOR_FULL_REPORT
    assert a["may_synthesize"] and a["full_report_allowed"]
    assert a["failed_checks"] == []
    assert len(a["slide_units"]) >= MIN_SLIDE_UNITS


def test_an_unregistered_company_is_not_treated_as_unidentified():
    # The registry is small on purpose; most real companies are not in it.
    a = assess_readiness(documents=_full_evidence(),
                         identity=UNREGISTERED_IDENTITY)
    assert a["state"] == READY_FOR_FULL_REPORT


# --- the incident ------------------------------------------------------------
def test_a_single_filing_may_not_become_a_full_report():
    """Sony, exactly as it failed: one SEC document and nothing else."""
    a = assess_readiness(
        documents=[_doc("about", "investor_material",
                        text="Report of foreign private issuer for the month "
                             "of May 2026.")],
        identity=RESOLVED_IDENTITY)
    assert a["state"] != READY_FOR_FULL_REPORT
    assert not a["full_report_allowed"]
    assert "source_count" in a["failed_checks"]
    assert "evidence_families" in a["failed_checks"]
    assert "market_source" in a["failed_checks"]


def test_a_pile_of_one_family_is_not_coverage():
    # Six filings satisfy "six documents retrieved" and tell a reader nothing
    # about what the company does or who buys from it.
    documents = [_doc("about", "investor_material",
                      text=f"Report of foreign private issuer number {i} "
                           f"furnished for the month of May 2026 pursuant to "
                           f"the rules of the Exchange Act.")
                 for i in range(6)]
    a = assess_readiness(documents=documents, identity=RESOLVED_IDENTITY)
    assert a["document_count"] == 6, "six real documents, one single family"
    assert a["state"] != READY_FOR_FULL_REPORT
    assert "no_dominant_family" in a["failed_checks"]
    assert a["dominant_share"] > 0.70


def test_no_identity_means_no_analysis_at_all():
    a = assess_readiness(documents=_full_evidence(), identity=None)
    assert a["state"] == IDENTITY_UNRESOLVED
    assert not a["may_synthesize"]


def test_identity_failure_outranks_every_other_signal():
    # Even perfect evidence cannot rescue a report about nobody in particular.
    a = assess_readiness(documents=_full_evidence(),
                         identity={"entity_resolved": False,
                                   "status": "UNKNOWN"})
    assert a["state"] == IDENTITY_UNRESOLVED


# --- the mandatory roles -----------------------------------------------------
def test_company_owned_pages_alone_cannot_pass():
    documents = [_doc("homepage"), _doc("product"), _doc("about"),
                 _doc("product"), _doc("homepage")]
    a = assess_readiness(documents=documents, identity=RESOLVED_IDENTITY)
    assert a["state"] != READY_FOR_FULL_REPORT
    assert "market_source" in a["failed_checks"]
    # Five undifferentiated company pages read as a private company, and a
    # private company has no investor family to find — so the missing
    # direction source is reported without being counted against it. What the
    # gate must not lose is that it is still missing, and that company-owned
    # pages alone still cannot carry a full report.
    assert "direction_source" in a["unmet_checks"]
    assert a["research_mode"] == "private_company"


def test_a_public_company_is_still_required_to_show_its_direction():
    """Modes may relax what is EXPECTED, never what is true. A filer that
    publishes no strategy or investor material fails the same check it always
    did — otherwise adding modes would have quietly weakened the gate for the
    companies it was already right about."""
    documents = [_doc("homepage", text="Northwind Freight files a Form 10-K "
                                       "with the Securities and Exchange "
                                       "Commission each year."),
                 _doc("product"), _doc("about"), _doc("product"),
                 _doc("homepage")]
    a = assess_readiness(documents=documents, identity=RESOLVED_IDENTITY)
    assert a["research_mode"] == "public_company"
    assert "direction_source" in a["failed_checks"]


def test_undated_evidence_cannot_support_recent_change_claims():
    documents = [
        _doc("homepage", text="Brightlake builds logistics software."),
        _doc("product", text="The routing platform plans delivery routes."),
        _doc("customers", text="Northwind Freight uses the platform."),
        _doc("about", "investor_material",
             text="Subscription revenue grew strongly."),
        _doc("blog", "executive_statement",
             text="Our chief executive set out an automation roadmap."),
    ]
    a = assess_readiness(documents=documents, identity=RESOLVED_IDENTITY)
    assert "dated_evidence" in a["failed_checks"]
    assert "what_changed" not in a["slide_units"]


def test_failed_and_empty_retrievals_are_not_evidence():
    documents = _full_evidence() + [
        _doc(status="FAILED", text="403 Forbidden"),
        _doc(text="   "),
    ]
    a = assess_readiness(documents=documents, identity=RESOLVED_IDENTITY)
    assert a["document_count"] == 6


# --- presentable material ----------------------------------------------------
def test_thin_evidence_cannot_promise_five_slides():
    documents = [_doc("homepage"), _doc("product")]
    a = assess_readiness(documents=documents, identity=RESOLVED_IDENTITY)
    assert "presentable_material" in a["failed_checks"]
    assert len(slide_units(documents)) < MIN_SLIDE_UNITS


def test_slide_units_are_never_padded_with_boilerplate():
    units = slide_units(_full_evidence())
    # sources, disclaimers and limitations are not subjects
    assert not any(u in units for u in
                   ("sources", "limitations", "disclaimer", "onboarding"))
    assert len(units) == len(set(units)), "each subject counts once"


def test_is_dated_recognises_real_date_forms():
    assert is_dated({"text_content": "quarter ended June 2026"})
    assert is_dated({"text_content": "filed 2026-05-05"})
    assert is_dated({"text_content": "results for FY2026"})
    assert not is_dated({"text_content": "we build great software"})


# --- retry -------------------------------------------------------------------
def test_a_gap_with_somewhere_left_to_look_is_retryable():
    documents = [_doc("homepage"), _doc("product"), _doc("about")]
    a = assess_readiness(documents=documents, identity=RESOLVED_IDENTITY,
                         attempt=1)
    assert a["state"] == RETRYABLE_EVIDENCE_GAP
    plan = a["retry_plan"]
    assert plan["available"]
    assert plan["target_families"], "a retry must name what it is looking for"
    assert plan["look_for"]


def test_worth_retrying_does_not_mean_refuse_to_say_anything():
    """Two different questions: is there enough to say, and is it worth
    looking further. Conflating them suppresses a useful limited view."""
    documents = [
        _doc("homepage", text="Brightlake is a logistics software company "
                              "founded in 2019 and based in Toronto."),
        _doc("product", text="The routing platform plans multi-stop delivery "
                             "routes for distributors, updated May 2026."),
        _doc("blog", "executive_statement",
             text="In June 2026 our chief executive set out the automation "
                  "roadmap for the next two years."),
    ]
    a = assess_readiness(documents=documents, identity=RESOLVED_IDENTITY,
                         attempt=1)
    assert a["state"] == RETRYABLE_EVIDENCE_GAP
    assert a["may_synthesize"], "three families is a real, if limited, view"
    assert not a["full_report_allowed"]


def test_one_family_is_never_enough_however_many_documents():
    documents = [_doc("about", "investor_material",
                      text=f"Report of foreign private issuer {i} furnished "
                           f"for the month of May 2026 under the rules of "
                           f"the Exchange Act.") for i in range(6)]
    a = assess_readiness(documents=documents, identity=RESOLVED_IDENTITY,
                         attempt=1)
    assert not a["may_synthesize"], "one viewpoint is not an analysis"
    assert a["material_level"] == "none"


def test_a_retry_avoids_ground_already_known_to_be_barren():
    failures = [{"url": "https://x.example/customers"},
                {"url": "https://x.example/investors"}]
    a = assess_readiness(documents=[_doc("homepage"), _doc("product")],
                         identity=RESOLVED_IDENTITY, failures=failures,
                         attempt=1)
    assert a["retry_plan"]["avoid_urls"] == [
        "https://x.example/customers", "https://x.example/investors"]


def test_the_retry_budget_is_finite():
    documents = [_doc("homepage"), _doc("product"), _doc("about")]
    a = assess_readiness(documents=documents, identity=RESOLVED_IDENTITY,
                         attempt=MAX_DISCOVERY_ATTEMPTS)
    assert a["retry_plan"]["exhausted"]
    assert not a["retry_plan"]["available"]
    assert a["state"] != RETRYABLE_EVIDENCE_GAP


def test_spent_budget_with_real_material_becomes_a_limited_report():
    documents = [_doc("homepage"), _doc("product"), _doc("about")]
    a = assess_readiness(documents=documents, identity=RESOLVED_IDENTITY,
                         attempt=MAX_DISCOVERY_ATTEMPTS)
    assert a["state"] == READY_FOR_LIMITED_REPORT
    assert a["may_synthesize"]
    assert not a["full_report_allowed"]


def test_spent_budget_with_nothing_found_is_insufficient():
    a = assess_readiness(documents=[], identity=RESOLVED_IDENTITY,
                         attempt=MAX_DISCOVERY_ATTEMPTS)
    assert a["state"] == INSUFFICIENT_EVIDENCE
    assert not a["may_synthesize"]


# --- explanation -------------------------------------------------------------
def test_the_explanation_avoids_internal_vocabulary():
    a = assess_readiness(documents=[_doc("homepage")],
                         identity=RESOLVED_IDENTITY)
    e = explain(a)
    # Only the VALUES reach a reader; the dict keys are the renderer's API.
    prose = " ".join(str(v) for value in e.values()
                     for v in (value if isinstance(value, list) else [value]))
    for internal in ("READY_FOR", "RETRYABLE", "INSUFFICIENT_EVIDENCE",
                     "IDENTITY_UNRESOLVED", "no_dominant_family",
                     "presentable_material", "family_counts", "slide_units"):
        assert internal not in prose, f"leaked internal name: {internal}"


def test_the_explanation_says_what_was_found_and_what_was_missing():
    a = assess_readiness(documents=[_doc("homepage"), _doc("product")],
                         identity=RESOLVED_IDENTITY)
    e = explain(a)
    assert e["headline"]
    assert e["found"], "a reader is told what WAS found, not only what wasn't"
    assert e["missing"]
    assert e["source_count"] == 2


@pytest.mark.parametrize("state_fixture", [
    ([], None, IDENTITY_UNRESOLVED),
    ([], RESOLVED_IDENTITY, RETRYABLE_EVIDENCE_GAP),
])
def test_every_outcome_is_one_of_the_declared_states(state_fixture):
    documents, identity, expected = state_fixture
    a = assess_readiness(documents=documents, identity=identity, attempt=1)
    assert a["state"] == expected
