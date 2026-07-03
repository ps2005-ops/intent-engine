from intent_engine.simulator.analysis import PremortemAnalyzer
from intent_engine.simulator.context_schema import BusinessContext


class FakeLLMClient:
    """Stands in for LLMClient so this test never touches the network or needs an API key."""

    def __init__(self, canned_response):
        self.canned_response = canned_response
        self.last_call_kwargs = None

    def call_tool(self, **kwargs):
        self.last_call_kwargs = kwargs
        return self.canned_response


class SequenceLLMClient:
    """Returns a different canned response on each successive call_tool, to test retry."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.call_count = 0

    def call_tool(self, **kwargs):
        response = self.responses[self.call_count]
        self.call_count += 1
        return response


CANNED_FLAT_RESPONSE = {
    "decision_summary": "Expand into a new market with significant capital.",
    "goals": ["establish market presence"],
    "constraints": ["18-month timeline", "$2M budget"],
    "risk_tolerance": "medium",
    "narrative_summary": "You're in the board meeting eight months from now explaining why the expansion drained the runway funding the business that actually worked.",
    "failure_descriptions": ["Runway runs out before expansion pays off.", "Local competitor undercuts pricing.", "Team overextends."],
    "failure_likelihoods": ["likely", "possible", "possible"],
    "failure_rationales": ["Runway is shorter than the expansion timeline.", "Competitors already have local presence.", "Team size is small for two markets."],
    "recommended_stress_tests": ["Model a 6-month funding delay.", "Survey local pricing."],
    "key_sensitivity": "Whether the $2M closes on schedule.",
}


def test_premortem_analyzer_reconstructs_intent_and_audit():
    fake_client = FakeLLMClient(CANNED_FLAT_RESPONSE)
    analyzer = PremortemAnalyzer(client=fake_client)
    context = BusinessContext(revenue="$60k MRR")

    result = analyzer.run("Expand into Asia with $2M.", context)

    assert result.intent.risk_tolerance == "medium"
    assert result.intent.goals == ["establish market presence"]

    assert len(result.risk_audit.failure_modes) == 3
    first = result.risk_audit.failure_modes[0]
    assert first.description == "Runway runs out before expansion pays off."
    assert first.likelihood == "likely"
    assert first.rationale == "Runway is shorter than the expansion timeline."
    assert result.risk_audit.key_sensitivity == "Whether the $2M closes on schedule."
    assert result.risk_audit.narrative_summary.startswith("You're in the board meeting")
    assert fake_client.last_call_kwargs["tool_name"] == "record_analysis"


def test_premortem_analyzer_zips_parallel_arrays_in_order():
    canned = dict(CANNED_FLAT_RESPONSE)
    fake_client = FakeLLMClient(canned)
    analyzer = PremortemAnalyzer(client=fake_client)

    result = analyzer.run("Expand into Asia with $2M.", BusinessContext())

    likelihoods = [fm.likelihood for fm in result.risk_audit.failure_modes]
    assert likelihoods == ["likely", "possible", "possible"]


def test_premortem_analyzer_retries_once_on_leaked_markup():
    garbled = dict(CANNED_FLAT_RESPONSE)
    garbled["key_sensitivity"] = "Whether the $2M closes on schedule.</sensitivity>\n</invoke>"
    clean = dict(CANNED_FLAT_RESPONSE)

    fake_client = SequenceLLMClient([garbled, clean])
    analyzer = PremortemAnalyzer(client=fake_client)

    result = analyzer.run("Expand into Asia with $2M.", BusinessContext())

    assert fake_client.call_count == 2
    assert result.risk_audit.key_sensitivity == "Whether the $2M closes on schedule."


def test_premortem_analyzer_raises_after_two_consecutive_leaks():
    garbled = dict(CANNED_FLAT_RESPONSE)
    garbled["key_sensitivity"] = "Whether the $2M closes on schedule.</sensitivity>"

    fake_client = SequenceLLMClient([garbled, garbled])
    analyzer = PremortemAnalyzer(client=fake_client)

    try:
        analyzer.run("Expand into Asia with $2M.", BusinessContext())
    except RuntimeError as exc:
        assert "malformed twice in a row" in str(exc)
    else:
        raise AssertionError("expected RuntimeError after two consecutive malformed responses")


def test_premortem_analyzer_does_not_false_positive_on_comparison_operators():
    canned = dict(CANNED_FLAT_RESPONSE)
    canned["key_sensitivity"] = "Whether churn stays <5% or CAC < $50 per customer."

    fake_client = FakeLLMClient(canned)
    analyzer = PremortemAnalyzer(client=fake_client)

    result = analyzer.run("Expand into Asia with $2M.", BusinessContext())

    assert result.risk_audit.key_sensitivity == "Whether churn stays <5% or CAC < $50 per customer."
