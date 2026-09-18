"""What posture would explain the actions this company took?

THE SAME DEFECT, A THIRD TIME
-----------------------------
`hidden_state.py` is complete and careful. It holds a distribution over
postures, refuses an observation that names fewer than two states with
distinct likelihoods, and refuses to let an unmentioned rival be silently
eliminated. `learning_cycle.run` accepts `hidden_states=` and
`hidden_state_observations=` and folds them properly.

Production passes neither. `hidden_state` does not appear anywhere in
`steps.py`, so `companies_tracked` has read 0 since the subsystem was built,
and it was carried as a working component the whole time.

This is the third instance of one pattern: a correct module, a call site that
never supplies its inputs, and a metric honestly reporting zero that everyone
read as "nothing happened yet". The observations argument was the first, the
mechanism tests the second.

WHY THE LIKELIHOODS ARE COARSE AND STATED
-----------------------------------------
`observe` needs P(action | posture). Nothing in the corpus estimates that, and
inventing three-decimal likelihoods would be the same error as printing a
0.586 prior as founder confidence.

So the table below is ordinal and deliberately blunt: an action is TELLING,
NEUTRAL or UNLIKELY under a posture, mapped to 3.0 / 1.0 / 0.35. Those numbers
are not measurements and are not presented as any; they encode "this action
fits that posture better than this other one", which is the strongest claim
the evidence supports. Every unlisted posture keeps a neutral likelihood, so
a rival can only ever be argued down, never deleted.
"""
from __future__ import annotations

import collections
from typing import Dict, List, Optional, Sequence, Tuple

from . import belief_formation as BF
from . import hidden_state as HS
from . import micro_evidence as ME

BINDING_VERSION = "hidden_state_binding.v1"

TELLING = 3.0
NEUTRAL = 1.0
UNLIKELY = 0.35

#: What each observed action says about posture. Read as: under this posture,
#: is this action more or less likely than under an average posture?
#:
#: Every row names at least two postures pulling in different directions,
#: because `observe` refuses anything less -- an action that every posture
#: explains equally is not evidence about posture.
_LIKELIHOODS: Dict[str, Dict[str, float]] = {
    ME.LAYOFF: {
        HS.COST_CUTTING: TELLING,
        HS.CAPITAL_CONSTRAINED: TELLING,
        HS.EXPANDING: UNLIKELY,
        HS.CAPACITY_CONSTRAINED: UNLIKELY,
    },
    ME.HIRING: {
        HS.EXPANDING: TELLING,
        HS.CAPACITY_CONSTRAINED: TELLING,
        HS.COST_CUTTING: UNLIKELY,
    },
    ME.CAPEX_SIGNAL: {
        HS.EXPANDING: TELLING,
        HS.CAPACITY_CONSTRAINED: TELLING,
        HS.CAPITAL_CONSTRAINED: UNLIKELY,
        HS.COST_CUTTING: UNLIKELY,
    },
    ME.CAPITAL_RETURN: {
        # Money handed back is money not needed internally.
        HS.CAPITAL_CONSTRAINED: UNLIKELY,
        HS.EXPANDING: UNLIKELY,
        HS.WAITING: TELLING,
    },
    ME.PRICING_SIGNAL: {
        HS.PRICE_AGGRESSIVE: TELLING,
        HS.DEFENDING: TELLING,
        HS.GROWING: NEUTRAL,
    },
    ME.MA_ACTIVITY: {
        HS.PREPARING_ACQUISITION: TELLING,
        HS.CAPITAL_CONSTRAINED: UNLIKELY,
    },
    ME.REGULATORY_ACTION: {
        HS.REGULATORY_DEFENSIVE: TELLING,
        HS.EXPANDING: UNLIKELY,
    },
    ME.PRODUCT_LAUNCH: {
        HS.EXPERIMENTING: TELLING,
        HS.PLATFORM_EXPANDING: TELLING,
        HS.COST_CUTTING: UNLIKELY,
    },
    ME.PARTNERSHIP: {
        HS.PLATFORM_EXPANDING: TELLING,
        HS.DEFENDING: NEUTRAL,
        HS.COST_CUTTING: UNLIKELY,
    },
    ME.COMMITTED_DEMAND: {
        HS.GROWING: TELLING,
        HS.CAPACITY_CONSTRAINED: TELLING,
        HS.WAITING: UNLIKELY,
    },
    ME.COST_SHOCK: {
        # An imposed cost tells you about the environment, and only weakly
        # about the posture the company chose in response.
        HS.COST_CUTTING: NEUTRAL,
        HS.CAPITAL_CONSTRAINED: NEUTRAL,
        HS.EXPANDING: UNLIKELY,
    },
}

