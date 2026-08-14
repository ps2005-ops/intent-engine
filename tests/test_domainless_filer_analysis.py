"""A company the regulator names must be analysable without a website.

WHERE THIS CAME FROM. Typed entry was taught to resolve any SEC registrant,
which turned "We could not identify Toyota Motor Corporation" into "We found
TOYOTA MOTOR CORP (TM)" -- and then the run could not be opened, because
`create_run` required a URL. The company was identified and still unusable.

Guessing `toyota.com` was never an option: whatever sits on a guessed domain
gets retrieved and reported under this company's name. What the regulator
does record is every filing the company has made, and for a foreign private
issuer the 20-F is a more authoritative account of the business than the
marketing site would have been.
"""
import pathlib
import tempfile

import pytest

from intent_engine.company_ingestion.service import (CompanyIngestionService,
                                                     IngestionError)


@pytest.fixture
def service():
    path = pathlib.Path(tempfile.mkdtemp()) / "ci.jsonl"
    return CompanyIngestionService(path=path)


@pytest.fixture
def no_edgar(monkeypatch):
    """Discovery without the network. The EDGAR adapter is exercised
    separately; these tests are about the run, not the fetch."""
    import intent_engine.company_ingestion.service as S
    monkeypatch.setattr(S, "propose_edgar_candidates", lambda **kw: [])
    return None


# --- the run opens ---------------------------------------------------------

def test_a_filer_run_opens_with_no_website(service):
    run = service.create_run(company_name="TOYOTA MOTOR CORP", website="",
                             cik="1094517", user_id="u1", as_of="2026-08-14")
    assert run["run_id"]
    assert run["cik"] == "1094517"


def test_no_domain_is_invented(service):
    """Substituting `sec.gov` would make the REGULATOR this company's
    website: its filings would group as company-published material from the
    sec.gov origin, and every filer on earth would share one origin."""
    run = service.create_run(company_name="TOYOTA MOTOR CORP", website="",
                             cik="1094517", user_id="u1", as_of="2026-08-14")
    assert run["domain"] == ""
    assert run["website"] == ""
    meta = service.run_meta(run["run_id"])
    assert meta["domain"] == ""
    assert meta["website"] == ""


def test_two_domainless_companies_are_two_runs(service):
    """The run id was keyed on the domain. With no domain both companies key
    on the empty string, so Toyota and Vale would have shared a run on any
    given day and merged one company's filings into the other's evidence."""
    toyota = service.create_run(company_name="TOYOTA MOTOR CORP", website="",
                                cik="1094517", user_id="u1",
                                as_of="2026-08-14")
    vale = service.create_run(company_name="Vale S.A.", website="",
                              cik="917851", user_id="u1", as_of="2026-08-14")
    assert toyota["run_id"] != vale["run_id"]
    assert toyota["subject_key"] == "sec-cik:1094517"
    assert vale["subject_key"] == "sec-cik:917851"


def test_a_run_with_neither_website_nor_cik_is_refused(service):
    """There is no subject to retrieve. Refusing is the honest answer; a run
    that opens on nothing produces an empty analysis of no company."""
    with pytest.raises(IngestionError):
        service.create_run(company_name="Nobody Ltd", website="", cik="",
                           user_id="u1", as_of="2026-08-14")


# --- the run does not fabricate a failure ----------------------------------

def test_no_homepage_failure_for_a_run_with_no_homepage(service, no_edgar):
    """A run that never requested a homepage has no homepage outcome.
    Recording a retrieval FAILURE would put a fabricated failure in the
    company's own record and count against its source health."""
    run = service.create_run(company_name="TOYOTA MOTOR CORP", website="",
                             cik="1094517", user_id="u1", as_of="2026-08-14")
    service.discover(run["run_id"])
    rows = [r for r in service.store.for_run(run["run_id"])
            if r.event_type == "ci.retrieval_failed"]
    assert rows == []


def test_the_identity_is_resolved_by_the_cik(service, no_edgar):
    """A CIK identifies exactly one filer -- more precisely than a domain,
    which is bought and resold. Without this the company was identified at
    the door and declared unidentified one step later."""
    run = service.create_run(company_name="TOYOTA MOTOR CORP", website="",
                             cik="1094517", user_id="u1", as_of="2026-08-14")
    service.discover(run["run_id"])
    identity = service.entity_identity(run["run_id"])
    assert identity.get("fallback_cik") == "1094517" or \
        identity.get("entity_resolved")


# --- the EDGAR adapter -----------------------------------------------------

def test_a_known_cik_is_not_re_resolved_by_name(monkeypatch):
    """Name matching is fuzzy. A second resolution that lands on a different
    registrant would attribute one company's filings to another, so a run
    that already knows its filer must never look it up again."""
    import intent_engine.company_ingestion.edgar as E
    called = []
    monkeypatch.setattr(E, "resolve_cik",
                        lambda *a, **k: called.append(a) or None)
    monkeypatch.setattr(E, "filing_candidates",
                        lambda resolved, **k: [{"cik10": resolved["cik10"]}])
    out = E.propose_edgar_candidates(company_name="TOYOTA MOTOR CORP",
                                     cik="1094517")
    assert called == []
    assert out[0]["cik10"] == "0001094517"


def test_without_a_cik_the_name_is_still_used(monkeypatch):
    import intent_engine.company_ingestion.edgar as E
    monkeypatch.setattr(E, "resolve_cik",
                        lambda *a, **k: {"cik": 1, "cik10": "0000000001",
                                         "title": "X", "ticker": "X"})
    monkeypatch.setattr(E, "filing_candidates",
                        lambda resolved, **k: [{"cik10": resolved["cik10"]}])
    out = E.propose_edgar_candidates(company_name="Anything")
    assert out[0]["cik10"] == "0000000001"


def test_the_adapter_never_raises(monkeypatch):
    """Discovery must never break because of this adapter."""
    import intent_engine.company_ingestion.edgar as E

    def boom(*a, **k):
        raise RuntimeError("SEC is down")

    monkeypatch.setattr(E, "filing_candidates", boom)
    assert E.propose_edgar_candidates(company_name="X", cik="1094517") == []
