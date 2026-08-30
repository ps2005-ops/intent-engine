"""A WARM run must do less, not merely say WARM.

MEASURED on the preview: Microsoft spent 27.7s in discovery re-proposing a
source list it had already built -- homepage fetch, sitemap walk, EDGAR search,
third-party filing search, curated fallback -- before one byte of evidence was
retrieved. On a company already read, none of that is new information.

These tests assert the EXPENSIVE CALLS DO NOT HAPPEN, not that a status field
says WARM. A planner nothing consumes is architecture theatre.
"""
from __future__ import annotations

import time

import pytest

from intent_engine.company_ingestion import service as SVC
from intent_engine.company_ingestion import snapshot as SN


@pytest.fixture
def svc(tmp_path):
    return SVC.CompanyIngestionService(path=tmp_path / "ci.jsonl")


def _seed_snapshot(svc, *, cik="0000789019", domain="microsoft.com",
                   age_s=60.0, urls=("https://microsoft.com/investor",
                                     "https://sec.gov/msft-10k")):
    now = time.time()
    key = SN.company_key("Microsoft Corporation", cik=cik, domain=domain)
    snap = SN.PublicCompanySnapshot(
        company_key=key, canonical_name="Microsoft Corporation",
        cik=cik, domains=(domain,),
        sources=tuple(SN.SourceRecord(url=u, source_class="company_owned")
                      for u in urls),
        created_at=now - age_s, refreshed_at=now - age_s)
    assert svc.snapshots.put(snap)
    return snap


def _run(svc, *, cik="0000789019", domain="microsoft.com"):
    run_id = svc.start(company_name="Microsoft Corporation",
                       website=f"https://{domain}") \
        if hasattr(svc, "start") else None
    return run_id


def test_a_warm_run_does_not_call_any_discovery_source(svc, tmp_path,
                                                       monkeypatch):
    """The point of the whole change: the expensive calls do not happen."""
    _seed_snapshot(svc)
    called = []
    for name in ("discover_candidates", "propose_edgar_candidates",
                 "propose_external_candidates", "official_fallback_candidates"):
        if hasattr(SVC, name):
            monkeypatch.setattr(SVC, name,
                                lambda *a, _n=name, **k: called.append(_n) or [])
    monkeypatch.setattr(SVC.CompanyIngestionService,
                        "_third_party_filing_candidates",
                        lambda self, *a, **k: called.append("third_party") or [])
    monkeypatch.setattr(SVC.CompanyIngestionService, "_sitemap_candidates",
                        lambda self, *a, **k: called.append("sitemap") or [])

    meta = {"company_name": "Microsoft Corporation", "cik": "0000789019",
            "domain": "microsoft.com", "website": "https://microsoft.com"}
    monkeypatch.setattr(SVC.CompanyIngestionService, "run_meta",
                        lambda self, r: dict(meta))
    monkeypatch.setattr(SVC.CompanyIngestionService, "_transition",
                        lambda self, *a, **k: None)

    out = svc.discover("run-warm")
    assert out, "a warm run produced no candidates at all"
    assert called == [], (
        f"a warm run still performed discovery work: {called}")
    assert len(out) == 2


def test_a_cold_run_writes_a_snapshot_the_next_run_can_use(svc, monkeypatch):
    """POSITIVE CONTROL: without the write-back nothing is ever warm."""
    meta = {"company_name": "Acme Robotics", "cik": "0001234567",
            "domain": "acme.example", "website": "https://acme.example"}
    cands = [{"url": "https://acme.example/investors",
              "source_class": "company_owned"}]
    assert svc._write_snapshot("run-cold", meta, cands) is True
    key = SN.company_key("Acme Robotics", cik="0001234567",
                         domain="acme.example")
    got = svc.snapshots.get(key)
    assert got is not None
    assert got.source_for("https://acme.example/investors") is not None
    assert SN.plan_refresh(got)["mode"] == "WARM"


def test_a_snapshot_for_another_company_is_refused(svc, monkeypatch):
    """A wrong snapshot is worse than no snapshot: it would put one
    company's sources under another's evidence."""
    _seed_snapshot(svc, cik="0000789019", domain="microsoft.com")
    snap = svc.snapshots.get(
        SN.company_key("Microsoft Corporation", cik="0000789019",
                       domain="microsoft.com"))
    assert svc._snapshot_is_for(snap, {"cik": "0000320193",
                                       "domain": "apple.com"}) is False
    assert svc._snapshot_is_for(snap, {"cik": "789019",
                                       "domain": "microsoft.com"}) is True


