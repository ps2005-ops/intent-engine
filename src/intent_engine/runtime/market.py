"""Market runtime — the real daily paper-learning loop.

Composes the EXISTING primitives (prediction ledger, market resolution,
paper loop, learning ledger) into the loop the founder specified:

    daily prediction -> eligibility -> paper position
    due prediction   -> resolve -> close linked paper position -> metrics
    resolved evidence-> daily learning candidates

Everything is credential-INDEPENDENT by construction: the market-data
touchpoints (resolve a prediction, price an instrument) are injected. Real
runtime wires the real Tiingo/FRED fetchers; tests wire deterministic fakes.
No real-money path exists here.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, List, Optional, Union

from intent_engine.core import prediction_ledger as pl
from intent_engine.core.market_resolution import resolve_market_prediction
from intent_engine.events import CompanyEventBus
from intent_engine.learning import LearningLedger
from intent_engine.learning.records import SuccessCriterion
from intent_engine.paper.eligibility import (
    EligibilityConfig, EligibilityResult, evaluate_prediction,
)
from intent_engine.paper.rejections import RejectionStore
from intent_engine.paper.service import PaperTradingLoop
from intent_engine.runtime.redaction import redact_secrets

# Minimum resolved predictions in a confidence bucket before its calibration
# error is worth a candidate. One resolution is noise.
_MIN_BUCKET = 5
_MISCALIBRATION = 0.20      # |predicted_mid - realized| beyond this -> candidate


class MarketRuntime:
    def __init__(self, root: Union[str, Path] = "data", *,
                 bus: Optional[CompanyEventBus] = None,
                 ledger_path: Optional[Union[str, Path]] = None):
        self.root = Path(root)
        self.bus = bus
        self.ledger_path = Path(ledger_path) if ledger_path \
            else self.root / "prediction_ledger.db"
        self.paper = PaperTradingLoop(self.root / "paper_book.db", bus=bus)
        self.learning = LearningLedger(self.root / "learning_ledger.db", bus=bus)
        self.rejections = RejectionStore(self.root / "paper_rejections.jsonl")

    # --- prediction -> paper -------------------------------------------------
    def open_paper_from_predictions(
        self, *, as_of: str, price_at: Callable[[str, str], float],
        regime_for: Callable[[str], str] = lambda _as_of: "unknown",
        config: Optional[EligibilityConfig] = None,
    ) -> Dict:
        """Run eligibility over unresolved predictions; open eligible ones,
        persist rejections for the rest. Idempotent: an already-open
        prediction is skipped (duplicate_exposure), a re-run records no
        duplicate rejection."""
        config = config or EligibilityConfig()
        regime = regime_for(as_of)
        unresolved = pl.list_predictions(unresolved_only=True,
                                         path=self.ledger_path)
        open_positions = self.paper.store.open_positions()
        open_pred_ids = {p.prediction_id for p in open_positions}
        opened, rejected, errors = [], [], []
        for prediction in unresolved:
            # Already represented by an open position: skip silently — this is
            # idempotency, not a rejection worth logging every re-run.
            if prediction.id in open_pred_ids:
                continue
            result = evaluate_prediction(
                prediction, config=config, open_prediction_ids=open_pred_ids,
                open_position_count=len(open_positions), regime=regime,
                reasoning=prediction.claim_text, as_of=as_of)
            if not result.eligible:
                if self.rejections.record(result, as_of=as_of):
                    rejected.append({"prediction_id": result.prediction_id,
                                     "rule": result.rule,
                                     "reason": result.reason})
                continue
            # PER-ITEM ISOLATION: a single instrument's price gap (or any
            # per-prediction error) must not abort the whole daily open. The
            # failure is recorded (persistently, once/day) and the batch
            # continues; a re-run retries this prediction tomorrow.
            try:
                entry = price_at(result.intent.instrument, as_of)
                position = self.paper.open_from_intent(result.intent,
                                                       entry_price=entry)
            except Exception as exc:  # noqa: BLE001 - isolate, record, continue
                msg = redact_secrets(f"{type(exc).__name__}: {exc}")
                self.rejections.record(
                    EligibilityResult(False, prediction.id, reason=msg,
                                      rule="data_error"), as_of=as_of)
                errors.append({"prediction_id": prediction.id, "error": msg})
                continue
            open_pred_ids.add(prediction.id)
            open_positions.append(position)
            opened.append(position.id)
        return {"as_of": as_of, "regime": regime, "opened": opened,
                "rejected": rejected, "errors": errors,
                "considered": len(unresolved)}

    # --- resolve + link ------------------------------------------------------
    def resolve_and_link(
        self, *, as_of: str,
        resolver: Callable = resolve_market_prediction,
        price_at: Optional[Callable[[str, str], float]] = None,
    ) -> Dict:
        """Resolve due predictions with rules and publish prediction.resolved,
        then reconcile paper positions. PER-ITEM ISOLATION: one prediction's
        resolver error does not abort the others. Closing is delegated to the
        single self-healing reconcile path, so a close failure here is retried
        on the next run rather than stranding a position. Idempotent: only
        unresolved due predictions are resolved."""
        due = [p for p in pl.list_predictions(unresolved_only=True,
                                              due_by=as_of, path=self.ledger_path)
               if p.resolution_rule is not None]
        resolved, errors = [], []
        for prediction in due:
            try:
                result = resolver(prediction)
                pl.resolve_prediction(prediction.id, result.outcome,
                                      resolution_note=result.note,
                                      path=self.ledger_path)
                self._publish_resolved(prediction, result.outcome)
                resolved.append({"prediction_id": prediction.id,
                                 "outcome": result.outcome})
            except Exception as exc:  # noqa: BLE001 - isolate, record, continue
                errors.append({"prediction_id": prediction.id,
                               "error": redact_secrets(f"{type(exc).__name__}: {exc}")})
        recon = self.reconcile_positions(price_at=price_at)
        return {"as_of": as_of, "resolved": resolved, "errors": errors,
                "closed_positions": recon["closed"],
                "reconcile_errors": recon["errors"]}

    def reconcile_positions(
        self, *, price_at: Optional[Callable[[str, str], float]] = None,
    ) -> Dict:
        """The SINGLE close path — self-healing and idempotent. For every OPEN
        paper position whose linked prediction is resolved:
          - happened / did_not_happen -> close at the instrument price on the
            prediction's resolve_by (skipped, retried next run, if the price
            is unavailable — never stranded);
          - unresolvable -> VOID (flat close, excluded from scored metrics),
            because there is no market outcome to mark against.
        Running this daily guarantees no position stays stranded open after
        its prediction resolves, even if an earlier close attempt failed."""
        by_id = {p.id: p for p in pl.list_predictions(path=self.ledger_path)}
        closed, voided, errors = [], [], []
        for pos in self.paper.store.open_positions():
            prediction = by_id.get(pos.prediction_id)
            if prediction is None or prediction.outcome is None:
                continue                     # not yet resolved -> leave open
            if prediction.outcome == "unresolvable":
                self.paper.close_position(
                    pos.id, exit_price=pos.entry_price, exit_reason="voided",
                    regime_at_exit=pos.regime)
                voided.append(pos.id)
                continue
            if price_at is None:
                continue                     # cannot mark without a price feed
            try:
                exit_price = price_at(pos.instrument, prediction.resolve_by)
                self.paper.close_position(
                    pos.id, exit_price=exit_price,
                    exit_reason="prediction_resolved")
                closed.append(pos.id)
            except Exception as exc:  # noqa: BLE001 - isolate; retry next run
                errors.append({"position_id": pos.id,
                               "error": redact_secrets(f"{type(exc).__name__}: {exc}")})
        return {"closed": closed, "voided": voided, "errors": errors}

    # --- daily learning candidates ------------------------------------------
    def generate_daily_candidates(self) -> Dict:
        """Turn newly-resolved evidence into learning candidates. Two sources
        wired here: recurring paper-trade losses (paper loop) and confidence
        miscalibration (prediction ledger Brier buckets). Read-only w.r.t.
        production; proposes only."""
        paper_ids = self.paper.emit_learning_candidates(self.learning)
        calib_ids = self._calibration_candidates()
        return {"paper_candidates": paper_ids,
                "calibration_candidates": calib_ids}

    def _calibration_candidates(self) -> List[str]:
        summary = pl.brier_summary(path=self.ledger_path)
        open_buckets = {
            c.provenance.get("bucket")
            for c in self.learning.list(source="calibration")
            if c.status in ("proposed", "evaluated")}
        proposed = []
        for bucket, stats in summary.calibration_buckets.items():
            if stats.count < _MIN_BUCKET:
                continue
            lo = int(bucket.split("-")[0])
            predicted_mid = (lo + 5) / 100.0
            error = abs(predicted_mid - stats.realized_rate)
            if error <= _MISCALIBRATION or bucket in open_buckets:
                continue
            c = self.learning.propose(
                source="calibration", target="confidence_mapping",
                statement=(f"Confidence bucket {bucket} is miscalibrated: "
                           f"predicted ~{predicted_mid:.0%}, realized "
                           f"{stats.realized_rate:.0%} over {stats.count}"),
                hypothesis="the confidence map overstates this bucket",
                baseline_ref="prediction_ledger.current",
                success_criteria=[SuccessCriterion(
                    metric="calibration_error", comparator="<=",
                    threshold=_MISCALIBRATION, direction="lower_better")],
                param_diff={"bucket": bucket,
                            "observed_realized": stats.realized_rate},
                provenance={"bucket": bucket, "count": stats.count,
                            "realized_rate": stats.realized_rate},
                idempotency_key=f"calibration:{bucket}")
            proposed.append(c.id)
        return proposed

    def metrics(self):
        return self.paper.metrics()

    # --- internals -----------------------------------------------------------
    def _publish_resolved(self, prediction, outcome: str) -> None:
        if self.bus is None:
            return
        self.bus.publish(
            "prediction.resolved", subject_type="prediction",
            subject_id=prediction.id, producer="resolution_job",
            actor_type="system", actor_id="resolution_job", source="system",
            payload={"outcome": outcome, "source": prediction.source,
                     "instrument": prediction.instrument},
            prediction_id=prediction.id, decision_id=prediction.decision_id,
            idempotency_key=f"prediction_resolved:{prediction.id}")
