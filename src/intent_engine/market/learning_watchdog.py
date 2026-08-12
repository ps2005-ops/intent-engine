"""Is the market intelligence system still LEARNING — not merely still running.

RELATIONSHIP TO `health.py`
----------------------------
`health.check()` answers the operational question: did the scheduler fire, is
storage writable, is the git tree what we think it is. This module answers the
different question that the 2026-08-12 incident exposed: a system can pass
every operational check, complete every cycle, and still be learning nothing —
or be learning fine while an observer reads the wrong store and concludes it
is dead.

So this watchdog does NOT re-derive operational state. It consumes
`learning_status.collect()`, which resolves every path through the
system-of-record declaration, and it consumes `health.check()` for the
scheduler/storage arm. One monitoring lineage, two questions.

SILENCE IS NOT ONE THING
-------------------------
The hardest requirement here is that quiet has many causes and they demand
opposite responses. "The world did nothing" is healthy. "We found nothing
because every source refused us" is an outage. "We found plenty and learned
nothing" is a product defect. A watchdog that collapses these into one alert
teaches an operator to ignore it, so `SILENCE_STATES` is a closed vocabulary
and every quiet verdict names which one it is.

NO NATURAL-LANGUAGE-ONLY ALERTS
--------------------------------
Every alert is a record with an id, a severity, the observed value, the
expected condition, and a next action. Prose belongs in `detail`, never in
place of the fields, because an alert that cannot be diffed between two runs
cannot be tracked to resolution.
"""
from __future__ import annotations

import dataclasses
import datetime
from typing import Dict, List, Optional

from . import learning_status as LS
from . import system_of_record as SOR

CONTRACT = "market_learning_watchdog.v1"

# --- severity (closed) -------------------------------------------------------
CRITICAL = "CRITICAL"      # the system of record is wrong or not writing
WARNING = "WARNING"        # learning is degrading or a channel has stalled
INFO = "INFO"              # a state worth recording, not worth waking anyone
SEVERITIES = (CRITICAL, WARNING, INFO)

# --- silence states (closed, §6) ---------------------------------------------
#: Why the system is quiet. These are NOT interchangeable and the whole point
#: of the vocabulary is that an operator acts differently on each.
NOTHING_NEW_IN_WORLD = "NOTHING_NEW_IN_WORLD"
NO_EVIDENCE_FOUND = "NO_EVIDENCE_FOUND"
SOURCE_DEGRADED = "SOURCE_DEGRADED"
RETRIEVAL_FAILED = "RETRIEVAL_FAILED"
EVIDENCE_FOUND_NO_LEARNING = "EVIDENCE_FOUND_NO_LEARNING"
LEARNING_OCCURRED = "LEARNING_OCCURRED"
SUBSYSTEM_NOT_RUNNING = "SUBSYSTEM_NOT_RUNNING"
BLOCKED_EXTERNAL = "BLOCKED_EXTERNAL"
BLOCKED_DATA = "BLOCKED_DATA"
SILENCE_STATES = (NOTHING_NEW_IN_WORLD, NO_EVIDENCE_FOUND, SOURCE_DEGRADED,
                  RETRIEVAL_FAILED, EVIDENCE_FOUND_NO_LEARNING,
                  LEARNING_OCCURRED, SUBSYSTEM_NOT_RUNNING, BLOCKED_EXTERNAL,
                  BLOCKED_DATA)

# --- alert ids (closed) ------------------------------------------------------
NO_NEW_CYCLE = "NO_NEW_CYCLE"
CYCLE_FAILED = "CYCLE_FAILED"
STORE_NOT_WRITING = "STORE_NOT_WRITING"
WRONG_DATA_ROOT = "WRONG_DATA_ROOT"
KNOWLEDGE_EFFECT_ZERO = "KNOWLEDGE_EFFECT_ZERO"
HIGH_ACTIVITY_LOW_LEARNING = "HIGH_ACTIVITY_LOW_LEARNING"
EVIDENCE_ZERO_UNEXPECTED = "EVIDENCE_ZERO_UNEXPECTED"
UNSUPERVISED_NOT_RUNNING = "UNSUPERVISED_NOT_RUNNING"
PROSPECTIVE_RL_NOT_RUNNING = "PROSPECTIVE_RL_NOT_RUNNING"
RL_DATA_NOT_ACCUMULATING = "RL_DATA_NOT_ACCUMULATING"
BELIEF_REVISION_STALE = "BELIEF_REVISION_STALE"
FOUNDER_CONSUMPTION_STALE = "FOUNDER_CONSUMPTION_STALE"
POPULATION_MISMATCH = "POPULATION_MISMATCH"
UNDATABLE_BY_READER = "UNDATABLE_BY_READER"
LEGACY_PIPELINE_ACTIVE_AS_CANONICAL = "LEGACY_PIPELINE_ACTIVE_AS_CANONICAL"
CREDITS_EXHAUSTED = "CREDITS_EXHAUSTED"

