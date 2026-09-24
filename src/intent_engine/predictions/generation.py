"""Generate company-linked predictions, then gate them into paper intents.

`generate_predictions` is credential-independent given an injected `predict_fn`
(the acceptance test injects a deterministic fake; production injects the LLM
generator). It NEVER lets evidence dated after the prediction leak in — the
signal is produced from the company's state as of the prediction timestamp, and
`resolve_by` is computed from that timestamp forward (leakage-safe by
construction; see also the historical bootstrap).

Two prediction shapes, per section 10:
  * MARKET prediction  — a public tradable company; has an instrument; can be
    scored quantitatively and can become a paper order.
  * STRATEGIC prediction — a private company; has NO instrument; is recorded and
    scored under a separate rubric; can NEVER become a stock order.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

from intent_engine.core.prediction_ledger import Prediction
from intent_engine.paper.eligibility import (
    EligibilityConfig,
    EligibilityResult,
    evaluate_prediction,
)
from intent_engine.universe.companies import CompanyProfile, CompanyPredictionUniverse

# predict_fn(company, state, as_of) -> signal dict or None (no call today)
PredictFn = Callable[[CompanyProfile, Dict[str, Any], str], Optional[Dict[str, Any]]]


def prediction_type(pred: Prediction) -> str:
    return "price_direction" if pred.instrument else "strategic_event"


def _resolve_by(as_of: str, horizon_days: int) -> str:
    return (date.fromisoformat(as_of[:10]) + timedelta(days=horizon_days)).isoformat()


def build_prediction(company: CompanyProfile, signal: Dict[str, Any],
                     as_of: str) -> Prediction:
    """Construct a core Prediction from a generation signal. The instrument is
    the company's tradable instrument (None for a private company -> strategic)."""
    horizon = int(signal.get("horizon_days", 21))
    created_at = signal.get("created_at") or f"{as_of[:10]}T13:30:00+00:00"
    return Prediction(
        source="market", entity_id=company.company_id,
        claim_text=signal.get("claim_text",
                              f"{company.canonical_name} {signal.get('direction')}"),
        probability=float(signal["probability"]),
        resolve_by=_resolve_by(as_of, horizon),
        instrument=company.tradable_instrument,     # None for private -> strategic
        direction=signal.get("direction"), horizon_days=horizon,
        created_at=created_at, decision_id=signal.get("decision_id"))


def generate_predictions(
    universe: CompanyPredictionUniverse, predict_fn: PredictFn, as_of: str, *,
    states: Optional[Dict[str, Dict[str, Any]]] = None,
    repo=None, max_companies: Optional[int] = None,
) -> List[Prediction]:
    """Generate + persist one prediction per eligible company (where predict_fn
    returns a signal). `max_companies` enforces the daily budget cap."""
    states = states or {}
    out: List[Prediction] = []
    companies = universe.prediction_companies()
    if max_companies is not None:
        companies = companies[:max_companies]
    for company in companies:
        signal = predict_fn(company, states.get(company.company_id, {}), as_of)
        if not signal:
            continue
        pred = build_prediction(company, signal, as_of)
        if repo is not None:
            repo.add(pred)
        out.append(pred)
    return out


def intents_for_predictions(
    predictions: List[Prediction], universe: CompanyPredictionUniverse, *,
    order_repo=None, regime: str = "unknown", as_of: Optional[str] = None,
    config: Optional[EligibilityConfig] = None,
) -> Tuple[List, List[EligibilityResult]]:
    """Run eligibility for a batch of predictions against the universe's tradable
    instruments. Returns (eligible_intents, all_results). Strategic (private)
    predictions have no tradable instrument, so they are naturally excluded from
    trading here — recorded, never ordered."""
    tradables = tuple(c.tradable_instrument for c in universe.tradable()
                      if c.tradable_instrument)
    cfg = config or EligibilityConfig(supported_instruments=tradables)
    open_ids = set()
    open_count = 0
    if order_repo is not None:
        open_orders = order_repo.open_orders()
        open_ids = {o.prediction_id for o in open_orders}
        open_count = len(open_orders)

    intents = []
    results: List[EligibilityResult] = []
    for pred in predictions:
        res = evaluate_prediction(
            pred, config=cfg, open_prediction_ids=open_ids,
            open_position_count=open_count, regime=regime,
            reasoning=pred.claim_text, as_of=as_of)
        results.append(res)
        if res.eligible and res.intent is not None:
            intents.append(res.intent)
            open_count += 1                 # keep the risk-limit honest in-batch
            open_ids.add(pred.id)
    return intents, results
