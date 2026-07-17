"""Market-engine phase, Task M2 (market-engine-execution-plan.md).

Deterministic macro/regime indicators computed from M1's FRED series. Every
function here is pure arithmetic over a caller-supplied observation list --
no network, no LLM, no thresholds tuned to make any historical fixture
"call" a crisis (A-M3: these are textbook definitions, cited where the
threshold itself is a real, external, already-published number -- e.g. the
Sahm Rule's 0.50pp trigger -- never something fit to this project's own
data). Indicators compute; they do not opine (no rendering, no prediction,
no probability language -- that belongs to a later, gated task).

Input shape mirrors macro_data.FredSeries.observations exactly:
List[Tuple[date_str, value]], ascending by date -- callers get that shape
either from a real M1 get_series() call or a fixture, this module doesn't
care which.
"""

from datetime import date as _date
from typing import Dict, List, Optional, Tuple, Union

try:
    from typing import Literal
except ImportError:  # pragma: no cover
    from typing_extensions import Literal

from pydantic import BaseModel

Observations = List[Tuple[str, float]]

# The real, published Sahm Rule recession-signal threshold (Sahm, "Direct
# Stimulus Payments to Individuals," Hutchins Center, 2019; also the
# documented trigger on FRED's own SAHMREALTIME series page) -- an
# external, already-established number we are citing, not one tuned
# against this project's own historical fixtures (A-M3).
SAHM_TRIGGER_THRESHOLD = 0.50

# Tolerance band for inflation_trend's "stable" bucket: a small noise/
# rounding tolerance so two YoY averages that differ by a hair don't flip
# the label, NOT a threshold chosen to make any crisis fixture read a
# particular way (A-M3) -- there is no crisis-outcome assertion anywhere
# in this module or its tests.
_INFLATION_STABLE_TOLERANCE_PP = 0.1


class Provenance(BaseModel):
    series_id: str
    observation_date: str  # the most recent observation date actually used


class CurveInversionResult(BaseModel):
    inverted: bool
    depth: float  # magnitude below zero, in percentage points; 0.0 if not inverted
    provenance: Provenance


class CreditSpreadPercentileResult(BaseModel):
    percentile: float  # 0-100: where the latest spread ranks within its own lookback window
    lookback_years: int
    window_size: int  # how many observations actually fell in the window (may be < a full lookback)
    provenance: Provenance


InflationTrendLabel = Literal["rising", "falling", "stable"]


class InflationTrendResult(BaseModel):
    trend: InflationTrendLabel
    yoy_3m_avg: float
    yoy_12m_avg: float
    provenance: Provenance


class UnemploymentMomentumResult(BaseModel):
    delta: float  # current 3-month avg minus the prior-12-months low of 3-month avgs, in pp
    triggered: bool  # delta >= SAHM_TRIGGER_THRESHOLD
    provenance: Provenance


class DrawdownStateResult(BaseModel):
    pct_off_high: float  # <= 0; e.g. -18.18 means 18.18% below the window's running high
    provenance: Provenance


def _years_before(d: _date, years: int) -> _date:
    try:
        return d.replace(year=d.year - years)
    except ValueError:  # Feb 29 with no leap year at the target year
        return d.replace(month=2, day=28, year=d.year - years)


def curve_inversion(observations: Observations) -> CurveInversionResult:
    """T10Y2Y (10-Year minus 2-Year Treasury constant-maturity yield),
    already a spread in FRED's own series. Textbook definition: the curve
    is "inverted" when this spread is negative (short rates exceed long
    rates). depth is how far below zero, in percentage points."""
    if not observations:
        raise ValueError("curve_inversion requires at least one observation.")
    latest_date, latest_value = observations[-1]
    inverted = latest_value < 0
    depth = -latest_value if inverted else 0.0
    return CurveInversionResult(
        inverted=inverted, depth=depth,
        provenance=Provenance(series_id="T10Y2Y", observation_date=latest_date),
    )


