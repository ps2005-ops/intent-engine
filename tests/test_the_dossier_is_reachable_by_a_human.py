"""The dossier inspection surface, over real HTTP.

Batch 8 closed every gate item except this one: the read model had
programmatic readers and no way for a person to look at it. A store nobody
can query is not an operator surface, and at 100 companies "read the jsonl"
is not an answer.

These are real WSGI round trips against a real analysis, not calls into the
view functions. The view functions are tested too, but a redaction that works
in a unit test and is bypassed by the route is the failure mode worth
spending a request on.
"""
from __future__ import annotations

import io
import json

import pytest

from intent_engine.demo_dossier import views
from intent_engine.demo_dossier.store import DossierStore
from intent_engine.demo_dossier.transport import payload_from_file
from intent_engine.demo_dossier import vocabulary as V


def get(app, path):
    """One GET, returning (status, parsed json)."""
    captured = {}

    def start(status, headers):
        captured["status"] = status
        captured["headers"] = headers

    body = b"".join(app({"REQUEST_METHOD": "GET", "PATH_INFO": path,
                         "QUERY_STRING": "", "CONTENT_LENGTH": "0",
                         "HTTP_HOST": "127.0.0.1", "HTTP_COOKIE": "",
                         "wsgi.input": io.BytesIO(b"")}, start))
    return captured["status"], json.loads(body.decode())


@pytest.fixture(scope="module")
def app_with_a_real_dossier(tmp_path_factory):
    """A real analysis through the real `_compose`, so the surface is
    reading something the production path actually wrote."""
    from company_fixture_pages import BASE, transport
    from intent_engine.webapp.app import WebApp
    from intent_engine.webapp.config import AppConfig

    tmp = tmp_path_factory.mktemp("dossier-surface")
    app = WebApp(AppConfig(
        env="test", secret="s" * 40, demo_mode=True,
        web_store_path=tmp / "web.jsonl", fi_store_path=tmp / "fi.jsonl",
        ci_store_path=tmp / "ci.jsonl"), transport=transport, resolver=False)

    run = app.ci.create_run(company_name="Brightlake", website=BASE,
                            user_id="u-1", as_of="2026-08-11T00:00:00+00:00")
    run_id = run["run_id"]
    candidates = app.ci.discover(run_id)
    picked = [c["candidate_id"] for c in candidates[:3]]
    app.ci.approve(run_id, user_id="u-1", approved_ids=picked,
                   rejected_ids=[c["candidate_id"] for c in candidates
                                 if c["candidate_id"] not in picked])
    app.ci.fetch_approved(run_id)
    app._compose(run_id)
    return app, tmp


def test_the_index_lists_a_real_persisted_dossier(app_with_a_real_dossier):
    app, _ = app_with_a_real_dossier
    status, payload = get(app, "/demo-dossiers")
    assert status.startswith("200")
    assert payload["contract"] == views.INDEX_CONTRACT
    assert payload["count"] >= 1
    assert payload["state"] == "DOSSIERS_PRESENT"
    row = payload["dossiers"][0]
    for field in ("company_id", "readiness", "market_availability",
                  "founder_availability", "effective_evidence_cutoff",
                  "founder_runtime_sha", "temporal_compatibility",
                  "population_compatibility", "quarantined", "generated_at"):
        assert field in row, field


def test_the_index_is_an_index_and_carries_no_reference_ids(
        app_with_a_real_dossier):
    """§4. An index that grew with the size of an analysis would be a dump."""
    app, _ = app_with_a_real_dossier
    _, payload = get(app, "/demo-dossiers")
    for row in payload["dossiers"]:
        assert "blocks" not in row
        assert "market_block" not in row
        assert "founder_block" not in row


def test_the_detail_surface_returns_one_dossier(app_with_a_real_dossier):
    app, tmp = app_with_a_real_dossier
    company = DossierStore(tmp).companies()[0]
    status, payload = get(app, f"/demo-dossiers/{company}")
    assert status.startswith("200")
    assert payload["contract"] == views.DETAIL_CONTRACT
    assert payload["company_id"] == company
    assert payload["market_block"]["availability"] == V.UNAVAILABLE
    assert payload["market_block"]["reason"]


