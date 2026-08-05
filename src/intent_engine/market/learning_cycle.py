"""Every session attempts to learn — and says why it did not, when it did not.

WHAT THIS REPLACES
------------------
`steps.assets_step` reports the ledger and passes `()` for revisions, so
NET KNOWLEDGE GAIN was structurally 0 on every cycle for eleven consecutive
cycles. Its docstring is right about the risk it was avoiding: an unattended
process that rewrites its own confidences nightly manufactures exactly the
daily-progress signal this project refuses to manufacture.

This module takes the opposite route to the same protection. Instead of
refusing to update, it makes every update *earned* by something external:

  - a preregistered expectation, committed before the observation existed;
  - deduplicated evidence carrying a real source;
  - a decay rule driven by the calendar, recorded as decay and never as
    contradiction.

A quiet session still reports zero. But it now reports zero WITH ITS WORKING:
what was observed, what was tested, and why nothing moved. Those are different
statements, and only the second one is evidence that the engine is alive.

THE ORDER OF THE THIRTEEN STEPS MATTERS
---------------------------------------
Reconciliation runs before belief revision, so an expectation is scored against
the observation that arrived — not against a posterior it just helped move.
Decay runs last, so a belief validated by this session's evidence is not
decayed in the same breath for being stale.

NOTHING HERE OPENS A POSITION
-----------------------------
No import of `paper_engine`, no order path, no position identity. Learning is
upstream of trading and does not depend on it — which is the whole point.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from . import belief_formation as BF
from . import beliefs as B
from . import causal as C
from . import counterfactual as CF
from . import expectation as EXP
from . import hidden_state as HS
from . import information_value as IV
from . import learning_store as LS
from . import micro_evidence as ME
from . import strategic_interaction as SI

CONTRACT_VERSION = "learning_cycle.v1"

# The thirteen things every session attempts (§22). Reported individually so a
# session that skipped one cannot present itself as having run them all.
STEPS = (
    "micro_evidence_ingestion",
    "belief_formation",
    "expected_vs_observed_reconciliation",
    "belief_revision",
    "hidden_state_update",
    "causal_graph_update",
    "interaction_memory_update",
    "counterfactual_update",
    "shadow_policy_update",
    "regret_calculation",
    "near_miss_analysis",
    "information_value_prioritisation",
    "knowledge_decay",
    "long_horizon_outcome_resolution",
)

ATTEMPTED = "ATTEMPTED"
SKIPPED = "SKIPPED"
FAILED = "FAILED"


@dataclass
class StepResult:
    """One step's outcome, including an honest zero."""
    name: str
    status: str
    changed: int = 0
    examined: int = 0
    note: str = ""

    def as_dict(self) -> dict:
        return {"step": self.name, "status": self.status,
                "examined": self.examined, "changed": self.changed,
                "note": self.note}


