"""Live end-to-end test of faster-whisper's real model against real
constructed audio fixtures. Skipped automatically unless a Transcriber can
actually be constructed here (faster-whisper installed AND its model
weights loadable -- the latter needs real network access to Hugging Face
Hub on first use in a given environment, unlike everything else this
project depends on). Same "report the real environment finding, don't
assume" discipline as test_calendar_live.py's OAuth-presence check, and same
"skip cleanly so the main suite stays green regardless of what this sandbox
allows" requirement.

Constructed once at collection time (not per test) since model loading has
a real, measured ~2s cost -- both tests below reuse the same loaded model.
"""

from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "speech_to_text"
KNOWN_PHRASE_PATH = FIXTURES / "known_phrase.wav"
SILENCE_PATH = FIXTURES / "silence.wav"


def _try_build_transcriber():
    try:
        from intent_engine.voice.speech_to_text import Transcriber

        return Transcriber()
    except Exception:
        return None


_transcriber = _try_build_transcriber()

pytestmark = pytest.mark.skipif(
    _transcriber is None,
    reason="faster-whisper model could not be loaded in this environment (not installed, or model weights "
    "unreachable -- Hugging Face Hub network access needed on first use). Verify locally if this environment "
    "cannot reach it.",
)


def test_real_transcription_of_known_phrase():
    result = _transcriber.transcribe(KNOWN_PHRASE_PATH)

    assert result.text is not None
    assert result.likely_silence is False
    # Loose match, not byte-identical -- real transcription normalizes
    # punctuation/numbers (measured: "two PM" -> "2 p.m." in real testing).
    lowered = result.text.lower()
    assert "thursday" in lowered
    assert "investor" in lowered


def test_real_transcription_of_silence_is_flagged_not_processed():
    result = _transcriber.transcribe(SILENCE_PATH)

    assert result.likely_silence is True
