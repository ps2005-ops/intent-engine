"""T005 mocked bars (docs/TASK4_SPEC_PROPOSAL.md, approved 2026-07-18):
bar (c) schema wall, bar (d) language wall, bar (e) rendering/silence/
provenance/additive-default coverage. Live bars (a)/(b) are Mac-side —
see T005_LIVE_RUNS.md; they are deliberately NOT mocked here
(mocked-as-live is a standing overnight wall)."""

from unittest.mock import MagicMock

import pytest

from intent_engine.core.mechanism_library import (
    RankedMechanism,
    TriggerCondition,
    load_mechanisms,
    match_mechanisms,
)
from intent_engine.simulator.mechanism_section import (
    EXTRACTION_TOOL_SCHEMA,
    SECTION_HEADER,
    assert_section_language_walls,
    compute_ranked_mechanisms,
    extract_decision_trigger_conditions,
    render_mechanism_section,
)
from intent_engine.simulator.pipeline import PremortemResult


# --- bar (c): schema wall ---------------------------------------------------

def test_schema_enum_is_exactly_the_closed_trigger_condition_set():
    enum = EXTRACTION_TOOL_SCHEMA["properties"]["trigger_conditions"]["items"]["enum"]
    assert set(enum) == set(TriggerCondition.__args__)
    assert len(enum) == len(TriggerCondition.__args__)


def test_schema_has_no_free_text_or_record_field():
    props = EXTRACTION_TOOL_SCHEMA["properties"]
    assert list(props.keys()) == ["trigger_conditions"]  # nothing else the model can say
    items = props["trigger_conditions"]["items"]
    assert items["type"] == "string" and "enum" in items  # enum-bound, no free text
    assert EXTRACTION_TOOL_SCHEMA["required"] == ["trigger_conditions"]


def test_extraction_prompt_hides_mechanism_library():
    # Information hiding: the prompt names conditions only -- never a
    # mechanism name from the library.
    from intent_engine.simulator.mechanism_section import EXTRACTION_SYSTEM_PROMPT
    for mechanism in load_mechanisms():
        assert mechanism.name not in EXTRACTION_SYSTEM_PROMPT
        assert mechanism.mechanism_id not in EXTRACTION_SYSTEM_PROMPT


# --- bar (d): language wall -------------------------------------------------

def test_rendered_section_for_every_library_mechanism_passes_walls():
    # Render ALL 17 real mechanisms -- the wall must hold against real data,
    # not just a friendly fixture.
    all_ranked = [
        RankedMechanism(mechanism=m, overlap_count=len(m.trigger_conditions), matched_conditions=list(m.trigger_conditions))
        for m in load_mechanisms()
    ]
    rendered = render_mechanism_section(all_ranked)
    assert rendered.startswith(SECTION_HEADER)
    assert_section_language_walls(rendered)  # raises on violation


def test_language_wall_catches_violations_and_word_boundaries():
    with pytest.raises(ValueError, match="language wall"):
        assert_section_language_walls("This will happen tomorrow")
    with pytest.raises(ValueError, match="language wall"):
        assert_section_language_walls("P=0.7 that spreads widen")
    with pytest.raises(ValueError, match="language wall"):
        assert_section_language_walls("you should buy now")
    # word-boundary: "buyers" must NOT trip the "buy" wall
    assert_section_language_walls("buyers relying on concentrated suppliers")


# --- bar (e): rendering / silence / provenance / additive default -----------

def _one_ranked():
    m = load_mechanisms()[0]
    return [RankedMechanism(mechanism=m, overlap_count=2, matched_conditions=list(m.trigger_conditions))]


def test_empty_match_renders_empty_string():
    assert render_mechanism_section([]) == ""


def test_rendered_line_carries_provenance_and_instance():
    ranked = _one_ranked()
    rendered = render_mechanism_section(ranked)
    m = ranked[0].mechanism
    assert m.name in rendered
    assert m.confidence_tier in rendered
    for cond in ranked[0].matched_conditions:
        assert cond in rendered  # matched-condition provenance, bar (d) of the plan
    inst = m.historical_instances[0]
    assert inst.case in rendered and str(inst.year) in rendered


def test_extract_uses_isolated_call_and_sorts(monkeypatch):
    client = MagicMock()
    client.call_tool.return_value = {"trigger_conditions": ["few_dominant_competitors", "concentrated_supplier_base"]}
    out = extract_decision_trigger_conditions("some decision", client=client)
    assert out == ["concentrated_supplier_base", "few_dominant_competitors"]
    assert client.call_tool.call_count == 1


def test_compute_ranked_mechanisms_silence_on_no_conditions():
    client = MagicMock()
    client.call_tool.return_value = {"trigger_conditions": []}
    assert compute_ranked_mechanisms("neutral decision", client=client) == []


def test_compute_ranked_mechanisms_matches_deterministically():
    client = MagicMock()
    client.call_tool.return_value = {
        "trigger_conditions": ["concentrated_supplier_base", "few_dominant_competitors"]}
    ranked = compute_ranked_mechanisms("supply decision", client=client)
    expected = match_mechanisms(["concentrated_supplier_base", "few_dominant_competitors"])
    assert [r.mechanism.mechanism_id for r in ranked] == [r.mechanism.mechanism_id for r in expected]


def test_premortem_result_additive_default_none():
    # Old 4-field construction still works; new field defaults to None.
    r = PremortemResult(intent="i", risk_audit="ra", scenario_set="s", elapsed_seconds=1.0)
    assert r.ranked_mechanisms is None
