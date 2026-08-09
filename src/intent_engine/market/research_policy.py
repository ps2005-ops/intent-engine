"""Choosing what to look at next, as a decision problem rather than an order.

WHAT WAS ACTUALLY MISSING
-------------------------
The engine has always chosen research actions. It has never recorded them. The
ledger holds 316 pieces of evidence and not one row saying "we asked source X
about company Y and this is what came back" — so the question "would a
different policy have done better?" had no data to be asked of, and any claim
about learned research allocation would have been a claim about nothing.

A policy cannot be evaluated against outcomes that were never paired with the
choices that produced them. So the first thing here is the log, and the
policies come second.

THE PROBLEM, STATED
-------------------
    STATE       what is unresolved, how stale, which sources have paid off
    ACTION      ask source family F about subject S for question Q
    OBSERVATION evidence, no evidence, or evidence that cannot be used
    REWARD      independent, discriminating, decision-relevant information,
                net of cost — and explicitly NOT volume

WHY THIS IS NOT CALLED REINFORCEMENT LEARNING
---------------------------------------------
Because it is not one yet. The rewards are delayed and sparse, the state is
partially observed, and — decisively — the historical log was produced by a
DETERMINISTIC policy, so there is no exploration in it to learn from. Off-policy
estimators that assume a randomising logger (inverse propensity weighting and
its relatives) are not merely imprecise here, they are inapplicable: every
propensity is 1 or 0. What can honestly be done is REPLAY: score a candidate
policy on the subset of the log where it would have made the same choice, and
report how much of the log that was. `overlap` is reported on every evaluation
for exactly this reason, and a policy scored on 8% of the log is described as
such rather than as a winner.

THE SAFETY WALL
---------------
A learned policy may reorder research. It may not do anything else. The list of
what it may not touch is explicit and the check raises rather than warns,
because the failure mode is a policy that gradually discovers that the highest
reward available to it is to stop asking hard questions.
"""
from __future__ import annotations

import dataclasses
import hashlib
import math
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

CONTRACT = "research_policy.v1"

# --- what a research action can be ------------------------------------------
#
# Source FAMILIES, not URLs. The choice a policy makes is "what kind of place
# should I look", and the specific document is downstream of that.
REGULATORY_FILING = "regulatory_filing"
COMPANY_OWNED = "company_owned"
INDEPENDENT_REPORTING = "independent_reporting"
ANALYST_COVERAGE = "analyst_coverage"
GOVERNMENT_DATA = "government_data"

SOURCE_FAMILIES = (REGULATORY_FILING, COMPANY_OWNED, INDEPENDENT_REPORTING,
                   ANALYST_COVERAGE, GOVERNMENT_DATA)

# --- what came back ----------------------------------------------------------
USED = "USED"            # evidence that entered the ledger
REFUSED = "REFUSED"      # retrieved and rejected by a contract
EMPTY = "EMPTY"          # the source had nothing
FAILED = "FAILED"        # the source could not be reached
OUTCOMES = (USED, REFUSED, EMPTY, FAILED)

# --- what a policy may never control ------------------------------------------
#
# Stated as data so the guard cannot drift from the doctrine it enforces.
RESTRICTED_ACTIONS = frozenset({
    "place_trade", "deploy", "send_customer_message", "sign_contract",
    "move_funds", "publish", "delete_records",
})


class PolicyRejected(ValueError):
    """A policy asked to do something a research policy may not do."""


class OutsideResearch(PolicyRejected):
    """Raised when a policy reaches past research ordering."""


def guard_action(action_kind: str) -> str:
    """The wall. Raises rather than warning, and is called on every dispatch.

    A learned policy optimising a research reward has no term that would stop
    it from taking a non-research action if one were reachable; the only thing
    that stops it is that the action is not reachable.
    """
    if action_kind in RESTRICTED_ACTIONS:
        raise OutsideResearch(
            f"{action_kind} is not a research action; a policy learned from "
            "information gain has no term that prices being wrong about it")
    return action_kind


