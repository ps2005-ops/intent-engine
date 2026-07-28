"""The disambiguation step, through the real web app.

A name like "Sony" names a family of companies. Choosing one silently produces
a confident report about the wrong entity; asking costs one click and is the
only honest option. These tests prove the question is asked, that nothing runs
until it is answered, and that the answer is respected.
"""
import io

import pytest

from intent_engine.webapp.app import WebApp
from intent_engine.webapp.config import AppConfig


class Client:
    def __init__(self, app):
        self.app, self.cookie = app, ""

    def request(self, method, path, body=""):
        env = {"REQUEST_METHOD": method, "PATH_INFO": path,
               "CONTENT_LENGTH": str(len(body)), "HTTP_HOST": "127.0.0.1",
               "HTTP_COOKIE": self.cookie,
               "wsgi.input": io.BytesIO(body.encode())}
        out = {}

        def sr(status, headers):
            out["status"], out["headers"] = status, headers
        payload = b"".join(self.app(env, sr)).decode()
        for k, v in out["headers"]:
            if k == "Set-Cookie" and v.startswith("sid="):
                self.cookie = "" if "Max-Age=0" in v else v.split(";")[0]
        return out["status"], dict(out["headers"]), payload

    def sid(self):
        return self.cookie.split("=", 1)[1] if self.cookie else None

    def csrf(self):
        return self.app.auth.csrf_token(self.sid())


def _no_network(url, timeout):
    raise OSError("test transport: network disabled")


@pytest.fixture
def client(tmp_path):
    config = AppConfig(env="test", secret="s" * 40, demo_mode=True,
                       autorun_sources=False,
                       web_store_path=tmp_path / "web.jsonl",
                       fi_store_path=tmp_path / "fi.jsonl",
                       ci_store_path=tmp_path / "ci.jsonl")
    app = WebApp(config, transport=_no_network, resolver=False)
    c = Client(app)
    c.request("POST", "/demo")
    return c


def _analyze(client, body):
    return client.request("POST", "/analyze",
                          f"consent=on&csrf={client.csrf()}&{body}")


def test_ambiguous_name_asks_instead_of_guessing(client):
    status, _, page = _analyze(
        client, "company_name=Sony&website=https://example.invalid")
    assert status.startswith("200")
    assert "Which company do you mean?" in page
    assert "Sony Group Corporation" in page
    assert "Sony Interactive Entertainment LLC" in page
    assert "Sony Electronics Inc." in page


def test_nothing_is_analysed_until_the_question_is_answered(client):
    _analyze(client, "company_name=Sony&website=https://example.invalid")
    # no run was created, so nothing was fetched and nothing was owned
    assert client.app.ci.store.read_all() == []


def test_the_choice_page_speaks_business_facts_not_identifiers(client):
    _, _, page = _analyze(
        client, "company_name=Sony&website=https://example.invalid")
    assert "Japan" in page
    assert "TSE: 6758" in page and "NYSE: SONY" in page
    # internal ids exist in the form values but are never shown as prose
    assert "entity_id" not in page.replace('name="entity_id"', "")
    assert "AMBIGUOUS" not in page


def test_choosing_the_parent_runs_against_sony_group(client):
    status, headers, _ = _analyze(client, "entity_id=sony-group")
    assert status.startswith("303"), status
    run_id = headers["Location"].split("/runs/")[1].rsplit("/sources", 1)[0]
    meta = client.app.ci.run_meta(run_id)
    assert meta["company_name"] == "Sony Group Corporation"
    assert "sony.com" in meta["website"]
    identity = client.app.ci.entity_identity(run_id)
    assert identity["canonical_legal_name"] == "Sony Group Corporation"


def test_choosing_a_subsidiary_runs_against_that_subsidiary(client):
    status, headers, _ = _analyze(
        client, "entity_id=sony-interactive-entertainment")
    assert status.startswith("303"), status
    run_id = headers["Location"].split("/runs/")[1].rsplit("/sources", 1)[0]
    identity = client.app.ci.entity_identity(run_id)
    assert identity["canonical_legal_name"] == \
        "Sony Interactive Entertainment LLC"
    assert identity["parent_entity_id"] == "sony-group"


def test_an_unambiguous_company_is_never_interrupted(client):
    status, headers, _ = _analyze(
        client, "company_name=Palantir&website=https://www.palantir.com")
    assert status.startswith("303"), status
    assert "/sources" in headers["Location"]


def test_a_registry_website_settles_the_name_without_asking(client):
    # typed the ambiguous common name, but gave the group's own domain
    status, headers, _ = _analyze(
        client, "company_name=Sony&website=https://www.sony.com")
    assert status.startswith("303"), status
    run_id = headers["Location"].split("/runs/")[1].rsplit("/sources", 1)[0]
    identity = client.app.ci.entity_identity(run_id)
    assert identity["entity_id"] == "sony-group"


def test_an_unknown_company_is_not_blocked_by_the_registry(client):
    status, headers, _ = _analyze(
        client, "company_name=Brightlake&website=https://brightlake.example")
    assert status.startswith("303"), status
    run_id = headers["Location"].split("/runs/")[1].rsplit("/sources", 1)[0]
    identity = client.app.ci.entity_identity(run_id)
    assert identity["entity_resolved"] is False
    assert identity["status"] == "UNKNOWN"
