"""The shadow-guess-and-correct loop: turns an accepted TaskAgentSpecStub
(suggestion.py) into a real, reviewable draft, and lets a person's reply
refine the NEXT draft -- proving the accept path leads somewhere real, without
building any actual send/act capability (explicitly out of scope this pass,
same as gmail_act/calendar_act requiring their own separate real-send gate
that doesn't exist yet).

Every draft is surfaced as "please review," never auto-sent -- DraftAttempt's
status vocabulary (pending_review/approved_as_is/corrected/rejected) has no
"sent" state at all, because nothing here can produce one. This mirrors the
same draft-and-review-only discipline as gmail_act/calendar_act: a pattern
being high-confidence changes how a draft is WORDED (see generate_draft's
thin-evidence disclaimer), never whether it requires review.

generate_draft() makes ONE minimal, separate LLM call -- deliberately not
folded into any combined call -- mirroring LuckTestAnalyzer's isolation
pattern in simulator/luck_test.py, for the same reason: a small, single-
purpose prompt is measurably more reliable than one competing demand inside a
larger extraction call.

Correction parsing (classify_draft_reply) is its OWN small classifier, not a
literal reuse of VoiceIntentClassifier. VoiceIntentClassifier's schema
(intent_type/target/when/content/salience) has no field for "did this person
approve, correct, or reject a specific draft they were just shown" -- forcing
that judgment through intent_type's fixed enum would be a genuine schema
mismatch, not a clean reuse. What IS reused is the same architectural
approach VoiceIntentClassifier uses (own prompt, own flat tool-use schema,
FAST_MODEL, a thin Stage-shaped wrapper) rather than standing up a heavier,
differently-shaped mechanism. Flagged here explicitly rather than silently
declared "the same classifier" when it isn't.

The refinement loop's re-scan (_gather_supporting_records) re-derives the
recipient from the spec's original supporting records and re-scans entity
memory fresh every time generate_draft() runs, so a NEW record matching that
recipient -- e.g. another day's real occurrence -- is naturally picked up.

That recipient re-scan alone is NOT enough for corrections, though -- this
was found by live verification, not assumed, and is worth stating plainly:
real corrected phrasing is often casual ("hey sarah, standup notes
attached") and does not contain one of _extract_recipient's gating verbs
(email/message/text/tell/...), so a pure recipient re-scan silently drops
the very correction the loop exists to surface. Fixed by tracking correction
provenance directly: DraftAttempt.correction_record_id records the exact
EntityMemoryRecord a correction produced, and _gather_supporting_records
ALWAYS includes every correction record ever produced for this spec_id
(looked up from draft_attempts.jsonl), in addition to the recipient re-scan
-- so a correction is never dependent on re-matching its own heuristic to
stay part of the evidence set.

A second, distinct gap was found by live verification AFTER that fix: a
genuine new occurrence -- a real, non-correction utterance for a later day of
the same recurring task -- ALSO has no gating verb once real speech has
settled into a casual register (e.g. "hey sarah, standup notes are up, we
finished the auth migration early"), and unlike a correction it has no
spec_id-linked provenance either. It was measured, not assumed, to be
completely invisible to _gather_supporting_records: based_on_record_ids
stayed frozen at the same count across two such occurrences, and
generate_draft() just kept re-emitting the one correction it could still see,
verbatim, regardless of either occurrence's real (and quite different)
content. That looked superficially like "the corrected style persisting" but
was actually blindness to anything new, not evidence of a learned preference.

Fixed with a SCOPED name-mention fallback, _name_and_timing_fallback: within
one spec's own gathering (never a corpus-wide scan), a record naming the
spec's ALREADY-CONFIRMED recipient is included if its hour also falls inside
the pattern's own learned hour-band (_timing_consistent, reused as-is from
pattern_watcher.py, computed from the spec's ORIGINAL supporting records so
the band stays anchored to what was actually accepted rather than drifting
with every new record). This is a genuinely different, narrower check than
the bare-capitalization name detector rejected in pattern_watcher.py's own
circularity fix: that one scanned ALL of entity memory with no idea which
name mattered, and measurably false-positived on ordinary capitalized nouns
("Thursday", "Alex"). This fallback only ever runs already knowing the one
confirmed name, inside one already-accepted spec's own records, gated by a
learned timing signal on top -- categorically narrower, not the same
mechanism reapplied.

This does NOT fully close "is this record really about the same task" --
stated plainly, not glossed over: a record that happens to mention the
recipient's name inside the learned hour-band but is about something
unrelated would still be a false positive (e.g. "sarah asked about the
office lease renewal" at 6:45pm). Timing narrows the false-positive surface
measurably; it does not eliminate it. No further signal is available in this
codebase to close that residual gap without adding one (e.g. a small LLM
relevance check), which is not built here -- flagged as a known, open,
residual risk, not resolved.

A THIRD gap was found by live verification after the two above: even once a
correction is correctly gathered, the model's actual behavior on an
EXPANDING, mixed set was never really "honor the correction" -- it was
"follow whatever's most recent in the chronologically-sorted list."
Disambiguating tests proved this directly: moving a correction to an earlier
position (no longer last) made its influence vanish entirely, even though
nothing else marked it as special -- because nothing DID mark it as special.
correction_record_id was real bookkeeping in our own JSONL, but was never
surfaced to the model itself; the prompt only ever showed a flat list with an
instruction to weight the most recent item, so "correction-following" worked
only by coincidence (a correction is usually the most recent record at the
moment it's given), not by design.

Fixed by tagging examples explicitly in the prompt itself
(_correction_record_ids + generate_draft's example formatting): each example
is labeled either "CORRECTED STYLE" (if its record_id is a correction for
THIS spec, per draft_attempts.jsonl) or "Past occurrence", and the system
prompt instructs the model to follow the LAST "CORRECTED STYLE" example's
style regardless of position, letting plain occurrences after it contribute
content/context without overriding it. Multiple corrections over time are
handled the same way: whichever "CORRECTED STYLE" example is chronologically
last among the corrections supersedes an earlier one -- a second, genuinely
different correction can still be given and will still stick.

Known, deliberate limitation, flagged not hidden: the recipient re-scan
itself (for non-correction records) still depends on
pattern_watcher._extract_recipient; if none of a spec's original supporting
records re-extract a recipient (shouldn't happen given they were already
grouped by one to form the pattern, but not structurally guaranteed), this
falls back to the frozen original supporting_record_ids rather than silently
returning nothing.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, List, Optional, Tuple, Union
from uuid import uuid4

from pydantic import BaseModel

try:
    from typing import Literal
except ImportError:  # pragma: no cover
    from typing_extensions import Literal

from .entity_memory import (
    DEFAULT_PATH,
    EntityMemoryRecord,
    EntityMemoryWriter,
    JsonlEntityMemoryWriter,
    read_records,
)
from .llm_client import LLMClient
from .pattern_watcher import _TIMING_BAND_HOURS, _extract_recipient, _timing_consistent
from .suggestion import TaskAgentSpecStub

FAST_MODEL = "claude-haiku-4-5-20251001"

DEFAULT_DRAFT_ATTEMPTS_PATH = Path("data/draft_attempts.jsonl")

DraftStatus = Literal["pending_review", "approved_as_is", "corrected", "rejected"]
DraftReplyClassification = Literal["approval", "correction", "rejection"]


def _current_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


class DraftAttempt(BaseModel):
    attempt_id: str
    spec_id: str  # links back to TaskAgentSpecStub.spec_id
    entity_id: str
    generated_text: str
    based_on_record_ids: List[str]
    timestamp: str
    status: DraftStatus
    correction_text: Optional[str] = None
    # The EntityMemoryRecord.record_id a correction produced, if status ==
    # "corrected" -- lets _gather_supporting_records always include it for
    # every later draft of this spec, without depending on _extract_recipient
    # being able to re-derive a recipient from the correction's own (often
    # casual) phrasing. See module docstring.
    correction_record_id: Optional[str] = None


# --- Draft generation -------------------------------------------------------

DRAFT_SYSTEM_PROMPT = """You are imitating a person's own established habit for a \
recurring message they send, based on real past examples of how they've phrased \
this same message before. Produce ONE new instance of this message -- this is \
imitation of an established habit, not creative writing. Do not invent new \
content, facts, names, or details the examples don't support.

