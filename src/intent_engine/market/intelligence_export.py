"""Sanitized market intelligence export — the ONLY channel to the demo UI.

WHY A NARROW EXPORT RATHER THAN LETTING THE UI READ THE STORES
---------------------------------------------------------------
The paper books, replay checkpoints and experiment registry are research
internals. A UI that reads them directly would couple a founder-facing product
to file layouts that change every operating cycle, and — far worse — would make
it trivially easy to render a control's win rate as if it were a finding. The
export is the enforcement point: if a field is not here, the UI cannot show it.

WHAT IS DELIBERATELY ABSENT
---------------------------
No paper-control internals. No win rates. No strategy names or thresholds. No
runtime paths. No credentials. No predictions. `FORBIDDEN_KEYS` is asserted
against the emitted payload by test, so a future field cannot leak by being
added upstream and forgotten here.

FAIL CLOSED
-----------
A missing value stays missing. Every field carries a status:

    observed      measured from real data
    inferred      derived from observed data, and says so
    unmeasurable  the data does not exist — NEVER a zero, never a guess

A fabricated financial series is the one error that would make this product
actively harmful, so there is no code path that invents one.

DESCRIPTIVE, NOT PREDICTIVE
---------------------------
Everything here describes what happened. `interpretation_allowed` marks what a
consumer may say about it, and the export refuses to phrase anything as a
recommendation. "The shares underperformed the benchmark by X" is permitted;
"the shares are undervalued" is not expressible.
"""
from __future__ import annotations

import json
import math
import pathlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

EXPORT_VERSION = "market_intel_export.v1"

OBSERVED = "observed"
INFERRED = "inferred"
UNMEASURABLE = "unmeasurable"

# Never emitted. Asserted against the payload by test rather than trusted.
FORBIDDEN_KEYS = frozenset({
    "win_rate", "net_return", "expectancy", "sharpe", "alpha", "edge",
    "strategy_key", "threshold", "signal_value", "paper", "book", "position",
    "api_key", "secret", "token", "password", "path", "root", "checkpoint",
    "prediction", "forecast", "recommendation", "target_price",
})

DISCLAIMER = ("Descriptive market context, not a recommendation and not a "
              "forecast. Derived from public price history.")


@dataclass(frozen=True)
class Field_:
    """One exported fact, with its provenance and its honesty status."""
    value: Optional[Any]
    status: str
    as_of: Optional[str] = None
    source: str = "public_daily_closes"
    note: str = ""

    def as_dict(self) -> dict:
        return {"value": self.value, "status": self.status,
                "as_of": self.as_of, "source": self.source,
                "note": self.note}


def _unmeasurable(reason: str) -> Field_:
    return Field_(None, UNMEASURABLE, note=reason)


def _pct_change(closes: Dict[str, float], as_of: str,
                sessions: int) -> Field_:
    """Return over the last N sessions. Unmeasurable when history is short.

    Sessions, not calendar days: counting calendar days would silently shorten
    every window across a weekend, and the error is invisible in the output.
    """
    usable = sorted((d, v) for d, v in (closes or {}).items()
                    if d <= as_of[:10] and v)
    if len(usable) < sessions + 1:
        return _unmeasurable(f"needs {sessions + 1} sessions, has {len(usable)}")
    start, end = usable[-(sessions + 1)][1], usable[-1][1]
    if not start:
        return _unmeasurable("zero reference price")
    return Field_(round((end - start) / start, 6), OBSERVED,
                  as_of=usable[-1][0])


def _volatility(closes: Dict[str, float], as_of: str,
                sessions: int = 20) -> Field_:
    usable = sorted((d, v) for d, v in (closes or {}).items()
                    if d <= as_of[:10] and v)
    if len(usable) < sessions + 1:
        return _unmeasurable("insufficient history for a volatility estimate")
    window = [v for _, v in usable[-(sessions + 1):]]
    rets = [(b - a) / a for a, b in zip(window, window[1:]) if a]
    if len(rets) < 2:
        return _unmeasurable("insufficient returns")
    mean = sum(rets) / len(rets)
    sd = math.sqrt(sum((r - mean) ** 2 for r in rets) / (len(rets) - 1))
    # Annualised, stated as INFERRED because it is a transformation of
    # observed data under an assumption (252 sessions, iid), not a measurement.
    return Field_(round(sd * math.sqrt(252), 6), INFERRED,
                  as_of=usable[-1][0],
                  note="annualised from 20 sessions assuming 252 trading days")


def _drawdown(closes: Dict[str, float], as_of: str,
              sessions: int = 252) -> Field_:
    usable = sorted((d, v) for d, v in (closes or {}).items()
                    if d <= as_of[:10] and v)
    if len(usable) < 30:
        return _unmeasurable("insufficient history for a drawdown")
    window = [v for _, v in usable[-sessions:]]
    peak, worst = window[0], 0.0
    for price in window:
        peak = max(peak, price)
        worst = min(worst, price / peak - 1)
    return Field_(round(worst, 6), OBSERVED, as_of=usable[-1][0],
                  note=f"maximum peak-to-trough over the last {len(window)} "
                       f"sessions")


def _relative(security: Field_, benchmark: Field_) -> Field_:
    """Benchmark-relative movement over the identical window."""
    if security.status != OBSERVED or benchmark.status != OBSERVED:
        return _unmeasurable("security or benchmark return unavailable")
    return Field_(round(security.value - benchmark.value, 6), OBSERVED,
                  as_of=security.as_of,
                  note="difference over the identical window")


