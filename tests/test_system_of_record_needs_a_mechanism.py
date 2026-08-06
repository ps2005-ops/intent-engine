"""Being a platform is not evidence that the record moved into it.

`buyer_concentration_exposure` was taught to require a causal mechanism. The
same defect was still live one pattern over, and it took three real companies
to see it.

`tool_to_system_of_record` qualified on any two of `consolidation`,
`multi_product` and `developer_surface`. The last two are true of very nearly
every B2B software company — several products and an API — so the reading
fired on *being a platform at all*. Measured live on preview-v3 at dad7d28,
Palantir, HubSpot and Snowflake each returned a DIFFERENT dominant reading
(the regulated-buyer fix holding) and then all three carried the identical
second sentence, verbatim apart from the company name:

    "{company} appears to be broadening from a focused tool toward being the
    place a team's work is stored, which raises switching cost and blunts the
    original product's sharpness."

The pattern's own `mechanism` field says the customer's source of truth moves
and switching cost rises once other systems read from it. Nothing in
`multi_product + developer_surface` says that. So the fix is not to vary the
wording — repeated readings stay legal when the evidence repeats — it is to
require the mechanism the sentence is asserting.
"""
from __future__ import annotations

import pytest

from intent_engine.strategic_intelligence.observations import (
    _detect_signals, derive_observations,
)
from intent_engine.strategic_intelligence.patterns import (
    HYPOTHESIS_SCAFFOLDS, PATTERN_LIBRARY,
)
from intent_engine.strategic_intelligence.reasoning import _hypothesis_for

PATTERNS = {p.pattern_id: p for p in PATTERN_LIBRARY}
SOR = PATTERNS["tool_to_system_of_record"]
SOR_SCAFFOLD = HYPOTHESIS_SCAFFOLDS["tool_to_system_of_record"]
MECHANISMS = ("system_of_record_claim", "shared_data_model",
              "replaces_incumbent_systems")

# What almost every B2B software company publishes. This is the input that
# used to be sufficient.
ATTRIBUTES_ONLY = (
    "Explore our product suite: analytics, collaboration and reporting. "
    "Developers can use our REST API and read the developer docs."
)


def _doc(sid, url, title, text, source_type="product"):
    return {"source_id": sid, "source_type": source_type, "final_url": url,
            "title": title, "meta_description": "", "text_content": text,
            "retrieval_status": "OK", "freshness": "CURRENT",
            "content_hash": sid, "retrieved_at": "2026-08-06",
            "parser_version": "p1"}


def _fires(docs, company="Acme"):
    obs = derive_observations(docs, company=company)
    return _hypothesis_for(SOR, SOR_SCAFFOLD, obs, company)


# --- the pattern declares what it needs -------------------------------------

def test_the_pattern_requires_a_causal_mechanism():
    """The gate infrastructure already existed. This pattern did not use it."""
    assert SOR.required_any_signals, \
        "tool_to_system_of_record has no mechanism gate"
    assert set(SOR.required_any_signals) == set(MECHANISMS)


def test_every_mechanism_is_a_qualifying_signal():
    """`validate()` enforces this, but state it where it is readable."""
    for m in MECHANISMS:
        assert m in SOR.qualifying_signals


def test_the_pattern_says_what_would_argue_against_it():
    """It previously declared nothing at all."""
    assert SOR.disconfirming_signals


# --- signal detection: attributes are not mechanisms -------------------------

def test_products_and_an_api_are_not_a_mechanism():
    """The exact shape that produced the same sentence for three companies."""
    found = _detect_signals(ATTRIBUTES_ONLY)
    assert "multi_product" in found
    assert "developer_surface" in found
    assert not (set(found) & set(MECHANISMS))


@pytest.mark.parametrize("text,expected", [
    ("We are the system of record for your customer data.",
     "system_of_record_claim"),
    ("Maintain a golden record across every team.", "system_of_record_claim"),
    ("Every product runs on a shared data model.", "shared_data_model"),
    ("Customers migrate off their old suite and retire legacy systems.",
     "replaces_incumbent_systems"),
])
def test_each_mechanism_is_detected(text, expected):
    assert expected in _detect_signals(text)


@pytest.mark.parametrize("text", [
    # The record explicitly stays somewhere else. Bare "system of truth"
    # matched this until the phrases were made directional.
    "We integrate with your existing tools. Two-way sync keeps your system "
    "of truth wherever it already lives.",
    # Positioned as an addition, not a replacement.
    "A companion to your system of record, not a replacement for it.",
])
def test_a_keyword_cannot_read_negation_so_the_phrase_carries_direction(text):
    assert not (set(_detect_signals(text)) & set(MECHANISMS))


# --- end to end through the reasoning layer ---------------------------------

def test_a_platform_with_no_mechanism_no_longer_asserts_the_reading():
    docs = [_doc("s1", "https://acme.example/products", "Products",
                 ATTRIBUTES_ONLY)]
    assert _fires(docs) is None


def test_consolidation_copy_alone_is_still_not_enough():
    """Marketing language about replacing tools is what the company SAYS."""
    docs = [_doc("s1", "https://acme.example/", "Acme",
                 "One workspace for everything. Replace several separate "
                 "tools. " + ATTRIBUTES_ONLY)]
    assert _fires(docs) is None


@pytest.mark.parametrize("mechanism_text", [
    "We are the system of record for your customer data.",
    "Every product runs on a shared data model, so the same underlying data "
    "powers each surface.",
    "Customers migrate off their previous suite and retire legacy systems.",
])
def test_a_real_mechanism_still_qualifies(mechanism_text):
    """The gate must not close the pattern down entirely."""
    docs = [_doc("s1", "https://acme.example/", "Acme",
                 ATTRIBUTES_ONLY + " " + mechanism_text)]
    assert _fires(docs) is not None


def test_the_reading_still_names_the_company():
    docs = [_doc("s1", "https://acme.example/", "Acme",
                 ATTRIBUTES_ONLY + " We are the system of record for your "
                 "customer data.")]
    fired = _fires(docs, company="Northwind")
    assert fired is not None
    text = " ".join(str(v) for v in vars(fired).values()) \
        if hasattr(fired, "__dict__") else str(fired)
    assert "Northwind" in text


# --- the property that actually failed live ---------------------------------

def test_two_companies_without_the_mechanism_do_not_share_the_sentence():
    """The live defect, reduced: two different companies, each with nothing
    but platform attributes, both previously received this reading."""
    a = [_doc("s1", "https://a.example/", "A", ATTRIBUTES_ONLY)]
    b = [_doc("s2", "https://b.example/", "B",
              "Our platform spans three products. Read the API reference.")]
    assert _fires(a, company="A") is None
    assert _fires(b, company="B") is None


def test_two_companies_that_both_hold_the_record_may_still_share_it():
    """Repetition is not the defect. Unearned repetition is.

    If two companies genuinely publish the same mechanism, the same reading is
    the correct output, and this test exists so nobody 'fixes' the repetition
    by forcing variety."""
    shared = " We are the system of record for your customer data."
    a = [_doc("s1", "https://a.example/", "A", ATTRIBUTES_ONLY + shared)]
    b = [_doc("s2", "https://b.example/", "B", ATTRIBUTES_ONLY + shared)]
    assert _fires(a, company="A") is not None
    assert _fires(b, company="B") is not None
