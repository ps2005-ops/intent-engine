"""A dispatched future must not outlive the interactive budget.

`may_start()` decides whether to DISPATCH; it says nothing about how long the
caller then waits. Discovery joined two futures with a bare `.result()`, so a
sitemap crawl or an EDGAR full-text search begun while the budget was intact
could still be running long after it was gone, and the request sat in that
join however long it took.

MEASURED: Microsoft on 517180e6 -- discovery 27.7s, retrieval 40.5s, 63% of a
107.8s CORE, against a 60s interactive budget nothing in this path enforced.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from intent_engine.company_ingestion.deadline import Deadline
from intent_engine.company_ingestion.service import _bounded_result


@pytest.fixture
def pool():
    p = ThreadPoolExecutor(max_workers=2)
    yield p
    p.shutdown(wait=False)


def test_a_slow_future_does_not_outlive_the_budget(pool):
    d = Deadline(total_s=0.25)
    fut = pool.submit(lambda: (time.sleep(5), ["never"])[1])
    began = time.monotonic()
    out = _bounded_result(fut, d, "discovery", "sitemap crawl")
    waited = time.monotonic() - began
    assert out is None, "a source that missed the budget was still awaited"
    assert waited < 2.0, f"waited {waited:.1f}s on a 0.25s budget"
    assert d.gaps and d.gaps[0]["stage"] == "discovery", (
        "the reader is not told which source was dropped")


def test_a_fast_future_is_still_used(pool):
    """POSITIVE CONTROL: the bound must not simply discard everything."""
    d = Deadline(total_s=30)
    fut = pool.submit(lambda: ["candidate-a", "candidate-b"])
    assert _bounded_result(fut, d, "discovery") == ["candidate-a",
                                                    "candidate-b"]
    assert not d.gaps


def test_an_expired_budget_does_not_even_wait(pool):
    d = Deadline(total_s=0.01)
    time.sleep(0.05)
    fut = pool.submit(lambda: (time.sleep(5), ["never"])[1])
    began = time.monotonic()
    assert _bounded_result(fut, d, "discovery") is None
    assert time.monotonic() - began < 0.5
    assert d.gaps


def test_no_deadline_means_batch_behaviour_is_unchanged(pool):
    """Batch callers have no customer waiting and must not be degraded."""
    fut = pool.submit(lambda: ["x"])
    assert _bounded_result(fut, None, "discovery") == ["x"]


def test_the_joins_in_discovery_are_bounded():
    """Structural: the call sites must use the helper, not bare .result()."""
    import inspect

    from intent_engine.company_ingestion import service as SVC
    src = inspect.getsource(SVC.CompanyIngestionService.discover)
    code = "\n".join(l for l in src.splitlines()
                     if not l.lstrip().startswith("#"))
    for name in ("sitemap", "third_party"):
        assert f"{name}.result()" not in code, (
            f"{name} is joined with an unbounded .result()")
    assert "_bounded_result(" in code
    assert "shutdown(wait=True)" not in code, (
        "the pool shutdown re-introduces the wait the joins just bounded")