def test_the_detail_surface_preserves_every_absence_distinction(
        app_with_a_real_dossier):
    """§5. The states must survive the trip to the reader, or an operator
    triaging 100 companies cannot tell our gaps from the company's."""
    app, tmp = app_with_a_real_dossier
    company = DossierStore(tmp).companies()[0]
    _, payload = get(app, f"/demo-dossiers/{company}")
    states = {b["state"] for b in payload["market_block"]["blocks"].values()}
    assert states, "the market blocks vanished on the way to the reader"
    for name, block in payload["market_block"]["blocks"].items():
        assert "state" in block and "is_measured_zero" in block, name
        # nothing absent may arrive looking like a measured zero
        if block["state"] in V.NOT_A_MEASURED_ZERO:
            assert block["is_measured_zero"] is False, name


def test_a_sparse_dossier_stays_sparse_through_the_surface(
        app_with_a_real_dossier):
    """The surface must not fill anything in on the way out."""
    app, tmp = app_with_a_real_dossier
    company = DossierStore(tmp).companies()[0]
    stored = DossierStore(tmp).latest(company)
    _, payload = get(app, f"/demo-dossiers/{company}")
    assert payload["crossing_state"] == stored.crossing_state
    assert payload["readiness"] == stored.readiness
    assert payload["decision_impact_state"] == stored.decision_impact_state
    assert payload["readiness"] != V.DEMO_VERIFIED


@pytest.fixture
def app_with_private_refs(app_with_a_real_dossier):
    """A dossier that ACTUALLY CARRIES private reference ids.

    WHY THIS FIXTURE EXISTS: a break proof that deleted the redaction was not
    caught, because the ordinary Brightlake run has no tenant scope, so its
    private blocks are empty and there is nothing to leak. The test passed for
    a reason unrelated to the guard — a negative control that cannot fail.

    So this persists a dossier whose private blocks are populated. If
    redaction is removed, `ldr-secret-1` reaches the reader.
    """
    from intent_engine.demo_dossier import (assemble, market_unavailable,
                                            read_founder_snapshot)
    from intent_engine.demo_dossier.contracts import FOUNDER_CONTRACT

    app, tmp = app_with_a_real_dossier
    founder = read_founder_snapshot({
        "contract_version": FOUNDER_CONTRACT, "snapshot_id": "fs-priv",
        "company_id": "tenant-b-co", "canonical_name": "Tenant B Co",
        "run_id": "r-priv", "availability": V.AVAILABLE,
        "tenant_id": "tenant-b", "tenant_state": "SCOPED",
        "data_population": V.REAL_ENTERPRISE, "coverage_state": "OBSERVED",
        "evidence_cutoff": "2026-08-11", "known_at": "2026-08-11",
        "living_decision_refs": {"state": "AVAILABLE",
                                 "ids": ["ldr-secret-1", "ldr-secret-2"],
                                 "count": 2},
        "mdr_refs": {"state": "AVAILABLE", "ids": ["mdr-secret-9"],
                     "count": 1},
        "mve_refs": {"state": "NOT_ATTEMPTED", "count": 0},
    })
    dossier = assemble(market_unavailable("no market engine here"), founder,
                       now="2026-08-11")
    DossierStore(tmp).save(dossier)
    return app, "tenant-b-co"


def test_private_reference_ids_are_never_published(app_with_private_refs):
    """§7. The cross-tenant attack has nothing to reach, because no private
    reference id is emitted to anybody — not even the owning tenant."""
    app, company = app_with_private_refs
    status, payload = get(app, f"/demo-dossiers/{company}")
    assert status.startswith("200")
    assert payload["private_references_published"] is False

    blob = json.dumps(payload)
    assert "ldr-secret-1" not in blob
    assert "ldr-secret-2" not in blob
    assert "mdr-secret-9" not in blob

    ldr = payload["founder_block"]["blocks"]["living_decisions"]
    assert ldr["ids"] == []
    assert ldr["ids_redacted"] is True
    assert ldr["redaction_reason"]
    # REDACTION IS NOT ABSENCE: the count survives, so a reader can tell
    # "two exist and you may not see them" from "there are none".
    assert ldr["state"] == "AVAILABLE"
    assert ldr["count"] == 2


def test_the_index_never_carries_a_private_reference_either(
        app_with_private_refs):
    app, _ = app_with_private_refs
    _, payload = get(app, "/demo-dossiers")
    assert "ldr-secret-1" not in json.dumps(payload)


