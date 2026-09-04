"""Attacking a synthetic control, because a fit nobody attacked is a number.

WHAT THIS IS FOR
----------------
`synthetic_control.fit` returns a treated-minus-synthetic path and a
pre-period fit statistic. Neither of those is evidence that the gap after the
treatment is the treatment. A donor pool of forty units will produce SOME gap
for any unit you name, at any date you name, and the gap will look exactly like
this one. The question a diagnostic answers is not "did we fit well" but "is
this gap unusual among the gaps this method produces when nothing happened".

So the central test here is Abadie's: run the identical fit treating each
DONOR as if it had been treated, and see where the real unit's effect ranks in
that distribution. If eleven of twenty placebo units show a gap as large, the
method has told you what it tells you about anything.

THE VERDICT IS NOT A NEW VOCABULARY
-----------------------------------
Every diagnostic here emits an `economic_method.MethodAssumptionCheck` — the
same object the forecasting assumptions already produce, with the same
PASSED / FAILED / UNTESTED results and the same CRITICAL / ADVISORY
severities — and the standing comes from `economic_method.interpret`, which
already exists and is already what the standing wall reads.

That is deliberate and it is the main design decision in this file. A second
verdict vocabulary beside `interpret`'s is precisely how the thesis and the
proof package came to disagree in V3: two honest local rules, no comparison
between them, and certainty gained by travelling from one surface to the next.
There is one ceiling and this file feeds it.

WHAT CANNOT BE TESTED HERE, AND SAYS SO
---------------------------------------
Two of the things most likely to be wrong about a synthetic control are facts
about how the study was run, not about the series:

  * whether the treatment date was chosen before the effect was seen;
  * whether the outcome was revised after the date the analysis claims to
    stand at.

No arrangement of the numbers can establish either. They come back UNTESTED
with the reason, and `interpret` already refuses a causal reading when a
CRITICAL assumption is untested — so a synthetic control cannot reach USEFUL
on the strength of statistics alone. That is the correct answer and it is
uncomfortable, which is why it is written down here.
"""
from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from . import economic_method as EM
from . import synthetic_control as SC

CONTRACT = "causal_diagnostics.v1"

#: A fit too short or too refused to attack. Distinct from a fit that was
#: attacked and survived, and from one that was attacked and failed.
INSUFFICIENT_FOR_DIAGNOSIS = "INSUFFICIENT_FOR_DIAGNOSIS"

#: The treated unit must rank in the top this share of the placebo
#: distribution. At 0.10 with nine donors the real unit has to be first. Not a
#: p-value: the placebo distribution is a permutation over a handful of units
#: and calling its tail a significance level would dress up a rank as a test.
PLACEBO_RANK_SHARE = 0.10

#: An in-time placebo at a sham date should produce a much smaller effect than
#: the real one. Below this ratio the real date is not special.
SHAM_EFFECT_RATIO = 0.50

#: Correlation between pre-period residual and time. A fit whose errors march
#: in one direction is not reproducing the unit, it is straddling it, and the
#: post-period gap inherits the march.
PRE_TREND_CORRELATION = 0.60

#: Donors moving together at the treatment date means a common shock hit the
#: whole panel. The synthetic unit absorbs it, so the gap is whatever the
#: treated unit did differently — which may be nothing to do with treatment.
COMMON_SHOCK_SHARE = 0.80


@dataclass(frozen=True)
class Diagnostic:
    """One attack, its statistic, and whether the fit survived it."""

    name: str
    result: str
    severity: str
    evidence: str
    statistic: Optional[float] = None
    threshold: Optional[float] = None
    #: Placebo units that could not be fitted. Reported because a placebo
    #: distribution built from three of twenty donors is a different object
    #: from one built from twenty, and dropping them silently would make a
    #: thin distribution look like a clean one.
    excluded: int = 0

    def as_dict(self) -> dict:
        out = dataclasses.asdict(self)
        out.update(contract=CONTRACT)
        return out


# --- statistics ----------------------------------------------------------------

