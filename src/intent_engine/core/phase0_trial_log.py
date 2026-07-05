"""Phase-0 trial logger: a thin observability layer around the MANUAL relay
process (see the channel-bridge proposal's Phase 0), not a pipeline change.

During the manual relay trial, a person (not this codebase) is the bridge:
they relay a real message from the actual target user, run it through the
appropriate existing entrypoint (process_voice_interaction() / /audio /
/verify), see the real result, and relay a plain-language reply back. This
module exists only so that a week of doing that produces a real, reviewable
record instead of memory -- so the eventual Phase 1 go/no-go decision is made
from evidence, same standard as everything else in this project.

Deliberately NOT automated judgment: worked_well is a field the human
evaluator fills in themselves, immediately after observing the real
interaction -- this module has no opinion on whether an interaction actually
worked, it only records what someone else decided.

Deliberately not wired into voice/cli.py as a new command -- log_trial_interaction()
is meant to be called directly, right after a manual relay interaction, by
whoever is doing the relaying. Same append-only JSONL convention as every
other record in this project (entity_memory.jsonl, suggestions.jsonl,
draft_attempts.jsonl) -- one line per interaction, never mutated.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Union

from pydantic import BaseModel, Field

try:
    from typing import Literal
except ImportError:  # pragma: no cover
    from typing_extensions import Literal

DEFAULT_PHASE0_LOG_PATH = Path("data/phase0_trial_log.jsonl")

InputType = Literal["text", "voice", "image"]
Entrypoint = Literal["process_voice_interaction", "/audio", "/verify"]
WorkedWell = Literal["yes", "no", "partial"]


def _current_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


class PhaseZeroLogEntry(BaseModel):
    timestamp: str = Field(default_factory=_current_timestamp)
    input_type: InputType
    paraphrase: str  # a short paraphrase of what was asked -- not necessarily verbatim, kept lightweight
    entrypoint: Entrypoint
    output: str  # the system's actual output, as relayed back
    worked_well: WorkedWell
    note: Optional[str] = None


def log_trial_interaction(
    input_type: InputType,
    paraphrase: str,
    entrypoint: Entrypoint,
    output: str,
    worked_well: WorkedWell,
    note: Optional[str] = None,
    path: Union[str, Path] = DEFAULT_PHASE0_LOG_PATH,
) -> PhaseZeroLogEntry:
    """Call this once, right after relaying a real interaction and judging
    the result -- the one place the human evaluator's judgment (worked_well,
    note) enters the record."""
    entry = PhaseZeroLogEntry(
        input_type=input_type,
        paraphrase=paraphrase,
        entrypoint=entrypoint,
        output=output,
        worked_well=worked_well,
        note=note,
    )
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(entry.model_dump_json() + "\n")
    return entry


def read_trial_log(path: Union[str, Path] = DEFAULT_PHASE0_LOG_PATH) -> List[PhaseZeroLogEntry]:
    """Reads the full trial log, in the order entries were recorded -- for
    reviewing a week's real evidence at Phase 1 go/no-go time."""
    path = Path(path)
    if not path.exists():
        return []
    entries = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entries.append(PhaseZeroLogEntry.model_validate_json(line))
    return entries
