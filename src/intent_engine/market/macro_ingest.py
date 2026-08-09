"""Real economic figures, from keyless public publishers.

WHAT THIS IS FOR
----------------
`macro_state` can hold a dated opinion about the economy. Until something
fills it, every economic chain in the engine starts at an UNKNOWN
MACRO_STATE node and no link below it can ever reach SUPPORTED. This is the
part that fills it.

WHY THESE SOURCES
-----------------
Treasury FiscalData is keyless, versioned, deep, and publishes the one thing
almost every transmission story starts from — the cost of money. It is chosen
because it is REACHABLE without an owner action, not because it is the most
informative series available. FRED would be better and needs a key the
environment does not have; when that key exists, adding it is a new entry in
`SERIES` and nothing else changes.

THE HONEST PART
---------------
FiscalData gives `record_date` — the month the figure describes — and no
release date at all. Neither easy answer is acceptable: an empty publication
date makes the figure unusable at any as-of, and treating `record_date` as the
release date claims the engine knew July's average rate on the 31st of July.

So publication is ASSUMED, with a deliberately generous lag, and the
assumption is carried on the observation rather than hidden in it. Erring late
can only make the engine look like it knew less than it did — which is the
safe direction, because the failure being guarded against is foresight the
engine never had.
"""
from __future__ import annotations

import datetime
import json
import urllib.parse
import urllib.request
from typing import Callable, List, Optional, Sequence

from . import macro_state as MS

CONTRACT = "macro_ingest.v1"

_FISCAL_V2 = ("https://api.fiscaldata.treasury.gov/services/api/fiscal_service"
              "/v2/accounting/od")
_FISCAL = _FISCAL_V2 + "/avg_interest_rates"

_TIMEOUT = 30
_HEADERS = {"User-Agent": "intent-engine/4.0 (economic world model)"}

#: How late a monthly Treasury dataset is ASSUMED to have been released.
#: The real release is a handful of business days into the following month;
#: 30 days is comfortably later than that, and later is the safe direction.
MONTHLY_PUBLICATION_LAG_DAYS = 30


def _http_get(url: str):  # pragma: no cover - exercised by the live path
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _assumed_publication(reference_period: str, lag_days: int) -> str:
    """A release date the engine is willing to be wrong about in one direction.

    Later than the truth means the engine under-claims what it knew. Earlier
    would mean it claims a figure before the publisher had it, which is
    exactly the leak `known_at` exists to stop.
    """
    day = datetime.date.fromisoformat(reference_period[:10])
    return (day + datetime.timedelta(days=lag_days)).isoformat()


def _rows(body) -> List[dict]:
    return [r for r in ((body or {}).get("data") or []) if isinstance(r, dict)]


def _as_float(raw) -> Optional[float]:
    """A number, or nothing. Never a zero standing in for a missing figure.

    Statistical feeds use empty strings, nulls and suppression markers for
    "not published", and `float("") -> 0.0` would be a measured economy
    reading zero inflation because the cell was blank.
    """
    if raw in (None, ""):
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _http_post(url: str, payload):  # pragma: no cover - live path
    body = json.dumps(payload).encode("utf-8")
    headers = dict(_HEADERS, **{"Content-Type": "application/json"})
    req = urllib.request.Request(url, headers=headers, data=body)
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def treasury_note_rate(*, retrieved_at: str, periods: int = 24,
                       fetcher: Optional[Callable] = None
                       ) -> List[MS.MacroObservation]:
    """Average interest rate on outstanding Treasury notes, by month.

    This is a MARKET_RATE, not a POLICY_RATE. The distinction matters: the
    average rate the Treasury actually pays reflects the whole outstanding
    stock and moves slowly, while a policy rate is set. Calling this a policy
    rate would let a slow-moving average be read as a central-bank decision.
    """
    get = fetcher or _http_get
    query = urllib.parse.urlencode({
        "filter": "security_desc:eq:Treasury Notes",
        "sort": "-record_date", "page[size]": str(periods)})
    body = get(f"{_FISCAL}?{query}")

    out: List[MS.MacroObservation] = []
    for row in _rows(body):
        period = str(row.get("record_date") or "")
        raw = row.get("avg_interest_rate_amt")
        if not period or raw in (None, ""):
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        out.append(MS.MacroObservation(
            state_kind=MS.MARKET_RATE,
            series_id="TREASURY_NOTES_AVG_RATE",
            label="Average interest rate on outstanding Treasury notes",
            value=value, unit="%", measure=MS.LEVEL,
            standing=MS.OBSERVED,
            reference_period=period,
            published_at=_assumed_publication(
                period, MONTHLY_PUBLICATION_LAG_DAYS),
            publication_basis=MS.ASSUMED_LAG,
            retrieved_at=retrieved_at,
            source="US Treasury, FiscalData",
            note=("release date not published by the source; assumed "
                  f"{MONTHLY_PUBLICATION_LAG_DAYS} days after period end")))
    return out


