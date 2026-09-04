"""A failed run may not present analysis on four pages and refusal on two.

MEASURED LIVE on 4952649. SEC EDGAR rate-limited the preview's egress and
every source for Meta Platforms came back HTTP 429, so the run FAILED having
retrieved nothing. What the customer saw:

    /full     "This analysis could not be completed … no approved source
               could be retrieved. There is no result to show — we do not
               invent one."
    /slides    the same
    /intro    "Meta Platforms, Inc. is a software platform business that
               runs on recurring software subscription: revenue is
               contracted and renews…"
    /story, /history, /connect   rendered

One run, six pages, two irreconcilable answers — and the confident four are
the ones a customer opens first. The business model was wrong as well, read
off SIC 7370 alone because the filing that says Meta sells advertising was
never retrieved; that is what a run with no evidence is: the SIC code's
guess, presented in the voice of a finding.

`/full` and `/slides` each carried the check. The other four never got it,
because it was written into the two pages rather than into the guard they
all share.
"""
from __future__ import annotations

import inspect

from intent_engine.webapp import app as APP


class _Session(dict):
    pass


class _App:
    """The smallest object `_step_guard` needs, with the run's state dialled
    in. Constructing the real WSGI app would test the harness, not the guard.
    """

    def __init__(self, availability):
        self._availability_value = availability
        self.failed_page_shown = False

    _owned = staticmethod(lambda session, run_id: True)

    def _availability(self, run_id):
        return self._availability_value

    def _error_page(self, code, msg):
        return ("error", code, msg)

    def _redirect(self, where):
        return ("redirect", where)

    def _failed_run_page(self, session, run_id):
        self.failed_page_shown = True
        return ("failed", run_id)

    def result_readiness(self, run_id):
        """The real contract, computed from the dialled-in availability.

        `only_watchable` asks this, so the double has to answer it or the
        guard under test cannot run. Mirrors the one line of the real
        implementation that decides `opens_result`: a result is readable when
        there is a report, or a bounded reading over documents that were
        actually retrieved.
        """
        avail = self._availability_value
        readable = bool(avail.get("has_report")
                        or (avail.get("has_result") and avail.get("documents")))
        return {"opens_result": readable, "in_flight": avail.get("in_flight")}

    # BORROWED, NOT REIMPLEMENTED. `only_watchable` is what stopped the
    # progress/run-page redirect loop, and a double with its own version
    # would let the real one drift away from the guard that depends on it.
    only_watchable = APP.WebApp.only_watchable
    _step_guard = APP.WebApp._step_guard


FAILED_NO_REPORT = {"in_flight": False, "state": "FAILED", "has_report": False}
FAILED_WITH_REPORT = {"in_flight": False, "state": "FAILED", "has_report": True}
COMPLETE = {"in_flight": False, "state": "COMPLETE", "has_report": True}
BOUNDED = {"in_flight": False, "state": "COMPLETE", "has_report": False,
           "documents": 3}


def test_a_failed_run_with_no_report_is_refused_on_every_step():
    app = _App(FAILED_NO_REPORT)
    assert app._step_guard(_Session(), "run-1") == ("failed", "run-1")
    assert app.failed_page_shown


def test_a_failed_run_that_still_composed_a_report_is_not_refused():
    """§ A BOUNDED READ REPLACES THE REFUSAL. Partial retrieval that still
    produced a report is a smaller analysis, not a failure, and refusing it
    would throw away work the reader can use."""
    app = _App(FAILED_WITH_REPORT)
    assert app._step_guard(_Session(), "run-2") is None
    assert not app.failed_page_shown


def test_a_completed_run_is_not_refused():
    app = _App(COMPLETE)
    assert app._step_guard(_Session(), "run-3") is None


def test_a_run_with_documents_and_no_report_is_not_refused():
    """The bounded state is not the failed state. Documents retrieved but no
    composed report still has something honest to show."""
    app = _App(BOUNDED)
    assert app._step_guard(_Session(), "run-4") is None


def test_an_in_flight_run_still_goes_to_progress_first():
    app = _App({"in_flight": True, "state": "RUNNING", "has_report": False})
    assert app._step_guard(_Session(), "run-5") == ("redirect",
                                                    "/runs/run-5/progress")


def test_every_step_page_goes_through_the_shared_guard():
    """THE SEAM. The check was correct in two page functions and absent from
    four; putting it in the guard is worth nothing if a page stops calling
    the guard."""
    source = inspect.getsource(APP.WebApp)
    # ALL SIX STEPS BY NAME. The first version of this test named three,
    # and `/story` — the one page that had kept its own ownership check
    # instead of calling the guard — was not among them. It rendered a full
    # narrative for a run with no evidence while the other five refused.
    for page in ("_intro_page", "_history_page", "_answer_page",
                 "_story_page", "_slides_page", "_connect_page"):
        body = source.split(f"def {page}(")[1].split("\n    def ")[0]
        assert "_step_guard" in body, f"{page} must go through the guard"
