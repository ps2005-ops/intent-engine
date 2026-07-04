from intent_engine.core.entity_memory import EntityMemoryRecord, JsonlEntityMemoryWriter, read_records
from intent_engine.core.permissions import PermissionRegistry
from intent_engine.voice.calendar import StubCalendarActor
from intent_engine.voice.classifier import VoiceIntentClassifier
from intent_engine.voice.gmail import StubGmailActor
from intent_engine.voice.pipeline import process_voice_interaction


class FakeLLMClient:
    """Stands in for LLMClient so this test never touches the network or needs an API key."""

    def __init__(self, canned_response):
        self.canned_response = canned_response
        self.last_call_kwargs = None

    def call_tool(self, **kwargs):
        self.last_call_kwargs = kwargs
        return self.canned_response


def test_process_voice_interaction_writes_every_interaction_regardless_of_salience(tmp_path):
    """No filtering: both a low-salience and a high-salience interaction for the
    same entity must both land in entity memory -- salience is a signal for
    Stage D to query/weight by later, not a write-time gate."""
    path = tmp_path / "entity_memory.jsonl"
    writer = JsonlEntityMemoryWriter(path=path)

    low_client = VoiceIntentClassifier(
        client=FakeLLMClient(
            {"intent_type": "reminder", "target": "milk", "when": None, "content": "buy milk", "salience": "low"}
        )
    )
    high_client = VoiceIntentClassifier(
        client=FakeLLMClient(
            {
                "intent_type": "priority_flag",
                "target": "pricing",
                "when": None,
                "content": "reconsider pricing",
                "salience": "high",
            }
        )
    )

    low_result = process_voice_interaction(
        entity_id="Acme Inc", utterance="remind me to buy milk", classifier=low_client, writer=writer
    )
    high_result = process_voice_interaction(
        entity_id="Acme Inc",
        utterance="we should reconsider our pricing strategy",
        classifier=high_client,
        writer=writer,
    )

    assert low_result.voice_intent.salience == "low"
    assert high_result.voice_intent.salience == "high"
    assert low_result.calendar_action is None  # not a calendar_block intent
    assert high_result.calendar_action is None
    assert low_result.gmail_action is None  # not an email_draft intent
    assert high_result.gmail_action is None

    records = read_records("Acme Inc", path=path)
    assert len(records) == 2  # both written -- neither filtered out
    assert {r.salience for r in records} == {"low", "high"}
    assert all(r.source == "voice" for r in records)
    assert all(r.goals == [] and r.constraints == [] for r in records)
    assert all(r.primary_priority is None for r in records)

    decision_texts = {r.decision_text for r in records}
    assert decision_texts == {"remind me to buy milk", "we should reconsider our pricing strategy"}


def _calendar_client():
    return FakeLLMClient(
        {
            "intent_type": "calendar_block",
            "target": "board meeting",
            "when": "Thursday afternoon",
            "content": "block off Thursday afternoon for the board meeting",
            "salience": "medium",
        }
    )


def test_calendar_block_intent_authorized_creates_event_end_to_end(tmp_path):
    """The full chain: classification -> entity memory write -> permission check
    -> StubCalendarActor, for real, not unit-tested in isolation."""
    path = tmp_path / "entity_memory.jsonl"
    writer = JsonlEntityMemoryWriter(path=path)
    registry = PermissionRegistry({"calendar_act": True})
    actor = StubCalendarActor(registry)

    result = process_voice_interaction(
        entity_id="Acme Inc",
        utterance="block off Thursday afternoon for the board meeting",
        classifier=VoiceIntentClassifier(client=_calendar_client()),
        writer=writer,
        permission_registry=registry,
        calendar_actor=actor,
    )

    assert result.voice_intent.intent_type == "calendar_block"
    assert result.calendar_action is not None
    assert result.calendar_action.authorized is True
    assert "board meeting" in result.calendar_action.confirmation
    assert "Thursday afternoon" in result.calendar_action.confirmation

    # entity memory write still happened, same as any other interaction
    records = read_records("Acme Inc", path=path)
    assert len(records) == 1
    assert records[0].decision_text == "block off Thursday afternoon for the board meeting"
    assert records[0].salience == "medium"


