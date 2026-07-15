from unittest.mock import MagicMock

from intent_engine.core.premortem_prediction_bridge import (
    BRIDGE_TOOL_SCHEMA,
    derive_predictions_from_premortem,
)
from intent_engine.core.prediction_ledger import _read_all
from intent_engine.core.schemas import FailureMode, RiskAudit


def _risk_audit():
    return RiskAudit(
        narrative_summary="You're explaining to your board in month 6 why burn outpaced revenue growth.",
        failure_modes=[
            FailureMode(description="Burn rate exceeds revenue growth for 2 consecutive quarters",
                        likelihood="likely", rationale="Current hiring plan outpaces projected revenue."),
            FailureMode(description="Key customer concentration causes a revenue cliff if one account churns",
                        likelihood="possible", rationale="Top account is 40% of revenue."),
            FailureMode(description="Competitor undercuts pricing before the next fundraise closes",
                        likelihood="unlikely", rationale="No signal of imminent competitive pricing action."),
        ],
        recommended_stress_tests=["Model a scenario where the top account churns mid-quarter."],
        key_sensitivity="Revenue concentration in one account",
    )


def _fake_client(predictions):
    client = MagicMock()
    client.call_tool.return_value = {"predictions": predictions}
    return client


# --- Bar (a): the drafting schema structurally lacks any record/include field


def test_bridge_tool_schema_has_no_id_or_include_or_record_field():
    """Model drafts, code decides -- checked directly, Stage-2-citation
    style: the schema the model sees literally cannot express "record
    this" or "here's my id" for anything."""
    prediction_item_schema = BRIDGE_TOOL_SCHEMA["properties"]["predictions"]["items"]["properties"]
    assert set(prediction_item_schema.keys()) == {"claim_text", "probability", "resolve_by"}
    for forbidden in ("id", "include", "record", "source", "entity_id"):
        assert forbidden not in prediction_item_schema


def test_derive_predictions_records_exactly_what_the_model_drafted(tmp_path):
    path = tmp_path / "ledger.db"
    client = _fake_client([
        {"claim_text": "Burn exceeds revenue growth for 2 quarters", "probability": 0.65, "resolve_by": "2027-01-15"},
        {"claim_text": "Top customer account churns", "probability": 0.2, "resolve_by": "2026-12-01"},
    ])

    predictions = derive_predictions_from_premortem("Acme Inc", _risk_audit(), client=client, ledger_path=path)

    assert len(predictions) == 2
    assert predictions[0].claim_text == "Burn exceeds revenue growth for 2 quarters"
    assert predictions[0].probability == 0.65
    assert predictions[0].source == "premortem"
    # NOT normalized -- prediction_ledger.py's entity_id is currently a raw
    # passthrough, unlike core/entity_memory.py's normalize_entity_id
    # convention. Real, adjacent inconsistency found while writing this
    # test; flagged in reports/overnight_trace.md rather than silently
    # patched into Task 1's already-committed file under this task's scope.
    assert predictions[0].entity_id == "Acme Inc"


def test_derive_predictions_actually_persists_to_the_ledger(tmp_path):
    """Real DB read, not just checking the return value -- confirms
    record_prediction() actually wrote rows, not just constructed objects."""
    path = tmp_path / "ledger.db"
    client = _fake_client([
        {"claim_text": "claim one", "probability": 0.5, "resolve_by": "2027-01-15"},
    ])
    derive_predictions_from_premortem("Acme Inc", _risk_audit(), client=client, ledger_path=path)

    rows = _read_all(path)
    assert len(rows) == 1
    assert rows[0].claim_text == "claim one"


def test_derive_predictions_states_the_real_current_date_in_the_prompt(tmp_path):
    """Real bug found in this task's own live verification: the model has
    no notion of "today" and drafted resolve_by dates already in the past.
    Fixed by stating the real date explicitly -- checked directly here,
    not just assumed fixed."""
    path = tmp_path / "ledger.db"
    client = _fake_client([{"claim_text": "x", "probability": 0.5, "resolve_by": "2027-01-15"}])
    derive_predictions_from_premortem("Acme Inc", _risk_audit(), client=client, ledger_path=path)

    user_message = client.call_tool.call_args.kwargs["user_message"]
    assert "Today's real date is" in user_message


def test_derive_predictions_rejects_a_non_future_resolve_by_date(tmp_path):
    """Code-level backstop, not trust in the prompt instruction alone: a
    candidate with a past or today's-date resolve_by must never be
    persisted, even if the model drafted one."""
    path = tmp_path / "ledger.db"
    client = _fake_client([
        {"claim_text": "stale claim", "probability": 0.5, "resolve_by": "2020-01-01"},
        {"claim_text": "valid claim", "probability": 0.5, "resolve_by": "2099-01-01"},
    ])
    predictions = derive_predictions_from_premortem("Acme Inc", _risk_audit(), client=client, ledger_path=path)

    assert len(predictions) == 1
    assert predictions[0].claim_text == "valid claim"


def test_derive_predictions_skips_a_malformed_resolve_by_date(tmp_path):
    path = tmp_path / "ledger.db"
    client = _fake_client([
        {"claim_text": "malformed", "probability": 0.5, "resolve_by": "not-a-date"},
        {"claim_text": "valid claim", "probability": 0.5, "resolve_by": "2099-01-01"},
    ])
    predictions = derive_predictions_from_premortem("Acme Inc", _risk_audit(), client=client, ledger_path=path)

    assert len(predictions) == 1
    assert predictions[0].claim_text == "valid claim"


def test_derive_predictions_feeds_the_real_failure_modes_into_the_prompt(tmp_path):
    path = tmp_path / "ledger.db"
    client = _fake_client([{"claim_text": "x", "probability": 0.5, "resolve_by": "2027-01-15"}])
    derive_predictions_from_premortem("Acme Inc", _risk_audit(), client=client, ledger_path=path)

    user_message = client.call_tool.call_args.kwargs["user_message"]
    assert "Burn rate exceeds revenue growth" in user_message
    assert "Key customer concentration" in user_message
