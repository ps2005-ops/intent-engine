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
EARLY_WARNING_STATUS = "EARLY_WARNING"
STATUSES = (ACCELERATING, STABLE, PLATEAUING, DEGRADING,
            EARLY_WARNING_STATUS, INSUFFICIENT_HISTORY)

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

# --- how much a rate is worth ------------------------------------------------
#
# WHY A RATE WITHOUT ITS DENOMINATOR IS NOT A MEASUREMENT
# -------------------------------------------------------
# `self_test_rate = 0.400` was reported as a headline and drove the whole
# engine's verdict to DEGRADING. Its denominator was FIVE — two self-tests
# and three bindings. The same 0.400 over five hundred would be a finding;
# over five it is two events.
#
# So every rate now carries its numerator, its denominator and a maturity,
# and DEGRADING may not be declared on an immature one. This is not a
# cosmetic improvement to the score: the levels are unchanged and what
# changes is what the engine is entitled to conclude from them.
INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"   # < 10 observations
EARLY = "EARLY"                               # 10-29
USABLE = "USABLE"                             # 30-99
MATURE = "MATURE"                             # 100+
SAMPLE_MATURITIES = (INSUFFICIENT_SAMPLE, EARLY, USABLE, MATURE)

#: Below this a rate may be REPORTED and may not drive a verdict.
MIN_DENOMINATOR_FOR_VERDICT = 10

#: A softer verdict for a real signal on too little evidence. Not "healthy" —
#: the number is what it is — and not DEGRADING either.
EARLY_WARNING = "EARLY_WARNING"


