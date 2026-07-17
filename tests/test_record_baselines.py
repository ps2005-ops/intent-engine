"""Tests for scripts/record_baselines.py (Task M8, market-engine-
execution-plan.md). All price data is injected via a fake price_fetcher
-- no network, no key required.
"""

import sys
from datetime import date
from pathlib import Path

import pytest

from intent_engine.core.market_resolution import TiingoSeries
from intent_engine.core.prediction_ledger import PctChangeRule

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from record_baselines import (  # noqa: E402
    BASE_RATE_SPY_2PCT_60D,
    MOMENTUM_PROBABILITY_IF_NEGATIVE,
    MOMENTUM_PROBABILITY_IF_POSITIVE,
    record_base_rate_baseline,
    record_momentum_baseline,
)


def _fake_fetcher(start_price: float, end_price: float):
    def fetcher(symbol, start, end):
        return TiingoSeries(symbol=symbol, observations=[("2026-04-01", start_price), ("2026-06-30", end_price)])
    return fetcher


FIXED_TODAY = date(2026, 6, 30)


def test_momentum_baseline_positive_trailing_return_yields_065(tmp_path):
    path = tmp_path / "ledger.db"
    p = record_momentum_baseline(
        "Acme Inc", path=path, price_fetcher=_fake_fetcher(100.0, 110.0), today=FIXED_TODAY,
    )
    assert p.probability == MOMENTUM_PROBABILITY_IF_POSITIVE
    assert p.probability == 0.65


def test_momentum_baseline_negative_trailing_return_yields_035(tmp_path):
    path = tmp_path / "ledger.db"
    p = record_momentum_baseline(
        "Acme Inc", path=path, price_fetcher=_fake_fetcher(110.0, 100.0), today=FIXED_TODAY,
    )
    assert p.probability == MOMENTUM_PROBABILITY_IF_NEGATIVE
    assert p.probability == 0.35


def test_momentum_baseline_source_and_resolution_rule_are_valid(tmp_path):
    path = tmp_path / "ledger.db"
    p = record_momentum_baseline(
        "Acme Inc", path=path, price_fetcher=_fake_fetcher(100.0, 110.0), today=FIXED_TODAY,
    )
    assert p.source == "baseline"
    assert isinstance(p.resolution_rule, PctChangeRule)
    assert p.resolution_rule.symbol == "SPY"
    assert p.resolution_rule.op == ">="
    assert p.resolution_rule.value == 0.02
    assert p.resolution_rule.window_days == 60
    assert p.resolution_source == "tiingo"
    assert p.resolve_by == "2026-08-29"  # FIXED_TODAY + 60 days


def test_momentum_baseline_is_deterministic_given_the_same_inputs(tmp_path):
    """Same trailing-return direction, same "today" -> same probability
    and same resolution_rule content across two separate calls (id and
    created_at are expected to differ -- the ledger stamps those fresh
    every record_prediction() call by design, not something determinism
    here claims to control)."""
    path = tmp_path / "ledger.db"
    p1 = record_momentum_baseline("Acme Inc", path=path, price_fetcher=_fake_fetcher(100.0, 110.0), today=FIXED_TODAY)
    p2 = record_momentum_baseline("Acme Inc", path=path, price_fetcher=_fake_fetcher(100.0, 110.0), today=FIXED_TODAY)
    assert p1.probability == p2.probability
    assert p1.resolution_rule == p2.resolution_rule
    assert p1.resolve_by == p2.resolve_by
    assert p1.id != p2.id  # two distinct ledger rows, as expected


def test_momentum_baseline_raises_on_insufficient_price_data(tmp_path):
    path = tmp_path / "ledger.db"

    def empty_fetcher(symbol, start, end):
        return TiingoSeries(symbol=symbol, observations=[])

    with pytest.raises(RuntimeError, match="Not enough"):
        record_momentum_baseline("Acme Inc", path=path, price_fetcher=empty_fetcher, today=FIXED_TODAY)


def test_base_rate_baseline_uses_the_frozen_constant_exactly(tmp_path):
    path = tmp_path / "ledger.db"
    p = record_base_rate_baseline("Acme Inc", path=path, today=FIXED_TODAY)
    assert p.probability == BASE_RATE_SPY_2PCT_60D
    assert p.probability == 0.8079


def test_base_rate_baseline_source_and_resolution_rule_are_valid(tmp_path):
    path = tmp_path / "ledger.db"
    p = record_base_rate_baseline("Acme Inc", path=path, today=FIXED_TODAY)
    assert p.source == "baseline"
    assert isinstance(p.resolution_rule, PctChangeRule)
    assert p.resolution_rule.symbol == "SPY"
    assert p.resolution_source == "tiingo"
    assert p.resolve_by == "2026-08-29"


def test_base_rate_baseline_is_deterministic():
    """No network, no injected fetcher at all -- the frozen constant means
    two calls with the same "today" are trivially identical in
    probability, proving there's genuinely no live recomputation inside
    record_base_rate_baseline."""
    from intent_engine.core.prediction_ledger import record_prediction  # noqa: F401  (sanity import only)

    import tempfile
    path1 = tempfile.mktemp(suffix=".db")
    path2 = tempfile.mktemp(suffix=".db")
    p1 = record_base_rate_baseline("Acme Inc", path=path1, today=FIXED_TODAY)
    p2 = record_base_rate_baseline("Acme Inc", path=path2, today=FIXED_TODAY)
    assert p1.probability == p2.probability == BASE_RATE_SPY_2PCT_60D


def test_frozen_base_rate_constant_is_between_0_and_1():
    assert 0.0 < BASE_RATE_SPY_2PCT_60D < 1.0
