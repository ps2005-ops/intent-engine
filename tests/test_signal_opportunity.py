"""Signal opportunity — and the boundary that keeps the future out of it.

The most important test in this file is
`test_future_bars_cannot_change_a_decision_time_label`. Everything else is
bookkeeping; that one is the guarantee.
"""
import math

import pytest

from intent_engine.market import signal_opportunity as SO


def _series(start: str, closes):
    """Consecutive daily closes from `start`."""
    from datetime import date, timedelta
    day = date.fromisoformat(start)
    out = {}
    for i, close in enumerate(closes):
        out[(day + timedelta(days=i)).isoformat()] = close
    return out


def _flat(n=40, value=100.0):
    return _series("2026-06-01", [value] * n)


def _volatile(n=40, base=100.0, swing=0.05):
    return _series("2026-06-01",
                   [base * (1 + swing * (1 if i % 2 else -1))
                    for i in range(n)])


# --- the definition ---------------------------------------------------------
def test_a_flat_instrument_offers_no_qualifying_opportunity():
    observable = SO.observable_opportunity(_flat(), as_of="2026-07-10")
    assert observable.measurable
    assert not observable.qualifies
    assert observable.expected_move == 0.0


def test_a_volatile_instrument_offers_one():
    observable = SO.observable_opportunity(_volatile(), as_of="2026-07-10")
    assert observable.qualifies
    assert observable.expected_move >= SO.MIN_ABS_RETURN


def test_too_few_bars_is_unmeasurable_not_false():
    """"We could not tell" and "there was nothing there" are different answers
    and must never share a value."""
    observable = SO.observable_opportunity(
        _series("2026-07-01", [100.0] * 5), as_of="2026-07-10")
    assert not observable.measurable
    assert SO.label(observable, fired=False) == SO.UNMEASURABLE
    assert "required" in observable.reason


def test_the_threshold_is_inherited_from_the_shipped_signal_constant():
    """Pre-registration integrity: the parameter was not chosen by looking at
    outcomes -- it is the constant the signal has used since day 1."""
    from intent_engine.market.signals import MIN_ABS_RETURN
    assert SO.MIN_ABS_RETURN is MIN_ABS_RETURN


# --- the 2x2 ----------------------------------------------------------------
def test_all_four_cells_are_reachable():
    """If the opportunity condition were the firing rule restated, two cells
    would be unreachable and the whole layer would measure nothing."""
    quiet = SO.observable_opportunity(_flat(), as_of="2026-07-10")
    live = SO.observable_opportunity(_volatile(), as_of="2026-07-10")
    assert SO.label(quiet, fired=False) == SO.CORRECTLY_QUIET
    assert SO.label(quiet, fired=True) == SO.FALSE_FIRE_CANDIDATE
    assert SO.label(live, fired=False) == SO.MISSED_OPPORTUNITY_CANDIDATE
    assert SO.label(live, fired=True) == SO.CORRECT_FIRE


# --- THE LOOKAHEAD BOUNDARY -------------------------------------------------
def test_future_bars_cannot_change_a_decision_time_label():
    """A live series is fetched whole and reused across replay dates, so it
    legitimately contains bars after `as_of`. They must not reach the estimate.

    Constructed so the future is wildly different from the past: if a single
    future bar leaked in, the volatility estimate would move and this fails.
    """
    as_of = "2026-07-10"
    past = _flat(40)
    future = dict(past)
    future.update(_series("2026-07-11", [100, 400, 20, 900, 5, 700]))

    truncated = SO.observable_opportunity(past, as_of=as_of)
    with_future = SO.observable_opportunity(future, as_of=as_of)

    assert with_future.as_dict() == truncated.as_dict()
    assert SO.label(with_future, fired=False) == SO.label(truncated,
                                                          fired=False)


def test_bars_available_counts_only_the_past():
    series = _flat(40)
    series.update(_series("2026-07-20", [100.0] * 30))
    observable = SO.observable_opportunity(series, as_of="2026-07-05")
    assert observable.bars_available == len(
        [d for d in series if d <= "2026-07-05"])


