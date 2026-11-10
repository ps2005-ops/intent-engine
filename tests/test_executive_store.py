"""T021 store, identity, and folded lifecycle.

Append-only discipline, idempotency, stable ids, loud corruption,
concurrency, folded state, and the lifecycle rules that let nothing skip a
step. 0 model calls. 0 network.
"""
import json
import threading

import pytest

from intent_engine.executive import (
    ExecutiveError, ExecutiveService, ExecutiveStore,
)
from intent_engine.executive.records import ExecutiveEvent
from intent_engine.executive.state import fold_executive
from intent_engine.executive.store import ExecutiveCorruptLogError

REF = [{"kind": "product_proposal", "ref_id": "P1"}]


@pytest.fixture()
def svc(tmp_path):
    return ExecutiveService(tmp_path / "executive.jsonl")


def _candidate(svc, origin_id="o1", references=None):
    return svc.register_candidate(
        references=references or REF,
        origin={"kind": "manual", "origin_id": origin_id})


# =============================================================================
# Append-only + identity
# =============================================================================

def test_store_has_no_mutation_api(tmp_path):
    store = ExecutiveStore(tmp_path / "executive.jsonl")
    for banned in ("update", "delete", "remove", "overwrite", "set_", "edit"):
        assert not [m for m in dir(store)
                    if banned in m.lower() and not m.startswith("_")]


def test_append_is_additive_and_ordered(svc):
    a = _candidate(svc, "o1")
    b = _candidate(svc, "o2")
    rows = svc.store.read_all()
    assert [r.event_type for r in rows] == ["executive.candidate_registered"] * 2
    assert [r.candidate_id for r in rows] == [a, b]


def test_idempotent_retry_returns_the_same_id(svc):
    first = _candidate(svc, "o1")
    second = _candidate(svc, "o1")
    assert first == second
    assert len(svc.store.read_all()) == 1


def test_stable_id_survives_a_retry(svc):
    candidate = _candidate(svc, "o1")
    facts = {"research": {"stances": ["SUPPORTED"]}}
    svc.record_conflicts(candidate, facts)
    svc.record_conflicts(candidate, facts)     # replay
    conflicts = [r for r in svc.store.read_all()
                 if r.event_type == "executive.conflict_detected"]
    ids = {r.conflict_id for r in conflicts}
    assert len(conflicts) == len(ids)          # no duplicate ids


def test_same_key_different_content_is_refused(svc):
    _candidate(svc, "o1")
    with pytest.raises(ValueError, match="already used for different content"):
        svc._record("executive.candidate_registered", actor_type="agent",
                    actor_id="a", candidate_id="X", subject_type="candidate",
                    subject_id="X",
                    payload={"references": REF, "extra": True},
                    idempotency_key="candidate:manual:o1")


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
    _candidate(svc, "o1")
    path = tmp_path / "executive.jsonl"
    good = path.read_text()
    path.write_text("{not json\n" + good)          # interior: records follow
    with pytest.raises(ExecutiveCorruptLogError, match="malformed"):
        ExecutiveStore(path).read_all()


def test_a_torn_tail_is_recovered_rather_than_bricking_the_log(svc, tmp_path):
    _candidate(svc, "o1")
    path = tmp_path / "executive.jsonl"
    before = len(ExecutiveStore(path).read_all())
    path.write_text(path.read_text() + "{not json\n")   # tail: nothing after
    assert len(ExecutiveStore(path).read_all()) == before


def test_a_future_schema_version_is_refused(tmp_path):
    path = tmp_path / "executive.jsonl"
    row = json.loads(ExecutiveEvent(
        event_type="executive.candidate_registered", actor_type="agent",
        actor_id="a", source="cli").to_json())
    row["schema_version"] = 99
    path.write_text(json.dumps(row) + "\n")
    with pytest.raises(ExecutiveError, match="schema v99"):
        ExecutiveStore(path).read_all()


