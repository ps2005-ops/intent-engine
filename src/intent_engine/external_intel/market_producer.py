"""Build and publish one company's `market_intel_export.v2`.

THE PROBLEM THIS SOLVES
-----------------------
The consumer, the wiring and the dashboard module for market context have all
existed for cycles. What never existed was a producer that reliably WROTE an
export the deployed service could read, so `_market_snapshot` found no file and
every founder saw "no market snapshot has been published". The section was
architecturally complete and empty in practice.

REFRESH MODEL: DAILY, PLUS AN ON-DEMAND STALE CHECK
---------------------------------------------------
`ensure_export` is what analysis calls. It returns immediately when a recent
export exists, and only fetches when there is none or the existing one has
gone stale. A founder never waits on a market download that a scheduled
refresh should already have done, and a run on a fresh company still gets real
data rather than a permanent gap.

Closes for a COMPLETED session never change, so this is safe to call as often
as a run happens: same inputs, same file, no duplicate work.

IDEMPOTENT, AND HONEST ABOUT WHAT THAT MEANS
---------------------------------------------
Re-running on the same day rewrites the same content. `generated_at` moves,
because it records when the file was written and pretending otherwise would be
a small lie in the provenance field. Everything a founder reads is unchanged.

WHAT THIS NEVER DOES
--------------------
Never modifies trading state. Never requires a paper position. Never infers a
price from prose. Never hand-authors a company's numbers. There is no import
here from the market engine's stores -- the only inputs are a ticker and
public closes.
"""
from __future__ import annotations

import json
import math
import pathlib
from datetime import date, datetime, timezone
from typing import Dict, List, Optional, Tuple

from . import prices as P
from .market_contract import (
    DISCLAIMER, INFERRED, INTERPRETATION_FORBIDDEN, OBSERVED, SCHEMA_VERSION,
    UNMEASURABLE, ExportViolation, MarketIntel, absent, measurement,
    unmeasurable, validate,
)

#: Trading sessions per window. Sessions, not calendar days: counting calendar
#: days silently shortens every window across a weekend and the error is
#: invisible in the output.
WINDOWS = (("1m", 21, "the past month"),
           ("3m", 63, "the past three months"),
           ("1y", 252, "the past year"))

#: Beyond this the snapshot describes a market that has moved on. Seven
#: calendar days spans a long weekend plus a holiday without tripping.
MAX_AGE_DAYS = 7

#: Below this many sessions there is not enough shape to draw a line that
#: means anything, so the chart series is omitted rather than drawn sparse.
MIN_CHART_OBSERVATIONS = 30

#: Sessions the trajectory chart covers — one year, matching the longest
#: window the prose quotes.
CHART_SESSIONS = 252


def export_path(root, ticker: str) -> pathlib.Path:
    return (pathlib.Path(root) / "reports" / "market" / "export"
            / f"{ticker.upper()}.json")


# --- measurement helpers ----------------------------------------------------
def _sorted_closes(closes: Dict[str, float], as_of: str) -> List[Tuple]:
    """Point-in-time: only sessions dated on or before `as_of`."""
    return sorted((d, v) for d, v in (closes or {}).items()
                  if d <= as_of[:10] and v)


def _pct_change(closes, as_of: str, sessions: int, label: str,
                period_words: str, source: str) -> dict:
    usable = _sorted_closes(closes, as_of)
    if len(usable) < sessions + 1:
        return unmeasurable(
            f"needs {sessions + 1} sessions of history for {period_words}, "
            f"has {len(usable)}", period=period_words, unit="percent",
            source=source)
    start, end = usable[-(sessions + 1)][1], usable[-1][1]
    if not start:  # pragma: no cover - a zero close is not a real quote
        return unmeasurable("zero reference price", period=label,
                            unit="percent", source=source)
    return measurement(round((end - start) / start * 100, 2), OBSERVED,
                       period=period_words, unit="percent", source=source,
                       observation_date=usable[-1][0])


