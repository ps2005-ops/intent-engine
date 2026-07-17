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
for the requested range) or any single NaN/placeholder observation
(FRED's own "." missing-value marker) RAISES. Nothing here ever returns an
"Unknown" string or a coerced default in place of a real value -- a caller
that wants tolerant handling of sparse series builds that on top of this,
explicitly, not silently inside it.
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


class FredSeries(BaseModel):
    series_id: str
    realtime_date: str  # provenance: the FRED vintage this observation set was fetched as-of
    observations: List[Tuple[str, float]]  # (date, value), ascending by date


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
    for obs in observations_raw:
        value_str = obs.get("value")
        if value_str is None or value_str == ".":
            raise ValueError(
                f"FRED series {series_id!r} has a missing/NaN observation at date={obs.get('date')!r} "
                f"(value={value_str!r}) -- never silently coerced to a default or dropped."
            )
        observations.append((obs["date"], float(value_str)))

    realtime_date = observations_raw[0].get("realtime_start") or raw.get("realtime_start", "")
    return FredSeries(series_id=series_id, realtime_date=realtime_date, observations=observations)


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
