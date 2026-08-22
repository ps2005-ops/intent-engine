"""A rivalry can be real and useless for learning how rivals respond.

The property worth holding: relationship validity and response observability
are separate judgements, and ranking on validity alone sends the next wave to
watch a company that does not publish.
"""
from __future__ import annotations

from intent_engine.market import strategic_episodes as SE


def cand(**kw):
    base = dict(actor_a="Shopify", actor_b="Salesforce",
                relationship_id="rel_1",
                competitive_object="E-commerce platform",
                relationship_standing="SUPPORTED",
                actions_a=7, actions_b=1, established_a=1, established_b=0,
                temporal_overlap=True, source_maturity="INDICATIVE")
    base.update(kw)
    return SE.score(**base)


# --- observability is not validity ----------------------------------------

def test_a_real_rivalry_with_a_silent_rival_is_not_observable():
    """Magento's rivalry with Shopify is evidenced by migration stories, and
    six official Adobe surfaces returned zero retrievable documents. The
    relationship is valid; the episode cannot be seen."""
    got = cand(actor_b="Magento", actions_b=0,
               relationship_standing="SUPPORTED")
    assert got.standing == SE.NOT_OBSERVABLE
    assert got.relationship_standing == "SUPPORTED"
    assert "could never be seen" in got.reason


def test_silence_is_symmetric():
    """A trigger with no observable counterparty and a counterparty with no
    observable trigger are one failure seen from two sides."""
    assert cand(actions_a=0).standing == SE.NOT_OBSERVABLE
    assert cand(actions_b=0).standing == SE.NOT_OBSERVABLE
    assert cand(actions_a=0, actions_b=0).response_observability == \
        "NEITHER_SIDE_PUBLISHES"


def test_both_sides_publishing_is_not_enough_without_an_object():
    """Two companies acting near each other is not a contest."""
    got = cand(established_a=0, established_b=0)
    assert got.standing == SE.LOW
    assert "acting near each other" in got.reason


def test_no_temporal_overlap_cannot_be_ordered():
    got = cand(temporal_overlap=False)
    assert got.standing == SE.MEDIUM
    assert "overlap in time" in got.reason


def test_a_provisional_source_caps_the_standing():
    """The family behind the evidence is PROVISIONAL, so the episode built on
    it cannot be HIGH however well the pair scores."""
    got = cand(source_maturity="PROVISIONAL")
    assert got.standing == SE.MEDIUM
    assert "PROVISIONAL" in got.reason


def test_everything_present_is_high():
    got = cand(source_maturity="INDICATIVE")
    assert got.standing == SE.HIGH


# --- ranking ---------------------------------------------------------------

def test_value_never_promotes_an_unobservable_pair():
    """A high-value question about a company that does not publish is still
    a question about a company that does not publish."""
    valuable_but_blind = cand(actor_b="Magento", actions_b=0, voi=0.99)
    ordinary = cand(source_maturity="INDICATIVE", voi=0.01)
    ranked = SE.rank([valuable_but_blind, ordinary])
    assert ranked[0].actor_b == "Salesforce"
    assert ranked[-1].standing == SE.NOT_OBSERVABLE


def test_value_breaks_ties_within_a_standing():
    low_value = cand(actor_a="A", source_maturity="INDICATIVE", voi=0.1)
    high_value = cand(actor_a="B", source_maturity="INDICATIVE", voi=0.9)
    assert SE.rank([low_value, high_value])[0].actor_a == "B"


def test_the_summary_names_the_best_learnable_pair():
    got = SE.summarise([
        cand(actor_b="Magento", actions_b=0),
        cand(source_maturity="INDICATIVE"),
    ])
    assert got["candidates"] == 2
    assert got["by_standing"][SE.NOT_OBSERVABLE] == 1
    assert got["best_learnable"]["actor_b"] == "Salesforce"


def test_a_candidate_carries_why_it_scored_that_way():
    got = cand(actor_b="Magento", actions_b=0)
    assert got.provenance
    assert any("observability" in p for p in got.provenance)
    assert got.as_dict()["response_observability"] == "ONE_SIDE_SILENT"


def test_no_learnable_pair_is_reported_as_none_not_as_a_guess():
    got = SE.summarise([cand(actions_a=0, actions_b=0)])
    assert got["best_learnable"] is None
