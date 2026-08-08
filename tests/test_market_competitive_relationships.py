"""Rivalry needs a competitive object. Everything else here follows.

The negative corpus is the point. Every case in it is a sentence that names
two companies and establishes no rivalry, and each one is tempting in a
different way — which is why the graph acquired three fabricated interaction
records the last time something matched on adjacency.

Precision is measured first and deliberately. Recall is reported, not chased.
"""
from __future__ import annotations

import pathlib

import pytest

from intent_engine.market import actor_relationships as AR
from intent_engine.market import competitive_relationships as CR
from intent_engine.market import learning_store as LS

REAL_LEDGER = pathlib.Path(
    "/Users/prathamsharma/intent-engine-market/reports/market/"
    "learning_ledger.jsonl")

SHOPIFY = dict(subject="shopify", aliases=["Shopify", "Shopify Inc."],
               source="https://www.shopify.com/customers/x",
               event_date="2026-08-05",
               competitive_object="E-commerce platform")


def pull(text, **overrides):
    kwargs = dict(SHOPIFY)
    kwargs.update(overrides)
    return CR.extract(text, **kwargs)


# --- the contract: no object, no claim -----------------------------------

def valid(**overrides):
    kwargs = dict(actor_a="Magento", actor_b="Shopify Plus",
                  competitive_object="E-commerce platform",
                  buyer_or_market="Bombay Shaving Company",
                  evidence_type=CR.REPLACEMENT_MIGRATION,
                  evidence_span="migrated from Magento to Shopify Plus",
                  source="https://www.shopify.com/customers/x",
                  event_date="2026-08-05")
    kwargs.update(overrides)
    return CR.claim(**kwargs)


def test_a_claim_without_a_competitive_object_is_refused():
    with pytest.raises(CR.CompetitiveClaimRejected, match="competitive object"):
        valid(competitive_object="")


@pytest.mark.parametrize("vacuous", [
    "the market", "business", "technology", "products", "customers",
    "the industry", "solutions", "it"])
def test_a_vacuous_object_is_not_an_object(vacuous):
    with pytest.raises(CR.CompetitiveClaimRejected, match="names nothing"):
        valid(competitive_object=vacuous)


def test_a_claim_without_a_buyer_is_refused():
    with pytest.raises(CR.CompetitiveClaimRejected, match="choosing"):
        valid(buyer_or_market="  ")


def test_an_unnamed_end_is_refused():
    with pytest.raises(CR.CompetitiveClaimRejected, match="names no actor"):
        valid(actor_b="our competitors")


def test_an_actor_does_not_compete_with_itself():
    """Same actor, two spellings. Both must still look like actors, or the
    named-actor gate refuses first and this check goes untested."""
    with pytest.raises(CR.CompetitiveClaimRejected, match="with itself"):
        valid(actor_a="Shopify Inc.", actor_b="Shopify Inc")


def test_an_unbuilt_evidence_type_is_refused_with_what_it_would_need():
    with pytest.raises(CR.CompetitiveClaimRejected, match="losing bidders"):
        valid(evidence_type="PROCUREMENT_ALTERNATIVE")


def test_every_built_type_states_what_it_cannot_prove():
    for kind in CR.BUILT:
        proves, does_not = CR.PROVES[kind]
        assert proves and does_not


def test_the_edge_carries_its_terms_into_the_graph():
    got = valid().as_relationship()
    assert got.predicate == AR.COMPETES_WITH
    assert "competitive object: E-commerce platform" in got.relationship_span
    assert "does not prove" in got.relationship_span


# --- the positive corpus --------------------------------------------------

def test_a_named_migration_is_rivalry():
    (got,), _ = pull("Bombay Shaving Company migrated from Magento to "
                     "Shopify Plus, achieving a 150% uplift in conversion.")
    assert got.evidence_type == CR.REPLACEMENT_MIGRATION
    assert {got.actor_a, got.actor_b} == {"Magento", "Shopify Plus"}
    assert got.buyer_or_market == "Bombay Shaving Company"
    assert got.competitive_object == "E-commerce platform"


def test_a_direct_statement_is_rivalry():
    (got,), _ = pull("Shopify competes directly with BigCommerce for "
                     "mid-market merchants across every region.")
    assert got.evidence_type == CR.DIRECT_COMPETITOR_STATEMENT
    assert got.actor_b == "BigCommerce"


def test_an_evaluation_against_a_named_alternative_is_rivalry():
    (got,), _ = pull("The merchant shortlisted BigCommerce before choosing "
                     "our platform for its storefront rebuild.")
    assert got.evidence_type == CR.CUSTOMER_ALTERNATIVE_EVALUATION


# --- the negative corpus: two names, no rivalry --------------------------

