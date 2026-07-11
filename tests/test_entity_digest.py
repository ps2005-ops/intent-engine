from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from intent_engine.core.entity_digest import (
    DIGEST_ITEM_TOOL_SCHEMA,
    check_for_digest,
    should_check_for_digest,
)
from intent_engine.core.entity_memory import EntityMemoryRecord, JsonlEntityMemoryWriter
from intent_engine.core.entity_summary import generate_weekly_summary


def _voice_record(entity_id, decision_text, timestamp):
    return EntityMemoryRecord(
        entity_id=entity_id, source="voice", decision_text=decision_text,
        goals=[], constraints=[], timestamp=timestamp,
    )


def _seed(entity_memory_path, entity_id, records):
    writer = JsonlEntityMemoryWriter(path=entity_memory_path)
    for r in records:
        writer.write(r)


def _fake_client(digest_text="A real observation."):
    client = MagicMock()
    client.call_tool.return_value = {"digest_text": digest_text}
    return client


def _fake_summary_client(summary_text="period summary"):
    client = MagicMock()
    client.call_tool.return_value = {"summary_text": summary_text}
    return client


def _iso(days_ago, hour=0, minute=0, second=0):
    """detect_recurring_message_patterns filters against the REAL current
    wall clock (lookback_days=30 from datetime.now()), not against
    relative record ordering -- pattern-candidate test data below must
    stay inside that real window, same convention test_pattern_watcher.py
    already uses. Trend-candidate test data (entity_summary's own
    detect_trends) has no such real-clock filter, so those tests below
    keep using fixed calendar dates for period-boundary clarity."""
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return dt.replace(hour=hour, minute=minute, second=second, microsecond=0).isoformat()


_WEEK_BOUNDS = [
    ("2026-01-01T00:00:00+00:00", "2026-01-08T00:00:00+00:00"),
    ("2026-01-08T00:00:00+00:00", "2026-01-15T00:00:00+00:00"),
    ("2026-01-15T00:00:00+00:00", "2026-01-22T00:00:00+00:00"),
]


def _seed_period(entity_memory_path, entity_id, week_index, count):
    start, _ = _WEEK_BOUNDS[week_index]
    base = int(start[8:10])
    records = [
        _voice_record(entity_id, f"Item {i}", f"2026-01-{base + 1:02d}T00:00:0{i}+00:00")
        for i in range(count)
    ]
    _seed(entity_memory_path, entity_id, records)


def _generate_summary(entity_id, week_index, entity_path, summary_path):
    start, end = _WEEK_BOUNDS[week_index]
    return generate_weekly_summary(entity_id, start, end, client=_fake_summary_client(),
                                    entity_memory_path=entity_path, summary_path=summary_path)


# --- Structural guarantee: the model is never asked to decide inclusion ----


def test_digest_item_tool_schema_has_no_include_or_exclude_field():
    props = set(DIGEST_ITEM_TOOL_SCHEMA["properties"].keys())
    assert props == {"digest_text"}
    assert "include" not in props and "exclude" not in props


# --- Silence: no candidates -> None, not an empty digest --------------------


def test_check_for_digest_returns_none_when_nothing_clears_any_bar(tmp_path):
    entity_path = tmp_path / "entity_memory.db"
    summary_path = tmp_path / "entity_summaries.db"
    digest_path = tmp_path / "entity_digests.db"

    result = check_for_digest(
        "Empty Co", client=_fake_client(),
        entity_memory_path=entity_path, summary_path=summary_path, digest_path=digest_path,
    )
    assert result is None


def test_check_for_digest_always_records_the_check_even_when_silent(tmp_path):
    entity_path = tmp_path / "entity_memory.db"
    summary_path = tmp_path / "entity_summaries.db"
    digest_path = tmp_path / "entity_digests.db"

    assert should_check_for_digest("Empty Co", path=digest_path) is True
    check_for_digest("Empty Co", client=_fake_client(),
                      entity_memory_path=entity_path, summary_path=summary_path, digest_path=digest_path)
    # A check ran (even though it found nothing) -- cadence should now say "too soon"
    # one second later, and "fine again" 4 real days later.
    now = datetime.now(timezone.utc)
    assert should_check_for_digest("Empty Co", path=digest_path,
                                    now=(now + timedelta(seconds=1)).isoformat()) is False
    assert should_check_for_digest("Empty Co", path=digest_path,
                                    now=(now + timedelta(days=4)).isoformat()) is True