#: How long a channel may be quiet before quiet becomes a finding. These are
#: OPERATING thresholds, not truths: a belief channel that is quiet for two
#: days during a slow news week is healthy, and one quiet for a fortnight is
#: not, and no amount of reasoning picks the boundary for us.
STALE_CYCLE_HOURS = 36
STALE_FOUNDER_DAYS = 7
STALE_BELIEF_DAYS = 14
#: Below this share of knowledge effects changing anything, over a large
#: enough denominator, the engine is busy rather than learning.
LOW_LEARNING_SHARE = 0.05
MIN_EFFECTS_FOR_VERDICT = 40


@dataclasses.dataclass(frozen=True)
class Alert:
    """One machine-readable finding. `detail` explains; it never replaces."""
    alert_id: str
    severity: str
    subsystem: str
    observed: str
    expected: str
    suggested_next_action: str
    first_seen: str = ""
    last_seen: str = ""
    runtime_sha: str = ""
    data_root: str = ""
    evidence: Dict = dataclasses.field(default_factory=dict)
    detail: str = ""

    def to_row(self) -> dict:
        return dataclasses.asdict(self)


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _hours_since(stamp: str, now=None) -> Optional[float]:
    if not stamp:
        return None
    text = str(stamp).replace("Z", "+00:00")
    try:
        moment = datetime.datetime.fromisoformat(text)
    except ValueError:
        try:
            moment = datetime.datetime.fromisoformat(text[:10])
        except ValueError:
            return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=datetime.timezone.utc)
    reference = now or datetime.datetime.now(datetime.timezone.utc)
    return (reference - moment).total_seconds() / 3600.0


def _silence(status: dict) -> dict:
    """Why is it quiet — one of nine answers, never a bare zero.

    Ordered from the causes an operator must act on to the ones they must
    not. `LEARNING_OCCURRED` is checked first because the commonest reason a
    watchdog is wrong is that it declares an outage during a healthy run.
    """
    knowledge = status["knowledge"]
    evidence = status["channels"].get("evidence", {})
    effects = knowledge["effects_in_window"]

    if knowledge["changed_something"]:
        return {"state": LEARNING_OCCURRED,
                "reason": (f"{knowledge['changed_something']} of {effects} "
                           f"knowledge effect(s) changed something")}
    if effects:
        return {"state": EVIDENCE_FOUND_NO_LEARNING,
                "reason": (f"{effects} knowledge effect(s), none of which "
                           f"changed anything — evidence arrived and the "
                           f"model did not move")}
    if evidence.get("status") == LS.NO_PRODUCER:
        return {"state": SUBSYSTEM_NOT_RUNNING,
                "reason": "no evidence has ever been written to this ledger"}
    if evidence.get("in_window"):
        return {"state": EVIDENCE_FOUND_NO_LEARNING,
                "reason": (f"{evidence['in_window']} evidence row(s) arrived "
                           f"and produced no knowledge effect in window")}
    if evidence.get("status") == LS.UNDATABLE:
        return {"state": BLOCKED_DATA,
                "reason": ("evidence rows exist but cannot be placed in a "
                           "window by this reader")}
    return {"state": NOTHING_NEW_IN_WORLD,
            "reason": ("the cycle ran and no new evidence arrived; this is "
                       "the healthy quiet state and is not an outage")}