@dataclass(frozen=True)
class ResearchAction:
    """Ask one source family one question about one subject."""

    source_family: str
    subject: str
    question: str = ""
    cost: float = 1.0

    def __post_init__(self) -> None:
        if self.source_family not in SOURCE_FAMILIES:
            raise PolicyRejected(
                f"unknown source family {self.source_family!r}")
        if self.cost <= 0:
            raise PolicyRejected(
                "an action with no cost makes every policy that takes more of "
                "them look better")

    @property
    def key(self) -> Tuple[str, str]:
        return (self.source_family, self.subject)

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclass(frozen=True)
class ResearchOutcome:
    """What one action produced, in the terms the reward is computed from."""

    outcome: str
    #: Did the evidence come from someone other than its subject?
    independent: bool = False
    #: Had this (source family, subject) already produced this fact?
    duplicate: bool = False
    #: Did it bear on a question that was actually open?
    resolved_open_question: bool = False
    #: Did it separate two live explanations, rather than adding weight to the
    #: one already ahead? This is the term a confirmation-seeking policy
    #: cannot farm — and it is Optional because a reconstructed log cannot
    #: answer it. None means UNMEASURED, and the reward credits nothing for
    #: it; returning False instead would make "we cannot tell" indistinguishable
    #: from "we checked and it did not", which is how an unmeasurable term
    #: quietly becomes a settled zero.
    discriminating: Optional[bool] = None
    #: Did it change something a reader would decide differently about?
    decision_relevant: bool = False
    latency_seconds: float = 0.0

    def __post_init__(self) -> None:
        if self.outcome not in OUTCOMES:
            raise PolicyRejected(f"unknown outcome {self.outcome!r}")

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclass(frozen=True)
class ResearchRecord:
    """One (context, action, outcome) triple. The unit a policy is scored on.

    `reconstructed` matters. A record rebuilt from evidence that is already in
    the ledger is not a log entry: the action was inferred from its result, so
    actions that produced nothing are systematically absent, and every rate
    computed from a reconstructed log is biased toward success. Reported, not
    corrected, because there is no honest correction — only a real log.
    """

    action: ResearchAction
    outcome: ResearchOutcome
    at: str = ""
    reconstructed: bool = False
    context: Dict[str, str] = field(default_factory=dict)
    #: What was ACTUALLY on the menu when this choice was made. Empty on a
    #: reconstructed row, because a log rebuilt from surviving evidence cannot
    #: know what else was available — which is exactly why `evaluate_offline`
    #: had to assume every family was, and why every policy that prefers a
    #: family the corpus happens to contain scored as though it had chosen it
    #: against competition.
    eligible_options: Tuple[str, ...] = ()

    @property
    def record_id(self) -> str:
        raw = "|".join((self.action.source_family, self.action.subject,
                        self.action.question, self.at, self.outcome.outcome))
        return "ra_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def as_dict(self) -> dict:
        return {"record": "research_action", "contract": CONTRACT,
                "record_id": self.record_id, "at": self.at,
                "reconstructed": self.reconstructed,
                "context": dict(self.context),
                **{f"action_{k}": v for k, v in self.action.as_dict().items()},
                **{f"outcome_{k}": v
                   for k, v in self.outcome.as_dict().items()}}


# --- the reward ---------------------------------------------------------------
#
# WEIGHTS ARE STATED, NOT TUNED. A tuned reward is a reward fitted to the
# behaviour it was supposed to judge. These say what the project believes is
# valuable, and if they are wrong that is a disagreement somebody can have.
#
# NOTHING HERE COUNTS DOCUMENTS. Every Goodhart failure this project has met
# came from rewarding a count: rows retrieved, beliefs declared, claims made.
# A policy that maximises volume scores zero on all five positive terms.
REWARD_WEIGHTS = {
    "independent": 1.0,        # somebody other than the subject said it
    "resolved_open_question": 1.5,
    "discriminating": 2.0,     # separated two live explanations
    "decision_relevant": 2.0,
    "duplicate": -1.0,
    "refused": -0.25,
    "failed": -0.1,
    "cost": -0.2,
}

#: The largest reward a single action can earn. Used to normalise, and to make
#: it obvious that no term scales with how much was retrieved.
MAX_ACTION_REWARD = (REWARD_WEIGHTS["independent"]
                     + REWARD_WEIGHTS["resolved_open_question"]
                     + REWARD_WEIGHTS["discriminating"]
                     + REWARD_WEIGHTS["decision_relevant"])


def reward(record: ResearchRecord) -> float:
    """What one action was worth, in information rather than in output."""
    out, act = record.outcome, record.action
    total = REWARD_WEIGHTS["cost"] * act.cost
    if out.outcome == FAILED:
        return total + REWARD_WEIGHTS["failed"]
    if out.outcome == REFUSED:
        total += REWARD_WEIGHTS["refused"]
    if out.outcome != USED:
        return total
    if out.duplicate:
        total += REWARD_WEIGHTS["duplicate"]
    for term in ("independent", "resolved_open_question", "discriminating",
                 "decision_relevant"):
        # `is True`, not truthiness: an unmeasured discriminating term is None
        # and must earn nothing rather than being coerced to False and read as
        # a measurement that came back negative.
        if getattr(out, term) is True:
            total += REWARD_WEIGHTS[term]
    return round(total, 6)


