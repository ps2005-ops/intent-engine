"""D-IBG-001's consumer — the private graph is finally ASKED something.

The defect class this file exists to prevent is not a crash. It is a founder
being shown "no internal impact" when the truth is "we cannot see your
business". Those two answers are rendered by the same empty template and mean
opposite things, so most tests below are PAIRS: the empty case and the measured
negative, asserted to be different states, from the same code path.

Every test uses a real `BusinessGraph` and real scopes. There is no mock of the
boundary here — a mocked boundary proves the mock.
"""
from __future__ import annotations

import types

import pytest

from intent_engine.business_graph import internal as P
from intent_engine.business_graph.model import (
    COMPANY, BusinessGraph, GraphError, Node,
)
from intent_engine.core.tenant import (
    SOURCE_SYNTHETIC_FIXTURE, ScopeAuditLog, TenantId, establish,
)
from intent_engine.external_intel.internal_impact import (
    ALL_PRIVATE_WITHHELD,
    CONTRACT,
    EXTERNAL_SUBJECT_KEY,
    INTERNAL_DATA_UNAVAILABLE,
    INTERNAL_IMPACT_IDENTIFIED,
    INTERNAL_LINK_WITHOUT_METRIC,
    MDR_METRIC_NOT_WIRED,
    MDR_NO_INTERNAL_WORLD,
    NO_INTERNAL_IMPACT,
    NO_PRIVATE_ROWS,
    NOT_A_NEGATIVE,
    POPULATION_KEY,
    REAL_ENTERPRISE,
    SCOPELESS_READ,
    SYNTHETIC_ENTERPRISE,
    AffectedMetric,
    InternalImpact,
    assess_internal_impact,
    minimum_data_request,
)

OBSERVED = "2026-07-01T00:00:00+00:00"
KNOWN = "2026-07-02T00:00:00+00:00"
SUBJECT = "company:snowflake"
DECISION_ASKED = "whether to re-price the enterprise tier this quarter"


@pytest.fixture
def audit(tmp_path) -> ScopeAuditLog:
    return ScopeAuditLog(tmp_path / "tenant_scope_audit.jsonl")


def _scope(audit, *, label: str = "", tenant=None):
    return establish(tenant=tenant or TenantId.mint(),
                     establishment_source=SOURCE_SYNTHETIC_FIXTURE,
                     display_label=label, audit=audit)


def _node(scope, *, local_id, kind, label="x", attrs=None,
          sensitivity=P.SENSITIVITY_INTERNAL):
    return P.private_node(scope=scope, kind=kind, local_id=local_id,
                          label=label, company_id="acme", source="crm",
                          observed_at=OBSERVED, known_at=KNOWN,
                          sensitivity=sensitivity, attrs=attrs)


def _real(subject=None):
    """Attrs for a REAL-population node, optionally declaring a subject."""
    attrs = {POPULATION_KEY: REAL_ENTERPRISE}
    if subject:
        attrs[EXTERNAL_SUBJECT_KEY] = subject
    return attrs


@pytest.fixture
def world(audit):
    """A tenant whose initiative declares a dependency on SUBJECT and moves a
    metric, plus a second tenant holding an identical-looking business."""
    a, b = _scope(audit, label="Acme"), _scope(audit, label="Acme Holdings")
    graph = BusinessGraph()
    graph.add_node(Node(node_id="company:acme", kind=COMPANY, label="Acme",
                        source="sec:edgar"))
    graph.add_private_node(
        _node(a, local_id="init-price", kind=P.INITIATIVE,
              label="Enterprise repricing", attrs=_real(SUBJECT)), scope=a)
    graph.add_private_node(
        _node(a, local_id="m-arr", kind=P.INTERNAL_METRIC,
              label="Enterprise ARR", attrs=_real()), scope=a)
    graph.add_private_edge(
        P.private_edge(scope=a, kind=P.INITIATIVE_AFFECTS_METRIC,
                       src_local_id="init-price", dst_local_id="m-arr",
                       derived=False, source="rev-ops"), scope=a)
    # Tenant B: same shape, same local ids, same declared subject.
    graph.add_private_node(
        _node(b, local_id="init-price", kind=P.INITIATIVE,
              label="Their repricing", attrs=_real(SUBJECT)), scope=b)
    graph.add_private_node(
        _node(b, local_id="m-arr", kind=P.INTERNAL_METRIC,
              label="Their ARR", attrs=_real()), scope=b)
    graph.add_private_edge(
        P.private_edge(scope=b, kind=P.INITIATIVE_AFFECTS_METRIC,
                       src_local_id="init-price", dst_local_id="m-arr",
                       derived=False, source="rev-ops"), scope=b)
    return types.SimpleNamespace(graph=graph, a=a, b=b)


