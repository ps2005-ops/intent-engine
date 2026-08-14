"""The market bridge: one configured root, four states that mean four things.

The live defect this pins: the founder side read market snapshots from its
OWN runtime root, so 26 published snapshots were invisible and every dossier
said "no market snapshot has been published for this company" -- true of the
directory it looked in, false of the deployment.
"""
from __future__ import annotations

import json

from intent_engine.demo_dossier import bridge as B
from intent_engine.demo_dossier import transport as T

CONTRACT = "market_demo_snapshot.v1"


def _snapshot(company="acme-corp", *, cutoff="2026-08-13", **over):
    payload = {
        "contract_version": CONTRACT, "company_id": company,
        "canonical_name": company, "snapshot_id": "ms-1",
        "availability": "AVAILABLE", "unavailable_reason": "",
        "generated_at": cutoff, "known_at": cutoff, "evidence_cutoff": cutoff,
        "market_population": "REAL_MARKET",
    }
    payload.update(over)
    return payload


def _publish(root, payload, name=None):
    d = root.joinpath(*T.MARKET_SNAPSHOT_DIR)
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{name or payload['company_id']}.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


# --- the four states, per company ------------------------------------------

def test_a_published_current_snapshot_is_current(tmp_path):
    _publish(tmp_path, _snapshot())
    a = B.for_company("acme-corp", root=tmp_path, today="2026-08-14")
    assert a.state == B.CURRENT
    assert a.usable and a.snapshot is not None
    assert a.company_id == "acme-corp"
    assert a.schema == CONTRACT
    assert a.generated_at == "2026-08-13"
    assert a.digest and a.freshness_days == 1
    assert str(tmp_path) in a.source_path


def test_no_file_for_this_company_is_missing_not_invalid(tmp_path):
    _publish(tmp_path, _snapshot("other-co"))
    a = B.for_company("acme-corp", root=tmp_path, today="2026-08-14")
    assert a.state == B.MISSING
    assert not a.usable
    assert "no snapshot" in a.reason.lower() or "published no" in a.reason


def test_an_unparseable_file_is_invalid_and_never_usable(tmp_path):
    d = tmp_path.joinpath(*T.MARKET_SNAPSHOT_DIR)
    d.mkdir(parents=True, exist_ok=True)
    (d / "acme-corp.json").write_text("{not json", encoding="utf-8")
    a = B.for_company("acme-corp", root=tmp_path, today="2026-08-14")
    assert a.state == B.INVALID
    assert not a.usable


def test_an_old_snapshot_is_stale_and_still_readable(tmp_path):
    _publish(tmp_path, _snapshot(cutoff="2026-01-01"))
    a = B.for_company("acme-corp", root=tmp_path, today="2026-08-14")
    assert a.state == B.STALE
    # STALE content is real; its age is stated. This is the one non-CURRENT
    # state whose payload a surface may still show.
    assert a.usable and a.snapshot is not None
    assert a.freshness_days > 21


def test_a_snapshot_filed_under_another_company_is_invalid(tmp_path):
    # The dangerous case: right filename, wrong contents. Showing this would
    # attribute one company's market intelligence to another.
    _publish(tmp_path, _snapshot("globex-inc"), name="acme-corp")
    a = B.for_company("acme-corp", root=tmp_path, today="2026-08-14")
    assert a.state == B.INVALID
    assert not a.usable
    assert "globex-inc" in a.reason


def test_an_unreadable_contract_version_is_invalid(tmp_path):
    _publish(tmp_path, _snapshot(contract_version="market_demo_snapshot.v99"))
    a = B.for_company("acme-corp", root=tmp_path, today="2026-08-14")
    assert a.state == B.INVALID
    assert not a.usable


def test_a_published_stated_absence_is_missing_not_current(tmp_path):
    _publish(tmp_path, _snapshot(availability="UNAVAILABLE",
                                 unavailable_reason="never analysed"))
    a = B.for_company("acme-corp", root=tmp_path, today="2026-08-14")
    assert a.state == B.MISSING
    assert "never analysed" in a.reason


# --- configuration ----------------------------------------------------------

def test_an_unconfigured_bridge_is_missing_and_says_so():
    a = B.for_company("acme-corp", env={}, today="2026-08-14")
    assert a.state == B.MISSING
    assert a.configured is False
    assert B.ENV_VAR in a.reason


def test_the_root_comes_from_the_environment_and_is_not_guessed(tmp_path):
    _publish(tmp_path, _snapshot())
    a = B.for_company("acme-corp", env={B.ENV_VAR: str(tmp_path)},
                      today="2026-08-14")
    assert a.state == B.CURRENT


def test_an_unset_root_never_falls_back_to_a_stale_fixture(tmp_path):
    # A fallback would be a second system of record: the product would show
    # market intelligence that no configured engine produced.
    _publish(tmp_path, _snapshot())
    a = B.for_company("acme-corp", env={}, today="2026-08-14")
    assert a.snapshot is None


# --- the startup reading ----------------------------------------------------