def sample_maturity(denominator: float) -> str:
    if denominator >= 100:
        return MATURE
    if denominator >= 30:
        return USABLE
    if denominator >= MIN_DENOMINATOR_FOR_VERDICT:
        return EARLY
    return INSUFFICIENT_SAMPLE


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

    denominators: Dict[str, Tuple[float, float]] = {}

    def rate(num: float, den: float, name: str = "",
             share: bool = True) -> Optional[float]:
        """A proportion, or None. Never a number greater than one.

        Every dimension here except `source_diversity` is a share of a
        population, and a share above 1.0 means the numerator and the
        denominator count different things. Clamping would hide that, so it
        is caught here and the mismatch is reported rather than rounded.

        `share=False` marks the ratios that are NOT shares. A window may
        revise more beliefs than it declares, because it revises beliefs
        declared in earlier windows — 8 revisions over 6 new declarations is
        a true statement about a healthy engine, not a population mismatch.
        Sending it through the share guard crashed the live report the first
        time revision outpaced declaration.
        """
        if not den:
            return None
        if share and num > den:
            raise ValueError(
                f"a share of {num} out of {den} counts two different "
                f"populations; fix the denominator rather than the number")
        if name:
            denominators[name] = (num, den)
        return round(num / den, 4)

    classes = collections.Counter(
        classify_cycle(_observation_metrics(o),
                       backlog=bool(getattr(o, "backlog_drain", False)))
        for o in observations)

    return {
        # Of the expectations that were EVALUATED, how many actually
        # discriminated. A pipeline whose evaluations mostly return
        # TOO_EARLY is not calibrating anything.
        "calibration_quality": rate(resolved, evaluated, "calibration_quality"),
        # Could the engine have been wrong? A reconciliation set with no
        # contradictions in it is not a strong engine; it is a filter that
        # cannot reach disagreement.
        "contradiction_reachability": rate(contradictions, reconciliations, "contradiction_reachability"),
        "source_diversity": float(len(sources)) if sources else None,
        "independent_confirmation": (
            rate(len(subjects), len(ledger_reconciliations),
                 "independent_confirmation")
            if ledger_reconciliations else None),
        # Of the expectations EXAMINED, how many belong to a family no
        # observation could refute. The denominator is examinations, not
        # beliefs declared this cycle: binding examines every open
        # expectation, including ones from earlier cycles, so dividing by
        # this cycle's declarations produced a "rate" of 1.44.
        "false_positive_rate": rate(unfalsifiable, evaluated, "false_positive_rate"),
        "self_test_rate": rate(totals["self_tests_refused"],
                               totals["self_tests_refused"] + resolved,
                               "self_test_rate"),
        "no_op_rate": rate(classes[NO_OP] + classes[DUPLICATE],
                           len(observations), "no_op_rate"),
        # Revisions PER declaration, not a share of them: the beliefs a
        # window revises were mostly declared before it started.
        "belief_revision_rate": rate(reconciliations, declared,
                                     "belief_revision_rate",
                                     share=False),
        "decision_impact_rate": rate(decision_impacts,
                                     totals["Founder_consumption"],
                                     "decision_impact_rate"),
        "knowledge_freshness": rate(unique, ingested, "knowledge_freshness"),
        # Every rate carries the pair it came from. 0.400 over five is two
        # events; the same number over five hundred is a finding, and a
        # report that shows only the ratio cannot tell them apart.
        "_denominators": dict(denominators),
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
    """Levels that are unacceptable whatever direction they came from.

    Each entry carries the pair it was computed from and that pair's
    maturity, so a caller can tell a finding from two events.
    """
    denominators = now.get("_denominators") or {}
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
            pair = denominators.get(name)
            suffix = ""
            if pair:
                num, den = pair
                suffix = (f" [{num:.0f}/{den:.0f}, "
                          f"{sample_maturity(den)}]")
            out.append(f"{name}={value} ({comparison}{threshold})"
                       f"{suffix}: {why}")
    return out


def _all_immature(failures: Sequence[str]) -> bool:
    """Whether EVERY triggering failure rests on too small a sample.

    One mature failure is enough to justify DEGRADING. All-immature is the
    only case that softens it, and softening means EARLY_WARNING rather
    than silence — the numbers are unchanged and what changes is what the
    engine claims to know from them.
    """
    if not failures:
        return False
    return all(f"{INSUFFICIENT_SAMPLE}]" in f or f"{EARLY}]" in f
               for f in failures)


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
            # Tagged with maturity for the same reason the level checks are:
            # `_all_immature` must judge every failure by its sample, and an
            # untagged trend would be read as mature by default.
            pair = (after.get("_denominators") or {}).get(name)
            suffix = (f" [{pair[0]:.0f}/{pair[1]:.0f}, "
                      f"{sample_maturity(pair[1])}]") if pair else ""
            out.append(f"{name} {was} -> {now}{suffix}")
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
    if degraded and _all_immature(degraded):
        return EARLY_WARNING_STATUS, (
            f"{len(degraded)} quality dimension(s) look wrong and every one "
            f"of them rests on a sample too small to carry a verdict "
            f"({'; '.join(degraded[:2])}). The levels are not softened; the "
            f"conclusion drawn from them is")
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


# ============================================================================
# THE SEVEN CHANNELS
# ============================================================================
#
# WHY CHANNELS AT ALL, WHEN THERE IS ALREADY A STATUS
# ---------------------------------------------------
# Everything above answers one question — is the engine learning faster —
# with one status. That is the wrong shape for the failure this project keeps
# hitting, which is a system that improves TECHNICALLY while learning NOTHING
# ECONOMICALLY. A single composite hides exactly that: wire a producer, fix a
# read path, align a runtime pin, and a blended score goes up in a week where
# no belief moved.
#
# So the channels are computed independently and are never averaged into one
# number. A caller who wants a headline gets the WORST measurable channel,
# not the mean, because a mean of seven is a way of not answering.
#
# WHY THE INPUT IS THE EFFECT LOG AND NOT THE CYCLE COUNTERS
# ----------------------------------------------------------
# `_observation_metrics` reads what a cycle DID: rows accepted, beliefs
# declared, documents considered. Those are activity counts, and a research
# policy optimised against them learns to fetch more documents. A
# `KnowledgeEffect` is the other thing: one evidence item, one knowledge
# object, and what actually happened to it — including NO_CHANGE, which is
# the majority and the only reason the log can price anything.
#
# WHY THE WINDOW KEY IS APPEND ORDER AND NOT `created_at`
# -------------------------------------------------------
# THIS IS THE TRAP IN THIS MODULE AND IT IS WORTH THE PARAGRAPH.
#
# 347 of the 402 live effects are written by the exposure fold, which sets
# `created_at` to the EVIDENCE'S OBSERVATION DATE, not to the day the effect
# was written. It does that on purpose: `effect_id` is keyed on `created_at`,
# so a stable value is what stops a nightly re-derivation of the standing
# evidence pool appending 347 fresh rows every night.
#
# The cost is that `created_at` is not a write time, and windowing on it
# produces a learning history stretching back to February — months in which
# this log did not exist. It would look like a rich trend and it would be
# retrieval time wearing occurrence time's clothes, which is the same defect
# that blocks historical thesis replay one layer down.
#
# The ledger is append-only and carries a `cycle` record at the end of every
# cycle. Position relative to those markers is a TRUE write order, so that is
# the window key. `created_at` is never read here, and a test pins that.
#
# WHAT THIS BUYS TODAY, HONESTLY
# ------------------------------
# 393 of 402 effects were appended in ONE cycle — the cycle that first gave
# the effect log a write path. So effect-based TRENDS have one cycle of
# history and report INSUFFICIENT_HISTORY. The LEVELS are measurable now, and
# the level is already the finding: 373 of 402 effects are NO_CHANGE.

# The NAMES come from `learning_channels`, which already defined four of them
# for declared movements. Importing rather than redeclaring is deliberate: two
# vocabularies for one idea disagree the first week either gains a member, and
# a report that says ECONOMIC_KNOWLEDGE_GAIN in two places must mean the same
# thing in both.
from .learning_channels import (  # noqa: E402
    ALL_CHANNELS as CHANNELS,
    CALIBRATION,
    ECONOMIC_KNOWLEDGE as ECONOMIC,
    FOUNDER_UTILITY as FOUNDER,
    RESEARCH_POLICY as RESEARCH,
    RETENTION,
    SYSTEM_CAPABILITY as SYSTEM,
    UNSUPERVISED_UTILITY as UNSUPERVISED,
)

#: A channel with no telemetry at all. Distinct from a measured zero, and the
#: distinction is the whole point: "no Founder decision was changed" and "no
#: mechanism records whether one was" call for opposite responses.
UNMEASURABLE = "UNMEASURABLE"

CHANNEL_STATUSES = (ACCELERATING, STABLE, PLATEAUING, DEGRADING,
                    EARLY_WARNING_STATUS, INSUFFICIENT_HISTORY, UNMEASURABLE)

#: Target types whose movement is ECONOMIC knowledge. `RESEARCH_QUESTION` and
#: `FOUNDER_DECISION_COMPONENT` are deliberately absent: they belong to the
#: research and Founder channels, and counting them here is how a Founder
#: rewrite would show up as economic learning.
ECONOMIC_TARGETS = frozenset({
    "EVENT", "BELIEF", "EXPECTATION", "CAUSAL_NODE", "CAUSAL_EDGE",
    "MECHANISM", "HYPOTHESIS", "THESIS", "HIDDEN_STATE", "RELATIONSHIP",
    "FALSIFIER", "COUNTERFACTUAL", "ECONOMIC_STATE", "COMPANY_EXPOSURE"})

#: Effect types that assert the knowledge state is different than it was.
#: Mirrors `knowledge_effect.CHANGING` without importing it, because this
#: module is read by the report layer and must not drag the write path in.
CHANGING_EFFECTS = frozenset({"CREATED", "SUPPORTED", "WEAKENED",
                              "CONTRADICTED", "REVISED", "RESOLVED",
                              "DISCRIMINATED", "INVALIDATED"})

#: Below this share of changing effects, a window ingested a great deal and
#: moved almost nothing. Not a failure on its own — most evidence SHOULD
#: change nothing — but the operator is told, because it is the difference
#: between a busy engine and a learning one.
LOW_LEARNING_SHARE = 0.10

#: `research_decision` rows needed before a POLICY claim is allowed. Matches
#: the graph's gate for B-POL-002 so the two cannot disagree.
MIN_RESEARCH_DECISIONS = 100


@dataclass(frozen=True)
class ChannelReport:
    """One learning channel, measured or explicitly not."""
    channel: str
    status: str
    reason: str
    numerator: Optional[float] = None
    denominator: Optional[float] = None
    rate: Optional[float] = None
    maturity: str = INSUFFICIENT_SAMPLE
    window: str = "lifetime"
    trend: str = ""
    detail: Dict[str, object] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "channel": self.channel, "status": self.status,
            "reason": self.reason, "numerator": self.numerator,
            "denominator": self.denominator, "rate": self.rate,
            "maturity": self.maturity, "window": self.window,
            "trend": self.trend, "detail": dict(self.detail),
        }


