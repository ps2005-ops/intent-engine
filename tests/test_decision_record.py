"""Bars for the event-sourced Decision Record (T010, Slice 1 data layer).

Every founder-review decision has a test here. Stdlib + pytest only; each
test uses a throwaway SQLite file, so nothing touches real data.
"""
import hashlib
import json
import sqlite3

import pytest

from intent_engine.core.decision_ids import is_decision_key, is_ulid
from intent_engine.core.decision_record import (
    DecisionService, DecisionState, RECORD_SCHEMA_VERSION, SchemaVersionError,
    TransitionError, fold, validate_event,
)


@pytest.fixture
def svc(tmp_path):
    return DecisionService(str(tmp_path / "decisions.db"))


def _advance(svc, did, *event_types):
    for et in event_types:
        svc.record_event(did, et, actor_type="human", actor_id="founder",
                         source="cli")


# (c) dual ID -----------------------------------------------------------------
def test_dual_id_shapes_and_uniqueness(svc):
    r1 = svc.create_decision("founder")
    r2 = svc.create_decision("founder")
    assert is_ulid(r1.decision_id) and len(r1.decision_id) == 26
    assert is_decision_key(r1.decision_key)
    assert r1.decision_id != r2.decision_id
    assert r1.decision_key != r2.decision_key
    n1 = int(r1.decision_key.split("-")[-1])
    n2 = int(r2.decision_key.split("-")[-1])
    assert n2 == n1 + 1                      # per-year sequence
    assert r1.record_schema_version == RECORD_SCHEMA_VERSION
    # lookups work by either identifier
    assert svc.get_decision(r1.decision_id).decision_key == r1.decision_key
    assert svc.get_decision(r1.decision_key).decision_id == r1.decision_id


# (a) fold: three independent axes + owner ------------------------------------
def test_fold_three_axes_and_owner(svc):
    r = svc.create_decision("founder")
    did = r.decision_id
    st = svc.get_current_state(did)
    assert (st.decision_status, st.execution_status, st.evaluation_status,
            st.owner) == ("draft", "not_started", "unresolved", None)

    svc.record_event(did, "OwnerAssigned", actor_type="human", actor_id="founder",
                     source="cli", payload={"owner": "Pratham"})
    _advance(svc, did, "DecisionSubmitted", "DecisionApproved", "ExecutionStarted")
    st = svc.get_current_state(did)
    assert (st.decision_status, st.execution_status, st.evaluation_status,
            st.owner) == ("approved", "executing", "unresolved", "Pratham")

    # evaluation axis moves independently of execution
    _advance(svc, did, "DecisionResolved", "DecisionCalibrated")
    st = svc.get_current_state(did)
    assert st.evaluation_status == "calibrated"
    assert st.execution_status == "executing"


def test_owner_transfer_folds_latest(svc):
    r = svc.create_decision("founder")
    svc.record_event(r.decision_id, "OwnerAssigned", actor_type="human",
                     actor_id="founder", source="cli", payload={"owner": "A"})
    svc.record_event(r.decision_id, "OwnerTransferred", actor_type="human",
                     actor_id="founder", source="cli", payload={"owner": "B"})
    assert svc.get_current_state(r.decision_id).owner == "B"


def test_cancel_abandons_execution(svc):
    r = svc.create_decision("founder")
    _advance(svc, r.decision_id, "DecisionSubmitted", "DecisionApproved",
             "ExecutionStarted", "DecisionCancelled")
    st = svc.get_current_state(r.decision_id)
    assert st.decision_status == "cancelled"
    assert st.execution_status == "abandoned"


# (d) transition validator ----------------------------------------------------
def test_transition_validator_rejects_illegal(svc):
    r = svc.create_decision("founder")
    with pytest.raises(TransitionError):
        svc.record_event(r.decision_id, "DecisionApproved", actor_type="human",
                         actor_id="founder", source="cli")  # approve before submit

    st = DecisionState("draft", "not_started", "unresolved", None)
    assert validate_event(st, "DecisionApproved")[0] is False
    assert validate_event(st, "DecisionSubmitted")[0] is True
    st2 = DecisionState("approved", "executing", "unresolved", None)
    assert validate_event(st2, "DecisionCalibrated")[0] is False   # needs resolved
    assert validate_event(st2, "DecisionResolved")[0] is True
    assert validate_event(st2, "nonsense_event")[0] is False


