"""What to pay attention to next, and why it is worth the wait.

THE QUESTION
------------
An engine that ingests everything available learns slowly and expensively. The
useful question is not "what can we collect" but "which single upcoming
observation would most change what we believe" — and that is answerable,
because uncertainty is measurable and decisions have stakes.

PRIORITY = INFORMATION GAIN × DECISION VALUE, DISCOUNTED BY COST AND DELAY
--------------------------------------------------------------------------
All four terms matter and each one alone misleads:

  - gain alone chases trivia the engine happens to be unsure about;
  - decision value alone re-reads things already settled;
  - ignoring cost recommends the unobtainable;
  - ignoring delay recommends an observation that lands after the decision.

The last is the one people forget. A perfectly discriminating observation
scheduled for after the deadline has an expected value of zero, and
`expected_date` past the decision horizon drives the priority to exactly that.

ENTROPY IS THE UNCERTAINTY MEASURE, WITH ITS LIMIT STATED
---------------------------------------------------------
A belief at 0.5 has maximum entropy and the most room to move; one at 0.95 has
little. This correctly ranks a genuinely open question above a settled one.
What it does NOT capture is that a settled belief can be settled wrongly, so
`InformationPriority` carries a `limitation` field and the summary states the
assumption rather than burying it.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from . import beliefs as B

CONTRACT_VERSION = "information_priority.v1"

# Observation classes with their typical cost and availability character.
# Cost is effort/latency, not money — nothing here is purchased.
OBSERVATION_KINDS = {
    "EARNINGS_RELEASE": {"cost": 0.1, "scheduled": True},
    "GUIDANCE": {"cost": 0.1, "scheduled": True},
    "MACRO_REPORT": {"cost": 0.05, "scheduled": True},
    "COMPETITOR_PRICE": {"cost": 0.4, "scheduled": False},
    "CUSTOMER_COMMENT": {"cost": 0.5, "scheduled": False},
    "SUPPLIER_REPORT": {"cost": 0.5, "scheduled": False},
    "CONTRACT_DECISION": {"cost": 0.3, "scheduled": False},
    "REGULATORY_RULING": {"cost": 0.2, "scheduled": True},
    "OPTIONS_POSITIONING": {"cost": 0.3, "scheduled": False},
    "INVENTORY_RELEASE": {"cost": 0.3, "scheduled": True},
    "ANNUAL_FILING": {"cost": 0.2, "scheduled": True},
}


@dataclass(frozen=True)
class InformationPriority:
    """One candidate observation, ranked by what resolving it would buy."""
    hypothesis_id: str
    subject: str
    current_entropy: float
    decision_value: float
    candidate_observation: str
    observation_kind: str
    expected_information_gain: float
    observation_cost: float
    expected_date: str
    priority: float
    limitation: str = ""
    falsifies: str = ""

    def as_dict(self) -> dict:
        return {"hypothesis_id": self.hypothesis_id, "subject": self.subject,
                "current_entropy": self.current_entropy,
                "decision_value": self.decision_value,
                "candidate_observation": self.candidate_observation,
                "observation_kind": self.observation_kind,
                "expected_information_gain":
                    self.expected_information_gain,
                "observation_cost": self.observation_cost,
                "expected_date": self.expected_date,
                "priority": self.priority, "limitation": self.limitation,
                "falsifies": self.falsifies}


def expected_information_gain(prior: float, *,
                              likelihood_if_true: float = 0.8,
                              likelihood_if_false: float = 0.3) -> float:
    """Expected entropy reduction from seeing this observation, either way.

    Averaged over both possible results weighted by how likely each is. That
    is what makes this a measure of the QUESTION rather than of the answer
    somebody hopes for: an observation only scores well when it discriminates
    whichever way it lands.
    """
    prior = min(max(prior, 1e-6), 1 - 1e-6)
    lt = min(max(likelihood_if_true, 1e-6), 1 - 1e-6)
    lf = min(max(likelihood_if_false, 1e-6), 1 - 1e-6)

    p_obs = prior * lt + (1 - prior) * lf
    p_no = prior * (1 - lt) + (1 - prior) * (1 - lf)
    if p_obs <= 0 or p_no <= 0:
        return 0.0

    post_obs = (prior * lt) / p_obs
    post_no = (prior * (1 - lt)) / p_no
    expected_after = p_obs * _h(post_obs) + p_no * _h(post_no)
    return round(max(_h(prior) - expected_after, 0.0), 6)


def _h(p: float) -> float:
    if p <= 0 or p >= 1:
        return 0.0
    return -(p * math.log2(p) + (1 - p) * math.log2(1 - p))


def prioritise(belief: B.StrategicBelief, *, candidate_observation: str,
               observation_kind: str, expected_date: str, as_of: str,
               decision_value: float = 0.5,
               decision_deadline: str = "",
               likelihood_if_true: float = 0.8,
               likelihood_if_false: float = 0.3,
               falsifies: str = "") -> InformationPriority:
    """Score one candidate observation for one belief.

    An observation expected AFTER the decision deadline scores zero, however
    discriminating it is. This is the term that is easiest to leave out and
    the one that most often makes a research agenda useless in practice.
    """
    if observation_kind not in OBSERVATION_KINDS:
        raise ValueError(f"unknown observation kind {observation_kind!r}")
    spec = OBSERVATION_KINDS[observation_kind]
    cost = float(spec["cost"])

    gain = expected_information_gain(
        belief.posterior_probability,
        likelihood_if_true=likelihood_if_true,
        likelihood_if_false=likelihood_if_false)

    limitation = ""
    if decision_deadline and expected_date[:10] > decision_deadline[:10]:
        priority = 0.0
        limitation = (f"expected {expected_date[:10]}, after the "
                      f"{decision_deadline[:10]} decision deadline; it "
                      f"cannot inform the decision it would answer")
    else:
        delay_days = _days(as_of, expected_date)
        # Gentle discount: a month's wait costs about 9% of the value.
        delay_penalty = 1.0 / (1.0 + max(delay_days or 0, 0) / 300.0)
        priority = round(gain * decision_value * delay_penalty
                         * (1.0 - cost * 0.5), 6)
        if not spec["scheduled"]:
            limitation = ("this observation is not on a published schedule, "
                          "so the expected date is an estimate")

    return InformationPriority(
        hypothesis_id=belief.belief_id, subject=belief.subject,
        current_entropy=belief.entropy, decision_value=decision_value,
        candidate_observation=candidate_observation,
        observation_kind=observation_kind,
        expected_information_gain=gain, observation_cost=cost,
        expected_date=expected_date[:10], priority=priority,
        limitation=limitation, falsifies=falsifies)


def agenda(priorities: Sequence[InformationPriority], *,
           limit: int = 10) -> dict:
    """The ranked research agenda: what the engine should watch next."""
    ranked = sorted(priorities, key=lambda p: p.priority, reverse=True)
    live = [p for p in ranked if p.priority > 0]
    return {
        "candidates": len(priorities),
        "actionable": len(live),
        "top": [p.as_dict() for p in ranked[:limit]],
        "highest_value_next_observation": live[0].as_dict() if live else None,
        "assumption": ("Priority ranks by how much a belief could move, so a "
                       "confidently-held wrong belief ranks low. Entropy "
                       "measures indecision, not correctness."),
    }


def _days(start: str, end: str) -> Optional[int]:
    from datetime import date
    try:
        return (date.fromisoformat(end[:10])
                - date.fromisoformat(start[:10])).days
    except (TypeError, ValueError):
        return None
