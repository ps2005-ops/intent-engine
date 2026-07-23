"""Product read adapter (T023).

Reads the product portfolio rollup and pending reviews. The adapter names
the counts the product subsystem already computed; it does not score,
rank, or roll anything up itself.
"""
from __future__ import annotations

from intent_engine.personal.adapters.base import Adapter, unavailable_claim
from intent_engine.personal.records import (
    AVAIL_SUPPORTED, SourceClaim, SourceRef,
)


class ProductAdapter(Adapter):
    subsystem = "product"

    def portfolio_summary(self, portfolio_id: str) -> list:
        if not self.available:
            return [unavailable_claim("product.portfolio",
                                      "the product subsystem is not connected")]
        try:
            view = self.service.portfolio(portfolio_id, as_of=self.as_of)
        except Exception as exc:                            # noqa: BLE001
            return [unavailable_claim(
                "product.portfolio",
                f"product could not read portfolio {portfolio_id}: "
                f"{type(exc).__name__}")]
        totals = view["rollup"]["totals"]
        replay = f"product:portfolio:{portfolio_id}:{self.as_of}"
        claims = []
        for key in ("opportunities", "proposals", "specs"):
            claims.append(SourceClaim(
                claim_id=f"product.{key}",
                text=f"{totals.get(key, 0)} {key} in the portfolio",
                availability=AVAIL_SUPPORTED,
                source_refs=(SourceRef(
                    subsystem="product", artifact_type="portfolio_rollup",
                    artifact_id=f"{portfolio_id}:{key}", replay_id=replay,
                    as_of=self.as_of),),
                transformation="direct"))
        return claims

    def pending_reviews(self) -> list:
        if not self.available:
            return []
        out = []
        for review in self.service.list_pending_reviews():
            pid = review["proposal_id"]
            out.append({
                "proposal_id": pid,
                "problem_id": review.get("problem_id"),
                "source_ref": SourceRef(
                    subsystem="product", artifact_type="pending_review",
                    artifact_id=pid,
                    replay_id=f"product:review:{pid}:{self.as_of}",
                    as_of=self.as_of).as_dict()})
        return out
