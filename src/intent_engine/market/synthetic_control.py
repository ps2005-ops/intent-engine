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

The solver is an active set over that simplex: it decides which donors carry
weight and solves exactly on them, terminating AT the optimum rather than
approaching it. Three descent methods were tried first and each returned the
wrong donors on a realistic pool; `_simplex_least_squares` records what they
returned and why it mattered. It is deterministic — the same inputs give the
same weights on every run — which matters because these weights are persisted
and later compared against a reload.

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


def _least_squares(columns: Sequence[Sequence[float]],
                   target: Sequence[float]) -> Optional[List[float]]:
    """Unconstrained least squares by modified Gram-Schmidt.

    NOT THE NORMAL EQUATIONS, AND THE DIFFERENCE WAS VISIBLE HERE.
    Forming A-transpose-A squares the condition number. That is usually a
    textbook caution and here it was the bug: the sum-to-one constraint is
    imposed by an appended row of a large constant, so the matrix is
    deliberately ill-conditioned, and squaring took it past what a float64
    can carry. On a three-donor problem whose exact answer is 0.6/0.4/0.0 the
    normal-equations solve returned 0.571/0.429/0.00003 — the constraint row
    dominated every inner product and the actual data was rounding error
    inside it.

    Orthogonalising the columns instead keeps the conditioning linear, and the
    same problem comes back exact. A rank-deficient set returns None rather
    than a pseudo-inverse: the caller drops the offending column, which is
    what the active set is for.
    """
    k = len(columns)
    if k == 0:
        return []
    m = len(target)
    basis: List[List[float]] = []
    upper = [[0.0] * k for _ in range(k)]
    for j in range(k):
        vector = list(columns[j])
        for i in range(j):
            projection = sum(basis[i][t] * vector[t] for t in range(m))
            upper[i][j] = projection
            for t in range(m):
                vector[t] -= projection * basis[i][t]
        norm = math.sqrt(sum(v * v for v in vector))
        reference = math.sqrt(sum(v * v for v in columns[j])) or 1.0
        if norm <= 1e-10 * reference:
            return None
        upper[j][j] = norm
        basis.append([v / norm for v in vector])

    projected = [sum(basis[i][t] * target[t] for t in range(m))
                 for i in range(k)]
    solution = [0.0] * k
    for i in range(k - 1, -1, -1):
        total = projected[i] - sum(upper[i][j] * solution[j]
                                   for j in range(i + 1, k))
        solution[i] = total / upper[i][i]
    return solution


def _least_squares_summing_to_one(columns: Sequence[Sequence[float]],
                                  target: Sequence[float]
                                  ) -> Optional[List[float]]:
    """Least squares over one set of columns, constrained to sum to one.

    THE CONSTRAINT IS SUBSTITUTED, NOT PENALISED.
    The version before this appended a row of a large constant M so that any
    deviation from a unit sum cost M squared. That is the standard trick and
    it was measurably wrong here: the penalty is exactly what makes the matrix
    ill-conditioned, so accuracy fought itself. Sweeping M over four orders of
    magnitude on a problem whose answer is known gave weight errors of 5.6e-6
    at 1e4, 1.3e-3 at 1e5, and a rank-deficient refusal at 1e7 — worse as the
    constraint got tighter, which is the signature of conditioning beating
    bias.

    Eliminating the last weight algebraically removes the constraint instead
    of approximating it. With w_last = 1 - sum(rest), the objective becomes an
    ORDINARY least squares in one fewer variable on the differenced columns,
    and the answer is exact to machine precision with no constant to tune.
    """
    k = len(columns)
    if k == 0:
        return []
    if k == 1:
        return [1.0]
    m = len(target)
    last = columns[-1]
    differenced = [[columns[j][t] - last[t] for t in range(m)]
                   for j in range(k - 1)]
    shifted = [target[t] - last[t] for t in range(m)]
    rest = _least_squares(differenced, shifted)
    if rest is None:
        return None
    return list(rest) + [1.0 - sum(rest)]