Examples are given oldest to newest. Some are labeled "CORRECTED STYLE" -- these \
are cases where the person EXPLICITLY asked for this exact wording/tone/structure \
going forward, not just another occurrence that happened to be phrased that way. \
The rest are labeled "Past occurrence".

Answer TWO SEPARATE questions below, and apply BOTH together in your draft --  \
they are independent signals, not competing ones, and neither should be dropped \
to satisfy the other:

1. TONE AND PHRASING STYLE -- what tone, formality, and phrasing structure should \
this draft use? Follow the MOST RECENT "CORRECTED STYLE" example's style, if one \
exists: it is the person's current standard and takes priority over any "Past \
occurrence" example's style, even ones that come later in the list. If more than \
one example is labeled "CORRECTED STYLE", the most recent one supersedes any \
earlier one.

2. RECURRING CONTENT ELEMENTS -- independent of style, does a specific detail or \
phrase (not just general wording, an actual repeated element) appear consistently \
across THREE OR MORE "Past occurrence" examples? If so, include that same \
recurring detail in your draft too, regardless of whether the "CORRECTED STYLE" \
example happens to contain it -- a real recurring content element must not be \
dropped just because a correction exists elsewhere in the list. A detail that \
appears in only one or two examples does not count; it must be repeated three or \
more times to count as recurring content, not a one-off."""

DRAFT_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "draft_text": {"type": "string", "maxLength": 400},
    },
    "required": ["draft_text"],
}


def _learned_hour_window(original_records: List[EntityMemoryRecord]) -> Optional[Tuple[int, int]]:
    """Re-derives the pattern's own learned hour-band from the spec's
    ORIGINAL supporting records (frozen at accept time), reusing
    pattern_watcher._timing_consistent as-is rather than inventing a new
    signal. Anchored to the original evidence, not recomputed from the
    ever-growing gathered set, so the band doesn't drift every time a new
    record is pulled in. None if the original evidence wasn't genuinely
    timing-consistent -- there's no reliable band to gate on in that case."""
    if not original_records:
        return None
    hours = [datetime.fromisoformat(r.timestamp).hour for r in original_records]
    consistent, window = _timing_consistent(hours)
    return window if consistent else None