# --- policies -------------------------------------------------------------------

class Policy:
    """Choose one source family, given a context. Nothing else."""

    name = "POLICY"

    def choose(self, context: Dict[str, str],
               options: Sequence[str]) -> str:  # pragma: no cover - interface
        raise NotImplementedError

    def learn(self, context: Dict[str, str], chosen: str,
              got: float) -> None:
        """Most policies do not. Present so the loop is uniform."""


class FixedPolicy(Policy):
    """Always the same family. The floor every other policy must clear."""

    def __init__(self, family: str, name: str = ""):
        self.family = family
        self.name = name or f"FIXED_{family.upper()}"

    def choose(self, context, options):
        return self.family if self.family in options else options[0]


class RandomPolicy(Policy):
    """Uniform choice from a fixed seed. Deterministic across runs.

    A policy that cannot be reproduced cannot be compared, and an evaluation
    that changes when it is re-run is not a measurement.
    """

    name = "RANDOM"

    def __init__(self, seed: int = 0):
        self._seed = seed
        self._n = 0

    def choose(self, context, options):
        self._n += 1
        digest = hashlib.sha256(
            f"{self._seed}|{self._n}|{context.get('subject', '')}".encode()
        ).digest()
        return options[digest[0] % len(options)]


class HistoricalYieldPolicy(Policy):
    """Whichever family has paid best so far, overall.

    The obvious learned policy, and the one most likely to be quietly wrong:
    it has no notion of context, so a family that is excellent for one kind of
    question drags every other question toward itself.
    """

    name = "HISTORICAL_YIELD"

    def __init__(self):
        self._total: Dict[str, float] = {}
        self._n: Dict[str, int] = {}

    def choose(self, context, options):
        def mean(family: str) -> float:
            n = self._n.get(family, 0)
            # An untried family is optimistic, not zero: a policy that never
            # tries a family can never learn that it was good.
            return self._total.get(family, 0.0) / n if n else MAX_ACTION_REWARD
        return max(options, key=lambda f: (mean(f), f))

    def learn(self, context, chosen, got):
        self._total[chosen] = self._total.get(chosen, 0.0) + got
        self._n[chosen] = self._n.get(chosen, 0) + 1


class ContextualBanditPolicy(Policy):
    """Per-context means with an optimism bonus. A bandit, and named as one.

    UCB over (context bucket, family). This is the honest ceiling for the data
    available: with a few hundred actions and no exploration in the log, a
    richer model would be fitting the sample. The context is deliberately
    coarse — the question type — because a context fine enough to identify a
    single subject turns every arm into a sample of one.
    """

    name = "CONTEXTUAL_BANDIT"

    def __init__(self, confidence: float = 1.0):
        self.confidence = confidence
        self._total: Dict[Tuple[str, str], float] = {}
        self._n: Dict[Tuple[str, str], int] = {}
        self._seen = 0

    @staticmethod
    def bucket(context: Dict[str, str]) -> str:
        return str(context.get("question_type") or "unknown")

    def choose(self, context, options):
        bucket = self.bucket(context)
        self._seen += 1

        def score(family: str) -> float:
            key = (bucket, family)
            n = self._n.get(key, 0)
            if not n:
                return MAX_ACTION_REWARD + self.confidence
            mean = self._total[key] / n
            return mean + self.confidence * math.sqrt(
                math.log(max(2, self._seen)) / n)
        return max(options, key=lambda f: (score(f), f))

    def learn(self, context, chosen, got):
        key = (self.bucket(context), chosen)
        self._total[key] = self._total.get(key, 0.0) + got
        self._n[key] = self._n.get(key, 0) + 1


class VOIPolicy(Policy):
    """The engine's stated heuristic: prefer sources that can contradict.

    Encoded as a fixed preference order rather than learned, because that is
    what the project already believes — a third party can establish a rivalry
    and a company's own newsroom cannot. It is here to be beaten.
    """

    name = "VOI_HEURISTIC"

    ORDER = (REGULATORY_FILING, GOVERNMENT_DATA, INDEPENDENT_REPORTING,
             ANALYST_COVERAGE, COMPANY_OWNED)

    def choose(self, context, options):
        for family in self.ORDER:
            if family in options:
                return family
        return options[0]


