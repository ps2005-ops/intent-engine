"""Stage C: Calendar integration, gated by the real PermissionRegistry
(core/permissions.py). StubCalendarReader/StubCalendarActor prove the
permission-check plumbing and the read/act two-tier domain-string distinction
work end-to-end before any real OAuth/vendor complexity gets added -- canned
events for reads, a canned confirmation string for the "act" stub, nothing
actually created or modified.

Read and act are two separate domain strings ("calendar_read", "calendar_act"),
not a new PermissionRegistry method -- it stays single-arg
(is_authorized(domain: str) -> bool), unchanged, per explicit design decision.

GoogleCalendarReader (below) is the first real (non-stub) Stage C integration,
read-only. It implements the SAME read_events() -> CalendarReadResult contract
as StubCalendarReader -- context_schema.py's build_personal_context() doesn't
need to change to use it instead of the stub. Two real deviations from the
stub's simplicity, both forced by the real API, not implementation choices:
(1) construction needs OAuth credentials + a time window, not just a
PermissionRegistry -- "list all events ever" isn't a real Calendar API
operation; (2) CalendarEvent.when has to be derived from a real ISO 8601
timestamp (or an all-day event's bare date), not copied from canned text.

Default time window: now through +7 days, primary calendar only, stated
explicitly here, not an implicit choice. Recurring events are represented by
their next single upcoming occurrence within that window, not expanded into
every instance within it. All-day events get a distinct "All day, <date>"
`when` rather than a fabricated time. All three are deliberate scope limits --
same treatment as email_draft's fresh-compose-only scope -- not oversights;
revisit if real usage shows a week isn't enough, or recurring-event dedup
isn't the right call for how people actually use this.

Every failure mode a real API introduces (expired/revoked OAuth token, rate
limit, network failure, malformed response) is caught inside read_events() and
translated into CalendarReadResult(authorized=False, failed=True, message=...)
-- never allowed to raise into process_voice_interaction(). "not_authorized"
and "read_failed" are kept distinct throughout (see context_schema.py's module
docstring for why conflating them would be a real problem, not just an
inconsistency).
"""

import datetime as dt
import logging
from pathlib import Path
from typing import List, Optional, Tuple, Union

from pydantic import BaseModel

from ..core.permissions import PermissionRegistry

CALENDAR_READ_DOMAIN = "calendar_read"
CALENDAR_ACT_DOMAIN = "calendar_act"

logger = logging.getLogger(__name__)


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
    # Additive, defaults False so every existing stub-produced result is
    # unaffected: distinguishes "not_authorized" (authorized=False,
    # failed=False -- a permission decision) from "read_failed"
    # (authorized=False, failed=True -- an operational failure: expired token,
    # rate limit, network error, malformed response). Conflating the two would
    # hide a real operational problem behind wording that implies the person
    # declined access.
    failed: bool = False


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


DEFAULT_CALENDAR_TOKEN_PATH = Path("data/calendar_token.json")
DEFAULT_CLIENT_SECRET_PATH = Path("credentials/client_secret.json")
CALENDAR_READONLY_SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
DEFAULT_LOOKAHEAD_DAYS = 7  # locked-in default: now through +7 days -- explicit, not implicit


def _format_event_when(start: dict) -> str:
    """`start` is a Calendar API event's 'start' dict: either
    {'dateTime': ..., 'timeZone': ...} for a timed event, or {'date': ...} for
    an all-day event. All-day events get a distinct format, not a fabricated
    time -- a real event has no "time" to invent for that case."""
    if "date" in start:
        try:
            date = dt.date.fromisoformat(start["date"])
            return f"All day, {date.strftime('%b %d, %Y')}"
        except ValueError:
            return f"All day, {start['date']}"
    raw = start.get("dateTime")
    if not raw:
        return "unspecified time"
    try:
        parsed = dt.datetime.fromisoformat(raw)
        return parsed.strftime("%a %b %d, %I:%M %p")
    except ValueError:
        return raw


