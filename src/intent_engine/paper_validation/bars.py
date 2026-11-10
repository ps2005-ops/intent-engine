"""Adjusted daily bars, cached with their vintage.

WHY NOT `market.prices.fetch_series` AS IT STANDS
-------------------------------------------------
It reads `quote.close`, which Yahoo splits-adjusts but does not
dividend-adjust. For TLT or HYG a month's dividend is a large fraction of a
month's return, so a close-to-close series understates bonds by their whole
coupon and makes every bond rule look worse than it is. This module asks the
SAME endpoint for `adjclose` and uses it, and reuses `market.prices._fetch`
and `PriceUnavailable` so there is one way this repository talks to Yahoo.

THE OPEN IS ADJUSTED BY THE SAME DAY'S FACTOR
---------------------------------------------
Entries and exits are at the open. Yahoo publishes no adjusted open, so the
open is scaled by that day's adjclose/close. Back-adjustment rescales every
price before an ex-date by the same factor, so the ratio of two adjusted
opens is the total return between them, dividends included, whatever later
dividends do to the levels.

AN UNFINISHED SESSION IS NOT A BAR
----------------------------------
During and shortly after a session the endpoint can return a bar for today
with a provisional close (or none). A forecast scored on a provisional
price is scored on a number that later changes. Bars dated on or after the
retrieval's New York date are dropped unless the retrieval happened after
18:00 New York time.
"""
from __future__ import annotations

import bisect
import datetime as _dt
import gzip
import hashlib
import json
import pathlib
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from intent_engine.market import prices as MP

