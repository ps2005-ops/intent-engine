"""The slot for news and company evidence (ablation arm C). PENDING.

The multi-source news/evidence channel is being built in parallel on branch
`prospect100/identity`. This module is the contract it plugs into, so arm C
can be run the day the channel exists without changing the harness, and so
that until then the harness cannot pretend it ran.

WHAT A PROVIDER MUST GUARANTEE
------------------------------
1. Every item is dated by when it became KNOWABLE: `knowable_at` is the
   later of its publication and its first retrieval. An item retrieved in
   2026 about a 2019 event is not 2019 evidence for a 2019 decision unless
   it was retrievable in 2019 -- and a provider that cannot say when it
   first saw an item must not offer it for historical decisions at all
   (`supports_history = False`).
2. Every item names its subject by manifest `company_id`, and the harness
   maps it to a listed security through `universe.listed_security`. A
   private company's news never reaches a trade; it is refused, not routed
   to a peer.
3. Every item names its ORIGIN (the author, not the venue) so independence
   can be counted ([[origin-is-the-author-not-the-venue]]). A subject's own
   filing does not corroborate itself.
4. Features are computed from items with `knowable_at <= cutoff` only, and
   each feature returns the evidence ids it read, `news:<id>@<knowable_at>`,
   which the leak checker re-reads like every other input.

`status()` is one of AVAILABLE, PENDING, UNAVAILABLE. Arm C runs only on
AVAILABLE and is reported NOT_MEASURED otherwise.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Protocol, Sequence, Tuple

AVAILABLE, PENDING, UNAVAILABLE = "AVAILABLE", "PENDING", "UNAVAILABLE"

#: The features arm C adds. Names are fixed now so the preregistration
#: covers them before any provider exists.
NEWS_FEATURES = (
    "news_items_30d",            # count of knowable items about the subject
    "news_independent_origins_30d",
    "news_net_stance_30d",       # mean stance in [-1, 1], 0 when none
    "news_adverse_event_30d",    # any item the provider types as adverse
)


@dataclass(frozen=True)
class EvidenceItem:
    evidence_id: str
    company_id: str
    published_at: str
    retrieved_at: str
    origin: str                  # who authored it
    source_class: str            # company_published | third_party | regulator
    stance: float = 0.0          # [-1, 1]; 0 = none stated
    event_type: str = ""
    text_sha256: str = ""

    @property
    def knowable_at(self) -> str:
        return max(self.published_at, self.retrieved_at)

    def eid(self) -> str:
        return f"news:{self.evidence_id}@{self.knowable_at}"


class EvidenceProvider(Protocol):
    name: str
    supports_history: bool

    def status(self) -> str: ...

    def items(self, company_id: str, *, cutoff: str
              ) -> Sequence[EvidenceItem]: ...


class ProviderBreach(RuntimeError):
    """A provider returned something its contract forbids."""


def news_features(provider: EvidenceProvider, company_id: str, *,
                  cutoff: str, window_start: str
                  ) -> Tuple[Dict[str, float], List[str]]:
    """Arm C's features, with the walls enforced here rather than trusted."""
    items = list(provider.items(company_id, cutoff=cutoff))
    for it in items:
        if it.knowable_at[:10] > cutoff:
            raise ProviderBreach(
                f"{provider.name} returned {it.evidence_id} knowable "
                f"{it.knowable_at} for a {cutoff} decision")
        if it.company_id != company_id:
            raise ProviderBreach(
                f"{provider.name} returned an item about {it.company_id} "
                f"for {company_id}")
    recent = [it for it in items if it.knowable_at[:10] >= window_start]
    origins = {it.origin for it in recent if it.source_class != "company_published"}
    stance = [it.stance for it in recent if it.stance]
    feats = {
        "news_items_30d": float(len(recent)),
        "news_independent_origins_30d": float(len(origins)),
        "news_net_stance_30d": (sum(stance) / len(stance)) if stance else 0.0,
        "news_adverse_event_30d": 1.0 if any(
            it.event_type.startswith("ADVERSE") for it in recent) else 0.0,
    }
    return feats, [it.eid() for it in recent]


@dataclass
class PendingProvider:
    """What arm C has today: nothing, said plainly."""
    name: str = "multi_source_news.pending"
    supports_history: bool = False
    reason: str = ("the multi-source news/evidence channel is under "
                   "construction on prospect100/identity; no provider is "
                   "wired, so arm C is NOT_MEASURED")

    def status(self) -> str:
        return PENDING

    def items(self, company_id: str, *, cutoff: str):
        raise ProviderBreach(self.reason)


@dataclass
class FixtureProvider:
    """An in-memory provider for tests of the contract (never for results)."""
    rows: List[EvidenceItem] = field(default_factory=list)
    name: str = "fixture"
    supports_history: bool = True

    def status(self) -> str:
        return AVAILABLE

    def items(self, company_id: str, *, cutoff: str):
        return [r for r in self.rows if r.company_id == company_id]
