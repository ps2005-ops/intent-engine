"""Live demo reliability — the failures a real first-time visitor hit.

Every test here reproduces something MEASURED on the deployed service at
eb18371, not something imagined. An external tester on a phone typed "Meta",
was told "This analysis could not be completed, so there is no result to
open", and then found the finished analysis by clicking "Your analyses". The
run had retrieved five sources, including Meta's own 10-K and 10-Q, and a
readable result existed at /runs/<id> the entire time.

Thousands of unit tests passed while that shipped, because each subsystem was
correct on its own: the worker composed a bounded result, the store kept it,
/runs/<id> rendered it. Only the seam between "the run's last transition" and
"is there something to show this person" was wrong, and nothing owned it.
"""
from __future__ import annotations

import io

import pytest

from intent_engine.webapp.app import WebApp
from intent_engine.webapp.config import AppConfig
from intent_engine.webapp.storage_state import record_boot


class Client:
    def __init__(self, app):
        self.app = app
        self.cookie = ""

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


def _no_network(url, timeout):
    raise OSError("test transport: network disabled")


@pytest.fixture
def app(tmp_path):
    # demo_mode ON, because that is what the deployed preview runs and this
    # file is about what a guest actually meets there.
    config = AppConfig(env="test", secret="s" * 40, demo_mode=True,
                       web_store_path=tmp_path / "web.jsonl",
                       fi_store_path=tmp_path / "fi.jsonl",
                       ci_store_path=tmp_path / "ci.jsonl")
    record_boot(tmp_path, boot_id="previous-process-boot")
    application = WebApp(config, transport=_no_network, resolver=False)
    application.auth.create_user("founder@example.com", "password123")
    return application


def _login(client):
    status, _, _ = client.request(
        "POST", "/login", "email=founder@example.com&password=password123")
    assert status.startswith("303")
    return client.app.auth.csrf_token(client.sid())


def _failed_run_holding_a_result(app, client):
    """A run whose last transition is FAILED but which HAS a readable result.

    This is not a contrived state. `_run_analysis` produces it deliberately:
    when composition raises it marks the run FAILED and then stores a bounded
    reading, precisely so a company with usable evidence is not thrown away.
    """
    run = app.ci.create_run(company_name="Testco",
                            website="https://testco.example",
                            user_id=app.auth.session(client.sid())["user_id"],
                            as_of="2026-08-17")
    run_id = run["run_id"] if isinstance(run, dict) else run
    user_id = app.auth.session(client.sid())["user_id"]
    from intent_engine.webapp.store import WebEvent
    app.web_store.append(WebEvent(
        event_type="web.run_owned", actor_type="human", actor_id=user_id,
        subject_type="run", subject_id=run_id,
        idempotency_key=f"own:{run_id}", payload={"user_id": user_id}))
    app.ci._transition(run_id, "testco.example", "FAILED")
    app._results[run_id] = {"run_id": run_id, "status": "PARTIAL",
                            "sections": [{"kind": "company_understanding",
                                          "claims": []}]}
    return run_id


# ===========================================================================
# the exact failure the external tester saw
# ===========================================================================
def test_a_result_that_exists_is_never_reported_as_a_failure(app,
                                                             monkeypatch):
    """§2, §4. THE friend test.

    Before the repair `_progress` branched on the run's state and rendered
    "This analysis could not be completed, so there is no result to open"
    for exactly this run — while /runs/<id> rendered the analysis.
    """
    c = Client(app)
    _login(c)
    run_id = _failed_run_holding_a_result(app, c)
    monkeypatch.setattr(app, "_retrieved_documents",
                        lambda rid: [{"final_url": "https://testco.example",
                                      "title": "Testco"}])

    readiness = app.result_readiness(run_id)
    assert readiness["opens_result"] is True, readiness
    assert readiness["state"] in app.READY_OPENS_RESULT, readiness

    status, headers, body = c.request("GET", f"/runs/{run_id}/progress")
    assert status.startswith("303"), (status, body[:400])
    assert headers["Location"].endswith(f"/runs/{run_id}"), headers
    assert "could not be completed" not in body.lower()


