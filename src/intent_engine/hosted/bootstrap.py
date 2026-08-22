"""Leakage-safe historical bootstrap (section 14).

Live paper outcomes accumulate slowly, so this replays the configured PUBLIC
companies over historical evaluation dates with strict walk-forward discipline:

  * LEAKAGE-SAFE — at each evaluation date, the predictor sees only state/evidence
    available BY that date (the injected `predict_fn` receives only `as_of`), and
    an outcome is scored only from prices at the prediction's own created/resolve
    dates. Future prices, later filings, and revised datasets can never leak
    backward.
  * COSTS + SLIPPAGE — every simulated trade's return is charged a round-trip
    transaction cost and slippage, so historical returns are not free.
  * TRAIN/EVAL SEPARATION — dates are split; out-of-sample metrics are reported
    separately from in-sample.
  * LABELLED SEPARATELY — results are written to a `bootstrap_outcome` stream
    tagged `label="historical"`, never mixed with live-forward paper outcomes,
    and `proves_live_profitability` is always False.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

from intent_engine.predictions.generation import build_prediction

BOOTSTRAP_STREAM = "bootstrap_outcome"

_UP = {"up", "long", "bull", "rise", "increase"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class BootstrapConfig:
    cost_bps: float = 5.0          # one-way transaction cost, basis points
    slippage_bps: float = 5.0      # one-way slippage, basis points
    train_fraction: float = 0.5    # first half of dates = in-sample


def _directional_accuracy(outs: List[dict]) -> Optional[float]:
    if not outs:
        return None
    return sum(1 for o in outs if o["happened"]) / len(outs)


def _brier(outs: List[dict]) -> Optional[float]:
    if not outs:
        return None
    return sum(o["brier"] for o in outs) / len(outs)


def run_bootstrap(
    universe, predict_fn: Callable, price_at: Callable[[str, str], float],
    eval_dates: List[str], *, store=None, config: Optional[BootstrapConfig] = None,
) -> Dict:
    """Walk-forward replay. `eval_dates` are ascending ISO dates; each is treated
    as a prediction date whose horizon resolves at a strictly later date."""
    config = config or BootstrapConfig()
    dates = sorted(eval_dates)
    split = max(1, int(len(dates) * config.train_fraction))
    train_dates, test_dates = set(dates[:split]), set(dates[split:])
    round_trip_cost = 2 * (config.cost_bps + config.slippage_bps) / 10_000.0

    per_company: Dict[str, List[dict]] = {}
    for company in universe.tradable():
        sym = company.tradable_instrument
        for as_of in dates:
            signal = predict_fn(company, {}, as_of)   # sees only as_of (no leak)
            if not signal:
                continue
            pred = build_prediction(company, signal, as_of)
            created_day = as_of[:10]
            resolve_day = (pred.resolve_by or as_of)[:10]
            if resolve_day <= created_day:
                continue
            try:
                entry = price_at(sym, created_day)   # only dates <= resolve
                exit_px = price_at(sym, resolve_day)
            except Exception:  # noqa: BLE001 - missing history: skip, no guess
                continue
            move = exit_px - entry
            predicted_up = str(pred.direction or "").lower() in _UP
            happened = (predicted_up and move > 0) or (not predicted_up and move < 0)
            brier = (pred.probability - 1.0) ** 2 if happened \
                else (pred.probability - 0.0) ** 2
            gross = (move / entry) if entry else 0.0
            direction_sign = 1.0 if predicted_up else -1.0
            net = gross * direction_sign - round_trip_cost   # costs + slippage
            row = {"company_id": company.company_id, "instrument": sym,
                   "as_of": created_day, "resolve_day": resolve_day,
                   "happened": happened, "brier": brier,
                   "gross_return": gross, "net_return": net,
                   "split": "train" if as_of in train_dates else "test",
                   "label": "historical", "proves_live_profitability": False}
            per_company.setdefault(company.company_id, []).append(row)
            if store is not None:
                rid = f"{company.company_id}:{created_day}"
                store.append(BOOTSTRAP_STREAM, rid, row, status="historical",
                             company_id=company.company_id,
                             idem_key=f"bootstrap:{rid}", ts=_now())

    metrics = {}
    for cid, outs in per_company.items():
        train = [o for o in outs if o["split"] == "train"]
        test = [o for o in outs if o["split"] == "test"]
        metrics[cid] = {
            "n": len(outs),
            "in_sample_accuracy": _directional_accuracy(train),
            "out_of_sample_accuracy": _directional_accuracy(test),
            "in_sample_brier": _brier(train),
            "out_of_sample_brier": _brier(test),
            "net_return_sum": round(sum(o["net_return"] for o in outs), 4),
        }
    return {"label": "historical", "proves_live_profitability": False,
            "train_dates": len(train_dates), "test_dates": len(test_dates),
            "companies": metrics}
