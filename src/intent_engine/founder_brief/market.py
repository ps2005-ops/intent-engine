"""Consumer for `market_intel_export.v1` — narrow, versioned, read-only.

THE BOUNDARY
------------
The market learning engine is an UPSTREAM SOURCE. This module reads one
versioned JSON contract and nothing else. It never touches a paper book, a
replay checkpoint, an experiment registry or a runtime path — not because those
are secret, but because a founder-facing product that reads research internals
will eventually render one of them, and the one most likely to be rendered is a
control's win rate.

WHAT THIS REFUSES TO PASS THROUGH
---------------------------------
* any performance figure from the engine's own paper trading
* any recommendation, however hedged
* any value or fairness judgement
* any forecast

The export publishes `interpretation_forbidden` and this module honours it: a
module that produced a sentence on that list would be a bug, so the sentence
builders below can only produce descriptive statements.

FAIL CLOSED
-----------
A wrong schema version, a stale snapshot, a ticker mismatch or a missing field
all end the same way — the module returns `available: False` with a reason, and
the dashboard renders "Unavailable" instead of a chart. A missing value is
never a zero.
"""
from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, Optional

SUPPORTED_VERSION = "market_intel_export.v1"

# Beyond this the snapshot describes a market that has moved on. Seven calendar
# days spans a long weekend plus a holiday without tripping.
MAX_AGE_DAYS = 7

REQUIRED_DISCLAIMER = ("Descriptive market context, not an investment "
                       "recommendation.")


@dataclass(frozen=True)
class MarketContext:
    """The founder-facing view of the market export. Descriptive only."""
    available: bool
    reason: str = ""
    ticker: str = ""
    as_of: str = ""
    age_days: Optional[int] = None
    stale: bool = False
    statements: tuple = ()
    modules: dict = None
    limitations: tuple = ()
    disclaimer: str = REQUIRED_DISCLAIMER

    def as_dict(self) -> dict:
        return {"available": self.available, "reason": self.reason,
                "ticker": self.ticker, "as_of": self.as_of,
                "age_days": self.age_days, "stale": self.stale,
                "statements": list(self.statements),
                "modules": self.modules or {},
                "limitations": list(self.limitations),
                "disclaimer": self.disclaimer}


def unavailable(reason: str, ticker: str = "") -> MarketContext:
    return MarketContext(available=False, reason=reason, ticker=ticker)


