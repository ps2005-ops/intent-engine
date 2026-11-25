"""Is Founder CURRENT, or merely untouched — the distinction, tested.

Both arms are mandatory. The no-material-change arm is the one that is easy
to get wrong in the flattering direction: a system that appends a revision
every night looks busy and is lying about receiving new intelligence.
"""
import json

import pytest

from intent_engine.market import founder_freshness as FF


def runtime(tmp_path, exports=(), revisions=()):
    root = tmp_path / "runtime"
    (root / "reports" / "market" / "strategic").mkdir(parents=True)
    for payload in exports:
        path = (root / "reports" / "market" / "strategic"
                / f"{payload['company_id']}.json")
        path.write_text(json.dumps(payload), encoding="utf-8")
    if revisions:
        (root / "reports" / "market" / "dossier_revisions.jsonl").write_text(
            "\n".join(json.dumps(r) for r in revisions), encoding="utf-8")
    return root


def export(company="acme", theses=("thesis-1",), generated="2026-08-13T10:00:00+00:00"):
    return {"company_id": company, "as_of": "2026-08-13",
            "export_version": "strategic_market_intel.v1",
            "generated_at": generated,
            "freshness": {"age_days": 0, "stale": False},
            "economic_theses": list(theses)}


def revision(company="acme", digest="", at="2026-08-13T11:00:00+00:00"):
    row = {"company_id": company, "record": "dossier_revision",
           "recorded_at": at, "revision_key": "rev_x"}
    if digest:
        row["semantic_digest"] = digest
    return row


# --- the semantic digest ------------------------------------------------------
def test_a_regenerated_identical_export_has_the_same_digest():
    """The property the whole state machine rests on.

    A nightly cycle re-deriving identical intelligence writes a
    byte-different file (new `generated_at`) and must produce the SAME
    digest, or every night becomes a 'material change'.
    """
    a = export(generated="2026-08-13T10:00:00+00:00")
    b = export(generated="2026-08-13T23:59:00+00:00")
    assert a != b
    assert FF.semantic_digest(a) == FF.semantic_digest(b)


def test_a_changed_thesis_changes_the_digest():
    assert FF.semantic_digest(export(theses=("thesis-1",))) != \
        FF.semantic_digest(export(theses=("thesis-1", "thesis-2")))


def test_the_freshness_block_alone_does_not_change_the_digest():
    a = export()
    b = dict(export(), freshness={"age_days": 9, "stale": True})
    assert FF.semantic_digest(a) == FF.semantic_digest(b)


# --- ARM B: no material change ------------------------------------------------
def test_an_identical_export_is_current_with_no_new_revision(tmp_path):
    """The arm that must not append an empty revision."""
    payload = export()
    root = runtime(tmp_path, exports=[payload],
                   revisions=[revision(digest=FF.semantic_digest(payload))])
    out = FF.assess(root=str(root), transport_configured=False)
    assert out["per_company"]["acme"]["state"] == \
        FF.CURRENT_NO_NEW_REVISION_REQUIRED
    assert out["current"] == 1
    assert out["current_share"] == 1.0


def test_running_the_same_state_twice_does_not_change_the_verdict(tmp_path):
    """Metamorphic: idempotent on unchanged intelligence."""
    payload = export()
    root = runtime(tmp_path, exports=[payload],
                   revisions=[revision(digest=FF.semantic_digest(payload))])
    first = FF.assess(root=str(root), transport_configured=False)
    # A later cycle rewrites the file with a new timestamp and nothing else.
    (root / "reports" / "market" / "strategic" / "acme.json").write_text(
        json.dumps(export(generated="2026-08-13T23:00:00+00:00")),
        encoding="utf-8")
    second = FF.assess(root=str(root), transport_configured=False)
    assert first["by_state"] == second["by_state"]
    assert second["current"] == 1


# --- ARM A: material change ---------------------------------------------------
def test_a_changed_export_is_stale_until_consumed(tmp_path):
    root = runtime(tmp_path, exports=[export(theses=("t1", "t2"))],
                   revisions=[revision(digest="sem_somethingelse")])
    state = FF.assess(root=str(root),
                      transport_configured=False)["per_company"]["acme"]
    assert state["state"] == FF.STALE_MARKET_INTELLIGENCE
    assert state["consumed_digest"] != state["current_digest"]


def test_a_configured_transport_reports_transport_stale(tmp_path):
    root = runtime(tmp_path, exports=[export()],
                   revisions=[revision(digest="sem_old")])
    state = FF.assess(root=str(root),
                      transport_configured=True)["per_company"]["acme"]
    assert state["state"] == FF.TRANSPORT_STALE


# --- missing is not current ---------------------------------------------------
def test_an_export_nobody_consumed_is_not_consumed_not_current(tmp_path):
    root = runtime(tmp_path, exports=[export()])
    state = FF.assess(root=str(root),
                      transport_configured=False)["per_company"]["acme"]
    assert state["state"] == FF.NOT_CONSUMED
    assert state["state"] not in FF.CURRENT_STATES


def test_a_revision_without_a_digest_cannot_be_proven_current(tmp_path):
    """The live case: 25 Founder revisions predate digest recording.

    They cannot be shown to correspond to the current export, and guessing
    CURRENT is exactly the false all-clear this module exists to prevent.
    """
    root = runtime(tmp_path, exports=[export()], revisions=[revision()])
    state = FF.assess(root=str(root),
                      transport_configured=False)["per_company"]["acme"]
    assert state["state"] == FF.STALE_MARKET_INTELLIGENCE


def test_a_company_with_no_export_is_unchecked_not_up_to_date(tmp_path):
    root = runtime(tmp_path, revisions=[revision(company="ghost")])
    state = FF.assess(root=str(root),
                      transport_configured=False)["per_company"]["ghost"]
    assert state["state"] == FF.EXPORT_NOT_CHECKED


def test_an_empty_runtime_reports_no_share_rather_than_zero(tmp_path):
    root = runtime(tmp_path)
    out = FF.assess(root=str(root), transport_configured=False)
    assert out["companies"] == 0
    assert out["current_share"] is None


def test_unconfigured_transport_is_a_fact_not_a_failure(tmp_path):
    out = FF.assess(root=str(runtime(tmp_path, exports=[export()])),
                    transport_configured=False)
    assert out["transport"] == FF.TRANSPORT_NOT_CONFIGURED
    assert "not a failure" in out["transport_note"]
    assert FF.TRANSPORT_FAILED not in out["by_state"]


@pytest.mark.parametrize("state", FF.STATES)
def test_every_state_is_closed(state):
    assert state in FF.STATES