def test_a_tenant_cannot_reach_another_tenants_private_rows(
        app_with_a_real_dossier):
    """The attack from §7, made concrete: Tenant B asks for a dossier by a
    path it controls. It receives the same redacted counts as anybody, and
    no id belonging to anyone."""
    app, tmp = app_with_a_real_dossier
    company = DossierStore(tmp).companies()[0]
    for probe in (company, f"{company}/../{company}", "tenant-a-secret-co"):
        status, payload = get(app, f"/demo-dossiers/{probe}")
        blob = json.dumps(payload)
        assert "ldr-" not in blob and "mdr-" not in blob, probe
        if status.startswith("200"):
            assert payload["private_references_published"] is False, probe


def test_an_unknown_company_is_a_stated_absence_not_a_bare_404():
    from intent_engine.webapp.app import WebApp
    from intent_engine.webapp.config import AppConfig
    import tempfile
    import pathlib

    tmp = pathlib.Path(tempfile.mkdtemp())
    app = WebApp(AppConfig(
        env="test", secret="s" * 40, demo_mode=True,
        web_store_path=tmp / "web.jsonl", fi_store_path=tmp / "fi.jsonl",
        ci_store_path=tmp / "ci.jsonl"), resolver=False)
    status, payload = get(app, "/demo-dossiers/nobody-has-analysed-this")
    assert status.startswith("404")
    assert payload["state"] == V.NOT_STARTED
    assert "not been analysed here" in payload["reason"]
    assert "not a statement about the company" in payload["reason"]


def test_an_empty_deployment_says_so_rather_than_returning_nothing():
    from intent_engine.webapp.app import WebApp
    from intent_engine.webapp.config import AppConfig
    import tempfile
    import pathlib

    tmp = pathlib.Path(tempfile.mkdtemp())
    app = WebApp(AppConfig(
        env="test", secret="s" * 40, demo_mode=True,
        web_store_path=tmp / "web.jsonl", fi_store_path=tmp / "fi.jsonl",
        ci_store_path=tmp / "ci.jsonl"), resolver=False)
    status, payload = get(app, "/demo-dossiers")
    assert status.startswith("200")
    assert payload["count"] == 0
    assert payload["state"] == "NO_DOSSIERS"
    assert payload["note"]


def test_the_telemetry_surface_returns_real_counters(
        app_with_a_real_dossier):
    app, _ = app_with_a_real_dossier
    status, payload = get(app, "/demo-dossiers/telemetry")
    assert status.startswith("200")
    counts = payload["counts"]
    assert counts["dossiers_assembled"] >= 1
    # the two numbers whose conflation hid 22 refused dossiers
    assert "market_snapshots_unavailable" in counts
    assert counts.get("market_snapshots_refused", 0) == 0
    assert counts["market_snapshots_unavailable"] >= 1


def test_the_telemetry_surface_publishes_no_vanity_score(
        app_with_a_real_dossier):
    """§6. A single readiness percentage would average a quarantined dossier
    against a ready one and describe neither."""
    app, _ = app_with_a_real_dossier
    _, payload = get(app, "/demo-dossiers/telemetry")
    blob = json.dumps(payload).lower()
    for word in ("readiness_score", "health_score", "percent_ready",
                 "quality_score"):
        assert word not in blob, word


def test_the_telemetry_route_is_not_shadowed_by_the_detail_route():
    """`/demo-dossiers/telemetry` and `/demo-dossiers/<company>` share a
    prefix. If ordering ever flips, telemetry becomes a 404 for a company
    called "telemetry" and nothing else would notice."""
    from intent_engine.webapp.app import WebApp
    from intent_engine.webapp.config import AppConfig
    import tempfile
    import pathlib

    tmp = pathlib.Path(tempfile.mkdtemp())
    app = WebApp(AppConfig(
        env="test", secret="s" * 40, demo_mode=True,
        web_store_path=tmp / "web.jsonl", fi_store_path=tmp / "fi.jsonl",
        ci_store_path=tmp / "ci.jsonl"), resolver=False)
    status, payload = get(app, "/demo-dossiers/telemetry")
    assert status.startswith("200")
    assert "counts" in payload
