"""Cross-system conflict detection and the Conflict Summary (T021).

This is the thing the executive layer exists to refuse to do quietly.
When Growth reports LIKELY, Research reports CONFLICTING, Analytics
reports UNAVAILABLE, and CRM reports high urgency, the wrong output is a
blended number. Averaging destroys the disagreement, and the
disagreement is the most useful thing in the room.

So every conflict is DETECTED from recorded facts, TYPED from a closed
taxonomy, and STATED with both sides named. There is no code path in this
module that combines two conflicting inputs into one value.

`staleness_conflict` is kept apart from `timeline_conflict` deliberately:
two inputs that were true at different times and were never reconciled is
a different problem from two inputs that disagree about scheduling.
"""
from __future__ import annotations

from datetime import datetime

from intent_engine.executive.records import (
    CONFLICT_DEPENDENCY, CONFLICT_EVIDENCE, CONFLICT_KINDS, CONFLICT_METRIC,
    CONFLICT_PRIORITY, CONFLICT_RESOURCE, CONFLICT_STALENESS,
    CONFLICT_STRATEGY, CONFLICT_TIMELINE, CONFLICT_UNKNOWN, ExecutiveError,
)

CONFLICT_RULE_VERSION = "conflict_detection.v1"

# Research stances that assert a direction, and those that withhold one.
_RESEARCH_SUPPORTS = {"SUPPORTED"}
_RESEARCH_DISPUTES = {"CONTRADICTED", "MIXED", "CONFLICTING"}
_RESEARCH_WITHHOLDS = {"INSUFFICIENT", "UNKNOWN", "NOT INVESTIGATED"}

# Growth labels that assert a direction, and those that withhold one.
_GROWTH_ASSERTS = {"DIFFERENCE OBSERVED"}
_GROWTH_WITHHOLDS = {"INCONCLUSIVE", "TOO FEW OBSERVATIONS",
                     "GUARDRAIL BREACHED", "OBSERVATIONAL ONLY",
                     "STOPPED EARLY — DEGRADED"}

# How far apart two load-bearing observations may sit before the gap is a
# fact about the decision rather than noise. Stated here so it can be read
# and argued with, in the manner of T014's health window.
STALENESS_GAP_DAYS = 90


def _conflict(kind: str, sides: list, detail: str) -> dict:
    if kind not in CONFLICT_KINDS:
        raise ExecutiveError(f"unknown conflict kind: {kind!r}")
    return {"kind": kind, "sides": sides, "detail": detail,
            "rule_version": CONFLICT_RULE_VERSION}


def _age_days(a: str, b: str) -> float:
    return abs((datetime.fromisoformat(a)
                - datetime.fromisoformat(b)).total_seconds()) / 86400.0


