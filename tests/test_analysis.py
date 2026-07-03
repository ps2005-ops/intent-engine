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


CANNED_FLAT_RESPONSE = {
    "decision_summary": "Expand into a new market with significant capital.",
    "goals": ["establish market presence"],
    "constraints": ["18-month timeline", "$2M budget"],
    "risk_tolerance": "medium",
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
    assert fake_client.last_call_kwargs["tool_name"] == "record_analysis"


def test_premortem_analyzer_zips_parallel_arrays_in_order():
    canned = dict(CANNED_FLAT_RESPONSE)
    fake_client = FakeLLMClient(canned)
    analyzer = PremortemAnalyzer(client=fake_client)

    result = analyzer.run("Expand into Asia with $2M.", BusinessContext())

    likelihoods = [fm.likelihood for fm in result.risk_audit.failure_modes]
    assert likelihoods == ["likely", "possible", "possible"]
