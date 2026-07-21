"""Folded experiment state and transition validation (T018).

Nothing here is stored as authoritative status: every value is folded
from the append-only log and re-validated on read. Two properties are
load-bearing:

  * VERSION BINDING (improvement 1) — the fold tracks the currently
    approved version. Assignment, exposure, observation, and analysis
    facts are only legal when bound to it; a fact bound to a superseded
    version is rejected at write time and flagged on read.
  * TERMINAL ARCHIVAL (improvement 7) — archived / superseded /
    invalidated / withdrawn / abandoned end activity without deleting
    anything.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from intent_engine.growth.records import GrowthError

# Registration components that must all exist before submission.
REQUIRED_REGISTRATION_PARTS = (
    "hypothesis", "arms", "metric", "guardrails", "randomization",
    "stopping_rules", "analysis_plan",
)

_TERMINAL_EVENT_TO_STATUS = {
    "growth.experiment_archived": "archived",
    "growth.experiment_superseded": "superseded",
    "growth.experiment_invalidated": "invalidated",
    "growth.experiment_withdrawn": "withdrawn",
    "growth.experiment_abandoned": "abandoned",
}

# Facts that must bind to the currently approved version.
VERSION_BOUND_EVENTS = {
    "growth.entity_assigned", "growth.exposure_recorded",
    "growth.observation_recorded", "growth.interim_read_recorded",
    "growth.result_labelled", "growth.snapshot_captured",
    "growth.stopping_rule_satisfied", "growth.reviewed",
}


@dataclass(frozen=True)
class ExperimentState:
    registration_status: str = "drafted"     # drafted | submitted | approved
                                             # | rejected
    lifecycle_status: str = "not_started"    # not_started | running | stopped
                                             # | archived | superseded
                                             # | invalidated | withdrawn
                                             # | abandoned
    review_status: str = "none"              # none | requested | reviewed
    approved_version: int | None = None
    draft_version: int = 1
    parts_defined: frozenset = frozenset()
    started: bool = False
    stopped: bool = False
    stop_rule_satisfied: bool = False
    stopped_without_rule: bool = False       # degrades every later label
    founder_override: bool = False
    guardrail_breached: bool = False
    interim_read_count: int = 0
    # arm_id -> allocation ratio, from the approved version
    arms: dict = field(default_factory=dict)
    has_control: bool = False
    assignments: dict = field(default_factory=dict)   # entity -> arm_id
    excluded_after_registration: frozenset = frozenset()
    decision_ids: tuple = ()
    terminal: bool = False


def _precondition(state: ExperimentState, event_type: str, payload: dict,
                  version: int | None) -> tuple[bool, str]:
    if state.terminal and event_type not in (
            "growth.knowledge_candidate_requested", "growth.decision_linked",
            "growth.snapshot_captured"):
        return (False, f"experiment is {state.lifecycle_status} — history is "
                       "preserved but no further activity is accepted")

    if event_type == "growth.experiment_drafted":
        return (not state.parts_defined and state.approved_version is None,
                "an experiment is drafted once")

    # --- registration components -------------------------------------------
    part_events = {
        "growth.hypothesis_defined": "hypothesis",
        "growth.arms_defined": "arms",
        "growth.metric_defined": "metric",
        "growth.guardrails_defined": "guardrails",
        "growth.randomization_defined": "randomization",
        "growth.stopping_rules_defined": "stopping_rules",
        "growth.analysis_plan_defined": "analysis_plan",
    }
    if event_type in part_events:
        part = part_events[event_type]
        if state.registration_status == "approved":
            # improvement 2: the metric (and every other registered part) is
            # immutable after approval. A different metric needs a NEW
            # version via an amendment, never an edit.
            return (False, f"{part} is frozen after approval — an amendment "
                           "creating a new experiment version is the only "
                           "way to change a registered commitment")
        return (True, "")

    if event_type == "growth.registration_submitted":
        missing = [p for p in REQUIRED_REGISTRATION_PARTS
                   if p not in state.parts_defined]
        if missing:
            return (False, f"registration incomplete: missing {missing}")
        return (state.registration_status in ("drafted", "rejected"),
                "registration already submitted")
    if event_type in ("growth.registration_approved",
                      "growth.registration_rejected"):
        return (state.registration_status == "submitted",
                "no submitted registration to review")
    if event_type == "growth.experiment_amended":
        return (state.registration_status == "approved",
                "only an approved experiment can be amended")

    # --- execution -----------------------------------------------------------
    if event_type == "growth.experiment_started":
        if state.registration_status != "approved":
            return (False, "an experiment may only start after HUMAN "
                           "approval of its pre-registration")
        return (not state.started, "experiment already started")

    if event_type in VERSION_BOUND_EVENTS:
        if state.approved_version is None:
            return (False, f"{event_type} requires an approved experiment "
                           "version")
        if version != state.approved_version:
            return (False, f"{event_type} must bind to the currently "
                           f"approved version ({state.approved_version}), "
                           f"got {version}")

    if event_type == "growth.entity_assigned":
        entity = payload.get("crm_entity_id")
        arm = payload.get("arm_id")
        if entity in state.excluded_after_registration:
            return (False, "entity was excluded after registration")
        if arm not in state.arms:
            return (False, f"unknown arm: {arm!r}")
        prior = state.assignments.get(entity)
        if prior is not None and prior != arm:
            return (False, "an entity can never be reassigned between arms")
        return (True, "")

    if event_type == "growth.exposure_recorded":
        entity = payload.get("crm_entity_id")
        if entity not in state.assignments:
            return (False, "exposure requires a prior assignment")
        if not state.started:
            return (False, "exposure before the experiment started")
        if state.stopped:
            return (False, "exposure after the experiment stopped")
        return (True, "")

    if event_type == "growth.observation_recorded":
        if not state.started:
            return (False, "observation before the experiment started")
        return (True, "")

    # --- analysis / conclusion ----------------------------------------------
    if event_type == "growth.experiment_stopped":
        return (state.started and not state.stopped,
                "only a running experiment can be stopped")
    if event_type == "growth.review_requested":
        return (state.started, "nothing to review before the experiment ran")
    if event_type == "growth.reviewed":
        return (state.review_status == "requested",
                "review requires a prior review request")
    if event_type == "growth.decision_linked":
        return (state.review_status == "reviewed",
                "a decision may only be linked after human review")

    return (True, "")


def _apply(state: ExperimentState, row) -> ExperimentState:
    et, payload = row.event_type, row.payload or {}
    d = dict(registration_status=state.registration_status,
             lifecycle_status=state.lifecycle_status,
             review_status=state.review_status,
             approved_version=state.approved_version,
             draft_version=state.draft_version,
             parts_defined=set(state.parts_defined),
             started=state.started, stopped=state.stopped,
             stop_rule_satisfied=state.stop_rule_satisfied,
             stopped_without_rule=state.stopped_without_rule,
             founder_override=state.founder_override,
             guardrail_breached=state.guardrail_breached,
             interim_read_count=state.interim_read_count,
             arms=dict(state.arms), has_control=state.has_control,
             assignments=dict(state.assignments),
             excluded_after_registration=set(state.excluded_after_registration),
             decision_ids=state.decision_ids, terminal=state.terminal)

    part_events = {
        "growth.hypothesis_defined": "hypothesis",
        "growth.arms_defined": "arms",
        "growth.metric_defined": "metric",
        "growth.guardrails_defined": "guardrails",
        "growth.randomization_defined": "randomization",
        "growth.stopping_rules_defined": "stopping_rules",
        "growth.analysis_plan_defined": "analysis_plan",
    }
    if et in part_events:
        d["parts_defined"].add(part_events[et])
        if et == "growth.arms_defined":
            d["arms"] = {a["arm_id"]: a.get("allocation", 0)
                         for a in payload.get("arms", [])}
            d["has_control"] = any(a.get("is_control")
                                   for a in payload.get("arms", []))
    elif et == "growth.registration_submitted":
        d["registration_status"] = "submitted"
    elif et == "growth.registration_approved":
        d["registration_status"] = "approved"
        d["approved_version"] = d["draft_version"]
    elif et == "growth.registration_rejected":
        d["registration_status"] = "rejected"
    elif et == "growth.experiment_amended":
        # A new version supersedes the old for FUTURE activity; historical
        # rows keep the version they were written against.
        d["draft_version"] = state.draft_version + 1
        d["approved_version"] = d["draft_version"]
        if payload.get("arms"):
            d["arms"] = {a["arm_id"]: a.get("allocation", 0)
                         for a in payload["arms"]}
            d["has_control"] = any(a.get("is_control")
                                   for a in payload["arms"])
    elif et == "growth.experiment_started":
        d["started"] = True
        d["lifecycle_status"] = "running"
    elif et == "growth.entity_assigned":
        d["assignments"][payload.get("crm_entity_id")] = payload.get("arm_id")
    elif et == "growth.entity_excluded_after_registration":
        d["excluded_after_registration"].add(payload.get("crm_entity_id"))
    elif et == "growth.guardrail_breached":
        d["guardrail_breached"] = True
    elif et == "growth.interim_read_recorded":
        d["interim_read_count"] = state.interim_read_count + 1
    elif et == "growth.stopping_rule_satisfied":
        d["stop_rule_satisfied"] = True
    elif et == "growth.experiment_stopped":
        d["stopped"] = True
        d["lifecycle_status"] = "stopped"
        if not state.stop_rule_satisfied:
            d["stopped_without_rule"] = True
    elif et == "growth.founder_override_recorded":
        d["founder_override"] = True
    elif et == "growth.review_requested":
        d["review_status"] = "requested"
    elif et == "growth.reviewed":
        d["review_status"] = "reviewed"
    elif et == "growth.decision_linked":
        did = payload.get("decision_id") or row.decision_id
        if did and did not in state.decision_ids:
            d["decision_ids"] = state.decision_ids + (did,)
    elif et in _TERMINAL_EVENT_TO_STATUS:
        d["lifecycle_status"] = _TERMINAL_EVENT_TO_STATUS[et]
        d["terminal"] = True

    d["parts_defined"] = frozenset(d["parts_defined"])
    d["excluded_after_registration"] = frozenset(d["excluded_after_registration"])
    return ExperimentState(**d)


def validate_growth_event(state: ExperimentState, event_type: str,
                          payload: dict, version=None):
    return _precondition(state, event_type, payload or {}, version)


def fold_experiment(rows, *, validate: bool = False) -> ExperimentState:
    state = ExperimentState()
    for row in rows:
        if validate:
            ok, reason = _precondition(state, row.event_type,
                                       row.payload or {},
                                       row.experiment_version)
            if not ok:
                raise GrowthError(
                    f"stored experiment history invalid at {row.event_type}: "
                    f"{reason}")
        state = _apply(state, row)
    return state
