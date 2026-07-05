"""The Suggestion Moment: turns a DetectedPattern (pattern_watcher.py) into a
single, plain-language suggestion, and handles the accept/decline flow.

Every suggestion is phrased as an observation with a question, never an
assumption already acted on -- "I've noticed X, want me to help?", never
"I've started helping with X." Wording explicitly reflects confidence: a
low-confidence pattern gets hedged language ("it looks like there might be"),
never the same assertive framing as a high-confidence one. This is the same
honesty discipline as everywhere else in this codebase, applied to the
person-facing surface instead of an internal field.

At most ONE unresolved suggestion is ever surfaced to a person at a time --
see surface_next_suggestion()'s docstring for why this is a real product
requirement, not a nice-to-have.

Accepting a suggestion produces a minimal, draft-only, permission-gated
TaskAgentSpecStub -- proves the accept path yields a real, inspectable
artifact. It is explicitly NOT the full spec/execution system (out of scope
this pass) and gated=True always: nothing here authorizes real sending or
acting, same as every existing act-tier domain requiring its own separate
permission check before anything real happens.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Union
from uuid import uuid4

from pydantic import BaseModel, Field

try:
    from typing import Literal
except ImportError:  # pragma: no cover
    from typing_extensions import Literal

from .pattern_watcher import DetectedPattern, detect_recurring_message_patterns
from .entity_memory import DEFAULT_PATH

DEFAULT_SUGGESTIONS_PATH = Path("data/suggestions.jsonl")

SuggestionStatus = Literal["pending", "accepted", "declined"]


def _current_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


class PatternSuggestion(BaseModel):
    pattern: DetectedPattern
    suggestion_text: str
    status: SuggestionStatus = "pending"


class TaskAgentSpecStub(BaseModel):
    """Minimal, inspectable stub produced on accept -- NOT a real execution
    spec. action is always "draft_only" and gated is always True this pass:
    proves the accept path produces a real artifact without building the full
    TaskAgentSpec execution runner (explicitly out of scope). trigger_hint is
    the pattern's own human-readable description, not a re-derived structured
    time window -- avoids re-parsing free text that's already been rendered
    once, and stays exactly as auditable as the pattern it came from.

    spec_id is this spec's OWN stable identity, distinct from
    source_pattern_id (the DetectedPattern's pattern_id, itself a fresh uuid4
    every detection run -- see _same_underlying_pattern). The spec, once
    created here at accept time, is never re-created, so draft_generator.py's
    DraftAttempt.spec_id can reference this id across every subsequent draft
    for the same accepted spec. supporting_record_ids is a snapshot of the
    real entity_memory records that grounded acceptance -- draft_generator.py
    uses it only as a starting point (to re-derive the recipient), then
    re-scans entity_memory fresh each time it drafts, so new instances
    (including a person's own corrections) are picked up without this stub
    ever needing to be mutated."""

    spec_id: str = Field(default_factory=lambda: str(uuid4()))
    source_pattern_id: str
    trigger_hint: str
    supporting_record_ids: List[str]
    action: Literal["draft_only"] = "draft_only"
    gated: bool = True


class SuggestionRecord(BaseModel):
    """One persisted line in suggestions.jsonl, append-only, same convention
    as entity_memory.jsonl. Stores the FULL DetectedPattern (not just its id)
    so later detection runs can check evidence overlap against it -- pattern_id
    is a fresh uuid4 every detection call, so it can't serve as a stable
    identity across repeated detection on the same/evolving history (see
    _same_underlying_pattern)."""

    suggestion_id: str
    entity_id: str
    pattern: DetectedPattern
    suggestion_text: str
    status: SuggestionStatus
    created_at: str
    resolved_at: Optional[str] = None
    task_agent_spec: Optional[TaskAgentSpecStub] = None


_CONFIDENCE_OPENERS = {
    "low": (
        "It's hard to say for sure yet, but it looks like there might be a pattern here, "
        "based on only a few observed instances so far: "
    ),
    "medium": "I've noticed a fairly consistent pattern: ",
    "high": "I've noticed a clear, consistent pattern: ",
}


def generate_suggestion(pattern: DetectedPattern) -> PatternSuggestion:
    """Turns a DetectedPattern into a single, plain-language suggestion.
    Reuses pattern.description (which already carries the recipient/timing/
    similarity specifics) rather than re-deriving them, and prefixes it with
    an opener whose hedging genuinely varies by pattern.confidence -- a
    low-confidence pattern must never read with the same certainty as a
    high-confidence one. Always ends with a question, never a statement that
    assumes the suggestion was already acted on.
    """
    opener = _CONFIDENCE_OPENERS[pattern.confidence]
    observation = pattern.description[0].lower() + pattern.description[1:]
    suggestion_text = (
        f"{opener}{observation} Want me to start drafting it for you to review each time, "
        "rather than writing it from scratch?"
    )
    return PatternSuggestion(pattern=pattern, suggestion_text=suggestion_text, status="pending")


def _read_all_suggestion_records(entity_id: str, path: Union[str, Path] = DEFAULT_SUGGESTIONS_PATH) -> List[SuggestionRecord]:
    path = Path(path)
    if not path.exists():
        return []
    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = SuggestionRecord.model_validate_json(line)
            if record.entity_id == entity_id:
                records.append(record)
    return records


def _read_latest_suggestion_records(entity_id: str, path: Union[str, Path] = DEFAULT_SUGGESTIONS_PATH) -> List[SuggestionRecord]:
    """The file is append-only -- resolving a suggestion (accept/decline)
    appends a NEW record with the same suggestion_id rather than mutating the
    original line. This collapses to one (the latest) record per
    suggestion_id, mirroring context_schema.py's "most recent wins for
    snapshot fields" pattern, just keyed per-suggestion instead of globally."""
    latest: dict = {}
    for record in _read_all_suggestion_records(entity_id, path=path):
        latest[record.suggestion_id] = record
    return list(latest.values())


def _append_suggestion_record(record: SuggestionRecord, path: Union[str, Path] = DEFAULT_SUGGESTIONS_PATH) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(record.model_dump_json() + "\n")


def _same_underlying_pattern(a: DetectedPattern, b: DetectedPattern) -> bool:
    """Two DetectedPatterns are treated as "the same recurring pattern" if
    their supporting evidence substantially overlaps. pattern_id can't serve
    as a stable identity across repeated detection calls (fresh uuid4 every
    time), so this compares supporting_record_ids instead -- a real, auditable
    substitute: if most of what grounds a newly-detected pattern is the same
    evidence that grounded a prior suggestion, it's the same underlying
    pattern re-detected (likely with a few more supporting days added), not a
    genuinely new one."""
    if a.pattern_type != b.pattern_type:
        return False
    a_ids, b_ids = set(a.supporting_record_ids), set(b.supporting_record_ids)
    if not a_ids or not b_ids:
        return False
    return len(a_ids & b_ids) / len(a_ids) > 0.5


def get_pending_suggestion(
    entity_id: str, path: Union[str, Path] = DEFAULT_SUGGESTIONS_PATH
) -> Optional[SuggestionRecord]:
    """Returns the existing pending SuggestionRecord for this entity, if any --
    used by voice/cli.py to show an unresolved suggestion at session start.
    Deliberately separate from surface_next_suggestion(): that function
    returns None both when a pending suggestion already exists (won't stack a
    second one) AND when nothing new is detected -- a caller that needs to
    distinguish "there's already one to show you" from "there's genuinely
    nothing" needs this, not that one."""
    existing = _read_latest_suggestion_records(entity_id, path=path)
    pending = [r for r in existing if r.status == "pending"]
    return pending[0] if pending else None


def surface_next_suggestion(
    entity_id: str,
    entity_memory_path: Union[str, Path] = DEFAULT_PATH,
    suggestions_path: Union[str, Path] = DEFAULT_SUGGESTIONS_PATH,
    min_occurrences: int = 3,
    lookback_days: int = 30,
) -> Optional[SuggestionRecord]:
    """Runs detection, filters out patterns already suggested (accepted,
    declined, OR still pending -- see below), and returns AT MOST ONE new
    pending SuggestionRecord, persisted, or None if there's nothing new to
    surface.

    Real product-feel requirement, not a nice-to-have: if a person already
    has an unresolved (pending) suggestion, this returns None rather than
    creating a second one -- stacking multiple unresolved "did you notice you
    do X" prompts on someone creates suggestion fatigue and trains them to
    dismiss the assistant wholesale rather than engage with any one ask. One
    clear, resolvable suggestion at a time; the next one only surfaces once
    the current one is accepted or declined.

    Declined patterns are never re-suggested (checked via
    _same_underlying_pattern's evidence-overlap, not pattern_id). Genuinely
    new patterns for the same entity are never suppressed by an old declined
    one -- only patterns that are substantially the SAME evidence as
    something already resolved get skipped.
    """
    existing = _read_latest_suggestion_records(entity_id, path=suggestions_path)
    if any(r.status == "pending" for r in existing):
        return None

    resolved_patterns = [r.pattern for r in existing]  # accepted or declined -- either way, already shown once

    candidates = detect_recurring_message_patterns(
        entity_id, min_occurrences=min_occurrences, lookback_days=lookback_days, path=entity_memory_path
    )
    for pattern in candidates:
        if any(_same_underlying_pattern(pattern, prior) for prior in resolved_patterns):
            continue

        suggestion = generate_suggestion(pattern)
        record = SuggestionRecord(
            suggestion_id=str(uuid4()),
            entity_id=entity_id,
            pattern=pattern,
            suggestion_text=suggestion.suggestion_text,
            status="pending",
            created_at=_current_timestamp(),
        )
        _append_suggestion_record(record, path=suggestions_path)
        return record

    return None


def accept_suggestion(
    suggestion_id: str, entity_id: str, path: Union[str, Path] = DEFAULT_SUGGESTIONS_PATH
) -> SuggestionRecord:
    """Marks the suggestion accepted and attaches a TaskAgentSpecStub -- a
    real, inspectable artifact proving the accept path works, not the full
    execution system. Appends a new record (append-only); does not mutate the
    original pending line."""
    existing = _read_latest_suggestion_records(entity_id, path=path)
    current = next((r for r in existing if r.suggestion_id == suggestion_id), None)
    if current is None:
        raise ValueError(f"No suggestion {suggestion_id!r} found for entity {entity_id!r}.")
    if current.status != "pending":
        raise ValueError(f"Suggestion {suggestion_id!r} is already {current.status!r}, not pending.")

    spec = TaskAgentSpecStub(
        source_pattern_id=current.pattern.pattern_id,
        trigger_hint=current.pattern.description,
        supporting_record_ids=current.pattern.supporting_record_ids,
    )
    updated = current.model_copy(update={"status": "accepted", "resolved_at": _current_timestamp(), "task_agent_spec": spec})
    _append_suggestion_record(updated, path=path)
    return updated


def decline_suggestion(
    suggestion_id: str, entity_id: str, path: Union[str, Path] = DEFAULT_SUGGESTIONS_PATH
) -> SuggestionRecord:
    """Marks the suggestion declined. surface_next_suggestion() will never
    re-suggest the same underlying pattern again (evidence-overlap check),
    but a genuinely different pattern for the same entity is never suppressed
    by this decline."""
    existing = _read_latest_suggestion_records(entity_id, path=path)
    current = next((r for r in existing if r.suggestion_id == suggestion_id), None)
    if current is None:
        raise ValueError(f"No suggestion {suggestion_id!r} found for entity {entity_id!r}.")
    if current.status != "pending":
        raise ValueError(f"Suggestion {suggestion_id!r} is already {current.status!r}, not pending.")

    updated = current.model_copy(update={"status": "declined", "resolved_at": _current_timestamp()})
    _append_suggestion_record(updated, path=path)
    return updated
