"""Durable, versioned persistence for the CompanyPredictionUniverse.

Each SAVE writes an immutable universe version (idempotent on version+label) to
the durable store, plus a "current pointer" row so a fresh runner can load the
active universe deterministically. Older versions are retained (append-only) so
a past day's predictions can be interpreted against the universe as it was.
"""
from __future__ import annotations

from typing import List, Optional

from intent_engine.universe.companies import CompanyPredictionUniverse

STREAM = "company_universe"
POINTER_STREAM = "company_universe_current"
POINTER_ID = "current"


class UniverseStore:
    def __init__(self, store):
        self.store = store

    def save(self, universe: CompanyPredictionUniverse, *, make_current: bool = True
             ) -> CompanyPredictionUniverse:
        universe.validate()
        rec_id = f"{universe.version}:{universe.label}"
        self.store.append(STREAM, rec_id, universe.model_dump(),
                          status="saved", idem_key=f"universe:{rec_id}",
                          ts=universe.created_at)
        if make_current:
            # pointer is mutable-by-append: newest row wins
            self.store.append(POINTER_STREAM, POINTER_ID, {"active": rec_id},
                             status="current")
        return universe

    def load(self, version_label: Optional[str] = None
             ) -> Optional[CompanyPredictionUniverse]:
        if version_label is None:
            ptr = self.store.get(POINTER_STREAM, POINTER_ID)
            if ptr is None:
                return None
            version_label = ptr.payload["active"]
        rec = self.store.get(STREAM, version_label)
        return CompanyPredictionUniverse(**rec.payload) if rec else None

    def load_or_seed(self, seed: CompanyPredictionUniverse
                     ) -> CompanyPredictionUniverse:
        """Load the active universe, seeding it on first run. This is what a job
        calls: idempotent, so the seed is written once and reused thereafter."""
        current = self.load()
        if current is not None:
            return current
        return self.save(seed)

    def versions(self) -> List[str]:
        return [r.record_id for r in self.store.latest(STREAM)]
