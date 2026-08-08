"""The rivalry's object may choose where to look. It may not be the answer.

Wave 7 ended with five real actions and zero established objects, because
every document retrieved was narrative. This planner picks the family whose
editorial purpose is to state the missing dimension — and must do so without
letting the reason it looked there become what it found.
"""
from __future__ import annotations

import inspect

import pytest

from intent_engine.market import action_object_queries as Q
from intent_engine.market import competitive_objects as CO


# --- the line the module must not cross -----------------------------------

def test_the_routing_hint_is_named_so_it_cannot_be_mistaken_for_evidence():
    plans = Q.plan(actor="Magento", action_id="a1",
                   missing_dimensions=["WHO"],
                   routing_hint="enterprise commerce")
    assert plans
    assert all(p.routing_hint_not_evidence == "enterprise commerce"
               for p in plans)
    field_names = {f for f in Q.ActionObjectQueryPlan.__dataclass_fields__}
    assert "competitive_object" not in field_names
    assert "routing_hint_not_evidence" in field_names


def test_the_hint_reaches_the_query_and_never_the_object():
    """The whole circularity, in one test.

    The rivalry says "enterprise commerce". That may appear in the SEARCH
    TERMS. The object extracted from whatever comes back must contain it
    only if the DOCUMENT said it.
    """
    hint = "enterprise commerce"
    plans = Q.plan(actor="Magento", action_id="a1",
                   missing_dimensions=["WHO", "WHAT"], routing_hint=hint)
    assert any(hint in " ".join(p.query_terms) for p in plans)

    # A document that does NOT mention the hint.
    document = ("Magento today launched a one-click checkout for "
                "independent retailers.")
    got, _ = CO.extract(document, action_id="a1", actor="Magento",
                        source="s", created_at="2026-08-08")
    blob = " ".join(str(v) for v in got.as_dict().values()).lower()
    assert "enterprise commerce" not in blob


def test_extract_has_no_parameter_a_plan_could_be_poured_into():
    """Structural, not advisory: there is nowhere to put it."""
    params = set(inspect.signature(CO.extract).parameters)
    for forbidden in ("routing_hint", "routing_hint_not_evidence",
                      "relationship_object", "competitive_object", "plan",
                      "query_terms"):
        assert forbidden not in params


# --- the planner reacts to measured per-question performance --------------

def test_a_measured_zero_sinks_below_an_untried_family():
    """Wave 7 measured the case study at 0.000 for ACTION_OBJECT. Ranking it
    on its 0.500 for NAMED_CUSTOMER is how one number recommended a family
    for a question it had already failed."""
    performance = {Q.CUSTOMER_MIGRATION_STORY: (0, 22)}
    plans = Q.plan(actor="Shopify", action_id="a1",
                   missing_dimensions=["WHO", "SUBSTITUTE"],
                   performance=performance, limit=len(Q.FAMILIES))
    families = [p.candidate_source_family for p in plans]
    assert Q.MIGRATION_PAGE in families
    assert families.index(Q.MIGRATION_PAGE) < \
        families.index(Q.CUSTOMER_MIGRATION_STORY)


def test_a_measured_winner_outranks_the_editorial_prior():
    performance = {Q.RELEASE_NOTES: (8, 10), Q.PRICING_PAGE: (0, 12)}
    plans = Q.plan(actor="Shopify", action_id="a1",
                   missing_dimensions=["WHAT"], performance=performance,
                   limit=len(Q.FAMILIES))
    families = [p.candidate_source_family for p in plans]
    assert families.index(Q.RELEASE_NOTES) < families.index(Q.PRICING_PAGE)


def test_the_plan_states_the_sample_its_choice_rests_on():
    """A measured 0.25 ranks BELOW an untried family on purpose — an untried
    family might be better and a measured one is known not to be — so this
    asks for the whole ranking rather than the head of it."""
    plans = Q.plan(actor="Shopify", action_id="a1",
                   missing_dimensions=["WHAT"],
                   performance={Q.PRICING_PAGE: (3, 12)},
                   limit=len(Q.FAMILIES))
    priced = [p for p in plans
              if p.candidate_source_family == Q.PRICING_PAGE][0]
    assert priced.measured_sample == 12
    assert priced.measured_yield == pytest.approx(0.25)
    assert "3/12" in priced.expected_information_gain


