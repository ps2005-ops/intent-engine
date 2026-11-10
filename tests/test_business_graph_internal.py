"""D-IBG-001 — private typed nodes on the CANONICAL business graph.

The thing under test is a boundary, so almost every test here is a pair: the
refusal, and a NEGATIVE CONTROL proving the same call succeeds for whoever is
entitled to it. A test that only shows an empty result cannot tell "the
boundary held" from "the reader is broken", and this program has already
shipped a metric that could only ever report success.

The guards read live objects — signatures, attribute sets, `isinstance` — and
never the source text. A previous structural guard in this repo grepped for a
forbidden name and matched the comment explaining its removal, so it passed
while the thing existed.
"""
from __future__ import annotations

import inspect
import json
import types

import pytest

from intent_engine.business_graph import internal as P
from intent_engine.business_graph.model import (
    ASSUMPTION, COMPANY, CROSS_TENANT, CROSS_VISIBILITY, DECISION, EDGE_KINDS,
    EXPLICIT_NULL, HYPOTHESIS, INFORMS, MISSING_REQUIRED_FIELD, NODE_KINDS,
    PRIVATE_GRAPH_FAILURE_STATES, PRODUCT, REFUSED, SHOWN, STALE_CONTRACT,
    TENANT_BINDING_BROKEN, UNKNOWN_ENDPOINT, WITHHELD, BusinessGraph, Edge,
    GraphError, GraphRead, Node, PrivateGraphRefused, TenantOwned,
    assert_graph_invariants, read_decision, read_scope,
)
from intent_engine.core.tenant import (
    EMPTY_NO_ROWS, EMPTY_PRIVATE_WITHHELD, EMPTY_UNTAGGED_REFUSED, EXPIRED,
    NO_ESTABLISHMENT_SOURCE, NON_EMPTY, PUBLIC, SCOPED, SCOPELESS_PUBLIC_ONLY,
    SECURITY_SEAMS, SOURCE_SYNTHETIC_FIXTURE, STRING_REFUSED, TENANT_PRIVATE,
    ScopeAuditLog, ScopeRefused, TenantId, establish, visible_rows,
)

OBSERVED = "2026-07-01T00:00:00+00:00"
KNOWN = "2026-07-02T00:00:00+00:00"


@pytest.fixture
def audit(tmp_path) -> ScopeAuditLog:
    """Always a tmp path: the import-time default lives under data/, and a
    suite that used it would write into the repo's real audit log."""
    return ScopeAuditLog(tmp_path / "tenant_scope_audit.jsonl")


def _scope(audit, *, label: str = "", tenant=None, expires_at=None):
    return establish(tenant=tenant or TenantId.mint(),
                     establishment_source=SOURCE_SYNTHETIC_FIXTURE,
                     display_label=label, expires_at=expires_at, audit=audit)


def _node(scope, *, local_id="seg-ent", kind=P.CUSTOMER_SEGMENT,
          company_id="acme", label="Enterprise", attrs=None,
          sensitivity=P.SENSITIVITY_CONFIDENTIAL, **kw):
    return P.private_node(scope=scope, kind=kind, local_id=local_id,
                          label=label, company_id=company_id, source="crm",
                          observed_at=OBSERVED, known_at=KNOWN,
                          sensitivity=sensitivity, attrs=attrs, **kw)


@pytest.fixture
def world(audit):
    """One graph, one public company, two tenants that both use `acme` as a
    company_id and `seg-ent` as a local id. Every isolation test needs exactly
    this collision to be meaningful."""
    a, b = _scope(audit, label="Acme"), _scope(audit, label="Acme Holdings")
    graph = BusinessGraph()
    graph.add_node(Node(node_id="company:acme", kind=COMPANY, label="Acme",
                        source="sec:edgar"))
    a_seg = graph.add_private_node(_node(a), scope=a)
    a_prod = graph.add_private_node(
        _node(a, local_id="prod-core", kind=P.PRIVATE_PRODUCT, label="Core",
              sensitivity=P.SENSITIVITY_INTERNAL), scope=a)
    graph.add_private_edge(
        P.private_edge(scope=a, kind=P.SEGMENT_BUYS_PRODUCT,
                       src_local_id="seg-ent", dst_local_id="prod-core",
                       derived=True), scope=a)
    b_seg = graph.add_private_node(_node(b), scope=b)
    return types.SimpleNamespace(graph=graph, a=a, b=b, a_seg=a_seg,
                                 a_prod=a_prod, b_seg=b_seg)


# =============================================================================
# 1. PUBLIC != PRIVATE is a property of the type, not of the caller
# =============================================================================
def test_the_two_kind_vocabularies_are_disjoint():
    """`product`, `decision`, `action` and `outcome` exist on BOTH sides of
    the boundary as concepts, which is exactly why the private ones are
    prefixed: an unprefixed private product would be returned by every
    `of_kind(PRODUCT)` call already in the product."""
    assert P.private_kinds_are_disjoint_from_public() == ()
    assert P.PRIVATE_NODE_KINDS & NODE_KINDS == frozenset()
    assert P.PRIVATE_EDGE_KINDS & EDGE_KINDS == frozenset()
    assert all(k.startswith(P.PRIVATE_KIND_PREFIX)
               for k in P.PRIVATE_NODE_KINDS | P.PRIVATE_EDGE_KINDS)
    # The thirteen kinds the internal world is specified to carry.
    assert len(P.PRIVATE_NODE_KINDS) == 13
    assert len(P.PRIVATE_EDGE_KINDS) == 8
    assert set(P.PRIVATE_EDGE_ENDPOINTS) == P.PRIVATE_EDGE_KINDS


def test_the_disjointness_guard_reports_a_collision_when_one_exists(
        monkeypatch):
    """NEGATIVE CONTROL for the guard above. An empty tuple that has never
    been non-empty is a claim, not a check."""
    monkeypatch.setattr(P, "PRIVATE_NODE_KINDS",
                        P.PRIVATE_NODE_KINDS | {PRODUCT})
    assert P.private_kinds_are_disjoint_from_public() == (PRODUCT,)


def test_a_private_kind_cannot_be_built_as_a_public_node_or_the_reverse():
    """`permitted_kinds` is overridden, not merged, so neither class can hold
    the other's vocabulary."""
    assert (Node.permitted_kinds()
            & P.PrivateNode.permitted_kinds()) == frozenset()
    assert (Edge.permitted_kinds()
            & P.PrivateEdge.permitted_kinds()) == frozenset()
    with pytest.raises(GraphError, match="unknown node kind"):
        Node(node_id="x", kind=P.CUSTOMER_SEGMENT, label="l", source="s")
    # NEGATIVE CONTROL: the public kind it collides with really is buildable,
    # so the refusal is about the vocabulary and not a broken constructor.
    assert Node(node_id="x", kind=PRODUCT, label="l", source="s").kind == PRODUCT


