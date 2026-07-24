"""The learning platform is observable from the web, read-only and gated.

/learning requires a session (like /runs), renders the candidate pipeline
and the paper book, and exposes NO promote/trade control. /learning/<id>
renders the explainability chain for a candidate.
"""
import io

import pytest

from intent_engine.learning import LearningLedger
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
    # seed a candidate directly into the SAME ledger the app reads (co-located
    # with the ci store path, per the app constructor).
    led = LearningLedger(tmp_path / "learning_ledger.db")
    c = led.propose(source="calibration", target="conf",
                    statement="shrink the 70-80 percent bucket",
                    hypothesis="overconfident there", baseline_ref="v1",
                    success_criteria=[{"metric": "brier", "comparator": "<=",
                                       "threshold": 0.2,
                                       "direction": "lower_better"}])
    led.evaluate(c.id, kind="rolling_backtest",
                 candidate_metrics={"brier": 0.15},
                 baseline_metrics={"brier": 0.25}, sample_size=30)
    application._seed_candidate_id = c.id
    return application


def _login(c):
    c.request("POST", "/login", "email=founder@example.com&password=password123")


def test_learning_requires_login(app):
    c = Client(app)
    status, headers, _ = c.request("GET", "/learning")
    assert status.startswith("303") and headers["Location"] == "/login"


def test_learning_page_shows_pipeline_and_paper_book(app):
    c = Client(app)
    _login(c)
    status, _, body = c.request("GET", "/learning")
    assert status == "200 OK"
    assert "Learning platform" in body
    assert "evaluated: 1" in body
    assert "shrink the 70-80 percent bucket" in body
    assert "no real money" in body           # shadow-only framing
    # read-only surface: the learning feature has no POST route at all, so
    # no form on the page may target it (the only form is session logout).
    low = body.lower()
    assert 'action="/learning' not in low
    assert "promote" not in body.replace(
        "a human promotes one, and never from here.", "").lower()


def test_explain_page_renders_chain(app):
    c = Client(app)
    _login(c)
    status, _, body = c.request("GET", f"/learning/{app._seed_candidate_id}")
    assert status == "200 OK"
    for label in ("Finding", "Evidence", "Reasoning", "Source agent", "Replay"):
        assert label in body


def test_unknown_candidate_is_404(app):
    c = Client(app)
    _login(c)
    status, _, _ = c.request("GET", "/learning/NOPE")
    assert status.startswith("404")
