"""Where price causes the thing that caused the price.

THE LOOP
--------
    belief -> positioning -> price -> risk constraints -> forced flows
           -> new price -> updated belief

Every arrow is somewhere else in this package. What this module adds is the
CLOSURE: the observation that the last arrow feeds the first, and that when
it does, a move is partly its own cause.

THE DISTINCTION THAT MUST SURVIVE
---------------------------------
    fundamental      the move the mechanism justifies
    reflexive        the additional move the constraint system produces

Collapsing them is how a system learns the wrong lesson twice. A -12% move
that was -4% fundamental and -8% forced deleveraging teaches "the mechanism
was three times stronger than we thought" if the two are merged, and the
engine then over-predicts the next one. `Loop.decompose` refuses to report a
single number.

WHAT THIS CANNOT DO
-------------------
It cannot measure the split. Nothing here observes positioning, and the
decomposition is a STRUCTURED HYPOTHESIS with a stated basis, carried at the
confidence the participant view supports. `attribution` returns bands, and
`measured` is permanently False until an actual positioning series exists to
calibrate against. The honest form of this analysis is "a large part of this
was forced", not "61% of this was forced".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .levelk import L1, ParticipantView, BUY, HOLD, SELL
from .vocabulary import require

CONTRACT = "econ_reflexivity.v1"

FUNDAMENTAL = "FUNDAMENTAL"
REFLEXIVE = "REFLEXIVE"

#: Named loops, each with the constraint that closes it. A loop with no named
#: constraint is a story about sentiment.
LOOPS = {
    "dealer_short_gamma": (
        "dealers hedging a short-gamma book sell into falls and buy into "
        "rallies, so hedging AMPLIFIES the move it is responding to",
        "the sign of aggregate dealer gamma"),
    "cta_trend_acceleration": (
        "trend followers add to a move that has already begun, and their "
        "adding is part of what continues it",
        "trailing trend and realised-volatility position sizing"),
    "vol_control_deleveraging": (
        "realised volatility rising forces exposure down, which raises "
        "realised volatility",
        "a constant portfolio-volatility target"),
    "margin_collateral_spiral": (
        "falling collateral value triggers margin calls, which force sales, "
        "which lower collateral value",
        "haircuts and maintenance margin"),
}


@dataclass(frozen=True)
class Loop:
    """One reflexive loop, and whether it is currently armed."""

    name: str
    description: str
    constraint: str
    armed: bool
    basis: str
    confidence: float = 0.3

    def as_dict(self) -> dict:
        return {"name": self.name, "description": self.description,
                "constraint": self.constraint, "armed": self.armed,
                "basis": self.basis, "confidence": round(self.confidence, 3)}


@dataclass(frozen=True)
class Attribution:
    """How much of a move the mechanism justifies, and how much is forced.

    Bands, not numbers. `measured` is False and there is no path that sets it
    True without a positioning series; see the module docstring.
    """

    fundamental_share: str
    reflexive_share: str
    basis: str
    loops: Tuple[str, ...]
    measured: bool = field(default=False, init=False)

    def sentence(self) -> str:
        return (f"a {self.fundamental_share} part of this move is what the "
                f"mechanism justifies and a {self.reflexive_share} part is "
                f"forced flow ({', '.join(self.loops) or 'no armed loop'}); "
                "the split is a structured hypothesis, not a measurement")

    def as_dict(self) -> dict:
        return {"fundamental_share": self.fundamental_share,
                "reflexive_share": self.reflexive_share,
                "basis": self.basis, "loops": list(self.loops),
                "measured": self.measured, "sentence": self.sentence()}


def armed_loops(view: ParticipantView, *,
                dealer_gamma_negative: Optional[bool] = None) -> List[Loop]:
    """Which loops the participant view says are live.

    `dealer_gamma_negative` is an INPUT rather than an inference. Dealer gamma
    sign is estimable from options open interest and this package has no
    market-data access; guessing it would put the most consequential loop in
    the set on a coin flip. None means unknown, and unknown is not armed.
    """
    responders = {r.participant: r for r in view.at(L1)}
    out: List[Loop] = []

    from .levelk import CTA, DEALERS, RISK_PARITY, VOL_CONTROL
    vc = responders.get(VOL_CONTROL)
    out.append(Loop(
        name="vol_control_deleveraging", description=LOOPS[
            "vol_control_deleveraging"][0],
        constraint=LOOPS["vol_control_deleveraging"][1],
        armed=bool(vc and vc.flow == SELL and vc.amplifying),
        basis=("volatility-control funds are selling mechanically"
               if vc and vc.flow == SELL
               else "no mechanical volatility-control response to this shock"),
        confidence=(vc.confidence if vc else 0.0)))

    cta = responders.get(CTA)
    out.append(Loop(
        name="cta_trend_acceleration",
        description=LOOPS["cta_trend_acceleration"][0],
        constraint=LOOPS["cta_trend_acceleration"][1],
        armed=bool(cta and cta.flow in (BUY, SELL) and cta.amplifying),
        basis=(f"trend followers are {cta.flow.lower()}ing with the move"
               if cta and cta.flow != HOLD
               else "no trend-following response to this shock"),
        confidence=(cta.confidence if cta else 0.0)))

    dealers = responders.get(DEALERS)
    out.append(Loop(
        name="dealer_short_gamma",
        description=LOOPS["dealer_short_gamma"][0],
        constraint=LOOPS["dealer_short_gamma"][1],
        armed=bool(dealer_gamma_negative and dealers),
        basis=("aggregate dealer gamma was supplied as negative"
               if dealer_gamma_negative
               else "dealer gamma sign was not supplied; unknown is not "
                    "armed, because this is the loop a guess would matter "
                    "most in"),
        confidence=0.5 if dealer_gamma_negative else 0.0))

    rp = responders.get(RISK_PARITY)
    out.append(Loop(
        name="margin_collateral_spiral",
        description=LOOPS["margin_collateral_spiral"][0],
        constraint=LOOPS["margin_collateral_spiral"][1],
        armed=bool(rp and rp.flow == SELL),
        basis=("leverage-constrained holders are reducing"
               if rp and rp.flow == SELL
               else "no leverage-constrained seller identified"),
        confidence=(rp.confidence if rp else 0.0)))
    return out


def attribution(view: ParticipantView, *,
                dealer_gamma_negative: Optional[bool] = None) -> Attribution:
    """Split a move into what the mechanism justifies and what is forced."""
    live = [l for l in armed_loops(view,
                                   dealer_gamma_negative=dealer_gamma_negative)
            if l.armed]
    n = len(live)
    if n == 0:
        return Attribution(
            fundamental_share="dominant", reflexive_share="negligible",
            basis="no reflexive loop is armed on the participant view",
            loops=())
    if n == 1:
        return Attribution(
            fundamental_share="larger", reflexive_share="material",
            basis=f"one armed loop: {live[0].name}",
            loops=tuple(l.name for l in live))
    if n == 2:
        return Attribution(
            fundamental_share="uncertain", reflexive_share="comparable",
            basis="two armed loops reinforcing the same direction",
            loops=tuple(l.name for l in live))
    return Attribution(
        fundamental_share="smaller", reflexive_share="dominant",
        basis=(f"{n} armed loops; at this point the move is substantially "
               "its own cause and the mechanism should not be re-estimated "
               "from it"),
        loops=tuple(l.name for l in live))


def learning_warning(a: Attribution) -> str:
    """What the engine must NOT conclude from a reflexive move.

    Returned as text so it can be attached to any belief update produced in
    the window. The failure it prevents is the expensive one: taking a forced
    -12% as evidence that a mechanism is three times stronger than believed,
    and then over-predicting the next episode.
    """
    if a.reflexive_share in ("comparable", "dominant"):
        return ("this move may not be used to re-estimate the mechanism's "
                "magnitude: a substantial part of it is forced flow, and "
                "fitting the mechanism to it would over-state the mechanism "
                "for every future episode")
    return ""
