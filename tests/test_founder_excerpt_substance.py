"""Excerpt ranking — the Shopify meta-description defect, fixed at the producer.

Shopify opened with "Learn about Shopify and how it works. Explore its pricing
plans and essential features for building and managing your business." That is
the page's SEO meta description. It names Shopify, so the identity gate passed
it CORRECTLY — it is Shopify writing about Shopify. It is copy about a PAGE
rather than about a business, and `_pick` took the first qualifying
observation with no way to prefer the one that says what the company does.
"""
import pytest
from intent_engine.founder_brief import build as B

SHOPIFY_META = ("Learn about Shopify and how it works. Explore its pricing "
                "plans and essential features for building and managing your "
                "business.")
BRIGHTLEDGER_BODY = ("Connectors read payout files from payment processors, "
                     "match them to ledger entries, and raise an exception "
                     "when a difference persists.")


def test_the_exact_shopify_opening_ranks_below_body_prose():
    assert B._excerpt_substance(BRIGHTLEDGER_BODY) > \
        B._excerpt_substance(SHOPIFY_META)


@pytest.mark.parametrize("meta", [
    "Learn about the platform and how it works.",
    "Discover everything you need to know about our pricing plans.",
    "Explore essential features for building your business.",
    "Get started with a free trial, no credit card required.",
])
def test_page_copy_is_demoted(meta):
    assert B._excerpt_substance(meta) < 0


@pytest.mark.parametrize("body", [
    BRIGHTLEDGER_BODY,
    "Stripe processes payments and settles funds to merchant accounts daily.",
    "The company manufactures and distributes industrial gases to 80 markets.",
])
def test_mechanism_bearing_prose_is_promoted(body):
    assert B._excerpt_substance(body) > 0


def test_second_person_marks_marketing_address():
    """A description is about the company; "your business" is about the
    reader."""
    assert B._excerpt_substance("We reconcile payouts for your business") < \
        B._excerpt_substance("We reconcile payouts for finance teams")


def test_ranking_is_ordinal_and_only_ever_reorders():
    """It cannot admit an excerpt the identity gate rejected — it runs after
    that gate and only sorts what survived it."""
    assert B._excerpt_substance("") == 0