def treasury_bill_rate(*, retrieved_at: str, periods: int = 24,
                       fetcher: Optional[Callable] = None
                       ) -> List[MS.MacroObservation]:
    """Average interest rate on outstanding Treasury bills, by month.

    The short end of the same curve the note series measures at the long end.
    It is here so the engine can hold a SPREAD rather than a level: a rate
    rising is ambiguous, and a short rate rising ABOVE a long one is a
    recognisable credit condition. Neither series alone can say that.
    """
    get = fetcher or _http_get
    query = urllib.parse.urlencode({
        "filter": "security_desc:eq:Treasury Bills",
        "sort": "-record_date", "page[size]": str(periods)})
    body = get(f"{_FISCAL}?{query}")

    out: List[MS.MacroObservation] = []
    for row in _rows(body):
        period = str(row.get("record_date") or "")
        value = _as_float(row.get("avg_interest_rate_amt"))
        if not period or value is None:
            continue
        out.append(MS.MacroObservation(
            state_kind=MS.MARKET_RATE, area=MS.US,
            series_id="TREASURY_BILLS_AVG_RATE",
            label="Average interest rate on outstanding Treasury bills",
            value=value, unit="%", measure=MS.LEVEL,
            standing=MS.OBSERVED,
            reference_period=period,
            published_at=_assumed_publication(
                period, MONTHLY_PUBLICATION_LAG_DAYS),
            publication_basis=MS.ASSUMED_LAG,
            retrieved_at=retrieved_at,
            source="US Treasury, FiscalData",
            note=("release date not published by the source; assumed "
                  f"{MONTHLY_PUBLICATION_LAG_DAYS} days after period end")))
    return out


def treasury_interest_expense(*, retrieved_at: str, periods: int = 24,
                              fetcher: Optional[Callable] = None
                              ) -> List[MS.MacroObservation]:
    """What the federal government actually pays to carry its debt, monthly.

    A FISCAL condition and not a rate: the rate is what the market charges,
    this is what the borrower spends. They diverge for years at a time,
    because the stock reprices slowly, and a transmission story about
    government spending pressure needs the second, not the first.

    ONE ROW A MONTH, AND THE ENDPOINT RETURNS THREE. Alongside accrued
    interest the feed publishes amortised discount and amortised PREMIUM, and
    the premium line is negative. Filtering only on the security type left all
    three under one series id, the premium row sorted last, and the engine
    read the United States as being paid 0.134 billion dollars a month to
    borrow. The group filter below is the difference between a fiscal series
    and three unrelated accounting lines wearing one name.
    """
    get = fetcher or _http_get
    query = urllib.parse.urlencode({
        "filter": ("expense_type_desc:eq:Treasury Notes,"
                   "expense_group_desc:eq:ACCRUED INTEREST EXPENSE"),
        "sort": "-record_date", "page[size]": str(periods)})
    body = get(f"{_FISCAL_V2}/interest_expense?{query}")

    out: List[MS.MacroObservation] = []
    seen = set()
    for row in _rows(body):
        period = str(row.get("record_date") or "")
        value = _as_float(row.get("month_expense_amt"))
        if not period or value is None:
            continue
        if str(row.get("expense_group_desc") or "") != \
                "ACCRUED INTEREST EXPENSE":
            continue
        if period in seen:
            # Belt as well as braces: if the publisher ever adds a fourth
            # line, the engine drops it rather than letting two figures for
            # one month fight over which is the state.
            continue
        seen.add(period)
        out.append(MS.MacroObservation(
            state_kind=MS.FISCAL, area=MS.US,
            series_id="TREASURY_NOTES_INTEREST_EXPENSE",
            label="Monthly accrued interest expense on Treasury notes",
            value=value / 1e9, unit="bn USD", measure=MS.LEVEL,
            standing=MS.OBSERVED,
            reference_period=period,
            published_at=_assumed_publication(
                period, MONTHLY_PUBLICATION_LAG_DAYS),
            publication_basis=MS.ASSUMED_LAG,
            retrieved_at=retrieved_at,
            source="US Treasury, FiscalData",
            note=("release date not published by the source; assumed "
                  f"{MONTHLY_PUBLICATION_LAG_DAYS} days after period end")))
    return out


