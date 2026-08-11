"""`CompanyDemoDossier` — the materialized view, and its exact round trip.

WHY THE BLOCKS ARE PLAIN DICTS
-------------------------------
Persistence and reload must produce a dossier that is semantically identical
to the one assembled in the first process (§15). The cheapest way to be sure
of that is for the in-memory shape and the serialized shape to be the same
shape, so a block is a dict on both sides and `from_dict(as_dict(d)) == d`
holds structurally rather than by careful field-by-field agreement.

WHY THE IDENTITY IS CONTENT-ADDRESSED
--------------------------------------
§14 wants two things that pull against each other: assembling the same inputs
twice must not create a second semantic record, and any changed input must
create a new version. A content hash over the canonical inputs gives both. It
deliberately covers the runtime SHAs and the evidence window as well as the
references — a dossier built from the same refs by different code, or over a
different window, is not the same dossier, and this program has already been
bitten by a content hash that quietly folded distinct records together.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional, Tuple

from intent_engine.demo_dossier import vocabulary as V

CONTRACT = "company_demo_dossier.v1"


@dataclass(frozen=True)
class CompanyDemoDossier:
    """One company, as two systems of record described it, joined and stated.

    This object references. It does not conclude. Every field is either a
    canonical id from one of the two stores, a state one of them declared, or
    metadata about the JOIN itself — which is the only thing the neutral side
    is entitled to derive.
    """
    contract_version: str = CONTRACT
    dossier_id: str = ""
    #: Monotonic per company, assigned on persist. 1 is the first observation.
    dossier_version: int = 0

    company_id: str = ""
    canonical_name: str = ""
    domain: str = ""
    ticker: str = ""

    cohort: str = V.FIELD_UNAVAILABLE
    coverage_class: str = V.FIELD_UNAVAILABLE

    generated_at: str = ""

    market_snapshot_id: str = ""
    founder_snapshot_id: str = ""
    market_runtime_sha: str = ""
    founder_runtime_sha: str = ""
    market_known_at: str = ""
    founder_known_at: str = ""
    #: The OLDER of the two cutoffs when both are known. A joint reading can
    #: only honestly claim to see as far as its blinder side.
    effective_evidence_cutoff: str = ""

    market_block: Dict[str, Any] = field(default_factory=dict)
    founder_block: Dict[str, Any] = field(default_factory=dict)
    product_block: Dict[str, Any] = field(default_factory=dict)
    quality_block: Dict[str, Any] = field(default_factory=dict)

    temporal_compatibility: str = V.WINDOW_UNKNOWN
    population_compatibility: str = V.POPULATION_UNKNOWN
    #: A synthetic or mixed join must carry this wherever it is shown.
    synthetic_label: str = ""

    decision_impact_state: str = V.IMPACT_UNAVAILABLE
    readiness: str = V.NOT_STARTED
    quarantined: bool = False
    quarantine_reasons: Tuple[str, ...] = ()

    #: The combined-crossing state, reported rather than hidden (§34). Both
    #: sides present is the only value that means the bridge actually opened.
    crossing_state: str = ""

    @property
    def market_available(self) -> bool:
        return self.market_block.get("availability") in V.HAS_CONTENT_STATES

    @property
    def founder_available(self) -> bool:
        return self.founder_block.get("availability") in V.HAS_CONTENT_STATES

    def content_key(self) -> str:
        """A stable digest of everything that makes this dossier THIS one.

        Excludes `dossier_version` and `generated_at`: a version number is
        assigned by the store after the key is computed, and a wall clock that
        entered the key would make every re-assembly a new record — which is
        precisely the idempotence §14 asks for.
        """
        payload = {
            "company_id": self.company_id,
            "market_snapshot_id": self.market_snapshot_id,
            "founder_snapshot_id": self.founder_snapshot_id,
            "market_runtime_sha": self.market_runtime_sha,
            "founder_runtime_sha": self.founder_runtime_sha,
            "effective_evidence_cutoff": self.effective_evidence_cutoff,
            "market_block": self.market_block,
            "founder_block": self.founder_block,
            "product_block": self.product_block,
            "quality_block": self.quality_block,
            "temporal_compatibility": self.temporal_compatibility,
            "population_compatibility": self.population_compatibility,
            "decision_impact_state": self.decision_impact_state,
            "readiness": self.readiness,
            "quarantined": self.quarantined,
            "quarantine_reasons": list(self.quarantine_reasons),
            "crossing_state": self.crossing_state,
        }
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def as_dict(self) -> dict:
        out = asdict(self)
        out["quarantine_reasons"] = list(self.quarantine_reasons)
        out["content_key"] = self.content_key()
        return out

    @classmethod
    def from_dict(cls, payload: Any) -> Optional["CompanyDemoDossier"]:
        """Reload. Returns None rather than a half-built dossier: a reader
        that cannot reconstruct the record must not present a partial one as
        the record."""
        if not isinstance(payload, dict):
            return None
        known = {f for f in cls.__dataclass_fields__}
        kwargs = {k: v for k, v in payload.items() if k in known}
        kwargs["quarantine_reasons"] = tuple(
            payload.get("quarantine_reasons") or ())
        try:
            return cls(**kwargs)
        except TypeError:
            return None
