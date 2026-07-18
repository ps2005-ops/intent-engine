"""Offline tests for the approved daily-cadence policy (item 1,
docs/BA_ACCELERATION_PROPOSAL.md). Every enforced constraint from the
approval gets a direct test: allowlist, cap 5, 14d floor, bucket spread,
anti-dup (vs ledger and within batch), baseline quota, rotation
determinism, spend ceiling."""

from datetime import date

import pytest

from intent_engine.core import daily_prediction_policy as policy
from intent_engine.core.prediction_ledger import record_prediction


AS_OF = date(2026, 7, 20)  # a Monday


def _cand(symbol="SPY", days=30, op=">=", value=0.02, probability=0.6, rule_type="pct_change"):
    resolve_by = date.fromordinal(AS_OF.toordinal() + days).isoformat()
    if rule_type == "pct_change":
        rule = {"type": "pct_change", "symbol": symbol, "op": op, "value": value, "window_days": days}
    else:
        rule = {"type": "level", "series": symbol, "op": op, "value": value, "by": resolve_by}
    return {
        "claim_text": f"{symbol} test claim ({days}d)",
        "probability": probability,
        "resolve_by": resolve_by,
        "resolution_rule": rule,
    }


# --- rotation determinism ---------------------------------------------------

def test_mechanism_rotation_deterministic_and_covers_all_families():
    seen = set()
    for offset in range(6):
        d = date.fromordinal(AS_OF.toordinal() + offset)
        fams = policy.mechanism_families_for(d)
        assert fams == policy.mechanism_families_for(d)  # same date -> same answer
        assert len(fams) == 3
        seen.update(fams)
    assert seen == set(policy.MECHANISM_FAMILIES)  # a week covers every family


def test_rotating_extra_deterministic_and_within_allowlists():
    for offset in range(16):
        d = date.fromordinal(AS_OF.toordinal() + offset)
        source, instrument = policy.rotating_extra_instrument(d)
        assert policy.rotating_extra_instrument(d) == (source, instrument)
        if source == "tiingo":
            assert instrument in policy.TIINGO_INSTRUMENTS
        else:
            assert instrument in policy.FRED_SERIES


# --- horizon buckets --------------------------------------------------------

def test_horizon_floor_rejected():
    assert policy.horizon_bucket(AS_OF, date.fromordinal(AS_OF.toordinal() + 13).isoformat()) is None


def test_horizon_bucket_nearest_with_tie_down():
    assert policy.horizon_bucket(AS_OF, date.fromordinal(AS_OF.toordinal() + 14).isoformat()) == 14
    assert policy.horizon_bucket(AS_OF, date.fromordinal(AS_OF.toordinal() + 45).isoformat()) == 30  # tie 30/60 -> down
    assert policy.horizon_bucket(AS_OF, date.fromordinal(AS_OF.toordinal() + 200).isoformat()) == 90


def test_horizon_bucket_unparseable():
    assert policy.horizon_bucket(AS_OF, "not-a-date") is None
    assert policy.horizon_bucket(AS_OF, None) is None


# --- the policy gate --------------------------------------------------------

def test_daily_cap_enforced():
    cands = [
        _cand("SPY", 14), _cand("SPY", 30),
        _cand("UNRATE", 60, rule_type="level", value=4.5),
        _cand("T10Y2Y", 90, rule_type="level", value=0.5),
        _cand("SPY", 60), _cand("SPY", 90, value=-0.05, op="<="),
    ]
    decision = policy.apply_daily_policy(cands, AS_OF, unresolved_live=[])
    assert len(decision.accepted) == policy.DAILY_CAP
    assert any("daily cap" in reason for _, reason in decision.rejected)


def test_allowlist_enforced():
    decision = policy.apply_daily_policy([_cand("TSLA", 30)], AS_OF, unresolved_live=[])
    assert decision.accepted == []
    assert "not in approved allowlist" in decision.rejected[0][1]


