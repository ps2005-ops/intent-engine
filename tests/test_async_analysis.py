"""The submission must stop waiting for the analysis.

MEASURED on the deployed preview: POST /analyze ran discovery, retrieval,
reasoning and rendering inside the request. A real browser was blocked for the
entire analysis -- minutes for Costco -- and the progress page, which already
records truthful stages, was unreachable during the one window it explains.
"""
import time

import pytest

from tests.test_strategic_intelligence import _WsgiClient, _live_transport
from intent_engine.webapp.app import WebApp
from intent_engine.webapp.config import AppConfig


def _async_app(tmp_path, transport=_live_transport):
    cfg = AppConfig(env="test", secret="s" * 40, demo_mode=True,
                    web_store_path=tmp_path / "w.jsonl",
                    fi_store_path=tmp_path / "fi.jsonl",
                    ci_store_path=tmp_path / "ci.jsonl")
    app = WebApp(cfg, transport=transport, resolver=False)
    app._analysis_async = True          # the production path, explicitly
    return app


def _submit(app, company="Acme"):
    c = _WsgiClient(app)
    c.request("POST", "/demo")
    started = time.monotonic()
    status, headers, _ = c.request(
        "POST", "/analyze",
        f"consent=on&csrf={c.csrf()}&company_name={company}"
        f"&website=https://acme.example")
    return c, status, headers, time.monotonic() - started


def test_submission_returns_immediately_and_work_continues(tmp_path):
    app = _async_app(tmp_path)
    c, status, headers, elapsed = _submit(app)
    assert status.startswith("303")
    assert headers["Location"].endswith("/progress")
    # The request must not carry the analysis. This is the regression that
    # would catch a return to the blocking POST.
    assert elapsed < 2.0, f"submission blocked for {elapsed:.1f}s"
    assert app.wait_for_analysis(headers["Location"].split("/runs/")[1]
                                 .split("/")[0], timeout=30)


def test_the_run_reaches_a_terminal_state_on_the_worker(tmp_path):
    app = _async_app(tmp_path)
    _, _, headers, _ = _submit(app)
    run_id = headers["Location"].split("/runs/")[1].split("/")[0]
    assert app.wait_for_analysis(run_id, timeout=30)
    assert app.ci.store.run_state(run_id) in app.TERMINAL_STATES


def test_a_double_click_does_not_start_two_analyses(tmp_path):
    app = _async_app(tmp_path)
    c = _WsgiClient(app)
    c.request("POST", "/demo")
    csrf = c.csrf()
    body = (f"consent=on&csrf={csrf}&company_name=Acme"
            f"&website=https://acme.example")
    _, h1, _ = c.request("POST", "/analyze", body)
    _, h2, _ = c.request("POST", "/analyze", body)
    run_id = h1["Location"].split("/runs/")[1].split("/")[0]
    assert h2["Location"].split("/runs/")[1].split("/")[0] == run_id
    # the second submission must not schedule a second execution
    assert app._schedule_analysis("u", run_id) is False
    assert app.wait_for_analysis(run_id, timeout=30)


def test_a_worker_exception_becomes_a_terminal_failed_state(tmp_path):
    """A worker that dies silently would leave the page claiming work
    forever -- the exact failure this change exists to remove."""
    def exploding(*args, **kwargs):
        raise RuntimeError("network gone")
    app = _async_app(tmp_path, transport=exploding)
    _, _, headers, _ = _submit(app)
    run_id = headers["Location"].split("/runs/")[1].split("/")[0]
    assert app.wait_for_analysis(run_id, timeout=30)
    assert app.ci.store.run_state(run_id) in app.TERMINAL_STATES
    assert run_id not in app._analysis_inflight


def test_scheduling_is_refused_once_a_run_is_terminal(tmp_path):
    app = _async_app(tmp_path)
    _, _, headers, _ = _submit(app)
    run_id = headers["Location"].split("/runs/")[1].split("/")[0]
    assert app.wait_for_analysis(run_id, timeout=30)
    assert app._schedule_analysis("u", run_id) is False