def credit_spread_percentile(observations: Observations, lookback_years: int = 10) -> CreditSpreadPercentileResult:
    """BAMLH0A0HYM2 (ICE BofA US High Yield Index Option-Adjusted Spread).
    Percentile rank (empirical CDF, textbook definition): what fraction of
    the trailing lookback_years' observations are at or below today's
    spread. Higher percentile = today's credit spread is elevated relative
    to its own recent history."""
    if not observations:
        raise ValueError("credit_spread_percentile requires at least one observation.")
    latest_date_str, latest_value = observations[-1]
    latest_date = _date.fromisoformat(latest_date_str)
    window_start = _years_before(latest_date, lookback_years)

    window = [(d, v) for d, v in observations if window_start <= _date.fromisoformat(d) <= latest_date]
    if not window:
        raise ValueError("credit_spread_percentile: no observations fall within the lookback window.")

    at_or_below = sum(1 for _, v in window if v <= latest_value)
    percentile = at_or_below / len(window) * 100

    return CreditSpreadPercentileResult(
        percentile=percentile, lookback_years=lookback_years, window_size=len(window),
        provenance=Provenance(series_id="BAMLH0A0HYM2", observation_date=latest_date_str),
    )


def inflation_trend(observations: Observations) -> InflationTrendResult:
    """CPIAUCSL (CPI, all urban consumers, index level -- not a rate). YoY
    at month i = (CPI[i] - CPI[i-12]) / CPI[i-12] * 100, the standard
    textbook year-over-year inflation calculation. Compares the average of
    the last 3 months' YoY against the average of the last 12 months' YoY:
    "rising" if the recent 3 months are running hotter, "falling" if
    cooler, "stable" within a small tolerance. Requires >=24 monthly
    observations (12 to anchor the oldest YoY point in the 12-month
    average, plus the 12 months that average spans)."""
    if len(observations) < 24:
        raise ValueError(
            f"inflation_trend requires at least 24 monthly observations to compute a full "
            f"12-month YoY average, got {len(observations)}."
        )
    values = [v for _, v in observations]
    latest_date = observations[-1][0]
    n = len(values)

    def yoy(i: int) -> float:
        return (values[i] - values[i - 12]) / values[i - 12] * 100

    yoy_3m = [yoy(i) for i in range(n - 3, n)]
    yoy_12m = [yoy(i) for i in range(n - 12, n)]
    yoy_3m_avg = sum(yoy_3m) / len(yoy_3m)
    yoy_12m_avg = sum(yoy_12m) / len(yoy_12m)

    diff = yoy_3m_avg - yoy_12m_avg
    if abs(diff) < _INFLATION_STABLE_TOLERANCE_PP:
        trend: InflationTrendLabel = "stable"
    elif diff > 0:
        trend = "rising"
    else:
        trend = "falling"

    return InflationTrendResult(
        trend=trend, yoy_3m_avg=yoy_3m_avg, yoy_12m_avg=yoy_12m_avg,
        provenance=Provenance(series_id="CPIAUCSL", observation_date=latest_date),
    )


def unemployment_momentum(observations: Observations) -> UnemploymentMomentumResult:
    """UNRATE (civilian unemployment rate). Sahm-Rule-style: the current
    3-month moving average of the unemployment rate, minus the LOW of the
    3-month moving averages over the prior 12 months (current month
    excluded from that low, so a genuinely fresh deterioration is
    measured against where the rate recently stood, not against itself).
    triggered=True at delta >= SAHM_TRIGGER_THRESHOLD, the real published
    Sahm Rule recession-signal threshold. Requires >=15 monthly
    observations (3 to form the current average, plus 12 more months to
    form the trailing window of prior 3-month averages)."""
    if len(observations) < 15:
        raise ValueError(
            f"unemployment_momentum requires at least 15 monthly observations, got {len(observations)}."
        )
    values = [v for _, v in observations]
    latest_date = observations[-1][0]
    n = len(values)

    def three_month_avg(end_index: int) -> float:
        return sum(values[end_index - 2:end_index + 1]) / 3

    current_avg = three_month_avg(n - 1)
    prior_avgs = [three_month_avg(i) for i in range(n - 13, n - 1)]  # the 12 months before current
    low = min(prior_avgs)
    delta = current_avg - low

    return UnemploymentMomentumResult(
        delta=delta, triggered=delta >= SAHM_TRIGGER_THRESHOLD,
        provenance=Provenance(series_id="UNRATE", observation_date=latest_date),
    )


