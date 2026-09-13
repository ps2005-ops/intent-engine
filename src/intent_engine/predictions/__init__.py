"""Durable, company-linked market predictions for the hosted loop.

Reuses the battle-tested `core.prediction_ledger.Prediction` record (its Brier
math, resolution-rule shapes, decision-id link) but persists it to the durable
store so predictions survive a fresh GitHub-Actions runner. `entity_id` carries
the company_id, so every prediction is linkable to the company it is about and
to the paper order it produced — the traceability the FINAL STANDARD requires.
"""
from __future__ import annotations

from intent_engine.predictions.repository import PredictionRepository
from intent_engine.predictions.generation import (
    build_prediction,
    generate_predictions,
    intents_for_predictions,
)
from intent_engine.predictions.resolution import resolve_due

__all__ = [
    "PredictionRepository",
    "build_prediction",
    "generate_predictions",
    "intents_for_predictions",
    "resolve_due",
]
