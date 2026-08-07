"""Is the engine actually learning, and is that learning getting better?

WHY THIS EXISTS
---------------
This question was deferred for three development cycles, every time losing to
a defect that was visible on a page. That ordering was itself the bug: a
founder-visible typo always looks more urgent than an invisible claim that the
engine is getting smarter, so the invisible claim never got checked.

It had never been checked. The first measurement taken here found that the
belief-testing loop had never once produced an informative result. Forty-six
beliefs had been declared, forty-six expectations preregistered, and every
single reconciliation came back TOO_EARLY — not because the windows were
young, but because production called the learning cycle without ever passing
an observation. The engine could accumulate beliefs and could not test one.

That defect is invisible from inside any single cycle's report, because each
cycle honestly reported `informative: 0` and there was nothing to compare it
to. It is only visible when the cycles are read as a series. That is what this
module is for.

WHAT IT REFUSES TO DO
---------------------
Three refusals, each of which cost something to learn:

1. **It does not report a rate it cannot compute.** Where the sample is too
   small the value is `UNMEASURABLE`, never zero. A calibration of 0.0 and a
   calibration that has never been measurable are opposite findings, and a
   dashboard that renders both as `0.0` is worse than no dashboard.

2. **It does not rank a bottleneck from a single cycle.** `funnel.py` learned
   this the hard way and the reasoning transfers exactly: one cycle cannot
   distinguish a broken stage from a quiet day. A stage is named the
   bottleneck only when it dominates the loss repeatedly.

3. **It does not read a backlog drain as a learning rate.** The first cycle to
   run the completed pipeline formed 35 beliefs from the whole accumulated
   evidence pool; the next three formed 7, 3 and 1 from fresh evidence only.
   The naive series 35→7→3→1 says DEGRADING. The truth is that the first
   number is a different quantity from the other three. A cohort whose intake
   is a backlog is flagged and excluded from velocity rather than smoothed.

WHAT COUNTS AS LEARNING
-----------------------
Not rows. A cycle that appends a hundred duplicate evidence records has
learned nothing, and a cycle that retires one belief it can no longer support
has learned something. The optimisation target this module reports against is

    validated commercial information gain  ×  founder decision usefulness

so quantity and quality are computed separately and never summed.
"""
from __future__ import annotations

import collections
import datetime as _dt
import json
import pathlib
import statistics
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

CONTRACT = "market_learning_health.v1"

# The sentinel. A metric is UNMEASURABLE when the data required to compute it
# does not exist yet -- distinct from a measured zero, which is a finding.
UNMEASURABLE = "UNMEASURABLE"

# --- learning status classes ------------------------------------------------
ACCELERATING = "LEARNING_ACCELERATING"
HEALTHY = "LEARNING_HEALTHY"
PLATEAU = "LEARNING_PLATEAU"
DEGRADING = "LEARNING_DEGRADING"
NO_NEW_EVIDENCE = "INSUFFICIENT_NEW_EVIDENCE"
BOTTLENECKED = "PIPELINE_BOTTLENECK"
NO_HISTORY = "INSUFFICIENT_HISTORY"

STATUS_CLASSES = frozenset({
    ACCELERATING, HEALTHY, PLATEAU, DEGRADING, NO_NEW_EVIDENCE,
    BOTTLENECKED, NO_HISTORY})

# --- the learning funnel ----------------------------------------------------
# Each stage is a subset of the one above it, so the conversion between
# adjacent stages is meaningful on its own. This is the same discipline the
# decision funnel uses, applied to information rather than to trades.
LEARNING_CHAIN = (
    "documents_considered",
    "candidate_event_sentences",
    "accepted_evidence",
    "belief_candidates",
    "beliefs_accepted",
    "expectations_created",
    "expectations_due",
    "expectations_resolved",
    "validated_knowledge",
)

# Which subsystem owns the loss between one stage and the next. Naming the
# stage is not enough for an operator to act -- they need the component.
STAGE_OWNER: Dict[str, str] = {
    "candidate_event_sentences": "BODY_EVIDENCE_SELECTION",
    "accepted_evidence": "EVENT_CLASSIFICATION",
    "belief_candidates": "BELIEF_FORMATION",
    "beliefs_accepted": "BELIEF_DEDUPLICATION",
    "expectations_created": "EXPECTATION_CREATION",
    # An expectation that never becomes scoreable has two possible causes and
    # they take opposite fixes, so the owner is decided by `why_unscoreable`
    # rather than assumed here. Defaulting to maturity would counsel patience
    # for a wiring fault; defaulting to observability would counsel rewiring
    # for a window that is simply young.
    "expectations_due": "EXPECTATION_MATURITY",
    "expectations_resolved": "OUTCOME_OBSERVABILITY",
    "validated_knowledge": "BELIEF_REVISION",
}

BOTTLENECK_CLASSES = frozenset(set(STAGE_OWNER.values()) | {
    "RETRIEVAL", "EVENT_EXTRACTION", "SUBJECT_BINDING", "CORROBORATION",
    "HIDDEN_STATE_INFERENCE", "INTERACTION_OBSERVATION", "CAUSAL_INFERENCE",
    "INFORMATION_ACQUISITION", "FOUNDER_RELEVANCE"})

# --- alerts -----------------------------------------------------------------
LEARNING_STALLED = "LEARNING_STALLED"
BELIEF_TESTING_STALLED = "BELIEF_TESTING_STALLED"
EXPECTATION_BACKLOG_GROWING = "EXPECTATION_BACKLOG_GROWING"
EVIDENCE_QUALITY_DROPPING = "EVIDENCE_QUALITY_DROPPING"
FALSE_POSITIVE_RATE_RISING = "FALSE_POSITIVE_RATE_RISING"
KNOWLEDGE_REVERSAL_RATE_RISING = "KNOWLEDGE_REVERSAL_RATE_RISING"
WATCHLIST_COVERAGE_DROPPING = "PRIORITY_WATCHLIST_COVERAGE_DROPPING"
FOUNDER_UTILITY_DROPPING = "FOUNDER_UTILITY_DROPPING"
PIPELINE_STAGE_REGRESSION = "PIPELINE_STAGE_REGRESSION"

ALERT_CLASSES = frozenset({
    LEARNING_STALLED, BELIEF_TESTING_STALLED, EXPECTATION_BACKLOG_GROWING,
    EVIDENCE_QUALITY_DROPPING, FALSE_POSITIVE_RATE_RISING,
    KNOWLEDGE_REVERSAL_RATE_RISING, WATCHLIST_COVERAGE_DROPPING,
    FOUNDER_UTILITY_DROPPING, PIPELINE_STAGE_REGRESSION})

# An alert on two data points is noise. Nothing fires below this many cycles.
MIN_CYCLES_FOR_ALERT = 3
# Velocity comparison needs a window and a prior window of the same length.
MIN_CYCLES_FOR_VELOCITY = 4
# Below this many resolved tests, every calibration figure is UNMEASURABLE.
MIN_RESOLVED_FOR_CALIBRATION = 5
# A change smaller than this fraction is not a trend, it is a rounding artefact.
MATERIAL_CHANGE = 0.20

