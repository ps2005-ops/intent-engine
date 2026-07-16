import pytest

from intent_engine.core.entity_memory import EntityMemoryRecord, SqliteEntityMemoryWriter
from intent_engine.core.pattern_watcher import DetectedPattern
from intent_engine.core.suggestion import (
    accept_suggestion,
    decline_suggestion,
    generate_suggestion,
    surface_next_suggestion,
)


def _pattern(confidence="medium", occurrence_count=5, record_ids=None):
    return DetectedPattern(
        entity_id="Acme Inc",
        pattern_type="recurring_message",
        description="You send a similar message to Sarah on 5 separate days, typically around 7pm-9pm (UTC). "
        "Wording similarity across these instances: 62%.",
        occurrence_count=occurrence_count,
        first_seen="2026-06-01T19:00:00+00:00",
        last_seen="2026-06-05T19:00:00+00:00",
        confidence=confidence,
        supporting_record_ids=record_ids or ["r1", "r2", "r3", "r4", "r5"],
    )


def _voice_record(entity_id, decision_text, timestamp):
    return EntityMemoryRecord(
        entity_id=entity_id,
        source="voice",
        decision_text=decision_text,
        goals=[],
        constraints=[],
        timestamp=timestamp,
        salience="low",
    )


# --- generate_suggestion ---------------------------------------------------


def test_generate_suggestion_low_confidence_is_hedged():
    suggestion = generate_suggestion(_pattern(confidence="low"))
    assert "hard to say for sure" in suggestion.suggestion_text
    assert suggestion.status == "pending"


def test_generate_suggestion_high_confidence_is_more_assertive_but_still_a_question():
    suggestion = generate_suggestion(_pattern(confidence="high"))
    assert "clear, consistent pattern" in suggestion.suggestion_text
    assert "hard to say for sure" not in suggestion.suggestion_text


def test_generate_suggestion_wording_genuinely_differs_by_confidence():
    low = generate_suggestion(_pattern(confidence="low")).suggestion_text
    medium = generate_suggestion(_pattern(confidence="medium")).suggestion_text
    high = generate_suggestion(_pattern(confidence="high")).suggestion_text
    assert len({low, medium, high}) == 3  # all three genuinely different, not the same text with a label swapped


def test_generate_suggestion_always_ends_with_a_question_never_an_assumed_action():
    for confidence in ("low", "medium", "high"):
        text = generate_suggestion(_pattern(confidence=confidence)).suggestion_text
        assert text.rstrip().endswith("?")
        assert "I've started" not in text
        assert "I've begun" not in text


# --- surface_next_suggestion / accept / decline ----------------------------


def test_surface_next_suggestion_creates_one_when_a_pattern_exists(tmp_path):
    entity_path = tmp_path / "entity_memory.jsonl"
    suggestions_path = tmp_path / "suggestions.jsonl"
    writer = SqliteEntityMemoryWriter(path=entity_path)

    from datetime import datetime, timedelta, timezone

    for days_ago in range(5, 0, -1):
        dt = (datetime.now(timezone.utc) - timedelta(days=days_ago)).replace(hour=19, minute=0, second=0, microsecond=0)
        writer.write(_voice_record("Acme Inc", "email Sarah the daily standup notes", dt.isoformat()))

    record = surface_next_suggestion(
        "Acme Inc", entity_memory_path=entity_path, suggestions_path=suggestions_path, min_occurrences=3
    )

    assert record is not None
    assert record.status == "pending"
    assert record.entity_id == "Acme Inc"
    assert "Sarah" in record.suggestion_text or "sarah" in record.suggestion_text.lower()


def test_surface_next_suggestion_returns_none_when_nothing_detected(tmp_path):
    entity_path = tmp_path / "entity_memory.jsonl"
    suggestions_path = tmp_path / "suggestions.jsonl"

    record = surface_next_suggestion("Acme Inc", entity_memory_path=entity_path, suggestions_path=suggestions_path)

    assert record is None


