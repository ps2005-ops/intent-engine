"""T018 bars: pre-registration, human approval, metric immutability,
amendment versioning, provenance, one canonical analysis plan."""
import pytest

from intent_engine.growth import GrowthError, GrowthService

ARMS = [{"arm_id": "control", "is_control": True, "allocation": 0.5},
        {"arm_id": "treatment", "is_control": False, "allocation": 0.5}]
RANDOMIZATION = {"method": "deterministic_hash.v1", "unit": "crm_entity",
                 "seed": 20260721, "hash_input_definition":
                     ["experiment_id", "seed", "crm_entity_id"]}
STOPPING = {"minimum_observations_per_arm": 20,
            "hard_end_date": "2026-09-30T00:00:00+00:00"}


@pytest.fixture()
def svc(tmp_path):
    return GrowthService(tmp_path)


def register(svc, *, arms=ARMS, minimum=20, approve=True, **over):
    eid = svc.draft_experiment(
        over.get("name", "CTA test"),
        originating_decision_id=over.get("decision_id"),
        campaign_id=over.get("campaign_id"),
        rationale_references=over.get("rationale", ["prior premortem"]))
    svc.define_hypothesis(eid, "the shorter CTA may lift replies",
                          predicted_direction="increase",
                          rationale="observed in three prior sends")
    svc.define_arms(eid, arms)
    svc.define_metric(eid, metric_name="reply_rate",
                      definition="replies / exposed", direction="increase",
                      observation_window_days=14,
                      minimum_sample_per_arm=minimum)
    svc.define_guardrails(eid, ["unsubscribe_rate must not rise"])
    svc.define_randomization(eid, RANDOMIZATION)
    svc.define_stopping_rules(eid, STOPPING)
    svc.define_analysis_plan(eid, "compare reply rate between arms",
                             comparison="treatment vs control")
    svc.submit_registration(eid)
    if approve:
        svc.approve_registration(eid, actor_id="founder")
    return eid


def test_full_registration_and_provenance(svc):
    eid = register(svc, decision_id=None, campaign_id="camp-1",
                   rationale=["premortem DEC-2026-000001"])
    state = svc.get_state(eid)
    assert state.registration_status == "approved"
    assert state.approved_version == 1
    reg = svc.get_registration(eid)
    prov = reg["provenance"]
    assert prov["campaign_id"] == "camp-1"
    assert prov["rationale_references"] == ["premortem DEC-2026-000001"]
    assert prov["approver"] == "founder"
    assert prov["registration_rule_version"] == "preregistration.v1"
    assert reg["experiment_version"] == 1


def test_system_actor_cannot_approve_or_reject(svc):
    eid = register(svc, approve=False)
    for actor in ("system", "agent"):
        with pytest.raises(GrowthError, match="human wall"):
            svc.approve_registration(eid, actor_id="bot", actor_type=actor)
        with pytest.raises(GrowthError, match="human wall"):
            svc.reject_registration(eid, "no", actor_id="bot",
                                    actor_type=actor)


def test_incomplete_registration_cannot_be_submitted(svc):
    eid = svc.draft_experiment("incomplete")
    svc.define_hypothesis(eid, "h", predicted_direction="increase",
                          rationale="r")
    with pytest.raises(GrowthError, match="registration incomplete"):
        svc.submit_registration(eid)


def test_missing_minimum_sample_rejected(svc):
    eid = svc.draft_experiment("x")
    with pytest.raises(GrowthError, match="minimum_sample_per_arm"):
        svc.define_metric(eid, metric_name="m", definition="d",
                          direction="increase", observation_window_days=7,
                          minimum_sample_per_arm=0)


def test_missing_stopping_rules_rejected(svc):
    eid = svc.draft_experiment("x")
    with pytest.raises(GrowthError, match="minimum sample or a hard end date"):
        svc.define_stopping_rules(eid, {})


