"""The V4 scorecard cannot be talked into a status."""
from __future__ import annotations

import pytest

from intent_engine.market import v4_readiness as VR


def axis(name="MACRO_STATE", status=VR.PASS, reason="measured"):
    return VR.AxisStatus(axis=name, status=status, reason=reason)


def test_statuses_are_counted_never_averaged():
    got = VR.scorecard([axis(status=VR.PASS),
                        axis("COMPANY_EXPOSURE", VR.PARTIAL, "some"),
                        axis("SCENARIOS", VR.NO, "absent")])
    assert got["by_status"] == {VR.PASS: 1, VR.PARTIAL: 1, VR.NO: 1}
    assert "score" not in got and "percentage" not in got


def test_an_axis_without_a_measured_reason_is_named():
    got = VR.scorecard([axis(reason="  ")])
    assert got["axes_without_a_measured_reason"] == ["MACRO_STATE"]


def test_missing_axes_are_reported_rather_than_ignored():
    got = VR.scorecard([axis()])
    assert "SCENARIOS" in got["missing_axes"]
    assert len(got["missing_axes"]) == len(VR.AXES) - 1


def test_an_unknown_status_is_refused():
    with pytest.raises(ValueError, match="unknown status"):
        VR.scorecard([axis(status="NEARLY")])


def test_executable_remaining_counts_partial_and_no_but_not_blocked():
    """Blocked-by-data is not work; PARTIAL and NO are."""
    got = VR.scorecard([axis(status=VR.PARTIAL),
                        axis("SCENARIOS", VR.NO, "absent"),
                        axis("SUPPLY_CHAIN", VR.BLOCKED_DATA, "no corpus"),
                        axis("EXPECTATIONS", VR.BLOCKED_OWNER, "needs a key")])
    assert set(got["executable_remaining"]) == {"MACRO_STATE", "SCENARIOS"}


def test_only_no_blocks():
    got = VR.scorecard([axis("SCENARIOS", VR.NO, "absent"),
                        axis("SUPPLY_CHAIN", VR.BLOCKED_DATA, "no corpus")])
    assert got["blocking"] == ["SCENARIOS"]