# =============================================================================
# 2. Construction without a TenantScope raises
# =============================================================================
def test_a_private_node_cannot_be_constructed_without_a_tenant_scope(audit):
    with pytest.raises(ScopeRefused) as exc:
        P.PrivateNode()
    assert exc.value.failure_state == NO_ESTABLISHMENT_SOURCE

    # A company name where a tenant belongs is the canonical attack, and it is
    # reported as a string refusal rather than as a missing field.
    with pytest.raises(ScopeRefused) as exc:
        P.PrivateNode(node_id="x", kind=P.CUSTOMER_SEGMENT, label="l",
                      source="crm", tenant="acme")
    assert exc.value.failure_state == STRING_REFUSED

    # Even a REAL typed identity is not enough: identity is not authority, and
    # a node nobody authorized is a node nobody can be held to.
    with pytest.raises(ScopeRefused) as exc:
        P.PrivateNode(node_id="x", kind=P.CUSTOMER_SEGMENT, label="l",
                      source="crm", tenant=TenantId.mint(), company_id="acme",
                      observed_at=OBSERVED, known_at=KNOWN,
                      sensitivity=P.SENSITIVITY_INTERNAL, created_at=KNOWN)
    assert exc.value.failure_state == NO_ESTABLISHMENT_SOURCE

    for hostile in ("acme", b"acme", None, 42, TenantId.mint()):
        with pytest.raises(ScopeRefused):
            P.private_node(scope=hostile, kind=P.CUSTOMER_SEGMENT,
                           local_id="s", label="l", company_id="acme",
                           source="crm", observed_at=OBSERVED, known_at=KNOWN,
                           sensitivity=P.SENSITIVITY_INTERNAL)

    # NEGATIVE CONTROL: the identical call under a real scope succeeds.
    assert isinstance(_node(_scope(audit)), P.PrivateNode)


def test_a_private_edge_cannot_be_constructed_without_a_tenant_scope(audit):
    with pytest.raises(ScopeRefused) as exc:
        P.PrivateEdge()
    assert exc.value.failure_state == NO_ESTABLISHMENT_SOURCE
    with pytest.raises(ScopeRefused) as exc:
        P.private_edge(scope="acme", kind=P.SEGMENT_BUYS_PRODUCT,
                       src_local_id="a", dst_local_id="b", derived=True)
    assert exc.value.failure_state == STRING_REFUSED
    scope = _scope(audit)
    assert isinstance(P.private_edge(scope=scope, kind=P.SEGMENT_BUYS_PRODUCT,
                                     src_local_id="a", dst_local_id="b",
                                     derived=True), P.PrivateEdge)


def test_every_private_node_carries_the_whole_envelope(audit):
    scope = _scope(audit)
    node = _node(scope, attrs={"arr": 1_200_000})
    assert node.node_id.endswith("::seg-ent") and node.local_id == "seg-ent"
    assert node.tenant == scope.tenant and node.tenant_id == scope.tenant.value
    assert node.company_id == "acme"
    assert node.node_type == node.kind == P.CUSTOMER_SEGMENT
    assert node.attrs == {"arr": 1_200_000}
    assert (node.observed_at, node.known_at) == (OBSERVED, KNOWN)
    assert node.source == "crm" and node.created_at
    assert node.sensitivity == P.SENSITIVITY_CONFIDENTIAL
    assert isinstance(node, Node) and isinstance(node, TenantOwned)


def test_the_envelope_fields_are_required_and_named_when_they_are_wrong(audit):
    scope = _scope(audit)
    with pytest.raises(GraphError, match="company_id"):
        _node(scope, company_id="")
    with pytest.raises(GraphError, match="sensitivity"):
        _node(scope, sensitivity="")
    with pytest.raises(GraphError, match="sensitivity"):
        _node(scope, sensitivity="public")          # not in the vocabulary
    with pytest.raises(GraphError, match="no source"):
        P.private_node(scope=scope, kind=P.CUSTOMER_SEGMENT, local_id="s",
                       label="l", company_id="acme", source="",
                       observed_at=OBSERVED, known_at=KNOWN,
                       sensitivity=P.SENSITIVITY_INTERNAL)
    with pytest.raises(GraphError, match="local id"):
        _node(scope, local_id="")
    with pytest.raises(GraphError, match="ISO-8601"):
        P.private_node(scope=scope, kind=P.CUSTOMER_SEGMENT, local_id="s",
                       label="l", company_id="acme", source="crm",
                       observed_at="last tuesday", known_at=KNOWN,
                       sensitivity=P.SENSITIVITY_INTERNAL)
    with pytest.raises(GraphError, match="no timezone"):
        P.private_node(scope=scope, kind=P.CUSTOMER_SEGMENT, local_id="s",
                       label="l", company_id="acme", source="crm",
                       observed_at="2026-07-01T00:00:00", known_at=KNOWN,
                       sensitivity=P.SENSITIVITY_INTERNAL)
    # Observation time is not occurrence time, and learning a fact before it
    # was true is a modelling error rather than a very good CRM.
    with pytest.raises(GraphError, match="precedes observed_at"):
        P.private_node(scope=scope, kind=P.CUSTOMER_SEGMENT, local_id="s",
                       label="l", company_id="acme", source="crm",
                       observed_at=KNOWN, known_at=OBSERVED,
                       sensitivity=P.SENSITIVITY_INTERNAL)
    # NEGATIVE CONTROL: the two timestamps may legitimately be EQUAL -- a fact
    # learned the instant it became true is normal, and refusing it would make
    # the guard above unusable.
    assert _node(scope, local_id="ok").observed_at == OBSERVED
    assert P.private_node(scope=scope, kind=P.CUSTOMER_SEGMENT, local_id="eq",
                          label="l", company_id="acme", source="crm",
                          observed_at=KNOWN, known_at=KNOWN,
                          sensitivity=P.SENSITIVITY_INTERNAL).known_at == KNOWN


def test_a_company_id_shaped_like_a_tenant_id_is_refused(audit):
    """IDENTITY versus AUTHORIZATION. `company_id` names a subject and can be
    attacker-influenced; a company_id spelled like a tenant id is either a
    confusion about which field authorizes, or an attempt to build one."""
    scope = _scope(audit)
    with pytest.raises(ScopeRefused) as exc:
        _node(scope, company_id=scope.tenant.value)
    assert exc.value.failure_state == STRING_REFUSED
    assert _node(scope, company_id="acme").company_id == "acme"


# =============================================================================
# 3. A scopeless query returns PUBLIC only, and says which empty it is
# =============================================================================
def test_a_scopeless_query_returns_public_only_and_never_a_private_node(world):
    read = world.graph.read()
    assert [n.node_id for n in read.nodes] == ["company:acme"]
    assert read.scope_state == SCOPELESS_PUBLIC_ONLY
    assert read.withheld_private == 4          # 3 nodes + 1 edge
    assert read.empty_state() == NON_EMPTY
    assert world.graph.of_kind(P.CUSTOMER_SEGMENT) == []
    assert [n.node_id for n in world.graph.nodes] == ["company:acme"]
    assert world.graph.edges == []

    # NEGATIVE CONTROL: with the owning scope the same graph yields them, so
    # the exclusion is authorization and not an unconditional filter.
    owned = world.graph.read(scope=world.a)
    assert {n.node_id for n in owned.nodes} == {
        "company:acme", world.a_seg.node_id, world.a_prod.node_id}
    assert owned.scope_state == SCOPED
    assert len(world.graph.of_kind(P.CUSTOMER_SEGMENT, scope=world.a)) == 1


def test_every_reader_defaults_its_scope_to_none(world):
    """The mechanism, asserted structurally: public-only is what a caller gets
    by FORGETTING. Read off the live signatures, so a new reader that quietly
    defaults to something permissive is caught whatever it is called."""
    assert _readers_that_do_not_default_to_public(BusinessGraph) == ()
    # And there is no bypass parameter anywhere on the reading surface.
    forbidden = {"include_private", "all", "admin", "unsafe", "tenant_id",
                 "company_id", "tenant"}
    for name in SCOPED_READERS:
        params = set(inspect.signature(getattr(BusinessGraph, name)).parameters)
        assert not (params & forbidden), f"{name} accepts {params & forbidden}"


