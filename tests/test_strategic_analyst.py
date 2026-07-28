"""The grounded analyst and the deterministic critic that polices it.

No network and no model: every test drives a recorded client, so CI is
deterministic. What is being tested is the CONTRACT -- that a fluent but
ungrounded analysis is rejected rather than rendered.
"""
import pytest

from intent_engine.strategic_intelligence.analyst import (
    AnalystUnavailable, ResultState, analyse, verify_analysis,
)
from intent_engine.strategic_intelligence.analyst.critic import rejects
from intent_engine.strategic_intelligence.analyst.runner import (
    FileCache, cache_key,
)
from intent_engine.strategic_intelligence.records import StrategicObservation


def _obs(oid, text, excerpt, source_class="company_owned", title="Page"):
    return StrategicObservation(
        observation_id=oid, text=text, observation_type="messaging",
        source_refs=[{"subsystem": "company_ingestion",
                      "artifact_type": "retrieved_source", "artifact_id": oid,
                      "source_class": source_class}],
        confidence="moderate", freshness="CURRENT", directly_observed=True,
        signals=("multi_product",), source_class=source_class,
        excerpt=excerpt, source_title=title, origin=f"https://x.test/{oid}",
        date="2026-07-20", strategic_signal="sells several products",
        relevance="context", entity="Sony Interactive Entertainment",
        weak=False, evidence_quality="strong")


SIE_OBS = [
    _obs("obs-1",
         "PlayStation Plus is sold in three membership tiers",
         "PlayStation Plus has three membership tiers: Essential, Extra and "
         "Premium, including cloud streaming and a catalogue of titles.",
         title="PlayStation Plus"),
    _obs("obs-2",
         "PlayStation Studios invests in first-party content",
         "PlayStation Studios funds first-party content and original content "
         "across a catalogue of titles spanning hardware generations.",
         title="PlayStation Studios"),
    _obs("obs-3",
         "Independent reporting on console attach rates",
         "Analysts note PlayStation hardware is sold near cost while "
         "subscription and software attach drive the margin.",
         source_class="independent_reporting", title="Industry analysis"),
]


def _good_analysis():
    return {
        "entity_scope": {"analysed_entity": "Sony Interactive Entertainment",
                         "is_subsidiary": True, "parent": "Sony Group",
                         "scope_note": "Segment figures are group-level."},
        "business_model": "Sells PlayStation consoles near cost and earns on "
                          "software, subscription tiers and first-party "
                          "content.",
        "sufficient_for_strategic_analysis": True,
        "insufficiency_reason": "",
        "evidence_gaps": ["No subscriber counts disclosed."],
        "insights": [{
            "headline": "PlayStation Plus tiers turn the console install base "
                        "into recurring subscription revenue, making the "
                        "catalogue rather than hardware the retention asset.",
            "what_is_changing": "Membership tiers and cloud streaming shift "
                                "the earning surface away from hardware.",
            "why_now": "Tiered PlayStation Plus and streaming are live today "
                       "(obs-1).",
            "tension": {"side_a": "Putting first-party titles in the "
                                  "subscription raises retention.",
                        "side_b": "It cannibalises full-price sales of the "
                                  "same titles.",
                        "why_it_exists": "The catalogue is both the "
                                         "subscription's draw and the "
                                         "premium product.",
                        "decision_owner": "PlayStation Studios leadership",
                        "what_would_resolve_it": "Disclosure of attach and "
                                                 "subscriber mix."},
            "economics": {"mechanism": "Subscription revenue is recurring and "
                                       "higher margin than hardware sold near "
                                       "cost; day-one catalogue inclusion "
                                       "trades unit revenue for retention.",
                          "levers": ["retention", "gross_margin",
                                     "content_economics"]},
            "competitive": {"compared_to": ["Microsoft Game Pass", "Nintendo"],
                            "how_this_company_differs": "Sony has held "
                                                        "first-party titles "
                                                        "out of day-one "
                                                        "subscription where "
                                                        "Microsoft has not.",
                            "likely_responder": "Microsoft",
                            "second_order_effect": "If Sony moves first-party "
                                                   "titles day-one, "
                                                   "third-party publishers "
                                                   "reprice their own "
                                                   "catalogue deals."},
            "counterargument": {"strongest_case_against": "Hardware cycles "
                                                          "still drive the "
                                                          "install base, and "
                                                          "subscription is "
                                                          "additive rather "
                                                          "than structural.",
                                "what_would_disprove_this": "Subscription "
                                                            "revenue flat "
                                                            "while hardware "
                                                            "units grow."},
            "decision_affected": "Whether first-party titles enter the "
                                 "subscription on release day.",
            "monitor": ["First-party day-one subscription announcements"],
            "confidence": "moderate",
            "confidence_rationale": "Moderate -- company pages plus one "
                                    "independent analysis, but no disclosed "
                                    "subscriber or attach figures.",
            "citations": ["obs-1", "obs-2", "obs-3"],
        }],
    }


