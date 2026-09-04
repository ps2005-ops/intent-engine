"""Level-k reasoning over market PARTICIPANT CLASSES, not over minds.

WHAT THIS IS
------------
Given a shock, what does each class of participant do, and what do they do
once they expect the others to have done it? That is the whole model. It is
not a simulation of any firm, it does not claim to know anyone's book, and it
produces FLOW DIRECTION with a confidence, never a size.

WHY CLASSES AND NOT AGENTS
--------------------------
Because a class has a MANDATE, and a mandate is publicly documented. A
volatility-control fund reduces equity exposure when realised volatility
rises; that is what the strategy is, stated in its own prospectus. An
individual manager's discretion is not knowable and modelling it is fiction.
Every reaction here has to name the mandate it follows -- `basis` is
required -- so a reader can check the claim against a document rather than
against a vibe.

THE THREE LEVELS ARE NOT THREE GUESSES
--------------------------------------
    L0  what the class does anyway, shock or no shock
    L1  the class's mechanical response to the shock
    L2  what it does anticipating the others' L1

L2 is where the value is and also where the fiction risk is highest, so L2
requires a NAMED counterparty whose L1 it is anticipating. An L2 reaction
that anticipates "the market" is refused: that is a sentiment, and it can be
written about any shock in any direction.

QRE IS AVAILABLE AND OFF BY DEFAULT
-----------------------------------
`quantal_response` is provided for the case where payoffs are actually
estimated. It is not used by `react` because this engine has not measured a
rationality parameter for any participant class, and fitting one to a handful
of episodes would produce a number with four decimal places and no content.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .causal import DOWN, UP
from .vocabulary import EconError, require

CONTRACT = "econ_levelk.v1"

# --- participant classes ----------------------------------------------------
CTA = "cta_trend_following"
VOL_CONTROL = "volatility_control"
RISK_PARITY = "risk_parity"
DEALERS = "options_dealers"
DISCRETIONARY_MACRO = "discretionary_macro"
LONG_ONLY = "long_only"
RETAIL = "retail"
MARKET_MAKERS = "market_makers"
BUYBACKS = "corporate_buybacks"
PASSIVE = "passive_index"
PARTICIPANTS = (CTA, VOL_CONTROL, RISK_PARITY, DEALERS, DISCRETIONARY_MACRO,
                LONG_ONLY, RETAIL, MARKET_MAKERS, BUYBACKS, PASSIVE)

#: The publicly-stated mandate each class follows. This is what `basis` must
#: be able to point at, and it is the reason a reaction is a claim about a
#: RULE rather than about a person's intentions.
MANDATES = {
    CTA: "position sized by trailing price trend and realised volatility; "
         "adds to trends and cuts against them, mechanically",
    VOL_CONTROL: "targets a constant portfolio volatility, so realised "
                 "volatility rising forces exposure down",
    RISK_PARITY: "equalises risk contribution across assets; a correlation "
                 "or volatility change reweights the whole book",
    DEALERS: "hedges an options book delta-neutrally; the sign of gamma "
             "decides whether hedging damps or amplifies moves",
    DISCRETIONARY_MACRO: "expresses a view; no mechanical rule, so its "
                         "reaction is the least predictable and is stated "
                         "with the lowest confidence here",
    LONG_ONLY: "benchmark-relative, slow, and constrained by mandate ranges",
    RETAIL: "flow follows attention and recent returns, with a documented "
            "tendency to buy drawdowns in index products",
    MARKET_MAKERS: "provides two-sided liquidity and widens as inventory "
                   "risk and volatility rise",
    BUYBACKS: "programmatic repurchase, price-insensitive within a window "
              "and suspended in blackout periods",
    PASSIVE: "buys and sells to track, in proportion to net subscriptions; "
             "indifferent to price",
}

L0, L1, L2 = 0, 1, 2
LEVELS = (L0, L1, L2)

BUY, SELL, HOLD = "BUY", "SELL", "HOLD"
FLOWS = (BUY, SELL, HOLD)


@dataclass(frozen=True)
class Reaction:
    """One participant class's response at one level of reasoning."""

    participant: str
    level: int
    flow: str
    #: The mandate clause this follows. Required; see the module docstring.
    basis: str
    confidence: float
    #: Trading days until the flow is expected to be visible.
    timing_days: int
    #: For L2 only: whose L1 this anticipates.
    anticipates: str = ""
    amplifying: bool = False

    def __post_init__(self) -> None:
        require(self.participant in PARTICIPANTS,
                f"unknown participant {self.participant!r}")
        require(self.level in LEVELS, f"unknown level {self.level}")
        require(self.flow in FLOWS, f"unknown flow {self.flow!r}")
        require(bool(self.basis.strip()),
                "a reaction names the mandate clause it follows; without one "
                "it is a guess about someone's intentions")
        require(0.0 <= self.confidence <= 1.0, "a probability")
        if self.level == L2:
            require(bool(self.anticipates) and
                    self.anticipates in PARTICIPANTS,
                    "an L2 reaction must name the participant class whose "
                    "response it anticipates; anticipating 'the market' is a "
                    "sentiment that can be written about any shock")

    def as_dict(self) -> dict:
        return {"participant": self.participant, "level": self.level,
                "flow": self.flow, "basis": self.basis,
                "confidence": round(self.confidence, 3),
                "timing_days": self.timing_days,
                "anticipates": self.anticipates,
                "amplifying": self.amplifying,
                "mandate": MANDATES[self.participant]}


