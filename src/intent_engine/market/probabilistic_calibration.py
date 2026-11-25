"""Score the engine's probability forecasts with a proper scoring rule.

WHY THIS EXISTS
---------------
`learning_health` reported a field called `expectation_calibration` whose value
was `confirmed / resolved`. That is a **hit rate**, not a calibration. The two
answer different questions and can point opposite ways:

- A hit rate asks *how often was the engine right*. Predict "demand
  strengthens" for every company in a rising market and the hit rate is
  excellent while the forecast carries no information at all.
- Calibration asks *when the engine said 0.59, did it happen 59% of the time*.
  That is a claim about the probability itself, and it is the only one of the
  two that can tell you the number means anything.

Displaying the first under the name of the second made a 0.72 hit rate read as
evidence of a calibrated model. Measured on the live ledger the moment a proper
score was finally computed: Brier 0.2138 against a climatology baseline of
0.2021, i.e. **negative skill** -- the engine's probabilities were worse than
always predicting the base rate. The hit rate had been 0.72 throughout.

WHAT IS SCORED, AND WHY THAT PAIRING
------------------------------------
One `belief_update` row carries both halves of a forecast-outcome pair: the
`prior` is the probability the engine held *before* the observation arrived,
and `direction` is what the observation did to it. Both are written in the same
row at reconciliation time.

That pairing is deliberate. Joining `reconciliation` outcomes to `belief` rows
by id would be a second source of truth for the same fact, and the belief rows
are formation snapshots in an append-only ledger -- their `posterior` is the
opening value, not the value that was standing when the test landed. A join
would silently score the wrong prior.

WHY A BASELINE IS MANDATORY
---------------------------
A Brier score alone is unreadable: 0.21 is good for a coin and poor for a
weather model. The reference here is **climatology** -- always predicting the
observed base rate. Beating it is the minimum bar for a probability to carry
information beyond "things usually go this way". `brier_skill` is reported
against that, never in isolation.

WHEN THIS REFUSES TO ANSWER
---------------------------
Two distinct refusals, because they are different findings:

- `PRE_CALIBRATION` -- too few resolved outcomes. A reliability curve over six
  points is a drawing, not a measurement.
- `NO_DISCRIMINATION` -- enough outcomes, but the forecasts barely vary. A
  near-constant probability cannot be calibrated across bins: every prediction
  lands in one bucket, so the curve has one point and tells you nothing about
  the model's ability to separate cases. This is reported *with* the Brier
  score rather than instead of it, because the score is still valid -- it is
  the reliability *diagram* that is not.
"""
from __future__ import annotations

import collections
import math
import statistics
from typing import Dict, List, Sequence, Tuple

CONTRACT = "probabilistic_calibration.v1"

#: Below this many resolved outcomes no proper score is reported. A Brier on a
#: handful of points moves more with one outcome than with the model.
MIN_RESOLVED_FOR_PROPER_SCORE = 20

#: Standard deviation of the forecast distribution below which the model is
#: emitting what is effectively one number. Not a tuned threshold -- it is one
#: percentage point of probability, beneath which the bins cannot differ.
MIN_FORECAST_SPREAD = 0.01

#: Width of a reliability bin. Ten bins over [0, 1] is the convention and is
#: coarse enough that a bin can hold more than one observation at these volumes.
BIN_WIDTH = 0.10

#: Returned in place of a skill number when the climatology baseline is
#: perfect (every outcome identical), where the ratio is a division by zero.
UNDEFINED_PERFECT_BASELINE = "UNDEFINED_PERFECT_BASELINE"

PRE_CALIBRATION = "PRE_CALIBRATION"
NO_DISCRIMINATION = "NO_DISCRIMINATION"
MEASURED = "MEASURED"

STRENGTHENED = "STRENGTHENED"


def pairs_from_updates(updates: Sequence[dict]
                       ) -> Tuple[Tuple[float, int], ...]:
    """(forecast probability, realised outcome) for every scorable update.

    A row is scorable only if it carries a numeric `prior` and a direction this
    module can read as a binary outcome. Anything else is skipped rather than
    defaulted -- a missing prior scored as 0.5 would invent a forecast the
    engine never made.
    """
    out: List[Tuple[float, int]] = []
    for row in updates:
        prior = row.get("prior")
        direction = row.get("direction")
        if not isinstance(prior, (int, float)):
            continue
        if direction not in (STRENGTHENED, "WEAKENED"):
            continue
        out.append((float(prior), 1 if direction == STRENGTHENED else 0))
    return tuple(out)


def _brier(pairs: Sequence[Tuple[float, int]]) -> float:
    return sum((p - o) ** 2 for p, o in pairs) / len(pairs)


def _log_loss(pairs: Sequence[Tuple[float, int]]) -> float:
    eps = 1e-9
    total = 0.0
    for p, o in pairs:
        p = min(max(p, eps), 1 - eps)
        total -= o * math.log(p) + (1 - o) * math.log(1 - p)
    return total / len(pairs)


def reliability(pairs: Sequence[Tuple[float, int]]) -> Tuple[dict, ...]:
    """Observed frequency against forecast probability, by bin.

    Bins with no observations are omitted rather than reported as zero: an
    empty bin means the engine never made a forecast in that range, which is
    not the same as making one and being wrong.
    """
    buckets: Dict[int, List[Tuple[float, int]]] = collections.defaultdict(list)
    for p, o in pairs:
        buckets[min(int(p / BIN_WIDTH), int(1 / BIN_WIDTH) - 1)].append((p, o))
    rows = []
    for idx in sorted(buckets):
        items = buckets[idx]
        mean_forecast = sum(p for p, _ in items) / len(items)
        observed = sum(o for _, o in items) / len(items)
        rows.append({
            "bin_lower": round(idx * BIN_WIDTH, 2),
            "bin_upper": round((idx + 1) * BIN_WIDTH, 2),
            "n": len(items),
            "mean_forecast": round(mean_forecast, 4),
            "observed_frequency": round(observed, 4),
            "gap": round(observed - mean_forecast, 4),
        })
    return tuple(rows)