def _unmeasurable(channel: str, why: str, **detail) -> ChannelReport:
    return ChannelReport(channel=channel, status=UNMEASURABLE, reason=why,
                         detail=detail)


def _rows(ledger: Sequence[dict], record: str) -> List[dict]:
    return [r for r in ledger if r.get("record") == record]


def cycle_segments(ledger: Sequence[dict]) -> List[List[dict]]:
    """The ledger split into cycles by APPEND ORDER, not by any date field.

    A `cycle` record is written at the end of a cycle, so everything since the
    previous marker belongs to the cycle that marker closes. Rows after the
    last marker are a cycle still open and are returned as a final segment —
    dropping them would silently lose the newest learning, and counting them
    as a closed cycle would report a partial cycle as a whole one, so the
    caller is told which it is by position.

    This function exists so that no caller is ever tempted to bucket effects
    by `created_at`. See the section header for why that field cannot carry a
    window.
    """
    segments: List[List[dict]] = []
    current: List[dict] = []
    for row in ledger:
        current.append(row)
        if row.get("record") == "cycle":
            segments.append(current)
            current = []
    if current:
        segments.append(current)
    return segments


def _effect_cycles(ledger: Sequence[dict]) -> List[List[dict]]:
    """Per cycle, the effects appended during it. Cycles with none are kept.

    An empty cycle is data: it is a cycle in which the engine attributed
    nothing, and dropping it would make the rate a rate over productive
    cycles only.
    """
    return [[r for r in seg if r.get("record") == "knowledge_effect"]
            for seg in cycle_segments(ledger)]


def _status_from_level(rate: Optional[float], denominator: float, *,
                       floor: float, low_reason: str, ok_reason: str,
                       trend: str = "") -> Tuple[str, str]:
    """A status from a LEVEL, with the sample deciding how hard it may speak.

    An immature sample may report a level and may not carry DEGRADING; that
    rule is the same one `_all_immature` enforces for trends, applied where
    there is no trend to have.
    """
    if rate is None:
        return UNMEASURABLE, low_reason
    mature_enough = denominator >= MIN_DENOMINATOR_FOR_VERDICT
    if rate < floor:
        if not mature_enough:
            return EARLY_WARNING_STATUS, (
                f"{low_reason} — on {denominator:.0f} observation(s), which "
                f"is too few to carry a verdict")
        return DEGRADING, low_reason
    if not mature_enough:
        return EARLY_WARNING_STATUS, (
            f"{ok_reason} — on {denominator:.0f} observation(s), too few to "
            f"carry a verdict either way")
    return (STABLE if not trend else
            {"UP": ACCELERATING, "DOWN": PLATEAUING}.get(trend, STABLE)), \
        ok_reason


