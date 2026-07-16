"""Tests for the `premortem` CLI's argparse layer and main() wiring.

Prior to this file, nothing in the test suite called cli.main() directly --
only the argparse-adjacent functions were reachable via unit tests on
run_premortem/pipeline. This exercises main() itself: required-flag
enforcement, --input file loading, report formatting, and the
entity-memory write that happens after run_premortem() returns.

The underlying LLM call is stubbed via a patched run_premortem (same
boundary test_analysis.py stubs at, one layer up) so these tests never
need ANTHROPIC_API_KEY or hit the network -- everything else in main()
(argparse, _load_from_args, formatting, the entity-memory write) runs for
real.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from intent_engine.core.entity_memory import SqliteEntityMemoryWriter, read_records
from intent_engine.core.schemas import FailureMode, RiskAudit, StructuredIntent
from intent_engine.simulator.cli import _build_parser, main
from intent_engine.simulator.pipeline import PremortemResult
from intent_engine.simulator.schemas import Scenario, ScenarioSet

FIXTURES_PATH = Path(__file__).parent / "fixtures" / "business_decisions.json"


def _load_fixture(fixture_id: str) -> dict:
    with open(FIXTURES_PATH) as f:
        fixtures = json.load(f)
    return next(fx for fx in fixtures if fx["id"] == fixture_id)


def _canned_result() -> PremortemResult:
    intent = StructuredIntent(
        decision_summary="Expand into a new market with significant capital.",
        goals=["establish market presence"],
        constraints=["18-month timeline", "$2M budget"],
        risk_tolerance="medium",
    )
    audit = RiskAudit(
        narrative_summary="You're in the board meeting eight months from now explaining the shortfall.",
        failure_modes=[
            FailureMode(description="Runway runs out before expansion pays off.", likelihood="likely", rationale="Runway is short."),
            FailureMode(description="Local competitor undercuts pricing.", likelihood="possible", rationale="Competitors have local presence."),
            FailureMode(description="Team overextends.", likelihood="possible", rationale="Team is small for two markets."),
        ],
        recommended_stress_tests=["Model a 6-month funding delay."],
        key_sensitivity="Whether the $2M closes on schedule.",
    )
    scenario_set = ScenarioSet(
        primary_priority="growth",
        scenarios=[
            Scenario(name="upside", tag="strong APAC traction", key_deltas="+$500k ARR"),
            Scenario(name="base", tag="as planned", key_deltas="flat runway"),
            Scenario(name="downside", tag="expansion stalls", key_deltas="-2 months runway"),
        ],
    )
    return PremortemResult(intent=intent, risk_audit=audit, scenario_set=scenario_set, elapsed_seconds=1.23)


# --- argparse layer ---------------------------------------------------------


def test_build_parser_requires_entity_id():
    parser = _build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--decision", "Do a thing"])


def test_main_requires_entity_id_flag(capsys):
    with pytest.raises(SystemExit):
        main(["--decision", "Do a thing"])


def test_main_requires_input_or_decision():
    with pytest.raises(SystemExit):
        main(["--entity-id", "Acme Inc"])


# --- real end-to-end invocation (LLM call stubbed, everything else real) --


def test_main_end_to_end_writes_entity_memory(tmp_path, capsys):
    fixture = _load_fixture("asia-expansion")
    input_path = tmp_path / "decision.json"
    input_path.write_text(json.dumps({"decision_text": fixture["decision_text"], "context": fixture["context"]}))

    db_path = tmp_path / "entity_memory.db"
    canned = _canned_result()

    with patch("intent_engine.simulator.cli.run_premortem", return_value=canned) as mock_run, \
         patch("intent_engine.simulator.cli.SqliteEntityMemoryWriter", lambda: SqliteEntityMemoryWriter(path=db_path)):
        exit_code = main(["--input", str(input_path), "--entity-id", "Acme Inc"])

    assert exit_code == 0

    mock_run.assert_called_once()
    called_decision_text, called_context = mock_run.call_args[0]
    assert called_decision_text == fixture["decision_text"]
    assert called_context.market == fixture["context"]["market"]

    records = read_records("Acme Inc", path=db_path)
    assert len(records) == 1
    record = records[0]
    assert record.entity_id == "acme inc"
    assert record.source == "simulator"
    assert record.decision_text == fixture["decision_text"]
    assert record.goals == canned.intent.goals
    assert record.constraints == canned.intent.constraints
    assert record.risk_tolerance == "medium"
    assert record.primary_priority == "growth"

    captured = capsys.readouterr()
    assert "PRIMARY PRIORITY: growth" in captured.out
    assert "Saved to entity memory: acme inc" in captured.err


def test_main_json_flag_prints_valid_json(tmp_path, capsys):
    fixture = _load_fixture("series-a-raise")
    input_path = tmp_path / "decision.json"
    input_path.write_text(json.dumps({"decision_text": fixture["decision_text"], "context": fixture["context"]}))

    db_path = tmp_path / "entity_memory.db"
    canned = _canned_result()

    with patch("intent_engine.simulator.cli.run_premortem", return_value=canned), \
         patch("intent_engine.simulator.cli.SqliteEntityMemoryWriter", lambda: SqliteEntityMemoryWriter(path=db_path)):
        exit_code = main(["--input", str(input_path), "--entity-id", "Beta Co", "--json"])

    assert exit_code == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["risk_audit"]["key_sensitivity"] == canned.risk_audit.key_sensitivity
    assert payload["scenario_set"]["primary_priority"] == "growth"
