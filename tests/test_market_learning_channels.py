"""A cleaner denominator is not a new fact about the world."""
from __future__ import annotations

import pytest

from intent_engine.market import learning_channels as LC


def test_a_pipeline_repair_cannot_be_filed_as_economic_knowledge():
    """The exact failure this prevents: wave 9 removed 22 non-actions and
    three counting defects, every number improved, and the count of
    established competitive objects stayed at one."""
    with pytest.raises(LC.ChannelRejected, match="cannot be counted as"):
        LC.movement(channel=LC.ECONOMIC_KNOWLEDGE, kind="non_action_removed",
                    count=22, detail="wave 9 precision gate")


def test_the_same_movement_is_accepted_as_system_capability():
    got = LC.movement(channel=LC.SYSTEM_CAPABILITY, kind="non_action_removed",
                      count=22, detail="wave 9 precision gate")
    assert got.channel == LC.SYSTEM_CAPABILITY


def test_a_movement_with_no_detail_cannot_be_audited():
    with pytest.raises(LC.ChannelRejected):
        LC.movement(channel=LC.SYSTEM_CAPABILITY, kind="duplicate_removed",
                    count=1, detail="   ")


def test_the_four_totals_are_reported_separately():
    got = LC.report([
        LC.movement(channel=LC.SYSTEM_CAPABILITY, kind="non_action_removed",
                    count=22, detail="precision gate"),
        LC.movement(channel=LC.SYSTEM_CAPABILITY, kind="duplicate_removed",
                    count=15, detail="anchor and content dedupe"),
    ])
    assert got["by_channel"][LC.SYSTEM_CAPABILITY]["total"] == 37
    assert got["by_channel"][LC.ECONOMIC_KNOWLEDGE]["total"] == 0
    assert "never summed" in got["note"]


# --- calibration is six questions -----------------------------------------

def test_an_untested_track_is_unmeasurable_and_not_zero():
    """An accuracy of 0.0 claims we tried and failed."""
    track = LC.CalibrationTrack(track=LC.RESPONSE_PREDICTION_ACCURACY)
    assert track.accuracy is None
    assert track.standing == LC.UNMEASURABLE
    assert track.as_dict()["accuracy"] is None


def test_every_joint_of_the_chain_has_its_own_track():
    got = LC.report([])
    names = [t["track"] for t in got["calibration"]]
    assert names == list(LC.CALIBRATION_TRACKS)
    assert len(names) == 6
    assert got["calibration_unmeasurable"] == 6


def test_a_measured_track_reports_its_rate():
    got = LC.report([], [LC.CalibrationTrack(
        track=LC.OBJECT_ESTABLISHMENT_ACCURACY, tested=4, correct=3,
        note="hand-adjudicated")])
    entry = next(t for t in got["calibration"]
                 if t["track"] == LC.OBJECT_ESTABLISHMENT_ACCURACY)
    assert entry["accuracy"] == 0.75
    assert entry["standing"] == "MEASURED"
    assert got["calibration_unmeasurable"] == 5
