"""An accounting policy is not a business model.

MEASURED LIVE on 517180e6. Microsoft's economic engine rendered as

    "... and we provide solution support and consulting services; revenue
     upon transfer of control of promised products or services to customers
     in an amount that reflects the consideration we expect to receive in
     exchange for those products or services"

which is the ASC 606 revenue-recognition policy shown to a chief executive as
what Microsoft sells.

This is the THIRD arrival of one defect: a filing states many things in the
grammar of a product sentence, and the grammar does not say what the sentence
is about. Staff offers were first, hypotheticals second.
"""
from __future__ import annotations

import pytest

from intent_engine.executive import economic_architecture as EA


# --- the real sentence that shipped -----------------------------------------
MICROSOFT_LIVE = (
    "revenue upon transfer of control of promised products or services to "
    "customers in an amount that reflects the consideration we expect to "
    "receive in exchange for those products or services")

BOILERPLATE = [
    pytest.param(MICROSOFT_LIVE, id="microsoft-live-defect"),
    pytest.param("We recognize revenue when a performance obligation is "
                 "satisfied by transferring a promised good to a customer",
                 id="performance-obligation"),
    pytest.param("Revenue is recognized net of allowances for returns and "
                 "any taxes collected from customers", id="revenue-is-recognized"),
    pytest.param("We allocate the transaction price to each performance "
                 "obligation based on its standalone selling price",
                 id="standalone-selling-price"),
    pytest.param("Our consolidated financial statements are prepared in "
                 "accordance with generally accepted accounting principles",
                 id="gaap-basis-of-preparation"),
]

# --- sentences that DO describe the business and must survive ---------------
REAL_PRODUCT = [
    pytest.param("We offer cloud-based solutions that provide customers with "
                 "software, services and platforms", id="cloud-products"),
    pytest.param("We sell subscriptions to our productivity suite to "
                 "commercial and consumer customers", id="subscriptions"),
    pytest.param("We provide solution support and consulting services",
                 id="services"),
    pytest.param("We design, manufacture and sell devices, including PCs, "
                 "tablets, gaming consoles and related accessories",
                 id="hardware"),
    pytest.param("We generate revenue from advertising on our platforms",
                 id="advertising"),
    # An insurer really does sell benefits. A stoplist wide enough to catch
    # accounting language must not refuse this.
    pytest.param("We sell health benefits and related services to employers "
                 "and members", id="insurer-sells-benefits"),
]


@pytest.mark.parametrize("clause", BOILERPLATE)
def test_accounting_language_is_not_a_business_model(clause):
    assert EA._is_accounting_policy(clause), (
        f"accounting boilerplate accepted as a product description: {clause[:70]!r}")
    assert EA._is_not_a_product(clause)


@pytest.mark.parametrize("clause", REAL_PRODUCT)
def test_a_real_product_sentence_still_qualifies(clause):
    """POSITIVE CONTROL.

    Without this the veto could pass by refusing everything, which would
    replace a wrong business model with no business model at all -- and
    `_business_model_of` treats empty as a real answer, so the failure would
    be silent.
    """
    assert not EA._is_accounting_policy(clause), (
        f"a genuine product sentence was vetoed as accounting: {clause[:70]!r}")
    assert not EA._is_not_a_product(clause)


def test_the_veto_does_not_lean_on_words_every_product_sentence_uses():
    """`revenue` and `customers` appear in real descriptions and must not be
    what disqualifies a clause -- that is how a stoplist starts refusing real
    companies."""
    for word in ("revenue", "customers", "services", "products", "benefits"):
        assert word not in EA._ACCOUNTING_POLICY, (
            f"{word!r} is a bare stoplist entry; it will refuse real "
            f"descriptions the way a 'benefits' veto would refuse an insurer")


def test_the_earlier_two_defects_stay_fixed():
    """Staff offers and hypotheticals, still vetoed (regression)."""
    assert EA._is_not_a_product(
        "We offer competitive compensation and a wide range of benefits, "
        "including many learning and development resources")
    assert EA._is_not_a_product(
        "we from time to time have had, and in the future may have, quality "
        "issues resulting from the design or manufacture of the products")
