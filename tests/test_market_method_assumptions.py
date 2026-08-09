"""An assumption that is listed and never tested is decoration.

C-MET-002 and C-MET-004. `EconomicMethod.assumptions` was a tuple of
sentences. Sentences do not fail, so a method whose assumptions were violated
produced the same number, with the same confidence, as one whose assumptions
held — and the offline comparison that found "AR1 beats persistence on four
short series" had no way to say whether those four were stationary.

These tests hold two lines:

  * every declared assumption comes back with a result, including UNTESTED,
    so a partial check cannot read as a complete one;
  * a failed CRITICAL assumption refuses the causal reading and keeps the
    descriptive one, because discarding the number would push a caller toward
    a method that fails silently instead.
"""
from __future__ import annotations

import json
import random

import pytest

from intent_engine.market import economic_method as EM
from intent_engine.market import learning_store as LS

AS_OF = "2026-08-09"

def _noise(seed, n):
    """Deterministic draws. Seeded so a failing test fails the same way."""
    rng = random.Random(seed)
    return [rng.gauss(0.0, 1.0) for _ in range(n)]


#: A RANDOM WALK, and long enough to be recognised as one. The fitted AR(1)
#: coefficient of a walk is biased DOWNWARD in short samples: the same
#: process over 36 points fits at 0.96 and passes a 0.98 screen. The screen
#: is not wrong; a short sample genuinely cannot tell a unit root from strong
#: mean reversion, and a fixture that hid that would be pinning a threshold
#: rather than a behaviour.
RANDOM_WALK = [100.0]
for _step in _noise(11, 240):
    RANDOM_WALK.append(RANDOM_WALK[-1] + _step)

#: A REAL AR(1): x_{t+1} = 2 + 0.6 x_t + e. Stationary, and one lag genuinely
#: carries the dependence, so both assumptions must hold. An earlier version
#: of this fixture was a deterministic period-6 cycle, which is stationary and
#: which one lag cannot capture — the advisory check failed on it, correctly,
#: and that made it useless as the "everything holds" case.
MEAN_REVERTING = [5.0]
for _shock in _noise(23, 240):
    MEAN_REVERTING.append(2.0 + 0.6 * MEAN_REVERTING[-1] + _shock)


# --- every assumption is answered for --------------------------------------

@pytest.mark.parametrize("name", sorted(EM.METHODS))
def test_every_declared_assumption_comes_back_with_a_result(name):
    """A check that silently returns only the testable ones looks complete.

    Run over EVERY registered method, not just AR1. AR1's two assumptions
    both reach purpose-built branches; the six declared-only methods reach
    none of them, and their assumptions are exactly the ones a partial check
    would drop without trace.
    """
    method = EM.METHODS[name]
    got = EM.check_assumptions(MEAN_REVERTING, name, series_name="s")
    assert len(got) == len(method.assumptions), (
        f"{name} declares {len(method.assumptions)} assumptions and "
        f"{len(got)} were answered for")
    assert {c.assumption for c in got} == set(method.assumptions)


def test_a_design_assumption_no_series_can_answer_is_untested_not_passed():
    """"the window was chosen before the effect was seen" is not in the data."""
    got = EM.check_assumptions([1.0] * 60, EM.EVENT_STUDY, series_name="s")
    chosen = [c for c in got if "chosen before" in c.assumption]
    assert chosen and chosen[0].result == EM.UNTESTED
    assert not chosen[0].tested
    assert "how the study was conducted" in chosen[0].evidence


def test_an_assumption_check_must_state_its_evidence():
    with pytest.raises(EM.MethodRefused) as err:
        EM.MethodAssumptionCheck(
            method=EM.AR1, question="", assumption="stationary",
            severity=EM.CRITICAL, result=EM.PASSED, evidence="  ")
    assert "reads as having been checked" in str(err.value)


# --- the tests actually discriminate ---------------------------------------

def test_a_random_walk_fails_the_stationarity_assumption():
    got = EM.check_assumptions(RANDOM_WALK, EM.AR1, series_name="walk")
    stationarity = [c for c in got if "stationary" in c.assumption][0]
    assert stationarity.result == EM.FAILED
    assert stationarity.severity == EM.CRITICAL
    assert stationarity.blocks_causal_reading
    assert stationarity.statistic >= stationarity.threshold


def test_stationarity_is_judged_on_the_coefficient_the_method_fits():
    """A trend passes an autocorrelation screen and fails the right one.

    On a long random walk the levels' autocorrelation and the fitted AR(1)
    coefficient agree, so that series cannot tell the two statistics apart.
    A monotone trend can: its lag-1 autocorrelation sits near 0.94 and the
    fitted coefficient is exactly 1.0, which is the number the assumption is
    a statement about.
    """
    trend = [float(i) for i in range(60)]
    got = EM.check_assumptions(trend, EM.AR1, series_name="trend")
    stationarity = [c for c in got if "stationary" in c.assumption][0]
    assert stationarity.result == EM.FAILED
    assert stationarity.statistic == pytest.approx(1.0, abs=1e-9), (
        "the screen read a statistic other than the fitted coefficient")