def test_progress_shows_a_truthful_stage_and_elapsed_time(tmp_path):
    app = _async_app(tmp_path)
    c, _, headers, _ = _submit(app)
    run_id = headers["Location"].split("/runs/")[1].split("/")[0]
    status, _, body = c.request("GET", f"/runs/{run_id}/progress")
    assert status.startswith("200") or status.startswith("303")
    if status.startswith("200"):
        assert "Running for" in body            # real elapsed, not a guess
        assert "%" not in body.split("<main")[1][:400] or "100%" not in body
        assert 'aria-live="polite"' in body     # accessible status
        assert "/analyses" in body              # a way back
        assert run_id not in body.split("<main")[1]   # no raw id on screen


def test_no_fake_percentage_or_countdown_anywhere_on_progress(tmp_path):
    app = _async_app(tmp_path)
    c, _, headers, _ = _submit(app)
    run_id = headers["Location"].split("/runs/")[1].split("/")[0]
    _, _, body = c.request("GET", f"/runs/{run_id}/progress")
    import re
    assert not re.search(r"\b\d{1,3}%\s*(complete|done)", body, re.I)
    assert "remaining" not in body.lower()


def test_stage_copy_never_invents_a_stage_that_did_not_run(tmp_path):
    app = _async_app(tmp_path)
    # every mapped key is a state the ingestion service actually transitions to
    assert app._stage_line(None) == "Still working through the available evidence"
    assert app._stage_line("DISCOVERING_SOURCES").startswith("Finding")
    assert app._stage_line("NOT_A_REAL_STATE") == (
        "Still working through the available evidence")


def test_another_visitor_cannot_see_the_run(tmp_path):
    app = _async_app(tmp_path)
    _, _, headers, _ = _submit(app)
    run_id = headers["Location"].split("/runs/")[1].split("/")[0]
    other = _WsgiClient(app)
    other.request("POST", "/demo")
    status, _, _ = other.request("GET", f"/runs/{run_id}/progress")
    assert status.startswith("404")


# --- the divergence guard ---------------------------------------------------
def test_the_product_is_async_by_default_in_every_environment(tmp_path):
    """This was briefly gated on env != "test", which left 3000+ tests
    exercising a path real users no longer receive. If someone reintroduces
    that gate to make a test easier, this fails."""
    cfg = AppConfig(env="test", secret="s" * 40, demo_mode=True,
                    web_store_path=tmp_path / "w.jsonl",
                    fi_store_path=tmp_path / "fi.jsonl",
                    ci_store_path=tmp_path / "ci.jsonl")
    app = WebApp(cfg, transport=_live_transport, resolver=False)
    assert app._analysis_async is True, (
        "the route suite must exercise the async path users receive")


def test_the_response_is_returned_before_the_work_finishes(tmp_path):
    """The decisive proof that the route is genuinely asynchronous.

    Observed INSIDE the request: at the moment the 303 is produced the run has
    not reached a terminal state. A synchronous route cannot satisfy this.
    """
    app = _async_app(tmp_path)
    observed = {}
    original = app._schedule_analysis

    def watching(user_id, run_id):
        scheduled = original(user_id, run_id)
        observed["state_at_response"] = app.ci.store.run_state(run_id)
        observed["run_id"] = run_id
        return scheduled

    app._schedule_analysis = watching
    c = _WsgiClient(app)
    c.request("POST", "/demo")
    status, headers, _ = c.request(
        "POST", "/analyze",
        f"consent=on&csrf={c.csrf()}&company_name=Acme"
        f"&website=https://acme.example")
    assert status.startswith("303")
    assert observed["state_at_response"] not in app.TERMINAL_STATES, (
        "the run was already finished when the response was built -- "
        "the route is still doing the work inline")
    assert app.wait_for_analysis(observed["run_id"], timeout=60)


# --- retry contract ---------------------------------------------------------
def _failed_run(tmp_path):
    def exploding(*a, **k):
        raise RuntimeError("network gone")
    app = _async_app(tmp_path, transport=exploding)
    c, _, headers, _ = _submit(app)
    run_id = headers["Location"].split("/runs/")[1].split("/")[0]
    assert app.wait_for_analysis(run_id, timeout=30)
    return app, c, run_id


def test_a_failed_run_offers_retry_and_explains_what_it_does(tmp_path):
    app, c, run_id = _failed_run(tmp_path)
    session = app.auth.session(c.cookie.split("=", 1)[1])
    state = app.retry_state(session, run_id)
    assert state["allowed"] is True
    assert "evidence pass again" in state["reason"]


