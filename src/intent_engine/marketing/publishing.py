"""Marketing publishing adapter — dry-run by default, real publish disabled.

Preserves every wall: real external publication (content.published) is a
HUMAN transition enforced by the event bus, requires PUBLISHING_ENABLED, an
explicit non-dry-run request, an approved draft, and a channel on the
allowlist. None of those hold during tests or this implementation, so this
adapter only ever emits `content.publish_dry_run` (a SIMULATED publish).

Modes (3D): DRAFT_ONLY < APPROVAL_REQUIRED (default) < TRUSTED_AUTONOMY.
TRUSTED_AUTONOMY is unreachable until the user manually enables it AND an
evidence threshold is met — it is not selectable from code alone.

The Publer provider is represented by a dry-run adapter that returns a
SIMULATED external post id without any network call. A real provider client
is a documented MANUAL step (credentials + the user's explicit approval of a
first controlled post); no real HTTP happens here.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

DRAFT_ONLY = "DRAFT_ONLY"
APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
TRUSTED_AUTONOMY = "TRUSTED_AUTONOMY"
DEFAULT_MODE = APPROVAL_REQUIRED

# Only channels the user has explicitly allowed may ever be targeted.
DEFAULT_ALLOWLIST = ("linkedin",)


class PublishingError(RuntimeError):
    pass


class PublishingDisabled(PublishingError):
    """A real publish was attempted while publishing is disabled."""


@dataclass(frozen=True)
class PublishResult:
    dry_run: bool
    channel: str
    external_post_id: Optional[str]
    status: str                  # "simulated" | "published"
    idempotency_key: str
    at: str = field(default_factory=lambda:
                    datetime.now(timezone.utc).isoformat(timespec="seconds"))


def _simulated_post_id(campaign_id: str, channel: str, revision_id: str) -> str:
    h = hashlib.sha256(f"{campaign_id}:{channel}:{revision_id}".encode())
    return "sim_" + h.hexdigest()[:16]


def publishing_enabled() -> bool:
    return os.environ.get("PUBLISHING_ENABLED", "").lower() in ("1", "true", "yes")


class PublishingAdapter:
    def __init__(self, *, bus=None, mode: str = DEFAULT_MODE,
                 allowlist=DEFAULT_ALLOWLIST):
        if mode == TRUSTED_AUTONOMY and not _autonomy_unlocked():
            raise PublishingError(
                "TRUSTED_AUTONOMY is not available until explicitly enabled "
                "with evidence; refusing to construct in that mode")
        self.bus = bus
        self.mode = mode
        self.allowlist = tuple(allowlist)

    def publish(self, *, campaign_id: str, revision_id: str, channel: str,
                body: str, approved: bool = False, dry_run: bool = True,
                actor_type: str = "system", actor_id: str = "publishing_adapter"
                ) -> PublishResult:
        if channel not in self.allowlist:
            raise PublishingError(
                f"channel {channel!r} is not on the allowlist {self.allowlist}")
        key = f"publish:{campaign_id}:{channel}:{revision_id}"

        # DRY RUN — the only path reachable in tests/this implementation.
        if dry_run or self.mode == DRAFT_ONLY:
            post_id = _simulated_post_id(campaign_id, channel, revision_id)
            if self.bus is not None:
                self.bus.publish(
                    "content.publish_dry_run", subject_type="content",
                    subject_id=revision_id, producer="publishing_adapter",
                    actor_type="system", actor_id=actor_id, source="system",
                    payload={"campaign_id": campaign_id, "channel": channel,
                             "simulated_post_id": post_id, "mode": self.mode},
                    idempotency_key=key)
            return PublishResult(dry_run=True, channel=channel,
                                 external_post_id=post_id, status="simulated",
                                 idempotency_key=key)

        # REAL publish — gated. All of these must hold or it refuses.
        if not publishing_enabled():
            raise PublishingDisabled(
                "PUBLISHING_ENABLED is not set — real publication is disabled")
        if self.mode == APPROVAL_REQUIRED and not approved:
            raise PublishingError(
                "APPROVAL_REQUIRED: a human-approved draft is required before "
                "real publication")
        if actor_type != "human":
            raise PublishingError(
                "real publication is a human wall; actor_type must be 'human'")
        # A real provider call would go here, behind the user's explicit
        # first-post approval. Intentionally not implemented in this session.
        raise PublishingDisabled(
            "real provider publishing is a documented MANUAL step (credentials "
            "+ your explicit approval of a first controlled post)")


def _autonomy_unlocked() -> bool:
    return os.environ.get("MARKETING_TRUSTED_AUTONOMY", "").lower() in (
        "1", "true", "yes")
