"""A standing instruction to look for a response that was predicted first.

WHY THE MACHINERY IS BUILT BEFORE THERE IS ANYTHING TO WATCH
------------------------------------------------------------
No live cross-actor expectation exists, because no counterparty publishes a
dated action stream yet. That is a data condition, not a design one, and
building the watch only once the data arrives means the first real episode
would be handled by code written in a hurry against a live case.

So the contract exists, is tested against fixtures, and its production store
is EMPTY. An empty durable store is an honest state; an absent one is not.

WHAT A WATCH MAY NOT DO
-----------------------
It may not widen. A watch created for a counterparty's pricing response to a
named contested object searches those source families for that actor inside
that window. "Look at everything they publish" is not a watch — it is a
crawl with a story attached, and anything it found would be selected after
the fact.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
from dataclasses import dataclass, field
from typing import Dict, Optional, Sequence, Tuple

CONTRACT = "response_watch.v1"

# --- status ------------------------------------------------------------------
WATCHING = "WATCHING"
RESOLVED = "RESOLVED"
WINDOW_CLOSED = "WINDOW_CLOSED"
CANCELLED = "CANCELLED"
STATUSES = (WATCHING, RESOLVED, WINDOW_CLOSED, CANCELLED)


class WatchRejected(ValueError):
    pass


@dataclass(frozen=True)
class ResponseWatch:
    watch_id: str
    expectation_id: str
    counterparty: str
    response_class: str
    competitive_object: str
    eligible_source_families: Tuple[str, ...]
    start_at: str
    resolve_by: str
    cadence_days: int = 7
    status: str = WATCHING
    provenance: Dict[str, str] = field(default_factory=dict)

    def is_open(self, as_of: str) -> bool:
        return self.status == WATCHING and as_of[:10] <= self.resolve_by

    def due(self, as_of: str, last_checked: str = "") -> bool:
        """Whether this watch should be actioned today.

        Cadence exists so a watch is a schedule rather than a poll: checking
        a quarterly pricing page daily spends budget to learn nothing.
        """
        if not self.is_open(as_of):
            return False
        if not last_checked:
            return True
        try:
            gap = (_dt.date.fromisoformat(as_of[:10])
                   - _dt.date.fromisoformat(last_checked[:10])).days
        except ValueError:
            return True
        return gap >= self.cadence_days

    def as_dict(self) -> dict:
        return {
            "contract": CONTRACT, "watch_id": self.watch_id,
            "expectation_id": self.expectation_id,
            "counterparty": self.counterparty,
            "response_class": self.response_class,
            "competitive_object": self.competitive_object,
            "eligible_source_families": list(self.eligible_source_families),
            "start_at": self.start_at, "resolve_by": self.resolve_by,
            "cadence_days": self.cadence_days, "status": self.status,
            "provenance": dict(self.provenance),
        }


def open_watch(*, expectation_id: str, counterparty: str, response_class: str,
               competitive_object: str,
               eligible_source_families: Sequence[str],
               start_at: str, resolve_by: str, cadence_days: int = 7,
               provenance: Optional[Dict[str, str]] = None) -> ResponseWatch:
    """Create a watch. Requires an expectation that already exists.

    The expectation id is mandatory and is not a formality: a watch with no
    preregistration behind it is a search, and whatever it finds will look
    like a confirmation of something nobody wrote down first.
    """
    if not expectation_id.strip():
        raise WatchRejected(
            "a watch with no preregistered expectation is a search, and "
            "whatever it finds will read as confirmation of something nobody "
            "wrote down first")
    if not counterparty.strip():
        raise WatchRejected("a watch must name whom it is watching")
    families = tuple(f for f in eligible_source_families if f)
    if not families:
        raise WatchRejected(
            "a watch must name the source families it will read; "
            "'everything they publish' is a crawl with a story attached")
    if resolve_by[:10] <= start_at[:10]:
        raise WatchRejected(
            "the window closes on or before it opens, so there is no future "
            "in which this watch could see anything")
    raw = f"{expectation_id}|{counterparty}|{response_class}"
    return ResponseWatch(
        watch_id="wch_" + hashlib.sha256(raw.encode()).hexdigest()[:12],
        expectation_id=expectation_id.strip(),
        counterparty=counterparty.strip(),
        response_class=response_class.strip(),
        competitive_object=competitive_object.strip(),
        eligible_source_families=families, start_at=start_at[:10],
        resolve_by=resolve_by[:10], cadence_days=max(1, int(cadence_days)),
        status=WATCHING, provenance=dict(provenance or {}))


def close(watch: ResponseWatch, *, as_of: str, status: str = WINDOW_CLOSED
          ) -> ResponseWatch:
    if status not in STATUSES:
        raise WatchRejected(f"{status!r} is not a watch status")
    return ResponseWatch(**{**watch.__dict__, "status": status})


def summarise(watches: Sequence[ResponseWatch], *, as_of: str = "") -> dict:
    import collections
    by_status = collections.Counter(w.status for w in watches)
    return {
        "contract": CONTRACT,
        "watches": len(watches),
        "open": sum(1 for w in watches if as_of and w.is_open(as_of)),
        "by_status": {s: by_status.get(s, 0) for s in STATUSES
                      if by_status.get(s, 0)},
        "note": ("an EMPTY store is the honest state while no counterparty "
                 "publishes a dated action stream. The contract exists so "
                 "the first real episode is not handled by code written in "
                 "a hurry against a live case."),
    }
