from unittest.mock import MagicMock

from intent_engine.core.entity_memory import EntityMemoryRecord, SqliteEntityMemoryWriter
from intent_engine.core.entity_summary import (
    EntitySummaryRecord,
    detect_trends,
    generate_weekly_summary,
    get_tiered_view,
    read_summaries,
)


def _record(entity_id, decision_text, timestamp, source="voice"):
    return EntityMemoryRecord(
        entity_id=entity_id, source=source, decision_text=decision_text,
        goals=[], constraints=[], timestamp=timestamp,
    )


def _seed(entity_memory_path, entity_id, records):
    writer = SqliteEntityMemoryWriter(path=entity_memory_path)
    for r in records:
        writer.write(r)


def _fake_client(summary_text="A short, factual summary."):
    client = MagicMock()
    client.call_tool.return_value = {"summary_text": summary_text}
    return client


# --- generate_weekly_summary: real period gathering, real citations --------


def test_generate_weekly_summary_gathers_only_records_in_period(tmp_path):
    entity_path = tmp_path / "entity_memory.db"
    summary_path = tmp_path / "entity_summaries.db"
    _seed(entity_path, "Acme Inc", [
        _record("Acme Inc", "Raise a Series A.", "2026-01-01T00:00:00+00:00"),
        _record("Acme Inc", "Hire a sales lead.", "2026-01-03T00:00:00+00:00"),
        _record("Acme Inc", "Cut prices 20%.", "2026-02-01T00:00:00+00:00"),  # outside period
    ])

    client = _fake_client()
    summary = generate_weekly_summary(
        "Acme Inc", "2026-01-01T00:00:00+00:00", "2026-01-08T00:00:00+00:00",
        client=client, entity_memory_path=entity_path, summary_path=summary_path,
    )

    assert len(summary.source_record_ids) == 2
    user_message = client.call_tool.call_args.kwargs["user_message"]
    assert "Raise a Series A." in user_message
    assert "Hire a sales lead." in user_message
    assert "Cut prices 20%." not in user_message


def test_generate_weekly_summary_source_record_ids_are_computed_not_llm_asserted(tmp_path):
    """The citation list must exactly match the real gathered records --
    checked directly against record_id, never taken from the model's
    output (the fake client here doesn't even have a way to state ids,
    proving the code path never asks it to)."""
    entity_path = tmp_path / "entity_memory.db"
    summary_path = tmp_path / "entity_summaries.db"
    r1 = _record("Acme Inc", "Raise a Series A.", "2026-01-01T00:00:00+00:00")
    r2 = _record("Acme Inc", "Hire a sales lead.", "2026-01-03T00:00:00+00:00")
    _seed(entity_path, "Acme Inc", [r1, r2])

    client = _fake_client()
    summary = generate_weekly_summary(
        "Acme Inc", "2026-01-01T00:00:00+00:00", "2026-01-08T00:00:00+00:00",
        client=client, entity_memory_path=entity_path, summary_path=summary_path,
    )

    assert set(summary.source_record_ids) == {r1.record_id, r2.record_id}
    # The tool schema itself never asked the model for ids at all.
    call_kwargs = client.call_tool.call_args.kwargs
    assert "source_record_ids" not in call_kwargs["input_schema"]["properties"]


def test_generate_weekly_summary_with_no_records_skips_the_llm_call(tmp_path):
    """An honest empty-period summary must not fabricate activity, and
    must not spend an LLM call producing one either -- there's nothing to
    summarize."""
    entity_path = tmp_path / "entity_memory.db"
    summary_path = tmp_path / "entity_summaries.db"

    client = _fake_client()
    summary = generate_weekly_summary(
        "Nonexistent Co", "2026-01-01T00:00:00+00:00", "2026-01-08T00:00:00+00:00",
        client=client, entity_memory_path=entity_path, summary_path=summary_path,
    )

    assert summary.source_record_ids == []
    assert "No activity recorded" in summary.summary_text
    client.call_tool.assert_not_called()


def test_generate_weekly_summary_persists_and_is_readable(tmp_path):
    entity_path = tmp_path / "entity_memory.db"
    summary_path = tmp_path / "entity_summaries.db"
    _seed(entity_path, "Acme Inc", [_record("Acme Inc", "Raise a Series A.", "2026-01-01T00:00:00+00:00")])

    client = _fake_client("Acme Inc raised a Series A this week.")
    generate_weekly_summary(
        "Acme Inc", "2026-01-01T00:00:00+00:00", "2026-01-08T00:00:00+00:00",
        client=client, entity_memory_path=entity_path, summary_path=summary_path,
    )

    stored = read_summaries("Acme Inc", path=summary_path)
    assert len(stored) == 1
    assert isinstance(stored[0], EntitySummaryRecord)
    assert stored[0].summary_text == "Acme Inc raised a Series A this week."