WINDOWS = (1, 7, 30, 90)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _date(value: object) -> Optional[_dt.date]:
    text = str(value or "")[:10]
    if len(text) != 10:
        return None
    try:
        return _dt.date.fromisoformat(text)
    except ValueError:
        return None


def _rate(numerator: float, denominator: float) -> object:
    """A conversion rate, or UNMEASURABLE when the denominator is empty.

    Zero over zero is not zero. A stage that nothing entered has no
    conversion rate, and reporting 0.0 would make an idle stage
    indistinguishable from a broken one.
    """
    if not denominator:
        return UNMEASURABLE
    return numerator / denominator


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _direction(current: float, prior: float) -> str:
    """Classify a change between two comparable windows."""
    if prior == 0 and current == 0:
        return "FLAT"
    if prior == 0:
        return "UP"
    change = (current - prior) / prior
    if abs(change) < MATERIAL_CHANGE:
        return "FLAT"
    return "UP" if change > 0 else "DOWN"


# ---------------------------------------------------------------------------
# per-cycle observation
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CycleObservation:
    """One learning session, reduced to the quantities health depends on.

    `backlog_drain` marks the cycle that first ran the completed pipeline over
    an already-accumulated evidence pool. Its belief count measures a stock,
    not a rate, and mixing it into a velocity series produces a fictional
    collapse on the following cycle.
    """
    as_of: str
    cycle: str
    outcome_class: str = ""
    documents_considered: int = 0
    candidate_event_sentences: int = 0
    accepted_evidence: int = 0
    duplicate_evidence: int = 0
    furniture_rejected: int = 0
    companies_evaluated: int = 0
    companies_with_new_evidence: int = 0
    belief_candidates: int = 0
    beliefs_accepted: int = 0
    beliefs_strengthened: int = 0
    beliefs_weakened: int = 0
    beliefs_retired: int = 0
    beliefs_decayed: int = 0
    expectations_created: int = 0
    expectations_evaluated: int = 0
    expectations_resolved: int = 0
    expectations_too_early: int = 0
    hidden_states_tracked: int = 0
    hidden_states_moved: int = 0
    causal_edges: int = 0
    interactions_observed: int = 0
    information_priorities: int = 0
    dossiers_written: int = 0
    refused: Dict[str, int] = field(default_factory=dict)
    backlog_drain: bool = False

    @property
    def date(self) -> Optional[_dt.date]:
        return _date(self.as_of)

    @property
    def validated_knowledge(self) -> int:
        """Knowledge that survived a test -- the only kind that counts here.

        A newly declared belief is a hypothesis, not knowledge. It becomes
        knowledge when an observation has been allowed to contradict it and
        did not.
        """
        return (self.beliefs_strengthened + self.beliefs_weakened
                + self.beliefs_retired)

    @property
    def expectations_due(self) -> int:
        return max(0, self.expectations_evaluated - self.expectations_too_early)

    def stage(self, name: str) -> int:
        if name == "expectations_due":
            return self.expectations_due
        if name == "validated_knowledge":
            return self.validated_knowledge
        return int(getattr(self, name, 0) or 0)

    def as_dict(self) -> dict:
        out = {
            "as_of": self.as_of, "cycle": self.cycle,
            "outcome_class": self.outcome_class,
            "backlog_drain": self.backlog_drain,
            "validated_knowledge": self.validated_knowledge,
        }
        for name in LEARNING_CHAIN:
            out[name] = self.stage(name)
        return out


def observation_from_report(report: dict, *, backlog_drain: bool = False
                            ) -> Optional[CycleObservation]:
    """Read one persisted cycle report into the health contract's terms.

    Returns None for a report with no learning block. Nine of the twenty
    recorded cycles predate the completed pipeline, and treating them as
    cycles that learned nothing would understate every rate computed here.
    """
    learning = report.get("learning") or {}
    if not learning:
        return None

    formation = learning.get("belief_formation") or {}
    belief = learning.get("belief_learning") or {}
    observed = learning.get("expected_vs_observed") or {}
    by_outcome = observed.get("by_outcome") or {}
    hidden = learning.get("hidden_states") or {}
    causal = learning.get("causal_graph") or {}
    priorities = learning.get("information_priorities") or {}
    export = learning.get("strategic_export") or {}
    interactions = learning.get("strategic_interactions") or {}
    translation = report.get("translation") or {}
    refused = dict(formation.get("refused") or {})

    evaluated = int(observed.get("evaluated", 0) or 0)
    too_early = int(by_outcome.get("TOO_EARLY", 0) or 0)
    # Accepted evidence is the classified total, not a separate counter: the
    # cycle report states what each candidate was classified AS, and the sum
    # of that is what actually entered the ledger this session.
    classified = sum(int(v or 0) for v
                     in (translation.get("classification_by_type") or {}
                         ).values())

    return CycleObservation(
        as_of=str(report.get("as_of") or learning.get("as_of") or "")[:10],
        cycle=str(report.get("cycle") or ""),
        outcome_class=str(learning.get("outcome_class") or ""),
        documents_considered=int(translation.get("documents_considered", 0)
                                 or 0),
        candidate_event_sentences=int(
            translation.get("candidate_sentences", 0) or 0),
        accepted_evidence=classified,
        furniture_rejected=int(translation.get("furniture_rejected", 0) or 0),
        companies_evaluated=int(translation.get("companies_processed", 0)
                                or 0),
        companies_with_new_evidence=int(
            translation.get("companies_with_evidence", 0) or 0),
        duplicate_evidence=int(translation.get("duplicate_candidates", 0)
                               or 0),
        belief_candidates=int(formation.get("candidates", 0) or 0),
        beliefs_accepted=int(belief.get("new", 0) or 0),
        beliefs_strengthened=int(belief.get("strengthened", 0) or 0),
        beliefs_weakened=int(belief.get("weakened", 0) or 0),
        beliefs_retired=int(belief.get("retired", 0) or 0),
        beliefs_decayed=int(belief.get("decayed", 0) or 0),
        expectations_created=int(formation.get("expectations", 0) or 0),
        expectations_evaluated=evaluated,
        expectations_resolved=int(observed.get("informative", 0) or 0),
        expectations_too_early=too_early,
        hidden_states_tracked=int(hidden.get("companies_tracked", 0) or 0),
        hidden_states_moved=int(hidden.get("companies_moved", 0) or 0),
        causal_edges=int(causal.get("edges_total", 0) or 0),
        interactions_observed=int(interactions.get("observed", 0) or 0),
        information_priorities=int(priorities.get("candidates", 0) or 0),
        dossiers_written=len(export.get("published") or ()),
        refused=refused,
        backlog_drain=backlog_drain,
    )


def load_cycle_observations(root: pathlib.Path) -> Tuple[CycleObservation, ...]:
    """Every persisted cycle report that ran the learning pipeline, in order.

    The earliest such cycle is marked as a backlog drain. It is the one that
    saw the standing evidence pool rather than a day's fresh arrivals, and no
    later cycle can be compared to it.
    """
    reports = sorted((root / "reports" / "market").glob("*.json"))
    out: List[CycleObservation] = []
    for path in reports:
        name = path.name
        if not (name.endswith("_day.json") or name.endswith("_night.json")):
            continue
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        obs = observation_from_report(report)
        if obs is not None:
            out.append(obs)
    out.sort(key=lambda o: (o.as_of, 0 if o.cycle == "day" else 1))
    # The first pipeline cycle to accept any belief drained the backlog.
    for index, obs in enumerate(out):
        if obs.beliefs_accepted:
            out[index] = CycleObservation(**{
                **{k: getattr(obs, k) for k in obs.__dataclass_fields__},
                "backlog_drain": True})
            break
    return tuple(out)