# --- offline evaluation ----------------------------------------------------------

@dataclass(frozen=True)
class PolicyEvaluation:
    """What a policy would have scored, and on how much of the log."""

    policy: str
    matched: int
    total: int
    mean_reward: Optional[float]
    #: Fraction of logged decisions where the policy agreed with the logger.
    #: The estimate is only about those, and a small overlap is a small claim.
    overlap: float = 0.0
    independent_rate: Optional[float] = None
    duplicate_rate: Optional[float] = None
    discriminating_rate: Optional[float] = None
    #: Rows where the choice set was ASSUMED to be every family, because the
    #: record did not carry one. A score computed mostly from these describes
    #: a menu that never existed.
    assumed_menu: int = 0
    note: str = ""

    @property
    def trustworthy(self) -> bool:
        """Whether the estimate rests on enough of the log to mean anything."""
        return self.matched >= 30 and self.overlap >= 0.2

    @property
    def menu_is_real(self) -> bool:
        """Whether any row was scored against the options it actually had.

        DELIBERATELY NOT FOLDED INTO `trustworthy`. Doing that would mark
        every existing evaluation untrustworthy at a stroke — no reconstructed
        row carries a menu — and the reward-hack audit that depends on
        `trustworthy` would stop reporting, which is a working guard switched
        off rather than a defect fixed. The two questions are different: "does
        this rest on enough rows" and "were those rows real choices". A
        cross-policy comparison stays meaningful under an assumed menu because
        every policy faces the same one; a claim about a single policy's
        absolute value does not.
        """
        return self.total > 0 and self.assumed_menu < self.total

    def as_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d.update(contract=CONTRACT, trustworthy=self.trustworthy,
                 menu_is_real=self.menu_is_real)
        return d


def evaluate_offline(log: Sequence[ResearchRecord], policy: Policy, *,
                     options: Sequence[str] = SOURCE_FAMILIES
                     ) -> PolicyEvaluation:
    """Replay: score the policy where it agreed with what was actually done.

    THIS IS NOT INVERSE PROPENSITY WEIGHTING and must not be read as if it
    were. IPW needs a logging policy that randomised; this one did not, so
    every propensity is 1 or 0 and the reweighting is undefined. Replay is
    what remains: an unbiased estimate of the policy's value ON THE SUBSET IT
    AGREES WITH, which is a different and smaller claim. `overlap` is how
    small.
    """
    matched: List[ResearchRecord] = []
    assumed_menu = 0
    for record in log:
        # THE MENU THAT EXISTED, where the row knows it. A prospective record
        # carries the eligible set; a reconstructed one cannot, and falls back
        # to the full family list. The fallback is counted and reported,
        # because scoring a policy against options that were never available
        # is how a constant preference order comes to look like a decision.
        available = list(record.eligible_options or options)
        if not record.eligible_options:
            assumed_menu += 1
        if not available:
            continue
        chosen = guard_action(policy.choose(dict(record.context), available))
        got = reward(record)
        if chosen == record.action.source_family:
            matched.append(record)
            policy.learn(dict(record.context), chosen, got)
    total = len(log)
    if not matched:
        return PolicyEvaluation(
            policy=policy.name, matched=0, total=total, mean_reward=None,
            overlap=0.0, assumed_menu=assumed_menu,
            note=("the policy never agreed with the logger, so the log says "
                  "nothing about it"))
    rewards = [reward(r) for r in matched]
    used = [r for r in matched if r.outcome.outcome == USED]
    return PolicyEvaluation(
        policy=policy.name, matched=len(matched), total=total,
        mean_reward=round(sum(rewards) / len(rewards), 4),
        overlap=round(len(matched) / total, 4) if total else 0.0,
        independent_rate=(round(sum(1 for r in used if r.outcome.independent)
                                / len(used), 4) if used else None),
        duplicate_rate=(round(sum(1 for r in used if r.outcome.duplicate)
                              / len(used), 4) if used else None),
        discriminating_rate=(
            round(sum(1 for r in used if r.outcome.discriminating)
                  / len(used), 4) if used else None),
        assumed_menu=assumed_menu,
        note=("replay estimate over the agreeing subset; not valid as a claim "
              "about the whole log"
              + (f"; {assumed_menu}/{total} rows had no recorded choice set "
                 "and were scored against every family"
                 if assumed_menu else "")))


