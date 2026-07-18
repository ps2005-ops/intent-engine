"""Market-engine phase, Task M1 (market-engine-execution-plan.md, part A-M
of the overnight execution plan family).

A requests-only client for FRED (Federal Reserve Economic Data): fetch +
on-disk JSON cache only, no interpretation, no LLM (that's M2/M3). Every
external call goes through a cache first so re-runs hit disk, not the
network, per the plan's network-wall discipline (A-M2).

Hard guards, deliberately strict ("the friend's-bot lesson" the plan's own
text names -- a data layer that silently substitutes a sentinel for a real
gap teaches every downstream consumer to trust a number that was never
actually observed): a missing series (the API returned zero observations
for the requested range), a None value, or an unparseable value RAISES.
Nothing here ever returns an "Unknown" string or a coerced default in
place of a real value.

AMENDED 2026-07-18 (user-approved deterministic rule -- see
tests/test_macro_data_gap_rule.py for the bars). The original guard raised
on ANY '.' observation, which made every long-lookback fetch of a
business-day daily series fail permanently (holidays are always in a 10y
window) and let one historical gap month (e.g. the Oct-2025 shutdown)
permanently kill CPI/UNRATE fetches. The amended rule distinguishes
FRED's own placeholder semantics from genuine gaps, in code:

1. For series in BUSINESS_DAILY_SERIES, a '.' on a weekend is FRED's
   expected non-business-day placeholder: dropped silently.
2. For those same series, a run of 1-2 consecutive WEEKDAY '.'s is a
   market-holiday placeholder (US market closures are 1, historically at
   most 2, consecutive business days): dropped silently.
3. A run of >=3 consecutive weekday '.'s in a business-daily series, or
   ANY '.' in any other series (monthly/quarterly data should exist for
   every period), is a GENUINE GAP: the observation is still never
   coerced -- it is excluded from `observations`, recorded with its date
   in `FredSeries.gaps`, and a loud warning is printed. Callers surface
   gaps in rendered output (regime_report's data-gaps section); the run
   itself stays alive -- an unattended weekly cron that dies forever on a
   one-month historical gap is an availability failure, not data honesty.
4. None values, unparseable values, and zero-observations-after-drops
   still RAISE -- the strictness against silent substitution is not
   weakened; '.' handling is narrowed to FRED's documented semantics.
"""

import json
import os
import time
from datetime import date
from pathlib import Path
from typing import List, Optional, Tuple, Union

import requests
from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()

FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"
DEFAULT_CACHE_DIR = Path("data/cache/fred")

# Seed series set for regime work (M2), chosen by the plan: fed funds, CPI,
# unemployment, yield-curve spread, high-yield credit spread, real GDP, M2
# money supply, VIX.
SEED_SERIES = ["DFF", "CPIAUCSL", "UNRATE", "T10Y2Y", "BAMLH0A0HYM2", "GDPC1", "M2SL", "VIXCLS"]

# Transient failure modes worth retrying (rate limit, server-side trouble).
# Non-transient failures (bad series_id, bad key) raise immediately -- a
# retry loop that masks a permanent 400/403 as "still trying" is its own
# kind of silent-Unknown failure.
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


# Series whose native frequency is business-daily: FRED publishes '.' rows
# for non-business days by its own semantics. Everything NOT in this set is
# held to the stricter any-'.'-is-a-gap rule. Widening this set is a
# reviewed code change, never inference.
BUSINESS_DAILY_SERIES = {"T10Y2Y", "BAMLH0A0HYM2", "DGS10", "VIXCLS"}

# Longest consecutive-weekday '.' run still explainable as a market holiday.
# US market closures are single days; rare events (e.g. Sandy, 2012) reached
# two. Three or more consecutive business days without data is a gap.
HOLIDAY_RUN_MAX = 2


class FredSeries(BaseModel):
    series_id: str
    realtime_date: str  # provenance: the FRED vintage this observation set was fetched as-of
    observations: List[Tuple[str, float]]  # (date, value), ascending by date
    gaps: List[str] = []  # dates of GENUINE-GAP '.' observations (rule 3) -- additive, default empty


def _cache_path(series_id: str, start: str, end: str, cache_dir: Union[str, Path]) -> Path:
    return Path(cache_dir) / f"{series_id}_{start}_{end}.json"


