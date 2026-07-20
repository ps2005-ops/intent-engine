"""T015 bars: decision lifecycle metrics — event-derived, superseded
visible, stalled rule versioned and boundary-tested."""
import pytest

from intent_engine.analytics import AnalyticsService
from intent_engine.core.decision_record import DecisionService

AS_OF = "2026-07-20T12:00:00+00:00"


@pytest.fixture()
def svc(tmp_path):
    return DecisionService(str(tmp_path / "decisions.db"))


def _advance(svc, did, *events, occurred_at=None):
    for ev in events:
        svc.record_event(did, ev, actor_type="human", actor_id="founder",
                         source="cli", occurred_at=occurred_at)


def _metrics(svc, window="all", as_of=AS_OF):
    return AnalyticsService(decision_service=svc).decision_metrics(window,
                                                                   as_of)


def test_lifecycle_counts_from_events(svc):
    a = svc.create_decision("founder", occurred_at="2026-07-01T00:00:00+00:00")
    _advance(svc, a.decision_id, "RecommendationIssued", "DecisionSubmitted",
             "DecisionApproved", occurred_at="2026-07-02T00:00:00+00:00")
    b = svc.create_decision("founder", occurred_at="2026-07-03T00:00:00+00:00")
    _advance(svc, b.decision_id, "DecisionSubmitted", "DecisionDeclined",
             occurred_at="2026-07-04T00:00:00+00:00")
    m = _metrics(svc)
    assert m["decisions_created"].value == 2
    assert m["recommendations_issued"].value == 1
    assert m["decisions_approved"].value == 1
    assert m["decisions_declined"].value == 1
    assert m["decisions_created"].metric_version == "decision_metrics.v1"
    assert m["decisions_created"].provenance["contributors"][
        "total_contributing"] == 2


def test_superseded_decisions_remain_visible(svc):
    old = svc.create_decision("founder")
    new = svc.create_decision("founder")
    svc.supersede_decision(old.decision_id, new.decision_id)
    m = _metrics(svc, as_of="2026-12-31T00:00:00+00:00")
    assert m["decisions_superseded"].value == 1
    dist = m["decision_stage_distribution"].value
    assert dist.get("superseded") == 1 and dist.get("draft") == 1


def test_event_derived_durations_use_occurred_at(svc):
    a = svc.create_decision("founder", occurred_at="2026-07-01T00:00:00+00:00")
    svc.record_event(a.decision_id, "RecommendationIssued",
                     actor_type="system", actor_id="pipe", source="system",
                     occurred_at="2026-07-03T00:00:00+00:00")
    m = _metrics(svc)
    assert m["median_days_to_recommendation"].value == 2.0


def test_no_completed_pairs_is_unavailable_not_zero(svc):
    svc.create_decision("founder")
    m = _metrics(svc)
    assert m["median_days_to_resolution"].status == "UNAVAILABLE"
    assert m["median_days_to_resolution"].value is None


def test_stalled_rule_boundary(svc):
    fresh = svc.create_decision("founder",
                                occurred_at="2026-07-10T00:00:00+00:00")
    stale = svc.create_decision("founder",
                                occurred_at="2026-07-01T00:00:00+00:00")
    m = _metrics(svc, as_of="2026-07-20T00:00:00+00:00")
    # fresh: 10 days old (< 14) not stalled; stale: 19 days -> stalled
    assert m["stalled_decisions"].value == 1
    assert "stalled.v1" in m["stalled_decisions"].annotations[0]
    ids = m["stalled_decisions"].provenance["contributors"]["sample_ids"]
    assert stale.decision_id in ids and fresh.decision_id not in ids
    # exactly 14 days: NOT stalled (rule says strictly greater)
    m2 = _metrics(svc, as_of="2026-07-15T00:00:00+00:00")
    assert m2["stalled_decisions"].value == 0


def test_custom_window_filters_counts(svc):
    svc.create_decision("founder", occurred_at="2026-06-01T00:00:00+00:00")
    svc.create_decision("founder", occurred_at="2026-07-15T00:00:00+00:00")
    m = _metrics(svc, window="7d", as_of=AS_OF)
    assert m["decisions_created"].value == 1          # only the July one
    m_all = _metrics(svc, window="all")
    assert m_all["decisions_created"].value == 2


def test_terminal_decision_not_stalled(svc):
    a = svc.create_decision("founder", occurred_at="2026-06-01T00:00:00+00:00")
    _advance(svc, a.decision_id, "DecisionSubmitted", "DecisionDeclined",
             occurred_at="2026-06-02T00:00:00+00:00")
    m = _metrics(svc, as_of=AS_OF)
    assert m["stalled_decisions"].value == 0          # declined != stalled