def _event_duration_minutes(start: dict, end: dict) -> int:
    if "date" in start and "date" in end:
        start_date = dt.date.fromisoformat(start["date"])
        end_date = dt.date.fromisoformat(end["date"])
        return max((end_date - start_date).days, 1) * 24 * 60
    try:
        start_dt = dt.datetime.fromisoformat(start["dateTime"])
        end_dt = dt.datetime.fromisoformat(end["dateTime"])
        return int((end_dt - start_dt).total_seconds() // 60)
    except (KeyError, ValueError):
        return 0


class GoogleCalendarReader:
    """Real Google Calendar integration, read-only. Same read_events() ->
    CalendarReadResult contract as StubCalendarReader -- see module docstring
    for the two real deviations (construction inputs, CalendarEvent.when
    derivation) and the failure-translation behavior.
    """

    def __init__(
        self,
        registry: PermissionRegistry,
        token_path: Union[str, Path] = DEFAULT_CALENDAR_TOKEN_PATH,
        client_secret_path: Union[str, Path] = DEFAULT_CLIENT_SECRET_PATH,
        lookahead_days: int = DEFAULT_LOOKAHEAD_DAYS,
    ):
        self.registry = registry
        self.token_path = Path(token_path)
        self.client_secret_path = Path(client_secret_path)
        self.lookahead_days = lookahead_days

    def _load_credentials(self) -> Tuple[Optional[object], Optional[str]]:
        # Imported here, not at module level, so importing this module doesn't
        # require the google-* packages unless GoogleCalendarReader is actually
        # instantiated -- StubCalendarReader/StubCalendarActor stay usable
        # without them installed.
        from google.auth.exceptions import RefreshError
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials

        if not self.token_path.exists():
            return None, "Calendar OAuth not yet set up -- run scripts/setup_calendar_auth.py once."

        creds = Credentials.from_authorized_user_file(str(self.token_path), CALENDAR_READONLY_SCOPES)
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                self.token_path.write_text(creds.to_json())
            except RefreshError as exc:
                logger.warning("Calendar token refresh failed: %s", exc)
                return None, "Calendar token needs re-authorization -- run scripts/setup_calendar_auth.py again."
        return creds, None

    def read_events(self) -> CalendarReadResult:
        if not self.registry.is_authorized(CALENDAR_READ_DOMAIN):
            return CalendarReadResult(authorized=False, message="Not authorized to read calendar.")

        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError

        creds, creds_error = self._load_credentials()
        if creds is None:
            return CalendarReadResult(authorized=False, failed=True, message=creds_error)

        now = dt.datetime.now(dt.timezone.utc)
        window_end = now + dt.timedelta(days=self.lookahead_days)

        try:
            service = build("calendar", "v3", credentials=creds, cache_discovery=False)
            response = (
                service.events()
                .list(
                    calendarId="primary",
                    timeMin=now.isoformat(),
                    timeMax=window_end.isoformat(),
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
        except HttpError as exc:
            status = exc.resp.status if getattr(exc, "resp", None) is not None else None
            if status in (429, 403):
                logger.warning("Calendar API rate limit or quota error: %s", exc)
                return CalendarReadResult(
                    authorized=False, failed=True, message="Calendar rate limit hit -- try again shortly."
                )
            logger.warning("Calendar API error: %s", exc)
            return CalendarReadResult(
                authorized=False, failed=True, message="Unable to read calendar right now (API error)."
            )
        except Exception as exc:  # network/transport failures -- never let this escape
            logger.warning("Calendar read failed (network/transport error): %s", exc)
            return CalendarReadResult(
                authorized=False, failed=True, message="Unable to read calendar right now (connection issue)."
            )

        events = []
        seen_recurring_ids = set()
        for item in response.get("items", []):
            try:
                recurring_id = item.get("recurringEventId")
                if recurring_id:
                    if recurring_id in seen_recurring_ids:
                        continue  # keep only the next occurrence per recurring series
                    seen_recurring_ids.add(recurring_id)

                start = item.get("start") or {}
                end = item.get("end") or {}
                events.append(
                    CalendarEvent(
                        title=item.get("summary") or "Untitled event",
                        when=_format_event_when(start),
                        duration_minutes=_event_duration_minutes(start, end),
                    )
                )
            except Exception as exc:  # one malformed event shouldn't sink the whole read
                logger.warning("Skipping malformed calendar event: %s", exc)
                continue

        return CalendarReadResult(authorized=True, events=events)
