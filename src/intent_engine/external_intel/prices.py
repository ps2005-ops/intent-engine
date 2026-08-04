"""Public daily closes — the only market input Founder Intelligence reads.

WHY A PROVIDER LIVES HERE RATHER THAN BEING IMPORTED FROM THE MARKET ENGINE
---------------------------------------------------------------------------
Importing the engine's fetcher would put an import edge from founder code into
a package whose neighbours are the paper book, the strategy registry and the
funnel. The edge would be harmless today and would be the path a leak took
later. Closes are a small, stable thing to fetch, so this package fetches its
own and imports nothing from the engine.

WHY THIS SOURCE
---------------
Measured, not preferred. Tiingo, Polygon, Alpha Vantage, Finnhub and IEX all
need a credential the deployed preview does not have -- market data has been
blocked on exactly that for several cycles. Yahoo's chart endpoint answers with
real daily closes and needs no key, so it is the only route from "listed
company" to "real market context" that works on the deployed service today.

WHAT THAT COSTS, STATED PLAINLY
--------------------------------
It is an undocumented endpoint with no availability promise. So:

  * a failure returns None and the market section reports itself absent with a
    reason -- never a zero, never an empty chart axis;
  * `source` travels on every series and into the export's `source_lineage`,
    so a later reader can ask whether a conclusion depended on this feed;
  * `as_of` is the last session ACTUALLY returned, not the date requested,
    because a stale feed answering an old close is the failure most likely to
    be mistaken for success.

NETWORK DISCIPLINE
------------------
Every fetch goes through the on-disk cache first, keyed by symbol and range.
A founder waiting on an HTTP round-trip mid-analysis is the behaviour the
refresh design exists to avoid, and an unattended job that re-downloads a year
of closes on every tick is how a free endpoint stops answering.
"""
from __future__ import annotations

import json
import pathlib
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Dict, List, Optional, Tuple

SOURCE = "yahoo_chart.v1"
PROVIDER = "public daily closes"
_ENDPOINT = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
# The endpoint refuses an empty user agent. Not evasion: it is a public
# endpoint answering a public quote, and this header is what makes it answer.
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; intent-engine/1.0)"}

#: The benchmark every company is compared against. One broad-market proxy,
#: named on the page, rather than a sector index chosen per company -- a
#: benchmark selected to flatter or damn a particular company is not a
#: comparison, and choosing it per company invites exactly that.
BENCHMARK_SYMBOL = "SPY"
BENCHMARK_NAME = "the broad US market (S&P 500 tracking fund)"

#: Cache lifetime. Closes for a completed session never change, so the only
#: reason to refetch is a NEW session -- six hours re-checks a few times a
#: trading day without hammering.
CACHE_TTL_SECONDS = 6 * 3600


@dataclass(frozen=True)
class PriceSeries:
    symbol: str
    closes: Dict[str, float]
    source: str = SOURCE
    currency: str = ""
    exchange: str = ""
    retrieved_at: str = ""

    @property
    def as_of(self) -> str:
        """The last session actually returned."""
        return max(self.closes) if self.closes else ""

    def __bool__(self) -> bool:
        return bool(self.closes)


def _cache_path(root, symbol: str, rng: str) -> pathlib.Path:
    safe = "".join(c for c in symbol.upper() if c.isalnum() or c in "-.")
    return pathlib.Path(root) / "cache" / "prices" / f"{safe}.{rng}.json"


#: TWO years, to measure ONE. The 1-year return needs 253 sessions (252 plus
#: the reference close), and a `1y` request returns 251 -- so asking for
#: exactly the window being measured left the year unmeasurable on every
#: company, while every shorter window worked. The extra history costs one
#: cached file and removes a gap that looked like missing data.
DEFAULT_RANGE = "2y"


def fetch(symbol: str, *, root=".", rng: str = DEFAULT_RANGE,
          fetcher=None, now: Optional[float] = None) -> Optional[PriceSeries]:
    """Daily closes for one symbol, cache first. None on any failure.

    `fetcher` is injected so tests never touch the network; production leaves
    it None and gets the real endpoint.
    """
    if not symbol:
        return None
    path = _cache_path(root, symbol, rng)
    now = time.time() if now is None else now
    cached = _read_cache(path, now)
    if cached is not None:
        return cached

    raw = (fetcher or _http_get)(symbol, rng)
    if raw is None:
        # A failed refresh must not throw away a usable older answer: the
        # export says how old it is, and stale-but-labelled beats absent.
        return _read_cache(path, now, ignore_ttl=True)
    series = _parse(symbol, raw)
    if series is None:
        return _read_cache(path, now, ignore_ttl=True)
    _write_cache(path, series, now)
    return series


def _read_cache(path: pathlib.Path, now: float,
                ignore_ttl: bool = False) -> Optional[PriceSeries]:
    if not path.exists():
        return None
    try:
        blob = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if not ignore_ttl and now - blob.get("cached_at", 0) > CACHE_TTL_SECONDS:
        return None
    closes = blob.get("closes") or {}
    if not closes:
        return None
    return PriceSeries(symbol=blob.get("symbol", ""), closes=closes,
                       source=blob.get("source", SOURCE),
                       currency=blob.get("currency", ""),
                       exchange=blob.get("exchange", ""),
                       retrieved_at=blob.get("retrieved_at", ""))


def _write_cache(path: pathlib.Path, series: PriceSeries, now: float) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({
            "cached_at": now, "symbol": series.symbol,
            "closes": series.closes, "source": series.source,
            "currency": series.currency, "exchange": series.exchange,
            "retrieved_at": series.retrieved_at}, sort_keys=True))
        tmp.replace(path)
    except OSError:  # pragma: no cover - a read-only disk must not break a run
        pass


def _http_get(symbol: str, rng: str) -> Optional[dict]:
    url = _ENDPOINT.format(symbol=urllib.parse.quote(symbol.upper()))
    url += f"?range={rng}&interval=1d"
    try:
        request = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        # Explicit, not silent: the caller turns None into a stated absence.
        return None


def _parse(symbol: str, raw: dict) -> Optional[PriceSeries]:
    """Chart JSON -> {date: close}. Any shape surprise returns None."""
    try:
        result = ((raw or {}).get("chart") or {}).get("result") or []
        if not result:
            return None
        first = result[0]
        stamps = first.get("timestamp") or []
        quote = ((first.get("indicators") or {}).get("quote") or [{}])[0]
        closes = quote.get("close") or []
        meta = first.get("meta") or {}
    except (AttributeError, TypeError, IndexError):
        return None
    if not stamps or len(stamps) != len(closes):
        return None
    out: Dict[str, float] = {}
    for stamp, close in zip(stamps, closes):
        # A null close is a non-session or a hole. It is DROPPED, never
        # carried forward and never zeroed -- a carried-forward price makes a
        # flat stretch the data never observed.
        if close is None:
            continue
        try:
            day = datetime.fromtimestamp(stamp, tz=timezone.utc).date()
        except (OverflowError, OSError, ValueError):  # pragma: no cover
            continue
        out[day.isoformat()] = float(close)
    if not out:
        return None
    return PriceSeries(
        symbol=symbol.upper(), closes=out, source=SOURCE,
        currency=meta.get("currency") or "",
        exchange=meta.get("fullExchangeName") or meta.get("exchangeName") or "",
        retrieved_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