def economic_channel(ledger: Sequence[dict]) -> ChannelReport:
    """Did the ECONOMIC knowledge state change, and how often.

    The denominator is every effect on an economic object, including
    NO_CHANGE. That is the point of the log: a numerator on its own is a
    success count, and a success count cannot tell a productive cycle from a
    prolific one.
    """
    effects = [r for r in _rows(ledger, "knowledge_effect")
               if r.get("target_type") in ECONOMIC_TARGETS]
    if not effects:
        return _unmeasurable(
            ECONOMIC,
            "no knowledge effect has been written against an economic "
            "object; this is absent telemetry, not an engine that learned "
            "nothing")
    changed = [e for e in effects
               if str(e.get("effect_type")) in CHANGING_EFFECTS]
    discriminating = [e for e in effects if e.get("discriminating")]
    rate = round(len(changed) / len(effects), 4)
    cycles = [c for c in _effect_cycles(ledger) if c]
    status, reason = _status_from_level(
        rate, float(len(effects)), floor=LOW_LEARNING_SHARE,
        low_reason=(f"{len(changed)} of {len(effects)} effects on economic "
                    f"objects changed anything; the rest were processed and "
                    f"moved nothing"),
        ok_reason=(f"{len(changed)} of {len(effects)} effects changed an "
                   f"economic object"))
    if len(cycles) < 2:
        status = INSUFFICIENT_HISTORY if status in (STABLE, ACCELERATING) \
            else status
        reason += (f". {len(cycles)} cycle(s) have appended effects, so a "
                   f"direction is not available; the level is")
    return ChannelReport(
        channel=ECONOMIC, status=status, reason=reason,
        numerator=float(len(changed)), denominator=float(len(effects)),
        rate=rate, maturity=sample_maturity(len(effects)),
        window="lifetime",
        detail={
            "discriminating": len(discriminating),
            "by_effect": dict(collections.Counter(
                str(e.get("effect_type")) for e in effects)),
            "by_target": dict(collections.Counter(
                str(e.get("target_type")) for e in effects)),
            "cycles_with_effects": len(cycles),
            "note": ("DISCRIMINATED / CONTRADICTED / RESOLVED separate live "
                     "explanations; SUPPORTED adds weight to the one already "
                     "ahead, and a confirmation-seeking policy can farm it"),
        })


def system_channel(execution_ledger: Sequence[dict] = ()) -> ChannelReport:
    """Engineering and runtime capability, kept OUT of the economic number.

    Wiring a producer, repairing a read path and pinning a runtime are real
    and valuable, and none of them is economic learning. They are counted
    here so that a week of them cannot be reported as the engine getting
    smarter about the world.
    """
    if not execution_ledger:
        return _unmeasurable(
            SYSTEM,
            "no execution record was supplied; system capability is tracked "
            "in the planner's ledger and this caller did not pass one")
    kinds = collections.Counter(str(r.get("kind")) for r in execution_ledger)
    gains = sum(kinds[k] for k in ("task", "repair", "experiment"))
    findings = kinds["finding"]
    days = len({str(r.get("at") or "")[:10] for r in execution_ledger} - {""})
    total = len(execution_ledger)
    status = STABLE if gains else PLATEAUING
    reason = (f"{gains} capability change(s) and {findings} finding(s) "
              f"recorded over {days} day(s) of execution history")
    if days < 2:
        status = INSUFFICIENT_HISTORY
        reason += ("; one day of history has no two halves to compare, so "
                   "the counts are reported and a direction is not")
    return ChannelReport(
        channel=SYSTEM, status=status, reason=reason,
        numerator=float(gains), denominator=float(total),
        rate=round(gains / total, 4) if total else None,
        maturity=sample_maturity(total), window="lifetime",
        detail={"by_kind": dict(kinds), "days": days,
                "note": ("system capability is NOT economic learning and is "
                         "never added to it")})


