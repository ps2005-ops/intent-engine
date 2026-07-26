"""Trend source provider interface + an injected fake (§3, §16).

Every real adapter (Reddit / HN / YouTube / GitHub / Product Hunt / RSS / an
authenticated analytics export …) implements `TrendSource`. Tests use
`FakeTrendSource` — NO real network calls ever run in the suite. A provider
declares the PERMITTED access `method`; because the foundation's `Provenance`
only allows api/rss/export/manual/synthetic/derived, an adapter cannot smuggle
in unauthorized scraping.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

try:
    from typing import Protocol, runtime_checkable
except ImportError:  # pragma: no cover
    from typing_extensions import Protocol, runtime_checkable  # type: ignore

from intent_engine.growth_os.foundation.records import PROVENANCE_METHODS, GrowthOSError


@dataclass
class RawTrendItem:
    """One observation as a provider returns it — normalized, provider-agnostic."""
    topic: str
    audience: str
    fmt: str                              # short_video | thread | article | repo | ...
    source_url: str
    published_at: str                     # content publication timestamp (ISO)
    engagement: dict = field(default_factory=dict)        # metric -> value
    metric_definitions: dict = field(default_factory=dict)  # metric -> definition
    sample_limitations: str = ""
    quality_signals: dict = field(default_factory=dict)   # bot_ratio, sentiment, ...
    business_signals: dict = field(default_factory=dict)  # business-outcome metrics
    is_seasonal: bool = False


@runtime_checkable
class TrendSource(Protocol):
    """The narrow surface Trend Intelligence depends on."""

    name: str
    method: str          # one of foundation.PROVENANCE_METHODS (the permitted path)

    def fetch(self, *, query: str, since: Optional[str] = None) -> List[RawTrendItem]:
        ...


class FakeTrendSource:
    """Deterministic in-memory source for tests + acceptance demos (no network)."""

    def __init__(self, name: str, method: str = "api",
                 items: Optional[List[RawTrendItem]] = None):
        if method not in PROVENANCE_METHODS:
            raise GrowthOSError(
                f"provider method {method!r} not a permitted path "
                f"({sorted(PROVENANCE_METHODS)})")
        self.name = name
        self.method = method
        self._items = list(items or [])

    def add(self, item: RawTrendItem) -> "FakeTrendSource":
        self._items.append(item)
        return self

    def fetch(self, *, query: str, since: Optional[str] = None) -> List[RawTrendItem]:
        out = [i for i in self._items if query.lower() in i.topic.lower()]
        if since:
            out = [i for i in out if i.published_at >= since]
        return out
