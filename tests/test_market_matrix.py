"""The completion matrix must be able to count itself.

A hand-written predecessor printed "PARTIAL (10)" above a table containing
twelve PARTIAL rows. Nobody noticed, and the miscount was carried into a
handoff as the authoritative remaining work. These tests make that class of
error impossible rather than merely embarrassing.
"""
import importlib.util
import pathlib

import pytest

_PATH = (pathlib.Path(__file__).resolve().parents[1] / "scripts"
         / "market_matrix.py")
_spec = importlib.util.spec_from_file_location("market_matrix", _PATH)
MM = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(MM)

MATRIX = MM.load()


def test_capability_counts_equal_the_number_of_axes():
    counts = MM.tally(MATRIX)
    assert sum(counts["capability"].values()) == counts["axes"]


def test_empirical_counts_equal_the_number_of_axes():
    counts = MM.tally(MATRIX)
    assert sum(counts["empirical"].values()) == counts["axes"]


def test_every_axis_id_is_unique():
    ids = [a["id"] for a in MATRIX["axes"]]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("axis", MATRIX["axes"], ids=lambda a: a["id"])
def test_every_axis_uses_the_closed_vocabularies(axis):
    assert axis["capability"] in MATRIX["capability_states"]
    assert axis["empirical"] in MATRIX["empirical_states"]


def test_capability_and_empirical_are_separate_axes():
    """The distinction that collapsed twelve finished subsystems into PARTIAL.

    A conservative channel with a complete seam and no movement today is
    capability=PASS / empirical=RAN_NO_CHANGE. If these ever merge, every
    quiet-but-working channel is mislabelled unfinished again.
    """
    complete_but_quiet = [a for a in MATRIX["axes"]
                          if a["capability"] == "PASS"
                          and a["empirical"] in ("RAN_NO_CHANGE", "SPARSE",
                                                 "BLOCKED_DATA",
                                                 "LEGACY_UNDATABLE")]
    assert complete_but_quiet, (
        "no axis exercises the capability/empirical split; the two-axis "
        "model is not being used and PARTIAL will creep back")


def test_blocking_excludes_honest_maturity_gates():
    """BLOCKED_DATA is not a blocker; PARTIAL and NOT_BUILT are.

    Driven by a SYNTHETIC matrix, not the live one. A break proof that
    widened `blocking()` to everything-not-PASS went NOT_CAUGHT because no
    axis currently carries capability=BLOCKED_DATA, so the branch that
    distinguishes an honest maturity gate from a real gap was never
    executed. A control that cannot fail is not a control.
    """
    synthetic = {"axes": [
        {"id": "PASSING", "capability": "PASS", "empirical": "MEASURED"},
        {"id": "GATED_DATA", "capability": "BLOCKED_DATA",
         "empirical": "BLOCKED_DATA"},
        {"id": "GATED_EXTERNAL", "capability": "BLOCKED_EXTERNAL",
         "empirical": "BLOCKED_EXTERNAL"},
        {"id": "NA", "capability": "NOT_APPLICABLE",
         "empirical": "NOT_APPLICABLE"},
        {"id": "REAL_GAP", "capability": "PARTIAL", "empirical": "UNMEASURED"},
        {"id": "MISSING", "capability": "NOT_BUILT", "empirical": "UNMEASURED"},
    ]}
    blockers = MM.blocking(synthetic)
    assert blockers == ["REAL_GAP", "MISSING"]
    for honest in ("PASSING", "GATED_DATA", "GATED_EXTERNAL", "NA"):
        assert honest not in blockers


def test_the_live_matrix_blocklist_matches_its_own_rule():
    blockers = MM.blocking(MATRIX)
    for axis in MATRIX["axes"]:
        expected = axis["capability"] in ("PARTIAL", "NOT_BUILT", "UNMEASURED")
        assert (axis["id"] in blockers) is expected


def test_the_render_states_whether_counts_agree():
    assert "AGREE" in MM.render(MATRIX)