def calibration_channel(ledger: Sequence[dict]) -> ChannelReport:
    """Did the engine get better at being RIGHT, not at being busy.

    Measured from things that can come out wrong: reconciliations that
    reached a verdict, and methods scored against persistence. A method that
    beat nothing is still a calibration measurement — it is the measurement
    that says do not deploy this.
    """
    reconciliations = _rows(ledger, "reconciliation")
    performance = _rows(ledger, "method_performance")
    resolved = [e for e in _rows(ledger, "knowledge_effect")
                if str(e.get("effect_type")) == "RESOLVED"]
    if not reconciliations and not performance:
        return _unmeasurable(
            CALIBRATION,
            "nothing has been scored against an outcome: no reconciliation "
            "reached a verdict and no method was measured against "
            "persistence")
    contradicted = [r for r in reconciliations
                    if str(r.get("outcome")) == "CONTRADICTED"]
    useful = [p for p in performance
              if str(p.get("standing")) not in
              ("NO_INCREMENTAL_VALUE", "REFUSED")]
    denominator = float(len(reconciliations))
    rate = (round(len(contradicted) / denominator, 4)
            if denominator else None)
    # A reconciliation set that never reaches disagreement is a report about
    # the filter, not a calibrated engine. That is why the numerator here is
    # CONTRADICTED rather than CONFIRMED.
    status, reason = _status_from_level(
        rate, denominator, floor=0.01,
        low_reason=(f"{len(reconciliations)} reconciliation(s) and not one "
                    f"contradicted anything; a set that cannot reach "
                    f"disagreement measures the filter, not the engine"),
        ok_reason=(f"{len(contradicted)} of {len(reconciliations)} "
                   f"reconciliations contradicted the belief behind them"))
    return ChannelReport(
        channel=CALIBRATION, status=status, reason=reason,
        numerator=float(len(contradicted)), denominator=denominator,
        rate=rate, maturity=sample_maturity(denominator), window="lifetime",
        detail={
            "reconciliations": len(reconciliations),
            "expectations_resolved": len(resolved),
            "methods_scored": len(performance),
            "methods_with_incremental_value": len(useful),
            "by_standing": dict(collections.Counter(
                str(p.get("standing")) for p in performance)),
            "note": ("a method that beat persistence and came back BOUNDED "
                     "or REFUSED is a calibration RESULT, not a shortfall"),
        })


def founder_channel(ledger: Sequence[dict],
                    decision_impacts: Sequence[dict] = ()) -> ChannelReport:
    """Did any of this CHANGE A DECISION.

    The one thing this channel may not do is count dossiers. A published
    report, a longer report and a new strategic section are all volume, and
    the call site that fed this module `len(published)` was reporting exactly
    that as decision value. Value is a FOUNDER_DECISION_COMPONENT effect or a
    recorded DecisionImpact, and where neither exists the honest answer is
    that nothing measures it.
    """
    components = [e for e in _rows(ledger, "knowledge_effect")
                  if str(e.get("target_type")) == "FOUNDER_DECISION_COMPONENT"]
    impacts = [i for i in decision_impacts if i]
    if not components and not impacts:
        return _unmeasurable(
            FOUNDER,
            "no FOUNDER_DECISION_COMPONENT effect and no recorded decision "
            "impact exist. Dossiers were published; whether any of them "
            "changed a decision is not recorded anywhere, and a count of "
            "publications is not an answer to that question",
            dossiers_published_is_not_value=True)
    changed = [e for e in components
               if str(e.get("effect_type")) in CHANGING_EFFECTS]
    graded = [str(i.get("impact") or i.get("standing") or "")
              for i in impacts]
    meaningful = [g for g in graded
                  if g in ("MEANINGFUL", "DECISION_CHANGING")]
    numerator = float(len(changed) + len(meaningful))
    denominator = float(len(components) + len(impacts))
    rate = round(numerator / denominator, 4) if denominator else None
    status, reason = _status_from_level(
        rate, denominator, floor=LOW_LEARNING_SHARE,
        low_reason=(f"{numerator:.0f} of {denominator:.0f} Founder records "
                    f"changed a decision component or graded above "
                    f"PRESENTATIONAL"),
        ok_reason=(f"{numerator:.0f} of {denominator:.0f} Founder records "
                   f"carried decision value"))
    return ChannelReport(
        channel=FOUNDER, status=status, reason=reason, numerator=numerator,
        denominator=denominator, rate=rate,
        maturity=sample_maturity(denominator), window="lifetime",
        detail={"decision_components": len(components),
                "impacts_recorded": len(impacts),
                "by_grade": dict(collections.Counter(g for g in graded if g))})


def retention_channel(ledger: Sequence[dict]) -> ChannelReport:
    """Is what was learned still USABLE — or has it quietly rotted.

    Retention failure turns past learning into unusable learning, and it is
    invisible to every rate above: an orphaned effect, a belief no
    observation can refresh and a duplicate fact all leave the counts intact
    and the knowledge worse.
    """
    effects = _rows(ledger, "knowledge_effect")
    beliefs = _rows(ledger, "belief")
    if not effects and not beliefs:
        return _unmeasurable(
            RETENTION, "nothing has been persisted to retain")
    # An effect that claims a change and names no object cannot be audited,
    # disputed or reloaded against anything.
    orphaned = [e for e in effects
                if str(e.get("effect_type")) in CHANGING_EFFECTS
                and not str(e.get("target_id") or "")]
    unprovenanced = [e for e in effects if not str(e.get("reason") or "")]
    stale = [b for b in beliefs
             if str(b.get("lifecycle_state") or "") in ("STALE", "RETIRED")]
    ids = [str(e.get("effect_id") or "") for e in effects]
    duplicates = len(ids) - len(set(ids))
    intact = len(effects) - len(orphaned) - len(unprovenanced) - duplicates
    denominator = float(len(effects))
    rate = round(intact / denominator, 4) if denominator else None
    status, reason = _status_from_level(
        rate, denominator, floor=0.95,
        low_reason=(f"{len(orphaned)} orphaned, {len(unprovenanced)} "
                    f"unexplained and {duplicates} duplicate effect(s) of "
                    f"{len(effects)}"),
        ok_reason=(f"{intact} of {len(effects)} persisted effects are "
                   f"attributable, explained and unduplicated"))
    return ChannelReport(
        channel=RETENTION, status=status, reason=reason,
        numerator=float(intact), denominator=denominator, rate=rate,
        maturity=sample_maturity(denominator), window="lifetime",
        detail={"orphaned": len(orphaned),
                "unexplained": len(unprovenanced),
                "duplicate_ids": duplicates,
                "beliefs": len(beliefs), "stale_or_retired": len(stale),
                "note": ("append-only integrity is checked by id, so a "
                         "duplicate id is a storage fault and not a second "
                         "observation")})


