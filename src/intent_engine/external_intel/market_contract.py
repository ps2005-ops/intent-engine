"""`market_intel_export.v2` — the sanctioned schema, enforced by ALLOWLIST.

WHY v2 EXISTS WHEN v1 ALREADY HAD A SANITISER
----------------------------------------------
v1 guarded with `FORBIDDEN_KEYS`, a blacklist. A blacklist answers "is this one
of the fields we thought of?" -- and the field that leaks is by definition the
one nobody thought of. An audit of the market engine's own daily report found
`funnel.counts.positions_opened`, `funnel.counts.buy`, `funnel.rates.
signal_fired`, `leaderboard.rows`, `fdr.discoveries` and `health.lock.path`.
Not one of those names is in v1's blacklist. Every one of them would have
ridden through.

So v2 inverts the test. `ALLOWED` names every field that may appear, at every
depth, and `validate()` raises on anything else. A new upstream field fails
closed -- it does not render, and it does not silently pass.

Two further v1 fields are gone on purpose, because the audit classified them
INTERNAL rather than SAFE:

    signal.state        described the engine's own detector ("the market
                        signal this system tracks is currently quiet"). That
                        is a sentence about the trading engine printed on a
                        founder's screen. A founder cannot act on it, and it
                        invites the follow-up question -- how well does the
                        signal do? -- that this boundary exists to refuse.
    opportunity.state   an internal opportunity label, listed as INTERNAL in
                        the audit for the same reason.

WHERE THE DATA COMES FROM, AND WHAT THAT BUYS
----------------------------------------------
The producer reads PUBLIC PRICE HISTORY directly. It does not read the market
engine's stores, reports, paper books, strategy registry or funnel at all --
there is no import path from this package to any of them. That is a stronger
guarantee than filtering engine artefacts would be: a leak would require
someone to add the import first, and the repository guard would see it.

MISSING IS NEVER ZERO
---------------------
Every measurement carries a `status`:

    observed      measured from real closes
    inferred      derived from observed data under a stated assumption
    unmeasurable  the data does not exist -- value stays None

A `value` of None with status `unmeasurable` is the honest encoding of "we do
not know". Zero is a measurement, and it is a different claim.

DESCRIPTIVE, NEVER PREDICTIVE
------------------------------
No recommendation, expected return, predicted direction, price target,
strategy performance or paper-trade result is expressible in this schema --
there is no key for one, so `validate()` rejects it rather than trusting the
producer to leave it out.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

SCHEMA_VERSION = "market_intel_export.v2"

OBSERVED = "observed"
INFERRED = "inferred"
UNMEASURABLE = "unmeasurable"
STATUSES = frozenset({OBSERVED, INFERRED, UNMEASURABLE})

DISCLAIMER = ("Descriptive market context from public price history. Not a "
              "recommendation, a valuation or a forecast.")

INTERPRETATION_FORBIDDEN = (
    "any buy, sell or hold suggestion, however hedged",
    "any statement that the shares are cheap, dear, over- or under-valued",
    "any forecast, price target or expected return",
    "any claim that price movement proves the operating strategy right "
    "or wrong",
    "any performance figure from the engine's own trading",
)

# --- the allowlist ----------------------------------------------------------
# `...` means "a leaf: any JSON scalar, list of scalars, or list of mappings
# already checked by its own spec". A mapping value means "recurse". `_ANY_KEY`
# means "the keys here are data (a period label, a date), not schema".
_ANY_KEY = "*"

#: One measurement. Every numeric value in this export is one of these, so
#: period, unit, source, observation date and freshness travel WITH the number
#: rather than being implied by where it sits. A number whose period is
#: implied by its key is a number that gets relabelled the first time a
#: consumer iterates the mapping in a different order.
MEASUREMENT = {
    "value": ...,
    "status": ...,
    "period": ...,
    "unit": ...,
    "source": ...,
    "observation_date": ...,
    "freshness_days": ...,
    "note": ...,
}

_EVENT = {
    "date": ...,
    "label": ...,
    "kind": ...,
    "source": ...,
    "evidence_id": ...,
}

ALLOWED = {
    "schema_version": ...,
    "company_id": ...,
    "ticker": ...,
    "exchange": ...,
    "currency": ...,
    "as_of": ...,
    "generated_at": ...,
    "data_freshness": {
        "latest_session": ...,
        "age_days": ...,
        "stale": ...,
        "status": ...,
        "note": ...,
    },
    "price_periods": {_ANY_KEY: MEASUREMENT},
    "benchmark": {
        "symbol": ...,
        "name": ...,
        "periods": {_ANY_KEY: MEASUREMENT},
    },
    "benchmark_relative_periods": {_ANY_KEY: MEASUREMENT},
    "annualized_volatility": MEASUREMENT,
    "period_drawdown": MEASUREMENT,
    "distance_from_period_high": MEASUREMENT,
    "market_regime": {
        "label": ...,
        "basis": ...,
        "status": ...,
        "observation_date": ...,
        "source": ...,
        "note": ...,
    },
    "relevant_market_events": [_EVENT],
    # Normalised closes for the trajectory chart. Real observations only, and
    # only ever plotted against the benchmark on the identical dates -- a
    # chart drawn from two different date sets is a comparison of two
    # different questions.
    "series": {
        "dates": ...,
        "company_indexed": ...,
        "benchmark_indexed": ...,
        "base": ...,
        "unit": ...,
        "source": ...,
        "note": ...,
    },
    "limitations": ...,
    "evidence_ids": ...,
    "source_lineage": {
        "provider": ...,
        "endpoint_family": ...,
        "method": ...,
        "retrieved_at": ...,
        "point_in_time": ...,
        "caveat": ...,
    },
    "disclaimer": ...,
    "interpretation_forbidden": ...,
}

#: Defence in depth, not the primary gate. The allowlist above already refuses
#: an unknown key; this catches a SANCTIONED key being filled with forbidden
#: CONTENT -- `market_regime.label = "sharpe 1.8"` passes the allowlist and
#: must still not ship.
FORBIDDEN_SUBSTRINGS = (
    "win_rate", "win rate", "sharpe", "profit factor", "profit_factor",
    "expectancy", "alpha", "paper_control", "paper control", "paper trade",
    "paper-trade", "strategy_key", "signal_fired", "positions_opened",
    "graduation", "buy signal", "sell signal", "price target",
    "expected return", "recommendation", "we recommend", "forecast",
)


class ExportViolation(ValueError):
    """The export tried to carry something the contract does not sanction."""


def measurement(value: Optional[float], status: str, *, period: str,
                unit: str, source: str, observation_date: str = "",
                freshness_days: Optional[int] = None,
                note: str = "") -> dict:
    """Build one measurement, refusing the encodings that mislead.

    A value with an `unmeasurable` status must be None, and a None value must
    not claim to be observed -- those two mistakes are how "we do not know"
    becomes "it is zero", which is the single most damaging error this export
    can make.
    """
    if status not in STATUSES:
        raise ExportViolation(f"unknown measurement status {status!r}")
    if status == UNMEASURABLE and value is not None:
        raise ExportViolation("an unmeasurable measurement cannot carry a "
                              "value")
    if status != UNMEASURABLE and value is None:
        raise ExportViolation(f"a {status} measurement needs a value; use "
                              f"{UNMEASURABLE!r} when the data is absent")
    return {"value": value, "status": status, "period": period, "unit": unit,
            "source": source, "observation_date": observation_date,
            "freshness_days": freshness_days, "note": note}


def unmeasurable(reason: str, *, period: str = "", unit: str = "",
                 source: str = "") -> dict:
    return measurement(None, UNMEASURABLE, period=period, unit=unit,
                       source=source, note=reason)


#: The two fields whose whole job is to NAME what is forbidden. They contain
#: the banned words by design -- "not a recommendation, a valuation or a
#: forecast" is a refusal, and a content scan cannot tell a refusal from a
#: claim.
#:
#: They are exempted from the scan by being FIXED rather than by being trusted:
#: each must equal this module's own constant exactly, so there is no free text
#: in them for anything to hide in. A producer that wanted to smuggle a
#: sentence past the scan by putting it in `disclaimer` fails validation
#: instead.
_FIXED_TEXT = {
    "disclaimer": DISCLAIMER,
    "interpretation_forbidden": list(INTERPRETATION_FORBIDDEN),
}


def validate(payload: Any, spec: Any = None, path: str = "") -> None:
    """Raise unless every field at every depth is sanctioned.

    Recursive by construction: the failure this replaces was a nested field
    (`funnel.counts.positions_opened`) passing a top-level check.
    """
    if spec is None:
        if not isinstance(payload, dict):
            raise ExportViolation("export must be a mapping")
        if payload.get("schema_version") != SCHEMA_VERSION:
            raise ExportViolation(
                f"schema_version is {payload.get('schema_version')!r}, "
                f"this contract is {SCHEMA_VERSION!r}")
        for key, fixed in _FIXED_TEXT.items():
            if key in payload and list(payload[key]) != list(fixed) \
                    and payload[key] != fixed:
                raise ExportViolation(
                    f"{key!r} must be this contract's own text verbatim; it "
                    f"is exempt from the content scan only because it is "
                    f"fixed")
        spec = ALLOWED

    here = path or "root"
    if spec is ...:
        _scan_content(payload, here)
        return

    if isinstance(spec, list):
        if not isinstance(payload, (list, tuple)):
            raise ExportViolation(f"{here} must be a list")
        for i, item in enumerate(payload):
            validate(item, spec[0], f"{here}[{i}]")
        return

    if isinstance(spec, dict):
        if not isinstance(payload, dict):
            raise ExportViolation(f"{here} must be a mapping")
        wildcard = spec.get(_ANY_KEY)
        for key, value in payload.items():
            if wildcard is not None and key not in spec:
                # The KEY is data (a period label). It still may not smuggle
                # content, so it is scanned like any other string.
                _scan_content(key, f"{here}.<key>")
                validate(value, wildcard, f"{here}.{key}")
                continue
            if key not in spec:
                raise ExportViolation(
                    f"unsanctioned field {here}.{key!r} — "
                    f"market_intel_export.v2 fails closed on fields it does "
                    f"not name, so add it to ALLOWED deliberately or drop it")
            if path == "" and key in _FIXED_TEXT:
                continue  # already checked verbatim above; nothing to scan
            validate(value, spec[key], f"{here}.{key}")
        return

    raise ExportViolation(f"malformed spec at {here}")  # pragma: no cover


def _scan_content(node: Any, path: str) -> None:
    """A sanctioned key filled with forbidden content is still a leak."""
    if isinstance(node, str):
        lowered = node.lower()
        for banned in FORBIDDEN_SUBSTRINGS:
            if banned in lowered:
                raise ExportViolation(
                    f"forbidden content {banned!r} in {path}")
    elif isinstance(node, dict):
        for key, value in node.items():
            _scan_content(key, f"{path}.<key>")
            _scan_content(value, f"{path}.{key}")
    elif isinstance(node, (list, tuple)):
        for i, item in enumerate(node):
            _scan_content(item, f"{path}[{i}]")


@dataclass(frozen=True)
class MarketIntel:
    """A validated export, or an explicit, reasoned absence.

    There is no third state. Every consumer branches on `available` and gets a
    sentence it can print when the answer is no.
    """
    available: bool
    reason: str = ""
    ticker: str = ""
    payload: Optional[dict] = None
    stale: bool = False
    age_days: Optional[int] = None

    @property
    def as_of(self) -> str:
        return ((self.payload or {}).get("data_freshness") or {}).get(
            "latest_session", "")

    def as_dict(self) -> dict:
        return {"available": self.available, "reason": self.reason,
                "ticker": self.ticker, "stale": self.stale,
                "age_days": self.age_days, "as_of": self.as_of,
                "payload": self.payload}


def absent(reason: str, ticker: str = "") -> MarketIntel:
    return MarketIntel(available=False, reason=reason, ticker=ticker)
