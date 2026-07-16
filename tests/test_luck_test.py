from intent_engine.core.entity_memory import EntityMemoryRecord, SqliteEntityMemoryWriter
from intent_engine.simulator.luck_test import LuckTestAnalyzer, compute_diversification_signal


class FakeLLMClient:
    """Stands in for LLMClient so this test never touches the network or needs an API key."""

    def __init__(self, canned_response):
        self.canned_response = canned_response
        self.last_call_kwargs = None

    def call_tool(self, **kwargs):
        self.last_call_kwargs = kwargs
        return self.canned_response


def _record(entity_id, goals, primary_priority=None):
    return EntityMemoryRecord(
        entity_id=entity_id,
        source="simulator",
        decision_text="some decision",
        goals=goals,
        constraints=[],
        risk_tolerance="medium",
        primary_priority=primary_priority,
    )


def test_diversification_signal_insufficient_history_when_no_records(tmp_path):
    path = tmp_path / "entity_memory.jsonl"
    assert compute_diversification_signal("Acme Inc", path=path) == "insufficient_history"


def test_diversification_signal_single_bet_with_one_record(tmp_path):
    path = tmp_path / "entity_memory.jsonl"
    writer = SqliteEntityMemoryWriter(path=path)
    writer.write(_record("Acme Inc", ["extend runway"], primary_priority="survival"))

    assert compute_diversification_signal("Acme Inc", path=path) == "single_bet"


def test_diversification_signal_single_bet_when_records_share_priority_and_goals(tmp_path):
    """Two records, same underlying bet reiterated -- must not count as multiple_bets."""
    path = tmp_path / "entity_memory.jsonl"
    writer = SqliteEntityMemoryWriter(path=path)
    writer.write(_record("Acme Inc", ["extend runway", "cut burn"], primary_priority="survival"))
    writer.write(_record("Acme Inc", ["extend runway"], primary_priority="survival"))

    assert compute_diversification_signal("Acme Inc", path=path) == "single_bet"


def test_diversification_signal_multiple_bets_on_differing_priority(tmp_path):
    path = tmp_path / "entity_memory.jsonl"
    writer = SqliteEntityMemoryWriter(path=path)
    writer.write(_record("Acme Inc", ["extend runway"], primary_priority="survival"))
    writer.write(_record("Acme Inc", ["capture market share"], primary_priority="growth"))

    assert compute_diversification_signal("Acme Inc", path=path) == "multiple_bets"


def test_diversification_signal_multiple_bets_on_disjoint_goals_same_priority(tmp_path):
    """No primary_priority difference, but zero goal overlap -- still counts as
    clearly different bets, per the "different priority OR clearly different
    goals" rule."""
    path = tmp_path / "entity_memory.jsonl"
    writer = SqliteEntityMemoryWriter(path=path)
    writer.write(_record("Acme Inc", ["expand into APAC"], primary_priority="growth"))
    writer.write(_record("Acme Inc", ["launch a loyalty program"], primary_priority="growth"))

    assert compute_diversification_signal("Acme Inc", path=path) == "multiple_bets"


def test_diversification_signal_is_entity_scoped(tmp_path):
    """Records for a different entity must not count toward this entity's signal."""
    path = tmp_path / "entity_memory.jsonl"
    writer = SqliteEntityMemoryWriter(path=path)
    writer.write(_record("Acme Inc", ["extend runway"], primary_priority="survival"))
    writer.write(_record("Other Co", ["capture market share"], primary_priority="growth"))

    assert compute_diversification_signal("Acme Inc", path=path) == "single_bet"


def test_luck_test_analyzer_combines_llm_output_with_computed_diversification(tmp_path):
    path = tmp_path / "entity_memory.jsonl"
    writer = SqliteEntityMemoryWriter(path=path)
    writer.write(_record("Acme Inc", ["extend runway"], primary_priority="survival"))
    writer.write(_record("Acme Inc", ["capture market share"], primary_priority="growth"))

    fake_client = FakeLLMClient({
        "demand_durability": "cyclical_hype",
        "timing_confidence": "low",
        "rationale": "The decision text describes a trend-driven spike with no durable demand signal.",
    })
    analyzer = LuckTestAnalyzer(client=fake_client, entity_memory_path=path)

    result = analyzer.run("Ride the current viral trend into a new product line.", "Acme Inc")

    assert result.demand_durability == "cyclical_hype"
    assert result.timing_confidence == "low"
    assert result.diversification_signal == "multiple_bets"  # computed, not from the LLM response
    assert "trend-driven" in result.rationale
    assert fake_client.last_call_kwargs["tool_name"] == "record_luck_test"


def test_luck_test_analyzer_does_not_call_llm_for_diversification_signal(tmp_path):
    """The LLM is only ever asked for demand_durability/timing_confidence/rationale
    -- diversification_signal must never appear in the tool schema or system
    prompt sent to the model."""
    path = tmp_path / "entity_memory.jsonl"
    fake_client = FakeLLMClient({
        "demand_durability": "unclear",
        "timing_confidence": "medium",
        "rationale": "Not enough signal either way.",
    })
    analyzer = LuckTestAnalyzer(client=fake_client, entity_memory_path=path)

    analyzer.run("Some decision.", "Acme Inc")

    schema_properties = fake_client.last_call_kwargs["input_schema"]["properties"]
    assert "diversification_signal" not in schema_properties
    assert "diversification_signal" not in fake_client.last_call_kwargs["system"]
