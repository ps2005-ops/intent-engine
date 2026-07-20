"""Offline tests for the approved daily-cadence policy (item 1,
docs/BA_ACCELERATION_PROPOSAL.md; widened to cadence v2 per
docs/CADENCE_V2_PROPOSAL.md, founder-approved 2026-07-19). Every enforced
constraint gets a direct test: allowlist (22 Tiingo + 12 FRED), cap 8,
14d floor, bucket spread, anti-dup (vs ledger and within batch), baseline
quota, rotation determinism (incl. the v2 5-instrument extra window),
spend ceiling ($7 unchanged)."""

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


# --- cadence v2 (founder-approved 2026-07-19) -------------------------------

def test_v2_allowlist_is_exactly_the_approved_set():
    assert policy.TIINGO_INSTRUMENTS == (
        "SPY", "QQQ", "IWM", "TLT", "GLD", "XLE", "XLF",
        "XLK", "XLV", "XLY", "XLP", "XLI", "XLB", "XLU", "XLRE", "XLC",
        "DIA", "MDY", "EFA", "EEM", "HYG", "LQD",
    )
    assert policy.FRED_SERIES == (
        "T10Y2Y", "UNRATE", "CPIAUCSL", "BAMLH0A0HYM2", "DGS10", "VIXCLS",
        "DGS2", "DGS30", "T10YIE", "DTWEXBGS", "DCOILWTICO", "DEXUSEU",
    )
    assert len(policy.TIINGO_INSTRUMENTS) == 22 and len(policy.FRED_SERIES) == 12


def test_v2_cap_and_ceiling_numbers():
    assert policy.DAILY_CAP == 8
    assert policy.MAX_PER_BUCKET_PER_DAY == 2  # 8/day = 4 buckets x 2, by construction
    assert policy.MONTHLY_SPEND_CEILING_USD == 7.00  # unchanged in v2
    # ~21 trading days x <=4 model calls x $0.02 stays far under the ceiling
    assert 21 * 4 * policy.ESTIMATED_COST_PER_MODEL_CALL_USD < policy.MONTHLY_SPEND_CEILING_USD


def test_v2_extra_window_deterministic_size_5_no_dupes_within_day():
    for offset in range(40):
        d = date.fromordinal(AS_OF.toordinal() + offset)
        window = policy.rotating_extra_instruments(d)
        assert window == policy.rotating_extra_instruments(d)
        assert len(window) == policy.DAILY_EXTRA_INSTRUMENT_COUNT == 5
        assert len(set(window)) == 5  # no instrument fetched twice in a day
        for source, instrument in window:
            assert (instrument in policy.TIINGO_INSTRUMENTS) if source == "tiingo" \
                else (instrument in policy.FRED_SERIES)
        # core+SPY never wastes an extra slot
        assert all(inst not in policy.CORE_SNAPSHOT_SERIES + ("SPY",) for _, inst in window)


def test_v2_rotation_covers_the_full_pool():
    # gcd(5, 29) == 1: 29 consecutive days must visit every pool entry.
    seen = set()
    for offset in range(29):
        seen.update(policy.rotating_extra_instruments(date.fromordinal(AS_OF.toordinal() + offset)))
    assert seen == set(policy._ROTATING_EXTRAS)
    assert len(seen) == 29


def test_v2_allowed_today_is_core_plus_spy_plus_window():
    today = policy.allowed_instruments_today(AS_OF)
    assert len(today) == 10  # 4 core + SPY + 5 extras == the <=10 data calls
    for s in policy.CORE_SNAPSHOT_SERIES + ("SPY",):
        assert s in today


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
    # 9 grounded, non-duplicate candidates spread 2-per-bucket: exactly
    # DAILY_CAP (8) accepted, the 9th rejected on the cap.
    cands = [
        _cand("SPY", 14), _cand("UNRATE", 14, rule_type="level", value=4.5),
        _cand("SPY", 30), _cand("UNRATE", 30, rule_type="level", value=4.5),
        _cand("SPY", 60), _cand("UNRATE", 60, rule_type="level", value=4.5),
        _cand("SPY", 90), _cand("UNRATE", 90, rule_type="level", value=4.5),
        _cand("T10Y2Y", 90, rule_type="level", value=0.5),
    ]
    decision = policy.apply_daily_policy(cands, AS_OF, unresolved_live=[])
    assert len(decision.accepted) == policy.DAILY_CAP == 8
    assert any("daily cap" in reason for _, reason in decision.rejected)


def test_allowlist_enforced():
    decision = policy.apply_daily_policy([_cand("TSLA", 30)], AS_OF, unresolved_live=[])
    assert decision.accepted == []
    assert "not in approved allowlist" in decision.rejected[0][1]


def test_grounding_enforced_only_todays_instruments():
    # QQQ is in the global allowlist but only grounded on days its window
    # includes it. Find a nearby day where it is NOT (with a 5-of-29
    # window most days qualify; assert one exists within the cycle).
    d = None
    for offset in range(29):
        cand_day = date.fromordinal(AS_OF.toordinal() + offset)
        if "QQQ" not in policy.allowed_instruments_today(cand_day):
            d = cand_day
            break
    assert d is not None, "no QQQ-free day in a full rotation cycle -- window logic broken"
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
    decision = policy.apply_daily_policy(
        cands, AS_OF, unresolved_live=[], already_recorded_today=policy.DAILY_CAP - 1)
    assert len(decision.accepted) == 1


# --- baselines --------------------------------------------------------------

def test_baseline_quota_unconditional_after_2026_07_18_amendment():
    # Option 1 (user decision): guaranteed daily accrual — quota is the cap
    # regardless of which buckets the engine used, even on a zero-recorded day.
    assert policy.baseline_quota([_cand("SPY", 60)], AS_OF) == policy.BASELINE_DAILY_CAP
    assert policy.baseline_quota([_cand("SPY", 30)], AS_OF) == policy.BASELINE_DAILY_CAP
    assert policy.baseline_quota([], AS_OF) == policy.BASELINE_DAILY_CAP


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
