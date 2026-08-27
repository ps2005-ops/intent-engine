"""The cross-asset universe, with availability stated rather than assumed.

THE RULE THIS MODULE EXISTS FOR
--------------------------------
Do not silently synthesize an unavailable series. A dollar index this engine
cannot fetch must read UNAVAILABLE and stay None; deriving a proxy and
presenting it under the real name is how a chart becomes fiction that nobody
can audit, because the proxy's assumptions are nowhere on the page.

FOUR AVAILABILITY STATES
------------------------
    LIVE          a keyless public publisher provides it and the adapter works
    KEYED         a real source exists and needs a key this deployment lacks
    DERIVABLE     not published, but computable from LIVE series by a stated
                  rule -- and the rule travels with the value
    UNAVAILABLE   no source this engine can read publishes it

DERIVABLE IS NOT LIVE
---------------------
A derived series carries `derivation` and enters the evidence graph with
standing INFERRED and `depends_on` naming its inputs. That is what keeps a
curve slope computed from two yields from later corroborating either of them
-- the double-counting wall reads the same lineage.

WHY LICENSED SERIES ARE LISTED AT ALL
--------------------------------------
OIS, currency basis and dealer gamma are listed as KEYED or UNAVAILABLE
rather than omitted. An omitted series is indistinguishable from one nobody
thought of; a listed one with a stated reason is a research priority with a
cost attached, and `missing()` is what feeds it into the queue.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .vocabulary import ALL_KINDS, MACRO, MARKET_STRUCTURE, require

CONTRACT = "econ_series.v1"

LIVE = "LIVE"
KEYED = "KEYED"
DERIVABLE = "DERIVABLE"
UNAVAILABLE = "UNAVAILABLE"
AVAILABILITY = (LIVE, KEYED, DERIVABLE, UNAVAILABLE)


@dataclass(frozen=True)
class SeriesSpec:
    """One cross-asset series: what it is, who publishes it, can we read it."""

    key: str
    #: The evidence-graph kind this series measures.
    kind: str
    label: str
    unit: str
    frequency: str
    availability: str
    publisher: str = ""
    #: For DERIVABLE only: the rule, and the keys it reads.
    derivation: str = ""
    inputs: Tuple[str, ...] = ()
    reason: str = ""

    def __post_init__(self) -> None:
        require(self.availability in AVAILABILITY,
                f"unknown availability {self.availability!r}")
        require(self.kind in ALL_KINDS,
                f"{self.kind!r} is not in the node vocabulary")
        if self.availability == DERIVABLE:
            require(bool(self.derivation) and bool(self.inputs),
                    f"{self.key} is DERIVABLE and must state the rule and "
                    "the series it reads; a derived value whose derivation "
                    "is not recorded is a number with no provenance")
        if self.availability in (KEYED, UNAVAILABLE):
            require(bool(self.reason),
                    f"{self.key} is {self.availability} and must say why; "
                    "an unexplained gap is indistinguishable from a series "
                    "nobody thought of")

    def as_dict(self) -> dict:
        return {"key": self.key, "kind": self.kind, "label": self.label,
                "unit": self.unit, "frequency": self.frequency,
                "availability": self.availability,
                "publisher": self.publisher, "derivation": self.derivation,
                "inputs": list(self.inputs), "reason": self.reason}


def _s(key, kind, label, unit, freq, avail, publisher="", derivation="",
       inputs=(), reason=""):
    return SeriesSpec(key=key, kind=kind, label=label, unit=unit,
                      frequency=freq, availability=avail,
                      publisher=publisher, derivation=derivation,
                      inputs=tuple(inputs), reason=reason)


#: THE UNIVERSE. Grouped as Section 5 groups it.
UNIVERSE: Tuple[SeriesSpec, ...] = (
    # --- RATES --------------------------------------------------------------
    _s("policy_rate", "policy_rate", "policy rate", "percent", "monthly",
       LIVE, publisher="central bank"),
    _s("sofr", "sofr", "secured overnight financing rate", "percent",
       "daily", KEYED, publisher="Federal Reserve Bank of New York",
       reason="the NY Fed reference-rate API is keyless but rate-limited per "
              "identified caller; this deployment has no registered "
              "identifier, so the adapter exists and the series does not"),
    _s("ois", "ois", "overnight index swap curve", "percent", "daily",
       UNAVAILABLE, reason="swap curves are licensed; no public publisher "
                           "this engine can read carries them"),
    _s("treasury_2y", "treasury_2y", "2-year Treasury yield", "percent",
       "daily", LIVE, publisher="US Treasury"),
    _s("treasury_5y", "treasury_5y", "5-year Treasury yield", "percent",
       "daily", LIVE, publisher="US Treasury"),
    _s("treasury_10y", "treasury_10y", "10-year Treasury yield", "percent",
       "daily", LIVE, publisher="US Treasury"),
    _s("treasury_30y", "treasury_30y", "30-year Treasury yield", "percent",
       "daily", LIVE, publisher="US Treasury"),
    _s("curve_2s10s", "curve_slope", "2s10s curve slope", "basis points",
       "daily", DERIVABLE, derivation="treasury_10y minus treasury_2y",
       inputs=("treasury_10y", "treasury_2y")),
    _s("curve_5s30s", "curve_slope", "5s30s curve slope", "basis points",
       "daily", DERIVABLE, derivation="treasury_30y minus treasury_5y",
       inputs=("treasury_30y", "treasury_5y")),
    _s("butterfly_2s5s10s", "curve_butterfly", "2s5s10s butterfly",
       "basis points", "daily", DERIVABLE,
       derivation="2 * treasury_5y minus treasury_2y minus treasury_10y",
       inputs=("treasury_5y", "treasury_2y", "treasury_10y")),
    _s("real_yield_10y", "real_yield", "10-year real yield", "percent",
       "daily", DERIVABLE,
       derivation=("treasury_10y minus the latest published year-on-year "
                   "inflation rate; a crude proxy for a TIPS yield and "
                   "labelled as one, never as the TIPS yield itself"),
       inputs=("treasury_10y", "inflation")),

    # --- CREDIT -------------------------------------------------------------
    _s("ig_spread", "credit_spread_ig", "investment-grade credit spread",
       "basis points", "daily", KEYED,
       reason="index-level spreads are published by index providers under "
              "licence; the free mirrors are stale and unattributable"),
    _s("hy_spread", "credit_spread_hy", "high-yield credit spread",
       "basis points", "daily", KEYED,
       reason="as investment grade: licensed at index level"),
    _s("financial_conditions", "financial_conditions",
       "financial conditions index", "index", "weekly", LIVE,
       publisher="Federal Reserve Bank of Chicago"),
    _s("bank_stress", "bank_stress", "bank lending standards", "net percent",
       "quarterly", LIVE, publisher="Federal Reserve senior loan officer "
                                    "survey"),

    # --- FX -----------------------------------------------------------------
    _s("dxy", "fx_dxy", "trade-weighted dollar", "index", "daily", LIVE,
       publisher="Federal Reserve H.10"),
    _s("eurusd", "fx_cross", "EUR/USD", "rate", "daily", LIVE,
       publisher="European Central Bank"),
    _s("usdjpy", "fx_cross", "USD/JPY", "rate", "daily", LIVE,
       publisher="European Central Bank"),
    _s("currency_basis", "currency_basis", "cross-currency basis",
       "basis points", "daily", UNAVAILABLE,
       reason="basis swaps are an OTC market with no public print"),

    # --- VOLATILITY / MARKET STRUCTURE --------------------------------------
    _s("vix", "vix", "equity implied volatility", "index", "daily", KEYED,
       reason="the index itself is licensed; the underlying options are not "
              "retrievable without a market-data subscription"),
    _s("realised_vol_20d", "realised_vol", "20-day realised volatility",
       "annualised percent", "daily", DERIVABLE,
       derivation="annualised standard deviation of 20 daily log returns of "
                  "the reference equity index",
       inputs=("sector_return",)),
    _s("vol_term", "vol_term_structure", "implied volatility term structure",
       "ratio", "daily", UNAVAILABLE,
       reason="requires an option surface; see vix"),
    _s("skew", "skew", "implied volatility skew", "ratio", "daily",
       UNAVAILABLE, reason="requires an option surface; see vix"),
    _s("dealer_gamma", "dealer_gamma_proxy", "aggregate dealer gamma",
       "notional", "daily", UNAVAILABLE,
       reason="estimable only from full option open interest by strike; "
              "reflexivity treats an unknown gamma sign as NOT armed rather "
              "than guessing it, because it is the loop a guess matters most "
              "in"),
    _s("breadth", "breadth", "advance-decline breadth", "ratio", "daily",
       DERIVABLE,
       derivation="share of tracked instruments closing above their 50-day "
                  "average, over the instruments this engine actually "
                  "prices; NOT the exchange-wide statistic of the same name",
       inputs=("sector_return",)),
    _s("funding_stress", "funding_stress", "funding stress", "basis points",
       "daily", DERIVABLE,
       derivation="spread of the shortest available money-market rate over "
                  "the policy rate",
       inputs=("policy_rate",)),

    # --- COMMODITIES --------------------------------------------------------
    _s("oil", "commodity_oil", "crude oil", "USD/barrel", "daily", LIVE,
       publisher="US Energy Information Administration"),
    _s("gas", "commodity_gas", "natural gas", "USD/MMBtu", "daily", LIVE,
       publisher="US Energy Information Administration"),
    _s("copper", "commodity_copper", "copper", "USD/tonne", "daily", KEYED,
       reason="exchange settlement prices are licensed"),
    _s("gold", "commodity_gold", "gold", "USD/ounce", "daily", KEYED,
       reason="exchange settlement prices are licensed"),
    _s("ags", "commodity_ags", "agricultural benchmark", "index", "monthly",
       LIVE, publisher="US Department of Agriculture"),
    _s("oil_curve", "commodity_curve", "crude oil curve shape", "ratio",
       "daily", UNAVAILABLE,
       reason="futures term structure is licensed; the spot series alone "
              "cannot express contango or backwardation, and inferring one "
              "would be inventing the shape this series exists to report"),

    # --- MACRO --------------------------------------------------------------
    _s("inflation", "inflation", "consumer price inflation", "percent",
       "monthly", LIVE, publisher="Bureau of Labor Statistics"),
    _s("labour", "labour", "unemployment rate", "percent", "monthly", LIVE,
       publisher="Bureau of Labor Statistics"),
    _s("wages", "wages", "average hourly earnings", "percent", "monthly",
       LIVE, publisher="Bureau of Labor Statistics"),
    _s("growth", "growth", "real output growth", "percent", "quarterly",
       LIVE, publisher="Bureau of Economic Analysis"),
    _s("industrial_production", "industrial_production",
       "industrial production", "index", "monthly", LIVE,
       publisher="Federal Reserve G.17"),
    _s("housing", "housing", "housing starts", "thousands", "monthly", LIVE,
       publisher="US Census Bureau"),

    # --- EQUITY ------------------------------------------------------------
    _s("sector_return", "sector_return", "sector total return", "percent",
       "daily", LIVE, publisher="public daily closes"),
    _s("small_large", "small_large_ratio", "small over large capitalisation",
       "ratio", "daily", DERIVABLE,
       derivation="ratio of the small-cap to the large-cap reference "
                  "instrument's cumulative return",
       inputs=("sector_return",)),
)

BY_KEY: Dict[str, SeriesSpec] = {s.key: s for s in UNIVERSE}


def available(*states: str) -> List[SeriesSpec]:
    wanted = set(states) or {LIVE}
    return [s for s in UNIVERSE if s.availability in wanted]


def missing() -> List[dict]:
    """Series a real analyst would want and this engine cannot read.

    Feeds the research queue. Each one carries the reason, so the queue holds
    "we cannot see dealer gamma because it needs a full option surface"
    rather than a blank.
    """
    return [{"key": s.key, "label": s.label,
             "availability": s.availability, "reason": s.reason}
            for s in UNIVERSE if s.availability in (KEYED, UNAVAILABLE)]


def coverage() -> dict:
    by_state: Dict[str, int] = {a: 0 for a in AVAILABILITY}
    for s in UNIVERSE:
        by_state[s.availability] += 1
    return {"contract": CONTRACT, "series": len(UNIVERSE),
            "by_availability": by_state,
            "readable_now": by_state[LIVE] + by_state[DERIVABLE],
            "note": ("DERIVABLE series are computed from LIVE ones by a "
                     "stated rule and enter the graph as INFERRED with their "
                     "inputs named; they never corroborate their own inputs")}
