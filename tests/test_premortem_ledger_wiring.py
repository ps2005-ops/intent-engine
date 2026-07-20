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
