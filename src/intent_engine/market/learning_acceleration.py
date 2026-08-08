"""Is the engine learning FASTER — and is it learning as WELL?

THE FAILURE THIS MODULE IS BUILT AGAINST
----------------------------------------
A rate metric that only counts things going up will, given a few weeks,
reward exactly the behaviours this project has already had to take back:

    duplicate evidence          the same wire story from a second outlet
    self-tests                  an expectation "resolved" by the evidence
                                that opened it — 20 of those fired live
    backfill                    reprocessing the standing pool and calling
                                the result a day's learning
    restatement                 a belief redeclared, counted twice
    cosmetic founder changes    a dossier rewritten, nothing decided

Every one of those raises volume. None is knowledge. So VOLUME NEVER SETS
THE STATUS ON ITS OWN: quality gates it, and there is no path to
ACCELERATING while any quality dimension is degrading. A run that ingests
twice as much and confirms half as reliably is DEGRADING, and the module
says so in those words.

WHY THE WINDOWS ARE MOSTLY EMPTY, AND STAY THAT WAY
---------------------------------------------------
The engine has SIX cycles that ran the learning pipeline. The eleven earlier
reports predate it and are not comparable, so they are excluded rather than
counted as quiet cycles — a zero from a cycle that had no pipeline is not a
cycle that learned nothing.

That means the 7-, 14- and 30-cycle windows read INSUFFICIENT_HISTORY, with
the real count attached. Computing them anyway over six cycles would produce
a number, and the number would be a lie about its own sample. `UNMEASURABLE`
is not zero, and neither is `INSUFFICIENT_HISTORY`.

THE BACKLOG CYCLE IS EXCLUDED FROM EVERY RATE
---------------------------------------------
The first cycle to accept beliefs saw the standing evidence pool, not a day's
arrivals. Including it makes every later cycle look like a collapse. It is
counted in the totals and excluded from the trends, and both facts are
reported.
"""
from __future__ import annotations

import collections
import statistics
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

CONTRACT = "learning_acceleration.v1"

# --- statuses ---------------------------------------------------------------
ACCELERATING = "ACCELERATING"
STABLE = "STABLE"
PLATEAUING = "PLATEAUING"
DEGRADING = "DEGRADING"
INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
STATUSES = (ACCELERATING, STABLE, PLATEAUING, DEGRADING,
            INSUFFICIENT_HISTORY)

# --- windows ----------------------------------------------------------------
#: A window needs at least two comparable halves to have a direction at all.
MIN_CYCLES_FOR_TREND = 4

RECENT = "recent"
#: `recent` is the SHORTEST window that can carry a direction, not the last
#: cycle. A one-cycle window has no halves to compare, so it can report
#: counts and never a trend — and a trend is the whole question.
WINDOWS: Tuple[Tuple[str, int], ...] = (
    (RECENT, MIN_CYCLES_FOR_TREND), ("7_cycle", 7), ("14_cycle", 14),
    ("30_cycle", 30))

#: Below this, a change is noise. Matches `learning_health.MATERIAL_CHANGE`
#: so the two reports cannot disagree about whether something moved.
MATERIAL_CHANGE = 0.20

# --- what a cycle produced --------------------------------------------------
NEW_KNOWLEDGE = "NEW_KNOWLEDGE"
NO_OP = "NO_OP"
DUPLICATE = "DUPLICATE"
RESTATEMENT = "RESTATEMENT"
CLASSES = (NEW_KNOWLEDGE, NO_OP, DUPLICATE, RESTATEMENT)

# --- quality dimensions -----------------------------------------------------
#
# Each is a RATE with a stated direction of goodness. `higher_is_better` is
# carried rather than assumed, because half of these are error rates and a
# composite that averaged them all in the same direction would rank a rising
# false-positive rate as improvement.
QUALITY_DIMENSIONS: Tuple[Tuple[str, bool], ...] = (
    ("calibration_quality", True),
    ("contradiction_reachability", True),
    ("source_diversity", True),
    ("independent_confirmation", True),
    ("false_positive_rate", False),
    ("self_test_rate", False),
    ("no_op_rate", False),
    ("belief_revision_rate", True),
    ("decision_impact_rate", True),
    ("knowledge_freshness", True),
)
QUALITY_NAMES = tuple(name for name, _ in QUALITY_DIMENSIONS)

