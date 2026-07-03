from intent_engine.core.classifier import IntentClassifier
from intent_engine.core.schemas import RawInput, StructuredIntent


class FakeLLMClient:
    """Stands in for LLMClient so this test never touches the network or needs an API key."""

    def __init__(self, canned_response):
        self.canned_response = canned_response
        self.last_call_kwargs = None

    def call_tool(self, **kwargs):
        self.last_call_kwargs = kwargs
        return self.canned_response


def test_intent_classifier_returns_structured_intent():
    canned = {
        "decision_summary": "Expand into a new market with significant capital.",
        "goals": ["establish market presence"],
        "constraints": ["18-month timeline", "$2M budget"],
        "risk_tolerance": "medium",
        "stated_priorities": ["growth"],
        "inferred_priorities": ["defensive positioning vs competitor"],
    }
    fake_client = FakeLLMClient(canned)
    classifier = IntentClassifier(client=fake_client)

    raw_input = RawInput(decision_text="Expand into Asia with $2M.", context_text="Revenue: $60k MRR")
    result = classifier.run(raw_input)

    assert isinstance(result, StructuredIntent)
    assert result.risk_tolerance == "medium"
    assert result.goals == ["establish market presence"]
    assert fake_client.last_call_kwargs["tool_name"] == "extract_intent"
