"""Learning read adapter (unified-learning platform).

Lets Personal AI observe and explain the learning pipeline — candidates,
their status, and the paper book's scored metrics — as cited SourceClaims.
It reads through PlatformLearningReader and reinterprets nothing: candidate
state belongs to the Learning Ledger, the metrics to the Paper loop. The
workspace remains read-only over all of it (a Personal-AI test asserts the
service has no write surface into other subsystems).
"""
from __future__ import annotations

from intent_engine.personal.adapters.base import Adapter, unavailable_claim
from intent_engine.personal.records import (
    AVAIL_SUPPORTED, FRESH_CURRENT, SourceClaim, SourceRef,
)


class LearningAdapter(Adapter):
    subsystem = "learning"

    def candidates(self, status=None, limit: int = 20) -> list:
        if not self.available:
            return [unavailable_claim(
                "learning.candidates",
                "the learning ledger is not connected")]
        try:
            rows = self.service.candidates(status=status)
        except Exception as exc:                            # noqa: BLE001
            return [unavailable_claim(
                "learning.candidates",
                f"learning ledger could not be read: {type(exc).__name__}")]
        if not rows:
            return [unavailable_claim(
                "learning.candidates",
                "no learning candidate is recorded"
                + (f" with status {status!r}" if status else ""))]
        claims = []
        for row in rows[:limit]:
            cid = row["id"]
            claims.append(SourceClaim(
                claim_id=f"learning.candidate.{cid}",
                text=f"[{row['status']}] {row['statement']} "
                     f"(source: {row['source']})",
                availability=AVAIL_SUPPORTED,
                source_refs=(SourceRef(
                    subsystem="learning", artifact_type="candidate",
                    artifact_id=cid,
                    replay_id=f"learning:{cid}:{row['created_at']}",
                    as_of=self.as_of, observed_at=row["created_at"],
                    freshness_status=FRESH_CURRENT),),
                transformation="direct", freshness_status=FRESH_CURRENT))
        return claims

    def paper_book(self) -> SourceClaim:
        if not self.available:
            return unavailable_claim("learning.paper_book",
                                     "the learning ledger is not connected")
        metrics = self.service.paper_metrics()
        if not metrics or metrics.get("closed_count", 0) == 0:
            return unavailable_claim(
                "learning.paper_book",
                "the paper-trading book has no closed positions yet")
        return SourceClaim(
            claim_id="learning.paper_book",
            text=(f"paper book: {metrics['closed_count']} closed, "
                  f"total P&L {metrics['total_pnl']:.2f}, "
                  f"win rate {metrics['win_rate']:.0%}, "
                  f"Sharpe {metrics['sharpe']}"),
            availability=AVAIL_SUPPORTED,
            source_refs=(SourceRef(
                subsystem="learning", artifact_type="paper_metrics",
                artifact_id="paper_book",
                replay_id=f"paper_metrics:{self.as_of}", as_of=self.as_of,
                freshness_status=FRESH_CURRENT),),
            transformation="direct", freshness_status=FRESH_CURRENT)

    def explain_candidate(self, candidate_id: str) -> dict:
        if not self.available:
            return {"available": False,
                    "reason": "the learning ledger is not connected"}
        return self.service.explain_candidate(candidate_id)