# --- outcome attachment -----------------------------------------------------
def _record(as_of="2026-06-10", state=SO.MISSED_OPPORTUNITY_CANDIDATE):
    observable = SO.observable_opportunity(_volatile(), as_of=as_of)
    return SO.AuditRecord(
        as_of=as_of, cycle_id="c", company_id="acme", instrument="ACME",
        strategic_view="present", evidence_ids=(), signal="baseline_momentum",
        signal_version="v1", inputs={}, threshold=SO.MIN_ABS_RETURN,
        raw_value=observable.expected_move, fired=False, fire_reason="flat",
        opportunity_state=state, opportunity=observable.as_dict())


def test_an_unelapsed_horizon_is_never_graded():
    """The textbook version of the bug this project has already hit twice."""
    record = _record(as_of="2026-07-30")
    resolved = SO.resolve_outcome(record, _volatile(), today="2026-08-01")
    assert resolved.outcome_state == SO.UNRESOLVED
    assert resolved.realized_return is None


def test_an_elapsed_horizon_is_graded():
    record = _record(as_of="2026-06-10")
    series = _series("2026-06-01", [100.0] * 20 + [110.0] * 40)
    resolved = SO.resolve_outcome(record, series, today="2026-08-30")
    assert resolved.outcome_state == SO.RESOLVED
    assert resolved.realized_return is not None
    assert resolved.calibration_eligible


def test_resolution_never_rewrites_the_decision_time_label():
    """The live label was decided from decision-time information and stays
    exactly as it was. Only outcome fields are filled in."""
    record = _record(as_of="2026-06-10")
    series = _series("2026-06-01", [100.0] * 20 + [300.0] * 40)
    resolved = SO.resolve_outcome(record, series, today="2026-08-30")
    assert resolved.opportunity_state == record.opportunity_state
    assert resolved.opportunity == record.opportunity
    assert resolved.fired == record.fired


def test_an_already_resolved_record_is_not_regraded_by_a_rerun():
    """Idempotence with teeth: a rerun must not re-mark an outcome against a
    later (different) price."""
    record = _record(as_of="2026-06-10")
    series = _series("2026-06-01", [100.0] * 20 + [110.0] * 40)
    once = SO.resolve_outcome(record, series, today="2026-08-30")
    later = dict(series)
    later.update(_series("2026-08-01", [999.0] * 10))
    twice = SO.resolve_outcome(once, later, today="2026-09-30")
    assert twice.realized_return == once.realized_return


def test_a_missing_close_leaves_the_record_unresolved_rather_than_guessing():
    record = _record(as_of="2026-06-10")
    resolved = SO.resolve_outcome(record, {}, today="2026-09-30")
    assert resolved.outcome_state == SO.UNRESOLVED


# --- confirmation is evaluation only ----------------------------------------
def test_a_candidate_miss_is_only_confirmed_after_the_outcome_exists():
    record = _record()
    assert SO.confirmed_miss(record) is None       # unresolved -> no verdict


def test_a_confirmed_miss_requires_a_real_move():
    record = _record(as_of="2026-06-10")
    big = _series("2026-06-01", [100.0] * 20 + [130.0] * 40)
    small = _series("2026-06-01", [100.0] * 20 + [100.2] * 40)
    assert SO.confirmed_miss(SO.resolve_outcome(record, big,
                                                today="2026-08-30")) is True
    assert SO.confirmed_miss(SO.resolve_outcome(record, small,
                                                today="2026-08-30")) is False


def test_only_missed_candidates_are_confirmable():
    quiet = _record(state=SO.CORRECTLY_QUIET)
    series = _series("2026-06-01", [100.0] * 20 + [130.0] * 40)
    assert SO.confirmed_miss(SO.resolve_outcome(quiet, series,
                                                today="2026-08-30")) is None


# --- summary ----------------------------------------------------------------
def test_a_rate_over_zero_resolutions_is_unmeasurable_not_zero():
    summary = SO.summarise([_record()])
    assert summary["confirmed_miss_rate"] is None
    assert "UNMEASURABLE" in summary["confirmed_miss_rate_note"]
    assert "UNMEASURABLE" in SO.render(summary)


def test_summary_counts_every_state():
    summary = SO.summarise([_record(), _record(state=SO.CORRECTLY_QUIET)])
    assert summary["evaluated"] == 2
    assert summary["states"][SO.MISSED_OPPORTUNITY_CANDIDATE] == 1
    assert summary["states"][SO.CORRECTLY_QUIET] == 1
    assert summary["unresolved"] == 2
    assert summary["definition"] == SO.DEFINITION
