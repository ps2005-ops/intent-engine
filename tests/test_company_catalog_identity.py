"""A private company is not an edge case. It is most companies.

MEASURED LIVE 2026-09-11 against the deployed preview on b88df2bb, one GET
per name to `/api/companies?q=`:

    Highspot 0   BigID 0   Cyera 0   Monte Carlo 0   Veeam 0
    Druva 0      Slalom 0
    ZoomInfo 1 -- correct, it is an SEC filer
    Sigma    1 -- "Sigma Lithium Corp", a lithium miner
    Point B  1 -- "Turning Point Brands, Inc.", a tobacco company

Seven of ten found nothing at all, and two of the three that resolved offered
A DIFFERENT COMPANY, which is worse than an empty list: a judge who accepts
the only suggestion on screen gets a confident report about a business with
no relationship to the one they typed. "Point B" reached Turning Point Brands
because `_match` scores CONTAINS on a partial final word, and "point b" is a
prefix of "point brands".

The cause is structural rather than a bad match rule: every source `suggest`
could reach -- the entity registry, the validation manifest, the SEC
registrant table -- is a register of PUBLIC companies. So the product could
find ten thousand filers and could not find Highspot.

These tests pin the identity contract, not the analysis. A catalog entry may
carry a name, a domain and the company's own URLs; it may not carry a lens, a
thesis or any sentence that could reach a report.
"""
import pytest

from intent_engine.company_ingestion import name_entry as NE
from intent_engine.company_ingestion.catalog import CATALOG, CATALOG_REGISTRY
from intent_engine.company_ingestion.suggest import suggest

#: The exact ten the demo qualifies on.
TEN = ["Highspot", "BigID", "Cyera", "Monte Carlo Data", "Veeam", "Druva",
       "Slalom", "Sigma Computing", "ZoomInfo", "Point B"]

#: How a person actually types each one. Case, spacing and prefixes.
VARIANTS = {
    "highspot": ["Highspot", "highspot", "HIGHSPOT", "High", "Highspot "],
    "bigid": ["BigID", "bigid", "BIGID", "big id", "Big"],
    "cyera": ["Cyera", "cyera", "CYERA", "Cye"],
    "monte_carlo_data": ["Monte Carlo Data", "monte carlo", "Monte Carlo",
                         "MONTE CARLO", "montecarlo", "Monte"],
    "veeam": ["Veeam", "veeam", "VEEAM", "Vee"],
    "druva": ["Druva", "druva", "DRUVA", "Druv"],
    "slalom": ["Slalom", "slalom", "SLALOM", "Slal"],
    "sigma_computing": ["Sigma Computing", "sigma computing", "Sigma",
                        "SIGMA", "sigma"],
    "zoominfo": ["ZoomInfo", "zoominfo", "ZOOMINFO", "Zoom Info", "ZoomI"],
    "point_b": ["Point B", "point b", "POINT B", "PointB", "pointb",
                "Point"],
}


def _ids(rows):
    return [r.entity_id for r in rows]


# --- discovery --------------------------------------------------------------

@pytest.mark.parametrize("entity_id,typed", [
    (eid, typed) for eid, queries in VARIANTS.items() for typed in queries])
def test_every_way_a_person_types_it_finds_it_first(entity_id, typed):
    """Not merely present in the list -- FIRST. A judge takes the top row."""
    rows = suggest(typed, allow_registrant=False)
    assert rows, f"{typed!r} returned nothing"
    assert rows[0].entity_id == entity_id, (
        f"{typed!r} offered {_ids(rows)[:3]} before {entity_id}")


@pytest.mark.parametrize("name", TEN)
def test_every_one_of_the_ten_carries_a_domain(name):
    """MANUAL_URL_REQUIRED = 0/10 depends on this and nothing else."""
    top = suggest(name, allow_registrant=False)[0]
    assert top.domain, f"{name} would still require a typed website"


@pytest.mark.parametrize("name", TEN)
def test_every_one_of_the_ten_resolves_without_a_website(name):
    entry = NE.resolve(company_name=name, allow_registrant=False)
    assert entry.resolved, f"{name} did not resolve: {entry.state}"
    assert entry.website, f"{name} resolved with no website"


# --- the two that used to answer with a different company -------------------

def test_sigma_is_the_analytics_company_not_the_lithium_miner():
    rows = suggest("Sigma", allow_registrant=False)
    assert rows[0].entity_id == "sigma_computing"
    assert "lithium" not in rows[0].legal_name.lower()


def test_point_b_is_the_consultancy_not_the_tobacco_company():
    rows = suggest("Point B", allow_registrant=False)
    assert rows[0].entity_id == "point_b"
    assert "turning point" not in rows[0].legal_name.lower()


# --- what an entry may and may not contain ----------------------------------

def test_no_catalog_entry_carries_analysis():
    """A qualified IDENTITY is allowed; a qualified ANSWER is not.

    If a lens, a thesis or a business-model verdict could be written here,
    the demo would be a puppet show: the report would say what the catalog
    said rather than what the documents said.
    """
    banned = ("lens", "thesis", "business_model", "decision", "recommend",
              "strategy", "insight", "conclusion", "verdict", "posture")
    for row in CATALOG:
        for key in row:
            assert key not in banned, (
                f"{row['entity_id']} carries analysis field {key!r}")


def test_every_catalog_url_is_on_the_company_s_own_domain():
    """A curated source must be the COMPANY speaking. A third-party URL here
    would launder somebody else's words into the company's own voice."""
    for profile in CATALOG_REGISTRY:
        host = profile.primary_domain.lower()
        root = host.split(".")[0]
        for source in profile.official_sources:
            assert root in source.url.lower(), (
                f"{profile.entity_id}: {source.url} is not on {host}")


def test_monte_carlo_points_at_the_domain_it_actually_publishes_on():
    """THE DEFECT THIS ENCODES. montecarlodata.com 301s to montecarlo.ai and
    the redirect guard correctly refuses the cross-domain hop -- so a run
    opened on the old domain retrieved NOTHING, and the product reported a
    company whose material "does not say clearly enough what decision it
    serves". That was never a fact about Monte Carlo."""
    top = suggest("Monte Carlo Data", allow_registrant=False)[0]
    assert top.domain == "montecarlo.ai"


def test_highspot_records_that_it_is_part_of_seismic():
    """Its own site says so, in the nav and twice in the body. Describing it
    as a standalone independent vendor would be an identity error."""
    profile = [p for p in CATALOG_REGISTRY if p.entity_id == "highspot"][0]
    assert "seismic" in profile.ambiguity_notes.lower()


def test_the_catalog_extends_without_touching_code():
    """Adding company eleven must be a data edit."""
    assert isinstance(CATALOG, tuple)
    assert all(isinstance(row, dict) for row in CATALOG)
    assert len(CATALOG_REGISTRY) == len(CATALOG)


def test_catalog_entries_reach_the_shared_registry():
    """One registry, three readers: suggest, resolve-by-name, match-by-domain.
    A catalog only the suggestion list could see would offer a company the
    resolver then failed to open."""
    from intent_engine.company_ingestion import entities as E
    ids = {p.entity_id for p in E.REGISTRY}
    for row in CATALOG:
        assert row["entity_id"] in ids
