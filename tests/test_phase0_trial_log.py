import pytest
from pydantic import ValidationError

from intent_engine.core.phase0_trial_log import (
    PhaseZeroLogEntry,
    log_trial_interaction,
    read_trial_log,
)


def test_log_trial_interaction_writes_and_returns_entry(tmp_path):
    path = tmp_path / "phase0_trial_log.jsonl"

    entry = log_trial_interaction(
        input_type="text",
        paraphrase="asked to block off Thursday afternoon for a pickup",
        entrypoint="process_voice_interaction",
        output="Blocked off Thursday 2-4pm for the pickup.",
        worked_well="yes",
        path=path,
    )

    assert isinstance(entry, PhaseZeroLogEntry)
    assert entry.worked_well == "yes"
    assert entry.timestamp  # default_factory populated it
    assert path.exists()


def test_log_trial_interaction_appends_multiple_entries(tmp_path):
    path = tmp_path / "phase0_trial_log.jsonl"

    log_trial_interaction("text", "first one", "process_voice_interaction", "output 1", "yes", path=path)
    log_trial_interaction("image", "photo of a lot", "/verify", "incomplete, weight tag not visible", "partial", path=path)
    log_trial_interaction("voice", "a mumbled voice note", "/audio", "no speech detected", "no", note="too quiet", path=path)

    entries = read_trial_log(path)

    assert len(entries) == 3
    assert [e.worked_well for e in entries] == ["yes", "partial", "no"]
    assert entries[2].note == "too quiet"


def test_read_trial_log_returns_empty_list_when_file_absent(tmp_path):
    entries = read_trial_log(tmp_path / "does_not_exist.jsonl")
    assert entries == []


def test_log_trial_interaction_note_defaults_to_none(tmp_path):
    path = tmp_path / "phase0_trial_log.jsonl"

    entry = log_trial_interaction("text", "paraphrase", "process_voice_interaction", "output", "yes", path=path)

    assert entry.note is None


def test_log_trial_interaction_rejects_invalid_worked_well(tmp_path):
    path = tmp_path / "phase0_trial_log.jsonl"

    with pytest.raises(ValidationError):
        log_trial_interaction("text", "paraphrase", "process_voice_interaction", "output", "sort of", path=path)


def test_log_trial_interaction_rejects_invalid_input_type(tmp_path):
    path = tmp_path / "phase0_trial_log.jsonl"

    with pytest.raises(ValidationError):
        log_trial_interaction("pdf", "paraphrase", "process_voice_interaction", "output", "yes", path=path)


def test_read_trial_log_preserves_order(tmp_path):
    path = tmp_path / "phase0_trial_log.jsonl"
    for i in range(5):
        log_trial_interaction("text", f"interaction {i}", "process_voice_interaction", f"output {i}", "yes", path=path)

    entries = read_trial_log(path)

    assert [e.paraphrase for e in entries] == [f"interaction {i}" for i in range(5)]