#: Sessions in the volatility window. SIXTY, not twenty, and the difference
#: matters more than it looks. Measured on Palantir, 2026-08-04: a 20-session
#: window spanning one +29.5% earnings gap annualises to 112%, which a founder
#: reads as "the market has no idea what this company is worth". Sixty sessions
#: gives the same day proportionate weight. A single event should be visible in
#: the number, not be the number.
_VOL_SESSIONS = 60

#: When one session accounts for more than this share of total squared
#: variation, the estimate is DESCRIBING THAT EVENT rather than describing a
#: level of uncertainty, and the note has to say so.
_VOL_DOMINANCE = 0.5


def _volatility(closes, as_of: str, source: str,
                sessions: int = _VOL_SESSIONS) -> dict:
    usable = _sorted_closes(closes, as_of)
    if len(usable) < sessions + 1:
        return unmeasurable(
            f"needs {sessions + 1} sessions for a stable volatility "
            f"estimate, has {len(usable)}",
            period=f"{sessions} sessions", unit="percent", source=source)
    window = [v for _, v in usable[-(sessions + 1):]]
    rets = [(b - a) / a for a, b in zip(window, window[1:]) if a]
    if len(rets) < 2:  # pragma: no cover
        return unmeasurable("insufficient returns",
                            period=f"{sessions} sessions", unit="percent",
                            source=source)
    mean = sum(rets) / len(rets)
    squared = [(r - mean) ** 2 for r in rets]
    total = sum(squared)
    sd = math.sqrt(total / (len(rets) - 1))

    note = (f"annualised from the last {len(rets)} sessions, assuming 252 "
            f"trading days")
    if total and max(squared) / total > _VOL_DOMINANCE:
        biggest = max(rets, key=abs)
        note += (f"; one session moved {biggest * 100:+.1f}% and accounts for "
                 f"most of this figure, so it reflects a single event more "
                 f"than a settled level of uncertainty")
    # INFERRED, not observed: annualising is a transformation under an
    # assumption (252 sessions, independent returns), not a measurement. The
    # status is the difference between a number and a modelled number.
    return measurement(round(sd * math.sqrt(252) * 100, 1), INFERRED,
                       period=f"annualised from the last {len(rets)} sessions",
                       unit="percent", source=source,
                       observation_date=usable[-1][0], note=note)


def _drawdown(closes, as_of: str, source: str, sessions: int = 252) -> dict:
    usable = _sorted_closes(closes, as_of)
    if len(usable) < 30:
        return unmeasurable("insufficient history for a drawdown",
                            period="the period shown", unit="percent",
                            source=source)
    window = [v for _, v in usable[-sessions:]]
    peak, worst = window[0], 0.0
    for price in window:
        peak = max(peak, price)
        worst = min(worst, price / peak - 1)
    return measurement(round(worst * 100, 1), OBSERVED,
                       period=f"the last {len(window)} sessions",
                       unit="percent", source=source,
                       observation_date=usable[-1][0],
                       note="deepest peak-to-trough fall in the period")


def _from_high(closes, as_of: str, source: str, sessions: int = 252) -> dict:
    usable = _sorted_closes(closes, as_of)
    if len(usable) < 30:
        return unmeasurable("insufficient history to locate a period high",
                            period="the period shown", unit="percent",
                            source=source)
    window = [v for _, v in usable[-sessions:]]
    high = max(window)
    if not high:  # pragma: no cover
        return unmeasurable("no positive close", period="the period shown",
                            unit="percent", source=source)
    return measurement(round((window[-1] / high - 1) * 100, 1), OBSERVED,
                       period=f"the last {len(window)} sessions",
                       unit="percent", source=source,
                       observation_date=usable[-1][0],
                       note="distance from the highest close in the period")


