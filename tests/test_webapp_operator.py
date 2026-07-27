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


def test_readyz_probes_runtime_root_writability(app):
    c = Client(app)
    status, _, body = c.request("GET", "/readyz")
    assert status == "200 OK" and '"ready"' in body
    assert "runtime_root" in body                     # probe ran + reported
    # if the runtime root is not writable, readyz must report NOT ready
    import unittest.mock as mock
    with mock.patch.object(app, "_probe_runtime_root_writable",
                           side_effect=OSError("read-only file system")):
        status, _, body = c.request("GET", "/readyz")
    assert status.startswith("503") and "not ready" in body


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


def test_readyz_reports_observed_capability_state_not_intent(app):
    """Release stabilization: /readyz must report what this process can
    ACTUALLY do.

    pypdf was declared in requirements.txt but not in pyproject, and the
    deployment builds with `pip install -e .`, so production silently had no
    PDF support while every config file and test claimed it did. Nothing
    outside the process could tell. These values are probed live.
    """
    import json
    import unittest.mock as mock
    import builtins

    c = Client(app)
    status, _, body = c.request("GET", "/readyz")
    assert status == "200 OK"
    caps = json.loads(body)["capabilities"]

    # pypdf is a declared install dependency, so it must really import here.
    assert caps["pdf_extraction"] is True
    # Rendering is off unless explicitly enabled, and must never be on by
    # default — enabling it is a deliberate act, not a deployment accident.
    assert caps["browser_rendering"] is False

    # The value must track reality, not a constant: simulate the deployment
    # that shipped without pypdf and confirm /readyz says so.
    real_import = builtins.__import__

    def no_pypdf(name, *a, **kw):
        if name == "pypdf":
            raise ImportError("No module named 'pypdf'")
        return real_import(name, *a, **kw)

    with mock.patch.object(builtins, "__import__", side_effect=no_pypdf):
        _, _, body = c.request("GET", "/readyz")
    assert json.loads(body)["capabilities"]["pdf_extraction"] is False

    # And it must remain sanitized.
    assert "SECRET" not in body.upper()
