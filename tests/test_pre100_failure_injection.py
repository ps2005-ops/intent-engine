"""§17: bounded failure proofs for the minimum-evidence CORE architecture.

Each injects ONE failure and asserts the product's declared behaviour under
it. Nothing here asserts a latency; these are about what survives.

The rule being tested throughout: an OPTIONAL failure costs its source and a
labelled gap, a REQUIRED failure costs the claim, and neither costs the run
or leaves the reader on a spinner.
"""
from __future__ import annotations

import datetime as dt

import pytest

from intent_engine.company_ingestion import sufficiency
from intent_engine.company_ingestion.deadline import Deadline
from intent_engine.company_ingestion.service import CompanyIngestionService

ENGLISH = ("The company reported revenue growth in the quarter ending March "
           "2026 and described its operating segments in detail. ")


def _page(url):
    body = (ENGLISH + f" This page is {url}. " + ENGLISH * 4).encode()
    return b"<html><body><p>" + body + b"</p></body></html>"


class _Injector:
    """A transport that answers normally except where told otherwise."""

    def __init__(self, *, fail_hosts=(), fail_status=(), hang_hosts=(),
                 malformed_hosts=()):
        self.calls = []
        self.fail_hosts = tuple(fail_hosts)
        self.fail_status = dict(fail_status)
        self.hang_hosts = tuple(hang_hosts)
        self.malformed_hosts = tuple(malformed_hosts)

    def __call__(self, url, timeout, max_bytes=2_000_000):
        import urllib.error
        self.calls.append(url)
        host = url.split("/")[2] if "//" in url else url
        if any(h in url for h in self.hang_hosts):
            raise TimeoutError("timed out")
        for pattern, code in self.fail_status.items():
            if pattern in url:
                raise urllib.error.HTTPError(url, code, "refused", {}, None)
        if any(h in url for h in self.fail_hosts):
            raise OSError("connection refused")
        if any(h in url for h in self.malformed_hosts):
            return (200, {"content-type": "text/html"}, b"<html><body></body>",
                    False)
        return (200, {"content-type": "text/html"}, _page(url), False)


def _run(tmp_path, transport, n=14):
    ci = CompanyIngestionService(tmp_path / "ci.jsonl", transport=transport,
                                 resolver=False)
    run = ci.create_run(company_name="Widget Co",
                        website="https://widget.example", user_id="u",
                        as_of=dt.date.today().isoformat())
    run_id = run["run_id"] if isinstance(run, dict) else run
    ids = []
    for i in range(n):
        cid = f"cand-{i:012d}"
        host = "widget.example" if i % 3 else "optional.example"
        ci._append("ci.candidate_discovered", run_id=run_id,
                   domain=ci.run_meta(run_id)["domain"],
                   subject_type="candidate", subject_id=cid,
                   payload={"candidate_id": cid,
                            "url": f"https://{host}/page-{i}",
                            "source_type": ["identity", "product", "investor",
                                            "customers", "blog", "pricing",
                                            "about", "careers"][i % 8],
                            "source_class": "company_owned",
                            "discovery_method": "known_path",
                            "company_id": ci.run_meta(run_id)["domain"],
                            "rank": i, "availability": "PROPOSED",
                            "same_domain": True, "why_relevant": "test"},
                   idempotency_key=f"cand:{run_id}:{cid}")
        ids.append(cid)
    ci.approve(run_id, user_id="u", approved_ids=ids, rejected_ids=[])
    # IDENTITY IS A PRECONDITION, not part of what these proofs inject.
    # Without it `assess_readiness` returns IDENTITY_UNRESOLVED and the
    # sufficiency probe can never close, so every deferral proof would be
    # measuring a fixture that never reaches the code under test.
    ci._identity_for(run_id, ci.run_meta(run_id))
    return ci, run_id, ids


def _probe(ci, run_id):
    def probe(documents):
        return sufficiency.evaluate(
            documents, identity=ci.entity_identity(run_id),
            failures=list(ci.store.failures(run_id)), subject_cik="")
    return probe