def test_only_a_final_failure_may_show_a_final_failure(app, monkeypatch):
    """§2. FAILED_FINAL is the one state allowed to say the analysis died."""
    c = Client(app)
    _login(c)
    run_id = _failed_run_holding_a_result(app, c)
    monkeypatch.setattr(app, "_retrieved_documents", lambda rid: [])
    app._results.pop(run_id, None)
    # Exhaust the retries so this is genuinely terminal rather than
    # recoverable — a run with an attempt left is not a final failure.
    app._analysis_attempts[run_id] = app.MAX_ANALYSIS_ATTEMPTS

    readiness = app.result_readiness(run_id)
    assert readiness["state"] == app.READY_FAILED, readiness
    assert readiness["opens_result"] is False

    _, _, body = c.request("GET", f"/runs/{run_id}/progress")
    assert "could not be completed" in body.lower()


def test_an_interrupted_run_is_recoverable_not_dead(app, monkeypatch):
    """§7. "No result yet" and "this is over" are different sentences.

    A worker that vanished (a free-instance restart) is the case where one
    more attempt genuinely runs.
    """
    c = Client(app)
    _login(c)
    run_id = _failed_run_holding_a_result(app, c)
    monkeypatch.setattr(app, "_retrieved_documents", lambda rid: [])
    app._results.pop(run_id, None)
    app.ci._transition(run_id, "testco.example", "INTERRUPTED")

    readiness = app.result_readiness(run_id)
    assert readiness["state"] == app.READY_BLOCKED, readiness
    assert readiness["retryable"] is True


def test_a_run_whose_sources_all_refused_is_not_offered_a_retry(app,
                                                                monkeypatch):
    """§54. A retry that dials the same refusing hosts is a recovery loop.

    403 and 404 are recorded `retryable=False` by the retrieval layer. Reading
    "state == FAILED" instead would put a button in front of a customer that
    cannot work, and manual recoveries must be zero.
    """
    c = Client(app)
    _login(c)
    run_id = _failed_run_holding_a_result(app, c)
    monkeypatch.setattr(app, "_retrieved_documents", lambda rid: [])
    app._results.pop(run_id, None)
    monkeypatch.setattr(app.ci.store, "failures",
                        lambda rid: [{"failure_type": "http_403",
                                      "retryable": False}])

    readiness = app.result_readiness(run_id)
    assert readiness["state"] == app.READY_FAILED, readiness
    assert readiness["retryable"] is False


def test_a_degraded_result_still_opens_the_analysis(app, monkeypatch):
    """§2, §29. An evidence gap may not be converted into a technical
    failure. A bounded reading is what the run established."""
    c = Client(app)
    _login(c)
    run_id = _failed_run_holding_a_result(app, c)
    monkeypatch.setattr(app, "_retrieved_documents",
                        lambda rid: [{"final_url": "https://testco.example"}])
    app._results[run_id] = {"run_id": run_id, "status": "FAILED"}

    readiness = app.result_readiness(run_id)
    assert readiness["state"] == app.READY_DEGRADED, readiness
    assert readiness["opens_result"] is True
    assert readiness["degraded"] is True


def test_progress_never_says_every_source_failed_when_some_were_read(
        app, monkeypatch):
    """MEASURED. Meta read five sources and was told every one had failed.

    The word "every" was printed whenever ANY source failed; the count that
    would have contradicted it was one call away and was never made.
    """
    c = Client(app)
    _login(c)
    run_id = _failed_run_holding_a_result(app, c)
    monkeypatch.setattr(app, "_retrieved_documents",
                        lambda rid: [{"final_url": "https://a.example"},
                                     {"final_url": "https://b.example"}])
    monkeypatch.setattr(app, "_failure_rows",
                        lambda rid: [("cand-1", "too large", "big", "")])

    text = app._failure_explanation(run_id, True)
    assert "every approved source failed" not in text.lower(), text
    assert "2 were read" in text, text