def compare(log: Sequence[ResearchRecord],
            policies: Sequence[Policy]) -> dict:
    """Every policy against the same log, with the baselines included.

    Baselines are not optional. A learned policy reported without the fixed
    and random ones beside it is a number with nothing to be better than.
    """
    results = [evaluate_offline(log, p) for p in policies]
    trustworthy = [r for r in results if r.trustworthy
                   and r.mean_reward is not None]
    ranked = sorted(trustworthy, key=lambda r: -(r.mean_reward or 0))
    random_result = next((r for r in results if r.policy == RandomPolicy.name),
                         None)
    return {
        "contract": CONTRACT,
        "log_size": len(log),
        "reconstructed": sum(1 for r in log if r.reconstructed),
        "evaluations": [r.as_dict() for r in results],
        "ranked": [r.policy for r in ranked],
        "best": ranked[0].policy if ranked else "",
        "beats_random": bool(
            ranked and random_result is not None
            and random_result.mean_reward is not None
            and ranked[0].mean_reward > random_result.mean_reward),
        "deployable": False,
        "why_not_deployable": (
            "the log was produced by a deterministic policy, so it contains "
            "no exploration; replay can rank policies on the subset they "
            "agree with and cannot establish what an unseen choice would have "
            "returned"),
    }


# --- the log, built from what the evidence actually did -------------------------------

def log_from_effects(rows: Sequence[dict], effects: Sequence,
                     *, costs: Optional[Dict[str, float]] = None
                     ) -> List[ResearchRecord]:
    """A research log priced by knowledge effects rather than by proxies.

    THE DIFFERENCE FROM `reconstruct_log`. That function had to guess what a
    piece of evidence was worth from the shape of the row: it could see
    independence and duplication and nothing else, so three of the reward's
    four positive terms were permanently zero and the volume attack won. This
    one reads the effect log — what the evidence CHANGED — so
    `resolved_open_question`, `discriminating` and `decision_relevant` become
    measurements instead of blanks.

    Evidence with a NO_CHANGE effect is a real, priced outcome: the source was
    consulted and moved nothing. Evidence with NO effect record at all is not
    in this log, because nobody examined it and pricing an unexamined action
    would invent a result.
    """
    from . import knowledge_effect as KE

    by_evidence = KE.by_evidence([e for e in effects])
    meta = {str(r.get("evidence_id") or ""): r for r in rows
            if r.get("record") == "evidence"}
    out: List[ResearchRecord] = []
    seen: Dict[Tuple[str, str, str], int] = {}
    for evidence_id, mine in sorted(by_evidence.items()):
        row = meta.get(evidence_id)
        if row is None:
            continue
        family = _ROLE_TO_FAMILY.get(str(row.get("source_role") or ""))
        subject = str(row.get("subject_company") or "")
        if not family or not subject:
            continue
        # Only DIRECT effects may price an action; a reconstructed attribution
        # is evidence about the past, not a measurement of this choice.
        priceable = [e for e in mine if e.priceable]
        changed = [e for e in priceable if e.changed]
        fact = str(row.get("fact") or "")[:160]
        key = (family, subject, fact)
        duplicate = key in seen
        seen[key] = seen.get(key, 0) + 1
        try:
            independence = float(row.get("independence"))
        except (TypeError, ValueError):
            independence = 0.0
        out.append(ResearchRecord(
            action=ResearchAction(
                source_family=family, subject=subject,
                question=str(row.get("evidence_type") or ""),
                cost=(costs or {}).get(family, 1.0)),
            outcome=ResearchOutcome(
                outcome=USED,
                independent=(independence >= INDEPENDENCE_THRESHOLD
                             and not row.get("self_authored", False)),
                duplicate=duplicate,
                resolved_open_question=any(
                    e.effect_type in (KE.RESOLVED, KE.CREATED)
                    for e in changed),
                # MEASURED NOW, not None. An effect that contradicted,
                # resolved, invalidated or discriminated separated two live
                # explanations; one that merely supported the leader did not.
                discriminating=(bool(any(e.discriminating for e in changed))
                                if priceable else None),
                decision_relevant=any(
                    e.target_type in (KE.CAUSAL_NODE, KE.CAUSAL_EDGE,
                                      KE.THESIS, KE.COMPANY_EXPOSURE,
                                      KE.ECONOMIC_STATE,
                                      KE.FOUNDER_DECISION_COMPONENT)
                    for e in changed)),
            at=str(row.get("observed_at") or ""),
            reconstructed=not any(e.priceable for e in mine),
            context={"subject": subject,
                     "question_type": str(row.get("evidence_type")
                                          or "unknown")}))
    return out