# --- Bank of Canada Valet ---------------------------------------------------
#
# Keyless, deep, and daily. Its figures carry the OBSERVATION date rather than
# a release date, and for a daily market series those are one business day
# apart at most — but "at most" is not "never", so the same conservative
# assumption applies and is recorded as ASSUMED_LAG rather than pretended away.
_VALET = "https://www.bankofcanada.ca/valet/observations"

#: A daily market series is published the next business day at the latest.
#: Three days covers a weekend without ever claiming same-day knowledge.
DAILY_PUBLICATION_LAG_DAYS = 3

#: Valet series -> (state kind, area, label, unit, measure, periods).
#:
#: PERIODS IS PER SERIES BECAUSE FREQUENCY IS. Asking for 24 observations of a
#: daily yield buys one month of history, and a panel built from it can only
#: compare August with July. The daily series ask for two years of business
#: days; the monthly indices ask for two years of months. One number for both
#: would either starve the panel or store forty years of a monthly index.
BOC_SERIES = {
    "V39079": (MS.POLICY_RATE, MS.CA,
               "Bank of Canada target for the overnight rate", "%", MS.LEVEL,
               520),
    "BD.CDN.10YR.DQ.YLD": (MS.MARKET_RATE, MS.CA,
                           "Government of Canada 10-year benchmark yield",
                           "%", MS.LEVEL, 520),
    "BD.CDN.2YR.DQ.YLD": (MS.MARKET_RATE, MS.CA,
                          "Government of Canada 2-year benchmark yield",
                          "%", MS.LEVEL, 520),
    "FXUSDCAD": (MS.CURRENCY, MS.GLOBAL,
                 "US dollar in Canadian dollars, daily average",
                 "CAD per USD", MS.LEVEL, 520),
    "M.BCPI": (MS.COMMODITY_PRICE, MS.GLOBAL,
               "Bank of Canada commodity price index, all commodities",
               "index", MS.LEVEL, 24),
    "M.ENER": (MS.ENERGY_PRICE, MS.GLOBAL,
               "Bank of Canada commodity price index, energy",
               "index", MS.LEVEL, 24),
}


def bank_of_canada(*, retrieved_at: str, periods: int = 24,
                   fetcher: Optional[Callable] = None,
                   only: Sequence[str] = ()) -> List[MS.MacroObservation]:
    """Every configured Valet series, in one request per series group.

    A currency and a commodity index are marked GLOBAL rather than CA: the
    Canadian dollar is not a fact about Canada alone, and pinning a cross rate
    to one side of it would let a US-exposed company's FX transmission read a
    Canadian macro state as if it were domestic.
    """
    get = fetcher or _http_get
    wanted = [s for s in BOC_SERIES if not only or s in only]
    out: List[MS.MacroObservation] = []
    for series_id in wanted:
        kind, area, label, unit, measure, depth = BOC_SERIES[series_id]
        body = get(f"{_VALET}/{urllib.parse.quote(series_id)}/json"
                   f"?recent={int(max(periods, depth))}")
        for row in (body or {}).get("observations") or []:
            if not isinstance(row, dict):
                continue
            period = str(row.get("d") or "")
            cell = row.get(series_id)
            value = _as_float(cell.get("v") if isinstance(cell, dict)
                              else cell)
            if not period or value is None:
                continue
            out.append(MS.MacroObservation(
                state_kind=kind, area=area,
                series_id=f"BOC_{series_id}", label=label,
                value=value, unit=unit, measure=measure,
                standing=MS.OBSERVED,
                reference_period=period,
                published_at=_assumed_publication(
                    period, DAILY_PUBLICATION_LAG_DAYS),
                publication_basis=MS.ASSUMED_LAG,
                retrieved_at=retrieved_at,
                source="Bank of Canada, Valet",
                note=("observation date published, release date not; assumed "
                      f"{DAILY_PUBLICATION_LAG_DAYS} days after observation")))
    return out