def test_surface_next_suggestion_never_stacks_a_second_pending_suggestion(tmp_path):
    """Real product requirement: a person must never have more than one
    unresolved suggestion at once."""
    entity_path = tmp_path / "entity_memory.jsonl"
    suggestions_path = tmp_path / "suggestions.jsonl"
    writer = SqliteEntityMemoryWriter(path=entity_path)

    from datetime import datetime, timedelta, timezone

    for days_ago in range(5, 0, -1):
        dt = (datetime.now(timezone.utc) - timedelta(days=days_ago)).replace(hour=19, minute=0, second=0, microsecond=0)
        writer.write(_voice_record("Acme Inc", "email Sarah the daily standup notes", dt.isoformat()))

    first = surface_next_suggestion(
        "Acme Inc", entity_memory_path=entity_path, suggestions_path=suggestions_path, min_occurrences=3
    )
    second = surface_next_suggestion(
        "Acme Inc", entity_memory_path=entity_path, suggestions_path=suggestions_path, min_occurrences=3
    )

    assert first is not None
    assert second is None  # still pending -- must not create a second one


def test_surface_next_suggestion_does_not_resurface_a_declined_pattern(tmp_path):
    entity_path = tmp_path / "entity_memory.jsonl"
    suggestions_path = tmp_path / "suggestions.jsonl"
    writer = SqliteEntityMemoryWriter(path=entity_path)

    from datetime import datetime, timedelta, timezone

    for days_ago in range(5, 0, -1):
        dt = (datetime.now(timezone.utc) - timedelta(days=days_ago)).replace(hour=19, minute=0, second=0, microsecond=0)
        writer.write(_voice_record("Acme Inc", "email Sarah the daily standup notes", dt.isoformat()))

    first = surface_next_suggestion(
        "Acme Inc", entity_memory_path=entity_path, suggestions_path=suggestions_path, min_occurrences=3
    )
    decline_suggestion(first.suggestion_id, "Acme Inc", path=suggestions_path)

    again = surface_next_suggestion(
        "Acme Inc", entity_memory_path=entity_path, suggestions_path=suggestions_path, min_occurrences=3
    )

    assert again is None  # same underlying pattern, already declined


def test_accept_suggestion_produces_a_gated_draft_only_spec(tmp_path):
    entity_path = tmp_path / "entity_memory.jsonl"
    suggestions_path = tmp_path / "suggestions.jsonl"
    writer = SqliteEntityMemoryWriter(path=entity_path)

    from datetime import datetime, timedelta, timezone

    for days_ago in range(5, 0, -1):
        dt = (datetime.now(timezone.utc) - timedelta(days=days_ago)).replace(hour=19, minute=0, second=0, microsecond=0)
        writer.write(_voice_record("Acme Inc", "email Sarah the daily standup notes", dt.isoformat()))

    pending = surface_next_suggestion(
        "Acme Inc", entity_memory_path=entity_path, suggestions_path=suggestions_path, min_occurrences=3
    )

    accepted = accept_suggestion(pending.suggestion_id, "Acme Inc", path=suggestions_path)

    assert accepted.status == "accepted"
    assert accepted.resolved_at is not None
    assert accepted.task_agent_spec is not None
    assert accepted.task_agent_spec.action == "draft_only"
    assert accepted.task_agent_spec.gated is True  # nothing here authorizes real sending
    assert accepted.task_agent_spec.source_pattern_id == pending.pattern.pattern_id


def test_accept_suggestion_raises_if_not_pending(tmp_path):
    suggestions_path = tmp_path / "suggestions.jsonl"
    entity_path = tmp_path / "entity_memory.jsonl"
    writer = SqliteEntityMemoryWriter(path=entity_path)

    from datetime import datetime, timedelta, timezone

    for days_ago in range(5, 0, -1):
        dt = (datetime.now(timezone.utc) - timedelta(days=days_ago)).replace(hour=19, minute=0, second=0, microsecond=0)
        writer.write(_voice_record("Acme Inc", "email Sarah the daily standup notes", dt.isoformat()))

    pending = surface_next_suggestion(
        "Acme Inc", entity_memory_path=entity_path, suggestions_path=suggestions_path, min_occurrences=3
    )
    decline_suggestion(pending.suggestion_id, "Acme Inc", path=suggestions_path)

    with pytest.raises(ValueError):
        accept_suggestion(pending.suggestion_id, "Acme Inc", path=suggestions_path)
