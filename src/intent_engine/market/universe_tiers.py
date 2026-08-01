"""Staged, point-in-time-safe trading universe.

WHY A SECOND UNIVERSE, AND WHY IT IS NOT A DUPLICATE
----------------------------------------------------
`universe.companies` is an EVIDENCE universe: ~28 hand-curated company profiles
carrying websites, competitors, strategic priorities and evidence sources. It
exists so Founder Intelligence can research a business, and every field in it is
there to support a narrative reading.

That is the wrong shape for a price-behaviour strategy, and not because it is
too small. A sector ETF has no competitors, no strategic priorities and no
business model to read; it cannot be expressed as a `CompanyProfile` without
inventing the fields. This module is the SECURITY universe: the minimum a price
claim needs -- a symbol, a type, a liquidity record, and membership dates.

The two are joined, not merged: a security that is also a curated company keeps
`company_id`, so evidence-backed and price-backed reasoning about the same name
stay linked.

SURVIVORSHIP BIAS IS THE POINT OF THE MEMBERSHIP DATES
------------------------------------------------------
Running today's symbol list across ten years of history is the classic way to
manufacture a backtest. Every company that went bankrupt, got acquired, or fell
out of the index is silently absent, so the sample is conditioned on survival --
and survival correlates with returns. The effect is large and always favourable.

So membership is a DATE RANGE, `eligible_on` refuses to admit a security outside
it, and a delisted security keeps its rows: `delisted_at` marks the end of
tradability, it does not delete the history. A test asserts a bankrupt name
still appears in a replay window that precedes its delisting.

WHAT THIS MODULE HONESTLY CANNOT DO
-----------------------------------
It has **no historical index-membership feed**. Nobody here has point-in-time
S&P 500 constituents. So this implements option (B) from the mission -- a
documented survivorship-aware approximation -- and states the residual bias
rather than hiding it: the tier lists are current-membership lists with explicit
delisting support, so a name that failed BEFORE this file was written is absent
and cannot be recovered. `SURVIVORSHIP_LIMITATION` is printed in every report
that uses a tier, and results are limited accordingly.
"""
from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

UNIVERSE_VERSION = "security_universe.v1"

# The limitation, stated once and printed everywhere a tier is used.
SURVIVORSHIP_LIMITATION = (
    "Tier membership is a CURRENT list with explicit delisting support, not a "
    "point-in-time index reconstruction. Securities that failed before this "
    "universe was authored are absent and cannot be recovered from it. Replay "
    "results carry an upward survivorship bias of unknown but non-zero size; "
    "no result may be reported as if the universe were survivorship-free."
)

# --- security types ---------------------------------------------------------
EQUITY = "equity"
SECTOR_ETF = "sector_etf"
BROAD_ETF = "broad_etf"
SUPPORTED_TYPES = frozenset({EQUITY, SECTOR_ETF, BROAD_ETF})

# Explicitly unsupported, each for a stated reason. Rejected by type rather
# than hoped to be absent.
UNSUPPORTED_TYPES = {
    "leveraged_etf": "daily rebalancing makes multi-day returns path-dependent "
                     "and not comparable to an unleveraged holding",
    "inverse_etf": "same path dependency, plus a sign convention that silently "
                   "inverts every direction test",
    "warrant": "non-linear payoff; a linear return calculation is simply wrong",
    "right": "short-dated and illiquid; no usable cost assumption",
    "adr_thin": "ADR liquidity and the underlying's calendar disagree",
}

# --- tiers ------------------------------------------------------------------
TIER_0 = 0   # the existing verified 28-company evidence universe
TIER_1 = 1   # 50-security validation universe
TIER_2 = 2   # 200-security operating universe
TIER_3 = 3   # up to 500, only after operational proof

TIER_TARGETS = {TIER_0: 28, TIER_1: 50, TIER_2: 200, TIER_3: 500}

# Promotion criteria, measured not asserted. Every one of these is a number the
# previous tier must actually produce.
PROMOTION_CRITERIA = {
    "data_completeness": 0.95,       # fraction of securities returning bars
    "source_success_rate": 0.95,
    "max_cycle_seconds": 1800,       # a cycle must fit inside its half-day slot
    "integrity_failures": 0,         # exactly zero, never "few"
    "min_effective_observations": 100,
}


class UniverseError(ValueError):
    """A security or tier that violates an eligibility rule."""


# --- eligibility ------------------------------------------------------------
# Versioned. Each rule states WHY it exists; a rule without a reason is a rule
# nobody can argue with later.
ELIGIBILITY_VERSION = "eligibility.v1"
MIN_PRICE = 5.0                  # sub-$5 spreads are a large fraction of price
MIN_MEDIAN_DOLLAR_VOLUME = 5e6   # the 5 bps slippage assumption needs liquidity
MIN_TRADING_HISTORY_DAYS = 250   # one year, so a 20-day lookback has context
MAX_MISSING_DATA_RATE = 0.02     # >2% gaps means the price series is unreliable