# =============================================================================
# 1. THE DISTINCTION THE MODULE EXISTS FOR
# =============================================================================
def test_an_empty_private_world_is_unavailable_and_never_a_negative(audit):
    """§18, stated exactly: an empty graph must NOT say NO_INTERNAL_IMPACT."""
    scope = _scope(audit)
    got = assess_internal_impact(BusinessGraph(), subject_id=SUBJECT,
                                 scope=scope)
    assert got.state == INTERNAL_DATA_UNAVAILABLE
    assert got.reason == NO_PRIVATE_ROWS
    assert got.state != NO_INTERNAL_IMPACT
    assert got.is_negative is False
    assert got.private_nodes_examined == 0


def test_a_populated_world_with_no_declaration_is_a_measured_negative(world):
    """The NEGATIVE CONTROL for the test above. Same call, same shapes, and a
    genuinely different answer — which is what proves the empty branch is a
    real distinction and not the only thing this function can say."""
    got = assess_internal_impact(world.graph, subject_id="company:unrelated",
                                 scope=world.a)
    assert got.state == NO_INTERNAL_IMPACT
    assert got.is_negative is True
    assert got.reason == ""
    # The negative is auditable: it names how many rows it examined to reach it.
    assert got.private_nodes_examined == 2


def test_the_two_empty_answers_are_not_the_same_state(world, audit):
    """Withheld-by-boundary and genuinely-absent are different reasons."""
    stranger = _scope(audit, label="Someone Else")
    withheld = assess_internal_impact(world.graph, subject_id=SUBJECT,
                                      scope=stranger)
    absent = assess_internal_impact(BusinessGraph(), subject_id=SUBJECT,
                                    scope=stranger)
    assert withheld.state == absent.state == INTERNAL_DATA_UNAVAILABLE
    assert withheld.reason == ALL_PRIVATE_WITHHELD
    assert absent.reason == NO_PRIVATE_ROWS
    assert withheld.withheld > 0 and absent.withheld == 0


def test_not_a_negative_membership_is_pinned(world):
    """Pins WHICH states, not how many. A length assertion passes when a state
    is swapped for another, which is the mutation that matters here."""
    assert NOT_A_NEGATIVE == {INTERNAL_LINK_WITHOUT_METRIC,
                              INTERNAL_DATA_UNAVAILABLE}
    assert NO_INTERNAL_IMPACT not in NOT_A_NEGATIVE
    assert INTERNAL_IMPACT_IDENTIFIED not in NOT_A_NEGATIVE


# =============================================================================
# 2. THE BOUNDARY HOLDS THROUGH THE CONSUMER
# =============================================================================
def test_a_scopeless_reader_gets_unavailable_not_a_negative(world):
    """Holding no authority is not evidence of no impact."""
    got = assess_internal_impact(world.graph, subject_id=SUBJECT, scope=None)
    assert got.state == INTERNAL_DATA_UNAVAILABLE
    assert got.reason == SCOPELESS_READ
    assert got.metrics == ()


def test_a_tenant_never_sees_the_other_tenants_identical_metric(world):
    """Both tenants declare the SAME subject with the SAME local ids. Each must
    get exactly its own metric — the collision is the point of the fixture."""
    a = assess_internal_impact(world.graph, subject_id=SUBJECT, scope=world.a)
    b = assess_internal_impact(world.graph, subject_id=SUBJECT, scope=world.b)
    assert a.state == b.state == INTERNAL_IMPACT_IDENTIFIED
    assert [m.label for m in a.metrics] == ["Enterprise ARR"]
    assert [m.label for m in b.metrics] == ["Their ARR"]
    assert {m.metric_id for m in a.metrics} & {m.metric_id for m in b.metrics} == set()


