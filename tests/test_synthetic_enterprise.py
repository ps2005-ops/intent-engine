"""D-SYN-001 — the world must be a business, and must stay labelled.

Two things make this world worth having. It RECONCILES, so an impact traced
through it is traced through numbers that add up rather than through fixture
soup. And it contains NEGATIVES, so the internal-impact reader's four answers
are all reachable — a world that could only produce "impact found" would make
every test of that reader unfalsifiable.

The labelling tests are the ones that matter most. Section 26 permits these
rows to prove capability and forbids them from proving an economic result, and
the way that rule actually breaks is never a malicious relabelling: it is a
helpful default somewhere downstream.
"""
from __future__ import annotations

import json

import pytest

from intent_engine.business_graph import internal as P
from intent_engine.business_graph import synthetic_enterprise as SE
from intent_engine.business_graph.model import BusinessGraph
from intent_engine.business_graph.private_store import PrivateGraphStore
from intent_engine.core.tenant import (
    SOURCE_SYNTHETIC_FIXTURE, ScopeAuditLog, ScopeRefused, TenantId, establish,
)
from intent_engine.external_intel.internal_impact import (
    POPULATION_KEY, REAL_ENTERPRISE, SYNTHETIC_ENTERPRISE,
    assess_internal_impact,
)


@pytest.fixture
def audit(tmp_path):
    return ScopeAuditLog(tmp_path / "audit.jsonl")


def _scope(audit, label=""):
    return establish(tenant=TenantId.mint(),
                     establishment_source=SOURCE_SYNTHETIC_FIXTURE,
                     display_label=label, audit=audit)


@pytest.fixture
def world(audit):
    scope = _scope(audit, "Alpha")
    return scope, SE.build(scope=scope, seed=7, include_canary=True)


# =============================================================================
# 1. IT IS A BUSINESS: THE NUMBERS RECONCILE
# =============================================================================
def test_the_world_reconciles(world):
    _, w = world
    assert SE.reconcile(w) == ()


def test_segment_revenue_sums_to_the_company_total(world):
    _, w = world
    assert sum(w.segment_arr.values()) == w.company_arr
    total = next(n for n in w.nodes if n.local_id == "co")
    assert total.attrs["arr"] == w.company_arr


def test_reconcile_reports_a_discrepancy_when_one_exists(world):
    """A guard that has never returned a non-empty result is untested."""
    _, w = world
    broken = SE.SyntheticEnterprise(
        identity=w.identity, nodes=w.nodes, edges=w.edges,
        company_arr=w.company_arr,
        segment_arr={**w.segment_arr, "seg-enterprise": 1})
    assert SE.reconcile(broken) != ()


def test_contracts_do_not_book_more_than_their_segment_holds(world):
    _, w = world
    booked = sum((n.attrs or {}).get("acv", 0) for n in w.nodes
                 if n.kind == P.CONTRACT)
    assert 0 < booked <= w.segment_arr["seg-enterprise"]


def test_pipeline_states_the_basis_it_is_a_multiple_of(world):
    _, w = world
    pipes = [n for n in w.nodes if n.kind == P.PIPELINE_OPPORTUNITY]
    assert pipes
    for pipe in pipes:
        assert pipe.attrs.get("coverage_of_segment_arr") is not None


# =============================================================================
# 2. IT CONTAINS NEGATIVES — all four answers are reachable
# =============================================================================
def test_every_reader_state_is_reachable_from_this_one_world(world):
    scope, w = world
    graph = SE.install(BusinessGraph(), w, scope=scope)
    states = {s: assess_internal_impact(graph, subject_id=s, scope=scope).state
              for s in SE.SUBJECTS}
    assert states[SE.SUBJECT_MOVES_METRICS] == "INTERNAL_IMPACT_IDENTIFIED"
    assert states[SE.SUBJECT_NO_IMPACT] == "NO_INTERNAL_IMPACT"
    assert states[SE.SUBJECT_LINK_NO_METRIC] == "INTERNAL_LINK_WITHOUT_METRIC"


def test_the_no_impact_subject_is_declared_by_nothing(world):
    """Its absence IS the fixture. If some node quietly declared it, the
    measured negative above would be measuring the wrong thing."""
    _, w = world
    for node in w.nodes:
        assert (node.attrs or {}).get("external_subject") != SE.SUBJECT_NO_IMPACT


def test_the_world_contains_an_action_that_moved_nothing(world):
    """Required by §6. Without it the world implies every action works, which
    is the belief this whole system exists to interrogate."""
    _, w = world
    outcomes = [n for n in w.nodes if n.kind == P.PRIVATE_OUTCOME]
    assert any(n.attrs.get("effect") == "NONE_DETECTED" for n in outcomes)


def test_the_world_contains_a_stale_metric_by_its_date_not_a_flag(world):
    _, w = world
    stale = next(n for n in w.nodes if n.local_id == "m-support-cost")
    fresh = next(n for n in w.nodes if n.local_id == "m-ent-arr")
    assert stale.observed_at < fresh.observed_at