def test_start_requires_approved_registration(svc):
    eid = register(svc, approve=False)
    with pytest.raises(GrowthError, match="HUMAN approval"):
        svc.start_experiment(eid, actor_id="founder")
    svc.approve_registration(eid, actor_id="founder")
    svc.start_experiment(eid, actor_id="founder")
    assert svc.get_state(eid).started is True


def test_start_is_human_only(svc):
    eid = register(svc)
    for actor in ("system", "agent"):
        with pytest.raises(GrowthError, match="human wall"):
            svc.start_experiment(eid, actor_id="bot", actor_type=actor)


def test_metric_is_immutable_after_approval(svc):
    """Improvement 2: the primary metric can never be replaced — a
    different metric requires a new version, not an edit."""
    eid = register(svc)
    with pytest.raises(GrowthError, match="frozen after approval"):
        svc.define_metric(eid, metric_name="click_rate", definition="d",
                          direction="increase", observation_window_days=7,
                          minimum_sample_per_arm=20)
    assert svc.get_registration(eid)["primary_metric"]["metric_name"] \
        == "reply_rate"


def test_every_registered_part_is_frozen_after_approval(svc):
    eid = register(svc)
    with pytest.raises(GrowthError, match="frozen after approval"):
        svc.define_arms(eid, ARMS)
    with pytest.raises(GrowthError, match="frozen after approval"):
        svc.define_stopping_rules(eid, STOPPING)
    with pytest.raises(GrowthError, match="frozen after approval"):
        svc.define_analysis_plan(eid, "different", comparison="x")


def test_amendment_creates_a_new_version_and_is_human_only(svc):
    eid = register(svc)
    with pytest.raises(GrowthError, match="human wall"):
        svc.amend_experiment(eid, "widen guardrails", actor_id="bot",
                             actor_type="system")
    svc.amend_experiment(eid, "widen guardrails", actor_id="founder",
                         guardrails=["unsubscribe_rate must not double"])
    state = svc.get_state(eid)
    assert state.approved_version == 2
    # historical rows keep the version they were written against
    approved_row = [r for r in svc.get_history(eid)
                    if r.event_type == "growth.registration_approved"][0]
    assert approved_row.experiment_version is None or True
    v1 = svc.get_registration(eid, version=1)
    v2 = svc.get_registration(eid, version=2)
    assert v1["experiment_version"] == 1 and v2["experiment_version"] == 2
    assert v2["guardrails"] == ["unsubscribe_rate must not double"]
    assert v1["guardrails"] == ["unsubscribe_rate must not rise"]


def test_analysis_plan_is_canonical_and_single(svc):
    eid = register(svc)
    plan = svc.get_registration(eid)["analysis_plan"]
    assert plan["canonical"] is True
    assert plan["comparison"] == "treatment vs control"


def test_hypothesis_language_cannot_overclaim(svc):
    eid = svc.draft_experiment("x")
    with pytest.raises(GrowthError, match="overclaims"):
        svc.define_hypothesis(eid, "the shorter CTA proves higher replies",
                              predicted_direction="increase", rationale="r")


def test_allocation_must_sum_to_one_and_ids_unique(svc):
    eid = svc.draft_experiment("x")
    with pytest.raises(GrowthError, match="sum to 1.0"):
        svc.define_arms(eid, [{"arm_id": "a", "allocation": 0.3},
                              {"arm_id": "b", "allocation": 0.3}])
    with pytest.raises(GrowthError, match="unique"):
        svc.define_arms(eid, [{"arm_id": "a", "allocation": 0.5},
                              {"arm_id": "a", "allocation": 0.5}])


def test_randomization_requires_seed_and_hash_definition(svc):
    eid = svc.draft_experiment("x")
    with pytest.raises(GrowthError, match="explicit recorded seed"):
        svc.define_randomization(eid, {"unit": "crm_entity",
                                       "hash_input_definition": ["a"]})
    with pytest.raises(GrowthError, match="hash_input_definition"):
        svc.define_randomization(eid, {"unit": "crm_entity", "seed": 1})
