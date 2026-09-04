"""The progress page may not ask the same read-only question three times.

`_progress` calls `result_readiness` up to three times, and each answer costs
several reads of the ingestion log -- the very log the running analysis is
appending to, so the parse cache misses every time. MEASURED on 743df06:
`/runs/<id>/progress` stopped answering for 100+ consecutive seconds during
analysis (AMD t=109, NVIDIA t=129) while `/version` stayed at 0.15s, and six
consecutive 45-second timeouts is how a live company became a FAILED row.

The memo is per REQUEST and lives on the thread-local, never on the app: one
shared between requests would show a visitor a state belonging to another.
"""
import threading

from intent_engine.webapp.app import WebApp


class _App(WebApp):
    """Counts the uncached computation without needing a live run."""

    def __init__(self):                                     # noqa: D107
        self.calls = 0
        self._request = threading.local()

    def _result_readiness(self, run_id):
        self.calls += 1
        return {"state": "READY_RESULT", "opens_result": True,
                "run": run_id, "terminal": True, "retryable": False}


def test_one_request_computes_it_once():
    app = _App()
    app._request.readiness = {}
    for _ in range(3):
        app.result_readiness("r1")
    assert app.calls == 1, app.calls


def test_a_different_run_in_the_same_request_is_its_own_answer():
    app = _App()
    app._request.readiness = {}
    a = app.result_readiness("r1")
    b = app.result_readiness("r2")
    assert app.calls == 2
    assert a["run"] == "r1" and b["run"] == "r2"


def test_the_next_request_does_not_inherit_the_answer(tmp_path):
    """THE SAFETY PROPERTY, THROUGH THE REAL REQUEST PATH.

    A first version of this set `_request.readiness` by hand to "simulate"
    what `__call__` does, and so asserted the behaviour of its own fixture:
    deleting the reset from `__call__` left it green. It drives the WSGI
    entry point now, because the reset being on that path is the whole
    claim -- a memo that outlived its request would hand one visitor a
    verdict computed for another.
    """
    from tests.test_strategic_intelligence import _WsgiClient
    from intent_engine.webapp.app import WebApp
    from intent_engine.webapp.config import AppConfig

    cfg = AppConfig(env="test", secret="s" * 40, demo_mode=True,
                    web_store_path=tmp_path / "w.jsonl",
                    fi_store_path=tmp_path / "fi.jsonl",
                    ci_store_path=tmp_path / "ci.jsonl")
    app = WebApp(cfg, resolver=False)
    client = _WsgiClient(app)
    client.request("GET", "/")
    seen = []
    real = type(app)._result_readiness
    try:
        type(app)._result_readiness = (
            lambda self, run_id: (seen.append(run_id),
                                  real(self, run_id))[1])
        # Two SEPARATE requests, each of which reads readiness at least once.
        for _ in range(2):
            client.request("GET", "/runs/01M0AAAAAAAAAAAAAAAAAAAAAA/progress")
    finally:
        type(app)._result_readiness = real
    assert len(seen) >= 2, (
        f"the second request reused the first request's memo ({seen})")


def test_another_thread_has_its_own_memo():
    app = _App()
    app._request.readiness = {}
    app.result_readiness("r1")
    seen = {}

    def other():
        app._request.readiness = {}
        seen["v"] = app.result_readiness("r1")
    t = threading.Thread(target=other)
    t.start()
    t.join()
    assert app.calls == 2, app.calls
    assert seen["v"]["run"] == "r1"


def test_it_still_answers_when_no_request_scope_exists():
    """Called off a request (a job, a test), it must compute rather than
    raise -- the memo is an optimisation, not a precondition."""
    app = _App()
    assert app.result_readiness("r1")["opens_result"] is True
    assert app.result_readiness("r1")["opens_result"] is True
    assert app.calls == 2