def test_one_lag_is_judged_on_in_sample_residuals_not_forecast_errors():
    """An expanding-window fit chases the series; its errors are not residuals.

    On a SHORT true AR(1) the difference bites: walk-forward errors from a
    fit that is still converging are strongly negatively autocorrelated, so
    scoring them fails the advisory on a series that satisfies it. On a long
    series the two agree, which is why this case is short on purpose.
    """
    short_ar1 = MEAN_REVERTING[:22]
    got = EM.check_assumptions(short_ar1, EM.AR1, series_name="short")
    one_lag = [c for c in got if "one lag carries" in c.assumption][0]
    assert one_lag.result == EM.PASSED, (
        f"a 22-point AR(1) failed its own advisory: {one_lag.evidence}")


def test_a_mean_reverting_series_passes_it():
    got = EM.check_assumptions(MEAN_REVERTING, EM.AR1, series_name="mr")
    stationarity = [c for c in got if "stationary" in c.assumption][0]
    assert stationarity.result == EM.PASSED
    assert not stationarity.blocks_causal_reading


def test_persistence_is_told_when_it_is_leaving_a_drift_on_the_table():
    """A monotone series makes 'no reliable short-horizon drift' false."""
    rising = [float(i) for i in range(40)]
    got = EM.check_assumptions(rising, EM.PERSISTENCE, series_name="rising")
    drift = [c for c in got if "no reliable short-horizon drift" in
             c.assumption][0]
    assert drift.result == EM.FAILED


# --- what may be said afterwards -------------------------------------------

def test_a_failed_critical_assumption_refuses_the_causal_reading():
    got = EM.check_assumptions(RANDOM_WALK, EM.AR1, series_name="walk")
    reading = EM.interpret(got, beat_baseline=True, predictions=200)
    assert reading["standing"] == EM.REFUSED
    assert reading["causal_reading_allowed"] is False


def test_a_refused_reading_still_keeps_the_descriptive_result():
    """REFUSED is a statement about identification, not about the number."""
    got = EM.check_assumptions(RANDOM_WALK, EM.AR1, series_name="walk")
    reading = EM.interpret(got, beat_baseline=True, predictions=200)
    assert reading["descriptive_result_retained"] is True
    assert "does not identify an effect" in reading["note"]


def test_a_method_that_did_not_beat_the_baseline_is_a_result_not_a_failure():
    got = EM.check_assumptions(MEAN_REVERTING, EM.AR1, series_name="mr")
    reading = EM.interpret(got, beat_baseline=False, predictions=200)
    assert reading["standing"] == EM.NO_INCREMENTAL_VALUE


def test_a_win_on_too_few_predictions_is_bounded_not_useful():
    """C-MET-001 recorded its 24-point wins as suggestive; that must hold.

    A later layer that promotes them to USEFUL undoes a careful reading
    without arguing with it.
    """
    got = EM.check_assumptions(MEAN_REVERTING, EM.AR1, series_name="mr")
    assert EM.interpret(got, beat_baseline=True, predictions=16
                        )["standing"] == EM.BOUNDED
    assert EM.interpret(got, beat_baseline=True, predictions=200
                        )["standing"] == EM.USEFUL


def test_an_untestable_critical_assumption_bounds_rather_than_passes():
    got = EM.check_assumptions([1.0] * 60, EM.EVENT_STUDY, series_name="s")
    reading = EM.interpret(got, beat_baseline=True, predictions=200)
    assert reading["standing"] == EM.BOUNDED
    assert reading["untested"] > 0


# --- the rows survive the process ------------------------------------------

def test_performance_and_checks_persist_and_reload(tmp_path):
    store = LS.LearningStore(tmp_path / "ledger.jsonl")
    performance = EM.score(MEAN_REVERTING, EM.AR1, series_name="mr")
    assert store.record_method_performance(
        performance, as_of=AS_OF, question_type=EM.FORECAST_LEVEL) is True
    assert store.record_method_performance(
        performance, as_of=AS_OF, question_type=EM.FORECAST_LEVEL) is False, (
        "the same measurement on the same date was appended twice")

    for check in EM.check_assumptions(MEAN_REVERTING, EM.AR1,
                                      series_name="mr", as_of=AS_OF):
        store.record_method_assumption_check(check)

    fresh = LS.LearningStore(tmp_path / "ledger.jsonl")
    assert len(fresh.method_performances()) == 1
    assert fresh.method_assumption_checks()
    assert fresh.method_performances()[0]["measured_as_of"] == AS_OF


def test_a_later_date_is_a_new_measurement_not_a_correction(tmp_path):
    """A score with no date attached outlives the regime it was taken in."""
    store = LS.LearningStore(tmp_path / "ledger.jsonl")
    performance = EM.score(MEAN_REVERTING, EM.AR1, series_name="mr")
    store.record_method_performance(performance, as_of="2026-08-09",
                                    question_type=EM.FORECAST_LEVEL)
    store.record_method_performance(performance, as_of="2026-09-09",
                                    question_type=EM.FORECAST_LEVEL)
    assert len(store.method_performances()) == 2


