"""F-TS-001 — TenantScope is issued, never inferred.

The guards in here read the CLASS, not the source text. A previous structural
guard in this program grepped for a forbidden name and matched the comment
explaining its removal, so it passed while the thing existed. Every guard below
therefore inspects live objects, and every guard has a test that PROVES it goes
red when the thing it forbids is added — a guard that has never failed is a
guard nobody has tested.
"""
from __future__ import annotations

import inspect
import json
import types
from datetime import datetime, timedelta, timezone

import pytest

from intent_engine.core import tenant as tenant_mod
from intent_engine.core.tenant import (
    EMPTY_NO_ROWS, EMPTY_PRIVATE_WITHHELD, EMPTY_UNTAGGED_REFUSED, EXPIRED,
    FAILURE_STATES, NO_ESTABLISHMENT_SOURCE, NON_EMPTY, PUBLIC, SCOPED,
    SCOPELESS_PUBLIC_ONLY, SECURITY_SEAMS, SOURCE_AUTHENTICATED_SESSION,
    SOURCE_SYNTHETIC_FIXTURE, STRING_REFUSED, TENANT_PRIVATE,
    TENANT_SCOPE_CONTRACT, TRUSTED_ESTABLISHMENT_SOURCES, ScopeAuditLog,
    ScopeRefused, TenantId, TenantScope, assert_no_evidence_constructors,
    coerce_scope, establish, export_partition, partition_path,
    requires_tenant_scope, scope_cache_key, scope_producers, visible_rows,
)

FIXED_ULID = "01J9ZZZZZZZZZZZZZZZZZZZZZZ"


@pytest.fixture
def audit(tmp_path) -> ScopeAuditLog:
    """Always a tmp path: an import-time default under data/ would let the
    suite write into the repo's real audit log."""
    return ScopeAuditLog(tmp_path / "tenant_scope_audit.jsonl")


def _scope(audit, *, label: str = "", capabilities=(), expires_at=None,
           tenant=None) -> TenantScope:
    return establish(tenant=tenant or TenantId.mint(),
                     establishment_source=SOURCE_AUTHENTICATED_SESSION,
                     display_label=label, capabilities=capabilities,
                     expires_at=expires_at, audit=audit)


# =============================================================================
# 1. A bare string is not an identity
# =============================================================================
def test_tenant_scope_cannot_be_constructed_from_a_bare_string(audit):
    with pytest.raises(ScopeRefused) as exc:
        TenantScope("acme")
    assert exc.value.failure_state == STRING_REFUSED

    # And the same refusal through the entry point, which also audits it.
    with pytest.raises(ScopeRefused) as exc:
        establish(tenant="acme",
                  establishment_source=SOURCE_AUTHENTICATED_SESSION,
                  audit=audit)
    assert exc.value.failure_state == STRING_REFUSED
    assert [r.failure_state for r in audit.refusals()] == [STRING_REFUSED]

    # NEGATIVE CONTROL: the same call with a typed identity succeeds, so the
    # refusal above is about the string and not about a broken constructor.
    assert isinstance(_scope(audit), TenantScope)


def test_direct_construction_is_refused_even_with_a_typed_identity():
    """establish() is the only entry point because it is what writes the
    audit row; a scope with no audit row is unaccountable authority."""
    with pytest.raises(ScopeRefused) as exc:
        TenantScope(tenant=TenantId.mint(),
                    establishment_source=SOURCE_AUTHENTICATED_SESSION,
                    issued_at="2026-08-10T00:00:00+00:00",
                    scope_id=FIXED_ULID)
    assert exc.value.failure_state == NO_ESTABLISHMENT_SOURCE


def test_a_company_name_can_never_become_a_tenant_identity():
    for hostile in ("acme", "Acme Corp", "acme.com", "Linear",
                    "tnt_acme", "", "../etc", "tnt_" + "a" * 26):
        with pytest.raises(ScopeRefused) as exc:
            TenantId(hostile)
        assert exc.value.failure_state == STRING_REFUSED
    # NEGATIVE CONTROL: a control-plane identity is accepted.
    assert TenantId.mint().value.startswith("tnt_")


