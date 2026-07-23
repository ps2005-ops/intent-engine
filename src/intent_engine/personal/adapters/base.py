"""Adapter base + the honest-absence claim builders (T023)."""
from __future__ import annotations

from intent_engine.personal.records import (
    AVAIL_OUT_OF_SCOPE, AVAIL_UNAVAILABLE, FRESH_UNKNOWN, SourceClaim,
)


class Adapter:
    """An anti-corruption boundary over one subsystem's read surface.

    Subclasses expose only the reads Personal AI needs and return
    `SourceClaim`s. They hold a reference to the subsystem's service (for
    reads) and the session `as_of`. They never write and never compute
    domain intelligence.
    """
    subsystem = None

    def __init__(self, service=None, *, as_of: str):
        self.service = service
        self.as_of = as_of

    @property
    def available(self) -> bool:
        return self.service is not None


def unavailable_claim(claim_id: str, reason: str) -> SourceClaim:
    """The subsystem exists but has nothing to report — honest, not
    invented."""
    return SourceClaim(claim_id=claim_id, text=reason,
                       availability=AVAIL_UNAVAILABLE, source_refs=(),
                       freshness_status=FRESH_UNKNOWN)


def out_of_scope_claim(claim_id: str, reason: str) -> SourceClaim:
    """No subsystem owns this capability (a recorded dependency gap)."""
    return SourceClaim(claim_id=claim_id, text=reason,
                       availability=AVAIL_OUT_OF_SCOPE, source_refs=(),
                       freshness_status=FRESH_UNKNOWN)
