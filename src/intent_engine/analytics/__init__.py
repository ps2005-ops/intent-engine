"""Analytics and Calibration (T015) — deterministic read-side views over
the platform's authoritative stores.

Ownership: analytics owns derived aggregate views ONLY. DecisionService
owns decisions; the prediction ledger owns claims/grades (brier_summary
is reused, never forked); the CRM owns relationship history; the event
system owns delivery. Analytics never writes to any of them, never
advances a checkpoint, never invents a missing fact, and never claims
calibration below the A-M5 evidence gate.

Canonical analytics contract: `models.py` (MetricResult, versions,
window semantics). Docs cross-reference it.
"""
from intent_engine.analytics.models import (  # noqa: F401
    METRIC_VERSIONS, NO_OBSERVATION_SOURCE, TOO_FEW, UNAVAILABLE,
    MetricResult, Window, make_window,
)
from intent_engine.analytics.calibration import (  # noqa: F401
    CALIBRATION_GATE_RESOLVED,
)
from intent_engine.analytics.service import AnalyticsService  # noqa: F401
