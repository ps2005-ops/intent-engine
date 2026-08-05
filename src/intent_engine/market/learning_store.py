"""Append-only persistence for beliefs, expectations and evidence.

WHY APPEND-ONLY
---------------
Same reason the asset ledger is: the value of a belief record is the trail, not
the current number. A store that overwrote would answer "what do we believe"
and lose "what changed our mind", and the second question is the one that shows
whether the engine is learning or drifting.

Rebuildable by construction. Every derived view — current posteriors, open
expectations — is a fold over the log, so the projection into the Business
Graph can be regenerated at any time and never becomes a second source of
truth.

A CORRUPT LINE IS SKIPPED, NEVER REPAIRED
-----------------------------------------
Matching `assets.AssetLedger` deliberately. Repairing a malformed row means
editing history, which is precisely what an append-only log exists to prevent.
`health` counts the skips so corruption is visible rather than silent.
"""
from __future__ import annotations

import json
import pathlib
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from . import beliefs as B
from . import expectation as EXP
from . import micro_evidence as ME

DEFAULT_PATH = "reports/market/learning_ledger.jsonl"

BELIEF = "belief"
BELIEF_UPDATE = "belief_update"
EXPECTATION = "expectation"
RECONCILIATION = "reconciliation"
EVIDENCE = "evidence"
CYCLE = "cycle"

RECORD_KINDS = frozenset({BELIEF, BELIEF_UPDATE, EXPECTATION,
                          RECONCILIATION, EVIDENCE, CYCLE})

# What a session actually produced. Recorded as a class, not as a count,
# because "3 things happened" is the sentence this project keeps having to
# take back. A cycle that ingested forty observations and moved nothing is
# NOT a cycle that gained knowledge, and the ledger has to be able to say so
# without a reader doing arithmetic on five other fields.
NEW_KNOWLEDGE = "NEW_KNOWLEDGE"              # a belief was declared
BELIEF_MOVEMENT = "BELIEF_MOVEMENT"          # an existing posterior moved
OBSERVED_NO_IMPACT = "OBSERVED_NO_IMPACT"    # evidence arrived, nothing moved
UNCLASSIFIABLE_INPUT = "UNCLASSIFIABLE_INPUT"  # candidates, no events
NO_NEW_EVIDENCE = "NO_NEW_EVIDENCE"          # nothing arrived at all
OUTCOME_CLASSES = (NEW_KNOWLEDGE, BELIEF_MOVEMENT, OBSERVED_NO_IMPACT,
                   UNCLASSIFIABLE_INPUT, NO_NEW_EVIDENCE)


