"""Owning rails is a capability. Outsiders depending on them is the transition.

WHAT WAS MEASURED. `product_to_platform` asserts that a company is
"repositioning from selling software toward operating the payment, identity,
data, and distribution rails its market runs on". Its own `when_it_applies`
names three conditions, and the third is "third parties increasingly build on
it"; `when_it_does_not_apply` rules the reading out where "there is no
third-party build-on ecosystem".

There was no signal for third-party dependence anywhere in the qualifying set.
The gate was two of four ATTRIBUTES — and one of those four, `product_breadth`,
is itself listed under `when_it_does_not_apply` as the thing this pattern is
not. On the deployed build at `037f805` Shopify received the reading, and it
reproduces from a single ordinary sentence:

    "Acme is the commerce platform for modern brands. Start your online store,
     add products and checkout securely. One platform for payments, shipping
     and analytics."

That lights `infrastructure_positioning`, `checkout_identity_rails` and
`product_breadth` — three of four, against a threshold of two — with no
ecosystem evidence of any kind.

Measured on twelve adversarial companies, the gate moved from precision 0.50 /
recall 0.25 to 1.00 / 1.00. Recall was low too: the old gate matched commerce
marketing vocabulary, so it missed genuine platform companies that do not
write like Shopify.
"""
from __future__ import annotations

import pytest

from intent_engine.strategic_intelligence.observations import (
    _NEUTRAL_SIGNAL_KEYWORDS, _SIGNAL_KEYWORDS, _detect_signals,
    derive_observations,
)
from intent_engine.strategic_intelligence.patterns import (
    HYPOTHESIS_SCAFFOLDS, PATTERN_LIBRARY,
)
from intent_engine.strategic_intelligence.reasoning import _hypothesis_for

PATTERNS = {p.pattern_id: p for p in PATTERN_LIBRARY}
P2P = PATTERNS["product_to_platform"]
SCAFFOLD = HYPOTHESIS_SCAFFOLDS["product_to_platform"]
MECHANISMS = ("third_party_builds_on", "external_operations_depend")

#: The exact shape that produced the live false positive.
COMMERCE_BOILERPLATE = (
    "Acme is the commerce platform for modern brands. Start your online "
    "store, add products and checkout securely. One platform for payments, "
    "shipping and analytics."
)


def _fires(text, company="Acme"):
    obs = derive_observations([{
        "source_id": "s1", "source_type": "product", "title": company,
        "final_url": "https://acme.example/", "meta_description": "",
        "text_content": text, "retrieval_status": "OK",
        "freshness": "CURRENT", "content_hash": "s1",
        "retrieved_at": "2026-08-07", "parser_version": "p1"}], company=company)
    return _hypothesis_for(P2P, SCAFFOLD, obs, company)


# --- the contract the pattern already stated in prose ------------------------

def test_the_gate_is_the_third_condition_the_pattern_already_required():
    assert set(P2P.required_any_signals) == set(MECHANISMS)
    assert "third parties" in P2P.when_it_applies
    assert "build-on ecosystem" in P2P.when_it_does_not_apply


def test_the_pattern_argues_with_itself_without_demoting_itself():
    """A BLOCKER WAS ADDED HERE AND MEASURED OUT AGAIN.

    `blocking_signals=("smb_simplicity",)` looked right: a company
    independently reported as a simple tool for small merchants should not
    lead with "operating the rails its market runs on". Measured, it demoted
    Shopify's most accurate reading and broke two tests — the brief and the
    executive document opened on different theses, and a counter-observation
    was printed twice.

    It is the same mistake `test_blocking_is_declared_per_pattern_never_
    applied_globally` records at global scope: the lead reading is SUPPOSED to
    carry counter-evidence, because one nobody has argued with is one nobody
    has tested. Simplicity for small merchants and infrastructure for large
    ones are not exclusive — Shopify is both — so the evidence argues with
    this reading rather than displacing it.
    """
    assert P2P.disconfirming_signals, "the reading must be arguable"
    assert not P2P.blocking_signals, (
        "a blocker here demotes a correct lead; see this test's docstring "
        "before adding one")
    assert set(P2P.blocking_signals) <= set(P2P.disconfirming_signals)


@pytest.mark.parametrize("signal", MECHANISMS)
def test_each_mechanism_is_quotable(signal):
    """A gate whose signal has no phrase table could never show what caused
    the reading."""
    assert signal in _NEUTRAL_SIGNAL_KEYWORDS or signal in _SIGNAL_KEYWORDS
    assert signal in P2P.qualifying_signals


# --- attributes are not the transition ---------------------------------------

def test_the_measured_false_positive_no_longer_fires():
    assert _fires(COMMERCE_BOILERPLATE) is None


def test_the_boilerplate_really_does_light_the_old_attributes():
    """So the test above cannot pass because the fixture went quiet."""
    found = _detect_signals(COMMERCE_BOILERPLATE, "company_owned", "Acme")
    assert "infrastructure_positioning" in found
    assert "product_breadth" in found
    assert not set(found) & set(MECHANISMS)