def test_only_a_trusted_context_may_establish_authority(audit):
    for source in ("evidence", "scraped_page", "model_output", "company_name",
                   "", "web_page"):
        with pytest.raises(ScopeRefused) as exc:
            establish(tenant=TenantId.mint(), establishment_source=source,
                      audit=audit)
        assert exc.value.failure_state == NO_ESTABLISHMENT_SOURCE
    assert len(audit.refusals()) == 6
    # NEGATIVE CONTROL: every trusted source really does work.
    for source in sorted(TRUSTED_ESTABLISHMENT_SOURCES):
        assert establish(tenant=TenantId.mint(), establishment_source=source,
                         audit=audit).establishment_source == source


# =============================================================================
# 2. The from_evidence guards — three nets, each proven to fail
# =============================================================================
# The primary guard: the EXACT attribute set. It does not care what a new
# constructor is called or whether it is annotated.
EXPECTED_SCOPE_ATTRS = frozenset({
    # fields
    "tenant", "establishment_source", "issued_at", "expires_at",
    "capabilities", "display_label", "scope_id", "_established_by",
    # behaviour
    "authorizes", "permits", "is_expired", "assert_live", "as_row", "from_row",
})
EXPECTED_TENANT_ID_ATTRS = frozenset({"value", "mint"})

# Everything defined in the module itself (imports excluded by __module__).
EXPECTED_MODULE_DEFINITIONS = frozenset({
    # classes
    "ScopeRefused", "TenantId", "TenantScope", "ScopedRead", "ScopeAuditEvent",
    "ScopeAuditLog", "TenantScoped", "SeamRegistry",
    # functions
    "_now", "_now_iso", "_parse_iso", "coerce_scope", "_default_audit_log",
    "establish", "_probe_kwargs", "requires_tenant_scope", "visible_rows",
    "export_partition", "partition_path", "scope_cache_key",
    "_return_annotation", "scope_producers", "assert_no_evidence_constructors",
})


def _own_attrs(cls) -> frozenset:
    """Non-dunder names the class itself defines."""
    return frozenset(
        n for n in vars(cls)
        if not (n.startswith("__") and n.endswith("__")))


def _module_definitions() -> frozenset:
    found = set()
    for name, obj in vars(tenant_mod).items():
        if name.startswith("__") and name.endswith("__"):
            continue
        if getattr(obj, "__module__", None) != tenant_mod.__name__:
            continue
        if inspect.isfunction(obj) or inspect.isclass(obj):
            found.add(name)
    return frozenset(found)


def _assert_attribute_sets_are_exact() -> None:
    """The guard itself, so the negative-control tests can call it."""
    assert _own_attrs(TenantScope) == EXPECTED_SCOPE_ATTRS
    assert _own_attrs(TenantId) == EXPECTED_TENANT_ID_ATTRS
    assert _module_definitions() == EXPECTED_MODULE_DEFINITIONS


def test_no_evidence_derived_constructor_exists_by_attribute_set():
    """THE assertion. `from_evidence` is absent because the attribute set of
    TenantScope is exactly this and nothing else."""
    _assert_attribute_sets_are_exact()
    assert "from_evidence" not in _own_attrs(TenantScope)
    assert "from_evidence" not in _module_definitions()


def test_the_attribute_set_guard_fails_when_such_a_method_is_added():
    """Proof the guard above can go red. Without this, the guard is a claim."""
    def from_evidence(cls, scraped_text):  # pragma: no cover - never called
        raise AssertionError("this must never be reachable")

    setattr(TenantScope, "from_evidence", classmethod(from_evidence))
    try:
        with pytest.raises(AssertionError):
            _assert_attribute_sets_are_exact()
    finally:
        delattr(TenantScope, "from_evidence")
    _assert_attribute_sets_are_exact()  # clean again


def test_the_attribute_set_guard_fails_on_a_module_level_constructor():
    def from_evidence(scraped_text):  # pragma: no cover - never called
        raise AssertionError("this must never be reachable")

    setattr(tenant_mod, "from_evidence", from_evidence)
    from_evidence.__module__ = tenant_mod.__name__
    try:
        with pytest.raises(AssertionError):
            _assert_attribute_sets_are_exact()
    finally:
        delattr(tenant_mod, "from_evidence")
    _assert_attribute_sets_are_exact()


def test_scope_producers_net_catches_a_renamed_constructor():
    """Net 2: reads the declared return type, so a rename does not help."""
    assert scope_producers() == frozenset({
        "establish", "coerce_scope", "TenantScope.from_row", "TenantId.mint"})
    assert_no_evidence_constructors()

    def hydrate(scraped_text) -> "TenantScope":  # pragma: no cover
        raise AssertionError("never reachable")

    hydrate.__annotations__["return"] = "TenantScope"
    setattr(tenant_mod, "hydrate", hydrate)
    try:
        assert "hydrate" in scope_producers()
        with pytest.raises(AssertionError, match="allowlist"):
            assert_no_evidence_constructors()
    finally:
        delattr(tenant_mod, "hydrate")
    assert_no_evidence_constructors()


