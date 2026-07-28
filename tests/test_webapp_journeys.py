"""V1.0.1 — end-to-end journeys over the WSGI app (in-process, no sockets).

The required journey: landing → login → start demo run → progress →
result → evidence → follow-up → share → revoke → logout → protected page
inaccessible. Plus isolation, error states, expired share, viewport,
labels, and safe error pages.
"""
import io
import re

import pytest

from intent_engine.webapp.app import WebApp
from intent_engine.webapp.config import AppConfig


class Client:
    def __init__(self, app, default_host="127.0.0.1"):
        self.app = app
        self.cookie = ""
        self.default_host = default_host

    def request(self, method, path, body="", host=None):
        host = host or self.default_host
        env = {"REQUEST_METHOD": method, "PATH_INFO": path,
               "CONTENT_LENGTH": str(len(body)), "HTTP_HOST": host,
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
    clock = {"t": 1000.0}
    config = AppConfig(env="test", secret="s" * 40,
                       web_store_path=tmp_path / "web.jsonl",
                       fi_store_path=tmp_path / "fi.jsonl",
                       ci_store_path=tmp_path / "ci.jsonl")
    application = WebApp(config, now_fn=lambda: clock["t"],
                         transport=_no_network, resolver=False)
    application._clock = clock
    application.auth.create_user("founder@example.com", "password123")
    application.auth.create_user("other@example.com", "password456")
    return application


def _login(client, email="founder@example.com", password="password123"):
    status, headers, _ = client.request(
        "POST", "/login", f"email={email}&password={password}")
    assert status.startswith("303")
    return client.app.auth.csrf_token(client.sid())


def _run_demo(client, csrf):
    status, headers, _ = client.request(
        "POST", "/analyze",
        f"consent=on&csrf={csrf}&website=https://northwind-demo.example")
    assert status.startswith("303")
    return headers["Location"].rsplit("/progress", 1)[0]


def test_full_required_journey(app):
    c = Client(app)
    # landing
    status, _, body = c.request("GET", "/")
    assert status == "200 OK" and "/login" in body
    assert "width=device-width" in body            # mobile viewport
    # login
    csrf = _login(c)
    # start demo run → progress
    run_url = _run_demo(c, csrf)
    status, _, body = c.request("GET", run_url + "/progress")
    assert status == "200 OK" and "COMPLETE" in body
    # result — Company Understanding present, no company score
    status, _, body = c.request("GET", run_url)
    assert status == "200 OK"
    assert "no overall company score" in body.lower()
    # evidence for a real claim id from the page
    claim_id = body.split("/evidence/")[1].split('"')[0]
    status, _, body = c.request("GET", f"{run_url}/evidence/{claim_id}")
    assert status == "200 OK" and "replay" in body
    # follow-up conversation is cited
    status, _, body = c.request(
        "POST", run_url + "/conversation",
        f"csrf={csrf}&question=why do you think this?")
    assert status == "200 OK" and "Cited artifacts" in body
    # share → link works → revoke → link dead
    status, _, body = c.request("POST", run_url + "/share", f"csrf={csrf}")
    token = body.split("/shared/")[1].split("<")[0]
    token_hash = body.split('name="token_hash" value="')[1].split('"')[0]
    anon = Client(app)
    status, headers, _ = anon.request("GET", f"/shared/{token}")
    assert status == "200 OK"
    assert headers.get("X-Robots-Tag") == "noindex, nofollow"
    status, _, _ = c.request("POST", run_url + "/share/revoke",
                             f"csrf={csrf}&token_hash={token_hash}")
    status, _, _ = anon.request("GET", f"/shared/{token}")
    assert status.startswith("404")
    # logout → protected page inaccessible
    c.request("POST", "/logout", f"csrf={csrf}")
    status, headers, _ = c.request("GET", run_url)
    assert status.startswith("303") and headers["Location"] == "/login"


def test_cross_user_isolation(app):
    a, b = Client(app), Client(app)
    csrf_a = _login(a)
    run_url = _run_demo(a, csrf_a)
    csrf_b = _login(b, "other@example.com", "password456")
    # B cannot view A's run, evidence, report, or conversation
    for path in (run_url, run_url + "/report", run_url + "/progress"):
        status, _, _ = b.request("GET", path)
        assert status.startswith("404")
    status, _, _ = b.request("POST", run_url + "/conversation",
                             f"csrf={csrf_b}&question=hi")
    assert status.startswith("404")
    # B cannot claim ownership of the same deterministic demo run
    status, _, _ = b.request(
        "POST", "/analyze",
        f"consent=on&csrf={csrf_b}&website=https://northwind-demo.example")
    assert status.startswith("403")


def test_arbitrary_company_autoruns_recommended_sources(app):
    """V1.2: a real domain auto-approves the recommended sources and runs
    straight through — there is no separate source-approval page. This test's
    transport has no network, so every source fails and the run ends in an
    honest, styled FAILED result rather than a dead-end."""
    c = Client(app)
    csrf = _login(c)
    status, headers, _ = c.request(
        "POST", "/analyze",
        f"consent=on&csrf={csrf}&company_name=Real+Co"
        f"&website=https://real-company.example")
    assert status.startswith("303")
    loc = headers["Location"]
    assert "/sources" not in loc                  # the 2nd page is gone
    run_id = loc.split("/runs/")[1].split("/")[0]
    assert app.ci.store.run_state(run_id) == "FAILED"    # no network → honest
    status, _, body = c.request("GET", f"/runs/{run_id}")
    assert status == "200 OK"
    assert "<style" in body                       # styled failure, not plain
    assert "could not be completed" in body


def test_expired_share_link(app):
    c = Client(app)
    csrf = _login(c)
    run_url = _run_demo(c, csrf)
    _, _, body = c.request("POST", run_url + "/share", f"csrf={csrf}")
    token = body.split("/shared/")[1].split("<")[0]
    app._clock["t"] += 8 * 24 * 3600              # past the 7-day TTL
    status, _, body = Client(app).request("GET", f"/shared/{token}")
    assert status.startswith("404") and "expired" in body


def test_error_states_and_labels(app):
    c = Client(app)
    status, _, body = c.request("GET", "/runs/does-not-exist")
    assert status.startswith("303")               # anonymous → login
    csrf = _login(c)
    status, _, body = c.request("GET", "/runs/does-not-exist")
    assert status.startswith("404")
    # login page accessibility basics
    _, _, body = c.request("GET", "/login")
    assert '<label for="email">' in body and '<label for="password">' in body
    # consent required
    status, _, _ = c.request("POST", "/analyze", f"csrf={csrf}")
    assert status.startswith("400")


def test_csrf_required_on_state_changes(app):
    c = Client(app)
    _login(c)
    status, _, _ = c.request("POST", "/analyze", "consent=on&csrf=forged")
    assert status.startswith("403")


def test_feedback_recorded_never_mutates_intelligence(app):
    c = Client(app)
    csrf = _login(c)
    run_url = _run_demo(c, csrf)
    before = [r for r in app.fi.store.read_all()
              if r.event_type == "fi.section_assembled"]
    status, _, body = c.request("POST", run_url + "/feedback",
                                f"csrf={csrf}&useful=partly")
    assert status == "200 OK" and "never silently changes" in body
    after = [r for r in app.fi.store.read_all()
             if r.event_type == "fi.section_assembled"]
    assert [r.content_fingerprint() for r in before] == \
           [r.content_fingerprint() for r in after]


def test_production_host_check_and_safe_error_page(tmp_path):
    config = AppConfig(env="production", secret="s" * 40, debug=False,
                       cookie_secure=True, trusted_hosts=("app.example",),
                       web_store_path=tmp_path / "web.jsonl",
                       fi_store_path=tmp_path / "fi.jsonl")
    app = WebApp(config)
    c = Client(app, default_host="app.example")
    status, _, _ = c.request("GET", "/", host="evil.example")
    assert status.startswith("400")
    status, _, body = c.request("GET", "/")
    assert status == "200 OK"
    # a forced error must not leak a traceback in production
    app.fi.run_status = None                      # break a handler on purpose
    app.auth.create_user("a@example.com", "password123")
    c2 = Client(app, default_host="app.example")
    csrf = _login(c2, "a@example.com", "password123")
    run_url = _run_demo(c2, csrf)
    status, _, body = c2.request("GET", run_url + "/progress")
    assert status.startswith("500")
    # This used to assert the literal word "logged", which is exactly how the
    # page came to promise "It has been logged" while nothing logged anything.
    # Assert the properties that actually matter instead: no traceback
    # reaches the user, and they are given a reference an operator can find.
    # tests/test_webapp_error_logging.py proves the log side.
    assert "Traceback" not in body
    assert re.search(r"reference [0-9a-f]{12}", body), body[:300]


def test_empty_database_startup(tmp_path):
    config = AppConfig(env="test", secret="s" * 40,
                       web_store_path=tmp_path / "fresh" / "web.jsonl",
                       fi_store_path=tmp_path / "fresh" / "fi.jsonl")
    app = WebApp(config)                          # no pre-existing data files
    status, _, body = Client(app).request("GET", "/readyz")
    assert status == "200 OK" and "ready" in body
