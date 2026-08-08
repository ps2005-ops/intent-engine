"""An action is not an interaction, and a labelled object is not an object.

The measurement that shaped this: 16 real actions were retrieved from rival
sites, the harness labelled every one "E-commerce platform", and relevance
duly scored 18 RELEVANT pairs — all of them Salesforce posts about AI
agents. Trusting a caller-supplied competitive object makes relevance
circular, so it now yields UNKNOWN, and the honest count is zero.
"""
from __future__ import annotations

import pytest

from intent_engine.market import competitive_actions as CA
from intent_engine.market import cross_actor_expectations as CAX


def act(**overrides):
    kwargs = dict(actor="Shopify", action_type=CA.PRODUCT_LAUNCH,
                  competitive_object="E-commerce platform",
                  event_time="2026-08-08", evidence_ids=("doc:x",),
                  span="Shopify today announced Checkout Blocks.",
                  source_family="official_announcement")
    kwargs.update(overrides)
    return CA.action(**kwargs)


# --- what an action must have ---------------------------------------------

def test_an_action_with_no_time_cannot_order_anything():
    with pytest.raises(CA.ActionRejected, match="ordering"):
        act(event_time="")


def test_an_action_with_no_evidence_is_model_knowledge():
    with pytest.raises(CA.ActionRejected, match="model knowledge"):
        act(evidence_ids=())


def test_an_action_carries_no_motive():
    assert "no motive" in act().as_dict()["caution"]
    assert act().standing == "OBSERVED"


# --- the registry is addresses, not competitors ---------------------------

def test_the_registry_asserts_no_competitive_position():
    entry = CA.REGISTRY[0]
    assert "asserts nothing about competitive position" in entry.basis
    assert CA.site_for("Magento").startswith("https://")
    assert CA.site_for("Magento Commerce") == CA.site_for("Magento")
    assert CA.site_for("A Company Nobody Named") == ""


def test_the_registry_is_not_the_curated_competitor_list():
    import inspect
    source = inspect.getsource(CA)
    # Behaviour, not grep: the module may DISCUSS the curated list and must
    # never read it.
    assert ".competitors" not in source
    assert "default_universe" not in source
    assert "peer_group" not in source


# --- narrative prose is not an announcement -------------------------------

NOT_ACTIONS = [
    ("narrative ships", "The other ships the agent and moves on."),
    ("retrospective", "One agent is just a bit better than the day it "
                      "shipped, which is the point of the whole exercise."),
    ("biography", "He was formerly the co-founder of Spindle AI, acquired "
                  "in 2025 by Salesforce, where his portfolio grew."),
    ("product description", "Gemma instantly resolves routine customer "
                            "inquiries from order status to shipping."),
]


@pytest.mark.parametrize("label,text", NOT_ACTIONS,
                         ids=[n for n, _ in NOT_ACTIONS])
def test_narrative_prose_does_not_become_an_action(label, text):
    got, _ = CA.extract(text, actor="Salesforce",
                        competitive_object="E-commerce platform",
                        event_time="2026-08-08", source="s",
                        source_family="official_announcement")
    assert got == (), [g.span for g in got]


@pytest.mark.parametrize("text,kind", [
    ("Salesforce today announced Agentforce Commerce for every merchant.",
     CA.PRODUCT_LAUNCH),
    ("Shopify cut its Plus pricing for mid-market merchants this quarter.",
     CA.PRICE_CHANGE),
    ("Shopify has agreed to acquire Checkout Systems for its merchants.",
     CA.ACQUISITION),
])
def test_a_real_announcement_is_an_action(text, kind):
    (got,), _ = CA.extract(text, actor="X",
                           competitive_object="E-commerce platform",
                           event_time="2026-08-08", source="s",
                           source_family="official_announcement")
    assert got.action_type == kind


# --- relevance is not circular --------------------------------------------

def test_an_asserted_competitive_object_yields_unknown_not_relevant():
    """The exact defect: 16 AI-agent posts labelled "E-commerce platform"
    scored 18 RELEVANT pairs because the label was trusted."""
    got = CA.assess(act(object_established=False),
                    relationship_id="cmp_1",
                    relationship_object="E-commerce platform",
                    relationship_actors=["Shopify", "Magento"])
    assert got.relevant == CA.UNKNOWN
    assert "circular" in got.reason


def _established(span, actor="Shopify"):
    from intent_engine.market import competitive_objects as CO
    obj, _ = CO.extract(span, action_id="a1", actor=actor, source="s",
                        created_at="2026-08-08")
    assert obj is not None and obj.is_usable, span
    return obj


def test_an_established_object_can_be_relevant():
    """Relevance now runs on the object the DOCUMENT established, and a
    second comparison against the action's label would reintroduce the
    label the module refuses to trust."""
    span = "Shopify launched Checkout Blocks for enterprise merchants."
    got = CA.assess(act(object_established=True, span=span),
                    relationship_id="cmp_1",
                    relationship_object="checkout infrastructure",
                    relationship_actors=["Shopify", "Magento"],
                    established_object=_established(span))
    assert got.relevant == CA.RELEVANT
    assert "contests" in got.reason


def test_a_different_object_is_irrelevant():
    span = "Shopify launched Checkout Blocks for enterprise merchants."
    got = CA.assess(act(object_established=True, span=span),
                    relationship_id="cmp_1",
                    relationship_object="CRM seat budget",
                    relationship_actors=["Shopify", "Magento"],
                    established_object=_established(span))
    assert got.relevant == CA.IRRELEVANT