@dataclass(frozen=True)
class Security:
    """One tradable instrument, with the dates it was actually tradable."""
    symbol: str
    security_type: str
    sector: str = ""
    name: str = ""
    company_id: str = ""          # links to the evidence universe when curated
    listed_at: str = "1900-01-01"
    delisted_at: Optional[str] = None   # kept, never deleted
    delisting_reason: str = ""
    median_dollar_volume: Optional[float] = None
    tier: int = TIER_1

    def __post_init__(self):
        if self.security_type not in SUPPORTED_TYPES:
            reason = UNSUPPORTED_TYPES.get(
                self.security_type, "unknown security type")
            raise UniverseError(f"{self.symbol}: {self.security_type} is not "
                                f"supported — {reason}")

    def eligible_on(self, as_of: str) -> bool:
        """Was this security tradable on that date?

        THE SURVIVORSHIP GUARD. A security is eligible only inside its listing
        window, so a replay of 2019 cannot use a company that listed in 2023,
        and a company delisted in 2021 REMAINS eligible for every date before
        that -- which is what stops the failures from vanishing.
        """
        day = as_of[:10]
        if day < self.listed_at[:10]:
            return False
        if self.delisted_at and day > self.delisted_at[:10]:
            return False
        return True

    @property
    def is_delisted(self) -> bool:
        return bool(self.delisted_at)

    def as_dict(self) -> dict:
        return {"symbol": self.symbol, "type": self.security_type,
                "sector": self.sector, "name": self.name,
                "company_id": self.company_id, "listed_at": self.listed_at,
                "delisted_at": self.delisted_at,
                "delisting_reason": self.delisting_reason,
                "median_dollar_volume": self.median_dollar_volume,
                "tier": self.tier}


def check_eligibility(*, symbol: str, price: Optional[float],
                      median_dollar_volume: Optional[float],
                      history_days: Optional[int],
                      missing_rate: Optional[float]) -> List[str]:
    """Which versioned rules this security fails. Empty list means eligible.

    Returns REASONS rather than a boolean so a skipped security can be
    explained in the report -- "skipped 143" with no breakdown is not a
    measurement, it is a shrug.
    """
    failures = []
    if price is None:
        failures.append("no_price")
    elif price < MIN_PRICE:
        failures.append(f"price_below_{MIN_PRICE}")
    if median_dollar_volume is None:
        failures.append("no_liquidity_data")
    elif median_dollar_volume < MIN_MEDIAN_DOLLAR_VOLUME:
        failures.append("illiquid")
    if history_days is None:
        failures.append("no_history")
    elif history_days < MIN_TRADING_HISTORY_DAYS:
        failures.append("insufficient_history")
    if missing_rate is not None and missing_rate > MAX_MISSING_DATA_RATE:
        failures.append("excessive_missing_data")
    return failures


# --- the tier lists ---------------------------------------------------------
# TIER 1: a 50-security validation universe. Chosen for liquidity and sector
# spread, NOT for past performance -- selecting constituents on returns would
# bake the answer into the universe. ETFs are included precisely because they
# are the case the narrative gate can never serve.
_TIER1_ETFS = [
    ("SPY", BROAD_ETF, "Broad"), ("QQQ", BROAD_ETF, "Broad"),
    ("IWM", BROAD_ETF, "Broad"), ("DIA", BROAD_ETF, "Broad"),
    ("XLK", SECTOR_ETF, "Technology"), ("XLF", SECTOR_ETF, "Financials"),
    ("XLE", SECTOR_ETF, "Energy"), ("XLV", SECTOR_ETF, "Healthcare"),
    ("XLI", SECTOR_ETF, "Industrials"), ("XLY", SECTOR_ETF, "Consumer Disc"),
    ("XLP", SECTOR_ETF, "Consumer Staples"), ("XLU", SECTOR_ETF, "Utilities"),
    ("XLB", SECTOR_ETF, "Materials"), ("XLRE", SECTOR_ETF, "Real Estate"),
    ("XLC", SECTOR_ETF, "Communication"),
]

_TIER1_EQUITIES = [
    ("AAPL", "Technology"), ("MSFT", "Technology"), ("NVDA", "Technology"),
    ("AVGO", "Technology"), ("ORCL", "Technology"), ("CRM", "Technology"),
    ("AMD", "Technology"), ("ADBE", "Technology"),
    ("JPM", "Financials"), ("BAC", "Financials"), ("GS", "Financials"),
    ("V", "Financials"), ("MA", "Financials"),
    ("JNJ", "Healthcare"), ("UNH", "Healthcare"), ("PFE", "Healthcare"),
    ("ABBV", "Healthcare"), ("LLY", "Healthcare"),
    ("XOM", "Energy"), ("CVX", "Energy"), ("COP", "Energy"),
    ("CAT", "Industrials"), ("HON", "Industrials"), ("GE", "Industrials"),
    ("UNP", "Industrials"),
    ("AMZN", "Consumer Disc"), ("TSLA", "Consumer Disc"),
    ("HD", "Consumer Disc"), ("MCD", "Consumer Disc"), ("NKE", "Consumer Disc"),
    ("PG", "Consumer Staples"), ("KO", "Consumer Staples"),
    ("PEP", "Consumer Staples"), ("WMT", "Consumer Staples"),
    ("NEE", "Utilities"), ("DUK", "Utilities"),
    ("LIN", "Materials"), ("SHW", "Materials"),
    ("GOOGL", "Communication"), ("META", "Communication"),
    ("DIS", "Communication"), ("NFLX", "Communication"),
    ("SHOP", "Technology"), ("SQ", "Technology"), ("UBER", "Technology"),
]