def test_a_bare_string_is_refused_as_authority(world):
    """A tenant id is an identity; an identity is not an authorization."""
    from intent_engine.core.tenant import ScopeRefused
    with pytest.raises(ScopeRefused):
        assess_internal_impact(world.graph, subject_id=SUBJECT,
                               scope=world.a.tenant.value)


# =============================================================================
# 3. THE BRIDGE IS A DECLARATION, NEVER A KEYWORD
# =============================================================================
def test_a_substring_of_the_declared_subject_does_not_match(audit):
    """"Linear" must not satisfy "Linear Minerals Corp." — the alias collision
    this codebase has already shipped once, in a different module."""
    scope = _scope(audit)
    graph = BusinessGraph()
    graph.add_private_node(
        _node(scope, local_id="init", kind=P.INITIATIVE,
              attrs=_real("company:linear-minerals-corp")), scope=scope)
    graph.add_private_node(
        _node(scope, local_id="m", kind=P.INTERNAL_METRIC, attrs=_real()),
        scope=scope)
    graph.add_private_edge(
        P.private_edge(scope=scope, kind=P.INITIATIVE_AFFECTS_METRIC,
                       src_local_id="init", dst_local_id="m", derived=False,
                       source="rev-ops"), scope=scope)
    got = assess_internal_impact(graph, subject_id="company:linear",
                                 scope=scope)
    assert got.state == NO_INTERNAL_IMPACT
    assert got.metrics == ()


def test_an_undeclared_node_is_never_linked_by_its_label(audit):
    """The label says the subject's name outright. It still does not count."""
    scope = _scope(audit)
    graph = BusinessGraph()
    graph.add_private_node(
        _node(scope, local_id="init", kind=P.INITIATIVE,
              label="Respond to Snowflake pricing", attrs=_real()),
        scope=scope)
    got = assess_internal_impact(graph, subject_id=SUBJECT, scope=scope)
    assert got.state == NO_INTERNAL_IMPACT


def test_an_empty_subject_is_refused_rather_than_matching_everything(world):
    with pytest.raises(GraphError):
        assess_internal_impact(world.graph, subject_id="", scope=world.a)


# =============================================================================
# 4. THE ANSWER IS DERIVED FROM GRAPH STATE, AND SHOWS ITS PATH
# =============================================================================
def test_an_identified_impact_carries_the_chain_that_reached_it(world):
    got = assess_internal_impact(world.graph, subject_id=SUBJECT,
                                 scope=world.a)
    assert got.state == INTERNAL_IMPACT_IDENTIFIED
    (metric,) = got.metrics
    assert metric.label == "Enterprise ARR"
    # The path starts at the node the TENANT declared, not at the metric.
    assert metric.via[0] == metric.declared_by
    assert metric.via[-1] == metric.metric_id
    assert len(metric.via) == 2


def test_a_two_hop_decision_action_metric_chain_is_followed(audit):
    """DECISION_AUTHORIZES_ACTION then ACTION_AFFECTS_METRIC — a route that
    only resolves if the walk actually traverses, rather than reading a
    neighbour list one hop deep."""
    scope = _scope(audit)
    graph = BusinessGraph()
    graph.add_private_node(
        _node(scope, local_id="dec", kind=P.PRIVATE_DECISION,
              attrs=_real(SUBJECT)), scope=scope)
    graph.add_private_node(
        _node(scope, local_id="act", kind=P.PRIVATE_ACTION, attrs=_real()),
        scope=scope)
    graph.add_private_node(
        _node(scope, local_id="m", kind=P.INTERNAL_METRIC,
              label="Churn", attrs=_real()), scope=scope)
    graph.add_private_edge(
        P.private_edge(scope=scope, kind=P.DECISION_AUTHORIZES_ACTION,
                       src_local_id="dec", dst_local_id="act", derived=False,
                       source="rev-ops"), scope=scope)
    graph.add_private_edge(
        P.private_edge(scope=scope, kind=P.ACTION_AFFECTS_METRIC,
                       src_local_id="act", dst_local_id="m", derived=False,
                       source="rev-ops"), scope=scope)
    got = assess_internal_impact(graph, subject_id=SUBJECT, scope=scope)
    assert got.state == INTERNAL_IMPACT_IDENTIFIED
    (metric,) = got.metrics
    assert metric.label == "Churn"
    assert len(metric.via) == 3


