"""ZERO_ANTHROPIC is a measured property, not a configuration claim.

`tests/test_zero_anthropic_runtime.py` already proves the required customer
path RENDERS with no hosted model available. It proves that by removing the
credential and refusing client construction, which is a statement about an
ENVIRONMENT. This file proves something different and stronger: that the
process can be told to refuse, that the refusal holds at both boundaries a
model can be reached through, and that the number of invocations which reached
the SDK is ZERO -- counted, not inferred from the absence of an exception.

The distinction matters because "no exception was raised" cannot separate a
path that did not call from a path that was never reached. `model_gate.calls()`
answers that directly.

Nothing here mocks away product behaviour. The analysis runs the real
pipeline over the repository's offline fixture site; only the network
transport is replaced, exactly as every other suite in this repository does.
"""
import io
import pathlib

import pytest

from intent_engine.core import model_gate as gate
from intent_engine.core.llm_client import LLMClient
from intent_engine.strategic_intelligence.analyst.runner import default_client
from intent_engine.webapp.app import WebApp
from intent_engine.webapp.config import AppConfig
from intent_engine.webapp.storage_state import record_boot

from company_fixture_pages import BASE as FIXTURE_BASE
from company_fixture_pages import transport as fixture_transport


# --- the gate itself --------------------------------------------------------

def test_the_gate_is_open_by_default(monkeypatch):
    monkeypatch.delenv(gate.ZERO_ANTHROPIC_ENV, raising=False)
    assert gate.anthropic_disabled() is False


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on", " on "])
def test_every_documented_truthy_spelling_closes_it(monkeypatch, value):
    monkeypatch.setenv(gate.ZERO_ANTHROPIC_ENV, value)
    assert gate.anthropic_disabled() is True


@pytest.mark.parametrize("value", ["", "0", "false", "no", "off"])
def test_falsey_spellings_leave_it_open(monkeypatch, value):
    monkeypatch.setenv(gate.ZERO_ANTHROPIC_ENV, value)
    assert gate.anthropic_disabled() is False


def test_construction_is_refused_even_with_a_key_present(monkeypatch):
    """A credential does not reopen the gate.

    This is the case unsetting the variable could never cover: an operator on
    a platform whose CLI cannot remove an environment variable, or a `.env`
    file on disk that `default_client` loads before it looks at the
    environment.
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-not-a-real-key")
    monkeypatch.setenv(gate.ZERO_ANTHROPIC_ENV, "1")
    with pytest.raises(gate.AnthropicDisabled):
        LLMClient()


def test_default_client_returns_none_rather_than_raising(monkeypatch):
    """The product path degrades honestly; it does not crash.

    `analyse` turns a None client into AnalystUnavailable, which the ingestion
    service reports as EVIDENCE_LIMITED with a stated reason. That is the
    contract the rest of the product is written against, and the gate must not
    change it.
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-not-a-real-key")
    monkeypatch.setenv(gate.ZERO_ANTHROPIC_ENV, "1")
    assert default_client() is None


def test_a_client_built_before_the_gate_closed_still_cannot_call(monkeypatch):
    """The construction guard alone is not sufficient, and this is why.

    A long-lived service builds its client once, in __init__, and holds it for
    the life of the process. A gate consulted only at construction would be
    consulted once, at boot. So `call_tool` re-checks immediately before the
    SDK call.

    The client is built with the gate OPEN and a syntactically plausible key,
    which is why no network is reachable from it: the call is refused before
    `messages.create` is ever named.
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-not-a-real-key")
    monkeypatch.delenv(gate.ZERO_ANTHROPIC_ENV, raising=False)
    client = LLMClient()                       # gate open: construction works

    monkeypatch.setenv(gate.ZERO_ANTHROPIC_ENV, "1")
    gate.reset_calls()
    with pytest.raises(gate.AnthropicDisabled):
        client.call_tool(system="s", user_message="u", tool_name="t",
                         tool_description="d", input_schema={"type": "object"})
    assert gate.calls() == 0, "a refused call must not be counted as one"


def test_the_counter_counts_sdk_invocations_and_nothing_else(monkeypatch):
    """A call is counted where it reaches the SDK, and refusals are not calls.

    The counter's whole purpose is to let a run state its real invocation
    count. If a refusal incremented it, "zero calls" would be unprovable in
    exactly the mode it exists to prove.
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-not-a-real-key")
    monkeypatch.delenv(gate.ZERO_ANTHROPIC_ENV, raising=False)
    client = LLMClient()
    gate.reset_calls()
    assert gate.calls() == 0

    # The SDK is reached and fails on the fake credential. Reaching it is the
    # event being counted; whether the provider liked the request is not.
    with pytest.raises(Exception):
        client.call_tool(system="s", user_message="u", tool_name="t",
                         tool_description="d", input_schema={"type": "object"})
    assert gate.calls() == 1


# --- the whole product, driven under the gate -------------------------------

def _app(tmp_path, transport):
    cfg = AppConfig(env="development", secret="s" * 40, autorun_sources=True,
                    web_store_path=tmp_path / "web.jsonl",
                    fi_store_path=tmp_path / "fi.jsonl",
                    ci_store_path=tmp_path / "ci.jsonl")
    record_boot(tmp_path, boot_id="previous-process-boot")
    # env="development", NOT "test". `WebApp.__init__` skips analyst
    # construction entirely under env="test", so a test that used it would
    # exercise a branch production never takes and prove nothing about the
    # gate. This is the production branch, with the gate deciding.
    app = WebApp(cfg, transport=transport, resolver=False)
    app._analysis_async = False
    app.auth.create_user("founder@example.com", "password123")
    return app