def _hour_in_window(hour: int, window: Tuple[int, int]) -> bool:
    start, _ = window
    band = {(start + i) % 24 for i in range(_TIMING_BAND_HOURS + 1)}
    return hour in band


def _name_and_timing_fallback(
    recipient: str, hour_window: Optional[Tuple[int, int]], candidates: List[EntityMemoryRecord]
) -> List[EntityMemoryRecord]:
    """Scoped fallback for real occurrences _extract_recipient's verb-gate
    misses (see module docstring for the measured gap this closes): matches
    on the spec's ALREADY-CONFIRMED recipient name appearing anywhere in the
    text, gated by the pattern's own learned hour-band. Only ever called
    within one spec's own gathering, on records already known to be
    voice-sourced and not otherwise matched -- never a corpus-wide scan, so
    this doesn't reintroduce the false-positive risk of pattern_watcher.py's
    rejected bare-capitalization alternative. Explicitly does NOT fully
    resolve "is this record really about the same task" -- see module
    docstring's stated residual risk."""
    if hour_window is None:
        return []
    matches = []
    for r in candidates:
        if recipient not in r.decision_text.lower():
            continue
        try:
            hour = datetime.fromisoformat(r.timestamp).hour
        except ValueError:
            continue
        if _hour_in_window(hour, hour_window):
            matches.append(r)
    return matches


