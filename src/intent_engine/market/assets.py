"""The Research Asset Ledger — durable, cumulative, append-only.

WHAT CHANGED AND WHY
--------------------
Day 15 and 16 kept this ledger as a markdown table maintained by hand. That was
honest but not durable: an unattended system writes to it every night, and a
table a process rewrites has no memory of what it used to say. The specific
loss is CONFIDENCE HISTORY. "Believed at 0.9" is a much weaker statement than
"held at 0.6, raised to 0.9 after the ablation, unchanged since" -- and only
the second one lets a reader judge whether a conclusion has actually been
tested or merely survived.

So the ledger is a log of REVISIONS, and an asset's current state is a fold
over its own history. Nothing is ever mutated in place. Retiring an asset
appends a retirement; it does not delete the belief that preceded it, because
the record of having been wrong is itself a research asset.

KNOWLEDGE DECAY, MECHANISED
---------------------------
Day 16 adopted the principle: *confidence belongs to evidence, not to age.*
This is the machinery. `last_validated` is a required field, contradicting
evidence moves an asset ACCEPTED -> UNDER_REVIEW, and review resolves to
CONFIRMED or RETIRED. An asset cannot sit under review forever without that
being visible, and an old asset that nothing has re-tested is reported as
unvalidated rather than as settled.

WHAT THIS DELIBERATELY DOES NOT DO
----------------------------------
It does not score assets, rank them, or compute an aggregate "knowledge" number
from confidences. A single scalar over heterogeneous beliefs would be a metric
that improves when you add weakly-held assets, which is the Goodhart failure
`METRIC_INTEGRITY.md` exists to prevent.
"""
from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence

# --- asset classes ----------------------------------------------------------
VALIDATED_POSITIVE = "validated_positive"
VALIDATED_NEGATIVE = "validated_negative"
INTEGRITY_FAILURE = "integrity_failure"
MEASUREMENT_TECHNIQUE = "measurement_technique"
ARCHITECTURE_PRINCIPLE = "architecture_principle"
OPERATIONAL_PRINCIPLE = "operational_principle"
UNRESOLVED_FINDING = "unresolved_finding"

CLASSES = frozenset({
    VALIDATED_POSITIVE, VALIDATED_NEGATIVE, INTEGRITY_FAILURE,
    MEASUREMENT_TECHNIQUE, ARCHITECTURE_PRINCIPLE, OPERATIONAL_PRINCIPLE,
    UNRESOLVED_FINDING,
})

# --- statuses ---------------------------------------------------------------
ACCEPTED = "ACCEPTED"
UNDER_REVIEW = "UNDER_REVIEW"
CONFIRMED = "CONFIRMED"
RETIRED = "RETIRED"

STATUSES = frozenset({ACCEPTED, UNDER_REVIEW, CONFIRMED, RETIRED})

# Legal status transitions. A retired asset is terminal: reviving one is the
# thing this project is explicitly forbidden to do, so the ledger cannot
# express it. Reaching the same conclusion again requires a NEW asset with its
# own evidence, which is the honest way to do it -- the old retirement stays
# visible next to it.
_TRANSITIONS = {
    ACCEPTED: {ACCEPTED, UNDER_REVIEW, RETIRED},
    UNDER_REVIEW: {UNDER_REVIEW, CONFIRMED, RETIRED},
    CONFIRMED: {CONFIRMED, UNDER_REVIEW, RETIRED},
    RETIRED: set(),
}

DEFAULT_PATH = "reports/market/research_assets.jsonl"


