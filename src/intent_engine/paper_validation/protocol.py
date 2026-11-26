"""The preregistered protocol: everything that could be tuned, fixed first.

WHY ONE HASHED DECLARATION
--------------------------
Cadence, horizon, costs, thresholds, the probability each rule states, the
bootstrap, the minimum sample for a claim and the promotion bar are the
places a backtest is quietly made to work. They are declared here once,
before the first replay result exists, and `declaration_hash()` is written
into every replay output and every forward record. `assert_unchanged`
refuses to run against a declaration that has moved. That does not make
cheating impossible in a repository one person controls; it makes it
VISIBLE, which is the achievable version (the same argument as
`econ.preregistration`).

THE DECISION PROTOCOL
---------------------
Decisions are taken at the close of a session, every 21 sessions on the SPY
calendar. A position is entered at the OPEN of the next session and exited
at the open 21 sessions later, which is also the next decision's entry, so
windows are contiguous and never overlap. Entering at the next open rather
than the decision close is deliberate: a fill at the close you decided on
is the commonest invisible lookahead in a daily backtest.

The forecast target is the sign of an EXCESS return over the window:
  * ETF universe:     instrument total return minus cash (fed funds known
                      at the decision, accrued act/360);
  * company universe: stock total return minus SPY over the same window.
`probability` is always P(excess > 0). Abstention states no probability.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict

CONTRACT = "paper_validation_protocol.v1"

PROTOCOL: Dict[str, Any] = {
    "contract": CONTRACT,
    "declared_at": "2026-11-09",
    "paper_only": True,
    # AMENDMENTS ARE PROSPECTIVE. A decision dated before `effective_from`
    # is evaluated exactly as originally declared; the replay and the Nov 9
    # cohort are untouched. Registered 2026-11-25 with approval.
    "amendments": [
        {"id": "A1-regime-fed-funds-frequency",
         "registered_at": "2026-11-25", "effective_from": "2026-11-26",
         "changes": "econ.regime policy change: v1 differenced the 12th-last "
                    "DFF cell, which on the panel's DAILY series is a "
                    "12-day change; v2 compares the mean of the latest "
                    "completed calendar month with the same month a year "
                    "earlier (econ_regime.v2)",
         "affects": ["regime_* features (feature set D)",
                     "regime_label / regime_at_decision on new records"],
         "does_not_affect": ["any record decided before effective_from",
                             "the 2007-2026 replay result",
                             "the 2026-11-09 forward cohort"]},
    ],
    "execution": {
        "cadence_sessions": 21,
        "horizon_sessions": 21,
        "calendar": "SPY sessions (Yahoo daily bars)",
        "decision_at": "session close",
        "entry": "open of the first session after the decision date",
        "exit": "open of the session 21 sessions after entry",
        "price_basis": "split- and dividend-adjusted (Yahoo adjclose; "
                       "open scaled by the same day's adjclose/close)",
        # cost.v1 from market/costs.py, charged on the CHANGE in position,
        # so a book that holds pays nothing and a book that flips pays twice.
        "cost_model": "market.costs cost.v1 (5 bps per side)",
        "slippage_bps_per_side": 5.0,
        "commission_bps": 0.0,
        "short_borrow_bps_per_year": 30.0,
        "company_legs": 2,          # stock vs SPY: both legs pay
        "max_gross_exposure": 1.0,  # equal risk budget, no leverage
        "sizing": "position in {-1, 0, +1} per instrument, book = mean",
    },
    "replay": {
        "anchor": "2003-01-02",
        "common_window_start": "2007-01-01",
        "refit": "first decision of each calendar year",
        "train_rows": "exit_date <= refit decision date (purged)",
        "min_history_sessions": 273,
        "model": "L2 logistic (econ.forecast.Model contract), "
                 "fitted per family",
        "model_trade_margin": 0.02,
    },
    "rule_probabilities": {
        # A rule states a direction, not a probability. The constant is the
        # engine's own `market.signals.BASELINE_PROBABILITY`, used for every
        # rule so Brier compares directions on equal terms.
        "directional_rule": 0.55,
    },
    "policies": {
        "cash": "always abstain",
        "buy_and_hold": "always long",
        "tsmom_12_1": "long if total return over sessions [t-252, t-21] > 0, "
                      "else short (Moskowitz, Ooi, Pedersen 2012)",
        "reversal_1m": "long if trailing 21-session return < 0, else short "
                       "(Jegadeesh 1990)",
        "econ_factor_credit": "ETF only. BAA10Y change over 91 days. "
                              "Narrowing: long risk assets, abstain on "
                              "defensives. Widening: long defensives "
                              "(SHY IEF TLT TIP GLD), abstain on risk assets",
        "ie_market_momentum": "market.strategy_library.baseline_momentum.v1 "
                              "unchanged (existing engine price policy)",
        "ie_econ_transmission": "company only. external_intel.econ_decision"
                                ".transmissions over the state rebuilt as of "
                                "the decision; any ADVERSE channel -> short "
                                "relative to SPY, else abstain (existing "
                                "economic engine)",
        "ie_econ_bayes": "company only. NEW HERE. Beta(1,1) per business "
                         "model class on the transmission flags' resolved "
                         "outcomes (exit <= t); short if posterior "
                         "P(underperform) > 0.52, else abstain",
        "logit_A": "price features",
        "logit_B": "price + macro (vintage-walled)",
        "logit_C": "B + news/company evidence: PENDING the evidence channel",
        "logit_D": "B + engine reasoning (econ regime flags; company "
                   "transmission counts)",
        "causal_filtered": "NOT_IMPLEMENTED: no declared causal edge reaches "
                           "a tradable instrument",
        "random_control": "seeded coin flip, p = 0.5 (negative control)",
        "permutation_control": "company only. same number of shorts per date "
                               "as ie_econ_transmission, on random companies",
        "shuffled_label_control": "logit_B fitted on permuted labels "
                                  "(negative control)",
        "oracle_canary": "peeks at the exit bar; must be REFUSED by the leak "
                         "checker and never scored",
    },
    "metrics": {
        "periods_per_year": 12,
        "bootstrap": "circular block bootstrap over decision dates",
        "bootstrap_block": 6,
        "bootstrap_draws": 2000,
        "bootstrap_seed": 20261109,
        "ci": 0.95,
        "reliability_bins": 10,
        "multiple_comparisons": "Holm over each comparison family",
        "min_periods_for_claim": 60,
        "min_periods_for_regime_cell": 24,
    },
    # A claim of superiority needs ALL of these. Win rate is not one of them.
    "superiority_claim": {
        "min_periods": 60,
        "ci_excludes_zero": True,
        "holm_adjusted_p": 0.05,
        "metric_primary": "Brier skill vs point-in-time climatology",
        "metric_secondary": "net Sharpe difference vs the universe benchmark",
    },
    # FORWARD promotion. Evaluated only on the forward shadow ledger. The
    # learning loop may PROPOSE; only a human may promote.
    "promotion": {
        "min_resolved_decision_dates": 36,
        "brier_skill_ci_low_gt": 0.0,
        "sharpe_diff_vs_benchmark_ci_low_gt": 0.0,
        "max_drawdown_not_worse_than_benchmark_by": 0.05,
        "calibration_slope_within": [0.5, 1.5],
        "holm_adjusted_p": 0.05,
        "authority": "human",
    },
    "learning": {
        "near_miss_band_multiple_of_cost": 2.0,
        "calibration_drift_window": 12,
        "calibration_drift_alarm_brier_rise": 0.02,
        "beliefs": "Beta(1,1) per (policy, family); shadow file only",
    },
}


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, default=str)


def declaration_hash() -> str:
    return hashlib.sha256(canonical(PROTOCOL).encode("utf-8")).hexdigest()


class ProtocolChanged(RuntimeError):
    """The declaration moved after a result was recorded against it."""


def assert_unchanged(expected: str) -> None:
    got = declaration_hash()
    if got != expected:
        raise ProtocolChanged(
            f"protocol hash {got[:12]} != recorded {expected[:12]}. A result "
            "recorded against one declaration cannot be re-read against "
            "another; declare a new protocol version instead of editing "
            "this one.")


def execution() -> Dict[str, Any]:
    return dict(PROTOCOL["execution"])


CADENCE = PROTOCOL["execution"]["cadence_sessions"]
HORIZON = PROTOCOL["execution"]["horizon_sessions"]
SLIPPAGE_BPS = PROTOCOL["execution"]["slippage_bps_per_side"]
BORROW_BPS_YEAR = PROTOCOL["execution"]["short_borrow_bps_per_year"]
RULE_P = PROTOCOL["rule_probabilities"]["directional_rule"]
MODEL_MARGIN = PROTOCOL["replay"]["model_trade_margin"]
MIN_HISTORY = PROTOCOL["replay"]["min_history_sessions"]



def regime_version_for(decision_date: str) -> str:
    """The econ.regime version the protocol prescribes for a decision date."""
    from intent_engine.econ import regime as RG
    for a in PROTOCOL.get("amendments", ()):
        if a["id"] == "A1-regime-fed-funds-frequency" and \
                decision_date[:10] >= a["effective_from"]:
            return RG.V2
    return RG.V1
