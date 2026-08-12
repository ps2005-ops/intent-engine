"""Daily, weekly and monthly learning products, from canonical stores only.

WHY THESE ARE ARTIFACTS AND NOT PRINTOUTS
------------------------------------------
"What did the market intelligence system learn this week?" was once answered by
reading a twenty-three-day-stale legacy database. The fix so far has been a
status command; this module is the durable half. A persisted report is what
lets next week say "that source degradation lasted three days and recovered" —
a claim no amount of live querying can make, because by then the transient
state is gone.

JSON IS AUTHORITATIVE. The prose projection is a view over it, generated
deterministically. No LLM selects what counts as a learning: an external model
may phrase already-chosen canonical facts later, but the selection is code, so
the report is identical when the provider is out of credits.

ACTIVITY IS NOT LEARNING
-------------------------
Every count here is paired with the quality question. `evidence_rows` sits next
to `evidence_that_changed_something`; a row count is never offered as a proxy
for learning, because "120 rows accepted" and "105 of them changed nothing" are
the same cycle described twice and only the second is about learning.

WEEKLY IS A SYNTHESIS, NOT A SUM
---------------------------------
Adding seven daily belief counts would count one belief that was touched on
five days as five beliefs. Weekly aggregates over IDENTITY — distinct belief,
expectation and thesis ids — and only sums quantities that are genuinely
additive (rows arrived, effects attributed).
"""
from __future__ import annotations

import collections
import datetime
import json
import pathlib
from typing import Dict, List, Optional

from . import learning_status as LS
from . import learning_watchdog as LW
from . import system_of_record as SOR

CONTRACT = "market_learning_report.v1"

DAY, WEEK, MONTH = "day", "week", "month"
PERIODS = (DAY, WEEK, MONTH)

#: Where the authoritative artifacts live, under the runtime root.
DAILY_DIR = "reports/learning/daily"
WEEKLY_DIR = "reports/learning/weekly"
MONTHLY_DIR = "reports/learning/monthly"
ALERTS_DIR = "reports/learning/alerts"

UNMEASURABLE = "UNMEASURABLE"
UNAVAILABLE = "UNAVAILABLE"

#: Effect types that moved the model. Imported in spirit from
#: `learning_status`, restated nowhere: one definition of "changed something".
CHANGING = LS.CHANGING_EFFECTS


def _ratio(numerator, denominator):
    return round(numerator / denominator, 4) if denominator else UNMEASURABLE


def _bounds(period: str, as_of: datetime.date) -> tuple:
    """[start, end] inclusive, and whether the period is still open.

    An incomplete period is marked, never presented as a finished one: a
    month-to-date figure shown as a month is how a report claims more history
    than it has.
    """
    if period == DAY:
        return as_of, as_of, False
    if period == WEEK:
        start = as_of - datetime.timedelta(days=as_of.weekday())
        end = start + datetime.timedelta(days=6)
        return start, end, end > as_of
    start = as_of.replace(day=1)
    nxt = (start + datetime.timedelta(days=32)).replace(day=1)
    end = nxt - datetime.timedelta(days=1)
    return start, end, end > as_of


def _rows_in(ledger: List[dict], start, end) -> List[dict]:
    kept = []
    for row in ledger:
        stamp, _ = LS._learned_at(row)
        if stamp and start.isoformat() <= stamp <= end.isoformat():
            kept.append(row)
    return kept


def _by_kind(rows) -> Dict[str, List[dict]]:
    out: Dict[str, List[dict]] = collections.defaultdict(list)
    for row in rows:
        out[str(row.get("record") or "")].append(row)
    return out


