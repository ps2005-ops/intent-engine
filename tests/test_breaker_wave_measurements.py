"""The wave runner is the measurement instrument, so it gets tested too.

A runner that reads a producer field by the wrong name manufactures uniform
defects across a whole cohort — this program has already lost a batch to
exactly that. These tests pin the readers and, above all, pin the difference
between a measured zero and an absent input.
"""
import importlib.util
import pathlib

import pytest

_PATH = (pathlib.Path(__file__).resolve().parents[1] / "scripts"
         / "v5_breaker_wave.py")
_spec = importlib.util.spec_from_file_location("v5_breaker_wave", _PATH)
wave = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wave)


def record(*, attempted=10, ok=5, documents=5, observations=7,
           independent=2, duplicates=0, republications=0, self_reports=3,
           unknown=0, concentration=0.5, state="MEASURED", fetch_seconds=10.0,
           failure_types=None, http_statuses=None):
    return {
        "fetch_seconds": fetch_seconds,
        "source_health": {
            "attempted": attempted, "ok": ok,
            "failure_types": failure_types or {},
            "http_status_counts": http_statuses or {},
        },
        "evidence": {
            "documents_retrieved": documents,
            "observations": observations,
            "evidence_independence_state": state,
            "independence": {
                "independent_evidence_count": independent,
                "duplicate_document_count": duplicates,
                "republication_count": republications,
                "company_self_report_count": self_reports,
                "unknown_lineage_count": unknown,
                "concentration_ratio": concentration,
            },
        },
    }


# --- missing is not zero -----------------------------------------------------
def test_a_ratio_with_no_denominator_is_unmeasurable_not_zero():
    out = wave._cohort_summary([record(attempted=0, ok=0, documents=0,
                                       observations=0, independent=0)])
    assert out["retrieval"]["retrieval_yield"] == wave.UNMEASURABLE
    assert out["evidence"]["observations_per_document"] == wave.UNMEASURABLE
    assert (out["independence"]["independent_document_share"]
            == wave.UNMEASURABLE)


def test_zero_independent_documents_is_unmeasurable_latency_not_zero():
    out = wave._cohort_summary([record(independent=0)])
    assert (out["independence"]["seconds_per_independent_document"]
            == wave.UNMEASURABLE)


def test_a_company_whose_producer_did_not_run_is_excluded_not_counted_zero():
    """An UNAVAILABLE company must not drag the cohort share toward zero."""
    both = wave._cohort_summary([record(state="MEASURED", independent=2),
                                 record(state="UNAVAILABLE", independent=0)])
    assert both["independence_measured_for"] == 1
    # 2 independent over the 10 documents of BOTH companies would be the bug:
    # the unmeasured company contributes documents to `documents` but its
    # independence is unknown, so it is reported, not silently averaged in.
    assert both["independence"]["independent_documents"] == 2


def test_learning_conversion_is_unavailable_with_a_reason_not_zero():
    """A record carrying no attribution at all still never reports zero.

    Batch 13 gave this metric a producer, so the field names now match the
    populations they divide. What the test protects is unchanged and is the
    only thing that mattered: the absence is stated, with a reason, and never
    as a number.
    """
    out = wave._cohort_summary([record()])
    conversion = out["learning_conversion"]
    assert conversion["state"] == wave.UNAVAILABLE
    assert conversion["effect_producing_evidence_rows"] == wave.UNAVAILABLE
    assert conversion["zero_effect_evidence_rows"] == wave.UNAVAILABLE
    assert conversion["learning_conversion"] == wave.UNAVAILABLE
    assert conversion["reason"]


def test_a_dead_backend_reports_blocked_not_unavailable():
    """The seam now exists, so the reason is nameable.

    "UNAVAILABLE" was the honest answer while nothing could attribute at all.
    Now that something can, a cohort whose reasoning layer never ran is
    BLOCKED_EXTERNAL_CREDITS — a fact about the backend — and that is a
    different report from "we have no way to measure this".
    """
    blocked = dict(record(),
                   learning={"attribution_state": "BLOCKED_EXTERNAL_CREDITS",
                             "evidence_rows": 7})
    conversion = wave._cohort_summary([blocked])["learning_conversion"]
    assert conversion["state"] == "BLOCKED_EXTERNAL_CREDITS"
    assert conversion["learning_conversion"] == wave.UNAVAILABLE
    assert conversion["companies_measured"] == 0


def test_measured_attribution_divides_rows_by_rows():
    measured = dict(record(),
                    learning={"attribution_state": "MEASURED",
                              "eligible_evidence_rows": 4,
                              "effect_producing_evidence_rows": 1,
                              "independent_effect_producing_evidence_rows": 1})
    conversion = wave._cohort_summary([measured])["learning_conversion"]
    assert conversion["state"] == "MEASURED"
    assert conversion["learning_conversion"] == 0.25
    assert conversion["zero_effect_evidence_rows"] == 3


