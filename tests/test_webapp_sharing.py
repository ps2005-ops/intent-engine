"""V1.0.1 — shareable-report security contract."""
import hashlib
import json

import pytest

from intent_engine.webapp.records import WebAppError, WebEvent
from intent_engine.webapp.sharing import SharingService
from intent_engine.webapp.store import WebStore


def _svc(tmp_path):
    clock = {"t": 1000.0}
    svc = SharingService(WebStore(tmp_path / "web.jsonl"),
                         now_fn=lambda: clock["t"])
    return svc, clock


def test_token_is_long_random_and_only_hash_persisted(tmp_path):
    svc, _ = _svc(tmp_path)
    token = svc.create_share(run_id="run-1", owner_id="user-a")
    assert len(token) >= 40                       # 256 bits urlsafe
    raw_log = (tmp_path / "web.jsonl").read_text()
    assert token not in raw_log                   # never persisted raw
    assert hashlib.sha256(token.encode()).hexdigest() in raw_log


def test_sharing_disabled_by_default(tmp_path):
    svc, _ = _svc(tmp_path)
    assert svc.resolve("any-guess") is None       # nothing shared until created


def test_resolve_revoke_expiry_and_access_log(tmp_path):
    svc, clock = _svc(tmp_path)
    token = svc.create_share(run_id="run-1", owner_id="user-a",
                             ttl_seconds=3600)
    assert svc.resolve(token) == "run-1"
    clock["t"] += 3601
    assert svc.resolve(token) is None             # expired
    clock["t"] -= 3601
    token2 = svc.create_share(run_id="run-1", owner_id="user-a")
    svc.revoke_share(
        token_hash=hashlib.sha256(token2.encode()).hexdigest(),
        owner_id="user-a")
    assert svc.resolve(token2) is None            # revoked
    log = svc.store.access_log()
    assert any(r.event_type == "web.share_accessed" for r in log)
    assert any(r.event_type == "web.share_denied" for r in log)


def test_only_owner_can_revoke(tmp_path):
    svc, _ = _svc(tmp_path)
    token = svc.create_share(run_id="run-1", owner_id="user-a")
    with pytest.raises(WebAppError, match="no such share for this owner"):
        svc.revoke_share(
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            owner_id="user-b")


def test_guessing_a_token_is_infeasible_and_logged(tmp_path):
    svc, _ = _svc(tmp_path)
    svc.create_share(run_id="run-1", owner_id="user-a")
    for guess in ("aaaa", "run-1", "0" * 43):
        assert svc.resolve(guess) is None
    denials = [r for r in svc.store.access_log()
               if r.event_type == "web.share_denied"]
    assert len(denials) == 3


def test_records_refuse_raw_token_persistence():
    with pytest.raises(WebAppError, match="raw share tokens"):
        WebEvent(event_type="web.share_created", actor_type="human",
                 actor_id="u", payload={"share_token_raw": "leak"}).validate()


def test_ttl_must_be_positive(tmp_path):
    svc, _ = _svc(tmp_path)
    with pytest.raises(WebAppError, match="ttl must be positive"):
        svc.create_share(run_id="r", owner_id="u", ttl_seconds=0)