# ---------------------------------------------------------------------------
# velocity and acceleration
# ---------------------------------------------------------------------------
VELOCITY_SERIES = (
    "accepted_evidence",
    "beliefs_accepted",
    "validated_knowledge",
    "expectations_created",
    "expectations_resolved",
    "information_priorities",
    "dossiers_written",
)


def _window_slice(observations: Sequence[CycleObservation], *, as_of: str,
                  days: int, offset: int = 0
                  ) -> Tuple[CycleObservation, ...]:
    """Cycles inside a [days]-long window ending `offset` windows back."""
    end = _date(as_of)
    if end is None:
        return ()
    upper = end - _dt.timedelta(days=days * offset)
    lower = upper - _dt.timedelta(days=days)
    return tuple(o for o in observations
                 if o.date is not None and lower < o.date <= upper)


def velocity(observations: Sequence[CycleObservation], *, as_of: str,
             days: int, offset: int = 0) -> Dict[str, object]:
    """Per-day rate of each learning series inside one window.

    Backlog-drain cycles are excluded rather than smoothed: including one
    makes the window it lands in look extraordinary and the next look broken.
    """
    window = tuple(o for o in _window_slice(observations, as_of=as_of,
                                            days=days, offset=offset)
                   if not o.backlog_drain)
    out: Dict[str, object] = {
        "window_days": days, "offset": offset, "cycles": len(window)}
    if not window:
        for name in VELOCITY_SERIES:
            out[name] = UNMEASURABLE
        out["measurable"] = False
        return out
    for name in VELOCITY_SERIES:
        out[name] = sum(o.stage(name) if name in LEARNING_CHAIN
                        else int(getattr(o, name, 0) or 0)
                        for o in window) / days
    out["measurable"] = True
    return out


def acceleration(observations: Sequence[CycleObservation], *, as_of: str,
                 days: int) -> Dict[str, object]:
    """This window's rate against the window before it.

    Returns INSUFFICIENT_HISTORY rather than a number whenever the prior
    window holds no cycle. An engine three days old cannot have a 30-day
    trend, and inventing one is the failure this whole module exists to stop.
    """
    current = velocity(observations, as_of=as_of, days=days, offset=0)
    prior = velocity(observations, as_of=as_of, days=days, offset=1)
    out: Dict[str, object] = {
        "window_days": days,
        "current_cycles": current["cycles"], "prior_cycles": prior["cycles"]}
    if not current.get("measurable") or not prior.get("measurable"):
        out["status"] = NO_HISTORY
        out["series"] = {}
        return out
    series: Dict[str, dict] = {}
    for name in VELOCITY_SERIES:
        now, before = current[name], prior[name]
        if not (_is_number(now) and _is_number(before)):
            continue
        series[name] = {"current": now, "prior": before,
                        "direction": _direction(now, before)}
    out["status"] = "MEASURED"
    out["series"] = series
    return out


def classify(observations: Sequence[CycleObservation], *, as_of: str,
             bottleneck: Optional[dict] = None) -> Dict[str, object]:
    """Name the engine's learning state, honestly.

    Order matters and encodes what an operator most needs to know first. A
    pipeline with a total blockage is reported as blocked even if its evidence
    intake is rising, because rising intake into a blocked stage is not
    learning -- it is a queue.
    """
    usable = [o for o in observations if not o.backlog_drain]
    if len(usable) < MIN_CYCLES_FOR_VELOCITY:
        return {"status": NO_HISTORY,
                "because": f"{len(usable)} comparable cycles on record; "
                           f"{MIN_CYCLES_FOR_VELOCITY} are needed before any "
                           f"rate can be compared to a prior rate",
                "cycles_available": len(usable)}

    if bottleneck and bottleneck.get("total_blockage"):
        return {"status": BOTTLENECKED,
                "because": bottleneck.get("because", ""),
                "stage": bottleneck.get("stage"),
                "owner": bottleneck.get("owner")}

    recent = usable[-MIN_CYCLES_FOR_ALERT:]
    if not any(o.accepted_evidence for o in recent):
        return {"status": NO_NEW_EVIDENCE,
                "because": "no cycle in the recent window ingested new "
                           "evidence; nothing could have been learned",
                "cycles_available": len(usable)}

    seven = acceleration(observations, as_of=as_of, days=7)
    if seven.get("status") != "MEASURED":
        return {"status": NO_HISTORY,
                "because": "no prior 7-day window to compare against",
                "cycles_available": len(usable)}

    # Validated knowledge is the series that decides the verdict. Evidence and
    # belief counts can both rise while nothing is ever confirmed or refuted,
    # and that state is a plateau however busy the intake looks.
    validated = seven["series"].get("validated_knowledge") or {}
    direction = validated.get("direction")
    if validated.get("current", 0) == 0 and validated.get("prior", 0) == 0:
        return {"status": PLATEAU,
                "because": "evidence and beliefs are moving but no belief was "
                           "confirmed, refuted or retired in either window; "
                           "the engine is accumulating, not validating",
                "cycles_available": len(usable)}
    if direction == "UP":
        return {"status": ACCELERATING,
                "because": "validated knowledge per day rose against the "
                           "prior window of equal length",
                "cycles_available": len(usable)}
    if direction == "DOWN":
        return {"status": DEGRADING,
                "because": "validated knowledge per day fell against the "
                           "prior window of equal length",
                "cycles_available": len(usable)}
    return {"status": HEALTHY,
            "because": "validated knowledge is being produced at a steady "
                       "rate against the prior window",
            "cycles_available": len(usable)}


