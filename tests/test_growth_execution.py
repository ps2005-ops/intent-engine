"""T018 bars: randomization, assignment, exposure, observations, and the
survivorship funnel."""
import importlib.util
import sys
from pathlib import Path

import pytest

from intent_engine.growth import GrowthError, GrowthService, assign
from intent_engine.growth.randomization import RANDOMIZATION_METHOD


def _load_sibling(name: str):
    """Repo convention (see test_founder_report_pdf.py): load a sibling test
    module by path rather than relying on tests/ being importable."""
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).resolve().parent / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_reg = _load_sibling("test_growth_registration")
ARMS, RANDOMIZATION, register = _reg.ARMS, _reg.RANDOMIZATION, _reg.register


@pytest.fixture()
def svc(tmp_path):
    return GrowthService(tmp_path)


@pytest.fixture()
def running(svc):
    eid = register(svc)
    svc.start_experiment(eid, actor_id="founder")
    return svc, eid


# --- randomization -----------------------------------------------------------

def test_assignment_is_reproducible_forever():
    alloc = {"control": 0.5, "treatment": 0.5}
    first = [assign("EXP1", 20260721, f"e{i}", alloc) for i in range(50)]
    second = [assign("EXP1", 20260721, f"e{i}", alloc) for i in range(50)]
    assert first == second
    # a different seed produces a different (but still stable) mapping
    other = [assign("EXP1", 999, f"e{i}", alloc) for i in range(50)]
    assert other != first
    assert other == [assign("EXP1", 999, f"e{i}", alloc) for i in range(50)]


def test_allocation_ratios_respected_within_tolerance():
    alloc = {"control": 0.5, "treatment": 0.5}
    arms = [assign("EXP", 1, f"unit-{i}", alloc) for i in range(2000)]
    share = arms.count("treatment") / len(arms)
    assert 0.45 <= share <= 0.55
    skewed = {"control": 0.9, "treatment": 0.1}
    arms2 = [assign("EXP", 1, f"unit-{i}", skewed) for i in range(2000)]
    assert 0.05 <= arms2.count("treatment") / len(arms2) <= 0.15


def test_randomization_metadata_is_fully_recorded(svc):
    eid = register(svc)
    rand = svc.get_registration(eid)["randomization"]
    assert rand["method"] == RANDOMIZATION_METHOD
    assert rand["seed"] == 20260721
    assert rand["unit"] == "crm_entity"
    assert "crm_entity_id" in rand["hash_input_definition"]


# --- assignment ---------------------------------------------------------------

def test_assignment_requires_started_experiment(svc):
    eid = register(svc)
    with pytest.raises(GrowthError, match="started experiment"):
        svc.assign_entity(eid, "e1")


def test_assignment_is_idempotent(running):
    svc, eid = running
    a = svc.assign_entity(eid, "e1")
    b = svc.assign_entity(eid, "e1")
    assert a.growth_event_id == b.growth_event_id
    assert len([r for r in svc.get_history(eid)
                if r.event_type == "growth.entity_assigned"]) == 1


def test_cross_arm_reassignment_is_impossible(running):
    svc, eid = running
    svc.assign_entity(eid, "e1")
    state = svc.get_state(eid)
    current = state.assignments["e1"]
    other = "treatment" if current == "control" else "control"
    with pytest.raises(GrowthError, match="never be reassigned"):
        svc._record(eid, "growth.entity_assigned", actor_type="system",
                    actor_id="x", version=state.approved_version,
                    payload={"crm_entity_id": "e1", "arm_id": other})


def test_excluded_entity_cannot_be_assigned(running):
    svc, eid = running
    svc.exclude_entity(eid, "e1", "bounced email", actor_id="founder")
    with pytest.raises(GrowthError, match="excluded after registration"):
        svc.assign_entity(eid, "e1")


def test_no_reassignment_or_rebalance_api_exists(svc):
    for banned in ("reassign", "rebalance", "rollout", "rollback", "launch"):
        assert not [m for m in dir(svc) if banned in m.lower()]


# --- exposure -----------------------------------------------------------------

def test_exposure_requires_assignment_and_is_idempotent(running):
    svc, eid = running
    with pytest.raises(GrowthError, match="requires a prior assignment"):
        svc.record_exposure(eid, "e1", exposure_key="send-1")
    svc.assign_entity(eid, "e1")
    svc.record_exposure(eid, "e1", exposure_key="send-1")
    svc.record_exposure(eid, "e1", exposure_key="send-1")
    exposures = [r for r in svc.get_history(eid)
                 if r.event_type == "growth.exposure_recorded"]
    assert len(exposures) == 1
    # a second distinct exposure IS a new fact
    svc.record_exposure(eid, "e1", exposure_key="send-2")
    assert len([r for r in svc.get_history(eid)
                if r.event_type == "growth.exposure_recorded"]) == 2