def _gather_supporting_records(
    spec: TaskAgentSpecStub,
    entity_id: str,
    path: Union[str, Path] = DEFAULT_PATH,
    attempts_path: Union[str, Path] = DEFAULT_DRAFT_ATTEMPTS_PATH,
) -> List[EntityMemoryRecord]:
    """Re-derives the CURRENT, possibly-expanded set of real instances backing
    this spec's recurring pattern -- not just the frozen snapshot captured at
    accept time. Combines three sources, since none alone is reliable (see
    module docstring): a recipient-based re-scan (catches new same-style
    occurrences that still use a gating verb), a name+timing-scoped fallback
    (catches casual same-register occurrences the verb-gate misses), and
    every correction record ever recorded for this exact spec_id (corrections
    aren't timing-gated -- a person can correct a draft at any hour)."""
    all_records = read_records(entity_id, path=path)
    by_id = {r.record_id: r for r in all_records}
    original_ids = set(spec.supporting_record_ids)
    original_records = [r for r in all_records if r.record_id in original_ids]

    reference_text = original_records[0].decision_text if original_records else spec.trigger_hint
    recipient = _extract_recipient(reference_text)
    if recipient is None:
        # Can't re-derive the recipient signal -- fall back to the frozen
        # snapshot rather than silently returning nothing.
        matching_ids = {r.record_id for r in original_records}
    else:
        matching_ids = {
            r.record_id for r in all_records if r.source == "voice" and _extract_recipient(r.decision_text) == recipient
        }

        hour_window = _learned_hour_window(original_records)
        fallback_candidates = [
            r for r in all_records if r.source == "voice" and r.record_id not in matching_ids
        ]
        for r in _name_and_timing_fallback(recipient, hour_window, fallback_candidates):
            matching_ids.add(r.record_id)

    for attempt in _read_all_draft_attempts(entity_id, path=attempts_path):
        if attempt.spec_id == spec.spec_id and attempt.correction_record_id:
            matching_ids.add(attempt.correction_record_id)

    matching = [by_id[rid] for rid in matching_ids if rid in by_id]
    matching.sort(key=lambda r: r.timestamp)
    return matching


def _correction_record_ids(
    spec: TaskAgentSpecStub, entity_id: str, attempts_path: Union[str, Path] = DEFAULT_DRAFT_ATTEMPTS_PATH
) -> set:
    """Every EntityMemoryRecord.record_id that is a correction FOR THIS SPEC
    (per draft_attempts.jsonl) -- used to tag examples explicitly in the
    prompt (see generate_draft), so the model is told which examples are
    stated corrections rather than inferring it from list position, which
    live verification showed does not work (see module docstring)."""
    return {
        attempt.correction_record_id
        for attempt in _read_all_draft_attempts(entity_id, path=attempts_path)
        if attempt.spec_id == spec.spec_id and attempt.correction_record_id
    }


def _format_examples(
    records: List[EntityMemoryRecord], correction_ids: set, example_text_transform: Optional[Callable[[str], str]] = None
) -> str:
    lines = []
    for i, r in enumerate(records):
        label = (
            "CORRECTED STYLE -- the person explicitly asked for this going forward"
            if r.record_id in correction_ids
            else "Past occurrence"
        )
        text = example_text_transform(r.decision_text) if example_text_transform else r.decision_text
        lines.append(f"{i + 1}. [{label}] {text}")
    return "\n".join(lines)


