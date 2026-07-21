"""T018 bars: stopping rules, peeking, result labels, founder overrides,
review, and the language wall."""
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

from intent_engine.growth import GrowthError, GrowthService


def _load_sibling(name):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).resolve().parent / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_reg = _load_sibling("test_growth_registration")
register, ARMS = _reg.register, _reg.ARMS

ONE_ARM = [{"arm_id": "single", "is_control": False, "allocation": 1.0}]


@pytest.fixture()
def svc(tmp_path):
    return GrowthService(tmp_path)


def _run(svc, *, arms=ARMS, minimum=20):
    eid = register(svc, arms=arms, minimum=minimum)
    svc.start_experiment(eid, actor_id="founder")
    return eid


def _populate(svc, eid, *, per_arm, control_successes, treatment_successes,
              prefix="e"):
    """Deterministically fill both arms to `per_arm` observations.

    `prefix` gives each batch distinct entities: an entity's outcome for a
    given metric and window is ONE immutable fact, so a second batch must
    use new entities rather than restating old ones."""
    filled = {"control": 0, "treatment": 0}
    successes = {"control": control_successes,
                 "treatment": treatment_successes}
    i = 0
    while any(v < per_arm for v in filled.values()):
        entity = f"{prefix}{i}"
        i += 1
        svc.assign_entity(eid, entity)
        arm = svc.get_state(eid).assignments[entity]
        if filled[arm] >= per_arm:
            continue
        svc.record_exposure(eid, entity, exposure_key="send-1")
        outcome = filled[arm] < successes[arm]
        svc.record_observation(eid, entity, metric_name="reply_rate",
                               outcome_value=outcome, source="crm",
                               window_start="2026-08-01",
                               window_end="2026-08-14")
        filled[arm] += 1
    return filled


# --- labels -------------------------------------------------------------------

def test_not_started_and_running_labels(svc):
    eid = register(svc)
    assert svc.get_result(eid)["label"] == "NOT_STARTED"
    svc.start_experiment(eid, actor_id="founder")
    assert svc.get_result(eid)["label"] == "TOO FEW OBSERVATIONS"


def test_below_minimum_is_too_few_observations(svc):
    eid = _run(svc, minimum=20)
    _populate(svc, eid, per_arm=3, control_successes=1, treatment_successes=2)
    result = svc.get_result(eid)
    assert result["label"] == "TOO FEW OBSERVATIONS"
    assert "NO CAUSAL CLAIM" in result["modifiers"]
    assert result["statistic"]["status"] == "UNAVAILABLE"
    assert "below the pre-registered minimum" in result["statistic"]["reason"]


def test_no_control_arm_is_permanently_observational(svc):
    eid = _run(svc, arms=ONE_ARM, minimum=2)
    for i in range(24):
        entity = f"e{i}"
        svc.assign_entity(eid, entity)
        svc.record_exposure(eid, entity, exposure_key="s")
        svc.record_observation(eid, entity, metric_name="reply_rate",
                               outcome_value=(i % 2 == 0), source="crm",
                               window_start="2026-08-01",
                               window_end="2026-08-14")
    result = svc.get_result(eid)
    assert result["label"] == "OBSERVATIONAL ONLY"
    assert "NO CAUSAL CLAIM" in result["modifiers"]
    assert "regardless of sample size" in " ".join(result["reasons"])
    assert result["statistic"]["status"] == "UNAVAILABLE"


def test_similar_arms_are_inconclusive(svc):
    eid = _run(svc, minimum=20)
    _populate(svc, eid, per_arm=40, control_successes=13,
              treatment_successes=14)
    result = svc.get_result(eid)
    assert result["label"] == "INCONCLUSIVE"
    assert "not distinguishable" in " ".join(result["reasons"])


def test_distinguishable_arms_are_difference_observed_not_a_win(svc):
    eid = _run(svc, minimum=20)
    _populate(svc, eid, per_arm=45, control_successes=9,
              treatment_successes=27)
    result = svc.get_result(eid)
    assert result["label"] == "DIFFERENCE OBSERVED"
    assert "REVIEW REQUIRED" in result["modifiers"]
    assert "not a conclusion" in " ".join(result["reasons"])
    assert result["human_reviewed"] is False


def test_guardrail_breach_dominates(svc):
    eid = _run(svc, minimum=2)
    _populate(svc, eid, per_arm=20, control_successes=4,
              treatment_successes=15)
    svc.record_guardrail_breach(eid, "unsubscribe_rate",
                                "rose from 0.4% to 2.1%")
    result = svc.get_result(eid)
    assert result["label"] == "GUARDRAIL BREACHED"
    assert "REVIEW REQUIRED" in result["modifiers"]


# --- stopping and peeking -----------------------------------------------------

def test_satisfying_a_stopping_rule_does_not_stop_anything(svc):
    eid = _run(svc, minimum=20)
    _populate(svc, eid, per_arm=22, control_successes=8,
              treatment_successes=9)
    outcome = svc.evaluate_stopping_rules(eid, as_of="2026-08-20T00:00:00+00:00")
    assert outcome["satisfied"] is True
    assert "remains an explicit human action" in outcome["note"]
    state = svc.get_state(eid)
    assert state.stop_rule_satisfied is True
    assert state.stopped is False               # nothing stopped itself


