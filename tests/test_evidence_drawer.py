"""The drawer that shows a buyer what the reading rests on.

It renders records that already cross the bridge. It must not recompute
independence or relevance -- two opinions about one document is how a drawer
and a count start disagreeing -- and it must not leak the identifiers the
projection was built to withhold.

The grouping is the design: sources are shown by WHAT THEY ARE WORTH. A flat
bibliography of eleven documents hides the only fact that matters about this
company's evidence, which is that none of them is an outside voice with
anything to say.
"""
import io
import json

import pytest

from intent_engine.company_ingestion import relevance as REL
from intent_engine.demo_dossier.dossier import CompanyDemoDossier
from intent_engine.webapp.app import WebApp
from intent_engine.webapp.config import AppConfig
from intent_engine.webapp.storage_state import record_boot


def _record(**kw):
    base = {
        "provenance_id": "prv_1", "title": "A source", "url": "https://x.test/a",
        "author": "Somebody", "host": "x.test", "subject": "Cloudflare",
        "self_authored": False, "source_class": "competitor",
        "evidence_type": "FILING", "published_at": "2026-01-01",
        "retrieved_at": "2026-08-15", "freshness": "FRESH",
        "lineage": "INDEPENDENT_EXTERNAL_SOURCE",
        "independence_bearing": True, "independent_voice": True,
        "relevance": REL.DIRECTLY_RELEVANT, "relevance_reason": "discusses it",
        "relevance_statement": "Discusses the company directly",
        "origin_group": "x.test", "passage": "It competes with Cloudflare.",
        "plain_statement": "Third-party reporting",
        "visibility": "PROVENANCE_AVAILABLE",
    }
    base.update(kw)
    return base


OWN = _record(provenance_id="prv_own", title="Cloudflare 10-K",
              author="Cloudflare", host="www.sec.gov", self_authored=True,
              independent_voice=False, independence_bearing=False,
              lineage="COMPANY_SELF_REPORT",
              plain_statement="A filing the company wrote about itself, "
                              "hosted by the SEC",
              url="https://www.sec.gov/Archives/edgar/data/1477333/x.htm")

SET_ASIDE = _record(
    provenance_id="prv_evk", title="EVENTIKO INC. 10-K",
    author="SEC filer 1816554", host="www.sec.gov",
    independence_bearing=False, independent_voice=True,
    relevance=REL.IRRELEVANT,
    relevance_reason="named once, only as an example in the author's account "
                     "of its own arrangements",
    relevance_statement="Independent of the company, but it does not say "
                        "enough about it to support this claim",
    plain_statement="A regulatory filing written by another company, hosted "
                    "by the SEC",
    url="https://www.sec.gov/Archives/edgar/data/1816554/x.htm")


class Client:
    def __init__(self, app):
        self.app = app

    def get(self, path):
        path, _, query = path.partition("?")
        env = {"REQUEST_METHOD": "GET", "PATH_INFO": path,
               "QUERY_STRING": query, "CONTENT_LENGTH": "0",
               "HTTP_HOST": "127.0.0.1", "HTTP_COOKIE": "",
               "wsgi.input": io.BytesIO(b"")}
        out = {}

        def sr(status, headers):
            out["status"] = status
        body = b"".join(self.app(env, sr)).decode()
        return out["status"], body


@pytest.fixture
def app(tmp_path):
    config = AppConfig(env="test", secret="s" * 40,
                       web_store_path=tmp_path / "w.jsonl",
                       fi_store_path=tmp_path / "f.jsonl",
                       ci_store_path=tmp_path / "c.jsonl", demo_mode=True)
    record_boot(tmp_path, boot_id="prev")
    return WebApp(config, transport=lambda u, t: None, resolver=False)