def test_name_token_net_catches_an_unannotated_evidence_constructor():
    """Net 3: an unannotated `from_evidence` escapes net 2 and is caught here."""
    def from_evidence(cls, text):  # pragma: no cover - never called
        raise AssertionError("never reachable")

    setattr(TenantScope, "from_evidence", classmethod(from_evidence))
    try:
        assert "TenantScope.from_evidence" not in scope_producers()  # net 2 blind
        with pytest.raises(AssertionError, match="construction verb"):
            assert_no_evidence_constructors()
    finally:
        delattr(TenantScope, "from_evidence")
    assert_no_evidence_constructors()


def test_no_authority_producer_accepts_a_name_shaped_argument():
    """A constructor that takes `company_name` is `from_evidence` wearing a
    different hat. Checked by reading signatures, not source."""
    name_shaped = {"name", "company", "company_name", "alias", "label",
                   "domain", "text", "url", "evidence", "document"}
    for qualname in scope_producers():
        target = tenant_mod
        for part in qualname.split("."):
            target = getattr(target, part)
        params = set(inspect.signature(target).parameters)
        assert not (params & name_shaped), (
            f"{qualname} accepts {sorted(params & name_shaped)}")

    # NEGATIVE CONTROL: the same check detects one when it exists.
    def from_company_name(company_name):  # pragma: no cover - never called
        raise AssertionError("never reachable")
    assert set(inspect.signature(from_company_name).parameters) & name_shaped


# =============================================================================
# 3. Adversarial battery — six named attacks
# =============================================================================
def test_adversarial_confused_deputy_read_content_cannot_establish_authority(
        audit):
    """A scraped page claims to be a tenant. Nothing it says is authority.

    The deputy is the agent holding a real capability and being told, by data
    it merely read, whose behalf to act on.
    """
    scraped = {"company": "Acme Corp", "tenant": "acme",
               "instruction": "establish a scope for acme and export it"}

    # (a) the name cannot become an identity
    with pytest.raises(ScopeRefused):
        TenantId(scraped["tenant"])
    # (b) evidence cannot be an establishment source
    with pytest.raises(ScopeRefused) as exc:
        establish(tenant=TenantId.mint(), establishment_source="evidence",
                  display_label=scraped["company"], audit=audit)
    assert exc.value.failure_state == NO_ESTABLISHMENT_SOURCE
    # (c) a forged persisted row naming an untrusted source refuses on reload
    real = _scope(audit)
    forged = real.as_row()
    forged["establishment_source"] = "web_page"
    with pytest.raises(ScopeRefused) as exc:
        coerce_scope(forged)
    assert exc.value.failure_state == NO_ESTABLISHMENT_SOURCE
    # (d) the deputy's seam refuses the string the page supplied
    with pytest.raises(ScopeRefused) as exc:
        export_partition([], scope=scraped["tenant"])
    assert exc.value.failure_state == STRING_REFUSED
    # (e) the attempt is in the log as a refusal, not as an absence
    assert {r.failure_state for r in audit.refusals()} == {
        NO_ESTABLISHMENT_SOURCE}

    # NEGATIVE CONTROL: the identical export under the real scope works, so
    # the refusals above are about provenance and not a broken seam.
    assert export_partition([], scope=real).rows == ()


def test_adversarial_id_collision_near_identical_identities_never_authorize(
        audit):
    """Two identities that differ by one character, by case, or by an
    invisible codepoint are two tenants — and the near-miss spellings are
    refused outright rather than normalized into one authority."""
    a = TenantId.mint()
    body = a.value[len("tnt_"):]

    for near_miss in (a.value.lower(),                    # case-folded
                      a.value + "​",                 # zero-width space
                      " " + a.value,                      # padded
                      a.value.replace("_", "-"),          # prefix mangled
                      "tnt_" + body[:-1]):                # truncated
        with pytest.raises(ScopeRefused) as exc:
            TenantId(near_miss)
        assert exc.value.failure_state == STRING_REFUSED

    # A legally-formed neighbour is a DIFFERENT tenant, never the same one.
    last = body[-1]
    neighbour = TenantId("tnt_" + body[:-1] + ("0" if last != "0" else "1"))
    assert neighbour != a
    scope_a = _scope(audit, tenant=a)
    assert scope_a.authorizes(neighbour) is False
    # NEGATIVE CONTROL: it authorizes its own identity, so False above means
    # "different tenant" and not "authorizes() always says no".
    assert scope_a.authorizes(a) is True
    assert scope_a.authorizes(TenantId(a.value)) is True


