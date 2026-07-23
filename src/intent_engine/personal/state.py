"""Folded workspace state (T023) — three memory lifecycles, kept apart.

    ephemeral session context   the current conversation window (turns)
    durable founder memory       goals, pinned findings, investigations,
                                 preferences — created ONLY by an explicit
                                 founder act
    generated artifacts          briefs and report drafts the workspace
                                 assembled

The rule the fold enforces: a conversation turn does not become durable
memory merely because it was said. Durable memory appears in the fold only
when the founder pins, saves a goal, opens an investigation, or preserves a
preference. The workspace may PROPOSE a memory candidate (recorded as a
candidate), and it stays a candidate until a person promotes it.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from intent_engine.personal.records import PersonalError


@dataclass(frozen=True)
class WorkspaceState:
    sessions: dict = field(default_factory=dict)        # session_id -> record
    open_session: str | None = None
    turns: dict = field(default_factory=dict)           # session_id -> [turns]
    # durable founder memory
    goals: dict = field(default_factory=dict)
    pins: dict = field(default_factory=dict)
    investigations: dict = field(default_factory=dict)
    preferences: dict = field(default_factory=dict)
    memory_candidates: tuple = ()                        # proposed, not promoted
    # generated artifacts
    briefs: dict = field(default_factory=dict)
    reports: dict = field(default_factory=dict)

    def durable_memory(self) -> dict:
        return {"goals": dict(self.goals), "pins": dict(self.pins),
                "investigations": dict(self.investigations),
                "preferences": dict(self.preferences)}

    def open_investigations(self) -> list:
        return sorted((i for i in self.investigations.values()
                       if i["status"] == "open"),
                      key=lambda i: i["investigation_id"])


def _precondition(state: WorkspaceState, row) -> tuple[bool, str]:
    et = row.event_type
    if et == "personal.session_opened":
        return (state.open_session is None,
                "a session is already open; close it first")
    if et == "personal.session_closed":
        return (state.open_session == row.session_id, "no such open session")
    if et == "personal.turn_recorded":
        return (state.open_session == row.session_id,
                "a turn belongs to the open session")
    if et in ("personal.memory_pinned", "personal.goal_saved",
              "personal.investigation_opened", "personal.preference_saved"):
        # founder-only is enforced at validate(); nothing else to gate
        return (True, "")
    if et == "personal.investigation_closed":
        iid = (row.payload or {}).get("investigation_id")
        return (iid in state.investigations,
                "cannot close an investigation that was never opened")
    return (True, "")


def _apply(state: WorkspaceState, row) -> WorkspaceState:
    et, p = row.event_type, row.payload or {}
    d = dict(
        sessions=dict(state.sessions), open_session=state.open_session,
        turns={k: list(v) for k, v in state.turns.items()},
        goals=dict(state.goals), pins=dict(state.pins),
        investigations={k: dict(v) for k, v in state.investigations.items()},
        preferences=dict(state.preferences),
        memory_candidates=state.memory_candidates,
        briefs=dict(state.briefs), reports=dict(state.reports))

    if et == "personal.session_opened":
        d["sessions"][row.session_id] = {"session_id": row.session_id,
                                         "opened_at": row.occurred_at}
        d["open_session"] = row.session_id
        d["turns"].setdefault(row.session_id, [])
    elif et == "personal.session_closed":
        d["open_session"] = None
    elif et == "personal.turn_recorded":
        turns = list(d["turns"].get(row.session_id, []))
        turns.append({"turn_id": row.subject_id,
                      "question": p.get("question"),
                      "intent": p.get("intent")})
        d["turns"][row.session_id] = turns
    elif et == "personal.memory_pinned":
        d["pins"][row.subject_id] = {"pin_id": row.subject_id,
                                     "reference": p.get("reference"),
                                     "note": p.get("note", "")}
    elif et == "personal.goal_saved":
        d["goals"][row.subject_id] = {"goal_id": row.subject_id,
                                      "goal": p.get("goal")}
    elif et == "personal.investigation_opened":
        d["investigations"][row.subject_id] = {
            "investigation_id": row.subject_id, "status": "open",
            "question": p.get("question"),
            "origin_reference": p.get("origin_reference")}
    elif et == "personal.investigation_closed":
        iid = p.get("investigation_id")
        if iid in d["investigations"]:
            d["investigations"][iid] = {**d["investigations"][iid],
                                        "status": "closed",
                                        "resolution": p.get("resolution", "")}
    elif et == "personal.preference_saved":
        d["preferences"][row.subject_id] = {"preference_id": row.subject_id,
                                            "preference": p.get("preference")}
    elif et == "personal.memory_candidate_proposed":
        d["memory_candidates"] = state.memory_candidates + (
            {"candidate_id": row.subject_id, "kind": p.get("kind"),
             "detail": p.get("detail", "")},)
    elif et == "personal.brief_assembled":
        d["briefs"][row.subject_id] = {"brief_id": row.subject_id,
                                       "as_of": p.get("as_of")}
    elif et == "personal.report_drafted":
        d["reports"][row.subject_id] = {"report_id": row.subject_id,
                                        "profile": p.get("profile"),
                                        "as_of": p.get("as_of")}
    return WorkspaceState(**d)


def validate_personal_event(state: WorkspaceState, row) -> tuple[bool, str]:
    return _precondition(state, row)


def fold_personal(rows, *, validate: bool = False) -> WorkspaceState:
    state = WorkspaceState()
    for row in rows:
        if validate:
            ok, reason = _precondition(state, row)
            if not ok:
                raise PersonalError(
                    f"stored workspace history is invalid at {row.event_type}:"
                    f" {reason}")
        state = _apply(state, row)
    return state