def evaluate(root=None, window: str = "7d", *, status=None,
             founder_last_write: str = "", now=None) -> dict:
    """Typed alerts over the canonical learning picture.

    `status` may be injected so the negative controls can drive exact states
    without a runtime tree; production passes nothing and it is collected.
    """
    status = status or LS.collect(root=root, window=window)
    sor = status["system_of_record"]
    stamp = _now()
    common = {"first_seen": stamp, "last_seen": stamp,
              "runtime_sha": sor.get("runtime_sha", ""),
              "data_root": sor.get("ledger", "")}
    alerts: List[Alert] = []

    def add(**kwargs):
        alerts.append(Alert(**{**common, **kwargs}))

    # --- the store itself ----------------------------------------------------
    if not sor.get("ledger_exists"):
        add(alert_id=WRONG_DATA_ROOT, severity=CRITICAL,
            subsystem="system_of_record",
            observed=f"no ledger at {sor.get('ledger')}",
            expected="the canonical learning ledger exists and is readable",
            suggested_next_action=("check --root; the declaration resolves "
                                   "stores relative to the runtime root"),
            evidence={"ledger": sor.get("ledger")})
        # Every downstream number would be a zero produced by absence.
        return _wrap(alerts, status, {"state": SUBSYSTEM_NOT_RUNNING,
                                      "reason": "no canonical ledger"})

    if not status["ledger_rows"]["all_time"]:
        add(alert_id=STORE_NOT_WRITING, severity=CRITICAL,
            subsystem="learning_ledger", observed="0 rows all time",
            expected="the canonical ledger accumulates rows",
            suggested_next_action="run a cycle and confirm it writes",
            evidence={"ledger": sor.get("ledger")})

    # --- cycles --------------------------------------------------------------
    cycles = status["cycles"]
    age = _hours_since(cycles.get("last") or "", now)
    if age is not None and age > STALE_CYCLE_HOURS:
        add(alert_id=NO_NEW_CYCLE, severity=CRITICAL, subsystem="scheduler",
            observed=f"last cycle {age:.0f}h ago ({cycles.get('last')})",
            expected=f"a cycle within {STALE_CYCLE_HOURS}h",
            suggested_next_action=("check launchd jobs and the runtime "
                                   "checkout the scheduler points at"),
            evidence={"last": cycles.get("last"),
                      "status": cycles.get("last_status")})
    if str(cycles.get("last_status") or "").upper().startswith("FAIL"):
        add(alert_id=CYCLE_FAILED, severity=CRITICAL, subsystem="scheduler",
            observed=f"last cycle status {cycles.get('last_status')}",
            expected="COMPLETED, or an explicit SKIPPED reason",
            suggested_next_action="read the cycle record's failing step",
            evidence={"last": cycles.get("last")})

    # --- learning quality ----------------------------------------------------
    knowledge = status["knowledge"]
    effects = knowledge["effects_in_window"]
    share = knowledge["changing_share"]
    if effects >= MIN_EFFECTS_FOR_VERDICT and share is not None:
        if share < LOW_LEARNING_SHARE:
            add(alert_id=HIGH_ACTIVITY_LOW_LEARNING, severity=WARNING,
                subsystem="knowledge",
                observed=f"{knowledge['changed_something']} of {effects} "
                         f"effects changed anything ({share:.1%})",
                expected=f"at or above {LOW_LEARNING_SHARE:.0%}",
                suggested_next_action=("check evidence independence and "
                                       "duplicate rate before adding sources"),
                evidence={"effects": effects, "share": share,
                          "by_type": knowledge["by_effect_type"]})
    elif effects == 0 and status["channels"].get(
            "evidence", {}).get("in_window"):
        add(alert_id=KNOWLEDGE_EFFECT_ZERO, severity=WARNING,
            subsystem="knowledge",
            observed="evidence arrived and produced no knowledge effect",
            expected="evidence is evaluated against beliefs",
            suggested_next_action="check the knowledge step ran in the cycle",
            evidence={"evidence_in_window": status["channels"]["evidence"][
                "in_window"]})

    # --- channels that must be running --------------------------------------
    for channel, alert_id, subsystem in (
            ("active_learning", PROSPECTIVE_RL_NOT_RUNNING, "active_learning"),
            ("evidence", EVIDENCE_ZERO_UNEXPECTED, "evidence")):
        report = status["channels"].get(channel, {})
        if report.get("status") == LS.NO_PRODUCER:
            add(alert_id=alert_id, severity=CRITICAL, subsystem=subsystem,
                observed=f"{channel} has never written a row",
                expected=f"{channel} writes rows during a cycle",
                suggested_next_action=(f"confirm the {channel} step is wired "
                                       f"into the canonical cycle"),
                evidence={"channel": report})

    # --- RL data must ACCUMULATE, not merely exist ---------------------------
    active = status["active_learning"]
    if not active.get("zero_result_captured"):
        add(alert_id=RL_DATA_NOT_ACCUMULATING, severity=WARNING,
            subsystem="active_learning",
            observed="no NO_RESULT/FAILED/REFUSED outcome has ever been "
                     "recorded",
            expected="the policy dataset records unsuccessful actions too",
            suggested_next_action=("verify failure paths are reachable "
                                   "through the production seam; a "
                                   "success-only dataset cannot support "
                                   "off-policy evaluation"),
            evidence={"outcomes": active.get("outcomes_all_time")})

    integrity = active.get("acquisition_counter_integrity") or {}
    if integrity.get("state") == "POPULATION_MISMATCH":
        add(alert_id=POPULATION_MISMATCH, severity=WARNING,
            subsystem="acquisition",
            observed=f"{integrity.get('rows_where_retrieved_exceeds_attempted')}"
                     f" of {integrity.get('repaired_rows')} repaired rows "
                     f"have retrieved > attempted",
            expected="numerator and denominator share a population",
            suggested_next_action=("the producer regressed after the "
                                   "2026-08-12 repair; check "
                                   "counterparty_sources.acquire"),
            evidence=integrity)
    elif integrity.get("state") == LS.LEGACY_INCOMPATIBLE_POPULATION:
        # NOT a defect and NOT an alert to act on: these rows predate the
        # counter repair and are correctly excluded from any yield. Raising a
        # WARNING for history that can never change would train an operator to
        # ignore this alert id.
        add(alert_id=POPULATION_MISMATCH, severity=INFO,
            subsystem="acquisition",
            observed=f"all {integrity.get('legacy_rows')} row(s) predate the "
                     f"counter repair",
            expected="repaired rows accumulate as new cycles run",
            suggested_next_action=("none; legacy rows are excluded from "
                                   "yields rather than rewritten"),
            evidence=integrity)

    # --- reader coverage -----------------------------------------------------
    undatable = status.get("undated_record_types") or {}
    if undatable:
        add(alert_id=UNDATABLE_BY_READER, severity=INFO, subsystem="reader",
            observed=f"{len(undatable)} record type(s) carry no resolvable "
                     f"timestamp",
            expected="every record type can be placed in a window",
            suggested_next_action=("add the producer's timestamp field to "
                                   "learning_status._LEARNED_AT_FIELDS"),
            evidence={"types": sorted(undatable)})

    # --- the incident itself, as a standing check ---------------------------
    for legacy in status.get("legacy_pipelines", []):
        if legacy.get("scheduled"):
            add(alert_id=LEGACY_PIPELINE_ACTIVE_AS_CANONICAL,
                severity=CRITICAL, subsystem="system_of_record",
                observed=f"{legacy.get('id')} is scheduled",
                expected="only the canonical entrypoint is scheduled",
                suggested_next_action="unschedule the legacy pipeline",
                evidence=legacy)

    # --- founder freshness ---------------------------------------------------
    if founder_last_write:
        days = (_hours_since(founder_last_write, now) or 0) / 24.0
        if days > STALE_FOUNDER_DAYS:
            add(alert_id=FOUNDER_CONSUMPTION_STALE, severity=WARNING,
                subsystem="founder_transport",
                observed=f"founder export last written {days:.1f} days ago",
                expected=f"within {STALE_FOUNDER_DAYS} days of market learning",
                suggested_next_action=("measure the seam: export not called, "
                                       "nothing eligible, or founder not "
                                       "reading — do not touch the file"),
                evidence={"founder_last_write": founder_last_write})

    return _wrap(alerts, status, _silence(status))


