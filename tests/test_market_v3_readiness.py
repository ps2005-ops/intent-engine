"""A bottleneck that is asserted is a belief; one that is computed is a finding."""
from __future__ import annotations

from intent_engine.market import v3_readiness as VR


def m(stage, inputs, outputs, reason="", blocked=False):
    return VR.StageMeasure(stage=stage, inputs=inputs, outputs=outputs,
                           reason=reason, blocked_by_data=blocked)


def test_the_narrowest_stage_that_actually_ran_is_the_bottleneck():
    got = VR.detect([m("SOURCE_RETRIEVAL", 100, 90),
                     m("EVENT_IDENTITY", 90, 85),
                     m("RESPONSE_OBSERVABILITY", 20, 1, "no dated stream")])
    assert got["primary_bottleneck"]["stage"] == "RESPONSE_OBSERVABILITY"
    # SOURCE_RETRIEVAL (0.90) is narrower than EVENT_IDENTITY (0.94).
    assert got["secondary_bottleneck"]["stage"] == "SOURCE_RETRIEVAL"


def test_a_stage_nobody_fed_is_not_the_loudest_bottleneck():
    """Scoring an unfed stage at 0.0 makes it win every time, and a stage
    nobody fed has not failed."""
    got = VR.detect([m("SOURCE_RETRIEVAL", 100, 50),
                     m("STRATEGIC_INTERACTION", 0, 0)])
    assert got["primary_bottleneck"]["stage"] == "SOURCE_RETRIEVAL"
    assert "STRATEGIC_INTERACTION" in got["stages_never_fed"]


def test_throughput_is_none_not_zero_when_starved():
    assert m("X", 0, 0).throughput is None
    assert m("X", 10, 0).throughput == 0.0


def test_the_recommendation_comes_from_the_measurement():
    got = VR.detect([m("TEMPORAL_COVERAGE", 23, 7, "capture publication dates")])
    assert got["recommended_next_action"] == "capture publication dates"


def test_detecting_nothing_says_so_rather_than_guessing():
    got = VR.detect([m("X", 0, 0)])
    assert got["primary_bottleneck"] is None
    assert "measure first" in got["recommended_next_action"]


# --- the scorecard --------------------------------------------------------

def test_statuses_are_counted_never_averaged():
    got = VR.scorecard([
        VR.AxisStatus(axis="EVIDENCE_INTEGRITY", status=VR.PASS, reason="r"),
        VR.AxisStatus(axis="STRATEGIC_REASONING", status=VR.BLOCKED, reason="r"),
    ])
    assert got["by_status"] == {VR.PASS: 1, VR.BLOCKED: 1}
    assert "not averaged" in got["note"]
    assert "percentage" not in str(got.get("score", ""))


def test_a_blocking_axis_is_named():
    got = VR.scorecard([
        VR.AxisStatus(axis="STRATEGIC_REASONING", status=VR.BLOCKED, reason="r")])
    assert got["blocking"] == ["STRATEGIC_REASONING"]


def test_an_axis_with_no_measured_reason_is_flagged():
    """Every status must cite a measured reason, or the scorecard is an
    opinion with a table around it."""
    got = VR.scorecard([
        VR.AxisStatus(axis="CALIBRATION", status=VR.PASS, reason="  ")])
    assert got["axes_without_a_measured_reason"] == ["CALIBRATION"]


def test_missing_axes_are_reported_rather_than_assumed_passing():
    got = VR.scorecard([
        VR.AxisStatus(axis="SAFETY_PAPER", status=VR.PASS, reason="enforced")])
    assert "EVIDENCE_INTEGRITY" in got["missing_axes"]