def test_a_declared_link_with_no_metric_is_a_gap_not_a_negative(audit):
    """An assumption depends on the subject and nothing measures it. That is
    missing instrumentation, and saying NO_INTERNAL_IMPACT here would report an
    unmeasured exposure as a measured zero."""
    scope = _scope(audit)
    graph = BusinessGraph()
    graph.add_private_node(
        _node(scope, local_id="asm", kind=P.INTERNAL_ASSUMPTION,
              label="Enterprise buyers are price-insensitive",
              attrs=_real(SUBJECT)), scope=scope)
    got = assess_internal_impact(graph, subject_id=SUBJECT, scope=scope)
    assert got.state == INTERNAL_LINK_WITHOUT_METRIC
    assert got.is_negative is False
    assert got.declared_links and got.metrics == ()


# =============================================================================
# 5. POPULATION AWARENESS — A FIXTURE IS NOT A FINDING
# =============================================================================
def test_an_untagged_row_is_treated_as_synthetic_not_as_real(audit):
    """Failing safe: an untagged row costs the answer its real-data claim,
    rather than letting a fixture be reported as an economic result."""
    scope = _scope(audit)
    graph = BusinessGraph()
    graph.add_private_node(
        _node(scope, local_id="init", kind=P.INITIATIVE,
              attrs={EXTERNAL_SUBJECT_KEY: SUBJECT}), scope=scope)
    graph.add_private_node(
        _node(scope, local_id="m", kind=P.INTERNAL_METRIC), scope=scope)
    graph.add_private_edge(
        P.private_edge(scope=scope, kind=P.INITIATIVE_AFFECTS_METRIC,
                       src_local_id="init", dst_local_id="m", derived=False,
                       source="rev-ops"), scope=scope)
    got = assess_internal_impact(graph, subject_id=SUBJECT, scope=scope)
    assert got.state == INTERNAL_IMPACT_IDENTIFIED
    assert got.populations == (SYNTHETIC_ENTERPRISE,)
    assert got.is_real_data_claim() is False


def test_a_fully_real_population_is_a_real_data_claim(world):
    got = assess_internal_impact(world.graph, subject_id=SUBJECT,
                                 scope=world.a)
    assert got.populations == (REAL_ENTERPRISE,)
    assert got.is_real_data_claim() is True


def test_an_unavailable_answer_is_never_a_real_data_claim(audit):
    """Absence of evidence must not pass the gate on the technicality that no
    synthetic row was involved."""
    got = assess_internal_impact(BusinessGraph(), subject_id=SUBJECT,
                                 scope=_scope(audit))
    assert got.populations == ()
    assert got.is_real_data_claim() is False


# =============================================================================
# 6. THE RESULT OBJECT CANNOT MISREPRESENT ITSELF
# =============================================================================
def test_an_unavailable_result_must_name_its_missing_prerequisite():
    with pytest.raises(GraphError):
        InternalImpact(state=INTERNAL_DATA_UNAVAILABLE, reason="")


def test_an_answered_result_may_not_carry_an_unavailability_reason():
    with pytest.raises(GraphError):
        InternalImpact(state=NO_INTERNAL_IMPACT, reason=NO_PRIVATE_ROWS)


def test_an_unknown_state_is_refused():
    with pytest.raises(GraphError):
        InternalImpact(state="PROBABLY_FINE")