class RecordedClient:
    """Deterministic stand-in for LLMClient."""

    def __init__(self, payload, fail_times=0):
        self.payload = payload
        self.fail_times = fail_times
        self.calls = 0

    def call_tool(self, **kwargs):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError("simulated transport failure")
        self.last_kwargs = kwargs
        return self.payload


# --- the happy path --------------------------------------------------------

def test_grounded_analysis_is_accepted():
    analysis, state, findings = analyse("Sony Interactive Entertainment",
                                        SIE_OBS,
                                        client=RecordedClient(_good_analysis()))
    assert state == ResultState.COMPLETE
    assert not rejects(findings)
    assert analysis.insights[0]["citations"] == ["obs-1", "obs-2", "obs-3"]


def test_evidence_pack_contains_every_observation_id():
    client = RecordedClient(_good_analysis())
    analyse("Sony Interactive Entertainment", SIE_OBS, client=client)
    packed = client.last_kwargs["user_message"]
    for o in SIE_OBS:
        assert o.observation_id in packed
    # whose account it is must be visible to the analyst
    assert "independent_reporting" in packed


# --- the critic rejects what it should -------------------------------------

def test_unresolvable_citation_is_rejected():
    bad = _good_analysis()
    bad["insights"][0]["citations"] = ["obs-1", "obs-99"]
    analysis, state, findings = analyse("Sony Interactive Entertainment",
                                        SIE_OBS, client=RecordedClient(bad))
    assert state == ResultState.STRATEGICALLY_INSUFFICIENT
    assert analysis is None
    assert any(f.check == "citation_unresolvable" for f in findings)


def test_invented_number_is_rejected():
    bad = _good_analysis()
    bad["insights"][0]["economics"]["mechanism"] = (
        "Subscription gross margin runs near 70% versus hardware sold at cost.")
    _, state, findings = analyse("Sony Interactive Entertainment", SIE_OBS,
                                 client=RecordedClient(bad))
    assert state == ResultState.STRATEGICALLY_INSUFFICIENT
    assert any(f.check == "invented_number" for f in findings)


def test_number_that_appears_in_evidence_is_allowed():
    obs = list(SIE_OBS) + [
        _obs("obs-4", "Disclosed margin",
             "The company disclosed a services gross margin of 70% for the "
             "period.", source_class="investor_material", title="Results")]
    ok = _good_analysis()
    ok["insights"][0]["economics"]["mechanism"] = (
        "Disclosed services gross margin of 70% versus hardware near cost.")
    ok["insights"][0]["citations"] = ["obs-1", "obs-4"]
    _, state, findings = analyse("Sony Interactive Entertainment", obs,
                                 client=RecordedClient(ok))
    assert not any(f.check == "invented_number" for f in findings)
    assert state == ResultState.COMPLETE


def test_generic_headline_is_rejected():
    """The original failure: fluent, confident, true of anyone."""
    bad = _good_analysis()
    bad["insights"][0]["headline"] = (
        "The company is absorbing adjacent tools until the work lives inside "
        "its platform ecosystem.")
    _, state, findings = analyse("Sony Interactive Entertainment", SIE_OBS,
                                 client=RecordedClient(bad))
    assert state == ResultState.STRATEGICALLY_INSUFFICIENT
    assert any(f.check == "generic_headline" for f in findings)


def test_real_product_names_wrapped_in_strategy_speak_are_rejected():
    """Naming two things from the evidence clears the anchoring test while
    still saying nothing. Density catches what anchoring cannot."""
    bad = _good_analysis()
    bad["insights"][0]["headline"] = (
        "PlayStation is expanding its subscription platform ecosystem.")
    _, state, findings = analyse("Sony Interactive Entertainment", SIE_OBS,
                                 client=RecordedClient(bad))
    assert state == ResultState.STRATEGICALLY_INSUFFICIENT
    assert any(f.check == "generic_density" for f in findings)


def test_filler_phrases_are_rejected():
    bad = _good_analysis()
    bad["insights"][0]["headline"] = (
        "PlayStation Plus drives growth through digital transformation of the "
        "catalogue.")
    _, _, findings = analyse("Sony Interactive Entertainment", SIE_OBS,
                             client=RecordedClient(bad))
    assert any(f.check == "generic_filler" for f in findings)