def research_channel(ledger: Sequence[dict]) -> ChannelReport:
    """Did RESEARCH get better at being useful, not at retrieving.

    A research action is priced by what its evidence DID, so the numerator is
    outcomes whose effects changed something. The channel refuses to claim a
    learned policy below the decision floor: architecture may pass while
    policy maturity stays blocked, and saying so is the difference between a
    measurement and a slogan.
    """
    decisions = _rows(ledger, "research_decision")
    outcomes = _rows(ledger, "research_outcome")
    if not decisions:
        return _unmeasurable(
            RESEARCH, "no research decision has been logged before its call")
    effects = {str(e.get("effect_id") or ""): e
               for e in _rows(ledger, "knowledge_effect")}
    linked_ids = [str(i) for o in outcomes
                  for i in (o.get("knowledge_effect_ids") or ())]
    by_status = collections.Counter(str(o.get("status")) for o in outcomes)
    # AN ABSENT LINK IS NOT A ZERO. Every outcome carrying an empty
    # `knowledge_effect_ids` means nothing recorded what the research
    # PRODUCED — which reads identically to research that produced nothing,
    # and is the opposite finding. The first version of this channel divided
    # anyway and reported 0 of 14, an accusation the ledger cannot support.
    if outcomes and not linked_ids:
        return _unmeasurable(
            RESEARCH,
            f"{len(decisions)} decision(s) and {len(outcomes)} outcome(s) "
            f"are logged, and not one outcome names the knowledge effects "
            f"its evidence produced. Whether research was USEFUL is "
            f"therefore unmeasured — which is not the same as research that "
            f"was useless, and the rate that would say so is withheld",
            decisions=len(decisions), outcomes=len(outcomes),
            by_status=dict(by_status),
            accepted_evidence=sum(int(o.get("accepted_evidence") or 0)
                                  for o in outcomes),
            missing_link="research_outcome.knowledge_effect_ids",
            policy_maturity="BLOCKED_DATA")
    productive = 0
    for outcome in outcomes:
        linked = [effects.get(str(i)) for i in
                  (outcome.get("knowledge_effect_ids") or ())]
        if any(e is not None
               and str(e.get("effect_type")) in CHANGING_EFFECTS
               for e in linked):
            productive += 1
    denominator = float(len(outcomes))
    rate = round(productive / denominator, 4) if denominator else None
    if len(decisions) < MIN_RESEARCH_DECISIONS:
        return ChannelReport(
            channel=RESEARCH, status=INSUFFICIENT_HISTORY,
            reason=(f"{len(decisions)} prospective decision(s) against a "
                    f"floor of {MIN_RESEARCH_DECISIONS}. The rate is "
                    f"reported; a policy claim is not, and the sample grows "
                    f"about two decisions a cycle"),
            numerator=float(productive), denominator=denominator, rate=rate,
            maturity=sample_maturity(len(decisions)), window="lifetime",
            detail={"decisions": len(decisions), "outcomes": len(outcomes),
                    "by_status": dict(by_status),
                    "empty_handed": by_status.get("NO_RESULT", 0),
                    "failed": by_status.get("FAILED", 0),
                    "policy_maturity": "BLOCKED_DATA"})
    status, reason = _status_from_level(
        rate, denominator, floor=LOW_LEARNING_SHARE,
        low_reason=(f"{productive} of {len(outcomes)} research outcomes "
                    f"produced an effect that changed anything"),
        ok_reason=(f"{productive} of {len(outcomes)} research outcomes "
                   f"changed something"))
    return ChannelReport(
        channel=RESEARCH, status=status, reason=reason,
        numerator=float(productive), denominator=denominator, rate=rate,
        maturity=sample_maturity(len(decisions)), window="lifetime",
        detail={"decisions": len(decisions), "outcomes": len(outcomes),
                "by_status": dict(by_status),
                "policy_maturity": "MEASURABLE"})