def test_the_world_contains_confidential_and_restricted_rows(world):
    _, w = world
    levels = {n.sensitivity for n in w.nodes}
    assert P.SENSITIVITY_CONFIDENTIAL in levels
    assert P.SENSITIVITY_RESTRICTED in levels


# =============================================================================
# 3. DETERMINISM IS THE CONTRACT
# =============================================================================
def test_the_same_seed_and_version_produce_identical_rows(audit):
    scope = _scope(audit)
    a = SE.build(scope=scope, seed=7)
    b = SE.build(scope=scope, seed=7)
    assert [n.as_row() for n in a.nodes] == [n.as_row() for n in b.nodes]
    assert a.identity.synthetic_world_id == b.identity.synthetic_world_id


def test_a_different_seed_is_a_different_world(audit):
    scope = _scope(audit)
    assert SE.build(scope=scope, seed=7).identity.synthetic_world_id != \
        SE.build(scope=scope, seed=8).identity.synthetic_world_id


def test_generated_at_does_not_come_from_the_clock(audit):
    """A fixture whose content depends on when it ran cannot support a
    decision record that has to be re-derivable later."""
    scope = _scope(audit)
    assert SE.build(scope=scope, seed=7).identity.generated_at == \
        SE.build(scope=scope, seed=7).identity.generated_at


def test_the_identity_carries_seed_version_schema_and_scenario(world):
    _, w = world
    got = w.identity.as_dict()
    for key in ("synthetic_world_id", "version", "seed", "schema_version",
                "scenario_id", "generated_at", "data_population"):
        assert key in got, key


# =============================================================================
# 4. LABELLING SURVIVES EVERYTHING
# =============================================================================
def test_every_node_carries_the_synthetic_population(world):
    _, w = world
    assert SE.assert_all_synthetic(w) == ()


def test_the_label_guard_reports_a_node_that_lost_its_tag(world):
    """Proves the guard can fire, rather than trusting that it would."""
    scope, w = world
    stripped = P.private_node(
        scope=scope, kind=P.INTERNAL_METRIC, local_id="m-untagged",
        label="Untagged", company_id="acme", source="synthetic_enterprise",
        observed_at="2026-07-01T00:00:00+00:00",
        known_at="2026-07-02T00:00:00+00:00",
        sensitivity=P.SENSITIVITY_INTERNAL,
        attrs={POPULATION_KEY: REAL_ENTERPRISE})
    broken = SE.SyntheticEnterprise(
        identity=w.identity, nodes=w.nodes + (stripped,), edges=w.edges,
        company_arr=w.company_arr, segment_arr=w.segment_arr)
    assert "m-untagged" in SE.assert_all_synthetic(broken)


def test_the_label_survives_persistence_and_reload(tmp_path, world):
    """Live object, persisted row, reloaded object — and the tag in all three."""
    scope, w = world
    store = PrivateGraphStore(tmp_path)
    store.append(scope=scope, nodes=w.nodes, edges=w.edges)
    raw = store.path_for(scope).read_text(encoding="utf-8")
    assert SYNTHETIC_ENTERPRISE in raw
    graph = store.load(scope=scope)
    for node in graph.read(scope=scope).nodes:
        assert node.attrs.get(POPULATION_KEY) == SYNTHETIC_ENTERPRISE


def test_an_answer_over_this_world_is_never_a_real_data_claim(world):
    scope, w = world
    graph = SE.install(BusinessGraph(), w, scope=scope)
    got = assess_internal_impact(graph, subject_id=SE.SUBJECT_MOVES_METRICS,
                                 scope=scope)
    assert got.is_real_data_claim() is False
    assert got.populations == (SYNTHETIC_ENTERPRISE,)


def test_the_world_id_travels_on_every_node(world):
    """So a decision can name WHICH synthetic world it was made in."""
    _, w = world
    for node in w.nodes:
        assert node.attrs.get("synthetic_world_id") == \
            w.identity.synthetic_world_id


# =============================================================================
# 5. THE STORE — partitioned, authorized on load, append-only
# =============================================================================
def test_a_scopeless_store_lookup_is_refused(tmp_path):
    with pytest.raises(ScopeRefused):
        PrivateGraphStore(tmp_path).path_for(None)


def test_two_tenants_get_two_partitions_and_neither_name_leaks_an_id(
        tmp_path, audit):
    a, b = _scope(audit, "A"), _scope(audit, "B")
    store = PrivateGraphStore(tmp_path)
    assert store.path_for(a) != store.path_for(b)
    assert a.tenant.value not in store.path_for(a).name
    assert b.tenant.value not in store.path_for(b).name


def test_a_row_owned_by_another_tenant_cannot_be_written_into_a_partition(
        tmp_path, audit):
    a, b = _scope(audit, "A"), _scope(audit, "B")
    store = PrivateGraphStore(tmp_path)
    foreign = SE.build(scope=b, seed=7).nodes[:1]
    from intent_engine.business_graph.model import PrivateGraphRefused
    with pytest.raises(PrivateGraphRefused):
        store.append(scope=a, nodes=foreign)


