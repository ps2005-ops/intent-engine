"""Real walk-forward candidate evaluation (1G) + promotion gating (1H)."""
from datetime import date, timedelta

from intent_engine.core import prediction_ledger as pl
from intent_engine.events import CompanyEventBus
from intent_engine.learning import LearningLedger, LearningError
from intent_engine.learning.evaluation import (
    MIN_RESOLVED, evaluate_candidate, walk_forward, weekly_evaluate,
)


def _resolved_set(tmp_path, n, *, prob, hit_rate):
    """n resolved predictions all in one confidence bucket; a fraction
    `hit_rate` actually happened."""
    path = tmp_path / "led.db"
    base = date(2026, 1, 1)
    preds = []
    for i in range(n):
        p = pl.record_prediction(
            source="market", entity_id="e", claim_text=f"c{i}", probability=prob,
            resolve_by=(base + timedelta(days=i)).isoformat(), path=path,
            instrument="SPY", direction="up", horizon_days=1)
        outcome = "happened" if i < int(n * hit_rate) else "did_not_happen"
        pl.resolve_prediction(p.id, outcome, path=path)
        preds.append(p)
    return [p for p in pl.list_predictions(path=path)
            if p.outcome in ("happened", "did_not_happen")]


def _ledger(tmp_path):
    bus = CompanyEventBus(tmp_path / "events")
    return LearningLedger(tmp_path / "learning.db", bus=bus)


def _calib_candidate(led):
    # overconfident 0.9 bucket: predicted 90%, realized ~50%
    return led.propose(
        source="calibration", target="confidence_mapping",
        statement="0.9 bucket overconfident", hypothesis="overconfident",
        baseline_ref="v1",
        success_criteria=[{"metric": "calibration_error", "comparator": "<=",
                           "threshold": 0.2, "direction": "lower_better"}],
        provenance={"bucket": "90-100"})


def test_walk_forward_produces_out_of_sample_windows(tmp_path):
    preds = _resolved_set(tmp_path, 30, prob=0.9, hit_rate=0.5)
    windows = walk_forward(preds)
    assert len(windows) >= 2
    # every test block comes after its train prefix (no leakage)
    for train, test in windows:
        assert train and test
        assert max(p.resolved_at for p in train) <= min(p.resolved_at for p in test)


def test_insufficient_evidence_blocks(tmp_path):
    preds = _resolved_set(tmp_path, 8, prob=0.9, hit_rate=0.5)   # < MIN_RESOLVED
    led = _ledger(tmp_path)
    c = _calib_candidate(led)
    res = evaluate_candidate(c, preds, led)
    assert res["status"] == "INSUFFICIENT_EVIDENCE"
    assert len(preds) < MIN_RESOLVED


def test_evaluation_records_candidate_vs_baseline(tmp_path):
    preds = _resolved_set(tmp_path, 40, prob=0.9, hit_rate=0.5)
    led = _ledger(tmp_path)
    c = _calib_candidate(led)
    res = evaluate_candidate(c, preds, led)
    assert res["status"] == "EVALUATED"
    # recalibrating a 90%-predicted / 50%-realized bucket lowers calib error
    w = res["windows"][0]
    assert w["candidate"]["calibration_error"] <= w["baseline"]["calibration_error"]
    assert led.evaluations_for(c.id)          # persisted


def test_non_calibration_candidate_not_fake_scored(tmp_path):
    preds = _resolved_set(tmp_path, 40, prob=0.9, hit_rate=0.5)
    led = _ledger(tmp_path)
    c = led.propose(source="paper_trade", target="regime:x", statement="s",
                    hypothesis="h", baseline_ref="b",
                    success_criteria=[{"metric": "win_rate", "comparator": ">=",
                                       "threshold": 0.5}])
    res = evaluate_candidate(c, preds, led)
    assert res["status"] == "INSUFFICIENT_EVIDENCE"
    assert "no walk-forward harness" in res["reason"]


def test_promotion_still_requires_human_and_evidence(tmp_path):
    preds = _resolved_set(tmp_path, 40, prob=0.9, hit_rate=0.5)
    led = _ledger(tmp_path)
    c = _calib_candidate(led)
    evaluate_candidate(c, preds, led)          # records evaluations
    # an agent may never promote, even with evidence
    try:
        led.promote(c.id, actor_type="agent", actor_id="bot", rationale="x")
        assert False, "agent promotion must raise"
    except LearningError as e:
        assert "HUMAN wall" in str(e)


def test_weekly_evaluate_covers_open_candidates(tmp_path):
    preds = _resolved_set(tmp_path, 40, prob=0.9, hit_rate=0.5)
    led = _ledger(tmp_path)
    _calib_candidate(led)
    results = weekly_evaluate(led, preds)
    assert any(r["status"] == "EVALUATED" for r in results.values())
