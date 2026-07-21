"""Result labelling and the survivorship funnel (T018).

There is no `winner`. A result is a LABEL plus its reasons, its
participation funnel, and the statistic that produced it (or the reason
that statistic is unavailable).

Improvement 4 — survivorship accounting is never optional. Every result
carries, per arm and overall:

    assigned
    exposed                     (of those assigned)
    observed                    (of those exposed)
    assigned_not_exposed
    exposed_not_observed
    excluded_after_registration
    invalid_observations

A funnel that quietly drops people is how an honest experiment becomes a
dishonest one, so these counts travel with every label.

Improvement 3 — only the ONE canonical pre-registered analysis plan can
produce a label. Exploratory analyses are recorded, are labelled
exploratory, and are structurally excluded from this computation.
"""
from __future__ import annotations

from intent_engine.growth.records import (
    LABEL_ABANDONED, LABEL_ARCHIVED, LABEL_DIFFERENCE, LABEL_GUARDRAIL,
    LABEL_INCONCLUSIVE, LABEL_INVALIDATED, LABEL_NOT_STARTED,
    LABEL_OBSERVATIONAL, LABEL_RUNNING, LABEL_STOPPED_EARLY,
    LABEL_SUPERSEDED, LABEL_TOO_FEW, LABEL_WITHDRAWN,
    MODIFIER_FOUNDER_OVERRIDE, MODIFIER_NO_CAUSAL_CLAIM,
    MODIFIER_REVIEW_REQUIRED, STATUS_UNAVAILABLE,
)
from intent_engine.growth.statistics import (
    arm_counts, difference_in_proportions, unavailable,
)

LABEL_RULE_VERSION = "result_label.v1"

_TERMINAL_LABELS = {
    "archived": LABEL_ARCHIVED, "superseded": LABEL_SUPERSEDED,
    "invalidated": LABEL_INVALIDATED, "withdrawn": LABEL_WITHDRAWN,
    "abandoned": LABEL_ABANDONED,
}


def participation_funnel(rows, state) -> dict:
    """Survivorship accounting from the append-only log (improvement 4)."""
    assigned, exposed, observed, invalid = {}, {}, {}, 0
    for row in rows:
        payload = row.payload or {}
        entity = payload.get("crm_entity_id")
        if row.event_type == "growth.entity_assigned":
            assigned.setdefault(payload.get("arm_id"), set()).add(entity)
        elif row.event_type == "growth.exposure_recorded":
            exposed.setdefault(payload.get("arm_id"), set()).add(entity)
        elif row.event_type == "growth.observation_recorded":
            observed.setdefault(payload.get("arm_id"), set()).add(entity)
        elif row.event_type == "growth.observation_rejected":
            invalid += 1

    per_arm = {}
    for arm_id in sorted(set(assigned) | set(exposed) | set(observed)):
        a = assigned.get(arm_id, set())
        e = exposed.get(arm_id, set())
        o = observed.get(arm_id, set())
        per_arm[arm_id] = {
            "assigned": len(a), "exposed": len(e), "observed": len(o),
            "assigned_not_exposed": len(a - e),
            "exposed_not_observed": len(e - o),
        }
    totals = {
        "assigned": sum(v["assigned"] for v in per_arm.values()),
        "exposed": sum(v["exposed"] for v in per_arm.values()),
        "observed": sum(v["observed"] for v in per_arm.values()),
        "assigned_not_exposed": sum(v["assigned_not_exposed"]
                                    for v in per_arm.values()),
        "exposed_not_observed": sum(v["exposed_not_observed"]
                                    for v in per_arm.values()),
        "excluded_after_registration": len(state.excluded_after_registration),
        "invalid_observations": invalid,
    }
    return {"per_arm": per_arm, "totals": totals,
            "note": ("counts are distinct entities; every drop-off between "
                     "stages is shown rather than absorbed")}


def _outcome_counts(rows, arm_id: str) -> tuple:
    """(observed_entities, successes) for one arm, from CANONICAL
    observations only — exploratory analyses cannot contribute."""
    observed, successes = set(), 0
    for row in rows:
        if row.event_type != "growth.observation_recorded":
            continue
        payload = row.payload or {}
        if payload.get("arm_id") != arm_id:
            continue
        observed.add(payload.get("crm_entity_id"))
        if payload.get("outcome_value"):
            successes += 1
    return len(observed), successes