# --- Statistics Canada, Web Data Service ------------------------------------
#
# THE ONE SOURCE THAT DATES ITSELF. StatCan returns `releaseTime` with every
# data point — the actual moment the figure became public. Every other
# publisher reachable without a key leaves the engine assuming, so this is the
# only series family whose publication basis is PUBLISHER rather than
# ASSUMED_LAG, and the only one whose vintage discipline is a fact instead of
# a conservative guess.
_STATCAN = ("https://www150.statcan.gc.ca/t1/wds/rest"
            "/getDataFromVectorsAndLatestNPeriods")

#: vector id -> (state kind, area, label, unit, measure).
STATCAN_SERIES = {
    2062815: (MS.EMPLOYMENT, MS.CA,
              "Canada unemployment rate, seasonally adjusted", "%", MS.LEVEL),
    41690973: (MS.INFLATION, MS.CA,
               "Canada consumer price index, all items", "index", MS.LEVEL),
    65201210: (MS.GROWTH, MS.CA,
               "Canada real GDP at basic prices, all industries",
               "mn chained CAD", MS.LEVEL),
    800450: (MS.INDUSTRIAL_PRODUCTION, MS.CA,
             "Canada manufacturing sales, all industries",
             "thousand CAD", MS.LEVEL),
    79311387: (MS.WAGES, MS.CA,
               "Canada average weekly earnings, industrial aggregate",
               "CAD", MS.LEVEL),
    1409153: (MS.HOUSING, MS.CA,
              "Canada housing starts, all areas", "units", MS.LEVEL),
}


def statistics_canada(*, retrieved_at: str, periods: int = 24,
                      fetcher: Optional[Callable] = None,
                      only: Sequence[int] = ()) -> List[MS.MacroObservation]:
    """Canadian national accounts and labour figures, with real release dates.

    `releaseTime` is used verbatim. It is the only publication date in this
    module that the engine did not have to invent, and using it means a
    backtest at a past date sees exactly the vintage a reader would have had.
    """
    post = fetcher or _http_post
    wanted = [v for v in STATCAN_SERIES if not only or v in only]
    body = post(_STATCAN, [{"vectorId": v, "latestN": int(periods)}
                           for v in wanted])
    out: List[MS.MacroObservation] = []
    for item in body if isinstance(body, list) else []:
        if not isinstance(item, dict) or item.get("status") != "SUCCESS":
            continue
        obj = item.get("object") or {}
        spec = STATCAN_SERIES.get(obj.get("vectorId"))
        if not spec:
            continue
        kind, area, label, unit, measure = spec
        for point in obj.get("vectorDataPoint") or []:
            period = str((point or {}).get("refPer") or "")
            value = _as_float((point or {}).get("value"))
            released = str((point or {}).get("releaseTime") or "")[:10]
            if not period or value is None or not released:
                continue
            out.append(MS.MacroObservation(
                state_kind=kind, area=area,
                series_id=f"STATCAN_V{obj.get('vectorId')}", label=label,
                value=value, unit=unit, measure=measure,
                standing=MS.OBSERVED,
                reference_period=period,
                published_at=released,
                publication_basis=MS.PUBLISHER,
                retrieved_at=retrieved_at,
                source="Statistics Canada, Web Data Service",
                note="release date published by the source"))
    return out


# --- US Bureau of Labor Statistics ------------------------------------------
#
# WRITTEN AND UNREACHABLE, ON PURPOSE. Every probe of the public API returned
# 503, with and without a browser user agent, so US inflation and US
# employment stay UNKNOWN. The adapter exists anyway because the alternative
# is a source gap with no adapter behind it — an absence nobody can tell from
# a decision not to try. `collect` reports it by name in `failures` every
# cycle, so the day the endpoint answers, this starts producing figures with
# no further change.
_BLS = "https://api.bls.gov/publicAPI/v2/timeseries/data/"

BLS_SERIES = {
    "CUUR0000SA0": (MS.INFLATION, "US consumer price index, all urban "
                    "consumers, all items", "index"),
    "LNS14000000": (MS.EMPLOYMENT, "US unemployment rate", "%"),
    "CES0500000003": (MS.WAGES, "US average hourly earnings, private",
                      "USD/hour"),
}