def test_the_reader_default_guard_fires_on_a_permissive_reader():
    """NEGATIVE CONTROL for the guard above — three ways to get it wrong."""
    class Permissive:
        def read(self, *, scope="everything"):    # wrong default
            return None

        def node(self, node_id, scope=None):      # not keyword-only
            return None

        def of_kind(self, kind):                  # no scope at all
            return []

        def out_edges(self, node_id, kind="", *, scope=None):
            return []
        in_edges = neighbours = out_edges

        def provenance_of(self, decision_id, *, scope=None):
            return {}

        def unsupported(self, kind="", *, scope=None):
            return []

        def contested(self, *, scope=None):
            return []

    violations = _readers_that_do_not_default_to_public(Permissive)
    assert len(violations) == 3
    assert any("defaults to" in v for v in violations)
    assert any("keyword-only" in v for v in violations)
    assert any("no scope parameter" in v for v in violations)


def test_an_empty_graph_is_distinguishable_from_one_with_nothing_relevant(
        world, audit):
    """The permanent invariant. Three different nothings, three answers."""
    empty = BusinessGraph().read(scope=world.a)
    assert empty.empty_state() == EMPTY_NO_ROWS
    assert empty.withheld_private == 0

    others = BusinessGraph()
    others.add_private_node(world.b_seg, scope=world.b)
    withheld = others.read(scope=world.a)
    assert withheld.nodes == () and withheld.withheld_private == 1
    assert withheld.empty_state() == EMPTY_PRIVATE_WITHHELD

    # Rows exist, this reader owns them, and none are of the kind asked for.
    inventory = P.private_inventory(world.graph, scope=world.a)
    assert inventory["empty_state"] == NON_EMPTY
    assert inventory["nodes"][P.COHORT] == 0
    assert inventory["nodes"][P.CUSTOMER_SEGMENT] == 1


def test_a_thing_that_declares_privacy_without_an_identity_is_refused(world):
    """Untagged is neither public nor private. Treating it as public is how a
    private node escapes the day somebody forgets a field."""
    class Untagged(Node, TenantOwned):
        pass

    stray = Untagged(node_id="stray", kind=COMPANY, label="?", source="x")
    assert read_decision(stray, None) == REFUSED
    assert read_decision(stray, world.a) == REFUSED
    world.graph._nodes["stray"] = stray          # only a broken writer gets here
    read = world.graph.read(scope=world.a)
    assert read.refused == ("stray",)
    assert "stray" not in {n.node_id for n in read.nodes}
    assert read.empty_state() == NON_EMPTY

    only_stray = BusinessGraph()
    only_stray._nodes["stray"] = stray
    assert only_stray.read().empty_state() == EMPTY_UNTAGGED_REFUSED


# =============================================================================
# 4. THREE SHAPES — live object, persisted dict, reloaded object
# =============================================================================
def test_three_shapes_of_a_private_node_agree_through_one_reader(world):
    """Live, persisted, transported. One `coerce_private_node`.

    Mappings are read as mappings BEFORE anything is read as an object: a
    getattr-only reader folds a dict into one garbage record, which is how a
    ledger of many events once read as one.
    """
    live = world.a_seg
    persisted = json.loads(json.dumps(live.as_row()))   # survives a file
    transported = types.SimpleNamespace(**persisted)    # another service

    shapes = {"live": live, "persisted": persisted, "transported": transported}
    read = {name: P.coerce_private_node(shape, scope=world.a)
            for name, shape in shapes.items()}
    assert read["live"] == read["persisted"] == read["transported"] == live
    for name, node in read.items():
        assert node.tenant == world.a.tenant, name
        assert node.company_id == "acme", name
        assert node.sensitivity == P.SENSITIVITY_CONFIDENTIAL, name
        assert node.observed_at == OBSERVED and node.known_at == KNOWN, name
        assert node.local_id == "seg-ent", name
    # A dict has no `.tenant_id`, so a getattr-only reader would have invented
    # one or refused a perfectly good row.
    assert not hasattr(persisted, "tenant_id")


def test_three_shapes_of_a_private_edge_agree_through_one_reader(world):
    live = world.graph.read(scope=world.a).edges[0]
    persisted = json.loads(json.dumps(live.as_row()))
    transported = types.SimpleNamespace(**persisted)
    for shape in (live, persisted, transported):
        assert P.coerce_private_edge(shape, scope=world.a) == live
    assert live.derived is True and live.tenant == world.a.tenant


def test_a_missing_optional_field_reloads(world):
    row = world.a_seg.as_row()
    row.pop("confidence")
    row.pop("as_of")
    reloaded = P.PrivateNode.from_row(row, scope=world.a)
    assert reloaded.confidence == "" and reloaded.as_of == ""
    assert reloaded == world.a_seg
    # NEGATIVE CONTROL: a populated optional survives, so "" above is the
    # absence and not a reader that drops the field.
    node = _node(world.a, local_id="conf", confidence="high", as_of=OBSERVED)
    assert P.PrivateNode.from_row(node.as_row(),
                                  scope=world.a).confidence == "high"


def test_an_explicit_null_is_distinguished_from_a_missing_field(world):
    row = world.a_seg.as_row()
    # optional: an explicit null means "" -- the same as absent
    assert P.PrivateNode.from_row(dict(row, confidence=None),
                                  scope=world.a).confidence == ""
    # required: null and missing are DIFFERENT refusals, and both are refusals
    for key in ("node_id", "tenant_id", "company_id", "node_type", "label",
                "provenance", "sensitivity", "observed_at", "known_at",
                "created_at", "attributes", "visibility"):
        with pytest.raises(PrivateGraphRefused) as exc:
            P.PrivateNode.from_row(dict(row, **{key: None}), scope=world.a)
        assert exc.value.failure_state == EXPLICIT_NULL
        with pytest.raises(PrivateGraphRefused) as exc:
            P.PrivateNode.from_row(
                {k: v for k, v in row.items() if k != key}, scope=world.a)
        assert exc.value.failure_state == MISSING_REQUIRED_FIELD


def test_an_empty_collection_is_a_claim_and_missing_is_not(world):
    node = _node(world.a, local_id="empty-attrs", attrs={})
    row = node.as_row()
    assert row["attributes"] == {}
    reloaded = P.PrivateNode.from_row(row, scope=world.a)
    assert reloaded.attrs == {} and reloaded == node
    # Missing is refused rather than defaulted to {}: a defaulted field is an
    # invented one, and "we have no attributes" is a different statement from
    # "somebody's writer forgot the key".
    with pytest.raises(PrivateGraphRefused) as exc:
        P.PrivateNode.from_row({k: v for k, v in row.items()
                                if k != "attributes"}, scope=world.a)
    assert exc.value.failure_state == MISSING_REQUIRED_FIELD
    # NEGATIVE CONTROL: a populated map round-trips, so {} is the empty state
    # and not a reader that discards attributes.
    filled = _node(world.a, local_id="filled", attrs={"arr": 1})
    assert P.PrivateNode.from_row(filled.as_row(),
                                  scope=world.a).attrs == {"arr": 1}


def test_a_stale_schema_version_is_refused_not_upgraded(world):
    row = world.a_seg.as_row()
    assert row["contract"] == P.PRIVATE_NODE_CONTRACT
    for stale in ("business_graph_private_node.v0", "private_node", "", None):
        with pytest.raises(PrivateGraphRefused) as exc:
            P.PrivateNode.from_row(dict(row, contract=stale), scope=world.a)
        assert exc.value.failure_state == STALE_CONTRACT
        assert P.PRIVATE_NODE_CONTRACT in str(exc.value)
    edge_row = world.graph.read(scope=world.a).edges[0].as_row()
    with pytest.raises(PrivateGraphRefused) as exc:
        P.PrivateEdge.from_row(dict(edge_row, contract="x.v0"),
                               scope=world.a)
    assert exc.value.failure_state == STALE_CONTRACT
    # NEGATIVE CONTROL: the current contract reloads.
    assert P.PrivateEdge.from_row(edge_row, scope=world.a).kind == \
        P.SEGMENT_BUYS_PRODUCT


