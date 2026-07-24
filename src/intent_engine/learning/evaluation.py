"""Real walk-forward candidate evaluation (1G).

Turns the weekly comparison from an interface into a real, deterministic,
out-of-sample harness — credential-independent because it operates over
already-persisted resolved predictions, not live data.

Scope, stated honestly: this implements a genuine walk-forward evaluation
for **calibration** candidates (the type the daily generator produces from
resolved-prediction evidence). Each candidate is scored candidate-vs-
baseline on EXPANDING out-of-sample windows, with a minimum-sample gate that
yields INSUFFICIENT_EVIDENCE rather than a flattering in-sample number.

Candidates whose evaluation needs machinery not yet built here (paper-trade
strategy replays, synthetic mechanism edits) are recorded as
INSUFFICIENT_EVIDENCE with an explicit reason — never scored with invented
metrics. That keeps promotion honest: no candidate can pass on fabricated
evidence.
"""
from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

from intent_engine.core.prediction_ledger import Prediction

# Minimum resolved predictions before a walk-forward evaluation is meaningful.
MIN_RESOLVED = 20
MIN_TEST = 5


def _resolved(preds: List[Prediction]) -> List[Prediction]:
    out = [p for p in preds if p.outcome in ("happened", "did_not_happen")
           and p.resolved_at]
    out.sort(key=lambda p: p.resolved_at)
    return out


def _y(p: Prediction) -> int:
    return 1 if p.outcome == "happened" else 0


def brier(preds: List[Prediction]) -> Optional[float]:
    if not preds:
        return None
    return sum((p.probability - _y(p)) ** 2 for p in preds) / len(preds)


def hit_rate(preds: List[Prediction]) -> Optional[float]:
    """Directional accuracy: prob>=0.5 predicts 'happened'."""
    if not preds:
        return None
    correct = sum(1 for p in preds if (p.probability >= 0.5) == (_y(p) == 1))
    return correct / len(preds)


def calibration_error(preds: List[Prediction]) -> Optional[float]:
    """Mean absolute gap between predicted probability and realized rate,
    aggregated over decile buckets (a real reliability-diagram error)."""
    if not preds:
        return None
    buckets: Dict[int, List[Prediction]] = {}
    for p in preds:
        buckets.setdefault(min(int(p.probability * 10), 9), []).append(p)
    total, n = 0.0, 0
    for decile, items in buckets.items():
        predicted_mid = (decile * 10 + 5) / 100.0
        realized = sum(_y(i) for i in items) / len(items)
        total += abs(predicted_mid - realized) * len(items)
        n += len(items)
    return total / n if n else None


