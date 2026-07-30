"""Real daily closes — the missing feedback channel.

WHY THIS EXISTS
---------------
The engine could research real companies and reach real decisions, and then
nothing. No prices meant no outcome, no grading, no calibration: a live
research engine rather than a live training one. Every "learning" number in
this project was potential until a decision could be checked against what the
market actually did.

WHY THIS SOURCE
---------------
Measured, not chosen by preference. Tiingo, Polygon, Alpha Vantage, Finnhub,
Twelve Data and IEX all require a credential this environment does not have.
Stooq now answers with a JavaScript bot-challenge instead of CSV. Yahoo's chart
endpoint answers with real daily OHLC and needs no key, so it is the only route
from "decision" to "graded decision" available today.

WHAT THAT COSTS, STATED PLAINLY
-------------------------------
It is an undocumented endpoint. It can change shape or start refusing without
notice, and it carries no availability promise. So:

  * every failure is explicit — a missing price returns None and the decision
    stays UNGRADED, never silently graded as flat;
  * the source is recorded on every series, so a later calibration review can
    ask whether a result depended on this feed;
  * `PriceSeries.as_of` is the last date actually returned, not the date asked
    for, because a stale feed answering an old close is the failure most likely
    to be mistaken for success.

The adapter interface matches the `price_at(symbol, day)` callable the hosted
context already injects, so swapping in a credentialed feed later is a
one-line change and nothing downstream moves.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Sequence, Tuple

SOURCE = "yahoo_chart.v1"
_ENDPOINT = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
# Present as a browser: the endpoint refuses an empty user agent. Not evasion —
# it is a public endpoint answering a public quote; the header is what makes it
# answer at all.
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; intent-engine/1.0)"}


class PriceUnavailable(RuntimeError):
    """The feed could not answer. Never swallowed into a fabricated price."""


@dataclass(frozen=True)
class PriceSeries:
    symbol: str
    closes: Dict[str, float] = field(default_factory=dict)
    source: str = SOURCE

    @property
    def as_of(self) -> Optional[str]:
        """The last date actually returned — not the date requested.

        A stale feed answering last week's close is the failure most likely to
        be mistaken for success, so the real boundary is always visible.
        """
        return max(self.closes) if self.closes else None

    def on(self, day: str) -> Optional[float]:
        """Close on `day`, or the most recent close before it.

        Markets are shut on weekends and holidays, so an exact-match-only
        lookup would report "no price" for roughly a third of calendar dates
        and quietly halve the sample. Never looks FORWARD: returning a price
        from after the date asked for is lookahead, and it would make every
        backtest optimistic in a way that is invisible afterwards.
        """
        if not self.closes:
            return None
        if day in self.closes:
            return self.closes[day]
        earlier = [d for d in self.closes if d <= day]
        return self.closes[max(earlier)] if earlier else None

    def window(self, start: str, end: str) -> List[float]:
        return [v for d, v in sorted(self.closes.items()) if start <= d <= end]


def _fetch(url: str, timeout: float) -> dict:
    request = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_series(symbol: str, *, days: int = 400, timeout: float = 20.0,
                 opener=None) -> PriceSeries:
    """Daily closes for `symbol`. Raises `PriceUnavailable` rather than guessing.

    `opener` is injectable so the offline suite exercises this parsing without
    a network call — the parsing is where the bugs live, not the socket.
    """
    url = _ENDPOINT.format(symbol=symbol) + f"?range={max(days, 5)}d&interval=1d"
    try:
        payload = (opener or _fetch)(url, timeout)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise PriceUnavailable(f"{symbol}: {type(exc).__name__}") from exc

    chart = (payload or {}).get("chart") or {}
    if chart.get("error"):
        raise PriceUnavailable(f"{symbol}: {chart['error']}")
    results = chart.get("result") or []
    if not results:
        raise PriceUnavailable(f"{symbol}: empty result")

    result = results[0]
    stamps = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []

    series: Dict[str, float] = {}
    for stamp, close in zip(stamps, closes):
        # A null close is a real thing in this feed (halted session, bad tick).
        # Dropped rather than carried forward: an invented price is worse than
        # a gap, because a gap is visible and an invention is not.
        if close is None:
            continue
        day = datetime.fromtimestamp(stamp, tz=timezone.utc).date().isoformat()
        series[day] = float(close)

    if not series:
        raise PriceUnavailable(f"{symbol}: no usable closes")
    return PriceSeries(symbol=symbol, closes=series)


def price_at_factory(cache: Optional[Dict[str, PriceSeries]] = None,
                     *, days: int = 400, fetcher=None):
    """A `price_at(symbol, day)` callable, matching what the hosted context
    already injects. One fetch per symbol, reused across every date."""
    store: Dict[str, PriceSeries] = cache if cache is not None else {}
    get = fetcher or fetch_series

    def price_at(symbol: str, day: str) -> float:
        if symbol not in store:
            store[symbol] = get(symbol, days=days)
        value = store[symbol].on(day[:10])
        if value is None:
            raise PriceUnavailable(f"{symbol}: no close on or before {day}")
        return value

    return price_at


def trading_window(series: PriceSeries, decision_day: str,
                   horizon_days: int) -> Tuple[Optional[float], Optional[float]]:
    """Entry and exit closes for a decision, or `(entry, None)` if the horizon
    has not arrived yet.

    An unresolved decision must stay unresolved. Grading it against the latest
    available close would score a 3-day-old position as though its 21-day
    horizon had passed, which is the most flattering possible error.
    """
    entry = series.on(decision_day)
    target = (date.fromisoformat(decision_day[:10])
              + timedelta(days=horizon_days)).isoformat()
    last = series.as_of
    if last is None or target > last:
        return entry, None
    return entry, series.on(target)
