"""ALFRED: vintage-correct economic and behavioural series, without a key.

WHY ALFRED AND NOT FRED
-----------------------
`fred.stlouisfed.org/graph/fredgraph.csv` accepts a `vintage_date` parameter
and SILENTLY IGNORES IT. Ask it for the saving rate as known in September 2008
and it hands back the series as known today, ending in 2026, with no error and
no warning. A historical replay built on that endpoint leaks hindsight into
every fold while appearing to be walled -- which is worse than not being
walled, because the leak is invisible.

`alfred.stlouisfed.org/graph/alfredgraph.csv` honours it. Same key-free
access, and the column comes back named `PSAVERT_20080915` so the vintage is
carried in the payload rather than only in the request.

WHY THIS MATTERS NUMERICALLY, NOT JUST IN PRINCIPLE
---------------------------------------------------
The US personal saving rate for June 2008:

    as known 2008-09-15    2.5
    as known 2010-01-04    3.5
    as known 2015-01-05    5.6
    as known 2026-01-02    4.6

A model backtested on 4.6 is reading a number that did not exist for years,
and it is wrong in the direction that flatters any account keyed on household
caution. Section 7 forbids using future-revised values in a vintage run, and
this is the module that makes obeying it possible.

WHY THE PREVIOUS RUN CALLED THIS KEYED
--------------------------------------
It called `fredgraph.csv` once with a 12-second timeout, got a timeout, and
recorded KEY_REQUIRED. The endpoint is keyless and answers in about 15-20
seconds under a plain user agent. A single probe with too short a deadline
became a documented architectural constraint -- so `probe_behavioural_sources`
now exists, and every availability claim in `econ.series` is traceable to a
recorded probe rather than to an inference.

NO CREDENTIALS
--------------
Nothing here reads an environment variable, and there is no key to leak.
"""
from __future__ import annotations

import datetime as _dt
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from intent_engine.econ import evidence as EV
from intent_engine.econ import vocabulary as V

CONTRACT = "alfred_ingest.v1"

_ALFRED = "https://alfred.stlouisfed.org/graph/alfredgraph.csv"
_FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv"

#: Long enough for the endpoint to actually answer. The previous run used 12
#: and concluded the source needed a key.
TIMEOUT = 30

_UA = {"User-Agent": "intent-engine research (github.com/intent-engine); "
                     "contact in repository"}


class AlfredError(RuntimeError):
    """The publisher did not answer, or answered with something unusable."""


class VintageIgnored(AlfredError):
    """A vintage request came back carrying observations after the vintage.

    The specific failure this module exists to prevent. Raised rather than
    warned: a caller that silently accepted this would be running a leaked
    backtest and reporting it as a walled one.
    """


# =============================================================================
# SERIES REGISTRY
# =============================================================================

@dataclass(frozen=True)
class AlfredSeries:
    """One FRED/ALFRED series, and what it measures for this engine."""

    series_id: str
    node_class: str
    kind: str
    label: str
    unit: str
    #: Days after the reference period before the figure is normally published.
    #: Only used when a vintage is NOT requested; with a vintage the publisher
    #: has already told us what was knowable.
    publication_lag_days: int
    subject: str = "US_households"
    #: True when higher means "more of the thing the construct names". Recorded
    #: here so the proxy layer is not the only place the direction lives.
    higher_is_more: bool = True

    def __post_init__(self) -> None:
        if self.kind not in V.ALL_KINDS:
            raise AlfredError(
                f"{self.series_id} claims kind {self.kind!r}, which is not in "
                "the node vocabulary; an unrecognised kind is how one economic "
                "quantity becomes two that never corroborate each other")


def _s(sid, cls, kind, label, unit, lag, **kw):
    return AlfredSeries(series_id=sid, node_class=cls, kind=kind, label=label,
                        unit=unit, publication_lag_days=lag, **kw)


B, M = V.BEHAVIORAL, V.MACRO