def test_stopping_is_human_only(svc):
    eid = _run(svc)
    for actor in ("system", "agent"):
        with pytest.raises(GrowthError, match="human wall"):
            svc.stop_experiment(eid, "r", actor_id="bot", actor_type=actor)


def test_early_stop_without_a_satisfied_rule_degrades_the_label(svc):
    eid = _run(svc, minimum=20)
    _populate(svc, eid, per_arm=45, control_successes=9,
              treatment_successes=27)
    svc.stop_experiment(eid, "founder call", actor_id="founder")
    result = svc.get_result(eid)
    assert result["label"] == "STOPPED EARLY — DEGRADED"
    assert "REVIEW REQUIRED" in result["modifiers"]
    assert "degrades what may be concluded" in " ".join(result["reasons"])


def test_interim_reads_are_recorded_and_counted(svc):
    eid = _run(svc, minimum=20)
    _populate(svc, eid, per_arm=5, control_successes=2, treatment_successes=3)
    for _ in range(3):
        svc.record_interim_read(eid, actor_id="founder", note="checking")
    result = svc.get_result(eid)
    assert result["interim_read_count"] == 3
    reads = [r for r in svc.get_history(eid)
             if r.event_type == "growth.interim_read_recorded"]
    assert reads[0].payload["reader"] == "founder"
    assert "observed_totals" in reads[0].payload


def test_exploratory_analysis_cannot_drive_the_label(svc):
    eid = _run(svc, minimum=20)
    _populate(svc, eid, per_arm=3, control_successes=1, treatment_successes=2)
    before = svc.get_result(eid)["label"]
    svc.record_exploratory_analysis(
        eid, "segment split by industry",
        "treatment looks stronger for SaaS accounts")
    after = svc.get_result(eid)
    assert after["label"] == before == "TOO FEW OBSERVATIONS"
    row = [r for r in svc.get_history(eid)
           if r.event_type == "growth.exploratory_analysis_recorded"][0]
    assert row.payload["analysis_class"] == "EXPLORATORY"
    assert row.payload["may_drive_label"] is False


# --- founder override ---------------------------------------------------------

def test_founder_override_is_a_first_class_immutable_fact(svc):
    eid = _run(svc, minimum=20)
    _populate(svc, eid, per_arm=40, control_successes=13,
              treatment_successes=14)
    assert svc.get_result(eid)["label"] == "INCONCLUSIVE"
    svc.record_founder_override(
        eid, decision="ship the shorter CTA anyway",
        reason="qualitative replies were clearly better",
        contrary_to="INCONCLUSIVE", actor_id="founder")
    result = svc.get_result(eid)
    assert result["label"] == "INCONCLUSIVE"        # the label does NOT change
    assert "FOUNDER OVERRIDE RECORDED" in result["modifiers"]
    row = [r for r in svc.get_history(eid)
           if r.event_type == "growth.founder_override_recorded"][0]
    assert row.payload["contrary_to"] == "INCONCLUSIVE"
    assert "a human did" in row.payload["note"]


def test_founder_override_is_human_only(svc):
    eid = _run(svc)
    with pytest.raises(GrowthError, match="human wall"):
        svc.record_founder_override(eid, decision="d", reason="r",
                                    contrary_to="x", actor_id="bot",
                                    actor_type="system")


# --- review -------------------------------------------------------------------

def test_review_requires_request_and_is_human_only(svc):
    eid = _run(svc, minimum=2)
    _populate(svc, eid, per_arm=5, control_successes=1, treatment_successes=4)
    with pytest.raises(GrowthError, match="prior review request"):
        svc.record_review(eid, conclusion="c", actor_id="founder")
    svc.request_review(eid)
    for actor in ("system", "agent"):
        with pytest.raises(GrowthError, match="human wall"):
            svc.record_review(eid, conclusion="c", actor_id="bot",
                              actor_type=actor)
    svc.record_review(eid, conclusion="the arms differed; worth another run",
                      actor_id="founder")
    assert svc.get_state(eid).review_status == "reviewed"


def test_review_conclusion_cannot_overclaim(svc):
    eid = _run(svc, minimum=2)
    _populate(svc, eid, per_arm=5, control_successes=1, treatment_successes=4)
    svc.request_review(eid)
    with pytest.raises(GrowthError, match="overclaims"):
        svc.record_review(eid, conclusion="treatment is the clear winner",
                          actor_id="founder")


# --- language wall ------------------------------------------------------------

def test_no_result_read_model_ever_speaks_like_a_deck(svc):
    eid = _run(svc, minimum=20)
    _populate(svc, eid, per_arm=45, control_successes=9,
              treatment_successes=27)
    blob = json.dumps(svc.get_result(eid), default=str).lower()
    for phrase in ("clear win", "definitely"):
        assert phrase not in blob
    for pattern in (r"\bwinner\b", r"\bwon\b", r"\bbeat\b", r"\bproves\b",
                    r"\bproven\b", r"\bsignificant\b", r"\bguaranteed\b",
                    r"\bcaused\b", r"\boutperform\b"):
        assert not re.search(pattern, blob), pattern


def test_there_is_no_winner_field_anywhere(svc):
    eid = _run(svc, minimum=2)
    _populate(svc, eid, per_arm=20, control_successes=4,
              treatment_successes=15)
    result = svc.get_result(eid)
    assert "winner" not in result
    assert not any("winner" in k.lower() for k in result)
