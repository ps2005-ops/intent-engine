"""Two demand figures that disagree, when neither is next to the other.

WHAT THE CHAIN ALREADY CATCHES
------------------------------
`demand_chain` compares ADJACENT states and marks a link CONTRADICTED when the
two ends moved in opposite directions. That is the right rule for the path it
models, and it leaves two gaps that the acceptance criteria for this node name
explicitly.

GAP ONE — POLARITY. The rule reads "both moved UP" as consistency. That holds
only if every state means more demand when it rises, and one does not:
CANCELLATIONS rising is committed demand leaving. Backlog up WITH cancellations
up is two figures moving the same way and disagreeing completely, and the chain
cannot say so because CANCELLATIONS is deliberately kept off the main path — it
is a leak out of the committed pool, not a step along it. Correct, and it means
cancellations are currently compared to nothing at all.

GAP TWO — DISTANCE. Bookings and revenue are four links apart. A company whose
new bookings are falling while recognised revenue rises is describing the most
familiar shape in enterprise software: revenue is the past arriving. The chain
sees BOOKINGS -> COMMITTED_DEMAND and three more steps, and in a corpus where
the middle states are unmeasured every one of those links is UNKNOWN. The
divergence is real, it is decision-relevant, and it is invisible.

WHY NOT JUST ADD MORE LINKS
---------------------------
Because a link asserts a causal step and these pairs are not steps. Bookings do
not become revenue by any route this engine has measured; the relationship is
an accounting one that holds over a lag nobody here has established. Modelling
the tension as a link would claim a mechanism. Modelling it as a TENSION claims
only what it is: two measured figures whose joint movement needs an
explanation, with the explanation left open.

NEVER FLATTENED
---------------
`summarise` reports tensions separately and refuses to produce an overall
demand verdict. There is no field here that says "demand strong". A reader
asking for one gets the tensions and their alternatives, which is the honest
answer and the useful one — the flattening is the failure this node exists to
prevent.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from . import demand_chain as DC

CONTRACT = "demand_tension.v1"


class TensionRejected(ValueError):
    """A tension asserted between states that do not disagree."""


# --- which way a rise points -------------------------------------------------
#
# Every state except one means MORE demand when it rises. Naming the exception
# in data rather than in a branch is what lets the comparison below stay one
# rule instead of a special case somebody deletes.
DEMAND_POSITIVE = "DEMAND_POSITIVE"
DEMAND_NEGATIVE = "DEMAND_NEGATIVE"

POLARITY = {state: DEMAND_POSITIVE for state in DC.STATES}
POLARITY[DC.CANCELLATIONS] = DEMAND_NEGATIVE

UP, DOWN, FLAT = "UP", "DOWN", "FLAT"


def demand_sign(state: str, direction: str) -> Optional[str]:
    """Which way this reading points for DEMAND, not for the figure.

    Returns None for FLAT and for anything unrecognised: a figure that did not
    move says nothing about direction, and refusing to guess is the whole
    reason this function exists rather than a `== UP` comparison at each site.
    """
    if direction not in (UP, DOWN):
        return None
    if POLARITY.get(state, DEMAND_POSITIVE) == DEMAND_NEGATIVE:
        return DOWN if direction == UP else UP
    return direction


# --- the pairs worth comparing even though they are not adjacent -------------
#
# Each carries the sentence a reader needs: what the disagreement would mean,
# the innocent explanation that fits it just as well, and the observation that
# would settle which. The alternative is not decoration — for every pair below
# there IS a benign reading, and a layer that reported only the alarming one
# would be the mirror image of the flattening this module prevents.
@dataclass(frozen=True)
class TensionRule:
    left: str
    right: str
    meaning: str
    alternative: str
    falsifier: str


RULES: Tuple[TensionRule, ...] = (
    TensionRule(
        left=DC.BACKLOG, right=DC.CANCELLATIONS,
        meaning="the committed pool is growing and leaking at the same time; "
                "the backlog figure alone reads as strength and is partly "
                "work that has already been withdrawn",
        alternative="the cancellations are concentrated in one contract or "
                    "one customer and say nothing about the rest of the pool",
        falsifier="the company states cancellations by customer or by "
                  "cohort, and they are concentrated"),
    TensionRule(
        left=DC.BOOKINGS, right=DC.REVENUE,
        meaning="revenue is the past arriving while new bookings fall; the "
                "revenue line will follow the bookings line after the "
                "recognition lag, and reporting revenue alone describes a "
                "quarter that has already ended",
        alternative="revenue mix shifted toward faster-recognising products, "
                    "so the two lines are measuring different things rather "
                    "than disagreeing",
        falsifier="the company states revenue by product or by recognition "
                  "profile and the mix explains the gap"),
    TensionRule(
        left=DC.ORDERS, right=DC.SHIPMENTS,
        meaning="orders are arriving faster than they can be delivered; the "
                "constraint is supply or capacity, and demand strength and "
                "revenue weakness are both true at once",
        alternative="shipments are timing-limited within the period and "
                    "recover in the next one, which is a calendar effect "
                    "rather than a constraint",
        falsifier="the company states a shipment or capacity constraint, or "
                  "the next period's shipments recover the shortfall"),
    TensionRule(
        left=DC.COMMITTED_DEMAND, right=DC.CANCELLATIONS,
        meaning="commitments and withdrawals are rising together, so the net "
                "position is unknown from either figure alone",
        alternative="the two figures cover different periods and the "
                    "cancellations relate to an older cohort",
        falsifier="the company states both figures for the same period"),
    TensionRule(
        left=DC.CUSTOMER_INTENT, right=DC.ORDERS,
        meaning="interest is not converting; pipeline and orders are moving "
                "in opposite directions and the gap is conversion",
        alternative="the pipeline is lengthening rather than failing, so the "
                    "orders lag rather than not arriving",
        falsifier="the company states cycle length or conversion rate"),
)


@dataclass(frozen=True)
class Tension:
    """Two measured figures that disagree, and what would settle it."""

    company_id: str
    left: str
    right: str
    left_direction: str
    right_direction: str
    meaning: str
    alternative: str
    falsifier: str
    evidence_ids: Tuple[str, ...] = ()

    def as_dict(self) -> dict:
        out = dataclasses.asdict(self)
        out.update(contract=CONTRACT, evidence_ids=list(self.evidence_ids))
        return out


def find(chain) -> Tuple[Tension, ...]:
    """Every tension between two MEASURED states of one company's chain.

    Both states have to be known. An unmeasured figure cannot disagree with
    anything, and inventing a tension from one measured figure and one absent
    one would be the same error as inferring demand from backlog — the thing
    `demand_chain.implies_demand` refuses to do.
    """
    readings = dict(getattr(chain, "readings", {}) or {})
    company = str(getattr(chain, "company_id", "") or "")
    out: List[Tension] = []
    for rule in RULES:
        left = readings.get(rule.left)
        right = readings.get(rule.right)
        if left is None or right is None:
            continue
        # NO `known` CHECK HERE, and its absence is deliberate. One was
        # written and a break proof found it redundant: `demand_chain.unknown`
        # always sets direction FLAT, and `demand_sign` returns None for FLAT,
        # so an unmeasured reading is already dropped one line below. Keeping
        # both would leave a guard that no input can reach — dead code with a
        # test naming it, which reads as coverage and is not. The property is
        # still enforced and still tested; what carries it is the direction.
        left_sign = demand_sign(rule.left, left.direction)
        right_sign = demand_sign(rule.right, right.direction)
        if left_sign is None or right_sign is None:
            continue
        if left_sign == right_sign:
            continue
        out.append(Tension(
            company_id=company, left=rule.left, right=rule.right,
            left_direction=left.direction, right_direction=right.direction,
            meaning=rule.meaning, alternative=rule.alternative,
            falsifier=rule.falsifier,
            evidence_ids=tuple(left.evidence_ids) + tuple(right.evidence_ids)))
    return tuple(out)


def summarise(chains: Sequence) -> dict:
    """Counts and the tensions themselves. NO overall demand verdict.

    There is deliberately no field here reading "demand strong" or a score
    that could stand in for one. Every figure this layer holds is one figure;
    the reason the tensions exist is that combining them into a verdict is
    exactly where the information is lost.
    """
    tensions = [t for chain in chains for t in find(chain)]
    by_pair: Dict[str, int] = {}
    for one in tensions:
        key = f"{one.left}/{one.right}"
        by_pair[key] = by_pair.get(key, 0) + 1
    return {
        "contract": CONTRACT,
        "tensions": len(tensions),
        "companies_with_a_tension": len({t.company_id for t in tensions}),
        "by_pair": by_pair,
        "rules_available": len(RULES),
        "found": [t.as_dict() for t in tensions[:10]],
        "every_tension_has_an_alternative": all(t.alternative
                                                for t in tensions),
        "note": ("two measured figures whose joint movement needs an "
                 "explanation. There is no overall demand verdict here and "
                 "there is not meant to be: a tension flattened into 'demand "
                 "strong' is the information going missing"),
    }