def test_a_stale_snapshot_falls_through_to_full_discovery(svc, monkeypatch):
    """STALE has a source list, but old enough that the LIST may be wrong --
    and a stale list cannot be repaired by revalidating its entries."""
    _seed_snapshot(svc, age_s=90 * 3600)
    snap = svc.snapshots.get(
        SN.company_key("Microsoft Corporation", cik="0000789019",
                       domain="microsoft.com"))
    assert SN.plan_refresh(snap)["mode"] == "STALE"
    assert SN.plan_refresh(snap)["rediscover"] is True


def test_an_unreadable_snapshot_costs_the_head_start_not_the_run(svc,
                                                                monkeypatch):
    """Falling through is a full cold discovery -- today's behaviour."""
    monkeypatch.setattr(type(svc.snapshots), "get",
                        lambda self, k: (_ for _ in ()).throw(OSError("boom")))
    meta = {"company_name": "Acme", "cik": "", "domain": "acme.example",
            "website": "https://acme.example"}
    monkeypatch.setattr(SVC.CompanyIngestionService, "run_meta",
                        lambda self, r: dict(meta))
    monkeypatch.setattr(SVC.CompanyIngestionService, "_transition",
                        lambda self, *a, **k: None)
    # Must not raise. It will attempt a cold discovery and return whatever
    # that produces (empty here, with no transport).
    svc.discover("run-broken")


def test_a_wrong_company_snapshot_is_refused_ON_THE_PRODUCTION_PATH(svc,
                                                                    monkeypatch):
    """Not the helper -- the CALL SITE.

    The first version of this file tested `_snapshot_is_for` directly, so
    deleting the check from `discover()` left it green. A guard with no
    caller is not a guard.
    """
    _seed_snapshot(svc, cik="0000789019", domain="microsoft.com",
                   urls=("https://microsoft.com/investor",))
    # A run about APPLE, whose key happens to resolve to the Microsoft
    # snapshot (forced here, which is what a key collision would do).
    meta = {"company_name": "Apple Inc.", "cik": "0000320193",
            "domain": "apple.com", "website": "https://apple.com"}
    monkeypatch.setattr(SVC.CompanyIngestionService, "run_meta",
                        lambda self, r: dict(meta))
    monkeypatch.setattr(SVC.CompanyIngestionService, "_transition",
                        lambda self, *a, **k: None)
    ms = svc.snapshots.get(SN.company_key("Microsoft Corporation",
                                          cik="0000789019",
                                          domain="microsoft.com"))
    monkeypatch.setattr(type(svc.snapshots), "get", lambda self, k: ms)
    for name in ("discover_candidates", "propose_edgar_candidates",
                 "propose_external_candidates", "official_fallback_candidates"):
        if hasattr(SVC, name):
            monkeypatch.setattr(SVC, name, lambda *a, **k: [])
    monkeypatch.setattr(SVC.CompanyIngestionService,
                        "_third_party_filing_candidates",
                        lambda self, *a, **k: [])
    monkeypatch.setattr(SVC.CompanyIngestionService, "_sitemap_candidates",
                        lambda self, *a, **k: [])
    out = svc.discover("run-wrongco")
    urls = {c.get("url") for c in out}
    assert "https://microsoft.com/investor" not in urls, (
        "another company's source list was consumed for this run")


def test_a_cold_run_writes_the_snapshot_FROM_DISCOVER(svc, monkeypatch):
    """Not the helper -- the CALL SITE. Without the write-back in
    `discover()`, nothing is ever warm and every test above still passes."""
    import inspect
    code = "\n".join(
        l for l in inspect.getsource(
            SVC.CompanyIngestionService.discover).splitlines()
        if not l.lstrip().startswith("#"))
    assert "_write_snapshot(" in code, (
        "discover() never records what it learned, so no run can be warm")


def test_the_planner_is_actually_consumed_by_discover():
    """Structural: `plan_refresh` must be called from the production path.

    A planner with no call site is exactly the defect this file exists to
    prevent, and it is invisible to every unit test of the planner itself.
    """
    import inspect
    code = "\n".join(
        l for l in inspect.getsource(
            SVC.CompanyIngestionService.discover).splitlines()
        if not l.lstrip().startswith("#"))
    assert "plan_refresh(" in code, (
        "discover() does not consult the refresh planner")
    assert "_candidates_from_snapshot(" in code