@dataclass(frozen=True)
class ParticipantView:
    """Every level for one shock, plus what the net flow looks like."""

    shock: str
    as_of: str
    reactions: Tuple[Reaction, ...]

    def at(self, level: int) -> List[Reaction]:
        return [r for r in self.reactions if r.level == level]

    def net_flow(self, level: int = L1) -> str:
        """Direction only. Never a size.

        A size would require knowing each class's assets, and this engine
        knows none of them. Counting classes is already a strong assumption
        -- it treats a $2bn vol-control fund and the whole passive complex as
        one vote each -- so the result is reported as a DIRECTION with the
        count behind it, and `as_dict` carries the count so a reader can see
        how thin the vote was.
        """
        rs = self.at(level)
        buys = sum(r.confidence for r in rs if r.flow == BUY)
        sells = sum(r.confidence for r in rs if r.flow == SELL)
        if abs(buys - sells) < 0.25:
            return HOLD
        return BUY if buys > sells else SELL

    @property
    def reflexivity_risk(self) -> str:
        """Whether the mechanical responders point the same way as the shock.

        This is the input to `reflexivity`, kept here because it is a
        property of the participant set: when the amplifying classes all sell
        into a fall, the fall is partly the selling.
        """
        amplifiers = [r for r in self.at(L1) if r.amplifying]
        if len(amplifiers) >= 3:
            return "HIGH"
        if len(amplifiers) == 2:
            return "MODERATE"
        return "LOW"

    def as_dict(self) -> dict:
        return {"contract": CONTRACT, "shock": self.shock,
                "as_of": self.as_of,
                "reactions": [r.as_dict() for r in self.reactions],
                "net_flow": {str(k): self.net_flow(k) for k in LEVELS},
                "participants_responding":
                    len({r.participant for r in self.at(L1)}),
                "reflexivity_risk": self.reflexivity_risk}


