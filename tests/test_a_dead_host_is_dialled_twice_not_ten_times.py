"""BW10-005: a host that will not answer must not be paid for repeatedly.

MEASURED, NOT GUESSED. On the breaker cohort, AMD and McKinsey each took ten
read timeouts at CONNECT_TIMEOUT_S=8 — about eighty seconds — and they were
the only two runs over 150 seconds (p50 18.5s, p95 178.9s). The same dead host
was then dialled again by discovery and by the bounded rediscovery passes, so
the eighty seconds was paid roughly three times.

THE FIX IS NOT A SHORTER TIMEOUT. Eight seconds is a reasonable budget for a
slow but real server, and cutting it would drop genuine evidence. The defect
is that the run had no memory: the tenth URL on a silent host learned exactly
what the first one did.

WHAT IT MUST NOT DO. Suppress a host on a 404 or a 403 — those are about the
path or the request. Suppress a host on a single transient timeout. Or drop a
candidate silently: a skipped candidate is recorded as `host_unreachable`,
retryable, which is a statement about us and never about the company.
"""
from __future__ import annotations

import email
import urllib.error

import pytest

from intent_engine.company_ingestion.service import CompanyIngestionService

BASE = "https://slowco.example"


DEAD = "dead.slowco.example"
DEAD_PAGES = [f"https://{DEAD}/p{i}" for i in range(1, 11)]


class _Counter:
    """A transport that counts dials per host. `fail_host` never answers.

    The dead host is a SUBDOMAIN of the company so discovery will admit it —
    an earlier version used an unrelated domain, discovery correctly refused
    it, and the load-bearing assertion skipped instead of running.
    """

    def __init__(self, fail_host: str = DEAD, mode="timeout"):
        self.fail_host = fail_host
        self.mode = mode
        self.dials = {}

    def __call__(self, url, timeout):
        from urllib.parse import urlparse
        host = urlparse(url).hostname or ""
        self.dials[host] = self.dials.get(host, 0) + 1
        if host == self.fail_host:
            if self.mode == "timeout":
                raise TimeoutError("The read operation timed out")
            raise urllib.error.HTTPError(
                url, 404, "not found", email.message_from_string(""), None)
        links = "".join(f'<a href="{u}">page {u[-2:]}</a>' for u in DEAD_PAGES)
        body = (f'<html><head><title>Slow Co</title>'
                f'<meta name="description" content="Slow Co sells widgets.">'
                f'</head><body><h1>Slow Co</h1>'
                f'<p>Slow Co sells widgets to enterprise buyers.</p>'
                f'{links}</body></html>').encode()
        return 200, {"content-type": "text/html"}, body, False


def test_a_silent_host_is_dialled_twice_not_ten_times(tmp_path):
    """THE LOAD-BEARING PROOF: dials, not seconds.

    Ten approved URLs on a host that never answers must cost two dials, not
    ten. Counting DIALS rather than wall time keeps the assertion honest on a
    fast machine and on a slow one.
    """
    transport = _Counter()
    service = CompanyIngestionService(str(tmp_path / "ci.jsonl"),
                                      transport=transport, resolver=False)
    run = service.create_run(company_name="Slow Co", website=BASE,
                             user_id="u", as_of="2026-08-12T00:00:00+00:00")
    run_id = run["run_id"]
    candidates = service.discover(run_id)
    dead = [c for c in candidates if DEAD in (c.get("url") or "")]
    assert len(dead) >= 4, (
        f"the fixture must approve several URLs on the dead host to prove "
        f"anything; discovery produced {len(dead)}")

    before = transport.dials.get(DEAD, 0)
    service.approve(run_id, user_id="u",
                    approved_ids=[c["candidate_id"] for c in dead],
                    rejected_ids=[c["candidate_id"] for c in candidates
                                  if c not in dead])
    outcome = service.fetch_approved(run_id)
    spent = transport.dials.get(DEAD, 0) - before

    assert spent <= CompanyIngestionService._DEAD_HOST_AFTER, (
        f"the run dialled a silent host {spent} times for {len(dead)} "
        f"candidates; the breaker exists to stop after "
        f"{CompanyIngestionService._DEAD_HOST_AFTER}")
    assert "host_unreachable" in {f.get("failure_type")
                                  for f in outcome["failed"]}
    # every skipped candidate is RECORDED, never silently dropped
    assert len(outcome["ok"]) + len(outcome["failed"]) == len(dead)


