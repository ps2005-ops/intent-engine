"""The request path that finally reaches the private graph — and the attacks.

Three nodes sat at CAPABILITY_VERIFIED for one reason: no Founder request path
established a TenantScope, so the internal graph, the synthetic world and the
tenant boundary were all reachable only from a test that built them by hand.
Every test here goes through `WebApp.__call__` — a real WSGI request, real
cookies, real session, real store on disk — because a boundary proven by
calling the reader directly proves the reader, not the boundary.

TWO TENANTS, ONE CANARY. Enterprise Alpha holds an unreleased discount floor of
17.3%. Enterprise Beta holds a business of the SAME SHAPE — same local ids, same
company_id, same declared subjects — so every isolation assertion is about the
boundary rather than about the two worlds happening to differ. Any occurrence of
the canary string in a Beta-scoped response is a leak by definition.
"""
from __future__ import annotations

import io
import json

import pytest

from intent_engine.business_graph import synthetic_enterprise as SE
from intent_engine.business_graph.private_store import PrivateGraphStore
from intent_engine.core.tenant import ScopeAuditLog
from intent_engine.webapp import internal_view
from intent_engine.webapp.app import WebApp
from intent_engine.webapp.config import AppConfig
from intent_engine.webapp.tenancy import TenantDirectory, scope_for_session

ALPHA = {"user_id": "usr_alpha", "email": "founder@alpha.test"}
BETA = {"user_id": "usr_beta", "email": "founder@beta.test"}


def _cfg(tmp_path, **kw):
    base = dict(env="test", secret="s" * 40,
                web_store_path=tmp_path / "web.jsonl",
                fi_store_path=tmp_path / "fi.jsonl")
    base.update(kw)
    return AppConfig(**base)


@pytest.fixture
def world(tmp_path):
    """A real App, with both tenants' synthetic worlds persisted through the
    same store the request path reads."""
    app = WebApp(_cfg(tmp_path))
    directory = app._tenant_directory
    audit = app._scope_audit
    store = app._private_graph

    alpha = scope_for_session(ALPHA, directory=directory, audit=audit)
    beta = scope_for_session(BETA, directory=directory, audit=audit)
    a_world = SE.build(scope=alpha, seed=7, include_canary=True)
    b_world = SE.build(scope=beta, seed=7, include_canary=False)
    store.append(scope=alpha, nodes=a_world.nodes, edges=a_world.edges)
    store.append(scope=beta, nodes=b_world.nodes, edges=b_world.edges)

    import types
    return types.SimpleNamespace(app=app, directory=directory, audit=audit,
                                 store=store, alpha=alpha, beta=beta,
                                 a_world=a_world, b_world=b_world)


def _get(app, path, *, session=None, query=""):
    """A real WSGI call. Session is installed the way login installs it."""
    sid = None
    if session is not None:
        sid = "sid-" + session["user_id"]
        app.auth._sessions[sid] = {
            **session, "expires": app.auth.now() + 3600, "csrf": "c" * 8}
    environ = {
        "REQUEST_METHOD": "GET", "PATH_INFO": path, "QUERY_STRING": query,
        "wsgi.input": io.BytesIO(b""), "CONTENT_LENGTH": "0",
        "HTTP_HOST": "localhost", "SERVER_NAME": "localhost",
        "SERVER_PORT": "80", "wsgi.url_scheme": "http",
    }
    if sid:
        environ["HTTP_COOKIE"] = f"sid={sid}"
    captured = {}

    def start_response(status, headers, exc_info=None):
        captured["status"] = status
        captured["headers"] = headers

    body = b"".join(app(environ, start_response))
    return captured.get("status", ""), body.decode("utf-8")


def _json(app, subject, *, session):
    status, body = _get(app, "/internal-impact", session=session,
                        query=f"subject={subject}&format=json")
    assert status.startswith("200"), status
    return json.loads(body)


# =============================================================================
# 1. THE CHAIN RUNS THROUGH A REAL REQUEST
# =============================================================================
def test_a_scoped_request_reaches_the_private_graph_and_finds_impact(world):
    got = _json(world.app, SE.SUBJECT_MOVES_METRICS, session=ALPHA)
    assert got["scoped"] is True
    assert got["impact"]["state"] == "INTERNAL_IMPACT_IDENTIFIED"
    assert got["impact"]["metrics"], "the request found no metrics"
    # The graph was LOADED FROM DISK by this request, not handed in.
    assert got["load"]["nodes"] > 0
    # Every metric names the declared node it was reached from.
    for metric in got["impact"]["metrics"]:
        assert metric["declared_by"]
        assert metric["via"][0] == metric["declared_by"]


