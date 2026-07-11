from intent_engine.core.entity_memory import (
    EntityMemoryRecord,
    JsonlEntityMemoryWriter,
    count_records_by_entity,
    normalize_entity_id,
    read_records,
    records_by_artifact_kind,
)


def _record(entity_id, decision_text, goals=None, constraints=None):
    return EntityMemoryRecord(
        entity_id=entity_id,
        source="simulator",
        decision_text=decision_text,
        goals=goals or [],
        constraints=constraints or [],
        risk_tolerance="medium",
        primary_priority="growth",
    )


def test_round_trip_write_and_read_by_entity_id(tmp_path):
    path = tmp_path / "entity_memory.jsonl"
    writer = JsonlEntityMemoryWriter(path=path)

    # Two records for the same real entity, written with different raw spellings --
    # should both land under one normalized entity_id.
    r1 = _record("Sarah's Startup", "Raise a Series A.", goals=["extend runway"])
    r2 = _record("sarahs startup", "Hire a sales team.", goals=["accelerate growth"])
    # A distinct, unrelated entity.
    r3 = _record("Acme Inc", "Cut prices 20%.", goals=["improve margin"])

    writer.write(r1)
    writer.write(r2)
    writer.write(r3)

    sarah_records = read_records("Sarah's Startup", path=path)
    acme_records = read_records("Acme Inc", path=path)

    # No cross-entity leakage, no missing records.
    assert len(sarah_records) == 2
    assert {r.decision_text for r in sarah_records} == {"Raise a Series A.", "Hire a sales team."}
    assert all(r.entity_id == normalize_entity_id("Sarah's Startup") for r in sarah_records)

    assert len(acme_records) == 1
    assert acme_records[0].decision_text == "Cut prices 20%."
    assert acme_records[0].entity_id == normalize_entity_id("Acme Inc")

    # Querying by a differently-spelled raw variant of the same entity still finds
    # both records -- the whole point of normalization.
    same_via_variant = read_records("sarahs startup", path=path)
    assert len(same_via_variant) == 2


def test_read_records_returns_empty_list_for_unknown_entity(tmp_path):
    path = tmp_path / "entity_memory.jsonl"
    writer = JsonlEntityMemoryWriter(path=path)
    writer.write(_record("Acme Inc", "Cut prices 20%."))

    assert read_records("Nonexistent Company", path=path) == []


def test_read_records_returns_empty_list_when_file_does_not_exist(tmp_path):
    path = tmp_path / "does_not_exist.jsonl"
    assert read_records("Anyone", path=path) == []


# --- Data foundation pass, Stage 1: SQLite backend + domain-typing ---------


def test_read_records_is_backed_by_sqlite_not_a_jsonl_file(tmp_path):
    """The migration's whole point: the backing file is a real SQLite
    database now, not JSON Lines -- checked directly by opening it as one,
    not just inferred from read_records() still working."""
    import sqlite3

    path = tmp_path / "entity_memory.db"
    writer = JsonlEntityMemoryWriter(path=path)
    writer.write(_record("Acme Inc", "Cut prices 20%."))

    conn = sqlite3.connect(str(path))
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "records" in tables


def test_artifact_kind_defaults_to_none_and_round_trips_through_write_and_read(tmp_path):
    path = tmp_path / "entity_memory.db"
    writer = JsonlEntityMemoryWriter(path=path)

    default_record = _record("Acme Inc", "Cut prices 20%.")
    assert default_record.artifact_kind is None
    writer.write(default_record)

    caption_record = EntityMemoryRecord(
        entity_id="Acme Inc", source="voice", decision_text="A caption.",
        goals=[], constraints=[], artifact_kind="caption",
    )
    writer.write(caption_record)

    stored = read_records("Acme Inc", path=path)
    assert {r.artifact_kind for r in stored} == {None, "caption"}


def test_records_by_artifact_kind_filters_by_entity_and_kind(tmp_path):
    path = tmp_path / "entity_memory.db"
    writer = JsonlEntityMemoryWriter(path=path)
    writer.write(EntityMemoryRecord(
        entity_id="Acme Inc", source="voice", decision_text="email Sarah the notes",
        goals=[], constraints=[], artifact_kind="message",
    ))
    writer.write(EntityMemoryRecord(
        entity_id="Acme Inc", source="voice", decision_text="A caption.",
        goals=[], constraints=[], artifact_kind="caption",
    ))
    writer.write(EntityMemoryRecord(
        entity_id="Other Co", source="voice", decision_text="email Bob the notes",
        goals=[], constraints=[], artifact_kind="message",
    ))

    messages = records_by_artifact_kind("Acme Inc", "message", path=path)
    assert len(messages) == 1
    assert messages[0].decision_text == "email Sarah the notes"

    captions = records_by_artifact_kind("Acme Inc", "caption", path=path)
    assert len(captions) == 1
    assert captions[0].decision_text == "A caption."


def test_records_by_artifact_kind_returns_empty_list_when_file_does_not_exist(tmp_path):
    path = tmp_path / "does_not_exist.db"
    assert records_by_artifact_kind("Anyone", "message", path=path) == []


def test_count_records_by_entity_matches_read_records_length(tmp_path):
    path = tmp_path / "entity_memory.db"
    writer = JsonlEntityMemoryWriter(path=path)
    writer.write(_record("Acme Inc", "Cut prices 20%."))
    writer.write(_record("Acme Inc", "Raise a Series A."))
    writer.write(_record("Other Co", "Something else."))

    assert count_records_by_entity("Acme Inc", path=path) == len(read_records("Acme Inc", path=path)) == 2
    assert count_records_by_entity("Other Co", path=path) == 1


def test_count_records_by_entity_returns_zero_when_file_does_not_exist(tmp_path):
    path = tmp_path / "does_not_exist.db"
    assert count_records_by_entity("Anyone", path=path) == 0
