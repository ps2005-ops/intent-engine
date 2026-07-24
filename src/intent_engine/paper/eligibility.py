"""Prediction -> paper-trading intent eligibility (1C).

Deterministic, pure, credential-independent: given a Prediction record and
the current book, decide whether it should become a paper position and, if
not, WHY. Not every prediction becomes a trade — explicit eligibility rules
gate it, and every rejection is persisted with a reason (no silent drop).

The adapter produces a PaperIntent carrying full provenance; it does NOT
fetch a price (that needs market data). The market job fetches the entry
price and opens the position from the intent, so this stays offline-testable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from intent_engine.core.prediction_ledger import Prediction

# Versioned so every paper position records which rules produced it — a
# promotion later can compare strategy/risk versions. Bump on any change.
STRATEGY_VERSION = "paper_strategy.v1"
RISK_RULE_VERSION = "paper_risk.v1"

# Instruments the shadow book supports. An allowlist, not "anything the
# prediction named" — provenance and price coverage must be known.
SUPPORTED_INSTRUMENTS = ("SPY", "QQQ", "IWM", "DIA", "TLT", "GLD", "HYG")

_DIRECTION_MAP = {"up": "long", "long": "long", "bull": "long",
                  "down": "short", "short": "short", "bear": "short"}


@dataclass(frozen=True)
class EligibilityConfig:
    supported_instruments: tuple = SUPPORTED_INSTRUMENTS
    min_confidence: float = 0.60          # below this, no edge worth a trade
    max_horizon_days: int = 400
    min_horizon_days: int = 1
    max_data_age_days: int = 5            # prediction must be fresh
    max_open_positions: int = 25         # portfolio-level risk limit
    allow_short: bool = True


@dataclass(frozen=True)
class PaperIntent:
    prediction_id: str
    decision_id: Optional[str]
    instrument: str
    direction: str                        # "long" | "short"
    confidence: float
    regime: str
    reasoning: str
    horizon_days: int
    data_snapshot: Dict[str, Any] = field(default_factory=dict)
    strategy_version: str = STRATEGY_VERSION
    risk_rule_version: str = RISK_RULE_VERSION
    created_at: str = ""


@dataclass(frozen=True)
class EligibilityResult:
    eligible: bool
    prediction_id: str
    intent: Optional[PaperIntent] = None
    reason: Optional[str] = None
    rule: Optional[str] = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _age_days(created_at: str, as_of: str) -> Optional[int]:
    try:
        c = datetime.fromisoformat(created_at).date()
        a = date.fromisoformat(as_of[:10])
        return (a - c).days
    except (ValueError, TypeError):
        return None


def evaluate_prediction(
    prediction: Prediction, *, config: EligibilityConfig,
    open_prediction_ids: Optional[set] = None,
    open_position_count: int = 0,
    regime: str = "unknown", reasoning: str = "", as_of: Optional[str] = None,
) -> EligibilityResult:
    open_prediction_ids = open_prediction_ids or set()
    as_of = as_of or _now()
    pid = prediction.id

    def reject(reason: str, rule: str) -> EligibilityResult:
        return EligibilityResult(False, pid, reason=reason, rule=rule)

    # portfolio-level risk limit
    if open_position_count >= config.max_open_positions:
        return reject(
            f"portfolio at max open positions ({config.max_open_positions})",
            "risk_limit")
    # not already represented
    if pid in open_prediction_ids:
        return reject("prediction already has an open paper position",
                      "duplicate_exposure")
    # already resolved predictions do not open new positions
    if prediction.outcome is not None:
        return reject("prediction is already resolved", "already_resolved")
    # supported instrument
    instrument = (prediction.instrument or "").upper()
    if instrument not in config.supported_instruments:
        return reject(f"instrument {instrument or '(none)'!r} not supported",
                      "unsupported_instrument")
    # direction
    direction = _DIRECTION_MAP.get(str(prediction.direction or "").lower())
    if direction is None:
        return reject(f"direction {prediction.direction!r} not interpretable",
                      "bad_direction")
    if direction == "short" and not config.allow_short:
        return reject("short positions disabled by policy", "short_disabled")
    # confidence (probability is the engine's stated confidence)
    confidence = float(prediction.probability)
    if confidence < config.min_confidence:
        return reject(
            f"confidence {confidence:.2f} < min {config.min_confidence:.2f}",
            "low_confidence")
    # horizon
    horizon = prediction.horizon_days
    if horizon is None or not (config.min_horizon_days <= horizon
                               <= config.max_horizon_days):
        return reject(f"horizon {horizon!r} outside "
                      f"[{config.min_horizon_days},{config.max_horizon_days}]",
                      "bad_horizon")
    # freshness
    age = _age_days(prediction.created_at, as_of)
    if age is None:
        return reject("prediction timestamp unparseable", "stale_data")
    if age > config.max_data_age_days:
        return reject(f"prediction is {age}d old (> {config.max_data_age_days})",
                      "stale_data")
    # complete provenance
    if not str(reasoning or prediction.claim_text or "").strip():
        return reject("no reasoning/claim available for provenance",
                      "incomplete_provenance")

    intent = PaperIntent(
        prediction_id=pid, decision_id=prediction.decision_id,
        instrument=instrument, direction=direction, confidence=confidence,
        regime=regime, reasoning=reasoning or prediction.claim_text,
        horizon_days=horizon,
        data_snapshot={"resolution_source": prediction.resolution_source,
                       "resolution_rule": (prediction.resolution_rule.model_dump()
                                           if prediction.resolution_rule else None),
                       "prediction_created_at": prediction.created_at},
        created_at=as_of)
    return EligibilityResult(True, pid, intent=intent)
