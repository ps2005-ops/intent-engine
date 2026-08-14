"""A company the regulator names is a company we can identify.

FOUND LIVE. Typing "Toyota Motor Corporation" into the deployed product
returned "We could not identify Toyota Motor Corporation". So did "Toyota",
"Vale", and "Vale S.A.". The register consulted by typed entry is the
five-entity curated registry plus the hundred-company validation manifest --
about 105 companies -- so every other real firm on earth was NOT_FOUND.

Sixteen of the twenty-six companies the market engine publishes live
intelligence for could not be typed into the product that was analysing them.

This is the same defect as the profile-layer one, one layer up: a VALIDATION
universe used as the product's knowledge base, this time for identity.
"""
import pytest

from intent_engine.company_ingestion import name_entry as NE


@pytest.fixture
def registrant(monkeypatch):
    """The SEC ticker table, without the network.

    Real rows, so the token matching under test is the real matching.
    """
    rows = {
        "toyota motor corporation": {"cik": 1094517, "cik10": "0001094517",
                                     "title": "TOYOTA MOTOR CORP/",
                                     "ticker": "TM"},
        "toyota": {"cik": 1094517, "cik10": "0001094517",
                   "title": "TOYOTA MOTOR CORP/", "ticker": "TM"},
        "vale s.a.": {"cik": 917851, "cik10": "0000917851",
                      "title": "Vale S.A.", "ticker": "VALE"},
    }
    monkeypatch.setattr(NE, "_REGISTRANT_CACHE", {})
    monkeypatch.setattr(NE, "_REGISTRANT_LOOKUP_ENABLED", True)
    monkeypatch.setattr(
        NE, "_registrant",
        lambda name: rows.get(str(name or "").strip().lower()))
    return rows


def test_a_registrant_is_identified_not_refused(registrant):
    entry = NE.resolve(company_name="Toyota Motor Corporation")
    assert entry.state == NE.IDENTIFIED_NO_DOMAIN
    assert entry.ticker == "TM"
    assert entry.source == "SEC registrant table"


def test_the_filing_index_artifact_never_reaches_a_reader(registrant):
    """EDGAR titles end in a slash because the index path did."""
    entry = NE.resolve(company_name="Toyota Motor Corporation")
    assert not entry.company_name.endswith("/")
    assert entry.company_name == "TOYOTA MOTOR CORP"


def test_a_legal_name_keeps_its_own_punctuation(registrant):
    """Stripping the index artifact must not eat the name. A first pass
    stripped trailing periods too and put "Vale S.A" on the live page."""
    entry = NE.resolve(company_name="Vale S.A.")
    assert entry.company_name == "Vale S.A."


def test_identified_is_not_resolved(registrant):
    """`resolved` means "we can start the analysis", and we cannot: there is
    no domain. Conflating the two would send retrieval at the demo site."""
    entry = NE.resolve(company_name="Toyota Motor Corporation")
    assert entry.resolved is False
    assert entry.website == ""


def test_no_domain_is_ever_invented(registrant):
    """The whole module refuses to guess a domain, and the new source has
    the least information of any of them -- so it must refuse hardest."""
    for name in ("Toyota Motor Corporation", "Vale S.A."):
        assert NE.resolve(company_name=name).website == ""


def test_a_real_unknown_is_still_not_found(registrant):
    """The new source must not turn every string into a company."""
    entry = NE.resolve(company_name="Zzzq Nonexistent Widget Co")
    assert entry.state == NE.COMPANY_NOT_FOUND


def test_the_curated_sources_still_win(registrant):
    """The registrant table is last: it can say neither AMBIGUOUS nor a
    domain, and both are worth more than breadth."""
    entry = NE.resolve(company_name="Cloudflare")
    assert entry.state == NE.HIGH_CONFIDENCE_MATCH
    assert entry.source == "validation manifest"
    assert entry.website


# --- the refusal that matters ----------------------------------------------

def test_the_lookup_is_off_by_default():
    """No offline run or test suite may make an outbound call by surprise.

    Deliberately does NOT use the fixture: this asserts the module default.
    """
    assert NE._REGISTRANT_LOOKUP_ENABLED is False
    assert NE._registrant("Toyota Motor Corporation") is None


def test_enabling_is_explicit(monkeypatch):
    monkeypatch.setattr(NE, "_REGISTRANT_LOOKUP_ENABLED", False)
    NE.enable_registrant_lookup(True)
    assert NE._REGISTRANT_LOOKUP_ENABLED is True
    NE.enable_registrant_lookup(False)
    assert NE._REGISTRANT_LOOKUP_ENABLED is False
