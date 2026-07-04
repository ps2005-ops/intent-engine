from intent_engine.core.permissions import PermissionRegistry
from intent_engine.voice.gmail import StubGmailReader


def test_read_authorized_returns_canned_messages():
    registry = PermissionRegistry({"gmail_read": True})
    reader = StubGmailReader(registry)

    result = reader.read_messages()

    assert result.authorized is True
    assert len(result.messages) == 3
    assert result.message is None


def test_read_unauthorized_states_it_not_silently_empty():
    registry = PermissionRegistry()  # no grants at all
    reader = StubGmailReader(registry)

    result = reader.read_messages()

    assert result.authorized is False
    assert result.messages == []
    # Same distinction as Calendar's: "not authorized" must not look like
    # "authorized, zero messages" -- message being set is what disambiguates it.
    assert result.message == "Not authorized to read Gmail."


def test_calendar_act_grant_does_not_authorize_gmail_read():
    """Cross-domain leakage check: a grant for one integration's domain string
    must never authorize a different integration -- domain strings are scoped
    per-integration, not per-permission-tier."""
    registry = PermissionRegistry({"calendar_act": True, "calendar_read": True})
    reader = StubGmailReader(registry)

    result = reader.read_messages()

    assert result.authorized is False
    assert result.message == "Not authorized to read Gmail."
