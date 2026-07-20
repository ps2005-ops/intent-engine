"""T006 bars as offline tests (docs/TASK5_WIRING_SPEC_PROPOSAL.md,
approved). Bar (a) — the real live run with recorded rows — needs live
calls and runs on the Mac (<=6-call budget); its full code path is
exercised here with a fake client + fake analyzer. Bars (b)-(e) are fully
asserted offline: schema wall, additive default, append-only/no-backfill,
CLI confirmation language, zero regressions (suite)."""

import re
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from intent_engine.core.premortem_prediction_bridge import BRIDGE_TOOL_SCHEMA
from intent_engine.core.prediction_ledger import list_predictions, record_prediction
from intent_engine.core.schemas import FailureMode, RiskAudit
from intent_engine.simulator.cli import _build_parser, _record_confirmation
from intent_engine.simulator.pipeline import PremortemResult, run_premortem


def _risk_audit():
    return RiskAudit(
        narrative_summary="You're explaining to your board in month 6 why burn outpaced revenue growth.",
        failure_modes=[
            FailureMode(description="Burn rate exceeds revenue growth for 2 consecutive quarters",
                        likelihood="likely", rationale="Current hiring plan outpaces projected revenue."),
        ],
        recommended_stress_tests=["Model a scenario where the top account churns mid-quarter."],
        key_sensitivity="Revenue concentration in one account",
    )


def _fake_analyzer():
    analyzer = MagicMock()
    analyzer.run.return_value = SimpleNamespace(
        intent=MagicMock(), risk_audit=_risk_audit(), scenario_set=MagicMock())
    return analyzer


def _fake_bridge_client(predictions):
    client = MagicMock()
    client.call_tool.return_value = {"predictions": predictions}
    return client


# --- bar (b): schema wall (restated per spec; structural) -------------------

def test_bridge_schema_still_has_no_record_or_include_field():
    item = BRIDGE_TOOL_SCHEMA["properties"]["predictions"]["items"]["properties"]
    assert set(item.keys()) == {"claim_text", "probability", "resolve_by"}
    for forbidden in ("id", "include", "record", "source", "entity_id"):
        assert forbidden not in item


# --- bar (c): additive default ----------------------------------------------

def test_default_run_records_nothing_and_field_is_none(tmp_path):
    ledger = tmp_path / "ledger.db"
    result = run_premortem("Hire a 4-person sales team", MagicMock(),
                           analyzer=_fake_analyzer(), bridge_ledger_path=ledger)
    assert result.ledgered_predictions is None
    assert list_predictions(path=ledger) == []


def test_premortem_result_constructs_with_original_fields_only():
    r = PremortemResult(intent=MagicMock(), risk_audit=_risk_audit(),
                        scenario_set=MagicMock(), elapsed_seconds=1.0)
    assert r.ranked_mechanisms is None and r.ledgered_predictions is None


def test_bridge_client_without_entity_id_is_an_explicit_error():
    with pytest.raises(ValueError, match="bridge_entity_id"):
        run_premortem("Some decision", MagicMock(), analyzer=_fake_analyzer(),
                      bridge_client=_fake_bridge_client([]))


# --- bar (a)-shaped mocked end-to-end + bar (d): append-only ----------------

def test_wired_run_records_source_premortem_rows_append_only(tmp_path):
    ledger = tmp_path / "ledger.db"
    # a pre-existing row the run must not touch (no-backfill / no-mutate):
    existing = record_prediction(
        source="market", entity_id="pre", claim_text="existing row",
        probability=0.5, resolve_by="2027-03-01", path=ledger,
        resolution_rule={"type": "pct_change", "symbol": "SPY", "op": ">=",
                         "value": 0.02, "window_days": 30},
        resolution_source="tiingo",
    )
    client = _fake_bridge_client([
        {"claim_text": "Burn exceeds revenue growth for 2 quarters",
         "probability": 0.65, "resolve_by": "2027-01-15"},
        {"claim_text": "Sales-team payback misses the 2-quarter plan",
         "probability": 0.4, "resolve_by": "2027-02-01"},
    ])

    result = run_premortem("Hire a 4-person sales team", MagicMock(),
                           analyzer=_fake_analyzer(), bridge_client=client,
                           bridge_entity_id="acme", bridge_ledger_path=ledger)

    assert result.ledgered_predictions is not None
    assert len(result.ledgered_predictions) == 2
    rows = list_predictions(source="premortem", path=ledger)
    assert len(rows) == 2
    assert all(r.source == "premortem" and 0 < r.probability < 1 for r in rows)
    # append-only: the pre-existing row is intact and untouched
    market = list_predictions(source="market", path=ledger)
    assert len(market) == 1
    assert market[0].claim_text == existing.claim_text
    assert market[0].created_at == existing.created_at
    # exactly one isolated drafting call
    assert client.call_tool.call_count == 1


