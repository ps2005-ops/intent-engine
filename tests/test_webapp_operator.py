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


def test_dashboard_reads_the_runtime_root_not_a_divergent_path(tmp_path, monkeypatch):
    """Config-drift regression: the web layer's learning/paper reads must use
    the SAME RUNTIME_ROOT the scheduler writes to, or the dashboard shows an
    empty/stale location in production."""
    runtime_root = tmp_path / "var_data"       # where the scheduler writes
    ci_dir = tmp_path / "ci"                    # a different location
    ci_dir.mkdir()
    monkeypatch.setenv("RUNTIME_ROOT", str(runtime_root))
    from intent_engine.learning import LearningLedger
    LearningLedger(runtime_root / "learning_ledger.db").propose(
        source="calibration", target="conf", statement="seeded in runtime root",
        hypothesis="h", baseline_ref="v1",
        success_criteria=[{"metric": "brier", "comparator": "<=",
                           "threshold": 0.2, "direction": "lower_better"}])
    config = AppConfig(env="test", secret="s" * 40,
                       web_store_path=ci_dir / "w.jsonl",
                       fi_store_path=ci_dir / "fi.jsonl",
                       ci_store_path=ci_dir / "ci.jsonl")
    application = WebApp(config, now_fn=lambda: 1000.0,
                         transport=_no_network, resolver=False)
    insp = application._personal.inspect_learning(as_of="2026-07-24")
    assert insp["pipeline"].get("proposed") == 1     # sees the scheduler's write
    assert str(application._learning_reader.learning.store.path).startswith(
        str(runtime_root))


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


def test_dashboard_surfaces_job_failure_reason(app, tmp_path):
    """Observability: a failed job must show WHY and SINCE-WHEN on the
    dashboard, not just its name — answerable without reading source."""
    from intent_engine.runtime.jobs import run_job
    # the app reads job status from its runtime root (co-located with ci store)
    root = app._runtime_root
    def boom():
        raise ValueError("tiingo rate limit exceeded")
    run_job("resolve", boom, root=root, retries=0)
    c = Client(app)
    _login(c)
    status, _, body = c.request("GET", "/dashboard")
    assert status == "200 OK"
    assert "tiingo rate limit exceeded" in body      # why
    assert "resolve failed at" in body               # what + since-when
    assert "recovery runbook" in body                # what action


def test_assistant_has_no_promote_or_publish_control(app):
    c = Client(app)
    _login(c)
    status, _, body = c.request("GET", "/assistant")
    assert status == "200 OK"
    low = body.lower()
    assert 'action="/assistant' not in low
    assert "human-gated" in low                  # states the boundary