def test_illegal_event_writes_nothing(svc):
    r = svc.create_decision("founder")
    before = len(svc.get_events(r.decision_id))
    with pytest.raises(TransitionError):
        svc.record_event(r.decision_id, "ExecutionStarted", actor_type="human",
                         actor_id="founder", source="cli")
    assert len(svc.get_events(r.decision_id)) == before   # rolled back


# (b) idempotency -------------------------------------------------------------
def test_idempotent_create(svc):
    r1 = svc.create_decision("founder", idempotency_key="intake-abc")
    r2 = svc.create_decision("founder", idempotency_key="intake-abc")
    assert r1.decision_id == r2.decision_id
    assert r1.decision_key == r2.decision_key
    con = sqlite3.connect(svc.db_path)
    try:
        n_rec = con.execute("SELECT COUNT(*) FROM decision_records").fetchone()[0]
        n_evt = con.execute("SELECT COUNT(*) FROM decision_events").fetchone()[0]
    finally:
        con.close()
    assert (n_rec, n_evt) == (1, 1)          # no duplicate rows


def test_idempotent_record_event(svc):
    r = svc.create_decision("founder")
    e1 = svc.record_event(r.decision_id, "DecisionSubmitted", actor_type="human",
                          actor_id="founder", source="cli", idempotency_key="sub-1")
    e2 = svc.record_event(r.decision_id, "DecisionSubmitted", actor_type="human",
                          actor_id="founder", source="cli", idempotency_key="sub-1")
    assert e1 == e2
    assert len(svc.get_events(r.decision_id)) == 2   # created + submitted once


# (7,8) ordering + timestamps -------------------------------------------------
def test_sequence_numbers_and_timestamps(svc):
    r = svc.create_decision("founder")
    _advance(svc, r.decision_id, "DecisionSubmitted", "DecisionApproved")
    evs = svc.get_events(r.decision_id)
    assert [e["sequence_number"] for e in evs] == [1, 2, 3]
    for e in evs:
        assert e["occurred_at"] and e["recorded_at"]     # both fields present
        assert e["actor_type"] == "human" and e["source"] == "cli"


# (e) canonical relationships -------------------------------------------------
def test_canonical_relationship_inverse_derived(svc):
    old = svc.create_decision("founder")
    new = svc.create_decision("founder")
    svc.supersede_decision(old.decision_id, new.decision_id)

    con = sqlite3.connect(svc.db_path)
    try:
        rows = con.execute("SELECT * FROM decision_relationships").fetchall()
    finally:
        con.close()
    assert len(rows) == 1                     # ONE direction stored
    assert rows[0][0] == new.decision_id and rows[0][2] == "supersedes"

    rel_old = svc.get_related_decisions(old.decision_id)
    assert rel_old["incoming"][0]["relationship_type"] == "superseded_by"
    assert rel_old["incoming"][0]["decision_id"] == new.decision_id
    rel_new = svc.get_related_decisions(new.decision_id)
    assert rel_new["outgoing"][0]["relationship_type"] == "supersedes"
    assert svc.get_current_state(old.decision_id).decision_status == "superseded"


def test_relationship_and_entity_uniqueness_and_multientity(svc):
    a = svc.create_decision("founder")
    b = svc.create_decision("founder")
    svc.add_relationship(a.decision_id, b.decision_id, "depends_on")
    svc.add_relationship(a.decision_id, b.decision_id, "depends_on")   # dup ignored
    svc.add_entity(a.decision_id, "Acme Inc", "subject")
    svc.add_entity(a.decision_id, "Acme Inc", "subject")              # dup ignored
    svc.add_entity(a.decision_id, "Rival Co", "competitor")          # multi-entity
    con = sqlite3.connect(svc.db_path)
    try:
        n_rel = con.execute("SELECT COUNT(*) FROM decision_relationships").fetchone()[0]
        n_ent = con.execute("SELECT COUNT(*) FROM decision_entities").fetchone()[0]
    finally:
        con.close()
    assert (n_rel, n_ent) == (1, 2)


