"""Public macro series, fetched without a credential.

WHY NOT FRED
------------
`core/macro_data.py` is a working FRED client and needs `FRED_API_KEY`. That
key is not set locally and is not set on the deployed preview -- it is one of
the two credentials the render blueprint marks `sync:false`. Macro context has
therefore rendered nothing on the live product for every cycle it has existed.

So these adapters use sources that answer without a key:

    BLS public API v2     consumer prices, unemployment  (monthly)
    Treasury FiscalData   average Treasury note rate     (monthly)
                          Department of Defense outlays  (monthly, FYTD)

All three were verified answering on 2026-08-04. If `FRED_API_KEY` is ever
set, adding a FRED-backed factor is a new entry in `SERIES` -- the contract,
the exposure gate and the surfaces do not change.

FAIL CLOSED, AND CACHE
----------------------
A failed fetch returns None and the factor simply does not appear; nothing is
substituted, and a missing reading never becomes a zero or an "unchanged".
Every response is cached on disk, because these are monthly series and a
founder-facing page must never wait on three HTTP round-trips.

The cache is also a quota. BLS's unregistered tier allows roughly 25 queries
per day per IP -- hit while building this, which is how the limit was found.
Two series at two requests each, once a day, is four. Without the cache a
handful of runs would exhaust it and every macro section would go quiet for
the rest of the day, which is the failure mode most easily mistaken for "this
company has no macro exposure".

On a host with an ephemeral disk the cache does not survive a restart, so a
cold boot can find the quota already spent. That degrades correctly -- the
factor is omitted rather than guessed -- but it is why a persistent cache
directory matters more here than it looks.
"""
from __future__ import annotations

import json
import pathlib
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from typing import Dict, Optional

from .macro_contract import MacroObservation
from .macro_exposure import (
    CONSUMER_PRICES, INTEREST_RATES, LABOUR_MARKET, PUBLIC_DEFENCE_SPEND,
)

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; intent-engine/1.0)"}

#: Monthly series change monthly. A day of cache is generous and still means
#: at most one fetch per series per day across every run.
CACHE_TTL_SECONDS = 24 * 3600

_BLS = "https://api.bls.gov/publicAPI/v2/timeseries/data/{series}"
_TREASURY = ("https://api.fiscaldata.treasury.gov/services/api/fiscal_service"
             "/v1/accounting/mts/mts_table_5")
_TREASURY_RATES = ("https://api.fiscaldata.treasury.gov/services/api/"
                   "fiscal_service/v2/accounting/od/avg_interest_rates")

_MONTHS = {"January": 1, "February": 2, "March": 3, "April": 4, "May": 5,
           "June": 6, "July": 7, "August": 8, "September": 9, "October": 10,
           "November": 11, "December": 12}


def _cache(root, name: str) -> pathlib.Path:
    return pathlib.Path(root) / "cache" / "macro" / f"{name}.json"


def _cached_get(root, name: str, url: str, now: Optional[float] = None,
                fetcher=None):
    now = time.time() if now is None else now
    path = _cache(root, name)
    if path.exists():
        try:
            blob = json.loads(path.read_text())
            if now - blob.get("cached_at", 0) <= CACHE_TTL_SECONDS:
                return blob.get("body")
        except (OSError, json.JSONDecodeError):
            pass
    body = (fetcher or _http_get)(url)
    if body is None:
        # Serve a stale cache rather than nothing: the observation carries its
        # own date, and the contract's currency check is what decides whether
        # it may still be shown.
        if path.exists():
            try:
                return json.loads(path.read_text()).get("body")
            except (OSError, json.JSONDecodeError):  # pragma: no cover
                return None
        return None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"cached_at": now, "body": body}))
        tmp.replace(path)
    except OSError:  # pragma: no cover - a read-only disk must not break a run
        pass
    return body


def _http_get(url: str):
    try:
        request = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return None


def _month_end(year: int, month: int) -> str:
    if month == 12:
        return date(year, 12, 31).isoformat()
    return (date(year, month + 1, 1) - __import__("datetime").timedelta(
        days=1)).isoformat()