def drawdown_state(observations: Observations, series_id: str = "unspecified") -> DrawdownStateResult:
    """Generic (not FRED-specific): % off the running high within the given
    window. Textbook definition: (latest - running_max) / running_max *
    100, always <= 0. Takes an explicit series_id since this indicator is
    not tied to one specific named series (a real equity price feed, once
    Tiingo is wired in M6, is the intended real caller)."""
    if not observations:
        raise ValueError("drawdown_state requires at least one observation.")
    latest_date, latest_value = observations[-1]
    running_high = max(v for _, v in observations)
    pct_off_high = (latest_value - running_high) / running_high * 100
    return DrawdownStateResult(
        pct_off_high=pct_off_high,
        provenance=Provenance(series_id=series_id, observation_date=latest_date),
    )


RegimeField = Union[
    CurveInversionResult, CreditSpreadPercentileResult, InflationTrendResult,
    UnemploymentMomentumResult, DrawdownStateResult, Literal["unavailable"],
]


def regime_snapshot(
    snapshot_date: str,
    series_data: Dict[str, "object"],  # Dict[str, macro_data.FredSeries] -- avoid a hard import cycle
    price_series: Optional[Tuple[str, Observations]] = None,  # (series_id, observations), if a real price feed exists
) -> Dict[str, RegimeField]:
    """Assembles every indicator into one dict, "as of" snapshot_date: each
    series is first filtered to observations with date <= snapshot_date
    (ISO date strings compare correctly as plain strings), so a snapshot
    for a past date never sees data that wasn't yet available. A series
    missing from series_data, or with insufficient/empty data after
    filtering, resolves to the literal string "unavailable" for that
    field -- never a silent default, never a crash of the whole snapshot
    over one field's gap. price_series is optional and separate from
    series_data because none of M1's FRED seed series is a genuine
    "price to draw down from" -- drawdown_state is real and independently
    tested (bar a), but a FRED-only snapshot honestly has no price feed
    to run it against yet (Tiingo lands in M6)."""

    def _filtered(series_id: str) -> Optional[Observations]:
        series = series_data.get(series_id)
        if series is None:
            return None
        obs = [(d, v) for d, v in series.observations if d <= snapshot_date]
        return obs or None

    result: Dict[str, RegimeField] = {"snapshot_date": snapshot_date}

    t10y2y = _filtered("T10Y2Y")
    try:
        result["curve_inversion"] = curve_inversion(t10y2y) if t10y2y else "unavailable"
    except ValueError:
        result["curve_inversion"] = "unavailable"

    hy_spread = _filtered("BAMLH0A0HYM2")
    try:
        result["credit_spread_percentile"] = credit_spread_percentile(hy_spread) if hy_spread else "unavailable"
    except ValueError:
        result["credit_spread_percentile"] = "unavailable"

    cpi = _filtered("CPIAUCSL")
    try:
        result["inflation_trend"] = inflation_trend(cpi) if cpi else "unavailable"
    except ValueError:
        result["inflation_trend"] = "unavailable"

    unrate = _filtered("UNRATE")
    try:
        result["unemployment_momentum"] = unemployment_momentum(unrate) if unrate else "unavailable"
    except ValueError:
        result["unemployment_momentum"] = "unavailable"

    if price_series is not None:
        price_id, price_obs = price_series
        filtered_price = [(d, v) for d, v in price_obs if d <= snapshot_date]
        try:
            result["drawdown_state"] = drawdown_state(filtered_price, series_id=price_id) if filtered_price else "unavailable"
        except ValueError:
            result["drawdown_state"] = "unavailable"
    else:
        result["drawdown_state"] = "unavailable"

    return result
