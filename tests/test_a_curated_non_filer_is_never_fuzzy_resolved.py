"""One company's filings may never become another's evidence (§3, P0).

MEASURED LIVE ACROSS THREE CONSECUTIVE BUILDS. Adastra Corporation is a
Toronto data and analytics consultancy that files with no US regulator. The
name "Adastra" matches ADASTRA HOLDINGS LTD. in the SEC register -- an
unrelated Canadian cannabis company whose SIC code is pharmaceutical
preparations.

Every layer that could not find a CIK fell back to a fuzzy name match and
found that company:

    1. `suggest` merged the two rows        -> the picker carried its CIK
    2. `subject_cik` fuzzy-resolved the name-> PHARMA classification
    3. `propose_edgar_candidates` did too   -> its Form 20-F was RETRIEVED

On e2ab6feb, with doors 1 and 2 already closed, the run still read

    https://www.sec.gov/Archives/edgar/data/1891512/.../form20f.htm

as the consultancy's own evidence, and its X-Ray asked management "which
development programmes to fund and which to stop, given how long it takes a
programme to reach approved products", with the words pharmaceutical,
prescription, exclusivity runway and rebate on the page.

CLOSING THE DOORS ONE AT A TIME IS WHAT KEPT IT ALIVE. Making `subject_cik`
return "" for a non-filer is precisely what sent `propose_edgar_candidates`
down its `else` branch and into the same wrong registrant. A defect with four
doors is not four defects.

So the question is asked ONCE -- `entities.declared_cik` -- and every door
honours the answer. Forty-four of the fifty curated entries declare no CIK,
which is the measure of how wide this was.
"""
from __future__ import annotations

import pytest

from intent_engine.company_ingestion.entities import declared_cik


# --- the one authority ------------------------------------------------------

def test_a_curated_non_filer_answers_empty_not_unknown():
    """The distinction the whole repair rests on: "" means DO NOT GUESS, and
    None means "not curated, resolve as you always did"."""
    assert declared_cik(company_name="Adastra Corporation") == ""
    assert declared_cik(company_name="Cohesity, Inc.") == ""
    assert declared_cik(company_name="project44, Inc.") == ""


def test_a_curated_filer_answers_with_its_cik():
    assert declared_cik(company_name="Rubrik, Inc.") == "0001943896"
    assert declared_cik(company_name="Commvault Systems, Inc.") == "0001169561"
    assert declared_cik(company_name="FiscalNote Holdings, Inc.") == "0001823466"


def test_an_uncatalogued_company_answers_none():
    """NOT "" -- the fallback must stay reachable for every company the
    registry has never heard of, which is most of the world."""
    assert declared_cik(company_name="Nonexistent Widgets Ltd") is None
    assert declared_cik(company_name="") is None


# --- the door that actually retrieved the wrong filing ----------------------

def test_the_consultancy_retrieves_no_filings_at_all():
    """THE LIVE FAILURE, REPRODUCED. This call is what put a cannabis
    company's Form 20-F under a consultancy's name."""
    from intent_engine.company_ingestion.edgar import propose_edgar_candidates
    got = propose_edgar_candidates(company_name="Adastra Corporation")
    assert got == [], (
        f"a curated non-filer was fuzzy-resolved into the SEC register and "
        f"returned {len(got)} filing candidate(s): "
        f"{[c.get('url') for c in got][:3]}")


def test_a_curated_filer_still_retrieves_its_own_filings():
    """POSITIVE CONTROL, and it is not decorative: rubrik.com answers HTTP 403
    on every path, so its SEC filings are the ONLY evidence it has. A repair
    that silenced this door would take Rubrik's entire analysis with it."""
    from intent_engine.company_ingestion.edgar import propose_edgar_candidates
    got = propose_edgar_candidates(company_name="Rubrik, Inc.", limit=3)
    assert got, "the curated filer lost its filings"
    for candidate in got:
        assert "data/1943896" in candidate.get("url", ""), (
            f"a filing under another registrant was proposed for Rubrik: "
            f"{candidate.get('url')}")


# --- every door asks the same question --------------------------------------

@pytest.mark.parametrize("module,func", [
    ("intent_engine.company_ingestion.edgar", "propose_edgar_candidates"),
    ("intent_engine.company_ingestion.service", "subject_cik"),
])
def test_each_door_consults_the_authority_before_guessing(module, func):
    import importlib
    import inspect
    mod = importlib.import_module(module)
    target = getattr(mod, func, None)
    if target is None:
        target = getattr(mod.CompanyIngestionService, func)
    src = inspect.getsource(target)
    assert ("declared_cik" in src or "resolve_entity" in src), (
        f"{module}.{func} resolves a CIK by fuzzy name match without asking "
        f"whether a curated identity already answered")


@pytest.mark.parametrize("method", ["_filer_cik", "_registrant"])
def test_the_webapp_doors_consult_it_too(method):
    """EACH DOOR, INDIVIDUALLY.

    A first version counted occurrences across the whole module and required
    two or more. Both doors take an import AND a call, so there were four --
    and disabling one door outright still left two. A break proof caught it
    and reported NOT_CAUGHT, which was true of the threshold and not of the
    guard. A count over a module cannot tell which door is open.
    """
    import inspect

    from intent_engine.webapp import app as A
    src = inspect.getsource(getattr(A.WebApp, method))
    assert "declared_cik" in src, (
        f"WebApp.{method} still resolves a CIK by fuzzy name match without "
        f"asking whether a curated identity already answered")
    assert "resolve_cik" in src, (
        f"WebApp.{method} no longer has a fallback at all, so an "
        f"uncatalogued company can never be resolved")


def test_forty_four_of_the_fifty_depend_on_this():
    """The blast radius, asserted so it cannot quietly shrink. Every catalog
    entry with no declared CIK reaches a fuzzy resolver with an empty CIK, and
    each is one name-collision away from another company's filings."""
    from intent_engine.company_ingestion.catalog import CATALOG_REGISTRY
    non_filers = [p for p in CATALOG_REGISTRY
                  if not (p.sec_cik or "").strip()]
    assert len(non_filers) >= 40, len(non_filers)
    for profile in non_filers[:8]:
        assert declared_cik(company_name=profile.legal_name) == "", (
            f"{profile.entity_id} does not answer 'not a filer' and would be "
            f"fuzzy-resolved")