def _drive(app):
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
                state["cookie"] = ("" if "Max-Age=0" in v
                                   else v.split(";")[0])
        return out["status"], dict(out["headers"]), payload

    request("POST", "/login", "email=founder@example.com&password=password123")
    return request, state


SURFACES = ("", "/intro", "/answer", "/story", "/dashboard", "/brief",
            "/xray", "/evidence", "/slides", "/full", "/history", "/connect")


def test_a_whole_analysis_completes_with_zero_anthropic_calls(tmp_path,
                                                              monkeypatch):
    """The acceptance test: a real run, every founder surface, counted at zero.

    A key IS present, deliberately. Proving the gate with no credential
    available would prove nothing the environment did not already prove.
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-not-a-real-key")
    monkeypatch.setenv(gate.ZERO_ANTHROPIC_ENV, "1")
    gate.reset_calls()

    app = _app(tmp_path, fixture_transport)
    assert app._analyst_client is None
    assert app._anthropic_gate_shut is True
    assert gate.ZERO_ANTHROPIC_ENV in app._analyst_error, app._analyst_error

    request, state = _drive(app)
    csrf = app.auth.csrf_token(state["cookie"].split("=", 1)[1])
    status, headers, _ = request(
        "POST", "/analyze",
        f"consent=on&csrf={csrf}&company_name=Brightlake"
        f"&website={FIXTURE_BASE}")
    assert status.startswith("303"), status
    run_id = headers["Location"].split("/runs/")[1].split("/")[0]

    for suffix in SURFACES:
        code, _h, body = request("GET", f"/runs/{run_id}{suffix}")
        assert not code.startswith("5"), (
            f"{suffix or '/(primary)'} answered {code} under the gate")
        if code.startswith("200"):
            assert body, f"{suffix or '/(primary)'} rendered nothing"

    # Q&A is the surface most likely to reach for a model.
    csrf = app.auth.csrf_token(state["cookie"].split("=", 1)[1])
    code, _h, body = request("POST", f"/runs/{run_id}/conversation",
                             f"csrf={csrf}&question=What+is+the+biggest+risk%3F")
    assert not code.startswith("5") and body

    assert gate.calls() == 0, (
        f"{gate.calls()} Anthropic call(s) reached the SDK under "
        f"{gate.ZERO_ANTHROPIC_ENV}=1")


def test_a_failing_run_stays_at_zero_including_its_recovery_path(tmp_path,
                                                                 monkeypatch):
    """Retries and exception recovery may not reach for a model either.

    A transport that refuses everything drives the run into its failure and
    bounded-result paths -- the ones that exist precisely to salvage something
    from a bad run, and therefore the ones most likely to reach for help.
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-not-a-real-key")
    monkeypatch.setenv(gate.ZERO_ANTHROPIC_ENV, "1")
    gate.reset_calls()

    def dead(url, timeout):
        raise OSError("no network in this test")

    app = _app(tmp_path, dead)
    request, state = _drive(app)
    csrf = app.auth.csrf_token(state["cookie"].split("=", 1)[1])
    status, headers, _ = request(
        "POST", "/analyze",
        f"consent=on&csrf={csrf}&company_name=Nowhere+Ltd"
        f"&website=https://nowhere.example")
    assert status.startswith("303"), status
    run_id = headers["Location"].split("/runs/")[1].split("/")[0]

    for suffix in ("", "/retry"):
        method = "POST" if suffix == "/retry" else "GET"
        body = (f"csrf={app.auth.csrf_token(state['cookie'].split('=', 1)[1])}"
                if method == "POST" else "")
        code, _h, _b = request(method, f"/runs/{run_id}{suffix}", body)
        assert not code.startswith("5"), f"{suffix} answered {code}"

    assert gate.calls() == 0


def test_the_gate_does_not_change_behaviour_when_open(tmp_path, monkeypatch):
    """The assisted mode still works, and still reports honestly.

    With the gate open and no credential, the product must reach exactly the
    state it reached before this change existed: no client, and an error
    string naming the missing key rather than the gate.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv(gate.ZERO_ANTHROPIC_ENV, raising=False)
    # `default_client` calls load_dotenv() before reading the environment.
    # This repository ships `.env.example` and no `.env`, so there is nothing
    # for it to resupply -- which is exactly the fragility the gate replaces,
    # and it is asserted here so a future `.env` turns this test red rather
    # than turning the assertion below into a coincidence.
    assert not pathlib.Path(".env").exists(), (
        "a .env would resupply the key and this test would stop measuring "
        "what it claims to measure; the gate is the durable control")

    app = _app(tmp_path, fixture_transport)
    assert app._anthropic_gate_shut is False
    assert app._analyst_client is None
    assert "ANTHROPIC_API_KEY" in app._analyst_error
    assert gate.ZERO_ANTHROPIC_ENV not in app._analyst_error


def test_the_analyst_is_the_only_reachable_model_seam(tmp_path, monkeypatch):
    """Three other `call_tool` sites exist on the live path and receive None.

    `personal.conversation.answer`, `founder_intelligence.conversation.answer`
    and `executive.service` all call a model when handed one. `WebApp` never
    hands them one -- it constructs `PersonalService(...)` and
    `FounderIntelligenceService(path)` with no `llm_client=` -- so those
    branches are unreachable from a request.

    That is currently true by omission, which is exactly the kind of property
    that stops being true in a later refactor without anybody noticing. This
    pins it, so a change that starts supplying one of them has to say so.
    """
    monkeypatch.delenv(gate.ZERO_ANTHROPIC_ENV, raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-not-a-real-key")
    app = _app(tmp_path, fixture_transport)

    assert app.fi.llm_client is None, (
        "FounderIntelligence was given a model client; the analyst is no "
        "longer the only reachable seam and the zero-Anthropic map is stale")
    assert app._personal.llm_client is None, (
        "PersonalService was given a model client; see above")