# --- BLS --------------------------------------------------------------------
def _bls_series(root, series_id: str, fetcher=None):
    """Latest two monthly readings, newest first."""
    url = _BLS.format(series=series_id) + "?latest=true"
    body = _cached_get(root, f"bls_{series_id}", url, fetcher=fetcher)
    latest = _bls_rows(body)
    # `latest=true` returns one point, so the comparison point needs its own
    # request. Year-over-year rather than month-over-month: a single month of
    # a noisy series is not a direction, and the annual comparison is the one
    # these series are normally read on.
    if not latest:
        return None, None
    year = int(latest[0]["year"])
    span = _cached_get(root, f"bls_{series_id}_{year}",
                       _BLS.format(series=series_id)
                       + f"?startyear={year - 1}&endyear={year}",
                       fetcher=fetcher)
    rows = _bls_rows(span)
    current = latest[0]
    prior = next((r for r in rows
                  if r["year"] == str(year - 1)
                  and r["periodName"] == current["periodName"]), None)
    return current, prior


def _bls_rows(body):
    try:
        series = ((body or {}).get("Results") or {}).get("series") or []
        return series[0].get("data") or []
    except (AttributeError, IndexError, TypeError):  # pragma: no cover
        return []


def _bls_observation(root, *, factor_key, label, series_id, unit, fetcher=None):
    current, prior = _bls_series(root, series_id, fetcher=fetcher)
    if not current:
        return None
    try:
        value = float(current["value"])
        month = _MONTHS.get(current.get("periodName", ""), 0)
        if not month:
            return None
        observed = _month_end(int(current["year"]), month)
    except (KeyError, TypeError, ValueError):  # pragma: no cover
        return None
    prior_value = None
    if prior:
        try:
            prior_value = float(prior["value"])
        except (KeyError, TypeError, ValueError):  # pragma: no cover
            prior_value = None
    return MacroObservation(
        factor_key=factor_key, label=label, series_id=series_id,
        current_value=value, prior_value=prior_value, unit=unit,
        observation_date=observed, frequency="monthly",
        source="US Bureau of Labor Statistics",
        source_url=f"https://data.bls.gov/timeseries/{series_id}",
        comparison_note="compared with the same month a year earlier")


# --- Treasury ---------------------------------------------------------------
def _treasury_defence(root, fetcher=None):
    query = urllib.parse.urlencode({
        "filter": ("classification_desc:eq:Total--Department of Defense"
                   "--Military Programs"),
        "sort": "-record_date", "page[size]": "24"})
    body = _cached_get(root, "treasury_dod", f"{_TREASURY}?{query}",
                       fetcher=fetcher)
    rows = (body or {}).get("data") or []
    if not rows:
        return None
    def _fytd(row):
        try:
            return float(row.get("current_fytd_net_outly_amt"))
        except (TypeError, ValueError):
            return None
    current = rows[0]
    value = _fytd(current)
    if value is None:
        return None
    # Same month, previous year: fiscal-year-to-date figures only compare
    # against the same point of another fiscal year. Comparing June FYTD with
    # May FYTD would show "growth" that is only one more month of spending.
    month = (current.get("record_date") or "")[5:7]
    prior = next((r for r in rows[1:]
                  if (r.get("record_date") or "")[5:7] == month), None)
    return MacroObservation(
        factor_key=PUBLIC_DEFENCE_SPEND,
        label="US Department of Defense outlays (fiscal year to date)",
        series_id="MTS Table 5 — Department of Defense, Military Programs",
        current_value=round(value / 1e9, 1),
        prior_value=(round(_fytd(prior) / 1e9, 1)
                     if prior and _fytd(prior) is not None else None),
        unit="$bn", observation_date=current.get("record_date", ""),
        frequency="monthly", source="US Treasury, Monthly Treasury Statement",
        source_url="https://fiscaldata.treasury.gov/datasets/monthly-treasury-statement/",
        comparison_note=("compared with the same month of the previous fiscal "
                         "year, which is the only like-for-like comparison "
                         "for a year-to-date figure"))


