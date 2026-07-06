"""`delegate`: the first real, live CLI entrypoint for the voice pipeline
(Cognitive Delegate). Text input only this pass -- stands in for a
transcript. No STT/audio, no TTS; that's Stage 2, proposed (not built) in
PROGRESS.md's checkpoint for this file.

Wires together, for the first time in one live session, everything already
validated in isolation: process_voice_interaction() (classification +
PersonalContext + entity memory + calendar/gmail dispatch),
Pattern-Watcher/Suggestion surfacing (core/suggestion.py), and DraftAttempt
review/correction (core/draft_generator.py). Nothing new is invented here
except this session/CLI plumbing -- assembly of proven pieces, not new
capability, aside from two small additive helpers this file needed and that
now live in core/ (suggestion.get_pending_suggestion,
draft_generator.get_pending_draft/persist_draft_attempt) since neither
module previously exposed a way to ask "is there an unresolved one right
now" without also risking creating a new one.

## Design decision 1: grants source
PermissionRegistry's constructor only ever took an in-memory dict -- no
persistence existed anywhere in this codebase before this file. Proposed and
built here: a local grants.json (DEFAULT_GRANTS_PATH), loaded once at CLI
start via load_permission_registry(). Deny-by-default is preserved at every
layer, not just the happy path: if the file doesn't exist, an empty
PermissionRegistry() is used (everything denied, stated explicitly to
stderr, not silent); if a domain is simply absent from a present file,
PermissionRegistry.is_authorized() already treats that as False -- nothing
here invents a default grant for an unlisted domain. A malformed file (not a
flat {"domain": bool} object) raises loudly rather than being silently
treated as "deny everything" -- a typo'd or malformed grants file is a real
misconfiguration a person should notice and fix, not something that should
quietly degrade to a safe-seeming default that masks the mistake.

## Design decision 2: interactive REPL, JSONL-backed state, not memory-only
Supports an interactive loop for convenient manual testing, but every piece
of "pending" state (pending Suggestion, pending DraftAttempt) is re-read from
suggestions.jsonl/draft_attempts.jsonl at the point it's needed, via
get_pending_suggestion()/get_pending_draft() -- never cached in a Python
variable across the session. This matches how suggestions.jsonl/
draft_attempts.jsonl already persist (append-only, latest-record-wins) and
means real usage later (one CLI invocation per voice note, process exits
between notes) works identically to leaving this REPL open across many
turns, since nothing here depends on the process staying alive to remember
state.

Calendar reading: real GoogleCalendarReader if OAuth credentials exist
(same check test_calendar_live.py uses), else StubCalendarReader -- the
fallback is always stated explicitly to stderr, never silent. Gmail reading
stays StubGmailReader (no real Gmail read integration exists yet). Gmail
acting stays StubGmailActor; calendar acting stays StubCalendarActor --
GoogleCalendarReader is read-only by design (see calendar.py's module
docstring), and no real "act" integration exists for either domain yet.

## Stage 2: file-based speech-to-text, `/audio <path>`
A REPL command, not a separate invocation mode -- chosen over a CLI flag
because the utterance loop already reads free-text lines, and a session may
mix typed utterances and audio files turn by turn; a `/audio` prefix
disambiguates without needing a second entrypoint. `voice/speech_to_text.py`
(Transcriber, faster-whisper) does the actual transcription; this file only
adds the confirmation gate and feeds the result into the EXACT SAME
process_voice_interaction() call path every other utterance already uses --
assembly in front of the existing loop, not a change to it.

Real safety requirement, not optional (see _handle_audio_command): the
transcript is always printed and confirmed ("Heard: '...' -- proceed?
[y/n/edit]") before anything reaches the pipeline. A mis-transcription
silently entering process_voice_interaction() could dispatch a wrong REAL
action (GoogleCalendarReader is real; calendar_act's stub still writes a
confirmed "created" record) or write a garbage EntityMemoryRecord that later
pollutes Pattern-Watcher's pattern detection with content nobody actually
said. "edit" lets the person correct a near-miss transcription rather than
discarding a mostly-right one outright.

The Transcriber is constructed lazily, on first `/audio` use, not at session
start -- sessions that never use audio never pay the ~2s model-load cost or
need faster-whisper importable at all, matching the "local import, real
default, no import-time hard dependency" pattern GoogleCalendarReader
already uses for the google-* packages.

## Image-verification, `/verify <path>`
Same REPL-command precedent as `/audio` -- a distinct input modality (an
image, not a spoken utterance or a recorded voice note), disambiguated via a
prefix rather than retrofitting a VoiceIntentType or touching
process_voice_interaction()/pipeline.py, per the approved image-verification
CLI-wiring proposal. Calls core/image_verification.verify_image() directly
against a fixed default checklist (overridable via --verification-checklist,
repeatable), and prints the result via render_verification_as_text() plus
its confidence -- ephemeral, human-review-only.

Deliberately asymmetric with `/audio`, and this is intentional, not an
oversight: `/audio` requires explicit y/n/edit confirmation before its
result reaches the pipeline, because it CAN dispatch a real action
(calendar_block/email_draft) or write an EntityMemoryRecord that pollutes
Pattern-Watcher. `/verify` does neither -- it never writes to entity memory,
never dispatches anything, and never feeds its result into
process_voice_interaction() at all. There is nothing here for a
confirmation step to gate, so it doesn't have one. No correction loop is
attached either -- criterion-adjustment correction handling stays exactly
where the architecture doc left it: blocked on real usage evidence that
doesn't exist yet, not attempted even in a lighter form here.

## Scrap-metal coarse estimate, `/scrap <path>`
Same REPL-command precedent as `/verify`, calling
core/scrap_estimate.estimate_scrap_lot() directly. No confirmation step,
same reasoning as `/verify`: nothing here dispatches a real action. One
real, flagged difference from `/verify`: this command DOES write one
EntityMemoryRecord per check (see scrap_estimate.py's module docstring for
why -- comparison_note's own requirement forces it), so it is not fully
"ephemeral" the way `/verify` is. No correction loop, same reasoning as
`/verify` -- grading feedback is almost certainly criterion-shaped.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from ..core.draft_generator import (
    DEFAULT_DRAFT_ATTEMPTS_PATH,
    DraftAttempt,
    generate_draft,
    get_pending_draft,
    persist_draft_attempt,
    process_draft_reply,
)
from ..core.entity_memory import DEFAULT_PATH as DEFAULT_ENTITY_MEMORY_PATH
from ..core.permissions import PermissionRegistry
from ..core.suggestion import (
    DEFAULT_SUGGESTIONS_PATH,
    SuggestionRecord,
    accept_suggestion,
    decline_suggestion,
    get_pending_suggestion,
    surface_next_suggestion,
)
from ..core.image_verification import render_verification_as_text, verify_image
from ..core.scrap_estimate import estimate_scrap_lot, render_scrap_estimate_as_text
from .calendar import DEFAULT_CALENDAR_TOKEN_PATH, DEFAULT_CLIENT_SECRET_PATH, GoogleCalendarReader, StubCalendarReader
from .context_schema import MockPersonalData, PersonalContext, build_personal_context
from .gmail import StubGmailReader
from .pipeline import process_voice_interaction
from .speech_to_text import Transcriber

AUDIO_COMMAND_PREFIX = "/audio "
VERIFY_COMMAND_PREFIX = "/verify "
SCRAP_COMMAND_PREFIX = "/scrap "

DEFAULT_GRANTS_PATH = Path("data/grants.json")
DEFAULT_VERIFICATION_CHECKLIST = ["Vendor name visible", "Date visible", "Amount visible"]


def load_permission_registry(path=DEFAULT_GRANTS_PATH) -> PermissionRegistry:
    """Deny-by-default at every layer -- see module docstring's Design
    decision 1 for the full reasoning."""
    path = Path(path)
    if not path.exists():
        print(f"No grants file at {path} -- starting deny-by-default (nothing authorized).", file=sys.stderr)
        return PermissionRegistry()
    with open(path) as f:
        raw = json.load(f)
    if not isinstance(raw, dict) or not all(isinstance(v, bool) for v in raw.values()):
        raise ValueError(f'{path} must be a flat JSON object of {{"domain": true/false}} grants, got: {raw!r}')
    print(f"Loaded grants from {path}: {raw}", file=sys.stderr)
    return PermissionRegistry(grants=raw)


def select_calendar_reader(registry: PermissionRegistry):
    """Real GoogleCalendarReader if OAuth credentials exist, else
    StubCalendarReader -- always stated explicitly, never silent."""
    if DEFAULT_CALENDAR_TOKEN_PATH.exists() and DEFAULT_CLIENT_SECRET_PATH.exists():
        print("Calendar: using real GoogleCalendarReader (OAuth credentials found).", file=sys.stderr)
        return GoogleCalendarReader(registry)
    print(
        f"Calendar: no OAuth credentials at {DEFAULT_CALENDAR_TOKEN_PATH} / {DEFAULT_CLIENT_SECRET_PATH} -- "
        "falling back to StubCalendarReader (canned data). Run scripts/setup_calendar_auth.py for real Calendar reads.",
        file=sys.stderr,
    )
    return StubCalendarReader(registry)


def _handle_pending_suggestion(
    entity_id: str, suggestions_path, entity_memory_path
) -> Optional[SuggestionRecord]:
    """Checks for an existing unresolved suggestion first; if none, runs
    detection for a genuinely new one. Returns the ACCEPTED record if the
    person accepted one this turn, else None (declined or nothing to show)."""
    pending = get_pending_suggestion(entity_id, path=suggestions_path)
    if pending is None:
        pending = surface_next_suggestion(
            entity_id, entity_memory_path=entity_memory_path, suggestions_path=suggestions_path
        )
    if pending is None:
        return None

    print("\n--- Pending suggestion ---")
    print(pending.suggestion_text)
    reply = input("Accept this suggestion? [y/n]: ").strip().lower()
    if reply in ("y", "yes"):
        accepted = accept_suggestion(pending.suggestion_id, entity_id, path=suggestions_path)
        print(f"Accepted. TaskAgentSpecStub created (spec_id={accepted.task_agent_spec.spec_id}).")
        return accepted
    decline_suggestion(pending.suggestion_id, entity_id, path=suggestions_path)
    print("Declined.")
    return None


def _handle_draft_review(
    entity_id: str, attempt: DraftAttempt, attempts_path, entity_memory_path
) -> DraftAttempt:
    print("\n--- Draft for review ---")
    print(attempt.generated_text)
    reply = input("Your reply (approve / correct + say what / reject): ").strip()
    updated = process_draft_reply(
        attempt.attempt_id, entity_id, reply, attempts_path=attempts_path, entity_memory_path=entity_memory_path
    )
    print(f"-> classified as: {updated.status}")
    if updated.status == "corrected":
        print(f"   correction recorded: {updated.correction_text!r}")
    return updated


def _handle_pending_draft(entity_id: str, attempts_path, entity_memory_path) -> Optional[DraftAttempt]:
    """A pending draft left over from a PRIOR invocation -- distinct from one
    just created this turn by accepting a suggestion (handled inline where
    it's created, below)."""
    pending = get_pending_draft(entity_id, path=attempts_path)
    if pending is None:
        return None
    return _handle_draft_review(entity_id, pending, attempts_path, entity_memory_path)


def _print_interaction_result(result, context: PersonalContext) -> None:
    intent = result.voice_intent
    print(f"  intent_type:  {intent.intent_type}")
    print(f"  target:       {intent.target}")
    print(f"  when:         {intent.when}")
    print(f"  content:      {intent.content}")
    print(f"  salience:     {intent.salience}")
    print("  external reads (PersonalContext, as actually rendered):")
    print(f"    gmail:    {context.gmail_context.state}")
    print(f"    calendar: {context.calendar_context.state}")
    print("  entity memory: written (source=voice)")
    if result.calendar_action is not None:
        if result.calendar_action.authorized:
            print(f"  calendar dispatch: {result.calendar_action.confirmation}")
        else:
            print(f"  calendar dispatch DENIED: {result.calendar_action.message}")
    if result.gmail_action is not None:
        if result.gmail_action.authorized:
            print(f"  gmail dispatch: {result.gmail_action.confirmation}")
        else:
            print(f"  gmail dispatch DENIED: {result.gmail_action.message}")


def _handle_audio_command(audio_path: str, transcriber: Transcriber) -> Optional[str]:
    """Transcribes audio_path and gates it behind explicit confirmation
    before anything reaches the pipeline -- see module docstring's Stage 2
    section for why this is a real safety requirement, not optional. Returns
    the (possibly person-edited) text to process, or None if nothing should
    be processed (no speech detected, discarded, or a transcription error)."""
    try:
        result = transcriber.transcribe(audio_path)
    except FileNotFoundError as exc:
        print(f"  {exc}")
        return None
    except Exception as exc:  # a corrupt/unsupported file -- never crash the session over one bad file
        print(f"  Could not transcribe {audio_path!r}: {exc}")
        return None

    if result.likely_silence or not result.text:
        print(
            f"  No clear speech detected in {audio_path!r} "
            f"(language_probability={result.language_probability}) -- nothing was processed."
        )
        return None

    print(f'  Heard: "{result.text}"')
    reply = input("  Proceed? [y/n/edit]: ").strip().lower()
    if reply in ("y", "yes"):
        return result.text
    if reply == "edit":
        edited = input("  Enter corrected text: ").strip()
        return edited or None
    print("  Discarded.")
    return None


def _handle_verify_command(image_path: str, checklist: list) -> None:
    """Runs verify_image() and prints the result -- ephemeral, human-review
    only. Deliberately has NO confirmation step, unlike _handle_audio_command
    above: this command never writes to entity memory and never dispatches
    anything, so there is nothing for a confirmation gate to protect. See
    module docstring's Image-verification section for why this asymmetry
    with /audio is intentional, not an oversight."""
    try:
        result = verify_image(image_path, checklist)
    except FileNotFoundError as exc:
        print(f"  {exc}")
        return
    except Exception as exc:  # a corrupt/unsupported image -- never crash the session over one bad file
        print(f"  Could not verify {image_path!r}: {exc}")
        return

    print(f"  {render_verification_as_text(result)}")
    print(f"  confidence: {result.confidence}")


def _handle_scrap_command(image_path: str, entity_id: str, entity_memory_path) -> None:
    """Runs estimate_scrap_lot() and prints the result. No confirmation step,
    same reasoning as /verify -- nothing here dispatches a real action. See
    module docstring's Scrap-metal section for the one real difference from
    /verify (this DOES write an EntityMemoryRecord, for comparison_note's
    sake) and why that still doesn't need a confirmation gate."""
    try:
        estimate = estimate_scrap_lot(image_path, entity_id, path=entity_memory_path)
    except FileNotFoundError as exc:
        print(f"  {exc}")
        return
    except Exception as exc:  # a corrupt/unsupported image -- never crash the session over one bad file
        print(f"  Could not estimate {image_path!r}: {exc}")
        return

    print(f"  {render_scrap_estimate_as_text(estimate)}")
    print(f"  confidence: {estimate.confidence}")


def _process_utterance(
    entity_id: str, utterance: str, registry: PermissionRegistry, gmail_reader, calendar_reader, entity_memory_path
) -> None:
    context = build_personal_context(
        entity_id,
        mock_data=MockPersonalData(),
        path=entity_memory_path,
        permission_registry=registry,
        gmail_reader=gmail_reader,
        calendar_reader=calendar_reader,
    )
    result = process_voice_interaction(
        entity_id,
        utterance,
        context=context,
        permission_registry=registry,
        entity_memory_path=entity_memory_path,
    )
    print(f"\n> {utterance}")
    _print_interaction_result(result, context)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="delegate", description="Cognitive Delegate voice-pipeline CLI (text input, Stage 1 -- no STT/audio)."
    )
    parser.add_argument("--entity-id", required=True, help="Who this session is for -- tags every entity-memory record.")
    parser.add_argument("--grants-path", default=str(DEFAULT_GRANTS_PATH))
    parser.add_argument("--entity-memory-path", default=str(DEFAULT_ENTITY_MEMORY_PATH))
    parser.add_argument("--suggestions-path", default=str(DEFAULT_SUGGESTIONS_PATH))
    parser.add_argument("--draft-attempts-path", default=str(DEFAULT_DRAFT_ATTEMPTS_PATH))
    parser.add_argument(
        "--verification-checklist",
        action="append",
        dest="verification_checklist",
        default=None,
        help="A checklist item for /verify (repeatable). Defaults to a standard receipt-style checklist if omitted.",
    )
    return parser


