"""The economy, as a state this engine can hold a dated opinion about.

WHY THIS EXISTS
---------------
The economic chain already models the transmission from the economy into a
company: MACRO_STATE -> CUSTOMER_STATE -> COMPANY_DEMAND -> ORDERS -> MARGIN
-> GUIDANCE -> OUTCOME. Measured against the live ledger it reports

    known 4, unknown 3, links {UNKNOWN: 4, HYPOTHESIZED: 2}

and the three unknown nodes start at the top. Every company-side node is
KNOWN and MACRO_STATE is not, so no link can ever reach SUPPORTED: the engine
knows a great deal about companies and nothing at all about the economy they
sit in. That is the V4 bottleneck, and this module is the missing anchor.

WHAT IT REFUSES TO DO
--------------------
A macro statistic is not a conclusion about a company. "The policy rate rose"
does not mean "demand will fall" — it opens a TRANSMISSION HYPOTHESIS that has
to be conditioned on a company's exposure and then tested. So this module
carries no `implies`, no `affects`, and no company field. It can say what the
economy did. It cannot say what that meant for anyone, and `consequence_of`
raises rather than returning a plausible sentence.

THREE TIMES, NEVER CONFLATED
----------------------------
This project has repeatedly collapsed observation time into occurrence time,
and the acceptance of a macro series is where that error is most tempting,
because a series has a THIRD time nobody thinks about:

    reference_period   the span the number DESCRIBES  (June 2026)
    published_at       when the agency released it    (2026-07-15)
    retrieved_at       when we fetched it             (2026-08-08)

A June figure published in July and read in August is one observation with
three dates, and using the wrong one silently invents a month of foresight.
`as_known_at` exists so a decision can be scored against the vintage that was
actually available when it was made — see `REVISIONS` below.

REVISIONS APPEND
----------------
Statistical agencies revise. A revision is a NEW observation of the same
reference period, not a correction of the old one: "we now think Q2 grew 1.4%"
is a different fact from "we thought Q2 grew 2.1%", and overwriting the first
destroys the only record of what the engine could have known. So revisions are
appended with `supersedes`, exactly as counterfactual adjudications are.
"""
from __future__ import annotations

import dataclasses
import hashlib
from dataclasses import dataclass, field
from typing import Dict, Optional, Sequence, Tuple

CONTRACT = "macro_state.v1"

# --- what kind of economic condition is being described --------------------
#
# Deliberately short. A vocabulary is added to when a real transmission needs
# it, never because the list looks incomplete: an unused state kind is an
# invitation to populate it with something plausible.
GROWTH = "GROWTH"
INFLATION = "INFLATION"
POLICY_RATE = "POLICY_RATE"
MARKET_RATE = "MARKET_RATE"
CREDIT_CONDITIONS = "CREDIT_CONDITIONS"
EMPLOYMENT = "EMPLOYMENT"
WAGES = "WAGES"
CONSUMER_DEMAND = "CONSUMER_DEMAND"
BUSINESS_INVESTMENT = "BUSINESS_INVESTMENT"
INDUSTRIAL_PRODUCTION = "INDUSTRIAL_PRODUCTION"
INVENTORY = "INVENTORY"
COMMODITY_PRICE = "COMMODITY_PRICE"
ENERGY_PRICE = "ENERGY_PRICE"
CURRENCY = "CURRENCY"
FISCAL = "FISCAL"
TRADE = "TRADE"
HOUSING = "HOUSING"

STATE_KINDS = (GROWTH, INFLATION, POLICY_RATE, MARKET_RATE, CREDIT_CONDITIONS,
               EMPLOYMENT, WAGES, CONSUMER_DEMAND, BUSINESS_INVESTMENT,
               INDUSTRIAL_PRODUCTION, INVENTORY, COMMODITY_PRICE,
               ENERGY_PRICE, CURRENCY, FISCAL, TRADE, HOUSING)

# --- how well the engine actually knows it ---------------------------------
OBSERVED = "OBSERVED"          # a named series published a figure
INFERRED = "INFERRED"          # derived from observed figures by stated rule
HYPOTHESIZED = "HYPOTHESIZED"  # asserted by a source, not measured by one
UNKNOWN = "UNKNOWN"            # nothing measures this

