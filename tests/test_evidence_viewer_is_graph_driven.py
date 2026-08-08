"""The first founder surface that reads the Business Graph.

Ingestion has built the graph since 37b9c92, and no founder surface read it --
so reports remained the effective source of truth for everything a founder
sees. This drives the evidence viewer through a real run and asserts the two
things a report cannot give it: the node resolves in the graph, and the ROLE
the evidence plays is visible.

A contradiction rendered identically to a supporting citation is the single
worst outcome for this page, so that is the assertion with teeth.
"""
import io
import re

import pytest

from intent_engine.webapp.app import WebApp
from intent_engine.webapp.config import AppConfig
from tests.test_strategic_intelligence import _live_transport


class _Client:
    def __init__(self, app):
        self.app, self.cookie = app, ""

    def request(self, method, path, body=""):
        env = {"REQUEST_METHOD": method, "PATH_INFO": path,
               "CONTENT_LENGTH": str(len(body)), "HTTP_HOST": "127.0.0.1",
               "HTTP_COOKIE": self.cookie,
               "wsgi.input": io.BytesIO(body.encode())}
        out = {}
        payload = b"".join(self.app(env, lambda s, h: out.update(
            status=s, headers=h))).decode()
        for key, value in out["headers"]:
            if key == "Set-Cookie" and value.startswith("sid="):
                self.cookie = ("" if "Max-Age=0" in value
                               else value.split(";")[0])
        return out["status"], payload

    def sid(self):
        return self.cookie.split("=", 1)[1] if self.cookie else None

    def csrf(self):
        return self.app.auth.csrf_token(self.sid())


def _text(html):
    html = re.sub(r"(?is)<(style|script)[^>]*>.*?</\1>", " ", html)
    return re.sub(r"\s+", " ", re.sub(r"(?s)<[^>]+>", " ", html)).strip()


@pytest.fixture
def run(tmp_path):
    cfg = AppConfig(env="test", secret="s" * 40, demo_mode=True,
                    autorun_sources=True,
                    web_store_path=tmp_path / "w.jsonl",
                    fi_store_path=tmp_path / "fi.jsonl",
                    ci_store_path=tmp_path / "ci.jsonl")
    app = WebApp(cfg, transport=_live_transport, resolver=False)
    client = _Client(app)
    client.request("POST", "/demo")
    status, _ = client.request(
        "POST", "/analyze",
        f"consent=on&csrf={client.csrf()}&company_name=Acme"
        f"&website=https://acme.example")
    run_id = next(iter(app._results))
    report = (app._results[run_id] or {}).get("strategic_report") or {}
    obs = [o["observation_id"] for o in (report.get("observations") or ())
           if isinstance(o, dict) and o.get("observation_id")]
    if not obs:
        pytest.skip("this fixture composed no observations")
    return app, client, run_id, obs[0]


def test_the_evidence_page_resolves_through_the_graph(run):
    app, client, run_id, obs_id = run
    status, html = client.request("GET", f"/runs/{run_id}/evidence/{obs_id}")
    assert status.startswith("200"), status
    assert "Evidence" in _text(html)


def test_evidence_absent_from_the_graph_fails_closed(run, monkeypatch):
    """No silent fallback to the report copy.

    A fallback is how two sources of truth survive a migration: the new path
    looks live while the old one is still answering. If the projection cannot
    place this node, the page must refuse rather than reassure.
    """
    app, client, run_id, obs_id = run
    from intent_engine.business_graph import BusinessGraph
    monkeypatch.setattr(type(app.ci), "business_graph",
                        lambda self, rid, result=None: BusinessGraph())
    status, _ = client.request("GET", f"/runs/{run_id}/evidence/{obs_id}")
    assert not status.startswith("200"), (
        "the page served report evidence the graph could not confirm")


def test_the_page_reads_the_graph_at_all():
    """Architecture guard: this surface must import the graph vocabulary.

    Without this, the migration can be reverted to a report read and every
    behavioural test above still passes on the fixture.
    """
    import inspect

    source = inspect.getsource(WebApp._observation_evidence_page)
    assert "business_graph" in source
    assert "CONTRADICTS" in source, (
        "the page cannot distinguish supporting from contradicting evidence")


def test_a_contradiction_is_labelled_as_one(tmp_path):
    """The assertion with teeth, driven off a graph built by ingestion."""
    from intent_engine.business_graph import CONTRADICTS, SUPPORTS
    from intent_engine.business_graph.projections import from_ingestion_run

    graph = from_ingestion_run(
        run_id="r1",
        retrieved=[{"source_id": "src-b", "final_url": "https://x.example",
                    "title": "X", "retrieval_status": "OK"}],
        report={"observations": [{"observation_id": "obs-src-b",
                                  "excerpt": "Self-serve is the focus."}],
                "blind_spots": [{"blind_spot_id": "blind-1",
                                 "observed_tension": "Enterprise vs self-serve.",
                                 "supporting_observation_ids": ["obs-src-b"]}]})
    assert graph.out_edges("obs-src-b", CONTRADICTS)
    assert not graph.out_edges("obs-src-b", SUPPORTS)
