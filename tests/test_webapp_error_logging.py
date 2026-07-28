"""A 500 must leave a diagnosable trace in private logs and nothing in public.

The error page promised "It has been logged" while `traceback.format_exc()`
was only called when debug was on. In production the traceback was never
formatted, never written, and discarded — a 500 left nothing behind but an
access-log line, so the one artefact needed to diagnose it never existed.
"""
import logging

import pytest

from intent_engine.webapp.app import WebApp
from intent_engine.webapp.config import AppConfig
from tests.test_webapp_journeys import Client


def _app(tmp_path, env):
    cfg = AppConfig(env=env, secret="s" * 40, debug=(env != "production"),
                    cookie_secure=(env == "production"),
                    web_store_path=tmp_path / "web.jsonl",
                    fi_store_path=tmp_path / "fi.jsonl",
                    trusted_hosts=("127.0.0.1",))
    app = WebApp(cfg)

    def boom(environ):
        raise RuntimeError("SENTINEL_INTERNAL_DETAIL_9137")
    app._route = boom
    return app


def test_production_500_logs_the_traceback(tmp_path, caplog):
    app = _app(tmp_path, "production")
    with caplog.at_level(logging.ERROR, logger="intent_engine.webapp"):
        status, _, body = Client(app).request("GET", "/")
    assert status.startswith("500")
    logged = caplog.text
    assert "SENTINEL_INTERNAL_DETAIL_9137" in logged, (
        "the traceback must reach private logs")
    assert "Traceback" in logged


def test_production_500_leaks_nothing_to_the_user(tmp_path, caplog):
    app = _app(tmp_path, "production")
    with caplog.at_level(logging.ERROR, logger="intent_engine.webapp"):
        _, _, body = Client(app).request("GET", "/")
    assert "SENTINEL_INTERNAL_DETAIL_9137" not in body
    assert "Traceback" not in body
    assert "/opt/render" not in body and ".py" not in body


def test_user_gets_a_reference_that_matches_the_log(tmp_path, caplog):
    """The bridge: quotable by the user, greppable by an operator, and
    carrying no internal detail across the boundary."""
    import re
    app = _app(tmp_path, "production")
    with caplog.at_level(logging.ERROR, logger="intent_engine.webapp"):
        _, _, body = Client(app).request("GET", "/")
    m = re.search(r"reference ([0-9a-f]{12})", body)
    assert m, f"no error reference shown to the user: {body[:300]}"
    assert m.group(1) in caplog.text, "reference must appear in the log too"


def test_no_longer_claims_logging_it_does_not_do(tmp_path, caplog):
    app = _app(tmp_path, "production")
    with caplog.at_level(logging.ERROR, logger="intent_engine.webapp"):
        _, _, body = Client(app).request("GET", "/")
    # The old copy asserted a fact that was false.
    assert "It has been logged." not in body


def test_debug_mode_still_shows_the_traceback_and_still_logs_it(tmp_path, caplog):
    app = _app(tmp_path, "development")
    with caplog.at_level(logging.ERROR, logger="intent_engine.webapp"):
        _, _, body = Client(app).request("GET", "/")
    assert "SENTINEL_INTERNAL_DETAIL_9137" in body     # developer convenience
    assert "SENTINEL_INTERNAL_DETAIL_9137" in caplog.text   # still recorded