def _fetch_with_retry(
    series_id: str, start: str, end: str, api_key: str, max_retries: int, timeout: float
) -> dict:
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": start,
        "observation_end": end,
    }
    last_error: Optional[str] = None
    for attempt in range(max_retries):
        try:
            response = requests.get(FRED_BASE_URL, params=params, timeout=timeout)
        except requests.RequestException as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            time.sleep(2 ** attempt)
            continue

        if response.status_code == 200:
            return response.json()

        if response.status_code in _RETRYABLE_STATUS_CODES:
            last_error = f"HTTP {response.status_code}: {response.text[:200]}"
            time.sleep(2 ** attempt)
            continue

        # Non-transient (e.g. 400 unknown series_id, 403 bad key) -- fail
        # loudly now, retrying would just delay the same real failure.
        raise RuntimeError(f"FRED API returned {response.status_code} for series {series_id!r}: {response.text[:300]}")

    raise RuntimeError(
        f"FRED API request for series {series_id!r} failed after {max_retries} attempts. Last error: {last_error}"
    )


def _parse_response(raw: dict, series_id: str) -> FredSeries:
    """Pure parsing + hard guards -- no network. Split out so tests can feed
    real or constructed fixture JSON directly, without a live call."""
    observations_raw = raw.get("observations")
    if not observations_raw:
        raise ValueError(
            f"FRED series {series_id!r} returned no observations for the requested range "
            "(missing/short series) -- never silently treated as an empty-but-valid result."
        )

    observations: List[Tuple[str, float]] = []
    gaps: List[str] = []
    weekday_dot_run: List[str] = []  # pending consecutive weekday '.' dates (business-daily series)

    def _flush_weekday_run() -> None:
        # Rule 2 vs rule 3: a short run is a holiday placeholder (dropped
        # silently); a long run is a genuine gap (recorded, warned).
        if len(weekday_dot_run) > HOLIDAY_RUN_MAX:
            gaps.extend(weekday_dot_run)
        weekday_dot_run.clear()

    is_business_daily = series_id in BUSINESS_DAILY_SERIES
    for obs in observations_raw:
        value_str = obs.get("value")
        obs_date = obs.get("date")
        if value_str is None:
            raise ValueError(
                f"FRED series {series_id!r} has a None observation at date={obs_date!r} "
                "-- never silently coerced to a default or dropped."
            )
        if value_str == ".":
            if is_business_daily:
                if date.fromisoformat(obs_date).weekday() >= 5:
                    continue  # rule 1: weekend placeholder, FRED's own semantics
                weekday_dot_run.append(obs_date)
            else:
                gaps.append(obs_date)  # rule 3: non-daily series, data should exist
            continue
        _flush_weekday_run()
        try:
            value = float(value_str)
        except ValueError:
            raise ValueError(
                f"FRED series {series_id!r} has an unparseable observation at date={obs_date!r} "
                f"(value={value_str!r}) -- never silently coerced."
            )
        observations.append((obs_date, value))
    _flush_weekday_run()

    if not observations:
        raise ValueError(
            f"FRED series {series_id!r} has no usable observations for the requested range "
            "after applying the documented placeholder rule -- never treated as empty-but-valid."
        )
    if gaps:
        print(
            f"WARNING: FRED series {series_id!r} has {len(gaps)} GENUINE-GAP observation(s) "
            f"(first: {gaps[0]}, last: {gaps[-1]}) -- excluded, recorded in .gaps, and surfaced "
            "in rendered reports. This is a real data gap (e.g. a shutdown month), not a holiday."
        )

    realtime_date = observations_raw[0].get("realtime_start") or raw.get("realtime_start", "")
    return FredSeries(series_id=series_id, realtime_date=realtime_date, observations=observations, gaps=gaps)


def get_series(
    series_id: str,
    start: Union[str, date],
    end: Union[str, date],
    api_key: Optional[str] = None,
    cache_dir: Union[str, Path] = DEFAULT_CACHE_DIR,
    max_retries: int = 3,
    timeout: float = 15.0,
) -> FredSeries:
    """Fetch one FRED series over [start, end], cached on disk so a re-run
    with the same series+range hits the cache, never the network again."""
    start_str = start.isoformat() if isinstance(start, date) else start
    end_str = end.isoformat() if isinstance(end, date) else end

    cache_path = _cache_path(series_id, start_str, end_str, cache_dir)
    if cache_path.exists():
        raw = json.loads(cache_path.read_text())
        return _parse_response(raw, series_id)

    resolved_key = api_key or os.environ.get("FRED_API_KEY")
    if not resolved_key:
        raise RuntimeError(
            "FRED_API_KEY is not set. Add it to a .env file or pass api_key= explicitly."
        )

    raw = _fetch_with_retry(series_id, start_str, end_str, resolved_key, max_retries, timeout)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(raw))
    return _parse_response(raw, series_id)