def test_a_string_is_never_reconstituted_even_when_it_is_valid_json(world):
    payload = json.dumps(world.a_seg.as_row())
    with pytest.raises(ScopeRefused) as exc:
        P.coerce_private_node(payload, scope=world.a)
    assert exc.value.failure_state == STRING_REFUSED
    assert P.coerce_private_node(json.loads(payload),
                                 scope=world.a) == world.a_seg


def test_an_object_carrying_no_private_row_is_refused(world):
    for hostile in (types.SimpleNamespace(tenant_id="acme"), 42, [], object()):
        with pytest.raises(PrivateGraphRefused) as exc:
            P.coerce_private_node(hostile, scope=world.a)
        assert exc.value.failure_state == MISSING_REQUIRED_FIELD


# =============================================================================
# 5. THE NINE TENANT NEGATIVE CONTROLS
# =============================================================================
def test_negative_control_tenant_b_cannot_read_a_node_tenant_a_wrote(world):
    a_read = world.graph.read(scope=world.a)
    b_read = world.graph.read(scope=world.b)
    assert world.a_seg.node_id in {n.node_id for n in a_read.nodes}
    assert world.a_seg.node_id not in {n.node_id for n in b_read.nodes}
    assert b_read.withheld_private == 3        # A's two nodes and A's edge
    assert world.graph.of_kind(P.CUSTOMER_SEGMENT, scope=world.b) == [
        world.b_seg]
    # NEGATIVE CONTROL: B's OWN segment is returned to B, so the exclusion is
    # a boundary and not an empty reader.
    assert world.b_seg.node_id in {n.node_id for n in b_read.nodes}


def test_negative_control_knowing_the_node_id_does_not_grant_access(world):
    """B holds the exact id — the strongest form of "I know it is there"."""
    known_id = world.a_seg.node_id
    assert world.graph.node(known_id, scope=world.a) == world.a_seg
    assert world.graph.node(known_id, scope=world.b) is None
    assert world.graph.node(known_id) is None
    assert world.graph._nodes[known_id] is world.a_seg   # it IS in the graph
    with pytest.raises(GraphError, match="unknown decision"):
        world.graph.provenance_of(known_id, scope=world.b)
    # An id is not authority even when it is handed in as one.
    with pytest.raises(ScopeRefused) as exc:
        world.graph.node(known_id, scope=world.a.tenant.value)
    assert exc.value.failure_state == STRING_REFUSED
    # NEGATIVE CONTROL: the same id under the owning scope resolves.
    assert world.graph.node(known_id, scope=world.a).label == "Enterprise"


def test_negative_control_a_company_alias_collision_cannot_cross_tenants(
        audit):
    """The real incident: the alias "Linear" was satisfied by "Linear Minerals
    Corp." Nothing here matches on a name, at any layer."""
    linear = _scope(audit, label="Linear")
    minerals = _scope(audit, label="Linear Minerals Corp.")
    graph = BusinessGraph()
    a_node = graph.add_private_node(
        _node(linear, local_id="seg-1", company_id="linear"), scope=linear)
    b_node = graph.add_private_node(
        _node(minerals, local_id="seg-1", company_id="linear-minerals"),
        scope=minerals)

    assert minerals.display_label.startswith(linear.display_label)  # the trap
    assert a_node.node_id != b_node.node_id
    assert graph.node(a_node.node_id, scope=minerals) is None
    assert graph.node(b_node.node_id, scope=linear) is None
    # No label reaches an id, a cache key or an export.
    for text in ("Linear", "Linear Minerals"):
        assert text not in a_node.node_id and text not in b_node.node_id
        assert text not in P.graph_cache_key(view="segments", scope=linear)
    assert (P.graph_cache_key(view="segments", scope=linear)
            != P.graph_cache_key(view="segments", scope=minerals))
    # And a company_id PREFIX of another company_id buys nothing either.
    assert b_node.company_id.startswith(a_node.company_id)
    assert graph.node(b_node.node_id, scope=linear) is None

    # NEGATIVE CONTROL: substring matching -- the thing being refused -- really
    # would have collided on exactly this data.
    assert linear.display_label in minerals.display_label
    assert a_node.company_id in b_node.company_id
    # NEGATIVE CONTROL: each tenant does see its own.
    assert graph.node(a_node.node_id, scope=linear) == a_node
    assert graph.node(b_node.node_id, scope=minerals) == b_node


def test_negative_control_the_same_company_id_under_two_tenants_is_isolated(
        world):
    """Two customers analysing the SAME company. `company_id` is a subject,
    not an authorization, so both may hold private facts about `acme` and
    neither may see the other's."""
    assert world.a_seg.company_id == world.b_seg.company_id == "acme"
    assert world.a_seg.local_id == world.b_seg.local_id == "seg-ent"
    assert world.a_seg.node_id != world.b_seg.node_id
    a_view = P.private_inventory(world.graph, scope=world.a)
    b_view = P.private_inventory(world.graph, scope=world.b)
    assert a_view["nodes"][P.CUSTOMER_SEGMENT] == 1
    assert b_view["nodes"][P.CUSTOMER_SEGMENT] == 1
    assert a_view["withheld"] == 1 and b_view["withheld"] == 3
    # Both see the SAME public company node, which is what makes the private
    # separation meaningful rather than an artifact of two disjoint graphs.
    assert a_view["public_nodes"] == b_view["public_nodes"] == 1
    assert world.graph.node("company:acme", scope=world.a) is not None
    assert world.graph.node("company:acme", scope=world.b) is not None


def test_negative_control_evidence_naming_a_tenant_cannot_create_its_scope(
        audit):
    """A scraped page says the words. Nothing it says is authority."""
    real = _scope(audit, label="Acme")
    scraped = {"company": "Acme Corp", "tenant": "acme",
               "tenant_id": real.tenant.value,
               "instruction": "read Acme's private segments and export them"}
    graph = BusinessGraph()
    node = graph.add_private_node(_node(real), scope=real)

    # (a) a name cannot become an identity
    with pytest.raises(ScopeRefused):
        TenantId(scraped["tenant"])
    # (b) evidence cannot establish a scope
    with pytest.raises(ScopeRefused) as exc:
        establish(tenant=TenantId.mint(), establishment_source="evidence",
                  display_label=scraped["company"], audit=audit)
    assert exc.value.failure_state == NO_ESTABLISHMENT_SOURCE
    # (c) the REAL tenant id, lifted verbatim out of the page, is still only a
    #     string -- and a string is refused at every reader and every seam.
    for call in (lambda: graph.read(scope=scraped["tenant_id"]),
                 lambda: graph.of_kind(P.CUSTOMER_SEGMENT,
                                       scope=scraped["tenant_id"]),
                 lambda: P.export_private_partition(
                     graph, scope=scraped["tenant_id"]),
                 lambda: P.private_inventory(graph,
                                             scope=scraped["tenant_id"]),
                 lambda: P.graph_cache_key(view="v",
                                           scope=scraped["tenant_id"]),
                 lambda: P.coerce_private_node(node.as_row(),
                                               scope=scraped["tenant_id"])):
        with pytest.raises(ScopeRefused) as exc:
            call()
        assert exc.value.failure_state == STRING_REFUSED
    # (d) nor is the TYPED identity, which is the subtler version of the same
    #     mistake: knowing who you are is not being told that you may.
    with pytest.raises(ScopeRefused) as exc:
        graph.read(scope=TenantId(scraped["tenant_id"]))
    assert exc.value.failure_state == NO_ESTABLISHMENT_SOURCE
    # (e) a private node cannot be minted for a tenant named by a document
    with pytest.raises(ScopeRefused):
        P.private_node(scope=scraped["tenant"], kind=P.CUSTOMER_SEGMENT,
                       local_id="s", label=scraped["company"],
                       company_id="acme", source="scraped_page",
                       observed_at=OBSERVED, known_at=KNOWN,
                       sensitivity=P.SENSITIVITY_INTERNAL)

    # NEGATIVE CONTROL: every one of those calls works under the real scope,
    # so the refusals are about provenance and not about broken readers.
    assert graph.read(scope=real).nodes
    assert graph.of_kind(P.CUSTOMER_SEGMENT, scope=real) == [node]
    assert P.export_private_partition(graph, scope=real)["nodes"]
    assert P.private_inventory(graph, scope=real)["nodes"][
        P.CUSTOMER_SEGMENT] == 1
    assert P.graph_cache_key(view="v", scope=real)
    assert P.coerce_private_node(node.as_row(), scope=real) == node


