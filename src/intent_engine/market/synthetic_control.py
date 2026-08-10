"""What would have happened otherwise, for one treated unit, or a refusal.

WHY THIS FILE EXISTS
--------------------
`economic_method.METHODS` has declared SYNTHETIC_CONTROL since V4 with
`estimator=None`. `require` refuses it, correctly and loudly, which means every
EFFECT_OF_POLICY question this engine has ever been asked has either fallen
back to a method with weaker assumptions or gone unanswered. A registry entry
is not an implementation, and the registry says so about itself.

The question a synthetic control answers is the one an executive actually asks
about a policy, a launch or a shock: not "did the number move" but "did it move
more than it would have anyway". The counterfactual is built from units that
were NOT treated, weighted so that their weighted average reproduces the
treated unit's PRE-treatment path. If it does, the same weights carry forward
and the gap after treatment is the estimate.

THE ENTIRE METHOD IS THE PRE-PERIOD
-----------------------------------
Everything that can go wrong with a synthetic control goes wrong in the fit:

  * a donor pool that cannot reproduce the pre-period produces a synthetic
    unit that was never a good comparison, and the post-period gap is measuring
    that failure rather than the treatment;
  * one donor carrying almost all the weight is not a synthetic control, it is
    a bilateral comparison with extra steps, and it inherits every idiosyncrasy
    of that one unit;
  * a single post-treatment observation reaching the objective makes the fit
    partly explain the thing it is supposed to predict, and no diagnostic
    downstream can detect that afterwards.

So this module refuses rather than reports in each of those cases, and the
refusal names which one. `causal_diagnostics` then attacks whatever survives.

WHY THE WEIGHTS ARE ON A SIMPLEX
--------------------------------
Non-negative and summing to one. This is not a stylistic constraint: it is what
stops the fit from extrapolating. Unrestricted least squares over a donor pool
will happily produce a synthetic unit that is 3.1 times one donor minus 2.1
times another — a combination that lies outside anything ever observed, fits
the pre-period beautifully, and means nothing. Restricted to the simplex, the
synthetic unit is always a weighted average of real units and the fit can fail
VISIBLY when the treated unit lies outside the donors' range. A method that
cannot fail is not measuring anything.

The solver is Frank-Wolfe, which stays on the simplex by construction rather
than projecting back onto it after each step, and is deterministic — the same
inputs give the same weights on every run, which matters because these weights
are persisted and later compared against a reload.

NO NUMPY
--------
Nothing in `src/` imports numpy and this file does not start. The arithmetic
here is a few hundred multiply-adds on series of tens of points.
"""
from __future__ import annotations

import dataclasses
import hashlib
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

CONTRACT = "synthetic_control.v1"

#: Method names, matching `economic_method`. Imported by name rather than from
#: that module to keep the dependency one-directional: economic_method binds
#: this module's estimator, so this module importing it would be a cycle.
SYNTHETIC_CONTROL = "SYNTHETIC_CONTROL"
SYNTHETIC_DID = "SYNTHETIC_DID"

# --- refusals ------------------------------------------------------------------
#
# Each of these is a distinct thing that went wrong and a distinct thing the
# caller might do about it. A single boolean would collapse "your donor pool is
# too small" and "your donor pool is fine and does not resemble you", and only
# the second of those is a finding about the world.

REFUSED_SHORT_PRE_PERIOD = "REFUSED_SHORT_PRE_PERIOD"
REFUSED_NO_DONORS = "REFUSED_NO_DONORS"
REFUSED_RAGGED_PANEL = "REFUSED_RAGGED_PANEL"
REFUSED_NO_DONOR_SUPPORT = "REFUSED_NO_DONOR_SUPPORT"
REFUSED_POOR_PRE_FIT = "REFUSED_POOR_PRE_FIT"
REFUSED_DEGENERATE_WEIGHTS = "REFUSED_DEGENERATE_WEIGHTS"
REFUSALS = (REFUSED_SHORT_PRE_PERIOD, REFUSED_NO_DONORS, REFUSED_RAGGED_PANEL,
            REFUSED_NO_DONOR_SUPPORT, REFUSED_POOR_PRE_FIT,
            REFUSED_DEGENERATE_WEIGHTS)

FITTED = "FITTED"


class LeakageError(AssertionError):
    """A post-treatment observation reached the fitting objective.

    Deliberately not a refusal and deliberately not a warning. A refusal is a
    result — the caller records it and moves on. This is a programming error in
    the caller, it invalidates every number the fit would produce, and it is
    undetectable in the output: a leaked fit looks BETTER than a clean one.
    Raising is the only response that cannot be ignored by accident.
    """