def _store(app, records, *, state="PROVENANCE_AVAILABLE", reason=""):
    store = app._demo_dossier_store()
    dossier = CompanyDemoDossier(
        company_id="cloudflare", canonical_name="Cloudflare",
        founder_block={"availability": "AVAILABLE",
                       "claim_provenance": {"state": state, "reason": reason,
                                            "records": records}})
    store.save(dossier)
    return dossier


def test_the_drawer_groups_sources_by_what_they_are_worth(app):
    _store(app, [OWN, SET_ASIDE])
    status, body = Client(app).get("/demo-dossiers/cloudflare/evidence")
    assert status.startswith("200"), status
    assert "Independent, but not relevant here" in body
    assert "Written by the company itself" in body
    # nothing supports the reading, and the page says so in a number
    assert "<strong>0</strong> of 2" in body


def test_a_set_aside_source_is_shown_not_hidden(app):
    """A source the system refused to count is more informative than a
    source it never mentions. This is the product's best demonstration that
    it does not overstate its own evidence."""
    _store(app, [OWN, SET_ASIDE])
    _, body = Client(app).get("/demo-dossiers/cloudflare/evidence")
    assert "EVENTIKO" in body
    assert "does not say enough about it" in body
    assert "Independent voice: yes" in body
    assert "Counts as corroboration: no" in body


def test_the_zero_is_reported_as_a_limit_of_our_search(app):
    """FOUND_NONE vs FAILED_TO_FIND. Discovery coverage is not measured, so
    a zero must read as OUR limit, never as a finding about the company."""
    _store(app, [OWN, SET_ASIDE])
    _, body = Client(app).get("/demo-dossiers/cloudflare/evidence")
    assert REL.FAILED_TO_FIND in body
    assert "limit of what we retrieved" in body
    assert "found none" not in body.lower()


def test_a_supporting_source_moves_the_headline(app):
    _store(app, [OWN, SET_ASIDE, _record()])
    _, body = Client(app).get("/demo-dossiers/cloudflare/evidence")
    assert "<strong>1</strong> of 3" in body
    assert "Independent and relevant" in body
    # with support present there is no zero-reading sentence to render
    assert "limit of what we retrieved" not in body


def test_the_drawer_leaks_no_identifier(app):
    leaky = _record(provenance_id="prv_x")
    _store(app, [leaky])
    _, body = Client(app).get("/demo-dossiers/cloudflare/evidence")
    for bad in ("source_id", "src_", "tenant", "content_hash", "run_id"):
        assert bad not in body, bad


def test_an_absent_projection_is_a_state_not_no_sources(app):
    """"No sources" would be a claim about the company. The page says what
    is actually true, which is that the projection is missing."""
    _store(app, [], state="PROVENANCE_UNAVAILABLE",
           reason="no documents were retrieved for this company")
    status, body = Client(app).get("/demo-dossiers/cloudflare/evidence")
    assert status.startswith("200")
    assert "PROVENANCE_UNAVAILABLE" in body
    assert "no documents were retrieved" in body


def test_an_unknown_company_says_which_absence_it_is(app):
    status, body = Client(app).get("/demo-dossiers/nosuch/evidence")
    assert status.startswith("404")
    assert "no analysis is stored here" in body.lower()


def test_the_drawer_recomputes_nothing(app):
    """It renders the crossed verdicts. If it decided independence itself the
    drawer and the count would eventually disagree, and only one of them is
    what the customer reads."""
    lying = _record(independence_bearing=False, independent_voice=True,
                    relevance=REL.DIRECTLY_RELEVANT)
    _store(app, [lying])
    _, body = Client(app).get("/demo-dossiers/cloudflare/evidence")
    # honours the crossed `independence_bearing`, not its own reading of
    # the DIRECTLY_RELEVANT verdict beside it
    assert "<strong>0</strong> of 1" in body


def test_every_decision_surface_links_to_the_drawer(app):
    """A drawer nobody can reach is not a drawer."""
    import inspect

    source = inspect.getsource(WebApp._decision_screen)
    assert source.count("/evidence") >= 3