# (f) schema-version guard ----------------------------------------------------
def test_schema_version_guard_rejects_future_major(svc):
    con = sqlite3.connect(svc.db_path)
    try:
        con.execute("INSERT INTO decision_records VALUES (?,?,?,?,?,?)",
                    ("Z" * 26, "DEC-2099-000001", "2099-01-01T00:00:00+00:00",
                     "future", RECORD_SCHEMA_VERSION + 1, "{}"))
        con.commit()
    finally:
        con.close()
    with pytest.raises(SchemaVersionError):
        svc.get_decision("DEC-2099-000001")


# (10) no raw sensitive intake text in event payloads -------------------------
def test_no_raw_sensitive_text_in_event_payloads(svc):
    secret = "ACME acquires BETA for $9.9M on 2026-08-01 (confidential)"
    r = svc.create_decision(
        "founder",
        metadata={"intake_sha256": hashlib.sha256(secret.encode()).hexdigest()})
    blob = json.dumps([e["payload"] for e in svc.get_events(r.decision_id)])
    assert secret not in blob
    assert "confidential" not in blob


# (h) append-only enforced structurally ---------------------------------------
def test_append_only_triggers_block_mutation(svc):
    r = svc.create_decision("founder")
    con = sqlite3.connect(svc.db_path)
    try:
        with pytest.raises(sqlite3.Error):
            con.execute("UPDATE decision_records SET created_by='x' WHERE decision_id=?",
                        (r.decision_id,))
        with pytest.raises(sqlite3.Error):
            con.execute("DELETE FROM decision_events WHERE decision_id=?",
                        (r.decision_id,))
    finally:
        con.close()


# fold() is pure and deterministic --------------------------------------------
def test_fold_is_pure():
    events = [{"event_type": t, "payload": {}} for t in
              ("DecisionCreated", "DecisionSubmitted", "DecisionApproved")]
    st = fold(events)
    assert st.decision_status == "approved"
    assert fold(events) == st          # deterministic, no side effects


# --- hardening (pre-commit review) -------------------------------------------

def test_relationship_requires_existing_decisions(svc):
    """FK integrity: an edge cannot reference a nonexistent decision —
    rejected at the service layer AND by the DB foreign key."""
    real = svc.create_decision("founder")
    ghost = "Z" * 26
    with pytest.raises(KeyError):
        svc.add_relationship(real.decision_id, ghost, "depends_on")
    with pytest.raises(KeyError):
        svc.add_relationship(ghost, real.decision_id, "depends_on")
    # DB-level backstop: FK fires even if the service checks were bypassed
    con = sqlite3.connect(svc.db_path)
    try:
        con.execute("PRAGMA foreign_keys = ON")
        with pytest.raises(sqlite3.IntegrityError):
            con.execute("INSERT INTO decision_relationships VALUES (?,?,?)",
                        (real.decision_id, ghost, "depends_on"))
    finally:
        con.close()


def test_self_relationship_rejected(svc):
    r = svc.create_decision("founder")
    with pytest.raises(ValueError):
        svc.add_relationship(r.decision_id, r.decision_id, "supersedes")


def test_relationship_and_entity_tables_append_only(svc):
    a = svc.create_decision("founder")
    b = svc.create_decision("founder")
    svc.add_relationship(a.decision_id, b.decision_id, "depends_on")
    svc.add_entity(a.decision_id, "Acme Inc", "subject")
    con = sqlite3.connect(svc.db_path)
    try:
        with pytest.raises(sqlite3.Error):
            con.execute("UPDATE decision_relationships SET relationship_type='blocks'")
        with pytest.raises(sqlite3.Error):
            con.execute("DELETE FROM decision_relationships")
        with pytest.raises(sqlite3.Error):
            con.execute("UPDATE decision_entities SET entity_id='Evil Co'")
        with pytest.raises(sqlite3.Error):
            con.execute("DELETE FROM decision_entities")
    finally:
        con.close()