def generate_draft(
    spec: TaskAgentSpecStub,
    entity_id: str,
    client: Optional[LLMClient] = None,
    path: Union[str, Path] = DEFAULT_PATH,
    attempts_path: Union[str, Path] = DEFAULT_DRAFT_ATTEMPTS_PATH,
    min_occurrences_for_confidence: int = 3,
    example_text_transform: Optional[Callable[[str], str]] = None,
    output_text_transform: Optional[Callable[[str], str]] = None,
) -> DraftAttempt:
    """Pulls the real prior instances of this recurring message from entity
    memory (re-derived fresh, see _gather_supporting_records) and produces a
    new draft via a single, minimal, separate LLM call.

    If fewer real instances back this draft than min_occurrences_for_confidence
    (matching detect_recurring_message_patterns' own default threshold), the
    surfaced text says so explicitly ("early days, this is a rough first
    attempt") rather than presenting a thin-evidence draft with false
    confidence -- same discipline as demand_durability/leverage_type.

    example_text_transform/output_text_transform: optional, both default to
    None (no-op) -- every existing caller (recurring_message included) is
    completely unaffected. Added for domains whose STORED decision_text
    carries scaffolding needed only for gathering/matching (e.g. a
    recipient-verb-gate phrase) that the model itself should never see --
    information hiding applied to that scaffolding, the same principle as
    never leaking prior-lot narratives elsewhere in this codebase. The
    gathering/matching logic above (_gather_supporting_records,
    _correction_record_ids) always operates on the RAW stored text,
    unaffected by either transform -- only what the model sees in the
    prompt, and what a caller displays afterward, changes.
    """
    client = client or LLMClient(model=FAST_MODEL)
    supporting_records = _gather_supporting_records(spec, entity_id, path=path, attempts_path=attempts_path)
    correction_ids = _correction_record_ids(spec, entity_id, attempts_path=attempts_path)

    examples = _format_examples(supporting_records, correction_ids, example_text_transform)
    user_message = (
        f"Examples of this recurring message, oldest to newest:\n{examples}\n\n"
        "Generate the next instance of this message in the same style."
    )

    result = client.call_tool(
        system=DRAFT_SYSTEM_PROMPT,
        user_message=user_message,
        tool_name="record_draft",
        tool_description="Record the generated draft message.",
        input_schema=DRAFT_TOOL_SCHEMA,
        max_tokens=256,
    )
    draft_text = result["draft_text"]
    if output_text_transform:
        draft_text = output_text_transform(draft_text)

    if len(supporting_records) < min_occurrences_for_confidence:
        draft_text = (
            f"(Early days -- this is a rough first attempt based on only "
            f"{len(supporting_records)} real instance(s) so far.) {draft_text}"
        )

    return DraftAttempt(
        attempt_id=str(uuid4()),
        spec_id=spec.spec_id,
        entity_id=entity_id,
        generated_text=draft_text,
        based_on_record_ids=[r.record_id for r in supporting_records],
        timestamp=_current_timestamp(),
        status="pending_review",
    )


# --- Draft attempt persistence (JSONL, same append-only convention) --------


def _read_all_draft_attempts(entity_id: str, path: Union[str, Path] = DEFAULT_DRAFT_ATTEMPTS_PATH) -> List[DraftAttempt]:
    path = Path(path)
    if not path.exists():
        return []
    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = DraftAttempt.model_validate_json(line)
            if record.entity_id == entity_id:
                records.append(record)
    return records


def _read_latest_draft_attempts(entity_id: str, path: Union[str, Path] = DEFAULT_DRAFT_ATTEMPTS_PATH) -> List[DraftAttempt]:
    """Append-only file -- a status change appends a new record with the same
    attempt_id rather than mutating the original line. Collapses to the
    latest record per attempt_id, same convention as suggestion.py."""
    latest: dict = {}
    for record in _read_all_draft_attempts(entity_id, path=path):
        latest[record.attempt_id] = record
    return list(latest.values())


def _append_draft_attempt(record: DraftAttempt, path: Union[str, Path] = DEFAULT_DRAFT_ATTEMPTS_PATH) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(record.model_dump_json() + "\n")


def persist_draft_attempt(attempt: DraftAttempt, path: Union[str, Path] = DEFAULT_DRAFT_ATTEMPTS_PATH) -> None:
    """Public entrypoint for persisting a DraftAttempt generate_draft() just
    produced -- generate_draft() itself deliberately does NOT persist (compute
    vs. persist stays separate, same reasoning as EntityMemoryWriter being a
    Protocol rather than folded into Stage.run()'s return). Used by
    voice/cli.py, a different subpackage, so it gets a real public function
    rather than reaching into the underscore-prefixed _append_draft_attempt
    directly across a package boundary."""
    _append_draft_attempt(attempt, path=path)


def get_pending_draft(entity_id: str, path: Union[str, Path] = DEFAULT_DRAFT_ATTEMPTS_PATH) -> Optional[DraftAttempt]:
    """Returns the single pending_review DraftAttempt for this entity, if any
    -- used by voice/cli.py to check for an unresolved draft at session
    start, re-reading fresh from draft_attempts.jsonl each time rather than
    depending on any in-memory state (same reload-per-invocation principle as
    suggestion.get_pending_suggestion()). Only one pending draft is ever
    expected at a time in this pass's flow, but if more than one somehow
    exists, the most recent is returned rather than guessed at."""
    pending = [a for a in _read_latest_draft_attempts(entity_id, path=path) if a.status == "pending_review"]
    if not pending:
        return None
    return max(pending, key=lambda a: a.timestamp)


