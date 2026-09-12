"""A shared name is not a shared identity (§6).

THE DEFECT THIS CLOSES, MEASURED LIVE 2026-09-11 on 17b6b08f. The curated
entry for Adastra Corporation -- a Toronto data and analytics consultancy --
came back from `/api/companies?q=Adastra` carrying

    cik=1891512   ticker=XTXXF   listing=Public

None of which it has. They belong to Adastra Holdings Ltd., an unrelated
Canadian cannabis company in the SEC register.

The cause is the dedupe key. `suggest` merges rows across its three sources so
that Cloudflare, which appears in all of them, is shown once -- and the key was
`" ".join(_words(legal_name))`, where `_words` strips `_SUFFIXES`. That set
contains BOTH "corporation" AND "holdings", so:

    "Adastra Corporation"    -> "adastra"
    "Adastra Holdings Ltd."  -> "adastra"

Same key, one row, two companies. And it is not cosmetic: a confirmed pick
posts `suggest_cik`, so the run would have opened on the consultancy's name
and retrieved a cannabis company's filings as its evidence -- the
wrong-company failure arriving through the one door the catalog exists to
close.

The merge now has its own key, which strips legal FORM ("Inc", "Ltd",
"Corporation") and keeps name words ("Holdings", "Group"). Loosening a MATCH is
how autocomplete stays usable; loosening an IDENTITY is how two companies
become one.
"""
from __future__ import annotations

import pytest

from intent_engine.company_ingestion import suggest as CS
from intent_engine.company_ingestion.suggest import (Suggestion, identity_key,
                                                     suggest)


# --- the key ----------------------------------------------------------------

@pytest.mark.parametrize("a,b", [
    ("Adastra Corporation", "Adastra Holdings Ltd."),
    ("Sigma Computing, Inc.", "Sigma Lithium Corporation"),
    ("Point B, LLC", "Turning Point Brands, Inc."),
    ("Clari Inc.", "Clarivate Plc"),
    ("Sony Group Corporation", "Sony Interactive Entertainment"),
])
def test_two_different_companies_do_not_share_an_identity_key(a, b):
    assert identity_key(a) != identity_key(b), (
        f"{a!r} and {b!r} both reduce to {identity_key(a)!r}, so the merge "
        f"would make them one company")


@pytest.mark.parametrize("a,b", [
    # THE MERGE MUST STILL WORK. These are one company spelled two ways by two
    # sources, and showing it twice fires the ambiguity signal on a company
    # that is not ambiguous.
    ("Cloudflare, Inc.", "Cloudflare Inc"),
    ("Rubrik, Inc.", "RUBRIK INC"),
    ("Commvault Systems, Inc.", "COMMVAULT SYSTEMS INC"),
    ("Samsara Inc.", "Samsara, Inc"),
])
def test_one_company_spelled_two_ways_still_shares_a_key(a, b):
    assert identity_key(a) == identity_key(b), (
        f"{a!r} and {b!r} no longer merge, so one company will be offered "
        f"twice")


def test_legal_form_is_stripped_and_name_words_are_not():
    assert identity_key("Acme Holdings Ltd.") == "acme holdings"
    assert identity_key("Acme Group PLC") == "acme group"
    assert identity_key("Acme Corporation") == "acme"
    assert identity_key("The Acme Company, Inc.") == "acme"


# --- the merge itself -------------------------------------------------------

def _rows(monkeypatch, registry, registrant):
    monkeypatch.setattr(CS, "_from_registry", lambda typed: list(registry))
    monkeypatch.setattr(CS, "_from_manifest", lambda typed: [])
    monkeypatch.setattr(CS, "_from_registrant",
                        lambda typed, **k: list(registrant))