# ---------------------------------------------------------------------------
# bottleneck detection
# ---------------------------------------------------------------------------
def funnel(observations: Sequence[CycleObservation],
           ledger_totals: Optional[Dict[str, int]] = None) -> Dict[str, object]:
    """Aggregate the learning funnel and find where information gain is lost.

    Ranked across every pipeline cycle, never one. A stage that lost
    everything on one quiet day is not a bottleneck; a stage that loses
    everything on every day is the only thing worth fixing.

    `ledger_totals` overrides stages the append-only ledger knows better than
    the cycle reports do. Reconciliations land in the ledger the moment they
    happen; the report that mentions them is written afterwards and may not
    exist yet. Reading those stages from reports alone made health announce
    zero tested beliefs while ten reconciliations sat in the ledger — the same
    stale-surface bug this module was built to catch, reproduced inside it.
    """
    totals = {name: sum(o.stage(name) for o in observations)
              for name in LEARNING_CHAIN}
    for name, value in (ledger_totals or {}).items():
        if name in totals:
            totals[name] = max(totals[name], value)
    conversions: Dict[str, object] = {}
    losses: List[Tuple[str, int, float]] = []
    for upper, lower in zip(LEARNING_CHAIN, LEARNING_CHAIN[1:]):
        entered, left = totals[upper], totals[lower]
        conversions[lower] = _rate(left, entered)
        if entered:
            losses.append((lower, entered - left, (entered - left) / entered))

    out: Dict[str, object] = {
        "cycles": len(observations), "totals": totals,
        "conversions": conversions}

    if not losses:
        out["bottleneck"] = None
        out["because"] = "no stage has been entered yet"
        return out

    # A stage that admitted nothing at all is the binding constraint whatever
    # the absolute loss elsewhere, because everything downstream of it is
    # starved by definition.
    total_blocks = [(s, lost, rate) for s, lost, rate in losses if rate >= 1.0]
    if total_blocks:
        # The EARLIEST total block is the binding one -- a later empty stage is
        # a symptom of the first, not a second independent fault.
        order = {name: i for i, name in enumerate(LEARNING_CHAIN)}
        stage, lost, rate = min(total_blocks, key=lambda t: order[t[0]])
        out["bottleneck"] = {
            "stage": stage, "owner": STAGE_OWNER.get(stage, stage),
            "entered": totals[LEARNING_CHAIN[order[stage] - 1]],
            "left": totals[stage], "loss_rate": rate, "total_blockage": True,
            "because": f"{totals[LEARNING_CHAIN[order[stage] - 1]]} items "
                       f"entered {stage} across {len(observations)} cycles "
                       f"and none left; every downstream stage is starved"}
        out["because"] = out["bottleneck"]["because"]
        return out

    stage, lost, rate = max(losses, key=lambda t: t[1])
    out["bottleneck"] = {
        "stage": stage, "owner": STAGE_OWNER.get(stage, stage),
        "lost": lost, "loss_rate": rate, "total_blockage": False,
        "because": f"{stage} accounts for the largest absolute loss of "
                   f"information gain ({lost} items over "
                   f"{len(observations)} cycles)"}
    out["because"] = out["bottleneck"]["because"]
    return out


def why_unscoreable(expectations: Sequence[dict], evidence: Sequence[dict],
                    *, as_of: str) -> Dict[str, object]:
    """Nothing has been scored. Is that patience, or is it a broken wire?

    Two causes produce an identical funnel and take opposite fixes:

      EXPECTATION_MATURITY   the windows are genuinely still open and no
                             qualifying observation could have arrived yet.
                             The fix is to wait. Shortening the window to
                             force a verdict would manufacture the verdict.

      OUTCOME_OBSERVABILITY  qualifying observations DID arrive and were
                             never matched to the expectation waiting for
                             them. The fix is to bind them, and waiting
                             changes nothing.

    They are told apart by asking whether evidence about the expectation's own
    subject landed after it was preregistered. If it did, the engine held the
    answer and did not look at it.
    """
    today = _date(as_of)
    open_rows = [e for e in expectations if e.get("preregistered_at")]
    if not open_rows:
        return {"cause": None, "because": "no expectation is on record"}

    by_subject: Dict[str, List[dict]] = collections.defaultdict(list)
    for item in evidence:
        subject = str(item.get("subject_company") or "").lower()
        if subject:
            by_subject[subject].append(item)

    answerable = 0
    matured = 0
    for row in open_rows:
        ends = _date(row.get("evaluation_window_ends"))
        if ends and today and ends <= today:
            matured += 1
        start = _date(row.get("preregistered_at"))
        subject = str(row.get("subject") or "").lower()
        for item in by_subject.get(subject, ()):
            seen = _date(item.get("observed_at"))
            if start and seen and seen >= start:
                answerable += 1
                break

    if answerable:
        return {
            "cause": "OUTCOME_OBSERVABILITY",
            "expectations": len(open_rows),
            "answerable_now": answerable,
            "matured": matured,
            "because": f"{answerable} of {len(open_rows)} open expectations "
                       f"have evidence about their own subject that arrived "
                       f"after they were preregistered; the observation "
                       f"exists and is not being matched to the expectation "
                       f"waiting for it",
        }
    return {
        "cause": "EXPECTATION_MATURITY",
        "expectations": len(open_rows),
        "answerable_now": 0,
        "matured": matured,
        "because": f"no evidence about any open expectation's subject has "
                   f"arrived since preregistration; {len(open_rows)} windows "
                   f"are open and there is genuinely nothing yet to score",
    }


# ---------------------------------------------------------------------------
# belief cohort survival -- learning QUALITY, not quantity
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Cohort:
    """Beliefs declared on one date, followed forward.

    Cohorts are how quantity is prevented from masquerading as quality. A
    cycle that declares a hundred beliefs and a cycle that declares two are
    indistinguishable until the cohorts are aged, and then they are not
    remotely alike.
    """
    created_at: str
    size: int
    tested: int
    still_supported: int
    strengthened: int
    weakened: int
    retired: int
    never_tested: int
    reversed_later: int
    affected_founder_decision: int

    def as_dict(self) -> dict:
        return {
            "created_at": self.created_at, "size": self.size,
            "tested": self.tested, "still_supported": self.still_supported,
            "strengthened": self.strengthened, "weakened": self.weakened,
            "retired": self.retired, "never_tested": self.never_tested,
            "reversed_later": self.reversed_later,
            "affected_founder_decision": self.affected_founder_decision,
            "test_rate": _rate(self.tested, self.size),
            "survival_rate": _rate(self.still_supported, self.tested),
            "reversal_rate": _rate(self.reversed_later, self.tested),
        }


def cohorts(beliefs: Sequence[dict], reconciliations: Sequence[dict],
            *, dossier_subjects: Sequence[str] = ()) -> Tuple[Cohort, ...]:
    """Group declared beliefs by declaration date and age them forward."""
    tested_by_belief: Dict[str, List[dict]] = collections.defaultdict(list)
    for rec in reconciliations:
        key = rec.get("hypothesis_id") or rec.get("belief_id") or ""
        if key:
            tested_by_belief[key].append(rec)

    subjects = {str(s).replace("-", "_").lower() for s in dossier_subjects}
    grouped: Dict[str, List[dict]] = collections.defaultdict(list)
    for belief in beliefs:
        grouped[str(belief.get("last_updated") or "")[:10]].append(belief)

    out: List[Cohort] = []
    for created_at in sorted(grouped):
        members = grouped[created_at]
        tested = strengthened = weakened = retired = 0
        supported = reversed_later = 0
        for belief in members:
            results = tested_by_belief.get(belief.get("belief_id", ""), [])
            informative = [r for r in results
                           if r.get("outcome") in ("CONFIRMED",
                                                   "PARTIALLY_CONFIRMED",
                                                   "CONTRADICTED")]
            if not informative:
                continue
            tested += 1
            confirms = sum(1 for r in informative
                           if r.get("outcome") != "CONTRADICTED")
            denies = len(informative) - confirms
            if confirms and not denies:
                strengthened += 1
                supported += 1
            elif denies and not confirms:
                weakened += 1
            else:
                # Both directions observed: the belief was supported and then
                # contradicted, or the reverse. That is a reversal, and it is
                # the single most important quality signal there is.
                reversed_later += 1
            if belief.get("lifecycle_state") == "RETIRED":
                retired += 1
        out.append(Cohort(
            created_at=created_at, size=len(members), tested=tested,
            still_supported=supported, strengthened=strengthened,
            weakened=weakened, retired=retired,
            never_tested=len(members) - tested, reversed_later=reversed_later,
            affected_founder_decision=sum(
                1 for b in members
                if str(b.get("subject", "")).lower() in subjects)))
    return tuple(out)