def _relative(security: dict, benchmark: dict, label: str,
              period_words: str, source: str) -> dict:
    if security["status"] != OBSERVED or benchmark["status"] != OBSERVED:
        return unmeasurable(
            "the company or the benchmark return is unavailable for this "
            "window, so the two cannot be compared",
            period=period_words, unit="percentage points", source=source)
    return measurement(round(security["value"] - benchmark["value"], 2),
                       OBSERVED, period=period_words,
                       unit="percentage points", source=source,
                       observation_date=security["observation_date"],
                       note="difference over the identical window")


def _series(closes, bench_closes, as_of: str, source: str) -> Optional[dict]:
    """Both lines indexed to 100 on their first SHARED session.

    Shared dates only. Two lines drawn from two different date sets look like
    a comparison and are not one -- the gap between them would partly be the
    gap between their calendars.
    """
    company = dict(_sorted_closes(closes, as_of))
    bench = dict(_sorted_closes(bench_closes, as_of))
    shared = sorted(set(company) & set(bench))
    # The producer keeps two years so the one-year RETURN is measurable; the
    # chart shows one, because that is the window the surrounding text talks
    # about and a chart on a different window than the prose invites the
    # reader to check one against the other and find them disagreeing.
    shared = shared[-CHART_SESSIONS:]
    if len(shared) < MIN_CHART_OBSERVATIONS:
        return None
    base_c, base_b = company[shared[0]], bench[shared[0]]
    if not base_c or not base_b:  # pragma: no cover
        return None
    # One point per ~3 sessions keeps the payload small and the line honest:
    # every plotted point is a real close, none is interpolated.
    step = max(1, len(shared) // 80)
    picked = shared[::step]
    if picked[-1] != shared[-1]:
        picked.append(shared[-1])
    return {
        "dates": picked,
        "company_indexed": [round(company[d] / base_c * 100, 2)
                            for d in picked],
        "benchmark_indexed": [round(bench[d] / base_b * 100, 2)
                              for d in picked],
        "base": 100,
        "unit": "index, first shared session = 100",
        "source": source,
        "note": ("every point is a real closing price on a session both "
                 "series traded; nothing is interpolated"),
    }


def _regime(bench_closes, as_of: str, source: str) -> dict:
    """Observable market-wide condition. Descriptive, never a forecast.

    Deliberately coarse and deliberately about the BENCHMARK, not the company:
    the point is to separate "this company moved" from "everything moved", and
    a finely-graded regime label invites being read as a prediction.
    """
    usable = _sorted_closes(bench_closes, as_of)
    if len(usable) < 63:
        return {"label": "", "basis": "", "status": UNMEASURABLE,
                "observation_date": "", "source": source,
                "note": "insufficient benchmark history to describe a regime"}
    window = [v for _, v in usable[-63:]]
    change = (window[-1] - window[0]) / window[0] * 100 if window[0] else 0.0
    rets = [(b - a) / a for a, b in zip(window, window[1:]) if a]
    mean = sum(rets) / len(rets) if rets else 0.0
    sd = (math.sqrt(sum((r - mean) ** 2 for r in rets) / (len(rets) - 1))
          * math.sqrt(252) * 100) if len(rets) > 1 else 0.0
    if change >= 5:
        label = "broadly rising"
    elif change <= -5:
        label = "broadly falling"
    else:
        label = "broadly flat"
    if sd >= 25:
        label += ", with elevated volatility"
    return {
        "label": label,
        "basis": (f"the benchmark moved {change:+.1f}% over the last 63 "
                  f"sessions, with {sd:.0f}% annualised volatility"),
        "status": OBSERVED,
        "observation_date": usable[-1][0],
        "source": source,
        "note": ("describes the market these shares trade in, not this "
                 "company, and covers only sessions that have already "
                 "completed"),
    }


# --- the producer -----------------------------------------------------------
def build_export(*, ticker: str, closes: Dict[str, float],
                 benchmark_closes: Dict[str, float], as_of: str,
                 exchange: str = "", currency: str = "", company_id: str = "",
                 source: str = P.SOURCE, retrieved_at: str = "",
                 evidence_ids=()) -> dict:
    """Assemble one validated export. Raises if it would violate the contract.

    Validation is on the way OUT rather than trusted at the call sites: a field
    added upstream six months from now would otherwise ride along unnoticed,
    which is exactly how the engine's funnel counters would have reached a
    founder's screen.
    """
    closes = closes or {}
    benchmark_closes = benchmark_closes or {}
    latest = max((d for d in closes if d <= as_of[:10]), default=None)

    price_periods, bench_periods, relative = {}, {}, {}
    for label, sessions, words in WINDOWS:
        price_periods[label] = _pct_change(closes, as_of, sessions, label,
                                           words, source)
        bench_periods[label] = _pct_change(benchmark_closes, as_of, sessions,
                                           label, words, source)
        relative[label] = _relative(price_periods[label], bench_periods[label],
                                    label, words, source)

    limitations: List[str] = []
    if not closes:
        limitations.append(
            "No price history was retrieved for this ticker, so every market "
            "measurement is reported as unavailable rather than estimated.")
    if not benchmark_closes:
        limitations.append(
            "No benchmark series was retrieved, so this company's movement "
            "cannot be separated from the market's.")
    short = [w for label, _, w in WINDOWS
             if price_periods[label]["status"] == UNMEASURABLE]
    if short and closes:
        limitations.append(
            "The available price history is too short to measure "
            + ", ".join(short) + ".")

    age = None
    if latest:
        try:
            age = (date.fromisoformat(as_of[:10])
                   - date.fromisoformat(latest)).days
        except ValueError:  # pragma: no cover
            age = None
    if age is not None and age > MAX_AGE_DAYS:
        limitations.append(
            f"The most recent session in this data is {age} days old, so it "
            f"may not reflect recent trading.")

    series = _series(closes, benchmark_closes, as_of, source)
    if series is None and closes:
        limitations.append(
            "Too few sessions are shared by this company and the benchmark to "
            "draw a comparable trajectory, so no chart is shown.")

    payload = {
        "schema_version": SCHEMA_VERSION,
        "company_id": company_id,
        "ticker": ticker.upper(),
        "exchange": exchange,
        "currency": currency,
        "as_of": as_of[:10],
        "generated_at": datetime.now(timezone.utc).isoformat(
            timespec="seconds"),
        "data_freshness": {
            "latest_session": latest or "",
            "age_days": age,
            "stale": bool(age is not None and age > MAX_AGE_DAYS),
            "status": OBSERVED if latest else UNMEASURABLE,
            "note": ("the newest completed session this export reflects"
                     if latest else "no completed session was retrieved"),
        },
        "price_periods": price_periods,
        "benchmark": {"symbol": P.BENCHMARK_SYMBOL, "name": P.BENCHMARK_NAME,
                      "periods": bench_periods},
        "benchmark_relative_periods": relative,
        "annualized_volatility": _volatility(closes, as_of, source),
        "period_drawdown": _drawdown(closes, as_of, source),
        "distance_from_period_high": _from_high(closes, as_of, source),
        "market_regime": _regime(benchmark_closes, as_of, source),
        "relevant_market_events": [],
        "limitations": limitations,
        "evidence_ids": list(evidence_ids),
        "source_lineage": {
            "provider": P.PROVIDER,
            "endpoint_family": source,
            "method": ("point-in-time: only sessions dated on or before "
                       "as_of are read"),
            "retrieved_at": retrieved_at,
            "point_in_time": as_of[:10],
            "caveat": ("an undocumented public endpoint with no availability "
                       "promise; a failure is reported, never filled in"),
        },
        "disclaimer": DISCLAIMER,
        "interpretation_forbidden": list(INTERPRETATION_FORBIDDEN),
    }
    if series is not None:
        payload["series"] = series
    validate(payload)
    return payload


def write_export(payload: dict, root=".") -> pathlib.Path:
    """Publish atomically, so a reader never sees a half-written file."""
    validate(payload)
    out = export_path(root, payload["ticker"])
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=1, sort_keys=True, default=str))
    tmp.replace(out)
    return out


