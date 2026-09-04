"""§3: regimes classified from what was knowable at T, never from hindsight.

WHY A CLASSIFIER AND NOT A CALENDAR
-----------------------------------
The previous run labelled regimes by year: 2007-2009 was CREDIT_CRISIS
because we know it was. That is fine for a descriptive breakdown and fatal
for a forecasting experiment, because "it is 2008" carries the answer. A
model told which regime it is in, by a labeller that knows how the period
ended, has been handed the outcome in a different shape.

So regimes are computed from the panel `as_known_at(T)` -- the same walled
read every feature goes through -- using thresholds fixed in this file before
any regime result was looked at.

WHY THRESHOLDS AND NOT A FITTED MODEL
-------------------------------------
A fitted regime model is another place to overfit, and it would need its own
holdout. Fixed thresholds on standard quantities are auditable, reproducible,
and cannot be tuned after seeing which split made the collective layer look
good. They are cruder than a Markov-switching model and that is the trade
being made deliberately.

WHY A REGIME IS NOT EXCLUSIVE
-----------------------------
An economy can be tightening AND in credit stress. Forcing one label per date
would make the classifier choose, and the choice would be arbitrary in
exactly the periods that matter most. `classify` returns every regime whose
condition holds, with the evidence that fired.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .vocabulary import EconError, require

CONTRACT = "econ_regime.v1"

CREDIT_STRESS = "CREDIT_STRESS"
LIQUIDITY_STRESS = "LIQUIDITY_STRESS"
INFLATION_SHOCK = "INFLATION_SHOCK"
DISINFLATION = "DISINFLATION"
LABOUR_DETERIORATION = "LABOUR_DETERIORATION"
RECOVERY = "RECOVERY"
LOW_VOL_EXPANSION = "LOW_VOL_EXPANSION"
POLICY_EASING = "POLICY_EASING"
POLICY_TIGHTENING = "POLICY_TIGHTENING"
REGIMES = (CREDIT_STRESS, LIQUIDITY_STRESS, INFLATION_SHOCK, DISINFLATION,
           LABOUR_DETERIORATION, RECOVERY, LOW_VOL_EXPANSION,
           POLICY_EASING, POLICY_TIGHTENING)

#: The calm regime. Section 16 requires a negative control: a layer that
#: claims value here as well as in crisis is claiming value everywhere, and
#: a genuinely regime-dependent signal should be quiet in calm periods.
NEGATIVE_CONTROL = LOW_VOL_EXPANSION

#: How many of the four stress families must be evaluable before an origin
#: may be called calm. Three of four: a calm reading with only two conditions
#: checked is closer to "we could not tell" than to "nothing was wrong".
CALM_QUORUM = 3

#: Thresholds, fixed before any regime result was inspected. Each is a
#: round number on a standard quantity rather than a fitted cut point,
#: because a fitted cut point is a hyperparameter chosen with the answer in
#: view.
THRESHOLDS = {
    # Delinquency rising materially year on year.
    "credit_delinquency_yoy": 0.10,
    # Unemployment up half a point over a year is the classic recession rule
    # of thumb's neighbourhood, without the hindsight-dated NBER call.
    "unemployment_rise_pp": 0.5,
    "unemployment_fall_pp": -0.3,
    # CPI year on year.
    "inflation_high": 0.04,
    "inflation_low": 0.015,
    # Policy rate change over a year.
    "policy_move_pp": 0.75,
    # Curve inversion, as a funding-stress proxy this engine can actually read.
    "curve_inversion_pp": 0.0,
}


@dataclass(frozen=True)
class RegimeReading:
    """Which regimes held at `as_of`, and what said so."""

    as_of: str
    regimes: Tuple[str, ...]
    evidence: Dict[str, float]
    vintage_cutoff: str
    #: Quantities the classifier wanted and could not read at this date.
    missing: Tuple[str, ...] = ()
    #: How many of the four stress families the classifier could actually
    #: evaluate here. A calm label resting on three is a weaker claim than
    #: one resting on four, and the difference has to be visible.
    stress_families_evaluated: int = 0

    def __post_init__(self) -> None:
        for r in self.regimes:
            require(r in REGIMES, f"unknown regime {r!r}")

    @property
    def confident(self) -> bool:
        """Were all the inputs the classifier wanted actually available?

        A regime read from half its inputs is a guess, and the periods where
        inputs are missing are the early ones -- exactly where a spurious
        label would do the most damage.
        """
        return not self.missing

    def holds(self, regime: str) -> bool:
        return regime in self.regimes

    def as_dict(self) -> dict:
        return {"as_of": self.as_of, "regimes": list(self.regimes),
                "evidence": dict(self.evidence),
                "vintage_cutoff": self.vintage_cutoff,
                "stress_families_evaluated": self.stress_families_evaluated,
                "missing": list(self.missing), "confident": self.confident}


#: How many observations make a YEAR, per series. NOT a constant.
#:
#: The first version of this file used 4 periods for everything. That is a
#: year for a quarterly series and FOUR MONTHS for a monthly one, so
#: "inflation year on year" was inflation over a third of a year, came in
#: around a third of its true value, and never once cleared the 4% shock
#: threshold. DISINFLATION fired at 98 of 115 origins and INFLATION_SHOCK at
#: none -- a regime split that looked plausible and was arithmetic.
PERIODS_PER_YEAR = {
    "DRCCLACBS": 4,      # quarterly
    "UNRATE": 12,        # monthly
    "CPIAUCSL": 12,      # monthly
    "DFF": 12,           # monthly average in this panel
}


def _yoy(hist, periods: int) -> Optional[float]:
    if len(hist) <= periods:
        return None
    a, b = hist[-1 - periods][1], hist[-1][1]
    return None if a == 0 else (b - a) / abs(a)


def _diff(hist, periods: int) -> Optional[float]:
    if len(hist) <= periods:
        return None
    return hist[-1][1] - hist[-1 - periods][1]


def classify(panel, as_of: str) -> RegimeReading:
    """Every regime whose condition holds, from the walled read at `as_of`.

    Reads through `Panel.history(..., as_of=)`, the same primitive every
    feature uses, so a regime label cannot see anything a forecast could not.
    """
    require(bool(as_of), "a regime reading is dated")
    ev: Dict[str, float] = {}
    missing: List[str] = []

    def hist(sid):
        # Enough history to look back a full year for this series' frequency,
        # plus a margin so a single skipped print does not blank the regime.
        need = PERIODS_PER_YEAR.get(sid, 4)
        h = panel.history(sid, as_of=as_of, lookback=need + 6)
        if len(h) <= need:
            missing.append(sid)
            return []
        return h

    delinq = hist("DRCCLACBS")
    unrate = hist("UNRATE")
    cpi = hist("CPIAUCSL")
    dff = hist("DFF")
    d2, d10 = hist("DGS2"), hist("DGS10")

    out: List[str] = []

    d_yoy = _yoy(delinq, PERIODS_PER_YEAR['DRCCLACBS']) if delinq else None
    if d_yoy is not None:
        ev["delinquency_yoy"] = round(d_yoy, 5)
        if d_yoy >= THRESHOLDS["credit_delinquency_yoy"]:
            out.append(CREDIT_STRESS)

    u_ch = _diff(unrate, PERIODS_PER_YEAR['UNRATE']) if unrate else None
    if u_ch is not None:
        ev["unemployment_change_pp"] = round(u_ch, 5)
        if u_ch >= THRESHOLDS["unemployment_rise_pp"]:
            out.append(LABOUR_DETERIORATION)
        elif u_ch <= THRESHOLDS["unemployment_fall_pp"]:
            out.append(RECOVERY)

    c_yoy = _yoy(cpi, PERIODS_PER_YEAR['CPIAUCSL']) if cpi else None
    if c_yoy is not None:
        ev["inflation_yoy"] = round(c_yoy, 5)
        if c_yoy >= THRESHOLDS["inflation_high"]:
            out.append(INFLATION_SHOCK)
        elif c_yoy <= THRESHOLDS["inflation_low"]:
            out.append(DISINFLATION)

    p_ch = _diff(dff, PERIODS_PER_YEAR['DFF']) if dff else None
    if p_ch is not None:
        ev["policy_change_pp"] = round(p_ch, 5)
        if p_ch >= THRESHOLDS["policy_move_pp"]:
            out.append(POLICY_TIGHTENING)
        elif p_ch <= -THRESHOLDS["policy_move_pp"]:
            out.append(POLICY_EASING)

    if d2 and d10:
        slope = d10[-1][1] - d2[-1][1]
        ev["curve_slope_pp"] = round(slope, 5)
        if slope < THRESHOLDS["curve_inversion_pp"]:
            out.append(LIQUIDITY_STRESS)

    # The calm case is the ABSENCE of every stress condition, not a condition
    # of its own -- otherwise a period could be simultaneously calm and in
    # crisis, and the negative control would stop being a control.
    #
    # WHY "not missing" WAS WRONG. Requiring EVERY input to be present made
    # the calm label unreachable before 2012, because DRCCLACBS has no
    # publisher vintage earlier than that. Measured: LOW_VOL_EXPANSION fired
    # at exactly 115 origins in a 343-origin arm AND at exactly 115 in a
    # 584-origin arm -- the same 115 post-2012 origins both times. A negative
    # control that can only occur in one decade is not a control for calm, it
    # is a control for "after 2012".
    #
    # The honest rule is that calm is a claim about the conditions that could
    # be EVALUATED. It needs a quorum -- three of the four stress families --
    # so it still rests on evidence, and `stress_families_evaluated` is
    # carried on the reading so a partial calm is visible rather than
    # indistinguishable from a complete one.
    stressed = {CREDIT_STRESS, LIQUIDITY_STRESS, INFLATION_SHOCK,
                LABOUR_DETERIORATION}
    evaluated = sum([
        "delinquency_yoy" in ev,
        "unemployment_change_pp" in ev,
        "inflation_yoy" in ev,
        "curve_slope_pp" in ev,
    ])
    if not (set(out) & stressed) and evaluated >= CALM_QUORUM:
        out.append(LOW_VOL_EXPANSION)

    return RegimeReading(as_of=as_of, regimes=tuple(sorted(set(out))),
                         evidence=ev, vintage_cutoff=as_of,
                         stress_families_evaluated=evaluated,
                         missing=tuple(sorted(set(missing))))


def classify_many(panel, origins: Sequence[str]) -> List[RegimeReading]:
    return [classify(panel, o) for o in origins]


def summarise(readings: Sequence[RegimeReading]) -> dict:
    counts = {r: 0 for r in REGIMES}
    for rd in readings:
        for r in rd.regimes:
            counts[r] += 1
    confident = sum(1 for r in readings if r.confident)
    calm_partial = sum(1 for r in readings
                       if LOW_VOL_EXPANSION in r.regimes
                       and r.stress_families_evaluated < 4)
    return {"contract": CONTRACT, "origins": len(readings),
            "confident": confident,
            "calm_quorum": CALM_QUORUM,
            "calm_on_partial_evidence": calm_partial,
            "unclassifiable": len(readings) - confident,
            "counts": {k: v for k, v in sorted(counts.items()) if v},
            "thresholds": dict(THRESHOLDS),
            "negative_control": NEGATIVE_CONTROL,
            "multi_regime_origins": sum(1 for r in readings
                                        if len(r.regimes) > 1)}