# --- rebuilding a log the engine never kept -----------------------------------------

#: How a source role in the ledger maps onto the family a policy would choose.
_ROLE_TO_FAMILY = {
    "regulatory_filing": REGULATORY_FILING,
    "company_owned": COMPANY_OWNED,
    "independent_reporting": INDEPENDENT_REPORTING,
    "analyst_coverage": ANALYST_COVERAGE,
    "government_data": GOVERNMENT_DATA,
}

#: How independent a source has to be before the reward calls it independent.
#:
#: The ledger stores independence as a SCORE, not a label — 0.9 for reporting,
#: 0.85 for a filing, 0.25 for a company's own newsroom — and the first version
#: of this reconstruction compared that float to the string "INDEPENDENT",
#: matched nothing, and fell through to a `self_authored` fallback that happened
#: to give a similar answer for the wrong reason.
INDEPENDENCE_THRESHOLD = 0.7


def reconstruct_log(rows: Sequence[dict]) -> List[ResearchRecord]:
    """Rebuild (action, outcome) pairs from evidence that survived.

    THE BIAS IS STRUCTURAL AND IS NOT CORRECTED HERE. An action is inferred
    from its result, so every action that returned nothing is missing: the
    reconstructed log contains only successes and near-successes, and the
    useful-evidence rate computed from it is not the engine's real hit rate.
    Every record is stamped `reconstructed=True` and every evaluation built on
    them inherits that caveat. The fix is a real log going forward, which is
    what `ResearchRecord` is for; this exists so the policies have something
    to be compared on before that log has any depth.
    """
    seen: Dict[Tuple[str, str, str], int] = {}
    out: List[ResearchRecord] = []
    for row in rows:
        if row.get("record") != "evidence":
            continue
        family = _ROLE_TO_FAMILY.get(str(row.get("source_role") or ""))
        subject = str(row.get("subject_company") or "")
        if not family or not subject:
            continue
        fact = str(row.get("fact") or "")[:160]
        key = (family, subject, fact)
        duplicate = key in seen
        seen[key] = seen.get(key, 0) + 1
        try:
            independence = float(row.get("independence"))
        except (TypeError, ValueError):
            independence = 0.0
        independent = (independence >= INDEPENDENCE_THRESHOLD
                       and not row.get("self_authored", False))
        out.append(ResearchRecord(
            action=ResearchAction(
                source_family=family, subject=subject,
                question=str(row.get("evidence_type") or "")),
            outcome=ResearchOutcome(
                outcome=USED,
                independent=bool(independent),
                duplicate=duplicate,
                resolved_open_question=bool(row.get("affected_hypotheses")),
                # UNMEASURABLE FROM A RECONSTRUCTED LOG, and left as None.
                # Whether a document separated two live explanations depends
                # on which explanations were live when it arrived, and the
                # ledger records the document, not the state of the argument
                # it landed in. The only honest repair is a real log written
                # at the moment of the choice.
                discriminating=None,
                # `relevance` is 0.6 on all 316 rows, so it distinguishes
                # nothing and is not read. What a document touched is a fact
                # about the document; what it was scored is not.
                decision_relevant=bool(row.get("affected_causal_nodes"))),
            at=str(row.get("observed_at") or row.get("available_at") or ""),
            reconstructed=True,
            context={"subject": subject,
                     "question_type": str(row.get("evidence_type") or
                                          "unknown")}))
    return out


# --- reward hacking ---------------------------------------------------------------

#: Populated by `audit_reward` so the change-rate pass reads the same policy
#: objects that were evaluated, learning included.
_POLICY_BY_NAME: Dict[str, "Policy"] = {}


