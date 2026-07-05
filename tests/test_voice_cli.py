import json
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

from intent_engine.core.entity_memory import EntityMemoryRecord, JsonlEntityMemoryWriter, read_records
from intent_engine.core.image_verification import VerificationResult
from intent_engine.core.permissions import PermissionRegistry
from intent_engine.voice.calendar import StubCalendarReader
from intent_engine.voice.cli import (
    DEFAULT_VERIFICATION_CHECKLIST,
    _build_parser,
    _handle_audio_command,
    _handle_verify_command,
    load_permission_registry,
    select_calendar_reader,
)
from intent_engine.voice.speech_to_text import TranscriptionResult


# --- grants loading -----------------------------------------------------


def test_load_permission_registry_deny_by_default_when_file_absent(tmp_path):
    registry = load_permission_registry(tmp_path / "no_such_file.json")

    assert isinstance(registry, PermissionRegistry)
    assert registry.is_authorized("calendar_act") is False
    assert registry.is_authorized("anything") is False


def test_load_permission_registry_loads_real_grants(tmp_path):
    grants_path = tmp_path / "grants.json"
    grants_path.write_text(json.dumps({"calendar_read": True, "calendar_act": False}))

    registry = load_permission_registry(grants_path)

    assert registry.is_authorized("calendar_read") is True
    assert registry.is_authorized("calendar_act") is False
    # A domain simply absent from the file must still deny -- not invent a grant.
    assert registry.is_authorized("gmail_act") is False


def test_load_permission_registry_rejects_malformed_file(tmp_path):
    grants_path = tmp_path / "grants.json"
    grants_path.write_text(json.dumps({"calendar_read": "yes"}))  # not a bool

    with pytest.raises(ValueError):
        load_permission_registry(grants_path)


def test_load_permission_registry_rejects_non_object_json(tmp_path):
    grants_path = tmp_path / "grants.json"
    grants_path.write_text(json.dumps(["calendar_read"]))

    with pytest.raises(ValueError):
        load_permission_registry(grants_path)


# --- calendar reader selection -------------------------------------------


def test_select_calendar_reader_falls_back_to_stub_when_no_credentials():
    registry = PermissionRegistry(grants={"calendar_read": True})
    with patch("intent_engine.voice.cli.DEFAULT_CALENDAR_TOKEN_PATH") as mock_token_path:
        mock_token_path.exists.return_value = False
        reader = select_calendar_reader(registry)
    assert isinstance(reader, StubCalendarReader)


# --- arg parsing ----------------------------------------------------------


def test_build_parser_requires_entity_id():
    parser = _build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])


def test_build_parser_accepts_entity_id_and_defaults(tmp_path):
    parser = _build_parser()
    args = parser.parse_args(["--entity-id", "Acme Inc"])
    assert args.entity_id == "Acme Inc"
    assert args.grants_path  # has a default


# --- session flow (mocked collaborators) ---------------------------------


def test_handle_pending_suggestion_returns_none_when_nothing_pending(tmp_path):
    from intent_engine.voice.cli import _handle_pending_suggestion

    result = _handle_pending_suggestion(
        "Acme Inc", tmp_path / "suggestions.jsonl", tmp_path / "entity_memory.jsonl"
    )
    assert result is None


def test_handle_pending_suggestion_accept_flow(tmp_path, monkeypatch):
    from datetime import datetime, timedelta, timezone

    from intent_engine.voice.cli import _handle_pending_suggestion

    entity_path = tmp_path / "entity_memory.jsonl"
    suggestions_path = tmp_path / "suggestions.jsonl"
    writer = JsonlEntityMemoryWriter(path=entity_path)
    for days_ago in range(5, 0, -1):
        dt = (datetime.now(timezone.utc) - timedelta(days=days_ago)).replace(hour=19, minute=0, second=0, microsecond=0)
        writer.write(
            EntityMemoryRecord(
                entity_id="Acme Inc", source="voice", decision_text="email Sarah the daily standup notes",
                goals=[], constraints=[], timestamp=dt.isoformat(), salience="low",
            )
        )

    monkeypatch.setattr("builtins.input", lambda _: "y")
    accepted = _handle_pending_suggestion("Acme Inc", suggestions_path, entity_path)

    assert accepted is not None
    assert accepted.status == "accepted"
    assert accepted.task_agent_spec is not None


def test_handle_pending_suggestion_decline_flow(tmp_path, monkeypatch):
    from datetime import datetime, timedelta, timezone

    from intent_engine.voice.cli import _handle_pending_suggestion

    entity_path = tmp_path / "entity_memory.jsonl"
    suggestions_path = tmp_path / "suggestions.jsonl"
    writer = JsonlEntityMemoryWriter(path=entity_path)
    for days_ago in range(5, 0, -1):
        dt = (datetime.now(timezone.utc) - timedelta(days=days_ago)).replace(hour=19, minute=0, second=0, microsecond=0)
        writer.write(
            EntityMemoryRecord(
                entity_id="Acme Inc", source="voice", decision_text="email Sarah the daily standup notes",
                goals=[], constraints=[], timestamp=dt.isoformat(), salience="low",
            )
        )

    monkeypatch.setattr("builtins.input", lambda _: "n")
    accepted = _handle_pending_suggestion("Acme Inc", suggestions_path, entity_path)

    assert accepted is None


def test_handle_pending_draft_returns_none_when_nothing_pending(tmp_path):
    from intent_engine.voice.cli import _handle_pending_draft

    result = _handle_pending_draft("Acme Inc", tmp_path / "draft_attempts.jsonl", tmp_path / "entity_memory.jsonl")
    assert result is None