def load_export(root, ticker: str, *, today: str = "") -> MarketIntel:
    """Read one published export, validating identity, version and freshness.

    Fails closed on every path: a wrong version, a ticker mismatch, unreadable
    JSON or an unsanctioned field all end as `absent` with a reason a founder
    can read, never as a partially-trusted payload.
    """
    if not ticker:
        return absent("No ticker was resolved for this company, so no market "
                      "series was looked up.")
    path = export_path(root, ticker)
    if not path.exists():
        return absent(f"No market snapshot has been published for "
                      f"{ticker.upper()} yet.", ticker.upper())
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return absent(f"The market snapshot could not be read "
                      f"({type(exc).__name__}).", ticker.upper())
    try:
        validate(payload)
    except ExportViolation as exc:
        # A snapshot that violates the contract is not shown in degraded form.
        # Rendering "most of" an export that carried an unsanctioned field is
        # how the field reaches the page.
        return absent(f"The market snapshot did not meet the published "
                      f"contract ({exc}).", ticker.upper())
    if (payload.get("ticker") or "").upper() != ticker.upper():
        return absent(f"The stored snapshot is for {payload.get('ticker')}, "
                      f"not {ticker.upper()}.", ticker.upper())

    freshness = payload.get("data_freshness") or {}
    latest = freshness.get("latest_session")
    if not latest:
        return absent("The market snapshot carries no completed session.",
                      ticker.upper())
    age = freshness.get("age_days")
    if today:
        try:
            age = (date.fromisoformat(today[:10])
                   - date.fromisoformat(latest)).days
        except ValueError:  # pragma: no cover
            pass
    stale = bool(age is not None and age > MAX_AGE_DAYS)
    return MarketIntel(available=True, ticker=payload["ticker"],
                       payload=payload, stale=stale, age_days=age)


