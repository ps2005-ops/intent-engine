"""Stage 2: file-based speech-to-text via faster-whisper -- a local, offline,
CPU-friendly CTranslate2 reimplementation of OpenAI's Whisper. Approved
direction (see PROGRESS.md's Stage 2 milestone note): no cloud vendor by
default, reasoned as a privacy decision for a family business, not just a
cost one -- real calendar/email/decision content never leaves the machine.

Real, flagged network dependency, unlike everything else installed so far:
model weights are fetched from Hugging Face Hub on first use per model size,
then cached locally by faster-whisper/huggingface_hub afterward. Confirmed
reachable from this sandboxed dev environment by direct test (a real "tiny"
model loaded and transcribed correctly in ~2s) -- contrary to the assumed
restriction going in, huggingface.co (including its CDN redirect target) was
NOT blocked here. This is an environment-specific finding, not a guarantee:
if a future environment genuinely blocks it, Transcriber's constructor will
raise on first construction (model load), not silently degrade -- the CLI
must let that surface, not swallow it.

DEFAULT_MODEL_SIZE="base": a reasoned middle default, not the fastest
option (tiny) or the most accurate (small+). Real voice notes for a personal
assistant are short and infrequent, not a real-time streaming constraint, so
trading tiny's extra speed for base's meaningfully better accuracy is the
right default; overridable via Transcriber(model_size=...) if a future
measurement says otherwise.

Transcriber is a thin class wrapping ONE loaded WhisperModel, matching this
codebase's existing dependency-injection pattern (VoiceIntentClassifier,
GoogleCalendarReader): constructed once per CLI session (model loading has a
real, measured ~2s cost), reused across every transcribe() call in that
session -- not reloaded per file.

transcribe() never raises for "no speech detected" -- that's a real,
expected outcome (a person recorded silence by mistake), represented via
TranscriptionResult.likely_silence=True and text=None, not an exception. It
DOES let genuine errors (a missing file, a corrupt/unsupported format)
propagate -- those are real problems the person should see, not something to
paper over as "probably silence."

likely_silence is flagged from TWO signals, either sufficient alone: (1) the
joined transcript is empty after whisper produces zero segments (the
observed, measured behavior on a real synthetic silent WAV: 0 segments,
language_probability 0.23, detected "language" nn -- an unlikely/garbage
code), or (2) info.language_probability falls below
_MIN_LANGUAGE_PROBABILITY. The threshold below is a reasoned starting point
from that one real measurement, not empirically calibrated against a large
corpus of real recordings -- same "flagged as an open, unvalidated choice"
discipline as pattern_watcher.py's similarity/timing thresholds.
"""

from pathlib import Path
from typing import Optional, Union

from pydantic import BaseModel

DEFAULT_MODEL_SIZE = "base"
_MIN_LANGUAGE_PROBABILITY = 0.5


class TranscriptionResult(BaseModel):
    text: Optional[str] = None  # None if no speech was detected -- never an empty string standing in for "nothing said"
    language: Optional[str] = None
    language_probability: Optional[float] = None
    likely_silence: bool = False


class Transcriber:
    """Wraps ONE loaded faster_whisper.WhisperModel. Constructed once per CLI
    session -- see module docstring for why this isn't reloaded per file."""

    def __init__(self, model_size: str = DEFAULT_MODEL_SIZE):
        # Imported here, not at module level, so importing this module (and
        # therefore voice/cli.py) doesn't require faster-whisper to be
        # installed unless a Transcriber is actually constructed -- same
        # "local import, real default, no import-time hard dependency"
        # pattern as GoogleCalendarReader's google-* imports.
        from faster_whisper import WhisperModel

        self._model = WhisperModel(model_size, device="cpu", compute_type="int8")

    def transcribe(self, path: Union[str, Path]) -> TranscriptionResult:
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {path}")

        segments, info = self._model.transcribe(str(path))
        text = " ".join(segment.text.strip() for segment in segments).strip()

        likely_silence = not text or (
            info.language_probability is not None and info.language_probability < _MIN_LANGUAGE_PROBABILITY
        )

        return TranscriptionResult(
            text=text or None,
            language=info.language,
            language_probability=info.language_probability,
            likely_silence=likely_silence,
        )
