"""A ticker we cannot find is not a company that is private.

The registry carried listings for three companies (Sony, Palantir, Shopify),
so every other company reached the founder dashboard with no ticker, and the
market card said "for a private company there is no market to read" over
Tesla and NVIDIA. Both are listed. That is a wrong fact, not an honest gap,
and it is the thing these tests exist to keep out.

The fixture is a trimmed copy of the SEC's real
`company_tickers_exchange.json` shape, including the cases that actually
matter: a company whose registered name is longer than what a founder types
(Costco), foreign issuers quoted twice (ASML, Toyota), and names that reach
several unrelated registrants (Apple).
"""
import json

import pytest

from intent_engine.company_ingestion.listings import (
    PRIVATE,
    PUBLIC_LISTING_RESOLVED,
    PUBLIC_LISTING_UNRESOLVED,
    UNKNOWN,
    SecTickerMap,
    normalize_company_name,
    resolve_listing,
)

# (cik, name, ticker, exchange) exactly as the SEC serves them.
_ROWS = [
    (1318605, "Tesla, Inc.", "TSLA", "Nasdaq"),
    (1045810, "NVIDIA CORP", "NVDA", "Nasdaq"),
    (909832, "COSTCO WHOLESALE CORP /NEW", "COST", "Nasdaq"),
    (796343, "ADOBE INC.", "ADBE", "Nasdaq"),
    (1561550, "Datadog, Inc.", "DDOG", "Nasdaq"),
    (1477333, "Cloudflare, Inc.", "NET", "NYSE"),
    (937966, "ASML HOLDING NV", "ASML", "Nasdaq"),
    (937966, "ASML HOLDING NV", "ASMLF", "OTC"),
    (1094517, "TOYOTA MOTOR CORP/", "TM", "NYSE"),
    (1094517, "TOYOTA MOTOR CORP/", "TOYOF", "OTC"),
    (1594805, "SHOPIFY INC.", "SHOP", "Nasdaq"),
    (1321655, "Palantir Technologies Inc.", "PLTR", "Nasdaq"),
    # A bare "Apple" reaches three registrants by prefix, but matches exactly
    # one of them EXACTLY -- see the two tests about precedence below.
    (320193, "Apple Inc.", "AAPL", "Nasdaq"),
    (1418121, "Apple Hospitality REIT, Inc.", "APLE", "NYSE"),
    (1974994, "Apple iSports Group, Inc.", "AAPI", "OTC"),
    # "General" is nobody's whole registered name, so it can only ever be a
    # prefix -- of several unrelated companies.
    (40545, "GENERAL ELECTRIC CO", "GE", "NYSE"),
    (40704, "GENERAL MILLS INC", "GIS", "NYSE"),
    (40533, "GENERAL DYNAMICS CORP", "GD", "NYSE"),
]


@pytest.fixture
def sec_map():
    blob = json.dumps({"fields": ["cik", "name", "ticker", "exchange"],
                       "data": [list(r) for r in _ROWS]}).encode()
    return SecTickerMap.from_json_bytes(blob)


@pytest.mark.parametrize("typed,ticker,exchange", [
    ("Tesla", "TSLA", "Nasdaq"),
    ("NVIDIA", "NVDA", "Nasdaq"),
    ("Costco", "COST", "Nasdaq"),
    ("Adobe", "ADBE", "Nasdaq"),
    ("Datadog", "DDOG", "Nasdaq"),
    ("Cloudflare", "NET", "NYSE"),
    ("Shopify", "SHOP", "Nasdaq"),
    ("Palantir", "PLTR", "Nasdaq"),
])
def test_the_companies_the_registry_could_not_reach(sec_map, typed, ticker,
                                                    exchange):
    """The original bottleneck: eight companies, none of them in the registry."""
    got = resolve_listing(company_name=typed, sec_map=sec_map)
    assert got.status == PUBLIC_LISTING_RESOLVED, got.reason
    assert (got.ticker, got.exchange) == (ticker, exchange)
    assert got.cik and got.source == "SEC registrant table"


