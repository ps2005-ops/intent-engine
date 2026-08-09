"""Absence must never impersonate a negative fact.

THE DEFECT THIS CLOSES
----------------------
The market→Founder dossier carried the CURRENT thesis and nothing about how
it got there. `economic_theses` was an allowlisted export field that the
production call site never passed, and revisions had no field at all.

So a consumer asked "what changed your mind?" could not tell:

    this thesis has never moved
    the history was not transported

apart — and those need OPPOSITE answers. Today every live revision is
CREATED, so both readings produce the same sentence and the defect is
invisible. It starts producing a wrong answer the moment a thesis first
moves, which is precisely when anyone would believe it.

The status is STATED, not inferred from the length of the revision list,
because "no revisions crossed" and "no revision exists" are the same empty
list.
"""
from __future__ import annotations

import pathlib

import pytest

from intent_engine.market import learning_store as LS
from intent_engine.market import strategic_export as SE
from intent_engine.market import strategic_publish as SP

MARKET_ROOT = pathlib.Path("/Users/prathamsharma/intent-engine-market")


def revision(**kwargs) -> dict:
    row = {"revision_id": "rev_1", "thesis_id": "th_1",
           "previous_revision": "", "transition": "CREATED",
           "changed_at": "2026-08-09", "changed_fields": [],
           "knowledge_effect_ids": [], "triggering_evidence": [],
           "previous_standing": "", "new_standing": "PROPOSED",
           "reason": "opened"}
    row.update(kwargs)
    return row


# --- the three states, which must never collapse ----------------------------

def test_no_history_is_not_no_movement():
    """The whole point. An empty list is produced by both."""
    got = SE._thesis_history([], available=False)
    assert got["status"] == SE.HISTORY_UNAVAILABLE
    assert "no claim about what changed it can be supported" in got["note"]


def test_created_only_is_available_and_unmoved():
    got = SE._thesis_history([revision()], available=True)
    assert got["status"] == SE.HISTORY_AVAILABLE_NO_MOVEMENT
    assert got["moved"] == 0
    assert got["revisions"] == 1


def test_a_non_created_transition_is_movement():
    got = SE._thesis_history(
        [revision(), revision(revision_id="rev_2", transition="WEAKENED")],
        available=True)
    assert got["status"] == SE.HISTORY_AVAILABLE_MOVED
    assert got["moved"] == 1
    assert got["revisions"] == 2


def test_an_empty_available_history_is_still_not_unavailable():
    """A company with no theses at all has an available, empty history."""
    assert SE._thesis_history([], available=True)["status"] == \
        SE.HISTORY_AVAILABLE_NO_MOVEMENT


def test_the_three_states_are_distinct():
    assert len(set(SE.HISTORY_STATES)) == 3


# --- the export carries the cause, not just the verdict ---------------------

def test_a_revision_carries_its_effect_and_evidence():
    got = SE._revision(revision(transition="WEAKENED",
                                knowledge_effect_ids=["ke_1"],
                                triggering_evidence=["ev_1"]))
    assert got["knowledge_effect_ids"] == ["ke_1"]
    assert got["triggering_evidence"] == ["ev_1"]
    assert got["previous_standing"] == ""
    assert got["new_standing"] == "PROPOSED"


def test_a_revision_survives_the_allowlist():
    """The wall fails closed, so a new field must be declared to cross."""
    payload = SE.build_export(
        company_id="acme", as_of="2026-08-09", subject_id="acme",
        display_name="Acme", subject_names=["Acme"], beliefs=[],
        thesis_revisions=[revision()], history_available=True)
    assert payload["thesis_revisions"][0]["revision_id"] == "rev_1"
    assert payload["thesis_history"]["status"] == \
        SE.HISTORY_AVAILABLE_NO_MOVEMENT


def test_unavailable_history_crosses_as_a_stated_status():
    payload = SE.build_export(
        company_id="acme", as_of="2026-08-09", subject_id="acme",
        display_name="Acme", subject_names=["Acme"], beliefs=[],
        thesis_revisions=[], history_available=False)
    assert payload["thesis_history"]["status"] == SE.HISTORY_UNAVAILABLE
    assert payload["thesis_revisions"] == []


# --- identity is by id, never by wording ------------------------------------

def test_revisions_are_matched_by_thesis_id_not_claim_text():
    """G-THE-004 was two theses with byte-identical claims. Matching on
    wording merged them and dropped four snapshots a night."""
    theses = [{"thesis_id": "th_1", "claim": "same words", "subject": "a"}]
    revisions = [revision(thesis_id="th_1"),
                 revision(revision_id="rev_9", thesis_id="th_2")]
    got = SP._revisions_for(revisions, theses)
    assert [r["revision_id"] for r in got] == ["rev_1"]


def test_a_thesis_belongs_to_its_subject_by_id():
    assert SP._belongs({"subject": "honda", "thesis_id": "t"}, "honda")
    assert not SP._belongs({"subject": "toyota", "thesis_id": "t"}, "honda")


def test_a_revision_with_no_matching_thesis_does_not_cross():
    assert SP._revisions_for([revision(thesis_id="orphan")], []) == []


# --- against the live ledger ------------------------------------------------

@pytest.mark.skipif(not (MARKET_ROOT / LS.DEFAULT_PATH).exists(),
                    reason="no live ledger")
def test_the_live_ledger_reports_no_movement_rather_than_no_history():
    """Production's real state, and the reading it must produce.

    Every live revision is CREATED, so the honest answer is that nothing has
    changed these views yet — NOT that the history is missing. Before the
    transport existed the Founder side could only have said the latter.
    """
    store = LS.LearningStore(MARKET_ROOT / LS.DEFAULT_PATH)
    snapshots = store.thesis_snapshots()
    revisions = store.thesis_revisions()
    if not snapshots:                                      # pragma: no cover
        pytest.skip("no thesis snapshots in the live ledger")

    subjects = {str(s.get("subject") or "") for s in snapshots} - {""}
    assert subjects, "snapshots must name their subject"
    seen = set()
    for subject in subjects:
        mine = [t for t in snapshots if SP._belongs(t, subject)]
        theirs = SP._revisions_for(revisions, mine)
        seen.add(SE._thesis_history(theirs, True)["status"])
    assert seen == {SE.HISTORY_AVAILABLE_NO_MOVEMENT}, (
        "every live revision is CREATED, so every subject must read "
        "AVAILABLE_NO_MOVEMENT; MOVED would mean a thesis transitioned and "
        "UNAVAILABLE would mean the transport regressed")