# ---------------------------------------------------------------------------
# the contract
# ---------------------------------------------------------------------------
@dataclass
class LearningHealth:
    as_of: str
    runtime_sha: str = ""
    observation: Dict[str, object] = field(default_factory=dict)
    belief: Dict[str, object] = field(default_factory=dict)
    expectation: Dict[str, object] = field(default_factory=dict)
    hidden_state: Dict[str, object] = field(default_factory=dict)
    interaction: Dict[str, object] = field(default_factory=dict)
    causal: Dict[str, object] = field(default_factory=dict)
    information_value: Dict[str, object] = field(default_factory=dict)
    counterfactual: Dict[str, object] = field(default_factory=dict)
    calibration: Dict[str, object] = field(default_factory=dict)
    knowledge: Dict[str, object] = field(default_factory=dict)
    founder_utility: Dict[str, object] = field(default_factory=dict)
    velocity: Dict[str, object] = field(default_factory=dict)
    acceleration: Dict[str, object] = field(default_factory=dict)
    mechanisms: Dict[str, object] = field(default_factory=dict)
    cohorts: List[dict] = field(default_factory=list)
    funnel: Dict[str, object] = field(default_factory=dict)
    status: Dict[str, object] = field(default_factory=dict)
    alerts: List[dict] = field(default_factory=list)
    coverage: Dict[str, object] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "contract": CONTRACT, "as_of": self.as_of,
            "runtime_sha": self.runtime_sha,
            "observation_health": self.observation,
            "belief_health": self.belief,
            "expectation_health": self.expectation,
            "hidden_state_health": self.hidden_state,
            "interaction_health": self.interaction,
            "causal_health": self.causal,
            "information_value": self.information_value,
            "counterfactual_health": self.counterfactual,
            "calibration": self.calibration,
            "knowledge_health": self.knowledge,
            "founder_utility": self.founder_utility,
            "mechanism_calibration": self.mechanisms,
            "velocity": self.velocity, "acceleration": self.acceleration,
            "cohorts": self.cohorts, "funnel": self.funnel,
            "status": self.status, "alerts": self.alerts,
            "coverage": self.coverage,
        }


# ---------------------------------------------------------------------------
# alerts
# ---------------------------------------------------------------------------
def alerts(observations: Sequence[CycleObservation],
           health: "LearningHealth") -> List[dict]:
    """Operator signals. Never shown to a founder, never fired on noise.

    Every alert here has to survive the same question: would an operator
    change what they did tomorrow because of it? A row that only says a
    number moved is deleted rather than demoted.
    """
    usable = [o for o in observations if not o.backlog_drain]
    out: List[dict] = []
    if len(usable) < MIN_CYCLES_FOR_ALERT:
        return out

    def fire(name: str, detail: str, severity: str = "WARN") -> None:
        out.append({"alert": name, "severity": severity, "detail": detail})

    recent = usable[-MIN_CYCLES_FOR_ALERT:]

    # Resolution counts come from the ledger via `health`, never from the
    # cycle reports. A reconciliation written minutes ago is real; the report
    # that will mention it does not exist yet, and an alert that fired on the
    # report would keep screaming "nothing has ever been tested" at an engine
    # that had just tested ten things.
    tested = int(health.expectation.get("expectations_confirmed", 0) or 0) \
        + int(health.expectation.get("expectations_contradicted", 0) or 0) \
        + int(health.expectation.get(
            "expectations_partially_confirmed", 0) or 0)
    created = int(health.expectation.get("expectations_total", 0) or 0)

    if not tested and not any(o.beliefs_accepted or o.validated_knowledge
                              for o in recent):
        fire(LEARNING_STALLED,
             f"no belief was formed, revised or retired in the last "
             f"{len(recent)} cycles")

    if created and not tested:
        fire(BELIEF_TESTING_STALLED,
             f"{created} expectations preregistered across {len(usable)} "
             f"cycles and not one has ever resolved informatively; no belief "
             f"in the engine has been tested", "CRITICAL")

    # A backlog is only growing if it is growing FASTER than it is drained.
    open_now = created - tested
    if open_now > 0 and not tested:
        fire(EXPECTATION_BACKLOG_GROWING,
             f"{open_now} expectations are open and none has ever resolved")

    reversal = health.knowledge.get("knowledge_later_reversed")
    if _is_number(reversal) and reversal > 0:
        total = health.knowledge.get("net_new_knowledge") or 0
        if _is_number(total) and total and reversal / total > 0.25:
            fire(KNOWLEDGE_REVERSAL_RATE_RISING,
                 f"{reversal} of {total} knowledge updates were later "
                 f"reversed")

    fp = health.calibration.get("false_positive_rate")
    if _is_number(fp) and fp > 0.5:
        fire(FALSE_POSITIVE_RATE_RISING,
             f"false positive rate {fp:.0%} across the resolved sample")

    written = health.founder_utility.get("strategic_dossiers_written")
    if _is_number(written) and written == 0:
        fire(FOUNDER_UTILITY_DROPPING,
             "no strategic dossier was published; nothing the engine learned "
             "can reach a founder decision")

    # A stage that used to convert and now converts nothing is a regression,
    # and it is invisible in the aggregate funnel because the aggregate still
    # carries the old successes.
    if len(usable) >= MIN_CYCLES_FOR_VELOCITY:
        half = len(usable) // 2
        early, late = usable[:half], usable[half:]
        for upper, lower in zip(LEARNING_CHAIN, LEARNING_CHAIN[1:]):
            before = _rate(sum(o.stage(lower) for o in early),
                           sum(o.stage(upper) for o in early))
            after = _rate(sum(o.stage(lower) for o in late),
                          sum(o.stage(upper) for o in late))
            if _is_number(before) and _is_number(after) \
                    and before > 0 and after == 0:
                fire(PIPELINE_STAGE_REGRESSION,
                     f"{lower} converted at {before:.0%} in earlier cycles "
                     f"and converts nothing now")

    cov = health.coverage or {}
    glob_now = cov.get("global", {}).get("companies_observed")
    watch = cov.get("watchlist", {}).get("companies_with_evidence")
    if _is_number(glob_now) and _is_number(watch) and glob_now and \
            watch / max(glob_now, 1) > 0.95 and glob_now < 10:
        fire(WATCHLIST_COVERAGE_DROPPING,
             "commercial observation has collapsed onto the watchlist; "
             "global coverage is no longer being maintained")

    return out