def test_calendar_block_intent_unauthorized_is_refused_but_still_written(tmp_path):
    """Denied permission must not silently drop the action -- it comes back
    explicitly refused. The entity-memory write must still happen: the standing
    'every interaction written, no filtering' rule doesn't get suspended just
    because the requested action was denied."""
    path = tmp_path / "entity_memory.jsonl"
    writer = JsonlEntityMemoryWriter(path=path)
    registry = PermissionRegistry()  # no grants at all -- deny-by-default
    actor = StubCalendarActor(registry)

    result = process_voice_interaction(
        entity_id="Acme Inc",
        utterance="block off Thursday afternoon for the board meeting",
        classifier=VoiceIntentClassifier(client=_calendar_client()),
        writer=writer,
        permission_registry=registry,
        calendar_actor=actor,
    )

    assert result.calendar_action is not None
    assert result.calendar_action.authorized is False
    assert result.calendar_action.confirmation is None
    assert result.calendar_action.message == "Not authorized to create calendar events."

    records = read_records("Acme Inc", path=path)
    assert len(records) == 1
    assert records[0].decision_text == "block off Thursday afternoon for the board meeting"


def test_non_calendar_intent_never_calls_calendar_actor(tmp_path):
    """A non-calendar_block intent must not touch the calendar actor at all --
    calendar_action stays None even when an authorized actor is supplied."""
    path = tmp_path / "entity_memory.jsonl"
    writer = JsonlEntityMemoryWriter(path=path)
    registry = PermissionRegistry({"calendar_act": True})
    actor = StubCalendarActor(registry)

    result = process_voice_interaction(
        entity_id="Acme Inc",
        utterance="remind me to buy milk",
        classifier=VoiceIntentClassifier(
            client=FakeLLMClient(
                {"intent_type": "reminder", "target": "milk", "when": None, "content": "buy milk", "salience": "low"}
            )
        ),
        writer=writer,
        permission_registry=registry,
        calendar_actor=actor,
    )

    assert result.voice_intent.intent_type == "reminder"
    assert result.calendar_action is None


def _email_draft_client():
    return FakeLLMClient(
        {
            "intent_type": "email_draft",
            "target": "sarah@acme.example",
            "when": None,
            "content": "board deck follow-up",
            "salience": "medium",
        }
    )


def test_email_draft_intent_authorized_creates_draft_end_to_end(tmp_path):
    """Fresh-compose only, per the recorded design decision: the full chain --
    classification -> entity memory write -> permission check ->
    StubGmailActor -- for a compose-style email_draft utterance."""
    path = tmp_path / "entity_memory.jsonl"
    writer = JsonlEntityMemoryWriter(path=path)
    registry = PermissionRegistry({"gmail_act": True})
    actor = StubGmailActor(registry)

    result = process_voice_interaction(
        entity_id="Acme Inc",
        utterance="draft an email to Sarah about the board deck follow-up",
        classifier=VoiceIntentClassifier(client=_email_draft_client()),
        writer=writer,
        permission_registry=registry,
        gmail_actor=actor,
    )

    assert result.voice_intent.intent_type == "email_draft"
    assert result.calendar_action is None
    assert result.gmail_action is not None
    assert result.gmail_action.authorized is True
    assert "sarah@acme.example" in result.gmail_action.confirmation
    assert "board deck follow-up" in result.gmail_action.confirmation

    records = read_records("Acme Inc", path=path)
    assert len(records) == 1
    assert records[0].decision_text == "draft an email to Sarah about the board deck follow-up"