def test_startup_reports_current_when_the_engine_is_publishing(tmp_path):
    _publish(tmp_path, _snapshot("a"))
    _publish(tmp_path, _snapshot("b", cutoff="2026-08-12"))
    s = B.assess(root=tmp_path, today="2026-08-14")
    assert s["state"] == B.CURRENT
    assert s["snapshot_count"] == 2
    # The NEWEST decides freshness, not an arbitrary file.
    assert s["evidence_cutoff"] == "2026-08-13"
    assert s["freshness_days"] == 1


def test_startup_reports_stale_when_the_engine_stopped(tmp_path):
    _publish(tmp_path, _snapshot("a", cutoff="2026-01-01"))
    s = B.assess(root=tmp_path, today="2026-08-14")
    assert s["state"] == B.STALE
    assert "not running on this schedule" in s["reason"]


def test_startup_distinguishes_unset_from_empty_from_unreadable(tmp_path):
    unset = B.assess(env={}, today="2026-08-14")
    assert unset["state"] == B.MISSING and unset["configured"] is False

    empty = tmp_path / "empty"
    empty.joinpath(*T.MARKET_SNAPSHOT_DIR).mkdir(parents=True)
    e = B.assess(root=empty, today="2026-08-14")
    assert e["state"] == B.MISSING and e["configured"] is True

    broken = tmp_path / "broken"
    d = broken.joinpath(*T.MARKET_SNAPSHOT_DIR)
    d.mkdir(parents=True)
    (d / "x.json").write_text("{oops", encoding="utf-8")
    b = B.assess(root=broken, today="2026-08-14")
    # Files present and none readable is a CONTRACT BREAK, not an empty
    # schedule -- the two need opposite repairs.
    assert b["state"] == B.INVALID


def test_startup_names_a_wrong_root_rather_than_reporting_empty(tmp_path):
    s = B.assess(root=tmp_path / "nowhere", today="2026-08-14")
    assert s["state"] == B.MISSING
    assert "the root is" in s["reason"]


# --- the digest -------------------------------------------------------------

def test_the_digest_is_semantic_not_bytewise(tmp_path):
    a = _snapshot()
    reordered = dict(reversed(list(a.items())))
    assert B._digest(a) == B._digest(reordered)


def test_the_digest_changes_when_the_intelligence_changes(tmp_path):
    assert B._digest(_snapshot()) != B._digest(_snapshot(cutoff="2026-08-12"))


# ---------------------------------------------------------------------------
# THE CROSSING. A bridge that resolves a path but whose payload the dossier
# refuses is not a bridge -- an earlier batch silently refused 22 dossiers
# over two unknown fields, and a refused dossier is indistinguishable from a
# company never analysed.
# ---------------------------------------------------------------------------

def test_a_current_snapshot_crosses_into_a_dossier_with_no_unknown_fields(
        tmp_path):
    from intent_engine.demo_dossier import assemble, founder_unavailable
    _publish(tmp_path, _snapshot(
        belief_refs={"state": "AVAILABLE", "ids": ["b1"], "count": 1,
                     "note": ""},
        expectation_refs={"state": "AVAILABLE", "ids": ["x1"], "count": 1,
                          "note": ""},
        evidence_reference_ids={"state": "AVAILABLE", "ids": ["e1", "e2"],
                                "count": 2, "note": ""}))
    a = B.for_company("acme-corp", root=tmp_path, today="2026-08-14")
    assert a.state == B.CURRENT
    d = assemble(a.snapshot,
                 founder_unavailable("no founder run", company_id="acme-corp"),
                 cohort="", manifest_version="", now="2026-08-14",
                 previous=None)
    assert d.quality_block["unknown_fields"] == []
    assert d.crossing_state == "MARKET_AVAILABLE_FOUNDER_UNAVAILABLE"
    blocks = d.market_block["blocks"]
    assert blocks["evidence"]["count"] == 2
    assert blocks["expectations"]["ids"] == ["x1"]


def test_an_unidentified_hidden_state_crosses_as_a_measured_zero(tmp_path):
    # The market engine reports this for 22 of 26 live companies: a hidden
    # state was tracked and its posterior is uniform. It must cross as "ran
    # and identified nothing", never as an unknown field and never as absent.
    _publish(tmp_path, _snapshot(hidden_state_refs={
        "state": "AVAILABLE", "ids": [], "count": 0, "unidentified": 1,
        "note": "1 hidden state(s) were tracked and none is identified: "
                "the posterior is uniform"}))
    from intent_engine.demo_dossier import assemble, founder_unavailable
    a = B.for_company("acme-corp", root=tmp_path, today="2026-08-14")
    d = assemble(a.snapshot,
                 founder_unavailable("no founder run", company_id="acme-corp"),
                 cohort="", manifest_version="", now="2026-08-14",
                 previous=None)
    assert d.quality_block["unknown_fields"] == []
    block = d.market_block["blocks"]["hidden_states"]
    assert block["state"] == "AVAILABLE"
    assert block["is_measured_zero"] is True
    assert "uniform" in block["note"]


def test_an_invalid_snapshot_never_reaches_a_dossier(tmp_path):
    _publish(tmp_path, _snapshot("globex-inc"), name="acme-corp")
    a = B.for_company("acme-corp", root=tmp_path, today="2026-08-14")
    assert a.snapshot is None or not a.usable