def test_exposure_after_stop_is_rejected(running):
    svc, eid = running
    svc.assign_entity(eid, "e1")
    svc.stop_experiment(eid, "done", actor_id="founder")
    with pytest.raises(GrowthError, match="after the experiment stopped"):
        svc.record_exposure(eid, "e1", exposure_key="late")


def test_version_binding_rejects_a_stale_version(running):
    """Improvement 1: activity must bind to the CURRENTLY approved version."""
    svc, eid = running
    svc.assign_entity(eid, "e1")
    svc.amend_experiment(eid, "widen guardrails", actor_id="founder")
    state = svc.get_state(eid)
    assert state.approved_version == 2
    with pytest.raises(GrowthError, match="currently approved version"):
        svc._record(eid, "growth.exposure_recorded", actor_type="system",
                    actor_id="x", version=1,
                    payload={"crm_entity_id": "e1", "arm_id": "control",
                             "exposure_key": "stale"})
    # historical facts keep their original version
    assigned = [r for r in svc.get_history(eid)
                if r.event_type == "growth.entity_assigned"][0]
    assert assigned.experiment_version == 1


# --- observations -------------------------------------------------------------

def _expose(svc, eid, entity):
    svc.assign_entity(eid, entity)
    svc.record_exposure(eid, entity, exposure_key="send-1")


def test_unregistered_metric_is_rejected_and_recorded(running):
    svc, eid = running
    _expose(svc, eid, "e1")
    with pytest.raises(GrowthError, match="not the pre-registered primary"):
        svc.record_observation(eid, "e1", metric_name="click_rate",
                               outcome_value=True, source="s",
                               window_start="2026-08-01", window_end="2026-08-14")
    kinds = [r.event_type for r in svc.get_history(eid)]
    assert "growth.observation_rejected" in kinds


def test_observation_requires_source_window_and_assignment(running):
    svc, eid = running
    _expose(svc, eid, "e1")
    with pytest.raises(GrowthError, match="source is mandatory"):
        svc.record_observation(eid, "e1", metric_name="reply_rate",
                               outcome_value=True, source="",
                               window_start="a", window_end="b")
    with pytest.raises(GrowthError, match="window is mandatory"):
        svc.record_observation(eid, "e1", metric_name="reply_rate",
                               outcome_value=True, source="s",
                               window_start="", window_end="")
    with pytest.raises(GrowthError, match="unassigned entity"):
        svc.record_observation(eid, "ghost", metric_name="reply_rate",
                               outcome_value=True, source="s",
                               window_start="a", window_end="b")


def test_observation_is_idempotent(running):
    svc, eid = running
    _expose(svc, eid, "e1")
    for _ in range(2):
        svc.record_observation(eid, "e1", metric_name="reply_rate",
                               outcome_value=True, source="crm",
                               window_start="2026-08-01",
                               window_end="2026-08-14")
    assert len([r for r in svc.get_history(eid)
                if r.event_type == "growth.observation_recorded"]) == 1


# --- survivorship funnel (improvement 4) -------------------------------------

def test_funnel_shows_every_dropoff(running):
    svc, eid = running
    # assigned + exposed + observed
    _expose(svc, eid, "a")
    svc.record_observation(eid, "a", metric_name="reply_rate",
                           outcome_value=True, source="crm",
                           window_start="2026-08-01", window_end="2026-08-14")
    # assigned + exposed, never observed
    _expose(svc, eid, "b")
    # assigned, never exposed
    svc.assign_entity(eid, "c")
    # excluded after registration
    svc.exclude_entity(eid, "d", "hard bounce", actor_id="founder")
    # an invalid observation
    with pytest.raises(GrowthError):
        svc.record_observation(eid, "a", metric_name="wrong_metric",
                               outcome_value=True, source="s",
                               window_start="x", window_end="y")

    funnel = svc.get_funnel(eid)
    totals = funnel["totals"]
    assert totals["assigned"] == 3
    assert totals["exposed"] == 2
    assert totals["observed"] == 1
    assert totals["assigned_not_exposed"] == 1
    assert totals["exposed_not_observed"] == 1
    assert totals["excluded_after_registration"] == 1
    assert totals["invalid_observations"] == 1
    # and it travels with the result, always
    assert svc.get_result(eid)["participation_funnel"]["totals"] == totals
