"""The canonical Growth-OS contract: provenance, confidence, the event
envelope, and the learning candidate. Pure, deterministic, offline.

Design rules made structural (unrepresentable-if-broken, not just documented):

  * A record with NO provenance cannot be constructed (Provenance is required).
  * `Provenance.method` names the PERMITTED access path (api/rss/export/manual/
    synthetic) — there is no "scrape" method, so a ToS-violating source is not
    expressible here.
  * A `Confidence` needs a `basis` string — a number with no stated reason is
    rejected (no black-box).
  * `content_fingerprint()` excludes the wall-clock `recorded_at` so re-recording
    the same fact a second later is idempotent, never a spurious conflict (the
    same lesson already load-bearing in storage.durable).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from intent_engine.core.decision_ids import is_ulid, new_ulid

GROWTH_OS_SCHEMA_VERSION = 1

ACTOR_TYPES = {"human", "agent", "system"}

# The ONLY ways a record may have been obtained. There is deliberately no
# "scrape" — §3/§19 forbid violating platform terms, so it cannot be named.
PROVENANCE_METHODS = {"api", "rss", "export", "manual", "synthetic", "derived"}


class GrowthOSError(ValueError):
    """Any Growth-OS contract violation — raised loudly, never guessed around."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --- provenance --------------------------------------------------------------

@dataclass(frozen=True)
class Provenance:
    """WHERE a record came from and HOW it was obtained (a permitted path)."""
    source: str                       # e.g. "reddit", "google_trends", "manual"
    method: str                       # one of PROVENANCE_METHODS
    uri: Optional[str] = None         # the specific resource, when there is one
    license: Optional[str] = None     # terms under which it may be used
    retrieved_at: str = field(default_factory=_now)

    def validate(self) -> "Provenance":
        if not self.source:
            raise GrowthOSError("provenance.source is required")
        if self.method not in PROVENANCE_METHODS:
            raise GrowthOSError(
                f"provenance.method {self.method!r} not permitted "
                f"(allowed: {sorted(PROVENANCE_METHODS)})")
        return self


# --- confidence --------------------------------------------------------------

@dataclass(frozen=True)
class Confidence:
    """A number in [0,1] AND the reason for it. No basis -> rejected."""
    value: float
    basis: str

    def validate(self) -> "Confidence":
        if not (0.0 <= float(self.value) <= 1.0):
            raise GrowthOSError(f"confidence.value {self.value!r} not in [0,1]")
        if not (self.basis or "").strip():
            raise GrowthOSError("confidence.basis is required (no black-box numbers)")
        return self


# --- the event envelope ------------------------------------------------------

@dataclass
class IntelRecord:
    """One immutable Growth-OS event. Provenance + confidence are mandatory."""
    stream: str
    event_type: str
    actor: str                        # human | agent | system
    provenance: Provenance
    confidence: Confidence
    payload: dict = field(default_factory=dict)
    observed_at: str = field(default_factory=_now)   # when it was true in the world
    recorded_at: str = field(default_factory=_now)   # when we wrote it (volatile)
    record_id: str = field(default_factory=new_ulid)
    idempotency_key: Optional[str] = None
    schema_version: int = GROWTH_OS_SCHEMA_VERSION

    def validate(self) -> "IntelRecord":
        if not self.stream:
            raise GrowthOSError("stream is required")
        if not self.event_type:
            raise GrowthOSError("event_type is required")
        if self.actor not in ACTOR_TYPES:
            raise GrowthOSError(f"actor {self.actor!r} not in {sorted(ACTOR_TYPES)}")
        if not is_ulid(self.record_id):
            raise GrowthOSError(f"record_id {self.record_id!r} is not a ULID")
        self.provenance.validate()
        self.confidence.validate()
        return self

    def content_fingerprint(self) -> str:
        """Identity for idempotency: everything EXCEPT the wall-clock
        `recorded_at` (re-recording the same fact must dedupe, not conflict)."""
        core = {
            "stream": self.stream, "event_type": self.event_type,
            "actor": self.actor, "payload": self.payload,
            "observed_at": self.observed_at,
            "provenance": asdict(self.provenance),
            "confidence": asdict(self.confidence),
            "schema_version": self.schema_version,
        }
        core["provenance"].pop("retrieved_at", None)   # also a write-time stamp
        blob = json.dumps(core, sort_keys=True, default=str)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def to_json(self) -> str:
        d = asdict(self)
        return json.dumps(d, sort_keys=True, default=str)

    @classmethod
    def from_json(cls, line: str) -> "IntelRecord":
        try:
            d = json.loads(line)
            prov = Provenance(**d.pop("provenance"))
            conf = Confidence(**d.pop("confidence"))
            return cls(provenance=prov, confidence=conf, **d)
        except (TypeError, KeyError, json.JSONDecodeError) as exc:
            raise GrowthOSError(f"malformed IntelRecord: {exc}") from exc


# --- learning candidate (bridges to the existing Learning Ledger) ------------

CANDIDATE_STATES = {"proposed", "accepted", "rejected"}
# Only a human moves a candidate out of 'proposed' — nothing self-promotes.
HUMAN_ONLY_CANDIDATE_STATES = {"accepted", "rejected"}


@dataclass
class LearningCandidate:
    """A proposed improvement with its evidence. Starts 'proposed'; only a human
    accepts/rejects it (§15/§19). Mirrors the growth_studio candidate shape."""
    statement: str
    success_metric: str
    evidence: list = field(default_factory=list)      # IntelRecord ids
    confidence: Optional[Confidence] = None
    proposed_by: str = "agent"
    status: str = "proposed"
    candidate_id: str = field(default_factory=new_ulid)
    created_at: str = field(default_factory=_now)

    def validate(self) -> "LearningCandidate":
        for f in ("statement", "success_metric"):
            if not (getattr(self, f) or "").strip():
                raise GrowthOSError(f"LearningCandidate.{f} is required")
        if not self.evidence:
            raise GrowthOSError("LearningCandidate needs at least one evidence id")
        if self.status not in CANDIDATE_STATES:
            raise GrowthOSError(f"status {self.status!r} not in {sorted(CANDIDATE_STATES)}")
        if self.confidence is not None:
            self.confidence.validate()
        return self

    def with_decision(self, status: str, *, actor: str) -> "LearningCandidate":
        """Human-only accept/reject. An agent/system caller is refused."""
        if status in HUMAN_ONLY_CANDIDATE_STATES and actor != "human":
            raise GrowthOSError(
                f"only a human may set candidate status {status!r} (got actor={actor!r})")
        if status not in CANDIDATE_STATES:
            raise GrowthOSError(f"status {status!r} not in {sorted(CANDIDATE_STATES)}")
        self.status = status
        return self