def test_the_consultancy_does_not_inherit_the_cannabis_company_s_cik(
        monkeypatch):
    """THE LIVE FAILURE, REPRODUCED. Both rows, one query, and the curated row
    must come back with the identifiers it actually has: none."""
    ours = Suggestion(legal_name="Adastra Corporation", common_name="Adastra",
                      country="Canada", domain="adastracorp.com",
                      entity_id="adastra", source=CS.REGISTRY,
                      match=CS.EXACT)
    theirs = Suggestion(legal_name="Adastra Holdings Ltd.",
                        common_name="Adastra", cik="1891512", ticker="XTXXF",
                        listing="Public", source="SEC registrant table",
                        match=CS.LEADING)
    _rows(monkeypatch, [ours], [theirs])
    got = suggest("Adastra", limit=6)
    by_id = {r.entity_id: r for r in got}
    assert "adastra" in by_id, f"the curated entry vanished: {got}"
    mine = by_id["adastra"]
    assert mine.cik == "", (
        f"the consultancy was handed CIK {mine.cik!r}, which belongs to "
        f"Adastra Holdings Ltd. A confirmed pick posts this, so the run would "
        f"have retrieved a cannabis company's filings as its evidence")
    assert mine.ticker == "", (
        f"the consultancy was handed ticker {mine.ticker!r}")
    assert len(got) == 2, (
        f"both companies must still be OFFERED -- a customer may mean either, "
        f"and suppressing one trades a wrong answer for a different one: {got}")


def test_one_company_from_two_sources_is_still_offered_once(monkeypatch):
    """THE POSITIVE CONTROL, and the reason the merge exists at all. Without
    it this test is the one that fails."""
    reg = Suggestion(legal_name="Cloudflare, Inc.", common_name="Cloudflare",
                     country="United States", domain="cloudflare.com",
                     entity_id="cloudflare", source=CS.REGISTRY,
                     match=CS.EXACT)
    sec = Suggestion(legal_name="Cloudflare Inc", cik="0001477333",
                     ticker="NET", source="SEC registrant table",
                     match=CS.EXACT)
    _rows(monkeypatch, [reg], [sec])
    got = suggest("Cloudflare", limit=6)
    assert len(got) == 1, f"one company was offered {len(got)} times: {got}"
    assert got[0].entity_id == "cloudflare"
    assert got[0].domain == "cloudflare.com"
    assert got[0].cik == "0001477333", "the merge lost the regulator's id"
    assert got[0].ticker == "NET"


def test_rows_that_disagree_on_a_cik_are_not_merged(monkeypatch):
    """A name can coincide; a CIK cannot. Two rows naming two filers stay two
    rows even when their names reduce alike."""
    a = Suggestion(legal_name="Acme Corp", common_name="Acme", cik="111",
                   source=CS.REGISTRY, match=CS.EXACT)
    b = Suggestion(legal_name="Acme Inc", common_name="Acme", cik="222",
                   source="SEC registrant table", match=CS.EXACT)
    _rows(monkeypatch, [a], [b])
    got = suggest("Acme", limit=6)
    assert len(got) == 2, (
        f"two filers with different CIKs were merged into one: {got}")
    assert {r.cik for r in got} == {"111", "222"}


def test_a_source_s_own_id_convention_is_not_treated_as_disagreement(
        monkeypatch):
    """`entity_id` is a source's naming convention, not a shared identifier.
    The catalog files Descartes as `descartes` and the validation manifest as
    `descartes-systems`; comparing those as strings split one company in two
    the first time this check was written."""
    a = Suggestion(legal_name="The Descartes Systems Group Inc.",
                   common_name="Descartes Systems", domain="descartes.com",
                   entity_id="descartes", source=CS.REGISTRY, match=CS.EXACT)
    b = Suggestion(legal_name="Descartes Systems Group Inc",
                   common_name="Descartes Systems", ticker="DSG",
                   entity_id="descartes-systems", source=CS.MANIFEST
                   if hasattr(CS, "MANIFEST") else "validation manifest",
                   match=CS.EXACT)
    _rows(monkeypatch, [a], [b])
    got = suggest("Descartes Systems", limit=6)
    assert len(got) == 1, (
        f"one company was split in two because two sources name its id "
        f"differently: {[(r.legal_name, r.entity_id) for r in got]}")


