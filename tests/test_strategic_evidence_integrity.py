"""Regression cases for the evidence layer feeding strategic reasoning.

Each case here was a real defect observed on the live service against Sony
Interactive Entertainment, where a console/games business was told it was
"turning a people-delivered service into a repeatable product" and had "SMB"
named as an affected function.

The defects were all in signal DETECTION, not in the reasoning thresholds:
the detectors manufactured the signals the thresholds then counted.
"""
from intent_engine.strategic_intelligence.observations import (
    derive_observations, _detect_signals, in_commerce_domain,
)


def _doc(sid, title, text, url="https://example.com/x", **kw):
    d = dict(source_id=sid, title=title, final_url=url, meta_description="",
             text_content=text, retrieved_at="2026-07-20T00:00:00Z",
             freshness="CURRENT")
    d.update(kw)
    return d


# --- 1. substring matching -------------------------------------------------
# "capital" and "rapid" both contain the substring "api". Any company that
# discusses capital allocation was reported as exposing a developer surface.

def test_capital_allocation_is_not_a_developer_surface():
    text = ("Our capital allocation supports long-term investment and the "
            "rapid growth of our network.")
    assert "developer_surface" not in _detect_signals(text)


def test_real_developer_surface_still_detected():
    text = ("Full REST API reference, SDK downloads and webhooks for "
            "integrating with our platform.")
    assert "developer_surface" in _detect_signals(text)


# --- 2. bare generic words as signals --------------------------------------
# A single ordinary adjective must not carry a strategic claim.

def test_unified_alone_is_not_consolidation():
    text = "A unified PlayStation experience across console and cloud."
    assert "consolidation" not in _detect_signals(text)


def test_explicit_consolidation_still_detected():
    text = ("Replace several separate tools with one workspace where all of "
            "your team's work lives in one place.")
    assert "consolidation" in _detect_signals(text)


# --- 3. the commerce domain gate opens on ordinary retail words ------------
# A games storefront says cart/checkout/buyer. That is retail vocabulary, not
# evidence that the company sells commerce infrastructure to merchants.

def test_consumer_storefront_does_not_trigger_smb_merchant_signals():
    text = ("Browse the PlayStation Store. Add to cart and checkout securely. "
            "Every buyer can find games and add-ons. Shopping is simple and "
            "easy to do from your console.")
    signals = _detect_signals(text)
    assert "smb_simplicity" not in signals, (
        "consumer retail language must not imply a small-merchant strategy")


def test_merchant_platform_still_detected():
    text = ("Shopify Plus gives large merchants commerce infrastructure. "
            "Enterprise merchants use commerce components to power commerce "
            "for their storefronts and checkout.")
    assert in_commerce_domain(text)
    assert "enterprise_expansion" in _detect_signals(text)


# --- 3b. who is speaking changes what a claim is worth ---------------------

_SIMPLICITY = ("Independent merchant reviews repeatedly praise fast setup and "
               "simple day-to-day operation, citing that simplicity as the "
               "top reason they choose to remain customers.")


def test_company_calling_itself_simple_is_not_evidence():
    assert "smb_simplicity" not in _detect_signals(_SIMPLICITY, "company_owned")


def test_customers_calling_it_simple_is_evidence():
    assert "smb_simplicity" in _detect_signals(_SIMPLICITY, "customer_voice")


# --- 4. page type ----------------------------------------------------------
# A careers page listing job families ("professional services", "solutions
# engineering") was the qualifying evidence for a services-to-product thesis.

def test_careers_page_is_not_strategic_evidence():
    docs = [_doc("c1", "Careers at PlayStation",
                 "We hire across engineering, solutions engineering and "
                 "professional services. Our implementation team works on "
                 "site with partners.",
                 url="https://www.playstation.com/en-us/careers/")]
    obs = derive_observations(docs)
    assert obs == [], "a careers page must not become a strategic observation"


def test_legal_page_is_not_strategic_evidence():
    docs = [_doc("l1", "Terms of Service",
                 "These terms of service govern your use of the service. "
                 "Your privacy policy rights are described below in detail "
                 "along with the applicable limitations of liability.",
                 url="https://example.com/legal/terms")]
    assert derive_observations(docs) == []


def test_product_page_is_still_strategic_evidence():
    docs = [_doc("p1", "Shopify Plus",
                 "Shopify Plus gives large merchants commerce infrastructure "
                 "and enterprise commerce components to power commerce at "
                 "scale for their storefronts.",
                 url="https://www.shopify.com/plus")]
    assert len(derive_observations(docs)) == 1


# --- 5. weak evidence must not qualify a hypothesis ------------------------

def test_weak_observations_are_excluded_from_qualifying_signals():
    """A weak observation may provide context but must not be the reason a
    strategic hypothesis fires."""
    from intent_engine.strategic_intelligence.observations import (
        qualifying_signals_of,
    )
    docs = [_doc("w1", "Get Started",
                 "Sign up and get started with a free trial. Learn more or "
                 "contact sales to book a demo of the unified workspace.",
                 url="https://example.com/signup")]
    obs = derive_observations(docs)
    for o in obs:
        if o.weak:
            assert qualifying_signals_of(o) == set()


# --- 6. end-to-end: the Sony failure ---------------------------------------

