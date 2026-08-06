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


# --- a threshold counts evidence; it cannot say what the reading is about ----
#
# The defect above was fixed in DETECTION, and this is the same claim arriving
# through the other door. `services_to_product` qualifies on any two of
# ("services_motion", "multi_product", "developer_surface"), so a company with
# an API page and a products page — every software company — met the threshold
# without a single observation about delivering work alongside customers, and
# was told it "converts what it learned delivering work alongside customers
# into products those customers can run themselves".
#
# Measured on the deployed preview at acf4357 across a twenty-company matrix:
# five of the seven full results (Datadog, MongoDB, Cloudflare, HubSpot, Visa)
# returned that IDENTICAL sentence as "The answer" — the one line a founder
# reads first. None had retrieved a services signal.

def _sig_obs(oid, signal, text, excerpt):
    from intent_engine.strategic_intelligence.records import (
        StrategicObservation,
    )
    return StrategicObservation(
        observation_id=oid, text=text, observation_type="messaging",
        source_refs=[{"artifact_id": f"src-{oid}"}], signals=(signal,),
        source_class="company_owned", excerpt=excerpt,
        source_title=f"src {oid}", origin=f"https://acme.example/{oid}",
        date="2026-08-06")


_API = ("o1", "developer_surface", "Acme exposes a surface others can build on.",
        "Build on our API: REST and GraphQL documentation for developers.")
_PRODUCTS = ("o2", "multi_product",
             "Acme sells several distinct products rather than one.",
             "Explore the suite: Compute, Storage, Analytics and Security.")
_SERVICES = ("o3", "services_motion",
             "Acme embeds engineers alongside its customers.",
             "Our implementation team works on-site alongside yours.")
# The TRANSFER, which is a different claim from having services at all.
_TRANSFER = ("o4", "productization",
             "Acme turns delivered work into something sold on its own.",
             "We productized what we learned delivering those engagements "
             "into a repeatable product.")
_PRICING = ("o5", "pricing_published", "Acme publishes its prices.",
            "Pricing starts at a low monthly price per seat, free plan "
            "available.")
_CONSOLIDATION = ("o6", "consolidation",
                  "Acme positions itself as replacing several tools.",
                  "One unified platform, a single source of truth replacing "
                  "several separate tools.")


def _fired(*specs):
    from intent_engine.strategic_intelligence.reasoning import (
        build_strategic_report,
    )
    report = build_strategic_report(
        company_name="Acme", observations=[_sig_obs(*s) for s in specs])
    return {h.pattern_id for h in report.hypotheses}


def test_a_services_reading_needs_evidence_of_a_service():
    assert "services_to_product" not in _fired(_API, _PRODUCTS)


def test_the_services_reading_still_fires_when_the_transition_is_observed():
    """The gate must not be a mute button.

    Updated when the contract tightened: the engagement alone no longer
    qualifies, because almost every large vendor has one. With the engagement
    AND the transfer it describes, the pattern is exactly as available as it
    ever was — which is what stops this being a mute button rather than a gate.
    """
    assert "services_to_product" in _fired(_API, _PRODUCTS, _SERVICES,
                                           _TRANSFER)
    assert "services_to_product" in _fired(_PRODUCTS, _SERVICES, _TRANSFER)


def test_removing_it_does_not_silence_the_reading_that_did_fit():
    """An API and a product suite still support a system-of-record reading —
    the fix removes one unsupported claim, not the analysis."""
    assert _fired(_API, _PRODUCTS), "the run must still reach a reading"


def test_a_required_signal_must_be_one_the_pattern_qualifies_on():
    import pytest
    from intent_engine.strategic_intelligence.records import ComparablePattern
    bad = ComparablePattern(
        pattern_id="p", name="n", description="d", mechanism="m",
        historical_examples=[{"name": "x", "note": "y", "source": "z"}],
        when_it_applies="a", when_it_does_not_apply="b",
        qualifying_signals=("multi_product",),
        required_signals=("services_motion",))
    with pytest.raises(Exception):
        bad.validate()


# --- having services is not the same claim as the transition -----------------
#
# Requiring `services_motion` was right and was not enough: almost every large
# vendor publishes a professional-services or implementation page. Measured on
# the deployed preview, the reading still dominated MongoDB, Cloudflare,
# HubSpot and Amazon — none of which claim that engagements taught them
# something they now sell WITHOUT the engagement. That claim is the mechanism
# the pattern is named for, and it is its own signal.

