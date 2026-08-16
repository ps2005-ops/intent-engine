"""No run route may serve another session's analysis.

MEASURED on the deployed preview 2026-08-03 (commit 1887d49). A guest session
that did NOT own run 01KZ3864JA8G8JPCX3SB6431JN asked for it four ways:

    /runs/{id}            404  "no such run for this account"
    /runs/{id}/brief      200  the full executive brief
    /runs/{id}/dashboard  200  the full intelligence dashboard
    /runs/{id}/story      200  the full decision story

The guard was present on the primary page, on /slides and on /sources, and
missing on exactly those three. That is the worst shape this bug can take:
the protection looks present, so nobody re-checks it.

This file enumerates the routes rather than testing the three that were
broken. A test naming only today's defect passes forever while the next route
ships without a guard.
"""
import io

import pytest

from intent_engine.webapp.app import WebApp
from intent_engine.webapp.config import AppConfig
from tests.test_strategic_intelligence import _live_transport

# Every GET route under /runs/{id} that renders analysis content.
LAYERS = ["", "/brief", "/dashboard", "/story", "/slides", "/full",
          "/sources", "/report", "/xray"]


class _Client:
    def __init__(self, app):
        self.app, self.cookie = app, ""

    def request(self, method, path, body=""):
        env = {"REQUEST_METHOD": method, "PATH_INFO": path,
               "CONTENT_LENGTH": str(len(body)), "HTTP_HOST": "127.0.0.1",
               "HTTP_COOKIE": self.cookie,
               "wsgi.input": io.BytesIO(body.encode())}
        out = {}
        payload = b"".join(self.app(env, lambda s, h: out.update(
            status=s, headers=h))).decode()
        for key, value in out["headers"]:
            if key == "Set-Cookie" and value.startswith("sid="):
                self.cookie = ("" if "Max-Age=0" in value
                               else value.split(";")[0])
        return out["status"], dict(out["headers"]), payload

    def sid(self):
        return self.cookie.split("=", 1)[1] if self.cookie else None

    def csrf(self):
        return self.app.auth.csrf_token(self.sid())


@pytest.fixture
def app(tmp_path):
    cfg = AppConfig(env="test", secret="s" * 40, demo_mode=True,
                    autorun_sources=True,
                    web_store_path=tmp_path / "w.jsonl",
                    fi_store_path=tmp_path / "fi.jsonl",
                    ci_store_path=tmp_path / "ci.jsonl")
    return WebApp(cfg, transport=_live_transport, resolver=False)


@pytest.fixture
def owned_run(app):
    """A finished run, and the session that owns it."""
    owner = _Client(app)
    owner.request("POST", "/demo")
    status, headers, _ = owner.request(
        "POST", "/analyze",
        f"consent=on&csrf={owner.csrf()}&company_name=Acme"
        f"&website=https://acme.example")
    assert status.startswith("303"), status
    return owner, headers["Location"].split("/runs/")[1].split("/")[0]


@pytest.mark.parametrize("layer", LAYERS)
def test_a_stranger_cannot_read_any_layer_of_someone_elses_run(
        app, owned_run, layer):
    """THE BREAK PROOF. A second guest session is a different account."""
    _owner, run_id = owned_run
    stranger = _Client(app)
    stranger.request("POST", "/demo")

    status, _, body = stranger.request("GET", f"/runs/{run_id}{layer}")
    assert status.startswith(("404", "302", "303")), (
        f"{layer or '/(primary)'} served a stranger HTTP {status}")
    # and it must not leak the analysis while doing so
    assert "Acme" not in body or status.startswith("404"), (
        f"{layer or '/(primary)'} leaked run content to a stranger")


@pytest.mark.parametrize("layer", LAYERS)
def test_the_owner_is_not_locked_out_by_the_guard(app, owned_run, layer):
    """A guard that also blocks the owner is not a fix."""
    owner, run_id = owned_run
    status, _, _ = owner.request("GET", f"/runs/{run_id}{layer}")
    assert not status.startswith(("401", "403", "404")), (
        f"{layer or '/(primary)'} refused the owner: {status}")


def test_every_run_layer_route_calls_the_ownership_guard():
    """Source-level, so a NEW route cannot ship without one.

    The behavioural tests above can only cover routes someone remembered to
    add to LAYERS. This walks the dispatch table instead.
    """
    import inspect
    import re

    # Scoped to /runs/ dispatches specifically. A first version matched any
    # handler taking parts[1] and flagged `_learning_explain_page`, whose
    # parts[1] is a learning-candidate id under /learning/{id} -- a different
    # resource with its own authorisation question, which this test is not
    # the right place to answer. (That question is open; see the cycle notes.)
    source = inspect.getsource(WebApp._route)
    handlers = set(re.findall(
        r'\("GET", "runs", \d+\)[^\n]*\n\s*return self\.(_[a-z_]+)\('
        r'session, parts\[1\]', source))
    assert handlers, "route table shape changed; this gate is not looking at it"
    unguarded = []
    for name in sorted(handlers):
        fn = getattr(WebApp, name, None)
        if fn is None:
            continue
        body = inspect.getsource(fn)
        if "_owned(session" not in body:
            unguarded.append(name)
    assert not unguarded, f"run routes with no ownership guard: {unguarded}"