@dataclass
class LearningResult:
    """What a session actually learned, and what it merely looked at."""
    as_of: str
    steps: List[StepResult] = field(default_factory=list)
    belief_summary: dict = field(default_factory=dict)
    formation_summary: dict = field(default_factory=dict)
    #: Beliefs opened from evidence that was ALREADY on the ledger, never
    #: folded into `formation_summary`. Kept apart because recovering a
    #: belief the engine should have formed months ago is a repair, and a
    #: repair reported as a session's learning is the overstatement this
    #: project keeps having to retract. Empty on every ordinary cycle.
    backfill_summary: dict = field(default_factory=dict)
    reconciliation_summary: dict = field(default_factory=dict)
    hidden_state_summary: dict = field(default_factory=dict)
    causal_summary: dict = field(default_factory=dict)
    interaction_summary: dict = field(default_factory=dict)
    counterfactual_summary: dict = field(default_factory=dict)
    near_miss_summary: dict = field(default_factory=dict)
    information_agenda: dict = field(default_factory=dict)
    trades_opened: int = 0
    #: which of the five outcome classes this session was (see learning_store)
    outcome_class: str = ""

    # --- the session's live objects, for the sanitized export only --------
    # Summaries are counts, and a founder cannot be told anything useful by a
    # count. The projector in `strategic_publish` needs the objects
    # themselves, so the session carries them here rather than rebuilding a
    # second, drifting copy from the ledger.
    #
    # DELIBERATELY OUTSIDE `as_dict()`. These are not report fields: the day
    # report is written to disk and read by operators, and putting live
    # objects in it would put the whole belief store into every cycle JSON.
    # `as_dict` names its keys explicitly, so nothing here can ride along.
    beliefs_after: Tuple[Any, ...] = ()
    hidden_states_after: Tuple[Any, ...] = ()
    interactions_seen: Tuple[Any, ...] = ()
    reconciliations_seen: Tuple[Any, ...] = ()
    priorities_seen: Tuple[Any, ...] = ()
    candidates_formed: Tuple[Any, ...] = ()

    @property
    def observations_ingested(self) -> int:
        for s in self.steps:
            if s.name == "micro_evidence_ingestion":
                return s.examined
        return 0

    @property
    def knowledge_gain(self) -> int:
        """Belief-layer learning ONLY. Never includes trade outcomes.

        Kept separate from anything trading produces, because conflating them
        is how eleven quiet markets got recorded as eleven quiet minds.
        """
        s = self.belief_summary
        return int(s.get("belief_knowledge_gain", 0)) + \
            int(self.hidden_state_summary.get("companies_moved", 0)) + \
            int(self.causal_summary.get("added", 0)) + \
            int(self.causal_summary.get("strengthened", 0)) + \
            int(self.causal_summary.get("weakened", 0))

    @property
    def learned_without_trading(self) -> bool:
        """The central claim this cycle has to be able to make."""
        return self.trades_opened == 0 and self.knowledge_gain > 0

    def why_nothing_moved(self) -> str:
        """The explanation a zero must carry. §22 forbids a bare zero."""
        if self.knowledge_gain:
            return ""
        ingested = self.observations_ingested
        recon = self.reconciliation_summary or {}
        by_outcome = recon.get("by_outcome", {})
        parts = [f"{ingested} observation(s) ingested",
                 f"{recon.get('evaluated', 0)} preregistered expectation(s) "
                 f"tested"]
        if by_outcome.get(EXP.TOO_EARLY):
            parts.append(f"{by_outcome[EXP.TOO_EARLY]} still inside their "
                         f"evaluation window")
        if by_outcome.get(EXP.UNINFORMATIVE):
            parts.append(f"{by_outcome[EXP.UNINFORMATIVE]} observed a move "
                         f"too small to discriminate")
        if by_outcome.get(EXP.UNMEASURABLE):
            parts.append(f"{by_outcome[EXP.UNMEASURABLE]} had no qualifying "
                         f"observation")
        if not ingested:
            parts.append("no new evidence carried a source, so nothing was "
                         "eligible to update a belief")
        return ("No belief moved this session. " + "; ".join(parts) +
                ". A tested-and-unmoved belief is a result, not an absence "
                "of work.")

    def as_dict(self) -> dict:
        return {
            "contract": CONTRACT_VERSION, "as_of": self.as_of,
            "steps": [s.as_dict() for s in self.steps],
            "steps_attempted": sum(1 for s in self.steps
                                   if s.status == ATTEMPTED),
            "steps_total": len(STEPS),
            "belief_learning": self.belief_summary,
            "belief_formation": self.formation_summary,
            "belief_formation_backfill": self.backfill_summary,
            "expected_vs_observed": self.reconciliation_summary,
            "hidden_states": self.hidden_state_summary,
            "causal_graph": self.causal_summary,
            "strategic_interactions": self.interaction_summary,
            "counterfactuals_and_regret": self.counterfactual_summary,
            "near_misses": self.near_miss_summary,
            "information_priorities": self.information_agenda,
            "belief_knowledge_gain": self.knowledge_gain,
            "trades_opened": self.trades_opened,
            "learned_without_trading": self.learned_without_trading,
            "why_nothing_moved": self.why_nothing_moved(),
            "outcome_class": self.outcome_class,
        }