def test_adversarial_alias_collision_linear_is_not_linear_minerals_corp(audit):
    """The real incident: the alias "Linear" was satisfied by "Linear Minerals
    Corp." A label is never authority here — it is excluded from equality,
    from the cache key and from the storage partition."""
    linear = _scope(audit, label="Linear")
    minerals = _scope(audit, label="Linear Minerals Corp.")

    assert minerals.display_label.startswith(linear.display_label)  # the trap
    assert minerals.authorizes(linear.tenant) is False
    assert linear.authorizes(minerals.tenant) is False
    assert scope_cache_key(linear) != scope_cache_key(minerals)
    assert linear.display_label not in scope_cache_key(linear)

    # The label is not part of identity: the same row under two labels is the
    # same authority, so nobody can gain or lose access by being renamed.
    row = linear.as_row()
    relabelled = dict(row, display_label="Something Else Entirely")
    assert coerce_scope(row) == coerce_scope(relabelled)

    # A name cannot be compared against at all -- it raises rather than
    # quietly returning False, so a caller reaching for the old habit is told.
    with pytest.raises(ScopeRefused) as exc:
        minerals.authorizes("Linear")
    assert exc.value.failure_state == STRING_REFUSED

    # NEGATIVE CONTROL: substring matching, the thing being refused, really
    # would have collided on this data.
    assert "Linear" in minerals.display_label


def test_adversarial_cache_collision_two_tenants_never_share_a_cache_key(audit):
    a = _scope(audit, label="Linear")
    b = _scope(audit, label="Linear Minerals Corp.")
    a_again = _scope(audit, tenant=a.tenant, label="Linear")

    assert scope_cache_key(a) != scope_cache_key(b)
    # Two scopes for the SAME tenant share a key, or the cache is useless.
    assert scope_cache_key(a) == scope_cache_key(a_again)
    assert a.scope_id != a_again.scope_id

    cache = {}
    cache[scope_cache_key(a)] = ["a-private-row"]
    assert scope_cache_key(b) not in cache

    # NEGATIVE CONTROL: a label-keyed cache -- the plausible wrong design --
    # demonstrably serves one tenant the other's rows on this same data.
    naive = {}
    naive[a.display_label[:6]] = ["a-private-row"]
    assert naive.get(b.display_label[:6]) == ["a-private-row"]

    with pytest.raises(ScopeRefused):
        scope_cache_key("Linear")


def test_adversarial_file_path_collision_partition_cannot_escape_its_root(
        tmp_path, audit):
    root = tmp_path / "tenants"
    root.mkdir()
    a = _scope(audit, label="Linear")
    b = _scope(audit, label="Linear Minerals Corp.")

    pa, pb = partition_path(root, scope=a), partition_path(root, scope=b)
    assert pa != pb
    assert root.resolve() in pa.parents and root.resolve() in pb.parents
    # The partition is the opaque identity, so two similarly-labelled tenants
    # never share a directory and no label ever reaches the filesystem.
    assert "Linear" not in str(pa) and "Linear" not in str(pb)

    # Traversal cannot even be spelled: it is refused at the identity.
    for traversal in ("../../etc/passwd", "..", "a/b", "tnt_../x", "."):
        with pytest.raises(ScopeRefused):
            TenantId(traversal)

    # NEGATIVE CONTROL: the escape is real if the partition is built from a
    # label instead of an identity -- which is why it is built from identity.
    escaped = (root / "../../etc").resolve()
    assert root.resolve() not in escaped.parents

    with pytest.raises(ScopeRefused):
        partition_path(root, scope="acme")


