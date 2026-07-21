"""MarketingService (T017) — the only write path for marketing workflow
artifacts, and the place every reused gate is enforced.

Reused, never reimplemented:
  * claim gate  -> the Company Event System's claim.review_requested /
                   human claim.approved / claim.rejected facts
  * quote gate  -> KnowledgeService.can_publish_quote (exact text + use)
  * CRM         -> CRMService reads for audience and relationship context
  * analytics   -> read-only MetricResults with their status preserved
  * knowledge   -> KnowledgeService items, active versions only
  * feedback    -> KnowledgeService.record_feedback (marketing never writes
                   the feedback store directly)
"""
from __future__ import annotations

from pathlib import Path

from intent_engine.core.decision_ids import new_ulid
from intent_engine.marketing.audience import select_audience
from intent_engine.marketing.drafts import validate_draft
from intent_engine.marketing.evidence import assert_scope_supports, resolve_evidence
from intent_engine.marketing.records import (
    CHANNELS, HUMAN_ONLY_EVENTS, MARKER_UNAVAILABLE, MarketingError,
    MarketingRow, json_normalize,
)
from intent_engine.marketing.state import (
    MarketingState, fold_marketing, validate_marketing_event,
)
from intent_engine.marketing.store import MarketingStore

DEFAULT_MARKETING_PATH = Path("data/marketing.jsonl")


