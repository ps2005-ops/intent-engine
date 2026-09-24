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


def test_an_optional_branch_cannot_spend_the_whole_budget(pool):
    """Bounded by "everything that is left" is not bounded in practice.

    MEASURED on NVIDIA at 6aefd58e: discovery 35.0s at 2% CPU, of which ~18s
    was the join on the third-party filing search. That wait WAS bounded --
    by `deadline.remaining`, which on a 60s budget is 40s and therefore never
    bit. A source class the product can do without does not get to decide how
    long the reader waits.
    """
    d = Deadline(total_s=60)
    fut = pool.submit(lambda: (time.sleep(5), ["late"])[1])
    began = time.monotonic()
    out = _bounded_result(fut, d, "discovery", "third-party search",
                          cap_s=0.3)
    waited = time.monotonic() - began
    assert out is None
    assert waited < 2.0, (
        f"an optional branch waited {waited:.1f}s with a 0.3s cap and 60s "
        f"of budget remaining")
    assert d.gaps


def test_the_cap_does_not_shorten_a_required_wait(pool):
    """POSITIVE CONTROL: `cap_s` is opt-in, and REQUIRED work is unaffected."""
    d = Deadline(total_s=60)
    fut = pool.submit(lambda: (time.sleep(0.4), ["evidence"])[1])
    assert _bounded_result(fut, d, "discovery") == ["evidence"]
    assert not d.gaps


def test_the_cap_never_extends_the_budget(pool):
    """A generous cap may not override an exhausted deadline."""
    d = Deadline(total_s=0.01)
    time.sleep(0.05)
    fut = pool.submit(lambda: (time.sleep(5), ["never"])[1])
    began = time.monotonic()
    assert _bounded_result(fut, d, "discovery", cap_s=30.0) is None
    assert time.monotonic() - began < 0.5, (
        "a large cap let an expired budget keep waiting")


def test_both_optional_discovery_branches_are_capped():
    """Structural: the sitemap walk and the filing search both take the cap.

    Capping one and not the other leaves the run's wait decided by whichever
    was forgotten.
    """
    import inspect
    import re

    from intent_engine.company_ingestion import service as SVC
    code = "\n".join(
        l for l in inspect.getsource(SVC.CompanyIngestionService.discover
                                     ).splitlines()
        if not l.lstrip().startswith("#"))
    sites = re.findall(r"_bounded_result\((?:[^()]|\([^()]*\))*\)", code, re.S)
    assert len(sites) >= 2, "join shape changed; this gate is not looking at it"
    # OPTIONAL ONLY. The EDGAR proposal is joined the same way and must NOT
    # carry this cap: it is the authoritative source for a filer and the one
    # branch a run cannot do without, so capping it at an optional branch's
    # share would drop required evidence to save time. The cap is about what
    # the product can live without, not about which calls happen to be joins.
    optional = [c for c in sites
                if "sitemap" in c or "third_party" in c or "third-party" in c]
    assert len(optional) >= 2, (
        "the optional branches are no longer identifiable in this gate")
    uncapped = [c for c in optional if "cap_s=" not in c]
    assert not uncapped, (
        f"{len(uncapped)} optional discovery join(s) uncapped: "
        f"{[c[:50] for c in uncapped]}")
    required = [c for c in sites if c not in optional]
    assert all("cap_s=" not in c for c in required), (
        "a REQUIRED join took the optional cap; that drops evidence the run "
        "needs in order to save time an optional branch was spending")


def test_edgar_asks_for_only_the_filings_the_run_is_entitled_to():
    """The EDGAR proposal is NOT dispatched in parallel, on purpose.

    MEASURED on NVIDIA at 6aefd58e: it did not start until t+11.2s, queued
    behind a homepage fetch whose links it never reads. Reclaiming that six
    seconds means dispatching before the homepage answers -- which means
    requesting the LARGER limit (5 rather than 3) and truncating, because the
    limit is the one thing it does take from the homepage.

    Truncating gives an identical candidate list and a DIFFERENT request
    count: every run with a working homepage would make two extra requests to
    SEC. `test_the_blocked_budget_is_strictly_larger_and_is_the_one_used`
    pins that property; this test states the trade at the call site so the
    next reader does not re-derive it from scratch and re-break it.
    """
    import inspect

    from intent_engine.company_ingestion import service as SVC
    code = "\n".join(
        l for l in inspect.getsource(SVC.CompanyIngestionService.discover
                                     ).splitlines()
        if not l.lstrip().startswith("#"))
    assert "_pool.submit(\n                propose_edgar_candidates" not in code, (
        "EDGAR is dispatched before the homepage answers, so its limit must "
        "be the larger one -- which makes extra SEC requests on every healthy "
        "run")
    assert "MAX_EDGAR_CANDIDATES_WEB_BLOCKED" in code and \
        "MAX_EDGAR_CANDIDATES" in code, (
        "the two limits are no longer both reachable, so the blocked budget "
        "cannot be the larger one")


def test_the_pool_has_a_worker_for_each_independent_branch():
    """Three branches through a pool of two queues one behind another and
    gives back the wall time the dispatch change exists to remove."""
    import inspect

    from intent_engine.company_ingestion import service as SVC
    code = inspect.getsource(SVC.CompanyIngestionService.discover)
    submits = code.count("_pool.submit(")
    workers = int(code.split("max_workers=")[1].split(",")[0].split(")")[0])
    assert workers >= submits, (
        f"{submits} branches dispatched into a pool of {workers}")
