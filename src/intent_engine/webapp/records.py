"""V1.0.1 webapp records — append-only events for accounts, ownership,
sharing, and access logging.

The webapp computes NO intelligence. It stores only what the public web
surface needs: who exists, who owns which run, which share tokens exist
(hashes only, never the token), and who accessed what. Same append-only
discipline as every other store (AgentOS kernel, T022).
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from intent_engine.core.decision_ids import is_ulid, new_ulid

WEBAPP_SCHEMA_VERSION = 1

WEB_EVENTS = frozenset({
    "web.user_created",
    "web.login_succeeded",
    "web.login_failed",
    "web.login_locked",
    "web.logout",
    "web.run_owned",
    "web.share_created",
    "web.share_revoked",
    "web.share_accessed",
    "web.share_denied",
    "web.page_event",
    "web.bootstrap_consumed",
})

ACTOR_TYPES = frozenset({"human", "system"})


class WebAppError(ValueError):
    """A webapp record or operation violated its contract."""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class WebEvent:
    event_type: str
    actor_type: str
    actor_id: str
    web_event_id: str = field(default_factory=new_ulid)
    subject_type: str | None = None
    subject_id: str | None = None
    occurred_at: str = field(default_factory=now_iso)
    recorded_at: str = field(default_factory=now_iso)
    idempotency_key: str | None = None
    schema_version: int = WEBAPP_SCHEMA_VERSION
    payload: dict = field(default_factory=dict)

    def validate(self) -> None:
        if self.event_type not in WEB_EVENTS:
            raise WebAppError(f"unknown event_type: {self.event_type!r}")
        if not is_ulid(self.web_event_id):
            raise WebAppError("web_event_id must be a ULID")
        if self.actor_type not in ACTOR_TYPES:
            raise WebAppError(f"unknown actor_type: {self.actor_type!r}")
        for name in ("actor_id", "occurred_at", "recorded_at"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name):
                raise WebAppError(f"{name} must be non-empty")
        if not isinstance(self.payload, dict):
            raise WebAppError("payload must be a dict")
        try:
            if json.loads(json.dumps(self.payload)) != self.payload:
                raise WebAppError("payload not round-trip safe")
        except (TypeError, ValueError) as exc:
            raise WebAppError(f"payload not JSON-safe: {exc}") from exc
        # A share token must NEVER be stored raw — only its hash.
        flat = json.dumps(self.payload)
        if "share_token_raw" in flat:
            raise WebAppError("raw share tokens must never be persisted")

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_json(cls, line: str) -> "WebEvent":
        data = json.loads(line)
        version = data.get("schema_version")
        if isinstance(version, int) and version > WEBAPP_SCHEMA_VERSION:
            raise WebAppError(
                f"row {data.get('web_event_id')} is schema v{version} > "
                f"supported v{WEBAPP_SCHEMA_VERSION}")
        return cls(**data)

    def content_fingerprint(self) -> str:
        core = {k: v for k, v in asdict(self).items()
                if k not in ("web_event_id", "recorded_at", "occurred_at")}
        return json.dumps(core, sort_keys=True)