SONY_DOCS = [
    _doc("d1", "Sony Interactive Entertainment - Who We Are",
         "Sony Interactive Entertainment is responsible for the PlayStation "
         "brand. We are a unified organisation spanning hardware, network "
         "services and worldwide studios. Our capital allocation supports "
         "long-term investment in first-party content and the rapid growth "
         "of our network.",
         url="https://sonyinteractive.com/en/our-company/"),
    _doc("d2", "PlayStation Plus Membership Tiers",
         "PlayStation Plus has three membership tiers: Essential, Extra and "
         "Premium. Plans start at a monthly price per month. Members get "
         "online multiplayer, a catalogue of titles and cloud streaming. It "
         "is simple and easy to get started.",
         url="https://www.playstation.com/en-us/ps-plus/"),
    _doc("d3", "PlayStation Store",
         "Browse the PlayStation Store. Add to cart and checkout securely. "
         "Every buyer can find games, add-ons and season passes. Shopping is "
         "simple and easy to do from your console or the web.",
         url="https://store.playstation.com/"),
    _doc("d5", "Careers at PlayStation",
         "We hire across engineering, solutions engineering and professional "
         "services. Our implementation team works on site with partners.",
         url="https://www.playstation.com/en-us/careers/"),
]


COMMERCE_DOCS = [
    _doc("m1", "Commerce Platform",
         "Our commerce platform gives merchants commerce infrastructure. "
         "Sellers use our storefront tools and point of sale to sell online "
         "across every channel, with checkout and payment rails built in.",
         url="https://example.com/platform"),
    _doc("m2", "Plus for Large Merchants",
         "Enterprise merchants and large merchants move upmarket with "
         "commerce components. Our merchants get an enterprise tier with "
         "commerce infrastructure for their storefronts and checkout.",
         url="https://example.com/plus"),
    _doc("m3", "App Marketplace for Merchants",
         "Our app store and partner ecosystem let app developers extend what "
         "merchants and sellers can do. Third-party apps plug into the "
         "commerce platform and its storefront and checkout surfaces.",
         url="https://example.com/apps"),
]


# --- 7. the analyst gets evidence the pattern library would discard --------

_ANALYST_DOC = _doc(
    "i1", "Industry analysis: console economics",
    "Analysts note PlayStation hardware has historically been sold near or "
    "below cost early in a cycle, with margin recovered through software "
    "attach and subscriptions. Microsoft has placed first-party titles into "
    "Game Pass on release day; Sony has largely declined to do so.",
    url="https://analyst.test/console-economics",
    source_class="independent_reporting")


def test_independent_analysis_is_dropped_by_signal_matching():
    """Documents the gap this exists to close: the single most valuable
    source in a run matches no controlled-vocabulary signal."""
    assert derive_observations([_ANALYST_DOC]) == []


def test_analyst_evidence_keeps_it():
    from intent_engine.strategic_intelligence.observations import (
        derive_analyst_evidence,
    )
    ev = derive_analyst_evidence([_ANALYST_DOC])
    assert len(ev) == 1
    assert ev[0].source_class == "independent_reporting"
    assert "Game Pass" in ev[0].excerpt


def test_analyst_evidence_still_excludes_careers_and_thin_pages():
    from intent_engine.strategic_intelligence.observations import (
        derive_analyst_evidence,
    )
    careers = _doc("c9", "Careers", "We are hiring across many teams and "
                   "functions in every region where we operate today.",
                   url="https://example.com/careers/")
    thin = _doc("t9", "Home", "Welcome.", url="https://example.com/")
    assert derive_analyst_evidence([careers, thin]) == []


def test_sony_produces_no_services_to_product_hypothesis():
    from intent_engine.strategic_intelligence.reasoning import (
        build_strategic_report,
    )
    obs = derive_observations(SONY_DOCS)
    report = build_strategic_report(
        company_name="Sony Interactive Entertainment", observations=obs)
    titles = " ".join(h.title for h in report.hypotheses).lower()
    assert "people-delivered service" not in titles
    assert "repeatable product" not in titles


def test_sony_never_names_smb_as_an_affected_function():
    from intent_engine.strategic_intelligence.reasoning import (
        build_strategic_report,
    )
    obs = derive_observations(SONY_DOCS)
    report = build_strategic_report(
        company_name="Sony Interactive Entertainment", observations=obs)
    for item in (getattr(report, "agenda", None) or []):
        assert "SMB" not in " ".join(item.get("affected_functions") or [])


def test_agenda_items_carry_the_field_the_renderer_reads():
    """render.py reads `inferred_discussion` (and only that) for the agenda
    heading, so an item missing it renders as an empty block.

    Built from a document set that DOES produce hypotheses, so the loop below
    is never vacuous -- the Sony set deliberately produces none.
    """
    from intent_engine.strategic_intelligence.reasoning import (
        build_strategic_report,
    )
    obs = derive_observations(COMMERCE_DOCS)
    report = build_strategic_report(company_name="Examplecorp",
                                    observations=obs)
    agenda = getattr(report, "agenda", None) or []
    assert agenda, "fixture must produce agenda items for this test to bite"
    for item in agenda:
        assert item.get("inferred_discussion"), \
            f"agenda item the renderer cannot title: {item!r}"
