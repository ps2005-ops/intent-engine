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


def _in_flight_progress(app):
    """The progress page for a run that has NOT finished.

    A submitted run reaches a terminal state before the assertion runs (the
    harness waits), and /progress then 303s -- so a gate written against the
    submitted run inspects an empty redirect body and passes vacuously. That
    is how the fake-percentage gate first "passed" while a percentage was on
    the page. Build a genuinely non-terminal run instead.
    """
    c = _WsgiClient(app)
    c.request("POST", "/demo")
    session = app.auth.session(c.cookie.split("=", 1)[1])
    run = app.ci.create_run(company_name="Acme",
                            website="https://acme.example",
                            user_id=session["user_id"],
                            as_of="2026-08-02T00:00:00+00:00")
    run_id = run["run_id"]
    from intent_engine.webapp.store import WebEvent
    app.web_store.append(WebEvent(
        event_type="web.run_owned", actor_type="human",
        actor_id=session["user_id"], subject_type="run", subject_id=run_id,
        idempotency_key=f"own:{run_id}",
        payload={"user_id": session["user_id"], "run_id": run_id}))
    app.ci._transition(run_id, run["domain"], "FETCHING_APPROVED_SOURCES")
    assert app.ci.store.run_state(run_id) not in app.TERMINAL_STATES
    status, _, body = c.request("GET", f"/runs/{run_id}/progress")
    assert status.startswith("200"), status
    return c, run_id, body


def test_no_fake_percentage_or_countdown_anywhere_on_progress(tmp_path):
    """BREAK PROOF B. The pipeline has no honest completion denominator, so
    any percentage on this page is invented."""
    import re
    app = _async_app(tmp_path)
    _, _, body = _in_flight_progress(app)
    assert "Running for" in body, "the page must show real elapsed time"
    # VISIBLE text only: `max-width:100%` in the stylesheet is not a claim
    # about completion, and a gate that trips on CSS gets deleted by the next
    # person rather than believed.
    visible = re.sub(r"<(style|script)[^>]*>.*?</\1>", " ", body,
                     flags=re.S | re.I)
    visible = re.sub(r"<[^>]+>", " ", visible)
    assert not re.search(r"\d{1,3}\s*%", visible), \
        f"a percentage is shown to the founder: {visible[:200]}"
    assert "remaining" not in visible.lower()
    assert "estimated" not in visible.lower()


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


# --- release-gate proofs: each of these must FAIL if the defect returns ------
def test_gate_c_a_terminal_run_never_shows_an_active_stage(tmp_path):
    """BREAK PROOF C. A run that finished while the page still showed
    "reading evidence" would poll forever and never say it was done.

    Driven from a run transitioned to COMPLETE directly. Written against a
    submitted run this passed vacuously: the test transport has no network, so
    those runs end FAILED and the completion branch was never reached.
    """
    app = _async_app(tmp_path)
    c, run_id, body = _in_flight_progress(app)
    assert "Reading the most relevant material" in body     # active, polling
    assert 'http-equiv="refresh"' in body

    meta = app.ci.run_meta(run_id)
    app.ci._transition(run_id, meta["domain"], "COMPLETE")
    status, headers, body = c.request("GET", f"/runs/{run_id}/progress")
    assert status.startswith("303"), (
        f"terminal run still rendered a progress page: {status}")
    assert headers["Location"] == f"/runs/{run_id}"


def test_gate_d_one_attempt_executes_exactly_once(tmp_path):
    """BREAK PROOF D. Measured, not inferred: two workers on one attempt can
    produce an identical-looking result while doing the work twice.

    The duplicate is scheduled WHILE the first is in flight. Scheduling it
    after completion passed vacuously -- the terminal check refused it for a
    different reason than the one under test.
    """
    import threading
    release = threading.Event()

    def slow(*a, **k):
        release.wait(timeout=10)
        raise RuntimeError("done")

    app = _async_app(tmp_path, transport=slow)
    c = _WsgiClient(app)
    c.request("POST", "/demo")
    run = app.ci.create_run(company_name="Acme",
                            website="https://acme.example", user_id="u",
                            as_of="2026-08-02T00:00:00+00:00")
    run_id = run["run_id"]
    assert app._schedule_analysis("u", run_id) is True
    for _ in range(200):                      # wait for the worker to enter
        if app._worker_starts.get(run_id):
            break
        time.sleep(0.01)
    # the duplicate arrives while the first attempt is genuinely running
    assert app._schedule_analysis("u", run_id) is False, \
        "a second worker was scheduled onto a live attempt"
    release.set()
    assert app.wait_for_analysis(run_id, timeout=30)
    assert app._worker_starts.get(run_id, 0) == 1, app._worker_starts
    assert app._terminal_writes.get(run_id, 0) == 1, app._terminal_writes


def test_gate_e_refresh_keeps_the_same_run_and_attempt(tmp_path):
    """BREAK PROOF E. Losing the run on refresh strands the founder with no
    way back to work that is still running."""
    app = _async_app(tmp_path)
    c, _, headers, _ = _submit(app)
    run_id = headers["Location"].split("/runs/")[1].split("/")[0]
    starts = app._worker_starts.get(run_id, 0)
    for _ in range(3):                            # refresh repeatedly
        status, _, _ = c.request("GET", f"/runs/{run_id}/progress")
        assert not status.startswith("404"), "owner lost their own run"
    assert app._worker_starts.get(run_id, 0) == starts, \
        "a refresh started another attempt"
    assert app.wait_for_analysis(run_id, timeout=60)
    _, _, listing = c.request("GET", "/analyses")
    assert run_id[:10] in listing, "the run vanished from history"