def test_adversarial_export_collision_an_export_carries_only_its_own_rows(
        audit):
    a, b = _scope(audit), _scope(audit)
    rows = [
        {"visibility": PUBLIC, "id": "p1"},
        {"visibility": TENANT_PRIVATE, "tenant_id": a.tenant.value, "id": "a1"},
        {"visibility": TENANT_PRIVATE, "tenant_id": b.tenant.value, "id": "b1"},
        {"id": "untagged"},                       # no visibility at all
    ]

    got_a = export_partition(rows, scope=a)
    assert [r["id"] for r in got_a.rows] == ["p1", "a1"]
    assert got_a.withheld_private == 1        # b1 -- counted, not vanished
    assert got_a.refused == (3,)              # untagged -- never assumed public
    assert got_a.scope_state == SCOPED

    # NEGATIVE CONTROL: B's export really does contain B's row, so A's export
    # excluding it is a boundary and not an empty reader.
    got_b = export_partition(rows, scope=b)
    assert [r["id"] for r in got_b.rows] == ["p1", "b1"]

    # Mutating the exported copy cannot reach the store's row.
    got_a.rows[1]["id"] = "tampered"
    assert rows[1]["id"] == "a1"

    with pytest.raises(ScopeRefused) as exc:
        export_partition(rows, scope=a.tenant.value)
    assert exc.value.failure_state == STRING_REFUSED


# =============================================================================
# 4. The seam: a bare string can never reach a security-sensitive body
# =============================================================================
def test_suite_guard_no_registered_seam_accepts_a_bare_string():
    """The suite-level guard. It probes every registered seam in the process
    and must find nothing."""
    assert SECURITY_SEAMS.audit() == ()
    assert len(SECURITY_SEAMS) >= 2  # export_partition, partition_path


def test_the_seam_guard_fires_on_a_seam_that_does_not_refuse():
    """Proof the guard can go red — two different ways to get it wrong."""
    def undecorated(rows, *, scope):  # pragma: no cover - never runs a body
        return "leaked"

    violations = SECURITY_SEAMS.audit(seams=[undecorated])
    assert len(violations) == 1 and "not wrapped" in violations[0]

    def marked_but_permissive(rows, *, scope):
        return "leaked"
    marked_but_permissive.__tenant_seam__ = True

    violations = SECURITY_SEAMS.audit(seams=[marked_but_permissive])
    assert len(violations) == 1 and "ACCEPTED a bare string" in violations[0]

    # And the guard finds it through the real registry too, not only when the
    # seams are handed to it.
    SECURITY_SEAMS.register(marked_but_permissive)
    try:
        assert any("ACCEPTED" in v for v in SECURITY_SEAMS.audit())
    finally:
        SECURITY_SEAMS.discard(marked_but_permissive)
    assert SECURITY_SEAMS.audit() == ()


def test_the_guard_probes_every_seam_signature_shape_without_false_alarms():
    """A guard that reports a correct seam as broken gets switched off.

    The shapes that break a naive positional probe: `scope` first, `scope`
    keyword-only, extra required parameters, *args/**kwargs.
    """
    @requires_tenant_scope
    def scope_first(scope, rows):        # pragma: no cover - body never runs
        return rows

    @requires_tenant_scope
    def many_params(a, b, *args, scope, c=1, **kwargs):  # pragma: no cover
        return a

    try:
        assert SECURITY_SEAMS.audit() == ()
    finally:
        SECURITY_SEAMS.discard(scope_first)
        SECURITY_SEAMS.discard(many_params)

    # A seam whose scope cannot be passed by keyword is reported rather than
    # silently skipped: unauditable is a violation, not a pass.
    def positional_only(rows, scope, /):  # noqa: E999 - py3.8+ syntax
        return rows
    positional_only.__tenant_seam__ = True
    violations = SECURITY_SEAMS.audit(seams=[positional_only])
    assert len(violations) == 1 and "cannot probe it" in violations[0]


def test_a_bare_string_never_reaches_a_seam_body(audit):
    reached = []

    @requires_tenant_scope
    def privileged(payload, *, scope):
        reached.append(scope)
        return "private data"

    try:
        for hostile in ("acme", b"acme", None, 42, {"tenant_id": "acme"}):
            with pytest.raises(ScopeRefused) as exc:
                privileged("x", scope=hostile)
            expected = (STRING_REFUSED if isinstance(hostile, (str, bytes))
                        else NO_ESTABLISHMENT_SOURCE)
            assert exc.value.failure_state == expected
        with pytest.raises(ScopeRefused) as exc:
            privileged("x")
        assert exc.value.failure_state == NO_ESTABLISHMENT_SOURCE
        assert reached == []      # the body never ran

        # NEGATIVE CONTROL: a real scope does reach the body.
        scope = _scope(audit)
        assert privileged("x", scope=scope) == "private data"
        assert reached == [scope]
    finally:
        SECURITY_SEAMS.discard(privileged)


