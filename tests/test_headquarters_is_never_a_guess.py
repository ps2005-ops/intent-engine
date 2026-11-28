"""A headquarters country is a claim about a company, and it is only made when
a status asserts it (2026-11-28: six private companies had none that could be
sourced; the old invariant forced a guess or blocked unrelated work)."""
import dataclasses

import pytest

from intent_engine.company_ingestion import entities as E
from intent_engine.company_ingestion.catalog import CATALOG_REGISTRY
from intent_engine.company_ingestion.suggest import suggest

SOURCED = {E.HQ_VERIFIED, E.HQ_COMPANY_REPORTED, E.HQ_CORROBORATED}


def test_every_status_is_known_and_consistent_with_what_is_displayed():
    for p in CATALOG_REGISTRY:
        assert p.hq_status in {""} | E.HQ_ASSERTING | E.HQ_NON_ASSERTING, p.entity_id
        if p.hq_status in E.HQ_NON_ASSERTING:
            assert not p.country and p.hq_note.strip(), p.entity_id
            assert not p.headquarters_displayable
        if p.hq_status in SOURCED:
            assert p.country and p.hq_sources, f"{p.entity_id}: a sourced status needs its sources"
            for src in p.hq_sources:
                assert src[0].startswith("https://") and src[2].strip()


@pytest.mark.parametrize("eid", ["firebolt", "aqua-security"])
def test_a_conflicting_or_provisional_headquarters_never_reaches_a_customer(eid):
    p = next(x for x in CATALOG_REGISTRY if x.entity_id == eid)
    assert p.hq_status in E.HQ_NON_ASSERTING and not p.country
    row = next(r for r in suggest(p.common_name, allow_registrant=False) if r.entity_id == eid)
    assert row.country == ""
    for c in ("Israel", "United States", "Germany", "India"):
        assert c not in row.describe()


def test_a_country_under_a_non_asserting_status_is_refused_by_the_invariant():
    p = next(x for x in CATALOG_REGISTRY if x.entity_id == "firebolt")
    forged = dataclasses.replace(p, country="Israel")
    assert not forged.headquarters_displayable


def test_a_regional_headquarters_is_not_the_global_one():
    p = next(x for x in CATALOG_REGISTRY if x.entity_id == "ivalua")
    assert p.country == "France" and p.hq_status == E.HQ_VERIFIED
    assert ("Americas", "Redwood City, United States") in p.regional_hq