def _evidence_block(kind: Dict[str, List[dict]]) -> dict:
    """Arrivals, and how many of them were actually new."""
    fresh = kind.get("evidence", [])
    seen = kind.get("evidence_seen", [])
    effects = kind.get("knowledge_effect", [])
    changed = [e for e in effects if str(e.get("effect_type")) in CHANGING]
    # Evidence ids that produced a CHANGING effect. Counted over ids, not
    # over effects: one row can produce several effects and summing them
    # would make a fraction whose numerator is not its denominator.
    changing_ids = {str(e.get("evidence_id")) for e in changed
                    if e.get("evidence_id")}
    return {
        "evidence_rows": len(fresh),
        "re_observations": len(seen),
        "arrivals_total": len(fresh) + len(seen),
        # The share of arrivals that were genuinely new information.
        "new_information_share": _ratio(len(fresh), len(fresh) + len(seen)),
        "knowledge_effects": len(effects),
        "evidence_that_changed_something": len(changing_ids),
        "zero_effect_evidence": max(len(fresh) - len(changing_ids), 0),
        "effects_by_type": dict(sorted(collections.Counter(
            str(e.get("effect_type") or "?") for e in effects).items())),
        "changing_effect_share": _ratio(len(changed), len(effects)),
        # No independence producer exists on the market branch; the founder
        # branch owns `company_ingestion.independence`. Reporting 0 here would
        # assert that no evidence was independent, which is a much stronger
        # claim than "nothing measured it".
        "independent_evidence_rows": UNAVAILABLE,
        "independent_evidence_note": (
            "evidence independence is produced on the founder branch "
            "(company_ingestion.independence); the market ledger carries no "
            "independence column"),
    }


def _beliefs_block(kind) -> dict:
    declared = kind.get("belief", [])
    updates = kind.get("belief_update", [])
    transitions = collections.Counter(
        str(u.get("transition") or u.get("kind") or "UNSPECIFIED")
        for u in updates)
    return {
        "beliefs_declared": len(declared),
        "beliefs_updated": len(updates),
        "distinct_beliefs_touched": len(
            {str(b.get("belief_id")) for b in declared + updates
             if b.get("belief_id")}),
        "transitions": dict(sorted(transitions.items())),
    }


def _expectations_block(kind) -> dict:
    preregistered = kind.get("expectation", [])
    reconciled = kind.get("reconciliation", [])
    outcomes = collections.Counter(
        str(r.get("outcome") or r.get("verdict") or r.get("result")
            or "UNSPECIFIED") for r in reconciled)
    return {
        "preregistered": len(preregistered),
        "reconciled": len(reconciled),
        "outcomes": dict(sorted(outcomes.items())),
        # Preregistration only means something if the record predates the
        # answer, so the two counts are kept apart rather than netted.
        "open_after_period": max(len(preregistered) - len(reconciled), 0),
    }


def _thesis_block(kind) -> dict:
    revisions = kind.get("thesis_revision", [])
    snapshots = kind.get("thesis_snapshot", [])
    return {
        "snapshots": len(snapshots),
        "revisions": len(revisions),
        "distinct_theses_revised": len(
            {str(r.get("thesis_id")) for r in revisions if r.get("thesis_id")}),
        "transitions": dict(sorted(collections.Counter(
            str(r.get("transition") or "UNSPECIFIED")
            for r in revisions).items())),
    }


def _research_block(kind) -> dict:
    decisions = kind.get("research_decision", [])
    outcomes = kind.get("research_outcome", [])
    status = collections.Counter(str(o.get("status") or "UNRECORDED")
                                 for o in outcomes)
    return {
        "decisions": len(decisions),
        "outcomes": len(outcomes),
        "by_status": dict(sorted(status.items())),
        # §13: a policy dataset holding only successes cannot support
        # off-policy evaluation, so the presence of failures is a REPORTED
        # property rather than an assumed one.
        "zero_result_captured": bool(
            {"NO_RESULT", "FAILED", "REFUSED"} & set(status)),
    }


def _method_block(kind) -> dict:
    performance = kind.get("method_performance", [])
    checks = kind.get("method_assumption_check", [])
    beat = sum(1 for p in performance if p.get("beat_baseline") is True)
    held = sum(1 for c in checks if c.get("holds") is True)
    return {
        "performance_rows": len(performance),
        "beat_baseline": beat,
        "beat_baseline_share": _ratio(beat, len(performance)),
        "assumption_checks": len(checks),
        "assumptions_held": held,
        # A method that wins while its identifying assumption fails has
        # produced a description, not an effect. The two are reported side by
        # side so neither can be read alone.
        "assumptions_held_share": _ratio(held, len(checks)),
    }


