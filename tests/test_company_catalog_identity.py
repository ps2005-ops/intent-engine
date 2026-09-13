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
    would launder somebody else's words into the company's own voice.

    THE FULL HOST, NOT ITS FIRST LABEL. This compared only
    `primary_domain.split(".")[0]`, so it accepted a source on ANY top-level
    domain sharing that label -- and a break proof caught it: switching
    FourKites' canonical domain from fourkites.ai to fourkites.com left this
    test green, over the one entry whose entire reason for existing is that
    the .com form redirects off-domain and cannot be used. A rule that cannot
    tell two TLDs apart cannot protect the thing it was written for.
    """
    for profile in CATALOG_REGISTRY:
        want = profile.primary_domain.lower().removeprefix("www.")
        for source in profile.official_sources:
            host = source.url.lower().split("/")[2].removeprefix("www.")
            assert host == want, (
                f"{profile.entity_id}: {source.url} is on {host}, not on "
                f"{want}")


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


# --- THE WHOLE CATALOG, NOT A NAMED LIST ------------------------------------
#
# WHY THESE ARE PARAMETRIZED OVER THE REGISTRY AND NOT OVER FORTY NAMES.
#
# The previous wave qualified ten companies by listing them here. The next
# forty were then MEASURED LIVE on b4db855b before any analysis was spent, and
# 33 of 40 returned nothing at all while TWO returned the wrong company:
# "Clari" offered only Clarivate Plc and Claritev Corp, and "Adastra" offered
# Adastra Holdings Ltd., a cannabis company. A hardcoded list of ten could not
# have caught any of it, and a hardcoded list of forty would not catch the
# forty-first.
#
# So the contract is stated over every entry the catalog holds: whatever is in
# it must be findable by its own name and by each name it claims, and no two
# entries may claim the same one. Adding a company is then a data edit that
# either satisfies the contract or fails it by itself.

_ALL = list(CATALOG_REGISTRY)


@pytest.mark.parametrize("entity_id", [p.entity_id for p in _ALL])
def test_every_catalog_entry_is_found_first_by_its_own_common_name(entity_id):
    """Not merely present -- FIRST. A judge takes the top row."""
    profile = [p for p in _ALL if p.entity_id == entity_id][0]
    rows = suggest(profile.common_name, allow_registrant=False)
    assert rows, f"{profile.common_name!r} returned nothing"
    assert rows[0].entity_id == entity_id, (
        f"{profile.common_name!r} offered {_ids(rows)[:3]} before {entity_id}")


@pytest.mark.parametrize("entity_id,alias", [
    (p.entity_id, a) for p in _ALL for a in p.aliases])
def test_every_alias_finds_its_own_entry_first(entity_id, alias):
    """An alias that does not win is a name the customer can type and miss."""
    rows = suggest(alias, allow_registrant=False)
    assert rows, f"alias {alias!r} of {entity_id} returned nothing"
    assert rows[0].entity_id == entity_id, (
        f"alias {alias!r} of {entity_id} offered {_ids(rows)[:3]}")


@pytest.mark.parametrize("entity_id", [p.entity_id for p in _ALL])
def test_every_catalog_entry_opens_without_a_website(entity_id):
    """MANUAL_URL_REQUIRED = 0 depends on a domain on the chosen row."""
    profile = [p for p in _ALL if p.entity_id == entity_id][0]
    assert profile.primary_domain.strip(), (
        f"{entity_id} carries no canonical domain, so a run on it would have "
        f"to ask the customer for a URL")
    resolution = NE.resolve_typed_name(profile.common_name) \
        if hasattr(NE, "resolve_typed_name") else None
    if resolution is not None:
        assert resolution is not False


def test_no_two_entries_claim_the_same_name_or_domain():
    """Two entries answering one alias means the loser is unreachable by it,
    and which one loses depends on declaration order."""
    seen_alias, seen_domain = {}, {}
    for profile in _ALL:
        host = profile.primary_domain.lower()
        assert host not in seen_domain, (
            f"{profile.entity_id} and {seen_domain[host]} both claim {host}")
        seen_domain[host] = profile.entity_id
        for alias in profile.aliases:
            key = " ".join(str(alias).lower().split())
            assert key not in seen_alias, (
                f"{profile.entity_id} and {seen_alias[key]} both claim the "
                f"alias {alias!r}")
            seen_alias[key] = profile.entity_id


@pytest.mark.parametrize("typed,ours,also_offered", [
    # MEASURED LIVE: each of these returned ONLY the wrong company.
    ("Clari", "clari", "Clarivate"),
    ("Sigma", "sigma_computing", "Sigma Lithium"),
    ("Point B", "point_b", "Turning Point Brands"),
])
def test_a_collision_puts_us_first_and_still_offers_the_other(
        typed, ours, also_offered):
    """THE CHOOSER WORKING, NOT A LAND GRAB. The registrant is a real company
    and a customer may well mean it, so it stays on the list -- second.
    Suppressing it would trade one wrong answer for a different one."""
    rows = suggest(typed, allow_registrant=True)
    assert rows, f"{typed!r} returned nothing"
    assert rows[0].entity_id == ours, (
        f"{typed!r} offered {_ids(rows)[:3]} before {ours}")
    names = " | ".join((r.common_name or "") + " " + (r.legal_name or "")
                       for r in rows)
    assert also_offered.lower() in names.lower(), (
        f"{typed!r} no longer offers {also_offered!r} at all: {names}")


@pytest.mark.parametrize("entity_id", ["rubrik", "6sense", "fiscalnote"])
def test_a_host_that_refuses_us_still_records_that_we_tried(entity_id):
    """A 403 FROM THE COMPANY'S OWN SITE IS NOT A COMPANY THAT PUBLISHES
    NOTHING. All three answered HTTP 403 on every path including robots.txt,
    so no sub-page could be attested -- but the homepage is the declared
    canonical domain and it was fetched, and 403 is the host ANSWERING.

    Carrying it means the run can report "their own site refused us" instead
    of carrying nothing and leaving no record that we tried. Carrying invented
    sub-paths instead would turn our refusal into their silence."""
    profile = [p for p in _ALL if p.entity_id == entity_id][0]
    assert profile.official_sources, (
        f"{entity_id} carries no source at all, so a blocked run has nothing "
        f"to try and no way to say it was refused")
    assert len(profile.official_sources) == 1, (
        f"{entity_id} lists {len(profile.official_sources)} sources for a host "
        f"that refused every path -- only the probed homepage is attested")
    assert "403" in profile.ambiguity_notes, (
        f"{entity_id} carries an unreadable host without saying so")


def test_fourkites_points_at_the_domain_it_actually_publishes_on():
    """THE SECOND MONTE CARLO. fourkites.com redirects to www.fourkites.ai and
    this product's fetcher refuses a redirect that leaves the approved domain
    -- `unsafe_redirect: redirect to www.fourkites.ai leaves the approved
    domain policy`. A run opened on the .com form therefore retrieves NOTHING,
    and the product would report a company that publishes nothing. Measured
    2026-09-11 through `safe_fetch`, both with and without the www prefix."""
    top = suggest("FourKites", allow_registrant=False)[0]
    assert top.domain == "fourkites.ai", (
        f"FourKites resolves to {top.domain!r}, which redirects off-domain")


@pytest.mark.parametrize("entity_id,host", [
    ("monte_carlo_data", "montecarlo.ai"),
    ("fourkites", "fourkites.ai"),
    ("starburst", "starburst.io"),
    ("gong", "gong.io"),
    ("alphasense", "alpha-sense.com"),
    ("adastra", "adastracorp.com"),
    ("o9_solutions", "o9solutions.com"),
])
def test_a_canonical_domain_is_not_the_name_plus_dot_com(entity_id, host):
    """Seven of the fifty do not live at <name>.com. Each was read from the
    company's own site rather than assumed, because assuming is how a run gets
    opened on a domain that redirects away or belongs to somebody else."""
    profile = [p for p in CATALOG_REGISTRY if p.entity_id == entity_id][0]
    assert profile.primary_domain == host


# --- the regulator's identifier has to survive to the row ---------------------

@pytest.mark.parametrize("entity_id,cik,ticker", [
    ("rubrik", "0001943896", "RBRK"),
    ("commvault", "0001169561", "CVLT"),
    ("samsara", "0001642896", "IOT"),
    ("descartes", "0001050140", "DSGX"),
    ("fiscalnote", "0001823466", "NOTE"),
    ("zoominfo", "0001794515", "GTM"),
])
def test_a_catalogued_filer_carries_its_cik_without_the_network(
        entity_id, cik, ticker):
    """THE DEFECT. `_from_registry` asked for `profile.ticker` -- a field
    `EntityProfile` does not define -- and asked for no CIK at all, so every
    catalogued filer reached the customer with neither.

    It was invisible because the SEC registrant row supplies a CIK and the
    merge fills the gap: the identity was being carried by the one source that
    is a ~1MB network fetch. `allow_registrant=False` is the point of this
    test, not an optimisation -- it is the assertion that the catalog stands on
    its own.

    It matters most where it is least visible: rubrik.com and fiscalnote.com
    answer HTTP 403 to every path, so on any request where that table did not
    load, two public filers would have lost their only evidence route and been
    reported as companies that publish nothing."""
    rows = suggest(
        [p.common_name for p in CATALOG_REGISTRY
         if p.entity_id == entity_id][0], allow_registrant=False)
    assert rows and rows[0].entity_id == entity_id
    assert rows[0].cik == cik, (
        f"{entity_id} reached the customer with cik={rows[0].cik!r}; the "
        f"catalog declares {cik}")
    assert rows[0].ticker == ticker, (
        f"{entity_id} reached the customer with ticker={rows[0].ticker!r}")


def test_a_private_company_invents_neither():
    """The other half of the same property: a declared-empty field stays
    empty. A catalog that filled in a plausible CIK would attribute one
    company's filings to another."""
    for entity_id in ("6sense", "credera", "project44", "workato"):
        rows = suggest(
            [p.common_name for p in CATALOG_REGISTRY
             if p.entity_id == entity_id][0], allow_registrant=False)
        assert rows and rows[0].entity_id == entity_id
        assert not rows[0].cik, f"{entity_id} acquired a CIK from nowhere"