def test_a_seam_without_a_scope_parameter_is_refused_at_decoration():
    with pytest.raises(TypeError, match="no `scope` parameter"):
        @requires_tenant_scope
        def not_really_a_seam(payload):  # pragma: no cover - never defined
            return payload


def test_an_expired_scope_is_refused_at_the_seam_and_at_every_reader(audit):
    soon = (datetime.now(timezone.utc) + timedelta(seconds=30)).isoformat(
        timespec="seconds")
    scope = _scope(audit, expires_at=soon)
    later = datetime.now(timezone.utc) + timedelta(minutes=5)

    assert scope.is_expired() is False
    assert scope.is_expired(later) is True
    with pytest.raises(ScopeRefused) as exc:
        scope.assert_live(later)
    assert exc.value.failure_state == EXPIRED

    # A scope that reloads already expired is refused at USE, not at load --
    # the audit trail must still be readable for an expired scope.
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(
        timespec="seconds")
    stale = coerce_scope(dict(scope.as_row(), expires_at=past))
    assert stale.is_expired() is True
    for call in (lambda: export_partition([], scope=stale),
                 lambda: scope_cache_key(stale),
                 lambda: visible_rows([], scope=stale),
                 lambda: stale.authorizes(stale.tenant)):
        with pytest.raises(ScopeRefused) as exc:
            call()
        assert exc.value.failure_state == EXPIRED

    # NEGATIVE CONTROL: an unexpired scope passes all four.
    live = _scope(audit)
    assert export_partition([], scope=live).rows == ()
    assert scope_cache_key(live)
    assert visible_rows([], scope=live).rows == ()
    assert live.authorizes(live.tenant) is True


# =============================================================================
# 5. Three-shape contract — producer, persisted row, transported consumer
# =============================================================================
def test_three_shapes_agree_through_one_shared_reader(audit):
    """Live object, persisted dict row, transported DTO. One reader.

    Two readers is how a ledger of many events once folded into one record:
    a getattr-only reader silently mis-reads a mapping. `coerce_scope` reads
    mappings as mappings first, and this test drives all three shapes through
    it so a producer and a consumer cannot drift apart unnoticed.
    """
    produced = _scope(audit, label="Acme", capabilities=("read_internal",),
                      expires_at="2030-01-01T00:00:00+00:00")

    persisted = json.loads(json.dumps(produced.as_row()))   # survives a file
    transported = types.SimpleNamespace(**persisted)        # another service

    shapes = {"live": produced, "persisted": persisted,
              "transported": transported}
    read = {name: coerce_scope(shape) for name, shape in shapes.items()}

    assert read["live"] == read["persisted"] == read["transported"]
    for name, scope in read.items():
        assert scope.tenant == produced.tenant, name
        assert scope.establishment_source == SOURCE_AUTHENTICATED_SESSION, name
        assert scope.capabilities == ("read_internal",), name
        assert scope.permits("read_internal") is True, name
        assert scope.permits("write_internal") is False, name
        assert scope_cache_key(scope) == scope_cache_key(produced), name

    # A mapping must not be read through the attribute path: a dict has no
    # `.tenant_id`, so a getattr-only reader would refuse or invent one.
    assert not hasattr(persisted, "tenant_id")


def test_a_string_is_never_reconstituted_even_when_it_is_valid_json(audit):
    scope = _scope(audit)
    payload = json.dumps(scope.as_row())
    with pytest.raises(ScopeRefused) as exc:
        coerce_scope(payload)
    assert exc.value.failure_state == STRING_REFUSED
    # NEGATIVE CONTROL: the caller decoding its own transport works.
    assert coerce_scope(json.loads(payload)) == scope


def test_missing_optional_field_reloads(audit):
    row = _scope(audit).as_row()
    row.pop("expires_at")
    row.pop("display_label")
    reloaded = coerce_scope(row)
    assert reloaded.expires_at is None and reloaded.is_expired() is False
    assert reloaded.display_label == ""


def test_empty_list_is_a_grant_of_nothing_not_a_grant_of_everything(audit):
    row = dict(_scope(audit).as_row(), capabilities=[])
    reloaded = coerce_scope(row)
    assert reloaded.capabilities == ()
    assert reloaded.permits("read_internal") is False
    # NEGATIVE CONTROL: a populated list does permit.
    assert coerce_scope(dict(row, capabilities=["read_internal"])).permits(
        "read_internal") is True