SOURCE = "yahoo_chart.v1+adjclose"
_URL = ("https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        "?period1=0&period2={period2}&interval=1d&events=div%2Csplits")
CACHE_DIR = pathlib.Path("reports/paper_validation/prices")
FIELDS = ("date", "open", "close", "adjclose")
#: The replay anchor is 2003-01-02 and needs 273 prior sessions. Older bars
#: are dropped from the stored cache: they are never read, and keeping
#: fifty years of KO in the repository would cost megabytes for nothing.
KEEP_FROM = "2001-01-01"


@dataclass(frozen=True)
class Bars:
    symbol: str
    dates: Tuple[str, ...]
    open_adj: Tuple[float, ...]
    close_adj: Tuple[float, ...]
    retrieved_at: str = ""
    sha256: str = ""
    source: str = SOURCE
    dividends: int = 0
    splits: int = 0

    def __post_init__(self) -> None:
        if list(self.dates) != sorted(set(self.dates)):
            raise ValueError(f"{self.symbol}: dates not strictly increasing")
        if not (len(self.dates) == len(self.open_adj) == len(self.close_adj)):
            raise ValueError(f"{self.symbol}: ragged bars")

    def __len__(self) -> int:
        return len(self.dates)

    @property
    def last_date(self) -> str:
        return self.dates[-1] if self.dates else ""

    def index_of(self, day: str) -> Optional[int]:
        i = bisect.bisect_left(self.dates, day)
        return i if i < len(self.dates) and self.dates[i] == day else None

    def index_on_or_before(self, day: str) -> Optional[int]:
        i = bisect.bisect_right(self.dates, day) - 1
        return i if i >= 0 else None

    def first_index_after(self, day: str) -> Optional[int]:
        i = bisect.bisect_right(self.dates, day)
        return i if i < len(self.dates) else None

    def truncated(self, day: str) -> "Bars":
        """Only what existed at the close of `day`. Used by the leak test."""
        i = bisect.bisect_right(self.dates, day)
        return Bars(self.symbol, self.dates[:i], self.open_adj[:i],
                    self.close_adj[:i], self.retrieved_at, self.sha256,
                    self.source, self.dividends, self.splits)


def _ny_now(now: _dt.datetime):
    from zoneinfo import ZoneInfo
    return now.astimezone(ZoneInfo("America/New_York"))


def complete_through(retrieved: _dt.datetime) -> str:
    """The last session date whose bar is final at `retrieved`."""
    ny = _ny_now(retrieved)
    if ny.hour >= 18:
        return ny.date().isoformat()
    return (ny.date() - _dt.timedelta(days=1)).isoformat()


def parse(symbol: str, payload: dict, *, retrieved: _dt.datetime
          ) -> Tuple[List[list], dict]:
    chart = (payload or {}).get("chart") or {}
    if chart.get("error"):
        raise MP.PriceUnavailable(f"{symbol}: {chart['error']}")
    results = chart.get("result") or []
    if not results:
        raise MP.PriceUnavailable(f"{symbol}: empty result")
    r = results[0]
    stamps = r.get("timestamp") or []
    q = ((r.get("indicators") or {}).get("quote") or [{}])[0]
    adj = ((r.get("indicators") or {}).get("adjclose") or [{}])[0]
    adjc = adj.get("adjclose") or []
    if len(adjc) != len(stamps):
        raise MP.PriceUnavailable(f"{symbol}: no adjclose series")
    cutoff = complete_through(retrieved)
    rows = []
    for k, stamp in enumerate(stamps):
        day = _dt.datetime.fromtimestamp(stamp, tz=_dt.timezone.utc
                                         ).date().isoformat()
        if day > cutoff:
            continue
        vals = [q.get(f, [None] * len(stamps))[k]
                for f in ("open", "high", "low", "close")]
        a = adjc[k]
        if any(v is None or v <= 0 for v in vals) or a is None or a <= 0:
            continue   # a gap is visible; an invented price is not
        if day < KEEP_FROM:
            continue
        rows.append([day, round(float(vals[0]), 6), round(float(vals[3]), 6),
                     round(float(a), 6)])
    # Yahoo occasionally repeats a date (a late print). Keep the last.
    dedup: Dict[str, list] = {}
    for row in rows:
        dedup[row[0]] = row
    rows = [dedup[d] for d in sorted(dedup)]
    events = r.get("events") or {}
    meta = {"dividends": len(events.get("dividends") or {}),
            "splits": len(events.get("splits") or {}),
            "instrument_type": (r.get("meta") or {}).get("instrumentType", ""),
            "currency": (r.get("meta") or {}).get("currency", ""),
            "exchange": (r.get("meta") or {}).get("exchangeName", ""),
            "complete_through": cutoff}
    if not rows:
        raise MP.PriceUnavailable(f"{symbol}: no usable bars")
    return rows, meta


def _content_sha(rows: Sequence[list]) -> str:
    return hashlib.sha256(json.dumps(rows, separators=(",", ":"))
                          .encode("utf-8")).hexdigest()


def fetch(symbol: str, *, opener: Optional[Callable] = None,
          now: Optional[_dt.datetime] = None, timeout: float = 30.0) -> dict:
    now = now or _dt.datetime.now(_dt.timezone.utc)
    url = _URL.format(symbol=symbol, period2=int(now.timestamp()))
    try:
        payload = (opener or MP._fetch)(url, timeout)
    except Exception as exc:                            # noqa: BLE001
        raise MP.PriceUnavailable(f"{symbol}: {type(exc).__name__}") from exc
    rows, meta = parse(symbol, payload, retrieved=now)
    return {"symbol": symbol, "source": SOURCE,
            "retrieved_at": now.isoformat(timespec="seconds"),
            "url": url.split("?")[0], "fields": list(FIELDS), "rows": rows,
            "sha256": _content_sha(rows), **meta}


def write_cache(doc: dict, cache_dir=CACHE_DIR) -> pathlib.Path:
    d = pathlib.Path(cache_dir)
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{doc['symbol']}.json.gz"
    raw = json.dumps(doc, separators=(",", ":")).encode("utf-8")
    # mtime=0 so the same content is the same bytes: a re-fetch that changed
    # nothing must not show up as a changed data file.
    with open(path, "wb") as fh, gzip.GzipFile(filename="", mode="wb",
                                                fileobj=fh, mtime=0) as gz:
        gz.write(raw)
    return path


def read_cache(symbol: str, cache_dir=CACHE_DIR) -> Optional[dict]:
    path = pathlib.Path(cache_dir) / f"{symbol}.json.gz"
    if not path.exists():
        return None
    with gzip.open(path, "rb") as gz:
        doc = json.loads(gz.read().decode("utf-8"))
    if _content_sha(doc["rows"]) != doc.get("sha256"):
        raise ValueError(f"{symbol}: cached rows do not match their sha256")
    return doc


def to_bars(doc: dict) -> Bars:
    dates, opens, closes = [], [], []
    for day, o, c, a in doc["rows"]:
        f = a / c
        dates.append(day)
        opens.append(o * f)
        closes.append(a)
    return Bars(doc["symbol"], tuple(dates), tuple(opens), tuple(closes),
                doc.get("retrieved_at", ""), doc.get("sha256", ""),
                doc.get("source", SOURCE), int(doc.get("dividends", 0)),
                int(doc.get("splits", 0)))


def load(symbols: Sequence[str], *, cache_dir=CACHE_DIR, refresh: bool = False,
         pause: float = 0.6, opener=None, now=None,
         log: Callable[[str], None] = lambda s: None
         ) -> Tuple[Dict[str, Bars], Dict[str, str]]:
    """Bars for each symbol, and the reason for each symbol that has none."""
    out: Dict[str, Bars] = {}
    failed: Dict[str, str] = {}
    for sym in symbols:
        doc = None if refresh else read_cache(sym, cache_dir)
        if doc is None:
            try:
                doc = fetch(sym, opener=opener, now=now)
                write_cache(doc, cache_dir)
                log(f"fetched {sym}: {len(doc['rows'])} bars "
                    f"{doc['rows'][0][0]}..{doc['rows'][-1][0]}")
                time.sleep(pause)
            except MP.PriceUnavailable as exc:
                failed[sym] = str(exc)
                log(f"FAILED {sym}: {exc}")
                continue
        out[sym] = to_bars(doc)
    return out, failed


def vintage(bars: Dict[str, Bars]) -> Dict[str, dict]:
    return {s: {"last_bar": b.last_date, "sha256": b.sha256[:16],
                "retrieved_at": b.retrieved_at, "source": b.source}
            for s, b in sorted(bars.items())}


def trim_doc(doc: dict) -> dict:
    """Re-shape a cache written with the full field set, without re-fetching."""
    if doc.get("fields") == list(FIELDS):
        return doc
    idx = {f: i for i, f in enumerate(doc["fields"])}
    rows = [[r[idx["date"]], round(float(r[idx["open"]]), 6),
             round(float(r[idx["close"]]), 6),
             round(float(r[idx["adjclose"]]), 6)]
            for r in doc["rows"] if r[idx["date"]] >= KEEP_FROM]
    out = dict(doc)
    out["fields"] = list(FIELDS)
    out["rows"] = rows
    out["sha256"] = _content_sha(rows)
    return out
