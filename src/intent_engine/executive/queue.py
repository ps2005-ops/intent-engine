"""The triage queue (T021) — the primary artifact.

The question this subsystem answers is *what decision deserves the
founder's attention next?* — a ranking before it is a writing task. So the
queue is the artifact, and a decision package is what opening one yields.

There is not one queue. A bug fix, a pricing change, and an acquisition
cannot share a single ordering — they are not comparable, and forcing them
into one list produces a ranking nobody can act on. So candidates are
PARTITIONED by their context's queue assignment (strategic / operational /
maintenance) and ORDERED within each.

Ordering is deterministic and from recorded facts only. A candidate that
cannot honestly be ordered — no readiness, no impact — is listed
separately with the gap named, exactly as T020 lists an unrankable
proposal, rather than being ranked against candidates that have the
inputs.

No model assigns an ordering. `queue.py` is deliberately separate from
`packages.py`: the triage/synthesis split is the whole point, and merging
them is how this quietly becomes a synthesis agent again.
"""
from __future__ import annotations

from intent_engine.executive.records import (
    ESCALATION_NEEDS_BOARD, ESCALATION_NEEDS_FOUNDER, IMPACT_LEVELS, QUEUES,
    QUEUE_ASSIGNMENT_VERSION,
)

QUEUE_ORDER_VERSION = "triage_queue.v1"

# Escalation levels that put a candidate in front of a person, ranked.
_ESCALATION_RANK = {ESCALATION_NEEDS_BOARD: 2, ESCALATION_NEEDS_FOUNDER: 1}
_IMPACT_RANK = {level: i for i, level in enumerate(IMPACT_LEVELS)}


def _ordering_key(entry: dict):
    """Deterministic, stated. Not a blended score — a tuple with a fixed
    precedence, so the same facts always produce the same order and the
    order is explainable field by field.

    Precedence:
      1. decision-ready before not-ready (a choice a person can make now
         comes ahead of one they cannot)
      2. higher escalation before lower
      3. more unresolved conflicts before fewer (disagreement is where a
         founder's judgment is most needed)
      4. larger impact before smaller
      5. more open decision debt before less
      6. candidate_id, as a stable final tie-break
    """
    return (
        0 if entry["decision_ready"] else 1,
        -_ESCALATION_RANK.get(entry["escalation"], 0),
        -entry["conflict_count"],
        -_IMPACT_RANK.get(entry["impact"], -1),
        -entry["open_debt_count"],
        entry["candidate_id"],
    )


def build_entry(*, candidate_id: str, queue: str, decision_ready: bool,
                escalation: str, conflict_count: int, impact,
                open_debt_count: int, age_days, horizon: str,
                decision_class: str, rankable: bool, gaps=None) -> dict:
    return {"candidate_id": candidate_id, "queue": queue,
            "decision_ready": bool(decision_ready), "escalation": escalation,
            "conflict_count": conflict_count, "impact": impact,
            "open_debt_count": open_debt_count, "age_days": age_days,
            "horizon": horizon, "decision_class": decision_class,
            "rankable": rankable, "gaps": list(gaps or [])}


def build_queues(entries: list) -> dict:
    """Partition into the three queues, order the rankable within each, and
    list the unrankable separately with their gaps."""
    partitioned = {q: {"rankable": [], "unrankable": []} for q in QUEUES}
    for entry in entries:
        bucket = "rankable" if entry["rankable"] else "unrankable"
        partitioned.setdefault(entry["queue"],
                               {"rankable": [], "unrankable": []})
        partitioned[entry["queue"]][bucket].append(entry)

    out = {}
    for queue in QUEUES:
        rankable = sorted(partitioned[queue]["rankable"], key=_ordering_key)
        unrankable = sorted(partitioned[queue]["unrankable"],
                            key=lambda e: e["candidate_id"])
        for position, entry in enumerate(rankable, 1):
            entry["queue_position"] = position
        out[queue] = {
            "order": [e["candidate_id"] for e in rankable],
            "entries": rankable,
            "unrankable": [{"candidate_id": e["candidate_id"],
                            "gaps": e["gaps"]} for e in unrankable],
        }
    return {
        "queue_order_version": QUEUE_ORDER_VERSION,
        "queue_assignment_version": QUEUE_ASSIGNMENT_VERSION,
        "queues": out,
        "ordering_precedence": [
            "decision-ready before not-ready",
            "higher escalation before lower",
            "more unresolved conflicts before fewer",
            "larger impact before smaller",
            "more open decision debt before less",
            "candidate id (stable tie-break)"],
        "note": ("three partitioned queues rather than one ordering, because "
                 "a maintenance fix and an acquisition are not comparable; "
                 "ordering is a fixed-precedence tuple, not a blended score, "
                 "so every position is explainable; a candidate that cannot "
                 "be ordered is listed separately with its gap named"),
    }
