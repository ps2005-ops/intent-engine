"""A question that commissions a conclusion will be answered with one."""
from __future__ import annotations

import pytest

from intent_engine.market import research_priorities as RP


def make(**kw):
    base = dict(subject="Salesforce", missing_fact=RP.NEED_BUYER,
                detail="Commerce Cloud enterprise launch",
                why_it_matters="the rivalry's object is unestablished")
    base.update(kw)
    return RP.priority(**base)


# --- neutrality ------------------------------------------------------------

def test_the_question_asks_for_an_observation_not_a_conclusion():
    got = make()
    assert got.question.startswith("Retrieve the buyer segment")
    for banned in ("prove", "find evidence that", "confirm that",
                   "show that", "competes"):
        assert banned not in got.question.lower()


def test_a_leading_rationale_is_refused():
    with pytest.raises(RP.PriorityRejected, match="commissions a conclusion"):
        make(why_it_matters="find evidence that Salesforce competes with Shopify")


def test_every_missing_fact_has_a_neutral_template():
    for fact in RP.MISSING_FACTS:
        got = make(missing_fact=fact)
        assert got.question.startswith("Retrieve")
        assert not RP._LEADING.search(got.question)


# --- routing by missing fact ----------------------------------------------

def test_a_date_question_does_not_go_to_a_pricing_page():
    got = make(missing_fact=RP.NEED_DATE)
    assert "newsroom" in got.eligible_source_families
    assert "pricing_page" not in got.eligible_source_families


def test_a_buyer_question_does_not_go_to_release_notes():
    """A release note cannot say who a product is for, however well the
    family has performed."""
    got = make(missing_fact=RP.NEED_BUYER)
    assert "pricing_page" in got.eligible_source_families
    assert "release_notes" not in got.eligible_source_families


def test_a_substitute_question_routes_to_migration_sources():
    got = make(missing_fact=RP.NEED_SUBSTITUTE)
    assert got.eligible_source_families[0] in (
        "migration_page", "comparison_page", "customer_migration_story")


def test_measured_performance_orders_but_never_admits():
    """Performance reorders the eligible families and cannot add one that
    the question does not need."""
    got = RP.route(RP.NEED_BUYER, performance={"solution_page": 0.9,
                                               "pricing_page": 0.1,
                                               "release_notes": 5.0})
    assert got[0] == "solution_page"
    assert "release_notes" not in got


def test_an_untried_family_is_not_sunk_below_a_measured_zero():
    got = RP.route(RP.NEED_BUYER, performance={"pricing_page": 0.0})
    assert got.index("solution_page") < got.index("pricing_page")


# --- ranking and refusal ---------------------------------------------------

def test_value_orders_the_queue():
    low, high = make(voi=0.1), make(subject="Adobe", voi=0.9)
    assert RP.rank([low, high])[0].subject == "Adobe"


def test_a_priority_with_no_subject_matter_is_refused():
    with pytest.raises(RP.PriorityRejected, match="asks nothing"):
        make(detail="   ")


def test_an_unknown_missing_fact_is_refused():
    with pytest.raises(RP.PriorityRejected, match="not a missing fact"):
        make(missing_fact="NEED_VIBES")


def test_the_summary_reports_which_facts_are_missing():
    got = RP.summarise([make(missing_fact=RP.NEED_DATE),
                        make(missing_fact=RP.NEED_BUYER)])
    assert got["priorities"] == 2
    assert set(got["by_missing_fact"]) == {RP.NEED_DATE, RP.NEED_BUYER}