def test_an_untried_family_says_so_rather_than_reporting_zero():
    """UNMEASURED is not zero. They are opposite findings."""
    plans = Q.plan(actor="Shopify", action_id="a1",
                   missing_dimensions=["WHAT"])
    assert all(p.measured_yield is None for p in plans)
    assert all("never attempted" in p.expected_information_gain
               for p in plans)


# --- high value never buys a generic page ---------------------------------

def test_a_high_voi_question_never_routes_to_a_generic_page():
    plans = Q.plan(actor="Salesforce", action_id="a1",
                   missing_dimensions=["WHO", "WHAT"],
                   voi_priority="HIGH", limit=len(Q.FAMILIES))
    assert plans
    for generic in Q.GENERIC_FAMILIES:
        assert all(p.candidate_source_family != generic for p in plans[:4])


def test_a_generic_family_cannot_outrank_a_purposeful_one():
    """Even with a flattering measured yield, the homepage stays last:
    a homepage that once mentioned a buyer is still not a page about one."""
    performance = {Q.HOMEPAGE: (5, 5), Q.PRICING_PAGE: (0, 0)}
    plans = Q.plan(actor="Shopify", action_id="a1",
                   missing_dimensions=["WHO"], performance=performance,
                   limit=len(Q.FAMILIES))
    families = [p.candidate_source_family for p in plans]
    if Q.HOMEPAGE in families:
        assert families.index(Q.PRICING_PAGE) < families.index(Q.HOMEPAGE)


# --- the plan must name a real gap ----------------------------------------

def test_an_established_object_is_not_planned_for():
    with pytest.raises(Q.PlanRejected) as excinfo:
        Q.plan(actor="Shopify", action_id="a1", missing_dimensions=[])
    assert "already established" in str(excinfo.value)


def test_families_are_chosen_for_the_dimension_that_is_missing():
    substitute = Q.plan(actor="Shopify", action_id="a1",
                        missing_dimensions=["SUBSTITUTE"], limit=3)
    assert substitute[0].candidate_source_family in (
        Q.MIGRATION_PAGE, Q.CUSTOMER_MIGRATION_STORY, Q.COMPARISON_PAGE)
    who = Q.plan(actor="Shopify", action_id="a1",
                 missing_dimensions=["WHO"], limit=3)
    assert all("WHO" in Q._SUPPLIES[p.candidate_source_family] for p in who)


def test_release_notes_are_not_offered_for_a_missing_buyer():
    """A changelog states what shipped and never who it is for."""
    plans = Q.plan(actor="Shopify", action_id="a1",
                   missing_dimensions=["WHO"], limit=len(Q.FAMILIES))
    assert all(p.candidate_source_family != Q.RELEASE_NOTES for p in plans)


# --- url classification ---------------------------------------------------

@pytest.mark.parametrize("url,family", [
    ("https://www.bigcommerce.com/essentials/pricing/", Q.PRICING_PAGE),
    ("https://www.bigcommerce.com/migration/", Q.MIGRATION_PAGE),
    ("https://www.shopify.com/pricing", Q.PRICING_PAGE),
    ("https://www.salesforce.com/solutions/retail/", Q.SOLUTION_PAGE),
    ("https://www.bigcommerce.com/", Q.HOMEPAGE),
])
def test_a_url_is_classified_by_its_own_path(url, family):
    assert Q.family_of(url) == family


def test_summarise_counts_the_generic_plans_it_made():
    plans = Q.plan(actor="Shopify", action_id="a1",
                   missing_dimensions=["WHO", "WHAT"], limit=len(Q.FAMILIES))
    got = Q.summarise(plans)
    assert got["plans"] == len(plans)
    assert got["generic_families_planned"] == 0