#: Below this many pre-treatment observations there is nothing to fit. Eight is
#: not a statistical threshold, it is the point below which the weights are
#: determined by noise and the pre-fit RMSPE stops being informative about
#: anything. Stated as a constant so a caller can disagree with the number
#: rather than with the idea.
MINIMUM_PRE_PERIOD = 8

#: Pre-treatment fit worse than this multiple of the treated unit's own
#: pre-period variation means the donors do not reproduce the unit. Expressed
#: as a RATIO rather than in the outcome's units so it transfers between a
#: series measured in percent and one measured in millions.
MAXIMUM_PRE_RMSPE_RATIO = 0.30

#: A single donor above this weight is a bilateral comparison. Not fatal on its
#: own — sometimes one unit really is the right comparison — so this bounds the
#: reading rather than refusing it, and `causal_diagnostics` decides.
CONCENTRATION_WARN = 0.80

#: Above this, it is no longer a weighted average of anything.
CONCENTRATION_REFUSE = 0.95


@dataclass(frozen=True)
class DonorWeight:
    """One donor and how much of the synthetic unit it is."""

    unit: str
    weight: float

    def as_dict(self) -> dict:
        return {"unit": self.unit, "weight": round(self.weight, 6)}


@dataclass(frozen=True)
class SyntheticControlFit:
    """A fitted counterfactual, or a refusal, with the reason either way.

    A refusal carries `status` in REFUSALS, `weights` empty, and every
    estimate field None. There is no partially-fitted state: a caller reading
    `effect` on a refused fit gets None, not a zero, because a zero effect and
    an absent estimate are different claims and only the first is a finding.
    """

    treated_unit: str
    method: str
    status: str
    treatment_index: int
    pre_periods: int
    post_periods: int
    donors_offered: int
    weights: Tuple[DonorWeight, ...] = ()
    pre_rmspe: Optional[float] = None
    treated_pre_variation: Optional[float] = None
    pre_fit_ratio: Optional[float] = None
    average_effect: Optional[float] = None
    effect_path: Tuple[float, ...] = ()
    synthetic_path: Tuple[float, ...] = ()
    refusal_detail: str = ""
    as_of: str = ""
    #: Set by SDID. Empty for plain synthetic control, and empty is the honest
    #: value: plain SCM weights every pre-period equally by construction, so a
    #: uniform vector here would claim a choice that was never made.
    time_weights: Tuple[float, ...] = ()

    @property
    def fitted(self) -> bool:
        return self.status == FITTED

    @property
    def contributing_donors(self) -> Tuple[DonorWeight, ...]:
        """Donors that are actually in the synthetic unit.

        Reported rather than the full weight vector because a pool of forty
        donors of which three matter is a different object from a pool of three
        — and printing forty rows, thirty-seven of them 0.000000, hides that.
        """
        return tuple(w for w in self.weights if w.weight > 1e-6)

    @property
    def concentration(self) -> Optional[float]:
        """The largest single donor weight, or None when there is no fit."""
        if not self.weights:
            return None
        return max(w.weight for w in self.weights)

    @property
    def fit_id(self) -> str:
        raw = "|".join((self.treated_unit, self.method,
                        str(self.treatment_index), self.as_of))
        return "scm_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def as_dict(self) -> dict:
        out = dataclasses.asdict(self)
        out["weights"] = [w.as_dict() for w in self.weights]
        out["effect_path"] = [round(v, 6) for v in self.effect_path]
        out["synthetic_path"] = [round(v, 6) for v in self.synthetic_path]
        out["time_weights"] = [round(v, 6) for v in self.time_weights]
        out.update(contract=CONTRACT, record="causal_estimate",
                   fit_id=self.fit_id, fitted=self.fitted,
                   concentration=self.concentration,
                   contributing_donors=[w.as_dict()
                                        for w in self.contributing_donors])
        return out


def load_estimate(row: dict) -> SyntheticControlFit:
    """Rebuild a fit from its persisted row.

    The round trip is asserted by test rather than assumed, because this
    program has repeatedly shipped a producer and a reader that agreed on a
    field name and disagreed on its shape — a dict where an object was
    expected, a getattr-only reader folding a whole ledger into one event.
    Fields the row does not carry are absent here too; they are never
    defaulted, because a defaulted weight vector reads as a fit.
    """
    known = {f.name for f in dataclasses.fields(SyntheticControlFit)}
    kwargs = {k: v for k, v in row.items() if k in known}
    kwargs["weights"] = tuple(
        DonorWeight(unit=w["unit"], weight=float(w["weight"]))
        for w in (row.get("weights") or ()))
    for key in ("effect_path", "synthetic_path", "time_weights"):
        kwargs[key] = tuple(float(v) for v in (row.get(key) or ()))
    return SyntheticControlFit(**kwargs)


