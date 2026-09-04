"""Follow-up questions answer about THIS run, and remember the last turn.

Two failures matter here and they are different. One is a leak: a question
asked on run A must never be answered from run B's report. The other is
amnesia: "why is that more important than regulation?" is unanswerable
without knowing what "that" referred to, and an assistant that quietly drops
the referent produces confident answers to a question nobody asked.
"""
from __future__ import annotations

import inspect

from intent_engine.webapp.app import WebApp
from intent_engine.webapp.config import AppConfig
from tests.test_measurement_is_canonical import _Client
from tests.test_strategic_intelligence import _live_transport


def _app(tmp_path):
    return WebApp(AppConfig(env="test", secret="s" * 40, demo_mode=True,
                            autorun_sources=True,
                            web_store_path=tmp_path / "w.jsonl",
                            fi_store_path=tmp_path / "fi.jsonl",
                            ci_store_path=tmp_path / "ci.jsonl"),
                  transport=_live_transport, resolver=False)


def _run(app, company="Acme", site="acme.example"):
    client = _Client(app)
    client.request("POST", "/demo")
    _s, headers, _b = client.request(
        "POST", "/analyze",
        f"consent=on&csrf={client.csrf()}&company_name={company}"
        f"&website=https://{site}")
    return client, headers["Location"].split("/runs/")[1].split("/")[0]


def test_a_question_is_answered_from_this_runs_own_report(tmp_path):
    """The context is fetched BY RUN ID, so it cannot be another company's."""
    src = inspect.getsource(WebApp._converse)
    assert "self._founder_layers(run_id)" in src, \
        "the answer does not read this run's own report"
    assert "_strategic_report_for(run_id)" in src, \
        "the answer does not read this run's own strategic report"
    # And the run id is the one from the URL, never from the form: a question
    # that could name its own run id would be a way to read another one.
    signature = inspect.signature(WebApp._converse)
    assert list(signature.parameters) == ["self", "session", "run_id", "form"]


def test_another_session_cannot_ask_about_this_run(tmp_path):
    """The Q&A route is a route, and a run id is the only thing protecting it."""
    app = _app(tmp_path)
    _client, run_id = _run(app)
    stranger = _Client(app)
    stranger.request("POST", "/demo")
    status, _h, _b = stranger.request(
        "POST", f"/runs/{run_id}/conversation",
        f"csrf={stranger.csrf()}&question=What+is+the+risk")
    assert not status.startswith("200"), \
        "another session answered a question about this run"


def test_two_runs_keep_separate_conversation_memory(tmp_path):
    """`_conversation_context` is keyed by run, so one company's follow-up
    context can never be handed to another's."""
    app = _app(tmp_path)
    _c1, run_a = _run(app, "Acme", "acme.example")
    _c2, run_b = _run(app, "Brightlake", "brightlake.example")
    assert run_a != run_b
    app._conversation_context[run_a] = ("pricing_power",)
    app._conversation_context[run_b] = ("regulation",)
    assert app._conversation_context[run_a] == ("pricing_power",)
    assert app._conversation_context[run_b] == ("regulation",)
    src = inspect.getsource(WebApp._converse)
    assert "_conversation_context.get(run_id" in src, \
        "follow-up context is not scoped to the run"


def test_the_previous_turn_is_carried_into_the_next_answer(tmp_path):
    """A follow-up like "why is that more important?" needs the referent."""
    src = inspect.getsource(WebApp._converse)
    assert "previous = self._conversation_context.get(run_id" in src, \
        "the previous turn is never read, so a follow-up has no referent"
    assert "self._conversation_context[run_id] =" in src, \
        "nothing is remembered for the next turn"
    read_at = src.index("previous = self._conversation_context")
    write_at = src.index("self._conversation_context[run_id] =")
    assert read_at < write_at, (
        "the turn is overwritten before it is read, so every follow-up sees "
        "its own topics instead of the previous answer's")
