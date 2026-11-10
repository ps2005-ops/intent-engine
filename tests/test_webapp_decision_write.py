"""The write path over HTTP: a logged-in person records what they chose.

The unit tests beside this one prove `record_human_decision` refuses what it
must. These prove the ROUTE is wired to it -- which is a separate fact, and
the one this codebase has got wrong before: a capability that exists, is
tested, and has no production caller reads as COMPLETE from every angle
except the running product.

So each test here goes through the WSGI app: session, CSRF, form, store.
"""
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
        path, _, query = path.partition("?")
        env = {"REQUEST_METHOD": method, "PATH_INFO": path,
               "QUERY_STRING": query,
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


@pytest.fixture
def app(tmp_path):
    config = AppConfig(env="test", secret="s" * 40,
                       web_store_path=tmp_path / "web.jsonl",
                       fi_store_path=tmp_path / "fi.jsonl",
                       ci_store_path=tmp_path / "ci.jsonl", demo_mode=True)
    record_boot(tmp_path, boot_id="previous-process-boot")
    application = WebApp(config, transport=lambda u, t: None, resolver=False)
    application.auth.create_user("founder@example.com", "password123")
    application.auth.create_user("other@example.com", "password456")
    return application


def _login(client, email="founder@example.com", password="password123"):
    status, _, _ = client.request(
        "POST", "/login", f"email={email}&password={password}")
    assert status.startswith("303")
    return client.app.auth.csrf_token(client.sid())


def _record(client, csrf, *, company="cloudflare", choice="HOLD",
            recommendation="expand into the mid-market"):
    return client.request(
        "POST", "/decisions/record",
        f"csrf={csrf}&company={company}&choice={choice}"
        f"&recommendation={recommendation.replace(' ', '+')}")


def test_a_logged_in_person_can_record_a_decision(app):
    c = Client(app)
    csrf = _login(c)
    status, headers, _ = _record(c, csrf)
    assert status.startswith("303"), status

    # and it is readable back through the scoped JSON view
    _, _, body = c.request("GET", "/decisions?format=json")
    assert '"scoped": true' in body.lower().replace("true", "true")
    assert "cloudflare" in body
    assert "founder@example.com" in body


def test_the_recorded_decision_names_the_session_not_the_form(app):
    """A form field naming the decider would let one person file a choice
    under another's name, and the record's whole audit value is who chose."""
    c = Client(app)
    csrf = _login(c)
    status, _, _ = c.request(
        "POST", "/decisions/record",
        f"csrf={csrf}&company=cloudflare&choice=HOLD"
        f"&actor=someone.else@evil.test&decided_by=someone.else@evil.test")
    assert status.startswith("303")
    _, _, body = c.request("GET", "/decisions?format=json")
    assert "founder@example.com" in body
    assert "someone.else@evil.test" not in body


def test_an_anonymous_visitor_cannot_record_a_decision(app):
    """Demo mode is on, so there IS a session -- an anonymous one. It carries
    no tenant scope, and a decision without a tenant has nowhere to live."""
    c = Client(app)
    status, _, _ = c.request("POST", "/demo", "")
    assert status.startswith("303")
    csrf = app.auth.csrf_token(c.sid()) or ""
    status, _, body = _record(c, csrf)
    assert status.startswith("403"), status
    assert "account" in body.lower()


def test_a_decision_with_no_choice_is_refused_by_name(app):
    c = Client(app)
    csrf = _login(c)
    status, _, body = _record(c, csrf, choice="")
    assert status.startswith("400"), status
    assert "NO_CHOICE" in body


def test_the_write_route_requires_csrf(app):
    c = Client(app)
    _login(c)
    status, _, _ = _record(c, "not-the-token")
    assert status.startswith("403")


def test_one_tenant_cannot_see_another_s_recorded_decision(app):
    """Two real logins on one deployment. The decision belongs to the one
    that made it."""
    a, b = Client(app), Client(app)
    csrf_a = _login(a)
    _record(a, csrf_a, choice="HOLD")

    _login(b, "other@example.com", "password456")
    _, _, theirs = b.request("GET", "/decisions?format=json")
    assert "HOLD" not in theirs

    # NEGATIVE CONTROL: the writer can still see it, so the assertion above
    # is about isolation rather than about nothing being readable at all.
    _, _, ours = a.request("GET", "/decisions?format=json")
    assert "cloudflare" in ours
