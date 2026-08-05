"""Beliefs that move on evidence, and record exactly what moved them.

WHAT A BELIEF IS HERE
---------------------
A proposition about the world with a probability attached, a trail of the
evidence that produced that probability, and a stated basis for the arithmetic.
It is not a score, not a confidence vibe, and not something the engine may
adjust because a cycle felt productive.

PRIOR → BASIS → POSTERIOR, ALWAYS RECORDED
------------------------------------------
Every update writes all three. A posterior with no recorded basis is
indistinguishable from a number someone typed, and six weeks later nobody can
tell which it was.

THE HONESTY PROBLEM WITH BAYES HERE
-----------------------------------
A real Bayesian update needs likelihoods — P(evidence | proposition true) and
P(evidence | false). This engine has not measured those for most propositions,
and inventing them would put four decimal places on a guess. So `update_method`
is part of the contract and is never decorative:

    EMPIRICAL_BAYES      likelihoods derived from measured base rates
    CALIBRATED_HEURISTIC a bounded step scaled by evidence quality, honest
                         about being a heuristic
    QUALITATIVE          direction recorded, magnitude explicitly not claimed

`CALIBRATED_HEURISTIC` is what most updates are today, and the report says so.
The alternative — dressing it as empirical Bayes — is the false-precision
failure the metric-integrity work exists to prevent.

FIVE RULES THAT KEEP THIS FROM MANUFACTURING CONFIDENCE
-------------------------------------------------------
1. Duplicate evidence updates once. Ids are content hashes, and `applied`
   remembers them, so re-reading an unchanged filing nightly does nothing.
2. Correlated evidence gets a design-effect penalty. Six outlets rewriting one
   press release are close to one witness, not six.
3. Self-authored evidence cannot corroborate the author's own motives.
4. Missing evidence does not weaken. Absence moves a belief toward uncertainty
   through decay, never toward false.
5. Model claims are not evidence. Only `MicroEvidence` — which cannot exist
   without a source — is accepted.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional, Sequence, Tuple

from . import micro_evidence as ME

CONTRACT_VERSION = "strategic_belief.v1"

# --- update methods -------------------------------------------------------
EMPIRICAL_BAYES = "EMPIRICAL_BAYES"
CALIBRATED_HEURISTIC = "CALIBRATED_HEURISTIC"
QUALITATIVE = "QUALITATIVE"
DECAY = "DECAY"
UPDATE_METHODS = frozenset({EMPIRICAL_BAYES, CALIBRATED_HEURISTIC,
                            QUALITATIVE, DECAY})

# --- lifecycle ------------------------------------------------------------
ACTIVE = "ACTIVE"
UNDER_REVIEW = "UNDER_REVIEW"
RETIRED = "RETIRED"
LIFECYCLE = frozenset({ACTIVE, UNDER_REVIEW, RETIRED})

# --- learning speed (§20) -------------------------------------------------
FAST = "FAST"        # minutes to days   — priors
MEDIUM = "MEDIUM"    # days to weeks     — mechanisms
SLOW = "SLOW"        # weeks to months   — structure
SPEEDS = frozenset({FAST, MEDIUM, SLOW})

# A belief never reaches certainty. 0.02/0.98 leaves room for the world to
# surprise a belief the engine was sure about, which has happened before.
_FLOOR, _CEIL = 0.02, 0.98

# The largest single-item move a heuristic update may make. Deliberately
# small: no one observation should be able to swing a structural belief, and
# the cap is what stops a noisy fast signal from rewriting slow knowledge.
_MAX_STEP = 0.12

# Structural beliefs resist fast evidence. A SLOW belief updated by a FAST
# observation moves at a third of the rate — the mechanism for §20's rule
# that a noisy signal must not permanently rewrite structural knowledge.
_SPEED_DAMPING = {(SLOW, FAST): 0.33, (SLOW, MEDIUM): 0.66,
                  (MEDIUM, FAST): 0.5}


@dataclass(frozen=True)
class BeliefUpdate:
    """One recorded movement, with everything needed to audit it."""
    at: str
    prior: float
    posterior: float
    method: str
    basis: str
    evidence_ids: Tuple[str, ...] = ()
    effective_sample_size: float = 0.0

    @property
    def direction(self) -> str:
        if self.posterior > self.prior:
            return "STRENGTHENED"
        if self.posterior < self.prior:
            return "WEAKENED"
        return "UNCHANGED"

    def as_dict(self) -> dict:
        return {"at": self.at, "prior": self.prior,
                "posterior": self.posterior, "method": self.method,
                "basis": self.basis, "direction": self.direction,
                "evidence_ids": list(self.evidence_ids),
                "effective_sample_size": self.effective_sample_size}


@dataclass(frozen=True)
class StrategicBelief:
    """A proposition, its probability, and the trail that produced it."""
    belief_id: str
    proposition: str
    subject: str
    prior_probability: float
    posterior_probability: float
    last_updated: str
    learning_speed: str = MEDIUM
    supporting_evidence_ids: Tuple[str, ...] = ()
    contradicting_evidence_ids: Tuple[str, ...] = ()
    applied_evidence_ids: Tuple[str, ...] = ()
    history: Tuple[BeliefUpdate, ...] = ()
    last_validated: str = ""
    decay_eligible: bool = True
    review_interval_days: int = 90
    confidence_basis: str = ""
    limitations: Tuple[str, ...] = ()
    lifecycle_state: str = ACTIVE

    @property
    def effective_sample_size(self) -> float:
        """Independent-equivalent evidence count, not the raw row count."""
        return round(sum(u.effective_sample_size for u in self.history), 3)

    @property
    def entropy(self) -> float:
        """Binary Shannon entropy — how undecided this belief is, 0..1."""
        p = self.posterior_probability
        if p <= 0 or p >= 1:
            return 0.0
        return round(-(p * math.log2(p) + (1 - p) * math.log2(1 - p)), 4)

    def has_applied(self, evidence_id: str) -> bool:
        return evidence_id in self.applied_evidence_ids

    def as_dict(self) -> dict:
        return {
            "belief_id": self.belief_id, "proposition": self.proposition,
            "subject": self.subject,
            "prior_probability": self.prior_probability,
            "posterior_probability": self.posterior_probability,
            "learning_speed": self.learning_speed,
            "supporting_evidence_ids": list(self.supporting_evidence_ids),
            "contradicting_evidence_ids":
                list(self.contradicting_evidence_ids),
            "last_updated": self.last_updated,
            "last_validated": self.last_validated,
            "decay_eligible": self.decay_eligible,
            "review_interval_days": self.review_interval_days,
            "confidence_basis": self.confidence_basis,
            "effective_sample_size": self.effective_sample_size,
            "entropy": self.entropy,
            "limitations": list(self.limitations),
            "lifecycle_state": self.lifecycle_state,
            "history": [u.as_dict() for u in self.history],
        }


def create(*, belief_id: str, proposition: str, subject: str,
           prior: float, at: str, learning_speed: str = MEDIUM,
           confidence_basis: str = "", decay_eligible: bool = True,
           review_interval_days: int = 90,
           limitations: Sequence[str] = ()) -> StrategicBelief:
    if learning_speed not in SPEEDS:
        raise ValueError(f"unknown learning_speed {learning_speed!r}")
    p = _clamp(prior)
    return StrategicBelief(
        belief_id=belief_id, proposition=proposition, subject=subject,
        prior_probability=p, posterior_probability=p, last_updated=at[:10],
        learning_speed=learning_speed, confidence_basis=confidence_basis,
        decay_eligible=decay_eligible,
        review_interval_days=review_interval_days,
        limitations=tuple(limitations))


def design_effect(items: Sequence[ME.MicroEvidence]) -> float:
    """Independent-equivalent count for a correlated batch.

    Six outlets rewriting one company press release are not six witnesses.
    The penalty is applied per source-role group: within a group items are
    treated as heavily correlated (each additional one contributes on a
    square-root scale), while across groups they add more freely. It is a
    deliberately conservative approximation and is labelled as one — the true
    correlation structure is not measured, and pretending otherwise would be
    the false precision this module refuses elsewhere.
    """
    if not items:
        return 0.0
    groups: Dict[str, List[ME.MicroEvidence]] = {}
    for item in items:
        groups.setdefault(item.source_role, []).append(item)
    total = 0.0
    for role, group in groups.items():
        weight = ME.INDEPENDENCE.get(role, 0.5)
        # sqrt growth within a correlated group: 1 → 1.0, 4 → 2.0, 9 → 3.0
        total += weight * math.sqrt(len(group))
    return round(total, 4)


def update(belief: StrategicBelief, evidence: Sequence[ME.MicroEvidence], *,
           at: str, method: str = CALIBRATED_HEURISTIC,
           likelihood_ratio: Optional[float] = None,
           evidence_speed: str = FAST) -> Tuple[StrategicBelief, bool]:
    """Revise on evidence. Returns (belief, changed).

    Returns the belief unchanged — and `changed=False` — whenever the evidence
    is duplicate, irrelevant, or purely neutral. That is a real and common
    result, and reporting it as an update would be the manufactured progress
    this whole design refuses.
    """
    if belief.lifecycle_state == RETIRED:
        return belief, False
    if method not in UPDATE_METHODS:
        raise ValueError(f"unknown update method {method!r}")

    fresh = [e for e in ME.deduplicate(evidence)
             if not belief.has_applied(e.evidence_id)
             and e.contradiction_role != ME.NEUTRAL]
    if not fresh:
        return belief, False

    supporting = [e for e in fresh if e.contradiction_role == ME.SUPPORTING]
    contradicting = [e for e in fresh
                     if e.contradiction_role == ME.CONTRADICTING]

    prior = belief.posterior_probability
    if method == EMPIRICAL_BAYES:
        if not likelihood_ratio or likelihood_ratio <= 0:
            raise ValueError(
                "EMPIRICAL_BAYES requires a measured likelihood_ratio; "
                "without one the update is a heuristic and must say so")
        posterior = _bayes(prior, likelihood_ratio)
        ess = design_effect(fresh)
        basis = (f"empirical Bayes, likelihood ratio {likelihood_ratio:.3f}, "
                 f"effective sample {ess}")
    elif method == QUALITATIVE:
        # Direction only. The posterior does not move; the trail records that
        # the belief was tested and which way the evidence leaned.
        posterior = prior
        ess = design_effect(fresh)
        lean = "supporting" if len(supporting) > len(contradicting) else \
            "contradicting" if contradicting else "mixed"
        basis = (f"qualitative: evidence leans {lean}; magnitude deliberately "
                 f"not claimed because no likelihood is measured")
    else:
        sup_ess = design_effect(supporting)
        con_ess = design_effect(contradicting)
        ess = sup_ess + con_ess
        net = sup_ess - con_ess
        if net == 0:
            # Genuinely balanced evidence. The belief was tested and did not
            # move, which is recorded rather than dropped.
            posterior = prior
            basis = (f"calibrated heuristic: supporting and contradicting "
                     f"evidence balanced at {sup_ess}/{con_ess}")
        else:
            quality = _mean_quality(supporting if net > 0 else contradicting)
            damping = _SPEED_DAMPING.get((belief.learning_speed,
                                          evidence_speed), 1.0)
            step = min(_MAX_STEP, abs(net) * 0.04 * quality) * damping
            posterior = _clamp(prior + (step if net > 0 else -step))
            basis = (f"calibrated heuristic: net effective evidence "
                     f"{net:+.3f}, quality {quality:.2f}, "
                     f"{belief.learning_speed}/{evidence_speed} damping "
                     f"{damping:.2f}")

    record = BeliefUpdate(at=at[:10], prior=prior, posterior=posterior,
                          method=method, basis=basis,
                          evidence_ids=tuple(e.evidence_id for e in fresh),
                          effective_sample_size=round(ess, 4))
    return replace(
        belief,
        posterior_probability=posterior,
        last_updated=at[:10], last_validated=at[:10],
        supporting_evidence_ids=belief.supporting_evidence_ids + tuple(
            e.evidence_id for e in supporting),
        contradicting_evidence_ids=belief.contradicting_evidence_ids + tuple(
            e.evidence_id for e in contradicting),
        applied_evidence_ids=belief.applied_evidence_ids + tuple(
            e.evidence_id for e in fresh),
        history=belief.history + (record,)), True


def update_from_reconciliation(belief: StrategicBelief, outcome: str, *,
                               at: str, rationale: str = "",
                               expectation_id: str = "",
                               evidence_speed: str = MEDIUM
                               ) -> Tuple[StrategicBelief, bool]:
    """Revise from a preregistered expectation's result. NO TRADE INVOLVED.

    This is the function that breaks the measured no-trade/no-learning
    dependency. A CONTRADICTED expectation moves the posterior down on the
    strength of a commitment made before the observation, which is stronger
    evidence than most filings and costs nothing to collect.
    """
    from . import expectation as EXP
    if belief.lifecycle_state == RETIRED or outcome not in EXP.INFORMATIVE:
        return belief, False

    prior = belief.posterior_probability
    magnitude = {EXP.CONFIRMED: 0.06, EXP.PARTIALLY_CONFIRMED: 0.03,
                 EXP.CONTRADICTED: -0.08}[outcome]
    damping = _SPEED_DAMPING.get((belief.learning_speed, evidence_speed), 1.0)
    posterior = _clamp(prior + magnitude * damping)
    record = BeliefUpdate(
        at=at[:10], prior=prior, posterior=posterior,
        method=CALIBRATED_HEURISTIC,
        basis=(f"preregistered expectation {outcome}: {rationale}"
               if rationale else f"preregistered expectation {outcome}"),
        evidence_ids=(expectation_id,) if expectation_id else (),
        effective_sample_size=1.0)
    return replace(belief, posterior_probability=posterior,
                   last_updated=at[:10], last_validated=at[:10],
                   history=belief.history + (record,)), True


def decay(belief: StrategicBelief, *, at: str,
          half_life_days: Optional[int] = None
          ) -> Tuple[StrategicBelief, bool]:
    """Move an unsupported belief toward uncertainty — never toward false.

    The distinction is the whole point. A belief nobody has checked in six
    months is not refuted; it is unvalidated. Decay therefore pulls the
    posterior toward 0.5 from whichever side it sits on, so a stale belief
    becomes less certain rather than becoming its own negation. Recorded with
    method DECAY so it is never mistaken for contradicting evidence.
    """
    if not belief.decay_eligible or belief.lifecycle_state == RETIRED:
        return belief, False
    anchor = belief.last_validated or belief.last_updated
    age = _days_between(anchor, at)
    if age is None:
        return belief, False
    interval = half_life_days or belief.review_interval_days
    if age < interval:
        return belief, False

    prior = belief.posterior_probability
    elapsed = age / float(interval)
    retained = 0.5 ** elapsed
    posterior = round(0.5 + (prior - 0.5) * retained, 4)
    if abs(posterior - prior) < 1e-4:
        return belief, False
    record = BeliefUpdate(
        at=at[:10], prior=prior, posterior=posterior, method=DECAY,
        basis=(f"unvalidated for {age}d against a {interval}d review "
               f"interval; moved toward uncertainty, NOT toward false"),
        effective_sample_size=0.0)
    return replace(belief, posterior_probability=posterior,
                   last_updated=at[:10],
                   history=belief.history + (record,)), True


def should_review(belief: StrategicBelief, *, at: str) -> bool:
    age = _days_between(belief.last_validated or belief.last_updated, at)
    return age is not None and age >= belief.review_interval_days


def _bayes(prior: float, likelihood_ratio: float) -> float:
    odds = (prior / (1 - prior)) * likelihood_ratio
    return _clamp(odds / (1 + odds))


def _mean_quality(items: Sequence[ME.MicroEvidence]) -> float:
    """Reliability × relevance, averaged. Self-authored items are halved.

    A company's own account of why it cut prices is not a witness to its
    motive; it is the defendant's testimony, and it is weighted accordingly.
    """
    if not items:
        return 0.0
    total = 0.0
    for item in items:
        q = item.reliability * item.relevance
        if item.self_authored:
            q *= 0.5
        total += q
    return round(total / len(items), 4)


def _clamp(value: float) -> float:
    return round(min(max(float(value), _FLOOR), _CEIL), 4)


def _days_between(start: str, end: str) -> Optional[int]:
    from datetime import date
    try:
        return (date.fromisoformat(end[:10])
                - date.fromisoformat(start[:10])).days
    except (TypeError, ValueError):
        return None


def summarise(before: Sequence[StrategicBelief],
              after: Sequence[StrategicBelief]) -> dict:
    """What actually moved this cycle, and in which direction.

    Reported separately from trade learning, because conflating them is how a
    quiet market got recorded as a quiet mind.
    """
    prior_by_id = {b.belief_id: b.posterior_probability for b in before}
    strengthened = weakened = unchanged_after_test = decayed = 0
    new = 0
    for belief in after:
        if belief.belief_id not in prior_by_id:
            new += 1
            continue
        was = prior_by_id[belief.belief_id]
        now = belief.posterior_probability
        last = belief.history[-1] if belief.history else None
        if last is not None and last.method == DECAY and now != was:
            decayed += 1
        elif now > was:
            strengthened += 1
        elif now < was:
            weakened += 1
        elif last is not None and last.at:
            unchanged_after_test += 1
    return {"beliefs_total": len(after), "new": new,
            "strengthened": strengthened, "weakened": weakened,
            "unchanged_after_test": unchanged_after_test,
            "decayed": decayed,
            "retired": sum(1 for b in after
                           if b.lifecycle_state == RETIRED),
            "belief_knowledge_gain": strengthened + weakened + new
                                     + unchanged_after_test}
