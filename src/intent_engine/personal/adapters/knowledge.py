"""Knowledge read adapter (T023).

Reads active knowledge items and names them as cited claims. It promotes,
validates, and reinterprets nothing — that all belongs to the knowledge
subsystem's human-gated workflow.
"""
from __future__ import annotations

from intent_engine.personal.adapters.base import Adapter, unavailable_claim
from intent_engine.personal.records import (
    AVAIL_SUPPORTED, SourceClaim, SourceRef, freshness_of,
)


class KnowledgeAdapter(Adapter):
    subsystem = "knowledge"

    def active_items(self, category=None, limit: int = 10) -> list:
        if not self.available:
            return [unavailable_claim("knowledge.items",
                                      "the knowledge subsystem is not connected")]
        try:
            items = self.service.search_knowledge(category=category)
        except Exception as exc:                            # noqa: BLE001
            return [unavailable_claim(
                "knowledge.items",
                f"knowledge could not be read: {type(exc).__name__}")]
        claims = []
        for item in items[:limit]:
            kid = item.get("knowledge_id") or item.get("id") or "unknown"
            observed = item.get("promoted_at") or item.get("created_at")
            fresh = freshness_of(observed, self.as_of)
            claims.append(SourceClaim(
                claim_id=f"knowledge.{kid}",
                text=item.get("title") or item.get("claim") or str(kid),
                availability=AVAIL_SUPPORTED,
                source_refs=(SourceRef(
                    subsystem="knowledge", artifact_type="knowledge_item",
                    artifact_id=str(kid),
                    replay_id=f"knowledge:{kid}:{self.as_of}", as_of=self.as_of,
                    observed_at=observed, freshness_status=fresh),),
                transformation="direct", freshness_status=fresh))
        if not claims:
            return [unavailable_claim("knowledge.items",
                                      "no active knowledge item is recorded")]
        return claims