#: The mechanical L1 responses. Keyed on (participant, shocked quantity,
#: direction). Absent combinations produce NO reaction rather than HOLD:
#: "this class's mandate says nothing about this shock" and "this class does
#: nothing" are different, and the second is a claim.
_L1_RULES: Dict[Tuple[str, str, str], Tuple[str, float, int, bool]] = {
    (VOL_CONTROL, "vix", UP): (SELL, 0.75, 2, True),
    (VOL_CONTROL, "realised_vol", UP): (SELL, 0.8, 2, True),
    (CTA, "sector_return", DOWN): (SELL, 0.65, 5, True),
    (CTA, "sector_return", UP): (BUY, 0.65, 5, True),
    (RISK_PARITY, "realised_vol", UP): (SELL, 0.6, 5, True),
    (RISK_PARITY, "credit_spread_hy", UP): (SELL, 0.5, 5, True),
    (DEALERS, "vix", UP): (SELL, 0.55, 1, True),
    (MARKET_MAKERS, "vix", UP): (HOLD, 0.6, 1, False),
    (MARKET_MAKERS, "funding_stress", UP): (HOLD, 0.7, 1, False),
    (RETAIL, "sector_return", DOWN): (BUY, 0.4, 3, False),
    (BUYBACKS, "sector_return", DOWN): (BUY, 0.45, 10, False),
    (PASSIVE, "sector_return", DOWN): (HOLD, 0.5, 1, False),
    (LONG_ONLY, "credit_spread_hy", UP): (SELL, 0.35, 20, False),
    (DISCRETIONARY_MACRO, "real_yield", UP): (SELL, 0.3, 10, False),
}


def react(*, quantity: str, direction: str, as_of: str,
          shock_label: str = "") -> ParticipantView:
    """Level 0, 1 and 2 responses to one shock."""
    require(direction in (UP, DOWN), f"unknown direction {direction!r}")
    reactions: List[Reaction] = []

    # L0 -- everyone continues doing what their mandate says they do anyway.
    for p in PARTICIPANTS:
        reactions.append(Reaction(
            participant=p, level=L0, flow=HOLD, basis=MANDATES[p],
            confidence=0.9, timing_days=0))

    # L1 -- the mechanical response, only where a mandate speaks to it.
    responders: List[Reaction] = []
    for p in PARTICIPANTS:
        rule = _L1_RULES.get((p, quantity, direction))
        if rule is None:
            continue
        flow, confidence, days, amplifying = rule
        r = Reaction(participant=p, level=L1, flow=flow,
                     basis=MANDATES[p], confidence=confidence,
                     timing_days=days, amplifying=amplifying)
        responders.append(r)
        reactions.append(r)

    # L2 -- anticipating the fastest mechanical responder. Only classes with
    # discretion can act at L2; a rules-based fund cannot front-run its own
    # rule, which is exactly what an unconstrained L2 layer would have it do.
    # DIRECTIONAL responders only. A class whose mandate says "widen and
    # keep quoting" is responding, and there is nothing in that to
    # anticipate. Including HOLD here silently disabled the whole L2 layer
    # for a volatility shock: market makers HOLD one day ahead of dealers
    # selling, they sorted first, and the branch below then declined to act
    # on a flow of HOLD -- so the level-k engine produced two levels and
    # reported three.
    directional = [r for r in responders if r.flow != HOLD]
    fastest = min(directional, key=lambda r: (r.timing_days, -r.confidence),
                  default=None)
    if fastest is not None:
        for p in (DISCRETIONARY_MACRO, MARKET_MAKERS):
            if p == fastest.participant:
                continue
            reactions.append(Reaction(
                participant=p, level=L2, flow=fastest.flow,
                basis=(f"{MANDATES[p]}; positions ahead of the mechanical "
                       f"{fastest.flow.lower()} that "
                       f"{fastest.participant} is expected to execute in "
                       f"{fastest.timing_days} day(s)"),
                confidence=fastest.confidence * 0.5,
                timing_days=max(0, fastest.timing_days - 1),
                anticipates=fastest.participant, amplifying=True))

    return ParticipantView(
        shock=shock_label or f"{direction} shock to {quantity}",
        as_of=as_of, reactions=tuple(reactions))


def quantal_response(payoffs: Sequence[float], *, rationality: float
                     ) -> List[float]:
    """Logit QRE choice probabilities. Provided, deliberately unused.

    `react` does not call this because no rationality parameter has been
    measured for any participant class here. Fitting one to a handful of
    episodes would produce a precise-looking number with no content, and the
    place that number would end up is a founder's screen.
    """
    require(rationality >= 0, "rationality is non-negative")
    if not payoffs:
        return []
    import math
    scaled = [rationality * p for p in payoffs]
    top = max(scaled)
    exps = [math.exp(s - top) for s in scaled]
    total = sum(exps) or 1.0
    return [e / total for e in exps]