def test_high_confidence_from_company_pages_only_is_rejected():
    bad = _good_analysis()
    bad["insights"][0]["confidence"] = "high"
    bad["insights"][0]["citations"] = ["obs-1", "obs-2"]      # both company
    _, state, findings = analyse("Sony Interactive Entertainment", SIE_OBS,
                                 client=RecordedClient(bad))
    assert state == ResultState.STRATEGICALLY_INSUFFICIENT
    assert any(f.check == "confidence_exceeds_evidence" for f in findings)


def test_missing_counterargument_is_rejected():
    bad = _good_analysis()
    bad["insights"][0]["counterargument"] = {}
    _, state, findings = analyse("Sony Interactive Entertainment", SIE_OBS,
                                 client=RecordedClient(bad))
    assert state == ResultState.STRATEGICALLY_INSUFFICIENT
    assert any(f.check == "no_counterargument" for f in findings)


def test_missing_economic_mechanism_is_rejected():
    bad = _good_analysis()
    bad["insights"][0]["economics"] = {"mechanism": "", "levers": []}
    _, _, findings = analyse("Sony Interactive Entertainment", SIE_OBS,
                             client=RecordedClient(bad))
    assert any(f.check == "no_economic_mechanism" for f in findings)


def test_subsidiary_without_named_parent_is_rejected():
    bad = _good_analysis()
    bad["entity_scope"] = {"analysed_entity": "Sony Interactive "
                           "Entertainment", "is_subsidiary": True,
                           "parent": ""}
    _, state, findings = analyse("Sony Interactive Entertainment", SIE_OBS,
                                 client=RecordedClient(bad))
    assert any(f.check == "unnamed_parent" for f in findings)
    assert state == ResultState.STRATEGICALLY_INSUFFICIENT


# --- honest refusal --------------------------------------------------------

def test_model_declaring_evidence_insufficient_is_respected():
    thin = {"entity_scope": {"analysed_entity": "Acme", "is_subsidiary": False},
            "business_model": "Unclear from the retrieved pages.",
            "sufficient_for_strategic_analysis": False,
            "insufficiency_reason": "Only descriptive marketing was retrieved.",
            "insights": [], "evidence_gaps": ["No filings or reporting."]}
    analysis, state, _ = analyse("Acme", SIE_OBS,
                                 client=RecordedClient(thin))
    assert state == ResultState.STRATEGICALLY_INSUFFICIENT
    assert analysis.insufficiency_reason


def test_no_client_raises_rather_than_inventing():
    with pytest.raises(AnalystUnavailable):
        analyse("Acme", SIE_OBS, client=None)


def test_too_little_evidence_short_circuits_before_any_call():
    analysis, state, _ = analyse("Acme", SIE_OBS[:1], client=None)
    assert state == ResultState.EVIDENCE_LIMITED
    assert analysis is None


def test_transport_failure_is_bounded_and_reported():
    client = RecordedClient(_good_analysis(), fail_times=99)
    analysis, state, _ = analyse("Acme", SIE_OBS, client=client)
    assert state == ResultState.FAILED
    assert analysis is None
    assert client.calls == 2                      # MAX_ATTEMPTS, not unbounded


def test_one_transient_failure_is_retried():
    client = RecordedClient(_good_analysis(), fail_times=1)
    _, state, _ = analyse("Sony Interactive Entertainment", SIE_OBS,
                          client=client)
    assert state == ResultState.COMPLETE
    assert client.calls == 2


# --- caching ---------------------------------------------------------------

def test_cache_prevents_a_second_call_for_identical_evidence(tmp_path):
    cache = FileCache(tmp_path)
    client = RecordedClient(_good_analysis())
    analyse("Sony Interactive Entertainment", SIE_OBS, client=client,
            cache=cache)
    analyse("Sony Interactive Entertainment", SIE_OBS, client=client,
            cache=cache)
    assert client.calls == 1


def test_cache_key_changes_when_evidence_changes():
    a = cache_key(SIE_OBS, "Sony", "m")
    b = cache_key(SIE_OBS[:2], "Sony", "m")
    assert a != b


def test_cache_key_changes_when_prompt_version_changes(monkeypatch):
    before = cache_key(SIE_OBS, "Sony", "m")
    monkeypatch.setattr(
        "intent_engine.strategic_intelligence.analyst.runner.PROMPT_VERSION",
        "different-version")
    assert cache_key(SIE_OBS, "Sony", "m") != before


# --- the critic used directly ----------------------------------------------

def test_verify_analysis_reports_every_problem_not_just_the_first():
    bad = _good_analysis()
    bad["insights"][0]["citations"] = ["nope"]
    bad["insights"][0]["counterargument"] = {}
    findings = verify_analysis(bad, observations=SIE_OBS,
                               company_name="Sony Interactive Entertainment")
    checks = {f.check for f in findings}
    assert {"citation_unresolvable", "no_counterargument"} <= checks