# --- Pattern candidates: real evidence-count + novelty gating --------------


def test_check_for_digest_surfaces_a_bar_passing_pattern(tmp_path):
    entity_path = tmp_path / "entity_memory.db"
    summary_path = tmp_path / "entity_summaries.db"
    digest_path = tmp_path / "entity_digests.db"

    _seed(entity_path, "Pattern Co", [
        _voice_record("Pattern Co", "email Sarah the weekly report", _iso(21)),
        _voice_record("Pattern Co", "email Sarah the weekly report", _iso(14)),
        _voice_record("Pattern Co", "email Sarah the weekly report", _iso(7)),
    ])

    result = check_for_digest(
        "Pattern Co", client=_fake_client("Sarah gets a weekly report regularly."),
        entity_memory_path=entity_path, summary_path=summary_path, digest_path=digest_path,
    )

    assert result is not None
    assert len(result.items) == 1
    assert result.items[0].kind == "pattern"
    assert result.items[0].digest_text == "Sarah gets a weekly report regularly."
    assert len(result.items[0].source_record_ids) == 3


def test_check_for_digest_repeat_run_is_silent_due_to_novelty_bar(tmp_path):
    """The exact same pattern, checked again, must not surface twice."""
    entity_path = tmp_path / "entity_memory.db"
    summary_path = tmp_path / "entity_summaries.db"
    digest_path = tmp_path / "entity_digests.db"

    _seed(entity_path, "Repeat Co", [
        _voice_record("Repeat Co", "email Sarah the weekly report", _iso(21)),
        _voice_record("Repeat Co", "email Sarah the weekly report", _iso(14)),
        _voice_record("Repeat Co", "email Sarah the weekly report", _iso(7)),
    ])

    first = check_for_digest("Repeat Co", client=_fake_client(),
                              entity_memory_path=entity_path, summary_path=summary_path, digest_path=digest_path)
    assert first is not None

    second = check_for_digest("Repeat Co", client=_fake_client(),
                               entity_memory_path=entity_path, summary_path=summary_path, digest_path=digest_path)
    assert second is None


# --- Trend candidates: persistence + evidence + novelty gating -------------


def test_check_for_digest_surfaces_a_bar_passing_trend(tmp_path):
    entity_path = tmp_path / "entity_memory.db"
    summary_path = tmp_path / "entity_summaries.db"
    digest_path = tmp_path / "entity_digests.db"

    for i, count in enumerate([2, 4, 6]):  # strictly increasing, persistence_count=2
        _seed_period(entity_path, "Trend Co", i, count)
        _generate_summary("Trend Co", i, entity_path, summary_path)

    result = check_for_digest(
        "Trend Co", client=_fake_client("Activity has been increasing for 3 weeks."),
        entity_memory_path=entity_path, summary_path=summary_path, digest_path=digest_path,
    )

    assert result is not None
    assert len(result.items) == 1
    assert result.items[0].kind == "trend"
    assert result.items[0].digest_text == "Activity has been increasing for 3 weeks."


def test_check_for_digest_rejects_a_trend_with_only_persistence_1(tmp_path):
    """The near-miss case: direction confirmed only once (a blip), not
    reconfirmed -- must NOT clear the M=2 persistence bar."""
    entity_path = tmp_path / "entity_memory.db"
    summary_path = tmp_path / "entity_summaries.db"
    digest_path = tmp_path / "entity_digests.db"

    for i, count in enumerate([4, 2, 4]):  # decreasing then increasing -- persistence_count=1
        _seed_period(entity_path, "Blip Co", i, count)
        _generate_summary("Blip Co", i, entity_path, summary_path)

    result = check_for_digest(
        "Blip Co", client=_fake_client(),
        entity_memory_path=entity_path, summary_path=summary_path, digest_path=digest_path,
    )
    assert result is None