def test_the_breaker_does_not_fire_on_a_host_that_answers(tmp_path):
    """The negative control. A healthy host must be dialled for every
    candidate — a breaker that trips on success would silently cost evidence,
    and this test fails if it does."""
    transport = _Counter(fail_host="nothing.invalid")
    service = CompanyIngestionService(str(tmp_path / "ci.jsonl"),
                                      transport=transport, resolver=False)
    run = service.create_run(company_name="Slow Co", website=BASE,
                             user_id="u", as_of="2026-08-12T00:00:00+00:00")
    run_id = run["run_id"]
    candidates = service.discover(run_id)
    live = [c for c in candidates if DEAD in (c.get("url") or "")][:5]
    assert live
    service.approve(run_id, user_id="u",
                    approved_ids=[c["candidate_id"] for c in live],
                    rejected_ids=[c["candidate_id"] for c in candidates
                                  if c not in live])
    outcome = service.fetch_approved(run_id)
    assert "host_unreachable" not in {f.get("failure_type")
                                      for f in outcome["failed"]}
    assert len(outcome["ok"]) == len(live)


def test_host_level_failures_are_counted_and_path_failures_are_not(tmp_path):
    """The classification that keeps one missing page from closing a host."""
    assert "timeout" in CompanyIngestionService._HOST_LEVEL_FAILURES
    assert "connection" in CompanyIngestionService._HOST_LEVEL_FAILURES
    assert "http_status" not in CompanyIngestionService._HOST_LEVEL_FAILURES
    assert "too_large" not in CompanyIngestionService._HOST_LEVEL_FAILURES


def test_the_breaker_trips_after_two_and_not_after_one():
    assert CompanyIngestionService._DEAD_HOST_AFTER == 2


def test_an_unreachable_host_is_a_recorded_refusal_not_a_silent_drop():
    """`host_unreachable` must be a host-refusal so downstream selection
    stops recommending that host, and must be retryable — the host may be
    fine tomorrow, and this is a statement about us."""
    assert "host_unreachable" in \
        CompanyIngestionService._HOST_REFUSAL_FAILURES


def test_counting_ignores_failures_whose_candidate_is_unknown():
    """A failure whose candidate cannot be resolved must not be attributed
    to some other host, which would suppress an innocent one."""
    class _Store:
        @staticmethod
        def failures(_):
            return [{"failure_type": "timeout", "candidate_id": "cand-gone"},
                    {"failure_type": "timeout", "candidate_id": "cand-1"}]

    service = CompanyIngestionService.__new__(CompanyIngestionService)
    service.store = _Store()
    counts = service._host_failure_counts(
        "r", {"cand-1": {"url": "https://a.example/x"}})
    assert counts == {"a.example": 1}


def test_a_page_level_failure_never_closes_the_host():
    class _Store:
        @staticmethod
        def failures(_):
            return [{"failure_type": "http_status", "candidate_id": "c"},
                    {"failure_type": "http_status", "candidate_id": "c"},
                    {"failure_type": "too_large", "candidate_id": "c"}]

    service = CompanyIngestionService.__new__(CompanyIngestionService)
    service.store = _Store()
    counts = service._host_failure_counts(
        "r", {"c": {"url": "https://a.example/x"}})
    assert counts == {}


@pytest.mark.parametrize("kind", ["timeout", "connection"])
def test_two_host_level_failures_are_enough_to_close_a_host(kind):
    class _Store:
        @staticmethod
        def failures(_):
            return [{"failure_type": kind, "candidate_id": "c1"},
                    {"failure_type": kind, "candidate_id": "c2"}]

    service = CompanyIngestionService.__new__(CompanyIngestionService)
    service.store = _Store()
    counts = service._host_failure_counts("r", {
        "c1": {"url": "https://dead.example/a"},
        "c2": {"url": "https://dead.example/b"}})
    assert counts["dead.example"] >= CompanyIngestionService._DEAD_HOST_AFTER


def test_one_failure_is_not_enough():
    class _Store:
        @staticmethod
        def failures(_):
            return [{"failure_type": "timeout", "candidate_id": "c1"}]

    service = CompanyIngestionService.__new__(CompanyIngestionService)
    service.store = _Store()
    counts = service._host_failure_counts(
        "r", {"c1": {"url": "https://dead.example/a"}})
    assert counts["dead.example"] < CompanyIngestionService._DEAD_HOST_AFTER


def test_hosts_are_counted_separately():
    """A dead host must not close a healthy sibling."""
    class _Store:
        @staticmethod
        def failures(_):
            return [{"failure_type": "timeout", "candidate_id": "c1"},
                    {"failure_type": "timeout", "candidate_id": "c2"},
                    {"failure_type": "timeout", "candidate_id": "c3"}]

    service = CompanyIngestionService.__new__(CompanyIngestionService)
    service.store = _Store()
    counts = service._host_failure_counts("r", {
        "c1": {"url": "https://dead.example/a"},
        "c2": {"url": "https://dead.example/b"},
        "c3": {"url": "https://alive.example/c"}})
    assert counts["dead.example"] == 2
    assert counts["alive.example"] == 1