def _sources_block(kind) -> dict:
    """Source standing, read under the names the producer actually writes.

    `source_health.v1` already carries a full degradation model —
    `source_family`, `state`, `failure_streak`, `last_success`,
    `fallback_family`, `affected`. This block consumes it rather than
    inventing a second one; the only thing missing was a reader.
    """
    health = kind.get("source_health", [])
    states = collections.Counter(str(h.get("state") or "UNKNOWN")
                                 for h in health)
    latest: Dict[str, dict] = {}
    for row in health:
        family = str(row.get("source_family") or "?")
        if (family not in latest
                or str(row.get("detected_at") or "")
                >= str(latest[family].get("detected_at") or "")):
            latest[family] = row
    degraded = sorted(f for f, r in latest.items()
                      if str(r.get("state")) != "HEALTHY")
    return {
        "observations": len(health),
        "families_tracked": len(latest),
        "by_state": dict(sorted(states.items())),
        "degraded_families": degraded,
        "fallbacks_active": sorted(
            str(r.get("fallback_family")) for r in latest.values()
            if r.get("fallback_family")),
        "longest_failure_streak": max(
            [int(r.get("failure_streak") or 0) for r in latest.values()]
            or [0]),
        # Intelligence that depends on a degraded family. This is the field
        # that keeps a source outage from being read as company inactivity.
        "affected_intelligence": sorted({
            str(a) for r in latest.values() if str(r.get("state")) != "HEALTHY"
            for a in (r.get("affected") or [])}),
        "note": ("a degraded source reduces observability; it is never "
                 "evidence that a company did nothing"),
    }


def _macro_block(kind) -> dict:
    observations = kind.get("macro_observation", [])
    return {
        "observations": len(observations),
        "distinct_conditions": len(
            {str(o.get("state_kind")) for o in observations
             if o.get("state_kind")}),
        "by_condition": dict(sorted(collections.Counter(
            str(o.get("state_kind") or "?") for o in observations).items())),
    }


def _bottleneck(blocks: dict) -> dict:
    """Which conversion is limiting learning — computed, never declared.

    A hardcoded bottleneck is a belief about the system that stops being
    checked the day it is typed, so this ranks the measured conversions and
    reports the worst one WITH the number that made it worst. A stage with no
    arrivals at all outranks a stage converting badly: an unmeasured stage
    cannot be improved deliberately.
    """
    evidence = blocks["evidence"]
    candidates = []

    arrivals = evidence["arrivals_total"]
    if not arrivals:
        candidates.append(("SOURCE_COVERAGE", 0.0,
                           "no evidence arrived at all in this period"))
    else:
        share = evidence["new_information_share"]
        if share != UNMEASURABLE and share < 0.34:
            candidates.append((
                "EVIDENCE_INDEPENDENCE", share,
                f"{evidence['re_observations']} of {arrivals} arrivals were "
                f"re-observations ({1 - share:.0%} already known)"))
        effects = evidence["knowledge_effects"]
        if effects:
            changing = evidence["changing_effect_share"]
            if changing != UNMEASURABLE and changing < 0.15:
                candidates.append((
                    "BELIEF_FORMATION", changing,
                    f"{effects} effects and only "
                    f"{evidence['changing_effect_share']:.0%} changed "
                    f"anything"))
        elif evidence["evidence_rows"]:
            candidates.append((
                "EVENT_CLASSIFICATION", 0.0,
                f"{evidence['evidence_rows']} evidence row(s) produced no "
                f"knowledge effect"))

    expectations = blocks["expectations"]
    if expectations["preregistered"] and not expectations["reconciled"]:
        candidates.append((
            "RECONCILIATION", 0.0,
            f"{expectations['preregistered']} expectation(s) preregistered "
            f"and none reconciled in this period"))

    research = blocks["research"]
    if not research["decisions"] and not research["outcomes"]:
        candidates.append((
            "PROSPECTIVE_RESEARCH_SAMPLE", 0.0,
            "no research action was chosen in this period"))

    if not candidates:
        return {"bottleneck": "NONE_MEASURED", "severity": None,
                "reason": ("every measured conversion is above its floor for "
                           "this period")}
    candidates.sort(key=lambda c: c[1])
    name, value, reason = candidates[0]
    return {"bottleneck": name, "severity": value, "reason": reason,
            "runners_up": [c[0] for c in candidates[1:]]}


