"""Growth-OS foundation — provenance/confidence contract, idempotent event
store, replay, and human-gated learning candidates. Offline, deterministic."""
import pytest

from intent_engine.growth_os.foundation import (
    Confidence,
    GrowthOSError,
    IntelRecord,
    IntelStore,
    LearningCandidate,
    Provenance,
)


def _rec(key="k1", topic="ai forecasting", recorded_at=None):
    r = IntelRecord(
        stream="research", event_type="growth_research.observed", actor="agent",
        provenance=Provenance(source="reddit", method="api", uri="https://r/x"),
        confidence=Confidence(0.7, basis="3 threads this week"),
        payload={"topic": topic}, idempotency_key=key)
    if recorded_at:
        r.recorded_at = recorded_at
    return r


# --- contract ---------------------------------------------------------------

def test_confidence_requires_a_basis():
    with pytest.raises(GrowthOSError):
        Confidence(0.7, basis="").validate()
    Confidence(0.7, basis="why").validate()          # ok


def test_confidence_range_enforced():
    with pytest.raises(GrowthOSError):
        Confidence(1.5, basis="x").validate()


def test_provenance_forbids_unpermitted_method():
    # there is no "scrape" — a ToS-violating source is not expressible
    with pytest.raises(GrowthOSError):
        Provenance(source="site", method="scrape").validate()
    Provenance(source="site", method="rss").validate()  # ok


def test_record_requires_provenance_and_confidence_and_ulid():
    r = _rec()
    r.validate()
    assert len(r.record_id) == 26                     # ULID


# --- store: idempotency + replay -------------------------------------------

def test_store_idempotent_ignores_write_stamp(tmp_path):
    s = IntelStore(tmp_path / "s.jsonl")
    s.append(_rec(recorded_at="2026-07-26T00:00:00+00:00"))
    s.append(_rec(recorded_at="2026-07-26T00:00:09+00:00"))  # later stamp, same content
    assert len(s.read_all()) == 1                     # deduped, not conflicted


def test_store_conflict_on_genuinely_different_content(tmp_path):
    s = IntelStore(tmp_path / "s.jsonl")
    s.append(_rec(topic="ai forecasting"))
    with pytest.raises(GrowthOSError):
        s.append(_rec(topic="something else"))        # same key, different content


def test_store_replays_deterministically(tmp_path):
    s = IntelStore(tmp_path / "s.jsonl")
    s.append(_rec(key="a", topic="t1"))
    s.append(_rec(key="b", topic="t2"))
    count = s.replay(lambda acc, r: (acc or 0) + 1, initial=0)
    assert count == 2
    # round-trips through JSON
    assert {r.payload["topic"] for r in s.read_all()} == {"t1", "t2"}


# --- learning candidate: human-gated ---------------------------------------

def test_candidate_needs_evidence():
    with pytest.raises(GrowthOSError):
        LearningCandidate(statement="x", success_metric="y", evidence=[]).validate()


def test_candidate_accept_is_human_only():
    c = LearningCandidate(statement="x", success_metric="y", evidence=["r1"])
    c.validate()
    with pytest.raises(GrowthOSError):
        c.with_decision("accepted", actor="agent")
    c.with_decision("accepted", actor="human")
    assert c.status == "accepted"