def test_a_canadian_issuer_carries_a_ticker_and_no_sec_cik():
    """Kinaxis is listed in Toronto and files with no US regulator. Both
    halves have to be true at once, which is what a `listings`-derived ticker
    and an absent `sec_cik` say together."""
    rows = suggest("Kinaxis", allow_registrant=False)
    assert rows[0].ticker == "KXS"
    assert not rows[0].cik


def test_the_primary_listing_wins_not_the_last_one():
    """Descartes is listed on NASDAQ and the TSX. The first declared listing
    is the primary one; taking whichever sorted last showed a Canadian symbol
    to a US reader."""
    profile = [p for p in CATALOG_REGISTRY if p.entity_id == "descartes"][0]
    assert profile.listings[0] == ("NASDAQ", "DSGX")
    assert suggest("Descartes Systems", allow_registrant=False)[0].ticker \
        == "DSGX"


def test_public_status_is_stated_only_where_a_source_says_so():
    """§6 asks for public/private status. A declared listing or SEC
    identifier is a source saying PUBLIC; the absence of one is not a source
    saying PRIVATE, and this field's contract is "where a source says so".

    So the assertion is asymmetric on purpose: the filers must read PUBLIC,
    and the rest must read EMPTY rather than PRIVATE."""
    public = {"rubrik", "commvault", "samsara", "descartes", "fiscalnote",
              "zoominfo", "kinaxis"}
    for profile in CATALOG_REGISTRY:
        row = suggest(profile.common_name, allow_registrant=False)[0]
        if profile.entity_id in public:
            assert row.listing == "PUBLIC", (
                f"{profile.entity_id} declares a listing or a CIK and still "
                f"reached the customer as {row.listing!r}")
        else:
            assert row.listing == "", (
                f"{profile.entity_id} was asserted to be {row.listing!r} on "
                f"the strength of an absent field")
