"""Structural diff between two dossiers.

WHY PROSE IS NOT COMPARED
--------------------------
Two analyses of the same unchanged company will phrase themselves differently
every run. A diff that compared sentences would report change constantly, and
a signal that fires always carries no information. So this compares canonical
states and reference ids only — the things that mean something moved.

WHY FIRST_OBSERVATION IS ITS OWN ANSWER
----------------------------------------
A company's first dossier differs from nothing. Reporting that as "everything
changed" would put every company in the 100-company first pass into the
changed bucket, making the second pass's real changes unfindable — and it
would do it while looking like a working diff (§17).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Tuple

from intent_engine.demo_dossier import vocabulary as V
from intent_engine.demo_dossier.dossier import CompanyDemoDossier

CONTRACT = "company_demo_dossier_diff.v1"

#: Top-level canonical fields compared directly.
_SCALARS = ("temporal_compatibility", "population_compatibility",
            "decision_impact_state", "readiness", "quarantined",
            "crossing_state", "coverage_class", "effective_evidence_cutoff",
            "market_runtime_sha", "founder_runtime_sha")

#: Paths into the blocks, as (label, block, key) — states and references, no
#: prose. `reason` and `note` are deliberately absent.
_BLOCK_FIELDS = (
    ("market_availability", "market_block", "availability"),
    ("market_coverage", "market_block", "coverage_state"),
    ("market_contract_state", "market_block", "contract_state"),
    ("market_independence", "market_block", "evidence_independence_state"),
    ("founder_availability", "founder_block", "availability"),
    ("founder_coverage", "founder_block", "coverage_state"),
    ("founder_contract_state", "founder_block", "contract_state"),
    ("recommendation_ref", "founder_block", "recommendation_ref"),
    ("recommendation_standing", "founder_block", "recommendation_standing"),
    ("internal_impact_state", "founder_block", "internal_impact_state"),
    ("internal_graph_availability", "founder_block",
     "internal_graph_availability"),
    ("founder_independence", "founder_block", "evidence_independence_state"),
)


@dataclass(frozen=True)
class DossierDiff:
    state: str = V.FIRST_OBSERVATION
    company_id: str = ""
    from_version: int = 0
    to_version: int = 0
    changed: Tuple[str, ...] = ()
    #: Blocks whose reference set or state moved, named individually so a
    #: reader sees WHICH intelligence moved rather than a count.
    changed_blocks: Tuple[str, ...] = ()

    @property
    def is_first(self) -> bool:
        return self.state == V.FIRST_OBSERVATION

    def as_dict(self) -> dict:
        return {"contract": CONTRACT, "state": self.state,
                "company_id": self.company_id,
                "from_version": self.from_version,
                "to_version": self.to_version,
                "changed": list(self.changed),
                "changed_blocks": list(self.changed_blocks)}


def _block_signature(block: Any) -> dict:
    """A block's comparable shape: its state, its count, and its ids.

    The state is included alongside the ids on purpose. A block that went from
    NOT_ATTEMPTED to AVAILABLE-with-nothing has genuinely changed — somebody
    looked — and comparing ids alone would call that no change.
    """
    blocks = (block or {}).get("blocks") or {}
    return {name: (row.get("state"), row.get("count"),
                   tuple(row.get("ids") or ()))
            for name, row in blocks.items()}


def compare(previous: Optional[CompanyDemoDossier],
            current: CompanyDemoDossier) -> DossierDiff:
    """Compare two dossiers for the same company. Deterministic."""
    if previous is None:
        return DossierDiff(state=V.FIRST_OBSERVATION,
                           company_id=current.company_id,
                           from_version=0,
                           to_version=current.dossier_version)

    changed = [name for name in _SCALARS
               if getattr(previous, name, None) != getattr(current, name, None)]
    for label, block, key in _BLOCK_FIELDS:
        if (getattr(previous, block) or {}).get(key) != \
                (getattr(current, block) or {}).get(key):
            changed.append(label)

    changed_blocks = []
    for side in ("market_block", "founder_block"):
        before = _block_signature(getattr(previous, side))
        after = _block_signature(getattr(current, side))
        for name in sorted(set(before) | set(after)):
            if before.get(name) != after.get(name):
                changed_blocks.append(f"{side.split('_')[0]}.{name}")

    if set(previous.quarantine_reasons) != set(current.quarantine_reasons):
        changed.append("quarantine_reasons")

    if not changed and not changed_blocks:
        return DossierDiff(state=V.NO_CHANGE, company_id=current.company_id,
                           from_version=previous.dossier_version,
                           to_version=current.dossier_version)
    return DossierDiff(state=V.CHANGED, company_id=current.company_id,
                       from_version=previous.dossier_version,
                       to_version=current.dossier_version,
                       changed=tuple(sorted(set(changed))),
                       changed_blocks=tuple(sorted(set(changed_blocks))))
