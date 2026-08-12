"""The learning watchdog: it must fire on real trouble and stay quiet on calm.

The negative controls are the harder half and are written first in spirit: a
watchdog that alerts during a healthy quiet week gets muted by its operator
within days, after which it detects nothing at all. Every "does not alert"
test below corresponds to a state this system genuinely reaches.
"""
import pytest

from intent_engine.market import learning_status as LS
from intent_engine.market import learning_watchdog as W


def status(**over):
    """A healthy canonical picture, overridable per test."""
    base = {
        "window": "7d",
        "system_of_record": {"id": "market_intelligence_learning_engine",
                             "ledger": "/root/reports/market/"
                                       "learning_ledger.jsonl",
                             "ledger_exists": True, "runtime_sha": "abc123"},
        "cycles": {"recorded": 10, "completed": 9,
                   "last": "2026-08-12T10:47:12+00:00",
                   "last_status": "COMPLETED"},
        "ledger_rows": {"all_time": 4960, "in_window": 900, "undated": 0},
        "channels": {
            "evidence": {"status": LS.RUNNING, "in_window": 40,
                         "all_time": 700, "by_record": {}, "reason": ""},
            "active_learning": {"status": LS.RUNNING, "in_window": 5,
                                "all_time": 40, "by_record": {},
                                "reason": ""},
        },
        "knowledge": {"effects_in_window": 100, "changed_something": 30,
                      "changed_nothing": 70, "by_effect_type": {},
                      "changing_share": 0.30},
        "active_learning": {"zero_result_captured": True,
                            "outcomes_all_time": {"SUCCESS": 38,
                                                  "NO_RESULT": 1},
                            "acquisition_counter_integrity": {
                                "state": "CONSISTENT"}},
        "undated_record_types": {},
        "legacy_pipelines": [{"id": "daily_market_predictions",
                              "scheduled": False}],
    }
    base.update(over)
    return base


def ids(report):
    return {a["alert_id"] for a in report["alerts"]}


NOW = __import__("datetime").datetime(2026, 8, 12, 20, 0,
                                      tzinfo=__import__("datetime").timezone.utc)


# --- it fires on real trouble ------------------------------------------------
def test_a_missing_ledger_is_critical_and_stops_downstream_verdicts():
    """Every number below an absent store would be a zero produced by absence."""
    sor = dict(status()["system_of_record"], ledger_exists=False)
    report = W.evaluate(status=status(system_of_record=sor), now=NOW)
    assert W.WRONG_DATA_ROOT in ids(report)
    assert report["status"] == W.CRITICAL
    # It must NOT go on to report learning verdicts from an absent ledger.
    assert report["silence"]["state"] == W.SUBSYSTEM_NOT_RUNNING


def test_a_stale_cycle_is_critical():
    report = W.evaluate(status=status(
        cycles={"recorded": 1, "completed": 1, "last_status": "COMPLETED",
                "last": "2026-08-01T00:00:00+00:00"}), now=NOW)
    assert W.NO_NEW_CYCLE in ids(report)


def test_a_failed_cycle_is_critical():
    report = W.evaluate(status=status(
        cycles={"recorded": 1, "completed": 0, "last_status": "FAILED",
                "last": "2026-08-12T10:00:00+00:00"}), now=NOW)
    assert W.CYCLE_FAILED in ids(report)


def test_busy_and_not_learning_is_flagged_with_the_share():
    report = W.evaluate(status=status(
        knowledge={"effects_in_window": 500, "changed_something": 2,
                   "changed_nothing": 498, "by_effect_type": {},
                   "changing_share": 0.004}), now=NOW)
    assert W.HIGH_ACTIVITY_LOW_LEARNING in ids(report)


def test_a_success_only_policy_dataset_is_flagged():
    report = W.evaluate(status=status(
        active_learning={"zero_result_captured": False,
                         "outcomes_all_time": {"SUCCESS": 40},
                         "acquisition_counter_integrity": {
                             "state": "CONSISTENT"}}), now=NOW)
    assert W.RL_DATA_NOT_ACCUMULATING in ids(report)


def test_a_scheduled_legacy_pipeline_is_critical():
    """The incident, as a standing check."""
    report = W.evaluate(status=status(
        legacy_pipelines=[{"id": "daily_market_predictions",
                           "scheduled": True}]), now=NOW)
    assert W.LEGACY_PIPELINE_ACTIVE_AS_CANONICAL in ids(report)
    assert report["status"] == W.CRITICAL