def _next_research_priority(bottleneck: dict, blocks: dict) -> dict:
    """Bottleneck to an actionable next investigation.

    A priority must name the missing FACT and the source family likely to
    carry it. It must never encode the answer: "find evidence demand is
    strengthening" is a prohibited shape, because a research action whose
    success condition is a conclusion cannot disconfirm anything.
    """
    plans = {
        "SOURCE_COVERAGE": (
            "no evidence is arriving",
            "widen the source family set; check source_health for refusals"),
        "EVIDENCE_INDEPENDENCE": (
            "arrivals are dominated by pages already read",
            "seek a source family off the companies' own domains"),
        "BELIEF_FORMATION": (
            "evidence arrives and beliefs do not move",
            "seek DISCRIMINATING evidence for an open belief — a fact whose "
            "two possible values imply different beliefs"),
        "EVENT_CLASSIFICATION": (
            "evidence is not being typed into events",
            "inspect the event typing stage on the newest evidence rows"),
        "RECONCILIATION": (
            "predictions are being made and never judged",
            "reconcile the oldest open expectations whose windows have closed"),
        "PROSPECTIVE_RESEARCH_SAMPLE": (
            "no prospective research action was taken",
            "run the research decision step so the policy accumulates "
            "experience"),
        "NONE_MEASURED": (
            "no conversion is below its floor",
            "continue the standing research queue"),
    }
    missing, action = plans.get(bottleneck["bottleneck"],
                                ("unclassified", "inspect the channel"))
    return {
        "bottleneck": bottleneck["bottleneck"],
        "missing_fact": missing,
        "suggested_action": action,
        "why_now": bottleneck.get("reason", ""),
        # An honest priority says what would change our mind, not what we hope
        # to confirm.
        "forbidden_shape": ("a query that names its desired conclusion is "
                            "refused; the action must be able to fail"),
    }


def _executive_summary(blocks: dict, bottleneck: dict) -> dict:
    """Deterministic selection. No model chooses what counts as a learning."""
    evidence = blocks["evidence"]
    top = []
    if evidence["evidence_that_changed_something"]:
        top.append(f"{evidence['evidence_that_changed_something']} evidence "
                   f"row(s) changed the model")
    for kind, count in sorted(evidence["effects_by_type"].items()):
        if kind in CHANGING and count:
            top.append(f"{count} {kind.lower()} effect(s)")
    contradictions = evidence["effects_by_type"].get("CONTRADICTED", 0)
    revalidations = evidence["effects_by_type"].get("NO_CHANGE", 0)
    return {
        "top_learnings": top or ["no model change in this period"],
        "top_contradictions": (
            [f"{contradictions} contradicting effect(s)"] if contradictions
            else ["none"]),
        "top_revalidations": (
            [f"{revalidations} observation(s) confirmed existing knowledge"]
            if revalidations else ["none"]),
        "top_degradations": blocks["sources"]["degraded_families"] or ["none"],
        "top_information_gaps": [bottleneck["reason"]],
        # Silence with a named cause. "Nothing changed" is a finding; "nothing
        # ran" is an outage, and a summary that cannot tell them apart is the
        # incident restated.
        "material_change": bool(evidence["evidence_that_changed_something"]),
    }