#: Month name -> number, as BLS labels its periods.
_BLS_MONTHS = {f"M{n:02d}": n for n in range(1, 13)}


def bureau_of_labor_statistics(*, retrieved_at: str, periods: int = 24,
                               fetcher: Optional[Callable] = None
                               ) -> List[MS.MacroObservation]:
    """US CPI, unemployment and earnings, when the publisher answers."""
    post = fetcher or _http_post
    year = int(retrieved_at[:4])
    body = post(_BLS, {"seriesid": sorted(BLS_SERIES),
                       "startyear": str(year - max(1, periods // 12)),
                       "endyear": str(year)})
    if (body or {}).get("status") != "REQUEST_SUCCEEDED":
        raise RuntimeError(
            "BLS refused the request: "
            f"{(body or {}).get('status')} {(body or {}).get('message')}")
    out: List[MS.MacroObservation] = []
    for series in ((body.get("Results") or {}).get("series") or []):
        spec = BLS_SERIES.get(series.get("seriesID"))
        if not spec:
            continue
        kind, label, unit = spec
        for point in series.get("data") or []:
            month = _BLS_MONTHS.get(str(point.get("period") or ""))
            value = _as_float(point.get("value"))
            if not month or value is None:
                continue
            period = f"{point.get('year')}-{month:02d}-01"
            out.append(MS.MacroObservation(
                state_kind=kind, area=MS.US,
                series_id=f"BLS_{series.get('seriesID')}", label=label,
                value=value, unit=unit, measure=MS.LEVEL,
                standing=MS.OBSERVED,
                reference_period=period,
                published_at=_assumed_publication(
                    period, MONTHLY_PUBLICATION_LAG_DAYS),
                publication_basis=MS.ASSUMED_LAG,
                retrieved_at=retrieved_at,
                source="US Bureau of Labor Statistics",
                note=("release date not returned by the API; assumed "
                      f"{MONTHLY_PUBLICATION_LAG_DAYS} days after period "
                      "end")))
    return out


#: series key -> builder. A new keyless publisher is one entry here.
SERIES = {
    "treasury_note_rate": treasury_note_rate,
    "treasury_bill_rate": treasury_bill_rate,
    "treasury_interest_expense": treasury_interest_expense,
    "bank_of_canada": bank_of_canada,
    "statistics_canada": statistics_canada,
    "bureau_of_labor_statistics": bureau_of_labor_statistics,
}


#: Which adapters speak POST rather than GET. Their `fetcher` argument takes
#: (url, payload) instead of (url), so a single injected double would be
#: called with the wrong arity — and a test that injected one would pass
#: against half the sources and TypeError against the other half.
POST_SERIES = frozenset({"statistics_canada", "bureau_of_labor_statistics"})


def collect(*, retrieved_at: str, only: Sequence[str] = (),
            fetcher: Optional[Callable] = None,
            poster: Optional[Callable] = None) -> dict:
    """Fetch every configured series, and report what failed rather than
    silently returning fewer observations.

    A source that errors must not look like a source that had nothing to say:
    the first is a broken adapter and the second is an economy that did not
    move, and treating them alike is how a dead feed goes unnoticed for weeks.
    `series_failed` is therefore part of the return value and not a log line.
    """
    wanted = [k for k in SERIES if not only or k in only]
    observations: List[MS.MacroObservation] = []
    failures = {}
    for key in wanted:
        injected = poster if key in POST_SERIES else fetcher
        try:
            observations.extend(
                SERIES[key](retrieved_at=retrieved_at, fetcher=injected))
        except Exception as exc:  # noqa: BLE001 - a feed must not fail a cycle
            failures[key] = f"{type(exc).__name__}: {exc}"
    return {
        "contract": CONTRACT,
        "series_attempted": len(wanted),
        "series_succeeded": len(wanted) - len(failures),
        "series_failed": sorted(failures),
        "failures": failures,
        "observations": observations,
        "observation_count": len(observations),
        "periods_covered": sorted({o.reference_period for o in observations}),
        "areas_covered": sorted({o.area for o in observations}),
        "kinds_covered": sorted({o.state_kind for o in observations}),
    }
