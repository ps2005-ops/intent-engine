from intent_engine.core.entity_memory import (
    EntityMemoryRecord,
    JsonlEntityMemoryWriter,
    normalize_entity_id,
    read_records,
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
