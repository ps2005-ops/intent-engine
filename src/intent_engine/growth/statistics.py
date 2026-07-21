"""Stdlib-only experiment statistics (T018).

The A3 wall stands: no new dependency. Everything here is computed with
the standard library, and anything that cannot be computed HONESTLY under
its own assumptions returns `UNAVAILABLE` with the failed assumption
named — never an approximation dressed up as a result.

Deliberately NOT implemented in V1 (and reported as founder decisions,
not silently omitted):

    p-values / null-hypothesis significance tests
    Bayesian posteriors or credible intervals
    sequential testing corrections (alpha spending, group sequential)
    variance reduction (CUPED) or adaptive allocation (Thompson sampling)

Those require a design review and, realistically, a declared numerical
dependency. Until then this module refuses to imply them: there is no
`p_value` field, no `significant` flag, and no `probability_better`.
"""
from __future__ import annotations

import math

from intent_engine.growth.records import STATUS_UNAVAILABLE

PROPORTION_STAT_VERSION = "diff_in_proportions.v1"
COUNTS_STAT_VERSION = "arm_counts.v1"

# Normal-approximation validity: the usual rule of thumb is at least this
# many expected successes AND failures per arm. Below it, the interval is
# not trustworthy, so it is not produced.
MIN_SUCCESSES_PER_ARM = 5
MIN_FAILURES_PER_ARM = 5

# 95% two-sided normal quantile, hard-coded because we do not ship a
# distribution library. Any other confidence level would require an
# inverse-CDF we cannot honestly provide with the stdlib.
_Z_95 = 1.959963984540054
SUPPORTED_CONFIDENCE = 0.95


def arm_counts(arm_id: str, *, assigned: int, exposed: int, observed: int,
               successes: int) -> dict:
    """Per-arm counts and an outcome rate. A rate with a zero denominator
    is UNAVAILABLE, never 0.0."""
    result = {
        "statistic_name": "arm_counts",
        "statistic_version": COUNTS_STAT_VERSION,
        "arm_id": arm_id,
        "assigned": assigned, "exposed": exposed, "observed": observed,
        "successes": successes,
        "assumptions": ["outcome successes are counted from observations "
                        "of the pre-registered primary metric only"],
        "assumption_check": "passed",
        "status": "OK",
        "rate": None,
        "reason": None,
    }
    if observed <= 0:
        result["status"] = STATUS_UNAVAILABLE
        result["reason"] = ("no observations for this arm — a rate cannot "
                            "honestly be computed (this is not a rate of 0)")
        return result
    result["rate"] = round(successes / observed, 6)
    return result


def difference_in_proportions(control: dict, treatment: dict,
                              confidence: float = SUPPORTED_CONFIDENCE) -> dict:
    """Point estimate of (treatment rate - control rate), with a normal
    -approximation interval ONLY when its assumptions hold.

    Returns a fully self-describing result: the assumptions, whether they
    passed, the version, and — when unavailable — exactly which assumption
    failed. There is no p-value and no significance flag by design.
    """
    assumptions = [
        f"independent observations within each arm",
        f"at least {MIN_SUCCESSES_PER_ARM} successes and "
        f"{MIN_FAILURES_PER_ARM} failures per arm (normal approximation)",
        f"confidence level {SUPPORTED_CONFIDENCE} (the only level this "
        "version can compute without a distribution library)",
    ]
    result = {
        "statistic_name": "difference_in_proportions",
        "statistic_version": PROPORTION_STAT_VERSION,
        "assumptions": assumptions,
        "assumption_check": "not_applicable",
        "status": STATUS_UNAVAILABLE,
        "point_estimate": None,
        "interval": None,
        "interval_excludes_zero": None,
        "confidence": confidence,
        "reason": None,
        "inputs": {"control": {k: control.get(k)
                               for k in ("arm_id", "observed", "successes")},
                   "treatment": {k: treatment.get(k)
                                 for k in ("arm_id", "observed", "successes")}},
    }

    if confidence != SUPPORTED_CONFIDENCE:
        result["reason"] = (f"confidence level {confidence} is not supported: "
                            "computing it would require an inverse normal CDF "
                            "this repository does not ship")
        return result

    n_c, x_c = control.get("observed", 0), control.get("successes", 0)
    n_t, x_t = treatment.get("observed", 0), treatment.get("successes", 0)
    if n_c <= 0 or n_t <= 0:
        result["reason"] = "an arm has no observations"
        return result

    p_c, p_t = x_c / n_c, x_t / n_t
    result["point_estimate"] = round(p_t - p_c, 6)

    failures = []
    for name, n, x in (("control", n_c, x_c), ("treatment", n_t, x_t)):
        if x < MIN_SUCCESSES_PER_ARM:
            failures.append(f"{name} has {x} successes "
                            f"(< {MIN_SUCCESSES_PER_ARM})")
        if (n - x) < MIN_FAILURES_PER_ARM:
            failures.append(f"{name} has {n - x} failures "
                            f"(< {MIN_FAILURES_PER_ARM})")
    if failures:
        result["assumption_check"] = "failed"
        result["reason"] = ("normal-approximation assumptions not met: "
                            + "; ".join(failures)
                            + " — the point estimate stands, the interval "
                              "does not")
        return result

    se = math.sqrt(p_c * (1 - p_c) / n_c + p_t * (1 - p_t) / n_t)
    if se == 0:
        result["assumption_check"] = "failed"
        result["reason"] = ("zero standard error (degenerate arms) — no "
                            "interval is meaningful")
        return result
    margin = _Z_95 * se
    low, high = (p_t - p_c) - margin, (p_t - p_c) + margin
    result.update(assumption_check="passed", status="OK",
                  interval=[round(low, 6), round(high, 6)],
                  interval_excludes_zero=bool(low > 0 or high < 0))
    return result


def unavailable(statistic_name: str, reason: str, version: str = "n/a") -> dict:
    return {"statistic_name": statistic_name, "statistic_version": version,
            "assumptions": [], "assumption_check": "not_applicable",
            "status": STATUS_UNAVAILABLE, "reason": reason}