def _wrap(alerts, status, silence) -> dict:
    by_severity = {s: [a.to_row() for a in alerts if a.severity == s]
                   for s in SEVERITIES}
    return {
        "contract": CONTRACT,
        "generated_at": _now(),
        "system_of_record": SOR.canonical_id(),
        "window": status.get("window"),
        # A watchdog that says only "healthy" teaches nobody anything. The
        # silence state says WHY it is quiet even when nothing is wrong.
        "silence": silence,
        "alerts": [a.to_row() for a in alerts],
        "counts": {s: len(by_severity[s]) for s in SEVERITIES},
        "status": (CRITICAL if by_severity[CRITICAL]
                   else WARNING if by_severity[WARNING] else "OK"),
    }


def render(report: dict) -> str:
    out = ["=" * 72,
           f"MARKET LEARNING WATCHDOG — {report['status']}",
           "=" * 72,
           f"  silence   {report['silence']['state']}",
           f"            {report['silence']['reason']}",
           f"  alerts    {report['counts'][CRITICAL]} critical, "
           f"{report['counts'][WARNING]} warning, "
           f"{report['counts'][INFO]} info",
           ""]
    if not report["alerts"]:
        out.append("  no alerts")
    for alert in report["alerts"]:
        out += [f"  [{alert['severity']}] {alert['alert_id']} "
                f"({alert['subsystem']})",
                f"      observed  {alert['observed']}",
                f"      expected  {alert['expected']}",
                f"      next      {alert['suggested_next_action']}"]
    out.append("=" * 72)
    return "\n".join(out)