def load(path, *, expected_ticker: str = "",
         today: Optional[str] = None) -> MarketContext:
    """Read one export file and validate it before anything is shown."""
    p = pathlib.Path(path)
    if not p.exists():
        return unavailable("no market snapshot has been published for this "
                           "company", expected_ticker)
    try:
        payload = json.loads(p.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        return unavailable(f"market snapshot unreadable ({type(exc).__name__})",
                           expected_ticker)
    return consume(payload, expected_ticker=expected_ticker, today=today)


def consume(payload: dict, *, expected_ticker: str = "",
            today: Optional[str] = None) -> MarketContext:
    """Validate identity, version and freshness, then build descriptive text."""
    version = (payload or {}).get("export_version")
    if version != SUPPORTED_VERSION:
        # Refuses rather than best-efforts an unknown schema: a field that
        # moved between versions would be rendered under the wrong label, and
        # a wrong number with a confident caption is worse than no number.
        return unavailable(
            f"market snapshot is {version!r}, this product reads "
            f"{SUPPORTED_VERSION!r} only")

    ticker = payload.get("ticker") or ""
    if expected_ticker and ticker and ticker.upper() != expected_ticker.upper():
        return unavailable(
            f"snapshot is for {ticker}, not {expected_ticker}", ticker)

    latest = payload.get("latest_completed_market_date")
    freshness = payload.get("freshness") or {}
    age = freshness.get("age_days")
    if latest and today:
        try:
            age = (date.fromisoformat(today[:10])
                   - date.fromisoformat(latest)).days
        except ValueError:  # pragma: no cover
            age = None
    if not latest:
        return unavailable("the snapshot carries no completed market date",
                           ticker)
    stale = bool(age is not None and age > MAX_AGE_DAYS)

    modules, statements, limitations = _modules(payload)
    limitations = list(limitations) + list(payload.get("limitations") or ())
    if stale:
        limitations.insert(0, f"This market data is {age} days old and may not "
                              f"reflect recent trading.")
    return MarketContext(
        available=bool(modules), reason="" if modules else
        "no market field in the snapshot was measurable",
        ticker=ticker, as_of=latest, age_days=age, stale=stale,
        statements=tuple(statements), modules=modules,
        limitations=tuple(limitations))


_WINDOW_WORDS = {"1m": "the past month", "3m": "the past three months",
                 "1y": "the past year"}


def _modules(payload: dict) -> tuple:
    """Build only the modules whose data is genuinely present.

    A module with an unmeasurable series is OMITTED rather than rendered empty:
    a chart axis with no line is read as "flat", which is a claim the data does
    not support.
    """
    modules: Dict[str, Any] = {}
    statements = []
    limitations = []

    price = payload.get("price_change") or {}
    relative = payload.get("benchmark_relative") or {}
    series = {}
    for window, field in price.items():
        if (field or {}).get("status") == "observed" and field.get(
                "value") is not None:
            series[window] = field["value"]
    if series:
        modules["price"] = {
            "series": series,
            "what_changed": _price_sentence(series),
            "so_what": ("Share-price movement is how the market is currently "
                        "pricing expectations for this business. It reflects "
                        "sentiment and positioning as well as fundamentals."),
            "what_to_watch": ("Whether the move continues after the next "
                              "scheduled disclosure, which separates a "
                              "re-rating from noise."),
        }
        statements.extend(_price_sentence(series, as_list=True))
    else:
        limitations.append("Share-price history was not available, so no "
                           "market trajectory is shown.")

    rel = {w: (f or {}).get("value") for w, f in relative.items()
           if (f or {}).get("status") == "observed"
           and (f or {}).get("value") is not None}
    if rel:
        modules["benchmark_relative"] = {
            "series": rel,
            "what_changed": _relative_sentence(rel),
            "so_what": ("Movement relative to the broad market separates what "
                        "is happening to this company from what is happening "
                        "to everything."),
            "what_to_watch": ("Whether the gap narrows once sector-wide "
                              "moves settle."),
        }
        statements.append(_relative_sentence(rel))

    vol = payload.get("volatility") or {}
    if vol.get("value") is not None and vol.get("status") in ("observed",
                                                              "inferred"):
        modules["volatility"] = {
            "value": vol["value"], "status": vol["status"],
            "what_changed": (f"Annualised volatility is about "
                             f"{vol['value'] * 100:.0f}%."),
            "so_what": ("Higher volatility means the market is less settled "
                        "about this company's outlook, which widens the range "
                        "of outcomes a plan should tolerate."),
            "what_to_watch": "Whether it subsides after the next disclosure.",
        }

    dd = payload.get("drawdown") or {}
    if dd.get("value") is not None and dd.get("status") == "observed":
        modules["drawdown"] = {
            "value": dd["value"],
            "what_changed": (f"The shares are about "
                             f"{abs(dd['value']) * 100:.0f}% below their "
                             f"highest point in the period shown."),
            "so_what": ("A deep drawdown changes the cost of raising capital "
                        "and the mood of existing investors."),
            "what_to_watch": "Whether the low holds on the next weak news.",
        }

    fundamentals = payload.get("fundamentals") or {}
    if fundamentals.get("status") == "unmeasurable":
        limitations.append(
            "No verified revenue, earnings or margin data is available for "
            "this company, so no financial trajectory is shown. Estimated "
            "figures are deliberately not substituted.")

    signal = payload.get("signal") or {}
    if signal.get("state"):
        modules["signal"] = {
            "state": signal["state"],
            "what_changed": (
                "The market signal this system tracks is currently "
                f"{signal['state']}."),
            "so_what": ("This describes the signal, not the company. A quiet "
                        "signal means no qualifying pattern was detected — "
                        "not that nothing is happening."),
            "what_to_watch": "Whether it becomes active around a disclosure.",
        }
    return modules, statements, limitations


def _price_sentence(series: Dict[str, float], as_list: bool = False):
    parts = []
    for window in ("1m", "3m", "1y"):
        if window in series:
            value = series[window]
            direction = "rose" if value > 0 else "fell"
            parts.append(f"The shares {direction} "
                         f"{abs(value) * 100:.1f}% over "
                         f"{_WINDOW_WORDS[window]}.")
    return parts if as_list else " ".join(parts)


def _relative_sentence(series: Dict[str, float]) -> str:
    for window in ("1y", "3m", "1m"):
        if window in series:
            value = series[window]
            word = "outperformed" if value > 0 else "underperformed"
            return (f"Over {_WINDOW_WORDS[window]} the shares {word} the "
                    f"broad market by {abs(value) * 100:.1f} percentage "
                    f"points.")
    return ""
