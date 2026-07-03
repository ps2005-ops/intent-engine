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
"""

from pathlib import Path
from typing import List, Optional, Union

from pydantic import BaseModel, Field

from ..core.entity_memory import DEFAULT_PATH, read_records


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


class PersonalContext(BaseModel):
    entity_id: str
    entity_history: EntityHistorySummary
    mock_data: MockPersonalData

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

        return "\n".join(lines)


def build_personal_context(
    entity_id: str,
    mock_data: MockPersonalData,
    path: Union[str, Path] = DEFAULT_PATH,
) -> PersonalContext:
    """The 'view': queries real entity_memory.read_records(entity_id), derives
    EntityHistorySummary from whatever's found (empty summary if no records),
    pairs it with the supplied mock data.

    read_records() already normalizes entity_id internally, so the raw string
    passed here doesn't need pre-normalization -- consistent with how
    JsonlEntityMemoryWriter.write() handles it on the write side. `path` defaults
    to the real entity-memory store but is overridable for tests, same pattern as
    JsonlEntityMemoryWriter/read_records themselves.
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

    return PersonalContext(entity_id=entity_id, entity_history=history, mock_data=mock_data)
