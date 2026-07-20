"""T014 bars: deterministic, versioned health + conversion signals.
Missing data yields UNKNOWN/UNAVAILABLE — never optimism, never a
probability."""
import pytest

from intent_engine.crm import (
    CONVERSION_RULE_VERSION, HEALTH_RULE_VERSION, CRMService,
)

NOW = "2026-07-20T12:00:00+00:00"


@pytest.fixture()
def crm(tmp_path):
    return CRMService(tmp_path / "crm.jsonl")


def _rec(crm, a, ev, occurred_at=None, payload=None):
    crm.record(a, ev, actor_type="human", actor_id="founder",
               occurred_at=occurred_at, payload=payload)


# --- health ------------------------------------------------------------------

def test_no_data_is_unknown_not_healthy(crm):
    a = crm.create_prospect(email="j@a.com")
    h = crm.get_health(a, now=NOW)
    assert h["category"] == "UNKNOWN"
    assert h["rule_version"] == HEALTH_RULE_VERSION
    assert any("not healthy" in r for r in h["reasons"])


def test_recent_positive_engagement_is_healthy_with_boundary(crm):
    a = crm.create_prospect(email="j@a.com")
    _rec(crm, a, "crm.replied", occurred_at="2026-06-20T12:00:00+00:00")
    assert crm.get_health(a, now=NOW)["category"] == "HEALTHY"   # exactly 30d
    b = crm.create_prospect(email="k@b.com")
    _rec(crm, b, "crm.replied", occurred_at="2026-06-19T11:00:00+00:00")
    assert crm.get_health(b, now=NOW)["category"] == "WATCH"     # 31d: stale


def test_unanswered_outreach_is_watch(crm):
    a = crm.create_prospect(email="j@a.com")
    _rec(crm, a, "crm.contacted", occurred_at="2026-07-15T12:00:00+00:00")
    h = crm.get_health(a, now=NOW)
    assert h["category"] == "WATCH"
    assert any("without a recorded reply" in r for r in h["reasons"])


def test_explicit_at_risk_dominates_recent_contact(crm):
    a = crm.create_prospect(email="j@a.com")
    for ev in ("crm.qualified", "crm.opportunity_opened", "crm.won",
               "crm.customer_activated", "crm.customer_at_risk"):
        _rec(crm, a, ev)
    _rec(crm, a, "crm.replied", occurred_at=NOW)
    h = crm.get_health(a, now=NOW)
    assert h["category"] == "AT_RISK"
    assert any("customer_at_risk" in r for r in h["reasons"])


def test_recovery_changes_signal_but_preserves_history(crm):
    a = crm.create_prospect(email="j@a.com")
    for ev in ("crm.qualified", "crm.opportunity_opened", "crm.won",
               "crm.customer_activated", "crm.customer_at_risk",
               "crm.customer_recovered"):
        _rec(crm, a, ev)
    _rec(crm, a, "crm.meeting_booked", occurred_at=NOW)
    assert crm.get_health(a, now=NOW)["category"] == "HEALTHY"
    types = [e.event_type for e in crm.get_history(a)]
    assert "crm.customer_at_risk" in types           # history intact


def test_churn_is_terminal_for_health(crm):
    a = crm.create_prospect(email="j@a.com")
    for ev in ("crm.qualified", "crm.opportunity_opened", "crm.won",
               "crm.customer_activated", "crm.churned"):
        _rec(crm, a, ev)
    h = crm.get_health(a, now=NOW)
    assert h["category"] == "AT_RISK"
    assert any("terminal" in r for r in h["reasons"])


# --- conversion --------------------------------------------------------------

def test_no_relevant_data_is_unavailable(crm):
    a = crm.create_prospect(email="j@a.com")
    c = crm.get_conversion_signal(a)
    assert c["category"] == "UNAVAILABLE"
    assert c["rule_version"] == CONVERSION_RULE_VERSION


def test_qualified_is_medium_meeting_is_high(crm):
    a = crm.create_prospect(email="j@a.com")
    _rec(crm, a, "crm.qualified")
    assert crm.get_conversion_signal(a)["category"] == "MEDIUM"
    _rec(crm, a, "crm.meeting_booked")
    assert crm.get_conversion_signal(a)["category"] == "HIGH"


def test_contacted_only_is_low(crm):
    a = crm.create_prospect(email="j@a.com")
    _rec(crm, a, "crm.contacted")
    assert crm.get_conversion_signal(a)["category"] == "LOW"


def test_disqualified_and_lost_dominate(crm):
    a = crm.create_prospect(email="j@a.com")
    _rec(crm, a, "crm.qualified")
    _rec(crm, a, "crm.meeting_booked")
    _rec(crm, a, "crm.lost")
    c = crm.get_conversion_signal(a)
    assert c["category"] == "LOW"
    assert any("terminal fact dominates" in r for r in c["reasons"])


def test_signals_carry_no_probability_or_accuracy_language(crm):
    import json
    a = crm.create_prospect(email="j@a.com")
    _rec(crm, a, "crm.qualified")
    blob = json.dumps([crm.get_health(a, now=NOW),
                       crm.get_conversion_signal(a)]).lower()
    for banned in ("%", "probability", "accura", "score", "predict"):
        assert banned not in blob