class MarketingService:
    def __init__(self, path=DEFAULT_MARKETING_PATH, *, crm_service=None,
                 knowledge_service=None, analytics_service=None,
                 decision_service=None, event_bus=None, metric_lookup=None):
        self.store = MarketingStore(path)
        self.crm = crm_service
        self.knowledge = knowledge_service
        self.analytics = analytics_service
        self.decisions = decision_service
        self.bus = event_bus
        self.metric_lookup = metric_lookup

    # --- internal write path --------------------------------------------------
    def _record(self, campaign_id, event_type, *, actor_type, actor_id,
                source="cli", payload=None, artifact_id=None, revision_id=None,
                occurred_at=None, idempotency_key=None, **refs) -> MarketingRow:
        if event_type in HUMAN_ONLY_EVENTS and actor_type != "human":
            raise MarketingError(
                f"{event_type} is a human wall transition; "
                f"actor_type={actor_type!r} cannot emit it (systems may "
                "draft and request review; they may not approve)")
        kwargs = dict(event_type=event_type, campaign_id=campaign_id,
                      actor_type=actor_type, actor_id=actor_id, source=source,
                      payload=json_normalize(dict(payload or {})),
                      artifact_id=artifact_id, revision_id=revision_id,
                      idempotency_key=idempotency_key, **refs)
        if occurred_at is not None:
            kwargs["occurred_at"] = occurred_at
        candidate = MarketingRow(**kwargs)
        if idempotency_key:
            existing = self.store.find_by_idempotency_key(idempotency_key)
            if existing is not None:
                if existing.content_fingerprint() != candidate.content_fingerprint():
                    raise ValueError(
                        f"idempotency_key {idempotency_key!r} was already "
                        "used for different content")
                return existing
        state = self.get_state(campaign_id) if event_type != \
            "marketing.campaign_created" else MarketingState()
        ok, reason = validate_marketing_event(state, event_type,
                                              payload or {}, revision_id)
        if not ok:
            raise MarketingError(f"{event_type}: {reason}")
        return self.store.append(candidate)

    def _stable_artifact_id(self, idempotency_key: str) -> str:
        """A retry of the same fact IS the same artifact: reuse the original
        id so the store's fingerprint check compares like-for-like instead
        of seeing a fresh ULID as 'different content'."""
        existing = self.store.find_by_idempotency_key(idempotency_key)
        return existing.artifact_id if existing is not None else new_ulid()

    # --- campaign -------------------------------------------------------------
    def create_campaign(self, name: str, *, objective: str, channel: str,
                        owner: str, actor_type: str = "human",
                        actor_id: str = "founder", idempotency_key=None) -> str:
        if channel not in CHANNELS:
            raise MarketingError(f"unknown channel: {channel!r}")
        payload = {"name": name, "objective": objective, "channel": channel,
                   "owner": owner}
        if idempotency_key:
            existing = self.store.find_by_idempotency_key(idempotency_key)
            if existing is not None:
                # A retry must be the SAME campaign; reusing the key for
                # different content is a caller bug, not a silent no-op.
                if existing.payload != json_normalize(payload):
                    raise ValueError(
                        f"idempotency_key {idempotency_key!r} was already "
                        "used for different content")
                return existing.campaign_id
        campaign_id = new_ulid()
        self._record(campaign_id, "marketing.campaign_created",
                     actor_type=actor_type, actor_id=actor_id,
                     idempotency_key=idempotency_key, payload=payload)
        return campaign_id

    def archive_campaign(self, campaign_id: str, *, actor_id: str,
                         actor_type: str = "human") -> MarketingRow:
        return self._record(campaign_id, "marketing.campaign_archived",
                            actor_type=actor_type, actor_id=actor_id,
                            payload={})

    # --- audience -------------------------------------------------------------
    def define_audience(self, campaign_id: str, *, as_of: str,
                        actor_type: str = "system",
                        actor_id: str = "marketing_agent", **criteria) -> dict:
        if self.crm is None:
            self._record(campaign_id, "marketing.audience_resolution_failed",
                         actor_type=actor_type, actor_id=actor_id,
                         payload={"reason": "no CRM service configured",
                                  "status": MARKER_UNAVAILABLE})
            raise MarketingError("audience selection requires a CRM service")
        selection = select_audience(self.crm, as_of=as_of, **criteria)
        key = f"audience:{campaign_id}:{as_of}"
        self._record(campaign_id, "marketing.audience_defined",
                     actor_type=actor_type, actor_id=actor_id,
                     artifact_id=self._stable_artifact_id(key),
                     payload=selection, idempotency_key=key)
        return selection

    # --- evidence -------------------------------------------------------------
    def attach_evidence(self, campaign_id: str, evidence: dict, *,
                        claim_text: str = "", actor_type: str = "system",
                        actor_id: str = "marketing_agent") -> dict:
        try:
            snapshot = resolve_evidence(
                evidence, decision_service=self.decisions,
                event_store=(self.bus.store if self.bus else None),
                knowledge_service=self.knowledge, crm_service=self.crm,
                metric_lookup=self.metric_lookup)
            if claim_text:
                assert_scope_supports(snapshot, claim_text)
        except MarketingError as exc:
            self._record(campaign_id, "marketing.evidence_rejected",
                         actor_type=actor_type, actor_id=actor_id,
                         payload={"evidence": evidence, "reason": str(exc)})
            raise
        self._record(campaign_id, "marketing.evidence_attached",
                     actor_type=actor_type, actor_id=actor_id,
                     payload=snapshot,
                     idempotency_key=(f"evidence:{campaign_id}:"
                                      f"{snapshot['evidence_type']}:"
                                      f"{snapshot['source_id']}"))
        return snapshot

    def get_evidence(self, campaign_id: str) -> list:
        return [r.payload for r in self.store.for_campaign(campaign_id)
                if r.event_type == "marketing.evidence_attached"]

    # --- briefs ---------------------------------------------------------------
    def create_brief(self, campaign_id: str, *, message: str,
                     call_to_action: str, permitted_claims=None,
                     prohibited_claims=None, quotes=None,
                     actor_type: str = "system",
                     actor_id: str = "marketing_agent") -> str:
        """Deterministic assembly from campaign inputs + attached evidence.
        No model call: the brief is a structured contract, not prose."""
        rows = self.store.for_campaign(campaign_id)
        created = next((r for r in rows
                        if r.event_type == "marketing.campaign_created"), None)
        if created is None:
            raise KeyError(f"no such campaign: {campaign_id}")
        audience = next((r.payload for r in reversed(rows)
                         if r.event_type == "marketing.audience_defined"), None)
        evidence = self.get_evidence(campaign_id)
        revision_id = new_ulid()
        brief = {
            "revision": 1,
            "campaign_objective": created.payload["objective"],
            "channel": created.payload["channel"],
            "audience": audience or MARKER_UNAVAILABLE,
            "primary_message": message,
            "call_to_action": call_to_action,
            "permitted_claims": sorted(permitted_claims or []),
            "prohibited_claims": sorted(prohibited_claims or []),
            "evidence": evidence,
            "quotes": list(quotes or []),
            "limitations": [e.get("limitations") for e in evidence
                            if e.get("limitations")],
            "unavailable": ([] if audience else ["audience not defined"]),
            "review_requirements": [
                "any non-descriptive claim requires human claim approval",
                "any quote requires exact consent for the intended use",
                "publishing handoff requires human approval",
            ],
        }
        self._record(campaign_id, "marketing.brief_created",
                     actor_type=actor_type, actor_id=actor_id,
                     artifact_id=revision_id, revision_id=revision_id,
                     payload=brief)
        return revision_id

    def revise_brief(self, campaign_id: str, *, actor_type: str = "system",
                     actor_id: str = "marketing_agent", **changes) -> str:
        current = self.get_brief(campaign_id)
        revision_id = new_ulid()
        payload = {**current, **changes, "revision": current["revision"] + 1}
        self._record(campaign_id, "marketing.brief_revised",
                     actor_type=actor_type, actor_id=actor_id,
                     artifact_id=revision_id, revision_id=revision_id,
                     payload=payload)
        return revision_id

    def get_brief(self, campaign_id: str) -> dict:
        rows = [r for r in self.store.for_campaign(campaign_id)
                if r.event_type in ("marketing.brief_created",
                                    "marketing.brief_revised")]
        if not rows:
            raise KeyError(f"no brief for campaign {campaign_id}")
        return {**rows[-1].payload, "revision_id": rows[-1].revision_id}

    # --- drafts ---------------------------------------------------------------
    def create_draft(self, campaign_id: str, body: str, *,
                     brief_revision_id: str, quotes=None,
                     actor_type: str = "agent",
                     actor_id: str = "content_agent",
                     idempotency_key=None) -> str:
        return self._write_draft(campaign_id, body, brief_revision_id,
                                 quotes, actor_type, actor_id,
                                 "marketing.draft_created", idempotency_key)

    def revise_draft(self, campaign_id: str, body: str, *,
                     brief_revision_id: str, quotes=None,
                     actor_type: str = "agent",
                     actor_id: str = "content_agent") -> str:
        return self._write_draft(campaign_id, body, brief_revision_id,
                                 quotes, actor_type, actor_id,
                                 "marketing.draft_revised", None)

    def _write_draft(self, campaign_id, body, brief_revision_id, quotes,
                     actor_type, actor_id, event_type, idempotency_key) -> str:
        brief = self.get_brief(campaign_id)
        if brief["revision_id"] != brief_revision_id:
            raise MarketingError(
                f"a draft must reference the EXACT current brief revision "
                f"({brief['revision_id']}), got {brief_revision_id}")
        revision_id = new_ulid()
        result = validate_draft(
            body, quotes=quotes, evidence_snapshots=brief["evidence"],
            knowledge_service=self.knowledge,
            approved_claim_ids=self.approved_claim_ids(campaign_id))
        self._record(campaign_id, event_type, actor_type=actor_type,
                     actor_id=actor_id, artifact_id=revision_id,
                     revision_id=revision_id, idempotency_key=idempotency_key,
                     payload={"body": body,
                              "brief_revision_id": brief_revision_id,
                              "quotes": list(quotes or []),
                              "validation": result.as_payload()})
        for claim in result.claim_references:
            if claim["requires_review"]:
                self._record(campaign_id, "marketing.claim_flagged",
                             actor_type="system", actor_id="draft_validator",
                             artifact_id=revision_id,
                             payload={"claim_id": claim["claim_id"],
                                      "claim_class": claim["claim_class"],
                                      "text": claim["text"]},
                             idempotency_key=(f"claim-flag:{revision_id}:"
                                              f"{claim['claim_id']}"))
        return revision_id

    def get_draft(self, campaign_id: str, revision_id=None) -> dict:
        rows = [r for r in self.store.for_campaign(campaign_id)
                if r.event_type in ("marketing.draft_created",
                                    "marketing.draft_revised")]
        if not rows:
            raise KeyError(f"no draft for campaign {campaign_id}")
        if revision_id is not None:
            for r in rows:
                if r.revision_id == revision_id:
                    return {**r.payload, "revision_id": revision_id}
            raise KeyError(f"no draft revision {revision_id}")
        return {**rows[-1].payload, "revision_id": rows[-1].revision_id}

    def revalidate_draft(self, campaign_id: str) -> dict:
        draft = self.get_draft(campaign_id)
        brief = self.get_brief(campaign_id)
        result = validate_draft(
            draft["body"], quotes=draft["quotes"],
            evidence_snapshots=brief["evidence"],
            knowledge_service=self.knowledge,
            approved_claim_ids=self.approved_claim_ids(campaign_id))
        return result.as_payload()

    # --- the claim gate (reused, never reimplemented) -------------------------
    def request_claim_review(self, campaign_id: str, claim_id: str,
                             claim_text: str, *, actor_type: str = "system",
                             actor_id: str = "marketing_agent") -> None:
        """Requests review through the EXISTING company-event claim gate.
        Only a human may then publish `claim.approved` for this claim id."""
        if self.bus is None:
            raise MarketingError("claim review requires the company event bus")
        self.bus.publish(
            "claim.review_requested", subject_type="claim",
            subject_id=claim_id, producer="approval_wall",
            actor_type=actor_type, actor_id=actor_id, source="system",
            payload={"campaign_id": campaign_id, "claim_text": claim_text},
            idempotency_key=f"claim-review:{campaign_id}:{claim_id}")
        self._record(campaign_id, "marketing.claim_review_requested",
                     actor_type=actor_type, actor_id=actor_id,
                     payload={"claim_id": claim_id})

    def approved_claim_ids(self, campaign_id: str = None) -> set:
        """Human `claim.approved` facts from the company event log, minus
        any later rejection. Marketing reads this gate; it never writes an
        approval."""
        if self.bus is None:
            return set()
        approved, rejected = set(), set()
        for ev in self.bus.store.read_all():
            if ev.event_type == "claim.approved" and ev.actor_type == "human":
                approved.add(ev.subject_id)
            elif ev.event_type == "claim.rejected":
                rejected.add(ev.subject_id)
        return approved - rejected

    # --- review ---------------------------------------------------------------
    def request_draft_review(self, campaign_id: str, revision_id: str, *,
                             actor_type: str = "system",
                             actor_id: str = "marketing_agent") -> MarketingRow:
        return self._record(campaign_id, "marketing.draft_review_requested",
                            actor_type=actor_type, actor_id=actor_id,
                            revision_id=revision_id, payload={})

    def approve_draft(self, campaign_id: str, revision_id: str, *,
                      actor_id: str, comment: str = "",
                      actor_type: str = "human") -> MarketingRow:
        return self._record(campaign_id, "marketing.draft_approved",
                            actor_type=actor_type, actor_id=actor_id,
                            revision_id=revision_id,
                            payload={"comment": comment})

    def reject_draft(self, campaign_id: str, revision_id: str, *,
                     actor_id: str, comment: str = "",
                     actor_type: str = "human") -> MarketingRow:
        return self._record(campaign_id, "marketing.draft_rejected",
                            actor_type=actor_type, actor_id=actor_id,
                            revision_id=revision_id,
                            payload={"comment": comment})

    # --- publishing handoff ---------------------------------------------------
    def create_handoff(self, campaign_id: str, *, channel: str,
                       scheduled_for=None, external_target: str = "",
                       actor_type: str = "system",
                       actor_id: str = "marketing_agent") -> str:
        state = self.get_state(campaign_id)
        draft = self.get_draft(campaign_id)
        blockers = self.handoff_blockers(campaign_id)
        if blockers:
            self._record(campaign_id, "marketing.handoff_blocked",
                         actor_type="system", actor_id="handoff_gate",
                         payload={"blocking_issues": blockers})
            raise MarketingError(f"handoff blocked: {blockers}")
        handoff_id = new_ulid()
        self._record(campaign_id, "marketing.publish_handoff_created",
                     actor_type=actor_type, actor_id=actor_id,
                     artifact_id=handoff_id,
                     revision_id=state.approved_draft_revision,
                     payload={"channel": channel,
                              "scheduled_for": scheduled_for,
                              "external_target": external_target,
                              "draft_revision_id": state.approved_draft_revision,
                              "approved_quotes": draft["quotes"],
                              "required_disclosures": [
                                  "no accuracy is claimed"],
                              "handoff_status": "awaiting_human_approval"})
        return handoff_id

    def handoff_blockers(self, campaign_id: str) -> list:
        """Every reason this campaign may NOT be queued for publication.
        Re-checked at approval time — a revocation after handoff creation
        still blocks."""
        blockers = []
        state = self.get_state(campaign_id)
        superseded = (state.approved_draft_revision is not None
                      and state.approved_draft_revision
                      != state.current_draft_revision)
        if superseded:
            blockers.append("a later draft revision invalidated the approval")
        elif state.draft_status != "approved":
            blockers.append("draft is not human-approved")
        validation = self.revalidate_draft(campaign_id)
        blockers.extend(validation["blocking_issues"])
        return blockers

    def approve_handoff(self, campaign_id: str, handoff_id: str, *,
                        actor_id: str, actor_type: str = "human") -> MarketingRow:
        blockers = self.handoff_blockers(campaign_id)
        if blockers:
            self._record(campaign_id, "marketing.handoff_blocked",
                         actor_type="system", actor_id="handoff_gate",
                         artifact_id=handoff_id,
                         payload={"blocking_issues": blockers})
            raise MarketingError(f"handoff blocked: {blockers}")
        return self._record(campaign_id, "marketing.publish_handoff_approved",
                            actor_type=actor_type, actor_id=actor_id,
                            artifact_id=handoff_id, payload={})

    def reject_handoff(self, campaign_id: str, handoff_id: str, *,
                       actor_id: str, reason: str = "",
                       actor_type: str = "human") -> MarketingRow:
        return self._record(campaign_id, "marketing.publish_handoff_rejected",
                            actor_type=actor_type, actor_id=actor_id,
                            artifact_id=handoff_id,
                            payload={"reason": reason})

    def get_handoff(self, handoff_id: str) -> dict:
        rows = self.store.for_artifact(handoff_id)
        created = next((r for r in rows
                        if r.event_type == "marketing.publish_handoff_created"),
                       None)
        if created is None:
            raise KeyError(f"no such handoff: {handoff_id}")
        state = dict(created.payload)
        for r in rows:
            if r.event_type == "marketing.publish_handoff_approved":
                state.update(handoff_status="approved", human_approver=r.actor_id,
                             approved_at=r.occurred_at)
            elif r.event_type == "marketing.publish_handoff_rejected":
                state.update(handoff_status="rejected")
        return state

    # --- publication recording (observational only) ---------------------------
    def record_publication(self, campaign_id: str, handoff_id: str, *,
                           external_platform: str, external_post_id: str,
                           occurred_at: str, actor_id: str,
                           actor_type: str = "human") -> MarketingRow:
        """Records that an EXTERNAL system published something. This
        repository never publishes; a publication fact must be supplied."""
        state = self.get_state(campaign_id)
        if state.approved_handoff_id != handoff_id:
            raise MarketingError(
                "publication must reference the APPROVED handoff for this "
                "campaign — this system never publishes, it only records "
                "an externally supplied result")
        if not external_platform or not external_post_id:
            raise MarketingError("external platform and post id are required "
                                 "— a publication fact is never assumed")
        return self._record(
            campaign_id, "marketing.publish_recorded", actor_type=actor_type,
            actor_id=actor_id, artifact_id=handoff_id, occurred_at=occurred_at,
            payload={"external_platform": external_platform,
                     "external_post_id": external_post_id,
                     "recorded_by": "external result supplied to the "
                                    "repository; not performed by it"},
            idempotency_key=f"publication:{external_platform}:{external_post_id}")

    # --- performance observations ---------------------------------------------
    def record_performance_observation(
            self, campaign_id: str, *, external_post_id: str,
            observation_source: str, window_start: str, window_end: str,
            metrics: dict, limitations: str = "", actor_id: str = "founder",
            actor_type: str = "human") -> str:
        if not observation_source:
            raise MarketingError("an observation source is mandatory")
        if not window_start or not window_end:
            raise MarketingError("an observation window is mandatory")
        for key, value in (metrics or {}).items():
            if value is not None and not isinstance(value, (int, float)):
                raise MarketingError(f"metric {key!r} must be numeric or null "
                                     "(null means UNAVAILABLE, not zero)")
        key = (f"observation:{external_post_id}:{window_start}:"
               f"{window_end}:{observation_source}")
        observation_id = self._stable_artifact_id(key)
        normalized = {k: (v if v is not None else MARKER_UNAVAILABLE)
                      for k, v in (metrics or {}).items()}
        self._record(
            campaign_id, "marketing.performance_observation_recorded",
            actor_type=actor_type, actor_id=actor_id,
            artifact_id=observation_id,
            payload={"external_post_id": external_post_id,
                     "observation_source": observation_source,
                     "window": {"start": window_start, "end": window_end},
                     "metrics": normalized,
                     "limitations": limitations or
                     "observed counts only; no causal attribution and no "
                     "revenue attribution is inferred from these numbers"},
            idempotency_key=(f"observation:{external_post_id}:"
                             f"{window_start}:{window_end}:"
                             f"{observation_source}"))
        return observation_id

    def observation_ratio(self, campaign_id: str, numerator_key: str,
                          denominator_key: str) -> dict:
        obs = [r.payload for r in self.store.for_campaign(campaign_id)
               if r.event_type == "marketing.performance_observation_recorded"]
        if not obs:
            return {"status": MARKER_UNAVAILABLE, "value": None,
                    "reason": "no performance observation recorded"}
        metrics = obs[-1]["metrics"]
        num, den = metrics.get(numerator_key), metrics.get(denominator_key)
        if not isinstance(den, (int, float)) or den == 0 \
                or not isinstance(num, (int, float)):
            return {"status": MARKER_UNAVAILABLE, "value": None,
                    "reason": "missing or empty denominator — a ratio cannot "
                              "honestly be computed"}
        return {"status": "OK", "value": round(num / den, 4),
                "numerator": num, "denominator": den}

    # --- feedback loop (through KnowledgeService ONLY) ------------------------
    def link_feedback(self, campaign_id: str, observation_id: str, *,
                      content: str, actor_id: str = "founder",
                      actor_type: str = "human") -> str:
        if self.knowledge is None:
            raise MarketingError("feedback requires the knowledge service")
        feedback_id = self.knowledge.record_feedback(
            "feedback.internal_review", content, actor_type=actor_type,
            actor_id=actor_id, source="crm",
            idempotency_key=f"marketing-observation:{observation_id}")
        self._record(campaign_id, "marketing.feedback_linked",
                     actor_type=actor_type, actor_id=actor_id,
                     artifact_id=observation_id,
                     payload={"feedback_id": feedback_id},
                     idempotency_key=f"feedback-link:{observation_id}")
        return feedback_id

    # --- reads ----------------------------------------------------------------
    def get_state(self, campaign_id: str) -> MarketingState:
        return fold_marketing(self.store.for_campaign(campaign_id),
                              validate=True)

    def get_history(self, campaign_id: str) -> list:
        rows = self.store.for_campaign(campaign_id)
        if not rows:
            raise KeyError(f"no such campaign: {campaign_id}")
        return rows

    def list_pending_reviews(self) -> list:
        out = []
        for campaign_id in sorted({r.campaign_id
                                   for r in self.store.read_all()}):
            state = self.get_state(campaign_id)
            if state.draft_status == "review_requested":
                out.append({"campaign_id": campaign_id,
                            "draft_revision_id": state.current_draft_revision})
        return out
