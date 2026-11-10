"""CompanyPredictionUniverse — classification, safety invariants, persistence.

The load-bearing test is the one proving a PRIVATE company can never generate an
order, and that a proxy is always labelled.
"""
import pytest

from intent_engine.storage.durable import DurableStore
from intent_engine.universe.companies import (
    CompanyClass,
    CompanyProfile,
    CompanyPredictionUniverse,
    UniverseValidationError,
    default_universe,
)
from intent_engine.universe.store import UniverseStore


def test_default_universe_validates_and_has_expected_classes():
    u = default_universe()
    assert u.by_id("shopify").classification == CompanyClass.PUBLIC_AND_TRADABLE
    assert u.by_id("stripe").classification == CompanyClass.PRIVATE_COMPANY
    # three structurally different tradables + the proxy (IPAY) = 4 tradable
    tradable_ids = {c.company_id for c in u.tradable()}
    assert {"shopify", "cloudflare", "duolingo"} <= tradable_ids
    assert "stripe" not in tradable_ids                       # private, never


def test_private_company_can_never_generate_order():
    priv = default_universe().by_id("stripe")
    assert priv.may_generate_order is False
    # even if some config bug flips the flags, validate() rejects it
    with pytest.raises(UniverseValidationError):
        CompanyProfile(company_id="x", canonical_name="X",
                       classification=CompanyClass.PRIVATE_COMPANY,
                       is_public=False, paper_trading_eligible=True,
                       tradable_instrument="XXX").validate_consistency()


def test_public_but_not_eligible_blocks_orders():
    c = CompanyProfile(
        company_id="ipo", canonical_name="Fresh IPO",
        classification=CompanyClass.PUBLIC_BUT_NOT_ELIGIBLE, is_public=True,
        ticker="IPO", paper_trading_eligible=False)
    c.validate_consistency()
    assert c.may_generate_order is False


def test_proxy_must_be_labelled():
    with pytest.raises(UniverseValidationError):
        CompanyProfile(company_id="p", canonical_name="P",
                       classification=CompanyClass.BENCHMARK_OR_PROXY,
                       is_public=True, tradable_instrument="SPY",
                       proxy_of=None).validate_consistency()
    proxy = default_universe().by_id("stripe_proxy_ipay")
    assert proxy.proxy_of == "stripe" and proxy.proxy_instrument == "IPAY"


def test_by_instrument_lookup():
    u = default_universe()
    assert u.by_instrument("NET").company_id == "cloudflare"
    assert u.by_instrument("shop").company_id == "shopify"   # case-insensitive


def test_peer_groups_span_structural_models():
    groups = default_universe().peer_groups()
    assert groups["ecommerce_platform"] == ["shopify"]
    assert groups["infrastructure"] == ["cloudflare"]
    assert groups["consumer_subscription"] == ["duolingo"]


def test_duplicate_company_id_rejected():
    a = CompanyProfile(company_id="dup", canonical_name="A",
                       classification=CompanyClass.PRIVATE_COMPANY, is_public=False)
    b = CompanyProfile(company_id="dup", canonical_name="B",
                       classification=CompanyClass.PRIVATE_COMPANY, is_public=False)
    with pytest.raises(UniverseValidationError):
        CompanyPredictionUniverse(companies=[a, b]).validate()


# --- durable persistence -----------------------------------------------------

def test_universe_persists_and_reloads(tmp_path):
    store = DurableStore(f"sqlite:///{tmp_path}/d.db")
    us = UniverseStore(store)
    us.save(default_universe())
    # a fresh process (new store instance) loads the active universe
    reopened = UniverseStore(DurableStore(f"sqlite:///{tmp_path}/d.db"))
    loaded = reopened.load()
    assert loaded is not None
    assert loaded.by_id("cloudflare").tradable_instrument == "NET"


def test_load_or_seed_is_idempotent(tmp_path):
    store = DurableStore(f"sqlite:///{tmp_path}/d.db")
    us = UniverseStore(store)
    us.load_or_seed(default_universe())
    us.load_or_seed(default_universe())          # second call must not duplicate
    assert store.count("company_universe") == 1
