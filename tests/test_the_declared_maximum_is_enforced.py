"""The page promises "up to two minutes". Amazon took 141.1s.

MEASURED on the 10-company cohort at c7c28d52: CORE p50 104.7s, max 141.1s
against a declared interactive maximum of 120s, with no terminal behaviour --
the reader was told something untrue and then left waiting past it.

`may_start()` decided whether a FETCH could begin. Nothing bounded
composition, which is 44s of that median and the largest single bucket.
"""
from __future__ import annotations

import time

from intent_engine.company_ingestion.deadline import Deadline
from intent_engine.strategic_intelligence.observations import (
    derive_observations,
)


def _docs(n, chars=4000):
    body = ("The Company designs and sells subscription software to "
            "enterprise customers, and earns revenue from recurring "
            "licences. " * (chars // 100))
    return [{"final_url": f"https://acme.example/{i}", "title": f"page {i}",
             "text_content": body, "content_hash": f"h{i}",
             "source_class": "company_owned", "source_type": "company_owned"}
            for i in range(n)]


def test_an_expired_budget_stops_reading_documents():
    d = Deadline(total_s=0.01)
    time.sleep(0.05)
    assert d.expired
    out = derive_observations(_docs(40), company="Acme Inc.", deadline=d)
    assert out == [], "an expired budget still read the whole document set"
    assert d.gaps, "the reader is not told which documents went unread"
    assert d.gaps[0]["stage"] == "observations"


def test_a_live_budget_reads_everything():
    """POSITIVE CONTROL: the bound must not simply stop the stage working.

    Without this, `return []` passes the test above and deletes the product --
    which is the exact failure this phase already shipped once.
    """
    d = Deadline(total_s=60)
    out = derive_observations(_docs(6), company="Acme Inc.", deadline=d)
    assert not d.gaps
    baseline = derive_observations(_docs(6), company="Acme Inc.")
    assert len(out) == len(baseline), (
        "a live budget changed what the stage produced")


def test_no_deadline_is_unchanged_behaviour():
    """Batch callers have no customer waiting and must not be degraded."""
    docs = _docs(6)
    assert derive_observations(docs, company="Acme Inc.", deadline=None) == \
        derive_observations(docs, company="Acme Inc.")


def test_the_deadline_reaches_composition_from_the_quality_gate():
    """Structural: the thread from `compose_with_quality` to the loop.

    `compose_with_quality` has always HELD a deadline; nothing carried it
    into the stage that spends the time. A parameter with no caller is not
    enforcement.
    """
    import inspect

    from intent_engine.company_ingestion import service as SVC

    def code(fn):
        return "\n".join(l for l in inspect.getsource(fn).splitlines()
                         if not l.lstrip().startswith("#"))

    # EVERY call site, not "the string appears somewhere". `compose_with_
    # quality` calls `self.compose` twice -- traced and untraced -- and a grep
    # passes while one of them silently runs unbounded. That mutation was not
    # caught until it was tried.
    gate = code(SVC.CompanyIngestionService.compose_with_quality)
    # EACH call site, examined on its own. Counting the string does not work:
    # this method also passes `deadline=` to several `trace.span(...)` calls,
    # so a compose call can silently lose it while the total stays the same.
    # That mutation survived the first version of this assertion.
    import re
    sites = re.findall(r"self\.compose\((?:[^()]|\([^()]*\))*\)", gate,
                       re.S)
    assert len(sites) >= 2, (
        "call-site shape changed; this gate is not looking at it")
    unbounded = [c for c in sites if "deadline=deadline" not in c]
    assert not unbounded, (
        f"{len(unbounded)} of {len(sites)} composition call sites run "
        f"unbounded: {[c[:60] for c in unbounded]}")
    assert "deadline=deadline" in code(SVC.CompanyIngestionService.compose), \
        "compose does not pass the deadline to the strategic report"
    assert "deadline=deadline" in code(
        SVC.CompanyIngestionService._strategic_report), \
        "the strategic report does not pass the deadline to the loop"


def test_the_stage_stops_between_documents_not_inside_one():
    """A half-read document would produce an excerpt that is not what the
    document says, and a wrong finding is worse than a missing one."""
    import inspect

    from intent_engine.strategic_intelligence import observations as O
    src = inspect.getsource(O.derive_observations)
    body = src[src.index("for doc in documents:"):]
    stop = body.index("break")
    first_read = body.index('doc.get("text_content"')
    assert stop < first_read, (
        "the deadline is checked after the document has been read, so the "
        "loop can stop having half-processed one")


def test_discovery_reports_which_of_its_stages_cost_what():
    """23.2s reported as one number cannot be repaired.

    Discovery is the second largest bucket in the cohort and it is five
    stages: a homepage fetch, a sitemap walk, an EDGAR proposal, an identity
    resolution and a curated fallback. Ranking them needs them named -- the
    same reason `core_composition` had to be subdivided before the 18s of
    discarded work inside it could be found.
    """
    import inspect

    from intent_engine.company_ingestion import service as SVC
    code = "\n".join(
        l for l in inspect.getsource(SVC.CompanyIngestionService.discover
                                     ).splitlines()
        if not l.lstrip().startswith("#"))
    for stage in ("edgar_propose", "identity_resolve", "official_fallback"):
        assert f'trace.mark("{stage}"' in code, f"{stage} is not timed"


def test_the_worker_passes_its_trace_into_discovery():
    """A span the production path never reaches records nothing."""
    import inspect

    from intent_engine.webapp.app import WebApp
    for name in dir(WebApp):
        fn = getattr(WebApp, name, None)
        try:
            src = inspect.getsource(fn)
        except (OSError, TypeError):
            continue
        if 'trace.span("discovery"' in src:
            assert "self.ci.discover(run_id, trace=trace" in src, (
                "discovery is timed but the worker does not hand it the trace")
            return
    raise AssertionError("no worker opens a discovery span")