def test_explicit_null_is_distinguished_from_missing(audit):
    row = _scope(audit).as_row()
    # optional: an explicit null means "does not expire", same as absent
    assert coerce_scope(dict(row, expires_at=None)).expires_at is None
    # required: an explicit null is NOT an empty value and is refused
    for key in ("tenant_id", "establishment_source", "issued_at",
                "capabilities", "scope_id"):
        with pytest.raises(ScopeRefused, match="explicit null"):
            coerce_scope(dict(row, **{key: None}))
        with pytest.raises(ScopeRefused, match="missing required key"):
            coerce_scope({k: v for k, v in row.items() if k != key})


def test_a_stale_producer_version_is_refused_not_upgraded(audit):
    row = _scope(audit).as_row()
    assert row["contract"] == TENANT_SCOPE_CONTRACT
    for stale in ("tenant_scope.v0", "tenant_scope", None):
        with pytest.raises(ScopeRefused) as exc:
            coerce_scope(dict(row, contract=stale))
        assert exc.value.failure_state == NO_ESTABLISHMENT_SOURCE
        assert TENANT_SCOPE_CONTRACT in str(exc.value)
    with pytest.raises(ScopeRefused):
        coerce_scope({k: v for k, v in row.items() if k != "contract"})


def test_an_object_carrying_no_scope_is_refused(audit):
    for hostile in (types.SimpleNamespace(tenant_id="acme"), 42, None, [],
                    object()):
        with pytest.raises(ScopeRefused) as exc:
            coerce_scope(hostile)
        assert exc.value.failure_state == NO_ESTABLISHMENT_SOURCE


# =============================================================================
# 6. Empty state — a scopeless query returns public only, and says so
# =============================================================================
def test_a_scopeless_query_returns_public_only_and_never_silently_private(
        audit):
    scope = _scope(audit)
    rows = [
        {"visibility": PUBLIC, "id": "p1"},
        {"visibility": TENANT_PRIVATE, "tenant_id": scope.tenant.value,
         "id": "a1"},
        {"id": "untagged"},
    ]
    got = visible_rows(rows)
    assert [r["id"] for r in got.rows] == ["p1"]
    assert got.scope_state == SCOPELESS_PUBLIC_ONLY
    assert got.withheld_private == 1
    assert got.refused == (2,)
    assert got.empty_state() == NON_EMPTY

    # NEGATIVE CONTROL: with a scope, the private row is returned -- so the
    # exclusion above is authorization and not an unconditional filter.
    with_scope = visible_rows(rows, scope=scope)
    assert [r["id"] for r in with_scope.rows] == ["p1", "a1"]
    assert with_scope.scope_state == SCOPED


def test_the_three_kinds_of_empty_are_distinguishable(audit):
    scope = _scope(audit)
    other = _scope(audit)

    nothing = visible_rows([])
    assert nothing.rows == () and nothing.empty_state() == EMPTY_NO_ROWS

    withheld = visible_rows(
        [{"visibility": TENANT_PRIVATE, "tenant_id": other.tenant.value}],
        scope=scope)
    assert withheld.rows == ()
    assert withheld.empty_state() == EMPTY_PRIVATE_WITHHELD
    assert withheld.withheld_private == 1

    refused = visible_rows([{"id": "untagged"}, "not even a row"])
    assert refused.rows == ()
    assert refused.empty_state() == EMPTY_UNTAGGED_REFUSED
    assert refused.refused == (0, 1)

    # An untagged row is neither public nor private: it is refused. Treating
    # it as public is how a private row escapes the day a field is forgotten.
    assert visible_rows([{"visibility": "", "tenant_id": scope.tenant.value}],
                        scope=scope).empty_state() == EMPTY_UNTAGGED_REFUSED
    # A private row with no owner is refused rather than shown to whoever asks.
    assert visible_rows([{"visibility": TENANT_PRIVATE}],
                        scope=scope).empty_state() == EMPTY_UNTAGGED_REFUSED


def test_a_string_is_not_a_weaker_scope(audit):
    with pytest.raises(ScopeRefused) as exc:
        visible_rows([], scope="acme")
    assert exc.value.failure_state == STRING_REFUSED


