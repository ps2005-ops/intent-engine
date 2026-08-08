"""Did the thing we learned survive the process that learned it?

WHY THIS EXISTS
---------------
Wave 5 discovered three valid COMPETES_WITH rivalries, reported them, and
wave 10 measured the persisted count as ZERO. Nothing failed. The extractor
was right, the claims were sound, and the store simply had no method that
could write a relationship down. Five waves of work planned around edges
that had never been saved.

The same defect was then found on the critical path: `CrossActorExpectation`
— the preregistration whose ENTIRE claim is that it existed before the
evidence — also had no write path. An in-memory preregistration cannot make
that claim to anybody.

WHAT MAKES THIS DETECTABLE RATHER THAN LUCKY
--------------------------------------------
Both were found by hand, one wave apart, because somebody happened to count.
The check here is mechanical: for each KIND of knowledge the engine claims
to accumulate, ask whether a write path exists, whether anything was
written, and whether a fresh reader can load it back. A kind that produced
objects this session and holds none on disk is `LOST`, and that is a
failure state rather than a quiet zero.

DERIVED IS NOT LOST
-------------------
Most modules here are folds over the ledger — near-miss corpora, corroboration,
episode rankings. Recomputing them is correct and cheap, and demanding that
they persist would be cargo cult. A kind is only tracked when losing it
loses INFORMATION: something a fresh process could not derive again from
what remains on disk.
"""
from __future__ import annotations

import collections
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

CONTRACT = "knowledge_retention.v1"

# --- how a kind of knowledge relates to storage -----------------------------
#: Written to the canonical store and reloadable.
DURABLE = "DURABLE"
#: Recomputable from what IS stored. Losing it costs time, not knowledge.
DERIVED = "DERIVED"
#: Produced, not recomputable, and NOT written anywhere. The defect.
LOST = "LOST"
#: A write path exists and nothing has used it yet.
UNUSED = "UNUSED"

STANDINGS = (DURABLE, DERIVED, LOST, UNUSED)

# --- overall ---------------------------------------------------------------
HEALTHY = "HEALTHY"
DEGRADED = "DEGRADED"
UNMEASURABLE = "UNMEASURABLE"


@dataclass(frozen=True)
class KnowledgeKind:
    """One thing the engine claims to learn, and where it goes."""
    name: str
    #: False for folds over the ledger — losing them loses no information.
    is_original: bool
    #: The store method that writes it, if any.
    write_path: str = ""
    #: How many exist in memory after this session.
    produced: int = 0
    #: How many a fresh reader can load.
    reloadable: int = 0
    note: str = ""

    @property
    def standing(self) -> str:
        if not self.is_original:
            return DERIVED
        if not self.write_path:
            return LOST if self.produced else UNUSED
        if self.produced and not self.reloadable:
            return LOST
        if not self.produced:
            return UNUSED
        return DURABLE

    @property
    def lost_count(self) -> int:
        return (self.produced - self.reloadable) if self.standing == LOST else 0

    def as_dict(self) -> dict:
        return {
            "name": self.name, "is_original": self.is_original,
            "write_path": self.write_path, "produced": self.produced,
            "reloadable": self.reloadable, "standing": self.standing,
            "lost": self.lost_count, "note": self.note,
        }


def audit(kinds: Sequence[KnowledgeKind]) -> dict:
    """Which knowledge would survive a restart, and which would not."""
    by_standing = collections.Counter(k.standing for k in kinds)
    lost = [k for k in kinds if k.standing == LOST]
    original = [k for k in kinds if k.is_original]
    durable = [k for k in original if k.standing == DURABLE]
    status = (DEGRADED if lost else
              HEALTHY if durable else
              UNMEASURABLE)
    return {
        "contract": CONTRACT,
        "kinds": len(kinds),
        "original_kinds": len(original),
        "by_standing": {s: by_standing.get(s, 0) for s in STANDINGS
                        if by_standing.get(s, 0)},
        "lost": [k.as_dict() for k in lost],
        "objects_lost": sum(k.lost_count for k in lost),
        "status": status,
        "reason": (
            f"{len(lost)} kind(s) produced knowledge this session that no "
            f"fresh process can load: "
            f"{', '.join(k.name for k in lost)}" if lost else
            f"{len(durable)} of {len(original)} original kinds are durable"
            if durable else
            "no original knowledge was produced, so retention cannot be "
            "measured"),
        "note": ("a DERIVED kind is not a failure: recomputing a fold over "
                 "the ledger is correct and cheap. Only knowledge that "
                 "cannot be re-derived is tracked for loss."),
    }