def test_read_summaries_returns_empty_list_when_file_does_not_exist(tmp_path):
    path = tmp_path / "does_not_exist.db"
    assert read_summaries("Anyone", path=path) == []


def test_read_summaries_isolates_by_entity(tmp_path):
    entity_path = tmp_path / "entity_memory.db"
    summary_path = tmp_path / "entity_summaries.db"
    _seed(entity_path, "Acme Inc", [_record("Acme Inc", "Raise a Series A.", "2026-01-01T00:00:00+00:00")])
    _seed(entity_path, "Other Co", [_record("Other Co", "Cut prices.", "2026-01-01T00:00:00+00:00")])

    client = _fake_client()
    generate_weekly_summary("Acme Inc", "2026-01-01T00:00:00+00:00", "2026-01-08T00:00:00+00:00",
                             client=client, entity_memory_path=entity_path, summary_path=summary_path)
    generate_weekly_summary("Other Co", "2026-01-01T00:00:00+00:00", "2026-01-08T00:00:00+00:00",
                             client=client, entity_memory_path=entity_path, summary_path=summary_path)

    assert len(read_summaries("Acme Inc", path=summary_path)) == 1
    assert len(read_summaries("Other Co", path=summary_path)) == 1


# --- get_tiered_view: summary-tier default, raw-tier only on request -------


def test_get_tiered_view_returns_summary_only_by_default(tmp_path):
    entity_path = tmp_path / "entity_memory.db"
    summary_path = tmp_path / "entity_summaries.db"
    _seed(entity_path, "Acme Inc", [_record("Acme Inc", "Raise a Series A.", "2026-01-01T00:00:00+00:00")])
    client = _fake_client()
    generate_weekly_summary("Acme Inc", "2026-01-01T00:00:00+00:00", "2026-01-08T00:00:00+00:00",
                             client=client, entity_memory_path=entity_path, summary_path=summary_path)

    view = get_tiered_view("Acme Inc", entity_memory_path=entity_path, summary_path=summary_path)

    assert len(view.summaries) == 1
    assert view.raw_records is None  # not requested -- distinct from "requested but empty"


def test_get_tiered_view_include_raw_returns_exactly_the_cited_records(tmp_path):
    entity_path = tmp_path / "entity_memory.db"
    summary_path = tmp_path / "entity_summaries.db"
    r1 = _record("Acme Inc", "Raise a Series A.", "2026-01-01T00:00:00+00:00")
    r2 = _record("Acme Inc", "Hire a sales lead.", "2026-01-03T00:00:00+00:00")
    r3 = _record("Acme Inc", "Cut prices 20%.", "2026-02-01T00:00:00+00:00")  # different period
    _seed(entity_path, "Acme Inc", [r1, r2, r3])

    client = _fake_client()
    generate_weekly_summary("Acme Inc", "2026-01-01T00:00:00+00:00", "2026-01-08T00:00:00+00:00",
                             client=client, entity_memory_path=entity_path, summary_path=summary_path)

    view = get_tiered_view("Acme Inc", include_raw=True, entity_memory_path=entity_path, summary_path=summary_path)

    assert view.raw_records is not None
    assert {r.record_id for r in view.raw_records} == {r1.record_id, r2.record_id}
    assert r3.record_id not in {r.record_id for r in view.raw_records}


def test_get_tiered_view_filters_by_period(tmp_path):
    entity_path = tmp_path / "entity_memory.db"
    summary_path = tmp_path / "entity_summaries.db"
    _seed(entity_path, "Acme Inc", [
        _record("Acme Inc", "Raise a Series A.", "2026-01-01T00:00:00+00:00"),
        _record("Acme Inc", "Cut prices 20%.", "2026-02-01T00:00:00+00:00"),
    ])
    client = _fake_client()
    generate_weekly_summary("Acme Inc", "2026-01-01T00:00:00+00:00", "2026-01-08T00:00:00+00:00",
                             client=client, entity_memory_path=entity_path, summary_path=summary_path)
    generate_weekly_summary("Acme Inc", "2026-02-01T00:00:00+00:00", "2026-02-08T00:00:00+00:00",
                             client=client, entity_memory_path=entity_path, summary_path=summary_path)

    view = get_tiered_view(
        "Acme Inc", period_start="2026-02-01T00:00:00+00:00",
        entity_memory_path=entity_path, summary_path=summary_path,
    )

    assert len(view.summaries) == 1
    assert view.summaries[0].period_start == "2026-02-01T00:00:00+00:00"


