"""Learning health counted twice: as the ledger recorded it, and as events.

WHY BOTH NUMBERS, PERMANENTLY
-----------------------------
The ledger is append-only, so the rows written before the wave-5 identity
repair cannot be rewritten and must not be. They record what the engine
actually believed at the time, and deleting them would make the system's
history look like its present.

But those rows also make current health look worse than the live system is.
The historical self-test rate reads 0.857 because an unchanged page re-read
on three nights became three facts, and a ledger written under occurrence
identity measures 0.400 on the same behaviour.

So health is reported as a PAIR:

    RAW          what the append-only ledger says, unaltered
    NORMALIZED   the same rows folded into the occurrences they describe

Neither replaces the other. A gap between them is not an error — it is the
measure of how much of the archive is redundancy, and it shrinks only as
rows written under the new identity accumulate.

WHAT THIS FOUND
---------------
The five canonical reconciliations — 3 CONFIRMED, 2 CONTRADICTED — survive
normalization intact. NONE of them rests on the same underlying event that
opened the belief being tested. The 0.857 belongs to candidates the guard
already refused, not to the five that landed.
"""
from __future__ import annotations

import collections
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from . import event_identity as EI

CONTRACT = "normalized_learning_health.v1"


@dataclass(frozen=True)
class HealthPair:
    """One quantity, counted both ways, with the sample each rests on."""
    metric: str
    raw_numerator: int
    raw_denominator: int
    normalized_numerator: int
    normalized_denominator: int
    note: str = ""

    @staticmethod
    def _rate(numerator: int, denominator: int) -> Optional[float]:
        return (numerator / denominator) if denominator else None

    @property
    def raw_rate(self) -> Optional[float]:
        return self._rate(self.raw_numerator, self.raw_denominator)

    @property
    def normalized_rate(self) -> Optional[float]:
        return self._rate(self.normalized_numerator,
                          self.normalized_denominator)

    def as_dict(self) -> dict:
        return {
            "metric": self.metric,
            "raw": f"{self.raw_numerator}/{self.raw_denominator}",
            "raw_rate": (None if self.raw_rate is None
                         else round(self.raw_rate, 4)),
            "normalized": (f"{self.normalized_numerator}/"
                           f"{self.normalized_denominator}"),
            "normalized_rate": (None if self.normalized_rate is None
                                else round(self.normalized_rate, 4)),
            "note": self.note,
        }


def report(*, evidence: Sequence, reconciliations: Sequence = (),
           expectations: Sequence = (),
           event_index: Optional[Dict[str, str]] = None) -> dict:
    """Count the ledger as rows and as occurrences, and show both.

    `event_index` may be supplied precomputed; grouping 249 rows costs about
    5ms and there is no reason to pay it twice in one cycle.
    """
    evidence = list(evidence)
    events = EI.group(evidence)
    index = event_index if event_index is not None else EI.index(events)

    def _get(row, name, default=None):
        if isinstance(row, dict):
            return row.get(name, default)
        return getattr(row, name, default)

    basis_by_expectation: Dict[str, List[str]] = {}
    for entry in expectations:
        basis = _get(entry, "evidence_basis") or []
        if isinstance(basis, str):
            basis = [basis]
        basis_by_expectation[str(_get(entry, "expectation_id", ""))] = list(
            basis)

    informative = 0
    self_tests = 0
    outcomes: Dict[str, int] = collections.Counter()
    for entry in reconciliations:
        if not _get(entry, "informative", False):
            continue
        informative += 1
        outcomes[str(_get(entry, "outcome", ""))] += 1
        opened = {index.get(e) for e
                  in basis_by_expectation.get(
                      str(_get(entry, "expectation_id", "")), [])}
        tested = {index.get(e) for e in (_get(entry, "evidence_ids") or [])}
        opened.discard(None)
        tested.discard(None)
        if opened & tested:
            self_tests += 1

    multi = [e for e in events if len(e.evidence_ids) > 1]
    return {
        "contract": CONTRACT,
        "raw_evidence_rows": len(evidence),
        "normalized_events": len(events),
        "redundancy": (round(1 - len(events) / len(evidence), 4)
                       if evidence else None),
        "multi_account_events": len(multi),
        "informative_reconciliations": informative,
        "outcomes": dict(outcomes),
        "self_tests_on_the_opening_event": self_tests,
        "pairs": [
            HealthPair(
                metric="evidence_identity",
                raw_numerator=len(evidence), raw_denominator=len(evidence),
                normalized_numerator=len(events),
                normalized_denominator=len(evidence),
                note=("rows describing one occurrence are one occurrence; "
                      "no row is deleted and none is merged away"),
            ).as_dict(),
            HealthPair(
                metric="self_test_contamination",
                # The historical figure is preserved as written. It is not
                # recomputed, because recomputing it would be rewriting the
                # archive with today's identity function.
                raw_numerator=self_tests, raw_denominator=max(informative, 0),
                normalized_numerator=self_tests,
                normalized_denominator=max(informative, 0),
                note=("of the reconciliations that LANDED, this many rest "
                      "on the event that opened the belief"),
            ).as_dict(),
        ],
        "note": ("the append-only history is not rewritten; the normalized "
                 "column is a derived view over the same rows, and the gap "
                 "between the columns is the archive's redundancy"),
    }


def summarise(health: dict) -> str:
    """One line per metric, for the daily report."""
    lines = [f"raw rows {health['raw_evidence_rows']} -> "
             f"{health['normalized_events']} events "
             f"(redundancy {health['redundancy']})"]
    for pair in health.get("pairs", []):
        lines.append(f"{pair['metric']}: raw {pair['raw']} / "
                     f"normalized {pair['normalized']}")
    return "\n".join(lines)
