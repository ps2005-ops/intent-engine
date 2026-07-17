"""Market-engine phase, Task M6 (market-engine-execution-plan.md).

Grades M5's resolution_rule against real data: pct_change rules against
Tiingo adjusted closes, level rules against FRED (reusing macro_data.get_series
directly -- M1 already built exactly this capability, no need to rebuild it).
resolve_market_prediction() only DECIDES an outcome; persisting it through
the ledger's own resolve_prediction() (Brier computed there, unchanged) is
the caller's job (scripts/resolve_market_predictions.py).

Tiingo client mirrors macro_data.py's FRED client shape exactly: on-disk
JSON cache, retry-with-backoff on transient failures, hard guards (empty
response or a missing adjClose raises -- never a coerced default).

Two grading concepts, adapted (not vendored) from a general "prediction
grader" pattern -- touched-vs-closed, and forward-search across gaps:
- pct_change rules use TOUCHED semantics for the ordering ops (>=, >, <=,
  <): the claim resolves "happened" the moment ANY trading day within the
  window crosses the threshold, matching how this kind of claim reads in
  plain language ("SPY rises 2%+ within 60 days" doesn't require it to
  STILL be up 2% on day 60 exactly). "==" uses CLOSED semantics: the
  value at the window's end specifically.
- Both rule types use forward-search when a target date (a rule's
  baseline day, a window's end day, a level rule's "by" date) has no
  observation -- weekends, holidays, a monthly series' release gap -- the
  first REAL observation on or after that date is used, capped so a
  data source that's simply missing/dead doesn't search forever.
"""

import json
import time
from datetime import date, timedelta
from pathlib import Path
from typing import List, NamedTuple, Optional, Tuple, Union

import os

import requests
from dotenv import load_dotenv
from pydantic import BaseModel

from .macro_data import get_series as get_fred_series
from .prediction_ledger import LevelRule, PctChangeRule, Prediction

load_dotenv()

TIINGO_BASE_URL = "https://api.tiingo.com/tiingo/daily/{symbol}/prices"
DEFAULT_TIINGO_CACHE_DIR = Path("data/cache/tiingo")

_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

# Forward-search caps: daily equity data has gaps of a few days at most
# (weekends/holidays); monthly macro series can have release gaps of
# several weeks, so its cap is wider. Both are generous-but-bounded --
# past the cap, the data source is treated as genuinely missing, not
# searched forever.
_TIINGO_FORWARD_SEARCH_DAYS = 10
_FRED_FORWARD_SEARCH_DAYS = 40


class TiingoSeries(BaseModel):
    symbol: str
    observations: List[Tuple[str, float]]  # (date "YYYY-MM-DD", adjClose), ascending


def _tiingo_cache_path(symbol: str, start: str, end: str, cache_dir: Union[str, Path]) -> Path:
    return Path(cache_dir) / f"{symbol}_{start}_{end}.json"


def _fetch_tiingo_with_retry(symbol: str, start: str, end: str, api_key: str, max_retries: int, timeout: float) -> list:
    url = TIINGO_BASE_URL.format(symbol=symbol)
    params = {"startDate": start, "endDate": end, "token": api_key}
    last_error: Optional[str] = None
    for attempt in range(max_retries):
        try:
            response = requests.get(url, params=params, timeout=timeout)
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

        raise RuntimeError(f"Tiingo API returned {response.status_code} for symbol {symbol!r}: {response.text[:300]}")

    raise RuntimeError(f"Tiingo API request for symbol {symbol!r} failed after {max_retries} attempts. Last error: {last_error}")


def _parse_tiingo_response(raw: list, symbol: str) -> TiingoSeries:
    if not raw:
        raise ValueError(f"Tiingo returned no price observations for symbol {symbol!r} in the requested range.")

    observations: List[Tuple[str, float]] = []
    for entry in raw:
        date_str = entry.get("date", "")[:10]  # Tiingo dates are "YYYY-MM-DDT00:00:00.000Z"
        adj_close = entry.get("adjClose")
        if not date_str or adj_close is None:
            raise ValueError(
                f"Tiingo observation for symbol {symbol!r} is missing date/adjClose: {entry!r} -- "
                "never silently coerced to a default or dropped."
            )
        observations.append((date_str, float(adj_close)))
    observations.sort(key=lambda o: o[0])
    return TiingoSeries(symbol=symbol, observations=observations)