def test_as_dict_reports_every_counter_including_the_zeroes(world):
    got = assess_internal_impact(world.graph, subject_id=SUBJECT,
                                 scope=world.a).as_dict()
    assert got["contract"] == CONTRACT
    for key in ("state", "subject_id", "metrics", "declared_links", "reason",
                "private_nodes_examined", "withheld", "refused",
                "populations", "scope_state", "is_real_data_claim"):
        assert key in got, key
    # Tenant B's two nodes AND the edge between them: an edge is withheld in
    # its own right, so the count is 3. A reader that only counted nodes would
    # under-report what it could not see.
    assert got["withheld"] == 3


# =============================================================================
# 7. THE SAME ANSWER SURVIVES PERSISTENCE — THE THREE-SHAPE RULE
# =============================================================================
def test_the_answer_is_identical_after_a_persist_and_reload_round_trip(world):
    """Live objects, persisted rows, reloaded objects — the shape collapse this
    program has shipped twice lives exactly here."""
    live = assess_internal_impact(world.graph, subject_id=SUBJECT,
                                  scope=world.a)
    exported = P.export_private_partition(world.graph, scope=world.a)
    rebuilt = BusinessGraph()
    for row in exported["nodes"]:
        if row.get("visibility") == "public":
            continue
        rebuilt.add_private_node(
            P.PrivateNode.from_row(row, scope=world.a), scope=world.a)
    for row in exported["edges"]:
        if row.get("visibility") == "public":
            continue
        rebuilt.add_private_edge(
            P.PrivateEdge.from_row(row, scope=world.a), scope=world.a)
    reloaded = assess_internal_impact(rebuilt, subject_id=SUBJECT,
                                      scope=world.a)
    assert reloaded.state == live.state
    assert [m.as_dict() for m in reloaded.metrics] == \
           [m.as_dict() for m in live.metrics]
    assert reloaded.is_real_data_claim() == live.is_real_data_claim()


# =============================================================================
# 8. MINIMUM DATA REQUEST — BOUNDED, AND ONLY WHERE IT IS WARRANTED
# =============================================================================
def test_no_request_is_generated_for_a_measured_negative(world):
    """Asking for more data to confirm a negative we already measured is how a
    data request becomes unbounded."""
    got = assess_internal_impact(world.graph, subject_id="company:unrelated",
                                 scope=world.a)
    assert minimum_data_request(got, decision=DECISION_ASKED) is None


def test_no_request_is_generated_for_an_identified_impact(world):
    got = assess_internal_impact(world.graph, subject_id=SUBJECT,
                                 scope=world.a)
    assert minimum_data_request(got, decision=DECISION_ASKED) is None


def test_an_unavailable_world_produces_a_bounded_request(audit):
    got = assess_internal_impact(BusinessGraph(), subject_id=SUBJECT,
                                 scope=_scope(audit))
    req = minimum_data_request(got, decision=DECISION_ASKED)
    assert req is not None
    assert req.reason == MDR_NO_INTERNAL_WORLD
    assert req.decision == DECISION_ASKED
    assert req.fields and req.window_days == 90
    # Bounded: named columns, not a system.
    assert "CRM" not in " ".join(req.fields)


def test_a_missing_metric_produces_a_request_naming_the_declared_node(audit):
    scope = _scope(audit)
    graph = BusinessGraph()
    graph.add_private_node(
        _node(scope, local_id="asm", kind=P.INTERNAL_ASSUMPTION,
              attrs=_real(SUBJECT)), scope=scope)
    got = assess_internal_impact(graph, subject_id=SUBJECT, scope=scope)
    req = minimum_data_request(got, decision=DECISION_ASKED)
    assert req.reason == MDR_METRIC_NOT_WIRED
    assert got.declared_links[0] in req.missing


def test_a_request_without_a_decision_is_refused(audit):
    from intent_engine.external_intel.internal_impact import MinimumDataRequest
    with pytest.raises(GraphError):
        MinimumDataRequest(decision="", fields=("a",),
                           reason=MDR_NO_INTERNAL_WORLD)


def test_a_request_without_fields_is_refused():
    from intent_engine.external_intel.internal_impact import MinimumDataRequest
    with pytest.raises(GraphError):
        MinimumDataRequest(decision=DECISION_ASKED, fields=(),
                           reason=MDR_NO_INTERNAL_WORLD)