# ---------------------------------------------------------------------------
# global vs watchlist coverage
# ---------------------------------------------------------------------------
def coverage(evidence: Sequence[dict], beliefs: Sequence[dict],
             *, watchlist: Sequence[str] = ()) -> Dict[str, object]:
    """Broad commercial learning, measured apart from watchlist depth.

    Kept separate on purpose. Optimising the watchlist will always improve
    the headline numbers, and a world model that only knows twenty-eight
    companies deeply is not a world model. If these two were one figure, the
    trade-off between them would be invisible exactly when it mattered.
    """
    watch = {str(w).replace("-", "_").lower() for w in watchlist}
    by_company = collections.Counter(
        str(e.get("subject_company") or "").lower() for e in evidence
        if e.get("subject_company"))
    families = collections.Counter(
        str(e.get("evidence_type") or "") for e in evidence
        if e.get("evidence_type"))
    belief_companies = collections.Counter(
        str(b.get("subject") or "").lower() for b in beliefs)

    observed = set(by_company)
    watch_observed = observed & watch if watch else set()

    return {
        "global": {
            "companies_observed": len(observed),
            "companies_with_active_memory": len(belief_companies),
            "event_families_covered": len(families),
            "event_families": dict(families.most_common()),
            "evidence_items": len(evidence),
        },
        "watchlist": {
            "companies": len(watch),
            "companies_with_evidence": len(watch_observed),
            "coverage_rate": _rate(len(watch_observed), len(watch)),
            "belief_density": _rate(
                sum(belief_companies[c] for c in watch_observed),
                len(watch_observed)),
        },
        "off_watchlist_companies_observed": len(observed - watch),
    }


# ---------------------------------------------------------------------------
# assembly
# ---------------------------------------------------------------------------
def assess(*, root: pathlib.Path, as_of: str, store=None,
           runtime_sha: str = "") -> LearningHealth:
    """Read the real runtime and answer the question this module is named for.

    Everything here comes from persisted artefacts -- the append-only ledger,
    the per-cycle reports, the published dossiers. Nothing is inferred from
    source code, because source code says what should happen and this module
    exists because what should happen was not happening.
    """
    root = pathlib.Path(root)
    if store is None:
        from . import learning_store as LS
        store = LS.LearningStore(root / LS.DEFAULT_PATH)

    rows = store._rows()
    evidence = [r for r in rows if r.get("record") == "evidence"]
    belief_rows = [r for r in rows if r.get("record") == "belief"]
    expectation_rows = [r for r in rows if r.get("record") == "expectation"]
    reconciliations = [r for r in rows if r.get("record") == "reconciliation"]

    observations = load_cycle_observations(root)
    health = LearningHealth(as_of=as_of[:10], runtime_sha=runtime_sha)

    # --- A. observation / evidence ---------------------------------------
    ages = []
    today = _date(as_of)
    for e in evidence:
        seen = _date(e.get("observed_at"))
        if seen and today:
            ages.append((today - seen).days)
    health.observation = {
        "cycles_observed": len(observations),
        "companies_evaluated": len({e.get("subject_company")
                                    for e in evidence}),
        "documents_considered": sum(o.documents_considered
                                    for o in observations),
        "candidate_event_sentences": sum(o.candidate_event_sentences
                                         for o in observations),
        "accepted_evidence": len(evidence),
        "duplicate_evidence": sum(o.duplicate_evidence for o in observations),
        "evidence_by_family": dict(collections.Counter(
            e.get("evidence_type") for e in evidence).most_common()),
        "evidence_by_company": dict(collections.Counter(
            e.get("subject_company") for e in evidence).most_common(20)),
        "evidence_age_days": {
            "median": statistics.median(ages) if ages else UNMEASURABLE,
            "max": max(ages) if ages else UNMEASURABLE},
        "stale_evidence": sum(1 for a in ages if a > 90),
        "self_authored": sum(1 for e in evidence if e.get("self_authored")),
    }

    # --- B. beliefs -------------------------------------------------------
    tested_ids = {r.get("hypothesis_id") for r in reconciliations
                  if r.get("outcome") in ("CONFIRMED", "PARTIALLY_CONFIRMED",
                                          "CONTRADICTED")}
    lifecycle = collections.Counter(b.get("lifecycle_state")
                                    for b in belief_rows)
    health.belief = {
        "beliefs_total": len(belief_rows),
        "beliefs_new": sum(o.beliefs_accepted for o in observations),
        "beliefs_strengthened": sum(o.beliefs_strengthened
                                    for o in observations),
        "beliefs_weakened": sum(o.beliefs_weakened for o in observations),
        "beliefs_retired": sum(o.beliefs_retired for o in observations),
        "beliefs_decayed": sum(o.beliefs_decayed for o in observations),
        "beliefs_never_tested": sum(1 for b in belief_rows
                                    if b.get("belief_id") not in tested_ids),
        "beliefs_by_lifecycle": dict(lifecycle),
        "beliefs_by_company": dict(collections.Counter(
            b.get("subject") for b in belief_rows).most_common(20)),
        "beliefs_with_contradicting_evidence": sum(
            1 for b in belief_rows if b.get("contradicting_evidence_ids")),
        "beliefs_without_recent_support": sum(
            1 for b in belief_rows if not b.get("last_validated")),
        "test_rate": _rate(len(tested_ids), len(belief_rows)),
    }

    # --- C. expectations --------------------------------------------------
    due = overdue = 0
    for row in expectation_rows:
        ends = _date(row.get("evaluation_window_ends"))
        if ends and today and ends <= today:
            due += 1
            if row.get("expectation_id") not in tested_ids:
                overdue += 1
    outcomes = collections.Counter(r.get("outcome") for r in reconciliations)
    resolution_days = []
    by_id = {r.get("expectation_id"): r for r in expectation_rows}
    for rec in reconciliations:
        start = _date((by_id.get(rec.get("expectation_id"))
                       or {}).get("preregistered_at"))
        end = _date(rec.get("evaluated_at"))
        if start and end:
            resolution_days.append((end - start).days)
    health.expectation = {
        "expectations_total": len(expectation_rows),
        "expectations_preregistered": sum(o.expectations_created
                                          for o in observations),
        "expectations_due": due,
        "expectations_tested": sum(o.expectations_evaluated
                                   for o in observations),
        "expectations_confirmed": outcomes.get("CONFIRMED", 0),
        "expectations_contradicted": outcomes.get("CONTRADICTED", 0),
        "expectations_partially_confirmed": outcomes.get(
            "PARTIALLY_CONFIRMED", 0),
        "expectations_unmeasurable": outcomes.get("UNMEASURABLE", 0),
        "expectations_too_early": sum(o.expectations_too_early
                                      for o in observations),
        "expectations_without_observation": overdue,
        "median_time_to_resolution": (statistics.median(resolution_days)
                                      if resolution_days else UNMEASURABLE),
        "soonest_window_close": min(
            (str(r.get("evaluation_window_ends"))[:10]
             for r in expectation_rows), default=UNMEASURABLE),
    }

    # --- D-F. hidden state, interaction, causal ---------------------------
    health.hidden_state = {
        "companies_tracked": max((o.hidden_states_tracked
                                  for o in observations), default=0),
        "states_changed": sum(o.hidden_states_moved for o in observations),
    }
    health.interaction = {
        "interactions_observed": sum(o.interactions_observed
                                     for o in observations),
    }
    health.causal = {
        "causal_paths_total": max((o.causal_edges for o in observations),
                                  default=0),
    }

    # --- G. information value --------------------------------------------
    health.information_value = {
        "information_priorities_total": sum(o.information_priorities
                                            for o in observations),
    }

    # --- H-I. counterfactual and calibration ------------------------------
    resolved = (outcomes.get("CONFIRMED", 0)
                + outcomes.get("PARTIALLY_CONFIRMED", 0)
                + outcomes.get("CONTRADICTED", 0))
    # Below the minimum sample every one of these is a number that would be
    # read as a measurement and is not one.
    if resolved < MIN_RESOLVED_FOR_CALIBRATION:
        health.calibration = {
            "effective_sample_size": resolved,
            "belief_calibration": UNMEASURABLE,
            "expectation_calibration": UNMEASURABLE,
            "false_positive_rate": UNMEASURABLE,
            "false_negative_rate": UNMEASURABLE,
            "brier_or_equivalent": UNMEASURABLE,
            "because": f"{resolved} informative resolutions on record; "
                       f"{MIN_RESOLVED_FOR_CALIBRATION} is the minimum at "
                       f"which any of these stops being noise",
        }
    else:
        confirmed = outcomes.get("CONFIRMED", 0) + outcomes.get(
            "PARTIALLY_CONFIRMED", 0)
        health.calibration = {
            "effective_sample_size": resolved,
            "expectation_calibration": confirmed / resolved,
            "false_positive_rate": outcomes.get("CONTRADICTED", 0) / resolved,
            "false_negative_rate": UNMEASURABLE,
            "belief_calibration": confirmed / resolved,
            "brier_or_equivalent": UNMEASURABLE,
        }
    health.counterfactual = {
        "near_misses": 0,
        "rejected_cases_later_supported": UNMEASURABLE,
        "accepted_cases_later_failed": UNMEASURABLE,
        "because": "counterfactual scoring needs resolved outcomes",
    } if resolved < MIN_RESOLVED_FOR_CALIBRATION else {
        "near_misses": 0,
        "rejected_cases_later_supported": 0,
        "accepted_cases_later_failed": outcomes.get("CONTRADICTED", 0),
    }

    # --- J. knowledge -----------------------------------------------------
    # Counted from the LEDGER, not from the cycle reports. A reconciliation is
    # knowledge the moment it is written; waiting for a report to mention it
    # would make health lag the thing it measures.
    validated = max(sum(o.validated_knowledge for o in observations), resolved)
    health.knowledge = {
        "net_new_knowledge": validated,
        "hypotheses_declared": len(belief_rows),
        "revalidated_knowledge": sum(1 for b in belief_rows
                                     if b.get("last_validated")),
        "duplicated_noop_evidence": sum(o.duplicate_evidence
                                        for o in observations),
        "retired_knowledge": sum(o.beliefs_retired for o in observations),
        "knowledge_per_cycle": _rate(validated, len(observations)),
        "knowledge_per_valid_evidence_item": _rate(validated, len(evidence)),
        "knowledge_survival_rate": _rate(
            sum(1 for b in belief_rows
                if b.get("belief_id") in tested_ids
                and b.get("lifecycle_state") == "ACTIVE"),
            len(tested_ids)),
        "knowledge_later_reversed": 0 if not tested_ids else UNMEASURABLE,
    }

    # --- K. founder utility ----------------------------------------------
    strategic_dir = root / "reports" / "market" / "strategic"
    published = sorted(p.stem for p in strategic_dir.glob("*.json")) \
        if strategic_dir.exists() else []
    # Consumption comes from the founder side's own acknowledgements, read
    # from the ledger it writes beside the dossiers it reads. An absent ledger
    # stays UNMEASURABLE rather than becoming zero: "nobody told us" and
    # "nobody used it" are opposite findings and only one of them is bad.
    from . import dossier_consumption as DC
    consumption = DC.summarise(root, published=len(published))
    health.founder_utility = {
        "strategic_dossiers_written": len(published),
        "strategic_dossiers_consumed": consumption.get("dossiers_used"),
        "consumption": consumption,
        "founder_utility_status": consumption.get("founder_utility_status"),
        "beliefs_relevant_to_founder_decisions": sum(
            1 for b in belief_rows
            if str(b.get("subject", "")).replace("_", "-").lower()
            in {p.lower() for p in published}),
        "founder_decisions_sharpened": UNMEASURABLE,
    }

    # --- velocity, acceleration, cohorts, funnel, status, alerts ----------
    health.velocity = {
        f"{d}d": velocity(observations, as_of=as_of, days=d) for d in WINDOWS}
    health.acceleration = {
        f"{d}d": acceleration(observations, as_of=as_of, days=d)
        for d in WINDOWS}
    health.cohorts = [c.as_dict() for c in cohorts(
        belief_rows, reconciliations, dossier_subjects=published)]
    # --- mechanism calibration -------------------------------------------
    # An outcome does not only revise the belief it tested; it revises the
    # standing of the MECHANISM that generated the expectation. Without this,
    # a transmission hypothesis that has been wrong every time it was checked
    # keeps proposing beliefs at full strength forever.
    from . import mechanism_calibration as MC
    health.mechanisms = MC.summarise(MC.calibrate(rows))

    health.funnel = funnel(observations, ledger_totals={
        "expectations_resolved": resolved,
        "expectations_due": due + resolved,
        "validated_knowledge": resolved,
    })

    # When the block is at "did any expectation ever become scoreable", the
    # funnel alone cannot name the owner -- see `why_unscoreable`.
    bottleneck = health.funnel.get("bottleneck") or {}
    if bottleneck.get("stage") == "expectations_due":
        diagnosis = why_unscoreable(expectation_rows, evidence, as_of=as_of)
        if diagnosis.get("cause"):
            bottleneck["owner"] = diagnosis["cause"]
            bottleneck["because"] = diagnosis["because"]
            bottleneck["diagnosis"] = diagnosis
            health.funnel["because"] = diagnosis["because"]

    from . import universe_tiers as UT
    try:
        watchlist = [s.symbol for s in UT.tier_0()]
    except Exception:  # noqa: BLE001 - coverage must not depend on the universe
        watchlist = []
    health.coverage = coverage(evidence, belief_rows, watchlist=watchlist)

    health.status = classify(observations, as_of=as_of,
                             bottleneck=health.funnel.get("bottleneck"))
    health.alerts = alerts(observations, health)
    return health


