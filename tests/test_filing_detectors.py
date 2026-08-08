"""Filing-specific detection, feeding the canonical observation contract."""
from __future__ import annotations

import pytest

from intent_engine.strategic_intelligence import filing_detectors as FD
from intent_engine.strategic_intelligence import observations as O

# --- what must be detected --------------------------------------------------
@pytest.mark.parametrize("text,expected", [
    ("Revenue increased 26% to $2.68 billion in fiscal 2025.",
     "revenue_trajectory"),
    ("Revenue growth was driven primarily by expansion within our existing "
     "customer base.", "expansion_within_customers"),
    ("Our net dollar retention rate was above 115% for the period.",
     "expansion_within_customers"),
    ("Annual recurring revenue grew to $3.1 billion as of December 31, 2025.",
     "recurring_revenue_base"),
    ("Gross margin declined to 80% from 82% in the prior year.",
     "margin_trajectory"),
    ("Capital expenditures were $412.0 million for the year.",
     "capital_intensity"),
    ("We acquired Acme Systems to extend our security product line.",
     "acquisition_activity"),
    ("We rely on a limited number of third-party cloud providers.",
     "supplier_dependency"),
    ("We have experienced pricing pressure in our core market.",
     "pricing_exposure"),
    ("The market for observability software is intensely competitive.",
     "competitive_intensity"),
    ("Cash and cash equivalents were $2.1 billion as of year end.",
     "liquidity_position"),
    ("We are subject to regulation by the Federal Trade Commission.",
     "regulatory_constraint"),
])
def test_a_stated_mechanism_is_detected(text, expected):
    assert expected in FD.detect(text)


# --- what must fail closed --------------------------------------------------
@pytest.mark.parametrize("text", [
    # generic risk boilerplate every filing carries
    "Our business could be adversely affected by a number of factors beyond "
    "our control, among other things.",
    "There can be no assurance that we will be successful in these efforts.",
    "Our results may be materially adversely affected by these conditions.",
    # headings and furniture
    "Item 1A. Risk Factors",
    "TABLE OF CONTENTS",
    "ANNUAL REPORT PURSUANT TO SECTION 13 OR 15(d) OF THE SECURITIES "
    "EXCHANGE ACT OF 1934",
    # descriptive prose with no mechanism
    "We are a monitoring and security platform for cloud applications.",
    "Our headquarters are located in New York, New York.",
    # a topic word without a direction or a figure
    "We discuss revenue in the following section.",
    "Margin is an important measure for our business.",
    "",
])
def test_prose_without_a_mechanism_fails_closed(text):
    assert FD.detect(text) == []


def test_a_subject_and_its_mechanism_must_share_a_sentence():
    """A document-wide match would let 'revenue' in one paragraph and
    'increased' in another combine into a claim neither makes."""
    split = ("We describe revenue in this section. Headcount increased 12% "
             "during the year.")
    assert "revenue_trajectory" not in FD.detect(split)


# --- the honesty contract ---------------------------------------------------
def test_every_proposition_declares_what_it_cannot_prove():
    for key, spec in FD.PROPOSITIONS.items():
        assert spec["cannot_prove"], key
        assert spec["supports"], key
        assert spec["label"], key


def test_expansion_cannot_prove_satisfaction():
    limit = FD.limitation_for(["expansion_within_customers"])
    assert "satisfaction" in limit


def test_competition_cannot_prove_a_rival_response():
    limit = FD.limitation_for(["competitive_intensity"])
    assert "motive" in limit or "response" in limit


def test_a_risk_disclosure_is_not_a_realised_event():
    """A disclosed dependence proves management considers it material."""
    spec = FD.PROPOSITIONS["supplier_dependency"]
    assert "material" in spec["supports"]
    assert "disrupted" in spec["cannot_prove"]


def test_the_taxonomy_is_closed_and_reviewable():
    assert 8 <= len(FD.PROPOSITIONS) <= 24


# --- canonical observation integrity ----------------------------------------
def test_filing_signals_carry_a_label_and_an_observation_type():
    """No filing-only observation kind: they use the canonical contract."""
    from intent_engine.strategic_intelligence.records import OBSERVATION_TYPES
    for key, spec in FD.PROPOSITIONS.items():
        assert O._SIGNAL_LABEL[key] == spec["label"]
        assert O._TYPE_FOR_SIGNAL[key] == spec["type"]
        assert spec["type"] in OBSERVATION_TYPES


def test_a_filing_becomes_a_canonical_observation():
    doc = {
        "final_url": "https://www.sec.gov/Archives/edgar/data/1/ddog-10k.htm",
        "title": "Datadog 10-K",
        "source_class": "investor_material",
        "content_hash": "f1",
        "text_content": (
            "ANNUAL REPORT PURSUANT TO SECTION 13 OR 15(d) OF THE SECURITIES "
            "EXCHANGE ACT OF 1934. Commission File Number 001-38480. "
            "Item 7. Management's Discussion and Analysis of Financial "
            "Condition and Results of Operations. Revenue increased 26% to "
            "$2.68 billion in fiscal 2025, driven primarily by expansion "
            "within our existing customer base."),
    }
    out = O.derive_observations([doc], company="Datadog")
    assert out, "a filing with a stated mechanism must produce an observation"
    o = out[0]
    assert "PURSUANT TO SECTION" not in o.excerpt
    assert o.source_class == "investor_material"


def test_a_filing_with_only_boilerplate_produces_nothing():
    doc = {
        "final_url": "https://www.sec.gov/Archives/edgar/data/2/x-10k.htm",
        "title": "Acme 10-K",
        "source_class": "investor_material",
        "content_hash": "f2",
        "text_content": (
            "ANNUAL REPORT PURSUANT TO SECTION 13 OR 15(d) OF THE SECURITIES "
            "EXCHANGE ACT OF 1934. Commission File Number 001-1. "
            "Item 1A. Risk Factors. Our business could be adversely affected "
            "by factors beyond our control, among other things. There can be "
            "no assurance that we will be successful."),
    }
    # No FILING PROPOSITION may come from boilerplate. The document can still
    # produce an observation from the pre-existing NEUTRAL `disclosed_risk`
    # detector, which is older than this module and out of its scope -- that
    # detector reads "Risk Factors" language and is what produced the original
    # "discloses specific risks rather than generic caveats" headline, which is
    # arguably wrong when the section holds only generic caveats. Recorded
    # here rather than silently changed.
    assert FD.detect(doc["text_content"]) == []
    for o in O.derive_observations([doc], company="Acme"):
        assert not any(k in (o.signals or ()) for k in FD.PROPOSITIONS)


def test_a_marketing_page_gains_no_filing_signal():
    """The detectors are source-specific: they must not fire on a web page."""
    assert FD.detect("Try Datadog free and see all your metrics in one "
                     "place with our cloud monitoring solution.") == []
