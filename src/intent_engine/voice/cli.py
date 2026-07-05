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
from .calendar import DEFAULT_CALENDAR_TOKEN_PATH, DEFAULT_CLIENT_SECRET_PATH, GoogleCalendarReader, StubCalendarReader
from .context_schema import MockPersonalData, PersonalContext, build_personal_context
from .gmail import StubGmailReader
from .pipeline import process_voice_interaction

DEFAULT_GRANTS_PATH = Path("data/grants.json")


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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="delegate", description="Cognitive Delegate voice-pipeline CLI (text input, Stage 1 -- no STT/audio)."
    )
    parser.add_argument("--entity-id", required=True, help="Who this session is for -- tags every entity-memory record.")
    parser.add_argument("--grants-path", default=str(DEFAULT_GRANTS_PATH))
    parser.add_argument("--entity-memory-path", default=str(DEFAULT_ENTITY_MEMORY_PATH))
    parser.add_argument("--suggestions-path", default=str(DEFAULT_SUGGESTIONS_PATH))
    parser.add_argument("--draft-attempts-path", default=str(DEFAULT_DRAFT_ATTEMPTS_PATH))
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

    print("\nEnter utterances (one per line). Type 'quit' to end the session.")
    for line in sys.stdin:
        utterance = line.strip()
        if not utterance:
            continue
        if utterance.lower() in ("quit", "exit"):
            break

        context = build_personal_context(
            args.entity_id,
            mock_data=MockPersonalData(),
            path=args.entity_memory_path,
            permission_registry=registry,
            gmail_reader=gmail_reader,
            calendar_reader=calendar_reader,
        )
        result = process_voice_interaction(
            args.entity_id,
            utterance,
            context=context,
            permission_registry=registry,
            entity_memory_path=args.entity_memory_path,
        )
        print(f"\n> {utterance}")
        _print_interaction_result(result, context)

    print("\nSession ended.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
