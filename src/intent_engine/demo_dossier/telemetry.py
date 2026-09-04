"""What the join actually did, counted.

WHY THIS EXISTS AT ALL
-----------------------
The 22-dossier incident was not caused by a missing guard. The guard worked
perfectly and refused every dossier; what was missing was a number that said
so. A refusal degraded to "no strategic section", which is also how a company
nobody has analysed looks, and the two stayed indistinguishable until
consumption telemetry was built and found it on its first run.

So this is not reporting furniture. `snapshots_refused` and
`unknown_fields_seen` are the two counters that would have caught it, and
they are separated from `snapshots_unavailable` for exactly that reason: a
producer this side refuses and a producer that never published must never
increment the same number.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Dict

from intent_engine.demo_dossier import vocabulary as V
from intent_engine.demo_dossier.assembler import (
    CROSSING_BOTH, CROSSING_FOUNDER_ONLY, CROSSING_MARKET_ONLY)
from intent_engine.demo_dossier.contracts import (FounderDemoSnapshot,
                                                  MarketDemoSnapshot)
from intent_engine.demo_dossier.dossier import CompanyDemoDossier

CONTRACT = "demo_dossier_telemetry.v1"


@dataclass
class DossierTelemetry:
    """In-memory counters over one process's assemblies."""
    counts: Counter = field(default_factory=Counter)
    quarantine_reasons: Counter = field(default_factory=Counter)
    unknown_fields: Counter = field(default_factory=Counter)

    def snapshot_read(self, snapshot) -> None:
        side = ("market" if isinstance(snapshot, MarketDemoSnapshot)
                else "founder")
        self.counts[f"{side}_snapshots_read"] += 1
        if snapshot.availability == V.AVAILABLE:
            self.counts[f"{side}_snapshots_available"] += 1
        elif snapshot.availability == V.REFUSED:
            # NOT the same number as "unavailable". Conflating them is the
            # defect this module exists to make impossible.
            self.counts[f"{side}_snapshots_refused"] += 1
        elif snapshot.availability == V.INCOMPATIBLE:
            self.counts[f"{side}_snapshots_incompatible"] += 1
        elif snapshot.availability == V.STALE:
            self.counts[f"{side}_snapshots_stale"] += 1
        else:
            self.counts[f"{side}_snapshots_unavailable"] += 1
        if snapshot.contract_state == V.OLDER_SUPPORTED:
            self.counts[f"{side}_snapshots_older_contract"] += 1
        for name in snapshot.unknown_fields:
            self.counts["unknown_fields_seen"] += 1
            self.unknown_fields[f"{side}.{name}"] += 1

    def assembled(self, dossier: CompanyDemoDossier) -> None:
        self.counts["dossiers_assembled"] += 1
        self.counts[f"crossing_{dossier.crossing_state}"] += 1
        if dossier.crossing_state == CROSSING_BOTH:
            self.counts["dossiers_rich"] += 1
        elif dossier.crossing_state in (CROSSING_FOUNDER_ONLY,
                                        CROSSING_MARKET_ONLY):
            self.counts["dossiers_partial"] += 1
        else:
            self.counts["dossiers_sparse"] += 1
        if dossier.crossing_state == CROSSING_FOUNDER_ONLY:
            self.counts["market_unavailable"] += 1
        if dossier.crossing_state == CROSSING_MARKET_ONLY:
            self.counts["founder_unavailable"] += 1
        if dossier.quarantined:
            self.counts["dossiers_quarantined"] += 1
            for reason in dossier.quarantine_reasons:
                self.quarantine_reasons[reason] += 1
        if dossier.temporal_compatibility in (V.DIFFERENT_WINDOW,
                                              V.WINDOW_UNKNOWN):
            self.counts["temporal_mismatch"] += 1
        if dossier.population_compatibility in (V.POPULATION_REFUSED,
                                                V.POPULATION_UNKNOWN):
            self.counts["population_mismatch"] += 1
        if V.CONTRACT_INCOMPATIBLE in (
                dossier.market_block.get("contract_state"),
                dossier.founder_block.get("contract_state")):
            self.counts["contract_mismatch"] += 1
        self.counts[f"readiness_{dossier.readiness}"] += 1

    def persisted(self, created: bool) -> None:
        self.counts["dossiers_persisted" if created
                    else "dossiers_idempotent_repeat"] += 1

    def reloaded(self, count: int = 1) -> None:
        self.counts["dossiers_reloaded"] += count

    def differed(self, state: str) -> None:
        self.counts[f"diff_{state}"] += 1

    def as_dict(self) -> Dict[str, object]:
        return {"contract": CONTRACT,
                "counts": dict(sorted(self.counts.items())),
                "quarantine_reasons": dict(sorted(
                    self.quarantine_reasons.items())),
                "unknown_fields": dict(sorted(self.unknown_fields.items()))}
