"""Public facts that are identical for every company and every analysis.

WHAT A COLD COMPANY IS
----------------------
"Cold" means this deployment holds no snapshot for THIS company. It does not
mean the deployment knows nothing about the public record. SEC's ticker map is
the same 795,179 bytes whether the customer typed Apple or a company nobody has
ever analysed here, and re-downloading it per analysis is not freshness — it is
the same fact, bought again.

MEASURED locally on one cold analysis (`scripts/perf_acquisition_ledger.py`):

    https://www.sec.gov/files/company_tickers.json    795,179 B   fetched 2x
    https://www.sec.gov/files/company_tickers_exchange.json 521,231 B

Two identical downloads inside one run, and ten more across a ten-company
cohort. The saving is bytes, seconds, AND requests to the one host this
codebase is most careful about — a cache here is strictly a smaller ask of
SEC, never a larger one, which is what separates it from the two acquisition
"optimizations" this project measured and reverted.

WHAT MAY LIVE HERE, AND WHAT MAY NOT
------------------------------------
Only PUBLIC REGISTRY FACTS that do not depend on the subject:

    ticker -> CIK maps, exchange listings, issuer submission indexes.

Never a conclusion about a company. A cached reading would make one run's
analysis the input to another's, which is the cross-company contamination the
cohort exists to disprove. Everything stored here is a verbatim response body
keyed by its URL, re-fetched when it ages out, and re-parsed per caller.

FRESHNESS IS NOT OPTIONAL. Each entry carries the instant it was fetched and a
TTL; past it the entry is a miss and the request is made. A registrant that
filed this morning must be findable this afternoon, so submission indexes get a
much shorter life than the ticker table, which changes when a company lists.

SCOPE IS THE PROCESS. Nothing is written to disk: the preview has no persistent
disk (`docs/INTERACTIVE_PERFORMANCE.md`, standing limitations), so a
disk-backed cache would silently be a no-op there and the measurement would be
about a machine we do not have.
"""
from __future__ import annotations

import os
import threading
import time

#: The registry tables. A company lists or delists on a timescale of days;
#: an hour of staleness cannot make a resolved CIK wrong, only occasionally
#: absent, and an absent CIK already falls back to the un-cached path.
TTL_REGISTRY_S = 3600.0

#: A registrant's submissions index changes when they file. Fifteen minutes
#: is short enough that a filing made during a session is still found by the
#: next analysis, and long enough to cover a cohort run.
TTL_SUBMISSIONS_S = 900.0

#: Bytes held in memory. The two registry tables are ~1.3MB together; this
#: allows for a cohort's submission indexes on top and then evicts oldest
#: first rather than growing without a bound on a small instance.
MAX_CACHE_BYTES = 24_000_000


class _Store:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict = {}          # url -> (fetched_at, ttl, body)
        self._bytes = 0
        self.stats = {"hit": 0, "miss": 0, "expired": 0, "stored": 0,
                      "evicted": 0, "bytes_saved": 0}

    def get(self, url: str):
        with self._lock:
            entry = self._entries.get(url)
            if entry is None:
                self.stats["miss"] += 1
                return None
            fetched_at, ttl, body = entry
            if time.monotonic() - fetched_at > ttl:
                self._entries.pop(url, None)
                self._bytes -= len(body)
                self.stats["expired"] += 1
                return None
            self.stats["hit"] += 1
            self.stats["bytes_saved"] += len(body)
            return body

    def put(self, url: str, body: bytes, ttl: float) -> None:
        if not body:
            return
        with self._lock:
            previous = self._entries.pop(url, None)
            if previous is not None:
                self._bytes -= len(previous[2])
            self._entries[url] = (time.monotonic(), ttl, body)
            self._bytes += len(body)
            self.stats["stored"] += 1
            while self._bytes > MAX_CACHE_BYTES and self._entries:
                oldest = min(self._entries,
                             key=lambda k: self._entries[k][0])
                self._bytes -= len(self._entries.pop(oldest)[2])
                self.stats["evicted"] += 1

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._bytes = 0


STORE = _Store()


def enabled() -> bool:
    return os.environ.get("CI_PUBLIC_METADATA_CACHE", "1").strip().lower() \
        not in ("0", "false", "no", "off")


def cached_bytes(url: str, ttl: float, fetch):
    """Return the body for `url`, fetching through `fetch()` on a miss.

    `fetch` is the caller's own bounded, SSRF-validated retrieval — this
    function never makes a request itself and never decides what may be
    dialled. A cache that could reach the network would be a second retrieval
    path with none of the first one's rules.
    """
    if not enabled():
        return fetch()
    hit = STORE.get(url)
    if hit is not None:
        return hit
    body = fetch()
    if isinstance(body, (bytes, bytearray)):
        STORE.put(url, bytes(body), ttl)
    return body


def stats() -> dict:
    return dict(STORE.stats)
