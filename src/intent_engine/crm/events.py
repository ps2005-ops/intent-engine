"""The canonical CRM contract (T014): envelope + taxonomy.

One entity identity: `crm_entity_id`, an opaque ULID minted at
crm.prospect_created. The SAME entity moves prospect -> customer (no
second identity). Name / email / domain are attributes carried in
payloads, never primary keys. External identities are linked explicitly
(crm.identity_linked); duplicate matching is exact-match on linked refs
only — no fuzzy merging, ever. Conflicts require explicit human
resolution.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from intent_engine.core.decision_ids import is_ulid, new_ulid

CRM_SCHEMA_VERSION = 1

# --- the closed taxonomy: only facts a real current workflow produces --------
LIFECYCLE_EVENTS = {
    "crm.prospect_created", "crm.identity_linked", "crm.qualified",
    "crm.disqualified", "crm.contacted", "crm.replied", "crm.meeting_booked",
    "crm.opportunity_opened", "crm.proposal_sent", "crm.won", "crm.lost",
    "crm.customer_activated", "crm.customer_at_risk", "crm.customer_recovered",
    "crm.churned", "crm.note_added", "crm.reopened",
    "crm.owner_assigned", "crm.owner_transferred",
}
DECISION_LINK_EVENTS = {"crm.decision_linked", "crm.report_shared"}
# Written ONLY by the Company Event consumer (observational facts):
CONSUMER_EVENTS = {"crm.decision_activity", "crm.report_generated"}
# The outreach wall: drafting may be automated; sending may not bypass a
# human approval (enforced in service.py; same wall as
# marketing/outreach/tracking_ledger_schema.md).
OUTREACH_EVENTS = {"crm.outreach_drafted", "crm.outreach_approved",
                   "crm.outreach_rejected", "crm.outreach_sent"}
# Reserved privacy path (accepted, audit-only; enforcement is a later
# slice — same pattern as the Decision Record privacy events):
PRIVACY_EVENTS = {"crm.access_restricted", "crm.anonymized", "crm.tombstoned"}

CRM_EVENT_TYPES = (LIFECYCLE_EVENTS | DECISION_LINK_EVENTS | CONSUMER_EVENTS
                   | OUTREACH_EVENTS | PRIVACY_EVENTS)

ACTOR_TYPES = {"human", "agent", "system"}
SOURCES = {"cli", "web_intake", "report_review", "crm", "api", "system",
           "company_event_consumer"}

# Typed decision-link roles (payload field link_type on crm.decision_linked)
DECISION_LINK_TYPES = {"subject", "prospect", "customer", "stakeholder",
                       "champion", "buyer", "recipient"}


class CRMEnvelopeError(ValueError):
    """A CRM event failed envelope validation."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class CRMEvent:
    crm_entity_id: str
    event_type: str
    actor_type: str
    actor_id: str
    source: str
    crm_event_id: str = field(default_factory=new_ulid)
    occurred_at: str = field(default_factory=_now)
    recorded_at: str = field(default_factory=_now)
    company_event_id: str | None = None
    decision_id: str | None = None
    correlation_id: str | None = None
    idempotency_key: str | None = None
    payload_schema_version: int = CRM_SCHEMA_VERSION
    payload: dict = field(default_factory=dict)

    def validate(self) -> None:
        if self.event_type not in CRM_EVENT_TYPES:
            raise CRMEnvelopeError(f"unknown CRM event_type: {self.event_type!r}")
        if not is_ulid(self.crm_event_id):
            raise CRMEnvelopeError("crm_event_id must be a ULID")
        if not is_ulid(self.crm_entity_id):
            raise CRMEnvelopeError("crm_entity_id must be a ULID "
                                   "(opaque identity — never an email)")
        if self.actor_type not in ACTOR_TYPES:
            raise CRMEnvelopeError(f"unknown actor_type: {self.actor_type!r}")
        if self.source not in SOURCES:
            raise CRMEnvelopeError(f"unknown source: {self.source!r}")
        for name in ("actor_id", "occurred_at", "recorded_at"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise CRMEnvelopeError(f"{name} must be a non-empty string")
        if not isinstance(self.payload, dict):
            raise CRMEnvelopeError("payload must be a dict")
        try:
            if json.loads(json.dumps(self.payload)) != self.payload:
                raise CRMEnvelopeError("payload does not survive JSON round-trip")
        except (TypeError, ValueError) as exc:
            raise CRMEnvelopeError(f"payload is not JSON-safe: {exc}") from exc

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_json(cls, line: str) -> "CRMEvent":
        data = json.loads(line)
        version = data.get("payload_schema_version")
        if isinstance(version, int) and version > CRM_SCHEMA_VERSION:
            raise CRMEnvelopeError(
                f"CRM event {data.get('crm_event_id')} schema v{version} > "
                f"supported v{CRM_SCHEMA_VERSION}")
        return cls(**data)

    def content_fingerprint(self) -> str:
        """Logical content locked by an idempotency_key. Timestamps and the
        minted id are excluded: a retry naturally carries a fresh clock but
        MUST carry the same facts."""
        core = {k: v for k, v in asdict(self).items()
                if k not in ("crm_event_id", "recorded_at", "occurred_at")}
        return json.dumps(core, sort_keys=True)
