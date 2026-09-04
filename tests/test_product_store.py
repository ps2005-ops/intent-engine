"""T020 store, identity, and folded lifecycle.

Append-only discipline, idempotency, stable ids, loud corruption,
concurrency, and the lifecycle rules that let nothing skip a step.
0 model calls. 0 network.
"""
import json
import threading

import pytest

from intent_engine.product import ProductError, ProductService, ProductStore
from intent_engine.product.records import ProductEvent
from intent_engine.product.state import fold_product
from intent_engine.product.store import ProductCorruptLogError

AS_OF = "2026-07-21T00:00:00+00:00"
REF = [{"kind": "crm_fact", "ref_id": "crm.churned:E1", "crm_entity_id": "E1"}]


@pytest.fixture()
def svc(tmp_path):
    return ProductService(tmp_path / "product.jsonl")


def _problem(svc, statement="Users abandon setup before first value"):
    return svc.record_problem(
        statement=statement, evidence_references=REF,
        why_now="the facts are current in the ledger",
        what_changes_if_ignored="the pattern repeats at a higher cost",
        first_observed_at=AS_OF, affected_customers=["E1"])


# =============================================================================
# Append-only + identity
# =============================================================================

def test_store_has_no_mutation_api(tmp_path):
    store = ProductStore(tmp_path / "product.jsonl")
    for banned in ("update", "delete", "remove", "overwrite", "set_", "edit"):
        assert not [m for m in dir(store)
                    if banned in m.lower() and not m.startswith("_")]


def test_append_is_additive_and_ordered(svc):
    first = _problem(svc)["problem_id"]
    second = _problem(svc, "Signup emails bounce for one domain")["problem_id"]
    rows = svc.store.read_all()
    assert [r.event_type for r in rows] == ["product.problem_recorded"] * 2
    assert [r.problem_id for r in rows] == [first, second]


def test_idempotent_retry_returns_the_same_row_and_id(svc):
    first = _problem(svc)
    again = _problem(svc)
    assert again["reused"] is True
    assert again["problem_id"] == first["problem_id"]
    assert len(svc.store.read_all()) == 1


def test_stable_id_survives_a_retry_of_the_same_key(svc):
    problem = _problem(svc)["problem_id"]
    first = svc.register_opportunity(problem, title="A guided walkthrough",
                                     evidence_references=REF)
    second = svc.register_opportunity(problem, title="A guided walkthrough",
                                      evidence_references=REF)
    assert first == second
    assert len([r for r in svc.store.read_all()
                if r.event_type == "product.opportunity_registered"]) == 1


def test_same_idempotency_key_with_different_content_is_refused(svc):
    problem = _problem(svc)["problem_id"]
    svc.register_opportunity(problem, title="A guided walkthrough",
                             evidence_references=REF)
    with pytest.raises(ValueError, match="already used for different content"):
        svc._record("product.opportunity_registered", actor_type="agent",
                    actor_id="product_agent", problem_id=problem,
                    opportunity_id="X", subject_type="opportunity",
                    subject_id="X",
                    payload={"title": "A guided walkthrough",
                             "evidence_references": REF, "different": True},
                    idempotency_key=f"opportunity:{problem}:A guided walkthrough")


def test_corrupt_log_fails_loudly(svc, tmp_path):
    """Corruption is still loud -- but only where dropping it would LOSE
    history.

    A malformed line with good records AFTER it is interior corruption of a
    file that is only ever appended to: the damage is unbounded and refusing
    to read is right. A malformed line with nothing readable after it is a
    torn TAIL -- a write killed part-way, which on the deployed preview
    bricked every request for hours because one bad byte made the whole log
    unreadable. That case is repaired and recorded, not refused.
    """
    _problem(svc)
    path = tmp_path / "product.jsonl"
    path.write_text("{not json\n" + path.read_text())   # interior
    with pytest.raises(ProductCorruptLogError, match="malformed"):
        ProductStore(path).read_all()


def test_a_torn_tail_is_recovered_rather_than_bricking_the_log(svc, tmp_path):
    _problem(svc)
    path = tmp_path / "product.jsonl"
    before = len(ProductStore(path).read_all())
    path.write_text(path.read_text() + "{not json\n")   # tail
    assert len(ProductStore(path).read_all()) == before