def test_a_completed_run_is_not_offered_retry(tmp_path):
    """A finished result is not an error to recover from."""
    app = _async_app(tmp_path)
    c, _, headers, _ = _submit(app)
    run_id = headers["Location"].split("/runs/")[1].split("/")[0]
    assert app.wait_for_analysis(run_id, timeout=30)
    if app.ci.store.run_state(run_id) not in app.RETRYABLE_STATES:
        session = app.auth.session(c.cookie.split("=", 1)[1])
        assert app.retry_state(session, run_id)["allowed"] is False


def test_retry_is_bounded_and_cannot_loop(tmp_path):
    app, c, run_id = _failed_run(tmp_path)
    session = app.auth.session(c.cookie.split("=", 1)[1])
    for _ in range(app.MAX_ANALYSIS_ATTEMPTS + 2):
        if app._schedule_analysis("u", run_id, allow_retry=True):
            app.wait_for_analysis(run_id, timeout=30)
    assert app.attempt_count(run_id) <= app.MAX_ANALYSIS_ATTEMPTS
    assert app.retry_state(session, run_id)["allowed"] is False


def test_retry_does_not_stack_while_an_attempt_is_live(tmp_path):
    app, _, run_id = _failed_run(tmp_path)
    with app._analysis_lock:
        app._analysis_inflight[run_id] = 0.0        # pretend one is running
    try:
        assert app._schedule_analysis("u", run_id, allow_retry=True) is False
    finally:
        with app._analysis_lock:
            app._analysis_inflight.pop(run_id, None)


def test_retry_returns_to_progress_not_a_blocking_request(tmp_path):
    app, c, run_id = _failed_run(tmp_path)
    status, headers, _ = c.request(
        "POST", f"/runs/{run_id}/retry", f"csrf={c.csrf()}")
    assert status.startswith("303")
    assert headers["Location"].endswith("/progress")


def test_another_visitor_cannot_retry_someone_elses_run(tmp_path):
    app, _, run_id = _failed_run(tmp_path)
    other = _WsgiClient(app)
    other.request("POST", "/demo")
    status, _, _ = other.request("POST", f"/runs/{run_id}/retry",
                                 f"csrf={other.csrf()}")
    assert status.startswith("404")


# --- interruption -----------------------------------------------------------
def test_a_vanished_worker_becomes_interrupted_not_forever_running(tmp_path):
    """Free instances restart without warning. A run left RUNNING forever
    never finishes and never admits it.

    Built from a run whose worker never ran -- `_transition` is idempotent per
    (run, state), so a finished run cannot be rewound to fake this.
    """
    app = _async_app(tmp_path)
    run = app.ci.create_run(company_name="Acme",
                            website="https://acme.example",
                            user_id="u", as_of="2026-08-02T00:00:00+00:00")
    run_id = run["run_id"]
    app.ci._transition(run_id, run["domain"], "DISCOVERING_SOURCES")
    assert app.ci.store.run_state(run_id) not in app.TERMINAL_STATES
    app.STALE_ATTEMPT_SECONDS = -1               # everything is now stale
    assert app._interrupted_if_stale(run_id) is True
    assert app.ci.store.run_state(run_id) == "INTERRUPTED"


def test_a_live_attempt_is_never_called_stale(tmp_path):
    """A legitimately slow run must not be killed for being slow."""
    app = _async_app(tmp_path)
    run = app.ci.create_run(company_name="Acme",
                            website="https://acme.example",
                            user_id="u", as_of="2026-08-02T00:00:00+00:00")
    run_id = run["run_id"]
    app.ci._transition(run_id, run["domain"], "DISCOVERING_SOURCES")
    app.STALE_ATTEMPT_SECONDS = -1
    with app._analysis_lock:
        app._analysis_inflight[run_id] = 0.0     # a worker IS on it
    try:
        assert app._interrupted_if_stale(run_id) is False
    finally:
        with app._analysis_lock:
            app._analysis_inflight.pop(run_id, None)


def test_a_terminal_run_is_never_reopened_as_interrupted(tmp_path):
    app = _async_app(tmp_path)
    _, _, headers, _ = _submit(app)
    run_id = headers["Location"].split("/runs/")[1].split("/")[0]
    assert app.wait_for_analysis(run_id, timeout=30)
    before = app.ci.store.run_state(run_id)
    app.STALE_ATTEMPT_SECONDS = -1
    assert app._interrupted_if_stale(run_id) is False
    assert app.ci.store.run_state(run_id) == before