# --- the solver ----------------------------------------------------------------

def _rmspe(residuals: Sequence[float]) -> float:
    if not residuals:
        return 0.0
    return math.sqrt(sum(r * r for r in residuals) / len(residuals))


def _variation(values: Sequence[float]) -> float:
    """Root mean squared deviation from the mean.

    The denominator of the pre-fit ratio. Using the mean rather than the level
    matters: a series sitting at 100 with a standard deviation of 0.2 is a very
    demanding target, and scaling the tolerance by the LEVEL would call a
    hopeless fit acceptable on it.
    """
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    return math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))


def assert_pre_treatment_only(pre_treated: Sequence[float],
                              pre_donors: Sequence[Sequence[float]],
                              treatment_index: int) -> None:
    """Every series entering the objective stops before the treatment.

    PUBLIC, AND CALLED BY EVERY FITTER RATHER THAN BY THE PANEL VALIDATOR.
    An earlier version of this check sat inside `fit`, downstream of the
    ragged-panel refusal, where nothing could reach it — the panel check
    already rejected a mis-sliced input, so the leakage guard was unreachable
    code with a test that could not fail. That is the same defect this program
    has recorded before under its own name.

    Here it guards the *objective*, which is the thing that must never see a
    post-treatment value, and it is called by `fit` and by `fit_sdid` on the
    slices they are about to optimise over. A future fitter that builds its
    slices differently — a rolling window, a donor-specific truncation, a
    caller passing pre-sliced input — trips it.

    Raises rather than refuses. A refusal is a result the caller records and
    moves on from; this is a programming error that invalidates every number
    the fit would produce and is invisible in the output, because a leaked fit
    scores BETTER on every downstream diagnostic than a clean one.
    """
    if len(pre_treated) != treatment_index:
        raise LeakageError(
            f"the treated pre-period slice has {len(pre_treated)} "
            f"observations for a treatment index of {treatment_index}; the "
            "objective would see an outcome it is meant to predict")
    for j, series in enumerate(pre_donors):
        if len(series) != treatment_index:
            raise LeakageError(
                f"donor {j} contributes {len(series)} observations to a "
                f"pre-period of {treatment_index}; the objective would see "
                "post-treatment data")


def _frank_wolfe(target: Sequence[float], donors: Sequence[Sequence[float]],
                 *, iterations: int = 500) -> List[float]:
    """Least squares over the unit simplex, without ever leaving it.

    Starts at the vertex of the single best donor and moves toward whichever
    vertex the gradient favours, by a step that shrinks as 2/(k+2). Every
    iterate is a convex combination of vertices, so non-negativity and the
    sum-to-one constraint hold at every step rather than being restored by a
    projection afterwards.

    Deterministic by construction: no random restarts, no tie-breaking on
    anything but index order. These weights are persisted and later compared
    against a reload, so a solver that could return a different optimum on a
    second call would make that comparison meaningless.
    """
    n = len(donors)
    periods = len(target)

    # Start from the best single donor rather than the uniform point. Both
    # converge; this one starts closer when the answer really is one donor,
    # which is the case a uniform start takes longest to reach and the case
    # the concentration check most needs to see clearly.
    best, best_error = 0, None
    for j, donor in enumerate(donors):
        error = sum((target[t] - donor[t]) ** 2 for t in range(periods))
        if best_error is None or error < best_error:
            best, best_error = j, error
    weights = [0.0] * n
    weights[best] = 1.0

    for _ in range(iterations):
        fitted = [sum(weights[j] * donors[j][t] for j in range(n))
                  for t in range(periods)]
        residual = [target[t] - fitted[t] for t in range(periods)]
        # d/dw_j of sum(residual^2) is -2 * sum(residual_t * donor_jt); the
        # factor of two is common to every component and cannot change which
        # component is smallest, so it is left out.
        gradient = [-sum(residual[t] * donors[j][t] for t in range(periods))
                    for j in range(n)]
        j_star = min(range(n), key=lambda j: (gradient[j], j))

        # EXACT LINE SEARCH, NOT THE 2/(k+2) SCHEDULE. The textbook step size
        # is what this used first, and on the fixture whose answer is known by
        # construction — a unit that IS 0.6 of one donor and 0.4 of another —
        # five hundred iterations returned 0.547/0.431 and left 2% of the
        # weight on a donor two orders of magnitude away in scale. The
        # linear subproblem favours large-magnitude donors whenever the
        # residual sums positive, and a step size that ignores the data cannot
        # undo that quickly: late iterations shrink old mass by a factor of
        # only (1 - 2/(k+2)).
        #
        # Minimising exactly along the segment costs one more pass over the
        # series and converges in tens of iterations instead of thousands. It
        # is still Frank-Wolfe and gamma is still confined to [0, 1], so every
        # iterate is still a convex combination of real units.
        direction = [donors[j_star][t] - fitted[t] for t in range(periods)]
        denominator = sum(d * d for d in direction)
        if denominator <= 1e-18:
            # The chosen vertex is already where we are. Nothing to move
            # toward, and dividing here would be dividing by zero.
            break
        gamma = sum(residual[t] * direction[t]
                    for t in range(periods)) / denominator
        gamma = min(1.0, max(0.0, gamma))
        if gamma <= 1e-15:
            # A zero step at the optimum of the linear subproblem is the
            # Frank-Wolfe stopping condition; further iterations cannot move.
            break
        for j in range(n):
            weights[j] *= (1.0 - gamma)
        weights[j_star] += gamma

    total = sum(weights)
    if total <= 0:
        # Unreachable from the simplex, and asserted rather than silently
        # renormalised: a zero-sum weight vector would mean the iteration left
        # the feasible set, which is a bug in this function and not a property
        # of the data.
        raise AssertionError("Frank-Wolfe left the simplex")
    return [w / total for w in weights]