def export_company(*, ticker: str, exchange: str = "",
                   closes: Optional[Dict[str, float]] = None,
                   benchmark_closes: Optional[Dict[str, float]] = None,
                   as_of: str, signal_quiet: bool = True,
                   opportunity_state: str = "",
                   company_id: str = "") -> dict:
    """One company's sanitized market snapshot.

    Fails closed throughout: an empty price series produces a payload of
    `unmeasurable` fields plus a stated limitation, never zeros and never an
    omitted section that a consumer might read as "nothing happened".
    """
    closes = closes or {}
    benchmark_closes = benchmark_closes or {}
    latest = max((d for d in closes if d <= as_of[:10]), default=None)

    windows = {"1m": 21, "3m": 63, "1y": 252}
    price_change = {k: _pct_change(closes, as_of, n) for k, n in windows.items()}
    bench_change = {k: _pct_change(benchmark_closes, as_of, n)
                    for k, n in windows.items()}
    relative = {k: _relative(price_change[k], bench_change[k]) for k in windows}

    limitations = []
    if not closes:
        limitations.append("No price history is available for this ticker; "
                           "every market field is unmeasurable.")
    if not benchmark_closes:
        limitations.append("No benchmark series is available, so "
                           "benchmark-relative movement cannot be computed.")
    unmeasured = [k for k, f in price_change.items()
                  if f.status == UNMEASURABLE]
    if unmeasured and closes:
        limitations.append(f"Insufficient history for: {', '.join(unmeasured)}.")

    payload = {
        "export_version": EXPORT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(
            timespec="seconds"),
        "ticker": ticker,
        "exchange": exchange,
        "company_id": company_id,
        "latest_completed_market_date": latest,
        "freshness": _freshness(latest, as_of),
        "price_change": {k: f.as_dict() for k, f in price_change.items()},
        "benchmark": {"symbol": "SPY",
                      "change": {k: f.as_dict()
                                 for k, f in bench_change.items()}},
        "benchmark_relative": {k: f.as_dict() for k, f in relative.items()},
        "volatility": _volatility(closes, as_of).as_dict(),
        "drawdown": _drawdown(closes, as_of).as_dict(),
        # Fundamentals are NOT fabricated. This project has no verified
        # earnings/revenue feed, so the fields exist and say so rather than
        # being silently absent (which a UI would render as "no news").
        "fundamentals": {
            "status": UNMEASURABLE,
            "note": ("No verified earnings, revenue, EPS or margin feed is "
                     "wired. These are reported as unavailable rather than "
                     "estimated — a fabricated financial series is the one "
                     "error that would make this actively harmful."),
        },
        "earnings_events": {"status": UNMEASURABLE,
                            "note": "no verified earnings calendar is wired"},
        "signal": {
            "state": "quiet" if signal_quiet else "active",
            "status": OBSERVED,
            "note": ("The engine's market signal is currently quiet. This "
                     "describes the signal, not the company."),
        },
        "opportunity": {"state": opportunity_state or "unknown",
                        "status": OBSERVED if opportunity_state
                        else UNMEASURABLE},
        "lineage": {
            "source": "public daily closes",
            "method": "point-in-time; only bars dated on or before as_of",
            "as_of": as_of[:10],
            "cost_model": "not applicable to descriptive market context",
        },
        "limitations": limitations,
        "disclaimer": DISCLAIMER,
        "interpretation_allowed": [
            "The shares moved X% over the period.",
            "The shares under/outperformed the benchmark by X over the period.",
            "Volatility is elevated/subdued relative to its recent history.",
            "The market signal is currently quiet.",
        ],
        "interpretation_forbidden": [
            "any buy/sell/hold recommendation, however hedged",
            "any statement of value, fairness or mispricing",
            "any forecast or price target",
            "any claim that a strategy predicts this company",
            "any presentation of engine trading performance as insight",
        ],
    }
    _assert_sanitized(payload)
    return payload


def _freshness(latest: Optional[str], as_of: str) -> dict:
    if not latest:
        return {"status": UNMEASURABLE, "note": "no completed bar available"}
    try:
        from datetime import date
        age = (date.fromisoformat(as_of[:10])
               - date.fromisoformat(latest)).days
    except (TypeError, ValueError):  # pragma: no cover
        return {"status": UNMEASURABLE, "note": "unparseable date"}
    return {"status": OBSERVED, "latest_bar": latest, "age_days": age,
            "stale": age > 5,
            "note": ("the newest completed session this export reflects")}


def _assert_sanitized(payload: dict) -> None:
    """Refuse to emit anything carrying a forbidden key, at any depth.

    Checked on the way out rather than trusted at the call sites: an upstream
    field added six months from now would otherwise ride along unnoticed.
    """
    def walk(node, path=""):
        if isinstance(node, dict):
            for key, value in node.items():
                lowered = str(key).lower()
                if lowered in FORBIDDEN_KEYS:
                    raise ExportLeak(
                        f"forbidden key {key!r} at {path or 'root'}")
                walk(value, f"{path}.{key}" if path else str(key))
        elif isinstance(node, (list, tuple)):
            for i, item in enumerate(node):
                walk(item, f"{path}[{i}]")

    walk(payload)


class ExportLeak(RuntimeError):
    """The export tried to emit an internal field."""


def write_export(payload: dict, root=".") -> pathlib.Path:
    """Publish one company's snapshot to the read-only export directory."""
    out = (pathlib.Path(root) / "reports/market/export"
           / f"{payload['ticker']}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=1, sort_keys=True, default=str))
    tmp.replace(out)
    return out