def _rmspe(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return math.sqrt(sum(v * v for v in values) / len(values))


def effect_ratio(fit: SC.SyntheticControlFit) -> Optional[float]:
    """Post-period error over pre-period error — Abadie's statistic.

    A large gap after the treatment is only interesting relative to how well
    the synthetic unit tracked BEFORE it. A unit the donors never reproduced
    will show a large post gap for the same reason it showed a large pre gap,
    and a raw effect size cannot tell the two apart.

    None when the pre-period error is zero: the ratio is undefined, not
    infinite, and reporting infinity would rank a perfect pre-fit above every
    real finding automatically.
    """
    if not fit.fitted or not fit.effect_path:
        return None
    pre = _rmspe(fit.effect_path[:fit.treatment_index])
    post = _rmspe(fit.effect_path[fit.treatment_index:])
    # RELATIVE, NOT ABSOLUTE. An absolute floor of 1e-12 was the first version
    # and it was wrong in both directions: on a series measured in millions it
    # never fires, and on a unit that IS a convex combination of its donors the
    # solver returns residuals around 1e-9 — arithmetic noise, not error — and
    # the ratio came back in the hundreds of millions. That number then ranked
    # first in every placebo distribution it entered.
    scale = fit.treated_pre_variation or 0.0
    if scale <= 0 or pre <= scale * 1e-9:
        return None
    return post / pre


def _correlation_with_time(values: Sequence[float]) -> Optional[float]:
    n = len(values)
    if n < 4:
        return None
    times = list(range(n))
    mean_t = sum(times) / n
    mean_v = sum(values) / n
    cov = sum((times[i] - mean_t) * (values[i] - mean_v) for i in range(n))
    var_t = sum((t - mean_t) ** 2 for t in times)
    var_v = sum((v - mean_v) ** 2 for v in values)
    if var_t <= 1e-12 or var_v <= 1e-12:
        return None
    return cov / math.sqrt(var_t * var_v)


# --- the attacks ---------------------------------------------------------------

def in_space_placebo(treated: Sequence[float], donors: Dict[str, Sequence[float]],
                     *, treatment_index: int, fit: SC.SyntheticControlFit
                     ) -> Diagnostic:
    """Run the same fit on every donor as if it had been treated.

    The real unit is never in a placebo's donor pool: it IS treated, so
    including it would let the placebo synthetic unit absorb the very effect
    the test is trying to detect.
    """
    real = effect_ratio(fit)
    if real is None:
        return Diagnostic(
            name="in_space_placebo", result=EM.UNTESTED, severity=EM.CRITICAL,
            evidence="the treated unit's pre-period error is zero, so the "
                     "post-over-pre ratio is undefined and there is nothing "
                     "to rank")
    names = sorted(donors)
    if len(names) < 3:
        return Diagnostic(
            name="in_space_placebo", result=EM.UNTESTED, severity=EM.CRITICAL,
            evidence=f"{len(names)} donor(s); a placebo distribution over "
                     "fewer than three units is a comparison, not a "
                     "distribution")

    ratios, excluded = [], 0
    for candidate in names:
        pool = {n: donors[n] for n in names if n != candidate}
        if not pool:
            excluded += 1
            continue
        placebo = SC.fit(donors[candidate], pool,
                         treatment_index=treatment_index,
                         treated_unit=f"placebo:{candidate}")
        got = effect_ratio(placebo)
        if got is None:
            # A donor the remaining pool cannot reproduce tells us nothing
            # about the treated unit. Counted, never silently dropped.
            excluded += 1
            continue
        ratios.append(got)

    if len(ratios) < 2:
        return Diagnostic(
            name="in_space_placebo", result=EM.UNTESTED, severity=EM.CRITICAL,
            evidence=f"only {len(ratios)} placebo unit(s) could be fitted out "
                     f"of {len(names)}; the rest were refused by the same "
                     "criteria the real fit passed",
            excluded=excluded)

    beaten = sum(1 for r in ratios if r >= real)
    # Rank among all units including the treated one, so the best possible
    # share is 1/(n+1) rather than 0 — a unit cannot be more extreme than
    # being the most extreme thing in the panel.
    share = (beaten + 1) / (len(ratios) + 1)
    best_possible = 1.0 / (len(ratios) + 1)

    # A THRESHOLD THE PANEL CANNOT REACH IS NOT A FAILED TEST.
    # With four fitted placebos the most extreme possible result is 20%, so a
    # threshold of 10% returns FAILED for every unit including one with a
    # thirty-fold effect. That reads as "the effect is not unusual" when what
    # happened is that the panel is too small to demonstrate it either way.
    # Measured, not guessed: on the fixture panel a genuine effect of 25
    # against a pre-period variation of 0.79 came back FAILED at a share of
    # exactly 1/(4+1).
    if best_possible > PLACEBO_RANK_SHARE:
        return Diagnostic(
            name="in_space_placebo", result=EM.UNTESTED, severity=EM.CRITICAL,
            evidence=(f"{len(ratios)} placebo unit(s) were fitted out of "
                      f"{len(names)}, so the most extreme achievable rank is "
                      f"{best_possible:.1%} and the {PLACEBO_RANK_SHARE:.0%} "
                      "threshold cannot be reached by any unit; this panel "
                      "cannot demonstrate the effect either way"),
            statistic=round(share, 6), threshold=PLACEBO_RANK_SHARE,
            excluded=excluded)

    return Diagnostic(
        name="in_space_placebo",
        result=EM.PASSED if share <= PLACEBO_RANK_SHARE else EM.FAILED,
        severity=EM.CRITICAL,
        evidence=(f"the treated unit's post-over-pre error ratio is "
                  f"{real:.3f}; {beaten} of {len(ratios)} placebo units reach "
                  f"or exceed it, putting it at {share:.1%} of the "
                  f"distribution against a threshold of "
                  f"{PLACEBO_RANK_SHARE:.0%}"),
        statistic=round(share, 6), threshold=PLACEBO_RANK_SHARE,
        excluded=excluded)


def in_time_placebo(treated: Sequence[float],
                    donors: Dict[str, Sequence[float]], *,
                    treatment_index: int, fit: SC.SyntheticControlFit
                    ) -> Diagnostic:
    """Refit pretending the treatment happened earlier, in the quiet period.

    Only pre-treatment observations are used, so the sham fit never sees the
    real post-period. If a date where nothing happened produces an effect of
    similar size, the real date is not special and the gap is the method's
    normal output rather than a finding.
    """
    real = fit.average_effect
    if real is None:
        return Diagnostic(
            name="in_time_placebo", result=EM.UNTESTED, severity=EM.ADVISORY,
            evidence="the real fit produced no effect to compare against")

    sham_index = treatment_index // 2
    if sham_index < SC.MINIMUM_PRE_PERIOD:
        return Diagnostic(
            name="in_time_placebo", result=EM.UNTESTED, severity=EM.ADVISORY,
            evidence=(f"a sham treatment at {sham_index} leaves less than the "
                      f"{SC.MINIMUM_PRE_PERIOD}-observation floor to fit on; "
                      "the pre-period is not long enough to be split"),
            statistic=float(sham_index), threshold=float(SC.MINIMUM_PRE_PERIOD))

    quiet_treated = list(treated[:treatment_index])
    quiet_donors = {n: list(s[:treatment_index]) for n, s in donors.items()}
    sham = SC.fit(quiet_treated, quiet_donors, treatment_index=sham_index,
                  treated_unit=f"{fit.treated_unit}:in-time-placebo")
    if not sham.fitted:
        return Diagnostic(
            name="in_time_placebo", result=EM.UNTESTED, severity=EM.ADVISORY,
            evidence=("the sham fit was refused: " + sham.status + " — "
                      + sham.refusal_detail))

    if abs(real) <= 1e-12:
        return Diagnostic(
            name="in_time_placebo", result=EM.UNTESTED, severity=EM.ADVISORY,
            evidence="the real effect is zero, so a ratio against it is "
                     "undefined")
    ratio = abs(sham.average_effect) / abs(real)
    return Diagnostic(
        name="in_time_placebo",
        result=EM.PASSED if ratio < SHAM_EFFECT_RATIO else EM.FAILED,
        severity=EM.ADVISORY,
        evidence=(f"a sham treatment at index {sham_index} produces an effect "
                  f"of {sham.average_effect:.4g} against the real "
                  f"{real:.4g}, a ratio of {ratio:.2f} against "
                  f"{SHAM_EFFECT_RATIO}"),
        statistic=round(ratio, 6), threshold=SHAM_EFFECT_RATIO)


def pre_trend(fit: SC.SyntheticControlFit) -> Diagnostic:
    """Do the pre-period errors march in one direction?

    A small RMSPE can hide a systematic drift: a synthetic unit that starts
    above the treated unit and ends below it has a low average error and is
    diverging at exactly the moment the post-period begins. The post-period gap
    then continues a trend that started before the treatment.
    """
    if not fit.fitted:
        return Diagnostic(
            name="pre_trend", result=EM.UNTESTED, severity=EM.CRITICAL,
            evidence="no fit to examine")
    residuals = fit.effect_path[:fit.treatment_index]
    correlation = _correlation_with_time(residuals)
    if correlation is None:
        return Diagnostic(
            name="pre_trend", result=EM.UNTESTED, severity=EM.CRITICAL,
            evidence=(f"{len(residuals)} pre-period residual(s) with no "
                      "variation to correlate against time"))
    return Diagnostic(
        name="pre_trend",
        result=EM.FAILED if abs(correlation) > PRE_TREND_CORRELATION
        else EM.PASSED,
        severity=EM.CRITICAL,
        evidence=(f"pre-period residuals correlate {correlation:+.3f} with "
                  f"time against a limit of {PRE_TREND_CORRELATION}; above it "
                  "the synthetic unit is diverging before the treatment and "
                  "the post-period gap continues that divergence"),
        statistic=round(correlation, 6), threshold=PRE_TREND_CORRELATION)


def weight_concentration(fit: SC.SyntheticControlFit) -> Diagnostic:
    """Is this a synthetic control or a comparison with one unit?"""
    if not fit.fitted or fit.concentration is None:
        return Diagnostic(
            name="weight_concentration", result=EM.UNTESTED,
            severity=EM.ADVISORY, evidence="no weights to examine")
    carrier = max(fit.weights, key=lambda w: w.weight)
    return Diagnostic(
        name="weight_concentration",
        result=EM.FAILED if fit.concentration >= SC.CONCENTRATION_WARN
        else EM.PASSED,
        severity=EM.ADVISORY,
        evidence=(f"{len(fit.contributing_donors)} donor(s) contribute; the "
                  f"largest, {carrier.unit!r}, carries "
                  f"{fit.concentration:.1%} against a limit of "
                  f"{SC.CONCENTRATION_WARN:.0%}"),
        statistic=round(fit.concentration, 6),
        threshold=SC.CONCENTRATION_WARN)


def common_shock(donors: Dict[str, Sequence[float]], *,
                 treatment_index: int) -> Diagnostic:
    """Did the whole panel move at the treatment date?

    If it did, something happened to everybody. The synthetic unit absorbs it
    by construction, which is the method working — but it also means the
    remaining gap is small, noisy, and the difference between two units'
    responses to a shared shock rather than the effect of a treatment one of
    them received. Advisory, because absorbing a common shock is exactly what
    the method is for; it bounds the reading rather than voiding it.
    """
    names = sorted(donors)
    if len(names) < 3 or treatment_index < 1:
        return Diagnostic(
            name="common_shock", result=EM.UNTESTED, severity=EM.ADVISORY,
            evidence=f"{len(names)} donor(s) is too few to see a shared move")
    steps = []
    for name in names:
        series = donors[name]
        if treatment_index >= len(series):
            continue
        steps.append(series[treatment_index] - series[treatment_index - 1])
    if len(steps) < 3:
        return Diagnostic(
            name="common_shock", result=EM.UNTESTED, severity=EM.ADVISORY,
            evidence="too few donors span the treatment date")
    up = sum(1 for s in steps if s > 0)
    share = max(up, len(steps) - up) / len(steps)
    return Diagnostic(
        name="common_shock",
        result=EM.FAILED if share >= COMMON_SHOCK_SHARE else EM.PASSED,
        severity=EM.ADVISORY,
        evidence=(f"{share:.0%} of {len(steps)} donors move the same way at "
                  f"the treatment date against a limit of "
                  f"{COMMON_SHOCK_SHARE:.0%}; a shared move means the "
                  "synthetic unit is absorbing a panel-wide shock and the "
                  "residual gap is a difference in responses"),
        statistic=round(share, 6), threshold=COMMON_SHOCK_SHARE)


# --- assembling the verdict ----------------------------------------------------
#
# The mapping from a diagnostic to an assumption is explicit and lives here,
# because the assumptions are the registry's and the statistics are this
# file's, and a mapping that lived in neither is how they drift apart.

#: assumption text in economic_method.METHODS[SYNTHETIC_CONTROL] -> diagnostic
ASSUMPTION_DIAGNOSTICS = {
    "the donor pool can reproduce the pre-period": "pre_trend",
    "no donor is itself affected by the treatment": "common_shock",
    "the treated unit's departure exceeds what this method produces for "
    "untreated units": "in_space_placebo",
    "the treatment date is not merely the date the gap was noticed":
        "in_time_placebo",
    "no single donor carries the synthetic unit": "weight_concentration",
}

#: Assumptions no arrangement of the series can establish. Recorded so the
#: count of untestable assumptions is a number rather than an impression.
UNTESTABLE_HERE = {
    "the treatment date was chosen before the effect was seen":
        "this is a fact about how the study was conducted; a series cannot "
        "distinguish a date chosen in advance from one chosen afterwards",
    "the outcome was not revised after the analysis date":
        "vintage is a property of the record, not of the values; the revised "
        "series and the original look identical here",
}


def assumption_coverage() -> dict:
    """Which of the method's declared assumptions this file can test.

    The debt is a NUMBER, not an impression. A dispatch table that quietly
    covers four of twelve cases and carries the other eight as unexamined
    debt is a shape this program has shipped before; the fix that worked was
    counting the uncovered ones and pinning the membership of the list rather
    than its length.
    """
    declared = list(EM.METHODS[SC.SYNTHETIC_CONTROL].assumptions)
    tested = set(ASSUMPTION_DIAGNOSTICS)
    untestable = set(UNTESTABLE_HERE)
    uncovered = [a for a in declared
                 if a not in tested and a not in untestable]
    orphan = sorted((tested | untestable) - set(declared))
    return {
        "contract": CONTRACT,
        "declared": len(declared),
        "tested_by_a_diagnostic": len([a for a in declared if a in tested]),
        "untestable_here": len([a for a in declared if a in untestable]),
        "uncovered": uncovered,
        # A mapping entry for an assumption the registry does not declare is
        # the same defect from the other side: a check that runs against
        # nothing, reported as coverage.
        "orphaned_mappings": orphan,
    }


def stress(fit: SC.SyntheticControlFit, treated: Sequence[float],
           donors: Dict[str, Sequence[float]], *,
           as_of: str = "") -> dict:
    """Run every attack, and return the diagnostics with a standing.

    The standing comes from `economic_method.interpret` over
    MethodAssumptionCheck rows, so it is the same ceiling every other surface
    reads. This function does not decide anything `interpret` could decide.
    """
    if not fit.fitted:
        return {
            "contract": CONTRACT,
            "status": INSUFFICIENT_FOR_DIAGNOSIS,
            "reason": (f"the fit was refused ({fit.status}); there is nothing "
                       "to attack, and a refusal is already its own finding"),
            "diagnostics": [],
            "checks": [],
            "standing": EM.REFUSED,
            "causal_reading_allowed": False,
        }

    diagnostics = [
        pre_trend(fit),
        common_shock(donors, treatment_index=fit.treatment_index),
        in_space_placebo(treated, donors,
                         treatment_index=fit.treatment_index, fit=fit),
        in_time_placebo(treated, donors,
                        treatment_index=fit.treatment_index, fit=fit),
        weight_concentration(fit),
    ]
    by_name = {d.name: d for d in diagnostics}

    checks: List[EM.MethodAssumptionCheck] = []
    for assumption, diagnostic_name in ASSUMPTION_DIAGNOSTICS.items():
        got = by_name[diagnostic_name]
        checks.append(EM.MethodAssumptionCheck(
            method=SC.SYNTHETIC_CONTROL, question=EM.EFFECT_OF_POLICY,
            assumption=assumption, severity=got.severity, result=got.result,
            evidence=got.evidence, series=fit.treated_unit,
            statistic=got.statistic, threshold=got.threshold, as_of=as_of))
    for assumption, why in UNTESTABLE_HERE.items():
        checks.append(EM.MethodAssumptionCheck(
            method=SC.SYNTHETIC_CONTROL, question=EM.EFFECT_OF_POLICY,
            assumption=assumption, severity=EM.CRITICAL, result=EM.UNTESTED,
            evidence=why, series=fit.treated_unit, as_of=as_of))

    reading = EM.interpret(checks)
    return {
        "contract": CONTRACT,
        "status": "DIAGNOSED",
        "diagnostics": [d.as_dict() for d in diagnostics],
        "checks": [c.as_dict() for c in checks],
        "standing": reading["standing"],
        "causal_reading_allowed": reading["causal_reading_allowed"],
        "why": reading["why"],
        "untestable_here": len(UNTESTABLE_HERE),
        "placebo_units_excluded": by_name["in_space_placebo"].excluded,
        "note": ("the standing is economic_method.interpret's, over the same "
                 "MethodAssumptionCheck rows the forecasting assumptions "
                 "produce; there is no second verdict vocabulary here"),
    }


def summarise(results: Sequence[dict]) -> dict:
    """Telemetry: the standing distribution, with every state present."""
    by_standing = {s: 0 for s in EM.STANDINGS}
    by_standing[INSUFFICIENT_FOR_DIAGNOSIS] = 0
    for got in results:
        key = got.get("standing") if got.get("status") == "DIAGNOSED" \
            else INSUFFICIENT_FOR_DIAGNOSIS
        by_standing[key] = by_standing.get(key, 0) + 1
    allowed = sum(1 for g in results if g.get("causal_reading_allowed"))
    return {
        "contract": CONTRACT,
        "diagnosed": len(results),
        "by_standing": by_standing,
        "causal_reading_allowed": allowed,
        "note": ("every standing is present at zero when it did not occur; a "
                 "distribution that omits its empty categories cannot report "
                 "that a category was empty"),
    }
