from intent_engine.core.permissions import PermissionRegistry
from intent_engine.voice.calendar import StubCalendarActor, StubCalendarReader


def test_read_authorized_returns_canned_events():
    registry = PermissionRegistry({"calendar_read": True})
    reader = StubCalendarReader(registry)

    result = reader.read_events()

    assert result.authorized is True
    assert len(result.events) == 3
    assert result.message is None


def test_read_unauthorized_states_it_not_silently_empty():
    registry = PermissionRegistry()  # no grants at all
    reader = StubCalendarReader(registry)

    result = reader.read_events()

    assert result.authorized is False
    assert result.events == []
    # The point: this must be distinguishable from "authorized, zero events" --
    # message being set (not None) is what makes that distinction possible.
    assert result.message == "Not authorized to read calendar."


def test_act_authorized_returns_canned_confirmation():
    registry = PermissionRegistry({"calendar_act": True})
    actor = StubCalendarActor(registry)

    result = actor.create_event("Team offsite", "Friday 1pm")

    assert result.authorized is True
    assert "Team offsite" in result.confirmation
    assert "Friday 1pm" in result.confirmation
    assert result.message is None


def test_act_unauthorized_states_it_explicitly():
    registry = PermissionRegistry()  # no grants at all
    actor = StubCalendarActor(registry)

    result = actor.create_event("Team offsite", "Friday 1pm")

    assert result.authorized is False
    assert result.confirmation is None
    assert result.message == "Not authorized to create calendar events."


def test_read_only_grant_does_not_authorize_act():
    """The actual test of the two-tier distinction, not just that gating exists."""
    registry = PermissionRegistry({"calendar_read": True})  # read only, no act grant
    reader = StubCalendarReader(registry)
    actor = StubCalendarActor(registry)

    read_result = reader.read_events()
    act_result = actor.create_event("Team offsite", "Friday 1pm")

    assert read_result.authorized is True
    assert act_result.authorized is False
    assert act_result.message == "Not authorized to create calendar events."


def test_act_only_grant_does_not_authorize_read():
    """The mirror case: an act grant must not leak into read authorization either."""
    registry = PermissionRegistry({"calendar_act": True})  # act only, no read grant
    reader = StubCalendarReader(registry)
    actor = StubCalendarActor(registry)

    read_result = reader.read_events()
    act_result = actor.create_event("Team offsite", "Friday 1pm")

    assert act_result.authorized is True
    assert read_result.authorized is False
    assert read_result.message == "Not authorized to read calendar."