STANDINGS = (OBSERVED, INFERRED, HYPOTHESIZED, UNKNOWN)

#: Only these may anchor a transmission chain. A HYPOTHESIZED macro state is
#: somebody's opinion about the economy, and a chain resting on it is a chain
#: resting on an opinion — it may be built, but it may not be called supported.
ANCHORING = frozenset({OBSERVED, INFERRED})

# --- what the number says ---------------------------------------------------
#
# LEVEL and CHANGE are different economic facts and the engine has confused
# them before. "Inflation is 3%" and "inflation fell to 3%" support opposite
# readings, and a series that only carries the level cannot express the second.
LEVEL = "LEVEL"
CHANGE = "CHANGE"
MEASURES = (LEVEL, CHANGE)

UP = "UP"
DOWN = "DOWN"
FLAT = "FLAT"
DIRECTIONS = (UP, DOWN, FLAT)

# --- where the publication date came from ----------------------------------
#
# Most statistical APIs give the period a figure describes and NOT the day it
# was released. That leaves a choice, and both easy answers are wrong: an
# empty publication date makes the figure unusable at any date, and using the
# record date claims the engine knew a month's figure on the last day of that
# month.
#
# So an assumed date is allowed, and it must err LATE. Assuming publication is
# later than it really was can only make the engine look like it knew LESS
# than it did, which is the safe direction — the failure this guards against
# is manufactured foresight, and a conservative lag cannot manufacture any.
PUBLISHER = "PUBLISHER"        # the source stated the release date
ASSUMED_LAG = "ASSUMED_LAG"    # derived from the period end, deliberately late
PUBLICATION_BASES = (PUBLISHER, ASSUMED_LAG)


class MacroRejected(ValueError):
    """A macro observation that would assert more than it measured."""


class CausalOverreach(MacroRejected):
    """Raised when a caller asks a statistic what it means for a company."""


@dataclass(frozen=True)
class MacroObservation:
    """One dated figure about one economic condition.

    No company field, deliberately. The moment a macro observation knows which
    company it is "about", somebody will read it as a claim about that company
    — and a national CPI print is not a fact about anyone's margins.
    """

    state_kind: str
    series_id: str          # the publisher's identifier, e.g. "DGS10"
    label: str              # what a person would call it
    value: float
    unit: str
    measure: str = LEVEL
    standing: str = OBSERVED

    #: The span the figure DESCRIBES. Never the day it was read.
    reference_period: str = ""
    #: When the publisher released it. A figure cannot inform a decision made
    #: before this date, whatever its reference period says.
    published_at: str = ""
    #: When this engine fetched it. Provenance only; never an economic date.
    retrieved_at: str = ""

    #: How `published_at` was arrived at. An ASSUMED_LAG date is an assumption
    #: the engine made, not a fact the publisher stated, and it is carried
    #: explicitly so no reader mistakes one for the other.
    publication_basis: str = PUBLISHER

    source: str = ""
    #: The observation this one revises, if any. Set by `revise`.
    supersedes: str = ""
    note: str = ""

    def __post_init__(self) -> None:
        if self.state_kind not in STATE_KINDS:
            raise MacroRejected(f"unknown state kind {self.state_kind!r}")
        if self.standing not in STANDINGS:
            raise MacroRejected(f"unknown standing {self.standing!r}")
        if self.measure not in MEASURES:
            raise MacroRejected(f"unknown measure {self.measure!r}")
        if self.publication_basis not in PUBLICATION_BASES:
            raise MacroRejected(
                f"unknown publication basis {self.publication_basis!r}")
        if (self.publication_basis == ASSUMED_LAG and self.published_at
                and self.published_at[:10] <= self.reference_period[:10]):
            raise MacroRejected(
                "an assumed publication date must fall AFTER the period it "
                "describes; assuming a figure was available on the last day "
                "of the period it measures is the foresight this field "
                "exists to prevent")
        if not self.series_id:
            raise MacroRejected("a macro observation needs its series id: "
                                "without one it cannot be revised, compared "
                                "to its own history, or traced to a publisher")
        if not self.reference_period:
            raise MacroRejected(
                "a macro observation needs the period it describes; falling "
                "back to the retrieval date is how a June figure becomes an "
                "August one")
        if self.published_at and self.reference_period[:10] > \
                self.published_at[:10]:
            raise MacroRejected(
                f"reference period {self.reference_period} is after "
                f"publication {self.published_at}: a figure cannot describe a "
                "period that had not finished when it was released")

    @property
    def observation_id(self) -> str:
        raw = "|".join((self.series_id, self.reference_period,
                        self.published_at, f"{self.value!r}", self.measure))
        return "macro_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    @property
    def anchors(self) -> bool:
        """Whether a transmission chain may rest on this."""
        return self.standing in ANCHORING

    def known_at(self, when: str) -> bool:
        """Could the engine have had this figure on `when`?

        Publication, not reference period. A Q2 figure released in August was
        not available in July, and scoring a July decision against it is the
        cleanest way to manufacture foresight the engine never had.
        """
        if not self.published_at:
            return False
        return self.published_at[:10] <= str(when)[:10]

    def as_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d.update(contract=CONTRACT, observation_id=self.observation_id,
                 anchors=self.anchors)
        return d