#: Postures the distribution ranges over. Kept wide on purpose: a narrow set
#: makes the leading reading look decisive because its rivals were never
#: admitted rather than because the evidence argued them down.
TRACKED_STATES: Tuple[str, ...] = (
    HS.GROWING, HS.DEFENDING, HS.EXPANDING, HS.COST_CUTTING,
    HS.CAPITAL_CONSTRAINED, HS.PREPARING_ACQUISITION, HS.PRICE_AGGRESSIVE,
    HS.CAPACITY_CONSTRAINED, HS.WAITING, HS.EXPERIMENTING,
    HS.REGULATORY_DEFENSIVE, HS.PLATFORM_EXPANDING,
)


def likelihoods_for(item: ME.MicroEvidence) -> Optional[Dict[str, float]]:
    """What this one action says about posture, or None if nothing."""
    table = _LIKELIHOODS.get(item.evidence_type)
    if not table:
        return None
    # Directional evidence sharpens one row: a price move down is a different
    # posture signal from a price move up, and the table cannot know which
    # arrived without reading the sentence.
    if item.evidence_type == ME.PRICING_SIGNAL:
        direction = BF.direction_of(item.fact)
        table = dict(table)
        if direction == "DOWN":
            table[HS.PRICE_AGGRESSIVE] = TELLING
            table[HS.GROWING] = UNLIKELY
        elif direction == "UP":
            table[HS.PRICE_AGGRESSIVE] = UNLIKELY
            table[HS.DEFENDING] = UNLIKELY
            table[HS.GROWING] = TELLING
    return table


def bind(evidence: Sequence[ME.MicroEvidence], *, as_of: str,
         existing: Sequence[HS.HiddenStateBelief] = ()
         ) -> Tuple[Tuple[HS.HiddenStateBelief, ...], List[dict],
                    Dict[str, int]]:
    """Posture distributions and the observations that should move them.

    Returns (starting distributions, observations, why-not counts) in exactly
    the shape `learning_cycle.run` already accepts — the point is to fill
    parameters that have always existed, not to add new ones.
    """
    refused: Dict[str, int] = collections.Counter()
    by_subject: Dict[str, List[ME.MicroEvidence]] = collections.defaultdict(list)
    for item in evidence:
        subject = (item.subject_company or "").strip().lower()
        if not subject:
            refused["no_subject"] += 1
            continue
        if likelihoods_for(item) is None:
            refused["action_says_nothing_about_posture"] += 1
            continue
        by_subject[subject].append(item)

    held = {b.subject: b for b in existing}
    starting: List[HS.HiddenStateBelief] = []
    observations: List[dict] = []

    for subject, items in sorted(by_subject.items()):
        belief = held.get(subject) or HS.uniform(
            subject, at=as_of, states=TRACKED_STATES)
        starting.append(belief)
        for item in sorted(items, key=lambda e: (e.observed_at,
                                                 e.evidence_id)):
            observations.append({
                "subject": subject,
                "action": f"{item.evidence_type}: {item.fact[:140]}",
                "likelihoods": likelihoods_for(item),
                "at": item.observed_at[:10],
                "evidence_ids": (item.evidence_id,),
            })
    return tuple(starting), observations, dict(refused)


def summarise(starting: Sequence[HS.HiddenStateBelief],
              observations: Sequence[dict],
              refused: Dict[str, int]) -> dict:
    return {
        "contract": BINDING_VERSION,
        "companies_with_posture_evidence": len(starting),
        "observations_bound": len(observations),
        "states_tracked": list(TRACKED_STATES),
        "refused": dict(sorted(refused.items())),
        "note": ("likelihoods are ordinal (telling / neutral / unlikely), not "
                 "estimated frequencies; no posture is ever eliminated, only "
                 "argued down"),
    }
