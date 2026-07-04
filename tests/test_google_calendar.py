"""Offline tests for GoogleCalendarReader's failure-translation logic --
mocked throughout, no real OAuth/network/credentials required. Live behavior
against a real Google account is covered separately in
tests/test_calendar_live.py, skipped unless real credentials are present.
"""

from unittest.mock import MagicMock, patch

from intent_engine.core.permissions import PermissionRegistry
from intent_engine.voice.calendar import GoogleCalendarReader


def test_read_events_not_authorized_never_touches_credentials(tmp_path):
    """Stage B's permission gate is checked FIRST -- a denied registry must
    short-circuit before ever touching the token file, matching the stub's
    behavior exactly."""
    registry = PermissionRegistry()  # deny-by-default
    reader = GoogleCalendarReader(registry, token_path=tmp_path / "does_not_exist.json")

    result = reader.read_events()

    assert result.authorized is False
    assert result.failed is False  # a permission decision, not an operational failure
    assert result.message == "Not authorized to read calendar."


def test_read_events_read_failed_when_never_set_up(tmp_path):
    registry = PermissionRegistry({"calendar_read": True})
    reader = GoogleCalendarReader(registry, token_path=tmp_path / "does_not_exist.json")

    result = reader.read_events()

    assert result.authorized is False
    assert result.failed is True
    assert "not yet set up" in result.message
    assert "setup_calendar_auth.py" in result.message


def test_read_events_read_failed_when_token_refresh_fails(tmp_path):
    from google.auth.exceptions import RefreshError

    token_path = tmp_path / "calendar_token.json"
    token_path.write_text("{}")  # just needs to exist -- Credentials loading itself is mocked
    registry = PermissionRegistry({"calendar_read": True})
    reader = GoogleCalendarReader(registry, token_path=token_path)

    fake_creds = MagicMock()
    fake_creds.expired = True
    fake_creds.refresh_token = "some-refresh-token"
    fake_creds.refresh.side_effect = RefreshError("token has been revoked")

    with patch("google.oauth2.credentials.Credentials.from_authorized_user_file", return_value=fake_creds):
        result = reader.read_events()

    assert result.authorized is False
    assert result.failed is True
    assert "re-authorization" in result.message


def test_read_events_read_failed_on_rate_limit(tmp_path):
    from googleapiclient.errors import HttpError

    token_path = tmp_path / "calendar_token.json"
    token_path.write_text("{}")
    registry = PermissionRegistry({"calendar_read": True})
    reader = GoogleCalendarReader(registry, token_path=token_path)

    fake_creds = MagicMock()
    fake_creds.expired = False

    fake_resp = MagicMock()
    fake_resp.status = 429
    http_error = HttpError(fake_resp, b'{"error": "rate limit exceeded"}')

    with patch("google.oauth2.credentials.Credentials.from_authorized_user_file", return_value=fake_creds), \
         patch("googleapiclient.discovery.build", side_effect=http_error):
        result = reader.read_events()

    assert result.authorized is False
    assert result.failed is True
    assert "rate limit" in result.message


def test_read_events_read_failed_on_network_error(tmp_path):
    token_path = tmp_path / "calendar_token.json"
    token_path.write_text("{}")
    registry = PermissionRegistry({"calendar_read": True})
    reader = GoogleCalendarReader(registry, token_path=token_path)

    fake_creds = MagicMock()
    fake_creds.expired = False

    with patch("google.oauth2.credentials.Credentials.from_authorized_user_file", return_value=fake_creds), \
         patch("googleapiclient.discovery.build", side_effect=ConnectionError("network unreachable")):
        result = reader.read_events()

    assert result.authorized is False
    assert result.failed is True
    assert "connection issue" in result.message