# ---------------------------------------------------------------------------
# history -- bounded, append-only
# ---------------------------------------------------------------------------
HISTORY_PATH = "reports/market/learning_health_history.jsonl"
MAX_HISTORY_ROWS = 400


def append_snapshot(health: LearningHealth, *, root: pathlib.Path,
                    path: str = HISTORY_PATH) -> bool:
    """Persist one bounded snapshot. Idempotent on (as_of, contract).

    Health needs history for the same reason the engine does: today's number
    means nothing without yesterday's. Bounded because an operator file that
    grows without limit becomes a file nobody opens.
    """
    target = pathlib.Path(root) / path
    target.parent.mkdir(parents=True, exist_ok=True)
    snapshot = {
        "contract": CONTRACT, "as_of": health.as_of,
        "runtime_sha": health.runtime_sha,
        "status": health.status.get("status"),
        "bottleneck": (health.funnel.get("bottleneck") or {}).get("owner"),
        "beliefs_total": health.belief.get("beliefs_total"),
        "beliefs_never_tested": health.belief.get("beliefs_never_tested"),
        "expectations_total": health.expectation.get("expectations_total"),
        "expectations_resolved": (
            health.expectation.get("expectations_confirmed", 0)
            + health.expectation.get("expectations_contradicted", 0)),
        "net_new_knowledge": health.knowledge.get("net_new_knowledge"),
        "evidence_items": health.observation.get("accepted_evidence"),
        "companies_observed": health.coverage.get("global", {}).get(
            "companies_observed"),
        "dossiers_written": health.founder_utility.get(
            "strategic_dossiers_written"),
        "alerts": [a["alert"] for a in health.alerts],
    }

    existing: List[dict] = []
    if target.exists():
        for line in target.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                existing.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    if any(r.get("as_of") == snapshot["as_of"]
           and r.get("contract") == CONTRACT for r in existing):
        return False
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(snapshot, sort_keys=True) + "\n")
    # Trim from the FRONT only, and only whole rows. History is append-only
    # for readers; the bound is maintenance, not editing.
    if len(existing) + 1 > MAX_HISTORY_ROWS:
        kept = (existing + [snapshot])[-MAX_HISTORY_ROWS:]
        target.write_text(
            "".join(json.dumps(r, sort_keys=True) + "\n" for r in kept),
            encoding="utf-8")
    return True