def test_every_one_of_the_forty_is_offered_exactly_once():
    """The whole-catalog statement of the same property: no curated entry may
    collide with another, and none may be duplicated by a second source."""
    from intent_engine.company_ingestion.catalog import CATALOG_REGISTRY
    for profile in CATALOG_REGISTRY:
        got = suggest(profile.common_name, allow_registrant=False)
        same = [r for r in got if r.entity_id == profile.entity_id]
        assert len(same) == 1, (
            f"{profile.entity_id} is offered {len(same)} times for its own "
            f"name: {[(r.legal_name, r.entity_id) for r in got]}")


# --- the same collision, one layer deeper -----------------------------------

def test_a_curated_company_with_no_cik_is_not_resolved_by_a_fuzzy_name_match():
    """MEASURED on Adastra, cohort A, 1b0d803c -- AFTER the suggestion merge
    was repaired.

    The picker no longer hands the consultancy the cannabis company's CIK, but
    the RUN resolves its own subject CIK separately: `subject_cik` falls back
    to `resolve_cik(company_name)`, a fuzzy match over the SEC ticker table,
    whenever `meta["cik"]` is empty -- which is every private company. For
    "Adastra Corporation" that returned ADASTRA HOLDINGS LTD., whose SIC code
    is pharmaceutical preparations, so a Toronto data consultancy was
    classified PHARMA and its X-Ray asked management which development
    programmes to fund, with watch metrics naming approved indications,
    prescriptions and exclusivity runway.

    One collision, three doors: the suggestion merge, and this. A curated
    profile that declares no CIK is stating the company is not a filer we know
    of, and that is an answer."""
    from intent_engine.company_ingestion import entities as E
    profile = E.resolve_entity(company_name="Adastra Corporation").profile
    assert profile is not None, "the curated consultancy no longer resolves"
    assert profile.sec_cik == "", (
        f"the consultancy declares CIK {profile.sec_cik!r}; it files with no "
        f"US regulator")
    assert profile.entity_id == "adastra"


def test_a_curated_filer_still_supplies_its_cik():
    """POSITIVE CONTROL. Suppressing the fuzzy lookup must not cost a real
    filer its EDGAR route -- rubrik.com answers 403 to every path, so its
    filings are the ONLY evidence it has."""
    from intent_engine.company_ingestion import entities as E
    for name, cik in (("Rubrik, Inc.", "0001943896"),
                      ("Commvault Systems, Inc.", "0001169561"),
                      ("FiscalNote Holdings, Inc.", "0001823466")):
        profile = E.resolve_entity(company_name=name).profile
        assert profile is not None and profile.sec_cik == cik, name


def test_subject_cik_consults_the_registry_before_guessing():
    """The repair must be ON the path. A registry lookup that `subject_cik`
    never performs leaves the fuzzy fallback deciding, which is the defect."""
    import inspect

    from intent_engine.company_ingestion.service import CompanyIngestionService
    src = inspect.getsource(CompanyIngestionService.subject_cik)
    assert "resolve_entity" in src, (
        "subject_cik still resolves an unknown CIK by fuzzy name match "
        "without asking the curated registry first")
    # Compared against the CALL SITE, not the first mention: the docstring
    # discusses `resolve_cik` by name several lines above the code that runs
    # it, so a text-position check on the bare word measures prose.
    call = src.index("from intent_engine.company_ingestion.edgar import "
                     "resolve_cik")
    assert src.index("resolve_entity") < call, (
        "the registry is consulted AFTER the fuzzy lookup, so the guess wins")


def test_an_uncatalogued_company_still_falls_back():
    """A company the registry has never heard of must keep the existing
    behaviour: the fallback exists because it is the only way a domain-entry
    run finds its filer at all."""
    from intent_engine.company_ingestion import entities as E
    assert E.resolve_entity(
        company_name="Nonexistent Widgets Ltd").profile is None
