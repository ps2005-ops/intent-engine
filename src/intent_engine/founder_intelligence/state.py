"""Folded run state and transition validation (T023.5).

The intelligence run is an append-only state machine. Transitions are
deterministic and idempotent: a retry that re-emits the current state is a
no-op, and only the legal forward transitions in `records._ALLOWED` are
permitted. A run is scoped to one company; there is no global mutable
"current company".
"""
from __future__ import annotations

from dataclasses import dataclass, field

from intent_engine.founder_intelligence.records import (
    COMPLETE, CREATED, FounderIntelligenceError, TERMINAL_STATES,
    transition_allowed,
)


@dataclass(frozen=True)
class RunState:
    run_id: str | None = None
    company_domain: str | None = None
    status: str = CREATED
    identity: dict | None = None
    ingested_sources: tuple = ()
    assembled_sections: tuple = ()
    snapshot_id: str | None = None
    limitations: tuple = ()
    feedback: tuple = ()


@dataclass(frozen=True)
class WorkspaceRuns:
    runs: dict = field(default_factory=dict)   # run_id -> RunState


def _apply(state: WorkspaceRuns, row) -> WorkspaceRuns:
    et, p = row.event_type, row.payload or {}
    runs = {k: v for k, v in state.runs.items()}
    rid = row.run_id
    run = runs.get(rid, RunState(run_id=rid, company_domain=row.company_domain))

    def _replace(**over):
        base = dict(run_id=run.run_id, company_domain=run.company_domain,
                    status=run.status, identity=run.identity,
                    ingested_sources=run.ingested_sources,
                    assembled_sections=run.assembled_sections,
                    snapshot_id=run.snapshot_id, limitations=run.limitations,
                    feedback=run.feedback)
        base.update(over)
        return RunState(**base)

    if et == "fi.run_created":
        run = _replace(status="CREATED",
                       company_domain=row.company_domain or run.company_domain)
    elif et == "fi.run_transitioned":
        run = _replace(status=p.get("to"))
    elif et == "fi.identity_resolved":
        run = _replace(identity=p.get("identity"))
    elif et == "fi.source_ingested":
        run = _replace(ingested_sources=run.ingested_sources
                       + (p.get("source_id"),))
    elif et == "fi.section_assembled":
        run = _replace(assembled_sections=run.assembled_sections
                       + (p.get("section_kind"),))
    elif et == "fi.run_completed":
        run = _replace(status="COMPLETE" if p.get("complete") else "PARTIAL",
                       limitations=tuple(p.get("limitations", [])))
    elif et == "fi.run_rejected":
        run = _replace(status="REJECTED")
    elif et == "fi.run_failed":
        run = _replace(status="FAILED")
    elif et == "fi.snapshot_captured":
        run = _replace(snapshot_id=row.subject_id)
    elif et == "fi.feedback_recorded":
        run = _replace(feedback=run.feedback + (p.get("feedback_id"),))

    runs[rid] = run
    return WorkspaceRuns(runs=runs)


def _precondition(state: WorkspaceRuns, row) -> tuple[bool, str]:
    et, p = row.event_type, row.payload or {}
    rid = row.run_id
    if et == "fi.run_created":
        return (rid not in state.runs, "a run is created once")
    if et == "fi.run_transitioned":
        run = state.runs.get(rid)
        if run is None:
            return (False, "cannot transition an uncreated run")
        nxt = p.get("to")
        if nxt == run.status:
            return (True, "")            # idempotent retry
        if not transition_allowed(run.status, nxt):
            return (False, f"illegal transition {run.status} -> {nxt}")
        return (True, "")
    if et in ("fi.section_assembled", "fi.identity_resolved",
              "fi.source_ingested", "fi.run_completed"):
        run = state.runs.get(rid)
        if run is None:
            return (False, f"{et} on an uncreated run")
        if run.status in TERMINAL_STATES and et != "fi.run_completed":
            return (False, f"{et} on a terminal run ({run.status})")
    return (True, "")


def validate_fi_event(state: WorkspaceRuns, row) -> tuple[bool, str]:
    return _precondition(state, row)


def fold_runs(rows, *, validate: bool = False) -> WorkspaceRuns:
    state = WorkspaceRuns()
    for row in rows:
        if validate:
            ok, reason = _precondition(state, row)
            if not ok:
                raise FounderIntelligenceError(
                    f"stored run history is invalid at {row.event_type}: "
                    f"{reason}")
        state = _apply(state, row)
    return state
