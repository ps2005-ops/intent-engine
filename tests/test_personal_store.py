"""T023 workspace store, provenance contract, and the three memory classes.

0 model calls. 0 network.
"""
import json

import pytest

from intent_engine.personal import (
    PersonalError, PersonalStore, SecretRejected, SourceClaim, SourceRef,
    fold_personal, freshness_of,
)
from intent_engine.personal.records import (
    AVAIL_CONFLICTED, AVAIL_OUT_OF_SCOPE, AVAIL_SUPPORTED, AVAIL_UNAVAILABLE,
    FRESH_CURRENT, FRESH_HISTORICAL, FRESH_STALE, FRESH_UNKNOWN, PersonalEvent,
    assert_no_secret, assert_workspace_language,
)
from intent_engine.personal.store import PersonalCorruptLogError

AS_OF = "2026-07-21T00:00:00+00:00"


def _ref(**over):
    kw = dict(subsystem="research", artifact_type="conclusion",
              artifact_id="CON-1", replay_id="R-1", as_of=AS_OF)
    kw.update(over)
    return SourceRef(**kw)


# =============================================================================
# The provenance contract
# =============================================================================

def test_a_supported_claim_must_cite_a_source_artifact():
    with pytest.raises(PersonalError, match="cites at least one source"):
        SourceClaim(claim_id="c1", text="reply rate rose",
                    availability=AVAIL_SUPPORTED, source_refs=()).validate()


def test_an_unavailable_claim_needs_no_source():
    SourceClaim(claim_id="c1", text="nothing recorded",
                availability=AVAIL_UNAVAILABLE, source_refs=()).validate()


def test_out_of_scope_is_a_first_class_availability():
    SourceClaim(claim_id="c1", text="no subsystem reports competitors",
                availability=AVAIL_OUT_OF_SCOPE, source_refs=()).validate()


def test_a_source_ref_carries_a_replay_id():
    with pytest.raises(PersonalError, match="carries a replay id"):
        SourceRef(subsystem="research", artifact_type="c", artifact_id="1",
                  replay_id="", as_of=AS_OF).validate()


def test_a_claim_cites_artifacts_not_merely_agents():
    """The invariant: 'research' is too broad; 'conclusion CON-1 at R-1' is
    trustworthy."""
    claim = SourceClaim(claim_id="c1", text="current evidence suggests X",
                        availability=AVAIL_SUPPORTED, source_refs=(_ref(),))
    claim.validate()
    ref = claim.source_refs[0]
    assert ref.artifact_id and ref.replay_id and ref.subsystem


def test_disagreement_is_a_representable_state():
    claim = SourceClaim(claim_id="c1", text="the sources disagree",
                        availability=AVAIL_CONFLICTED, source_refs=(_ref(),))
    claim.validate()
    assert claim.availability == AVAIL_CONFLICTED


def test_claim_text_passes_the_workspace_language_wall():
    with pytest.raises(PersonalError, match="overclaims"):
        SourceClaim(claim_id="c1", text="this is obviously the best option",
                    availability=AVAIL_SUPPORTED, source_refs=(_ref(),)).validate()


# =============================================================================
# Freshness
# =============================================================================

def test_freshness_is_unknown_without_a_timestamp():
    assert freshness_of(None, AS_OF) == FRESH_UNKNOWN


def test_freshness_grades_by_age():
    assert freshness_of("2026-07-01T00:00:00+00:00", AS_OF) == FRESH_CURRENT
    assert freshness_of("2026-01-01T00:00:00+00:00", AS_OF) == FRESH_STALE
    assert freshness_of("2024-01-01T00:00:00+00:00", AS_OF) == FRESH_HISTORICAL


def test_a_future_timestamp_is_unknown_not_current():
    assert freshness_of("2027-01-01T00:00:00+00:00", AS_OF) == FRESH_UNKNOWN


# =============================================================================
# Privacy / secrets
# =============================================================================

@pytest.mark.parametrize("secret", [
    "my key is sk-ABCDEFGHIJKLMNOPQRSTUV",
    "AKIA1234567890ABCDEF",
    "token ghp_abcdefghijklmnopqrstuvwxyz",
    "password: hunter2",
    "-----BEGIN RSA PRIVATE KEY-----",
])
def test_secrets_are_refused_before_storage(secret):
    with pytest.raises(SecretRejected):
        assert_no_secret(secret, where="note")


def test_ordinary_founder_text_is_not_a_secret():
    assert_no_secret("we should investigate why activation stalled",
                     where="note")


# =============================================================================
# Store on the kernel base
# =============================================================================

