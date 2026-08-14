"""Causal-engine pillar #3: calibration substrate. Task 1 of the overnight
execution plan (2026-07-15, ~/Downloads/overnight-execution-plan.md).

A prediction ledger: record a probabilistic claim, later resolve it against
a real outcome, and track calibration (do stated probabilities match
realized frequencies) via Brier scores computed in code, never model-asserted
-- same "model drafts/claims, code decides/computes" discipline as every
other scoring mechanism in this project (compute_coherence_note,
source_record_ids, the digest gate's inclusion decision).

Append-only, same convention as every other store in this project
(suggestion.py, draft_generator.py's DraftAttempt): resolving a prediction
appends a new row with the same id rather than mutating the original;
reads collapse to the latest row per id.

SCOPE WALL, per Task 1's own spec: no wiring into PremortemAnalyzer or any
live path yet. No backfilling old predictions. No UI. This is substrate
only -- a later task is where a live path actually writes to this ledger.

Task M5 (market-engine-execution-plan.md) extended this additively: two
new source values ("market", "baseline"), and 5 new nullable fields
(instrument, direction, horizon_days, resolution_rule, resolution_source)
for machine-evaluable market predictions. Additive per A3/M5's own scope
wall: no existing field renamed or removed, no SQL schema change needed
at all -- the underlying `predictions` table already stores each
Prediction as one JSON blob in its `data` column (see `_ensure_schema`
below), so a new Optional Prediction field is "free": an old row's JSON,
missing these fields entirely, still round-trips through
`Prediction.model_validate_json()` with them defaulting to None, no
migration script required. resolution_rule is validated at record time
by pydantic itself (a discriminated union on "type" -- PctChangeRule or
LevelRule) -- a malformed rule dict fails BaseModel construction with a
real ValidationError before anything is persisted, per the task's own
"reject malformed rules at record time" bar. Rules are DEFINED and
VALIDATED here only; evaluating one against real data is M6's job.
"""

import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional, Union

try:
    from typing import Literal
except ImportError:  # pragma: no cover
    from typing_extensions import Literal

from pydantic import BaseModel, Field

from .db import get_connection

DEFAULT_LEDGER_PATH = Path("data/prediction_ledger.db")

#: The version of the stored schema, published from the module that OWNS it.
#:
#: `executive/snapshots.py` has reported a prediction version since snapshots
#: existed, and imported this name to get it -- from a module that never
#: defined it. The import raised every time and the handler supplied the same
#: string the import would have, so the failure was invisible: success and
#: fallback were indistinguishable by construction.
#:
#: Still `v1`, and that is not inertia. Task M5 added five fields for
#: machine-evaluable market predictions, and every one of them lives inside
#: the JSON `data` blob -- the `predictions` TABLE in `_ensure_schema` is
#: unchanged since it was written. A reader of the table sees the same columns
#: it always did, so the version it is told is the version it gets. Bump this
#: when `_ensure_schema` changes, not when a field is added to `Prediction`.
PREDICTION_SCHEMA_VERSION = "prediction_ledger.v1"

PredictionSource = Literal["premortem", "scrap", "digest", "manual", "market", "baseline"]
PredictionOutcome = Literal["happened", "did_not_happen", "unresolvable"]
ResolutionSource = Literal["tiingo", "fred"]
ComparisonOp = Literal[">=", "<=", ">", "<", "=="]


class PctChangeRule(BaseModel):
    """e.g. {"type":"pct_change","symbol":"SPY","op":">=","value":0.02,"window_days":60}
    -- evaluated by M6 against Tiingo adjusted closes."""
    type: Literal["pct_change"]
    symbol: str
    op: ComparisonOp
    value: float
    window_days: int


class LevelRule(BaseModel):
    """e.g. {"type":"level","series":"UNRATE","op":">=","value":4.5,"by":"2026-12-31"}
    -- evaluated by M6 against FRED observations."""
    type: Literal["level"]
    series: str
    op: ComparisonOp
    value: float
    by: str  # ISO date string


ResolutionRule = Union[PctChangeRule, LevelRule]


def _current_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


