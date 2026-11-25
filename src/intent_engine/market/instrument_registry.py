"""Point-in-time instrument eligibility: was this instrument tradable at the decision?

WHY
---
169 audit rows (104 graded events) were OLO decisions dated 2026-07-31 to
2026-11-25. Olo Inc. completed its take-private merger and filed Form 25-NSE
on 2025-09-12 and Form 15-12G on 2025-09-23: it had not traded for ten months
when the first decision was recorded. They were graded UNRESOLVABLE, which
reads as "we could not measure" when the truth is "there was nothing to
decide".

THE TWO RULES
-------------
1. An instrument whose delisting or deregistration was FILED on or before the
   decision date is INELIGIBLE at that date. It cannot enter a tradable
   forecast universe, and a record already made is classified, not deleted.
2. An instrument delisted AFTER a legitimate decision stays in the
   evaluation. Dropping it is survivorship bias. Its exit is the last close
   on or before the delisting date, labelled as such (for a cash merger that
   is close to the consideration; for a distressed delisting it is the last
   price anyone could have traded at).

Evidence is SEC EDGAR's submission history (Form 25, 25-NSE, 15-12B, 15-12G,
15-15D), point-in-time by filing date. CIKs come from a curated map that
carries its evidence, then the SEC ticker table (which omits delisted names,
so the map is required for exactly the cases this module exists for).
"""
from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

CONTRACT = "instrument_eligibility.v1"
#: Filings collected as evidence. Only DEREGISTRATION_FORMS can make an
#: instrument ineligible: Form 25 is per security and per exchange (Shopify
#: filed one in 2025-03 to move from NYSE to Nasdaq and kept trading; NextEra
#: has a 2019 25-NSE for one security), and 15-15D suspends reporting for a
#: plan or a debt security. Measured on the live universe on 2026-11-25: the
#: naive rule excluded NEE, PG and SHOP, all trading, which would have been a
#: selection bias manufactured by the guard meant to prevent one.
DELISTING_FORMS = ("25", "25-NSE", "15-12B", "15-12G", "15-15D")
DEREGISTRATION_FORMS = ("15-12B", "15-12G")
ELIGIBLE, INELIGIBLE, UNKNOWN = "ELIGIBLE", "INELIGIBLE", "UNKNOWN"

#: Curated symbol -> CIK for names the live ticker table no longer lists.
#: Each entry carries how it was established.
CURATED_CIKS: Dict[str, dict] = {
    "OLO": {"cik": 1431695, "name": "Olo Inc.",
            "evidence": "SEC submissions CIK0001431695: 8-K 1.01 2025-07-03 "
                        "(merger agreement), 8-K 2.01/3.01 + 25-NSE 2025-09-12, "
                        "15-12G 2025-09-23; verified 2026-11-25"},
}


@dataclass(frozen=True)
class Status:
    symbol: str
    as_of: str
    state: str                       # ELIGIBLE / INELIGIBLE / UNKNOWN
    reason: str
    delisted_on: str = ""            # first delisting-form filing date, if any
    evidence: tuple = ()

    def as_dict(self) -> dict:
        return {"contract": CONTRACT, "symbol": self.symbol, "as_of": self.as_of,
                "state": self.state, "reason": self.reason,
                "delisted_on": self.delisted_on, "evidence": list(self.evidence)}


@dataclass
class Registry:
    """`filings_for(cik) -> [(filing_date, form)]` and `cik_for(symbol)` are
    injected so the rules are testable offline."""
    filings_for: Callable[[int], List[tuple]]
    cik_for: Callable[[str], Optional[int]]
    _cache: Dict[int, List[tuple]] = field(default_factory=dict)

    def filings(self, symbol: str) -> Optional[List[tuple]]:
        cik = self.cik_for(symbol)
        if cik is None:
            return None
        if cik not in self._cache:
            self._cache[cik] = sorted(self.filings_for(cik))
        return self._cache[cik]

    def status(self, symbol: str, as_of: str, *,
               price_absent: Optional[bool] = None) -> Status:
        """`price_absent`: True when no price bar exists near `as_of`.

        INELIGIBLE needs BOTH an issuer-level deregistration filed by `as_of`
        AND the absence of prices. Either alone is not enough: a filing can be
        about one security, and a missing bar can be a feed problem.
        """
        a = as_of[:10]
        try:
            fs = self.filings(symbol)
        except Exception as exc:     # a lookup failure is UNKNOWN, never ELIGIBLE by default
            return Status(symbol, a, UNKNOWN,
                          f"registry lookup failed: {type(exc).__name__}")
        if fs is None:
            return Status(symbol, a, UNKNOWN, "no CIK for this symbol")
        dereg = [(d, f) for d, f in fs if f in DEREGISTRATION_FORMS]
        before = [x for x in dereg if x[0] <= a]
        ev = tuple(f"SEC {f} {d}" for d, f in fs if f in DELISTING_FORMS)
        if before and price_absent:
            d, f = before[0]
            return Status(symbol, a, INELIGIBLE,
                          f"Form {f} (issuer deregistration) filed {d}, on or "
                          "before the decision, and no price near the decision: "
                          "not tradable at decision time",
                          delisted_on=d, evidence=ev)
        if before and price_absent is None:
            return Status(symbol, a, UNKNOWN, "deregistration on file but price "
                          "availability not checked", delisted_on=before[0][0],
                          evidence=ev)
        after = [x for x in dereg if x[0] > a]
        return Status(symbol, a, ELIGIBLE,
                      "no issuer deregistration by the decision date"
                      + (" (prices present)" if before else ""),
                      delisted_on=after[0][0] if after else "", evidence=ev)


def sec_registry(cache_path: Optional[pathlib.Path] = None) -> Registry:
    """Production registry over SEC EDGAR. Cached per CIK on disk."""
    import gzip, urllib.request
    from intent_engine.company_ingestion.third_party_filings import _sec_user_agent
    cache = {}
    if cache_path and pathlib.Path(cache_path).exists():
        cache = json.loads(pathlib.Path(cache_path).read_text())

    def _get(url):
        req = urllib.request.Request(url, headers={"User-Agent": _sec_user_agent(),
                                                   "Accept-Encoding": "gzip"})
        with urllib.request.urlopen(req, timeout=30) as r:
            b = r.read()
            return json.loads(gzip.decompress(b) if r.headers.get(
                "Content-Encoding") == "gzip" else b)

    tickers: Dict[str, int] = {}

    def cik_for(symbol):
        if symbol in CURATED_CIKS:
            return CURATED_CIKS[symbol]["cik"]
        if not tickers:
            for v in _get("https://www.sec.gov/files/company_tickers.json").values():
                tickers[v["ticker"].upper()] = int(v["cik_str"])
        return tickers.get(symbol.upper().replace(".", "-"))

    def filings_for(cik):
        k = str(cik)
        if k not in cache:
            f = _get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json")["filings"]["recent"]
            cache[k] = [(d, t) for d, t in zip(f["filingDate"], f["form"])
                        if t in DELISTING_FORMS]
            if cache_path:
                pathlib.Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
                pathlib.Path(cache_path).write_text(json.dumps(cache))
        return [tuple(x) for x in cache[k]]

    return Registry(filings_for=filings_for, cik_for=cik_for)