# --- /audio command (Stage 2 STT) -----------------------------------------


def _fake_transcriber(result: TranscriptionResult):
    transcriber = MagicMock()
    transcriber.transcribe.return_value = result
    return transcriber


def test_handle_audio_command_confirms_and_returns_text_on_yes(monkeypatch):
    transcriber = _fake_transcriber(
        TranscriptionResult(text="block off Thursday at 2pm", language="en", language_probability=0.99)
    )
    monkeypatch.setattr("builtins.input", lambda _: "y")

    result = _handle_audio_command("/some/file.wav", transcriber)

    assert result == "block off Thursday at 2pm"


def test_handle_audio_command_discards_on_no(monkeypatch):
    transcriber = _fake_transcriber(
        TranscriptionResult(text="block off Thursday at 2pm", language="en", language_probability=0.99)
    )
    monkeypatch.setattr("builtins.input", lambda _: "n")

    result = _handle_audio_command("/some/file.wav", transcriber)

    assert result is None


def test_handle_audio_command_edit_replaces_text(monkeypatch):
    transcriber = _fake_transcriber(
        TranscriptionResult(text="block off Thursday at 2pm", language="en", language_probability=0.99)
    )
    replies = iter(["edit", "block off Thursday at 3pm instead"])
    monkeypatch.setattr("builtins.input", lambda _: next(replies))

    result = _handle_audio_command("/some/file.wav", transcriber)

    assert result == "block off Thursday at 3pm instead"


def test_handle_audio_command_never_processes_likely_silence(monkeypatch):
    """Real safety requirement: silence/no-speech must never be fed forward,
    and must never even prompt for confirmation."""
    transcriber = _fake_transcriber(
        TranscriptionResult(text=None, language="nn", language_probability=0.23, likely_silence=True)
    )
    called = []
    monkeypatch.setattr("builtins.input", lambda p: called.append(p) or "y")

    result = _handle_audio_command("/some/silence.wav", transcriber)

    assert result is None
    assert called == []  # never even asked for confirmation


def test_handle_audio_command_reports_missing_file_without_crashing():
    transcriber = MagicMock()
    transcriber.transcribe.side_effect = FileNotFoundError("Audio file not found: /nope.wav")

    result = _handle_audio_command("/nope.wav", transcriber)

    assert result is None


def test_handle_audio_command_reports_transcription_error_without_crashing():
    transcriber = MagicMock()
    transcriber.transcribe.side_effect = RuntimeError("corrupt audio stream")

    result = _handle_audio_command("/bad/file.wav", transcriber)

    assert result is None


# --- /verify command (image-verification wiring) --------------------------


def test_build_parser_verification_checklist_defaults_to_none():
    parser = _build_parser()
    args = parser.parse_args(["--entity-id", "Acme Inc"])
    assert args.verification_checklist is None


def test_build_parser_verification_checklist_is_repeatable():
    parser = _build_parser()
    args = parser.parse_args(
        ["--entity-id", "Acme Inc", "--verification-checklist", "A", "--verification-checklist", "B"]
    )
    assert args.verification_checklist == ["A", "B"]


def test_handle_verify_command_prints_verdict_missing_reasoning_confidence(capsys):
    result = VerificationResult(verdict="incomplete", missing=["Date visible"], reasoning="date not shown", confidence="medium")
    with patch("intent_engine.voice.cli.verify_image", return_value=result) as mock_verify:
        _handle_verify_command("/some/receipt.png", DEFAULT_VERIFICATION_CHECKLIST)

    mock_verify.assert_called_once_with("/some/receipt.png", DEFAULT_VERIFICATION_CHECKLIST)
    captured = capsys.readouterr()
    assert "incomplete" in captured.out
    assert "Date visible" in captured.out
    assert "date not shown" in captured.out
    assert "medium" in captured.out


def test_handle_verify_command_does_not_touch_entity_memory(tmp_path):
    """Real asymmetry with /audio: /verify never writes to entity memory --
    ephemeral, human-review-only, no persistence of any kind."""
    entity_path = tmp_path / "entity_memory.jsonl"
    result = VerificationResult(verdict="complete", missing=[], reasoning="all fields visible", confidence="high")
    with patch("intent_engine.voice.cli.verify_image", return_value=result):
        _handle_verify_command("/some/receipt.png", DEFAULT_VERIFICATION_CHECKLIST)

    assert not entity_path.exists()


def test_handle_verify_command_reports_missing_file_without_crashing(capsys):
    with patch("intent_engine.voice.cli.verify_image", side_effect=FileNotFoundError("Image not found: /nope.png")):
        _handle_verify_command("/nope.png", DEFAULT_VERIFICATION_CHECKLIST)

    captured = capsys.readouterr()
    assert "not found" in captured.out.lower()


def test_handle_verify_command_reports_invalid_image_without_crashing(capsys):
    with patch("intent_engine.voice.cli.verify_image", side_effect=ValueError("Unsupported image type '.bmp'")):
        _handle_verify_command("/bad/file.bmp", DEFAULT_VERIFICATION_CHECKLIST)

    captured = capsys.readouterr()
    assert "could not verify" in captured.out.lower()


def test_handle_verify_command_never_prompts_for_confirmation(monkeypatch):
    """No confirmation step by design -- input() must never be called."""
    result = VerificationResult(verdict="complete", missing=[], reasoning="all fields visible", confidence="high")
    called = []
    monkeypatch.setattr("builtins.input", lambda p: called.append(p) or "y")
    with patch("intent_engine.voice.cli.verify_image", return_value=result):
        _handle_verify_command("/some/receipt.png", DEFAULT_VERIFICATION_CHECKLIST)

    assert called == []
