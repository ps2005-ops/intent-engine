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
    """The handler must return WHILE the analysis is still running.

    This asserted `elapsed < 2.0`, which is a proxy for the property and a
    wall-clock bound on a shared machine: it failed once inside a 6000-test
    guard run while passing 3/3 alone, on a change that could not reach this
    path at all. A timing threshold cannot tell a blocking handler from a busy
    laptop.

    The property itself is an ORDER, so it is asserted as one. The worker is
    held on a latch that this test controls; if the POST carried the analysis
    it could not return until the latch was released, and the latch is only
    released after the response has been asserted. No duration is measured,
    and the test is not slower for being correct.
    """
    import threading

    app = _async_app(tmp_path)
    holding = threading.Event()
    released = threading.Event()
    real = app._run_analysis

    def _held(user_id, run_id):
        holding.set()
        # Bounded so a genuine regression fails the test instead of hanging
        # the suite. The bound is a deadlock escape, never the assertion.
        released.wait(timeout=30)
        return real(user_id, run_id)

    app._run_analysis = _held
    c, status, headers, _ = _submit(app)

    assert status.startswith("303")
    assert headers["Location"].endswith("/progress")
    # THE REGRESSION THIS CATCHES: a return to the blocking POST. The worker
    # has started and has NOT been allowed to finish, yet the handler already
    # answered -- which a synchronous handler cannot do.
    assert holding.wait(timeout=30), "the worker never started"
    assert not released.is_set()

    released.set()
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
    # ACTIVE, POLLING -- asserted against the canonical hydration vocabulary
    # rather than one frozen sentence. This read "Reading the most relevant
    # material", which was the generic lifecycle stage line the progress page
    # showed before `hydration.assess` was wired to it. The intent of the gate
    # is that an unfinished run shows an active stage and a finished one does
    # not; which words say so is the product's business, and pinning the old
    # sentence would have made this gate fail for a page that got better.
    from intent_engine.founder_brief import hydration as _H
    active = list(_H.TIER_COPY.values()) + ["Reading the most relevant "
                                            "material"]
    assert any(line in body for line in active), (
        "the in-flight progress page shows no active stage at all")
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


def test_gate_g_a_failed_transition_does_not_erase_a_reading_that_exists(
        tmp_path):
    """BREAK PROOF G, the converse of F, and just as damaging.

    "FAILED" is the LAST transition, not the whole story: the evidence loop can
    fail a pass, transition FAILED, and retrieve on a later one. Measured live
    on preview-v3 (Alphabet, https://abc.xyz): `/brief` served 820 words off
    the composed dossier while the PRIMARY screen served a failure page saying
    the run produced nothing.

    A run that composed a reading is a bounded result, not a failure, and the
    primary screen renders the same founder brief it renders for every other
    run. The state stays FAILED and the failure detail stays reachable.
    """
    app = _async_app(tmp_path)
    c, _, headers, _ = _submit(app)
    run_id = headers["Location"].split("/runs/")[1].split("/")[0]
    assert app.wait_for_analysis(run_id, timeout=60)
    assert app._retrieved_documents(run_id), "fixture must retrieve something"
    assert app._availability(run_id)["has_report"], \
        "fixture must compose a reading for this test to bite"

    # exactly the state Alphabet was in: FAILED, with a composed dossier
    meta = app.ci.run_meta(run_id)
    app.ci._transition(run_id, meta["domain"], "FAILED")
    assert app.ci.store.run_state(run_id) == "FAILED"

    status, _, body = c.request("GET", f"/runs/{run_id}")
    assert not str(status).startswith("5"), f"primary answered {status}"
    assert "no approved source could be retrieved" not in body
    assert "could not be completed" not in body, \
        "a composed reading is being shown as a failure"
    assert len(_main_text(body).split()) > 150, "primary carries no analysis"


def _main_text(html):
    import re as _re
    m = _re.search(r"<main\b[^>]*>(.*?)</main>", html, _re.S | _re.I)
    inner = _re.sub(r"<(script|style)[^>]*>.*?</\1>", " ",
                    m.group(1) if m else html, flags=_re.S | _re.I)
    return " ".join(_re.sub(r"<[^>]+>", " ", inner).split())


