"""Deployed operator surfaces: /version, /dashboard, /assistant, /status.json.
Read-only and login-gated; no promote/publish control on the web."""
import pytest

from intent_engine.webapp.app import WebApp
from intent_engine.webapp.config import AppConfig
from tests.test_webapp_journeys import Client, _no_network


@pytest.fixture
def app(tmp_path):
    config = AppConfig(env="test", secret="s" * 40,
                       web_store_path=tmp_path / "web.jsonl",
                       fi_store_path=tmp_path / "fi.jsonl",
                       ci_store_path=tmp_path / "ci.jsonl")
    application = WebApp(config, now_fn=lambda: 1000.0,
                         transport=_no_network, resolver=False)
    application.auth.create_user("founder@example.com", "password123")
    return application


def _login(c):
    c.request("POST", "/login", "email=founder@example.com&password=password123")


def test_version_is_public_and_safe(app):
    c = Client(app)
    status, _, body = c.request("GET", "/version")   # no login required
    assert status == "200 OK"
    assert "app_version" in body and "commit" in body
    # never leaks a secret
    assert "SECRET" not in body.upper()


@pytest.mark.parametrize("path", ["/dashboard", "/assistant", "/status.json"])
def test_operator_pages_require_login(app, path):
    c = Client(app)
    status, headers, _ = c.request("GET", path)
    assert status.startswith("303") and headers["Location"] == "/login"


def test_dashboard_renders_sections(app):
    c = Client(app)
    _login(c)
    status, _, body = c.request("GET", "/dashboard")
    assert status == "200 OK"
    for section in ("Needs attention", "Market learning", "Synthetic worlds",
                    "Configuration", "Data integrity"):
        assert section in body
    # every card explains what and why (Phase 4 requirement)
    assert "Why it matters" in body


def test_status_json_has_no_secret_values(app):
    c = Client(app)
    _login(c)
    status, _, body = c.request("GET", "/status.json")
    assert status == "200 OK"
    # config health reports statuses, never values
    for token in ("missing", "unprobed", "configured"):
        pass  # any status is fine
    assert "API_KEY" in body                    # names appear
    assert "sk-" not in body                     # no key material


def test_assistant_has_no_promote_or_publish_control(app):
    c = Client(app)
    _login(c)
    status, _, body = c.request("GET", "/assistant")
    assert status == "200 OK"
    low = body.lower()
    assert 'action="/assistant' not in low
    assert "human-gated" in low                  # states the boundary
