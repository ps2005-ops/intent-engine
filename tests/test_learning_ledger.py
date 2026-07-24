"""Learning & Promotion Ledger — the candidate lifecycle and its two walls.

Cadence: propose (daily) -> evaluate (weekly) -> promote/reject (monthly).
The walls under test: promotion requires a HUMAN actor AND the predefined
criteria met consistently across evaluations; nothing here mutates
production.
"""
import pytest

from intent_engine.events import CompanyEventBus
from intent_engine.learning import (
    LearningLedger, LearningError, SuccessCriterion,
)
from intent_engine.learning.records import beats_baseline, clears


def _ledger(tmp_path):
    bus = CompanyEventBus(tmp_path / "events")
    return LearningLedger(tmp_path / "learning.db", bus=bus), bus


def _propose(led, **over):
    kw = dict(
        source="calibration", target="confidence_mapping",
        statement="shrink the 70-80% bucket", hypothesis="overconfident there",
        baseline_ref="prod.v1",
        success_criteria=[{"metric": "brier", "comparator": "<=",
                           "threshold": 0.2, "direction": "lower_better"}])
    kw.update(over)
    return led.propose(**kw)


def _two_good_evals(led, cid):
    led.evaluate(cid, kind="rolling_backtest",
                 candidate_metrics={"brier": 0.15},
                 baseline_metrics={"brier": 0.25}, sample_size=40)
    led.evaluate(cid, kind="synthetic_scenario",
                 candidate_metrics={"brier": 0.18},
                 baseline_metrics={"brier": 0.24}, sample_size=30)


# --- pure math ---------------------------------------------------------------

def test_clears_and_beats_directionality():
    lower = SuccessCriterion(metric="brier", comparator="<=", threshold=0.2,
                             direction="lower_better")
    higher = SuccessCriterion(metric="sharpe", comparator=">=", threshold=1.0,
                              direction="higher_better")
    assert clears(lower, 0.15) and not clears(lower, 0.25)
    assert beats_baseline(lower, 0.15, 0.25)        # lower is better
    assert not beats_baseline(lower, 0.30, 0.25)
    assert beats_baseline(higher, 1.5, 1.2)         # higher is better


# --- lifecycle ---------------------------------------------------------------

def test_propose_records_and_publishes(tmp_path):
    led, bus = _ledger(tmp_path)
    c = _propose(led)
    assert c.status == "proposed"
    assert led.get(c.id).status == "proposed"
    types = [e.event_type for e in bus.store.read_all()]
    assert types == ["learning.candidate_proposed"]


def test_candidate_without_criteria_is_never_promotable(tmp_path):
    led, _ = _ledger(tmp_path)
    with pytest.raises(LearningError, match="success_criteria"):
        _propose(led, success_criteria=[])


def test_evaluate_advances_status_and_sets_verdict(tmp_path):
    led, bus = _ledger(tmp_path)
    c = _propose(led)
    ev = led.evaluate(c.id, kind="rolling_backtest",
                      candidate_metrics={"brier": 0.15},
                      baseline_metrics={"brier": 0.25}, sample_size=40)
    assert ev.verdict == "outperforms"
    assert led.get(c.id).status == "evaluated"
    assert "learning.candidate_evaluated" in [e.event_type
                                              for e in bus.store.read_all()]


def test_underperforming_evaluation_verdict(tmp_path):
    led, _ = _ledger(tmp_path)
    c = _propose(led)
    ev = led.evaluate(c.id, kind="rolling_backtest",
                      candidate_metrics={"brier": 0.40},   # worse than bar
                      baseline_metrics={"brier": 0.25}, sample_size=40)
    assert ev.verdict == "underperforms"


# --- the promotion wall ------------------------------------------------------

def test_agent_cannot_promote(tmp_path):
    led, _ = _ledger(tmp_path)
    c = _propose(led)
    _two_good_evals(led, c.id)
    with pytest.raises(LearningError, match="HUMAN wall"):
        led.promote(c.id, actor_type="agent", actor_id="bot", rationale="no")


def test_promotion_needs_enough_evidence(tmp_path):
    led, _ = _ledger(tmp_path)
    c = _propose(led)
    led.evaluate(c.id, kind="rolling_backtest",
                 candidate_metrics={"brier": 0.15},
                 baseline_metrics={"brier": 0.25}, sample_size=40)
    with pytest.raises(LearningError, match="not promotable"):
        led.promote(c.id, actor_type="human", actor_id="founder",
                    rationale="too early")


def test_promotion_needs_criteria_met_consistently(tmp_path):
    led, _ = _ledger(tmp_path)
    c = _propose(led)
    # one good, one that misses the bar -> not consistent
    led.evaluate(c.id, kind="rolling_backtest",
                 candidate_metrics={"brier": 0.15},
                 baseline_metrics={"brier": 0.25}, sample_size=40)
    led.evaluate(c.id, kind="synthetic_scenario",
                 candidate_metrics={"brier": 0.30},   # misses <=0.2
                 baseline_metrics={"brier": 0.25}, sample_size=30)
    readiness = led.evaluate_promotion_readiness(c.id)
    assert readiness["ready"] is False
    with pytest.raises(LearningError, match="not promotable"):
        led.promote(c.id, actor_type="human", actor_id="founder",
                    rationale="mixed")


def test_human_promotes_when_ready_and_publishes(tmp_path):
    led, bus = _ledger(tmp_path)
    c = _propose(led)
    _two_good_evals(led, c.id)
    assert led.evaluate_promotion_readiness(c.id)["ready"] is True
    dec = led.promote(c.id, actor_type="human", actor_id="founder",
                      rationale="beats baseline on both evaluations")
    assert dec.decision == "promoted"
    assert led.get(c.id).status == "promoted"
    assert dec.criteria_audit == {"brier": True}
    # the promotion event exists and was emitted by a human (bus wall)
    promoted = [e for e in bus.store.read_all()
                if e.event_type == "learning.candidate_promoted"]
    assert len(promoted) == 1 and promoted[0].actor_type == "human"


def test_reject_records_terminal_status(tmp_path):
    led, bus = _ledger(tmp_path)
    c = _propose(led)
    led.reject(c.id, rationale="superseded")
    assert led.get(c.id).status == "rejected"
    assert "learning.candidate_rejected" in [e.event_type
                                             for e in bus.store.read_all()]


def test_cannot_evaluate_after_terminal(tmp_path):
    led, _ = _ledger(tmp_path)
    c = _propose(led)
    led.reject(c.id, rationale="no")
    with pytest.raises(LearningError, match="already"):
        led.evaluate(c.id, kind="rolling_backtest",
                     candidate_metrics={"brier": 0.1},
                     baseline_metrics={"brier": 0.2})


def test_ledger_is_append_only_no_mutation_surface():
    from intent_engine.learning.ledger import LearningStore
    banned = [m for m in dir(LearningStore)
              if any(w in m.lower() for w in ("update", "delete", "remove"))
              and not m.startswith("_")]
    assert banned == []


def test_no_bus_is_tolerated(tmp_path):
    """The ledger works without an event bus (offline capability preserved)."""
    led = LearningLedger(tmp_path / "l.db")     # no bus
    c = _propose(led)
    _two_good_evals(led, c.id)
    dec = led.promote(c.id, actor_type="human", actor_id="founder",
                      rationale="ok")
    assert dec.decision == "promoted"
