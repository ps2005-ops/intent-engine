"""Live end-to-end test against a REAL Google Calendar account, read-only.

Skipped automatically unless real OAuth credentials exist at
credentials/client_secret.json and data/calendar_token.json (produced by
running scripts/setup_calendar_auth.py once, interactively -- that step
cannot be automated, same reason test_simulator_e2e.py skips without a real
ANTHROPIC_API_KEY set).

This is a LIVE test, not part of the offline commit gate: the pre-commit
guard (scripts/precommit_guard.sh) deselects it along with the other
live/networked tests. Run it explicitly as a diagnostic:

    .venv/bin/python -m pytest tests/test_calendar_live.py -q

Known state (2026-07-20): with credentials present, the Google Calendar API
returns `403 accessNotConfigured` for GCP project 965657964785 because the
Calendar API is not enabled for that project. Enabling it is a founder
action in the Google Cloud console -- do not weaken this test to hide the
403; it is reporting a real external configuration gap.
"""

import pytest

from intent_engine.core.permissions import PermissionRegistry
from intent_engine.voice.calendar import (
    DEFAULT_CALENDAR_TOKEN_PATH,
    DEFAULT_CLIENT_SECRET_PATH,
    GoogleCalendarReader,
)

pytestmark = pytest.mark.skipif(
    not (DEFAULT_CALENDAR_TOKEN_PATH.exists() and DEFAULT_CLIENT_SECRET_PATH.exists()),
    reason="Real Google Calendar credentials not present; run scripts/setup_calendar_auth.py once to enable this test.",
)


def test_real_calendar_read_returns_authorized_result():
    registry = PermissionRegistry({"calendar_read": True})
    reader = GoogleCalendarReader(registry)

    result = reader.read_events()

    assert result.authorized is True
    assert result.failed is False
    print(f"\nReal Calendar read: {len(result.events)} event(s) in the next 7 days.")
    for event in result.events:
        print(f"  {event.title} -- {event.when} ({event.duration_minutes} min)")
