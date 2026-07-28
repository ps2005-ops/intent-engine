"""No empty finished-looking report, ever.

A report-shaped page with the findings removed is worse than no page: it reads
as "we analysed this company and there was nothing there", which is a claim
about the company rather than about what could be read. These tests drive a
company whose site refuses everything and assert the reader gets an honest
dead-end with real ways out.
"""
import email
import io
import urllib.error

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


def _one_thin_filing(url, timeout):
    """Sony's failure mode, reproduced: everything refuses automation except a
    single procedural document that says nothing about the business.

    Exactly one usable source is the interesting case. Zero is already handled
    by the total-failure page; one is what produced a confident report about a
    multinational on the strength of a filing cover sheet.
    """
    if url.rstrip("/").endswith("/about"):
        body = (b"<html><head><title>Form 6-K</title></head><body>"
                b"<p>Report of foreign private issuer furnished for the month "
                b"of May 2026 pursuant to the rules of the Exchange Act. This "
                b"report is incorporated by reference into the registration "
                b"statements of the registrant.</p></body></html>")
        return (200, {"content-type": "text/html"}, body, False)
    raise urllib.error.HTTPError(url, 403, "forbidden",
                                 email.message_from_string(""), None)


@pytest.fixture
def client(tmp_path):
    config = AppConfig(env="test", secret="s" * 40, demo_mode=True,
                       autorun_sources=True,
                       web_store_path=tmp_path / "web.jsonl",
                       fi_store_path=tmp_path / "fi.jsonl",
                       ci_store_path=tmp_path / "ci.jsonl")
    app = WebApp(config, transport=_one_thin_filing, resolver=False)
    c = Client(app)
    c.request("POST", "/demo")
    return c


def _run_thin(client):
    status, headers, _ = client.request(
        "POST", "/analyze",
        f"consent=on&csrf={client.csrf()}&company_name=Opaque Holdings"
        f"&website=https://opaque.example")
    assert status.startswith("303"), status
    run_id = headers["Location"].split("/runs/")[1].split("/")[0]
    return run_id, client.request("GET", f"/runs/{run_id}")


def test_thin_evidence_never_renders_a_strategic_dashboard(client):
    _, (status, _, page) = _run_thin(client)
    assert status.startswith("200")
    assert "Not enough public evidence" in page
    # none of the report furniture — a reader must not think they got a report
    for section in ("Strategic hypotheses", "Blind spots",
                    "Leadership questions", "Comparable patterns"):
        assert section not in page, f"report section rendered anyway: {section}"


def test_no_strategic_report_object_is_built_at_all(client):
    run_id, _ = _run_thin(client)
    result = client.app._results[run_id]
    assert result["strategic_report"] is None
    assert result["readiness"]["may_synthesize"] is False


def test_the_page_says_what_was_found_and_what_was_missing(client):
    _, (_, _, page) = _run_thin(client)
    assert "What was found" in page
    assert "What was missing" in page
    assert "What you can do" in page


def test_every_way_out_is_offered(client):
    _, (_, _, page) = _run_thin(client)
    assert "Run a fresh analysis" in page
    assert "Add an official source" in page
    assert "Correct the company" in page
    assert "Try a prepared company" in page


def test_missing_evidence_is_not_presented_as_a_claim_about_the_company(client):
    _, (_, _, page) = _run_thin(client)
    assert "statement about what could be read" in page


def test_the_page_uses_no_internal_state_names(client):
    _, (_, _, page) = _run_thin(client)
    for internal in ("INSUFFICIENT_EVIDENCE", "RETRYABLE_EVIDENCE_GAP",
                     "READY_FOR_FULL_REPORT", "may_synthesize",
                     "no_dominant_family", "family_counts", "IDENTITY"):
        assert internal not in page, f"leaked internal name: {internal}"


def test_retry_is_offered_only_when_somewhere_new_is_left_to_look(client):
    """A button that can only repeat itself is the worst kind of dead end,
    because it looks like progress."""
    run_id, (_, _, page) = _run_thin(client)
    offered = "Look again for the missing evidence" in page
    assert offered == client.app._has_untried_sources(run_id)


def test_retry_recomposes_and_returns_to_the_result(client):
    run_id, _ = _run_thin(client)
    status, headers, _ = client.request(
        "POST", f"/runs/{run_id}/retry", f"csrf={client.csrf()}")
    assert status.startswith("303")
    assert headers["Location"] == f"/runs/{run_id}"


def test_retry_does_not_manufacture_evidence_that_is_not_there(client):
    run_id, _ = _run_thin(client)
    before = len(client.app.ci.store.retrieved(run_id))
    client.request("POST", f"/runs/{run_id}/retry", f"csrf={client.csrf()}")
    after = client.app.ci.store.retrieved(run_id)
    assert len(after) == before
    assert client.app._results[run_id]["strategic_report"] is None


def test_retry_belongs_to_the_runs_owner(client, tmp_path):
    run_id, _ = _run_thin(client)
    other = Client(client.app)
    other.request("POST", "/demo")
    status, _, _ = other.request("POST", f"/runs/{run_id}/retry",
                                 f"csrf={other.csrf()}")
    assert status.startswith("404")
