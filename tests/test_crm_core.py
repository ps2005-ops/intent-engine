"""T014 bars: CRM identity + append-only storage."""
import threading

import pytest

from intent_engine.core.decision_ids import is_ulid
from intent_engine.crm import CRMEnvelopeError, CRMService
from intent_engine.crm.store import CRMCorruptLogError


@pytest.fixture()
def crm(tmp_path):
    return CRMService(tmp_path / "crm.jsonl")


def test_crm_ids_are_opaque_and_unique(crm):
    a = crm.create_prospect(name="Jane", email="jane@acme.com")
    b = crm.create_prospect(name="Jane B", email="jane@beta.com")
    assert is_ulid(a) and is_ulid(b) and a != b


def test_human_attributes_are_payload_not_keys(crm):
    a = crm.create_prospect(name="Jane", email="jane@acme.com")
    ev = crm.get_history(a)[0]
    assert ev.crm_entity_id == a != "jane@acme.com"
    assert ev.payload["email"] == "jane@acme.com"     # attribute only


def test_idempotent_create_creates_zero_new_rows(crm):
    a = crm.create_prospect(email="jane@acme.com", idempotency_key="intake-1")
    b = crm.create_prospect(email="jane@acme.com", idempotency_key="intake-1")
    assert a == b
    assert len(crm.store.read_all()) == 1


def test_same_key_different_content_fails(crm):
    a = crm.create_prospect(email="jane@acme.com")
    crm.record(a, "crm.contacted", actor_type="human", actor_id="founder",
               idempotency_key="touch-1")
    with pytest.raises(ValueError, match="different content"):
        crm.record(a, "crm.replied", actor_type="human", actor_id="founder",
                   idempotency_key="touch-1")


def test_append_order_preserved_and_no_mutation_api(crm):
    a = crm.create_prospect(email="j@a.com")
    crm.record(a, "crm.contacted", actor_type="human", actor_id="founder")
    crm.record(a, "crm.replied", actor_type="human", actor_id="founder")
    types = [e.event_type for e in crm.get_history(a)]
    assert types == ["crm.prospect_created", "crm.contacted", "crm.replied"]
    banned = [m for m in dir(crm.store)
              if any(w in m.lower() for w in ("update", "delete", "remove"))
              and not m.startswith("_")]
    assert banned == []


def test_malformed_log_fails_clearly(crm):
    a = crm.create_prospect(email="j@a.com")
    with open(crm.store.path, "a") as f:
        f.write("not json at all\n")
    with pytest.raises(CRMCorruptLogError, match="malformed"):
        crm.get_history(a)


def test_concurrent_writers_do_not_corrupt(crm):
    a = crm.create_prospect(email="j@a.com")
    errors = []

    def worker(n):
        try:
            for i in range(8):
                crm.record(a, "crm.note_added", actor_type="human",
                           actor_id="founder",
                           payload={"note": f"n{n}-{i}"},
                           idempotency_key=f"note-{n}-{i}")
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert len(crm.get_history(a)) == 25          # 1 create + 24 notes


def test_identity_resolution_is_exact_and_conservative(crm):
    a = crm.create_prospect(name="Jane", email="jane@acme.com")
    crm.record(a, "crm.identity_linked", actor_type="human",
               actor_id="founder", payload={"external_ref": "crunchbase:acme"})
    assert crm.get_entity(a) == a
    assert crm.get_entity("jane@acme.com") == a          # exact email
    assert crm.get_entity("crunchbase:acme") == a        # explicit link
    assert crm.get_entity("jane@ACME.com") is None       # no fuzzy matching
    assert crm.get_entity("jane") is None


def test_conflicting_identities_require_explicit_resolution(crm):
    a = crm.create_prospect(email="shared@acme.com")
    b = crm.create_prospect(email="other@acme.com")
    crm.record(b, "crm.identity_linked", actor_type="human",
               actor_id="founder", payload={"external_ref": "shared@acme.com"})
    with pytest.raises(CRMEnvelopeError, match="explicit resolution"):
        crm.get_entity("shared@acme.com")            # ambiguous: no silent merge