_FIELDS = tuple(f.name for f in dataclasses.fields(MacroObservation))


def from_dict(row: dict) -> MacroObservation:
    """Rehydrate a stored figure.

    Ignores the keys `as_dict` adds back (`contract`, `observation_id`,
    `anchors`) and the ledger's own envelope, so a row survives a round trip
    without the derived fields being mistaken for stored ones — a recomputed
    id that disagreed with the stored one would silently split one figure into
    two.
    """
    return MacroObservation(**{k: row[k] for k in _FIELDS if k in row})


def revise(previous: MacroObservation, *, value: float, published_at: str,
           retrieved_at: str = "", note: str = "") -> MacroObservation:
    """A revised figure for the same reference period.

    Appends rather than replaces. "We now think Q2 grew 1.4%" and "we thought
    Q2 grew 2.1%" are two facts, and only keeping the second destroys the
    record of what the engine could have believed at the time.
    """
    if published_at[:10] < (previous.published_at or "")[:10]:
        raise MacroRejected(
            "a revision cannot predate the figure it revises")
    return dataclasses.replace(
        previous, value=value, published_at=published_at,
        retrieved_at=retrieved_at or previous.retrieved_at,
        supersedes=previous.observation_id,
        note=note or "revision")


def as_known_at(observations: Sequence[MacroObservation], when: str
                ) -> Tuple[MacroObservation, ...]:
    """The vintage that was actually available on `when`.

    THE LEAK THIS CLOSES. Revisions arrive months later, so the current value
    of a series is not what the engine knew when it made a call. Evaluating a
    past decision against today's revised figure grades it on information that
    did not exist — and it flatters the engine every time, because revisions
    move toward the truth. For each series and reference period this returns
    the LATEST figure published on or before `when`, and nothing else.
    """
    latest: Dict[Tuple[str, str], MacroObservation] = {}
    for obs in observations:
        if not obs.known_at(when):
            continue
        key = (obs.series_id, obs.reference_period)
        held = latest.get(key)
        if held is None or obs.published_at[:10] >= held.published_at[:10]:
            latest[key] = obs
    return tuple(sorted(latest.values(),
                        key=lambda o: (o.series_id, o.reference_period)))


def direction(current: MacroObservation,
              previous: Optional[MacroObservation]) -> str:
    """Which way the condition moved, or FLAT when it did not move.

    Refuses to compare across series or across measures: the difference
    between a level and a change is not itself a direction, and two different
    series are two different questions.
    """
    if previous is None:
        return FLAT
    if previous.series_id != current.series_id:
        raise MacroRejected(
            f"cannot difference {previous.series_id} against "
            f"{current.series_id}: they measure different things")
    if previous.measure != current.measure:
        raise MacroRejected("cannot difference a level against a change")
    if current.value > previous.value:
        return UP
    if current.value < previous.value:
        return DOWN
    return FLAT


