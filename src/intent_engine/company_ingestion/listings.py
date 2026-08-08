"""Which listed security, if any, a typed company name refers to.

WHY THIS EXISTS
---------------
`entities.py` is a hand-written registry of companies whose identity we can
state without guessing. It is the right shape for official-source fallback,
and the wrong shape for market context: it contained exactly THREE companies
with listings (Sony, Palantir, Shopify), so `WebApp._ticker_of` returned ""
for every other company, `_market_snapshot()` was never called, and the
founder dashboard reported "no market snapshot" for Tesla and NVIDIA. The
market engine was never the problem -- nothing downstream of the ticker was
ever reached.

MEASURED on the deployed preview 2026-08-02: Tesla resolved no ticker and the
market card rendered as an absence.

WHERE THE ANSWER COMES FROM
---------------------------
The SEC publishes `company_tickers_exchange.json` -- every registrant's CIK,
name, ticker and exchange. It is official, free, needs no API key, and is the
same authority the filings themselves come from. That makes it the right
primary source: using a market-data vendor here would put a paid dependency
in front of a fact the regulator already publishes.

MATCHING IS DELIBERATELY NOT FUZZY
----------------------------------
"Do not infer tickers from company names through uncontrolled fuzzy matching"
is a correctness requirement, not a style note: a wrong ticker attaches
another company's price history to this company's analysis, which is worse
than having none. So matching is exact on a normalised form, then an exact
leading-token prefix, and NOTHING else -- no edit distance, no token overlap
scoring, no "best" match.

A query resolves only when it lands on exactly ONE registrant (one CIK).
"Apple" reaches three (Apple Inc., Apple Hospitality REIT, Apple iSports) and
so is returned AMBIGUOUS rather than resolved to the famous one. "General"
reaches eight. Refusing those is the feature.

SHARE CLASSES AND ADRs
----------------------
One registrant often carries several tickers: ASML is ASML on Nasdaq and
ASMLF over the counter; Toyota is TM on the NYSE and TOYOF over the counter.
These are the same company, so this is a venue choice rather than an identity
ambiguity -- but it still changes the price series, so it is made explicitly:
a real exchange beats an over-the-counter quotation, and the alternatives are
carried on the resolution so an operator can see what was not chosen.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Optional, Sequence

# --- resolution states ------------------------------------------------------
# PUBLIC_LISTING_UNRESOLVED exists to stop the single worst failure in this
# area: rendering "this company is private" because a lookup came back empty.
# Not finding a ticker is a statement about the lookup. Being private is a
# statement about the company. Conflating them tells a founder something false
# about Tesla.
PUBLIC_LISTING_RESOLVED = "PUBLIC_LISTING_RESOLVED"
PUBLIC_LISTING_UNRESOLVED = "PUBLIC_LISTING_UNRESOLVED"
PRIVATE = "PRIVATE"
UNKNOWN = "UNKNOWN"

SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers_exchange.json"

# Venues that are a company's primary listing. An over-the-counter quotation
# of a foreign ordinary share is a real quote, but it is not the listing a
# reader means by "the shares", and its series is thinner.
_PRIMARY_EXCHANGES = ("nasdaq", "nyse", "nyse american", "nyse arca", "cboe")

_LEGAL_SUFFIXES = (
    "inc", "incorporated", "corp", "corporation", "co", "company", "ltd",
    "limited", "plc", "nv", "sa", "ag", "holdings", "holding", "group",
    "the", "lp", "llc", "trust", "adr", "se", "ab", "as", "oyj", "spa",
)
_SUFFIX_RE = re.compile(r"\b(?:%s)\b" % "|".join(_LEGAL_SUFFIXES))


def normalize_company_name(name: str) -> str:
    """A comparable form of a company name.

    Deterministic and lossy in one direction only: punctuation and legal-form
    words go, word order and spelling do not. "Tesla, Inc." and "Tesla" both
    become "tesla"; "Toyota Motor Corp/" becomes "toyota motor".
    """
    text = (name or "").lower()
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    text = _SUFFIX_RE.sub(" ", text)
    return " ".join(text.split())


@dataclass(frozen=True)
class ListingResolution:
    """What we concluded about this company's listing, and why.

    `reason` is written for an operator reading a diagnostic, not for the
    founder-facing page -- the pages phrase the four states themselves.
    """
    status: str
    ticker: str = ""
    exchange: str = ""
    cik: str = ""
    source: str = ""
    reason: str = ""
    matched_name: str = ""
    alternatives: tuple = ()
    candidates: tuple = ()

    @property
    def is_public(self) -> bool:
        return self.status in (PUBLIC_LISTING_RESOLVED,
                               PUBLIC_LISTING_UNRESOLVED)

    def as_dict(self) -> dict:
        return {"status": self.status, "ticker": self.ticker,
                "exchange": self.exchange, "cik": self.cik,
                "source": self.source, "reason": self.reason,
                "matched_name": self.matched_name,
                "alternatives": [dict(a) for a in self.alternatives],
                "candidates": [dict(c) for c in self.candidates]}


class SecTickerMap:
    """The SEC registrant table, indexed for exact and prefix lookup.

    Built once and reused. The network fetch is injected so the suite never
    touches sec.gov, and a failed fetch yields an EMPTY map rather than an
    exception -- an unavailable lookup must degrade to "unresolved", never
    take down an analysis that was otherwise fine.
    """

    def __init__(self, rows: Sequence[dict] = ()):
        self._exact: dict = {}
        self._rows: list = []
        for row in rows:
            name = str(row.get("name") or "")
            key = normalize_company_name(name)
            if not key or not row.get("ticker"):
                continue
            entry = {"cik": str(row.get("cik") or ""), "name": name,
                     "ticker": str(row["ticker"]).strip().upper(),
                     "exchange": str(row.get("exchange") or "").strip(),
                     "key": key}
            self._rows.append(entry)
            self._exact.setdefault(key, []).append(entry)

    def __len__(self) -> int:
        return len(self._rows)

    @classmethod
    def from_json_bytes(cls, blob: bytes) -> "SecTickerMap":
        """Parse the SEC file's columnar form: {"fields": [...], "data": [...]}."""
        try:
            payload = json.loads(blob.decode("utf-8", "replace"))
        except Exception:                                   # noqa: BLE001
            return cls(())
        fields = payload.get("fields")
        data = payload.get("data")
        if not fields or not isinstance(data, list):
            return cls(())
        try:
            idx = {f: fields.index(f) for f in ("cik", "name", "ticker",
                                                "exchange")}
        except ValueError:
            return cls(())
        rows = []
        for record in data:
            if not isinstance(record, (list, tuple)):
                continue
            if len(record) <= max(idx.values()):
                continue
            rows.append({k: record[i] for k, i in idx.items()})
        return cls(rows)

    def lookup(self, name: str) -> list:
        """Registrants this name denotes. Exact first, then leading tokens."""
        key = normalize_company_name(name)
        if not key:
            return []
        hits = self._exact.get(key)
        if hits:
            return list(hits)
        tokens = key.split()
        return [r for r in self._rows if r["key"].split()[:len(tokens)]
                == tokens]


