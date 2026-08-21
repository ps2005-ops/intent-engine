"""The harness, the product and a real socket, with a real instance replaced.

WHY IN-PROCESS TESTS WERE NOT ENOUGH. Every guard for the recovery path so
far calls the WSGI app directly. That proves the application logic and proves
nothing about the thing that actually broke: a client with its own cookie jar,
talking HTTP, across an instance replacement. The two of two lost canary runs
were lost by exactly that client against exactly that boundary, and the four
instrument defects before them were all found at seams a direct call skips.

So this runs the real `pre100.capture` session against a real server on a real
port, replaces the instance underneath it, and requires the harness to reach
the same verdict it would reach live.

No network: the transport is disabled, so the synthetic demo company is what
is analysed. That is enough -- the question here is lifecycle, not evidence.
"""
import io
import threading
import wsgiref.simple_server

import pytest

from intent_engine.pre100 import capture as C
from intent_engine.webapp import run_recovery as R
from intent_engine.webapp.app import WebApp
from intent_engine.webapp.config import AppConfig

SECRET = "s" * 40


def _no_network(url, timeout):
    raise OSError("test transport: network disabled")


class _Swappable:
    """A WSGI app whose implementation can be replaced under a live socket.

    This is the instance replacement, modelled at the only place a client can
    observe it: the port stays open, the cookies stay in the jar, and the
    application behind them is a different process's worth of state.
    """

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        return self.app(environ, start_response)


class _Quiet(wsgiref.simple_server.WSGIRequestHandler):
    def log_message(self, *args):        # keep the suite's output readable
        pass


def _build(tmp_path):
    return WebApp(AppConfig(env="development", secret=SECRET, demo_mode=True,
                            autorun_sources=True,
                            web_store_path=tmp_path / "web.jsonl",
                            fi_store_path=tmp_path / "fi.jsonl",
                            ci_store_path=tmp_path / "ci.jsonl"),
                  transport=_no_network, resolver=False)


@pytest.fixture(autouse=True)
def _restore_boot_id():
    """BOOT_ID is a MODULE global, so a test that forges one forges it for
    every test after it.

    Found by this file failing only when run whole: the first test replaced
    the boot id and never put it back, so the second test's "replacement" was
    a no-op and `restart_observed` read False. A leaked global that makes a
    later assertion pass would have been the dangerous direction of the same
    bug.
    """
    import intent_engine.webapp.storage_state as ss
    original, started = ss.BOOT_ID, ss._PROCESS_STARTED
    yield
    ss.BOOT_ID, ss._PROCESS_STARTED = original, started


@pytest.fixture
def server(tmp_path):
    holder = _Swappable(_build(tmp_path / "instance-1"))
    httpd = wsgiref.simple_server.make_server(
        "127.0.0.1", 0, holder, handler_class=_Quiet)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        yield holder, base, tmp_path
    finally:
        httpd.shutdown()
        httpd.server_close()


def _open_a_run(base):
    """A guest starts an analysis, exactly as `capture_company` does."""
    session = C.Session(base, timeout=60)
    session.get("/")
    session.post("/demo", {})
    _s, _u, entry = session.get("/demo")
    csrf = C.Session.csrf(entry)
    assert csrf, "no csrf on the entry page"
    status, url, page = session.post(
        "/analyze", {"csrf": csrf, "consent": "on",
                     "website": "https://northwind-demo.example"})
    assert "/runs/" in url, (status, C.text_of(page)[:300])
    return session, csrf, url.split("/runs/")[1].split("/")[0]


def test_the_process_identity_changes_when_the_instance_is_replaced(server):
    holder, base, tmp_path = server
    before = C.process_identity(base)
    assert before.get("boot_id"), before
    # A rebuilt app inside one interpreter shares the module-level BOOT_ID, so
    # the identity is forced here rather than pretended: this asserts the
    # CLIENT can see a change, which is the property the harness relies on.
    holder.app = _build(tmp_path / "instance-2")
    import intent_engine.webapp.storage_state as ss
    ss.BOOT_ID = "boot-of-the-second-instance"
    ss._PROCESS_STARTED = None
    after = C.process_identity(base)
    assert C._restart_observed(before, after) is True, (before, after)


def test_a_run_survives_nothing_and_is_still_never_a_dead_end(server):
    """The measured failure, reproduced and then required to end well."""
    holder, base, tmp_path = server
    session, csrf, run_id = _open_a_run(base)

    # The customer reaches a result before the instance goes.
    state, landed, seconds, _samples = C.wait_for_run(session, run_id,
                                                      timeout=90, poll=1)
    assert state == C.READY, (state, seconds)

    holder.app = _build(tmp_path / "instance-2")      # the instance is replaced

    status, _url, page = session.get(f"/runs/{run_id}")
    body = C.text_of(page)
    assert status == 200, status
    assert "lost when the service restarted" in body.lower(), body[:400]
    assert "does not have an analysis with that id" not in body.lower()
    # And the harness must NAME it rather than store it as content.
    assert C.run_is_gone(body)


def test_the_harness_reports_a_lost_run_with_the_restart_that_caused_it(
        server, tmp_path):
    """`capture_company` end to end, with the instance replaced mid-journey.

    This is the whole point: a wave of fifty must be able to say WHY a company
    is missing. A row that says RUN_LOST and nothing else sent a previous
    session hunting for an application bug that was an instance replacement.
    """
    holder, base, root = server
    import intent_engine.webapp.storage_state as ss
    original_boot = ss.BOOT_ID

    real_wait = C.wait_for_run

    def replace_after_the_result(session, run_id, **kwargs):
        outcome = real_wait(session, run_id, **kwargs)
        # Replace the instance in the exact window the canaries lost: after
        # the run is readable, before the questions are asked.
        holder.app = _build(root / "instance-2")
        ss.BOOT_ID = "boot-of-the-instance-that-took-over"
        ss._PROCESS_STARTED = None
        return outcome

    C.wait_for_run = replace_after_the_result
    try:
        row = C.capture_company(
        "Northwind Demo", base=base,
        website="https://northwind-demo.example",
                                root=tmp_path / "captures", sha="localproof")
    finally:
        C.wait_for_run = real_wait
        ss.BOOT_ID = original_boot

    assert row["status"] == C.RUN_LOST, row
    assert row["restart_observed"] is True, row
    assert row.get("answers_captured") == 0, row
    # Nothing was stored as an answer.
    import json
    import pathlib
    manifest = json.loads(
        (pathlib.Path(row["capture_path"]) / "manifest.json").read_text())
    assert manifest["status"] == C.RUN_LOST
    assert not (pathlib.Path(row["capture_path"]) / "qa.json").exists()


def test_ten_real_answers_are_captured_when_nothing_is_replaced(server,
                                                                tmp_path):
    """THE POSITIVE CONTROL, and the one that catches the dead Q&A route.

    Without this the suite could pass with a harness that never captures an
    answer at all -- which is very close to what was happening.
    """
    holder, base, root = server
    row = C.capture_company(
        "Northwind Demo", base=base,
        website="https://northwind-demo.example",
                            root=tmp_path / "captures", sha="localproof")
    assert row["status"] == C.READY, row
    import json
    import pathlib
    qa = json.loads(
        (pathlib.Path(row["capture_path"]) / "qa.json").read_text())
    assert len(qa) == len(C.BOARD_QUESTIONS), len(qa)
    for answer in qa:
        assert not C.not_an_answer(answer["answer"], answer["status"]), answer
        assert not C.run_is_gone(answer["answer"])