def get_prices(
    symbol: str,
    start: Union[str, date],
    end: Union[str, date],
    api_key: Optional[str] = None,
    cache_dir: Union[str, Path] = DEFAULT_TIINGO_CACHE_DIR,
    max_retries: int = 3,
    timeout: float = 15.0,
) -> TiingoSeries:
    """Fetch one symbol's adjusted-close prices over [start, end], cached on
    disk exactly like macro_data.get_series -- a re-run with the same
    symbol+range hits the cache, never the network again."""
    start_str = start.isoformat() if isinstance(start, date) else start
    end_str = end.isoformat() if isinstance(end, date) else end

    cache_path = _tiingo_cache_path(symbol, start_str, end_str, cache_dir)
    if cache_path.exists():
        raw = json.loads(cache_path.read_text())
        return _parse_tiingo_response(raw, symbol)

    resolved_key = api_key or os.environ.get("TIINGO_API_KEY")
    if not resolved_key:
        raise RuntimeError("TIINGO_API_KEY is not set. Add it to a .env file or pass api_key= explicitly.")

    raw = _fetch_tiingo_with_retry(symbol, start_str, end_str, resolved_key, max_retries, timeout)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(raw))
    return _parse_tiingo_response(raw, symbol)


# --- grading -----------------------------------------------------------------


class ResolutionResult(NamedTuple):
    outcome: str  # "happened" | "did_not_happen" | "unresolvable" -- matches PredictionOutcome
    note: str  # always populated: what data/comparison produced this outcome, for audit


def _forward_search(observations: List[Tuple[str, float]], target_date: str, max_forward_days: int) -> Optional[Tuple[str, float]]:
    """The first observation with date >= target_date. None if nothing
    exists within max_forward_days of target_date -- a source that's
    genuinely missing data isn't searched forever."""
    candidates = sorted(o for o in observations if o[0] >= target_date)
    if not candidates:
        return None
    first_date, first_value = candidates[0]
    gap_days = (date.fromisoformat(first_date) - date.fromisoformat(target_date)).days
    if gap_days > max_forward_days:
        return None
    return (first_date, first_value)


def _evaluate_op(actual: float, op: str, threshold: float) -> bool:
    if op == ">=":
        return actual >= threshold
    if op == "<=":
        return actual <= threshold
    if op == ">":
        return actual > threshold
    if op == "<":
        return actual < threshold
    if op == "==":
        return actual == threshold
    raise ValueError(f"Unknown comparison op {op!r}")  # unreachable: ComparisonOp is a closed Literal