# --- the fit -------------------------------------------------------------------

def fit(treated: Sequence[float], donors: Dict[str, Sequence[float]], *,
        treatment_index: int, treated_unit: str = "", as_of: str = "",
        minimum_pre_period: int = MINIMUM_PRE_PERIOD,
        maximum_pre_rmspe_ratio: float = MAXIMUM_PRE_RMSPE_RATIO
        ) -> SyntheticControlFit:
    """Fit a synthetic control, or refuse with the reason.

    `treatment_index` is the first POST-treatment position: everything strictly
    before it is the pre-period the weights are fitted on, and everything from
    it onward is out of sample for the fit. The partition is enforced here
    rather than trusted to the caller, for the same reason `walk_forward`
    enforces its split in `economic_method` — in-sample scoring is the easiest
    way to make a method look good and it leaves no trace in the output.
    """
    treated = [float(v) for v in treated]
    names = sorted(donors)
    pool = [[float(v) for v in donors[name]] for name in names]

    def refuse(status: str, detail: str) -> SyntheticControlFit:
        return SyntheticControlFit(
            treated_unit=treated_unit, method=SYNTHETIC_CONTROL, status=status,
            treatment_index=treatment_index,
            pre_periods=max(treatment_index, 0),
            post_periods=max(len(treated) - treatment_index, 0),
            donors_offered=len(names), refusal_detail=detail, as_of=as_of)

    if not names:
        return refuse(REFUSED_NO_DONORS,
                      "a synthetic control needs units that were not treated; "
                      "none were offered")
    ragged = [name for name, series in zip(names, pool)
              if len(series) != len(treated)]
    if ragged:
        # A ragged panel is refused rather than truncated. Truncating to the
        # shortest donor silently changes which periods the fit saw, and the
        # output would not record that it had happened.
        return refuse(
            REFUSED_RAGGED_PANEL,
            f"{len(ragged)} donor(s) have a different length from the treated "
            f"series ({len(treated)}): {', '.join(ragged[:5])}")
    if treatment_index < minimum_pre_period:
        return refuse(
            REFUSED_SHORT_PRE_PERIOD,
            f"{treatment_index} pre-treatment observation(s) against a floor "
            f"of {minimum_pre_period}; below it the weights are fitted on "
            "noise and the pre-fit statistic stops being informative")
    if treatment_index >= len(treated):
        return refuse(
            REFUSED_SHORT_PRE_PERIOD,
            f"treatment index {treatment_index} leaves no post-treatment "
            f"observation in a series of {len(treated)}")

    pre_treated = treated[:treatment_index]
    pre_donors = [series[:treatment_index] for series in pool]

    assert_pre_treatment_only(pre_treated, pre_donors, treatment_index)
    weights = _frank_wolfe(pre_treated, pre_donors)

    synthetic_pre = [sum(weights[j] * pre_donors[j][t]
                         for j in range(len(names)))
                     for t in range(treatment_index)]
    pre_residual = [pre_treated[t] - synthetic_pre[t]
                    for t in range(treatment_index)]
    pre_rmspe = _rmspe(pre_residual)
    variation = _variation(pre_treated)

    if variation <= 1e-12:
        # A flat treated pre-period. Any donor reproduces it, the ratio is
        # undefined, and a fit here says nothing about donor support. Refused
        # rather than divided by zero.
        return refuse(
            REFUSED_NO_DONOR_SUPPORT,
            "the treated unit does not move in the pre-period, so no donor "
            "pool can be shown to track it and a good fit would be vacuous")

    ratio = pre_rmspe / variation
    concentration = max(weights)

    if ratio > maximum_pre_rmspe_ratio:
        return dataclasses.replace(
            refuse(REFUSED_POOR_PRE_FIT,
                   f"pre-treatment RMSPE {pre_rmspe:.6g} is {ratio:.1%} of the "
                   f"treated unit's own pre-period variation {variation:.6g}, "
                   f"above {maximum_pre_rmspe_ratio:.0%}; the donor pool does "
                   "not reproduce this unit and the post-period gap would be "
                   "measuring that, not the treatment"),
            weights=tuple(DonorWeight(unit=n, weight=w)
                          for n, w in zip(names, weights)),
            pre_rmspe=round(pre_rmspe, 6),
            treated_pre_variation=round(variation, 6),
            pre_fit_ratio=round(ratio, 6))

    if concentration >= CONCENTRATION_REFUSE:
        carrier = names[weights.index(concentration)]
        return dataclasses.replace(
            refuse(REFUSED_DEGENERATE_WEIGHTS,
                   f"donor {carrier!r} carries {concentration:.1%} of the "
                   "weight; this is a bilateral comparison with one unit and "
                   "inherits everything idiosyncratic about it, so calling it "
                   "a synthetic control would overstate what was built"),
            weights=tuple(DonorWeight(unit=n, weight=w)
                          for n, w in zip(names, weights)),
            pre_rmspe=round(pre_rmspe, 6),
            treated_pre_variation=round(variation, 6),
            pre_fit_ratio=round(ratio, 6))

    synthetic_full = [sum(weights[j] * pool[j][t] for j in range(len(names)))
                      for t in range(len(treated))]
    effect_path = [treated[t] - synthetic_full[t] for t in range(len(treated))]
    post = effect_path[treatment_index:]
    average = sum(post) / len(post) if post else None

    return SyntheticControlFit(
        treated_unit=treated_unit, method=SYNTHETIC_CONTROL, status=FITTED,
        treatment_index=treatment_index, pre_periods=treatment_index,
        post_periods=len(treated) - treatment_index,
        donors_offered=len(names),
        weights=tuple(DonorWeight(unit=n, weight=w)
                      for n, w in zip(names, weights)),
        pre_rmspe=round(pre_rmspe, 6),
        treated_pre_variation=round(variation, 6),
        pre_fit_ratio=round(ratio, 6),
        average_effect=round(average, 6) if average is not None else None,
        effect_path=tuple(effect_path),
        synthetic_path=tuple(synthetic_full),
        as_of=as_of)


