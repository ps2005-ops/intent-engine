"""The market leg of the neutral read model.

The one thing this file exists to hold: `None` and `()` must never serialize
to the same block. A producer that emitted an empty list for a subsystem that
never ran would publish "we looked and found no causal result" — a finding
nobody made — and no amount of care on the consuming side could recover the
distinction once the bytes were written.
"""
from __future__ import annotations

import json

import pytest

from intent_engine.market import demo_snapshot_export as D
from intent_engine.market import strategic_publish as SP


def test_a_subsystem_that_did_not_run_is_unavailable_not_empty():
    payload = D.build_snapshot(company_id="acme", as_of="2026-08-11",
                               causal_results=None)
    block = payload["causal_result_refs"]
    assert block["state"] == D.REF_UNAVAILABLE
    assert block["count"] == 0
    assert block["note"]


def test_a_subsystem_that_ran_and_found_nothing_is_available_and_empty():
    payload = D.build_snapshot(company_id="acme", as_of="2026-08-11",
                               causal_results=[])
    block = payload["causal_result_refs"]
    assert block["state"] == D.REF_AVAILABLE
    assert block["count"] == 0


def test_the_two_absences_are_not_the_same_bytes():
    """The distinction has to survive serialization or it never existed."""
    absent = json.dumps(D.build_snapshot(
        company_id="a", as_of="2026-08-11", replay_episodes=None)
        ["replay_refs"], sort_keys=True)
    empty = json.dumps(D.build_snapshot(
        company_id="a", as_of="2026-08-11", replay_episodes=[])
        ["replay_refs"], sort_keys=True)
    assert absent != empty


def test_references_are_ids_and_never_bodies():
    payload = D.build_snapshot(
        company_id="acme", as_of="2026-08-11",
        beliefs=[{"belief_id": "b1", "proposition": "margins are widening",
                  "confidence": 0.8}])
    assert payload["belief_refs"]["ids"] == ["b1"]
    assert "margins are widening" not in json.dumps(payload)


def test_a_bounded_reference_list_still_reports_its_true_size():
    rows = [{"evidence_id": f"e{i}"} for i in range(D.MAX_REFS + 25)]
    payload = D.build_snapshot(company_id="acme", as_of="2026-08-11",
                               evidence_rows=rows)
    block = payload["evidence_reference_ids"]
    assert len(block["ids"]) == D.MAX_REFS
    assert block["count"] == D.MAX_REFS + 25


def test_independence_is_never_derived_from_the_row_count():
    payload = D.build_snapshot(
        company_id="acme", as_of="2026-08-11",
        evidence_rows=[{"evidence_id": f"e{i}"} for i in range(9)])
    assert payload["evidence_independence_state"] == "UNAVAILABLE"


@pytest.mark.parametrize("field", ["tenant_id", "data_population", "scope",
                                   "private_refs", "credential"])
def test_this_side_may_never_publish_an_authority_field(field):
    with pytest.raises(D.SnapshotLeak):
        D.build_snapshot(company_id="acme", as_of="2026-08-11",
                         source_health={"state": "AVAILABLE", field: "x"})


def test_a_trading_internal_is_refused_on_the_way_out():
    with pytest.raises(D.SnapshotLeak):
        D.build_snapshot(company_id="acme", as_of="2026-08-11",
                         learning_summary={"note": "sharpe of 1.4 this cycle"})


def test_a_stated_absence_is_publishable_and_says_why():
    payload = D.unavailable("ghost-co", "never analysed", as_of="2026-08-11")
    assert payload["availability"] == "UNAVAILABLE"
    assert payload["unavailable_reason"] == "never analysed"
    assert payload["contract_version"] == D.SNAPSHOT_VERSION


def test_an_unknown_population_falls_to_synthetic_not_real():
    """The safe direction. A snapshot whose population nobody declared must
    not be joined to real internal data as though it were real evidence."""
    payload = D.build_snapshot(company_id="acme", as_of="2026-08-11",
                               market_population="INVENTED")
    assert payload["market_population"] == D.SYNTHETIC_MARKET


def test_the_runtime_sha_field_name_matches_what_provenance_emits():
    """A wrong key here is invisible: the snapshot publishes an empty sha,
    the dossier records no market runtime, and nothing raises."""
    from intent_engine.market.runtime_provenance import provenance
    assert "runtime_git_sha" in provenance()
    assert SP._runtime_sha() == provenance()["runtime_git_sha"]


def test_a_snapshot_is_written_where_the_founder_side_looks(tmp_path):
    payload = D.build_snapshot(company_id="acme-corp", as_of="2026-08-11")
    path = D.write_snapshot(payload, root=tmp_path)
    assert path == tmp_path / D.EXPORT_DIR / "acme-corp.json"
    assert json.loads(path.read_text())["company_id"] == "acme-corp"
