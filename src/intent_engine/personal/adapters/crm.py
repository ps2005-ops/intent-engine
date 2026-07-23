"""CRM read adapter (T023).

Reads customer health/conversion signals for a given entity. The signal is
computed by `crm/signals.py`; the adapter names the category it returned
and attaches provenance. It derives no signal of its own.
"""
from __future__ import annotations

from intent_engine.personal.adapters.base import Adapter, unavailable_claim
from intent_engine.personal.records import (
    AVAIL_SUPPORTED, AVAIL_UNAVAILABLE, SourceClaim, SourceRef,
)


class CRMAdapter(Adapter):
    subsystem = "crm"

    def health(self, crm_entity_id: str) -> SourceClaim:
        if not self.available:
            return unavailable_claim("crm.health",
                                     "the CRM subsystem is not connected")
        try:
            signal = self.service.get_health(crm_entity_id, now=self.as_of)
        except Exception as exc:                            # noqa: BLE001
            return unavailable_claim(
                "crm.health",
                f"CRM could not read entity {crm_entity_id}: "
                f"{type(exc).__name__}")
        category = signal.get("category", "UNKNOWN")
        availability = (AVAIL_UNAVAILABLE if category == "UNKNOWN"
                        else AVAIL_SUPPORTED)
        return SourceClaim(
            claim_id=f"crm.health.{crm_entity_id}",
            text=f"customer {crm_entity_id} health is {category}"
                 + (f" ({'; '.join(signal.get('reasons', []))})"
                    if signal.get("reasons") else ""),
            availability=availability,
            source_refs=(SourceRef(
                subsystem="crm", artifact_type="health_signal",
                artifact_id=crm_entity_id,
                replay_id=f"crm:health:{crm_entity_id}:{self.as_of}",
                as_of=self.as_of,
                snapshot_version=str(signal.get("rule_version"))),) if
                availability == AVAIL_SUPPORTED else (),
            transformation="direct")