@pytest.mark.parametrize("typed,ticker,exchange,other", [
    ("ASML", "ASML", "Nasdaq", "ASMLF"),
    ("Toyota", "TM", "NYSE", "TOYOF"),
])
def test_a_foreign_issuer_resolves_to_its_real_exchange_not_the_otc_line(
        sec_map, typed, ticker, exchange, other):
    """Same company, two quotations. The choice changes the price series, so
    it is made explicitly and the discarded line stays visible."""
    got = resolve_listing(company_name=typed, sec_map=sec_map)
    assert (got.status, got.ticker, got.exchange) == (
        PUBLIC_LISTING_RESOLVED, ticker, exchange)
    assert other in [a["ticker"] for a in got.alternatives]


def test_a_name_reaching_several_companies_is_never_narrowed_silently(sec_map):
    """"General" is no registrant's whole name, so it reaches three unrelated
    companies by prefix alone. Picking the biggest is the guess this module
    exists to refuse."""
    got = resolve_listing(company_name="General", sec_map=sec_map)
    assert got.status == PUBLIC_LISTING_UNRESOLVED
    assert not got.ticker
    assert {c["ticker"] for c in got.candidates} == {"GE", "GIS", "GD"}


def test_an_exact_registered_name_wins_over_companies_that_merely_share_it(
        sec_map):
    """"Apple" IS Apple Inc.'s whole registered name once the legal form is
    dropped; the REIT and the iSports company only begin with the same word.
    Exact equality is the strongest signal short of a ticker, so refusing here
    would fail the common case to guard against a rarer one -- and the prefix
    branch never runs when an exact match exists.
    """
    got = resolve_listing(company_name="Apple", sec_map=sec_map)
    assert (got.status, got.ticker) == (PUBLIC_LISTING_RESOLVED, "AAPL")
    assert got.matched_name == "Apple Inc."


def test_an_unknown_company_is_not_called_private(sec_map):
    """THE BREAK PROOF. Stripe is not an SEC registrant. That is a fact about
    the lookup, and it must not be rendered as a fact about the company."""
    got = resolve_listing(company_name="Stripe", sec_map=sec_map)
    assert got.status == UNKNOWN
    assert got.status != PRIVATE
    assert not got.ticker


def test_private_is_only_asserted_when_the_identity_record_says_so(sec_map):
    got = resolve_listing(company_name="Stripe", sec_map=sec_map,
                          known_private=True)
    assert got.status == PRIVATE


def test_a_curated_listing_outranks_the_lookup(sec_map):
    """Sony's primary line is Tokyo, which the SEC table cannot express."""
    got = resolve_listing(company_name="Sony", sec_map=sec_map,
                          registry_listings=[{"exchange": "TSE",
                                              "ticker": "6758"}])
    assert (got.status, got.ticker, got.exchange) == (
        PUBLIC_LISTING_RESOLVED, "6758", "TSE")
    assert got.source == "curated entity registry"


def test_no_listing_source_is_unknown_rather_than_private():
    """A failed fetch must degrade to "we do not know", never to a claim."""
    got = resolve_listing(company_name="Tesla", sec_map=None)
    assert got.status == UNKNOWN
    assert got.status != PRIVATE


def test_a_broken_sec_payload_yields_an_empty_map_not_an_exception():
    assert len(SecTickerMap.from_json_bytes(b"not json")) == 0
    assert len(SecTickerMap.from_json_bytes(b'{"fields":[],"data":[]}')) == 0


@pytest.mark.parametrize("raw,expected", [
    ("Tesla, Inc.", "tesla"),
    ("NVIDIA CORP", "nvidia"),
    ("COSTCO WHOLESALE CORP /NEW", "costco wholesale new"),
    ("ASML HOLDING NV", "asml"),
])
def test_normalisation_drops_legal_form_and_nothing_else(raw, expected):
    assert normalize_company_name(raw) == expected


def test_matching_never_uses_edit_distance(sec_map):
    """A near-miss is a miss. "Tesle" must not reach Tesla."""
    assert resolve_listing(company_name="Tesle",
                           sec_map=sec_map).status == UNKNOWN
    assert resolve_listing(company_name="Nvidia Corpp",
                           sec_map=sec_map).status == UNKNOWN