# Known delistings/failures kept ON PURPOSE. Without at least one, the
# survivorship machinery is untested against the case it exists for.
_KNOWN_DELISTED = [
    ("FRC", EQUITY, "Financials", "2023-05-01",
     "seized by regulators and sold; equity wiped out"),
    ("SIVB", EQUITY, "Financials", "2023-03-17",
     "bank failure; equity wiped out"),
    ("TWTR", EQUITY, "Communication", "2022-10-28",
     "taken private"),
]


def tier_1() -> List[Security]:
    """The 50-security validation universe, plus retained delistings."""
    out = [Security(symbol=s, security_type=t, sector=sec, tier=TIER_1)
           for s, t, sec in _TIER1_ETFS]
    out += [Security(symbol=s, security_type=EQUITY, sector=sec, tier=TIER_1)
            for s, sec in _TIER1_EQUITIES]
    out += [Security(symbol=s, security_type=t, sector=sec, tier=TIER_1,
                     delisted_at=d, delisting_reason=r)
            for s, t, sec, d, r in _KNOWN_DELISTED]
    return out


def tier_0() -> List[Security]:
    """The existing evidence universe, expressed as securities.

    Reused rather than restated, so the two universes cannot drift apart.
    """
    from intent_engine.universe.companies import default_universe
    out = []
    for company in default_universe().prediction_companies():
        symbol = getattr(company, "tradable_instrument", None)
        if not symbol:
            continue
        out.append(Security(symbol=symbol, security_type=EQUITY,
                            sector=company.sector or "",
                            name=company.canonical_name or "",
                            company_id=company.company_id, tier=TIER_0))
    return out


def universe_for(tier: int) -> List[Security]:
    """Every security in this tier and below, de-duplicated by symbol.

    Cumulative because a tier is a widening, not a replacement -- and
    de-duplicated because the evidence universe and tier 1 genuinely overlap
    (SHOP is in both), and counting it twice would inflate every denominator.
    """
    if tier < TIER_0 or tier > TIER_3:
        raise UniverseError(f"unknown tier {tier}")
    seen: Dict[str, Security] = {}
    for sec in tier_0():
        seen.setdefault(sec.symbol, sec)
    if tier >= TIER_1:
        for sec in tier_1():
            # keep the tier-0 entry when it exists: it carries the company link
            seen.setdefault(sec.symbol, sec)
    if tier >= TIER_2:
        raise UniverseError(
            "TIER 2 (200 securities) is not populated. Promotion requires the "
            "measured criteria in PROMOTION_CRITERIA to be met by tier 1 "
            "first; an empty tier is reported, never silently substituted.")
    return list(seen.values())


def eligible_universe(tier: int, as_of: str) -> List[Security]:
    """Tier membership filtered to what was actually tradable on that date."""
    return [s for s in universe_for(tier) if s.eligible_on(as_of)]


@dataclass(frozen=True)
class PromotionCheck:
    tier: int
    measured: dict
    passed: tuple
    failed: tuple

    @property
    def promoted(self) -> bool:
        return not self.failed

    def as_dict(self) -> dict:
        return {"tier": self.tier, "measured": self.measured,
                "passed": list(self.passed), "failed": list(self.failed),
                "promoted": self.promoted}


def check_promotion(tier: int, measured: dict) -> PromotionCheck:
    """Has this tier earned the next one? Measured, never assumed."""
    passed, failed = [], []
    for name, threshold in PROMOTION_CRITERIA.items():
        value = measured.get(name)
        if value is None:
            failed.append(f"{name}: UNMEASURED")
            continue
        ok = (value <= threshold if name in ("max_cycle_seconds",
                                             "integrity_failures")
              else value >= threshold)
        (passed if ok else failed).append(f"{name}={value}")
    return PromotionCheck(tier, measured, tuple(passed), tuple(failed))


def composition(securities: Sequence[Security]) -> dict:
    """What the universe is actually made of, including its own limitation."""
    by_type: Dict[str, int] = {}
    by_sector: Dict[str, int] = {}
    for s in securities:
        by_type[s.security_type] = by_type.get(s.security_type, 0) + 1
        by_sector[s.sector or "unknown"] = by_sector.get(
            s.sector or "unknown", 0) + 1
    delisted = [s for s in securities if s.is_delisted]
    return {"version": UNIVERSE_VERSION,
            "eligibility_version": ELIGIBILITY_VERSION,
            "total": len(securities), "by_type": by_type,
            "by_sector": dict(sorted(by_sector.items())),
            "delisted_retained": len(delisted),
            "delisted_symbols": sorted(s.symbol for s in delisted),
            "with_company_evidence": sum(1 for s in securities if s.company_id),
            "survivorship_limitation": SURVIVORSHIP_LIMITATION}
