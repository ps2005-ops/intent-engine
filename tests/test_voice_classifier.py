from intent_engine.voice.classifier import VoiceIntentClassifier
from intent_engine.voice.context_schema import EntityHistorySummary, MockPersonalData, PersonalContext
from intent_engine.voice.schemas import VoiceIntent


class FakeLLMClient:
    """Stands in for LLMClient so this test never touches the network or needs an API key."""

    def __init__(self, canned_response):
        self.canned_response = canned_response
        self.last_call_kwargs = None

    def call_tool(self, **kwargs):
        self.last_call_kwargs = kwargs
        return self.canned_response


CANNED_RESPONSE = {
    "intent_type": "reminder",
    "target": "Sarah",
    "when": "in 5 days",
    "content": "follow up",
    "salience": "low",
}


def test_voice_intent_classifier_returns_voice_intent():
    fake_client = FakeLLMClient(CANNED_RESPONSE)
    classifier = VoiceIntentClassifier(client=fake_client)

    result = classifier.run("Remind me to follow up with Sarah in 5 days")

    assert isinstance(result, VoiceIntent)
    assert result.intent_type == "reminder"
    assert result.target == "Sarah"
    assert result.salience == "low"
    assert fake_client.last_call_kwargs["tool_name"] == "record_voice_intent"


def test_voice_intent_classifier_works_without_context():
    fake_client = FakeLLMClient(CANNED_RESPONSE)
    classifier = VoiceIntentClassifier(client=fake_client)

    result = classifier.run("Remind me to follow up with Sarah in 5 days", context=None)

    assert isinstance(result, VoiceIntent)
    assert "Context about this person" not in fake_client.last_call_kwargs["user_message"]


def test_voice_intent_classifier_injects_context_when_provided():
    fake_client = FakeLLMClient(CANNED_RESPONSE)
    classifier = VoiceIntentClassifier(client=fake_client)

    context = PersonalContext(
        entity_id="acme inc",
        entity_history=EntityHistorySummary(recent_goals=["extend runway"]),
        mock_data=MockPersonalData(calendar_density="busy"),
    )
    classifier.run("Remind me to follow up with Sarah in 5 days", context=context)

    user_message = fake_client.last_call_kwargs["user_message"]
    assert "Context about this person" in user_message
    assert "extend runway" in user_message
