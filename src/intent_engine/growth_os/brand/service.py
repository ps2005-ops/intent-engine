"""BrandMemoryService (§6) — the only write path for the brand model.

Lifecycle: an agent (or human) PROPOSES a fact; only a HUMAN approves it into
`active`; only a human retires it. `check_consistency(text)` is the gate content
modules call — it flags any active messaging/positioning/claim/value fact whose
declared `contradicts` phrase appears in the text, returning the offending fact
so the conflict is explainable, never a silent block.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from intent_engine.growth_os.foundation import (
    Confidence,
    GrowthOSError,
    IntelRecord,
    IntelStore,
    Provenance,
)
from intent_engine.growth_os.brand.records import (
    BRAND_APPROVED,
    BRAND_FACT_KINDS,
    BRAND_PROPOSED,
    BRAND_RETIRED,
    BRAND_STREAM,
    CONSISTENCY_GATED_KINDS,
    HUMAN_ONLY_BRAND_EVENTS,
)


@dataclass
class BrandConflict:
    fact_id: str
    kind: str
    statement: str
    contradicting_phrase: str


class BrandMemoryService:
    def __init__(self, store: IntelStore):
        self.store = store

    # -- lifecycle ----------------------------------------------------------
    def propose(self, *, kind: str, key: str, statement: str,
                provenance: Provenance, confidence: Confidence,
                contradicts: Optional[list] = None, proof_ref: Optional[str] = None,
                actor: str = "agent") -> IntelRecord:
        """Propose a brand fact. Agents may propose; nothing becomes active
        without a human approval."""
        if kind not in BRAND_FACT_KINDS:
            raise GrowthOSError(f"brand kind {kind!r} not in {sorted(BRAND_FACT_KINDS)}")
        if not (key or "").strip() or not (statement or "").strip():
            raise GrowthOSError("brand fact needs a key and a statement")
        payload = {"kind": kind, "key": key, "statement": statement,
                   "contradicts": list(contradicts or []), "proof_ref": proof_ref}
        rec = IntelRecord(
            stream=BRAND_STREAM, event_type=BRAND_PROPOSED, actor=actor,
            provenance=provenance, confidence=confidence, payload=payload,
            idempotency_key=f"brand:propose:{kind}:{key}")
        return self.store.append(rec)

    def approve(self, *, kind: str, key: str, actor: str,
                provenance: Provenance, confidence: Confidence) -> IntelRecord:
        """HUMAN-ONLY. Promote the proposed fact to active. A messaging/claim
        fact that would contradict an ALREADY-active fact is refused."""
        self._require_human(BRAND_APPROVED, actor)
        proposed = self._latest(kind, key, BRAND_PROPOSED)
        if proposed is None:
            raise GrowthOSError(f"no proposed brand fact {kind}:{key} to approve")
        # never approve messaging that contradicts existing approved messaging
        if kind in CONSISTENCY_GATED_KINDS:
            conflicts = self.check_consistency(proposed.payload["statement"],
                                               exclude_key=key)
            if conflicts:
                c = conflicts[0]
                raise GrowthOSError(
                    f"cannot approve {kind}:{key} — it contradicts active "
                    f"{c.kind} {c.fact_id} ({c.contradicting_phrase!r})")
        rec = IntelRecord(
            stream=BRAND_STREAM, event_type=BRAND_APPROVED, actor=actor,
            provenance=provenance, confidence=confidence,
            payload=dict(proposed.payload),
            idempotency_key=f"brand:approve:{kind}:{key}")
        return self.store.append(rec)

    def retire(self, *, kind: str, key: str, actor: str,
               provenance: Provenance, confidence: Confidence) -> IntelRecord:
        """HUMAN-ONLY. Retire an active fact (append-only: history is kept)."""
        self._require_human(BRAND_RETIRED, actor)
        rec = IntelRecord(
            stream=BRAND_STREAM, event_type=BRAND_RETIRED, actor=actor,
            provenance=provenance, confidence=confidence,
            payload={"kind": kind, "key": key},
            idempotency_key=f"brand:retire:{kind}:{key}")
        return self.store.append(rec)

    @staticmethod
    def _require_human(event_type: str, actor: str) -> None:
        if event_type in HUMAN_ONLY_BRAND_EVENTS and actor != "human":
            raise GrowthOSError(
                f"{event_type} is human-only (got actor={actor!r}) — "
                "agents may propose, only a human approves/retires")

    # -- read model ---------------------------------------------------------
    def _latest(self, kind: str, key: str, event_type: str) -> Optional[IntelRecord]:
        # append order is the causal order (the log is append-only); last wins.
        match = None
        for r in self.store.read_all():
            if (r.event_type == event_type
                    and r.payload.get("kind") == kind and r.payload.get("key") == key):
                match = r
        return match

    def active_facts(self, *, kind: Optional[str] = None) -> list[IntelRecord]:
        """A fact is active iff its LATEST lifecycle event (in append order — the
        causal order of an append-only log) is an approval, not a retirement.
        Order-robust: never depends on same-timestamp ULID tie-breaks."""
        latest: dict = {}      # (kind, key) -> record of its last approve/retire
        for r in self.store.read_all():          # append order == causal order
            if r.event_type in (BRAND_APPROVED, BRAND_RETIRED):
                latest[(r.payload.get("kind"), r.payload.get("key"))] = r
        facts = [r for r in latest.values() if r.event_type == BRAND_APPROVED]
        if kind:
            facts = [r for r in facts if r.payload.get("kind") == kind]
        return facts

    # -- the gate -----------------------------------------------------------
    def check_consistency(self, text: str, *, exclude_key: Optional[str] = None
                          ) -> list[BrandConflict]:
        """Return every active messaging/positioning/claim/value fact whose
        declared `contradicts` phrase appears in `text`. Empty list = consistent.
        Explainable: each conflict names the fact and the phrase."""
        low = (text or "").lower()
        conflicts: list[BrandConflict] = []
        for fact in self.active_facts():
            if fact.payload.get("kind") not in CONSISTENCY_GATED_KINDS:
                continue
            if exclude_key is not None and fact.payload.get("key") == exclude_key:
                continue
            for phrase in fact.payload.get("contradicts", []):
                if phrase and phrase.lower() in low:
                    conflicts.append(BrandConflict(
                        fact_id=fact.record_id, kind=fact.payload["kind"],
                        statement=fact.payload["statement"],
                        contradicting_phrase=phrase))
        return conflicts

    def is_consistent(self, text: str) -> bool:
        return not self.check_consistency(text)