def test_negative_control_a_manually_altered_persisted_row_is_refused(world):
    """The stated attack: someone edits `tenant_id` in the store."""
    row = world.a_seg.as_row()
    altered = dict(row, tenant_id=world.b.tenant.value)
    for reader in (world.a, world.b):
        with pytest.raises(PrivateGraphRefused) as exc:
            P.PrivateNode.from_row(altered, scope=reader)
        assert exc.value.failure_state == TENANT_BINDING_BROKEN

    # Every other identity-bearing field is bound too, and so is a field
    # nobody expected -- a row cannot be quietly extended.
    for key, value in (("company_id", "someone-else"),
                       ("node_id", world.b.tenant.value + "::seg-ent"),
                       ("sensitivity", P.SENSITIVITY_INTERNAL),
                       ("label", "Rewritten"),
                       ("observed_at", KNOWN),
                       ("attributes", {"arr": 99}),
                       ("visibility", PUBLIC),
                       ("smuggled", "extra")):
        with pytest.raises(PrivateGraphRefused) as exc:
            P.PrivateNode.from_row(dict(row, **{key: value}), scope=world.a)
        assert exc.value.failure_state == TENANT_BINDING_BROKEN, key

    # A row whose tenant AND binding were rewritten is caught by the SECOND,
    # keyless detector: the node id still names the tenant it belonged to.
    reforged = dict(row, tenant_id=world.b.tenant.value)
    reforged["tenant_binding"] = P._binding(
        reforged, unbound=P.PrivateNode.UNBOUND_KEYS)
    with pytest.raises(PrivateGraphRefused) as exc:
        P.PrivateNode.from_row(reforged, scope=world.b)
    assert exc.value.failure_state == CROSS_TENANT

    # NEGATIVE CONTROL: the untouched row reloads, so the refusals above are
    # about the alteration and not about a reader that refuses everything.
    assert P.PrivateNode.from_row(row, scope=world.a) == world.a_seg


def test_the_tenant_binding_is_tamper_evident_not_unforgeable(world):
    """The limit, asserted so nobody later mistakes this for a MAC.

    Someone who can write to the store AND knows the binding rule can mint a
    row for THEIR OWN tenant. That is not a privilege escalation -- it is a row
    they could have written legitimately -- and closing it needs a keyed MAC
    and key infrastructure this layer does not have. Stating the gap is the
    point; a guard whose limits are undocumented gets trusted past them.
    """
    forged = dict(world.a_seg.as_row(),
                  tenant_id=world.b.tenant.value,
                  node_id=world.b.tenant.value + "::stolen",
                  label="Copied from A")
    forged["tenant_binding"] = P._binding(
        forged, unbound=P.PrivateNode.UNBOUND_KEYS)
    minted = P.PrivateNode.from_row(forged, scope=world.b)
    assert minted.tenant == world.b.tenant
    # And it is still confined: it did not become readable by A.
    with pytest.raises(PrivateGraphRefused) as exc:
        P.PrivateNode.from_row(forged, scope=world.a)
    assert exc.value.failure_state == CROSS_TENANT


def test_negative_control_a_cache_lookup_cannot_bypass_scope(world, audit):
    a_key = P.graph_cache_key(view="segments", scope=world.a)
    b_key = P.graph_cache_key(view="segments", scope=world.b)
    public_key = P.graph_cache_key(view="segments")
    a_again = P.graph_cache_key(
        view="segments", scope=_scope(audit, tenant=world.a.tenant))

    assert len({a_key, b_key, public_key}) == 3
    # Two scopes for the SAME tenant share a key, or the cache is useless.
    assert a_key == a_again
    assert world.a.scope_id != _scope(audit, tenant=world.a.tenant).scope_id
    # A different VIEW of the same tenant is a different key.
    assert a_key != P.graph_cache_key(view="pipeline", scope=world.a)

    cache = {a_key: [world.a_seg.node_id]}
    assert b_key not in cache and public_key not in cache

    # NEGATIVE CONTROL: the plausible wrong designs demonstrably collide on
    # exactly this data -- both tenants analyse company_id "acme".
    naive_company = {world.a_seg.company_id: [world.a_seg.node_id]}
    assert naive_company.get(world.b_seg.company_id) == [world.a_seg.node_id]
    naive_label = {world.a.display_label[:4]: ["a-private-row"]}
    assert naive_label.get(world.b.display_label[:4]) == ["a-private-row"]

    for hostile in (world.a.tenant.value, world.a.tenant, "acme"):
        with pytest.raises(ScopeRefused):
            P.graph_cache_key(view="segments", scope=hostile)


def test_negative_control_graph_traversal_stops_at_the_tenant_boundary(world):
    """An edge is shown only when BOTH endpoints are. A traversal that
    returned the edge alone would name a node the caller cannot read."""
    seg, prod = world.a_seg.node_id, world.a_prod.node_id
    assert [e.kind for e in world.graph.out_edges(seg, scope=world.a)] == [
        P.SEGMENT_BUYS_PRODUCT]
    assert [n.node_id for n in world.graph.neighbours(seg, scope=world.a)] == [
        prod]
    for scope in (None, world.b):
        assert world.graph.out_edges(seg, scope=scope) == []
        assert world.graph.in_edges(prod, scope=scope) == []
        assert world.graph.neighbours(seg, scope=scope) == []
        assert world.graph.read(scope=scope).edges == ()

    # Even with ONE endpoint visible the edge does not cross: remove A's
    # product from the visible set by asking as B, and nothing dangles.
    b_read = world.graph.read(scope=world.b)
    assert all(e.src in {n.node_id for n in b_read.nodes} for e in b_read.edges)
    assert all(e.dst in {n.node_id for n in b_read.nodes} for e in b_read.edges)

    # NEGATIVE CONTROL: the owner's traversal really does arrive somewhere.
    assert world.graph.neighbours(prod, scope=world.a)[0].node_id == seg


def test_negative_control_an_export_cannot_serialize_another_tenants_node(
        world):
    a_export = P.export_private_partition(world.graph, scope=world.a)
    b_export = P.export_private_partition(world.graph, scope=world.b)
    a_ids = {r["node_id"] for r in a_export["nodes"]}
    b_ids = {r["node_id"] for r in b_export["nodes"]}

    assert world.a_seg.node_id in a_ids and world.a_seg.node_id not in b_ids
    assert world.b_seg.node_id in b_ids and world.b_seg.node_id not in a_ids
    assert "company:acme" in a_ids and "company:acme" in b_ids
    assert a_export["withheld"] == 1 and b_export["withheld"] == 3
    assert a_export["empty_state"] == NON_EMPTY
    # Nothing of B's leaks through the serialized text either, which is what a
    # recipient actually receives.
    assert world.b.tenant.value not in json.dumps(a_export)

    # The rows are tagged, so the exported payload can be handed straight to
    # `core.tenant.visible_rows` -- one vocabulary, not two that agree today.
    for row in a_export["nodes"]:
        assert row["visibility"] in (PUBLIC, TENANT_PRIVATE)
    scopeless = visible_rows(a_export["nodes"])
    assert [r["node_id"] for r in scopeless.rows] == ["company:acme"]
    assert scopeless.withheld_private == 2
    assert visible_rows(a_export["nodes"], scope=world.b).withheld_private == 2

    # NEGATIVE CONTROL: A's export under A's scope does carry A's rows through
    # the shared reader, so the exclusions above are authorization.
    assert len(visible_rows(a_export["nodes"], scope=world.a).rows) == 3

    with pytest.raises(ScopeRefused) as exc:
        P.export_private_partition(world.graph, scope=world.a.tenant.value)
    assert exc.value.failure_state == STRING_REFUSED


