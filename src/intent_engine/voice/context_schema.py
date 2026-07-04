"""PersonalContext: a view computed from entity memory, not a standalone snapshot
object (superseded the original Week 4 plan — see the amendment note at the top of
docs/weekly/week-04-plan.md and docs/weekly/intent-engine-v2-entity-memory.md).

This is the first real test of whether "PersonalContext as a view over entity
memory" works cleanly. Real data (EntityHistorySummary, from
core.entity_memory.read_records) and mock data (MockPersonalData, for the
calendar/relationship/communication concepts entity memory has no writer for yet —
that's Stage C) are kept structurally separate, not blended into one flat schema,
so it's never ambiguous which fields are fact vs. placeholder. Stage D will
eventually need to reason over this data without confusing the two.

gmail_context/calendar_context (added when this got wired into the live
process_voice_interaction() path): gated, real (stub) pulls from
StubGmailReader/StubCalendarReader, kept as their own third category alongside
entity_history (real) and mock_data (placeholder) -- domain-named, not collapsed
into one shared bucket, matching the project's existing precedent (the
domain-string convention) of never forcing distinct domains into a shared shape.

Their `state` field is three-valued from day one, not a bool -- "fetched",
"not_authorized", "skipped_for_cost". Only the first two are ever produced today
(every pull is attempted unconditionally, matching today's real, near-zero stub
cost). "skipped_for_cost" is reserved, unused, for when a future cost-based
gating or caching strategy decides NOT to attempt a pull at all -- the same
reserved-field pattern already used for EntityMemoryRecord.outcome. Whether pulls
should stay unconditional, become conditionally gated, or get cached is an
explicit, OPEN, deliberately deferred decision -- see PROGRESS.md and
docs/weekly/intent-engine-v2-entity-memory.md. Deciding it now would mean
guessing against a cost (real Stage C vendor latency) that doesn't exist yet
with stubs -- the same trap this project already avoided once with entity_id
normalization and the compound-action schema. When that decision does get made,
it changes which pull-strategy populates this field, not the field shape itself.
"""

from pathlib import Path
from typing import List, Optional, Union

from pydantic import BaseModel, Field

try:
    from typing import Literal
except ImportError:  # pragma: no cover
    from typing_extensions import Literal

from ..core.entity_memory import DEFAULT_PATH, read_records
from ..core.permissions import PermissionRegistry
from .calendar import CalendarEvent, StubCalendarReader
from .gmail import GmailMessage, StubGmailReader

ExternalReadState = Literal["fetched", "not_authorized", "skipped_for_cost"]


class EntityHistorySummary(BaseModel):
    """Derived from real entity_memory.read_records(entity_id). All fields
    empty/None if this entity has no records yet."""

    recent_goals: List[str] = Field(default_factory=list)
    recent_decisions: List[str] = Field(default_factory=list)
    risk_tolerance: Optional[str] = None
    primary_priority: Optional[str] = None


class MockPersonalData(BaseModel):
    """Placeholder data for concepts entity memory has no writer for yet
    (Stage C territory: calendar, relationships, communication patterns). Kept
    structurally separate from EntityHistorySummary so it's never ambiguous
    which fields are real vs. placeholder."""

    calendar_density: Optional[str] = None
    important_relationships: List[str] = Field(default_factory=list)
    communication_patterns: Optional[str] = None


class GmailContext(BaseModel):
    """Result of a gated pull from StubGmailReader, three-valued -- see module
    docstring for why "not_authorized" and "skipped_for_cost" are distinct from
    each other and from an empty `messages` list."""

    state: ExternalReadState
    messages: List[GmailMessage] = Field(default_factory=list)
    message: Optional[str] = None


class CalendarContext(BaseModel):
    """Result of a gated pull from StubCalendarReader, three-valued -- see
    GmailContext."""

    state: ExternalReadState
    events: List[CalendarEvent] = Field(default_factory=list)
    message: Optional[str] = None