def test_a_future_schema_version_is_refused_rather_than_guessed_at(tmp_path):
    path = tmp_path / "product.jsonl"
    row = json.loads(ProductEvent(
        event_type="product.problem_recorded", actor_type="agent",
        actor_id="a", source="cli").to_json())
    row["schema_version"] = 99
    path.write_text(json.dumps(row) + "\n")
    with pytest.raises(ProductError, match="schema v99"):
        ProductStore(path).read_all()


def test_concurrent_appends_all_survive(tmp_path):
    store = ProductStore(tmp_path / "product.jsonl")

    def _append(n):
        store.append(ProductEvent(
            event_type="product.intake_scanned", actor_type="system",
            actor_id="t", source="intake", subject_type="opportunity",
            subject_id=f"O{n}", payload={"n": n},
            idempotency_key=f"k{n}"))

    threads = [threading.Thread(target=_append, args=(n,)) for n in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    rows = ProductStore(tmp_path / "product.jsonl").read_all()
    assert sorted(r.payload["n"] for r in rows) == list(range(12))


def test_parse_cache_is_keyed_on_mtime_and_size(svc, tmp_path):
    _problem(svc)
    store = ProductStore(tmp_path / "product.jsonl")
    assert len(store.read_all()) == 1
    assert store._cache_key is not None
    svc.register_opportunity(svc.get_state().problems and
                             list(svc.get_state().problems)[0],
                             title="A walkthrough", evidence_references=REF)
    assert len(store.read_all()) == 2      # cache invalidated by the new write


def test_tampered_history_raises_on_fold(svc, tmp_path):
    problem = _problem(svc)["problem_id"]
    svc.register_opportunity(problem, title="A walkthrough",
                             evidence_references=REF)
    path = tmp_path / "product.jsonl"
    lines = path.read_text().splitlines()
    # Remove the problem, leaving the opportunity that depended on it.
    path.write_text(lines[1] + "\n")
    with pytest.raises(ProductError, match="stored product history is invalid"):
        ProductService(path).get_state()


# =============================================================================
# Folded lifecycle
# =============================================================================

def test_fold_reproduces_state_from_rows_alone(svc):
    problem = _problem(svc)["problem_id"]
    opportunity = svc.register_opportunity(problem, title="A walkthrough",
                                           evidence_references=REF)
    folded = fold_product(svc.store.read_all())
    assert folded.problems[problem]["state"] == "active"
    assert folded.opportunities[opportunity]["problem_id"] == problem


def test_a_solution_recorded_before_its_problem_is_rejected(svc):
    with pytest.raises(ProductError, match="requires a recorded problem"):
        svc._record("product.opportunity_registered", actor_type="agent",
                    actor_id="a", problem_id="NOPE", opportunity_id="O1",
                    subject_type="opportunity", subject_id="O1",
                    payload={"title": "t", "evidence_references": REF})


def test_a_proposal_requires_an_indexed_opportunity(svc):
    with pytest.raises(ProductError, match="requires an indexed opportunity"):
        svc.draft_proposal(
            "NOPE", candidate_solution="do a thing", tradeoffs=["t"],
            risks=["r"], known=["k"], unknown=["u"], assumptions=["a"])


def test_human_only_events_refuse_an_agent_actor(svc):
    problem = _problem(svc)["problem_id"]
    with pytest.raises(ProductError, match="human wall transition"):
        svc.retire_problem(problem, reason="obsolete", actor_id="bot",
                           actor_type="agent")


def test_portfolio_and_theme_ordering_is_enforced(svc):
    with pytest.raises(ProductError, match="existing portfolio"):
        svc._record("product.theme_declared", actor_type="human",
                    actor_id="founder", portfolio_id="NOPE", theme_id="T1",
                    subject_type="theme", subject_id="T1",
                    payload={"name": "x"})


def test_an_initiative_requires_an_existing_theme(svc):
    with pytest.raises(ProductError, match="no such strategic theme"):
        svc.create_initiative("NOPE", "Onboarding", actor_id="founder")