def test_supersede_is_atomic_rolls_back_on_illegal_transition(svc):
    """Superseding a terminal decision must fail AND leave zero relationship
    rows — the edge and the event are one transaction, not two."""
    old = svc.create_decision("founder")
    _advance(svc, old.decision_id, "DecisionSubmitted", "DecisionDeclined")
    new = svc.create_decision("founder")
    with pytest.raises(TransitionError):
        svc.supersede_decision(old.decision_id, new.decision_id)
    con = sqlite3.connect(svc.db_path)
    try:
        n_rel = con.execute("SELECT COUNT(*) FROM decision_relationships").fetchone()[0]
    finally:
        con.close()
    assert n_rel == 0                       # no partial write survived


def test_owner_and_supersede_payloads_validated(svc):
    r = svc.create_decision("founder")
    before = len(svc.get_events(r.decision_id))
    for payload in ({}, {"owner": ""}, {"owner": "   "}, {"owner": 42}):
        with pytest.raises(ValueError):
            svc.record_event(r.decision_id, "OwnerAssigned", actor_type="human",
                             actor_id="founder", source="cli", payload=payload)
    with pytest.raises(ValueError):
        svc.record_event(r.decision_id, "DecisionSuperseded", actor_type="human",
                         actor_id="founder", source="cli", payload={})
    assert len(svc.get_events(r.decision_id)) == before   # zero rows written
    # OwnerTransferred validated too (needs an owner first)
    svc.record_event(r.decision_id, "OwnerAssigned", actor_type="human",
                     actor_id="founder", source="cli", payload={"owner": "A"})
    with pytest.raises(ValueError):
        svc.record_event(r.decision_id, "OwnerTransferred", actor_type="human",
                         actor_id="founder", source="cli", payload={"owner": ""})


def test_fold_validates_persisted_history(svc):
    """A hand-inserted illegal event (bypassing the service) must raise on
    read, not fold silently."""
    r = svc.create_decision("founder")
    con = sqlite3.connect(svc.db_path)
    try:
        # ExecutionStarted while still draft — the validator would never allow it
        con.execute(
            "INSERT INTO decision_events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("X" * 26, r.decision_id, 2, "ExecutionStarted",
             "2026-07-20T00:00:00+00:00", "2026-07-20T00:00:00+00:00",
             "system", "tamper", "system", None, "analytical", "{}", 1))
        con.commit()
    finally:
        con.close()
    with pytest.raises(TransitionError):
        svc.get_current_state(r.decision_id)


def test_idempotency_key_reuse_across_operations_rejected(svc):
    """The key is globally UNIQUE, so a replay must be the SAME operation;
    reuse for a different event type or decision raises instead of silently
    returning the wrong event."""
    r = svc.create_decision("founder")
    svc.record_event(r.decision_id, "DecisionSubmitted", actor_type="human",
                     actor_id="founder", source="cli", idempotency_key="k-1")
    with pytest.raises(ValueError):
        svc.record_event(r.decision_id, "DecisionApproved", actor_type="human",
                         actor_id="founder", source="cli", idempotency_key="k-1")
    other = svc.create_decision("founder")
    with pytest.raises(ValueError):
        svc.record_event(other.decision_id, "DecisionSubmitted", actor_type="human",
                         actor_id="founder", source="cli", idempotency_key="k-1")


def test_decision_key_sequence_exhaustion_fails_clearly():
    from intent_engine.core.decision_ids import format_decision_key
    assert format_decision_key(2026, 999999) == "DEC-2026-999999"
    with pytest.raises(ValueError):
        format_decision_key(2026, 1000000)      # never wraps or malforms