def diagnose_source_preference(log: Sequence[ResearchRecord]) -> dict:
    """Why the stated preference order and the measured value disagree.

    THE FINDING THIS EXISTS TO RECORD. `VOIPolicy` is not a value-of-
    information computation. It is a fixed order beginning with
    `regulatory_filing`, so on any log containing filings it selects them and
    nothing else — it is `FixedPolicy(REGULATORY_FILING)` wearing a name that
    suggests a calculation. Measured on the 316-row reconstructed log the two
    are identical to full precision on matched, overlap, mean reward,
    independence, duplication and discrimination.

    The order's stated rationale is independence: prefer sources that can
    contradict the subject. But independence is 1.0 for BOTH filings and
    independent reporting, so that rationale does not separate them. What
    separates them is duplication — 0.75 against 0.027 — because a filing
    restates a company's position while reporting carries new events.

    NOTHING HERE FLIPS THE ORDER. Two reasons. First, a preference derived
    from this log would be derived from evidence that survived, and the rows
    that would justify it — actions that returned nothing — are the ones the
    reconstruction cannot contain. Second, duplication among retrieved
    documents and hit rate per action are different quantities, and only the
    first is measurable here. The honest output is the disagreement and its
    size, and the prospective log is what settles it.
    """
    import collections

    by_family: Dict[str, List[ResearchRecord]] = collections.defaultdict(list)
    for record in log:
        by_family[record.action.source_family].append(record)

    def rate(rows: List[ResearchRecord], attribute: str) -> Optional[float]:
        used = [r for r in rows if r.outcome.outcome == USED]
        if not used:
            return None
        return round(sum(1 for r in used
                         if getattr(r.outcome, attribute) is True)
                     / len(used), 4)

    measured = {}
    for family, rows in by_family.items():
        rewards = [reward(r) for r in rows]
        measured[family] = {
            "actions": len(rows),
            "mean_reward": round(sum(rewards) / len(rewards), 4),
            "independent_rate": rate(rows, "independent"),
            "duplicate_rate": rate(rows, "duplicate"),
            "discriminating_rate": rate(rows, "discriminating"),
        }

    ranked_by_value = [f for f, _ in sorted(
        measured.items(), key=lambda kv: -kv[1]["mean_reward"])]
    stated = [f for f in VOIPolicy.ORDER if f in measured]
    agrees = stated == ranked_by_value
    top_stated = stated[0] if stated else ""
    top_measured = ranked_by_value[0] if ranked_by_value else ""
    return {
        "contract": CONTRACT,
        "stated_order": stated,
        "measured_order": ranked_by_value,
        "order_agrees_with_measurement": agrees,
        "stated_first": top_stated,
        "measured_first": top_measured,
        "by_family": measured,
        # The candidate causes, answered rather than listed. Each is checked
        # against the measurement rather than asserted.
        "cause": {
            "policy_reads_performance_state": False,
            "policy_is_a_constant": True,
            "duplication_penalised": REWARD_WEIGHTS["duplicate"] < 0,
            "independence_separates_the_top_two": (
                len({measured.get(f, {}).get("independent_rate")
                     for f in (top_stated, top_measured) if f}) > 1),
            "duplication_separates_the_top_two": (
                len({measured.get(f, {}).get("duplicate_rate")
                     for f in (top_stated, top_measured) if f}) > 1),
        },
        "verdict": (
            "the stated order matches the measurement" if agrees else
            f"the stated order asks {top_stated} first; the measured value "
            f"ranks {top_measured} first. The order is a constant that reads "
            "no performance state, so this is not a miscalibrated estimate — "
            "there is no estimate"),
        "why_not_corrected_here": (
            "a replacement order derived from this log would be derived from "
            "evidence that survived; the actions that returned nothing are "
            "exactly the rows that would justify it, and they are absent. "
            "Duplication among retrieved documents is measurable here; hit "
            "rate per action is not"),
        "settled_by": "a prospective decision log with recorded choice sets",
    }