def main(argv=None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    registry = load_permission_registry(args.grants_path)
    calendar_reader = select_calendar_reader(registry)
    gmail_reader = StubGmailReader(registry)

    print(f"=== Cognitive Delegate session -- entity_id={args.entity_id!r} ===")

    # Step 2: pending Suggestion (existing, or newly detected this turn).
    accepted = _handle_pending_suggestion(args.entity_id, args.suggestions_path, args.entity_memory_path)
    if accepted is not None:
        spec = accepted.task_agent_spec
        draft = generate_draft(spec, args.entity_id, path=args.entity_memory_path, attempts_path=args.draft_attempts_path)
        persist_draft_attempt(draft, path=args.draft_attempts_path)
        updated = _handle_draft_review(args.entity_id, draft, args.draft_attempts_path, args.entity_memory_path)
        if updated.status == "corrected":
            print("\nGenerating a follow-up draft to demonstrate the correction's effect...")
            second_draft = generate_draft(
                spec, args.entity_id, path=args.entity_memory_path, attempts_path=args.draft_attempts_path
            )
            persist_draft_attempt(second_draft, path=args.draft_attempts_path)
            print("--- Next draft (reflecting your correction) ---")
            print(second_draft.generated_text)

    # Step 3: a pending draft left over from a PRIOR invocation, if any.
    _handle_pending_draft(args.entity_id, args.draft_attempts_path, args.entity_memory_path)

    transcriber: Optional[Transcriber] = None  # lazy -- only constructed on first /audio use
    verification_checklist = args.verification_checklist or DEFAULT_VERIFICATION_CHECKLIST

    print(
        "\nEnter utterances (one per line), '/audio <path>' for a recorded file, "
        "'/verify <path>' to check an image, or '/scrap <path>' for a scrap-metal lot photo. "
        "Type 'quit' to end the session."
    )
    for line in sys.stdin:
        raw = line.strip()
        if not raw:
            continue
        if raw.lower() in ("quit", "exit"):
            break

        if raw.startswith(AUDIO_COMMAND_PREFIX):
            audio_path = raw[len(AUDIO_COMMAND_PREFIX):].strip()
            if transcriber is None:
                print("Loading speech-to-text model (first use this session)...")
                transcriber = Transcriber()
            utterance = _handle_audio_command(audio_path, transcriber)
            if utterance is None:
                continue
        elif raw.startswith(VERIFY_COMMAND_PREFIX):
            image_path = raw[len(VERIFY_COMMAND_PREFIX):].strip()
            _handle_verify_command(image_path, verification_checklist)
            continue
        elif raw.startswith(SCRAP_COMMAND_PREFIX):
            image_path = raw[len(SCRAP_COMMAND_PREFIX):].strip()
            _handle_scrap_command(image_path, args.entity_id, args.entity_memory_path)
            continue
        else:
            utterance = raw

        _process_utterance(args.entity_id, utterance, registry, gmail_reader, calendar_reader, args.entity_memory_path)

    print("\nSession ended.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