def is_stale(root, ticker: str, *, today: str) -> bool:
    """True when an export is missing or old enough to be worth refetching."""
    intel = load_export(root, ticker, today=today)
    return (not intel.available) or intel.stale


def ensure_export(*, ticker: str, root, today: str, exchange: str = "",
                  company_id: str = "", fetcher=None,
                  allow_fetch: bool = True) -> MarketIntel:
    """The call analysis makes. Reuses a fresh export; refreshes a stale one.

    `allow_fetch=False` is the read-only mode a rendering path uses, so that
    displaying a page can never trigger a network fetch.
    """
    if not ticker:
        return absent("No ticker was resolved for this company, so no market "
                      "series was looked up.")
    existing = load_export(root, ticker, today=today)
    if existing.available and not existing.stale:
        return existing
    if not allow_fetch:
        return existing

    series = P.fetch(ticker, root=root, fetcher=fetcher)
    if not series:
        # Keep whatever was already published rather than deleting it: an
        # export labelled six days old is worth more than a blank section,
        # and `stale` already tells the reader which it is.
        return existing if existing.available else absent(
            f"Price history for {ticker.upper()} could not be retrieved, so "
            f"no market context is shown. Nothing is estimated in its place.",
            ticker.upper())
    bench = P.fetch(P.BENCHMARK_SYMBOL, root=root, fetcher=fetcher)
    payload = build_export(
        ticker=ticker, closes=series.closes,
        benchmark_closes=(bench.closes if bench else {}),
        as_of=today, exchange=exchange or series.exchange,
        currency=series.currency, company_id=company_id,
        source=series.source, retrieved_at=series.retrieved_at)
    write_export(payload, root)
    return load_export(root, ticker, today=today)
