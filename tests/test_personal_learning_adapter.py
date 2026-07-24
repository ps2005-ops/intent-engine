"""Personal AI observes and explains the learning platform — read-only.

The workspace can inspect the candidate pipeline and paper book and expand
any candidate into the Finding->Evidence->Confidence->Reasoning->Source->
Replay chain. It writes nothing into the learning ledger or paper book.
"""
from intent_engine.events import CompanyEventBus
from intent_engine.learning import LearningLedger
from intent_engine.learning.inspection import PlatformLearningReader
from intent_engine.paper import PaperTradingLoop
from intent_engine.personal.service import PersonalService


def _platform(tmp_path):
    bus = CompanyEventBus(tmp_path / "events")
    led = LearningLedger(tmp_path / "l.db", bus=bus)
    loop = PaperTradingLoop(tmp_path / "p.db", bus=bus)
    reader = PlatformLearningReader(led, loop)
    ps = PersonalService(tmp_path / "personal.jsonl", learning_reader=reader)
    return led, loop, ps


def _seed_candidate(led):
    c = led.propose(source="calibration", target="conf",
                    statement="shrink the 70-80% bucket",
                    hypothesis="overconfident there", baseline_ref="v1",
                    success_criteria=[{"metric": "brier", "comparator": "<=",
                                       "threshold": 0.2,
                                       "direction": "lower_better"}])
    led.evaluate(c.id, kind="rolling_backtest",
                 candidate_metrics={"brier": 0.15},
                 baseline_metrics={"brier": 0.25}, sample_size=30)
    return c


def test_inspect_learning_reports_pipeline_and_candidates(tmp_path):
    led, _, ps = _platform(tmp_path)
    c = _seed_candidate(led)
    insp = ps.inspect_learning(as_of="2026-07-24")
    assert insp["pipeline"] == {"evaluated": 1}
    assert any(c.id in ref["artifact_id"]
               for cand in insp["candidates"] for ref in cand["source_refs"])


def test_inspect_learning_reports_paper_book(tmp_path):
    led, loop, ps = _platform(tmp_path)
    p = loop.open_position(prediction_id="pr-1", instrument="SPY",
                           direction="long", entry_price=100, regime="risk_on",
                           confidence=0.9, reasoning="x")
    loop.close_position(p.id, exit_price=110, exit_reason="target")
    insp = ps.inspect_learning(as_of="2026-07-24")
    assert "paper book" in insp["paper_book"]["text"]
    assert insp["paper_book"]["availability"] == "SUPPORTED"


def test_empty_platform_is_honest_not_fabricated(tmp_path):
    _, _, ps = _platform(tmp_path)
    insp = ps.inspect_learning(as_of="2026-07-24")
    assert insp["pipeline"] == {}
    # honest UNAVAILABLE, not an invented candidate
    assert insp["candidates"][0]["availability"] == "UNAVAILABLE"
    assert insp["paper_book"]["availability"] == "UNAVAILABLE"


def test_explain_candidate_chain(tmp_path):
    led, _, ps = _platform(tmp_path)
    c = _seed_candidate(led)
    ex = ps.explain_candidate(c.id, as_of="2026-07-24")
    assert ex["available"] is True
    for key in ("finding", "evidence", "confidence", "reasoning",
                "source_agent", "replay_id"):
        assert key in ex
    assert ex["source_agent"] == "calibration"
    assert len(ex["evidence"]) == 1
    assert ex["replay_id"].startswith("learning:")


def test_personal_service_has_no_learning_write_surface(tmp_path):
    """The workspace observes and explains; it may not propose, evaluate,
    promote, or trade. No such method exists on the service."""
    led, _, ps = _platform(tmp_path)
    forbidden = ("propose", "evaluate", "promote", "reject", "open_position",
                 "close_position")
    for name in forbidden:
        assert not hasattr(ps, name), f"workspace must not expose {name}"
