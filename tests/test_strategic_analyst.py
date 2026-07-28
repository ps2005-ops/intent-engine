"""The grounded analyst and the deterministic critic that polices it.

No network and no model: every test drives a recorded client, so CI is
deterministic. What is being tested is the CONTRACT -- that a fluent but
ungrounded analysis is rejected rather than rendered, and that what reaches a
founder is advice rather than a data structure.
"""
import copy

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


def _good():
    return {
        "entity_scope": {"analysed_entity": "Sony Interactive Entertainment",
                         "is_subsidiary": True, "parent": "Sony Group",
                         "scope_note": "Segment figures are group-level."},
        "business_model": {
            "one_line": "Sells PlayStation hardware near cost and earns on "
                        "software, subscription tiers and first-party "
                        "catalogue.",
            "where_profit_comes_from": "Software attach and PlayStation Plus "
                                       "subscriptions, not the console.",
            "where_value_leaks": "First-party titles placed in the catalogue "
                                 "earn subscription revenue instead of "
                                 "full-price unit revenue.",
            "what_customers_actually_buy": "Access to a specific catalogue "
                                           "and the friends already on it.",
            "what_management_appears_to_optimise": "Install base and "
                                                   "first-party catalogue "
                                                   "value (inferred).",
        },
        "sufficient_for_strategic_analysis": True,
        "insufficiency_reason": "",
        "the_insight": {
            "sentence": "PlayStation Plus tiers turn the console install base "
                        "into recurring subscription revenue, making the "
                        "catalogue rather than hardware the retention asset.",
            "paragraph": "Hardware sold near cost is recovered through attach "
                         "and subscription, so the catalogue is what keeps a "
                         "player paying once the console is bought.",
            "why_now": "Tiered PlayStation Plus and cloud streaming are live.",
            "tension": {"side_a": "Putting first-party titles in the "
                                  "subscription raises retention.",
                        "side_b": "It cannibalises full-price sales of the "
                                  "same titles.",
                        "why_it_exists": "The catalogue is both the "
                                         "subscription's draw and the "
                                         "premium product."},
            "economics": {"mechanism": "Subscription revenue is recurring and "
                                       "higher margin than hardware sold near "
                                       "cost; day-one catalogue inclusion "
                                       "trades unit revenue for retention.",
                          "levers": ["retention", "gross_margin",
                                     "content_economics"]},
            "consequence_chain": [
                "First-party titles enter the catalogue at launch.",
                "Full-price unit revenue on those titles falls.",
                "Subscription retention rises and revenue becomes recurring.",
                "Studio budgets are justified against subscriber months "
                "rather than launch units.",
            ],
            "citations": ["obs-1", "obs-2", "obs-3"],
        },
        "decisions": [{
            "decision": "Put first-party titles into PlayStation Plus on "
                        "release day, or hold them at full price.",
            "why_it_matters": "It sets whether the catalogue or the console "
                              "is the retention asset.",
            "urgency": "this_year",
            "cost_of_waiting": "Every quarter of delay lets subscriber "
                               "expectations set around a rival catalogue.",
            "what_a_competitor_may_do_first": "Microsoft widens Game Pass "
                                              "day-one coverage further.",
            "upside": "Recurring revenue and higher retention.",
            "downside": "Permanent loss of full-price unit revenue.",
            "what_would_invalidate_it": "Evidence that attach revenue is "
                                        "growing faster than subscription.",
            "what_to_watch": "Day-one catalogue announcements.",
            "confidence": "moderate",
            "confidence_rationale": "Moderate -- company pages plus one "
                                    "independent analysis, no subscriber "
                                    "figures disclosed.",
            "missing_evidence": "Subscriber counts and attach rates.",
            "citations": ["obs-1", "obs-3"],
        }],
        "competitive": {
            "who_is_forcing_the_change": "Microsoft, by normalising day-one "
                                         "subscription access.",
            "who_benefits": "Players who buy fewer than three titles a year.",
            "who_loses": "Third-party publishers relying on full-price "
                         "launches.",
            "who_must_respond": "Third-party publishers pricing catalogue "
                                "deals.",
            "who_can_ignore_this": "Nintendo, whose catalogue rarely "
                                   "discounts.",
            "if_nobody_responds": "Console margin stays tied to hardware "
                                  "cycles.",
        },
        "questions": [
            "If the catalogue is the retention asset, what happens the first "
            "year it has no flagship release?",
        ],
        "strongest_case_we_are_wrong": "Hardware cycles still drive the "
                                       "install base, and subscription is "
                                       "additive rather than structural.",
        "evidence_gaps": ["No subscriber counts disclosed."],
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


def _run(payload, obs=None, company="Sony Interactive Entertainment"):
    return analyse(company, obs or SIE_OBS, client=RecordedClient(payload))


# --- the happy path --------------------------------------------------------

def test_grounded_analysis_is_accepted():
    analysis, state, findings = _run(_good())
    assert state == ResultState.COMPLETE
    assert not rejects(findings)
    assert analysis.the_insight["sentence"].startswith("PlayStation Plus")
    assert analysis.decisions[0]["cost_of_waiting"]


def test_evidence_pack_contains_every_observation_id():
    client = RecordedClient(_good())
    analyse("Sony Interactive Entertainment", SIE_OBS, client=client)
    packed = client.last_kwargs["user_message"]
    for o in SIE_OBS:
        assert o.observation_id in packed
    assert "independent_reporting" in packed


# --- founder-shaped output -------------------------------------------------

def test_analysis_without_decisions_is_not_complete():
    """Something true that a founder cannot act on is not a finished answer."""
    bad = _good()
    bad["decisions"] = []
    analysis, state, findings = _run(bad)
    assert state == ResultState.STRATEGICALLY_INSUFFICIENT
    assert any(f.check == "no_decisions" for f in findings)


def test_a_topic_is_not_a_decision():
    bad = _good()
    bad["decisions"][0]["decision"] = ("Explore opportunities in cloud "
                                       "streaming for the catalogue.")
    _, state, findings = _run(bad)
    assert state == ResultState.STRATEGICALLY_INSUFFICIENT
    assert any(f.check == "not_a_decision" for f in findings)


def test_a_decision_must_say_what_waiting_costs():
    bad = _good()
    bad["decisions"][0]["cost_of_waiting"] = "   "
    _, state, findings = _run(bad)
    assert state == ResultState.STRATEGICALLY_INSUFFICIENT
    assert any(f.check == "no_cost_of_waiting" for f in findings)


def test_software_speak_never_reaches_the_page():
    bad = _good()
    bad["decisions"][0]["why_it_matters"] = (
        "Decision affected: the supporting evidence shows a likely agenda "
        "item for the catalogue.")
    _, state, findings = _run(bad)
    assert state == ResultState.STRATEGICALLY_INSUFFICIENT
    assert any(f.check == "software_speak" for f in findings)


def test_repeating_the_insight_as_a_decision_is_flagged():
    bad = _good()
    bad["decisions"][0]["decision"] = bad["the_insight"]["sentence"]
    _, _, findings = _run(bad)
    assert any(f.check == "repetition" for f in findings)


# --- the critic rejects what it should -------------------------------------

def test_insight_is_grounded_by_its_decisions_citations():
    """Live validation: the model cited all decisions and omitted the nested
    insight citations field. That is a formatting quirk, not an ungrounded
    claim -- but every citation must still resolve."""
    ok = _good()
    del ok["the_insight"]["citations"]
    _, state, findings = _run(ok)
    assert not any(f.check == "citation_missing" for f in findings)
    assert state == ResultState.COMPLETE


def test_uncited_insight_with_uncited_decisions_is_still_rejected():
    bad = _good()
    del bad["the_insight"]["citations"]
    bad["decisions"][0]["citations"] = []
    _, state, findings = _run(bad)
    assert any(f.check == "citation_missing" for f in findings)
    assert state == ResultState.STRATEGICALLY_INSUFFICIENT


def test_unresolvable_citation_is_rejected():
    bad = _good()
    bad["the_insight"]["citations"] = ["obs-1", "obs-99"]
    analysis, state, findings = _run(bad)
    assert state == ResultState.STRATEGICALLY_INSUFFICIENT
    assert analysis is None
    assert any(f.check == "citation_unresolvable" for f in findings)


def test_unresolvable_decision_citation_is_rejected():
    bad = _good()
    bad["decisions"][0]["citations"] = ["obs-nope"]
    _, state, findings = _run(bad)
    assert state == ResultState.STRATEGICALLY_INSUFFICIENT
    assert any(f.check == "citation_unresolvable" for f in findings)


def test_invented_number_is_rejected():
    bad = _good()
    bad["the_insight"]["economics"]["mechanism"] = (
        "Subscription gross margin runs near 70% versus hardware sold at cost.")
    _, state, findings = _run(bad)
    assert state == ResultState.STRATEGICALLY_INSUFFICIENT
    assert any(f.check == "invented_number" for f in findings)


def test_calendar_years_are_not_invented_figures():
    """Found in cross-sector validation: a sound bank analysis was thrown away
    because it said a loan book reprices through 2026."""
    ok = _good()
    ok["the_insight"]["why_now"] = ("The catalogue commitment runs through "
                                    "2026.")
    _, state, findings = _run(ok)
    assert not any(f.check == "invented_number" for f in findings)
    assert state == ResultState.COMPLETE


def test_a_real_figure_is_still_caught_alongside_a_year():
    bad = _good()
    bad["the_insight"]["why_now"] = ("By 2026 subscription revenue reached "
                                     "$4,200 million.")
    _, _, findings = _run(bad)
    assert any(f.check == "invented_number" for f in findings)


def test_number_that_appears_in_evidence_is_allowed():
    obs = list(SIE_OBS) + [
        _obs("obs-4", "Disclosed margin",
             "The company disclosed a services gross margin of 70% for the "
             "period.", source_class="investor_material", title="Results")]
    ok = _good()
    ok["the_insight"]["economics"]["mechanism"] = (
        "Disclosed services gross margin of 70% versus hardware near cost.")
    ok["the_insight"]["citations"] = ["obs-1", "obs-4"]
    _, state, findings = _run(ok, obs=obs)
    assert not any(f.check == "invented_number" for f in findings)
    assert state == ResultState.COMPLETE


def test_generic_insight_is_rejected():
    """The original failure: fluent, confident, true of anyone."""
    bad = _good()
    bad["the_insight"]["sentence"] = (
        "The company is absorbing adjacent tools until the work lives inside "
        "its platform ecosystem.")
    _, state, findings = _run(bad)
    assert state == ResultState.STRATEGICALLY_INSUFFICIENT
    assert any(f.check == "generic_headline" for f in findings)


def test_real_product_names_wrapped_in_strategy_speak_are_rejected():
    """Naming two things from the evidence clears the anchoring test while
    still saying nothing. Density catches what anchoring cannot."""
    bad = _good()
    bad["the_insight"]["sentence"] = (
        "PlayStation is expanding its subscription platform ecosystem.")
    _, state, findings = _run(bad)
    assert state == ResultState.STRATEGICALLY_INSUFFICIENT
    assert any(f.check == "generic_density" for f in findings)


def test_filler_phrases_are_rejected():
    bad = _good()
    bad["the_insight"]["sentence"] = (
        "PlayStation Plus drives growth through digital transformation of the "
        "catalogue.")
    _, _, findings = _run(bad)
    assert any(f.check == "generic_filler" for f in findings)


def test_high_confidence_from_company_pages_only_is_rejected():
    bad = _good()
    bad["decisions"][0]["confidence"] = "high"
    bad["the_insight"]["citations"] = ["obs-1", "obs-2"]      # both company
    _, state, findings = _run(bad)
    assert state == ResultState.STRATEGICALLY_INSUFFICIENT
    assert any(f.check == "confidence_exceeds_evidence" for f in findings)


def test_missing_counterargument_is_rejected():
    bad = _good()
    bad["strongest_case_we_are_wrong"] = ""
    _, state, findings = _run(bad)
    assert state == ResultState.STRATEGICALLY_INSUFFICIENT
    assert any(f.check == "no_counterargument" for f in findings)


def test_missing_economic_mechanism_is_rejected():
    bad = _good()
    bad["the_insight"]["economics"] = {"mechanism": "", "levers": []}
    _, _, findings = _run(bad)
    assert any(f.check == "no_economic_mechanism" for f in findings)


def test_subsidiary_without_named_parent_is_rejected():
    bad = _good()
    bad["entity_scope"] = {"analysed_entity": "Sony Interactive Entertainment",
                           "is_subsidiary": True, "parent": ""}
    _, state, findings = _run(bad)
    assert any(f.check == "unnamed_parent" for f in findings)
    assert state == ResultState.STRATEGICALLY_INSUFFICIENT


# --- honest refusal --------------------------------------------------------

def test_model_declaring_evidence_insufficient_is_respected():
    thin = {"entity_scope": {"analysed_entity": "Acme", "is_subsidiary": False},
            "business_model": {"one_line": "Unclear from the retrieved pages."},
            "sufficient_for_strategic_analysis": False,
            "insufficiency_reason": "Only descriptive marketing was retrieved.",
            "the_insight": {}, "decisions": [], "competitive": {},
            "questions": [], "strongest_case_we_are_wrong": "",
            "evidence_gaps": ["No filings or reporting."]}
    analysis, state, _ = analyse("Acme", SIE_OBS, client=RecordedClient(thin))
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
    client = RecordedClient(_good(), fail_times=99)
    analysis, state, _ = analyse("Acme", SIE_OBS, client=client)
    assert state == ResultState.FAILED
    assert analysis is None
    assert client.calls == 2                      # MAX_ATTEMPTS, not unbounded


def test_one_transient_failure_is_retried():
    client = RecordedClient(_good(), fail_times=1)
    _, state, _ = analyse("Sony Interactive Entertainment", SIE_OBS,
                          client=client)
    assert state == ResultState.COMPLETE
    assert client.calls == 2


# --- caching ---------------------------------------------------------------

def test_cache_prevents_a_second_call_for_identical_evidence(tmp_path):
    cache = FileCache(tmp_path)
    client = RecordedClient(_good())
    analyse("Sony Interactive Entertainment", SIE_OBS, client=client,
            cache=cache)
    analyse("Sony Interactive Entertainment", SIE_OBS, client=client,
            cache=cache)
    assert client.calls == 1


def test_cache_key_changes_when_evidence_changes():
    assert cache_key(SIE_OBS, "Sony", "m") != cache_key(SIE_OBS[:2], "Sony",
                                                        "m")


def test_cache_key_changes_when_prompt_version_changes(monkeypatch):
    before = cache_key(SIE_OBS, "Sony", "m")
    monkeypatch.setattr(
        "intent_engine.strategic_intelligence.analyst.runner.PROMPT_VERSION",
        "different-version")
    assert cache_key(SIE_OBS, "Sony", "m") != before


# --- the critic used directly ----------------------------------------------

def test_verify_analysis_reports_every_problem_not_just_the_first():
    bad = copy.deepcopy(_good())
    bad["the_insight"]["citations"] = ["nope"]
    bad["strongest_case_we_are_wrong"] = ""
    findings = verify_analysis(bad, observations=SIE_OBS,
                               company_name="Sony Interactive Entertainment")
    checks = {f.check for f in findings}
    assert {"citation_unresolvable", "no_counterargument"} <= checks