def compute_result(rows, state, registration: dict) -> dict:
    """Deterministic label from recorded facts. Never persisted as
    authority — a snapshot may capture it, with its inputs."""
    funnel = participation_funnel(rows, state)
    modifiers = []
    reasons = []

    control_arm = next((a["arm_id"] for a in registration.get("arms", [])
                        if a.get("is_control")), None)
    treatment_arms = [a["arm_id"] for a in registration.get("arms", [])
                      if not a.get("is_control")]
    minimum = registration.get("minimum_sample_per_arm")

    per_arm_stats = {}
    for arm in registration.get("arms", []):
        arm_id = arm["arm_id"]
        n_obs, successes = _outcome_counts(rows, arm_id)
        per_arm_stats[arm_id] = arm_counts(
            arm_id,
            assigned=funnel["per_arm"].get(arm_id, {}).get("assigned", 0),
            exposed=funnel["per_arm"].get(arm_id, {}).get("exposed", 0),
            observed=n_obs, successes=successes)

    base = {
        "label_rule_version": LABEL_RULE_VERSION,
        "experiment_version": state.approved_version,
        "participation_funnel": funnel,
        "per_arm": per_arm_stats,
        "minimum_sample_per_arm": minimum,
        "interim_read_count": state.interim_read_count,
        "stopping_rule_satisfied": state.stop_rule_satisfied,
        "human_reviewed": state.review_status == "reviewed",
        "analysis_plan": registration.get("analysis_plan"),
        "statistic": None,
    }

    # terminal states first — history preserved, activity ended
    if state.lifecycle_status in _TERMINAL_LABELS:
        return {**base, "label": _TERMINAL_LABELS[state.lifecycle_status],
                "modifiers": [MODIFIER_NO_CAUSAL_CLAIM],
                "reasons": [f"experiment is {state.lifecycle_status}; "
                            "history is retained in full"]}

    if not state.started:
        return {**base, "label": LABEL_NOT_STARTED, "modifiers": [],
                "reasons": ["no exposure has occurred"]}

    if state.founder_override:
        modifiers.append(MODIFIER_FOUNDER_OVERRIDE)
    if state.stopped_without_rule:
        modifiers.append(MODIFIER_REVIEW_REQUIRED)
        reasons.append("stopped by a human before a pre-registered stopping "
                       "rule was satisfied — every downstream read is degraded")

    if state.guardrail_breached:
        return {**base, "label": LABEL_GUARDRAIL,
                "modifiers": modifiers + [MODIFIER_REVIEW_REQUIRED],
                "reasons": reasons + ["a pre-registered guardrail was breached"]}

    # No control arm -> permanently observational, no matter how much data
    if control_arm is None:
        return {**base, "label": LABEL_OBSERVATIONAL,
                "modifiers": modifiers + [MODIFIER_NO_CAUSAL_CLAIM],
                "reasons": reasons + [
                    "no control arm was pre-registered, so no comparison "
                    "can support a causal claim regardless of sample size"],
                "statistic": unavailable(
                    "difference_in_proportions",
                    "no control arm exists in this design")}

    # Sample-size gate, per arm, against the PRE-REGISTERED minimum
    under = [arm_id for arm_id, s in per_arm_stats.items()
             if s["observed"] < (minimum or 0)]
    if under:
        label = (LABEL_STOPPED_EARLY if state.stopped_without_rule
                 else LABEL_TOO_FEW)
        return {**base, "label": label,
                "modifiers": modifiers + [MODIFIER_NO_CAUSAL_CLAIM],
                "reasons": reasons + [
                    f"arms below the pre-registered minimum of {minimum} "
                    f"observations: {sorted(under)}"],
                "statistic": unavailable(
                    "difference_in_proportions",
                    f"observed sample below the pre-registered minimum "
                    f"for {sorted(under)}")}

    primary_treatment = treatment_arms[0] if treatment_arms else None
    if primary_treatment is None:
        return {**base, "label": LABEL_OBSERVATIONAL,
                "modifiers": modifiers + [MODIFIER_NO_CAUSAL_CLAIM],
                "reasons": reasons + ["no treatment arm to compare"]}

    stat = difference_in_proportions(per_arm_stats[control_arm],
                                    per_arm_stats[primary_treatment])
    base["statistic"] = stat

    if stat["status"] == STATUS_UNAVAILABLE:
        return {**base, "label": LABEL_INCONCLUSIVE,
                "modifiers": modifiers + [MODIFIER_REVIEW_REQUIRED],
                "reasons": reasons + [
                    f"the pre-registered analysis could not be computed: "
                    f"{stat['reason']}"]}

    if stat["interval_excludes_zero"]:
        if state.stopped_without_rule:
            return {**base, "label": LABEL_STOPPED_EARLY,
                    "modifiers": modifiers + [MODIFIER_REVIEW_REQUIRED],
                    "reasons": reasons + [
                        "a difference was observed, but the early stop "
                        "degrades what may be concluded from it"]}
        return {**base, "label": LABEL_DIFFERENCE,
                "modifiers": modifiers + [MODIFIER_REVIEW_REQUIRED],
                "reasons": reasons + [
                    "the pre-registered interval excludes zero — this is an "
                    "observed difference awaiting human review, not a "
                    "conclusion and not an instruction to act"]}

    return {**base, "label": LABEL_INCONCLUSIVE, "modifiers": modifiers,
            "reasons": reasons + [
                "the pre-registered interval includes zero — the arms are "
                "not distinguishable under the registered analysis"]}
