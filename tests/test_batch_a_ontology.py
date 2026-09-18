"""Batch A: the classes the gauntlet's first cohort proved were missing.

Two of the eight were classified in a way that CONTRADICTED how the company
earns — not coarsely, wrongly:

    Walmart -> BRANDED_CONSUMER, "where the brand carries pricing power the
               product alone would not command". Walmart's entire model is
               that price is LOW; the rent is in turns and sourcing power.

    Amazon  -> BRANDED_CONSUMER, from SIC 5961 (catalog and mail-order). Its
               profit is a marketplace take rate, a cloud utility and an ad
               auction, and the segment carrying the earnings is not the one
               the SIC code names.

The other six were coarse but defensible and were deliberately NOT changed:
a class is added only when a real company demonstrates the need.
"""
from __future__ import annotations

import pytest

from intent_engine.executive.company_profile import (
    _ECONOMICS, classify_sic, multi_engine_hint, profile_for,
    revenue_model_hint,
)

_SIC_RETAIL = {"sic": "5331", "sic_description": "Retail-Variety Stores"}
_SIC_SOFTWARE = {"sic": "7370", "sic_description": "Services-Computer "
                                                   "Programming"}


# ===========================================================================
# a retailer is not a brand
# ===========================================================================
@pytest.mark.parametrize("code", ["5331", "5961", "5411", "5200", "5731",
                                  "5812", "5912"])
def test_a_retail_sic_code_classifies_as_retail(code):
    """SIC 52-59 ARE the retail major groups. BRANDED_CONSUMER belongs to
    the manufacturers of branded goods, which are SIC 20-39.

    Four-digit codes only: a bare major group is treated as residual by
    `classify_sic`, and a registrant is always filed under a full code.
    """
    model, sector = classify_sic(code)
    assert model == "SCALE_RETAIL", (code, model)
    assert sector == "RETAIL"


def test_scale_retail_economics_are_not_brand_premium_economics():
    retail = _ECONOMICS["SCALE_RETAIL"]
    brand = _ECONOMICS["BRANDED_CONSUMER"]
    assert retail["business_model"] != brand["business_model"]
    # The distinguishing facts, in the class's own words.
    assert "thin margin" in retail["business_model"]
    assert "inventory turns" in retail["business_model"]
    # The brand class earns on pricing power; this one explicitly does not.
    assert "pricing power" in brand["business_model"]
    assert "pricing power" not in retail["business_model"]
    assert retail["pricing_model"] != brand["pricing_model"]


def test_walmart_is_not_described_as_a_brand_premium_business():
    """The manifest itself carried the wrong class for the world's largest
    discounter, so fixing the SIC map alone would not have reached it."""
    profile = profile_for(name="Walmart Inc.", domain="walmart.com")
    assert profile.business_model_class == "SCALE_RETAIL"


# ===========================================================================
# several businesses under one owner
# ===========================================================================
def test_a_filer_reporting_a_cloud_and_a_commerce_segment_is_multi_engine():
    text = ("Our reportable segments are North America, International and "
            "Amazon Web Services. Net sales from online stores and "
            "third-party seller services are presented below.")
    assert multi_engine_hint(text) == "MULTI_ENGINE_PLATFORM"


def test_a_product_called_marketplace_does_not_make_a_company_multi_engine():
    """MEASURED while building this: matching the word "marketplace" made
    META multi-engine, because Facebook Marketplace is a product name."""
    text = ("Our reportable segments are Family of Apps and Reality Labs. "
            "Marketplace lets people buy and sell items locally. We use "
            "cloud computing services from third parties.")
    assert multi_engine_hint(text) is None


def test_segment_language_is_required():
    text = ("Amazon Web Services is great. We run online stores.")
    assert multi_engine_hint(text) is None


def test_multi_engine_economics_refuse_a_single_margin_story():
    econ = _ECONOMICS["MULTI_ENGINE_PLATFORM"]
    assert "carries the profit" in econ["business_model"]
    assert econ["macro"] and econ["revenue_drivers"]


# ===========================================================================
# advertising dominance, not advertising presence
# ===========================================================================
def test_a_dominance_claim_is_required_to_read_as_an_advertising_platform():
    """MEASURED: a looser rule reclassified MICROSOFT, whose filing reports
    "search and news advertising revenue" as one line among many."""
    assert revenue_model_hint(
        "We generate substantially all of our revenue from selling "
        "advertising placements.") == "ADVERTISING_PLATFORM"
    assert revenue_model_hint(
        "Search and news advertising revenue increased $1.2 billion.") is None
    assert revenue_model_hint(
        "Advertising expense was $412 million for the year.") is None


def test_an_advertising_platform_and_a_retailer_do_not_share_economics():
    ads = _ECONOMICS["ADVERTISING_PLATFORM"]
    retail = _ECONOMICS["SCALE_RETAIL"]
    assert ads["pricing_model"] != retail["pricing_model"]
    assert ads["demand_model"] != retail["demand_model"]
    assert set(ads["revenue_drivers"]) != set(retail["revenue_drivers"])


# ===========================================================================
# the classes Batch A did NOT prove were needed
# ===========================================================================
def test_the_coarse_but_defensible_classes_were_left_alone():
    """§6: do not add a class unless a real company demonstrates the need.

    Caterpillar's assigned class describes its economics well, and Batch A
    produced no company those five classes actively mis-describe. Splitting
    BANK out of BALANCE_SHEET_OR_NETWORK needs Visa or Mastercard beside
    JPMorgan to show the merge costs something -- that is Batch C.
    """
    for retained in ("MANUFACTURE_AND_AFTERMARKET", "COMMODITY_PRODUCER",
                     "REGULATED_PRODUCT_OR_PROVIDER", "DESIGN_AND_MANUFACTURE",
                     "BALANCE_SHEET_OR_NETWORK"):
        assert retained in _ECONOMICS