class LedgerError(ValueError):
    """A revision the ledger refuses to record."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class Revision:
    """One append-only entry. Never edited, never removed.

    `seq` is the revision's position in its asset's history, assigned at write
    time. Order is NOT derived from `at`: timestamps have second resolution, so
    a declaration and a same-cycle revision routinely share one -- which made
    "is this the first revision?" answer yes for both and misfiled a weakening
    as a new finding. Position is a fact about the log; a timestamp is a
    coincidence of how fast the machine ran.
    """
    asset_id: str
    at: str
    status: str
    confidence: float
    reason: str
    evidence: tuple = ()
    sample_size: Optional[int] = None
    effective_sample_size: Optional[int] = None
    cycle_id: str = ""
    seq: int = 0

    def as_dict(self) -> dict:
        return {"asset_id": self.asset_id, "at": self.at,
                "status": self.status, "confidence": self.confidence,
                "reason": self.reason, "evidence": list(self.evidence),
                "sample_size": self.sample_size,
                "effective_sample_size": self.effective_sample_size,
                "cycle_id": self.cycle_id, "seq": self.seq}


@dataclass(frozen=True)
class Asset:
    """The folded current state of one asset, plus its whole history."""
    asset_id: str
    title: str
    asset_class: str
    claim: str
    scope: str = ""
    limitations: str = ""
    contradiction_conditions: str = ""
    impact: str = ""
    first_observed: str = ""
    revisions: tuple = ()

    @property
    def status(self) -> str:
        return self.revisions[-1].status if self.revisions else ACCEPTED

    @property
    def confidence(self) -> Optional[float]:
        return self.revisions[-1].confidence if self.revisions else None

    @property
    def previous_confidence(self) -> Optional[float]:
        return self.revisions[-2].confidence if len(self.revisions) > 1 else None

    @property
    def last_validated(self) -> str:
        return self.revisions[-1].at if self.revisions else self.first_observed

    @property
    def still_believed(self) -> bool:
        return self.status in (ACCEPTED, CONFIRMED)

    @property
    def under_review_reason(self) -> str:
        return (self.revisions[-1].reason
                if self.revisions and self.status == UNDER_REVIEW else "")

    @property
    def retired_reason(self) -> str:
        return (self.revisions[-1].reason
                if self.revisions and self.status == RETIRED else "")

    @property
    def revalidated(self) -> bool:
        """Has anything tested this since it was first established?

        One revision means "asserted once and never revisited". The ledger
        reports that rather than letting age pass for confirmation.
        """
        return len(self.revisions) > 1

    def as_dict(self) -> dict:
        return {
            "asset_id": self.asset_id, "title": self.title,
            "class": self.asset_class, "claim": self.claim,
            "status": self.status, "confidence": self.confidence,
            "previous_confidence": self.previous_confidence,
            "first_observed": self.first_observed,
            "last_validated": self.last_validated,
            "still_believed": self.still_believed,
            "revalidated": self.revalidated,
            "scope": self.scope, "limitations": self.limitations,
            "contradiction_conditions": self.contradiction_conditions,
            "impact": self.impact,
            "under_review_reason": self.under_review_reason,
            "retired_reason": self.retired_reason,
            "evidence": list(self.revisions[-1].evidence)
                        if self.revisions else [],
            "sample_size": self.revisions[-1].sample_size
                           if self.revisions else None,
            "effective_sample_size": self.revisions[-1].effective_sample_size
                                     if self.revisions else None,
            "revision_history": [r.as_dict() for r in self.revisions],
        }


class AssetLedger:
    """Append-only JSONL. Two record types: `asset` (declaration, once) and
    `revision` (status/confidence change, many)."""

    def __init__(self, path=DEFAULT_PATH):
        self.path = pathlib.Path(path)

    # --- reading ------------------------------------------------------------
    def _rows(self) -> List[dict]:
        if not self.path.exists():
            return []
        rows = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                # A corrupt line is skipped, never silently repaired. Repairing
                # it would edit history, which is the one thing this file is
                # for. `health` counts these so a corruption is visible.
                continue
        return rows

    def all(self) -> List[Asset]:
        """Fold the log into current assets, in declaration order."""
        declared: Dict[str, dict] = {}
        order: List[str] = []
        revisions: Dict[str, List[Revision]] = {}
        for row in self._rows():
            kind = row.get("record")
            if kind == "asset":
                aid = row.get("asset_id")
                if aid and aid not in declared:
                    declared[aid] = row
                    order.append(aid)
            elif kind == "revision":
                aid = row.get("asset_id")
                if not aid:
                    continue
                revisions.setdefault(aid, []).append(Revision(
                    asset_id=aid, at=row.get("at", ""),
                    status=row.get("status", ACCEPTED),
                    confidence=row.get("confidence"),
                    reason=row.get("reason", ""),
                    evidence=tuple(row.get("evidence") or ()),
                    sample_size=row.get("sample_size"),
                    effective_sample_size=row.get("effective_sample_size"),
                    cycle_id=row.get("cycle_id", ""),
                    seq=row.get("seq", len(revisions.get(aid, ())))))
        out = []
        for aid in order:
            row = declared[aid]
            out.append(Asset(
                asset_id=aid, title=row.get("title", ""),
                asset_class=row.get("class", UNRESOLVED_FINDING),
                claim=row.get("claim", ""), scope=row.get("scope", ""),
                limitations=row.get("limitations", ""),
                contradiction_conditions=row.get("contradiction_conditions", ""),
                impact=row.get("impact", ""),
                first_observed=row.get("first_observed", ""),
                revisions=tuple(revisions.get(aid, ()))))
        return out

    def get(self, asset_id: str) -> Optional[Asset]:
        for asset in self.all():
            if asset.asset_id == asset_id:
                return asset
        return None

    # --- writing ------------------------------------------------------------
    def _append(self, row: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True, default=str) + "\n")

    def declare(self, *, asset_id: str, title: str, asset_class: str,
                claim: str, confidence: float, first_observed: str,
                evidence: Sequence[str] = (), scope: str = "",
                limitations: str = "", contradiction_conditions: str = "",
                impact: str = "", sample_size: Optional[int] = None,
                effective_sample_size: Optional[int] = None,
                cycle_id: str = "") -> Asset:
        """Declare an asset and record its first revision. Idempotent: a
        second declaration of the same id returns the existing asset rather
        than duplicating it, so a cycle that reruns does not fork history."""
        if asset_class not in CLASSES:
            raise LedgerError(f"unknown asset class {asset_class!r}")
        existing = self.get(asset_id)
        if existing is not None:
            return existing
        self._append({"record": "asset", "asset_id": asset_id, "title": title,
                      "class": asset_class, "claim": claim, "scope": scope,
                      "limitations": limitations,
                      "contradiction_conditions": contradiction_conditions,
                      "impact": impact, "first_observed": first_observed,
                      "at": _now()})
        self.revise(asset_id=asset_id, status=ACCEPTED, confidence=confidence,
                    reason="first established", evidence=evidence,
                    sample_size=sample_size,
                    effective_sample_size=effective_sample_size,
                    cycle_id=cycle_id)
        return self.get(asset_id)

    def revise(self, *, asset_id: str, status: str, confidence: float,
               reason: str, evidence: Sequence[str] = (),
               sample_size: Optional[int] = None,
               effective_sample_size: Optional[int] = None,
               cycle_id: str = "", at: Optional[str] = None) -> Revision:
        """Append a revision. Validates the transition; never edits history."""
        if status not in STATUSES:
            raise LedgerError(f"unknown status {status!r}")
        if not reason:
            raise LedgerError("a revision must state its reason")
        asset = self.get(asset_id)
        if asset is None:
            raise LedgerError(f"unknown asset {asset_id!r}; declare it first")
        current = asset.status
        if asset.revisions and status not in _TRANSITIONS[current]:
            raise LedgerError(
                f"{asset_id}: {current} -> {status} is not a legal transition"
                + (" (a retired asset is never revived; establish a new asset)"
                   if current == RETIRED else ""))
        revision = Revision(asset_id=asset_id, at=at or _now(), status=status,
                            confidence=confidence, reason=reason,
                            evidence=tuple(evidence),
                            sample_size=sample_size,
                            effective_sample_size=effective_sample_size,
                            cycle_id=cycle_id, seq=len(asset.revisions))
        row = revision.as_dict()
        row["record"] = "revision"
        self._append(row)
        return revision

    # --- reporting ----------------------------------------------------------
    def summary(self) -> dict:
        assets = self.all()
        by_status: Dict[str, int] = {}
        by_class: Dict[str, int] = {}
        for asset in assets:
            by_status[asset.status] = by_status.get(asset.status, 0) + 1
            by_class[asset.asset_class] = by_class.get(asset.asset_class, 0) + 1
        return {"total": len(assets), "by_status": by_status,
                "by_class": by_class,
                "still_believed": sum(1 for a in assets if a.still_believed),
                "never_revalidated": [a.asset_id for a in assets
                                      if not a.revalidated]}


@dataclass(frozen=True)
class ResearchVelocity:
    """What a cycle actually learned. Zero is a legitimate value.

    Extends the Day 16 metric with the review lifecycle. The net calculation is
    stated explicitly below because an implicit one invites quiet reweighting
    the day the number is disappointing.
    """
    new_positive: int = 0
    new_negative: int = 0
    strengthened: int = 0
    weakened: int = 0
    placed_under_review: int = 0
    confirmed: int = 0
    retired: int = 0
    integrity_failures_found: int = 0
    techniques_adopted: int = 0
    hypotheses_retired: int = 0

    @property
    def net_knowledge_gain(self) -> int:
        """NET = (new_positive + new_negative + strengthened + confirmed
                  + integrity_failures_found + techniques_adopted)
                 - (weakened + placed_under_review)

        Three deliberate choices:

        * A validated NEGATIVE counts the same as a positive. Ruling something
          out is knowledge, and a system that scored only positives would be
          rewarded for never testing anything it might lose.
        * `weakened` and `placed_under_review` SUBTRACT. A day that undermines
          a held conclusion leaves the project knowing less than it thought,
          and recording that as progress because an event occurred is the
          exact accounting trick this metric exists to refuse.
        * `retired` is NEUTRAL -- it neither adds nor subtracts. The knowledge
          was already booked when the asset was placed under review; counting
          the retirement too would pay twice for one discovery, and counting it
          negatively would punish the ledger for finishing its own process.
        """
        gained = (self.new_positive + self.new_negative + self.strengthened
                  + self.confirmed + self.integrity_failures_found
                  + self.techniques_adopted)
        lost = self.weakened + self.placed_under_review
        return gained - lost

    def as_dict(self) -> dict:
        return {"new_positive": self.new_positive,
                "new_negative": self.new_negative,
                "strengthened": self.strengthened,
                "weakened": self.weakened,
                "placed_under_review": self.placed_under_review,
                "confirmed": self.confirmed, "retired": self.retired,
                "integrity_failures_found": self.integrity_failures_found,
                "techniques_adopted": self.techniques_adopted,
                "hypotheses_retired": self.hypotheses_retired,
                "net_knowledge_gain": self.net_knowledge_gain}

    def render(self) -> str:
        lines = []
        for key, value in self.as_dict().items():
            label = key.replace("_", " ")
            fmt = f"{value:>+4}" if key == "net_knowledge_gain" else f"{value:>4}"
            lines.append(f"  {label:<28}{fmt}")
        if self.net_knowledge_gain == 0:
            lines.append("\n  NO NEW KNOWLEDGE — a legitimate result, recorded "
                         "as such rather than padded.")
        return "\n".join(lines)


def velocity_from_revisions(revisions: Sequence[Revision],
                            ledger: AssetLedger) -> ResearchVelocity:
    """Derive velocity from what was actually appended this cycle.

    Derived rather than hand-entered so the number cannot drift from the
    ledger it claims to summarise.
    """
    by_id = {a.asset_id: a for a in ledger.all()}
    counts = {"new_positive": 0, "new_negative": 0, "strengthened": 0,
              "weakened": 0, "placed_under_review": 0, "confirmed": 0,
              "retired": 0, "integrity_failures_found": 0,
              "techniques_adopted": 0}
    for revision in revisions:
        asset = by_id.get(revision.asset_id)
        if revision.seq == 0 and asset is not None:
            cls = asset.asset_class
            if cls == VALIDATED_NEGATIVE:
                counts["new_negative"] += 1
            elif cls == INTEGRITY_FAILURE:
                counts["integrity_failures_found"] += 1
            elif cls == MEASUREMENT_TECHNIQUE:
                counts["techniques_adopted"] += 1
            else:
                counts["new_positive"] += 1
            continue
        if revision.status == UNDER_REVIEW:
            counts["placed_under_review"] += 1
        elif revision.status == CONFIRMED:
            counts["confirmed"] += 1
        elif revision.status == RETIRED:
            counts["retired"] += 1
        elif asset is not None:
            prior = asset.previous_confidence
            if prior is not None and revision.confidence is not None:
                if revision.confidence > prior:
                    counts["strengthened"] += 1
                elif revision.confidence < prior:
                    counts["weakened"] += 1
    return ResearchVelocity(**counts)
