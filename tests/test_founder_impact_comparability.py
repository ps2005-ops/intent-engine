"""A change between two revisions is not value unless both saw the same evidence.

The confound this closes is the one that cannot be detected after the fact: a
dossier revised three weeks later differs from its predecessor for two reasons
at once — the engine reasoned differently, and the engine saw more filings.
Attributing the whole difference to reasoning is how a value metric comes to
measure the calendar.

Built while comparable pairs are still ZERO, deliberately. Once the first real
pair exists the fields would have to be back-filled from records that never
carried them, and that back-fill is a guess wearing a timestamp.
"""
from __future__ import annotations

import pytest

from intent_engine.external_intel import decision_impact as di


def impact(**kw):
    base = dict(analysis_id="a1", company_id="ACME", dossier_id="ACME",
                dossier_revision="2026-08-10", belief_id="b1",
                graph_node_id="", deltas=(), materiality=di.NONE,
                reason="no change")
    base.update(kw)
    return di.DecisionImpact(**base)


# --- three states, never two ------------------------------------------------

def test_matching_windows_are_attributable():
    got = impact(before_known_at="2026-08-01", after_known_at="2026-08-01")
    assert got.comparability == di.SAME_WINDOW
    assert got.attributable


def test_a_wider_window_is_not_attributable_to_reasoning():
    """The later side saw more. The difference may be evidence arriving."""
    got = impact(before_known_at="2026-08-01", after_known_at="2026-08-22")
    assert got.comparability == di.WIDER_WINDOW
    assert not got.attributable


def test_unrecorded_windows_are_not_matching_windows():
    """A comparison whose windows were not recorded is not one whose windows
    agreed, and pooling the two is how "changed its mind" becomes "saw more"."""
    assert impact().comparability == di.UNKNOWN_WINDOW
    assert not impact().attributable
    assert impact(before_known_at="2026-08-01").comparability == \
        di.UNKNOWN_WINDOW
    assert impact(after_known_at="2026-08-01").comparability == \
        di.UNKNOWN_WINDOW


def test_the_three_states_are_distinct():
    assert len(set(di.COMPARABILITY)) == 3


@pytest.mark.parametrize("materiality", [
    di.NONE, di.MEANINGFUL, di.DECISION_CHANGING, di.FIRST_OBSERVATION])
def test_attribution_is_independent_of_how_large_the_change_was(materiality):
    """A DECISION_CHANGING difference across two evidence windows is still
    not evidence about the engine. Size and attributability are orthogonal,
    and collapsing them is how the most dramatic rows get counted first."""
    got = impact(materiality=materiality, before_known_at="2026-08-01",
                 after_known_at="2026-08-22")
    assert not got.attributable


# --- the fields survive the record ------------------------------------------

def test_the_windows_and_lineage_reach_the_persisted_row():
    got = impact(before_known_at="2026-08-01", after_known_at="2026-08-01",
                 prior_revision_id="rev_a", current_revision_id="rev_b")
    row = got.as_dict()
    assert row["before_known_at"] == "2026-08-01"
    assert row["after_known_at"] == "2026-08-01"
    assert row["prior_revision_id"] == "rev_a"
    assert row["current_revision_id"] == "rev_b"
    assert row["comparability"] == di.SAME_WINDOW
    assert row["attributable"] is True


def test_an_older_row_without_the_fields_still_reads():
    """The 25 rows already on disk carry none of this, and must not crash a
    reader — they read as UNKNOWN_WINDOW, which is what they are."""
    row = impact().as_dict()
    assert row["comparability"] == di.UNKNOWN_WINDOW
    assert row["attributable"] is False


def test_the_windows_do_not_change_the_impact_identity():
    """Identity is the comparison, not the metadata about it; two rows for the
    same comparison must not become two rows because a field was added."""
    bare = impact()
    windowed = impact(before_known_at="2026-08-01",
                      after_known_at="2026-08-01")
    assert bare.decision_impact_id == windowed.decision_impact_id


# --- against what is actually on disk ---------------------------------------

def test_the_live_corpus_is_honestly_unattributable():
    """Measured, not assumed: every persisted row predates these fields."""
    import json
    import pathlib

    path = pathlib.Path("/Users/prathamsharma/intent-engine-market/reports/"
                        "market/decision_impact.jsonl")
    if not path.exists():
        pytest.skip("no persisted decision impacts")
    rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    assert rows, "the corpus is empty; this test would pass by iterating none"
    for row in rows:
        # None of them recorded a window, so none may enter a value rate.
        assert not row.get("before_known_at")
        assert row.get("materiality") == di.FIRST_OBSERVATION