def detect_conflicts(facts: dict) -> list:
    """Deterministic detection from recorded upstream facts.

    `facts` carries what each subsystem already reported; nothing here
    recomputes another subsystem's answer.
    """
    conflicts = []
    research = facts.get("research") or {}
    stances = list(research.get("stances") or [])
    experiments = list(facts.get("experiments") or [])
    metrics = list(facts.get("metrics") or [])
    crm = facts.get("crm") or {}

    # --- evidence conflict: research and growth point different ways ---------
    disputing = [s for s in stances if s in _RESEARCH_DISPUTES]
    asserting_experiments = [e for e in experiments
                             if e.get("label") in _GROWTH_ASSERTS]
    if disputing and asserting_experiments:
        conflicts.append(_conflict(
            CONFLICT_EVIDENCE,
            [{"subsystem": "research", "position": sorted(set(disputing))},
             {"subsystem": "growth",
              "position": sorted({e.get("label") for e in asserting_experiments})}],
            "an experiment reports an observed difference while the linked "
            "research remains unsettled; both are recorded and neither is "
            "averaged into the other"))

    # --- metric conflict: the metric that would settle it is UNAVAILABLE -----
    unavailable = [m for m in metrics if m.get("status") != "OK"]
    if unavailable and (disputing or asserting_experiments):
        conflicts.append(_conflict(
            CONFLICT_METRIC,
            [{"subsystem": "analytics",
              "position": sorted({m.get("status") for m in unavailable})},
             {"subsystem": "research/growth",
              "position": "an unsettled or asserted direction"}],
            "the metric that would settle the disagreement cannot honestly "
            "be computed, so the disagreement stands rather than being "
            "resolved by the number that is available"))

    # --- staleness conflict: two inputs true at different times --------------
    timestamps = sorted(t for t in (facts.get("input_timestamps") or []) if t)
    if len(timestamps) >= 2:
        gap = _age_days(timestamps[0], timestamps[-1])
        if gap > STALENESS_GAP_DAYS:
            conflicts.append(_conflict(
                CONFLICT_STALENESS,
                [{"subsystem": "inputs", "position": f"oldest {timestamps[0]}"},
                 {"subsystem": "inputs", "position": f"newest {timestamps[-1]}"}],
                f"load-bearing inputs sit {gap:.0f} days apart, beyond the "
                f"{STALENESS_GAP_DAYS}-day gap policy; they were true at "
                "different times and were not reconciled"))

    # --- priority conflict: urgency without supporting evidence --------------
    if crm.get("category") == "AT_RISK" and (
            not stances or set(stances) <= _RESEARCH_WITHHOLDS):
        conflicts.append(_conflict(
            CONFLICT_PRIORITY,
            [{"subsystem": "crm", "position": "AT_RISK"},
             {"subsystem": "research",
              "position": sorted(set(stances)) or "no stance recorded"}],
            "customer facts indicate urgency while the linked research "
            "withholds a direction; urgency and evidence disagree about how "
            "soon this deserves attention"))

    # --- strategy conflict: no human alignment behind urgent work ------------
    if crm.get("category") == "AT_RISK" and not facts.get("alignment"):
        conflicts.append(_conflict(
            CONFLICT_STRATEGY,
            [{"subsystem": "crm", "position": "AT_RISK"},
             {"subsystem": "strategy", "position": "no alignment declared"}],
            "urgent customer facts sit against no recorded strategic "
            "alignment; whether this belongs to a declared theme is open"))

    # --- dependency conflict -------------------------------------------------
    unmet = list(facts.get("unmet_dependencies") or [])
    if unmet and facts.get("decision_ready") is True:
        conflicts.append(_conflict(
            CONFLICT_DEPENDENCY,
            [{"subsystem": "readiness", "position": "ready"},
             {"subsystem": "graph", "position": f"{len(unmet)} unmet"}],
            "readiness reports the inputs are present while the decision "
            "graph reports unmet dependencies"))

    # --- resource conflict ---------------------------------------------------
    if facts.get("budget_declared") is False and facts.get("needs_budget"):
        conflicts.append(_conflict(
            CONFLICT_RESOURCE,
            [{"subsystem": "decision_debt", "position": "need_budget"},
             {"subsystem": "budget", "position": "none declared"}],
            "the decision waits on a budget that nobody has declared"))

    # --- timeline conflict ---------------------------------------------------
    horizon = facts.get("decision_horizon")
    if horizon in ("immediate", "short_term") and unmet:
        conflicts.append(_conflict(
            CONFLICT_TIMELINE,
            [{"subsystem": "context", "position": f"horizon {horizon}"},
             {"subsystem": "graph", "position": f"{len(unmet)} unmet "
                                                "dependencies"}],
            "the recorded horizon is near-term while the dependency graph "
            "puts other work ahead of it; the schedule and the graph "
            "disagree"))

    return sorted(conflicts, key=lambda c: (c["kind"], c["detail"]))


def conflict_summary(conflicts: list) -> dict:
    """The artifact. A summary, deliberately NOT a resolution.

    There is no combined score here, and there is no code path in this
    module that produces one: a founder reading this sees who disagrees
    and about what, which is the input to a judgment rather than a
    substitute for one.
    """
    by_kind = {}
    for conflict in conflicts:
        by_kind.setdefault(conflict["kind"], []).append(conflict)
    unresolved_kinds = sorted(by_kind)
    return {
        "rule_version": CONFLICT_RULE_VERSION,
        "total": len(conflicts),
        "kinds": unresolved_kinds,
        "by_kind": {kind: [{"sides": c["sides"], "detail": c["detail"]}
                           for c in items]
                    for kind, items in sorted(by_kind.items())},
        "conflicts": conflicts,
        "resolution": "none — a disagreement is reported, not averaged",
        "note": ("each entry names both sides and what they disagree about; "
                 "no combined figure is produced, because combining two "
                 "conflicting inputs discards the information that made "
                 "them worth reading"),
    }


def classify_unknown(sides: list, detail: str) -> dict:
    """A disagreement nobody has a rule for is still recorded, typed
    `unknown_conflict`, rather than dropped for lacking a category."""
    return _conflict(CONFLICT_UNKNOWN, sides, detail)