#: ABSOLUTE degradation conditions, checked on the LEVEL rather than the
#: trend. A trend-only rule has a blind spot that this module hit on its
#: first live run: the self-test rate went from undefined (nothing to guard)
#: to 0.8, which is not a "decline" in any comparable sense and is plainly
#: not a healthy engine. Four out of five of its would-be resolutions were
#: the evidence that opened the belief.
#:
#: Each is (dimension, comparison, threshold, why).
ABSOLUTE_LIMITS: Tuple[Tuple[str, str, float, str], ...] = (
    ("self_test_rate", ">", 0.5,
     "more than half of the engine's would-be resolutions were the evidence "
     "that opened the belief; it is marking its own homework"),
    ("no_op_rate", ">", 0.5,
     "most cycles in this window ingested evidence and moved nothing"),
    ("false_positive_rate", ">", 0.5,
     "more than half the beliefs declared committed to something no "
     "observation could refute"),
    ("knowledge_freshness", "<", 0.5,
     "most of what was ingested was already in the ledger"),
    ("contradiction_reachability", "==", 0.0,
     "nothing in this window contradicted anything: a reconciliation set "
     "that never reaches disagreement is a report about the filter, not a "
     "strong engine"),
)

#: `contradiction_reachability == 0` only means something once there are
#: enough reconciliations for a zero to be surprising.
MIN_RECONCILIATIONS_FOR_REACHABILITY = 5


@dataclass(frozen=True)
class WindowReport:
    """One window's counts, rates and direction — or why it has none."""
    window: str
    cycles_required: int
    cycles_available: int
    status: str
    reason: str
    metrics: Dict[str, float] = field(default_factory=dict)
    quality: Dict[str, Optional[float]] = field(default_factory=dict)
    volume_direction: str = ""
    quality_direction: str = ""
    degradations: Tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {
            "window": self.window,
            "cycles_required": self.cycles_required,
            "cycles_available": self.cycles_available,
            "status": self.status, "reason": self.reason,
            "metrics": dict(self.metrics), "quality": dict(self.quality),
            "volume_direction": self.volume_direction,
            "quality_direction": self.quality_direction,
            "degradations": list(self.degradations),
        }


def _observation_metrics(obs) -> Dict[str, float]:
    """One cycle, as the counts §5 asks for. Missing fields read zero."""
    def get(name: str) -> float:
        return float(getattr(obs, name, 0) or 0)

    accepted = get("accepted_evidence")
    duplicates = get("duplicate_evidence")
    # From observation binding, not belief formation. Reading the wrong
    # refusal dictionary made `self_test_rate` report 0.0 for a window in
    # which the guard fired twenty times.
    self_tests = get("self_tests_refused")
    return {
        "evidence_ingested": accepted + duplicates,
        "unique_evidence": accepted,
        "duplicate_evidence": duplicates,
        "self_tests_refused": self_tests,
        "beliefs_declared": get("beliefs_accepted"),
        "beliefs_strengthened": get("beliefs_strengthened"),
        "beliefs_weakened": get("beliefs_weakened"),
        "beliefs_retired": get("beliefs_retired"),
        "knowledge_decay_events": get("beliefs_decayed"),
        "expectations_created": get("expectations_created"),
        "informative_reconciliations": get("expectations_resolved"),
        "mechanisms_tested": get("expectations_evaluated"),
        "hidden_states_updated": get("hidden_states_moved"),
        "causal_episodes": get("expectations_resolved"),
        "causal_edges_tested": get("causal_edges"),
        "relationships_added": get("interactions_observed"),
        "interactions_added": get("interactions_observed"),
        "cross_actor_expectations": 0.0,
        "VOI_items": get("information_priorities"),
        "research_priorities": get("information_priorities"),
        "Founder_consumption": get("dossiers_written"),
        "companies_with_new_evidence": get("companies_with_new_evidence"),
        "candidate_event_sentences": get("candidate_event_sentences"),
        "documents_considered": get("documents_considered"),
    }