class Prediction(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = Field(default_factory=_current_timestamp)
    source: PredictionSource
    entity_id: str
    claim_text: str
    probability: float  # 0-1, stated at creation time -- never touched at resolution
    resolve_by: str  # ISO date string
    resolved_at: Optional[str] = None
    outcome: Optional[PredictionOutcome] = None
    # Computed here in code at resolution time, from probability + outcome --
    # never asked of or asserted by a model. None until resolved; stays None
    # forever for "unresolvable" (excluded from brier_summary, not scored as
    # if it were a miss).
    brier_component: Optional[float] = None
    resolution_note: Optional[str] = None
    # Task M5 additions -- all nullable, all None for every non-market/
    # baseline source (premortem/scrap/digest/manual predictions never set
    # these; they resolve via a human/existing path, not M6).
    instrument: Optional[str] = None  # e.g. "SPY"
    direction: Optional[str] = None  # free text (e.g. "up"/"down") -- no closed set specified by the plan
    horizon_days: Optional[int] = None
    resolution_rule: Optional[ResolutionRule] = Field(default=None, discriminator="type")
    resolution_source: Optional[ResolutionSource] = None
    # T010 Slice 1B addition (V1_COMPLETION_ROADMAP.md Part E): a nullable
    # REFERENCE to the Decision Record that owns this prediction's decision
    # identity. Strictly one-way per the accepted design: the ledger never
    # allocates decisions, infers status, or writes records -- it only
    # carries the opaque ULID stamped by the caller. Additive like the M5
    # fields: old rows' JSON round-trips with this defaulting to None.
    decision_id: Optional[str] = None


def _ensure_schema(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS predictions (
            id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            source TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            resolved_at TEXT,
            outcome TEXT,
            data TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_predictions_id ON predictions(id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_predictions_source ON predictions(source)")
    conn.commit()


def _persist(prediction: Prediction, path: Union[str, Path]) -> None:
    conn = get_connection(path)
    try:
        _ensure_schema(conn)
        conn.execute(
            "INSERT INTO predictions (id, created_at, source, entity_id, resolved_at, outcome, data) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (prediction.id, prediction.created_at, prediction.source, prediction.entity_id,
             prediction.resolved_at, prediction.outcome, prediction.model_dump_json()),
        )
        conn.commit()
    finally:
        conn.close()


def _read_all(path: Union[str, Path]) -> List[Prediction]:
    path = Path(path)
    if not path.exists():
        return []
    conn = get_connection(path)
    try:
        _ensure_schema(conn)
        rows = conn.execute("SELECT data FROM predictions ORDER BY rowid").fetchall()
    finally:
        conn.close()
    return [Prediction.model_validate_json(row[0]) for row in rows]


def _read_latest(path: Union[str, Path]) -> List[Prediction]:
    latest: Dict[str, Prediction] = {}
    for p in _read_all(path):
        latest[p.id] = p
    return list(latest.values())


def record_prediction(
    source: PredictionSource,
    entity_id: str,
    claim_text: str,
    probability: float,
    resolve_by: Union[str, date],
    path: Union[str, Path] = DEFAULT_LEDGER_PATH,
    instrument: Optional[str] = None,
    direction: Optional[str] = None,
    horizon_days: Optional[int] = None,
    resolution_rule: Optional[Union[Dict[str, Any], PctChangeRule, LevelRule]] = None,
    resolution_source: Optional[ResolutionSource] = None,
    decision_id: Optional[str] = None,
) -> Prediction:
    if not (0.0 <= probability <= 1.0):
        raise ValueError(f"probability must be in [0, 1], got {probability!r}")

    resolve_by_str = resolve_by.isoformat() if isinstance(resolve_by, date) else resolve_by
    # resolution_rule is validated here, at record time, by Prediction's own
    # discriminated-union field -- a malformed dict (wrong/missing "type",
    # missing a type-specific required field, wrong value type) raises a
    # real pydantic.ValidationError from this constructor call, before
    # _persist() ever runs. Nothing is written on a malformed rule.
    prediction = Prediction(
        source=source, entity_id=entity_id, claim_text=claim_text,
        probability=probability, resolve_by=resolve_by_str,
        instrument=instrument, direction=direction, horizon_days=horizon_days,
        resolution_rule=resolution_rule, resolution_source=resolution_source,
        decision_id=decision_id,
    )
    _persist(prediction, path)
    return prediction


def resolve_prediction(
    prediction_id: str,
    outcome: PredictionOutcome,
    resolution_note: Optional[str] = None,
    path: Union[str, Path] = DEFAULT_LEDGER_PATH,
) -> Prediction:
    predictions = _read_latest(path)
    current = next((p for p in predictions if p.id == prediction_id), None)
    if current is None:
        raise ValueError(f"No prediction {prediction_id!r} found.")
    if current.outcome is not None:
        raise ValueError(f"Prediction {prediction_id!r} is already resolved (outcome={current.outcome!r}).")

    brier_component = None
    if outcome == "happened":
        brier_component = (current.probability - 1.0) ** 2
    elif outcome == "did_not_happen":
        brier_component = (current.probability - 0.0) ** 2
    # outcome == "unresolvable" -> brier_component stays None, excluded from brier_summary

    updated = current.model_copy(update={
        "resolved_at": _current_timestamp(),
        "outcome": outcome,
        "brier_component": brier_component,
        "resolution_note": resolution_note,
    })
    _persist(updated, path)
    return updated


def list_predictions(
    source: Optional[PredictionSource] = None,
    unresolved_only: bool = False,
    due_by: Optional[Union[str, date]] = None,
    path: Union[str, Path] = DEFAULT_LEDGER_PATH,
    decision_id: Optional[str] = None,
) -> List[Prediction]:
    """Task M6 addition: a small, additive read primitive -- the resolve
    script needs to find "all due, unresolved predictions" and no public
    function exposed that before now (only aggregate stats via
    brier_summary()). "unresolved" matches resolve_prediction()'s own
    definition exactly: outcome is None (not resolved_at, though the two
    are always set together in practice)."""
    predictions = _read_latest(path)
    if source is not None:
        predictions = [p for p in predictions if p.source == source]
    if decision_id is not None:
        # T010 Slice 1B: "all predictions for this decision" is the read the
        # idempotent intake wiring and the report (Slice 2A) both need.
        predictions = [p for p in predictions if p.decision_id == decision_id]
    if unresolved_only:
        predictions = [p for p in predictions if p.outcome is None]
    if due_by is not None:
        due_by_str = due_by.isoformat() if isinstance(due_by, date) else due_by
        predictions = [p for p in predictions if p.resolve_by <= due_by_str]
    return predictions


class CalibrationBucket(NamedTuple):
    count: int
    realized_rate: float  # fraction of this bucket's predictions that actually happened


class BrierSummary(NamedTuple):
    count: int
    mean_brier: Optional[float]  # None when count == 0
    # Keyed by predicted-probability decile, e.g. "70-80%" -- lets a person
    # see WHERE calibration is good/bad, not just one aggregate number.
    calibration_buckets: Dict[str, CalibrationBucket]


def brier_summary(
    source: Optional[PredictionSource] = None,
    window_days: Optional[int] = None,
    path: Union[str, Path] = DEFAULT_LEDGER_PATH,
) -> BrierSummary:
    """Real, code-computed calibration summary over resolved predictions.
    "unresolvable" outcomes are excluded entirely -- they were never scored
    as either a hit or a miss, so including them (as either) would fabricate
    information the resolution never provided.

    window_days: if given, only predictions RESOLVED within the last
    window_days (from now) are included -- lets a caller ask "how am I
    calibrated recently" separately from "how am I calibrated all-time."
    """
    predictions = _read_latest(path)
    resolved = [p for p in predictions if p.outcome in ("happened", "did_not_happen")]

    if source is not None:
        resolved = [p for p in resolved if p.source == source]

    if window_days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
        resolved = [p for p in resolved if datetime.fromisoformat(p.resolved_at) >= cutoff]

    if not resolved:
        return BrierSummary(count=0, mean_brier=None, calibration_buckets={})

    mean_brier = sum(p.brier_component for p in resolved) / len(resolved)

    raw_buckets: Dict[str, Dict[str, int]] = {}
    for p in resolved:
        decile = min(int(p.probability * 10), 9)  # clamps probability==1.0 into the top bucket
        key = f"{decile * 10}-{decile * 10 + 10}%"
        bucket = raw_buckets.setdefault(key, {"count": 0, "happened": 0})
        bucket["count"] += 1
        if p.outcome == "happened":
            bucket["happened"] += 1

    calibration_buckets = {
        key: CalibrationBucket(count=b["count"], realized_rate=b["happened"] / b["count"])
        for key, b in raw_buckets.items()
    }

    return BrierSummary(count=len(resolved), mean_brier=mean_brier, calibration_buckets=calibration_buckets)
