"""The reviewed registry classifies a business only where no regulator does,
and only with the company's own words as its basis.

MEASURED 2026-11-28 (prospect-98 w6): 22 of 70 private companies read "what
kind of business this is has not been established", which switches off the
pattern library, the per-class metrics and the macro transmission table.
"""
from intent_engine.company_ingestion.catalog import CATALOG_REGISTRY
from intent_engine.executive import company_profile as CP


def test_every_curated_class_is_a_known_class_with_a_basis():
    curated = [p for p in CATALOG_REGISTRY if p.business_model_class]
    assert curated
    for p in curated:
        assert p.business_model_class in CP.MODEL_CLASSES, p.entity_id
        assert p.business_model_basis.strip(), f"{p.entity_id}: a class without the company's own words"


def test_a_private_registered_company_is_classified_and_says_why():
    prof = CP.profile_for(name="Improving", domain="improving.com", manifest=None)
    assert prof.known and prof.profile_source == "CURATED_REGISTRY"
    assert prof.business_model_class == "PEOPLE_OR_ROUTE_BASED_SERVICES"
    assert "reviewed company registry" in prof.profile_limitation
    assert "Enterprise AI" in prof.profile_limitation          # the company's own words


def test_the_regulator_still_outranks_the_registry():
    registrant = {"sic": "7372", "sic_description": "SERVICES-PREPACKAGED SOFTWARE"}
    prof = CP.profile_for(name="Improving", domain="improving.com", manifest=None, registrant=registrant)
    assert prof.profile_source.startswith("SEC_SIC")


def test_an_unregistered_company_is_untouched():
    prof = CP.profile_for(name="Acme Widgets", domain="acme-widgets.example", manifest=None)
    assert prof.profile_source == "NONE" and not prof.known


def test_the_reader_is_told_it_is_a_reviewed_classification():
    from intent_engine.adaptive import profile as AP
    assert AP.model_source_of("CURATED_REGISTRY") == AP.MODEL_SOURCE_CURATED