def resolve_pct_change_rule(
    rule: PctChangeRule, created_at_date: str, resolve_by: str, price_fetcher=get_prices,
) -> ResolutionResult:
    try:
        theoretical_end = (date.fromisoformat(created_at_date) + timedelta(days=rule.window_days)).isoformat()
        fetch_end = max(theoretical_end, resolve_by)
        series = price_fetcher(rule.symbol, created_at_date, fetch_end)
    except (ValueError, RuntimeError) as exc:
        return ResolutionResult("unresolvable", f"Could not fetch Tiingo prices for {rule.symbol!r}: {exc}")

    if not series.observations:
        return ResolutionResult("unresolvable", f"No Tiingo price data available for {rule.symbol!r} in the resolution window.")

    baseline = _forward_search(series.observations, created_at_date, _TIINGO_FORWARD_SEARCH_DAYS)
    if baseline is None:
        return ResolutionResult("unresolvable", f"No baseline price found for {rule.symbol!r} at or after {created_at_date}.")
    baseline_date, baseline_price = baseline

    effective_end_point = _forward_search(series.observations, theoretical_end, _TIINGO_FORWARD_SEARCH_DAYS)
    effective_end = effective_end_point[0] if effective_end_point else min(resolve_by, series.observations[-1][0])

    if rule.op == "==":
        end_point = effective_end_point or (series.observations[-1] if series.observations else None)
        if end_point is None:
            return ResolutionResult("unresolvable", f"No end-of-window price found for {rule.symbol!r} near {theoretical_end}.")
        end_date, end_price = end_point
        pct = (end_price - baseline_price) / baseline_price
        happened = _evaluate_op(pct, "==", rule.value)
        return ResolutionResult(
            "happened" if happened else "did_not_happen",
            f"{rule.symbol}: window-end pct change {pct:.4f} on {end_date} (baseline {baseline_price} on "
            f"{baseline_date}) {'==' if happened else '!='} {rule.value}.",
        )

    in_window = [(d, v) for d, v in series.observations if baseline_date <= d <= effective_end]
    for observed_date, price in in_window:
        pct = (price - baseline_price) / baseline_price
        if _evaluate_op(pct, rule.op, rule.value):
            return ResolutionResult(
                "happened",
                f"{rule.symbol}: pct change {pct:.4f} on {observed_date} satisfied {rule.op} {rule.value} "
                f"(baseline {baseline_price} on {baseline_date}).",
            )

    if effective_end < resolve_by and not effective_end_point:
        return ResolutionResult(
            "unresolvable",
            f"Resolution window for {rule.symbol!r} [{baseline_date}, {theoretical_end}] has no data through "
            f"its end and resolve_by ({resolve_by}) has passed.",
        )

    return ResolutionResult(
        "did_not_happen",
        f"{rule.symbol}: no day in [{baseline_date}, {effective_end}] satisfied {rule.op} {rule.value} pct change "
        f"(baseline {baseline_price} on {baseline_date}).",
    )


def resolve_level_rule(rule: LevelRule, fred_fetcher=get_fred_series) -> ResolutionResult:
    fetch_start = rule.by
    fetch_end = (date.fromisoformat(rule.by) + timedelta(days=_FRED_FORWARD_SEARCH_DAYS)).isoformat()
    try:
        series = fred_fetcher(rule.series, fetch_start, fetch_end)
    except (ValueError, RuntimeError) as exc:
        return ResolutionResult("unresolvable", f"Could not fetch FRED series {rule.series!r}: {exc}")

    point = _forward_search(series.observations, rule.by, _FRED_FORWARD_SEARCH_DAYS)
    if point is None:
        return ResolutionResult("unresolvable", f"No FRED observation found for {rule.series!r} at or after {rule.by}.")

    obs_date, value = point
    happened = _evaluate_op(value, rule.op, rule.value)
    return ResolutionResult(
        "happened" if happened else "did_not_happen",
        f"{rule.series}={value} on {obs_date} (target by {rule.by}) {rule.op} {rule.value}: "
        f"{'satisfied' if happened else 'not satisfied'}.",
    )


def resolve_market_prediction(
    prediction: Prediction, price_fetcher=get_prices, fred_fetcher=get_fred_series,
) -> ResolutionResult:
    """Evaluates prediction.resolution_rule against real data. Does NOT
    persist anything -- the caller (scripts/resolve_market_predictions.py)
    writes the result through the ledger's own resolve_prediction()."""
    rule = prediction.resolution_rule
    if rule is None:
        return ResolutionResult("unresolvable", "Prediction has no resolution_rule to evaluate.")

    created_at_date = prediction.created_at[:10]
    if isinstance(rule, PctChangeRule):
        return resolve_pct_change_rule(rule, created_at_date, prediction.resolve_by, price_fetcher)
    if isinstance(rule, LevelRule):
        return resolve_level_rule(rule, fred_fetcher)
    return ResolutionResult("unresolvable", f"Unknown resolution_rule type: {type(rule).__name__}")  # unreachable