# ===========================================================================
# the flow itself
# ===========================================================================
def test_the_landing_page_does_not_ask_for_a_company(app):
    """§8. The first screen sells; it does not put the visitor to work."""
    c = Client(app)
    _, _, body = c.request("GET", "/")
    assert 'name="company_name"' not in body, "landing still carries the form"
    assert 'action="/analyze"' not in body
    assert "/login" in body
    assert 'action="/demo"' in body


def test_the_landing_page_offers_exactly_two_next_steps(app):
    """§10, §48. Nothing else may compete with the demo CTA."""
    c = Client(app)
    _, _, body = c.request("GET", "/")
    assert "Try the demo" in body
    assert "Log in" in body
    for jargon in ("market bridge", "snapshot", "guest-session",
                   "learning metrics"):
        assert jargon not in body.lower(), jargon


def test_try_the_demo_lands_on_the_company_question(tmp_path):
    """§10. The button must reach the field, not loop back to the pitch."""
    config = AppConfig(env="test", secret="s" * 40, demo_mode=True,
                       web_store_path=tmp_path / "web.jsonl",
                       fi_store_path=tmp_path / "fi.jsonl",
                       ci_store_path=tmp_path / "ci.jsonl")
    record_boot(tmp_path, boot_id="previous-process-boot")
    app = WebApp(config, transport=_no_network, resolver=False)
    c = Client(app)
    status, headers, _ = c.request("POST", "/demo", "")
    assert status.startswith("303")
    assert headers["Location"] == "/demo", headers
    status, _, body = c.request("GET", "/demo")
    assert status == "200 OK"
    assert 'name="company_name"' in body


def test_the_progress_page_does_not_send_the_customer_to_your_analyses(
        app, monkeypatch):
    """§5. "Your analyses" is not a recovery instruction.

    That link is how the external tester eventually found their result, and
    needing it at all is the defect.
    """
    c = Client(app)
    _login(c)
    run_id = _failed_run_holding_a_result(app, c)
    app.ci._transition(run_id, "testco.example", "FETCHING_APPROVED_SOURCES")
    app._results.pop(run_id, None)
    monkeypatch.setattr(app, "_retrieved_documents", lambda rid: [])

    _, _, body = c.request("GET", f"/runs/{run_id}/progress")
    main = body.split("<main>", 1)[-1]
    assert "/analyses" not in main, "progress page still routes to /analyses"
    assert "building the analysis" in main.lower()


# ===========================================================================
# retrieval: the third-party vantage point
# ===========================================================================
def test_a_third_party_filing_is_fetched_against_the_filing_budget():
    """MEASURED on Meta. Every third-party filing came back "too large".

    These candidates carried no byte budget at all, so retrieval fell back to
    the 2MB cap meant for an arbitrary untrusted host — and every one of them
    is a 10-K on sec.gov, the publisher whose real document sizes are the
    reason MAX_FILING_BYTES exists. The only source class independent of the
    subject was being discarded by a default.
    """
    from intent_engine.company_ingestion import third_party_filings as TPF
    from intent_engine.company_ingestion.edgar import MAX_FILING_BYTES

    candidate = {"url": "https://www.sec.gov/Archives/edgar/data/1/x/a.htm",
                 "filer": "Rival Inc.", "filer_cik": "1", "form": "10-K",
                 "file_date": "2026-01-01"}
    emitted = TPF._emit(candidate, company_name="Testco",
                        assessment={"relevance": "HIGH", "reason": "r",
                                    "excerpt": "e", "substantive_mentions": 2})
    assert emitted["max_bytes"] == MAX_FILING_BYTES
    assert emitted["accept_truncated"] is True
