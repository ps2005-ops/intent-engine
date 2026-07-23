"""V2.0 GrowthStudioService — bounded continuous planning, no external
authority. Orchestrates existing Marketing/Growth/product-analytics
capability through references; the Studio itself can neither publish nor
send anything, structurally."""
from __future__ import annotations

import hashlib

from intent_engine.agentos.identity import stable_id as _kernel_stable_id
from intent_engine.growth_studio.briefing import compose_brief
from intent_engine.growth_studio.channels import check_draft
from intent_engine.growth_studio.learning import validate_candidate
from intent_engine.growth_studio.records import (
    LOOP_STATES, LOOP_TRANSITIONS, MANUAL_PUBLICATION_ACTORS, PRODUCT_ID,
    StudioError, StudioEvent, require_scope,
)
from intent_engine.growth_studio.store import DEFAULT_STUDIO_PATH, StudioStore

EXPERIMENT_PLAN_REQUIRED = (
    "objective", "funnel_stage", "audience", "channel", "hypothesis",
    "control_or_baseline", "variable_changed", "success_metric",
    "guardrail_metric", "start_window", "end_window",
    "minimum_evidence_threshold", "stop_condition", "approval_state",
    "measurement_plan", "known_confounders",
)

MAX_MODEL_CALLS_PER_RUN = 0    # deterministic operation calls no model