def classify_cycle(metrics: Dict[str, float], *, backlog: bool) -> str:
    """What CLASS of thing a cycle produced. Counts alone cannot say."""
    if backlog:
        # It drained a standing pool. Real work, not a day's learning rate.
        return RESTATEMENT
    if metrics.get("beliefs_declared") or \
            metrics.get("informative_reconciliations"):
        return NEW_KNOWLEDGE
    if metrics.get("duplicate_evidence") and not metrics.get(
            "unique_evidence"):
        return DUPLICATE
    if metrics.get("unique_evidence"):
        return NO_OP          # evidence arrived and moved nothing
    return NO_OP


def quality(observations: Sequence, *, ledger: Sequence[dict] = (),
            decision_impacts: int = 0) -> Dict[str, Optional[float]]:
    """The ten quality dimensions, or None where nothing measures them.

    `None` is deliberate and is NOT zero. A dimension with no telemetry and a
    dimension measured at zero call for opposite responses, and this project
    has already shipped one metric that collapsed them.
    """
    if not observations:
        return {name: None for name in QUALITY_NAMES}

    totals: Dict[str, float] = collections.Counter()
    for obs in observations:
        for key, value in _observation_metrics(obs).items():
            totals[key] += value

    unfalsifiable = float(sum(
        (getattr(o, "binding_refused", {}) or {}).get(
            "family_not_falsifiable_by_observation", 0)
        for o in observations))
    ingested = totals["evidence_ingested"]
    unique = totals["unique_evidence"]
    resolved = totals["informative_reconciliations"]
    evaluated = max(totals["mechanisms_tested"], unfalsifiable)
    declared = totals["beliefs_declared"]
    strengthened = totals["beliefs_strengthened"]
    weakened = totals["beliefs_weakened"]

    contradictions = weakened
    reconciliations = strengthened + weakened
    # Both halves of this ratio must come from the SAME population. Counting
    # the ledger's distinct subjects over the WINDOW's reconciliations was a
    # share of 9 out of 1 the moment the two diverged — caught by `rate`,
    # which raises rather than clamping, and found by a break proof rather
    # than by a test.
    ledger_reconciliations = [r for r in ledger
                              if r.get("record") == "reconciliation"]
    subjects = {str(r.get("subject") or "")
                for r in ledger_reconciliations} - {""}
    sources = {str(r.get("source_role") or "") for r in ledger
               if r.get("record") == "evidence"} - {""}

    def rate(num: float, den: float) -> Optional[float]:
        """A proportion, or None. Never a number greater than one.

        Every dimension here except `source_diversity` is a share of a
        population, and a share above 1.0 means the numerator and the
        denominator count different things. Clamping would hide that, so it
        is caught here and the mismatch is reported rather than rounded.
        """
        if not den:
            return None
        if num > den:
            raise ValueError(
                f"a share of {num} out of {den} counts two different "
                f"populations; fix the denominator rather than the number")
        return round(num / den, 4)

    classes = collections.Counter(
        classify_cycle(_observation_metrics(o),
                       backlog=bool(getattr(o, "backlog_drain", False)))
        for o in observations)

    return {
        # Of the expectations that were EVALUATED, how many actually
        # discriminated. A pipeline whose evaluations mostly return
        # TOO_EARLY is not calibrating anything.
        "calibration_quality": rate(resolved, evaluated),
        # Could the engine have been wrong? A reconciliation set with no
        # contradictions in it is not a strong engine; it is a filter that
        # cannot reach disagreement.
        "contradiction_reachability": rate(contradictions, reconciliations),
        "source_diversity": float(len(sources)) if sources else None,
        "independent_confirmation": (
            rate(len(subjects), len(ledger_reconciliations))
            if ledger_reconciliations else None),
        # Of the expectations EXAMINED, how many belong to a family no
        # observation could refute. The denominator is examinations, not
        # beliefs declared this cycle: binding examines every open
        # expectation, including ones from earlier cycles, so dividing by
        # this cycle's declarations produced a "rate" of 1.44.
        "false_positive_rate": rate(unfalsifiable, evaluated),
        "self_test_rate": rate(totals["self_tests_refused"],
                               totals["self_tests_refused"] + resolved),
        "no_op_rate": rate(classes[NO_OP] + classes[DUPLICATE],
                           len(observations)),
        "belief_revision_rate": rate(reconciliations, declared),
        "decision_impact_rate": rate(decision_impacts,
                                     totals["Founder_consumption"]),
        "knowledge_freshness": rate(unique, ingested),
    }


