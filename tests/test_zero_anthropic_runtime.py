"""The required customer path completes with NO hosted-model access at all.

Runtime proof, not architecture inspection: the whole WSGI product is driven
end to end with ANTHROPIC_API_KEY removed from the environment and any attempt
to construct a client raised. If a required producer reached for the model,
this run raises rather than degrading quietly.

The hosted preview cannot be used for this half: its key IS set, and the
Render CLI cannot unset an environment variable, so "absent" is not a state
that instance can be put into. §16 allows "absent, disabled, invalid, or
demonstrably unused" — this file proves the first, against the same code the
preview serves.
"""
import io
import os

import pytest

from intent_engine.webapp.app import WebApp
from intent_engine.webapp.config import AppConfig
from tests.test_strategic_intelligence import _live_transport

REQUIRED_SURFACES = ("", "/xray", "/brief", "/full", "/slides", "/sources")


@pytest.fixture
def no_model_app(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    # Any construction of a hosted client is a failure of the required path,
    # so it raises rather than returning a stub that could silently answer.
    import intent_engine.core.llm_client as llm

    def _refuse(*a, **k):
        raise AssertionError(
            "the required customer path constructed a hosted model client")

    for name in ("LLMClient", "get_client", "client"):
        if hasattr(llm, name):
            monkeypatch.setattr(llm, name, _refuse, raising=False)

    cfg = AppConfig(env="test", secret="s" * 40, demo_mode=True,
                    autorun_sources=True,
                    web_store_path=tmp_path / "w.jsonl",
                    fi_store_path=tmp_path / "fi.jsonl",
                    ci_store_path=tmp_path / "ci.jsonl")
    return WebApp(cfg, transport=_live_transport, resolver=False)


def _client(app):
    state = {"cookie": ""}

    def request(method, path, body=""):
        env = {"REQUEST_METHOD": method, "PATH_INFO": path,
               "CONTENT_LENGTH": str(len(body)), "HTTP_HOST": "127.0.0.1",
               "HTTP_COOKIE": state["cookie"],
               "wsgi.input": io.BytesIO(body.encode())}
        out = {}
        payload = b"".join(app(env, lambda s, h: out.update(
            status=s, headers=h))).decode()
        for k, v in out["headers"]:
            if k == "Set-Cookie" and v.startswith("sid="):
                state["cookie"] = v.split(";")[0]
        return out["status"], dict(out["headers"]), payload

    return request, state


def test_the_required_path_completes_with_no_hosted_model(no_model_app):
    app = no_model_app
    request, state = _client(app)
    request("POST", "/demo")
    assert "ANTHROPIC_API_KEY" not in os.environ

    csrf = app.auth.csrf_token(state["cookie"].split("=", 1)[1])
    status, headers, _ = request(
        "POST", "/analyze",
        f"consent=on&csrf={csrf}&company_name=Acme"
        f"&website=https://acme.example")
    assert status.startswith("303"), status
    run_id = headers["Location"].split("/runs/")[1].split("/")[0]
    request("GET", f"/runs/{run_id}")

    for surface in REQUIRED_SURFACES:
        code, _, body = request("GET", f"/runs/{run_id}{surface}")
        assert not code.startswith("5"), (
            f"{surface or '/(primary)'} answered {code} without a model")
        # A redirect is a legitimate answer with an empty body; only a page
        # that claims to have rendered must have rendered something.
        if code.startswith("200"):
            assert body, f"{surface or '/(primary)'} rendered nothing"

    # CEO Q&A is on the required path too, and it is the surface most likely
    # to reach for a model.
    csrf = app.auth.csrf_token(state["cookie"].split("=", 1)[1])
    code, _, body = request("POST", f"/runs/{run_id}/conversation",
                            f"csrf={csrf}&question=What+is+the+biggest+risk%3F")
    assert not code.startswith("5"), f"Q&A answered {code} without a model"
    assert body


def test_the_learning_surface_needs_no_hosted_model(no_model_app):
    request, _ = _client(no_model_app)
    code, _, body = request("GET", "/learning-acceleration")
    assert code.startswith("200") and body