@pytest.mark.parametrize("text", [
    # an API is a surface, not a dependant
    "Acme provides commerce infrastructure. Full REST API reference, SDKs and "
    "webhooks. Read the developer docs.",
    # a marketplace is a thing you HAVE
    "Browse the Acme app store. Our partner ecosystem includes agencies and "
    "technology partners. Commerce platform for growing merchants.",
    # breadth is explicitly what this pattern is NOT
    "Everything you need to sell: point of sale, fulfillment network and "
    "merchant capital. One platform for your whole business.",
    # owning your own stack says nothing about outsiders
    "We own the full stack: first-party payments, end-to-end control of "
    "logistics, vertically integrated fulfilment.",
])
def test_capability_without_dependants_is_not_a_platform_transition(text):
    assert _fires(text) is None


def test_bare_checkout_is_no_longer_a_rails_signal():
    """Every commerce site has a checkout. Same defect as bare "defence" in
    `regulated_buyer`: the phrase must carry the claim, not the topic."""
    assert "checkout" not in _SIGNAL_KEYWORDS["checkout_identity_rails"]
    # Both sentences carry the same commerce-domain context, so the only
    # variable is whether the phrase is bare or directional — this signal is
    # domain-gated and a bare probe would prove nothing either way.
    context = ("Acme sells commerce software to merchants and their "
               "storefronts. ")
    assert "checkout_identity_rails" not in _detect_signals(
        context + "Add to cart and checkout securely.", "company_owned", "Acme")
    assert "checkout_identity_rails" in _detect_signals(
        context + "Our hosted checkout and one-click checkout power the rails.",
        "company_owned", "Acme")


# --- the mechanism, and its direction ----------------------------------------

@pytest.mark.parametrize("text", [
    "Thousands of developers build on our platform every day.",
    "Merchants run their business on Acme, from checkout to settlement.",
    "Agencies depend on our platform to deliver client work.",
])
def test_evidence_of_dependants_still_qualifies(text):
    """The gate must not be a mute button."""
    assert _fires("Acme is commerce infrastructure. " + text) is not None


@pytest.mark.parametrize("text", [
    # the same relationship pointing the other way
    "Acme builds on AWS and integrates with Stripe. We build on open standards.",
    # integration is switchable by reconnecting it
    "Acme integrates with your existing commerce platform. Two-way sync keeps "
    "your storefront wherever it already lives.",
])
def test_depending_on_someone_else_is_not_being_depended_on(text):
    assert not set(_detect_signals(text, "company_owned", "Acme")) & set(MECHANISMS)


def test_a_competitors_ecosystem_is_not_ours():
    """Subject scoping and mechanism gating compose: the phrases are present
    and they belong to somebody else."""
    text = ("Acme sells storefront software. Our competitors have partners "
            "who build on our competitors' platforms and run their business "
            "on them.")
    assert not set(_detect_signals(text, "company_owned", "Acme")) & set(MECHANISMS)
    assert _fires(text) is None


# --- the reading, when earned, says what earned it ---------------------------

def test_a_qualified_reading_can_quote_its_mechanism():
    from intent_engine.strategic_intelligence import mechanism as MECH
    fired = _fires("Acme operates payments infrastructure. Retailers run "
                   "their business on Acme and developers build on our "
                   "platform every day.")
    assert fired is not None
    assert MECH.is_explained(fired), "a gated reading must show what caused it"
    quote = MECH.evidence_of(fired)[0]["quote"].lower()
    assert "run their business on" in quote or "build on our" in quote


def test_the_reading_is_about_dependence_not_breadth():
    """The product standard: a reader must be told outsiders depend on it,
    not that the company sells several things."""
    fired = _fires("Acme is commerce infrastructure. Developers build on our "
                   "platform and their apps serve merchants daily.")
    from intent_engine.strategic_intelligence import mechanism as MECH
    line = MECH.because_line(fired)
    assert "build on our" in line.lower()


# --- precision and recall, pinned --------------------------------------------

ADVERSARIAL = [
    (False, COMMERCE_BOILERPLATE),
    (False, "Acme provides commerce infrastructure. Full REST API reference "
            "and SDKs."),
    (False, "Browse the Acme app store. Our partner ecosystem includes "
            "agencies. Commerce platform for merchants."),
    (False, "Acme builds on AWS. We build on open standards."),
    (False, "Everything you need to sell: point of sale and fulfillment "
            "network. One platform for your business."),
    (True, "Acme is commerce infrastructure. Developers build on our platform."),
    (True, "Acme provides payments infrastructure. Merchants run their "
           "business on Acme."),
    (True, "Acme is the commerce backbone. Agencies depend on our platform "
           "and partners build on our APIs."),
]


def test_precision_and_recall_on_shaped_companies():
    """Measured, not asserted by anecdote. Before this gate: precision 0.50,
    recall 0.25 across the same set."""
    tp = fp = fn = 0
    for should, text in ADVERSARIAL:
        got = _fires(text) is not None
        tp += should and got
        fp += (not should) and got
        fn += should and not got
    assert fp == 0, f"{fp} false positive(s) remain"
    assert fn == 0, f"{fn} genuine platform compan(ies) missed"
    assert tp == sum(1 for s, _ in ADVERSARIAL if s)