def _direction(current: float, prior: float) -> str:
    if prior == 0:
        return "UP" if current > 0 else "FLAT"
    change = (current - prior) / abs(prior)
    if change > MATERIAL_CHANGE:
        return "UP"
    if change < -MATERIAL_CHANGE:
        return "DOWN"
    return "FLAT"


def window(observations: Sequence, *, name: str, size: int,
           ledger: Sequence[dict] = (), decision_impacts: int = 0
           ) -> WindowReport:
    """One window, computed only where the history defends it."""
    usable = [o for o in observations
              if not getattr(o, "backlog_drain", False)]
    available = len(usable)
    if available < size:
        return WindowReport(
            window=name, cycles_required=size, cycles_available=available,
            status=INSUFFICIENT_HISTORY,
            reason=(f"{available} comparable cycle(s) against a window of "
                    f"{size}. Computing it anyway would produce a number "
                    f"about a sample that does not exist"))

    slice_ = usable[-size:]
    totals: Dict[str, float] = collections.Counter()
    for obs in slice_:
        for key, value in _observation_metrics(obs).items():
            totals[key] += value
    metrics = {k: round(v, 4) for k, v in sorted(totals.items())}
    classes = collections.Counter(
        classify_cycle(_observation_metrics(o), backlog=False)
        for o in slice_)
    metrics.update({f"cycles_{c.lower()}": float(classes[c]) for c in CLASSES})
    metrics["zero_trade_learning"] = float(classes[NEW_KNOWLEDGE])

    now = quality(slice_, ledger=ledger, decision_impacts=decision_impacts)

    if size < MIN_CYCLES_FOR_TREND:
        return WindowReport(
            window=name, cycles_required=size, cycles_available=available,
            status=INSUFFICIENT_HISTORY,
            reason=(f"a {size}-cycle window has no two halves to compare; "
                    f"counts are reported, a direction is not"),
            metrics=metrics, quality=now)

    half = max(len(slice_) // 2, 1)
    older, newer = slice_[:half], slice_[half:]

    def volume_of(part) -> float:
        return sum(_observation_metrics(o)["unique_evidence"]
                   + _observation_metrics(o)["beliefs_declared"]
                   + _observation_metrics(o)["informative_reconciliations"]
                   for o in part) / max(len(part), 1)

    volume = _direction(volume_of(newer), volume_of(older))
    before = quality(older, ledger=ledger, decision_impacts=decision_impacts)
    after = quality(newer, ledger=ledger, decision_impacts=decision_impacts)
    reconciliations = int(metrics.get("beliefs_strengthened", 0)
                          + metrics.get("beliefs_weakened", 0))
    degraded = (degradations(before, after)
                + absolute_failures(now, reconciliations=reconciliations))
    quality_direction = _quality_direction(before, after, degraded)

    status, reason = _status(volume, quality_direction, degraded, classes)
    return WindowReport(
        window=name, cycles_required=size, cycles_available=available,
        status=status, reason=reason, metrics=metrics, quality=now,
        volume_direction=volume, quality_direction=quality_direction,
        degradations=tuple(degraded))


def absolute_failures(now: Dict[str, Optional[float]], *,
                      reconciliations: int = 0) -> List[str]:
    """Levels that are unacceptable whatever direction they came from."""
    out: List[str] = []
    for name, comparison, threshold, why in ABSOLUTE_LIMITS:
        value = now.get(name)
        if value is None:
            continue
        if name == "contradiction_reachability" and \
                reconciliations < MIN_RECONCILIATIONS_FOR_REACHABILITY:
            continue
        value = float(value)
        breached = ((comparison == ">" and value > threshold)
                    or (comparison == "<" and value < threshold)
                    or (comparison == "==" and value == threshold))
        if breached:
            out.append(f"{name}={value} ({comparison}{threshold}): {why}")
    return out


def degradations(before: Dict[str, Optional[float]],
                 after: Dict[str, Optional[float]]) -> List[str]:
    """Which dimensions got materially worse. The explicit condition list.

    A dimension that was unmeasured and is now measured is NOT a degradation,
    however the number reads: the change is in the telemetry, not the engine.
    That blind spot is covered by `absolute_failures`, which reads levels.
    """
    out: List[str] = []
    for name, higher_is_better in QUALITY_DIMENSIONS:
        was, now = before.get(name), after.get(name)
        if was is None or now is None:
            continue
        moved = _direction(float(now), float(was))
        if moved == "FLAT":
            continue
        worse = (moved == "DOWN") if higher_is_better else (moved == "UP")
        if worse:
            out.append(f"{name} {was} -> {now}")
    return out


def _quality_direction(before, after, degraded: Sequence[str]) -> str:
    if degraded:
        return "DOWN"
    improved = 0
    for name, higher_is_better in QUALITY_DIMENSIONS:
        was, now = before.get(name), after.get(name)
        if was is None or now is None:
            continue
        moved = _direction(float(now), float(was))
        if moved == "FLAT":
            continue
        if (moved == "UP") == higher_is_better:
            improved += 1
    return "UP" if improved else "FLAT"


def _status(volume: str, quality_direction: str, degraded: Sequence[str],
            classes: collections.Counter) -> Tuple[str, str]:
    """The matrix. Quality gates volume, and never the other way round."""
    # A stall and a decline are different findings, and a window where
    # nothing was learned trips the no-op limit by definition. Reporting
    # that as DEGRADING would be the same fact stated twice under the more
    # alarming name, so a pure stall is PLATEAUING — and anything ELSE
    # degrading alongside it still outranks the stall.
    other = [d for d in degraded if not d.startswith("no_op_rate")]
    if not classes[NEW_KNOWLEDGE] and not other:
        return PLATEAUING, (
            "no cycle in this window declared a belief or resolved an "
            "expectation; evidence arrived and nothing moved. That is a "
            "stall, not a decline")
    if degraded:
        return DEGRADING, (
            f"{len(degraded)} quality dimension(s) got materially worse "
            f"({'; '.join(degraded[:3])}). Volume is {volume}, and volume "
            f"rising while quality falls is the thing this status exists to "
            f"refuse to call acceleration")
    if not classes[NEW_KNOWLEDGE]:
        return PLATEAUING, (
            "no cycle in this window declared a belief or resolved an "
            "expectation; evidence arrived and nothing moved")
    if volume == "UP" and quality_direction in ("UP", "FLAT"):
        return ACCELERATING, (
            f"new knowledge in {classes[NEW_KNOWLEDGE]} of "
            f"{sum(classes.values())} cycles, volume UP, and no quality "
            f"dimension degrading")
    if volume == "DOWN":
        return PLATEAUING, (
            "volume fell with quality steady; the engine is still learning, "
            "less of it")
    return STABLE, (
        f"new knowledge in {classes[NEW_KNOWLEDGE]} of "
        f"{sum(classes.values())} cycles, volume {volume}, quality "
        f"{quality_direction}")


def report(observations: Sequence, *, ledger: Sequence[dict] = (),
           decision_impacts: int = 0) -> dict:
    """Every window that the history defends, and the reason for the rest."""
    windows = [window(observations, name=name, size=size, ledger=ledger,
                      decision_impacts=decision_impacts)
               for name, size in WINDOWS]
    computed = [w for w in windows if w.status != INSUFFICIENT_HISTORY]
    headline = computed[0] if computed else windows[0]
    backlog = [o for o in observations
               if getattr(o, "backlog_drain", False)]
    return {
        "contract": CONTRACT,
        "status": headline.status,
        "reason": headline.reason,
        "cycles_total": len(observations),
        "cycles_comparable": len(observations) - len(backlog),
        "backlog_cycles_excluded": len(backlog),
        "windows": {w.window: w.as_dict() for w in windows},
        "windows_computed": [w.window for w in computed],
        "quality": headline.quality,
        "degradations": list(headline.degradations),
        "note": ("volume never sets the status on its own: a window with any "
                 "degrading quality dimension cannot read ACCELERATING, "
                 "however much it ingested. A None quality reading is "
                 "absent telemetry, not a zero"),
    }
