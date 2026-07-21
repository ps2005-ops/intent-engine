"""Folded marketing workflow state (T017).

Independent axes — collapsing them would let one green light imply
another. Nothing here is a stored status field; every value is folded
from the append-only history, and illegal transitions are rejected at
write time and re-checked on validated reads.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from intent_engine.marketing.records import MarketingError


@dataclass(frozen=True)
class MarketingState:
    campaign_status: str = "draft"          # draft | active | archived
    brief_status: str = "missing"           # missing | drafted | revised
    draft_status: str = "missing"           # missing | drafted | review_requested
                                            # | approved | rejected
    publishing_status: str = "not_ready"    # not_ready | handoff_ready
                                            # | approved_for_handoff
                                            # | recorded_as_published
    observation_status: str = "none"        # none | recorded
    current_owner: str | None = None
    current_brief_revision: str | None = None
    current_draft_revision: str | None = None
    approved_draft_revision: str | None = None
    approved_handoff_id: str | None = None
    audience_defined: bool = False
    # claim_id -> "flagged" | "review_requested"; company-event approvals
    # live in the EVENT log, not here (one claim gate, not two).
    claims: dict = field(default_factory=dict)


def _precondition(state: MarketingState, event_type: str, payload: dict,
                  revision_id: str | None) -> tuple[bool, str]:
    if event_type == "marketing.campaign_created":
        return (state.campaign_status == "draft" and not state.audience_defined
                and state.brief_status == "missing",
                "a campaign is created once")
    if state.campaign_status == "archived" and event_type not in (
            "marketing.performance_observation_recorded",
            "marketing.feedback_linked"):
        return (False, "campaign is archived")
    if event_type == "marketing.audience_defined":
        return (True, "")
    if event_type in ("marketing.brief_created", "marketing.brief_revised"):
        if event_type == "marketing.brief_created":
            return (state.brief_status == "missing",
                    "a brief is created once; later versions are revisions")
        return (state.brief_status != "missing", "no brief to revise")
    if event_type == "marketing.draft_created":
        if state.brief_status == "missing":
            return (False, "a draft requires an existing brief")
        return (state.draft_status == "missing",
                "a draft is created once; later versions are revisions")
    if event_type == "marketing.draft_revised":
        return (state.draft_status != "missing", "no draft to revise")
    if event_type == "marketing.draft_review_requested":
        return (state.draft_status in ("drafted", "review_requested",
                                       "rejected"),
                "review requires a current draft revision")
    if event_type in ("marketing.draft_approved", "marketing.draft_rejected"):
        if state.draft_status != "review_requested":
            return (False, "approval requires a prior review request")
        if revision_id != state.current_draft_revision:
            return (False, "approval must bind to the EXACT current draft "
                           f"revision ({state.current_draft_revision})")
        return (True, "")
    if event_type == "marketing.publish_handoff_created":
        if state.draft_status != "approved":
            return (False, "a publishing handoff requires an approved draft")
        if state.approved_draft_revision != state.current_draft_revision:
            return (False, "the current draft revision is not the approved "
                           "one — a later revision invalidated the approval")
        return (True, "")
    if event_type in ("marketing.publish_handoff_approved",
                      "marketing.publish_handoff_rejected"):
        return (state.publishing_status in ("handoff_ready",
                                            "approved_for_handoff"),
                "no publishing handoff to review")
    if event_type == "marketing.publish_recorded":
        return (state.publishing_status == "approved_for_handoff",
                "publication may only be recorded against an APPROVED "
                "handoff — this system never publishes")
    if event_type == "marketing.performance_observation_recorded":
        return (state.publishing_status == "recorded_as_published",
                "a performance observation requires a recorded publication")
    return (True, "")


def _apply(state: MarketingState, row) -> MarketingState:
    et, payload = row.event_type, row.payload
    d = dict(campaign_status=state.campaign_status,
             brief_status=state.brief_status, draft_status=state.draft_status,
             publishing_status=state.publishing_status,
             observation_status=state.observation_status,
             current_owner=state.current_owner,
             current_brief_revision=state.current_brief_revision,
             current_draft_revision=state.current_draft_revision,
             approved_draft_revision=state.approved_draft_revision,
             approved_handoff_id=state.approved_handoff_id,
             audience_defined=state.audience_defined,
             claims=dict(state.claims))

    if et == "marketing.campaign_created":
        d["campaign_status"] = "active"
        d["current_owner"] = payload.get("owner")
    elif et == "marketing.campaign_archived":
        d["campaign_status"] = "archived"
    elif et == "marketing.audience_defined":
        d["audience_defined"] = True
    elif et == "marketing.brief_created":
        d["brief_status"] = "drafted"
        d["current_brief_revision"] = row.revision_id
    elif et == "marketing.brief_revised":
        d["brief_status"] = "revised"
        d["current_brief_revision"] = row.revision_id
    elif et in ("marketing.draft_created", "marketing.draft_revised"):
        d["draft_status"] = "drafted"
        d["current_draft_revision"] = row.revision_id
    elif et == "marketing.draft_review_requested":
        d["draft_status"] = "review_requested"
    elif et == "marketing.draft_approved":
        d["draft_status"] = "approved"
        d["approved_draft_revision"] = row.revision_id
    elif et == "marketing.draft_rejected":
        d["draft_status"] = "rejected"
    elif et == "marketing.publish_handoff_created":
        d["publishing_status"] = "handoff_ready"
    elif et == "marketing.publish_handoff_approved":
        d["publishing_status"] = "approved_for_handoff"
        d["approved_handoff_id"] = row.artifact_id
    elif et == "marketing.publish_handoff_rejected":
        d["publishing_status"] = "not_ready"
    elif et == "marketing.publish_recorded":
        d["publishing_status"] = "recorded_as_published"
    elif et == "marketing.performance_observation_recorded":
        d["observation_status"] = "recorded"
    elif et == "marketing.claim_flagged":
        d["claims"][payload["claim_id"]] = "flagged"
    elif et == "marketing.claim_review_requested":
        d["claims"][payload["claim_id"]] = "review_requested"
    return MarketingState(**d)


def validate_marketing_event(state: MarketingState, event_type: str,
                             payload: dict, revision_id=None):
    return _precondition(state, event_type, payload or {}, revision_id)


def fold_marketing(rows, *, validate: bool = False) -> MarketingState:
    state = MarketingState()
    for row in rows:
        if validate:
            ok, reason = _precondition(state, row.event_type,
                                       row.payload or {}, row.revision_id)
            if not ok:
                raise MarketingError(
                    f"stored marketing history invalid at {row.event_type}: "
                    f"{reason}")
        state = _apply(state, row)
    return state
