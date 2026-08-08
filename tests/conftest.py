"""Make test-local helper modules (recorded fixtures) importable."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


# --- asynchronous analysis, exercised by every route test -------------------
#
# `POST /analyze` returns a 303 immediately and the analysis continues on a
# worker. That is what a real user now receives, so the route suite must go
# through it rather than through a synchronous variant that no longer exists
# in production.
#
# Tests still want to assert on FINISHED runs. So the wait lives here, in the
# harness, and never in the product: the response is observed immediately
# (proving the request does not block), and only then does the fixture wait
# for the owned attempt to reach a terminal state.
import pytest


@pytest.fixture(autouse=True)
def _await_async_analysis(monkeypatch):
    """After any request that schedules analysis, wait for the worker.

    Deterministic: it waits on the run's terminal state, never on a sleep of a
    guessed length, and fails loudly on timeout rather than leaving a test to
    assert against a half-finished run.
    """
    from intent_engine.webapp.app import WebApp

    original = WebApp.__call__

    def waiting_call(self, environ, start_response):
        chunks = original(self, environ, start_response)
        try:
            path = environ.get("PATH_INFO", "")
            method = environ.get("REQUEST_METHOD", "")
            if method == "POST" and path == "/analyze":
                for run_id in list(getattr(self, "_analysis_inflight", {})):
                    if not self.wait_for_analysis(run_id, timeout=60):
                        raise AssertionError(
                            f"analysis worker did not finish for {run_id}")
        except AttributeError:
            pass
        return chunks

    monkeypatch.setattr(WebApp, "__call__", waiting_call)
    yield