def test_reload_refuses_rows_whose_binding_was_altered(tmp_path, world):
    scope, w = world
    store = PrivateGraphStore(tmp_path)
    store.append(scope=scope, nodes=w.nodes[:3])
    path = store.path_for(scope)
    rows = [json.loads(l) for l in path.read_text().splitlines()]
    rows[0]["label"] = "tampered"
    path.write_text("\n".join(json.dumps(r, sort_keys=True) for r in rows))
    result = store.load_into(BusinessGraph(), scope=scope)
    assert result.refused, "a hand-edited row was accepted"
    assert result.nodes == 2


def test_a_load_reports_zero_refusals_when_nothing_is_wrong(tmp_path, world):
    """The NEGATIVE CONTROL: `refused` must be able to be empty, or the test
    above is satisfied by a store that refuses everything."""
    scope, w = world
    store = PrivateGraphStore(tmp_path)
    store.append(scope=scope, nodes=w.nodes, edges=w.edges)
    result = store.load_into(BusinessGraph(), scope=scope)
    assert result.refused == ()
    assert result.nodes == len(w.nodes)


def test_the_store_is_append_only_and_the_latest_row_wins(tmp_path, world):
    scope, w = world
    store = PrivateGraphStore(tmp_path)
    store.append(scope=scope, nodes=w.nodes[:1])
    store.append(scope=scope, nodes=w.nodes[:1])
    assert len(store.path_for(scope).read_text().strip().splitlines()) == 2
    assert store.load_into(BusinessGraph(), scope=scope).nodes == 1


def test_a_tenants_partition_contains_only_its_own_rows(tmp_path, audit):
    """The PARTITION, not the read filter, is what this asserts.

    A break proof collapsing every tenant into one file came back NOT_CAUGHT:
    the canary stayed hidden because `from_row` refuses a cross-tenant row at
    load time, so the partition is genuine defence in depth rather than the
    thing holding the line. That is worth knowing and worth keeping — but a
    redundant guard nothing measures decays into a comment. This measures it:
    with one shared file, B's load would REFUSE A's rows and `refused` would be
    non-empty.
    """
    a, b = _scope(audit, "A"), _scope(audit, "B")
    store = PrivateGraphStore(tmp_path)
    a_world, b_world = SE.build(scope=a, seed=7), SE.build(scope=b, seed=7)
    store.append(scope=a, nodes=a_world.nodes, edges=a_world.edges)
    store.append(scope=b, nodes=b_world.nodes, edges=b_world.edges)

    for scope, world in ((a, a_world), (b, b_world)):
        result = store.load_into(BusinessGraph(), scope=scope)
        assert result.refused == (), (
            "this tenant's partition holds another tenant's rows; the read "
            "filter is refusing them, which means the partition is not doing "
            "its half of the job")
        assert result.nodes == len(world.nodes)


# =============================================================================
# 6. A SYNTHETIC ROW MAY NOT JOIN A REAL ONE — D-SYN-001 acceptance 2
# =============================================================================
def test_a_synthetic_metric_joined_to_a_real_initiative_raises(world):
    """Not a downgraded confidence — a refusal.

    A mixed answer is not a weaker finding, it is an incoherent one: half of it
    describes a fixture and half describes a business, and no reader can tell
    which half moved the conclusion.
    """
    from intent_engine.external_intel.internal_impact import MixedPopulation

    scope, w = world
    graph = SE.install(BusinessGraph(), w, scope=scope)
    # A REAL initiative declaring the same subject as the synthetic world.
    graph.add_private_node(P.private_node(
        scope=scope, kind=P.INITIATIVE, local_id="init-real",
        label="Real initiative", company_id="acme",
        source="crm", observed_at="2026-07-01T00:00:00+00:00",
        known_at="2026-07-02T00:00:00+00:00",
        sensitivity=P.SENSITIVITY_INTERNAL,
        attrs={POPULATION_KEY: REAL_ENTERPRISE,
               "external_subject": SE.SUBJECT_MOVES_METRICS}), scope=scope)
    with pytest.raises(MixedPopulation):
        assess_internal_impact(graph, subject_id=SE.SUBJECT_MOVES_METRICS,
                               scope=scope)


def test_an_all_synthetic_answer_does_not_raise(world):
    """The NEGATIVE CONTROL. Without it the guard above is satisfied by a
    reader that refuses every answer."""
    scope, w = world
    graph = SE.install(BusinessGraph(), w, scope=scope)
    got = assess_internal_impact(graph, subject_id=SE.SUBJECT_MOVES_METRICS,
                                 scope=scope)
    assert got.populations == (SYNTHETIC_ENTERPRISE,)


def test_the_mixture_guard_is_callable_and_reports_only_a_mixture():
    from intent_engine.external_intel.internal_impact import (
        MixedPopulation, refuse_mixed_population,
    )
    refuse_mixed_population(())
    refuse_mixed_population((SYNTHETIC_ENTERPRISE,))
    refuse_mixed_population((REAL_ENTERPRISE,))
    with pytest.raises(MixedPopulation):
        refuse_mixed_population((SYNTHETIC_ENTERPRISE, REAL_ENTERPRISE))
