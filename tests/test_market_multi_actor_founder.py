"""The three items wave 6 owed, built and tested on canonical fixtures.

There is no live interaction, so the founder path is proved deterministically.
That is the right order: the contract should exist and be strict BEFORE real
data arrives, or the first real interaction is also the first time anybody
finds out what the surface says.
"""
from __future__ import annotations

import pytest

from intent_engine.market import competitive_objects as CO
from intent_engine.market import competitor_voi as CV
from intent_engine.market import multi_actor_view as MAV
from intent_engine.market import research_planning as RP
from intent_engine.market import strategic_objectives as SO


# --- source performance by question type ---------------------------------

def perf(family, question, yield_=0.2, retrieved=50):
    return RP.SourceFamilyPerformance(
        source_family=family, question_type=question, retrieved=retrieved,
        relationship_yield=yield_, last_updated="2026-08-08")


REAL = [
    perf("customer_case_study", RP.NEEDS_CUSTOMER, 0.500, 22),
    perf("customer_case_study", RP.NEEDS_COMPETITOR, 0.136, 22),
    perf("customer_case_study", RP.NEEDS_ACTION_OBJECT, 0.000, 22),
    perf("government_award", RP.NEEDS_GOVERNMENT_BUYER, 0.172, 64),
]


def test_one_family_scores_differently_per_question():
    """Case studies: 0.500 for a named customer, 0.136 for a competitor,
    0.000 for an action object. One number would recommend it for all three."""
    scores = {p.question_type: p.relationship_yield
              for p in REAL if p.source_family == "customer_case_study"}
    assert scores[RP.NEEDS_CUSTOMER] > scores[RP.NEEDS_COMPETITOR]
    assert scores[RP.NEEDS_ACTION_OBJECT] == 0.0


def test_a_familys_score_for_another_question_cannot_rank_it_here():
    """Case studies hold three records. Without narrowing, whichever landed
    last in the dict ranks the family — and the last one is ACTION_OBJECT at
    0.000, which would push the best source for a named customer down."""
    got = RP.plan(RP.NEEDS_CUSTOMER, performance=REAL)
    assert "0.500" in got.reasons["customer_case_study"]
    assert "0.000" not in got.reasons["customer_case_study"]

    other = RP.plan(RP.NEEDS_GOVERNMENT_BUYER, performance=REAL)
    assert other.families == ("government_award",)
    assert "customer_case_study" in other.excluded


def test_the_action_object_question_routes_to_document_classes_that_name_buyers():
    got = RP.plan(RP.NEEDS_ACTION_OBJECT, performance=REAL)
    assert "pricing_page" in got.families
    assert "product_launch_page" in got.families
    # A rival's blog is narrative and is not offered for this question.
    assert "rival_newsroom" not in got.families


def test_every_question_type_has_at_least_one_family():
    for question in RP.QUESTION_TYPES:
        assert RP.CAN_ANSWER[question], question


def test_the_performance_key_is_family_and_question():
    assert perf("x", RP.NEEDS_CUSTOMER).key == ("x", RP.NEEDS_CUSTOMER)


# --- competitor VOI: decision relevance or nothing ------------------------

def voi(**overrides):
    kwargs = dict(
        uncertainty="whether Magento and Shopify contest the same decision",
        subject="Shopify", counterparty="Magento",
        decision_field=CV.MIGRATION_RISK,
        decision_relevance="a shared decision changes migration exposure",
        competing_explanations=("same buying decision", "adjacent workflow"),
        evidence_needed="a buyer document naming both",
        source_family="customer_case_study")
    kwargs.update(overrides)
    return CV.item(**kwargs)


def test_a_question_that_moves_no_decision_field_is_refused():
    with pytest.raises(CV.ItemRejected, match="nobody acts on"):
        voi(decision_field="ARE_THEY_PEERS")


def test_it_would_be_good_to_know_is_refused():
    with pytest.raises(CV.ItemRejected, match="refuse"):
        voi(decision_relevance="  ")


def test_a_question_with_one_answer_is_a_lookup():
    with pytest.raises(CV.ItemRejected, match="lookup"):
        voi(competing_explanations=("only one reading",))


def test_a_question_no_source_can_answer_is_unresolvable_not_queued():
    got = voi(source_family="")
    assert got.priority == CV.UNRESOLVABLE
    assert "consume budget forever" in got.reason


def test_urgent_fields_rank_high():
    assert voi(decision_field=CV.PRICING_WATCH).priority == CV.HIGH
    assert voi(decision_field=CV.DIFFERENTIATION).priority == CV.MEDIUM