def test_grounding_enforced_only_todays_instruments():
    # QQQ is in the global allowlist but only grounded on its rotation day.
    d = AS_OF
    if "QQQ" in policy.allowed_instruments_today(d):
        d = date.fromordinal(d.toordinal() + 1)  # move to a day QQQ is NOT the extra
        assert "QQQ" not in policy.allowed_instruments_today(d)
    decision = policy.apply_daily_policy([_cand("QQQ", 30)], d, unresolved_live=[])
    assert decision.accepted == []
    assert "not grounded in today's snapshot" in decision.rejected[0][1]


def test_bucket_spread_max_two_per_bucket():
    cands = [_cand("SPY", 30), _cand("UNRATE", 30, rule_type="level", value=4.5),
             _cand("T10Y2Y", 30, rule_type="level", value=0.5)]
    decision = policy.apply_daily_policy(cands, AS_OF, unresolved_live=[])
    assert len(decision.accepted) == 2
    assert "already has 2 today" in decision.rejected[0][1]


def test_within_batch_dedup():
    decision = policy.apply_daily_policy([_cand("SPY", 30), _cand("SPY", 32)], AS_OF, unresolved_live=[])
    # 30 and 32 days both bucket to 30 -> same (instrument, direction, bucket) key
    assert len(decision.accepted) == 1
    assert "duplicate" in decision.rejected[0][1]


def test_dedup_against_unresolved_ledger(tmp_path):
    ledger = tmp_path / "ledger.db"
    existing = record_prediction(
        source="market", entity_id="t", claim_text="existing", probability=0.6,
        resolve_by=date.fromordinal(AS_OF.toordinal() + 30).isoformat(), path=ledger,
        instrument="SPY", horizon_days=30,
        resolution_rule={"type": "pct_change", "symbol": "SPY", "op": ">=", "value": 0.02, "window_days": 30},
        resolution_source="tiingo",
    )
    decision = policy.apply_daily_policy([_cand("SPY", 30)], AS_OF, unresolved_live=[existing])
    assert decision.accepted == []
    assert "duplicate" in decision.rejected[0][1]


def test_opposite_direction_not_a_duplicate():
    up = _cand("SPY", 30, op=">=", value=0.02)
    down = _cand("SPY", 30, op="<=", value=-0.03)
    decision = policy.apply_daily_policy([up, down], AS_OF, unresolved_live=[])
    assert len(decision.accepted) == 2


def test_already_recorded_today_shrinks_budget():
    cands = [_cand("SPY", 14), _cand("SPY", 30), _cand("SPY", 60)]
    decision = policy.apply_daily_policy(cands, AS_OF, unresolved_live=[], already_recorded_today=4)
    assert len(decision.accepted) == 1


# --- baselines --------------------------------------------------------------

def test_baseline_quota_requires_60d_bucket():
    assert policy.baseline_quota([_cand("SPY", 60)], AS_OF) == policy.BASELINE_DAILY_CAP
    assert policy.baseline_quota([_cand("SPY", 30)], AS_OF) == 0
    assert policy.baseline_quota([], AS_OF) == 0


# --- spend ceiling ----------------------------------------------------------

def test_month_spend_and_ceiling():
    rows = [{"date": "2026-07-01", "model_calls": 2}] * 10  # $0.40 estimated
    assert policy.month_estimated_spend_usd(rows, 2026, 7) == pytest.approx(0.40)
    assert not policy.ceiling_exceeded(rows, AS_OF, 2)
    # 349 runs x 2 calls = $13.96 -- over the $7 ceiling
    many = [{"date": "2026-07-01", "model_calls": 2}] * 349
    assert policy.ceiling_exceeded(many, AS_OF, 2)


def test_ceiling_ignores_other_months_and_bad_rows():
    rows = [{"date": "2026-06-30", "model_calls": 500}, {"date": "junk", "model_calls": 500}, {}]
    assert policy.month_estimated_spend_usd(rows, 2026, 7) == 0.0
    assert not policy.ceiling_exceeded(rows, AS_OF, 2)
