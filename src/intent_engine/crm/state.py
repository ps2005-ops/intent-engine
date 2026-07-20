"""CRM state = a deterministic fold over append-only facts (T014).

Three independent axes — one simplistic funnel would lie:

    relationship: new | engaged | closed
    opportunity:  none | qualified | opportunity | proposal | won | lost
    customer:     not_customer | active | at_risk | churned

plus folded owner, last-contact timestamp, decision links, and outreach
draft states. No mutable stage field exists anywhere; terminal states
(lost / disqualified / churned) reopen ONLY through an explicit
crm.reopened event — never silently.
"""
from __future__ import annotations

from dataclasses import dataclass, field


class CRMTransitionError(ValueError):
    """An event is illegal given the current folded state."""


@dataclass(frozen=True)
class CRMState:
    relationship: str = "new"
    opportunity: str = "none"
    customer: str = "not_customer"
    owner: str | None = None
    last_contact_at: str | None = None
    decision_ids: tuple = ()
    # draft_id -> "drafted" | "approved" | "rejected" | "sent"
    outreach: dict = field(default_factory=dict)
    closed_reason: str | None = None


_CONTACT_EVENTS = {"crm.contacted", "crm.replied", "crm.meeting_booked"}
_ENGAGING_EVENTS = _CONTACT_EVENTS | {"crm.qualified",
                                      "crm.opportunity_opened",
                                      "crm.proposal_sent", "crm.won"}


def _precondition(state: CRMState, event_type: str, payload: dict
                  ) -> tuple[bool, str]:
    rel, opp, cust = state.relationship, state.opportunity, state.customer
    closed = rel == "closed"
    if event_type == "crm.prospect_created":
        return (rel == "new" and not state.last_contact_at
                and opp == "none" and cust == "not_customer",
                "an entity is created only once")
    # Observational and audit facts stay recordable on a closed
    # relationship; state-changing facts require an explicit reopen.
    _ALLOWED_WHEN_CLOSED = {
        "crm.reopened", "crm.note_added", "crm.identity_linked",
        "crm.decision_linked", "crm.decision_activity",
        "crm.report_generated", "crm.access_restricted", "crm.anonymized",
        "crm.tombstoned",
    }
    if closed and event_type not in _ALLOWED_WHEN_CLOSED:
        return (False, f"relationship is closed ({state.closed_reason}); "
                       "reopening requires an explicit crm.reopened event")
    if event_type == "crm.reopened":
        return (closed, "crm.reopened is only valid from a terminal state")
    if event_type == "crm.qualified":
        return (opp == "none", "crm.qualified requires opportunity=none")
    if event_type == "crm.disqualified":
        return (cust == "not_customer",
                "cannot disqualify an existing customer")
    if event_type == "crm.opportunity_opened":
        return (opp == "qualified",
                "opportunity requires prior qualification")
    if event_type == "crm.proposal_sent":
        return (opp == "opportunity",
                "proposal requires an opened opportunity")
    if event_type == "crm.won":
        return (opp in ("opportunity", "proposal"),
                "won requires a qualified, opened opportunity")
    if event_type == "crm.lost":
        return (opp in ("qualified", "opportunity", "proposal"),
                "lost requires an open pre-won opportunity")
    if event_type == "crm.customer_activated":
        return (opp == "won" and cust == "not_customer",
                "activation requires a won opportunity")
    if event_type == "crm.customer_at_risk":
        return (cust == "active", "at-risk requires an active customer")
    if event_type == "crm.customer_recovered":
        return (cust == "at_risk", "recovery requires an at-risk customer")
    if event_type == "crm.churned":
        return (cust in ("active", "at_risk"),
                "churn requires an existing customer")
    if event_type == "crm.owner_assigned":
        return (state.owner is None,
                "owner already assigned (use crm.owner_transferred)")
    if event_type == "crm.owner_transferred":
        return (state.owner is not None,
                "no current owner (use crm.owner_assigned)")
    # outreach wall preconditions (per draft_id)
    if event_type in ("crm.outreach_approved", "crm.outreach_rejected"):
        draft = payload.get("draft_id")
        return (state.outreach.get(draft) in ("drafted", "approved", "rejected"),
                f"no outreach draft {draft!r} to review")
    if event_type == "crm.outreach_sent":
        draft = payload.get("draft_id")
        return (state.outreach.get(draft) == "approved",
                f"outreach {draft!r} requires a prior human approval "
                "(and no later rejection) before any send")
    return (True, "")


def _apply(state: CRMState, event) -> CRMState:
    et, payload = event.event_type, event.payload
    rel, opp, cust = state.relationship, state.opportunity, state.customer
    owner, last, closed_reason = (state.owner, state.last_contact_at,
                                  state.closed_reason)
    decisions = state.decision_ids
    outreach = dict(state.outreach)

    if et in _ENGAGING_EVENTS and rel == "new":
        rel = "engaged"
    if et in _CONTACT_EVENTS:
        last = event.occurred_at
    if et == "crm.qualified":
        opp = "qualified"
    elif et == "crm.disqualified":
        rel, closed_reason = "closed", "disqualified"
    elif et == "crm.opportunity_opened":
        opp = "opportunity"
    elif et == "crm.proposal_sent":
        opp = "proposal"
    elif et == "crm.won":
        opp = "won"
    elif et == "crm.lost":
        opp, rel, closed_reason = "lost", "closed", "lost"
    elif et == "crm.customer_activated":
        cust = "active"
    elif et == "crm.customer_at_risk":
        cust = "at_risk"
    elif et == "crm.customer_recovered":
        cust = "active"
    elif et == "crm.churned":
        cust, rel, closed_reason = "churned", "closed", "churned"
    elif et == "crm.reopened":
        rel, closed_reason = "engaged", None
        if opp == "lost":
            opp = "none"
    elif et in ("crm.owner_assigned", "crm.owner_transferred"):
        owner = payload.get("owner")
    elif et == "crm.decision_linked":
        did = payload.get("decision_id") or event.decision_id
        if did and did not in decisions:
            decisions = decisions + (did,)
    elif et == "crm.outreach_drafted":
        outreach.setdefault(payload.get("draft_id"), "drafted")
    elif et == "crm.outreach_approved":
        outreach[payload.get("draft_id")] = "approved"
    elif et == "crm.outreach_rejected":
        outreach[payload.get("draft_id")] = "rejected"
    elif et == "crm.outreach_sent":
        outreach[payload.get("draft_id")] = "sent"

    return CRMState(relationship=rel, opportunity=opp, customer=cust,
                    owner=owner, last_contact_at=last,
                    decision_ids=decisions, outreach=outreach,
                    closed_reason=closed_reason)


def validate_crm_event(state: CRMState, event_type: str,
                       payload: dict) -> tuple[bool, str]:
    ok, reason = _precondition(state, event_type, payload or {})
    return ok, reason


def fold_crm(events, *, validate: bool = False) -> CRMState:
    """Fold ordered events into current state. With validate=True
    (production reads + write path), an illegal persisted history raises
    instead of folding silently — same discipline as the Decision Record."""
    state = CRMState()
    for ev in events:
        if validate:
            ok, reason = _precondition(state, ev.event_type, ev.payload or {})
            if not ok:
                raise CRMTransitionError(
                    f"stored CRM history invalid at {ev.event_type}: {reason}")
        state = _apply(state, ev)
    return state