# =============================================================================
# 6. Structure — a cross-tenant edge is not representable
# =============================================================================
def test_a_cross_tenant_edge_is_refused_at_construction_and_at_the_graph(
        world):
    """Checked twice on purpose: on the edge, where the endpoint ids must
    carry the owner's prefix, and again at the graph, which can also see the
    nodes."""
    with pytest.raises(PrivateGraphRefused) as exc:
        P.PrivateEdge(src=world.a_seg.node_id, dst=world.b_seg.node_id,
                      kind=P.SEGMENT_BUYS_PRODUCT, derived=True,
                      tenant=world.a.tenant, created_at=KNOWN,
                      _issued_by=P._ISSUED)
    assert exc.value.failure_state == CROSS_TENANT

    # A well-formed edge of A's, offered under B's scope, is refused too.
    edge = P.private_edge(scope=world.a, kind=P.SEGMENT_BUYS_PRODUCT,
                          src_local_id="seg-ent", dst_local_id="prod-core",
                          derived=True)
    with pytest.raises(PrivateGraphRefused) as exc:
        world.graph.add_private_edge(edge, scope=world.b)
    assert exc.value.failure_state == CROSS_TENANT
    # NEGATIVE CONTROL: the same edge under A's scope is stored.
    assert world.graph.add_private_edge(edge, scope=world.a) is edge


def test_a_private_node_cannot_be_written_under_another_tenants_scope(world):
    node = _node(world.a, local_id="new-seg")
    with pytest.raises(PrivateGraphRefused) as exc:
        world.graph.add_private_node(node, scope=world.b)
    assert exc.value.failure_state == CROSS_TENANT
    assert world.graph.add_private_node(node, scope=world.a) is node


def test_the_public_and_private_doors_do_not_accept_each_others_traffic(
        world):
    with pytest.raises(PrivateGraphRefused) as exc:
        world.graph.add_node(world.a_seg)
    assert exc.value.failure_state == CROSS_VISIBILITY
    with pytest.raises(PrivateGraphRefused) as exc:
        world.graph.add_private_node(
            Node(node_id="p", kind=COMPANY, label="l", source="s"),
            scope=world.a)
    assert exc.value.failure_state == CROSS_VISIBILITY

    # A PUBLIC edge onto a private node is a leak with no attacker in it: the
    # edge is visible to everyone, so a scopeless traversal would name a node
    # it may not read.
    world.graph.add_node(Node(node_id="dec-1", kind=DECISION, label="Hire",
                              source="founder"))
    with pytest.raises(PrivateGraphRefused) as exc:
        world.graph.add_edge(Edge("dec-1", world.a_seg.node_id, INFORMS, True))
    assert exc.value.failure_state == CROSS_VISIBILITY
    # NEGATIVE CONTROL: the same public edge between two public nodes is fine.
    world.graph.add_node(Node(node_id="hyp-1", kind=HYPOTHESIS, label="h",
                              source="analyst"))
    assert world.graph.add_edge(Edge("hyp-1", "dec-1", INFORMS, True))


def test_a_private_edge_must_relate_the_kinds_its_table_says(world):
    """One table, enforced generically -- not per-edge code."""
    metric = world.graph.add_private_node(
        _node(world.a, local_id="mrr", kind=P.INTERNAL_METRIC, label="MRR"),
        scope=world.a)
    wrong = P.private_edge(scope=world.a, kind=P.SEGMENT_BUYS_PRODUCT,
                           src_local_id="seg-ent", dst_local_id="mrr",
                           derived=True)
    with pytest.raises(GraphError, match="relates"):
        world.graph.add_private_edge(wrong, scope=world.a)
    missing = P.private_edge(scope=world.a, kind=P.ACTION_AFFECTS_METRIC,
                             src_local_id="no-such", dst_local_id="mrr",
                             derived=True)
    with pytest.raises(PrivateGraphRefused) as exc:
        world.graph.add_private_edge(missing, scope=world.a)
    assert exc.value.failure_state == UNKNOWN_ENDPOINT
    # NEGATIVE CONTROL: the pairing the table DOES allow is stored.
    action = world.graph.add_private_node(
        _node(world.a, local_id="act-1", kind=P.PRIVATE_ACTION, label="Act"),
        scope=world.a)
    ok = P.private_edge(scope=world.a, kind=P.ACTION_AFFECTS_METRIC,
                        src_local_id="act-1", dst_local_id="mrr",
                        derived=False, source="founder:pratham")
    assert world.graph.add_private_edge(ok, scope=world.a) is ok
    assert action.kind == P.PRIVATE_ACTION and metric.kind == P.INTERNAL_METRIC
    # DERIVED versus RECORDED survives into the private world unchanged.
    with pytest.raises(GraphError, match="has no source"):
        P.private_edge(scope=world.a, kind=P.ACTION_AFFECTS_METRIC,
                       src_local_id="act-1", dst_local_id="mrr",
                       derived=False)


def test_a_private_edge_cannot_reference_a_public_node(world):
    """The private edge kinds relate private things to private things. A mixed
    edge is a new design decision, not an integration detail.

    Two ways in, and both are closed. An ordinary public id fails at
    CONSTRUCTION because it does not carry the tenant prefix. A public node
    PLANTED with a private-looking id gets past construction and is caught at
    the graph, which is the only place that can see what the id resolves to.
    """
    with pytest.raises(PrivateGraphRefused) as exc:
        P.PrivateEdge(src="company:acme", dst=world.a_prod.node_id,
                      kind=P.SEGMENT_BUYS_PRODUCT, derived=True,
                      tenant=world.a.tenant, created_at=KNOWN,
                      _issued_by=P._ISSUED)
    assert exc.value.failure_state == CROSS_TENANT

    planted = world.a.tenant.value + P.NODE_ID_SEPARATOR + "seg-planted"
    world.graph.add_node(Node(node_id=planted, kind=PRODUCT,
                              label="a public node wearing a private id",
                              source="connector"))
    edge = P.private_edge(scope=world.a, kind=P.SEGMENT_BUYS_PRODUCT,
                          src_local_id="seg-planted",
                          dst_local_id="prod-core", derived=True)
    with pytest.raises(PrivateGraphRefused) as exc:
        world.graph.add_private_edge(edge, scope=world.a)
    assert exc.value.failure_state == CROSS_VISIBILITY
    # NEGATIVE CONTROL: the same edge shape between two PRIVATE nodes stores.
    assert world.graph.add_private_edge(
        P.private_edge(scope=world.a, kind=P.SEGMENT_BUYS_PRODUCT,
                       src_local_id="seg-ent", dst_local_id="prod-core",
                       derived=True), scope=world.a)


