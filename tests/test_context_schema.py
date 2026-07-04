from intent_engine.core.entity_memory import EntityMemoryRecord, JsonlEntityMemoryWriter
from intent_engine.core.permissions import PermissionRegistry
from intent_engine.voice.context_schema import (
    CalendarContext,
    EntityHistorySummary,
    GmailContext,
    MockPersonalData,
    PersonalContext,
    build_personal_context,
)


def _record(entity_id, decision_text, goals, primary_priority, risk_tolerance):
    return EntityMemoryRecord(
        entity_id=entity_id,
        source="simulator",
        decision_text=decision_text,
        goals=goals,
        constraints=[],
        risk_tolerance=risk_tolerance,
        primary_priority=primary_priority,
    )


def test_build_personal_context_aggregates_across_records_and_uses_most_recent_for_snapshot_fields(tmp_path):
    path = tmp_path / "entity_memory.jsonl"
    writer = JsonlEntityMemoryWriter(path=path)

    # Written first (older, per JSONL append order) -- lowercase raw entity_id.
    writer.write(_record("acme inc", "Double headcount.", ["scale ahead of demand"], "survival", "medium"))
    # Written second (more recent) -- deliberately different casing, to keep
    # normalization coverage through this layer, not just in the writer's own tests.
    writer.write(_record("Acme Inc", "Raise a Series A.", ["extend runway"], "growth", "high"))

    ctx = build_personal_context("acme inc", MockPersonalData(), path=path)

    # Union across all records, not just the most recent.
    assert ctx.entity_history.recent_goals == ["scale ahead of demand", "extend runway"]
    assert ctx.entity_history.recent_decisions == ["Double headcount.", "Raise a Series A."]

    # Snapshot fields (risk_tolerance/primary_priority) come from the most recent
    # record, not the first-written one and not some blend of both.
    assert ctx.entity_history.primary_priority == "growth"
    assert ctx.entity_history.risk_tolerance == "high"


def test_build_personal_context_returns_empty_history_for_unknown_entity(tmp_path):
    path = tmp_path / "entity_memory.jsonl"
    writer = JsonlEntityMemoryWriter(path=path)
    writer.write(_record("acme inc", "Double headcount.", ["scale ahead of demand"], "survival", "medium"))

    ctx = build_personal_context("a company that has never used premortem", MockPersonalData(), path=path)

    assert ctx.entity_history.recent_goals == []
    assert ctx.entity_history.recent_decisions == []
    assert ctx.entity_history.risk_tolerance is None
    assert ctx.entity_history.primary_priority is None
    assert "No history yet" in ctx.to_prompt_text()


def test_build_personal_context_returns_empty_history_when_store_does_not_exist(tmp_path):
    path = tmp_path / "does_not_exist.jsonl"

    ctx = build_personal_context("anyone", MockPersonalData(), path=path)

    assert ctx.entity_history.recent_goals == []
    assert ctx.entity_history.primary_priority is None


def test_to_prompt_text_keeps_real_and_mock_sections_visibly_separate(tmp_path):
    path = tmp_path / "entity_memory.jsonl"
    writer = JsonlEntityMemoryWriter(path=path)
    writer.write(_record("acme inc", "Double headcount.", ["scale ahead of demand"], "survival", "medium"))

    mock = MockPersonalData(calendar_density="busy", important_relationships=["Sarah"])
    ctx = build_personal_context("acme inc", mock, path=path)
    text = ctx.to_prompt_text()

    assert "Known history (from entity memory):" in text
    assert "Assumed context (placeholder, not yet real data):" in text
    # Real content lands under the history section, not mixed into the mock one.
    history_section, mock_section = text.split("Assumed context")
    assert "scale ahead of demand" in history_section
    assert "Sarah" in mock_section


def test_build_personal_context_defaults_to_deny_by_default_registry(tmp_path):
    """No permission_registry supplied -- gmail_context/calendar_context must
    come back explicitly not_authorized, not silently empty and not crash."""
    path = tmp_path / "entity_memory.jsonl"

    ctx = build_personal_context("acme inc", MockPersonalData(), path=path)

    assert ctx.gmail_context.state == "not_authorized"
    assert ctx.gmail_context.messages == []
    assert ctx.gmail_context.message == "Not authorized to read Gmail."
    assert ctx.calendar_context.state == "not_authorized"
    assert ctx.calendar_context.events == []
    assert ctx.calendar_context.message == "Not authorized to read calendar."


def test_build_personal_context_fetches_when_authorized(tmp_path):
    path = tmp_path / "entity_memory.jsonl"
    registry = PermissionRegistry({"gmail_read": True, "calendar_read": True})

    ctx = build_personal_context("acme inc", MockPersonalData(), path=path, permission_registry=registry)

    assert ctx.gmail_context.state == "fetched"
    assert len(ctx.gmail_context.messages) == 3
    assert ctx.gmail_context.message is None
    assert ctx.calendar_context.state == "fetched"
    assert len(ctx.calendar_context.events) == 3
    assert ctx.calendar_context.message is None


def test_build_personal_context_domains_are_independent(tmp_path):
    """A calendar_read grant must not authorize gmail_read, and vice versa --
    same cross-domain isolation already proven for the act tier."""
    path = tmp_path / "entity_memory.jsonl"
    registry = PermissionRegistry({"calendar_read": True})

    ctx = build_personal_context("acme inc", MockPersonalData(), path=path, permission_registry=registry)

    assert ctx.calendar_context.state == "fetched"
    assert ctx.gmail_context.state == "not_authorized"


def test_to_prompt_text_surfaces_not_authorized_explicitly_not_silently(tmp_path):
    path = tmp_path / "entity_memory.jsonl"

    ctx = build_personal_context("acme inc", MockPersonalData(), path=path)
    text = ctx.to_prompt_text()

    assert "External reads (real, permission-gated, stub data):" in text
    assert "Gmail: Not authorized to read Gmail." in text
    assert "Calendar: Not authorized to read calendar." in text


def test_to_prompt_text_shows_fetched_data_when_authorized(tmp_path):
    path = tmp_path / "entity_memory.jsonl"
    registry = PermissionRegistry({"gmail_read": True, "calendar_read": True})

    ctx = build_personal_context("acme inc", MockPersonalData(), path=path, permission_registry=registry)
    text = ctx.to_prompt_text()

    assert "Gmail: 3 message(s)" in text
    assert "Calendar: 3 event(s)" in text


def test_skipped_for_cost_state_is_already_representable_no_schema_change_needed():
    """The third state exists in the schema today even though no pull-strategy
    produces it yet -- confirms a future cost-based gating/caching decision only
    needs to change WHICH strategy populates this field, not the field shape."""
    ctx = PersonalContext(
        entity_id="acme inc",
        entity_history=EntityHistorySummary(),
        mock_data=MockPersonalData(),
        gmail_context=GmailContext(state="skipped_for_cost"),
        calendar_context=CalendarContext(state="skipped_for_cost"),
    )

    text = ctx.to_prompt_text()
    assert "Gmail: skipped (not attempted this pass)." in text
    assert "Calendar: skipped (not attempted this pass)." in text
