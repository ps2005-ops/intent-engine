from intent_engine.core.permissions import PermissionRegistry
from intent_engine.voice.gmail import StubGmailActor, StubGmailReader


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


def test_act_authorized_returns_canned_confirmation():
    registry = PermissionRegistry({"gmail_act": True})
    actor = StubGmailActor(registry)

    result = actor.create_draft("sarah@acme.example", "Board deck follow-up")

    assert result.authorized is True
    assert "sarah@acme.example" in result.confirmation
    assert "Board deck follow-up" in result.confirmation
    assert result.message is None


def test_act_unauthorized_states_it_explicitly():
    registry = PermissionRegistry()  # no grants at all
    actor = StubGmailActor(registry)

    result = actor.create_draft("sarah@acme.example", "Board deck follow-up")

    assert result.authorized is False
    assert result.confirmation is None
    assert result.message == "Not authorized to create Gmail drafts."


def test_read_only_grant_does_not_authorize_act():
    """The actual test of the two-tier distinction, not just that gating exists."""
    registry = PermissionRegistry({"gmail_read": True})  # read only, no act grant
    reader = StubGmailReader(registry)
    actor = StubGmailActor(registry)

    read_result = reader.read_messages()
    act_result = actor.create_draft("sarah@acme.example", "Board deck follow-up")

    assert read_result.authorized is True
    assert act_result.authorized is False
    assert act_result.message == "Not authorized to create Gmail drafts."


def test_act_only_grant_does_not_authorize_read():
    """The mirror case: an act grant must not leak into read authorization either."""
    registry = PermissionRegistry({"gmail_act": True})  # act only, no read grant
    reader = StubGmailReader(registry)
    actor = StubGmailActor(registry)

    read_result = reader.read_messages()
    act_result = actor.create_draft("sarah@acme.example", "Board deck follow-up")

    assert act_result.authorized is True
    assert read_result.authorized is False
    assert read_result.message == "Not authorized to read Gmail."


def test_calendar_act_grant_does_not_authorize_gmail_act():
    """Cross-domain leakage check, act tier: a grant for a different
    integration's act domain must never authorize Gmail's act domain."""
    registry = PermissionRegistry({"calendar_act": True})
    actor = StubGmailActor(registry)

    result = actor.create_draft("sarah@acme.example", "Board deck follow-up")

    assert result.authorized is False
    assert result.message == "Not authorized to create Gmail drafts."