def test_gate_f_a_failed_run_is_never_dressed_as_a_limited_result(tmp_path):
    """BREAK PROOF F. A failure rendered as "Limited analysis" claims the
    evidence review completed when it did not."""
    def exploding(*a, **k):
        raise RuntimeError("network gone")
    app = _async_app(tmp_path, transport=exploding)
    c, _, headers, _ = _submit(app)
    run_id = headers["Location"].split("/runs/")[1].split("/")[0]
    assert app.wait_for_analysis(run_id, timeout=60)
    assert app.ci.store.run_state(run_id) == "FAILED"
    _, _, body = c.request("GET", f"/runs/{run_id}")
    assert "could not be completed" in body
    assert "Limited analysis" not in body, "a failure is posing as a result"


# --- capacity ---------------------------------------------------------------
def test_capacity_is_explicitly_bounded(tmp_path):
    """The queue lives in this process. An unbounded one is a memory leak
    with a friendly name."""
    app = _async_app(tmp_path)
    assert app.MAX_ACTIVE_ANALYSES == 1        # free instance
    assert app.MAX_PENDING_ANALYSES >= 1
    assert app.MAX_PENDING_ANALYSES < 100


def test_work_beyond_capacity_is_refused_not_silently_dropped(tmp_path):
    import threading
    release = threading.Event()

    def slow(*a, **k):
        release.wait(timeout=10)
        raise RuntimeError("done")

    app = _async_app(tmp_path, transport=slow)
    limit = app.MAX_ACTIVE_ANALYSES + app.MAX_PENDING_ANALYSES
    accepted, runs = 0, []
    for i in range(limit + 3):
        run = app.ci.create_run(company_name=f"Acme{i}",
                                website=f"https://acme{i}.example",
                                user_id="u",
                                as_of="2026-08-02T00:00:00+00:00")
        runs.append(run["run_id"])
        if app._schedule_analysis("u", run["run_id"]):
            accepted += 1
    assert accepted <= limit, f"accepted {accepted} beyond a bound of {limit}"
    release.set()
    for run_id in runs:
        app.wait_for_analysis(run_id, timeout=30)


def test_a_refused_submission_never_leaves_a_run_claiming_to_run(tmp_path):
    """A run accepted but never executed would poll forever."""
    app = _async_app(tmp_path)
    app.MAX_ACTIVE_ANALYSES = 0
    app.MAX_PENDING_ANALYSES = 0
    run = app.ci.create_run(company_name="Acme",
                            website="https://acme.example", user_id="u",
                            as_of="2026-08-02T00:00:00+00:00")
    assert app._schedule_analysis("u", run["run_id"]) is False
    assert run["run_id"] not in app._analysis_inflight


# --- terminal-state matrix --------------------------------------------------
def test_every_terminal_state_stops_polling_and_drops_the_active_stage(
        tmp_path):
    """An INTERRUPTED run polled forever under 'Reading the public
    evidence...': the progress page's terminal set omitted it, and the
    stale-marker refuses to re-mark a run it already marked."""
    for state in ("FAILED", "REJECTED", "INTERRUPTED"):
        app = _async_app(tmp_path / state)
        c, _, headers, _ = _submit(app)
        run_id = headers["Location"].split("/runs/")[1].split("/")[0]
        app.wait_for_analysis(run_id, timeout=30)
        meta = app.ci.run_meta(run_id) or {}
        app.ci._transition(run_id, meta.get("domain", ""), state)
        _, _, html = c.request("GET", f"/runs/{run_id}/progress")
        assert 'http-equiv="refresh"' not in html, (
            f"{state} keeps polling a run that will never advance")
        assert "Reading the public evidence" not in html, (
            f"{state} still shows an active stage")


def test_interrupted_says_so_rather_than_implying_work_continues(tmp_path):
    app = _async_app(tmp_path)
    c, _, headers, _ = _submit(app)
    run_id = headers["Location"].split("/runs/")[1].split("/")[0]
    app.wait_for_analysis(run_id, timeout=30)
    meta = app.ci.run_meta(run_id) or {}
    app.ci._transition(run_id, meta.get("domain", ""), "INTERRUPTED")
    _, _, html = c.request("GET", f"/runs/{run_id}/progress")
    assert "interrupt" in html.lower() or "stopped" in html.lower()


# --- rate-limit honesty -----------------------------------------------------
def test_a_refused_demo_says_when_to_come_back():
    """"Please try again later" is not an answer to "when?" -- and the
    window is already known at the point of refusal."""
    from intent_engine.webapp.app import _retry_phrase
    assert _retry_phrase(30) == "You can try again in under a minute."
    assert _retry_phrase(600) == "You can try again in about 11 minutes."
    assert "hours" in _retry_phrase(7200)
    # never promise a moment that has already passed
    assert _retry_phrase(-5) == "You can try again in under a minute."


def test_the_rate_limit_page_carries_a_time_and_reassures_about_live_runs(
        tmp_path):
    cfg = AppConfig(env="test", secret="s" * 40, demo_mode=True,
                    web_store_path=tmp_path / "w.jsonl",
                    fi_store_path=tmp_path / "fi.jsonl",
                    ci_store_path=tmp_path / "ci.jsonl",
                    demo_ip_analyses_per_hour=1)
    app = WebApp(cfg, transport=_live_transport, resolver=False)
    app._analysis_async = True
    c = _WsgiClient(app)
    c.request("POST", "/demo")
    body = (f"consent=on&csrf={c.csrf()}&company_name=Acme"
            f"&website=https://acme.example")
    c.request("POST", "/analyze", body)
    status, _, html = c.request("POST", "/analyze", body)
    assert status.startswith("429")
    assert "try again in" in html
    assert "already running are unaffected" in html
