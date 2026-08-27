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



# =============================================================================
# BEHAVIOURAL SERIES (Section 4's collective-human family)
# =============================================================================
# Section 27's rule applies here more sharply than anywhere else: NEVER
# FABRICATE UNAVAILABLE DATA. The temptation with behavioural series is
# acute, because a plausible-looking sentiment number is easy to synthesise
# and nobody would immediately notice. So the ones that are genuinely
# readable are marked LIVE with their publisher named, and the ones that are
# proprietary, licensed or simply not published are marked UNAVAILABLE with
# the reason -- which is what keeps the collective-state coverage figure
# honest rather than flattering.

#: A NOTE ON WHAT WAS CHECKED, NOT ASSUMED
#: ----------------------------------------
#: These were first written as LIVE, because the underlying figures are
#: public and the series ids are real. Then the endpoints were actually
#: called. The BLS API answers and is genuinely keyless -- so the two series
#: this engine reads through it are LIVE. FRED's keyless CSV endpoint did NOT
#: answer this engine within a usable timeout, and `macro_ingest` already
#: records that the FRED API needs a key the deployment does not have. So
#: every FRED-routed series below is KEYED, which is the difference between a
#: coverage figure that is true and one that merely looks better.
BEHAVIOURAL: Tuple[SeriesSpec, ...] = (
    # --- readable now, keyless, verified by calling it ----------------------
    _s("JTS000000000000000QUR", "quits", "US quits rate, total nonfarm",
       "percent", "monthly", LIVE, publisher="BLS JOLTS (api.bls.gov)"),
    _s("LNS11300000", "labour_participation",
       "US labour force participation rate", "percent", "monthly", LIVE,
       publisher="BLS (api.bls.gov)"),

    # --- real, public, and behind a key this deployment does not have -------
    _s("UMCSENT", "survey_confidence", "U. Michigan consumer sentiment",
       "index", "monthly", KEYED, publisher="University of Michigan / FRED",
       reason="routed through FRED, whose API needs a key this deployment "
              "does not hold; the keyless fredgraph CSV endpoint did not "
              "answer within 12s when called"),
    _s("MICH", "household_expectation", "U. Michigan inflation expectation",
       "percent", "monthly", KEYED, publisher="University of Michigan / FRED",
       reason="same FRED key gap as UMCSENT"),
    _s("PSAVERT", "saving_rate", "personal saving rate", "percent",
       "monthly", KEYED, publisher="BEA / FRED",
       reason="same FRED key gap; BEA's own API also requires registration"),
    _s("BABATOTALSAUS", "business_formation", "business applications",
       "thousands", "monthly", KEYED, publisher="Census BFS / FRED",
       reason="same FRED key gap. The Census BFS API was tested directly and "
              "returns 'Missing Key'; a guessed bulk-CSV path 404s. A "
              "keyless route may exist and has not been found, which is a "
              "different statement from one existing"),
    _s("DRCCLACBS", "delinquency", "credit card delinquency rate, all banks",
       "percent", "quarterly", KEYED, publisher="Federal Reserve H.8 / FRED",
       reason="same FRED key gap. This is the single most damaging gap in "
              "the behavioural family: delinquency is the discriminating "
              "instrument for financial anxiety, and without it that "
              "construct rests on contested proxies alone"),
    _s("REVOLSL", "revolving_balance", "revolving consumer credit",
       "billions", "monthly", KEYED, publisher="Federal Reserve G.19 / FRED",
       reason="same FRED key gap"),

    # --- derivable from series already read ---------------------------------
    _s("job_switching_rate", "job_switching", "quits relative to "
       "participation", "ratio", "monthly", DERIVABLE,
       derivation="the quits rate against the participation rate; a rising "
                  "quits rate on a falling participation rate is people "
                  "leaving the labour force, which is the OPPOSITE reading "
                  "to confident job-switching",
       inputs=("JTS000000000000000QUR", "LNS11300000")),
    _s("defensive_share", "defensive_spending",
       "staples share of retail control group", "ratio", "monthly",
       UNAVAILABLE,
       reason="requires the retail sales control-group detail, which routes "
              "through FRED or the Census advance report; no adapter reads "
              "either, so this is declared rather than approximated"),

    # --- named, and NOT available ------------------------------------------
    _s("consumer_trade_down", "trade_down", "observed trade-down intensity",
       "ratio", "monthly", UNAVAILABLE,
       reason="no public series measures basket substitution directly; the "
              "readable evidence is company disclosure of it, which enters "
              "as COMPANY evidence and therefore may not corroborate a "
              "consumer aggregate built from the same disclosures"),
    _s("big_ticket_intent", "big_ticket_intent",
       "durable-goods buying conditions", "index", "monthly", KEYED,
       reason="the U. Michigan buying-conditions sub-indices are published "
              "but not in the free FRED series set this engine reads"),
    _s("household_trust", "trust_index", "trust in institutions",
       "index", "annual", UNAVAILABLE,
       reason="the major trust barometers are proprietary and annual; an "
              "annual figure cannot support a quarterly-horizon forecast "
              "comparison, so this construct stays measurement-blocked"),
    _s("search_distress", "search_interest", "search volume, distress terms",
       "index", "weekly", UNAVAILABLE,
       reason="trends APIs forbid the redistribution this would require, and "
              "the unauthenticated endpoints are rate-limited to the point "
              "of unusability. Named so the gap is legible rather than "
              "looking like an oversight"),
    _s("retail_speculation", "retail_speculation",
       "retail share of speculative volume", "ratio", "daily", UNAVAILABLE,
       reason="retail order-flow share is a vendor product; the free proxies "
              "for it are themselves derived from price, which would make "
              "this a market signal wearing a behavioural label"),
    _s("public_language_tone", "public_language", "aggregate public tone",
       "index", "daily", UNAVAILABLE,
       reason="no licensed corpus is configured; a tone index built from "
              "whatever text happened to be scrapeable measures the scrape, "
              "not the population"),
)

# Folded into the one universe, so `available()`, `missing()` and
# `coverage()` all see the behavioural family without a second code path --
# a parallel registry is how a series ends up readable by one reporter and
# invisible to another.
UNIVERSE = UNIVERSE + BEHAVIOURAL
BY_KEY = {s.key: s for s in UNIVERSE}


def behavioural_coverage() -> dict:
    """What the collective-state layer can actually measure today.

    Reported separately from the economic coverage because the two have very
    different shapes: the macro side is mostly readable and the behavioural
    side is mostly not, and averaging them into one figure would hide the
    fact that half the collective vocabulary has no instrument at all.
    """
    from .proxies import BY_DIMENSION, uncovered_dimensions
    readable = {s.kind for s in BEHAVIOURAL
                if s.availability in (LIVE, DERIVABLE)}
    blocked = {s.kind: s.reason for s in BEHAVIOURAL
               if s.availability in (UNAVAILABLE, KEYED)}
    measurable, blocked_dims = [], {}
    for dim, proxies in BY_DIMENSION.items():
        kinds = {p.kind for p in proxies}
        if kinds & readable:
            measurable.append(dim)
        else:
            blocked_dims[dim] = sorted(
                f"{k}: {blocked.get(k, 'no series declared')}"
                for k in kinds)
    return {"behavioural_series": len(BEHAVIOURAL),
            "readable_now": len(readable),
            "blocked": len(blocked),
            "dimensions_measurable_now": sorted(measurable),
            "dimensions_blocked_by_data": blocked_dims,
            "dimensions_with_no_proxy_at_all": uncovered_dimensions()}


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