class GrowthStudioService:
    def __init__(self, path=DEFAULT_STUDIO_PATH):
        self.store = StudioStore(path)
        self.model_calls = 0   # budget counter; asserted 0 in tests

    # --- plumbing -------------------------------------------------------------
    def _stable_id(self, key: str) -> str:
        return _kernel_stable_id(self.store, key)

    def _append(self, event_type, *, actor_type, actor_id, item_id=None,
                subject_type=None, subject_id=None, payload=None,
                idempotency_key=None):
        return self.store.append(StudioEvent(
            event_type=event_type, actor_type=actor_type, actor_id=actor_id,
            item_id=item_id, subject_type=subject_type, subject_id=subject_id,
            payload=dict(payload or {}), idempotency_key=idempotency_key))

    # --- loop items -----------------------------------------------------------
    def create_item(self, kind: str, payload: dict, *, actor_type="system",
                    actor_id="growth_studio", state="OBSERVED") -> str:
        if state not in LOOP_STATES:
            raise StudioError(f"unknown state {state!r}")
        require_scope(payload, kind=kind)
        stable_key = (f"item:{kind}:{payload.get('objective')}:"
                      f"{payload.get('evidence_window')}")
        item_id = self._stable_id(stable_key)
        self._append("studio.item_created", actor_type=actor_type,
                     actor_id=actor_id, item_id=item_id,
                     subject_type="item", subject_id=item_id,
                     payload={"kind": kind, "state": state, **payload},
                     idempotency_key=stable_key)
        return item_id

    def transition(self, item_id: str, to: str, *, actor_type="system",
                   actor_id="growth_studio", note="") -> None:
        current = self.store.item_state(item_id)
        if current is None:
            raise StudioError(f"no such item {item_id!r}")
        if to not in LOOP_TRANSITIONS.get(current, set()):
            raise StudioError(
                f"invalid transition {current} -> {to}")
        if to == "PUBLISHED_EXTERNALLY_RECORDED" and \
                actor_type not in MANUAL_PUBLICATION_ACTORS:
            raise StudioError(
                "APPROVED_FOR_FUTURE_EXECUTION is terminal in V2.0: only a "
                "human or an existing approved source may record an external "
                "publication — the Studio never publishes")
        self._append("studio.item_transitioned", actor_type=actor_type,
                     actor_id=actor_id, item_id=item_id,
                     subject_type="item", subject_id=item_id,
                     payload={"from": current, "to": to, "note": note},
                     idempotency_key=f"transition:{item_id}:{to}")

    # --- observations (read-side references, never rewritten events) ----------
    def record_observation(self, *, source: str, metric: str, value,
                           window: dict, evidence_refs: list,
                           availability="SUPPORTED") -> str:
        if availability == "UNAVAILABLE" and value is not None:
            raise StudioError("an UNAVAILABLE metric cannot carry a value — "
                              "unavailable is not zero")
        stable_key = (f"obs:{source}:{metric}:{window.get('start')}:"
                      f"{window.get('end')}")
        obs_id = self._stable_id(stable_key)
        self._append("studio.observation_recorded", actor_type="system",
                     actor_id="growth_studio", subject_type="observation",
                     subject_id=obs_id,
                     payload={"source": source, "metric": metric,
                              "value": value, "window": dict(window),
                              "evidence_refs": list(evidence_refs),
                              "availability": availability,
                              "authority": "reference to product/marketing "
                                           "analytics — raw events are never "
                                           "reinterpreted here"},
                     idempotency_key=stable_key)
        return obs_id

    # --- drafts (must already satisfy channel policy) --------------------------
    def reference_draft(self, item_id: str, *, channel: str, body: str,
                        statements: list, campaign_id: str) -> None:
        violations = check_draft(channel=channel, body=body,
                                 statements=statements)
        if violations:
            raise StudioError(f"channel policy violations: {violations}")
        self._append("studio.draft_referenced", actor_type="system",
                     actor_id="growth_studio", item_id=item_id,
                     subject_type="draft", subject_id=campaign_id,
                     payload={"channel": channel,
                              "campaign_id": campaign_id,
                              "statement_classes": [s["class"]
                                                    for s in statements],
                              "body_sha256": hashlib.sha256(
                                  body.encode()).hexdigest()},
                     idempotency_key=f"draft:{item_id}:{campaign_id}")

    # --- experiments ----------------------------------------------------------
    def plan_experiment(self, item_id: str, plan: dict) -> str:
        missing = [f for f in EXPERIMENT_PLAN_REQUIRED
                   if plan.get(f) in (None, "")]
        if missing:
            raise StudioError(
                f"ExperimentPlan incomplete (no 'try three posts and see "
                f"what works'): missing {missing}")
        stable_key = f"plan:{item_id}"
        plan_id = self._stable_id(stable_key)
        self._append("studio.experiment_planned", actor_type="system",
                     actor_id="growth_studio", item_id=item_id,
                     subject_type="experiment_plan", subject_id=plan_id,
                     payload=dict(plan),
                     idempotency_key=stable_key)
        return plan_id

    # --- learning -------------------------------------------------------------
    def propose_learning(self, item_id: str, candidate: dict, *,
                         experiment: dict) -> str:
        validate_candidate(candidate, experiment=experiment)
        stable_key = f"learning:{item_id}:{candidate['statement']}"
        lid = self._stable_id(stable_key)
        self._append("studio.learning_proposed", actor_type="system",
                     actor_id="growth_studio", item_id=item_id,
                     subject_type="learning", subject_id=lid,
                     payload={"candidate": dict(candidate),
                              "experiment_id": experiment.get("experiment_id"),
                              "status": "PROPOSED — not memory until a human "
                                        "accepts it"},
                     idempotency_key=stable_key)
        return lid

    def accept_learning(self, learning_id: str, *, actor_id: str,
                        actor_type="human", note="") -> None:
        if actor_type != "human":
            raise StudioError("only a human may accept a learning into "
                              "durable growth memory")
        proposed = [r for r in self.store.read_all()
                    if r.event_type == "studio.learning_proposed"
                    and r.subject_id == learning_id]
        if not proposed:
            raise StudioError(f"no proposed learning {learning_id!r}")
        self._append("studio.learning_accepted", actor_type="human",
                     actor_id=actor_id, item_id=proposed[-1].item_id,
                     subject_type="learning", subject_id=learning_id,
                     payload={"note": note,
                              "candidate": proposed[-1].payload["candidate"]},
                     idempotency_key=f"learning-accept:{learning_id}")

    def reject_learning(self, learning_id: str, reason: str, *,
                        actor_id: str) -> None:
        self._append("studio.learning_rejected", actor_type="human",
                     actor_id=actor_id, subject_type="learning",
                     subject_id=learning_id, payload={"reason": reason},
                     idempotency_key=f"learning-reject:{learning_id}")

    # --- inert execution manifests for V2.5 ------------------------------------
    def create_manifest(self, item_id: str, *, channel: str,
                        approved_draft_ref: str) -> str:
        state = self.store.item_state(item_id)
        if state != "APPROVED_FOR_FUTURE_EXECUTION":
            raise StudioError("a manifest may exist only for an approved "
                              f"item (state is {state})")
        stable_key = f"manifest:{item_id}"
        mid = self._stable_id(stable_key)
        self._append("studio.manifest_created", actor_type="system",
                     actor_id="growth_studio", item_id=item_id,
                     subject_type="manifest", subject_id=mid,
                     payload={"channel": channel,
                              "approved_draft_ref": approved_draft_ref,
                              "inert": True,
                              "authority": "V2.5 input only — the Studio has "
                                           "no execution surface"},
                     idempotency_key=stable_key)
        return mid

    def record_publication(self, item_id: str, *, actor_type: str,
                           actor_id: str, channel: str, url_or_ref: str,
                           published_at: str) -> None:
        """Manual/approved-source recording of an EXTERNAL publication."""
        self.transition(item_id, "PUBLISHED_EXTERNALLY_RECORDED",
                        actor_type=actor_type, actor_id=actor_id,
                        note=f"published externally: {channel}")
        self._append("studio.publication_recorded", actor_type=actor_type,
                     actor_id=actor_id, item_id=item_id,
                     subject_type="publication", subject_id=item_id,
                     payload={"channel": channel, "ref": url_or_ref,
                              "published_at": published_at},
                     idempotency_key=f"pub:{item_id}")

    # --- the daily briefing (deterministic, idempotent, budgeted) --------------
    def produce_briefing(self, *, as_of_date: str, sections: dict,
                         actor_id="growth_studio") -> dict:
        if self.model_calls > MAX_MODEL_CALLS_PER_RUN:
            raise StudioError("model-call budget exceeded")
        brief = compose_brief(as_of_date=as_of_date, sections=sections)
        stable_key = f"briefing:{PRODUCT_ID}:{as_of_date}"
        brief_id = self._stable_id(stable_key)
        self._append("studio.briefing_produced", actor_type="system",
                     actor_id=actor_id, subject_type="briefing",
                     subject_id=brief_id,
                     payload=brief,
                     idempotency_key=stable_key)
        return {"briefing_id": brief_id, **brief}