def test_no_run_route_mutates_the_run_while_the_worker_is_working(tmp_path):
    """The reads were writes.

    `_autorun` approves and fetches and `_real_result` composes — both from a
    GET. A reader refreshing during the analysis raced the worker doing the
    same thing: that is the live 400 at t=0 (a lost approval race) and the live
    500 that followed (a compose racing a compose). Measured on preview-v3 at
    a183f51, all six routes sampled together at t=0: `/`=400 while
    `/progress`, `/brief`, `/full`, `/slides` and `/sources` all answered 200.

    Held in flight explicitly rather than by timing, so this cannot pass by
    finishing first.
    """
    app = _async_app(tmp_path)
    c, _, headers, _ = _submit(app)
    run_id = headers["Location"].split("/runs/")[1].split("/")[0]
    assert app.wait_for_analysis(run_id, timeout=60)

    def explode(*a, **k):
        raise AssertionError("a GET mutated a run that is still in flight")

    # Drop the cached result, so a handler that reaches for `_real_result`
    # has to COMPOSE — which is exactly the write this must not perform.
    app._results.pop(run_id, None)
    with app._analysis_lock:
        app._analysis_inflight[run_id] = time.monotonic()
    approve, fetch, compose = app.ci.approve, app.ci.fetch_approved, app._compose
    app.ci.approve = app.ci.fetch_approved = app._compose = explode
    try:
        for suffix in ("", "/brief", "/full", "/slides"):
            status, _h, _b = c.request("GET", f"/runs/{run_id}{suffix}")
            code = str(status).split()[0]
            assert not code.startswith(("4", "5")), \
                f"{suffix or '/'} answered {status} while in flight"
    finally:
        app.ci.approve, app.ci.fetch_approved = approve, fetch
        app._compose = compose
        with app._analysis_lock:
            app._analysis_inflight.pop(run_id, None)


def test_the_availability_projection_never_composes(tmp_path):
    """It is consulted on every request, so it must not be able to do work."""
    app = _async_app(tmp_path)
    c, _, headers, _ = _submit(app)
    run_id = headers["Location"].split("/runs/")[1].split("/")[0]
    assert app.wait_for_analysis(run_id, timeout=60)
    app._results.pop(run_id, None)

    def explode(*a, **k):
        raise AssertionError("_availability composed a result")

    original, app._compose = app._compose, explode
    try:
        avail = app._availability(run_id)
    finally:
        app._compose = original
    assert avail["level"] in (
        app.AVAIL_NO_CONTENT, app.AVAIL_IN_PROGRESS, app.AVAIL_BOUNDED,
        app.AVAIL_FULL, app.AVAIL_FAILURE)


def test_gate_g3_a_failed_run_with_evidence_leads_with_what_it_could_read(
        tmp_path):
    """Alphabet's EXACT shape, which gate G did not model.

    Measured live on preview-v3 at c9afbc7, run 01KZB7BBJ43ZKYXE5CG4VEHMCQ:
    FAILED, five sources read including the 10-K and 10-Q, and NO composed
    strategic report — so the `has_report` branch never fired and the primary
    screen served a 278-word failure page while `/brief`, off the same run,
    served 1060 words. `_founder_layers` and `_founder_brief_page` both
    tolerate a missing report; the primary screen was the only surface that
    would not.
    """
    app = _async_app(tmp_path)
    c, _, headers, _ = _submit(app)
    run_id = headers["Location"].split("/runs/")[1].split("/")[0]
    assert app.wait_for_analysis(run_id, timeout=60)
    assert app._retrieved_documents(run_id), "fixture must retrieve something"

    # documents, a result, but no composed reading — and FAILED
    app._results[run_id] = dict(app._results[run_id] or {},
                                strategic_report=None)
    meta = app.ci.run_meta(run_id)
    app.ci._transition(run_id, meta["domain"], "FAILED")
    assert not app._availability(run_id)["has_report"]

    status, _, body = c.request("GET", f"/runs/{run_id}")
    assert not str(status).startswith("5"), f"primary answered {status}"
    assert "no approved source could be retrieved" not in body
    text = _main_text(body)
    assert len(text.split()) > 150, \
        f"primary carries no analysis ({len(text.split())} words)"
    # and the deeper layers still agree with it
    for suffix in ("/brief", "/full", "/slides"):
        deep, _h, _b = c.request("GET", f"/runs/{run_id}{suffix}")
        assert not str(deep).startswith("5"), f"{suffix} answered {deep}"