#: Every series verified by an actual call. `scripts/probe_behavioural_sources`
#: and `tests/test_alfred_ingest` both exercise this list.
REGISTRY: Tuple[AlfredSeries, ...] = (
    # --- behavioural: what households did or reported --------------------
    _s("UMCSENT", B, "survey_confidence",
       "U. Michigan consumer sentiment", "index", 15),
    _s("MICH", B, "household_expectation",
       "U. Michigan 1-year inflation expectation", "percent", 15),
    _s("PSAVERT", B, "saving_rate", "US personal saving rate", "percent", 30),
    _s("DRCCLACBS", B, "delinquency",
       "credit card delinquency rate, all commercial banks", "percent", 60),
    _s("REVOLSL", B, "revolving_balance",
       "revolving consumer credit outstanding", "billions", 40),
    _s("BABATOTALSAUS", B, "business_formation",
       "business applications, total", "thousands", 35),
    _s("JTSQUR", B, "quits", "quits rate, total nonfarm", "percent", 40),
    _s("CIVPART", B, "labour_participation",
       "labour force participation rate", "percent", 20),
    #: Added after a second probe round. Every one of these was called before
    #: being listed; `reports/behavioural_source_probe.json` is the record.
    _s("CORCACBS", B, "delinquency",
       "credit card charge-off rate, all commercial banks", "percent", 60),
    _s("DRSFRMACBS", B, "delinquency",
       "single-family mortgage delinquency rate", "percent", 60),
    _s("TDSP", B, "debt_service_burden",
       "household debt service payments as a share of disposable income",
       "percent", 70),
    _s("U6RATE", B, "underemployment",
       "U-6 total unemployed plus marginally attached and part-time for "
       "economic reasons", "percent", 20),
    _s("EMRATIO", B, "employment_ratio",
       "employment-population ratio", "percent", 20),
    _s("BOGZ1FL153064486Q", B, "risk_taking_proxy",
       "household equity holdings as a share of financial assets",
       "percent", 75),
    _s("DGORDER", B, "big_ticket_intent",
       "manufacturers' new orders, durable goods", "millions", 35),
    _s("HSN1F", B, "big_ticket_intent",
       "new one-family houses sold", "thousands", 30),
    _s("USACSCICP02STSAM", B, "survey_expectation",
       "OECD consumer confidence indicator, United States", "index", 40),

    # --- macro: the base economic model's own inputs ----------------------
    _s("UNRATE", M, "labour", "US unemployment rate", "percent", 20),
    _s("CPIAUCSL", M, "inflation", "CPI, all urban consumers", "index", 15),
    _s("DFF", M, "policy_rate", "effective federal funds rate", "percent", 1),
    _s("DGS2", M, "treasury_2y", "2-year Treasury constant maturity",
       "percent", 1),
    _s("DGS10", M, "treasury_10y", "10-year Treasury constant maturity",
       "percent", 1),
    _s("BAMLH0A0HYM2", M, "credit_spread_hy",
       "ICE BofA US high yield option-adjusted spread", "percent", 1),
    _s("HOUST", M, "housing", "housing starts", "thousands", 20),
    _s("INDPRO", M, "industrial_production", "industrial production index",
       "index", 20),
    _s("PCEC96", M, "consumer_demand", "real personal consumption",
       "billions", 30),
    _s("GDPC1", M, "growth", "real gross domestic product", "billions", 30),
)

BY_ID: Dict[str, AlfredSeries] = {s.series_id: s for s in REGISTRY}
BEHAVIOURAL_IDS = tuple(s.series_id for s in REGISTRY
                        if s.node_class == V.BEHAVIORAL)
MACRO_IDS = tuple(s.series_id for s in REGISTRY if s.node_class == V.MACRO)


# =============================================================================
# FETCH
# =============================================================================

def _http_get(url: str) -> str:  # pragma: no cover - the live path
    socket.setdefaulttimeout(TIMEOUT)
    try:
        req = urllib.request.Request(url, headers=_UA)
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raise AlfredError(f"HTTP {e.code} for {url}") from e
    except Exception as e:                                  # noqa: BLE001
        raise AlfredError(f"{type(e).__name__}: {e}") from e


def _parse_csv(body: str) -> Tuple[str, List[Tuple[str, float]]]:
    """Return (value column name, [(date, value)]). Missing values dropped.

    ALFRED writes '.' for a period with no observation. Those are DROPPED
    rather than zero-filled: a zero saving rate and an unpublished saving rate
    support completely different conclusions.
    """
    lines = [l for l in body.strip().splitlines() if l.strip()]
    if len(lines) < 2:
        raise AlfredError(f"response had {len(lines)} line(s); expected a "
                          "header and at least one observation")
    header = lines[0].split(",")
    if len(header) < 2:
        raise AlfredError(f"unparseable header: {lines[0]!r}")
    col = header[1].strip()
    out: List[Tuple[str, float]] = []
    for line in lines[1:]:
        parts = line.split(",")
        if len(parts) < 2:
            continue
        try:
            out.append((parts[0].strip(), float(parts[1])))
        except ValueError:
            continue                      # '.' -- no observation that period
    if not out:
        raise AlfredError(f"{col}: no numeric observations in {len(lines)-1} "
                          "rows; the series exists and is empty, which is a "
                          "different problem from a failed request")
    return col, out