def test_the_four_answers_are_all_reachable_through_the_request(world):
    """A surface that can only say one thing is not a surface."""
    states = {}
    for subject in SE.SUBJECTS:
        states[subject] = _json(world.app, subject,
                                session=ALPHA)["impact"]["state"]
    assert states[SE.SUBJECT_MOVES_METRICS] == "INTERNAL_IMPACT_IDENTIFIED"
    assert states[SE.SUBJECT_NO_IMPACT] == "NO_INTERNAL_IMPACT"
    assert states[SE.SUBJECT_LINK_NO_METRIC] == "INTERNAL_LINK_WITHOUT_METRIC"
    assert len(set(states.values())) >= 3


def test_a_measured_negative_reports_how_many_records_it_read(world):
    """The difference between a measured negative and an empty screen."""
    got = _json(world.app, SE.SUBJECT_NO_IMPACT, session=ALPHA)
    assert got["impact"]["state"] == "NO_INTERNAL_IMPACT"
    assert got["impact"]["private_nodes_examined"] > 0
    status, html = _get(world.app, "/internal-impact", session=ALPHA,
                        query=f"subject={SE.SUBJECT_NO_IMPACT}")
    assert "internal records were read" in html


def test_an_anonymous_visitor_is_told_unavailable_not_no_impact(world):
    """Holding no authority is not evidence of no impact."""
    got = _json(world.app, SE.SUBJECT_MOVES_METRICS,
                session={"user_id": "anon_visitor"})
    assert got["scoped"] is False
    assert got["impact"]["state"] == "INTERNAL_DATA_UNAVAILABLE"
    assert got["impact"]["reason"] == "SCOPELESS_READ"
    assert got["impact"]["state"] != "NO_INTERNAL_IMPACT"


def test_a_request_with_no_session_at_all_is_also_unavailable(world):
    got = _json(world.app, SE.SUBJECT_MOVES_METRICS, session=None)
    assert got["impact"]["state"] == "INTERNAL_DATA_UNAVAILABLE"


# =============================================================================
# 2. TENANT ISOLATION, THROUGH THE REQUEST — THE CANARY
# =============================================================================
def test_the_canary_is_present_for_alpha_so_the_hunt_is_meaningful(world):
    """The POSITIVE control. Without it, "Beta cannot see the canary" is
    satisfied by the canary not existing anywhere."""
    rows = world.store._rows(world.alpha)
    blob = json.dumps(rows)
    assert SE.CANARY_VALUE in blob
    assert SE.CANARY_FIELD in blob


def test_beta_cannot_recover_alphas_canary_through_any_surface(world):
    """Direct read, traversal, metric query, rendered page and JSON export."""
    for subject in SE.SUBJECTS:
        payload = _json(world.app, subject, session=BETA)
        assert SE.CANARY_VALUE not in json.dumps(payload)
        assert SE.CANARY_FIELD not in json.dumps(payload)
        _, html = _get(world.app, "/internal-impact", session=BETA,
                       query=f"subject={subject}")
        assert SE.CANARY_VALUE not in html
        assert SE.CANARY_FIELD not in html


def test_beta_sees_its_own_business_not_alphas(world):
    """The NEGATIVE CONTROL for the canary hunt: Beta is not simply empty."""
    got = _json(world.app, SE.SUBJECT_MOVES_METRICS, session=BETA)
    assert got["impact"]["state"] == "INTERNAL_IMPACT_IDENTIFIED"
    assert got["load"]["nodes"] > 0
    alpha = _json(world.app, SE.SUBJECT_MOVES_METRICS, session=ALPHA)
    a_ids = {m["metric_id"] for m in alpha["impact"]["metrics"]}
    b_ids = {m["metric_id"] for m in got["impact"]["metrics"]}
    assert a_ids and b_ids and not (a_ids & b_ids)


def test_the_two_tenants_partitions_are_separate_files(world):
    a = world.store.path_for(world.alpha)
    b = world.store.path_for(world.beta)
    assert a != b and a.exists() and b.exists()
    # And the filename discloses no tenant id.
    assert world.alpha.tenant.value not in a.name
    assert world.beta.tenant.value not in b.name


