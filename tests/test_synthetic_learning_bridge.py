"""Synthetic Worlds -> Learning Ledger bridge (Phase 2).

The bridge turns a synthetic-world evaluation into READ-ONLY learning
candidates. It proposes; it never promotes and never touches the frozen
synthetic module or any production weight.
"""
from intent_engine.events import CompanyEventBus
from intent_engine.learning import LearningLedger
from intent_engine.learning.synthetic_bridge import (
    candidates_from_synthetic_eval, weaknesses,
)
from intent_engine.core.synthetic_worlds import generate_worlds, run_offline_eval


def _ledger(tmp_path):
    bus = CompanyEventBus(tmp_path / "events")
    return LearningLedger(tmp_path / "l.db", bus=bus), bus


def _blind_spot_results():
    # a mechanism the engine repeatedly fails, and one it always gets
    weak = [{"ground_truth": ("m_credit",), "identified": False,
             "world_type": "single"} for _ in range(4)]
    strong = [{"ground_truth": ("m_rates",), "identified": True,
               "world_type": "single"} for _ in range(4)]
    return weak + strong


def test_weaknesses_flags_blind_spots_only():
    ws = weaknesses(_blind_spot_results())
    assert [w["mechanism"] for w in ws] == ["m_credit"]
    assert ws[0]["identification_rate"] == 0.0


def test_weaknesses_ignores_low_sample():
    two = [{"ground_truth": ("m_x",), "identified": False,
            "world_type": "single"} for _ in range(2)]
    assert weaknesses(two) == []       # under _MIN_WORLDS


def test_bridge_proposes_candidates(tmp_path):
    led, bus = _ledger(tmp_path)
    ids = candidates_from_synthetic_eval(_blind_spot_results(), led,
                                         eval_id="e1")
    assert len(ids) == 1
    c = led.get(ids[0])
    assert c.source == "synthetic_world"
    assert c.status == "proposed"
    assert c.target == "mechanism:m_credit"
    assert c.success_criteria[0].metric == "identification_rate"
    assert "learning.candidate_proposed" in [e.event_type
                                             for e in bus.store.read_all()]


def test_bridge_is_idempotent_per_open_mechanism(tmp_path):
    led, _ = _ledger(tmp_path)
    candidates_from_synthetic_eval(_blind_spot_results(), led, eval_id="e1")
    assert candidates_from_synthetic_eval(_blind_spot_results(), led,
                                          eval_id="e2") == []


def test_clean_offline_eval_yields_no_false_positives(tmp_path):
    """The deterministic offline eval identifies by construction — the
    bridge must not fabricate weaknesses from a clean run."""
    led, _ = _ledger(tmp_path)
    results = run_offline_eval(generate_worlds())
    assert weaknesses(results) == []
    assert candidates_from_synthetic_eval(results, led) == []