def test_concurrent_appends_all_survive(tmp_path):
    store = ExecutiveStore(tmp_path / "executive.jsonl")

    def _append(n):
        store.append(ExecutiveEvent(
            event_type="executive.intake_scanned", actor_type="system",
            actor_id="t", source="intake", candidate_id=f"C{n}",
            subject_type="candidate", subject_id=f"C{n}",
            payload={"n": n}, idempotency_key=f"k{n}"))

    threads = [threading.Thread(target=_append, args=(n,)) for n in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    rows = ExecutiveStore(tmp_path / "executive.jsonl").read_all()
    assert sorted(r.payload["n"] for r in rows) == list(range(12))


def test_tampered_history_raises_on_fold(svc, tmp_path):
    candidate = _candidate(svc, "o1")
    svc.build_context(candidate, decision_horizon="short_term",
                      decision_class="product",
                      resolved_inputs={"x": {"a": 1}})
    path = tmp_path / "executive.jsonl"
    lines = path.read_text().splitlines()
    # keep the context, drop the candidate it depends on
    path.write_text(lines[1] + "\n")
    with pytest.raises(ExecutiveError,
                       match="stored executive history is invalid"):
        ExecutiveService(path).get_state()


# =============================================================================
# Folded lifecycle — nothing skips a step
# =============================================================================

def test_a_candidate_with_no_reference_is_rejected(svc):
    with pytest.raises(ExecutiveError, match="carries at least one reference"):
        svc.register_candidate(references=[], origin={"kind": "manual",
                                                      "origin_id": "x"})


def test_a_context_requires_a_registered_candidate(svc):
    with pytest.raises(ExecutiveError, match="no such candidate"):
        svc.build_context("NOPE", decision_horizon="short_term",
                          decision_class="product", resolved_inputs={})


def test_a_context_requires_a_known_horizon_and_class(svc):
    candidate = _candidate(svc, "o1")
    with pytest.raises(ExecutiveError, match="horizon"):
        svc.build_context(candidate, decision_horizon="whenever",
                          decision_class="product", resolved_inputs={"x": 1})
    with pytest.raises(ExecutiveError, match="class"):
        svc.build_context(candidate, decision_horizon="short_term",
                          decision_class="vibes", resolved_inputs={"x": 1})


def test_a_package_requires_a_context(svc):
    candidate = _candidate(svc, "o1")
    with pytest.raises(ExecutiveError, match="renders a context"):
        svc.draft_package(candidate,
                          decision_question="q", references=REF,
                          unknowns=["u"])


def test_a_package_heading_to_review_needs_two_options(svc):
    candidate = _candidate(svc, "o1")
    svc.build_context(candidate, decision_horizon="short_term",
                      decision_class="product", resolved_inputs={"x": 1})
    package = svc.draft_package(candidate, decision_question="q",
                                references=REF, unknowns=["u"])
    svc.add_option(package, label="A", benefits=["b"], costs=["c"],
                   risks=["r"], unknowns=["u"], reversibility="easy")
    with pytest.raises(ExecutiveError, match="at least two options"):
        svc.request_review(package)
    svc.add_option(package, label="B", benefits=["b"], costs=["c"],
                   risks=["r"], unknowns=["u"], reversibility="moderate")
    svc.request_review(package)               # now permitted


def test_human_only_events_refuse_an_agent_actor(svc):
    candidate = _candidate(svc, "o1")
    with pytest.raises(ExecutiveError, match="human wall transition"):
        svc.dismiss_candidate(candidate, reason="x", actor_id="bot",
                              actor_type="agent")


def test_an_outcome_requires_a_linked_decision(svc):
    candidate = _candidate(svc, "o1")
    svc.build_context(candidate, decision_horizon="short_term",
                      decision_class="product", resolved_inputs={"x": 1})
    package = svc.draft_package(candidate, decision_question="q",
                                references=REF, unknowns=["u"])
    with pytest.raises(ExecutiveError, match="requires a linked Decision"):
        svc.observe_outcome(package, observation="it worked")


def test_fold_reproduces_state_from_rows_alone(svc):
    candidate = _candidate(svc, "o1")
    svc.build_context(candidate, decision_horizon="strategic",
                      decision_class="governance", resolved_inputs={"x": 1})
    folded = fold_executive(svc.store.read_all())
    assert folded.candidates[candidate]["status"] == "open"
    _, context = folded.current_context(candidate)
    assert context["decision_horizon"] == "strategic"