def score(pairs: Sequence[Tuple[float, int]]) -> dict:
    """Proper scores plus the baseline that makes them readable.

    Always returns a `status` and a `because`. A caller must not infer "no
    calibration problem" from a missing number -- see the two refusals in the
    module docstring.
    """
    n = len(pairs)
    if n < MIN_RESOLVED_FOR_PROPER_SCORE:
        return {
            "contract": CONTRACT,
            "status": PRE_CALIBRATION,
            "n": n,
            "minimum_n": MIN_RESOLVED_FOR_PROPER_SCORE,
            "because": (
                f"{n} resolved probability forecasts on record; "
                f"{MIN_RESOLVED_FOR_PROPER_SCORE} is the minimum at which a "
                f"proper score stops moving more with one outcome than with "
                f"the model"),
        }

    base_rate = sum(o for _, o in pairs) / n
    forecasts = [p for p, _ in pairs]
    spread = statistics.pstdev(forecasts) if n > 1 else 0.0

    brier = _brier(pairs)
    brier_climatology = _brier([(base_rate, o) for _, o in pairs])
    log_loss = _log_loss(pairs)
    log_loss_climatology = _log_loss([(base_rate, o) for _, o in pairs])

    # Skill is the fractional reduction in loss against climatology. Positive
    # means the forecast carried information the base rate did not.
    #
    # DEGENERATE BASELINE: when every outcome is identical, climatology
    # predicts it exactly and scores a perfect 0. The ratio is then a division
    # by zero, and returning 0.0 for it would be the worst available answer --
    # it reads as "no better and no worse than the baseline" for a model that
    # is strictly worse. There is no finite skill number here, so say so.
    degenerate = brier_climatology == 0
    brier_skill = (UNDEFINED_PERFECT_BASELINE if degenerate
                   else 1 - brier / brier_climatology)
    log_loss_skill = (UNDEFINED_PERFECT_BASELINE if not log_loss_climatology
                      else 1 - log_loss / log_loss_climatology)

    discriminating = spread >= MIN_FORECAST_SPREAD
    status = MEASURED if discriminating else NO_DISCRIMINATION
    because = (
        "forecast probabilities vary enough for a reliability curve to mean "
        "something" if discriminating else
        f"the {n} forecasts span only {max(forecasts) - min(forecasts):.3f} "
        f"of probability (sd {spread:.4f}); the Brier score below is valid "
        f"but the reliability curve is one bin and cannot show "
        f"discrimination")

    return {
        "contract": CONTRACT,
        "status": status,
        "n": n,
        "base_rate": round(base_rate, 4),
        "brier": round(brier, 4),
        "brier_climatology": round(brier_climatology, 4),
        "brier_skill_vs_climatology": (
            round(brier_skill, 4) if isinstance(brier_skill, float)
            else brier_skill),
        "beats_climatology": brier < brier_climatology,
        "log_loss": round(log_loss, 4),
        "log_loss_climatology": round(log_loss_climatology, 4),
        "log_loss_skill_vs_climatology": (
            round(log_loss_skill, 4) if isinstance(log_loss_skill, float)
            else log_loss_skill),
        "forecast_min": round(min(forecasts), 4),
        "forecast_max": round(max(forecasts), 4),
        "forecast_spread_sd": round(spread, 4),
        "distinct_forecasts": len(set(round(p, 4) for p in forecasts)),
        "reliability": reliability(pairs),
        "because": because,
    }


def render(result: dict) -> List[str]:
    """Markdown lines. Never prints a curve for a status that refused one."""
    status = result.get("status")
    if status == PRE_CALIBRATION:
        return [
            f"- Probabilistic calibration: **{PRE_CALIBRATION}** "
            f"(n={result.get('n')}, need {result.get('minimum_n')})",
            f"  _{result.get('because')}_",
        ]
    verdict = ("beats climatology" if result.get("beats_climatology")
               else "**WORSE than climatology**")

    def _skill(value):
        return f"{value:+}" if isinstance(value, (int, float)) else str(value)
    lines = [
        f"- Brier score: {result.get('brier')} vs climatology "
        f"{result.get('brier_climatology')} -> skill "
        f"{_skill(result.get('brier_skill_vs_climatology'))} ({verdict})",
        f"- Log loss: {result.get('log_loss')} vs climatology "
        f"{result.get('log_loss_climatology')} -> skill "
        f"{_skill(result.get('log_loss_skill_vs_climatology'))}",
        f"- Forecast range: {result.get('forecast_min')} .. "
        f"{result.get('forecast_max')} "
        f"(sd {result.get('forecast_spread_sd')}, "
        f"{result.get('distinct_forecasts')} distinct values over "
        f"{result.get('n')} predictions)",
        f"- Discrimination: **{status}**",
        f"  _{result.get('because')}_",
    ]
    if status != NO_DISCRIMINATION and result.get("reliability"):
        lines += ["", "| forecast | n | observed | gap |",
                  "|---|---:|---:|---:|"]
        for row in result["reliability"]:
            lines.append(
                f"| {row['bin_lower']:.1f}-{row['bin_upper']:.1f} "
                f"| {row['n']} | {row['observed_frequency']:.3f} "
                f"| {row['gap']:+.3f} |")
    return lines
