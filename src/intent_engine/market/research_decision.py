"""The choice, written down before it is made.

WHAT WAS ACTUALLY MISSING
-------------------------
`research_policy` gave the engine a log of (action, outcome) pairs and a way to
score policies on it. But that log is REBUILT from evidence that survived, and
an action is therefore inferred from its result. Three kinds of row can never
appear in it:

    the source was asked and had nothing;
    the document came back and was refused;
    the family was eligible and was not chosen.

The first two make every rate computed from the log biased toward success — it
is a success log wearing the name of a research log. The third is worse,
because it is what a policy comparison needs most: to say a policy would have
done better, you have to know what else it could have done.

So this module records the DECISION, before the call, with the choice set
attached, and pairs an outcome to it afterwards whatever the outcome was.

WHY THE CHOICE SET IS LOAD-BEARING
----------------------------------
`research_policy.evaluate_offline` currently offers every policy all five
source families on every record, because the log does not say which were
available. A policy is therefore scored against a menu that never existed, and
`VOIPolicy` — whose preference order begins with `regulatory_filing` and which
is a constant rather than a computation — wins the filing rows by construction.
Recording the eligible set is not an enhancement to policy learning. It is the
difference between a measurement and an artefact.

WHAT THIS MODULE REFUSES TO DO
------------------------------
It will not invent a propensity. A deterministic policy has no selection
probability, and writing 1.0 into that field would make the log look like it
came from a randomising logger, which is exactly the precondition that
inverse-propensity estimators check for and this log does not meet. The status
field carries KNOWN / DETERMINISTIC / UNAVAILABLE and supplying a probability
alongside DETERMINISTIC raises.

It will not accept a chosen action that is absent from its own candidate set,
or one recorded as ineligible. A choice set assembled after the fact to contain
the winner is the single most attractive way to fake this layer, and it is the
one an outcome-driven reconstruction produces naturally.

It will not accept an outcome that started before its decision was written.
That ordering is the whole claim this module makes; if it is not enforced, a
reconstructed pair is indistinguishable from a prospective one.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

CONTRACT = "research_decision.v1"

# --- provenance ---------------------------------------------------------------
#
# The wall. A row that was written before the call and a row inferred from a
# surviving document are different KINDS of evidence about the policy, and
# pooling them lets the success bias in the second silently establish the value
# of the first.
PROSPECTIVE = "PROSPECTIVE"
RECONSTRUCTED = "RECONSTRUCTED"
PROVENANCES = (PROSPECTIVE, RECONSTRUCTED)

# --- how the choice was made --------------------------------------------------
#: The policy randomised and the probability is recorded. Only this status may
#: carry a number.
KNOWN = "KNOWN"
#: The policy is deterministic. There is no propensity. Not 1.0 — none.
DETERMINISTIC = "DETERMINISTIC"
#: The policy randomised but did not expose its probability.
UNAVAILABLE = "UNAVAILABLE"
PROBABILITY_STATUSES = (KNOWN, DETERMINISTIC, UNAVAILABLE)

# --- what came back -----------------------------------------------------------
SUCCESS = "SUCCESS"
#: The source was reachable and had nothing. TRAINING DATA, not an error.
NO_RESULT = "NO_RESULT"
#: Documents came back and every fact in them was already held.
NO_NEW_INFORMATION = "NO_NEW_INFORMATION"
#: Retrieved and rejected by a contract.
REFUSED = "REFUSED"
FAILED = "FAILED"
TIMEOUT = "TIMEOUT"
STATUSES = (SUCCESS, NO_RESULT, NO_NEW_INFORMATION, REFUSED, FAILED, TIMEOUT)

#: Statuses that mean the engine learned the source had nothing to give. These
#: are the rows the reconstructed log cannot contain, and the reason this
#: module exists.
EMPTY_HANDED = frozenset({NO_RESULT, NO_NEW_INFORMATION})


#: Acquisition family -> the coarser EVIDENCE source role `research_policy`
#: reasons over. DECLARED ONCE, HERE. The cycle chooses an acquisition family
#: (`customer_case_study`); a policy reasons about who published the document
#: (`company_owned`). Both vocabularies are needed and neither can replace the
#: other, but a second copy of this table in the step that writes the log
#: would drift from this one silently, and the symptom would be a company's
#: own case study scoring as an independent witness.
RP_FAMILY_FOR = {
    "government_award": "government_data",
    "partnership_release": "company_owned",
    "customer_case_study": "company_owned",
}


class DecisionRejected(ValueError):
    """A research decision that would misrepresent how it was made."""


def _digest(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


# --- the choice set -----------------------------------------------------------

@dataclass(frozen=True)
class CandidateAction:
    """One option that was actually on the table, chosen or not.

    `eligible=False` with a `refusal_reason` is a first-class row. A family
    that was cadence-blocked, or that cannot answer the predicate, was
    CONSIDERED AND EXCLUDED, and a log that simply omits it cannot distinguish
    "not applicable" from "never thought of".
    """

    source_family: str
    query_strategy: str = ""
    estimated_cost: float = 1.0
    estimated_latency: float = 0.0
    expected_voi: float = 0.0
    eligible: bool = True
    refusal_reason: str = ""

    def __post_init__(self) -> None:
        if not self.source_family:
            raise DecisionRejected("a candidate needs a source family")
        if self.eligible and self.refusal_reason:
            raise DecisionRejected(
                f"{self.source_family} is marked eligible and also carries a "
                f"refusal reason ({self.refusal_reason!r}); one of those is "
                "wrong and a reader cannot tell which")
        if not self.eligible and not self.refusal_reason:
            raise DecisionRejected(
                f"{self.source_family} was excluded without a stated reason; "
                "an unexplained exclusion is indistinguishable from a family "
                "the planner forgot")

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


# --- the state the choice was made in -----------------------------------------

@dataclass(frozen=True)
class StateSnapshot:
    """Bounded features describing what was unresolved when the choice was made.

    BOUNDED ON PURPOSE. Serialising the application state would make every
    snapshot unique, unjoinable and enormous; a policy needs a stable feature
    vector it can condition on, and a future model needs these fields to mean
    the same thing across months.
    """

    as_of: str = ""
    open_hypotheses: int = 0
    unresolved_falsifiers: int = 0
    stale_facts: int = 0
    subjects_without_exposure: int = 0
    world_model_gaps: int = 0
    research_budget_remaining: float = 0.0
    dominant_self_test_class: str = ""
    learning_status: str = ""

    @property
    def snapshot_id(self) -> str:
        return "st_" + _digest(dataclasses.asdict(self))

    def as_dict(self) -> dict:
        out = dataclasses.asdict(self)
        out.update(contract=CONTRACT, snapshot_id=self.snapshot_id)
        return out


# --- the decision -------------------------------------------------------------

@dataclass(frozen=True)
class ResearchDecision:
    """What was chosen, out of what, by whom, expecting what — written first."""

    subject: str
    question_type: str
    chosen_action: str
    candidates: Tuple[CandidateAction, ...]
    selection_policy: str
    policy_version: str = "1"
    question_id: str = ""
    missing_fact: str = ""
    state_snapshot_id: str = ""
    expected_voi: float = 0.0
    expected_cost: float = 1.0
    budget_remaining: float = 0.0
    query_strategy: str = ""
    selection_probability: Optional[float] = None
    selection_probability_status: str = DETERMINISTIC
    chosen_at: str = ""
    provenance: str = PROSPECTIVE
    #: TWO VOCABULARIES, KEPT APART. `chosen_action` is the thing actually
    #: chosen — an acquisition family like `customer_case_study`, which is
    #: what the cycle iterates. `research_policy` reasons over EVIDENCE source
    #: roles (`company_owned`, `independent_reporting`, ...), a coarser axis.
    #: Collapsing the two would either restrict the log to roles the cycle
    #: never picks from, or let a role name be recorded as a choice nobody
    #: made. The bridge maps one to the other and this field carries it.
    policy_family: str = ""
    note: str = ""

    def __post_init__(self) -> None:
        if self.provenance not in PROVENANCES:
            raise DecisionRejected(f"unknown provenance {self.provenance!r}")
        status = self.selection_probability_status
        if status not in PROBABILITY_STATUSES:
            raise DecisionRejected(
                f"unknown selection_probability_status {status!r}")
        # THE PROPENSITY WALL. A deterministic policy has no propensity, and a
        # 1.0 written here would present this log as one an off-policy
        # estimator could consume.
        if status != KNOWN and self.selection_probability is not None:
            raise DecisionRejected(
                f"selection_probability={self.selection_probability} was "
                f"supplied with status {status}; only {KNOWN} may carry a "
                "number, because a deterministic choice has no propensity and "
                "recording one would misrepresent the log as explored")
        if status == KNOWN:
            probability = self.selection_probability
            if probability is None or not 0.0 < probability <= 1.0:
                raise DecisionRejected(
                    f"status {KNOWN} needs a probability in (0, 1], got "
                    f"{probability!r}")
        if not self.candidates:
            raise DecisionRejected(
                "a decision with no candidate set records a choice nobody can "
                "check; log the eligible options even when there is one")
        # Checked BEFORE membership: if nothing was on the menu there was no
        # choice to record, and reporting that as "your pick is missing from
        # the set" names the symptom instead of the cause.
        if not any(c.eligible for c in self.candidates):
            raise DecisionRejected(
                "no candidate was eligible, so there was no decision to make")
        # THE CHOICE-SET WALL. Assembling the menu after the fact so that it
        # contains the winner is what an outcome-driven reconstruction does by
        # default, and it is undetectable downstream.
        chosen = [c for c in self.candidates
                  if c.source_family == self.chosen_action]
        if not chosen:
            raise DecisionRejected(
                f"chosen action {self.chosen_action!r} is not in its own "
                f"candidate set "
                f"{sorted(c.source_family for c in self.candidates)!r}")
        if not chosen[0].eligible:
            raise DecisionRejected(
                f"chosen action {self.chosen_action!r} was recorded as "
                f"ineligible ({chosen[0].refusal_reason!r})")

    @property
    def decision_id(self) -> str:
        return "rd_" + _digest({
            "subject": self.subject, "question_type": self.question_type,
            "chosen": self.chosen_action, "at": self.chosen_at,
            "policy": self.selection_policy,
            "candidates": sorted(c.source_family for c in self.candidates)})

    @property
    def eligible_families(self) -> Tuple[str, ...]:
        """The real menu. This is what a policy must be scored against."""
        return tuple(sorted(c.source_family for c in self.candidates
                            if c.eligible))

    @property
    def forgone(self) -> Tuple[str, ...]:
        """Eligible options that were not taken — the counterfactual arm."""
        return tuple(f for f in self.eligible_families
                     if f != self.chosen_action)

    def as_dict(self) -> dict:
        return {
            "record": "research_decision", "contract": CONTRACT,
            "decision_id": self.decision_id,
            "state_snapshot_id": self.state_snapshot_id,
            "subject": self.subject, "question_id": self.question_id,
            "question_type": self.question_type,
            "missing_fact": self.missing_fact,
            "candidate_actions": [c.as_dict() for c in self.candidates],
            "chosen_action": self.chosen_action,
            "selection_policy": self.selection_policy,
            "policy_version": self.policy_version,
            "expected_voi": round(self.expected_voi, 6),
            "expected_cost": round(self.expected_cost, 6),
            "budget_remaining": round(self.budget_remaining, 6),
            "source_family": self.chosen_action,
            "query_strategy": self.query_strategy,
            "selection_probability": self.selection_probability,
            "selection_probability_status": self.selection_probability_status,
            "chosen_at": self.chosen_at, "provenance": self.provenance,
            "policy_family": self.policy_family,
            "eligible_families": list(self.eligible_families),
            "forgone": list(self.forgone),
            "note": self.note,
        }


# --- what the action returned -------------------------------------------------

@dataclass(frozen=True)
class DecisionOutcome:
    """What one logged decision produced, including nothing.

    Named `DecisionOutcome` rather than `ResearchOutcome` because
    `research_policy.ResearchOutcome` already exists and means something
    narrower — the bundle of reward TERMS. Reusing the name across two modules
    that are imported together would make every call site ambiguous.
    """

    decision_id: str
    status: str
    started_at: str = ""
    completed_at: str = ""
    documents_attempted: int = 0
    documents_retrieved: int = 0
    accepted_evidence: int = 0
    refused_evidence: int = 0
    new_events: int = 0
    independent_events: int = 0
    dependent_events: int = 0
    knowledge_effect_ids: Tuple[str, ...] = ()
    #: WHICH evidence this action produced. Without it the delayed half of
    #: the reward has no way to trace a later consequence back to the action
    #: that found the evidence, and credit could only be spread across
    #: everything that ran that night.
    produced_evidence_ids: Tuple[str, ...] = ()
    immediate_reward: Optional[float] = None
    latency_seconds: float = 0.0
    cost: float = 0.0
    failure_type: str = ""

    def __post_init__(self) -> None:
        if not self.decision_id:
            raise DecisionRejected(
                "an outcome without a decision_id is an observation with no "
                "choice attached, which is the row this module exists to stop")
        if self.status not in STATUSES:
            raise DecisionRejected(f"unknown status {self.status!r}")
        if self.status in (FAILED, TIMEOUT) and not self.failure_type:
            raise DecisionRejected(
                f"{self.status} needs a failure_type; an unrecognised failure "
                "is the only information a failed action carries")
        if self.status == SUCCESS and not self.accepted_evidence:
            raise DecisionRejected(
                f"{SUCCESS} with no accepted evidence is {NO_RESULT} or "
                f"{NO_NEW_INFORMATION}; calling it success is how an empty "
                "action becomes a productive one in the rates")

    @property
    def empty_handed(self) -> bool:
        return self.status in EMPTY_HANDED

    def as_dict(self) -> dict:
        out = dataclasses.asdict(self)
        out["knowledge_effect_ids"] = list(self.knowledge_effect_ids)
        out["produced_evidence_ids"] = list(self.produced_evidence_ids)
        out.update(record="research_outcome", contract=CONTRACT)
        return out


@dataclass(frozen=True)
class DelayedOutcome:
    """A consequence that arrived later. Appended, never folded backwards.

    The immediate reward stays what it was. A belief that resolved three weeks
    after the action that found the evidence is a SECOND record, because
    rewriting the first would destroy the only honest measurement of what was
    knowable at the time.
    """

    decision_id: str
    outcome_type: str
    target_id: str
    reward_delta: float
    observed_at: str = ""
    provenance: str = ""

    def __post_init__(self) -> None:
        if not self.decision_id or not self.outcome_type:
            raise DecisionRejected(
                "a delayed outcome needs the decision it belongs to and the "
                "kind of consequence it was")

    @property
    def delayed_id(self) -> str:
        return "dl_" + _digest({
            "decision": self.decision_id, "type": self.outcome_type,
            "target": self.target_id, "at": self.observed_at})

    def as_dict(self) -> dict:
        out = dataclasses.asdict(self)
        out.update(record="research_delayed_outcome", contract=CONTRACT,
                   delayed_id=self.delayed_id)
        return out


# --- pairing ------------------------------------------------------------------

def pair(decisions: Sequence[ResearchDecision],
         outcomes: Sequence[DecisionOutcome]
         ) -> Tuple[List[Tuple[ResearchDecision, DecisionOutcome]],
                    List[ResearchDecision], List[DecisionOutcome]]:
    """Join decisions to outcomes, and REPORT the ones that did not join.

    Orphans are the interesting rows. A decision with no outcome is an action
    that was chosen and never completed — a crash, a timeout, a cycle that died
    — and it is exactly the sort of row a success log loses.

    An outcome whose `started_at` precedes its decision's `chosen_at` is
    refused, because the ordering is the only thing separating a prospective
    log from a reconstruction that put the choice set in afterwards.
    """
    by_id = {d.decision_id: d for d in decisions}
    joined: List[Tuple[ResearchDecision, DecisionOutcome]] = []
    matched_ids = set()
    orphan_outcomes: List[DecisionOutcome] = []
    for outcome in outcomes:
        decision = by_id.get(outcome.decision_id)
        if decision is None:
            orphan_outcomes.append(outcome)
            continue
        started, chosen = outcome.started_at, decision.chosen_at
        if started and chosen and started < chosen:
            raise DecisionRejected(
                f"outcome for {outcome.decision_id} started {started} but its "
                f"decision was written {chosen}; an outcome that predates its "
                "decision means the choice was recorded after the result")
        joined.append((decision, outcome))
        matched_ids.add(outcome.decision_id)
    orphan_decisions = [d for d in decisions
                        if d.decision_id not in matched_ids]
    return joined, orphan_decisions, orphan_outcomes


def to_research_record(decision: ResearchDecision, outcome: DecisionOutcome,
                       *, duplicate: bool = False,
                       discriminating: Optional[bool] = None,
                       decision_relevant: bool = False,
                       resolved_open_question: bool = False,
                       independent: bool = False):
    """Project a prospective pair into the shape `research_policy` scores.

    This is the bridge that lets the existing evaluation machinery read real
    records. `reconstructed` is set from the decision's provenance rather than
    hardcoded, so a reconstructed row projected through here keeps its mark.
    """
    from . import research_policy as RP

    status_to_outcome = {
        SUCCESS: RP.USED,
        NO_RESULT: RP.EMPTY,
        NO_NEW_INFORMATION: RP.USED,
        REFUSED: RP.REFUSED,
        FAILED: RP.FAILED,
        TIMEOUT: RP.FAILED,
    }
    projected = status_to_outcome[outcome.status]
    return RP.ResearchRecord(
        action=RP.ResearchAction(
            source_family=decision.policy_family or decision.chosen_action,
            subject=decision.subject,
            question=decision.question_type,
            cost=max(decision.expected_cost, 0.0001)),
        outcome=RP.ResearchOutcome(
            outcome=projected,
            independent=independent,
            # NO_NEW_INFORMATION is precisely a duplicate: documents arrived
            # and every fact was held. The caller may also flag one.
            duplicate=duplicate or outcome.status == NO_NEW_INFORMATION,
            resolved_open_question=resolved_open_question,
            discriminating=discriminating,
            decision_relevant=decision_relevant,
            latency_seconds=outcome.latency_seconds),
        at=decision.chosen_at,
        reconstructed=decision.provenance == RECONSTRUCTED,
        context={"subject": decision.subject,
                 "question_type": decision.question_type},
        # The real menu travels with the row, so a policy is scored against
        # what was available rather than against every family that exists.
        eligible_options=tuple(
            RP_FAMILY_FOR.get(f, f) for f in decision.eligible_families))


# --- the wall, as a computation -----------------------------------------------

def split_by_provenance(decisions: Sequence[ResearchDecision]
                        ) -> Dict[str, List[ResearchDecision]]:
    out: Dict[str, List[ResearchDecision]] = {p: [] for p in PROVENANCES}
    for decision in decisions:
        out[decision.provenance].append(decision)
    return out


def evaluation_standing(decisions: Sequence[ResearchDecision]) -> dict:
    """Whether a policy claim built on these rows is allowed to stand.

    A policy is not production-ready on reconstructed data, however much of it
    there is. This returns the standing and the reason rather than a boolean,
    because "not yet" and "never from this input" are different answers.
    """
    split = split_by_provenance(decisions)
    prospective, reconstructed = (len(split[PROSPECTIVE]),
                                  len(split[RECONSTRUCTED]))
    total = prospective + reconstructed
    explored = sum(1 for d in split[PROSPECTIVE]
                   if d.selection_probability_status == KNOWN)
    forgone = sum(1 for d in split[PROSPECTIVE] if d.forgone)
    if not prospective:
        standing, why = "NOT_EVALUABLE", (
            "no prospective decisions; every row was inferred from evidence "
            "that survived, so actions returning nothing are absent and every "
            "rate is biased toward success")
    elif not forgone:
        standing, why = "NOT_EVALUABLE", (
            f"{prospective} prospective decisions but none recorded a forgone "
            "eligible option, so there is no alternative to compare against")
    elif not explored:
        standing, why = "REPLAY_ONLY", (
            f"{prospective} prospective decisions, none with a known "
            "propensity; replay can score a policy on the subset it agrees "
            "with, and cannot estimate what an unchosen option would have "
            "returned")
    else:
        standing, why = "OFFLINE_EVALUABLE", (
            f"{explored} of {prospective} prospective decisions carry a known "
            "selection probability")
    return {
        "contract": CONTRACT, "standing": standing, "why": why,
        "prospective": prospective, "reconstructed": reconstructed,
        "total": total,
        "reconstructed_share": (round(reconstructed / total, 4)
                                if total else 0.0),
        "with_forgone_option": forgone,
        "with_known_propensity": explored,
        "deployable": False,
        "why_not_deployable": (
            "a research policy is not promoted from this module; promotion "
            "requires the reward-hack audit and a baseline comparison on "
            "prospective rows"),
    }


def summarise(decisions: Sequence[ResearchDecision],
              outcomes: Sequence[DecisionOutcome] = (),
              delayed: Sequence[DelayedOutcome] = ()) -> dict:
    """Counts a reader can check the claims against."""
    import collections

    joined, orphan_decisions, orphan_outcomes = pair(decisions, outcomes)
    by_status = collections.Counter(o.status for o in outcomes)
    by_family = collections.Counter(d.chosen_action for d in decisions)
    by_policy = collections.Counter(d.selection_policy for d in decisions)
    candidates = sum(len(d.candidates) for d in decisions)
    eligible = sum(len(d.eligible_families) for d in decisions)
    return {
        "contract": CONTRACT,
        "decisions": len(decisions),
        "outcomes": len(outcomes),
        "paired": len(joined),
        "decisions_without_outcome": len(orphan_decisions),
        "outcomes_without_decision": len(orphan_outcomes),
        "candidate_rows": candidates,
        "eligible_options": eligible,
        "mean_choice_set": (round(eligible / len(decisions), 3)
                            if decisions else 0.0),
        "decisions_with_a_forgone_option": sum(1 for d in decisions
                                               if d.forgone),
        "by_status": {s: by_status.get(s, 0) for s in STATUSES},
        "empty_handed": sum(by_status.get(s, 0) for s in EMPTY_HANDED),
        "by_chosen_family": dict(by_family),
        "by_policy": dict(by_policy),
        "delayed_outcomes": len(delayed),
        "delayed_reward_total": round(sum(d.reward_delta for d in delayed), 6),
        **evaluation_standing(decisions),
        "note": ("empty_handed rows are the ones a reconstructed log cannot "
                 "contain; if this is zero on a real run, check that the "
                 "logger is writing outcomes for families that returned "
                 "nothing rather than only for the ones that produced"),
    }


# --- the delayed half of the reward --------------------------------------------

#: Consequence kinds an action can earn credit for after the fact.
BELIEF_RESOLVED = "BELIEF_RESOLVED"
FALSIFIER_RESOLVED = "FALSIFIER_RESOLVED"
THESIS_REVISED = "THESIS_REVISED"
MECHANISM_TESTED = "MECHANISM_TESTED"
DECISION_IMPACT = "FOUNDER_DECISION_IMPACT"

#: What a consequence is worth. Stated, not tuned. A revision that WEAKENED a
#: thesis is worth as much as one that strengthened it: an action that showed
#: the engine it was wrong did the same job as one that confirmed it, and a
#: reward that paid only for confirmation would teach the policy to seek it.
DELAYED_WEIGHTS = {
    BELIEF_RESOLVED: 1.5,
    FALSIFIER_RESOLVED: 2.0,
    THESIS_REVISED: 2.0,
    MECHANISM_TESTED: 1.5,
    DECISION_IMPACT: 3.0,
}


def credit_revisions(decisions: Sequence[ResearchDecision],
                     outcomes: Sequence[DecisionOutcome],
                     revisions: Sequence, *, observed_at: str = ""
                     ) -> Tuple[List[DelayedOutcome], dict]:
    """Pay an action for a thesis revision its evidence later caused.

    THE LINK, AND WHERE IT BREAKS. A revision names the knowledge effects that
    moved the thesis. An effect names the evidence it came from. So an action
    earns delayed credit when a revision cites an effect whose evidence that
    action produced — decision -> outcome -> evidence -> effect -> revision.

    That chain only closes if the outcome recorded WHICH evidence it produced,
    which is why `produced_evidence_ids` exists. Where it is empty the credit
    is unattributable, and this returns zero with the reason rather than
    spreading the reward across every action from that night. An action
    credited for a consequence it cannot be shown to have caused is worse than
    an uncredited one: it teaches the policy a false association.
    """
    by_decision = {}
    for outcome in outcomes:
        for evidence_id in outcome.produced_evidence_ids:
            by_decision.setdefault(str(evidence_id), outcome.decision_id)
    known = {d.decision_id for d in decisions}
    out: List[DelayedOutcome] = []
    unattributable = 0
    credited_revisions = set()
    reward_by_transition: dict = {}
    for revision in revisions:
        cited = list(getattr(revision, "knowledge_effect_ids", ())
                     or (revision.get("knowledge_effect_ids", ())
                         if isinstance(revision, dict) else ()))
        evidence = list(getattr(revision, "triggering_evidence", ())
                        or (revision.get("triggering_evidence", ())
                            if isinstance(revision, dict) else ()))
        matched = [by_decision[e] for e in evidence if e in by_decision]
        if not matched:
            if cited or evidence:
                unattributable += 1
            continue
        thesis_id = str(getattr(revision, "thesis_id", "")
                        or (revision.get("thesis_id", "")
                            if isinstance(revision, dict) else ""))
        transition = str(getattr(revision, "transition", "")
                         or (revision.get("transition", "")
                             if isinstance(revision, dict) else ""))
        for decision_id in sorted(set(matched)):
            if decision_id not in known:
                continue
            out.append(DelayedOutcome(
                decision_id=decision_id, outcome_type=THESIS_REVISED,
                target_id=thesis_id,
                reward_delta=DELAYED_WEIGHTS[THESIS_REVISED],
                observed_at=observed_at, provenance="thesis_revision"))
            credited_revisions.add((thesis_id, transition))
            reward_by_transition[transition] = round(
                reward_by_transition.get(transition, 0.0)
                + DELAYED_WEIGHTS[THESIS_REVISED], 6)
    return out, {
        "contract": CONTRACT,
        "revisions_considered": len(revisions),
        "delayed_outcomes": len(out),
        "unattributable_revisions": unattributable,
        "actions_with_produced_evidence": sum(
            1 for o in outcomes if o.produced_evidence_ids),
        # THE SAME FIGURES UNDER THE NAMES AN OPERATOR ASKS FOR. Delayed
        # credit was computed and persisted for a run before anything
        # projected it, so "did this action get paid for what it found" had a
        # correct answer nobody could read.
        "delayed_outcomes_written": len(out),
        "decisions_credited": len({o.decision_id for o in out}),
        "revisions_credited": len(credited_revisions),
        "untraceable_revisions": unattributable,
        "reward_delta_total": round(sum(o.reward_delta for o in out), 6),
        # SYMMETRY, MADE CHECKABLE. One weight pays every revision, so a
        # weakening earns exactly what a strengthening earns. That is
        # deliberate — an action that found the evidence which knocked a
        # thesis down did the same job as one that propped it up — and it is
        # reported per transition so the claim can be verified rather than
        # taken on trust.
        "reward_by_transition": dict(sorted(reward_by_transition.items())),
        "note": ("a revision whose evidence cannot be traced to a logged "
                 "action earns nobody credit; spreading it over the night's "
                 "actions would teach the policy an association that was "
                 "never observed"),
    }