def test_email_draft_intent_unauthorized_is_refused_but_still_written(tmp_path):
    """Same invariant as Calendar's: a denied gmail_act must not suppress the
    entity-memory write."""
    path = tmp_path / "entity_memory.jsonl"
    writer = JsonlEntityMemoryWriter(path=path)
    registry = PermissionRegistry()  # no grants at all -- deny-by-default
    actor = StubGmailActor(registry)

    result = process_voice_interaction(
        entity_id="Acme Inc",
        utterance="draft an email to Sarah about the board deck follow-up",
        classifier=VoiceIntentClassifier(client=_email_draft_client()),
        writer=writer,
        permission_registry=registry,
        gmail_actor=actor,
    )

    assert result.gmail_action is not None
    assert result.gmail_action.authorized is False
    assert result.gmail_action.confirmation is None
    assert result.gmail_action.message == "Not authorized to create Gmail drafts."

    records = read_records("Acme Inc", path=path)
    assert len(records) == 1
    assert records[0].decision_text == "draft an email to Sarah about the board deck follow-up"


def test_non_email_intent_never_calls_gmail_actor(tmp_path):
    """A non-email_draft intent must not touch the Gmail actor at all --
    gmail_action stays None even when an authorized actor is supplied."""
    path = tmp_path / "entity_memory.jsonl"
    writer = JsonlEntityMemoryWriter(path=path)
    registry = PermissionRegistry({"gmail_act": True})
    actor = StubGmailActor(registry)

    result = process_voice_interaction(
        entity_id="Acme Inc",
        utterance="block off Thursday afternoon for the board meeting",
        classifier=VoiceIntentClassifier(client=_calendar_client()),
        writer=writer,
        permission_registry=registry,
        gmail_actor=actor,
    )

    assert result.voice_intent.intent_type == "calendar_block"
    assert result.gmail_action is None


def test_process_voice_interaction_builds_personal_context_when_not_supplied(tmp_path):
    """Closes the gap found in Step 2a: when no context is supplied, the
    classifier must actually receive a real PersonalContext built from prior
    entity-memory records for this entity, not classify with context=None."""
    path = tmp_path / "entity_memory.jsonl"
    writer = JsonlEntityMemoryWriter(path=path)

    # Seed prior history for this entity before the interaction under test.
    writer.write(
        EntityMemoryRecord(
            entity_id="Acme Inc",
            source="simulator",
            decision_text="Raise a Series A.",
            goals=["extend runway"],
            constraints=[],
            risk_tolerance="high",
            primary_priority="growth",
        )
    )

    fake_client = FakeLLMClient(
        {"intent_type": "reminder", "target": "milk", "when": None, "content": "buy milk", "salience": "low"}
    )
    classifier = VoiceIntentClassifier(client=fake_client)

    process_voice_interaction(
        entity_id="Acme Inc",
        utterance="remind me to buy milk",
        classifier=classifier,
        writer=writer,
        entity_memory_path=path,
    )

    user_message = fake_client.last_call_kwargs["user_message"]
    assert "Context about this person" in user_message
    assert "extend runway" in user_message  # real prior history, not context=None


def test_process_voice_interaction_context_reflects_deny_by_default_reads(tmp_path):
    """No permission_registry supplied -- the auto-built PersonalContext's
    external reads must come back explicitly not_authorized, not silently
    empty, and must not block classification."""
    path = tmp_path / "entity_memory.jsonl"
    writer = JsonlEntityMemoryWriter(path=path)

    fake_client = FakeLLMClient(
        {"intent_type": "reminder", "target": "milk", "when": None, "content": "buy milk", "salience": "low"}
    )
    classifier = VoiceIntentClassifier(client=fake_client)

    process_voice_interaction(
        entity_id="Acme Inc",
        utterance="remind me to buy milk",
        classifier=classifier,
        writer=writer,
        entity_memory_path=path,
    )

    user_message = fake_client.last_call_kwargs["user_message"]
    assert "Not authorized to read Gmail." in user_message
    assert "Not authorized to read calendar." in user_message
