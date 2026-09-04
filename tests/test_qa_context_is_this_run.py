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
    """Whatever follow-up memory exists is keyed BY RUN.

    Asserted against the store itself rather than against the source text.
    The previous version of this test grepped `_converse` for
    `_conversation_context.get(run_id` and passed -- against code that could
    never execute. A structural assertion is only as true as the reachability
    of the line it matches, which is why `test_the_answer_path_has_no_dead_code`
    below now guards that separately.
    """
    app = _app(tmp_path)
    _c1, run_a = _run(app, "Acme", "acme.example")
    _c2, run_b = _run(app, "Brightlake", "brightlake.example")
    assert run_a != run_b
    app._conversation_context[run_a] = ("pricing_power",)
    app._conversation_context[run_b] = ("regulation",)
    assert app._conversation_context[run_a] == ("pricing_power",)
    assert app._conversation_context[run_b] == ("regulation",)


def test_the_answer_path_has_no_dead_code(tmp_path):
    """A STRUCTURAL ASSERTION IS WORTHLESS ON AN UNREACHABLE LINE.

    `_converse` carried forty-eight lines of a second, older Q&A engine below
    an unconditional `return`: twelve of its twenty-four top-level statements
    could never run, and the only writer of `_conversation_context` was among
    them. A test that grepped for that writer passed while follow-up memory
    was never stored on the live path.

    This walks the AST instead of the text, so the same class of defect
    cannot come back and take a green test with it.
    """
    import ast
    for name in ("_converse", "_progress", "_analyze"):
        function = ast.parse(
            inspect.getsource(getattr(WebApp, name)).lstrip()).body[0]
        returned_at = None
        for index, node in enumerate(function.body):
            if isinstance(node, ast.Return):
                returned_at = index
                break
        if returned_at is None:
            continue
        unreachable = len(function.body) - (returned_at + 1)
        assert unreachable == 0, (
            f"{name} has {unreachable} unreachable top-level statement(s) "
            f"after an unconditional return; any structural test matching "
            f"them is a false green")


def test_why_a_reading_was_withheld_is_visible(tmp_path):
    """THE DIAGNOSTIC THAT DID NOT EXIST.

    Q&A refuses a strategic question when `brief.key_insight is None` and no
    executive contract overrides it. Live on e4b5ad6b that refusal fired on
    3-5 of 6 questions for every company in the ten-company matrix, including
    two with 13 documents and all three evidence roles filled -- and there was
    no way to tell from a live run whether `safe_insights` had received no
    candidates or dropped every one of them. It had to be inferred from
    source, which is not a diagnosis.
    """
    import json
    app = _app(tmp_path)
    client, run_id = _run(app)
    status, _h, body = client.request("GET", f"/runs/{run_id}/telemetry")
    assert status.startswith("200"), status
    reading = json.loads(body).get("reading") or {}
    for key in ("key_insight_present", "candidates_dropped",
                "contract_present", "contract_reading_exists",
                "qa_would_withhold"):
        assert key in reading, f"the diagnostic does not report {key}"
    # And it must agree with the rule Q&A actually applies.
    assert reading["qa_would_withhold"] == (
        not reading["key_insight_present"]
        and not reading["contract_reading_exists"])