def test_store_subclasses_the_kernel(tmp_path):
    from intent_engine.agentos.append_only import AppendOnlyStore
    store = PersonalStore(tmp_path / "personal.jsonl")
    assert isinstance(store, AppendOnlyStore)
    # no store mechanics reimplemented here
    src = (__import__("pathlib").Path(
        "src/intent_engine/personal/store.py").read_text())
    assert "os.fsync" not in src and "fcntl" not in src


def test_append_is_idempotent(tmp_path):
    store = PersonalStore(tmp_path / "personal.jsonl")
    row = PersonalEvent(event_type="personal.session_opened",
                        actor_type="human", actor_id="founder", source="cli",
                        session_id="S1", subject_id="S1", idempotency_key="k1")
    store.append(row)
    store.append(PersonalEvent(
        event_type="personal.session_opened", actor_type="human",
        actor_id="founder", source="cli", session_id="S1", subject_id="S1",
        idempotency_key="k1"))
    assert len(store.read_all()) == 1


def test_corrupt_log_fails_loudly(tmp_path):
    store = PersonalStore(tmp_path / "personal.jsonl")
    store.append(PersonalEvent(event_type="personal.session_opened",
                               actor_type="human", actor_id="f", source="cli",
                               session_id="S1", subject_id="S1"))
    path = tmp_path / "personal.jsonl"
    path.write_text(path.read_text() + "{bad\n")
    with pytest.raises(PersonalCorruptLogError):
        PersonalStore(path).read_all()


# =============================================================================
# The three memory lifecycles
# =============================================================================

def test_a_conversation_turn_is_not_durable_memory(tmp_path):
    store = PersonalStore(tmp_path / "personal.jsonl")
    store.append(PersonalEvent(event_type="personal.session_opened",
                               actor_type="human", actor_id="f", source="cli",
                               session_id="S1", subject_id="S1"))
    store.append(PersonalEvent(
        event_type="personal.turn_recorded", actor_type="human", actor_id="f",
        source="cli", session_id="S1", subject_id="T1",
        payload={"question": "why are we losing confidence?",
                 "intent": "EXPLAIN_FINDING"}))
    state = fold_personal(store.read_all())
    # the turn is in the ephemeral session, and NOT in durable memory
    assert state.turns["S1"][0]["question"].startswith("why are we")
    assert state.durable_memory() == {"goals": {}, "pins": {},
                                      "investigations": {}, "preferences": {}}


def test_durable_memory_is_a_founder_only_act(tmp_path):
    store = PersonalStore(tmp_path / "personal.jsonl")
    # an agent/system cannot pin
    with pytest.raises(PersonalError, match="only a person creates it"):
        store.append(PersonalEvent(
            event_type="personal.memory_pinned", actor_type="agent",
            actor_id="workspace", source="workspace", subject_id="P1",
            payload={"reference": {"kind": "conclusion", "ref_id": "CON-1"}}))


def test_an_explicit_pin_creates_durable_memory(tmp_path):
    store = PersonalStore(tmp_path / "personal.jsonl")
    store.append(PersonalEvent(
        event_type="personal.memory_pinned", actor_type="human",
        actor_id="founder", source="cli", subject_id="P1",
        payload={"reference": {"subsystem": "research", "artifact_id": "CON-1"},
                 "note": "watch this"}))
    state = fold_personal(store.read_all())
    assert "P1" in state.pins
    assert state.pins["P1"]["reference"]["artifact_id"] == "CON-1"


def test_a_memory_candidate_is_proposed_not_promoted(tmp_path):
    store = PersonalStore(tmp_path / "personal.jsonl")
    store.append(PersonalEvent(
        event_type="personal.memory_candidate_proposed", actor_type="agent",
        actor_id="workspace", source="workspace", subject_id="MC1",
        payload={"kind": "goal", "detail": "sounds like a goal"}))
    state = fold_personal(store.read_all())
    assert len(state.memory_candidates) == 1
    assert state.goals == {}          # proposed, not promoted


def test_tampered_history_raises_on_fold(tmp_path):
    store = PersonalStore(tmp_path / "personal.jsonl")
    store.append(PersonalEvent(event_type="personal.session_opened",
                               actor_type="human", actor_id="f", source="cli",
                               session_id="S1", subject_id="S1"))
    store.append(PersonalEvent(event_type="personal.turn_recorded",
                               actor_type="human", actor_id="f", source="cli",
                               session_id="S1", subject_id="T1",
                               payload={"question": "q", "intent": "UNKNOWN"}))
    path = tmp_path / "personal.jsonl"
    lines = path.read_text().splitlines()
    path.write_text(lines[1] + "\n")   # a turn with no open session
    with pytest.raises(PersonalError, match="stored workspace history is "
                                           "invalid"):
        fold_personal(PersonalStore(path).read_all(), validate=True)