# --- detect_trends: deterministic, no LLM call ------------------------------

_WEEK_BOUNDS = [
    ("2026-01-01T00:00:00+00:00", "2026-01-08T00:00:00+00:00"),
    ("2026-01-08T00:00:00+00:00", "2026-01-15T00:00:00+00:00"),
    ("2026-01-15T00:00:00+00:00", "2026-01-22T00:00:00+00:00"),
    ("2026-01-22T00:00:00+00:00", "2026-01-29T00:00:00+00:00"),
]


def _seed_period(entity_memory_path, entity_id, week_index, count, source="voice"):
    start, _ = _WEEK_BOUNDS[week_index]
    base = int(start[8:10])  # day-of-month, so timestamps land inside [start, end)
    records = [
        _record(entity_id, f"Item {i}", f"2026-01-{base + 1:02d}T00:00:0{i}+00:00", source=source)
        for i in range(count)
    ]
    _seed(entity_memory_path, entity_id, records)


def _generate_summary_for_week(entity_id, week_index, entity_path, summary_path):
    start, end = _WEEK_BOUNDS[week_index]
    client = _fake_client()
    return generate_weekly_summary(entity_id, start, end, client=client,
                                    entity_memory_path=entity_path, summary_path=summary_path)


def test_detect_trends_finds_increasing_record_volume_with_full_persistence(tmp_path):
    entity_path = tmp_path / "entity_memory.db"
    summary_path = tmp_path / "entity_summaries.db"
    counts = [2, 4, 6]  # strictly increasing across 3 weeks
    for i, count in enumerate(counts):
        _seed_period(entity_path, "Growth Co", i, count)
        _generate_summary_for_week("Growth Co", i, entity_path, summary_path)

    trends = detect_trends("Growth Co", summary_path=summary_path, entity_memory_path=entity_path)
    volume_trend = next(t for t in trends if t.trend_dimension == "record_volume")

    assert volume_trend.direction == "increasing"
    assert volume_trend.persistence_count == 2  # 2 agreeing consecutive comparisons
    assert len(volume_trend.source_record_ids) == sum(counts)


def test_detect_trends_reports_persistence_1_for_a_blip_not_yet_reconfirmed(tmp_path):
    entity_path = tmp_path / "entity_memory.db"
    summary_path = tmp_path / "entity_summaries.db"
    counts = [4, 2, 4]  # decreasing, then increasing -- only the latest comparison agrees with itself
    for i, count in enumerate(counts):
        _seed_period(entity_path, "Blip Co", i, count)
        _generate_summary_for_week("Blip Co", i, entity_path, summary_path)

    trends = detect_trends("Blip Co", summary_path=summary_path, entity_memory_path=entity_path)
    volume_trend = next(t for t in trends if t.trend_dimension == "record_volume")

    assert volume_trend.direction == "increasing"
    assert volume_trend.persistence_count == 1  # a real blip, not yet reconfirmed


def test_detect_trends_produces_no_candidate_for_a_stable_dimension(tmp_path):
    entity_path = tmp_path / "entity_memory.db"
    summary_path = tmp_path / "entity_summaries.db"
    counts = [3, 3, 3]  # no change at all
    for i, count in enumerate(counts):
        _seed_period(entity_path, "Steady Co", i, count)
        _generate_summary_for_week("Steady Co", i, entity_path, summary_path)

    trends = detect_trends("Steady Co", summary_path=summary_path, entity_memory_path=entity_path)
    assert not any(t.trend_dimension == "record_volume" for t in trends)


def test_detect_trends_returns_empty_list_with_fewer_than_2_summaries(tmp_path):
    entity_path = tmp_path / "entity_memory.db"
    summary_path = tmp_path / "entity_summaries.db"
    _seed_period(entity_path, "New Co", 0, 3)
    _generate_summary_for_week("New Co", 0, entity_path, summary_path)

    trends = detect_trends("New Co", summary_path=summary_path, entity_memory_path=entity_path)
    assert trends == []
