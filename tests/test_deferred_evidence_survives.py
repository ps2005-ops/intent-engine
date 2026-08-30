"""§5/§24: evidence CORE did not wait for is acquired, not dropped.

These tests drive `WebApp._acquire_deferred` itself rather than its helpers.
A test that calls the helper directly passes with the CALL SITE deleted — the
"a fix with no caller stays green" defect, which this session has already
produced twice.
"""
from __future__ import annotations

import types

import pytest

from intent_engine.webapp.app import WebApp


class _Trace:
    def span(self, *_a, **_k):
        from contextlib import nullcontext
        return nullcontext({})


def _app_with(ci, results=None):
    """A WebApp shell holding only what `_acquire_deferred` reaches for."""
    app = WebApp.__new__(WebApp)
    app.ci = ci
    app._results = results if results is not None else {}
    app._analysis_deadlines = {}
    return app


class _FakeStore:
    def __init__(self, documents):
        self._documents = list(documents)

    def retrieved(self, _run_id):
        return list(self._documents)

    def failures(self, _run_id):
        return []


class _FakeCI:
    def __init__(self, *, arriving, deadline_sink):
        self.store = _FakeStore([{"url": "https://x.example/a"}])
        self._arriving = arriving
        self.deadlines = deadline_sink
        self.updates = []

    def fetch_approved(self, _run_id, *, candidate_ids=None, deadline=None):
        self.deadlines.append(deadline)
        self.store._documents.extend(self._arriving)
        return {"ok": [], "failed": [], "deferred": [], "sufficiency": None}

    def run_meta(self, _run_id):
        return {"domain": "x.example", "company_name": "X"}

    def record_analysis_updated(self, run_id, *, fields, new_documents,
                                reason):
        self.updates.append({"fields": list(fields),
                             "new_documents": new_documents,
                             "reason": reason})


def test_the_worker_gives_the_continuation_a_fresh_budget():
    """THE ASSERTION IS THE BUDGET HANDED TO THE FETCH, not a constructor."""
    from intent_engine.company_ingestion.deadline import (
        MIN_USEFUL_FETCH_S, Deadline,
    )
    from intent_engine.company_ingestion.records import CONNECT_TIMEOUT_S
    import time

    sink = []
    ci = _FakeCI(arriving=[{"url": "https://x.example/b"}],
                 deadline_sink=sink)
    app = _app_with(ci)
    # The interactive deadline is all but spent, exactly as it is by the time
    # `core_ready` has been marked.
    spent = Deadline.for_tier("tier1")
    spent.started_at = time.monotonic() - 59.0
    app._analysis_deadlines["r1"] = spent
    app._tier_for = lambda _run_id: "tier1"
    app._compose = lambda run_id, deep=False, trace=None: {
        "strategic_report": {"thesis": "same", "result_state": "X",
                             "status": "OK", "decision_implications": []}}

    core = {"strategic_report": {"thesis": "same", "result_state": "X",
                                 "status": "OK", "decision_implications": []}}
    app._acquire_deferred("r1", core, ["cand-1"], trace=_Trace())

    assert sink, "the deferred fetch was never made"
    handed = sink[0]
    assert handed is not spent, "the continuation reused the spent budget"
    assert handed.budget_for(CONNECT_TIMEOUT_S) >= MIN_USEFUL_FETCH_S, (
        "the continuation was handed a budget that refuses every source, so "
        "deferral would silently become deletion")


def test_a_changed_thesis_is_announced_not_swapped_in():
    """A recommendation that quietly becomes a different recommendation is
    worse than a slower one."""
    ci = _FakeCI(arriving=[{"url": "https://x.example/b"},
                           {"url": "https://x.example/c"}],
                 deadline_sink=[])
    app = _app_with(ci)
    app._analysis_deadlines["r1"] = None
    app._tier_for = lambda _run_id: "tier1"
    app._compose = lambda run_id, deep=False, trace=None: {
        "strategic_report": {"thesis": "the wider evidence says otherwise",
                             "result_state": "X", "status": "OK",
                             "decision_implications": ["act"]}}

    core = {"strategic_report": {"thesis": "the first answer",
                                 "result_state": "X", "status": "OK",
                                 "decision_implications": []}}
    out = app._acquire_deferred("r1", core, ["cand-1"], trace=_Trace())

    assert ci.updates, "the answer changed and the reader was not told"
    assert set(ci.updates[0]["fields"]) == {"thesis", "decision_implications"}
    assert ci.updates[0]["new_documents"] == 2
    assert out["strategic_report"]["thesis"] == \
        "the wider evidence says otherwise"