def run(*, as_of: str, store: LS.LearningStore,
        evidence: Sequence[ME.MicroEvidence] = (),
        observations: Optional[Dict[str, dict]] = None,
        hidden_states: Sequence[HS.HiddenStateBelief] = (),
        hidden_state_observations: Sequence[dict] = (),
        graph: Optional[C.CausalGraph] = None,
        interactions: Sequence[SI.StrategicInteraction] = (),
        counterfactuals: Sequence[CF.Counterfactual] = (),
        near_misses: Sequence[CF.NearMiss] = (),
        information_candidates: Sequence[dict] = (),
        shadow_registry: Optional[Any] = None,
        trades_opened: int = 0,
        cycle: str = "day",
        candidates_seen: int = 0,
        decay_beliefs: bool = True,
        backfill_evidence: bool = False) -> LearningResult:
    """Run one full learning session. Attempts all thirteen steps.

    `observations` maps expectation_id → {observed_value, observed_at,
    observed_direction, evidence_ids}. An expectation with no entry is scored
    TOO_EARLY or UNMEASURABLE by `reconcile`, never as a refutation.

    `backfill_evidence` is OFF by default and must be asked for. It lets
    formation see evidence already on the ledger — see `_backfill_formation`
    for what that is repairing and why it is not ordinary learning.
    """
    result = LearningResult(as_of=as_of[:10], trades_opened=trades_opened)
    observations = observations or {}
    graph = graph if graph is not None else C.CausalGraph()
    before_edges = graph.all()

    # 1. micro-evidence ingestion -----------------------------------------
    known = store.evidence_ids()
    fresh = [e for e in ME.deduplicate(evidence)
             if e.evidence_id not in known]
    for item in fresh:
        store.record_evidence(item)
    result.steps.append(StepResult(
        "micro_evidence_ingestion", ATTEMPTED, changed=len(fresh),
        examined=len(evidence),
        note=(f"{len(evidence) - len(fresh)} already ingested and skipped"
              if len(evidence) != len(fresh) else "")))

    beliefs_before = store.beliefs()
    by_id = {b.belief_id: b for b in beliefs_before}
    working: Dict[str, B.StrategicBelief] = dict(by_id)

    # 1b. belief FORMATION ------------------------------------------------
    # Runs before reconciliation and revision so a belief opened this session
    # is visible to everything after it — but its expectation is registered
    # with a window that opens today, so the evidence that PROPOSED it can
    # never be the evidence that CONFIRMS it. That is the whole reason
    # preregistration is load-bearing rather than ceremonial.
    #
    # Without this step the engine could translate perfect evidence for
    # twenty-eight companies and still report zero, because revision needs a
    # belief to revise and nothing anywhere created the first one.
    candidates, refused = BF.propose(fresh, as_of=as_of,
                                     existing=tuple(working.values()))
    for candidate in candidates:
        store.declare_belief(candidate.belief)
        working[candidate.belief.belief_id] = candidate.belief
        if candidate.expectation is not None:
            store.record_expectation(candidate.expectation)
    result.formation_summary = BF.summarise(candidates, refused)
    result.candidates_formed = tuple(candidates)
    result.steps.append(StepResult(
        "belief_formation", ATTEMPTED, examined=len(fresh),
        changed=len(candidates),
        note=("no evidence proposed a belief: "
              + ", ".join(f"{k} {v}" for k, v in sorted(refused.items()))
              if not candidates and refused else "")))

    # 1c. belief formation BACKFILL, only when asked for -------------------
    backfilled = _backfill_formation(
        store, working, as_of=as_of, skip_ids={e.evidence_id for e in fresh},
        result=result) if backfill_evidence else ()

    # 2. expected vs observed ---------------------------------------------
    # AN EXPECTATION REGISTERED TODAY IS NOT TESTED TODAY.
    #
    # Measured on the first real production cycle: six beliefs were declared,
    # six expectations preregistered, and the same session immediately
    # "tested" all six and wrote six TOO_EARLY rows into an append-only
    # ledger. Two things were wrong with that. The report said
    # `evaluated: 6` when zero tests could have happened, and at one row per
    # expectation per session the ledger would have accumulated thousands of
    # records of nothing having happened yet.
    open_expectations = [e for e in store.open_expectations(as_of=as_of)
                         if e.preregistered_at[:10] < as_of[:10]]
    reconciliations: List[EXP.Reconciliation] = []
    for e in open_expectations:
        obs = observations.get(e.expectation_id, {})
        r = EXP.reconcile(e, as_of=as_of,
                          observed_value=obs.get("observed_value"),
                          observed_at=obs.get("observed_at", ""),
                          observed_direction=obs.get("observed_direction"),
                          evidence_ids=obs.get("evidence_ids", ()))
        reconciliations.append(r)
        # TOO_EARLY is the absence of a result, not a result. It stays in the
        # session summary — an operator should see that a window is running —
        # and out of the permanent record, which exists to say what happened.
        if r.outcome != EXP.TOO_EARLY:
            store.record_reconciliation(r)
    result.reconciliation_summary = EXP.summarise(reconciliations)
    result.steps.append(StepResult(
        "expected_vs_observed_reconciliation", ATTEMPTED,
        examined=len(open_expectations),
        changed=result.reconciliation_summary["informative"],
        note="" if open_expectations else
             "no preregistered expectation was open this session"))

    # 3. belief revision ---------------------------------------------------
    # Reconciliations first: an expectation is scored against the observation
    # that arrived, not against a posterior it just helped move.
    revised = 0
    for r in reconciliations:
        belief = working.get(r.hypothesis_id)
        if belief is None:
            continue
        updated, changed = B.update_from_reconciliation(
            belief, r.outcome, at=as_of, rationale=r.rationale,
            expectation_id=r.expectation_id)
        if changed:
            working[belief.belief_id] = updated
            store.record_update(belief.belief_id, updated.history[-1])
            revised += 1

    by_subject: Dict[str, List[ME.MicroEvidence]] = {}
    for item in fresh:
        by_subject.setdefault(item.subject_company, []).append(item)
    for belief in list(working.values()):
        items = [e for e in by_subject.get(belief.subject, ())
                 if not belief.has_applied(e.evidence_id)]
        if not items:
            continue
        updated, changed = B.update(working[belief.belief_id], items,
                                    at=as_of)
        if changed:
            working[belief.belief_id] = updated
            store.record_update(belief.belief_id, updated.history[-1])
            revised += 1
    result.steps.append(StepResult(
        "belief_revision", ATTEMPTED, examined=len(working),
        changed=revised))

    # 4. hidden states -----------------------------------------------------
    hs_after: List[HS.HiddenStateBelief] = list(hidden_states)
    hs_index = {b.subject: i for i, b in enumerate(hs_after)}
    hs_changed = 0
    for obs in hidden_state_observations:
        subject = obs.get("subject")
        if subject not in hs_index:
            continue
        try:
            hs_after[hs_index[subject]] = HS.observe(
                hs_after[hs_index[subject]], action=obs["action"],
                likelihoods=obs["likelihoods"], at=as_of,
                evidence_ids=obs.get("evidence_ids", ()),
                invalidating_evidence=obs.get("invalidating_evidence", ""))
            hs_changed += 1
        except HS.HiddenStateError:
            # A refused observation is a guard firing, not a cycle failure.
            continue
    result.hidden_state_summary = HS.summarise(hidden_states, hs_after)
    result.steps.append(StepResult(
        "hidden_state_update", ATTEMPTED, examined=len(hidden_states),
        changed=hs_changed))

    # 5. causal graph ------------------------------------------------------
    result.causal_summary = graph.summarise(before=before_edges)
    result.steps.append(StepResult(
        "causal_graph_update", ATTEMPTED, examined=len(graph.all()),
        changed=result.causal_summary["added"]
        + result.causal_summary["strengthened"]
        + result.causal_summary["weakened"]))

    # 6. interaction memory ------------------------------------------------
    result.interaction_summary = SI.summarise(interactions)
    result.steps.append(StepResult(
        "interaction_memory_update", ATTEMPTED, examined=len(interactions),
        changed=result.interaction_summary["with_response"]))

    # 7/9. counterfactuals and regret --------------------------------------
    result.counterfactual_summary = CF.summarise(counterfactuals)
    result.steps.append(StepResult(
        "counterfactual_update", ATTEMPTED, examined=len(counterfactuals),
        changed=result.counterfactual_summary["resolved"]))

    # 8. shadow policies ---------------------------------------------------
    if shadow_registry is not None:
        shadow_registry.assert_isolated()
        result.steps.append(StepResult(
            "shadow_policy_update", ATTEMPTED,
            examined=len(shadow_registry.all_books()),
            note="isolation verified; no shadow policy touches the "
                 "principal paper book"))
    else:
        result.steps.append(StepResult(
            "shadow_policy_update", SKIPPED,
            note="no shadow registry supplied to this session"))

    result.steps.append(StepResult(
        "regret_calculation", ATTEMPTED,
        examined=result.counterfactual_summary["resolved"],
        changed=result.counterfactual_summary["actionable_regret_records"],
        note=f"no-trade regret "
             f"{result.counterfactual_summary['no_trade_regret']} over "
             f"{result.counterfactual_summary['no_trade_decisions_scored']} "
             f"scored no-trade decisions"))

    # 10. near misses ------------------------------------------------------
    result.near_miss_summary = CF.analyse_near_misses(near_misses)
    result.steps.append(StepResult(
        "near_miss_analysis", ATTEMPTED, examined=len(near_misses),
        changed=sum(1 for f in result.near_miss_summary["findings"]
                    if f["recommendation"] == "REVIEW_THRESHOLD")))

    # 11. information value ------------------------------------------------
    priorities = []
    for c in information_candidates:
        belief = working.get(c.get("belief_id", ""))
        if belief is None:
            continue
        try:
            priorities.append(IV.prioritise(
                belief, candidate_observation=c["candidate_observation"],
                observation_kind=c["observation_kind"],
                expected_date=c["expected_date"], as_of=as_of,
                decision_value=c.get("decision_value", 0.5),
                decision_deadline=c.get("decision_deadline", ""),
                falsifies=c.get("falsifies", "")))
        except ValueError:
            continue
    result.information_agenda = IV.agenda(priorities)
    result.steps.append(StepResult(
        "information_value_prioritisation", ATTEMPTED,
        examined=len(information_candidates),
        changed=result.information_agenda["actionable"]))

    # 12. decay — LAST, so this session's validation is respected ----------
    decayed = 0
    if decay_beliefs:
        for belief in list(working.values()):
            updated, changed = B.decay(belief, at=as_of)
            if changed:
                working[belief.belief_id] = updated
                store.record_update(belief.belief_id, updated.history[-1])
                decayed += 1
        result.steps.append(StepResult(
            "knowledge_decay", ATTEMPTED, examined=len(working),
            changed=decayed,
            note="decay moves a belief toward uncertainty, never toward "
                 "false"))
    else:
        result.steps.append(StepResult("knowledge_decay", SKIPPED,
                                       note="decay disabled for this run"))

    # 13. long-horizon outcome resolution ----------------------------------
    resolved = sum(1 for c in counterfactuals
                   if c.verdict != CF.UNRESOLVED)
    result.steps.append(StepResult(
        "long_horizon_outcome_resolution", ATTEMPTED,
        examined=len(counterfactuals), changed=resolved,
        note="trade outcomes are strong validation evidence, and are no "
             "longer the only path to knowledge"))

    # BACKFILLED BELIEFS COUNT AS ALREADY-HELD, NOT AS NEW.
    #
    # `summarise` calls anything absent from `before` "new", and `new` feeds
    # `belief_knowledge_gain`, which feeds `learned_without_trading` — the
    # one claim this cycle exists to make honestly. A repair that recovered
    # eight beliefs the engine should have formed in July would otherwise
    # report as a session that learned eight things today. Adding them to
    # `before` says the true thing: they are held, and this session is not
    # where they came from.
    result.belief_summary = B.summarise(tuple(beliefs_before) + backfilled,
                                        tuple(working.values()))
    # THE LEDGER SAYS WHAT KIND OF SESSION THIS WAS.
    #
    # Not "how many things happened" — that number has been the source of
    # every overstatement this project has had to retract. A session that
    # ingested forty observations and moved nothing is a different outcome
    # from one that declared a belief, and the ledger records which, once,
    # idempotently, from a closed vocabulary.
    result.outcome_class = _classify_outcome(
        result, len(fresh), len(candidates), revised,
        candidates_seen=candidates_seen)
    store.record_cycle(
        as_of=as_of, cycle=cycle, outcome=result.outcome_class,
        detail=result.why_nothing_moved() or (
            f"{len(candidates)} belief(s) declared, {revised} revision(s)"),
        counts={"evidence_ingested": len(fresh),
                "beliefs_declared": len(candidates),
                "beliefs_revised": revised,
                "expectations_registered": sum(
                    1 for c in candidates if c.expectation),
                "expectations_tested": len(open_expectations),
                "trades_opened": trades_opened})
    result.beliefs_after = tuple(working.values())
    result.hidden_states_after = tuple(hs_after)
    result.interactions_seen = tuple(interactions)
    result.reconciliations_seen = tuple(reconciliations)
    result.priorities_seen = tuple(priorities)
    return result