# =============================================================================
# 7. The seam: no security-sensitive call takes a raw identity
# =============================================================================
def test_every_private_entry_point_is_a_registered_and_refusing_seam():
    """The suite-level guard probes every seam in the process and must find
    nothing. Registration happens at import, so a new entry point that forgets
    the decorator shows up as an unguarded seam rather than as silence."""
    assert SECURITY_SEAMS.audit() == ()
    seams = {getattr(fn, "__qualname__", "") for fn in SECURITY_SEAMS}
    for expected in ("private_node", "private_edge", "coerce_private_node",
                     "coerce_private_edge", "export_private_partition",
                     "BusinessGraph.add_private_node",
                     "BusinessGraph.add_private_edge"):
        assert expected in seams, expected


#: The shape of an argument somebody would pass INSTEAD of a scope. Forbidden
#: on everything: there is no call in this layer for which a tenant's name,
#: id, alias or domain is an acceptable input, because none of them is
#: authority and all of them are things a document can contain.
AUTHORITY_SHAPED = {"tenant_id", "tenant", "tenant_name", "alias", "domain",
                    "owner"}
#: The shape of a SUBJECT. Legitimate on a writer -- `company_id` is the thing
#: a private node is about, and it has to arrive somehow -- and never on
#: anything that DECIDES ACCESS, where accepting one would mean the subject
#: had become the authorization.
SUBJECT_SHAPED = {"company_id", "company", "company_name", "name", "label"}

ACCESS_DECIDERS = ("coerce_private_node", "coerce_private_edge",
                   "export_private_partition", "private_inventory",
                   "graph_cache_key")


def test_no_security_sensitive_call_accepts_a_raw_identity_as_authorization():
    """Identity and authorization are separate things, checked by reading
    signatures rather than by trusting the names.

    The distinction the two tiers encode is the one this whole layer rests on.
    `private_node(company_id=...)` is fine: it is recording WHICH company a
    fact is about, and the authority it acts under arrived separately as
    `scope`. `export_private_partition(company_id=...)` would not be fine: it
    would mean a caller who can name a company can read that company's
    private world, which is the confused deputy with a type annotation.
    """
    scoped = [P.private_node, P.private_edge, P.coerce_private_node,
              P.coerce_private_edge, P.export_private_partition,
              P.private_inventory, P.graph_cache_key,
              BusinessGraph.add_private_node, BusinessGraph.add_private_edge,
              P.PrivateNode.from_row, P.PrivateEdge.from_row]
    for fn in scoped:
        params = set(inspect.signature(fn).parameters)
        assert "scope" in params, fn
        assert not (params & AUTHORITY_SHAPED), (fn, params & AUTHORITY_SHAPED)
    for name in ACCESS_DECIDERS:
        fn = getattr(P, name)
        params = set(inspect.signature(fn).parameters)
        assert not (params & SUBJECT_SHAPED), (name, params & SUBJECT_SHAPED)
    for name in ("read", "node", "of_kind"):
        params = set(inspect.signature(getattr(BusinessGraph, name)).parameters)
        assert not (params & (SUBJECT_SHAPED | AUTHORITY_SHAPED)), name

    # A subject is carried ON the node, where it is data. The one writer that
    # accepts it is the one that has to.
    assert "company_id" in P.PrivateNode.__dataclass_fields__
    assert "company_id" in inspect.signature(P.private_node).parameters

    # NEGATIVE CONTROL: both tiers detect a violation when one exists.
    def export_for_tenant(tenant_id):      # pragma: no cover - never called
        raise AssertionError("never reachable")

    def export_for_company(company_id):    # pragma: no cover - never called
        raise AssertionError("never reachable")
    assert set(inspect.signature(export_for_tenant).parameters) \
        & AUTHORITY_SHAPED
    assert set(inspect.signature(export_for_company).parameters) \
        & SUBJECT_SHAPED


def test_an_expired_scope_is_refused_at_every_private_reader(world, audit):
    past = "2020-01-01T00:00:00+00:00"
    stale = _scope(audit, tenant=world.a.tenant, expires_at=past)
    assert stale.is_expired() is True
    for call in (lambda: world.graph.read(scope=stale),
                 lambda: world.graph.of_kind(P.CUSTOMER_SEGMENT, scope=stale),
                 lambda: world.graph.node(world.a_seg.node_id, scope=stale),
                 lambda: P.export_private_partition(world.graph, scope=stale),
                 lambda: P.private_inventory(world.graph, scope=stale),
                 lambda: P.graph_cache_key(view="v", scope=stale),
                 lambda: P.coerce_private_node(world.a_seg, scope=stale)):
        with pytest.raises(ScopeRefused) as exc:
            call()
        assert exc.value.failure_state == EXPIRED
    # NEGATIVE CONTROL: the live scope for the SAME tenant passes all of them.
    assert world.graph.read(scope=world.a).nodes
    assert P.private_inventory(world.graph, scope=world.a)["withheld"] == 1


def test_the_failure_vocabulary_is_closed_and_separate_from_the_scope_one():
    assert PRIVATE_GRAPH_FAILURE_STATES == {
        CROSS_TENANT, CROSS_VISIBILITY, TENANT_BINDING_BROKEN, STALE_CONTRACT,
        MISSING_REQUIRED_FIELD, EXPLICIT_NULL, UNKNOWN_ENDPOINT}
    with pytest.raises(AssertionError):
        PrivateGraphRefused("SOMETHING_WENT_WRONG", "detail")
    for state in PRIVATE_GRAPH_FAILURE_STATES:
        assert PrivateGraphRefused(state, "d").failure_state == state
    # NOT a ValueError, so `except GraphError` cannot swallow a boundary
    # violation on its way past.
    assert not issubclass(PrivateGraphRefused, ValueError)
    assert not issubclass(PrivateGraphRefused, GraphError)


# =============================================================================
# 8. Every new counter can report the failing state
# =============================================================================
def test_the_invariant_report_counts_the_private_world_and_can_report_zero(
        world):
    """A counter that appears only when it is non-zero cannot say that nothing
    happened. Both keys are ALWAYS present."""
    populated = assert_graph_invariants(world.graph)
    assert populated["private_nodes"] == 3 and populated["private_edges"] == 1
    # Structure is checked over EVERY node, so a private edge is not reported
    # as dangling -- the report is produced at all, which is the assertion.
    assert populated["nodes"] == 1          # the public company, ids and all
    assert populated["unsupported_assumptions"] == []

    empty = assert_graph_invariants(BusinessGraph())
    assert empty["private_nodes"] == 0 and empty["private_edges"] == 0
    assert "private_nodes" in empty and "private_edges" in empty

    public_only = BusinessGraph()
    public_only.add_node(Node(node_id="a", kind=ASSUMPTION, label="l",
                              source="s"))
    report = assert_graph_invariants(public_only)
    assert report["private_nodes"] == 0
    assert report["unsupported_assumptions"] == ["a"]
    # No private node id ever reaches the report: a count is not a disclosure,
    # an id is.
    assert world.a_seg.node_id not in json.dumps(populated)


def test_the_inventory_names_every_kind_including_the_absent_ones(world):
    inventory = P.private_inventory(world.graph, scope=world.a)
    assert set(inventory["nodes"]) == P.PRIVATE_NODE_KINDS
    assert set(inventory["edges"]) == P.PRIVATE_EDGE_KINDS
    assert inventory["nodes"][P.CUSTOMER_SEGMENT] == 1
    assert inventory["nodes"][P.COHORT] == 0          # absent, and it SAYS so
    assert inventory["edges"][P.SEGMENT_BUYS_PRODUCT] == 1
    assert inventory["edges"][P.OUTCOME_RESOLVES_DECISION] == 0
    assert inventory["scope_state"] == SCOPED

    # A scopeless inventory reports the public view honestly: every private
    # count zero, and `withheld` carrying the true total rather than nothing.
    scopeless = P.private_inventory(world.graph)
    assert set(scopeless["nodes"].values()) == {0}
    assert scopeless["withheld"] == 4
    assert scopeless["scope_state"] == SCOPELESS_PUBLIC_ONLY
    assert scopeless["public_nodes"] == 1

    # NEGATIVE CONTROL for `refused`: it counts, and it can count above zero.
    assert inventory["refused"] == 0
    class Untagged(Node, TenantOwned):
        pass
    world.graph._nodes["stray"] = Untagged(node_id="stray", kind=COMPANY,
                                           label="?", source="x")
    assert P.private_inventory(world.graph, scope=world.a)["refused"] == 1


