"""Stage C: stub Calendar integration, gated by the real PermissionRegistry
(core/permissions.py). Proves the permission-check plumbing and the read/act
two-tier domain-string distinction work end-to-end before any real OAuth/vendor
complexity gets added. No real Google Calendar API calls anywhere in this module
-- canned events for reads, a canned confirmation string for the "act" stub,
nothing actually created or modified.

Read and act are two separate domain strings ("calendar_read", "calendar_act"),
not a new PermissionRegistry method -- it stays single-arg
(is_authorized(domain: str) -> bool), unchanged, per explicit design decision.
"""

from typing import List, Optional

from pydantic import BaseModel

from ..core.permissions import PermissionRegistry

CALENDAR_READ_DOMAIN = "calendar_read"
CALENDAR_ACT_DOMAIN = "calendar_act"


class CalendarEvent(BaseModel):
    title: str
    when: str  # human-readable, not parsed -- matches VoiceIntent.when's convention
    duration_minutes: int


_CANNED_EVENTS = [
    CalendarEvent(title="Investor sync", when="Monday 10am", duration_minutes=30),
    CalendarEvent(title="Product review", when="Tuesday 2pm", duration_minutes=60),
    CalendarEvent(title="1:1 with Sarah", when="Wednesday 9am", duration_minutes=30),
]


class CalendarReadResult(BaseModel):
    # `authorized` and `message` exist so "not authorized" is stated explicitly,
    # not confused with "authorized, but zero events" -- an empty `events` list
    # alone can't distinguish those two states. Same "state what it would do,
    # don't silently skip" principle as the two-engine design.
    authorized: bool
    events: List[CalendarEvent] = []
    message: Optional[str] = None


class CalendarActResult(BaseModel):
    authorized: bool
    confirmation: Optional[str] = None
    message: Optional[str] = None


class StubCalendarReader:
    """Fake calendar reader -- returns hardcoded events, gated by "calendar_read"."""

    def __init__(self, registry: PermissionRegistry):
        self.registry = registry

    def read_events(self) -> CalendarReadResult:
        if not self.registry.is_authorized(CALENDAR_READ_DOMAIN):
            return CalendarReadResult(authorized=False, message="Not authorized to read calendar.")
        return CalendarReadResult(authorized=True, events=list(_CANNED_EVENTS))


class StubCalendarActor:
    """Fake calendar actor -- create_event() doesn't actually create anything,
    just returns a canned confirmation, gated by "calendar_act" specifically --
    separate from "calendar_read" so a read grant never implies an act grant."""

    def __init__(self, registry: PermissionRegistry):
        self.registry = registry

    def create_event(self, title: str, when: str) -> CalendarActResult:
        if not self.registry.is_authorized(CALENDAR_ACT_DOMAIN):
            return CalendarActResult(authorized=False, message="Not authorized to create calendar events.")
        return CalendarActResult(
            authorized=True,
            confirmation=f"Created event '{title}' at {when} (stub -- nothing actually created).",
        )
