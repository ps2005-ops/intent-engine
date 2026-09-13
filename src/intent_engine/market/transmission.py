"""Where a measured economy meets a specific company, and stays a hypothesis.

WHY THIS EXISTS
---------------
`macro_state` knows the cost of money rose. `company_exposure` knows which
companies have said they care. Neither, alone, is a claim about anything: an
economy with no exposure is a story, and an exposure with no economy is a
sensitivity to nothing in particular. This is the object that joins them —
and the object that refuses to let the join become an assertion.

A TRANSMISSION IS A HYPOTHESIS, PERMANENTLY
-------------------------------------------
The temptation is to treat the join as a conclusion: rates rose, this company
said it is rate-sensitive, therefore its costs are rising. That inference is
usually reasonable and it is not an observation. The company may have hedged,
refinanced early, or be sitting on cash. So a transmission is born
HYPOTHESIZED and can only be moved by an outcome that was preregistered
against it.

WHAT EVERY LINK MUST CARRY
--------------------------
    mechanism      the stated route, not a correlation
    direction      which way the effect should run
    lag            when it should show up, so "not yet" is distinguishable
                   from "not happening"
    falsifier      the observation that would kill it
    alternative    the competing explanation that would also fit
    standing       and how it was earned

A link without a falsifier is not a hypothesis, it is a belief, and this
module refuses to construct one.
"""
from __future__ import annotations

import dataclasses
import hashlib
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from . import company_exposure as CX
from . import macro_state as MS

CONTRACT = "transmission.v1"

# --- standing ---------------------------------------------------------------
HYPOTHESIZED = "HYPOTHESIZED"    # both ends real, nothing tested
SUPPORTED = "SUPPORTED"          # a preregistered outcome came in as expected
CONTRADICTED = "CONTRADICTED"    # a preregistered outcome went the other way
UNTESTABLE = "UNTESTABLE"        # no observation could settle it

STANDINGS = (HYPOTHESIZED, SUPPORTED, CONTRADICTED, UNTESTABLE)

# --- direction --------------------------------------------------------------
RAISES = "RAISES"
LOWERS = "LOWERS"
AMBIGUOUS = "AMBIGUOUS"
DIRECTIONS = (RAISES, LOWERS, AMBIGUOUS)


class TransmissionRejected(ValueError):
    """A transmission that would assert more than its two ends support."""


@dataclass(frozen=True)
class Transmission:
    """One economic condition, one company, one stated route between them."""

    company_id: str
    state_kind: str
    dimension: str
    mechanism: str
    direction: str
    lag_days: int
    falsifier: str
    alternative_explanation: str
    standing: str = HYPOTHESIZED
    #: WHICH ECONOMY moved. An `EconomicState` is keyed `(area, state_kind)`,
    #: so CA:MARKET_RATE and US:MARKET_RATE are two states; dropping the area
    #: here gave both the same `transmission_id` and, downstream, the same
    #: thesis identity.
    area: str = ""
    #: Both ends' provenance, so a rendered sentence walks back to a series
    #: and to the company's own words.
    macro_observation_id: str = ""
    exposure_evidence_ids: Tuple[str, ...] = ()
    exposure_standing: str = ""
    as_of: str = ""
    note: str = ""

    def __post_init__(self) -> None:
        if self.direction not in DIRECTIONS:
            raise TransmissionRejected(f"unknown direction {self.direction!r}")
        if self.standing not in STANDINGS:
            raise TransmissionRejected(f"unknown standing {self.standing!r}")
        if not self.mechanism.strip():
            raise TransmissionRejected(
                "a transmission needs a stated mechanism; without one it is a "
                "correlation with a company's name attached")
        if not self.falsifier.strip():
            raise TransmissionRejected(
                "a transmission needs a falsifier: a link nothing could "
                "disprove is a belief, not a hypothesis")
        if self.lag_days < 0:
            raise TransmissionRejected(
                "a negative lag would let an effect precede its cause")

    @property
    def transmission_id(self) -> str:
        raw = "|".join((self.company_id, self.area, self.state_kind,
                        self.dimension, self.mechanism))
        return "tx_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    @property
    def tested(self) -> bool:
        return self.standing in (SUPPORTED, CONTRADICTED)

    def due_at(self, from_date: str) -> str:
        """When an effect should be visible, so silence becomes readable.

        Without a due date "nothing has happened" is indistinguishable from
        "it has not happened YET", and a transmission that is never due is
        never wrong.
        """
        import datetime
        day = datetime.date.fromisoformat(str(from_date)[:10])
        return (day + datetime.timedelta(days=self.lag_days)).isoformat()

    def as_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d.update(contract=CONTRACT, transmission_id=self.transmission_id,
                 tested=self.tested)
        return d