# --- Correction parsing ------------------------------------------------------
#
# Own small classifier -- NOT a literal reuse of VoiceIntentClassifier. See
# module docstring for why forcing this through VoiceIntentClassifier's
# intent_type enum would be a real schema mismatch, not a clean fit.

REPLY_SYSTEM_PROMPT = """You are classifying how a person responded to a drafted \
message they were shown for review, before it is used for anything. Given the \
original draft and the person's reply, classify the reply as EXACTLY ONE of:

approval: they are satisfied with the draft as-is (e.g. "looks good", "yes", \
"send it", "that works") -- nothing is actually sent, this only means they \
approve the wording.

correction: they want the wording, content, or tone changed. correction_text \
must be the CORRECTED version of the message itself, in their own words, drawn \
only from what they actually said -- never invent content they didn't provide. \
If they only describe the change ("make it shorter") without restating the \
message, apply their instruction to the original draft to produce the corrected \
text, but do not add facts or details neither the draft nor the reply supports.

rejection: they don't want this draft, or don't want this recurring suggestion \
at all (e.g. "no", "don't bother", "stop asking", "not this one").

If the reply is NOT a correction, correction_text must be an empty string."""

REPLY_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "classification": {"type": "string", "enum": ["approval", "correction", "rejection"]},
        "correction_text": {"type": "string", "maxLength": 400},
    },
    "required": ["classification", "correction_text"],
}


def classify_draft_reply(
    draft_text: str, reply_text: str, client: Optional[LLMClient] = None
) -> Tuple[DraftReplyClassification, str]:
    client = client or LLMClient(model=FAST_MODEL)
    user_message = f"Draft shown to the person:\n{draft_text}\n\nPerson's reply:\n{reply_text}"
    result = client.call_tool(
        system=REPLY_SYSTEM_PROMPT,
        user_message=user_message,
        tool_name="classify_reply",
        tool_description="Classify the person's reply to a drafted message.",
        input_schema=REPLY_TOOL_SCHEMA,
        max_tokens=256,
    )
    return result["classification"], result["correction_text"]


def process_draft_reply(
    attempt_id: str,
    entity_id: str,
    reply_text: str,
    client: Optional[LLMClient] = None,
    attempts_path: Union[str, Path] = DEFAULT_DRAFT_ATTEMPTS_PATH,
    entity_memory_path: Union[str, Path] = DEFAULT_PATH,
    entity_memory_writer: Optional[EntityMemoryWriter] = None,
) -> DraftAttempt:
    """Classifies reply_text against the pending DraftAttempt and updates its
    status. On a correction, ALSO writes correction_text as a new
    EntityMemoryRecord(source="voice") -- this is what feeds the refinement
    loop: the next generate_draft() call for the same spec re-scans entity
    memory fresh and picks this up (see _gather_supporting_records)."""
    existing = _read_latest_draft_attempts(entity_id, path=attempts_path)
    current = next((a for a in existing if a.attempt_id == attempt_id), None)
    if current is None:
        raise ValueError(f"No draft attempt {attempt_id!r} found for entity {entity_id!r}.")
    if current.status != "pending_review":
        raise ValueError(f"Draft attempt {attempt_id!r} is already {current.status!r}, not pending_review.")

    classification, correction_text = classify_draft_reply(current.generated_text, reply_text, client=client)

    if classification == "approval":
        updated = current.model_copy(update={"status": "approved_as_is"})
    elif classification == "rejection":
        updated = current.model_copy(update={"status": "rejected"})
    else:
        new_record = EntityMemoryRecord(
            entity_id=entity_id,
            source="voice",
            decision_text=correction_text,
            goals=[],
            constraints=[],
        )
        writer = entity_memory_writer or JsonlEntityMemoryWriter(path=entity_memory_path)
        writer.write(new_record)
        updated = current.model_copy(
            update={
                "status": "corrected",
                "correction_text": correction_text,
                "correction_record_id": new_record.record_id,
            }
        )

    _append_draft_attempt(updated, path=attempts_path)
    return updated
