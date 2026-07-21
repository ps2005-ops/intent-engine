"""GrowthService (T018) — the only write path, and where every wall lives.

Reused, never reimplemented:
    CRM          -> CRMService reads for audience/entity state
    Marketing    -> campaign/artifact references only
    Decisions    -> DecisionService owns the conclusion record
    Predictions  -> record_prediction / brier_summary own hypothesis grading
    Analytics    -> read-only metric views, statuses preserved
    Knowledge    -> KnowledgeService owns every learning promotion
    Events       -> CompanyEventBus owns delivery and the approval walls
"""
from __future__ import annotations

from intent_engine.core.decision_ids import new_ulid
from intent_engine.growth.randomization import (
    assign, validate_allocation, validate_randomization,
)
from intent_engine.growth.records import (
    HUMAN_ONLY_EVENTS, NAMESPACE_PRODUCTION, GrowthError, GrowthEvent,
    json_normalize, scan_banned_language,
)
from intent_engine.growth.results import compute_result, participation_funnel
from intent_engine.growth.state import (
    ExperimentState, fold_experiment, validate_growth_event,
)
from intent_engine.growth.store import GrowthStore

REGISTRATION_RULE_VERSION = "preregistration.v1"


class GrowthService:
    def __init__(self, base_dir="data", namespace: str = NAMESPACE_PRODUCTION,
                 *, crm_service=None, knowledge_service=None,
                 decision_service=None, analytics_service=None,
                 event_bus=None, ledger_path=None):
        self.store = GrowthStore(base_dir, namespace)
        self.namespace = namespace
        self.crm = crm_service
        self.knowledge = knowledge_service
        self.decisions = decision_service
        self.analytics = analytics_service
        self.bus = event_bus
        self.ledger_path = ledger_path

    # --- internal write path --------------------------------------------------
    def _stable_id(self, idempotency_key: str) -> str:
        """A retry of the same fact IS the same artifact — reuse the original
        id so the fingerprint compares like-for-like."""
        existing = self.store.find_by_idempotency_key(idempotency_key)
        return existing.subject_id if existing is not None else new_ulid()

    def _record(self, experiment_id, event_type, *, actor_type, actor_id,
                source="cli", payload=None, version=None, arm_id=None,
                subject_type=None, subject_id=None, occurred_at=None,
                idempotency_key=None, **refs) -> GrowthEvent:
        if event_type in HUMAN_ONLY_EVENTS and actor_type != "human":
            raise GrowthError(
                f"{event_type} is a human wall transition; "
                f"actor_type={actor_type!r} cannot emit it — nothing "
                "approves, starts, stops, or concludes itself here")
        kwargs = dict(event_type=event_type, experiment_id=experiment_id,
                      namespace=self.namespace, actor_type=actor_type,
                      actor_id=actor_id, source=source,
                      payload=json_normalize(dict(payload or {})),
                      experiment_version=version, arm_id=arm_id,
                      subject_type=subject_type, subject_id=subject_id,
                      idempotency_key=idempotency_key, **refs)
        if occurred_at is not None:
            kwargs["occurred_at"] = occurred_at
        candidate = GrowthEvent(**kwargs)
        if idempotency_key:
            existing = self.store.find_by_idempotency_key(idempotency_key)
            if existing is not None:
                if existing.content_fingerprint() != candidate.content_fingerprint():
                    raise ValueError(
                        f"idempotency_key {idempotency_key!r} was already "
                        "used for different content")
                return existing
        state = (self.get_state(experiment_id)
                 if event_type != "growth.experiment_drafted"
                 else ExperimentState())
        ok, reason = validate_growth_event(state, event_type, payload or {},
                                           version)
        if not ok:
            raise GrowthError(f"{event_type}: {reason}")
        return self.store.append(candidate)

    # =====================================================================
    # PRE-REGISTRATION
    # =====================================================================
    def draft_experiment(self, name: str, *, originating_decision_id=None,
                         campaign_id=None, rationale_references=None,
                         actor_type: str = "human", actor_id: str = "founder",
                         idempotency_key=None) -> str:
        """Provenance is captured at the very first fact (improvement 5)."""
        payload = {"name": name,
                   "originating_decision_id": originating_decision_id,
                   "campaign_id": campaign_id,
                   "rationale_references": list(rationale_references or []),
                   "registration_rule_version": REGISTRATION_RULE_VERSION,
                   "namespace": self.namespace}
        if idempotency_key:
            existing = self.store.find_by_idempotency_key(idempotency_key)
            if existing is not None:
                if existing.payload != json_normalize(payload):
                    raise ValueError(
                        f"idempotency_key {idempotency_key!r} was already "
                        "used for different content")
                return existing.experiment_id
        experiment_id = new_ulid()
        self._record(experiment_id, "growth.experiment_drafted",
                     actor_type=actor_type, actor_id=actor_id, payload=payload,
                     decision_id=originating_decision_id,
                     campaign_id=campaign_id,
                     idempotency_key=idempotency_key)
        return experiment_id

    def define_hypothesis(self, experiment_id, statement: str, *,
                          predicted_direction: str, rationale: str,
                          actor_type="human", actor_id="founder"):
        hits = scan_banned_language(statement)
        if hits:
            raise GrowthError(
                f"hypothesis language overclaims: {hits} — a hypothesis "
                "states what we expect, not what is true")
        return self._record(experiment_id, "growth.hypothesis_defined",
                            actor_type=actor_type, actor_id=actor_id,
                            payload={"statement": statement,
                                     "predicted_direction": predicted_direction,
                                     "rationale": rationale})

    def define_arms(self, experiment_id, arms: list, *, actor_type="human",
                    actor_id="founder"):
        allocation = validate_allocation(arms)
        n_control = sum(1 for a in arms if a.get("is_control"))
        if n_control > 1:
            raise GrowthError("at most one control arm")
        return self._record(experiment_id, "growth.arms_defined",
                            actor_type=actor_type, actor_id=actor_id,
                            payload={"arms": arms, "allocation": allocation,
                                     "has_control": n_control == 1})

    def define_metric(self, experiment_id, *, metric_name: str,
                      definition: str, direction: str,
                      observation_window_days: int,
                      minimum_sample_per_arm: int, secondary_metrics=None,
                      actor_type="human", actor_id="founder"):
        if not minimum_sample_per_arm or minimum_sample_per_arm < 1:
            raise GrowthError("a positive minimum_sample_per_arm must be "
                              "pre-registered")
        if direction not in ("increase", "decrease"):
            raise GrowthError("direction must be 'increase' or 'decrease'")
        return self._record(
            experiment_id, "growth.metric_defined", actor_type=actor_type,
            actor_id=actor_id,
            payload={"primary_metric": {"metric_name": metric_name,
                                        "definition": definition,
                                        "direction": direction,
                                        "observation_window_days":
                                            observation_window_days},
                     "minimum_sample_per_arm": minimum_sample_per_arm,
                     "secondary_metrics": list(secondary_metrics or [])})

    def define_guardrails(self, experiment_id, guardrails: list, *,
                          actor_type="human", actor_id="founder"):
        return self._record(experiment_id, "growth.guardrails_defined",
                            actor_type=actor_type, actor_id=actor_id,
                            payload={"guardrails": list(guardrails)})

    def define_randomization(self, experiment_id, spec: dict, *,
                             actor_type="human", actor_id="founder"):
        return self._record(experiment_id, "growth.randomization_defined",
                            actor_type=actor_type, actor_id=actor_id,
                            payload=validate_randomization(spec))

    def define_stopping_rules(self, experiment_id, rules: dict, *,
                              actor_type="human", actor_id="founder"):
        if not rules.get("minimum_observations_per_arm") \
                and not rules.get("hard_end_date"):
            raise GrowthError("a stopping rule must declare at least a "
                              "minimum sample or a hard end date")
        return self._record(experiment_id, "growth.stopping_rules_defined",
                            actor_type=actor_type, actor_id=actor_id,
                            payload=dict(rules))

    def define_analysis_plan(self, experiment_id, plan: str, *,
                             comparison: str, actor_type="human",
                             actor_id="founder"):
        """Improvement 3: exactly ONE canonical analysis plan per version."""
        return self._record(experiment_id, "growth.analysis_plan_defined",
                            actor_type=actor_type, actor_id=actor_id,
                            payload={"plan": plan, "comparison": comparison,
                                     "canonical": True})

    def submit_registration(self, experiment_id, *, actor_type="system",
                            actor_id="growth_agent"):
        return self._record(experiment_id, "growth.registration_submitted",
                            actor_type=actor_type, actor_id=actor_id,
                            payload={})

    def approve_registration(self, experiment_id, *, actor_id: str,
                             actor_type="human", note: str = ""):
        return self._record(experiment_id, "growth.registration_approved",
                            actor_type=actor_type, actor_id=actor_id,
                            payload={"approver": actor_id, "note": note})

    def reject_registration(self, experiment_id, reason: str, *, actor_id: str,
                            actor_type="human"):
        return self._record(experiment_id, "growth.registration_rejected",
                            actor_type=actor_type, actor_id=actor_id,
                            payload={"reason": reason})

    def amend_experiment(self, experiment_id, reason: str, *, actor_id: str,
                         actor_type="human", **changes):
        """Improvement 1+2: an amendment creates a NEW approved version.
        Historical facts keep the version they were written against; all
        SUBSEQUENT activity must bind to the new version."""
        state = self.get_state(experiment_id)
        return self._record(experiment_id, "growth.experiment_amended",
                            actor_type=actor_type, actor_id=actor_id,
                            version=state.approved_version,
                            payload={"reason": reason,
                                     "previous_version": state.approved_version,
                                     "new_version": state.draft_version + 1,
                                     **changes})

    def get_registration(self, experiment_id, version=None) -> dict:
        """The registered commitment for a version (default: approved)."""
        rows = self.store.for_experiment(experiment_id)
        if not rows:
            raise KeyError(f"no such experiment: {experiment_id}")
        state = fold_experiment(rows)
        target = version or state.approved_version or state.draft_version
        reg = {"experiment_version": target, "arms": [],
               "provenance": {}, "namespace": self.namespace}
        for row in rows:
            p = row.payload or {}
            if row.event_type == "growth.experiment_drafted":
                reg["name"] = p.get("name")
                reg["provenance"] = {
                    "originating_decision_id": p.get("originating_decision_id"),
                    "campaign_id": p.get("campaign_id"),
                    "rationale_references": p.get("rationale_references", []),
                    "registration_rule_version":
                        p.get("registration_rule_version"),
                }
            elif row.event_type == "growth.hypothesis_defined":
                reg["hypothesis"] = p
            elif row.event_type == "growth.arms_defined":
                reg["arms"] = p.get("arms", [])
                reg["allocation"] = p.get("allocation", {})
            elif row.event_type == "growth.metric_defined":
                reg["primary_metric"] = p.get("primary_metric")
                reg["minimum_sample_per_arm"] = p.get("minimum_sample_per_arm")
                reg["secondary_metrics"] = p.get("secondary_metrics", [])
            elif row.event_type == "growth.guardrails_defined":
                reg["guardrails"] = p.get("guardrails", [])
            elif row.event_type == "growth.randomization_defined":
                reg["randomization"] = p
            elif row.event_type == "growth.stopping_rules_defined":
                reg["stopping_rules"] = p
            elif row.event_type == "growth.analysis_plan_defined":
                reg["analysis_plan"] = p
            elif row.event_type == "growth.registration_approved":
                reg["provenance"]["approver"] = p.get("approver")
            elif row.event_type == "growth.experiment_amended":
                if row.payload.get("new_version", 0) <= target:
                    for key in ("arms", "guardrails", "stopping_rules"):
                        if key in p:
                            reg[key] = p[key]
                    reg.setdefault("amendments", []).append(
                        {"version": p.get("new_version"),
                         "reason": p.get("reason")})
        return reg

    # =====================================================================
    # EXECUTION
    # =====================================================================
    def start_experiment(self, experiment_id, *, actor_id: str,
                         actor_type="human"):
        state = self.get_state(experiment_id)
        row = self._record(experiment_id, "growth.experiment_started",
                           actor_type=actor_type, actor_id=actor_id,
                           version=state.approved_version, payload={})
        if self.bus is not None:
            self.bus.publish(
                "growth.experiment_started", subject_type="experiment",
                subject_id=experiment_id, producer="growth_platform",
                actor_type=actor_type, actor_id=actor_id, source="system",
                payload={"namespace": self.namespace,
                         "experiment_version": state.approved_version},
                correlation_id=experiment_id,
                idempotency_key=f"growth-started:{experiment_id}")
        return row

    def exclude_entity(self, experiment_id, crm_entity_id: str, reason: str, *,
                       actor_id: str, actor_type="human"):
        """Improvement 4: exclusions AFTER registration are recorded facts,
        counted in the funnel, never invisible."""
        state = self.get_state(experiment_id)
        return self._record(
            experiment_id, "growth.entity_excluded_after_registration",
            actor_type=actor_type, actor_id=actor_id,
            version=state.approved_version, crm_entity_id=crm_entity_id,
            payload={"crm_entity_id": crm_entity_id, "reason": reason},
            idempotency_key=f"exclude:{experiment_id}:{crm_entity_id}")

    def assign_entity(self, experiment_id, crm_entity_id: str, *,
                      actor_type="system", actor_id="growth_platform"):
        state = self.get_state(experiment_id)
        reg = self.get_registration(experiment_id)
        if not state.started:
            raise GrowthError("assignment requires a started experiment")
        rand = reg.get("randomization") or {}
        arm_id = assign(experiment_id, rand.get("seed"), crm_entity_id,
                        reg.get("allocation", {}))
        try:
            return self._record(
                experiment_id, "growth.entity_assigned",
                actor_type=actor_type, actor_id=actor_id,
                version=state.approved_version, arm_id=arm_id,
                crm_entity_id=crm_entity_id, subject_type="assignment",
                payload={"crm_entity_id": crm_entity_id, "arm_id": arm_id,
                         "randomization_method": rand.get("method"),
                         "seed": rand.get("seed")},
                idempotency_key=f"assign:{experiment_id}:{crm_entity_id}")
        except GrowthError as exc:
            if "reassigned" in str(exc):
                self._record(
                    experiment_id, "growth.assignment_conflict_rejected",
                    actor_type="system", actor_id="growth_platform",
                    version=state.approved_version,
                    crm_entity_id=crm_entity_id,
                    payload={"crm_entity_id": crm_entity_id,
                             "attempted_arm": arm_id,
                             "existing_arm": state.assignments.get(crm_entity_id),
                             "reason": str(exc)})
            raise

    def record_exposure(self, experiment_id, crm_entity_id: str, *,
                        exposure_key: str, campaign_id=None,
                        occurred_at=None, actor_type="system",
                        actor_id="growth_platform"):
        state = self.get_state(experiment_id)
        arm_id = state.assignments.get(crm_entity_id)
        return self._record(
            experiment_id, "growth.exposure_recorded", actor_type=actor_type,
            actor_id=actor_id, version=state.approved_version, arm_id=arm_id,
            crm_entity_id=crm_entity_id, campaign_id=campaign_id,
            subject_type="exposure", occurred_at=occurred_at,
            payload={"crm_entity_id": crm_entity_id, "arm_id": arm_id,
                     "exposure_key": exposure_key},
            idempotency_key=f"expose:{experiment_id}:{crm_entity_id}:{exposure_key}")

    def record_observation(self, experiment_id, crm_entity_id: str, *,
                           metric_name: str, outcome_value, source: str,
                           window_start: str, window_end: str,
                           occurred_at=None, actor_type="system",
                           actor_id="growth_platform"):
        state = self.get_state(experiment_id)
        reg = self.get_registration(experiment_id)
        primary = (reg.get("primary_metric") or {}).get("metric_name")
        if metric_name != primary:
            self._record(experiment_id, "growth.observation_rejected",
                         actor_type="system", actor_id="growth_platform",
                         version=state.approved_version,
                         crm_entity_id=crm_entity_id,
                         payload={"metric_name": metric_name,
                                  "reason": "not the pre-registered primary "
                                            "metric"})
            raise GrowthError(
                f"observation metric {metric_name!r} is not the "
                f"pre-registered primary metric {primary!r} — choosing a "
                "metric after data exists is exactly what pre-registration "
                "prevents")
        if not source:
            raise GrowthError("an observation source is mandatory")
        if not window_start or not window_end:
            raise GrowthError("an observation window is mandatory")
        arm_id = state.assignments.get(crm_entity_id)
        if arm_id is None:
            raise GrowthError("observation for an unassigned entity")
        return self._record(
            experiment_id, "growth.observation_recorded",
            actor_type=actor_type, actor_id=actor_id,
            version=state.approved_version, arm_id=arm_id,
            crm_entity_id=crm_entity_id, subject_type="observation",
            occurred_at=occurred_at,
            payload={"crm_entity_id": crm_entity_id, "arm_id": arm_id,
                     "metric_name": metric_name,
                     "outcome_value": outcome_value,
                     "observation_source": source,
                     "window": {"start": window_start, "end": window_end}},
            idempotency_key=(f"observe:{experiment_id}:{crm_entity_id}:"
                             f"{metric_name}:{window_start}:{window_end}"))

    def record_guardrail_breach(self, experiment_id, guardrail: str,
                                detail: str, *, actor_type="system",
                                actor_id="growth_platform"):
        state = self.get_state(experiment_id)
        return self._record(experiment_id, "growth.guardrail_breached",
                            actor_type=actor_type, actor_id=actor_id,
                            version=state.approved_version,
                            payload={"guardrail": guardrail,
                                     "detail": detail})

    # =====================================================================
    # ANALYSIS, STOPPING, REVIEW
    # =====================================================================
    def record_interim_read(self, experiment_id, *, actor_id: str,
                            actor_type="human", note: str = ""):
        """Peeking is allowed; hiding it is not."""
        state = self.get_state(experiment_id)
        result = self.get_result(experiment_id)
        return self._record(
            experiment_id, "growth.interim_read_recorded",
            actor_type=actor_type, actor_id=actor_id,
            version=state.approved_version,
            payload={"reader": actor_id, "note": note,
                     "observed_totals":
                         result["participation_funnel"]["totals"],
                     "label_at_read": result["label"]})

    def record_exploratory_analysis(self, experiment_id, description: str,
                                    findings: str, *, actor_type="system",
                                    actor_id="growth_agent"):
        """Improvement 3: recorded, labelled exploratory, and structurally
        unable to influence the canonical label."""
        state = self.get_state(experiment_id)
        return self._record(
            experiment_id, "growth.exploratory_analysis_recorded",
            actor_type=actor_type, actor_id=actor_id,
            version=state.approved_version,
            payload={"analysis_class": "EXPLORATORY",
                     "description": description, "findings": findings,
                     "may_drive_label": False,
                     "caveat": "exploratory analyses never produce a result "
                               "label and never justify a decision"})

    def evaluate_stopping_rules(self, experiment_id, *, as_of: str) -> dict:
        """Evaluates the PRE-REGISTERED rules. Satisfying a rule records a
        fact and does NOT stop anything."""
        state = self.get_state(experiment_id)
        reg = self.get_registration(experiment_id)
        rules = reg.get("stopping_rules") or {}
        result = self.get_result(experiment_id)
        per_arm = result["per_arm"]
        minimum = rules.get("minimum_observations_per_arm")
        reasons, satisfied = [], False
        if minimum:
            if per_arm and all(s["observed"] >= minimum
                               for s in per_arm.values()):
                satisfied = True
                reasons.append(f"every arm reached {minimum} observations")
            else:
                reasons.append(f"not every arm has reached {minimum} "
                               "observations")
        if rules.get("hard_end_date") and as_of >= rules["hard_end_date"]:
            satisfied = True
            reasons.append(f"hard end date {rules['hard_end_date']} reached")
        if satisfied and not state.stop_rule_satisfied:
            self._record(experiment_id, "growth.stopping_rule_satisfied",
                         actor_type="system", actor_id="growth_platform",
                         version=state.approved_version,
                         payload={"reasons": reasons, "as_of": as_of},
                         idempotency_key=f"stoprule:{experiment_id}")
        return {"satisfied": satisfied, "reasons": reasons,
                "note": "a satisfied rule is a FACT; stopping remains an "
                        "explicit human action"}

    def stop_experiment(self, experiment_id, reason: str, *, actor_id: str,
                        actor_type="human"):
        state = self.get_state(experiment_id)
        row = self._record(experiment_id, "growth.experiment_stopped",
                           actor_type=actor_type, actor_id=actor_id,
                           version=state.approved_version,
                           payload={"reason": reason,
                                    "stopping_rule_was_satisfied":
                                        state.stop_rule_satisfied})
        if self.bus is not None:
            self.bus.publish(
                "growth.experiment_stopped", subject_type="experiment",
                subject_id=experiment_id, producer="growth_platform",
                actor_type=actor_type, actor_id=actor_id, source="cli",
                payload={"namespace": self.namespace},
                correlation_id=experiment_id,
                idempotency_key=f"growth-stopped:{experiment_id}")
        return row

    def record_founder_override(self, experiment_id, *, decision: str,
                                reason: str, contrary_to: str, actor_id: str,
                                actor_type="human"):
        """Improvement 8: a founder decision against the statistical read is
        an immutable, first-class fact — never a quiet relabel."""
        state = self.get_state(experiment_id)
        return self._record(
            experiment_id, "growth.founder_override_recorded",
            actor_type=actor_type, actor_id=actor_id,
            version=state.approved_version,
            payload={"decision": decision, "reason": reason,
                     "contrary_to": contrary_to,
                     "note": "the data did not make this decision; a human "
                             "did, and said so"})

    def request_review(self, experiment_id, *, actor_type="system",
                       actor_id="growth_agent"):
        state = self.get_state(experiment_id)
        return self._record(experiment_id, "growth.review_requested",
                            actor_type=actor_type, actor_id=actor_id,
                            version=state.approved_version, payload={})

    def record_review(self, experiment_id, *, conclusion: str, actor_id: str,
                      actor_type="human", snapshot_id=None):
        state = self.get_state(experiment_id)
        hits = scan_banned_language(conclusion)
        if hits:
            raise GrowthError(f"review conclusion overclaims: {hits}")
        return self._record(experiment_id, "growth.reviewed",
                            actor_type=actor_type, actor_id=actor_id,
                            version=state.approved_version,
                            payload={"conclusion": conclusion,
                                     "reviewer": actor_id,
                                     "snapshot_id": snapshot_id})

    def link_decision(self, experiment_id, decision_id: str, *, actor_id: str,
                      actor_type="human"):
        state = self.get_state(experiment_id)
        # the review wall is checked BEFORE the lookup: "you haven't
        # reviewed this yet" is the more useful failure than "that id
        # doesn't exist".
        if state.review_status != "reviewed":
            raise GrowthError("growth.decision_linked: a decision may only "
                              "be linked after human review")
        if self.decisions is not None \
                and self.decisions.get_decision(decision_id) is None:
            raise KeyError(f"no such decision: {decision_id}")
        return self._record(experiment_id, "growth.decision_linked",
                            actor_type=actor_type, actor_id=actor_id,
                            version=state.approved_version,
                            decision_id=decision_id,
                            payload={"decision_id": decision_id},
                            idempotency_key=(f"decision-link:{experiment_id}:"
                                             f"{decision_id}"))

    # --- terminal states (improvement 7) --------------------------------------
    def _terminal(self, experiment_id, event_type, reason, actor_id,
                  actor_type="human"):
        state = self.get_state(experiment_id)
        return self._record(experiment_id, event_type, actor_type=actor_type,
                            actor_id=actor_id, version=state.approved_version,
                            payload={"reason": reason,
                                     "history_retained": True})

    def archive_experiment(self, experiment_id, reason, *, actor_id,
                           actor_type="human"):
        return self._terminal(experiment_id, "growth.experiment_archived",
                              reason, actor_id, actor_type)

    def invalidate_experiment(self, experiment_id, reason, *, actor_id,
                              actor_type="human"):
        return self._terminal(experiment_id, "growth.experiment_invalidated",
                              reason, actor_id, actor_type)

    def withdraw_experiment(self, experiment_id, reason, *, actor_id,
                            actor_type="human"):
        return self._terminal(experiment_id, "growth.experiment_withdrawn",
                              reason, actor_id, actor_type)

    def supersede_experiment(self, experiment_id, successor_id, *, actor_id,
                             actor_type="human"):
        state = self.get_state(experiment_id)
        return self._record(experiment_id, "growth.experiment_superseded",
                            actor_type=actor_type, actor_id=actor_id,
                            version=state.approved_version,
                            payload={"superseded_by": successor_id,
                                     "history_retained": True})

    def abandon_experiment(self, experiment_id, reason, *, actor_id,
                           actor_type="human"):
        return self._terminal(experiment_id, "growth.experiment_abandoned",
                              reason, actor_id, actor_type)

    # =====================================================================
    # INTEGRATIONS (references only — the other systems stay authoritative)
    # =====================================================================
    def link_hypothesis_prediction(self, experiment_id, *, claim_text: str,
                                   probability: float, resolve_by: str,
                                   entity_id: str = "experiment",
                                   decision_id=None, actor_id="founder"):
        """The hypothesis may be ledgered as a real prediction. Grading is
        the ledger's job; calibration stays behind the A-M5 gate."""
        if self.ledger_path is None:
            raise GrowthError("no prediction ledger configured")
        from intent_engine.core.prediction_ledger import record_prediction
        prediction = record_prediction(
            source="premortem", entity_id=entity_id, claim_text=claim_text,
            probability=probability, resolve_by=resolve_by,
            path=self.ledger_path, decision_id=decision_id)
        state = self.get_state(experiment_id)
        self._record(experiment_id, "growth.hypothesis_prediction_linked",
                     actor_type="human", actor_id=actor_id,
                     version=state.approved_version,
                     prediction_id=prediction.id,
                     payload={"prediction_id": prediction.id},
                     idempotency_key=(f"hypothesis-prediction:"
                                      f"{experiment_id}:{prediction.id}"))
        return prediction.id

    def request_knowledge_candidate(self, experiment_id, *, content: str,
                                    actor_id: str, actor_type="human") -> str:
        """A learning becomes a FEEDBACK record through KnowledgeService.
        It never auto-promotes; validation stays human and stays there."""
        if self.knowledge is None:
            raise GrowthError("no knowledge service configured")
        state = self.get_state(experiment_id)
        if state.review_status != "reviewed":
            raise GrowthError("a knowledge candidate requires human review "
                              "of the experiment first")
        result = self.get_result(experiment_id)
        if result["label"] in ("TOO FEW OBSERVATIONS", "INCONCLUSIVE"):
            content = (f"[{result['label']}] {content} — recorded as an "
                       "observation only; it supports no conclusion")
        feedback_id = self.knowledge.record_feedback(
            "feedback.experiment_result", content, actor_type=actor_type,
            actor_id=actor_id, source="system",
            idempotency_key=f"experiment-result:{experiment_id}")
        self._record(experiment_id, "growth.knowledge_candidate_requested",
                     actor_type=actor_type, actor_id=actor_id,
                     version=state.approved_version,
                     payload={"feedback_id": feedback_id,
                              "label_at_request": result["label"]},
                     idempotency_key=f"knowledge-candidate:{experiment_id}")
        return feedback_id

    # =====================================================================
    # READS
    # =====================================================================
    def get_state(self, experiment_id) -> ExperimentState:
        return fold_experiment(self.store.for_experiment(experiment_id),
                               validate=True)

    def get_history(self, experiment_id) -> list:
        rows = self.store.for_experiment(experiment_id)
        if not rows:
            raise KeyError(f"no such experiment: {experiment_id}")
        return rows

    def get_result(self, experiment_id) -> dict:
        rows = self.store.for_experiment(experiment_id)
        if not rows:
            raise KeyError(f"no such experiment: {experiment_id}")
        state = fold_experiment(rows)
        result = compute_result(rows, state, self.get_registration(experiment_id))
        result["experiment_id"] = experiment_id
        result["namespace"] = self.namespace
        return result

    def get_funnel(self, experiment_id) -> dict:
        rows = self.store.for_experiment(experiment_id)
        return participation_funnel(rows, fold_experiment(rows))

    def list_pending_reviews(self) -> list:
        out = []
        for experiment_id in self.store.experiment_ids():
            state = self.get_state(experiment_id)
            if state.review_status == "requested":
                out.append({"experiment_id": experiment_id,
                            "experiment_version": state.approved_version})
        return out