def test_an_unchanged_answer_is_not_announced():
    """An update signal that fires on every run tells a reader nothing."""
    ci = _FakeCI(arriving=[{"url": "https://x.example/b"}],
                 deadline_sink=[])
    app = _app_with(ci)
    app._analysis_deadlines["r1"] = None
    app._tier_for = lambda _run_id: "tier1"
    same = {"strategic_report": {"thesis": "steady", "result_state": "X",
                                 "status": "OK",
                                 "decision_implications": ["act"]}}
    app._compose = lambda run_id, deep=False, trace=None: same
    app._acquire_deferred("r1", same, ["cand-1"], trace=_Trace())
    assert not ci.updates


def test_nothing_new_means_no_recomposition():
    """Recomposing over identical evidence spends the CPU share that the deep
    pass is queued behind, and cannot change the answer."""
    ci = _FakeCI(arriving=[], deadline_sink=[])
    app = _app_with(ci)
    app._analysis_deadlines["r1"] = None
    app._tier_for = lambda _run_id: "tier1"
    composed = {"n": 0}

    def _compose(run_id, deep=False, trace=None):
        composed["n"] += 1
        return {"strategic_report": {}}

    app._compose = _compose
    core = {"strategic_report": {"thesis": "a"}}
    out = app._acquire_deferred("r1", core, ["cand-1"], trace=_Trace())
    assert composed["n"] == 0
    assert out is core


# ---------------------------------------------------------------------------
# THE TEST THAT WAS MISSING, and the reason 34 suite failures were the first
# thing to notice a change that had never been wired.
# ---------------------------------------------------------------------------
def test_the_worker_actually_passes_the_probe_to_acquisition():
    """`_run_analysis` must CALL the thing, not merely be able to.

    An edit added `_sufficiency_probe` and `_acquire_deferred` and failed to
    write the one line in `_run_analysis` that uses them. The helpers were
    complete, sixteen break proofs held and thirty-one focused tests passed,
    while every production run called `fetch_approved` with no probe and then
    raised `NameError: deferred_ids`. Nothing that drives a helper directly
    can see that; only something that drives the worker can.

    So this asserts on the ARGUMENTS acquisition was called with, taken from
    the real `_run_analysis` frame.
    """
    import inspect

    from intent_engine.webapp.app import WebApp

    raw = inspect.getsource(WebApp._run_analysis)
    # CODE, NOT PROSE. The first version of this test matched
    # `_acquire_deferred` inside the COMMENT that explains it and reported the
    # call was in the wrong place. A structural assertion that a comment can
    # satisfy is not a structural assertion.
    source = "\n".join(line for line in raw.split("\n")
                       if not line.strip().startswith("#"))
    assert "sufficiency_probe=self._sufficiency_probe(run_id)" in source, (
        "_run_analysis does not pass a sufficiency probe to fetch_approved — "
        "the minimum-CORE path is inert")
    # `deferred_ids` must be BOUND before the continuation reads it, on every
    # path -- including the one where the approval was already recorded and
    # the retrieval block is skipped entirely.
    assign = source.index("deferred_ids: list = []")
    guard = source.index("if deferred_ids:")
    assert assign < guard, (
        "`deferred_ids` is read before it is bound on the already-approved "
        "path")
    assert source.index("_acquire_deferred") > source.index(
        'mark_lifecycle(run_id, "core_ready")'), (
        "deferred evidence is acquired BEFORE core_ready, which is the wait "
        "this whole change exists to remove")
    # And the core trace must not wait for the continuation: two of ten cohort
    # rows already lost their spans to a narrower version of that window.
    assert source.index('record_trace(run_id, "core"') < source.index(
        "_acquire_deferred"), (
        "the core trace is recorded after the deferred acquisition, widening "
        "the window that already cost the two slowest rows their spans")