class LearningStore:
    """The append-only learning log, and folds over it."""

    def __init__(self, path=DEFAULT_PATH):
        self.path = pathlib.Path(path)
        self._corrupt = 0

    # --- writing ----------------------------------------------------------
    def _append(self, record: str, payload: dict) -> None:
        if record not in RECORD_KINDS:
            raise ValueError(f"unknown record kind {record!r}")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        row = dict(payload)
        row["record"] = record
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True, default=str) + "\n")

    def declare_belief(self, belief: B.StrategicBelief) -> bool:
        """Declare a belief once. Returns False if it was already declared.

        Idempotent because the cycle is: a nightly run that re-reads the same
        filings would otherwise append a fresh declaration every night. The
        fold already keeps the first, so the duplicates were invisible in the
        projection and unbounded on disk — the worst combination, because
        nothing would ever have surfaced the growth.
        """
        if belief.belief_id in self.belief_ids():
            return False
        self._append(BELIEF, belief.as_dict())
        return True

    def belief_ids(self) -> frozenset:
        return frozenset(r.get("belief_id") for r in self._rows()
                         if r.get("record") == BELIEF and r.get("belief_id"))

    def record_update(self, belief_id: str,
                      update: B.BeliefUpdate) -> None:
        payload = update.as_dict()
        payload["belief_id"] = belief_id
        self._append(BELIEF_UPDATE, payload)

    def record_expectation(self, e: EXP.ExpectedObservation) -> bool:
        """Preregister once. A re-registered expectation is not a new test."""
        if e.expectation_id in self.expectation_ids():
            return False
        self._append(EXPECTATION, e.as_dict())
        return True

    def expectation_ids(self) -> frozenset:
        return frozenset(r.get("expectation_id") for r in self._rows()
                         if r.get("record") == EXPECTATION
                         and r.get("expectation_id"))

    def record_cycle(self, *, as_of: str, cycle: str, outcome: str,
                     detail: str = "", counts: Optional[dict] = None) -> bool:
        """One row per learning session, saying what class of thing happened.

        Idempotent on (as_of, cycle): a job that fires twice records one
        session, matching every other hosted job's contract. Replayable, and
        the only place the ledger states an interpretation rather than a fact
        — which is why the interpretation is a closed vocabulary.
        """
        if outcome not in OUTCOME_CLASSES:
            raise ValueError(f"unknown outcome class {outcome!r}")
        cycle_id = f"{as_of[:10]}|{cycle}"
        if cycle_id in self.cycle_ids():
            return False
        self._append(CYCLE, {"cycle_id": cycle_id, "as_of": as_of[:10],
                             "cycle": cycle, "outcome": outcome,
                             "detail": detail[:400],
                             "counts": dict(counts or {}),
                             "schema": "learning_cycle_record.v1"})
        return True

    def cycle_ids(self) -> frozenset:
        return frozenset(r.get("cycle_id") for r in self._rows()
                         if r.get("record") == CYCLE and r.get("cycle_id"))

    def cycles(self) -> Tuple[dict, ...]:
        return tuple(r for r in self._rows() if r.get("record") == CYCLE)

    def record_reconciliation(self, r: EXP.Reconciliation) -> None:
        self._append(RECONCILIATION, r.as_dict())

    def record_evidence(self, e: ME.MicroEvidence) -> None:
        self._append(EVIDENCE, e.as_dict())

    # --- reading ----------------------------------------------------------
    def _rows(self) -> List[dict]:
        if not self.path.exists():
            return []
        rows: List[dict] = []
        self._corrupt = 0
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                self._corrupt += 1
                continue
        return rows

    def beliefs(self) -> Tuple[B.StrategicBelief, ...]:
        """Fold declarations and updates into current beliefs.

        Declaration order is preserved; a re-declared belief keeps its
        original prior, because the first prior is the one the trail is
        anchored to.
        """
        declared: Dict[str, dict] = {}
        order: List[str] = []
        updates: Dict[str, List[dict]] = {}
        for row in self._rows():
            kind = row.get("record")
            if kind == BELIEF:
                bid = row.get("belief_id")
                if bid and bid not in declared:
                    declared[bid] = row
                    order.append(bid)
            elif kind == BELIEF_UPDATE:
                bid = row.get("belief_id")
                if bid:
                    updates.setdefault(bid, []).append(row)

        out: List[B.StrategicBelief] = []
        for bid in order:
            row = declared[bid]
            history = tuple(
                B.BeliefUpdate(
                    at=u.get("at", ""), prior=float(u.get("prior", 0.5)),
                    posterior=float(u.get("posterior", 0.5)),
                    method=u.get("method", B.CALIBRATED_HEURISTIC),
                    basis=u.get("basis", ""),
                    evidence_ids=tuple(u.get("evidence_ids") or ()),
                    effective_sample_size=float(
                        u.get("effective_sample_size", 0.0)))
                for u in sorted(updates.get(bid, []),
                                key=lambda u: u.get("at", "")))
            # Declared ids first: evidence that PROPOSED a belief is applied
            # from the moment it is declared, and a reload that forgot them
            # would let the same fact strengthen the belief it created.
            applied = tuple(row.get("applied_evidence_ids") or ()) + tuple(
                e for u in history for e in u.evidence_ids)
            out.append(B.StrategicBelief(
                belief_id=bid, proposition=row.get("proposition", ""),
                subject=row.get("subject", ""),
                prior_probability=float(row.get("prior_probability", 0.5)),
                posterior_probability=(history[-1].posterior if history
                                       else float(row.get(
                                           "posterior_probability", 0.5))),
                last_updated=(history[-1].at if history
                              else row.get("last_updated", "")),
                learning_speed=row.get("learning_speed", B.MEDIUM),
                applied_evidence_ids=applied,
                supporting_evidence_ids=tuple(
                    row.get("supporting_evidence_ids") or ()),
                contradicting_evidence_ids=tuple(
                    row.get("contradicting_evidence_ids") or ()),
                history=history,
                last_validated=row.get("last_validated", ""),
                decay_eligible=bool(row.get("decay_eligible", True)),
                review_interval_days=int(
                    row.get("review_interval_days", 90)),
                confidence_basis=row.get("confidence_basis", ""),
                limitations=tuple(row.get("limitations") or ()),
                lifecycle_state=row.get("lifecycle_state", B.ACTIVE)))
        return tuple(out)

    def open_expectations(self, *, as_of: str
                          ) -> Tuple[EXP.ExpectedObservation, ...]:
        """Preregistered expectations that have not yet been scored.

        Scored means a reconciliation with an INFORMATIVE outcome exists. A
        TOO_EARLY reconciliation deliberately leaves the expectation open —
        it is a note that the window is still running, not a verdict.
        """
        settled = {
            r.get("expectation_id") for r in self._rows()
            if r.get("record") == RECONCILIATION
            and r.get("outcome") in EXP.INFORMATIVE}
        out = []
        for row in self._rows():
            if row.get("record") != EXPECTATION:
                continue
            if row.get("expectation_id") in settled:
                continue
            rng = row.get("expected_range")
            out.append(EXP.ExpectedObservation(
                expectation_id=row.get("expectation_id", ""),
                hypothesis_id=row.get("hypothesis_id", ""),
                subject=row.get("subject", ""),
                expected_event=row.get("expected_event", ""),
                expected_direction=row.get("expected_direction", EXP.FLAT),
                preregistered_at=row.get("preregistered_at", ""),
                evaluation_window_ends=row.get("evaluation_window_ends", ""),
                falsifier=row.get("falsifier", ""),
                metric=row.get("metric", ""),
                evidence_basis=tuple(row.get("evidence_basis") or ()),
                expected_range=tuple(rng) if rng else None,
                relevant_actors=tuple(row.get("relevant_actors") or ()),
                expected_reactions=tuple(row.get("expected_reactions") or ()),
                uncertainty=float(row.get("uncertainty", 0.5))))
        return tuple(out)

    def evidence_ids(self) -> frozenset:
        """Every evidence id ever ingested — the dedup key across cycles."""
        return frozenset(r.get("evidence_id") for r in self._rows()
                         if r.get("record") == EVIDENCE
                         and r.get("evidence_id"))

    def reconciliations(self) -> Tuple[dict, ...]:
        return tuple(r for r in self._rows()
                     if r.get("record") == RECONCILIATION)

    def health(self) -> dict:
        rows = self._rows()
        counts: Dict[str, int] = {}
        for row in rows:
            kind = row.get("record", "unknown")
            counts[kind] = counts.get(kind, 0) + 1
        return {"path": str(self.path), "rows": len(rows),
                "by_record": counts, "corrupt_lines_skipped": self._corrupt,
                "exists": self.path.exists()}