def load_sec_ticker_map(*, transport=None, resolver=None,
                        timeout: float = 10.0) -> SecTickerMap:
    """Fetch and index the SEC registrant table, or return an empty map."""
    from intent_engine.company_ingestion.edgar import _fetch_bytes
    try:
        blob = _fetch_bytes(SEC_TICKERS_URL, transport=transport,
                            resolver=resolver, timeout=timeout)
    except Exception:                                        # noqa: BLE001
        return SecTickerMap(())
    return SecTickerMap.from_json_bytes(blob)


def _pick_primary(rows: Sequence[dict]) -> tuple:
    """The listing a reader means, and the ones that were not chosen."""
    ranked = sorted(
        rows,
        key=lambda r: (0 if r["exchange"].lower() in _PRIMARY_EXCHANGES else 1,
                       len(r["ticker"]), r["ticker"]))
    return ranked[0], tuple(
        {"ticker": r["ticker"], "exchange": r["exchange"]} for r in ranked[1:])


def resolve_listing(*, company_name: str = "", website: str = "",
                    registry_listings: Sequence = (),
                    sec_map: Optional[SecTickerMap] = None,
                    known_private: bool = False) -> ListingResolution:
    """Resolve a company to one listed security, or say honestly why not.

    Order, strongest first:

    1. a listing already asserted on the curated identity record;
    2. the SEC registrant table;
    3. unresolved, with the reason stated.
    """
    if known_private:
        return ListingResolution(
            status=PRIVATE, source="identity record",
            reason="the identity record states this company is not listed")

    # 1. CURATED IDENTITY. Already reviewed by a human, so it outranks a
    #    lookup -- and it is the only place a non-SEC primary listing (a
    #    Tokyo or Toronto line) is currently asserted.
    for listing in registry_listings or ():
        exchange, ticker = "", ""
        if isinstance(listing, dict):
            exchange = str(listing.get("exchange") or "")
            ticker = str(listing.get("ticker") or "")
        elif isinstance(listing, (list, tuple)) and len(listing) == 2:
            exchange, ticker = str(listing[0]), str(listing[1])
        if ticker:
            return ListingResolution(
                status=PUBLIC_LISTING_RESOLVED, ticker=ticker.strip().upper(),
                exchange=exchange.strip(), source="curated entity registry",
                reason="the verified identity record carries this listing")

    if sec_map is None or not len(sec_map):
        return ListingResolution(
            status=UNKNOWN, source="none",
            reason="no listing source was available for this run")

    rows = sec_map.lookup(company_name)
    if not rows:
        # Not being an SEC registrant is the ordinary case for a private
        # company, but it is also what a misspelling looks like, so this
        # stops short of asserting PRIVATE.
        return ListingResolution(
            status=UNKNOWN, source="SEC registrant table",
            reason=f"no SEC registrant matches {company_name!r}")

    ciks = {r["cik"] for r in rows}
    if len(ciks) > 1:
        # Several DIFFERENT companies. Choosing here is exactly the guess this
        # module exists to refuse.
        return ListingResolution(
            status=PUBLIC_LISTING_UNRESOLVED, source="SEC registrant table",
            reason=f"{company_name!r} matches {len(ciks)} different SEC "
                   f"registrants; a name alone does not choose between them",
            candidates=tuple({"ticker": r["ticker"], "name": r["name"],
                              "exchange": r["exchange"], "cik": r["cik"]}
                             for r in sorted(rows, key=lambda x: x["ticker"])))

    primary, alternatives = _pick_primary(rows)
    return ListingResolution(
        status=PUBLIC_LISTING_RESOLVED, ticker=primary["ticker"],
        exchange=primary["exchange"], cik=primary["cik"],
        source="SEC registrant table", matched_name=primary["name"],
        alternatives=alternatives,
        reason=f"{company_name!r} matches SEC registrant "
               f"{primary['name']!r} (CIK {primary['cik']})")