def walk_forward(preds: List[Prediction], *, min_train: int = 10,
                 min_test: int = MIN_TEST, splits: int = 3
                 ) -> List[Tuple[List[Prediction], List[Prediction]]]:
    """Expanding-window splits, chronological. Each split trains on the
    prefix and tests on the next block — out-of-sample by construction."""
    preds = _resolved(preds)
    n = len(preds)
    if n < min_train + min_test:
        return []
    test_total = n - min_train
    block = max(min_test, test_total // splits)
    windows = []
    start = min_train
    while start + min_test <= n:
        end = min(start + block, n)
        windows.append((preds[:start], preds[start:end]))
        start = end
    return windows


def apply_calibration_shift(preds: List[Prediction], *, bucket: str,
                            observed_realized: float) -> List[Prediction]:
    """The candidate transform: in the named decile bucket, move predicted
    probabilities toward the TRAIN-observed realized rate (shrink
    overconfidence). Deterministic, pure. Learned only from train data —
    the caller passes the train-derived observed_realized, so this is not
    peeking at the test window."""
    lo = int(bucket.split("-")[0])
    hi = lo + 10
    shifted = []
    for p in preds:
        pct = p.probability * 100
        if lo <= pct < hi or (hi == 100 and pct == 100):
            shifted.append(p.model_copy(update={"probability": observed_realized}))
        else:
            shifted.append(p)
    return shifted


def _bucket_train_realized(train: List[Prediction], bucket: str) -> Optional[float]:
    lo = int(bucket.split("-")[0])
    hi = lo + 10
    items = [p for p in train
             if lo <= p.probability * 100 < hi or (hi == 100 and p.probability * 100 == 100)]
    if not items:
        return None
    return sum(_y(i) for i in items) / len(items)


def evaluate_calibration_candidate(
    candidate, resolved_preds: List[Prediction], learning_ledger, *,
    record: bool = True,
) -> Dict:
    """Walk-forward evaluate a calibration candidate. For each out-of-sample
    window: baseline (no shift) vs candidate (train-derived shift) on
    calibration_error / brier / hit_rate, recorded as a ledger Evaluation."""
    bucket = candidate.provenance.get("bucket")
    resolved = _resolved(resolved_preds)
    if bucket is None:
        return {"status": "NOT_APPLICABLE",
                "reason": "candidate carries no calibration bucket"}
    if len(resolved) < MIN_RESOLVED:
        return {"status": "INSUFFICIENT_EVIDENCE",
                "reason": f"{len(resolved)} resolved < {MIN_RESOLVED} required"}

    windows = walk_forward(resolved)
    if not windows:
        return {"status": "INSUFFICIENT_EVIDENCE",
                "reason": "not enough data for a walk-forward split"}

    per_window, recorded = [], []
    for i, (train, test) in enumerate(windows):
        train_realized = _bucket_train_realized(train, bucket)
        if train_realized is None:
            continue
        base = {"calibration_error": calibration_error(test),
                "brier": brier(test), "hit_rate": hit_rate(test)}
        shifted_test = apply_calibration_shift(
            test, bucket=bucket, observed_realized=train_realized)
        cand = {"calibration_error": calibration_error(shifted_test),
                "brier": brier(shifted_test), "hit_rate": hit_rate(shifted_test)}
        per_window.append({"window": i, "test_n": len(test),
                           "baseline": base, "candidate": cand})
        if record and len(test) >= MIN_TEST:
            ev = learning_ledger.evaluate(
                candidate.id, kind="rolling_backtest",
                candidate_metrics={k: v for k, v in cand.items() if v is not None},
                baseline_metrics={k: v for k, v in base.items() if v is not None},
                window={"split": i, "train_n": len(train), "test_n": len(test),
                        "out_of_sample": True},
                sample_size=len(test),
                actor_id="walk_forward_harness")
            recorded.append(ev.id)

    if not per_window:
        return {"status": "INSUFFICIENT_EVIDENCE",
                "reason": "no window had data in the target bucket"}
    return {"status": "EVALUATED", "bucket": bucket, "windows": per_window,
            "evaluation_ids": recorded}


def evaluate_candidate(candidate, resolved_preds: List[Prediction],
                       learning_ledger, *, record: bool = True) -> Dict:
    """Dispatch by candidate source/target. Only calibration candidates have
    a real walk-forward harness today; others are recorded honestly as
    INSUFFICIENT_EVIDENCE with the reason, never fake-scored."""
    if candidate.source == "calibration" or candidate.target == "confidence_mapping":
        return evaluate_calibration_candidate(candidate, resolved_preds,
                                              learning_ledger, record=record)
    return {"status": "INSUFFICIENT_EVIDENCE",
            "reason": f"no walk-forward harness for source={candidate.source!r} "
                      "yet; not scored on fabricated evidence"}


def weekly_evaluate(learning_ledger, resolved_preds: List[Prediction], *,
                    record: bool = True) -> Dict:
    """Evaluate every still-open candidate. Returns a per-candidate status."""
    results = {}
    for candidate in learning_ledger.list():
        if candidate.status not in ("proposed", "evaluated"):
            continue
        results[candidate.id] = evaluate_candidate(
            candidate, resolved_preds, learning_ledger, record=record)
    return results