def test_one_source_403_costs_that_source_and_not_the_run(tmp_path):
    tx = _Injector(fail_status={"page-4": 403})
    ci, run_id, ids = _run(tmp_path, tx)
    result = ci.fetch_approved(run_id)
    assert result["status"] in ("PARTIAL", "COMPLETE")
    assert len(result["ok"]) >= 10
    failed = [f for f in result["failed"] if f["failure_type"] == "http_status"]
    assert failed, "the 403 was not recorded as a failure"
    assert "403" in failed[0]["safe_message"]


def test_a_malformed_source_is_refused_not_admitted_as_empty(tmp_path):
    """An empty document would silently pad an evidence-free report."""
    tx = _Injector(malformed_hosts=("page-2",))
    ci, run_id, ids = _run(tmp_path, tx)
    result = ci.fetch_approved(run_id)
    kinds = {f["failure_type"] for f in result["failed"]}
    assert "javascript_only" in kinds or "parse_error" in kinds
    for record in result["ok"]:
        assert (record.get("text_content") or "").strip()


def test_a_hanging_host_is_bounded_and_recorded_as_a_gap(tmp_path):
    tx = _Injector(hang_hosts=("optional.example",))
    ci, run_id, ids = _run(tmp_path, tx)
    deadline = Deadline.for_tier("tier1")
    result = ci.fetch_approved(run_id, deadline=deadline)
    assert result["ok"], "a hanging optional host took the whole run"
    assert result["failed"], "the hang was not recorded"


def test_a_deferred_source_that_fails_is_recorded_never_silent(tmp_path):
    tx = _Injector(fail_status={"page-9": 403, "page-11": 500})
    ci, run_id, ids = _run(tmp_path, tx)
    first = ci.fetch_approved(run_id, sufficiency_probe=_probe(ci, run_id))
    deferred = list(first["deferred"])
    assert deferred, "nothing deferred — the fixture does not exercise this"
    ci.fetch_approved(run_id, candidate_ids=deferred,
                      deadline=Deadline.for_continuation("tier1"))
    retrieved = {r["source_id"] for r in ci.store.retrieved(run_id)}
    failed = {f.get("candidate_id") for f in ci.store.failures(run_id)}
    dropped = [c for c in deferred
               if f"src-{c[5:]}" not in retrieved and c not in failed]
    assert not dropped, f"deferred sources vanished: {dropped}"


def test_core_survives_when_every_optional_host_is_dead(tmp_path):
    """Sufficient evidence from the company's own domain must still compose."""
    tx = _Injector(fail_hosts=("optional.example",))
    ci, run_id, ids = _run(tmp_path, tx)
    result = ci.fetch_approved(run_id, sufficiency_probe=_probe(ci, run_id))
    assert result["ok"], "CORE produced nothing while its own domain answered"
    # Every document came from the host that answered, and every refusal from
    # the dead host is a RECORDED fact about a request rather than a silent
    # absence or a finding about the company.
    assert all("widget.example" in (r.get("original_url") or "")
               for r in result["ok"])
    dead = [f for f in result["failed"]
            if "optional.example" in str(f.get("safe_message", ""))
            or f["failure_type"] in ("connection", "timeout",
                                     "host_unreachable")]
    assert dead, "the dead optional host produced no recorded failure"


def test_when_nothing_answers_the_run_is_terminal_not_endless(tmp_path):
    """A bounded abstention is a valid product outcome; a spinner is not."""
    tx = _Injector(fail_hosts=("widget.example", "optional.example"))
    ci, run_id, ids = _run(tmp_path, tx)
    result = ci.fetch_approved(run_id, sufficiency_probe=_probe(ci, run_id))
    assert result["status"] == "FAILED"
    assert len(result["failed"]) == 14
    assert not result["ok"]
    # Every refusal is a RECORDED fact about a request, not a claim about the
    # company, and every approved candidate is accounted for.
    assert len(ci.store.failures(run_id)) == 14