def test_zero_observations_under_a_dead_backend_is_not_an_evidence_finding():
    """0.0 observations per document must not read as "documents were empty".

    Every company in the b12_after wave returned 0 observations because the
    reasoning backend was credit-exhausted, not because the retrieved pages
    carried nothing. The rate is still reported; what this pins is that the
    rate never travels without the state that explains it.
    """
    dead = [dict(record(observations=0),
                 intelligence={"strategic_report": "PRESENT",
                               "result_state": "FAILED"}),
            dict(record(observations=0),
                 intelligence={"strategic_report": "ABSENT"})]
    out = wave._cohort_summary(dead)
    assert out["evidence"]["observations_per_document"] == 0.0
    state = out["evidence"]["observations_state"]
    assert state["state"] == "BLOCKED_EXTERNAL_CREDITS"
    assert state["companies_with_usable_report"] == 0


def test_a_usable_report_makes_the_observation_count_a_real_measurement():
    live = [dict(record(observations=4),
                 intelligence={"strategic_report": "PRESENT",
                               "result_state": "COMPLETE"})]
    state = wave._cohort_summary(live)["evidence"]["observations_state"]
    assert state["state"] == "MEASURED"
    assert state["companies_with_usable_report"] == 1


# --- the detector ------------------------------------------------------------
def test_low_volume_cannot_produce_a_verdict():
    out = wave._high_activity_low_learning(
        documents=5, independent=0, duplicates=0, republications=0,
        measured_companies=1)
    assert out["status"] == wave.UNMEASURABLE
    assert out["detected"] is False


def test_high_volume_and_no_independence_is_detected_and_names_the_stage():
    out = wave._high_activity_low_learning(
        documents=100, independent=3, duplicates=40, republications=10,
        measured_companies=10)
    assert out["detected"] is True
    assert out["status"] == "DEGRADING"
    assert out["which_conversion_failed"] == "documents → independent evidence"


def test_healthy_independence_is_not_flagged():
    out = wave._high_activity_low_learning(
        documents=100, independent=40, duplicates=0, republications=0,
        measured_companies=10)
    assert out["detected"] is False
    assert out["status"] == "STABLE"


def test_the_belief_arm_is_never_claimed_stable():
    """The half that needs the effect ledger must never assert learning.

    Reporting STABLE here would say the system IS learning on the basis of a
    measurement nothing performed. Batch 13 gave the arm a producer, so the
    value is now the attribution STATE rather than a fixed UNMEASURABLE — and
    the invariant is what it always was: without a measured attribution, this
    arm never claims the system learned anything.
    """
    for documents, independent in ((100, 40), (100, 1), (5, 0)):
        out = wave._high_activity_low_learning(
            documents=documents, independent=independent, duplicates=0,
            republications=0, measured_companies=10)
        assert out["belief_arm"] != "STABLE"
        assert out["belief_arm"] in (wave.UNMEASURABLE, wave.UNAVAILABLE)


def test_a_blocked_backend_names_itself_in_the_belief_arm():
    out = wave._high_activity_low_learning(
        documents=100, independent=40, duplicates=0, republications=0,
        measured_companies=10,
        learning={"state": "BLOCKED_EXTERNAL_CREDITS",
                  "reason": "no knowledge state was produced"})
    assert out["belief_arm"] == "BLOCKED_EXTERNAL_CREDITS"
    # and the chain names the unmeasured step rather than blaming evidence
    assert "BLOCKED_EXTERNAL_CREDITS" in out["first_starved_conversion"]


def test_the_first_starved_conversion_is_the_earliest_one():
    """Retrieval starvation outranks a later unmeasured stage."""
    starved = wave._first_starved_conversion(
        documents=100, independent=1,
        learning={"state": "BLOCKED_EXTERNAL_CREDITS"})
    assert starved == "documents → independent evidence"


# --- population compatibility ------------------------------------------------
def test_observations_per_document_is_a_rate_and_may_exceed_one():
    out = wave._cohort_summary([record(documents=2, observations=10)])
    assert out["evidence"]["observations_per_document"] == 5.0


def test_independent_document_share_is_bounded_by_one():
    out = wave._cohort_summary([record(documents=5, independent=5)])
    assert out["independence"]["independent_document_share"] == 1.0


@pytest.mark.parametrize("statuses", [{"HTTP 403": 3, "HTTP 404": 7}])
def test_http_statuses_are_summed_as_counts_not_collapsed_to_a_set(statuses):
    out = wave._cohort_summary([record(http_statuses=statuses),
                                record(http_statuses=statuses)])
    assert out["retrieval"]["http_status_counts"] == {"HTTP 403": 6,
                                                      "HTTP 404": 14}