def test_an_adjacent_object_is_unknown_not_relevant():
    """ADJACENT never builds an interaction."""
    span = "Shopify launched Checkout Blocks for enterprise merchants."
    got = CA.assess(act(object_established=True, span=span),
                    relationship_id="cmp_1",
                    relationship_object="enterprise commerce platform",
                    relationship_actors=["Shopify", "Magento"],
                    established_object=_established(span))
    assert got.relevant in (CA.UNKNOWN, CA.IRRELEVANT)
    assert got.relevant != CA.RELEVANT


def test_an_actor_outside_the_relationship_is_irrelevant():
    got = CA.assess(act(actor="Comcast", object_established=True),
                    relationship_id="cmp_1",
                    relationship_object="E-commerce platform",
                    relationship_actors=["Shopify", "Magento"])
    assert got.relevant == CA.IRRELEVANT
    assert "not a party" in got.reason


# --- preregistration: the order is the whole thing ------------------------

def expectation(**overrides):
    kwargs = dict(interaction_id="int_1", trigger_actor="Shopify",
                  counterparty="Magento",
                  trigger_action="launched a migration programme",
                  mechanism="a migration programme lowers the switching "
                            "cost away from Magento for the same buyer",
                  expected_response_class=(CAX.MIGRATION_INCENTIVE,),
                  resolution_window="2026-11-08",
                  disconfirming_outcome="Magento announces no migration or "
                                        "pricing change by the window",
                  created_at="2026-08-08")
    kwargs.update(overrides)
    return CAX.register(**kwargs)


def test_a_menu_of_responses_is_not_a_prediction():
    with pytest.raises(CAX.ExpectationRejected, match="menu"):
        expectation(expected_response_class=(
            CAX.PRICE_RESPONSE, CAX.PRODUCT_RESPONSE, CAX.BUNDLE_RESPONSE,
            CAX.MIGRATION_INCENTIVE))


def test_an_expectation_must_name_what_would_make_it_wrong():
    with pytest.raises(CAX.ExpectationRejected, match="wrong"):
        expectation(disconfirming_outcome="")


def test_an_expectation_must_state_why_they_would_respond():
    with pytest.raises(CAX.ExpectationRejected, match="coincidence"):
        expectation(mechanism="  ")


def test_a_window_that_closes_before_it_opens_is_refused():
    with pytest.raises(CAX.ExpectationRejected, match="no future"):
        expectation(resolution_window="2026-08-01")


def test_evidence_predating_the_prediction_cannot_test_it():
    """The only structural defence against a story assembled backwards."""
    with pytest.raises(CAX.ExpectationRejected, match="predates"):
        CAX.observe(expectation(), response_class=CAX.MIGRATION_INCENTIVE,
                    observed_at="2026-07-01", evidence_ids=("ev_1",),
                    as_of="2026-09-01")


def test_a_matching_later_response_confirms():
    got = CAX.observe(expectation(), response_class=CAX.MIGRATION_INCENTIVE,
                      observed_at="2026-09-01", evidence_ids=("ev_1",),
                      as_of="2026-09-01")
    assert got.outcome == CAX.CONFIRMED
    assert got.status == CAX.RESOLVED


def test_a_different_response_is_an_alternative_not_a_refutation():
    got = CAX.observe(expectation(), response_class=CAX.PRICE_RESPONSE,
                      observed_at="2026-09-01", evidence_ids=("ev_1",),
                      as_of="2026-09-01")
    assert got.outcome == CAX.ALTERNATIVE_RESPONSE


def test_silence_inside_the_window_is_not_a_refutation():
    got = CAX.observe(expectation(), response_class=CAX.NO_RESPONSE,
                      observed_at="2026-09-01", evidence_ids=(),
                      as_of="2026-09-01")
    assert got.outcome == CAX.NO_RESPONSE_YET
    assert got.status == CAX.OPEN


def test_silence_past_the_window_contradicts():
    got = CAX.observe(expectation(), response_class=CAX.NO_RESPONSE,
                      observed_at="2026-12-01", evidence_ids=(),
                      as_of="2026-12-01")
    assert got.outcome == CAX.CONTRADICTED


def test_an_unresolved_expectation_is_reported_as_a_success():
    assert "is a success" in CAX.summarise([expectation()])["note"]


# --- a restructuring is a price change, and a footer is not ---------------
#
# The live BigCommerce announcement reads "Starting June 1, 2026,
# BigCommerce is updating its plan structure and pricing" and matched no
# pattern: no cut, no raise, no "new pricing". The dated frame is what lets
# it in without letting in every page that mentions updated pricing.

DATED_PRICE_CHANGES = [
    "Starting June 1, 2026, BigCommerce is updating its plan structure "
    "and pricing.",
    "Effective March 1, 2026, we are changing our rates for all plans.",
]

UNDATED_PRICE_PROSE = [
    "Our pricing page was updated recently with clearer plan structure.",
    "See our updated pricing for more information about fees.",
    "Pricing and plan structure are explained below in detail for you.",
    "Starting a new store is easy and our pricing is simple to understand.",
]


@pytest.mark.parametrize("text", DATED_PRICE_CHANGES)
def test_a_dated_restructuring_is_a_price_change(text):
    found, _ = CA.extract(text, actor="BigCommerce", competitive_object="",
                          event_time="2026-08-08", source="s",
                          source_family="pricing_page")
    assert found and found[0].action_type == CA.PRICE_CHANGE


@pytest.mark.parametrize("text", UNDATED_PRICE_PROSE)
def test_undated_pricing_prose_is_not_a_price_change(text):
    """A change nobody dated is a description of the current price."""
    found, _ = CA.extract(text, actor="BigCommerce", competitive_object="",
                          event_time="2026-08-08", source="s",
                          source_family="pricing_page")
    assert not found