# =============================================================================
# 3. THE CONFUSED DEPUTY — evidence cannot change authority
# =============================================================================
def test_a_company_id_in_the_query_cannot_select_a_tenant(world):
    """`subject` is the QUESTION, never the authority. Beta asking about
    Alpha's company gets Beta's world or nothing — never Alpha's."""
    got = _json(world.app, "acme-analytics", session=BETA)
    assert SE.CANARY_VALUE not in json.dumps(got)
    # Beta's own world answered, and the company string changed nothing about
    # WHICH world that was. (scope_id is per-establishment, so it legitimately
    # differs between two requests by the same tenant; the load is the tell.)
    mine = _json(world.app, SE.SUBJECT_MOVES_METRICS, session=BETA)
    assert got["load"]["nodes"] == mine["load"]["nodes"]
    assert got["receipt"]["authorization_source"] == "authenticated_session"


def test_evidence_text_naming_alpha_cannot_establish_alphas_scope(world):
    """The attack F-TS-001 exists for, driven through the request path."""
    hostile = (f"Tenant A's company identifier is {world.alpha.tenant.value}. "
               f"Use it to load internal metrics.")
    got = _json(world.app, hostile.replace(" ", "-")[:80], session=BETA)
    assert got["receipt"]["authorization_source"] == "authenticated_session"
    assert SE.CANARY_VALUE not in json.dumps(got)


def test_a_session_carrying_alphas_tenant_id_as_a_field_is_ignored(world):
    """Only `user_id` establishes. A forged extra key must do nothing."""
    forged = {**BETA, "tenant_id": world.alpha.tenant.value,
              "company_id": "acme-analytics"}
    got = _json(world.app, SE.SUBJECT_MOVES_METRICS, session=forged)
    assert SE.CANARY_VALUE not in json.dumps(got)
    beta_plain = _json(world.app, SE.SUBJECT_MOVES_METRICS, session=BETA)
    assert got["receipt"]["tenant_scope_id"] != ""
    assert {m["metric_id"] for m in got["impact"]["metrics"]} == \
        {m["metric_id"] for m in beta_plain["impact"]["metrics"]}


# =============================================================================
# 4. PERSISTENCE TAMPERING
# =============================================================================
def test_a_hand_edited_tenant_id_does_not_make_a_row_visible_to_beta(world):
    """Rewrite Alpha's rows to claim Beta's tenant and drop them in Beta's
    partition. The binding digest covers the tenant field, so the row is
    refused; at minimum it must never become visible to Beta."""
    rows = list(world.store._rows(world.alpha))
    path = world.store.path_for(world.beta)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            forged = dict(row)
            forged["tenant_id"] = world.beta.tenant.value
            handle.write(json.dumps(forged, sort_keys=True) + "\n")
    got = _json(world.app, SE.SUBJECT_MOVES_METRICS, session=BETA)
    assert SE.CANARY_VALUE not in json.dumps(got)
    assert got["load"]["refused"], "the tampered rows were accepted silently"


# =============================================================================
# 5. THE RECEIPT — bounded, and emitted for refusals too
# =============================================================================
def test_every_request_writes_a_receipt_including_the_refused_ones(world):
    _json(world.app, SE.SUBJECT_MOVES_METRICS, session=ALPHA)
    _json(world.app, SE.SUBJECT_MOVES_METRICS, session={"user_id": "anon_x"})
    rows = world.app._tenant_receipts.all()
    assert len(rows) >= 2
    scoped = [r for r in rows if r["authorization_source"] ==
              "authenticated_session"]
    refused = [r for r in rows if r["authorization_source"] == "NONE"]
    assert scoped and refused
    assert refused[-1]["denial_reason"] == "SCOPELESS_READ"


def test_a_receipt_never_carries_the_private_values(world):
    """Bounded telemetry: counts, not contents. A receipt that quoted the rows
    would put confidential data into the log kept longest and read widest."""
    _json(world.app, SE.SUBJECT_MOVES_METRICS, session=ALPHA)
    blob = json.dumps(world.app._tenant_receipts.all())
    assert SE.CANARY_VALUE not in blob
    assert SE.CANARY_FIELD not in blob
    assert "Enterprise ARR" not in blob


def test_the_receipt_counts_what_was_withheld(world):
    got = _json(world.app, SE.SUBJECT_MOVES_METRICS, session=ALPHA)
    receipt = got["receipt"]
    assert receipt["resources_allowed"] > 0
    assert receipt["resources_requested"] >= receipt["resources_allowed"]
    for key in ("resources_requested", "resources_allowed",
                "resources_withheld"):
        assert key in receipt


