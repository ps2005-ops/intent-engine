"""Paper-Trading Shadow Loop — record contracts.

SIMULATION ONLY. No broker, no real money, no live orders anywhere in this
package (a test asserts the service exposes no order-submission surface).
This is the "first real source of objective feedback" the founder's
architecture calls for: the engine's predictions become tracked paper
positions, scored in code, so calibration is measured against a portfolio
outcome — not asserted.

Traceability is a hard contract, not a convention: every PaperPosition
MUST carry the prediction, the decision, the regime, the confidence, and
the reasoning it came from. `require_traceable()` raises otherwise — "no
black box", enforced. This is why a paper trade can always be expanded
back to prediction -> reasoning -> confidence -> regime -> decision record.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

try:
    from typing import Literal
except ImportError:  # pragma: no cover
    from typing_extensions import Literal

from pydantic import BaseModel, Field

from intent_engine.core.decision_ids import new_ulid

PositionStatus = Literal["open", "closed"]
Direction = Literal["long", "short"]
ExitReason = Literal["target", "stop", "prediction_resolved", "manual"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class PaperPosition(BaseModel):
    id: str = Field(default_factory=new_ulid)
    opened_at: str = Field(default_factory=_now)
    # --- traceability (all required; enforced by require_traceable) ----------
    prediction_id: str
    decision_id: Optional[str] = None   # carried from the prediction if any
    regime: str                          # regime label at entry
    confidence: float                    # 0-1, the engine's stated confidence
    reasoning: str                       # the engine's own recorded basis
    # --- position mechanics --------------------------------------------------
    instrument: str
    direction: Direction
    entry_price: float
    size: float                          # units held (fraction-of-equity * ...)
    stop_price: Optional[float] = None
    target_price: Optional[float] = None
    status: PositionStatus = "open"
    # --- provenance (additive; carried from the eligibility adapter) ---------
    # Nullable so older rows round-trip; set for every position opened from a
    # prediction via the eligibility adapter.
    horizon_days: Optional[int] = None
    strategy_version: Optional[str] = None
    risk_rule_version: Optional[str] = None
    opened_from: Optional[str] = None    # e.g. "prediction"
    data_snapshot: dict = Field(default_factory=dict)
    # --- close (None until closed) -------------------------------------------
    closed_at: Optional[str] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[ExitReason] = None
    pnl: Optional[float] = None          # signed, in equity units
    return_pct: Optional[float] = None   # signed fractional return on entry
    regime_at_exit: Optional[str] = None

    def require_traceable(self) -> None:
        missing = [f for f in ("prediction_id", "regime", "reasoning")
                   if not str(getattr(self, f) or "").strip()]
        if missing:
            raise ValueError(
                f"paper position is not traceable — missing {missing}; "
                "every position must connect to prediction/regime/reasoning "
                "(no black box)")
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(
                f"confidence must be in [0,1], got {self.confidence!r}")