def build(period: str = DAY, *, root=None, as_of=None) -> dict:
    """One canonical learning report. Reads only declared canonical stores."""
    if period not in PERIODS:
        raise ValueError(f"unknown period {period!r}; expected {PERIODS}")
    as_of = as_of or datetime.date.today()
    start, end, partial = _bounds(period, as_of)

    paths = SOR.stores(root)
    ledger_path = paths["learning_ledger"]
    ledger = LS._read(ledger_path)
    rows = _rows_in(ledger, start, end)
    kind = _by_kind(rows)

    # Coverage: which rows this reader could NOT place, and why. Undatable
    # rows stay visible rather than shrinking the window silently.
    undatable = collections.Counter(
        str(r.get("record") or "") for r in ledger
        if not LS._learned_at(r)[0])
    fields_used = collections.Counter(
        LS._learned_at(r)[1] for r in rows if LS._learned_at(r)[1])

    blocks = {
        "evidence": _evidence_block(kind),
        "beliefs": _beliefs_block(kind),
        "expectations": _expectations_block(kind),
        "thesis": _thesis_block(kind),
        "research": _research_block(kind),
        "method": _method_block(kind),
        "sources": _sources_block(kind),
        "macro": _macro_block(kind),
    }
    bottleneck = _bottleneck(blocks)

    return {
        "contract": CONTRACT,
        "report_version": 1,
        "period": period,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "partial_period": partial,
        "partial_month": partial if period == MONTH else False,
        "generated_at": datetime.datetime.now(
            datetime.timezone.utc).isoformat(),
        "system_of_record": SOR.canonical_id(),
        "data_root": str(ledger_path),
        "runtime_sha": "",
        "rows": {
            "in_period": len(rows),
            "ledger_all_time": len(ledger),
            "undatable_all_time": sum(undatable.values()),
            "undatable_by_kind": dict(sorted(undatable.items())),
            "date_field_used": dict(sorted(fields_used.items())),
        },
        "channels": blocks,
        "bottleneck": bottleneck,
        "next_research_priority": _next_research_priority(bottleneck, blocks),
        "executive_summary": _executive_summary(blocks, bottleneck),
    }


def persist(report: dict, *, root=None) -> pathlib.Path:
    """Write the authoritative artifact and return its path."""
    base = pathlib.Path(root) if root else pathlib.Path(
        SOR.canonical().get("scheduler", {}).get("runtime_root", "."))
    period = report["period"]
    if period == DAY:
        directory, name = DAILY_DIR, report["end"]
    elif period == WEEK:
        start = datetime.date.fromisoformat(report["start"])
        directory = WEEKLY_DIR
        name = f"{start.isocalendar()[0]}-W{start.isocalendar()[1]:02d}"
    else:
        directory, name = MONTHLY_DIR, report["start"][:7]
    out = base / directory
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{name}.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=False),
                    encoding="utf-8")
    return path


def render(report: dict) -> str:
    summary = report["executive_summary"]
    evidence = report["channels"]["evidence"]
    out = [
        "=" * 72,
        f"MARKET LEARNING — {report['period'].upper()} "
        f"{report['start']}..{report['end']}"
        + ("  [PARTIAL PERIOD]" if report["partial_period"] else ""),
        "=" * 72,
        f"  rows in period {report['rows']['in_period']}   "
        f"undatable (all time) {report['rows']['undatable_all_time']}",
        "",
        "WHAT ARRIVED",
        f"  {evidence['evidence_rows']} new evidence row(s), "
        f"{evidence['re_observations']} re-observation(s)",
        f"  {evidence['knowledge_effects']} knowledge effect(s); "
        f"{evidence['evidence_that_changed_something']} row(s) changed the "
        f"model",
        f"  effects: {evidence['effects_by_type'] or '-'}",
        "",
        "WHAT MOVED",
        f"  beliefs   declared {report['channels']['beliefs']['beliefs_declared']}"
        f", updated {report['channels']['beliefs']['beliefs_updated']}",
        f"  expect.   preregistered "
        f"{report['channels']['expectations']['preregistered']}, reconciled "
        f"{report['channels']['expectations']['reconciled']}",
        f"  thesis    revisions "
        f"{report['channels']['thesis']['revisions']}",
        f"  research  {report['channels']['research']['by_status'] or '-'}",
        "",
        "SUMMARY",
    ]
    for line in summary["top_learnings"]:
        out.append(f"  + {line}")
    out += [
        f"  contradictions  {', '.join(summary['top_contradictions'])}",
        f"  degraded        {', '.join(summary['top_degradations'])}",
        "",
        "BOTTLENECK",
        f"  {report['bottleneck']['bottleneck']}: "
        f"{report['bottleneck']['reason']}",
        "",
        "NEXT INVESTIGATION",
        f"  {report['next_research_priority']['suggested_action']}",
        "=" * 72,
    ]
    return "\n".join(out)
