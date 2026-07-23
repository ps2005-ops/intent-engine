"""V1.0.1 secure shareable reports.

Contract (execution-grade prompt §shareable-report security):
- 256-bit random tokens; only the SHA-256 hash is ever persisted;
- disabled by default — a share exists only after explicit creation;
- explicit revocation; expiry support; access logging;
- the shared view is the report SUBSET (render_report_preview): no
  private notes, no internal metadata;
- shared pages carry noindex; guessing another token is proven
  infeasible by test (hash lookup over 256-bit space).
"""
from __future__ import annotations

import hashlib
import secrets

from intent_engine.webapp.records import WebAppError, WebEvent

DEFAULT_SHARE_TTL_SECONDS = 7 * 24 * 3600


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class SharingService:
    def __init__(self, store, *, now_fn=None):
        import time
        self.store = store
        self.now = now_fn or time.time

    def create_share(self, *, run_id: str, owner_id: str,
                     ttl_seconds: int = DEFAULT_SHARE_TTL_SECONDS) -> str:
        """Returns the raw token exactly once; only its hash is stored."""
        if ttl_seconds <= 0:
            raise WebAppError("share ttl must be positive")
        token = secrets.token_urlsafe(32)          # 256 bits
        self.store.append(WebEvent(
            event_type="web.share_created", actor_type="human",
            actor_id=owner_id, subject_type="share", subject_id=run_id,
            payload={"token_hash": _hash(token), "run_id": run_id,
                     "owner_id": owner_id,
                     "expires_at": self.now() + ttl_seconds,
                     "revoked": False}))
        return token

    def revoke_share(self, *, token_hash: str, owner_id: str) -> None:
        share = self.store.shares().get(token_hash)
        if share is None or share["owner_id"] != owner_id:
            raise WebAppError("no such share for this owner")
        self.store.append(WebEvent(
            event_type="web.share_revoked", actor_type="human",
            actor_id=owner_id, subject_type="share",
            subject_id=share["run_id"],
            payload={"token_hash": token_hash}))

    def resolve(self, token: str, *, remote: str = "unknown"):
        """run_id if the token is live; None (with a logged denial) if not."""
        token_hash = _hash(token or "")
        share = self.store.shares().get(token_hash)
        denied = (share is None or share.get("revoked")
                  or share["expires_at"] <= self.now())
        event = "web.share_denied" if denied else "web.share_accessed"
        self.store.append(WebEvent(
            event_type=event, actor_type="system", actor_id="webapp",
            subject_type="share",
            subject_id=share["run_id"] if share else "unknown",
            payload={"token_hash": token_hash, "remote": remote,
                     "reason": ("missing" if share is None else
                                "revoked" if share.get("revoked") else
                                "expired" if share["expires_at"] <= self.now()
                                else "ok")}))
        return None if denied else share["run_id"]