@dataclass(frozen=True)
class EconomicState:
    """What the engine currently holds about one condition, and how firmly."""

    state_kind: str
    standing: str
    observation: Optional[MacroObservation] = None
    moved: str = FLAT
    prior: Optional[MacroObservation] = None
    reason: str = ""

    @property
    def known(self) -> bool:
        return self.standing != UNKNOWN

    @property
    def anchors(self) -> bool:
        return self.standing in ANCHORING

    def as_dict(self) -> dict:
        return {"contract": CONTRACT, "state_kind": self.state_kind,
                "standing": self.standing, "moved": self.moved,
                "known": self.known, "anchors": self.anchors,
                "reason": self.reason,
                "observation": (self.observation.as_dict()
                                if self.observation else None),
                "prior_observation_id": (self.prior.observation_id
                                         if self.prior else "")}


def unknown(state_kind: str, reason: str = "") -> EconomicState:
    """An honest absence. Not a zero, and not a neutral reading.

    UNKNOWN must never be rendered as FLAT or as 'no change': "we did not
    measure this" and "this did not move" support completely different
    decisions, and collapsing them is how an unmeasured economy reads as a
    calm one.
    """
    return EconomicState(
        state_kind=state_kind, standing=UNKNOWN,
        reason=reason or "no series in evidence measures this condition")


def state_of(state_kind: str, observations: Sequence[MacroObservation], *,
             as_of: str) -> EconomicState:
    """The engine's dated reading of one condition.

    Vintage-correct by construction: it reads only what was published on or
    before `as_of`, so a state built for a past date cannot see a revision
    that had not happened yet.
    """
    if state_kind not in STATE_KINDS:
        raise MacroRejected(f"unknown state kind {state_kind!r}")
    mine = [o for o in as_known_at(observations, as_of)
            if o.state_kind == state_kind]
    if not mine:
        return unknown(state_kind)
    # Newest reference period wins; a longer series is not a better one.
    mine.sort(key=lambda o: (o.reference_period, o.published_at))
    current = mine[-1]
    earlier = [o for o in mine[:-1] if o.series_id == current.series_id]
    prior = earlier[-1] if earlier else None
    return EconomicState(
        state_kind=state_kind, standing=current.standing,
        observation=current, prior=prior,
        moved=direction(current, prior),
        reason=(f"{current.label} {current.value}{current.unit} for "
                f"{current.reference_period}, published "
                f"{current.published_at or 'undated'}"))


def consequence_of(state: EconomicState, *_args, **_kwargs):
    """Deliberately not implemented, and deliberately present.

    Every reader of this module eventually wants `consequence_of(rates_up,
    company)` to return a sentence, and a plausible one is always available.
    That is the single most dangerous function this file could contain: it
    would turn a national statistic into a claim about a specific company
    without touching that company's exposure or testing anything.

    The economy does not have consequences on its own. A transmission does,
    and a transmission needs an exposure, a mechanism, a lag and a falsifier —
    all of which live in the causal layer, not here. Raising is the contract.
    """
    raise CausalOverreach(
        f"{state.state_kind} is a measured condition, not a conclusion about "
        "a company; build a transmission hypothesis with an exposure, a "
        "mechanism and a falsifier instead")


def summarise(states: Sequence[EconomicState]) -> dict:
    """What the engine knows about the economy, counted rather than averaged.

    An average of an economy is not an economy, and one number would let a
    fully unknown condition hide behind a well-measured one.
    """
    by_standing: Dict[str, int] = {}
    for s in states:
        by_standing[s.standing] = by_standing.get(s.standing, 0) + 1
    anchoring = [s for s in states if s.anchors]
    return {
        "contract": CONTRACT,
        "conditions": len(states),
        "by_standing": by_standing,
        "anchoring": len(anchoring),
        "anchoring_kinds": sorted(s.state_kind for s in anchoring),
        "unknown_kinds": sorted(s.state_kind for s in states if not s.known),
        "moved": {s.state_kind: s.moved for s in states
                  if s.known and s.moved != FLAT},
        "note": ("standings are counted, never averaged; an unmeasured "
                 "condition is UNKNOWN and never FLAT"),
    }