NEGATIVE = [
    ("integration",
     "Shopify integrates with NetSuite for automated inventory sync."),
    ("partnership",
     "Shopify partners with Stripe to deliver merchant payments."),
    ("same customer",
     "The merchant uses Shopify and also uses Klaviyo for email."),
    ("complementary",
     "Storefronts built on Shopify are powered by Cloudflare at the edge."),
    ("analyst comparison",
     "Analysts compared Shopify with Amazon on price targets this quarter."),
    ("share price",
     "Shares of Shopify rose while Amazon stock fell after the print."),
    ("co-mention",
     "Shopify and Adyen both appeared at the commerce conference."),
    ("partner of both",
     "The agency works with Shopify and works with BigCommerce."),
    ("outperformance",
     "Shopify outperformed BigCommerce shares over the trailing year."),
]


@pytest.mark.parametrize("label,text", NEGATIVE, ids=[n for n, _ in NEGATIVE])
def test_the_negative_corpus_produces_no_rivalry(label, text):
    got, _ = pull(text)
    assert got == (), f"{label} produced {[(c.actor_a, c.actor_b) for c in got]}"


def test_a_fiscal_period_is_not_a_competitor():
    """"increased 8.9% compared to FY2026" proposed "Toyota vs FY2026"."""
    got, refused = pull(
        "Vehicle unit sales increased by 8.9% to 524 thousand units in "
        "FY2027, benchmarked against FY2026 across every region.")
    assert all(c.actor_b != "FY2026" for c in got)


def test_same_sector_alone_produces_nothing():
    got, _ = pull("Shopify and Infosys are both classified as Technology "
                  "companies in the index this quarter.")
    assert got == ()


def test_precision_on_the_shaped_corpus_is_total():
    """Recall is reported; precision is the thing that is not traded away."""
    true_positives = 0
    for text in ("Bombay Shaving Company migrated from Magento to Shopify "
                 "Plus for its storefront.",
                 "Shopify competes directly with BigCommerce for mid-market "
                 "merchants across regions.",
                 "The merchant shortlisted BigCommerce before choosing our "
                 "platform for the rebuild."):
        true_positives += len(pull(text)[0])
    false_positives = sum(len(pull(text)[0]) for _, text in NEGATIVE)
    assert false_positives == 0
    assert true_positives == 3
    precision = true_positives / (true_positives + false_positives)
    assert precision == 1.0


# --- model knowledge is refused, and used only as a scoreboard -----------

def test_the_curated_competitor_list_is_never_a_source():
    """The universe hand-carries `competitors`. It is model knowledge.

    "Everyone knows Shopify competes with Amazon" is exactly the claim this
    module exists to refuse, so the curated list must not appear in any
    extraction path.
    """
    import inspect

    # Behaviour, not grep: the module may DISCUSS the curated list in its
    # docstring, and must never read it. Nothing in the extraction path
    # imports the universe at all.
    source = inspect.getsource(CR)
    assert "universe" not in source
    assert "peer_group" not in source
    assert ".competitors" not in source


def test_the_corpus_found_a_rival_the_curated_list_does_not_have():
    """The measurement that shows why the curated list is not evidence."""
    from intent_engine.universe.companies import default_universe

    shopify = next(c for c in default_universe().prediction_companies()
                   if c.company_id == "shopify")
    curated = {str(x).lower() for x in (shopify.competitors or ())}
    (got,), _ = pull("Bombay Shaving Company migrated from Magento to "
                     "Shopify Plus for its storefront rebuild.")
    assert "magento" not in curated
    assert got.actor_a == "Magento"


# --- against the real ledger ---------------------------------------------

def test_the_real_ledger_yields_one_fully_specified_claim():
    if not REAL_LEDGER.exists():                       # pragma: no cover
        return
    from intent_engine.market.steps import _aliases_for
    from intent_engine.universe.companies import default_universe

    comps = {c.company_id: c for c in
             default_universe().prediction_companies()}
    store = LS.LearningStore(REAL_LEDGER)
    seen = {}
    for row in store.evidence():
        company = comps.get((row.subject_company or "").strip().lower())
        if not company:
            continue
        got, _ = CR.extract(row.fact, subject=company.company_id,
                            aliases=_aliases_for(company), source=row.source,
                            event_date=row.observed_at[:10],
                            competitive_object=str(company.industry or ""))
        for claim in got:
            seen.setdefault(claim.claim_id, claim)
    assert len(seen) == 1
    only = next(iter(seen.values()))
    assert {only.actor_a, only.actor_b} == {"Magento", "Shopify Plus"}
    assert only.buyer_or_market == "Bombay Shaving Company"
    assert only.competitive_object == "E-commerce platform"
