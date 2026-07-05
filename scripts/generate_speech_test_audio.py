"""One-time generator for speech-to-text's synthetic test-audio fixtures.

Two real, constructed audio files (not real recordings, not hallucinated):
one synthesized "known phrase" (via macOS's built-in `say`, no new
dependency -- a real accuracy check against a phrase we know the exact
intended content of) and one near-silent WAV (pure Python stdlib `wave`
module, no dependency at all -- exercises the failure path).

`say` is macOS-only, so this script only needs to be RE-run if the fixtures
change; the resulting WAV files are committed to
tests/fixtures/speech_to_text/, so the live test itself has no dependency on
`say` being present wherever it eventually runs.
"""

import struct
import subprocess
import wave
from pathlib import Path

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "speech_to_text"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

KNOWN_PHRASE = "block off Thursday at two PM for the investor call"
KNOWN_PHRASE_PATH = OUTPUT_DIR / "known_phrase.wav"
SILENCE_PATH = OUTPUT_DIR / "silence.wav"

subprocess.run(
    ["say", "--file-format=WAVE", "--data-format=LEI16@16000", "-o", str(KNOWN_PHRASE_PATH), KNOWN_PHRASE],
    check=True,
)
print(f"Wrote {KNOWN_PHRASE_PATH} (phrase: {KNOWN_PHRASE!r})")

with wave.open(str(SILENCE_PATH), "wb") as f:
    f.setnchannels(1)
    f.setsampwidth(2)
    f.setframerate(16000)
    frames = struct.pack("<" + "h" * 32000, *([0] * 32000))  # 2 seconds of pure silence
    f.writeframes(frames)
print(f"Wrote {SILENCE_PATH} (2s of silence)")