def test_the_read_decision_vocabulary_is_exercised_in_all_three_states(world):
    """SHOWN / WITHHELD / REFUSED. A three-valued answer that only ever
    returns two of its values is a two-valued answer with extra documentation.
    """
    public = world.graph.node("company:acme")
    assert read_decision(public, None) == SHOWN
    assert read_decision(world.a_seg, world.a) == SHOWN
    assert read_decision(world.a_seg, None) == WITHHELD
    assert read_decision(world.a_seg, world.b) == WITHHELD

    class Untagged(Node, TenantOwned):
        pass
    assert read_decision(Untagged(node_id="s", kind=COMPANY, label="?",
                                  source="x"), world.a) == REFUSED


def test_read_scope_separates_none_from_a_bad_scope(world):
    assert read_scope(None) is None
    assert read_scope(world.a) is world.a
    with pytest.raises(ScopeRefused) as exc:
        read_scope("tnt_bogus")
    assert exc.value.failure_state == STRING_REFUSED
    for hostile in (42, object(), world.a.tenant, ["scope"]):
        with pytest.raises(ScopeRefused) as exc:
            read_scope(hostile)
        assert exc.value.failure_state == NO_ESTABLISHMENT_SOURCE


def test_a_graph_read_reports_which_empty_it_is(world):
    assert GraphRead().empty_state() == EMPTY_NO_ROWS
    assert GraphRead(withheld_private=2).empty_state() == EMPTY_PRIVATE_WITHHELD
    assert GraphRead(refused=("x",)).empty_state() == EMPTY_UNTAGGED_REFUSED
    assert GraphRead(nodes=(world.a_seg,)).empty_state() == NON_EMPTY
    # Withheld outranks refused, and rows outrank both: the states are ordered
    # so the most informative true thing is what gets reported.
    assert GraphRead(withheld_private=1,
                     refused=("x",)).empty_state() == EMPTY_PRIVATE_WITHHELD


def test_a_private_node_has_no_serialization_that_loses_its_owner(world):
    """`Node.as_dict` returns an UNTAGGED row, which is the shape every reader
    treats as public. Anything serializing nodes generically would therefore
    have emitted a private node as a public one, and nothing about the result
    would have looked wrong."""
    for thing in (world.a_seg, world.graph.read(scope=world.a).edges[0]):
        row = thing.as_dict()
        assert row == thing.as_row()
        assert row["visibility"] == TENANT_PRIVATE
        assert row["tenant_id"] == world.a.tenant.value
    # NEGATIVE CONTROL: a genuinely public node still serializes as before,
    # so the override is about privacy and not about changing every row.
    public = world.graph.node("company:acme").as_dict()
    assert "tenant_id" not in public and public["kind"] == COMPANY


def test_the_remaining_refusals_each_have_a_test(world, audit):
    """The guards that no other test happens to walk through.

    Grouped rather than spread out because each is one line of behaviour, but
    present rather than omitted: an unexercised refusal is a refusal nobody
    has confirmed exists.
    """
    # a live object of the wrong tenant, handed straight to the coercer
    with pytest.raises(PrivateGraphRefused) as exc:
        P.coerce_private_node(world.a_seg, scope=world.b)
    assert exc.value.failure_state == CROSS_TENANT
    edge = world.graph.read(scope=world.a).edges[0]
    with pytest.raises(PrivateGraphRefused) as exc:
        P.coerce_private_edge(edge, scope=world.b)
    assert exc.value.failure_state == CROSS_TENANT
    # a persisted EDGE row of the wrong tenant
    with pytest.raises(PrivateGraphRefused) as exc:
        P.PrivateEdge.from_row(edge.as_row(), scope=world.b)
    assert exc.value.failure_state == CROSS_TENANT
    # a row that is not a mapping at all
    with pytest.raises(PrivateGraphRefused) as exc:
        P.PrivateNode.from_row(42, scope=world.a)
    assert exc.value.failure_state == MISSING_REQUIRED_FIELD
    # a tenant field replaced with a company name never reaches a comparison
    forged = dict(world.a_seg.as_row(), tenant_id="Acme Corp")
    forged["tenant_binding"] = P._binding(
        forged, unbound=P.PrivateNode.UNBOUND_KEYS)
    with pytest.raises(ScopeRefused) as exc:
        P.PrivateNode.from_row(forged, scope=world.a)
    assert exc.value.failure_state == STRING_REFUSED
    # a local id containing the separator would make the prefix ambiguous
    with pytest.raises(GraphError, match="separates the tenant prefix"):
        _node(world.a, local_id="seg" + P.NODE_ID_SEPARATOR + "ent")
    # attributes that cannot survive a file fail where the mistake was made
    with pytest.raises(GraphError, match="JSON-serializable"):
        _node(world.a, local_id="unserializable", attrs={"when": object()})
    # a cache key with no view names nothing
    with pytest.raises(GraphError, match="view name"):
        P.graph_cache_key(view="", scope=world.a)
    # there is no scopeless read of a private row
    with pytest.raises(ScopeRefused) as exc:
        P.PrivateNode.from_row(world.a_seg.as_row(), scope=None)
    assert exc.value.failure_state == NO_ESTABLISHMENT_SOURCE
    # a private edge built with a name where an owner belongs
    with pytest.raises(ScopeRefused) as exc:
        P.PrivateEdge(src="a", dst="b", kind=P.SEGMENT_BUYS_PRODUCT,
                      derived=True, tenant="acme")
    assert exc.value.failure_state == STRING_REFUSED
    # NEGATIVE CONTROL: each of those calls has a form that works.
    assert P.coerce_private_node(world.a_seg, scope=world.a) == world.a_seg
    assert P.PrivateEdge.from_row(edge.as_row(), scope=world.a) == edge
    assert P.graph_cache_key(view="v", scope=world.a)
    assert _node(world.a, local_id="fine", attrs={"n": 1}).attrs == {"n": 1}


# =============================================================================
# The reader guard, used by two tests above
# =============================================================================
SCOPED_READERS = ("read", "node", "of_kind", "out_edges", "in_edges",
                  "neighbours", "provenance_of", "unsupported", "contested")


def _readers_that_do_not_default_to_public(cls) -> tuple:
    """Every reader whose `scope` is missing, non-None by default, or
    positional. Empty tuple is the pass.

    Reads live signatures. The failure this prevents is not hypothetical: a
    reader that defaults `scope` to anything other than None makes PRIVATE the
    thing a caller gets by forgetting.
    """
    violations = []
    for name in SCOPED_READERS:
        fn = getattr(cls, name, None)
        if fn is None:
            violations.append(f"{name}: absent")
            continue
        params = inspect.signature(fn).parameters
        if "scope" not in params:
            violations.append(f"{name}: no scope parameter")
            continue
        param = params["scope"]
        if param.default is not None:
            violations.append(
                f"{name}: scope defaults to {param.default!r}, not None")
        elif param.kind is not inspect.Parameter.KEYWORD_ONLY:
            violations.append(f"{name}: scope is not keyword-only")
    return tuple(violations)
