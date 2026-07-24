"""Coarse regime label for the paper loop — a thin reuse of the platform's
existing regime intelligence (core.regime_engine.regime_snapshot).

Hardening note: the previous runtime referenced a non-existent
`regime_engine.current_regime`, so every real-runtime paper position was
silently stamped regime="unknown" (breaking regime attribution). This
module removes that dead branch by deriving a coarse label from the
composed snapshot the engine ALREADY computes — no new market intelligence,
just a mapping over existing, tested signals. Missing data -> "unknown",
never a fabricated regime.
"""
from __future__ import annotations

from typing import Dict

RISK_OFF = "risk_off"
RISK_ON = "risk_on"
NEUTRAL = "neutral"
UNKNOWN = "unknown"

# Credit-spread percentile above this reads as stress; below reads as calm.
_STRESS_PCTL = 70.0
_CALM_PCTL = 30.0


def regime_label(snapshot: Dict[str, object]) -> str:
    """Map a regime_snapshot() result to one coarse label. Uses the two most
    robust signals — yield-curve inversion and credit-spread percentile —
    and stays 'unknown' when neither is available."""
    curve = snapshot.get("curve_inversion")
    credit = snapshot.get("credit_spread_percentile")
    inverted = getattr(curve, "inverted", None)
    pctl = getattr(credit, "percentile", None)

    if inverted is None and pctl is None:
        return UNKNOWN
    stress = (inverted is True) or (pctl is not None and pctl >= _STRESS_PCTL)
    calm = (inverted is False) and (pctl is not None and pctl <= _CALM_PCTL)
    if stress:
        return RISK_OFF
    if calm:
        return RISK_ON
    return NEUTRAL


def fetch_regime_label(as_of: str, *, fred_key: str,
                       get_series=None) -> str:
    """Fetch the core FRED series and derive a label. Best-effort: any
    failure (no key, network, parse) resolves to 'unknown' rather than
    raising — regime is context on a paper position, not a gate."""
    try:
        from intent_engine.core.macro_data import get_series as _get_series
        from intent_engine.core.regime_engine import regime_snapshot
        fetch = get_series or _get_series
        series_ids = ("T10Y2Y", "BAMLH0A0HYM2")
        start = f"{int(as_of[:4]) - 2}{as_of[4:]}"
        data = {}
        for sid in series_ids:
            try:
                data[sid] = fetch(sid, start, as_of, api_key=fred_key)
            except Exception:  # noqa: BLE001 - one missing series is not fatal
                continue
        if not data:
            return UNKNOWN
        return regime_label(regime_snapshot(as_of, data))
    except Exception:  # noqa: BLE001
        return UNKNOWN