#: The stated route for each exposure dimension. Written once, here, so a
#: mechanism cannot be invented at the call site to fit a company — which is
#: how a model starts explaining everything.
_MECHANISM: Dict[str, Tuple[str, str, int, str, str]] = {
    CX.RATE: (
        "a higher cost of borrowing raises the interest expense on floating "
        "or maturing debt",
        RAISES, 90,
        "interest expense is flat or falls while the rate rises",
        "the debt was fixed, hedged, or repaid before the rate moved"),
    CX.CREDIT: (
        "tighter credit conditions raise the cost or reduce the availability "
        "of refinancing",
        RAISES, 180,
        "the company refinances at or below its previous cost",
        "the company funded itself from cash and never entered the market"),
    CX.FX: (
        "a currency move changes the reported value of revenue earned abroad",
        AMBIGUOUS, 90,
        "reported revenue moves against the currency move",
        "the exposure was hedged, or the mix of currencies offset itself"),
    CX.COMMODITY: (
        "an input price change moves cost of goods before it moves price",
        RAISES, 90,
        "gross margin is stable through an input price move",
        "the contract was struck in advance, or the cost was passed through"),
    CX.ENERGY: (
        "an energy price change moves operating cost for an energy-intensive "
        "process",
        RAISES, 90,
        "operating cost is flat through an energy price move",
        "energy was hedged, or is too small a share of cost to show"),
    CX.LABOR: (
        "wage pressure raises operating cost where headcount is the input",
        RAISES, 180,
        "operating cost per unit falls while wages rise",
        "headcount fell, or productivity absorbed the increase"),
    CX.SUPPLY: (
        "a supply constraint caps the units that can be produced and sold",
        LOWERS, 90,
        "volumes rise through a stated supply constraint",
        "inventory absorbed it, or the constraint was resolved quietly"),
    CX.CUSTOMER_CONCENTRATION: (
        "demand conditions among a concentrated customer base move orders "
        "more than they would a diversified one",
        AMBIGUOUS, 180,
        "orders are stable while the named customers' demand moves",
        "the customers' own demand diverged from the aggregate measure"),
    CX.CAPITAL_INTENSITY: (
        "a higher cost of capital raises the hurdle a capital programme must "
        "clear, so planned spending is deferred",
        LOWERS, 270,
        "capital spending is raised or held through a rising cost of capital",
        "the programme was already committed, or is funded from operating "
        "cash and insensitive to the rate"),
    CX.REGULATORY: (
        "a fiscal or regulatory change alters the cost of operating in a "
        "named jurisdiction",
        AMBIGUOUS, 270,
        "operating cost in the jurisdiction is unchanged after the measure "
        "takes effect",
        "the change was anticipated and already in the cost base"),
}


def propose(*, exposure: CX.Exposure, state: MS.EconomicState,
            as_of: str = "") -> Optional[Transmission]:
    """The hypothesis these two ends support, or None.

    Returns None rather than a weak transmission when either end is
    unestablished. A transmission built on an UNKNOWN exposure is a sector
    prior, and one built on a HYPOTHESIZED economy is an opinion about an
    opinion — both would render as confidently as a real one.
    """
    if not CX.conditions_transmission(exposure, state):
        return None
    route = _MECHANISM.get(exposure.dimension)
    if route is None:
        return None
    mechanism, direction, lag, falsifier, alternative = route
    return Transmission(
        company_id=exposure.company_id, state_kind=state.state_kind,
        area=str(getattr(state, "area", "") or ""),
        dimension=exposure.dimension, mechanism=mechanism,
        direction=direction, lag_days=lag, falsifier=falsifier,
        alternative_explanation=alternative, standing=HYPOTHESIZED,
        macro_observation_id=(state.observation.observation_id
                              if state.observation else ""),
        exposure_evidence_ids=tuple(exposure.evidence_ids),
        exposure_standing=exposure.standing, as_of=as_of,
        note=("the economy moved and this company has said it is sensitive; "
              "whether the effect arrives is not yet known"))


def propose_all(profiles: Dict[str, Dict[str, CX.Exposure]],
                states: Sequence[MS.EconomicState], *,
                as_of: str = "") -> List[Transmission]:
    """Every hypothesis the current evidence supports, across companies."""
    out: List[Transmission] = []
    for company_profile in profiles.values():
        for exposure in company_profile.values():
            for state in states:
                proposed = propose(exposure=exposure, state=state,
                                   as_of=as_of)
                if proposed is not None:
                    out.append(proposed)
    return out


def summarise(transmissions: Sequence[Transmission]) -> dict:
    """Counted by standing, and never collapsed into a confidence.

    A count of hypotheses is not evidence of anything: proposing a thousand
    transmissions would look like a thousand insights and would mean the
    exposure model had started guessing.
    """
    by_standing: Dict[str, int] = {}
    by_dimension: Dict[str, int] = {}
    for t in transmissions:
        by_standing[t.standing] = by_standing.get(t.standing, 0) + 1
        by_dimension[t.dimension] = by_dimension.get(t.dimension, 0) + 1
    return {
        "contract": CONTRACT,
        "transmissions": len(transmissions),
        "by_standing": by_standing,
        "by_dimension": by_dimension,
        "companies": len({t.company_id for t in transmissions}),
        "tested": sum(1 for t in transmissions if t.tested),
        "every_one_falsifiable": all(t.falsifier.strip()
                                     for t in transmissions),
        "note": ("all HYPOTHESIZED until a preregistered outcome moves one; "
                 "a count of hypotheses is not a count of findings"),
    }