def estimator(treated: Sequence[float], donors: Dict[str, Sequence[float]],
              *, treatment_index: int, **kwargs) -> Optional[float]:
    """The callable `economic_method` binds, returning the average effect.

    Returns None on a refusal rather than raising, because the registry's
    contract is that a method produces a number or does not, and the refusal
    with its reason is available from `fit` to any caller that wants it. A
    caller that only wants the number gets None, which is not zero.
    """
    got = fit(treated, donors, treatment_index=treatment_index, **kwargs)
    return got.average_effect if got.fitted else None


def summarise(fits: Sequence[SyntheticControlFit]) -> dict:
    """Telemetry: attempts and refusals by reason.

    Every state is present in the mapping whether or not it occurred, so a
    reason that never fires reads as zero-of-a-known-category rather than as a
    missing key. A counter that can only appear when it is non-zero cannot
    report that nothing happened.
    """
    by_status = {status: 0 for status in (FITTED,) + REFUSALS}
    for got in fits:
        by_status[got.status] = by_status.get(got.status, 0) + 1
    fitted = [f for f in fits if f.fitted]
    concentrated = [f for f in fitted
                    if (f.concentration or 0) >= CONCENTRATION_WARN]
    return {
        "contract": CONTRACT,
        "attempted": len(fits),
        "fitted": len(fitted),
        "refused": len(fits) - len(fitted),
        "by_status": by_status,
        "concentrated_fits": len(concentrated),
        "concentration_warn": CONCENTRATION_WARN,
        "note": ("every refusal reason is present at zero when it did not "
                 "occur; a reason that appears only when it fires cannot "
                 "report that it did not"),
    }