def test_check_for_digest_trend_novelty_survives_across_checks_but_not_a_repeat(tmp_path):
    entity_path = tmp_path / "entity_memory.db"
    summary_path = tmp_path / "entity_summaries.db"
    digest_path = tmp_path / "entity_digests.db"

    for i, count in enumerate([2, 4, 6]):
        _seed_period(entity_path, "Trend Repeat Co", i, count)
        _generate_summary("Trend Repeat Co", i, entity_path, summary_path)

    first = check_for_digest("Trend Repeat Co", client=_fake_client(),
                              entity_memory_path=entity_path, summary_path=summary_path, digest_path=digest_path)
    assert first is not None

    second = check_for_digest("Trend Repeat Co", client=_fake_client(),
                               entity_memory_path=entity_path, summary_path=summary_path, digest_path=digest_path)
    assert second is None  # same (entity_id, dimension, direction) identity -- already surfaced


# --- Batch cap: top 3 by evidence count, overflow stays eligible -----------


def _named_pattern(entity_id, name, n):
    """n occurrences of a distinct recurring-message pattern, spaced a
    few real days apart, all inside the default 30-day lookback window."""
    return [
        _voice_record(entity_id, f"email {name} the update", _iso(days_ago=3 * (i + 1)))
        for i in range(n)
    ]


def test_check_for_digest_caps_at_3_items_ranked_by_evidence_count(tmp_path):
    entity_path = tmp_path / "entity_memory.db"
    summary_path = tmp_path / "entity_summaries.db"
    digest_path = tmp_path / "entity_digests.db"

    # 4 distinct recurring-message patterns for the same entity, with
    # different evidence counts, so ranking is unambiguous.
    records = (
        _named_pattern("Cap Co", "Ann", 3) + _named_pattern("Cap Co", "Bob", 4)
        + _named_pattern("Cap Co", "Cara", 5) + _named_pattern("Cap Co", "Dee", 6)
    )
    _seed(entity_path, "Cap Co", records)

    result = check_for_digest(
        "Cap Co", client=_fake_client(),
        entity_memory_path=entity_path, summary_path=summary_path, digest_path=digest_path,
    )

    assert result is not None
    assert len(result.items) == 3  # hard cap, not 4
    # Ranked by evidence count descending -- Ann (n=3) is the overflow.
    evidence_counts = sorted((item.evidence_count for item in result.items), reverse=True)
    assert evidence_counts == [6, 5, 4]


def test_check_for_digest_overflow_item_stays_eligible_for_next_check(tmp_path):
    """The 4th (lowest-evidence) candidate that didn't make the cap must
    NOT be recorded as surfaced -- it should still be novel next time."""
    entity_path = tmp_path / "entity_memory.db"
    summary_path = tmp_path / "entity_summaries.db"
    digest_path = tmp_path / "entity_digests.db"

    records = (
        _named_pattern("Overflow Co", "Ann", 3) + _named_pattern("Overflow Co", "Bob", 4)
        + _named_pattern("Overflow Co", "Cara", 5) + _named_pattern("Overflow Co", "Dee", 6)
    )
    _seed(entity_path, "Overflow Co", records)

    first = check_for_digest("Overflow Co", client=_fake_client(),
                              entity_memory_path=entity_path, summary_path=summary_path, digest_path=digest_path)
    assert len(first.items) == 3

    # Same data again -- the 3 that were surfaced are now non-novel, but
    # Ann's pattern (the overflow) should still clear every bar and surface.
    second = check_for_digest("Overflow Co", client=_fake_client(),
                               entity_memory_path=entity_path, summary_path=summary_path, digest_path=digest_path)
    assert second is not None
    assert len(second.items) == 1
    assert second.items[0].evidence_count == 3