def _simplex_least_squares(target: Sequence[float],
                           donors: Sequence[Sequence[float]]) -> List[float]:
    """Non-negative weights summing to one, at the exact optimum.

    WHY AN ACTIVE SET AND NOT A DESCENT METHOD
    ------------------------------------------
    Three solvers were written and measured before this one, and each was
    wrong on real donor pools rather than merely imprecise.

    Frank-Wolfe with the textbook 2/(k+2) schedule returned 0.547/0.431 where
    the answer was 0.6/0.4. Exact line search fixed that and failed harder on
    a pool built the way a real one is — donors driven by shared factors, so
    nearly collinear — returning 0.276/0.086/0.638 for a true 0.5/0.3/0.2.
    Adding away steps reached the answer only after fifty thousand iterations,
    which at sixteen placebo refits per diagnostic is not a solver but a delay.

    That mattered beyond accuracy, in two places. The weights ARE the product:
    `contributing_donors` is what a reader is shown as the units making up the
    synthetic control, and 0.276/0.086/0.638 names the wrong units. And the
    residual the solver left behind was divided into by
    `causal_diagnostics.effect_ratio`, which turned solver error into a
    post-over-pre ratio of a thousand and ranked it first in every placebo
    distribution it entered.

    An active set terminates AT the optimum in finitely many steps instead of
    approaching it. Each step solves an equality-constrained least squares on
    the currently-supported donors, which has a closed form; the loop only has
    to decide which donors are in the support. It is deterministic, which
    matters because these weights are persisted and later compared against a
    reload.

    THE OPTIMALITY CONDITION
    ------------------------
    For a minimum over the simplex, the gradient must be EQUAL across every
    donor carrying weight and no smaller anywhere else. A donor outside the
    support whose gradient is lower would reduce the error if admitted, so it
    is admitted; when none is, the point is optimal. That is the whole loop.
    """
    n = len(donors)
    if n == 0:
        return []
    m = len(target)
    scale = max((abs(v) for col in donors for v in col), default=1.0) or 1.0
    tolerance = 1e-9 * scale * scale * max(m, 1)

    def gradients(weights):
        fitted = [sum(weights[j] * donors[j][t] for j in range(n))
                  for t in range(m)]
        resid = [target[t] - fitted[t] for t in range(m)]
        # The gradient of the squared error in w_j is -2*sum(resid * x_j); the
        # factor of two is common to every donor and cannot change any
        # comparison between them.
        return [-sum(resid[t] * donors[j][t] for t in range(m))
                for j in range(n)]

    best = min(range(n), key=lambda j: (sum((target[t] - donors[j][t]) ** 2
                                            for t in range(m)), j))
    weights = [0.0] * n
    weights[best] = 1.0
    support = [best]

    for _ in range(4 * n + 16):
        grad = gradients(weights)
        inside = sum(grad[j] for j in support) / len(support)
        outside = [j for j in range(n)
                   if j not in support and grad[j] < inside - tolerance]
        if not outside:
            break
        support.append(min(outside, key=lambda j: (grad[j], j)))

        # Walk toward the unconstrained optimum on this support, stopping at
        # the first donor that would go negative, until the whole support is
        # feasible. Dropping donors one at a time rather than all at once
        # keeps every intermediate point on the simplex.
        for _ in range(n + 1):
            trial = _least_squares_summing_to_one(
                [donors[j] for j in support], target)
            if trial is None:
                support.pop()
                break
            if all(v >= -1e-12 for v in trial):
                weights = [0.0] * n
                for j, v in zip(support, trial):
                    weights[j] = max(v, 0.0)
                break
            step = min((weights[j] / (weights[j] - v)
                        for j, v in zip(support, trial)
                        if v < 0 and weights[j] != v), default=0.0)
            moved = [0.0] * n
            for j, v in zip(support, trial):
                moved[j] = weights[j] + step * (v - weights[j])
            weights = moved
            support = [j for j in support if weights[j] > 1e-12]
            if not support:
                support = [best]
                weights = [0.0] * n
                weights[best] = 1.0
                break

    total = sum(weights)
    if total <= 0:  # pragma: no cover - the support always holds one donor
        weights = [0.0] * n
        weights[best] = 1.0
        return weights
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
    weights = _simplex_least_squares(pre_treated, pre_donors)

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