def test_a_channel_that_never_ran_is_critical():
    report = W.evaluate(status=status(channels={
        "evidence": {"status": LS.RUNNING, "in_window": 5, "all_time": 5,
                     "by_record": {}, "reason": ""},
        "active_learning": {"status": LS.NO_PRODUCER, "in_window": 0,
                            "all_time": 0, "by_record": {}, "reason": ""},
    }), now=NOW)
    assert W.PROSPECTIVE_RL_NOT_RUNNING in ids(report)


# --- §7 NEGATIVE CONTROLS: it must stay quiet -------------------------------
def test_a_calm_week_with_a_completed_cycle_raises_nothing():
    """The single most important negative control.

    If this ever fails, the watchdog will be muted and will then detect
    nothing at all.
    """
    report = W.evaluate(status=status(), now=NOW)
    assert report["alerts"] == []
    assert report["status"] == "OK"


def test_no_new_evidence_after_a_normal_cycle_is_not_an_outage():
    """Quiet world, healthy system — NOTHING_NEW_IN_WORLD, no alert."""
    report = W.evaluate(status=status(
        channels={"evidence": {"status": LS.RAN_NO_CHANGE, "in_window": 0,
                               "all_time": 700, "by_record": {},
                               "reason": ""},
                  "active_learning": {"status": LS.RUNNING, "in_window": 0,
                                      "all_time": 40, "by_record": {},
                                      "reason": ""}},
        knowledge={"effects_in_window": 0, "changed_something": 0,
                   "changed_nothing": 0, "by_effect_type": {},
                   "changing_share": None}), now=NOW)
    assert report["silence"]["state"] == W.NOTHING_NEW_IN_WORLD
    assert W.KNOWLEDGE_EFFECT_ZERO not in ids(report)
    assert report["status"] == "OK"


def test_beliefs_unchanged_after_genuine_re_observation_is_not_an_alert():
    """Most evidence SHOULD change nothing. A low count is not a low share."""
    report = W.evaluate(status=status(
        knowledge={"effects_in_window": 12, "changed_something": 0,
                   "changed_nothing": 12, "by_effect_type": {},
                   "changing_share": 0.0}), now=NOW)
    # Below the denominator floor, no verdict is issued at all.
    assert W.HIGH_ACTIVITY_LOW_LEARNING not in ids(report)
    assert report["silence"]["state"] == W.EVIDENCE_FOUND_NO_LEARNING


def test_rl_blocked_data_while_collection_runs_is_not_an_alert():
    """Statistical immaturity is not a fault, so long as data accumulates."""
    report = W.evaluate(status=status(
        active_learning={"zero_result_captured": True,
                         "outcomes_all_time": {"SUCCESS": 3, "FAILED": 1},
                         "acquisition_counter_integrity": {
                             "state": "CONSISTENT"}}), now=NOW)
    assert W.RL_DATA_NOT_ACCUMULATING not in ids(report)
    assert report["status"] == "OK"


def test_an_exhausted_llm_provider_does_not_make_the_engine_look_dead():
    """Deterministic learning continues; the watchdog must reflect that.

    This is the shape of the real environment: Anthropic credits exhausted,
    every deterministic channel running. Reporting CRITICAL here would be the
    incident in a new costume.
    """
    report = W.evaluate(status=status(), now=NOW)
    assert report["status"] == "OK"
    assert report["silence"]["state"] == W.LEARNING_OCCURRED


def test_a_fresh_founder_export_is_not_stale():
    report = W.evaluate(status=status(),
                        founder_last_write="2026-08-11T00:00:00+00:00",
                        now=NOW)
    assert W.FOUNDER_CONSUMPTION_STALE not in ids(report)


def test_a_genuinely_stale_founder_export_is_flagged():
    report = W.evaluate(status=status(),
                        founder_last_write="2026-07-01T00:00:00+00:00",
                        now=NOW)
    assert W.FOUNDER_CONSUMPTION_STALE in ids(report)


# --- alert shape -------------------------------------------------------------
@pytest.mark.parametrize("field", [
    "alert_id", "severity", "subsystem", "observed", "expected",
    "suggested_next_action", "first_seen", "last_seen", "runtime_sha",
    "data_root", "evidence"])
def test_every_alert_carries_every_required_field(field):
    """No natural-language-only alerts: an alert that cannot be diffed
    between two runs cannot be tracked to resolution."""
    report = W.evaluate(status=status(
        cycles={"recorded": 1, "completed": 0, "last_status": "FAILED",
                "last": "2026-08-01T00:00:00+00:00"}), now=NOW)
    assert report["alerts"]
    for alert in report["alerts"]:
        assert field in alert


def test_every_severity_and_silence_state_is_closed():
    report = W.evaluate(status=status(), now=NOW)
    assert report["silence"]["state"] in W.SILENCE_STATES
    for alert in report["alerts"]:
        assert alert["severity"] in W.SEVERITIES
