"""Market and macro credentials must be checkable from outside the service.

Three consecutive cycles reported "TIINGO_API_KEY / FRED_API_KEY availability
unknown" and left the market and macro objectives blocked -- not because the
keys were hard to add, but because nothing on the running service published
whether they existed. `/readyz` reported the reasoning key and nothing else,
so a one-second check became an unanswerable question.

Presence only. The values are never read into a response, and these tests
assert that as strictly as they assert the booleans.
"""
import json

import pytest

from intent_engine.webapp.app import WebApp
from intent_engine.webapp.config import AppConfig
from tests.test_strategic_intelligence import _live_transport

_SECRET = "tiingo-secret-value-do-not-leak"


def _readyz(app):
    out, body = [], []
    body = app({"REQUEST_METHOD": "GET", "PATH_INFO": "/readyz",
                "wsgi.url_scheme": "http", "QUERY_STRING": "",
                "HTTP_HOST": "localhost"},
               lambda s, h: out.append(s))
    return json.loads(b"".join(body).decode())


@pytest.fixture
def app(tmp_path):
    cfg = AppConfig(env="test", secret="s" * 40, demo_mode=True,
                    web_store_path=tmp_path / "w.jsonl",
                    fi_store_path=tmp_path / "fi.jsonl",
                    ci_store_path=tmp_path / "ci.jsonl")
    return WebApp(cfg, transport=_live_transport, resolver=False)


@pytest.mark.parametrize("env_var,field", [
    ("TIINGO_API_KEY", "market_key_present"),
    ("FRED_API_KEY", "macro_key_present"),
])
def test_absence_and_presence_are_both_reported(app, monkeypatch, env_var,
                                                field):
    monkeypatch.delenv(env_var, raising=False)
    assert _readyz(app)["capabilities"][field] is False

    monkeypatch.setenv(env_var, _SECRET)
    assert _readyz(app)["capabilities"][field] is True


@pytest.mark.parametrize("env_var", ["TIINGO_API_KEY", "FRED_API_KEY"])
def test_the_value_never_reaches_the_response(app, monkeypatch, env_var):
    """A capability probe that leaks the credential is worse than no probe."""
    monkeypatch.setenv(env_var, _SECRET)
    body = json.dumps(_readyz(app))
    assert _SECRET not in body
    assert "secret-value" not in body


def test_both_fields_are_always_present_so_absence_is_distinguishable(app,
                                                                      monkeypatch):
    """A MISSING field and a false field look identical to a caller that has
    to use .get() -- which is how "availability unknown" kept being reported.
    """
    monkeypatch.delenv("TIINGO_API_KEY", raising=False)
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    caps = _readyz(app)["capabilities"]
    assert "market_key_present" in caps
    assert "macro_key_present" in caps
