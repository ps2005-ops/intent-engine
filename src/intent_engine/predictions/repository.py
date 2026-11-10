"""Durable persistence for company-linked predictions (append-only).

Creation is idempotent on the prediction id; resolution is idempotent on
(id, outcome) — so re-running generation or resolution never duplicates or
double-resolves. Latest-wins folding gives the current state of each prediction.
"""
from __future__ import annotations

from typing import List, Optional

from intent_engine.core.prediction_ledger import Prediction

STREAM = "prediction"


class PredictionRepository:
    def __init__(self, store):
        self.store = store

    def _persist(self, pred: Prediction, *, idem: str) -> Prediction:
        self.store.append(
            STREAM, pred.id, pred.model_dump(mode="json"),
            status=(pred.outcome or "open"), company_id=pred.entity_id,
            ref_id=(pred.instrument or None), idem_key=idem, ts=pred.created_at)
        return pred

    def add(self, pred: Prediction) -> Prediction:
        return self._persist(pred, idem=f"pred:{pred.id}")

    def resolve(self, pred: Prediction) -> Prediction:
        # one resolution row per outcome transition
        return self._persist(pred, idem=f"pred:{pred.id}:{pred.outcome}")

    def get(self, prediction_id: str) -> Optional[Prediction]:
        rec = self.store.get(STREAM, prediction_id)
        return Prediction(**rec.payload) if rec else None

    def all_latest(self) -> List[Prediction]:
        return [Prediction(**r.payload) for r in self.store.latest(STREAM)]

    def by_company(self, company_id: str) -> List[Prediction]:
        return [Prediction(**r.payload)
                for r in self.store.latest(STREAM, company_id=company_id)]

    def unresolved(self) -> List[Prediction]:
        return [p for p in self.all_latest() if p.outcome is None]

    def resolved(self) -> List[Prediction]:
        return [p for p in self.all_latest()
                if p.outcome in ("happened", "did_not_happen")]

    def due(self, as_of: str) -> List[Prediction]:
        """Unresolved predictions whose horizon has completed by `as_of`.
        Catch-up by construction: anything overdue from a skipped run is still
        returned until it is resolved."""
        cutoff = as_of[:10]
        return [p for p in self.unresolved()
                if (p.resolve_by or "")[:10] <= cutoff]