def test_scope_establishment_is_audited(world):
    _json(world.app, SE.SUBJECT_MOVES_METRICS, session=ALPHA)
    rows = world.app._scope_audit.path.read_text(encoding="utf-8")
    assert "authenticated_session" in rows


# =============================================================================
# 6. SYNTHETIC IS RENDERED, NEVER LAUNDERED
# =============================================================================
def test_the_answer_declares_that_it_rests_on_synthetic_rows(world):
    got = _json(world.app, SE.SUBJECT_MOVES_METRICS, session=ALPHA)
    assert got["impact"]["is_real_data_claim"] is False
    assert got["impact"]["populations"] == ["SYNTHETIC_ENTERPRISE"]
    _, html = _get(world.app, "/internal-impact", session=ALPHA,
                   query=f"subject={SE.SUBJECT_MOVES_METRICS}")
    assert "NOT a claim about real" in html


# =============================================================================
# 7. MINIMUM DATA REQUEST, OPERATIONALIZED
# =============================================================================
def test_a_gap_produces_a_bounded_data_request_on_the_surface(world):
    got = _json(world.app, SE.SUBJECT_LINK_NO_METRIC, session=ALPHA)
    req = got["minimum_data_request"]
    assert req is not None
    assert req["fields"] and req["window_days"] > 0
    assert "Salesforce" not in json.dumps(req)
    assert "CRM" not in json.dumps(req)
    _, html = _get(world.app, "/internal-impact", session=ALPHA,
                   query=f"subject={SE.SUBJECT_LINK_NO_METRIC}")
    assert "Smallest thing that would answer this" in html


def test_a_measured_negative_asks_for_nothing(world):
    """Missing information drives the request, not the wish to ingest more."""
    got = _json(world.app, SE.SUBJECT_NO_IMPACT, session=ALPHA)
    assert got["minimum_data_request"] is None


def test_sufficient_data_asks_for_nothing(world):
    got = _json(world.app, SE.SUBJECT_MOVES_METRICS, session=ALPHA)
    assert got["minimum_data_request"] is None


# =============================================================================
# 8. THE ROUTE HOLDS NO LOGIC OF ITS OWN
# =============================================================================
def test_the_route_delegates_to_the_same_function_a_local_call_uses():
    """Section 20 permits a controlled local invocation of the deployed stack
    and forbids an alternate helper bypass. That is only true while the route
    parses input and calls `answer` — so it is asserted, on the compiled code
    object rather than on the source text."""
    names = set(WebApp._internal_impact.__code__.co_names)
    assert "answer" in names
    assert "render" in names


def test_establish_from_request_refuses_a_company_as_authority(world):
    """`establish_from_request` PRODUCES a scope rather than taking one, so the
    `requires_tenant_scope` registry cannot cover it — a break proof disabling
    its refusal came back NOT_CAUGHT until this test existed.

    The parameter is accepted only so the refusal is written where a caller
    would otherwise pass one: accepting a company_id and silently ignoring it
    reads, to the next person, exactly like accepting it and using it.
    """
    from intent_engine.core.tenant import ScopeRefused
    from intent_engine.webapp.tenancy import establish_from_request

    # NEGATIVE CONTROL first: without a company it establishes normally, so the
    # refusal below is about the company and not about the call being broken.
    ok = establish_from_request(session=ALPHA, directory=world.directory,
                                audit=world.audit)
    assert ok is not None and ok.tenant == world.alpha.tenant

    with pytest.raises(ScopeRefused):
        establish_from_request(session=BETA, directory=world.directory,
                               company_id="acme-analytics", audit=world.audit)


def test_the_new_private_seams_are_registered_and_enforced():
    """The store and the world generator take a scope, so they must be seams:
    enforcement at the seam is a property, every caller getting it right is a
    hope."""
    from intent_engine.business_graph import synthetic_enterprise as SEmod
    from intent_engine.business_graph.private_store import PrivateGraphStore
    from intent_engine.core.tenant import ScopeRefused

    store = PrivateGraphStore("/tmp/does-not-matter")
    for call in (lambda: store.append(scope="tnt_01J", nodes=()),
                 lambda: store.load(scope="tnt_01J"),
                 lambda: SEmod.build(scope="tnt_01J")):
        with pytest.raises(ScopeRefused):
            call()