def _answer(*specs):
    """The pattern that would be "The answer" — first in the portfolio."""
    from intent_engine.strategic_intelligence.reasoning import (
        build_strategic_report,
    )
    report = build_strategic_report(
        company_name="Acme", observations=[_sig_obs(*s) for s in specs])
    return report.hypotheses[0].pattern_id if report.hypotheses else None


def test_a_professional_services_page_alone_is_not_the_transition():
    """The live case: enterprise vendor with implementation services."""
    assert "services_to_product" not in _fired(_API, _PRODUCTS, _SERVICES)


def test_self_serve_saas_with_a_services_page_is_not_the_transition():
    assert "services_to_product" not in _fired(_PRODUCTS, _SERVICES, _PRICING)


def test_an_api_company_with_no_transfer_evidence_is_not_the_transition():
    assert "services_to_product" not in _fired(_API, _PRODUCTS)


def test_a_company_that_describes_the_transfer_still_gets_the_reading():
    """A genuine services-to-product company must keep it."""
    assert "services_to_product" in _fired(_API, _PRODUCTS, _SERVICES,
                                           _TRANSFER)
    assert "services_to_product" in _fired(_SERVICES, _TRANSFER)


def test_the_transfer_reading_is_the_answer_when_nothing_argues_with_it():
    assert _answer(_API, _PRODUCTS, _SERVICES, _TRANSFER,
                   _CONSOLIDATION) == "services_to_product"


def test_published_pricing_costs_the_reading_its_rank_not_only_its_wording():
    """Disconfirming evidence has to cost something a reader can see.

    Published self-serve pricing is the plainest evidence that the product is
    already sold without the engagement. The reading is not deleted — it stays
    available as a secondary hypothesis — but a reading the evidence argues
    with must not be the first line on the page when a cleaner one exists.
    """
    contested = _fired(_API, _PRODUCTS, _SERVICES, _TRANSFER, _CONSOLIDATION,
                       _PRICING)
    assert "services_to_product" in contested, "it must remain available"
    assert _answer(_API, _PRODUCTS, _SERVICES, _TRANSFER, _CONSOLIDATION,
                   _PRICING) != "services_to_product"


def test_blocking_is_declared_per_pattern_never_applied_globally():
    """A blanket penalty on counter-evidence was tried first, and was wrong.

    Sorting contested readings down globally broke the property the product
    deliberately has — `test_flagship_hypothesis_has_real_counter_evidence`:
    the lead reading is SUPPOSED to carry counter-evidence, because one nobody
    has argued with is one nobody has tested. Nine tests failed, and they were
    right to.

    So blocking is a per-pattern declaration, and a pattern may only be blocked
    by a signal it already declares as arguing against it.
    """
    import pytest
    from intent_engine.strategic_intelligence.patterns import PATTERN_LIBRARY
    from intent_engine.strategic_intelligence.records import ComparablePattern

    declared = [p for p in PATTERN_LIBRARY if p.blocking_signals]
    assert declared, "no pattern declares blocking signals"
    for pattern in declared:
        for signal in pattern.blocking_signals:
            assert signal in pattern.disconfirming_signals

    bad = ComparablePattern(
        pattern_id="p", name="n", description="d", mechanism="m",
        historical_examples=[{"name": "x", "note": "y", "source": "z"}],
        when_it_applies="a", when_it_does_not_apply="b",
        qualifying_signals=("multi_product",),
        disconfirming_signals=(),
        blocking_signals=("pricing_published",))
    with pytest.raises(Exception):
        bad.validate()


def test_a_blocked_reading_stays_available_as_a_secondary_hypothesis():
    """Blocking costs it first place, not its place."""
    from intent_engine.strategic_intelligence.reasoning import _demote_contested
    from intent_engine.strategic_intelligence.patterns import PATTERN_LIBRARY

    by_id = {p.pattern_id: p for p in PATTERN_LIBRARY}

    class _H:
        def __init__(self, pid):
            self.pattern_id = pid

    blocked = _H("services_to_product")
    clean = _H("tool_to_system_of_record")
    order = _demote_contested([blocked, clean], by_id, {"pricing_published"})
    assert order[0] is clean, "a blocked reading is still leading"
    assert blocked in order, "a blocked reading was dropped, not demoted"

    # with nothing arguing against it, it leads again
    unblocked = _demote_contested([blocked, clean], by_id, set())
    assert unblocked[0] is blocked