def audit_reward(log: Sequence[ResearchRecord]) -> dict:
    """Try to farm the reward, and report whether it can be farmed.

    Four attacks, each a policy that is obviously bad and obviously cheap:

        VOLUME        take the family that answers most often
        CONFIRMING    take the family that agrees with the subject about itself
        EASY          avoid the families that refuse things
        CHEAPEST      minimise cost and nothing else

    If any of them tops the ranking, the reward is measuring the wrong thing
    and no learned policy built on it can be trusted — which is a finding
    about the reward, not about the attack.
    """
    by_family: Dict[str, List[ResearchRecord]] = {}
    for record in log:
        by_family.setdefault(record.action.source_family, []).append(record)

    def most(key: Callable[[List[ResearchRecord]], float]) -> str:
        if not by_family:
            return SOURCE_FAMILIES[0]
        return max(sorted(by_family), key=lambda f: key(by_family[f]))

    attacks = [
        FixedPolicy(most(lambda rs: sum(1 for r in rs
                                        if r.outcome.outcome == USED)),
                    name="ATTACK_VOLUME"),
        FixedPolicy(COMPANY_OWNED, name="ATTACK_CONFIRMING"),
        FixedPolicy(most(lambda rs: -sum(1 for r in rs
                                         if r.outcome.outcome == REFUSED)),
                    name="ATTACK_EASY"),
        FixedPolicy(most(lambda rs: -sum(r.action.cost for r in rs)
                         / max(1, len(rs))), name="ATTACK_CHEAPEST"),
    ]
    honest = [VOIPolicy(), ContextualBanditPolicy(), RandomPolicy()]
    # Kept by name so the change-rate pass can re-ask each policy what it
    # would have chosen. A fresh instance would be wrong: the bandit learned
    # during the evaluation, and re-running it cold would score a different
    # policy from the one that was measured.
    global _POLICY_BY_NAME
    _POLICY_BY_NAME = {p.name: p for p in attacks + honest}
    results = {p.name: evaluate_offline(log, p) for p in attacks + honest}
    # TRUSTWORTHY ONLY. A bandit that matched twelve of three hundred rows can
    # post the highest mean in the table on noise, and letting it sit above an
    # attack would report a hackable reward as safe. An estimate that cannot
    # be trusted cannot exonerate one either.
    scored = {n: r.mean_reward for n, r in results.items()
              if r.mean_reward is not None and r.trustworthy}
    unscored = sorted(n for n, r in results.items() if not r.trustworthy)
    if not scored:
        return {"contract": CONTRACT, "audited": len(log), "hackable": None,
                "not_trustworthy": unscored,
                "note": "no policy matched enough of the log to be scored"}
    top = max(scored, key=lambda n: scored[n])
    ties = sorted(n for n, v in scored.items()
                  if abs(v - scored[top]) < 1e-9)

    # AN ATTACK WINNING IS NOT THE SAME AS THE REWARD BEING HACKED, and the
    # first version of this audit could not tell the difference. It reported
    # HACKABLE because ATTACK_VOLUME topped the table — but ATTACK_VOLUME
    # picks the family with the most accepted answers, and in this corpus that
    # family also has the HIGHEST rate of knowledge change (0.76), the highest
    # discrimination rate and the LOWEST duplication (0.03). The volume arm and
    # the value arm are the same arm. Calling that a hack would mean the audit
    # fires whenever the best source is also the most prolific one, which is
    # most of the time, and an alarm that is always on is not an alarm.
    #
    # A hack is winning WITHOUT producing knowledge. So the test is whether
    # the leading attack changes less per action than the best honest policy:
    # farming volume means a low change rate, and a source that genuinely
    # teaches has a high one.
    change_rate = _change_rate_by_policy(log, results)
    attackers = [n for n in ties if n.startswith("ATTACK_")]
    honest_best = max((n for n in scored if not n.startswith("ATTACK_")),
                      key=lambda n: scored[n], default="")
    hacked = []
    for name in attackers:
        mine = change_rate.get(name)
        theirs = change_rate.get(honest_best)
        if mine is None or theirs is None or mine < theirs:
            hacked.append(name)
    return {
        "contract": CONTRACT,
        "audited": len(log),
        "scores": {n: round(v, 4) for n, v in sorted(scored.items())},
        "change_rate": {n: round(v, 4) for n, v in sorted(change_rate.items())},
        "not_trustworthy": unscored,
        "top": top,
        "tied_at_the_top": ties,
        "best_honest": honest_best,
        "hackable": bool(hacked),
        "hacking_policies": sorted(hacked),
        "note": ("an attack is a hack when it wins while changing LESS per "
                 "action than the best honest policy; an attack that wins "
                 "because the prolific source is also the informative one is "
                 "the reward working, not failing"),
    }


def _change_rate_by_policy(log: Sequence[ResearchRecord],
                           results: Dict[str, PolicyEvaluation],
                           options: Sequence[str] = SOURCE_FAMILIES
                           ) -> Dict[str, float]:
    """Share of a policy's matched actions that changed a knowledge object.

    Measured off the outcome fields the effect log now fills in. Before
    attribution existed this could not be computed at all, which is why the
    audit had to fall back on "did an attack win" and reported a false
    positive on the first corpus it saw.
    """
    out: Dict[str, float] = {}
    for name in results:
        policy = _POLICY_BY_NAME.get(name)
        if policy is None:
            continue
        matched = [r for r in log
                   if policy.choose(dict(r.context), list(options))
                   == r.action.source_family]
        if not matched:
            continue
        changed = sum(1 for r in matched
                      if r.outcome.resolved_open_question
                      or r.outcome.decision_relevant
                      or r.outcome.discriminating is True)
        out[name] = changed / len(matched)
    return out
