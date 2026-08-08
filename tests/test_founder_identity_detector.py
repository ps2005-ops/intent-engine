"""Self-description identity — recovery without reopening the leak.

Two failures are in tension here and both are measured, not hypothetical:

  the LEAK      Stripe's page opened with "Figma democratizes design through
                its collaborative design products." — a customer story hosted
                on stripe.com, about somebody else.

  the COST      Brightledger's best sentence, "Connectors read payout files
                from payment processors, match them to ledger entries...",
                was rejected because it neither says "we" nor "Brightledger",
                and the page fell back to something duller.

A change that fixes one by reopening the other is not an improvement, so the
leak cases and the recovery cases are asserted in the same file, against the
same classifier.
"""
import pytest

from intent_engine.founder_brief import identity as ID


BRIGHTLEDGER_DOCS = [
    {"origin": "https://brightledger.example/docs/connectors",
     "source_title": "Connectors and matches | Brightledger docs"},
    {"origin": "https://brightledger.example/product/reconciliation",
     "source_title": "Reconciliation | Brightledger"},
]

STRIPE_PAGES = [
    {"origin": "https://stripe.com/customers/figma",
     "source_title": "Figma Completes Rollout of New Billing Model | Stripe"},
    {"origin": "https://stripe.com/payments",
     "source_title": "Payments | Stripe"},
]


# ===========================================================================
# THE LEAK MUST STAY CLOSED
# ===========================================================================
def test_customer_story_is_never_the_focal_company_description():
    """The exact passage that leaked, on the exact page that carried it."""
    result = ID.classify(
        "Figma democratizes design through its collaborative design products.",
        company="Stripe",
        origin="https://stripe.com/customers/figma",
        title="Figma Completes Rollout of New Billing Model | Stripe",
        source_class="company_owned",
        vocabulary=ID.owned_vocabulary(STRIPE_PAGES, company="Stripe"))
    assert result.state == ID.NOT_SELF
    assert result.usable is False


def test_a_customer_story_never_enters_the_owned_vocabulary():
    """Otherwise /customers/figma teaches the engine that Figma is Stripe's.

    This is the subtle way the leak would come back: not through the
    classifier, but through the lexicon it consults.
    """
    vocabulary = ID.owned_vocabulary(STRIPE_PAGES, company="Stripe")
    assert "figma" not in vocabulary
    assert "payments" in vocabulary


def test_first_party_host_alone_never_proves_self_description():
    """The assumption that shipped Figma's description under Stripe's name."""
    result = ID.classify(
        "Acme Corp reduced onboarding time by ninety percent last quarter.",
        company="Stripe", origin="https://stripe.com/blog/some-post",
        title="A post | Stripe", source_class="company_owned")
    assert result.state == ID.UNKNOWN
    assert result.usable is False


def test_we_inside_a_customer_story_is_the_customers_voice():
    """The single most dangerous string in this problem.

    Rejections are checked before positive signals precisely so that a
    customer saying "we cut our costs" on a vendor's case-study page cannot
    be read as the vendor describing itself.
    """
    result = ID.classify(
        "We cut our reconciliation costs by half after switching.",
        company="Stripe", origin="https://stripe.com/customers/acme",
        title="Acme case study | Stripe", source_class="company_owned")
    assert result.state == ID.NOT_SELF


@pytest.mark.parametrize("path,title", [
    ("/partners/acme", "Acme partner story | Vendor"),
    ("/integrations/slack", "Slack integration | Vendor"),
    ("/compare/vendor-vs-acme", "Vendor vs Acme | Vendor"),
    ("/legal/terms", "Terms of Service | Vendor"),
    ("/marketplace/listing", "Listing | Vendor"),
])
def test_third_party_and_boilerplate_page_classes_are_rejected(path, title):
    result = ID.classify(
        "The platform connects ledgers and reconciles entries automatically.",
        company="Vendor", origin=f"https://vendor.example{path}",
        title=title, source_class="company_owned")
    assert result.state == ID.NOT_SELF


def test_competitor_and_customer_source_classes_are_rejected_outright():
    for source_class in ("competitor", "customer_voice"):
        result = ID.classify(
            "We build the leading reconciliation platform.",
            company="Vendor", origin="https://vendor.example/about",
            title="About", source_class=source_class)
        assert result.state == ID.NOT_SELF


def test_pricing_page_is_not_a_company_description():
    """Notion, Linear and Brightledger all opened with a price list."""
    result = ID.classify(
        "Plans start at nine dollars per user per month, billed annually.",
        company="Vendor", origin="https://vendor.example/pricing",
        title="Pricing | Vendor", source_class="company_owned")
    assert result.state == ID.NOT_SELF


# ===========================================================================
# THE COST MUST BE RECOVERED
# ===========================================================================
def test_brightledger_product_sentence_is_recovered():
    """The measured cost of the strict rule, now paid back.

    The sentence names no company and says no "we". It qualifies because
    `connectors` is a section of Brightledger's own site.
    """
    vocabulary = ID.owned_vocabulary(BRIGHTLEDGER_DOCS, company="Brightledger")
    assert "connectors" in vocabulary

    result = ID.classify(
        "Connectors read payout files from payment processors, match them to "
        "ledger entries, and raise an exception when a difference persists.",
        company="Brightledger",
        origin="https://brightledger.example/docs/connectors",
        title="Connectors and matches | Brightledger docs",
        source_class="company_owned", observation_type="product_surface",
        vocabulary=vocabulary)
    assert result.state == ID.PROBABLE
    assert result.usable is True
    assert "subject_is_an_owned_product" in result.signals


def test_a_passage_naming_the_company_is_still_confirmed():
    result = ID.classify(
        "Brightledger reconciles payouts across a dozen payment processors.",
        company="Brightledger", origin="https://brightledger.example/about",
        title="About", source_class="company_owned")
    assert result.state == ID.CONFIRMED


def test_first_person_is_still_confirmed_on_an_identity_page():
    result = ID.classify(
        "We build reconciliation software for finance teams at scale.",
        company="Brightledger", origin="https://brightledger.example/about",
        title="About | Brightledger", source_class="company_owned")
    assert result.state == ID.CONFIRMED


def test_unknown_subject_on_an_identity_page_does_not_reach_probable():
    """An unowned subject proves nothing, so confidence must not rise.

    This is the Figma sentence with the customer-story path removed — the
    case where the classifier has nothing but the host, and must say so.
    """
    vocabulary = ID.owned_vocabulary(BRIGHTLEDGER_DOCS,
                                     company="Brightledger")
    result = ID.classify(
        "Figma democratizes design through its collaborative design products.",
        company="Brightledger",
        origin="https://brightledger.example/product/overview",
        title="Overview", source_class="company_owned",
        observation_type="product_surface", vocabulary=vocabulary)
    assert result.state == ID.UNKNOWN
    assert result.usable is False


# ===========================================================================
# CONTRACT
# ===========================================================================
def test_state_vocabulary_is_closed():
    cases = [
        ("", "Vendor", "", ""),
        ("We do things.", "Vendor", "https://v.example/about", "About"),
        ("Something else entirely.", "Vendor", "https://v.example/x", "X"),
    ]
    for excerpt, company, origin, title in cases:
        result = ID.classify(excerpt, company=company, origin=origin,
                             title=title, source_class="company_owned")
        assert result.state in ID.STATES


def test_usable_is_exactly_confirmed_and_probable():
    assert ID.USABLE == frozenset({ID.CONFIRMED, ID.PROBABLE})
    assert ID.NOT_SELF not in ID.USABLE
    assert ID.UNKNOWN not in ID.USABLE