def unsupervised_channel(discoveries: Sequence[dict] = ()) -> ChannelReport:
    """Did a discovery turn out to be USEFUL, not tidy.

    Geometry is not the measure. A mixture model can partition noise
    beautifully; the question this channel asks is whether knowing the group
    reduced held-out forecast error. The recorded result — better geometry
    from KMeans/GMM, better held-out utility from the deterministic economic
    rule — is exactly the reading this channel must be able to reproduce, and
    a silhouette-based score would invert it.
    """
    if not discoveries:
        return _unmeasurable(
            UNSUPERVISED,
            "no discovery has been scored; unsupervised structure is a "
            "hypothesis generator and an unscored hypothesis is not a gain")
    scored = [d for d in discoveries if d.get("utility") is not None]
    if not scored:
        return _unmeasurable(
            UNSUPERVISED,
            f"{len(discoveries)} discovery/discoveries exist and none "
            f"carries a held-out utility score; separation and coherence "
            f"describe the partition, not its worth",
            discoveries=len(discoveries))
    useful = [d for d in scored if float(d.get("utility") or 0) > 0]
    denominator = float(len(scored))
    rate = round(len(useful) / denominator, 4)
    status, reason = _status_from_level(
        rate, denominator, floor=LOW_LEARNING_SHARE,
        low_reason=(f"{len(useful)} of {len(scored)} scored discoveries "
                    f"reduced held-out error; the rest are patterns in the "
                    f"data, which is not the same thing as knowledge"),
        ok_reason=(f"{len(useful)} of {len(scored)} scored discoveries "
                   f"reduced held-out forecast error"))
    return ChannelReport(
        channel=UNSUPERVISED, status=status, reason=reason,
        numerator=float(len(useful)), denominator=denominator, rate=rate,
        maturity=sample_maturity(denominator), window="lifetime",
        detail={"scored": len(scored), "unscored": len(discoveries) - len(scored),
                "note": ("utility is held-out error reduction; silhouette "
                         "and coherence are never utility")})


def channels(ledger: Sequence[dict], *,
             execution_ledger: Sequence[dict] = (),
             decision_impacts: Sequence[dict] = (),
             discoveries: Sequence[dict] = ()) -> Dict[str, ChannelReport]:
    """All seven, computed independently and never blended."""
    return {
        ECONOMIC: economic_channel(ledger),
        SYSTEM: system_channel(execution_ledger),
        CALIBRATION: calibration_channel(ledger),
        FOUNDER: founder_channel(ledger, decision_impacts),
        RETENTION: retention_channel(ledger),
        RESEARCH: research_channel(ledger),
        UNSUPERVISED: unsupervised_channel(discoveries),
    }


def high_activity_low_learning(ledger: Sequence[dict]) -> dict:
    """Is the engine busy and not learning — stated in those words.

    This is the reading a volume metric cannot produce and an operator most
    needs. It is deliberately not a status: it is a named condition with the
    three counts that establish it, because "120 rows accepted" and "105 of
    them changed nothing" are the same cycle described twice and only the
    second is about learning.
    """
    effects = _rows(ledger, "knowledge_effect")
    evidence = _rows(ledger, "evidence")
    if not effects:
        return {"detected": False, "status": UNMEASURABLE,
                "reason": ("no effect has been attributed, so activity "
                           "cannot be compared with learning")}
    changed = [e for e in effects
               if str(e.get("effect_type")) in CHANGING_EFFECTS]
    no_change = len(effects) - len(changed)
    share = round(len(changed) / len(effects), 4)
    revisions = [r for r in _rows(ledger, "thesis_revision")
                 if str(r.get("transition") or r.get("kind") or "")
                 not in ("", "CREATED")]
    detected = (share < LOW_LEARNING_SHARE
                and len(effects) >= MIN_DENOMINATOR_FOR_VERDICT)
    return {
        "detected": bool(detected),
        "status": DEGRADING if detected else STABLE,
        "evidence_rows": len(evidence),
        "effects": len(effects),
        "effects_that_changed_something": len(changed),
        "effects_that_changed_nothing": no_change,
        "changing_share": share,
        "thesis_transitions": len(revisions),
        "reason": (
            (f"{len(evidence)} evidence rows produced {len(effects)} "
             f"attributions and {len(changed)} of them changed anything "
             f"({share:.1%}); {len(revisions)} thesis transition(s). The "
             f"engine is working and its knowledge is nearly static")
            if detected else
            (f"{len(changed)} of {len(effects)} attributions changed "
             f"something ({share:.1%}), at or above the "
             f"{LOW_LEARNING_SHARE:.0%} floor")),
        "note": ("most evidence SHOULD change nothing; this reads as a "
                 "finding only when the share is low AND the volume is "
                 "large enough for the share to mean something"),
    }


#: The candidate bottlenecks, and the channel or gate that measures each. The
#: current one is COMPUTED from these, never declared: a hardcoded bottleneck
#: is a belief about the system that stops being checked the day it is typed.
BOTTLENECKS: Tuple[Tuple[str, str], ...] = (
    ("ECONOMIC_STATE_COVERAGE", ECONOMIC),
    ("METHOD_VALIDATION", CALIBRATION),
    ("FOUNDER_VALUE", FOUNDER),
    ("RETENTION", RETENTION),
    ("PROSPECTIVE_SAMPLE_SIZE", RESEARCH),
    ("UNSUPERVISED_UTILITY", UNSUPERVISED),
    ("RUNTIME_ALIGNMENT", SYSTEM),
)