# --- bar (e): CLI confirmation language + flag default ----------------------

def test_record_predictions_flag_exists_and_defaults_off():
    args = _build_parser().parse_args(["--entity-id", "acme", "--decision", "x"])
    assert args.record_predictions is False


def test_confirmation_line_carries_no_forecast_language():
    line = _record_confirmation(3).lower()
    for pattern in (r"\bwill\b", r"\bforecast\b", r"\baccurate\b", r"\baccuracy\b", r"p="):
        assert not re.search(pattern, line), pattern
    assert "source=premortem" in line


# =============================================================================
# T010 Slice 1B bars (V1_COMPLETION_ROADMAP.md Part E): decision_id
# integration. One accepted intake -> one Decision Record -> every ledger
# row carries the same decision_id -> retry creates zero duplicates.
# =============================================================================

import json

from intent_engine.core.decision_record import DecisionService


def _svc(tmp_path):
    return DecisionService(str(tmp_path / "decisions.db"))


_CANDIDATES = [
    {"claim_text": "Burn exceeds revenue growth for 2 quarters",
     "probability": 0.65, "resolve_by": "2027-01-15"},
    {"claim_text": "Sales-team payback misses the 2-quarter plan",
     "probability": 0.4, "resolve_by": "2027-02-01"},
]


def test_bridge_schema_still_has_no_decision_field():
    """The model can never see or set decision identity -- stamping is code."""
    item = BRIDGE_TOOL_SCHEMA["properties"]["predictions"]["items"]["properties"]
    for forbidden in ("decision_id", "decision_key", "decision"):
        assert forbidden not in item


def test_ledger_decision_id_is_additive_and_filterable(tmp_path):
    ledger = tmp_path / "ledger.db"
    old = record_prediction(source="manual", entity_id="e", claim_text="old row",
                            probability=0.5, resolve_by="2027-01-01", path=ledger)
    did = "0" * 26
    new = record_prediction(source="premortem", entity_id="e", claim_text="new row",
                            probability=0.6, resolve_by="2027-01-01", path=ledger,
                            decision_id=did)
    assert old.decision_id is None          # pre-record rows unaffected
    assert new.decision_id == did
    rows = list_predictions(path=ledger, decision_id=did)
    assert [r.claim_text for r in rows] == ["new row"]


def test_wired_run_creates_one_record_and_stamps_every_row(tmp_path):
    """Bar (c): one decision_id across the record, its events, and ALL its
    ledger rows -- verified by direct read."""
    ledger = tmp_path / "ledger.db"
    svc = _svc(tmp_path)
    result = run_premortem(
        "Hire a 4-person sales team", MagicMock(), analyzer=_fake_analyzer(),
        bridge_client=_fake_bridge_client(_CANDIDATES),
        bridge_entity_id="acme", bridge_ledger_path=ledger,
        decision_service=svc, decision_intake_key="intake-1")

    rec = result.decision_record
    assert rec is not None and len(rec.decision_id) == 26
    rows = list_predictions(path=ledger, decision_id=rec.decision_id)
    assert len(rows) == 2 == len(result.ledgered_predictions)
    assert {r.decision_id for r in rows} == {rec.decision_id}
    # ordered event flow: DecisionCreated then RecommendationIssued
    types = [e["event_type"] for e in svc.get_events(rec.decision_id)]
    assert types == ["DecisionCreated", "RecommendationIssued"]
    # the entity is linked as subject
    assert svc.get_entities(rec.decision_id) == [
        {"entity_id": "acme", "relationship_type": "subject"}]


