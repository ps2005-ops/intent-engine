"""Folded research state and the four-layer structural rules (T019).

The five separation rules, enforced at write time and re-checked on read:

    one Request may have many Plans (a revision is a new version)
    one Plan may have many Sessions
    one Session produces exactly one Evidence Package
    one Package may yield at most one Conclusion per plan version
    a Conclusion never exists without a Package; a Package never exists
        without an APPROVED Plan
"""
from __future__ import annotations

from dataclasses import dataclass, field

from intent_engine.research.records import ResearchError

REQUIRED_PLAN_PARTS = ("goal", "questions", "evidence_requirements",
                       "stopping_conditions", "failure_definition",
                       "tool_allowlist", "budget")

# Facts that may only occur under an approved plan version.
PLAN_BOUND_EVENTS = {
    "research.session_started", "research.source_registered",
    "research.evidence_indexed", "research.claim_indexed",
    "research.relation_indexed", "research.package_assembled",
    "research.conclusion_drafted", "research.package_snapshot",
    "research.graph_snapshot",
}


@dataclass(frozen=True)
class ResearchState:
    plan_status: str = "none"            # none | drafted | submitted
                                         # | approved | rejected
    approved_plan_version: int | None = None
    draft_plan_version: int = 1
    plan_parts: frozenset = frozenset()
    open_session: str | None = None
    sessions: tuple = ()
    packages: tuple = ()
    session_packages: dict = field(default_factory=dict)  # session -> package
    package_conclusions: dict = field(default_factory=dict)  # package -> conc
    review_status: str = "none"          # none | requested | reviewed
    reused_from: str | None = None


def _precondition(state: ResearchState, event_type: str, payload: dict,
                  version, session_id) -> tuple[bool, str]:
    if event_type == "research.request_created":
        return (state.plan_status == "none" and not state.sessions,
                "a request is created once")

    if event_type == "research.plan_drafted":
        return (state.plan_status in ("none", "rejected", "approved"),
                "a plan is already in progress")
    if event_type == "research.plan_submitted":
        missing = [p for p in REQUIRED_PLAN_PARTS if p not in state.plan_parts]
        if missing:
            return (False, f"plan incomplete: missing {missing}")
        return (state.plan_status == "drafted", "no drafted plan to submit")
    if event_type in ("research.plan_approved", "research.plan_rejected"):
        return (state.plan_status == "submitted",
                "no submitted plan to review")
    if event_type == "research.plan_amended":
        return (state.plan_status == "approved",
                "only an approved plan can be amended")

    if event_type in PLAN_BOUND_EVENTS:
        if state.approved_plan_version is None:
            return (False, f"{event_type} requires an APPROVED research plan "
                           "— collection before approval is exactly what "
                           "pre-registration prevents")
        if version != state.approved_plan_version:
            return (False, f"{event_type} must bind to the approved plan "
                           f"version ({state.approved_plan_version}), got "
                           f"{version}")

    if event_type == "research.session_started":
        return (state.open_session is None,
                "a session is already open; close it first")
    if event_type == "research.session_closed":
        return (state.open_session is not None, "no open session")
    if event_type in ("research.source_registered", "research.evidence_indexed",
                      "research.claim_indexed", "research.relation_indexed"):
        return (state.open_session is not None,
                f"{event_type} requires an open research session")

    if event_type == "research.package_assembled":
        if session_id is None:
            return (False, "a package must reference its session")
        if session_id in state.session_packages:
            return (False, "one session produces exactly ONE package")
        return (True, "")

    if event_type == "research.conclusion_drafted":
        package_id = payload.get("package_id")
        if package_id not in state.packages:
            return (False, "a conclusion requires an existing package")
        if package_id in state.package_conclusions:
            return (False, "one package yields at most ONE conclusion per "
                           "plan version")
        return (True, "")

    if event_type == "research.reviewed":
        return (state.review_status == "requested",
                "review requires a prior review request")
    return (True, "")


def _apply(state: ResearchState, row) -> ResearchState:
    et, payload = row.event_type, row.payload or {}
    d = dict(plan_status=state.plan_status,
             approved_plan_version=state.approved_plan_version,
             draft_plan_version=state.draft_plan_version,
             plan_parts=set(state.plan_parts),
             open_session=state.open_session, sessions=state.sessions,
             packages=state.packages,
             session_packages=dict(state.session_packages),
             package_conclusions=dict(state.package_conclusions),
             review_status=state.review_status, reused_from=state.reused_from)

    if et == "research.request_reused":
        d["reused_from"] = payload.get("reused_from")
    elif et == "research.plan_drafted":
        d["plan_status"] = "drafted"
        d["plan_parts"] = set(payload.get("parts", []))
    elif et == "research.plan_submitted":
        d["plan_status"] = "submitted"
    elif et == "research.plan_approved":
        d["plan_status"] = "approved"
        d["approved_plan_version"] = d["draft_plan_version"]
    elif et == "research.plan_rejected":
        d["plan_status"] = "rejected"
    elif et == "research.plan_amended":
        d["draft_plan_version"] = state.draft_plan_version + 1
        d["approved_plan_version"] = d["draft_plan_version"]
        d["plan_parts"] = set(payload.get("parts", state.plan_parts))
    elif et == "research.session_started":
        d["open_session"] = row.session_id
        d["sessions"] = state.sessions + (row.session_id,)
    elif et == "research.session_closed":
        d["open_session"] = None
    elif et == "research.package_assembled":
        d["packages"] = state.packages + (row.subject_id,)
        d["session_packages"][row.session_id] = row.subject_id
    elif et == "research.conclusion_drafted":
        d["package_conclusions"][payload.get("package_id")] = row.subject_id
    elif et == "research.review_requested":
        d["review_status"] = "requested"
    elif et == "research.reviewed":
        d["review_status"] = "reviewed"

    d["plan_parts"] = frozenset(d["plan_parts"])
    return ResearchState(**d)


def validate_research_event(state, event_type, payload, version=None,
                            session_id=None):
    return _precondition(state, event_type, payload or {}, version, session_id)


def fold_research(rows, *, validate: bool = False) -> ResearchState:
    state = ResearchState()
    for row in rows:
        if validate:
            ok, reason = _precondition(state, row.event_type, row.payload or {},
                                       row.plan_version, row.session_id)
            if not ok:
                raise ResearchError(
                    f"stored research history invalid at {row.event_type}: "
                    f"{reason}")
        state = _apply(state, row)
    return state