def fetch_series(series_id: str, *, vintage: str = "",
                 fetcher: Optional[Callable[[str], str]] = None
                 ) -> Tuple[str, List[Tuple[str, float]]]:
    """One series, optionally as it was known on `vintage`.

    With a vintage this calls ALFRED, and REFUSES a response containing
    observations dated after the vintage -- the exact symptom of the endpoint
    ignoring the parameter, which `fredgraph` does silently.
    """
    get = fetcher or _http_get
    if vintage:
        body = get(f"{_ALFRED}?id={series_id}&vintage_date={vintage}")
        col, rows = _parse_csv(body)
        leaked = [d for d, _ in rows if d > vintage]
        if leaked:
            raise VintageIgnored(
                f"{series_id} at vintage {vintage} returned {len(leaked)} "
                f"observation(s) dated after it (latest {max(leaked)}). The "
                "endpoint ignored the vintage parameter, so every value here "
                "may be a later revision. This is refused rather than "
                "warned: a leaked backtest reported as a walled one is worse "
                "than an unwalled one.")
        return col, rows
    body = get(f"{_FRED}?id={series_id}")
    return _parse_csv(body)


def _published_at(period: str, lag_days: int) -> str:
    """When a figure became knowable, when no vintage was requested."""
    y, m, d = (int(x) for x in period.split("-"))
    nxt = _dt.date(y + (m == 12), (m % 12) + 1, 1)
    return (nxt + _dt.timedelta(days=lag_days)).isoformat()


def to_nodes(spec: AlfredSeries, rows: Sequence[Tuple[str, float]], *,
             vintage: str = "", retrieved_at: str = "",
             since: str = "") -> List[EV.EconomicNode]:
    """Turn parsed rows into evidence nodes with honest availability dates.

    With a vintage, `available_at` IS the vintage: the publisher has told us
    the figure was knowable then, which beats any assumed lag. Without one,
    the per-series publication lag is used and the node says so.
    """
    out = []
    for period, value in rows:
        if since and period < since:
            continue
        available = vintage or _published_at(period, spec.publication_lag_days)
        basis = ("publisher vintage" if vintage
                 else f"assumed {spec.publication_lag_days}d publication lag")
        out.append(EV.node(
            node_class=spec.node_class, kind=spec.kind, subject=spec.subject,
            standing=V.OBSERVED, occurred_at=period, available_at=available,
            value=value, unit=spec.unit,
            statement=f"{spec.label}: {value}{spec.unit} for {period}",
            publisher="Federal Reserve Bank of St. Louis (ALFRED/FRED)",
            venue="alfred.stlouisfed.org" if vintage else "fred.stlouisfed.org",
            document_id=spec.series_id, producer=f"{CONTRACT}:{basis}",
            confidence=0.9, retrieved_at=retrieved_at))
    return out


def collect(*, retrieved_at: str, vintage: str = "",
            only: Sequence[str] = (), behavioural_only: bool = False,
            since: str = "",
            fetcher: Optional[Callable[[str], str]] = None) -> dict:
    """Fetch every configured series, reporting what failed by name.

    A publisher that refuses must never look like an economy that did not
    move, so `sources_failed` is part of the return value rather than a log
    line, and `empty_because` distinguishes the two states explicitly.
    """
    wanted = [s for s in REGISTRY
              if (not only or s.series_id in only)
              and (not behavioural_only or s.node_class == V.BEHAVIORAL)]
    nodes: List[EV.EconomicNode] = []
    failures: Dict[str, str] = {}
    per_series: Dict[str, int] = {}
    for spec in wanted:
        try:
            _col, rows = fetch_series(spec.series_id, vintage=vintage,
                                      fetcher=fetcher)
            got = to_nodes(spec, rows, vintage=vintage,
                           retrieved_at=retrieved_at, since=since)
            nodes.extend(got)
            per_series[spec.series_id] = len(got)
        except Exception as exc:          # noqa: BLE001 - a feed must not
            failures[spec.series_id] = f"{type(exc).__name__}: {exc}"[:300]
    by_kind: Dict[str, int] = {}
    for n in nodes:
        by_kind[n.kind] = by_kind.get(n.kind, 0) + 1
    return {"contract": CONTRACT, "nodes": nodes, "collected": len(nodes),
            "vintage": vintage, "by_kind": by_kind,
            "per_series": per_series,
            "series_attempted": len(wanted),
            "series_failed": failures,
            "empty_because": ("" if nodes else
                              ("every series failed" if failures else
                               "series answered with no usable rows"))}