#: Worst first. A channel nothing measures outranks a channel measured badly:
#: an unmeasured capability cannot be improved deliberately, and improving a
#: measured one while another is dark is how a system optimises what it can
#: see.
_BOTTLENECK_RANK = {UNMEASURABLE: 0, DEGRADING: 1, INSUFFICIENT_HISTORY: 2,
                    EARLY_WARNING_STATUS: 3, PLATEAUING: 4, STABLE: 5,
                    ACCELERATING: 6}


def bottleneck(reports: Dict[str, ChannelReport]) -> dict:
    """Which channel is holding the system back, derived from the channels."""
    ranked = sorted(
        BOTTLENECKS,
        key=lambda pair: (_BOTTLENECK_RANK.get(
            reports[pair[1]].status if pair[1] in reports else UNMEASURABLE,
            0), pair[0]))
    name, channel = ranked[0]
    report_ = reports.get(channel)
    return {
        "bottleneck": name,
        "channel": channel,
        "status": report_.status if report_ else UNMEASURABLE,
        "reason": report_.reason if report_ else "channel not computed",
        "ranking": [{"bottleneck": n, "channel": c,
                     "status": (reports[c].status if c in reports
                                else UNMEASURABLE)}
                    for n, c in ranked],
        "note": ("computed from measured channel status, worst first; an "
                 "UNMEASURABLE channel outranks a DEGRADING one because a "
                 "capability nothing measures cannot be improved on purpose"),
    }


def operator_summary(reports: Dict[str, ChannelReport], *,
                     activity: dict, limit: dict) -> List[str]:
    """What an operator needs, in sentences, with no debug dump."""
    lines: List[str] = []
    measured = [r for r in reports.values() if r.status != UNMEASURABLE]
    dark = [r for r in reports.values() if r.status == UNMEASURABLE]
    economic = reports.get(ECONOMIC)
    if economic and economic.rate is not None:
        lines.append(
            f"The engine attributed {economic.denominator:.0f} effects and "
            f"{economic.numerator:.0f} of them changed an economic object "
            f"({economic.rate:.1%}).")
    if activity.get("detected"):
        lines.append(
            f"HIGH ACTIVITY, LOW LEARNING: {activity['evidence_rows']} "
            f"evidence rows, {activity['effects_that_changed_nothing']} "
            f"attributions that moved nothing, "
            f"{activity['thesis_transitions']} thesis transition(s).")
    calibration = reports.get(CALIBRATION)
    if calibration and calibration.status != UNMEASURABLE:
        lines.append(f"Calibration: {calibration.reason}.")
    if dark:
        lines.append(
            "Nothing measures: "
            + ", ".join(sorted(r.channel for r in dark))
            + " — these are absent instruments, not zero results.")
    lines.append(f"Bottleneck: {limit['bottleneck']} ({limit['status']}).")
    lines.append(
        f"{len(measured)} of {len(reports)} channels are measurable.")
    return lines


def report(observations: Sequence, *, ledger: Sequence[dict] = (),
           decision_impacts: int = 0,
           execution_ledger: Sequence[dict] = (),
           decision_impact_records: Sequence[dict] = (),
           discoveries: Sequence[dict] = ()) -> dict:
    """Every window that the history defends, and the reason for the rest.

    `decision_impacts` stays an int for the volume/quality half above, which
    has used it as a denominator since before the channels existed. The
    Founder CHANNEL deliberately ignores it and reads
    `decision_impact_records`: a count of published dossiers is publication
    volume, and feeding it to a channel called Founder VALUE is the exact
    substitution this node exists to stop.
    """
    windows = [window(observations, name=name, size=size, ledger=ledger,
                      decision_impacts=decision_impacts)
               for name, size in WINDOWS]
    computed = [w for w in windows if w.status != INSUFFICIENT_HISTORY]
    headline = computed[0] if computed else windows[0]
    backlog = [o for o in observations
               if getattr(o, "backlog_drain", False)]
    per_channel = channels(ledger, execution_ledger=execution_ledger,
                           decision_impacts=decision_impact_records,
                           discoveries=discoveries)
    activity = high_activity_low_learning(ledger)
    limit = bottleneck(per_channel)
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
        # THE SEVEN, INDEPENDENT AND UNBLENDED.
        "channels": {name: rep.as_dict()
                     for name, rep in per_channel.items()},
        "channels_measurable": sorted(
            name for name, rep in per_channel.items()
            if rep.status != UNMEASURABLE),
        "channels_unmeasurable": sorted(
            name for name, rep in per_channel.items()
            if rep.status == UNMEASURABLE),
        "effect_cycles": sum(1 for c in _effect_cycles(ledger) if c),
        "high_activity_low_learning": activity,
        "bottleneck": limit,
        "operator_summary": operator_summary(per_channel, activity=activity,
                                             limit=limit),
        "note": ("volume never sets the status on its own: a window with any "
                 "degrading quality dimension cannot read ACCELERATING, "
                 "however much it ingested. A None quality reading is "
                 "absent telemetry, not a zero. The seven channels are "
                 "computed independently and are never averaged: a system "
                 "can improve technically while learning nothing "
                 "economically, and one number hides exactly that"),
    }