def test_read_events_success_formats_and_dedups_recurring_events(tmp_path):
    token_path = tmp_path / "calendar_token.json"
    token_path.write_text("{}")
    registry = PermissionRegistry({"calendar_read": True})
    reader = GoogleCalendarReader(registry, token_path=token_path)

    fake_creds = MagicMock()
    fake_creds.expired = False

    canned_items = {
        "items": [
            {
                "summary": "Investor sync",
                "start": {"dateTime": "2026-07-10T10:00:00-04:00"},
                "end": {"dateTime": "2026-07-10T10:30:00-04:00"},
            },
            {
                "summary": "Daily standup",
                "recurringEventId": "standup-series",
                "start": {"dateTime": "2026-07-09T09:00:00-04:00"},
                "end": {"dateTime": "2026-07-09T09:15:00-04:00"},
            },
            {
                # Second instance of the SAME recurring series -- must be deduped,
                # only the first (earlier) occurrence should survive.
                "summary": "Daily standup",
                "recurringEventId": "standup-series",
                "start": {"dateTime": "2026-07-10T09:00:00-04:00"},
                "end": {"dateTime": "2026-07-10T09:15:00-04:00"},
            },
            {
                "summary": "Company offsite",
                "start": {"date": "2026-07-11"},
                "end": {"date": "2026-07-12"},
            },
        ]
    }

    fake_service = MagicMock()
    fake_service.events.return_value.list.return_value.execute.return_value = canned_items

    with patch("google.oauth2.credentials.Credentials.from_authorized_user_file", return_value=fake_creds), \
         patch("googleapiclient.discovery.build", return_value=fake_service):
        result = reader.read_events()

    assert result.authorized is True
    assert result.failed is False
    titles = [e.title for e in result.events]
    assert titles == ["Investor sync", "Daily standup", "Company offsite"]  # only ONE standup instance

    offsite = next(e for e in result.events if e.title == "Company offsite")
    assert offsite.when.startswith("All day,")
    assert offsite.duration_minutes == 24 * 60  # one full day


def test_read_events_degrades_gracefully_on_event_missing_start_and_end(tmp_path):
    """A dict-shaped event with no start/end info at all (a real API oddity,
    not a crash) gets SOME representation, not silently dropped --
    _format_event_when/_event_duration_minutes degrade gracefully instead of
    raising for missing keys."""
    token_path = tmp_path / "calendar_token.json"
    token_path.write_text("{}")
    registry = PermissionRegistry({"calendar_read": True})
    reader = GoogleCalendarReader(registry, token_path=token_path)

    fake_creds = MagicMock()
    fake_creds.expired = False

    canned_items = {
        "items": [
            {"summary": "Fine event", "start": {"dateTime": "2026-07-10T10:00:00-04:00"},
             "end": {"dateTime": "2026-07-10T10:30:00-04:00"}},
            {"summary": "Incomplete event"},  # no start/end keys at all
        ]
    }
    fake_service = MagicMock()
    fake_service.events.return_value.list.return_value.execute.return_value = canned_items

    with patch("google.oauth2.credentials.Credentials.from_authorized_user_file", return_value=fake_creds), \
         patch("googleapiclient.discovery.build", return_value=fake_service):
        result = reader.read_events()

    assert result.authorized is True
    assert [e.title for e in result.events] == ["Fine event", "Incomplete event"]
    incomplete = next(e for e in result.events if e.title == "Incomplete event")
    assert incomplete.when == "unspecified time"
    assert incomplete.duration_minutes == 0


def test_read_events_skips_a_genuinely_malformed_item_but_keeps_others(tmp_path):
    """An item that isn't even a dict (a real API-response oddity a bit
    beyond graceful degradation) must be skipped, not crash the whole read --
    every OTHER event still comes back."""
    token_path = tmp_path / "calendar_token.json"
    token_path.write_text("{}")
    registry = PermissionRegistry({"calendar_read": True})
    reader = GoogleCalendarReader(registry, token_path=token_path)

    fake_creds = MagicMock()
    fake_creds.expired = False

    canned_items = {
        "items": [
            {"summary": "Fine event", "start": {"dateTime": "2026-07-10T10:00:00-04:00"},
             "end": {"dateTime": "2026-07-10T10:30:00-04:00"}},
            None,  # genuinely malformed -- not even a dict
        ]
    }
    fake_service = MagicMock()
    fake_service.events.return_value.list.return_value.execute.return_value = canned_items

    with patch("google.oauth2.credentials.Credentials.from_authorized_user_file", return_value=fake_creds), \
         patch("googleapiclient.discovery.build", return_value=fake_service):
        result = reader.read_events()

    assert result.authorized is True
    assert [e.title for e in result.events] == ["Fine event"]