def read_history(root: pathlib.Path,
                 path: str = HISTORY_PATH) -> Tuple[dict, ...]:
    target = pathlib.Path(root) / path
    if not target.exists():
        return ()
    out = []
    for line in target.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return tuple(out)


# ---------------------------------------------------------------------------
# the operator surface
# ---------------------------------------------------------------------------
# NOT a founder surface. Everything below is engineering telemetry about how
# the engine learns, which is exactly the material a founder should never be
# shown: it invites reading a pipeline conversion rate as a business fact.
def _fmt(value: object) -> str:
    if value is UNMEASURABLE or value == UNMEASURABLE:
        return "unmeasured"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def _pct(value: object) -> str:
    if not _is_number(value):
        return "unmeasured"
    return f"{value:.0%}"


def render(health: LearningHealth) -> str:
    """The operator report, answering the nine questions in order.

    Written so the first eight lines are enough on a normal day. An operator
    who has to read a table to find out whether the engine is learning will
    stop reading it, and then the measurement exists but the loop does not.
    """
    d = health.as_dict()
    status = d["status"]
    bottleneck = (d["funnel"].get("bottleneck") or {})
    belief, expectation = d["belief_health"], d["expectation_health"]
    knowledge, calibration = d["knowledge_health"], d["calibration"]
    utility, cov = d["founder_utility"], d["coverage"]

    lines = [
        f"# Market learning health — {d['as_of']}",
        "",
        f"**Learning status: {status['status']}**",
        f"{status.get('because', '')}",
        "",
        f"- Runtime: `{d['runtime_sha'] or 'unknown'}`",
        f"- Cycles with the learning pipeline: "
        f"{d['observation_health']['cycles_observed']}",
        "",
        "## Where the bottleneck is",
        "",
    ]
    if bottleneck:
        lines += [
            f"**{bottleneck.get('owner')}** — at stage "
            f"`{bottleneck.get('stage')}`.",
            "",
            bottleneck.get("because", ""),
            "",
        ]
    else:
        lines += ["No stage has been entered yet.", ""]

    lines += [
        "## What the engine knows, and how much of it has been tested",
        "",
        f"- Beliefs held: {belief['beliefs_total']}",
        f"- Ever tested: {_pct(belief['test_rate'])} "
        f"({belief['beliefs_never_tested']} never tested)",
        f"- Confirmed / contradicted: "
        f"{expectation['expectations_confirmed']} / "
        f"{expectation['expectations_contradicted']}",
        f"- Validated knowledge: {knowledge['net_new_knowledge']}",
        f"- Expectation calibration: "
        f"{_fmt(calibration['expectation_calibration'])} "
        f"(n={calibration['effective_sample_size']})",
        "",
    ]
    if calibration.get("because"):
        lines += [f"_{calibration['because']}_", ""]

    lines += [
        "## Is learning speeding up?",
        "",
    ]
    seven = d["acceleration"].get("7d") or {}
    if seven.get("status") != "MEASURED":
        lines += [
            "Not answerable yet — there is no prior 7-day window of equal "
            "length to compare against. Reported as unmeasured rather than "
            "as flat.",
            "",
        ]
    else:
        for name, row in sorted(seven.get("series", {}).items()):
            lines.append(f"- {name}: {row['current']:.2f}/day "
                         f"vs {row['prior']:.2f}/day ({row['direction']})")
        lines.append("")

    mech = d.get("mechanism_calibration") or {}
    if mech:
        lines += [
            "## Which mechanisms were tested rather than assumed",
            "",
            f"- Tested: {mech.get('mechanisms_tested')} of "
            f"{mech.get('mechanisms_total')} "
            f"({mech.get('tests_total')} tests, "
            f"{mech.get('confirmations')} confirmed, "
            f"{mech.get('contradictions')} contradicted)",
        ]
        for row in mech.get("mechanisms", []):
            if not row.get("tested"):
                continue
            lines.append(
                f"  - `{row['mechanism']}` — {row['tested']} tests across "
                f"{row['independent_subjects']} companies, "
                f"{row['contradicted']} contradicted → "
                f"{row['maturity']} (reliability {_fmt(row['reliability'])})")
        untested = mech.get("assumed_but_never_tested") or []
        if untested:
            lines.append(f"- Still assumed, never tested: "
                         f"{', '.join(untested)}")
        lines.append("")

    lines += [
        "## Is the learning reaching a founder?",
        "",
        f"- Strategic dossiers written: "
        f"{utility['strategic_dossiers_written']}",
        f"- Used in founder reasoning: "
        f"{_fmt(utility['strategic_dossiers_consumed'])}",
        f"- Status: **{utility.get('founder_utility_status')}**",
    ]
    consumption = utility.get("consumption") or {}
    if consumption.get("because"):
        lines.append(f"  _{consumption['because']}_")
    elif consumption:
        lines.append(
            f"  received {consumption.get('dossiers_received')} · "
            f"eligible {consumption.get('dossiers_eligible')} · "
            f"used {consumption.get('dossiers_used')} · "
            f"rendered {consumption.get('dossiers_rendered')} "
            f"(rate {_fmt(consumption.get('consumption_rate'))})")

    lines += [
        "",
        "## Commercial coverage",
        "",
        f"- Companies observed (global): "
        f"{cov.get('global', {}).get('companies_observed')}",
        f"- Event families covered: "
        f"{cov.get('global', {}).get('event_families_covered')}",
        f"- Priority watchlist covered: "
        f"{_pct(cov.get('watchlist', {}).get('coverage_rate'))} "
        f"of {cov.get('watchlist', {}).get('companies')}",
        f"- Observed off the watchlist: "
        f"{cov.get('off_watchlist_companies_observed')}",
        "",
    ]

    if d["alerts"]:
        lines += ["## Alerts", ""]
        for alert in d["alerts"]:
            lines.append(f"- **{alert['alert']}** ({alert['severity']}) — "
                         f"{alert['detail']}")
        lines.append("")
    else:
        lines += ["## Alerts", "", "None.", ""]

    return "\n".join(lines)