def test_voi_is_generated_from_real_state_and_skips_the_settled():
    class Rel:
        actor_a, actor_b = "Magento", "Shopify"
        competitive_object = "E-commerce platform"

    class Act:
        action_id, actor, action_type = "act_1", "Salesforce", "PRODUCT_LAUNCH"

    class Settled:
        action_id, actor, action_type = "act_2", "Shopify", "PRICE_CHANGE"

    established, _ = CO.extract(
        "Shopify cut its Plus pricing for mid-market merchants.",
        action_id="act_2", actor="Shopify", source="s",
        created_at="2026-08-08")
    got = CV.from_state(
        relationships=[Rel()], actions=[Act(), Settled()],
        objects_by_action={"act_2": established},
        routing={"COMPETITOR_RELATIONSHIP": ("customer_case_study",),
                 "ACTION_OBJECT": ("product_launch_page",)})
    # One item for the relationship's scope, one for the UNestablished
    # action. The action whose object is established is not uncertain.
    assert len(got) == 2
    assert all("act_2" not in i.uncertainty for i in got)
    assert CV.summarise(got)["actionable"] >= 1


# --- founder view: hypotheses, never a motive -----------------------------

class Relationship:
    claim_id = "cmp_1"
    actor_a, actor_b = "Magento", "Shopify"
    competitive_object = "checkout infrastructure"
    buyer_or_market = "enterprise merchants"


class Action:
    action_id = "act_1"
    actor = "Shopify"
    action_type = "PRODUCT_LAUNCH"
    span = "Shopify launched Checkout Blocks for enterprise merchants."


def objectives(n=2):
    made = []
    for objective in ("expanding share in enterprise checkout",
                      "reducing churn among existing enterprise merchants",
                      "improving margin on the existing base")[:n]:
        made.append(SO.hypothesise(
            actor="Shopify", objective=objective,
            action=Action.span, affected_actor="Magento",
            alternative_objectives=("ordinary product roadmap",
                                    "partner-driven request"),
            falsifier="no further enterprise checkout work in two quarters",
            expected_next_action="further enterprise checkout releases"))
    return made


def view(**overrides):
    obj, _ = CO.extract(Action.span, action_id="act_1", actor="Shopify",
                        source="s", created_at="2026-08-08")
    kwargs = dict(relationship=Relationship(), action=Action(),
                  competitive_object=obj, interaction_id="int_1",
                  objectives=objectives())
    kwargs.update(overrides)
    return MAV.build(**kwargs)


def test_a_single_objective_would_read_as_a_motive_and_is_refused():
    with pytest.raises(MAV.ViewRejected, match="rather than a question"):
        view(objectives=objectives(1))


def test_every_required_section_is_present():
    got = view()
    assert set(MAV.REQUIRED_SECTIONS) <= set(got.sections)
    assert all(got.sections[s].strip() for s in MAV.REQUIRED_SECTIONS)


def test_the_view_says_what_it_does_not_know():
    got = view()
    unknown = got.sections["what_we_do_not_know"]
    assert "The objective" in unknown
    assert "does not discriminate" in unknown
    assert "ESTABLISHED" in unknown


def test_the_view_carries_every_alternative_it_was_given():
    got = view(objectives=objectives(3))
    assert len(got.objectives_considered) == 3


def test_motive_language_is_refused_on_the_rendered_output():
    class Motive(Action):
        span = ("Shopify launched Checkout Blocks in order to take share "
                "from Magento in enterprise merchants.")

    with pytest.raises(MAV.ViewRejected, match="motive"):
        view(action=Motive())


def test_every_section_traces_to_a_record():
    got = view()
    assert got.provenance["relationship"] == "cmp_1"
    assert got.provenance["action"] == "act_1"
    assert got.provenance["competitive_object"].startswith("obj_")


def test_with_no_expectation_the_view_says_so_rather_than_inventing_one():
    got = view()
    assert "No response has been preregistered" in \
        got.sections["what_response_we_expect"]


def test_the_rendered_view_reads_as_six_sections():
    text = view().render()
    for name in MAV.REQUIRED_SECTIONS:
        assert name.replace("_", " ").upper() in text


# --- decision impact: a mention is not a risk update ---------------------

def test_an_unestablished_object_moves_monitoring_and_nothing_else():
    got = MAV.decision_impact(view(), object_standing="PARTIAL")
    assert got["changed"] == ["monitoring"]
    assert "competitive_risk" in got["unchanged"]
    assert "cannot say the action touches" in got["reason"]


def test_an_established_object_moves_risk_but_never_pricing():
    got = MAV.decision_impact(view(), object_standing="ESTABLISHED")
    assert "competitive_risk" in got["changed"]
    # Asserting only that it appears in `unchanged` would pass while it ALSO
    # appeared in `changed`; the field must be absent from `changed`.
    assert "pricing_watch" not in got["changed"]
    assert "pricing_watch" in got["unchanged"]
    assert "until a pricing action is observed" in got["reason"]


def test_the_impact_fields_are_closed():
    got = MAV.decision_impact(view(), object_standing="ESTABLISHED")
    assert set(got["changed"]) | set(got["unchanged"]) == set(
        MAV.IMPACT_FIELDS)