def _treasury_rates(root, fetcher=None):
    query = urllib.parse.urlencode({
        "filter": "security_desc:eq:Treasury Notes",
        "sort": "-record_date", "page[size]": "24"})
    body = _cached_get(root, "treasury_rates", f"{_TREASURY_RATES}?{query}",
                       fetcher=fetcher)
    rows = (body or {}).get("data") or []
    if not rows:
        return None
    def _rate(row):
        try:
            return float(row.get("avg_interest_rate_amt"))
        except (TypeError, ValueError):  # pragma: no cover
            return None
    current = rows[0]
    value = _rate(current)
    if value is None:  # pragma: no cover
        return None
    month = (current.get("record_date") or "")[5:7]
    prior = next((r for r in rows[1:]
                  if (r.get("record_date") or "")[5:7] == month), None)
    return MacroObservation(
        factor_key=INTEREST_RATES,
        label="Average interest rate on outstanding Treasury notes",
        series_id="Average Interest Rates on US Treasury Securities",
        current_value=value,
        prior_value=_rate(prior) if prior else None,
        unit="percent", observation_date=current.get("record_date", ""),
        frequency="monthly", source="US Treasury, FiscalData",
        source_url=("https://fiscaldata.treasury.gov/datasets/"
                    "average-interest-rates-treasury-securities/"),
        comparison_note="compared with the same month a year earlier")


#: factor key -> builder. Only factors an exposure rule can select appear here,
#: and only factors with a working keyless source.
SERIES = {
    PUBLIC_DEFENCE_SPEND: _treasury_defence,
    INTEREST_RATES: _treasury_rates,
    CONSUMER_PRICES: lambda root, fetcher=None: _bls_observation(
        root, factor_key=CONSUMER_PRICES,
        label="US consumer price index (all urban consumers)",
        series_id="CUUR0000SA0", unit="index", fetcher=fetcher),
    LABOUR_MARKET: lambda root, fetcher=None: _bls_observation(
        root, factor_key=LABOUR_MARKET, label="US unemployment rate",
        series_id="LNS14000000", unit="percent", fetcher=fetcher),
}


def observe(factor_key: str, *, root, fetcher=None
            ) -> Optional[MacroObservation]:
    """One factor's current reading, or None. Never a substituted value."""
    builder = SERIES.get(factor_key)
    if builder is None:
        return None
    try:
        return builder(root, fetcher=fetcher)
    except Exception:  # noqa: BLE001 - a bad upstream shape must not break a run
        return None


def build_factors(observations, *, root, today: str, fetcher=None,
                  extra_texts=()):
    """The company's admissible macro factors, exposure-gated.

    ORDER MATTERS, AND NOT FOR PERFORMANCE. Exposure is established FIRST,
    from the company's own evidence, and only then is a series fetched. The
    reverse order -- fetch the macro picture, then look for a company to
    attach it to -- is how generic macro commentary gets written, because once
    a number is in hand the temptation is to find a use for it.
    """
    from .macro_contract import MacroFactor, admissible
    from .macro_exposure import find_exposures

    factors = []
    for exposure in find_exposures(observations, extra_texts=extra_texts):
        reading = observe(exposure.factor_key, root=root, fetcher=fetcher)
        if reading is None:
            continue
        factors.append(MacroFactor(
            observation=reading, exposure=exposure,
            confidence_basis=(
                f"The exposure is taken from this company's own retrieved "
                f"evidence, which uses the phrase “{exposure.matched_on}"
                f"”; the reading is a published "
                f"{reading.frequency} series from {reading.source}."),
            limitation=(
                "This establishes that the company operates where this factor "
                "applies, and the direction the factor has moved. It does not "
                "measure how much of this company's revenue is exposed, and "
                "it is not evidence that the factor has already affected "
                "results.")))
    return admissible(factors, today=today)