# =============================================================================
# 7. Establishment is persisted and auditable
# =============================================================================
def test_establishment_is_recorded_and_reloads_in_a_fresh_reader(tmp_path):
    path = tmp_path / "audit.jsonl"
    log = ScopeAuditLog(path)
    scope = establish(tenant=TenantId.mint(),
                      establishment_source=SOURCE_SYNTHETIC_FIXTURE,
                      capabilities=("read_internal",), actor="operator:pratham",
                      display_label="Synthetic Co", audit=log)
    with pytest.raises(ScopeRefused):
        establish(tenant=TenantId.mint(), establishment_source="evidence",
                  audit=log)

    # A FRESH reader over the same file -- the write must have hit the disk,
    # not merely an in-memory list.
    reloaded = ScopeAuditLog(path)
    rows = reloaded.read_all()
    assert [r.event_type for r in rows] == ["scope.established",
                                            "scope.refused"]
    established = rows[0]
    assert established.scope_id == scope.scope_id
    assert established.tenant_id == scope.tenant.value
    assert established.establishment_source == SOURCE_SYNTHETIC_FIXTURE
    assert established.actor == "operator:pratham"
    assert reloaded.for_tenant(scope.tenant) == [established]
    assert [r.failure_state for r in reloaded.refusals()] == [
        NO_ESTABLISHMENT_SOURCE]

    # The audit log is queried by identity, never by name.
    with pytest.raises(ScopeRefused):
        reloaded.for_tenant("Synthetic Co")

    # The label is not in the audit row's identity fields either.
    assert "Synthetic Co" not in json.dumps(established.as_dict())


def test_the_default_audit_path_is_resolvable_and_actually_written(
        tmp_path, monkeypatch):
    """`establish()` with no explicit log must still land on disk.

    A write path that only exists when a test hands it a location is a write
    path production never uses. The env override is how the runtime points at
    its real store; this exercises that resolution rather than assuming it.
    """
    path = tmp_path / "default_audit.jsonl"
    monkeypatch.setenv("INTENT_ENGINE_SCOPE_AUDIT", str(path))
    scope = establish(tenant=TenantId.mint(),
                      establishment_source=SOURCE_AUTHENTICATED_SESSION)
    assert path.exists()
    assert [r.scope_id for r in ScopeAuditLog(path).read_all()] == [
        scope.scope_id]


def test_every_documented_untrusted_source_is_actually_refused(audit):
    """`NEVER_TRUSTED_SOURCES` is documentation; this makes it load-bearing.

    The rule is the allowlist, so a source nobody thought to name is refused
    anyway -- but a named source that turned out to be accepted would be a
    comment contradicting the code, which is how a guard starts lying.
    """
    for source in tenant_mod.NEVER_TRUSTED_SOURCES:
        assert source not in TRUSTED_ESTABLISHMENT_SOURCES
        with pytest.raises(ScopeRefused) as exc:
            establish(tenant=TenantId.mint(), establishment_source=source,
                      audit=audit)
        assert exc.value.failure_state == NO_ESTABLISHMENT_SOURCE
    assert len(audit.refusals()) == len(tenant_mod.NEVER_TRUSTED_SOURCES)


def test_carrying_a_scope_is_declared_not_inferred_from_shape(audit):
    """`TenantScoped` is a declaration, not a duck type.

    A lookalike with an attribute named `scope` is not scoped. Accepting one
    because it has the right shape is the alias collision again: authority
    inferred from resemblance rather than from an assertion someone made.
    """
    class InternalRow(tenant_mod.TenantScoped):
        def __init__(self, scope):
            self.scope = scope

    class LooksTheSame:
        def __init__(self, scope):
            self.scope = scope

    scope = _scope(audit)
    assert isinstance(InternalRow(scope), tenant_mod.TenantScoped)
    assert not isinstance(LooksTheSame(scope), tenant_mod.TenantScoped)
    assert hasattr(LooksTheSame(scope), "scope")   # the trap it avoids


def test_failure_states_are_a_closed_named_vocabulary():
    assert FAILURE_STATES == {NO_ESTABLISHMENT_SOURCE, STRING_REFUSED, EXPIRED}
    # A refusal with an unnamed state cannot be constructed, so telemetry can
    # never grow an uncountable bucket.
    with pytest.raises(AssertionError):
        ScopeRefused("SOMETHING_WENT_WRONG", "detail")
    for state in FAILURE_STATES:
        assert ScopeRefused(state, "detail").failure_state == state


def test_a_scope_cannot_be_repointed_after_it_is_issued(audit):
    scope = _scope(audit)
    other = TenantId.mint()
    for attr, value in (("tenant", other), ("expires_at", None),
                        ("capabilities", ("admin",))):
        with pytest.raises(Exception):
            setattr(scope, attr, value)
    assert scope.authorizes(other) is False
