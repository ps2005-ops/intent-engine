"""T016 bars: feedback ledger + quote-consent gate."""
import pytest

from intent_engine.knowledge import KnowledgeError, KnowledgeService
from intent_engine.knowledge.store import KnowledgeCorruptLogError


@pytest.fixture()
def svc(tmp_path):
    return KnowledgeService(tmp_path / "feedback.jsonl",
                            tmp_path / "knowledge.jsonl")


def _fb(svc, **over):
    kw = dict(actor_type="human", actor_id="founder")
    kw.update(over)
    return svc.record_feedback("feedback.customer_reply",
                               "The report changed our hiring plan.", **kw)


def test_append_only_history_and_timestamps(svc):
    fid = _fb(svc, occurred_at="2026-07-01T00:00:00+00:00")
    rows = svc.get_feedback(fid)
    assert len(rows) == 1
    assert rows[0].occurred_at == "2026-07-01T00:00:00+00:00"
    assert rows[0].recorded_at != rows[0].occurred_at    # kept separate
    banned = [m for m in dir(svc.feedback)
              if any(w in m.lower() for w in ("update", "delete", "remove"))
              and not m.startswith("_")]
    assert banned == []


def test_idempotent_retry_zero_rows_and_conflict_rejected(svc):
    a = _fb(svc, idempotency_key="k1")
    b = _fb(svc, idempotency_key="k1")
    assert len(svc.feedback.read_all()) == 1
    with pytest.raises(ValueError, match="different content"):
        svc.record_feedback("feedback.internal_review", "different",
                            actor_type="human", actor_id="founder",
                            idempotency_key="k1")


def test_corrupt_log_fails_loudly(svc):
    _fb(svc)
    with open(svc.feedback.path, "a") as f:
        f.write("garbage line\n")
    with pytest.raises(KnowledgeCorruptLogError, match="malformed"):
        svc.feedback.read_all()


def test_unknown_feedback_type_rejected(svc):
    with pytest.raises(KnowledgeError, match="unknown record_type"):
        svc.record_feedback("feedback.vibes", "x", actor_type="human",
                            actor_id="founder")


# --- quote gate --------------------------------------------------------------

QUOTE = "The report changed our hiring plan."


def test_no_consent_cannot_publish(svc):
    fid = _fb(svc)
    check = svc.can_publish_quote(fid, QUOTE, "public")
    assert check["allowed"] is False
    assert "QUOTE CONSENT REQUIRED" in check["reason"]


def test_requested_only_cannot_publish(svc):
    fid = _fb(svc)
    svc.record_quote_consent(fid, "requested", QUOTE, "public",
                             actor_type="agent", actor_id="content_agent")
    assert svc.can_publish_quote(fid, QUOTE, "public")["allowed"] is False


def test_human_approval_for_exact_quote_publishes(svc):
    fid = _fb(svc)
    svc.record_quote_consent(fid, "approved", QUOTE, "public",
                             actor_type="human", actor_id="founder")
    assert svc.can_publish_quote(fid, QUOTE, "public")["allowed"] is True
    # a DIFFERENT text span is not covered
    assert svc.can_publish_quote(fid, QUOTE + " Really.",
                                 "public")["allowed"] is False


def test_system_approval_rejected(svc):
    fid = _fb(svc)
    for actor in ("agent", "system"):
        with pytest.raises(KnowledgeError, match="human wall"):
            svc.record_quote_consent(fid, "approved", QUOTE, "public",
                                     actor_type=actor, actor_id="bot")


def test_rejection_and_revocation_block(svc):
    fid = _fb(svc)
    svc.record_quote_consent(fid, "rejected", QUOTE, "public",
                             actor_type="human", actor_id="founder")
    assert svc.can_publish_quote(fid, QUOTE, "public")["allowed"] is False
    svc.record_quote_consent(fid, "approved", QUOTE, "public",
                             actor_type="human", actor_id="founder")
    assert svc.can_publish_quote(fid, QUOTE, "public")["allowed"] is True
    svc.record_quote_consent(fid, "revoked", QUOTE, "public",
                             actor_type="human", actor_id="founder")
    assert svc.can_publish_quote(fid, QUOTE, "public")["allowed"] is False
    # history fully preserved
    kinds = [r.record_type for r in svc.get_feedback(fid)]
    assert kinds.count("feedback.quote_consent_approved") == 1
    assert kinds.count("feedback.quote_consent_revoked") == 1


def test_internal_consent_does_not_imply_public(svc):
    fid = _fb(svc)
    svc.record_quote_consent(fid, "approved", QUOTE, "internal",
                             actor_type="human", actor_id="founder")
    assert svc.can_publish_quote(fid, QUOTE, "internal")["allowed"] is True
    assert svc.can_publish_quote(fid, QUOTE, "public")["allowed"] is False