# --- the CYCLE measures it, not a human running a script -------------------

def _observation(series_id, period, value, published, area="CA"):
    return {
        "record": "macro_observation", "state_kind": "MARKET_RATE",
        "series_id": series_id, "label": f"{area} yield", "value": value,
        "unit": "%", "measure": "LEVEL", "standing": "OBSERVED", "area": area,
        "reference_period": period, "published_at": published,
        "retrieved_at": published, "publication_basis": "PUBLISHER",
        "source": "https://example.test/s",
    }


@pytest.fixture()
def scored_root(tmp_path):
    """A root holding one series long enough to score."""
    (tmp_path / "reports" / "market").mkdir(parents=True)
    ledger = tmp_path / LS.DEFAULT_PATH
    ledger.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for i, value in enumerate(MEAN_REVERTING[:60]):
        month = f"{2021 + i // 12}-{i % 12 + 1:02d}-01"
        published = f"{2021 + i // 12}-{i % 12 + 1:02d}-15"
        rows.append(_observation("CA10Y", month, round(value, 4), published))
    ledger.write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return tmp_path


def _method_payload(root, *, as_of=AS_OF, run_id="m1"):
    from intent_engine.market import cycle as C
    from intent_engine.market import steps as ST

    ctx = C.CycleContext(cycle="market", as_of=as_of, root=root,
                         session=None, run_id=run_id)
    return ST.knowledge_step(ctx).get("economic_method") or {}


def test_the_cycle_scores_the_series_it_holds(scored_root):
    """C-MET-001 was a comparison a human ran once, on data frozen in 2026."""
    got = _method_payload(scored_root)
    assert "error" not in got, got.get("error")
    assert got["series_scored"] >= 1
    assert got["evaluations"] >= 3, (
        "three baselines should each be scored on the series")
    assert got["performance_records_written"] == got["evaluations"]
    assert got["assumption_checks_written"] > 0


def test_a_fresh_process_reads_back_what_the_cycle_scored(scored_root):
    _method_payload(scored_root)
    fresh = LS.LearningStore(scored_root / LS.DEFAULT_PATH)
    performances = fresh.method_performances()
    assert performances, (
        "the scores reached the report and not the ledger, which is the "
        "state that makes every cross-cycle method claim a one-off")
    assert all(r.get("measured_as_of") for r in performances)
    assert fresh.method_assumption_checks()


def test_the_report_says_which_method_leads_and_persistence_may_win(
        scored_root):
    got = _method_payload(scored_root)
    assert got["leader"]
    assert got["leader"] in EM.METHODS
    # Nothing here asserts AR1 wins. Persistence leading is the expected
    # result on a macro level series and is not a failure of the run.
    assert set(got["beat_persistence_on"]) <= set(EM.METHODS)


def test_running_the_same_date_twice_appends_no_second_measurement(
        scored_root):
    first = _method_payload(scored_root, run_id="m1")
    second = _method_payload(scored_root, run_id="m2")
    assert first["performance_records_written"] > 0
    assert second["performance_records_written"] == 0, (
        "the same measurement on the same date was written twice")
    assert second["performances_held"] == first["performances_held"]


def test_a_series_too_short_to_score_is_counted_not_scored(tmp_path):
    """Filling the ledger with rows whose only content is 'too small'."""
    (tmp_path / "reports" / "market").mkdir(parents=True)
    ledger = tmp_path / LS.DEFAULT_PATH
    ledger.parent.mkdir(parents=True, exist_ok=True)
    rows = [_observation("SHORT", f"2026-0{i + 1}-01", 3.0 + i * 0.1,
                         f"2026-0{i + 1}-15") for i in range(4)]
    ledger.write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    got = _method_payload(tmp_path)
    assert got["series_too_short"] == 1
    assert got["series_scored"] == 0
    assert got["evaluations"] == 0


def test_the_scoring_never_reads_a_figure_published_after_the_cycle_date(
        scored_root):
    """Vintage safety, at the seam rather than in the module's docstring."""
    _method_payload(scored_root, as_of="2022-01-01", run_id="early")
    _method_payload(scored_root, as_of=AS_OF, run_id="late")

    store = LS.LearningStore(scored_root / LS.DEFAULT_PATH)
    by_date = {}
    for row in store.method_performances():
        by_date.setdefault(row["measured_as_of"], []).append(row)
    # Asserted unconditionally. Guarding this behind "if both dates are
    # present" would make the test pass silently the day the early cycle
    # stopped scoring at all, which is the failure it exists to catch.
    assert {"2022-01-01", AS_OF} <= set(by_date), (
        f"both cycles must have scored; got {sorted(by_date)}")
    early_points = max(r["predictions"] for r in by_date["2022-01-01"])
    late_points = max(r["predictions"] for r in by_date[AS_OF])
    assert early_points < late_points, (
        f"a cycle dated 2022 scored on {early_points} points and one dated "
        f"2026 on {late_points}; equal counts mean the early cycle read "
        "figures that had not been published yet")