class PersonalContext(BaseModel):
    entity_id: str
    entity_history: EntityHistorySummary
    mock_data: MockPersonalData
    gmail_context: GmailContext
    calendar_context: CalendarContext

    def to_prompt_text(self) -> str:
        lines = ["Known history (from entity memory):"]
        history_lines = []
        if self.entity_history.recent_goals:
            history_lines.append(f"  Recent goals: {', '.join(self.entity_history.recent_goals)}")
        if self.entity_history.recent_decisions:
            history_lines.append(f"  Recent decisions: {', '.join(self.entity_history.recent_decisions)}")
        if self.entity_history.risk_tolerance:
            history_lines.append(f"  Risk tolerance: {self.entity_history.risk_tolerance}")
        if self.entity_history.primary_priority:
            history_lines.append(f"  Primary priority: {self.entity_history.primary_priority}")
        lines.extend(history_lines or ["  No history yet -- this entity has no prior entity-memory records."])

        lines.append("")
        lines.append("Assumed context (placeholder, not yet real data):")
        mock_lines = []
        if self.mock_data.calendar_density:
            mock_lines.append(f"  Calendar density: {self.mock_data.calendar_density}")
        if self.mock_data.important_relationships:
            mock_lines.append(f"  Important relationships: {', '.join(self.mock_data.important_relationships)}")
        if self.mock_data.communication_patterns:
            mock_lines.append(f"  Communication patterns: {self.mock_data.communication_patterns}")
        lines.extend(mock_lines or ["  No mock context provided."])

        lines.append("")
        lines.append("External reads (real, permission-gated, stub data):")
        if self.gmail_context.state == "fetched":
            if self.gmail_context.messages:
                lines.append(f"  Gmail: {len(self.gmail_context.messages)} message(s) -- "
                              f"{', '.join(m.subject for m in self.gmail_context.messages)}")
            else:
                lines.append("  Gmail: authorized, no messages.")
        elif self.gmail_context.state == "not_authorized":
            lines.append(f"  Gmail: {self.gmail_context.message or 'not authorized.'}")
        else:
            lines.append("  Gmail: skipped (not attempted this pass).")

        if self.calendar_context.state == "fetched":
            if self.calendar_context.events:
                lines.append(f"  Calendar: {len(self.calendar_context.events)} event(s) -- "
                              f"{', '.join(e.title for e in self.calendar_context.events)}")
            else:
                lines.append("  Calendar: authorized, no events.")
        elif self.calendar_context.state == "not_authorized":
            lines.append(f"  Calendar: {self.calendar_context.message or 'not authorized.'}")
        else:
            lines.append("  Calendar: skipped (not attempted this pass).")

        return "\n".join(lines)


def build_personal_context(
    entity_id: str,
    mock_data: MockPersonalData,
    path: Union[str, Path] = DEFAULT_PATH,
    permission_registry: Optional[PermissionRegistry] = None,
    gmail_reader: Optional[StubGmailReader] = None,
    calendar_reader: Optional[StubCalendarReader] = None,
) -> PersonalContext:
    """The 'view': queries real entity_memory.read_records(entity_id), derives
    EntityHistorySummary from whatever's found (empty summary if no records),
    pairs it with the supplied mock data, and pulls gated gmail_read/calendar_read
    data unconditionally (today's interim pull-strategy -- see module docstring).

    read_records() already normalizes entity_id internally, so the raw string
    passed here doesn't need pre-normalization -- consistent with how
    JsonlEntityMemoryWriter.write() handles it on the write side. `path` defaults
    to the real entity-memory store but is overridable for tests, same pattern as
    JsonlEntityMemoryWriter/read_records themselves.

    permission_registry defaults to a fresh, deny-by-default PermissionRegistry()
    if not supplied -- same "deny by default, not silently permissive" behavior
    as everywhere else this registry is used. gmail_reader/calendar_reader are
    overridable for tests, same dependency-injection pattern as the rest of
    voice/pipeline.py.
    """
    records = read_records(entity_id, path=path)

    if not records:
        history = EntityHistorySummary()
    else:
        # Most recent record (by timestamp) for risk_tolerance/primary_priority --
        # a current snapshot, not an average. goals/decisions aggregate across ALL
        # records instead, since those are a history, not a single current state.
        most_recent = max(records, key=lambda r: r.timestamp)
        history = EntityHistorySummary(
            recent_goals=[goal for record in records for goal in record.goals],
            recent_decisions=[record.decision_text for record in records],
            risk_tolerance=most_recent.risk_tolerance,
            primary_priority=most_recent.primary_priority,
        )

    registry = permission_registry or PermissionRegistry()
    gmail_reader = gmail_reader or StubGmailReader(registry)
    calendar_reader = calendar_reader or StubCalendarReader(registry)

    gmail_read_result = gmail_reader.read_messages()
    gmail_context = GmailContext(
        state="fetched" if gmail_read_result.authorized else "not_authorized",
        messages=gmail_read_result.messages,
        message=gmail_read_result.message,
    )

    calendar_read_result = calendar_reader.read_events()
    calendar_context = CalendarContext(
        state="fetched" if calendar_read_result.authorized else "not_authorized",
        events=calendar_read_result.events,
        message=calendar_read_result.message,
    )

    return PersonalContext(
        entity_id=entity_id,
        entity_history=history,
        mock_data=mock_data,
        gmail_context=gmail_context,
        calendar_context=calendar_context,
    )