def test_gate_g4_composition_failure_still_leaves_a_useful_bounded_result(
        tmp_path):
    """BREAK PROOF G4 — the measured Alphabet cause, not a hypothetical one.

    Five fresh Alphabet runs on 568f7ec ended identically: five sources read
    including the 10-K and the 10-Q, and composition raising
    `PersonalError: claim text overclaims: ['always']` — the editorial
    language wall refusing one sentence. The wall is right to refuse it. It
    was wrong that refusing one sentence threw the whole run away and served a
    failure page for a company whose filings had been read.

    The run stays FAILED. The reader does not lose it.
    """
    app = _async_app(tmp_path)

    real_compose = app._compose
    calls = {"n": 0}

    def exploding_compose(run_id):
        calls["n"] += 1
        real_compose(run_id)                     # retrieval really happened
        raise ValueError("claim text overclaims: ['always']")

    app._compose = exploding_compose
    c, _, headers, _ = _submit(app)
    run_id = headers["Location"].split("/runs/")[1].split("/")[0]
    assert app.wait_for_analysis(run_id, timeout=90)
    assert calls["n"], "compose was never reached"

    assert app.ci.store.run_state(run_id) == "FAILED", \
        "the run's own state must stay honest"
    assert app._retrieved_documents(run_id), "fixture must retrieve something"

    status, _h, body = c.request("GET", f"/runs/{run_id}")
    assert not str(status).startswith(("4", "5")), f"primary answered {status}"
    text = _main_text(body)
    assert "no approved source could be retrieved" not in text
    assert "could not be completed" not in text, \
        "a run with usable evidence is still shown as a failure"
    assert len(text.split()) > 150, \
        f"the reader lost the run ({len(text.split())} words)"
    # nothing invented, and no exception text ever reaches a reader
    for leaked in ("overclaims", "ValueError", "Traceback"):
        assert leaked not in body, f"exception detail leaked: {leaked}"
    # AND IT SCORES AS THE PRODUCT'S OWN INSTRUMENT SEES IT, unchanged.
    # Naming five sources and then saying nothing could be read is the same
    # untruth the failure page had, so the bounded surface must say what it
    # read, what is missing, and what to do next.
    from intent_engine.webapp import acceptance as _acc
    verdict = _acc.score(body, company="Acme")
    assert verdict["state"] in (_acc.USEFUL_FULL, _acc.USEFUL_BOUNDED), \
        f"scored {verdict['state']}: {verdict['reasons']}"
    # and the page may not contradict itself: "N page(s) read" printed above
    # "No usable public source could be read" was live at 19a9c5d.
    assert not ("page(s) read" in text
                and "No usable public source could be read" in text), \
        "the page says both that it read sources and that it read none"


def test_gate_g5_the_fallback_needs_evidence_and_invents_nothing(tmp_path):
    """It may not manufacture a result out of nothing, and it may not carry a
    recommendation the composer never produced."""
    app = _async_app(tmp_path)
    c, _, headers, _ = _submit(app)
    run_id = headers["Location"].split("/runs/")[1].split("/")[0]
    assert app.wait_for_analysis(run_id, timeout=60)

    bounded = app._bounded_result(run_id, ValueError("x"))
    assert bounded is not None
    assert bounded["strategic_report"] is None, "the fallback invented a report"
    assert not bounded["sections"], "the fallback invented sections"
    assert bounded["readiness"]["may_synthesize"] is False
    assert bounded["observations"], "the fallback dropped the evidence"
    assert bounded["composition_failure"]["error_class"] == "ValueError"
    assert "x" not in str(bounded["composition_failure"]), \
        "the exception message reached the result"

    # deterministic: same run, same facts, same object
    assert app._bounded_result(run_id, ValueError("x")) == bounded

    # and with nothing retrieved there is nothing to offer
    app._retrieved_documents = lambda _rid: ()
    assert app._bounded_result(run_id, ValueError("x")) is None


def test_gate_g2_a_run_that_really_retrieved_nothing_still_says_so(tmp_path):
    """The other half: the honest sentence must survive for the run it was
    written for, or this fix has simply moved the lie."""
    def exploding(*a, **k):
        raise RuntimeError("network gone")
    app = _async_app(tmp_path, transport=exploding)
    c, _, headers, _ = _submit(app)
    run_id = headers["Location"].split("/runs/")[1].split("/")[0]
    assert app.wait_for_analysis(run_id, timeout=60)
    assert not app._retrieved_documents(run_id)
    _, _, body = c.request("GET", f"/runs/{run_id}")
    assert "no approved source could be retrieved" in body
    assert "source(s) were read" not in body


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
        # A REDIRECT BODY WOULD SATISFY BOTH ASSERTIONS VACUOUSLY. Clear the
        # result so this run genuinely has nothing to open and the progress
        # page must actually render — otherwise the test passes on an empty
        # string and can no longer fail for the reason it was written.
        app._results.pop(run_id, None)
        _, _, html = c.request("GET", f"/runs/{run_id}/progress")
        assert html.strip(), f"{state} rendered no page to check"
        assert 'http-equiv="refresh"' not in html, (
            f"{state} keeps polling a run that will never advance")
        assert "Reading the public evidence" not in html, (
            f"{state} still shows an active stage")


def test_interrupted_says_so_rather_than_implying_work_continues(tmp_path):
    """An interrupted run WITH NOTHING TO SHOW says it stopped.

    The result must be cleared first, and that is the point rather than a
    fixture detail: a run that was interrupted after producing something
    readable now OPENS that result instead of reporting a stop, because a
    customer-ready result outranks stale worker metadata. Leaving the result
    in place made this assertion read an empty redirect body and pass for a
    reason that had nothing to do with the wording it checks.
    """
    app = _async_app(tmp_path)
    c, _, headers, _ = _submit(app)
    run_id = headers["Location"].split("/runs/")[1].split("/")[0]
    app.wait_for_analysis(run_id, timeout=30)
    meta = app.ci.run_meta(run_id) or {}
    app.ci._transition(run_id, meta.get("domain", ""), "INTERRUPTED")
    app._results.pop(run_id, None)
    assert app.result_readiness(run_id)["opens_result"] is False
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