def test_retry_same_intake_key_creates_zero_duplicates(tmp_path):
    """Bar (b): reprocessing the same accepted intake reuses the record and
    creates zero duplicate records, events, or ledger rows -- and makes zero
    additional drafting calls."""
    ledger = tmp_path / "ledger.db"
    svc = _svc(tmp_path)
    client = _fake_bridge_client(_CANDIDATES)
    kwargs = dict(analyzer=_fake_analyzer(), bridge_client=client,
                  bridge_entity_id="acme", bridge_ledger_path=ledger,
                  decision_service=svc, decision_intake_key="intake-1")
    r1 = run_premortem("Hire a 4-person sales team", MagicMock(), **kwargs)
    r2 = run_premortem("Hire a 4-person sales team", MagicMock(), **kwargs)

    assert r1.decision_record.decision_id == r2.decision_record.decision_id
    assert r1.decision_record.decision_key == r2.decision_record.decision_key
    rows = list_predictions(path=ledger, decision_id=r1.decision_record.decision_id)
    assert len(rows) == 2                          # zero duplicate ledger rows
    assert client.call_tool.call_count == 1        # zero extra drafting calls
    types = [e["event_type"] for e in svc.get_events(r1.decision_record.decision_id)]
    assert types == ["DecisionCreated", "RecommendationIssued"]   # no duplicate events
    assert [p.id for p in r2.ledgered_predictions] == [p.id for p in rows]


def test_failed_analysis_appends_typed_event_and_preserves_record(tmp_path):
    svc = _svc(tmp_path)
    analyzer = MagicMock()
    analyzer.run.side_effect = RuntimeError("provider timeout")
    with pytest.raises(RuntimeError):
        run_premortem("Hire a 4-person sales team", MagicMock(), analyzer=analyzer,
                      decision_service=svc, decision_intake_key="intake-x")
    # the record survives; the failure is a typed, appended fact
    import sqlite3 as _sq
    con = _sq.connect(str(svc.db_path))
    try:
        did = con.execute("SELECT decision_id FROM decision_records").fetchone()[0]
    finally:
        con.close()
    types = [e["event_type"] for e in svc.get_events(did)]
    assert types == ["DecisionCreated", "AnalysisFailed"]
    payload = svc.get_events(did)[-1]["payload"]
    assert payload == {"error_type": "RuntimeError"}   # type only, no raw text


def test_failed_bridge_appends_typed_event_keeps_earlier_facts(tmp_path):
    ledger = tmp_path / "ledger.db"
    svc = _svc(tmp_path)
    client = MagicMock()
    client.call_tool.side_effect = RuntimeError("api down")
    with pytest.raises(RuntimeError):
        run_premortem("Hire a 4-person sales team", MagicMock(),
                      analyzer=_fake_analyzer(), bridge_client=client,
                      bridge_entity_id="acme", bridge_ledger_path=ledger,
                      decision_service=svc, decision_intake_key="intake-y")
    import sqlite3 as _sq
    con = _sq.connect(str(svc.db_path))
    try:
        did = con.execute("SELECT decision_id FROM decision_records").fetchone()[0]
    finally:
        con.close()
    types = [e["event_type"] for e in svc.get_events(did)]
    # earlier facts (creation + recommendation) are NOT erased by the failure
    assert types == ["DecisionCreated", "RecommendationIssued", "PredictionLoggingFailed"]
    assert list_predictions(path=ledger) == []     # nothing half-written


def test_no_raw_intake_text_in_any_event_payload(tmp_path):
    secret = "CONFIDENTIAL: acquire BetaCorp for $9.9M before August"
    svc = _svc(tmp_path)
    result = run_premortem(secret, MagicMock(), analyzer=_fake_analyzer(),
                           decision_service=svc, decision_intake_key="intake-z")
    blob = json.dumps([e["payload"] for e in
                       svc.get_events(result.decision_record.decision_id)])
    assert secret not in blob and "CONFIDENTIAL" not in blob and "BetaCorp" not in blob


def test_decision_record_flag_exists_and_defaults_off():
    args = _build_parser().parse_args(["--entity-id", "acme", "--decision", "x"])
    assert args.decision_record is False


def test_decision_record_default_run_unchanged(tmp_path):
    """No service passed -> additive field None, nothing else changes."""
    result = run_premortem("Hire a 4-person sales team", MagicMock(),
                           analyzer=_fake_analyzer())
    assert result.decision_record is None
