from unittest.mock import MagicMock, patch

import pytest

from intent_engine.voice.speech_to_text import TranscriptionResult, Transcriber


def _fake_whisper_model(segments, language="en", language_probability=0.99):
    model = MagicMock()
    info = MagicMock()
    info.language = language
    info.language_probability = language_probability
    model.transcribe.return_value = (segments, info)
    return model


def _fake_segment(text):
    seg = MagicMock()
    seg.text = text
    return seg


def test_transcribe_raises_on_missing_file(tmp_path):
    with patch("faster_whisper.WhisperModel") as mock_cls:
        mock_cls.return_value = _fake_whisper_model([])
        transcriber = Transcriber()

    with pytest.raises(FileNotFoundError):
        transcriber.transcribe(tmp_path / "does_not_exist.wav")


def test_transcribe_returns_joined_text_for_real_speech(tmp_path):
    audio_path = tmp_path / "fake.wav"
    audio_path.write_bytes(b"fake-audio-bytes")

    with patch("faster_whisper.WhisperModel") as mock_cls:
        mock_cls.return_value = _fake_whisper_model(
            [_fake_segment("Block off Thursday at 2pm"), _fake_segment(" for the investor call.")],
            language_probability=0.99,
        )
        transcriber = Transcriber()

    result = transcriber.transcribe(audio_path)

    assert isinstance(result, TranscriptionResult)
    assert result.text == "Block off Thursday at 2pm for the investor call."
    assert result.likely_silence is False
    assert result.language == "en"


def test_transcribe_flags_likely_silence_on_empty_segments(tmp_path):
    audio_path = tmp_path / "silence.wav"
    audio_path.write_bytes(b"fake-silent-audio-bytes")

    with patch("faster_whisper.WhisperModel") as mock_cls:
        mock_cls.return_value = _fake_whisper_model([], language="nn", language_probability=0.23)
        transcriber = Transcriber()

    result = transcriber.transcribe(audio_path)

    assert result.text is None
    assert result.likely_silence is True


def test_transcribe_flags_likely_silence_on_low_language_probability_even_with_text(tmp_path):
    """A low language_probability is its own signal, independent of whether
    some (unreliable) text came back -- must not be trusted just because
    segments happened to be non-empty."""
    audio_path = tmp_path / "garbled.wav"
    audio_path.write_bytes(b"fake-garbled-audio-bytes")

    with patch("faster_whisper.WhisperModel") as mock_cls:
        mock_cls.return_value = _fake_whisper_model([_fake_segment("uh")], language_probability=0.3)
        transcriber = Transcriber()

    result = transcriber.transcribe(audio_path)

    assert result.likely_silence is True