def _backfill_formation(store: LS.LearningStore,
                        working: Dict[str, B.StrategicBelief], *, as_of: str,
                        skip_ids: Any, result: LearningResult
                        ) -> Tuple[B.StrategicBelief, ...]:
    """Open beliefs from evidence ALREADY on the ledger. A repair, not a session.

    WHAT IT REPAIRS
    ---------------
    `propose` runs on `fresh` — evidence whose id is not already recorded.
    That is correct for a nightly cycle and it left a hole: evidence ingested
    by a cycle that ran BEFORE belief formation existed can never reach
    formation, because every later run dedupes those rows away first.
    Measured on the production ledger: 9 evidence rows, 0 beliefs, and
    `refused: {}` — not one reason, because there was nothing to refuse. The
    same 9 rows against a store that had not seen them declared 8 beliefs.

    An operator reading that zero could not tell it from "the evidence was
    not good enough", which is the failure mode this whole module exists to
    prevent.

    WHY IT IS NOT SIMPLY THE NORMAL PATH WITH A WIDER INPUT
    -------------------------------------------------------
    Deduplication is rule 1 in `beliefs.py` and it is load-bearing:
    re-reading an unchanged filing nightly must do nothing. This does not
    touch it. Nothing is re-ingested, no evidence row is written, and the
    normal cycle's `fresh` is unchanged. The only thing widened is what
    FORMATION may look at, once, when a human asks for it.

    PREREGISTRATION STILL HOLDS, AND THIS IS THE SUBTLE PART
    --------------------------------------------------------
    Expectations are registered at the SESSION date, never at the evidence's
    original date. Reconciliation only scores expectations where
    `preregistered_at < as_of`, so backfilling a July observation with a July
    date would produce an expectation whose window had already closed and
    which the very evidence that opened it could settle. Dating from today
    keeps the rule that opened evidence can never be confirming evidence.

    IT IS NOT ONE OF THE FOURTEEN STEPS
    ------------------------------------
    Deliberately absent from `STEPS` and from `result.steps`. `steps_total`
    is `len(STEPS)` and operators read attempted-against-total to see whether
    a session ran completely; adding a step that only sometimes exists would
    make every ordinary cycle look like it skipped one. It reports through
    `backfill_summary` alone, which surfaces as its own top-level
    `belief_formation_backfill` key — separate, as it should be.

    IT MAY NOT COUNT AS LEARNING
    -----------------------------
    The caller adds these to `beliefs_before` when summarising, so they are
    not counted as `new`, do not reach `belief_knowledge_gain`, and cannot
    make `learned_without_trading` true. They are still published to the
    founder side, because the belief is real — only the claim that this
    session discovered it would be false.
    """
    # `skip_ids` are the rows this very session just ingested: formation has
    # already seen them, and reconsidering them here would double-count.
    recorded = [e for e in store.evidence() if e.evidence_id not in skip_ids]
    if not recorded:
        result.backfill_summary = {"requested": True, "examined": 0,
                                   "declared": 0, "beliefs": [],
                                   "note": "no evidence was on the ledger"}
        return ()

    candidates, refused = BF.propose(recorded, as_of=as_of,
                                     existing=tuple(working.values()))
    opened: List[B.StrategicBelief] = []
    for candidate in candidates:
        store.declare_belief(candidate.belief)
        working[candidate.belief.belief_id] = candidate.belief
        if candidate.expectation is not None:
            store.record_expectation(candidate.expectation)
        opened.append(candidate.belief)

    summary = BF.summarise(candidates, refused)
    summary.update({
        "requested": True, "examined": len(recorded),
        "declared": len(opened),
        "beliefs": [b.belief_id for b in opened],
        "note": ("opened from evidence already on the ledger; a repair of "
                 "evidence that predates belief formation, NOT learning "
                 "earned this session, and excluded from knowledge gain")})
    if not opened and refused:
        summary["note"] = ("nothing on the ledger proposed a belief: "
                           + ", ".join(f"{k} {v}"
                                       for k, v in sorted(refused.items())))
    result.backfill_summary = summary
    return tuple(opened)


def _classify_outcome(result: LearningResult, ingested: int, declared: int,
                      revised: int, *, candidates_seen: int = 0) -> str:
    """Which of the five things happened. Deliberately not a score.

    Order matters: declaring a belief is new knowledge even in a session that
    also revised one, because the declaration is the thing that did not exist
    before. `OBSERVED_NO_IMPACT` is a real and common result — evidence
    arrived, no belief moved — and is recorded as such rather than as a
    smaller version of learning.

    The last two are the pair an operator most needs kept apart.
    `UNCLASSIFIABLE_INPUT` means candidate sentences reached the translator
    and none of them carried an event, which is a pipeline symptom.
    `NO_NEW_EVIDENCE` means nothing arrived at all, which is a retrieval
    symptom or simply a quiet day. Reporting both as zero is what made eleven
    consecutive cycles indistinguishable from each other.
    """
    if declared:
        return LS.NEW_KNOWLEDGE
    if revised or result.hidden_state_summary.get("companies_moved"):
        return LS.BELIEF_MOVEMENT
    if ingested:
        return LS.OBSERVED_NO_IMPACT
    if candidates_seen:
        return LS.UNCLASSIFIABLE_INPUT
    return LS.NO_NEW_EVIDENCE
