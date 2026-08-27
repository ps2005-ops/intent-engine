"""The V2 power layer: release timing, effective sample, blocked folds.

Each test names the defect it exists to prevent. A test that only asserts a
function returns something is a test that cannot fail usefully.
"""
from __future__ import annotations

import datetime as _dt

import pytest

from intent_engine.econ import baselines as BS
from intent_engine.econ import blocked as BL
from intent_engine.econ import episodes as EPI
from intent_engine.econ import evaluation_record as ER
from intent_engine.econ import experiment as EX
from intent_engine.econ import forecast as FC
from intent_engine.econ import incremental as INC
from intent_engine.econ import panel as PN
from intent_engine.econ import power as PW
from intent_engine.econ import regime as RG
from intent_engine.econ import release as RL


# =============================================================================
# §4 RELEASE TIMING
# =============================================================================

def test_july_cpi_is_not_available_on_31_july():
    """The failure a monthly origin grid makes possible."""
    assert RL.released_at("CPIAUCSL", "2024-07-01") > "2024-07-31"
    assert RL.available_as_of("CPIAUCSL", "2024-07-31") == "2024-06-01"
    with pytest.raises(RL.ReleaseLeak):
        RL.assert_released("CPIAUCSL", "2024-07-01", "2024-07-31")


def test_a_quarterly_lag_is_measured_from_the_quarter_end():
    """`alfred._published_at` measured it from the quarter LABEL.

    Q1 is labelled 1 January, so first-of-next-month plus a 30-day lag put
    the advance GDP estimate in early March -- five weeks before it exists.
    """
    assert RL.released_at("GDPC1", "2024-01-01") >= "2024-04-01"
    assert RL.available_as_of("GDPC1", "2024-05-15") == "2024-01-01"


def test_every_series_in_the_release_table_states_a_basis():
    for r in RL.RULES:
        assert r.basis.strip(), f"{r.series_id} has a lag and no reason"


def test_a_series_with_no_release_rule_is_refused_not_guessed():
    with pytest.raises(RL.ReleaseLeak):
        RL.released_at("NOT_A_SERIES", "2024-01-01")


def test_quarterly_series_may_not_carry_non_quarter_months():
    with pytest.raises(RL.InterpolationRefused):
        RL.refuse_interpolation("GDPC1", ["2024-01-01", "2024-02-01"])
    RL.refuse_interpolation("GDPC1", ["2024-01-01", "2024-04-01"])


def test_a_rate_that_crosses_zero_uses_a_difference_not_a_ratio():
    """PSAVERT printed negative in 1999 and passed through zero.

    A relative change divides by that base: the feature was undefined at
    three origins, the series was dropped for imbalance, and only the
    instrument guard revealed it.
    """
    hist = [("p", 0.0)] * 13 + [("q", -1.0)]
    assert EX.change("PSAVERT", hist, 12) == -1.0
    assert EX.change("INDPRO", hist, 12) is None


# =============================================================================
# §5 EFFECTIVE SAMPLE
# =============================================================================

def test_more_rows_from_the_same_periods_is_not_more_information():
    """§5's whole point, as an assertion rather than a hope."""
    rows, values = [], []
    for i in range(40):
        o = f"{2000 + i // 4}-{(i % 4) * 3 + 1:02d}-15"
        for _ in range(10):
            rows.append(o)
            values.append(float(i))
    s = PW.measure(origins=rows, values=values)
    assert s.raw_rows == 400
    assert s.unique_origins == 40
    assert s.effective_origins < s.unique_origins, (
        "perfectly autocorrelated origins were counted as independent")


def test_headline_never_renders_a_row_count_alone():
    s = PW.measure(origins=["2000-01-15", "2000-02-15", "2000-03-15"],
                   values=[1.0, 2.0, 3.0])
    h = s.headline()
    for word in ("origins", "effective", "episodes"):
        assert word in h, f"the headline omits {word}"


def test_a_phase_map_beats_contiguity_for_a_global_sample():
    """Consecutive monthly origins spanning many crises are ONE run of dates
    and MANY macroeconomic phases. Counting the first is how a 1978-2026
    sample reported '1 episode'."""
    origins = [f"{y}-{m:02d}-15" for y in range(2000, 2004)
               for m in range(1, 13)]
    plain = PW.measure(origins=origins, values=[float(i) for i in
                                                range(len(origins))])
    assert plain.independent_episodes == 1

    class _E:
        def __init__(self, i, lo, hi):
            self.episode_id, self.start_as_known, self.end_as_known = i, lo, hi
    eps = [_E("EP_A", "2000-01-15", "2000-12-15"),
           _E("EP_B", "2002-01-15", "2002-12-15")]
    phases = PW.phase_map(origins, eps)
    withmap = PW.measure(origins=origins,
                         values=[float(i) for i in range(len(origins))],
                         phase_of=phases)
    assert withmap.independent_episodes >= 3


def test_projected_mde_scales_with_independent_units_not_rows():
    """A monotone fixture would be maximally autocorrelated and effective
    sample would FALL as rows rise -- which is the module working, and the
    wrong thing to assert. This uses a mildly persistent series instead."""
    import random
    rng = random.Random(7)

    def vals(n, ar=0.3):
        out, lvl = [], 0.0
        for _ in range(n):
            lvl = ar * lvl + rng.gauss(0, 1)
            out.append(lvl)
        return out
    a = PW.measure(origins=[f"2000-{m:02d}-15" for m in range(1, 13)],
                   values=vals(12))
    b = PW.measure(origins=[f"{y}-{m:02d}-15" for y in range(2000, 2004)
                            for m in range(1, 13)],
                   values=vals(48))
    assert b.effective_origins > a.effective_origins
    assert PW.projected_mde(0.02, a, b) < 0.02


# =============================================================================
# §8/§9 DEPENDENCE AND FOLDS
# =============================================================================

def _rows(n=120, horizon=360):
    d = _dt.date(1998, 2, 15)
    out = []
    for i in range(n):
        o = (d + _dt.timedelta(days=30 * i)).isoformat()
        res = (d + _dt.timedelta(days=30 * i + horizon)).isoformat()
        for t in "abcde":
            out.append(FC.Row(origin=o, target=t, horizon_days=horizon,
                              features={"x": float(i)}, outcome=i % 2 == 0,
                              outcome_knowable_at=res))
    return out


def test_blocked_folds_purge_training_rows_that_resolve_into_the_test_window():
    folds = BL.make_folds(_rows(), folds=5)
    assert folds
    BL.assert_folds_clean(folds)
    assert sum(f.purged for f in folds) > 0, (
        "nothing was purged on a 360-day horizon with monthly origins, so "
        "the purge is not running")
    for f in folds:
        assert f.train_end < f.test_start


def test_shuffled_rows_cannot_produce_clean_folds():
    import random
    rows = _rows()
    random.Random(1).shuffle(rows)
    # make_folds sorts internally, so cleanliness survives a shuffled INPUT.
    # What must never survive is a fold whose train reaches into its test.
    folds = BL.make_folds(rows, folds=5)
    BL.assert_folds_clean(folds)


def test_a_single_block_yields_no_interval_rather_than_a_zero_width_one():
    """'[+0.00000, +0.00000]' reads as certainty and means 'undefined'."""
    lo, hi, _p, k = INC._episode_bootstrap_ci(
        [0.1, -0.1, 0.2], ["2008-01-15"] * 3, seed=1)
    assert k == 1 and lo is None and hi is None


def test_an_episode_floor_of_three_is_enforced_on_robustness():
    c = INC.Comparison(
        name="x", dimension="d", regime="ALL", horizon_days=0, population="p",
        n_paired=100, base_score=0.3, augmented_score=0.2, delta=0.1,
        ci_low=0.05, ci_high=0.15, p_value=0.01, verdict=INC.IMPROVEMENT,
        n_clusters=10, n_episodes=2, fdr_adjusted=True, survives_fdr=True,
        mde=0.02)
    assert not c.robust, "two episodes must not be reported as robust"
    # The guard must fire on the state a reader would act on -- an interval
    # clear of zero that survived the family -- not on `robust`, which has
    # already applied the floor and would make the guard unable to fail.
    with pytest.raises(INC.ClusteringDefect):
        INC.assert_not_promoted_underpowered(c)
    ok = INC.Comparison(
        name="x", dimension="d", regime="ALL", horizon_days=0, population="p",
        n_paired=100, base_score=0.3, augmented_score=0.2, delta=0.1,
        ci_low=0.05, ci_high=0.15, p_value=0.01, verdict=INC.IMPROVEMENT,
        n_clusters=10, n_episodes=5, fdr_adjusted=True, survives_fdr=True,
        mde=0.02)
    assert ok.robust
    INC.assert_not_promoted_underpowered(ok)


def test_one_cluster_per_row_is_refused():
    c = INC.Comparison(
        name="x", dimension="d", regime="ALL", horizon_days=0, population="p",
        n_paired=100, base_score=0.3, augmented_score=0.2, delta=0.1,
        ci_low=0.05, ci_high=0.15, p_value=0.01, verdict=INC.IMPROVEMENT,
        n_clusters=100, n_episodes=5, fdr_adjusted=True, survives_fdr=True,
        mde=0.02)
    with pytest.raises(INC.ClusteringDefect):
        INC.assert_clusters_are_origins(c)


# =============================================================================
# §7 EPISODES
# =============================================================================

def test_a_contiguous_crisis_is_one_episode_not_many():
    readings = [
        RG.RegimeReading(as_of=f"2008-{m:02d}-15",
                         regimes=("CREDIT_STRESS",), evidence={},
                         vintage_cutoff=f"2008-{m:02d}-15",
                         stress_families_evaluated=4)
        for m in range(1, 13)]
    eps = EPI.discover(readings)
    assert len(eps) == 1
    assert eps[0].origin_count == 12


def test_two_crises_separated_by_a_normalisation_are_two_episodes():
    def calm(d):
        return RG.RegimeReading(as_of=d, regimes=("LOW_VOL_EXPANSION",),
                                evidence={}, vintage_cutoff=d,
                                stress_families_evaluated=4)

    def stress(d):
        return RG.RegimeReading(as_of=d, regimes=("CREDIT_STRESS",),
                                evidence={}, vintage_cutoff=d,
                                stress_families_evaluated=4)
    rs = ([stress(f"2008-{m:02d}-15") for m in range(1, 4)]
          + [calm(f"2009-{m:02d}-15") for m in range(1, 11)]
          + [stress(f"2010-{m:02d}-15") for m in range(1, 4)])
    assert len(EPI.discover(rs)) == 2


def test_the_coverage_audit_separates_a_miss_from_an_unreachable_window():
    audit = EPI.coverage_audit([], ("1998-02-15", "2026-08-15"))
    statuses = {r["window"]: r["status"] for r in audit["windows"]}
    assert statuses["1973_75"] == "OUT_OF_REACH"
    assert statuses["2007_09"] == "MISSED"


def test_calm_is_reachable_before_the_credit_series_exists():
    """A negative control that can only occur after 2012 is not a control
    for calm; it is a control for 'after 2012'."""
    r = RG.RegimeReading(
        as_of="2004-06-15", regimes=("LOW_VOL_EXPANSION",),
        evidence={"unemployment_change_pp": -0.1, "inflation_yoy": 0.02,
                  "curve_slope_pp": 1.0},
        vintage_cutoff="2004-06-15", missing=("DRCCLACBS",),
        stress_families_evaluated=3)
    assert r.holds(RG.LOW_VOL_EXPANSION)
    assert not r.confident, "a partial calm must not read as a complete one"
    assert RG.CALM_QUORUM == 3


# =============================================================================
# §10 THE BASELINE LADDER
# =============================================================================

def test_a_macro_model_that_loses_to_a_constant_fails_the_gate():
    scores = {
        BS.BASE_RATE: BS.BaselineScore(BS.BASE_RATE, 0.20, 100, 0.6),
        BS.PERSISTENCE: BS.BaselineScore(BS.PERSISTENCE, 0.22, 100, 0.6),
        BS.AR: BS.BaselineScore(BS.AR, 0.23, 100, 0.6),
        BS.MACRO: BS.BaselineScore(BS.MACRO, 0.25, 100, 0.5),
    }
    g = BS.gate(scores)
    assert not g.passed
    assert BS.BASE_RATE in g.lost_to


def test_a_macro_model_that_beats_every_trivial_rung_passes():
    scores = {
        BS.BASE_RATE: BS.BaselineScore(BS.BASE_RATE, 0.25, 100, 0.6),
        BS.PERSISTENCE: BS.BaselineScore(BS.PERSISTENCE, 0.26, 100, 0.6),
        BS.AR: BS.BaselineScore(BS.AR, 0.24, 100, 0.6),
        BS.MACRO: BS.BaselineScore(BS.MACRO, 0.20, 100, 0.7),
    }
    assert BS.gate(scores).passed


def test_persistence_reads_the_targets_own_last_move():
    """It used to read the PREVIOUS ROW's outcome -- a different target at
    the same origin, so 'persistence' predicted housing from industrial
    production."""
    assert BS.PERSISTENCE_FEATURE == "self_last_move"


# =============================================================================
# §2 THE EVALUATION REGISTRY
# =============================================================================

def _ev(eid, supersedes=""):
    return ER.Evaluation(
        evaluation_id=eid, supersedes=supersedes, reason="because",
        method=ER.CLUSTER_BOOTSTRAP, delta=-0.01, ci_low=-0.02, ci_high=0.01,
        raw_rows=500, unique_origins=50, effective_origins=35.0,
        independent_episodes=1, code_sha="abc", panel_hash="def",
        preregistration_hash="ghi", at="2026-08-27",
        original_method=ER.ROW_BOOTSTRAP if supersedes else "")


def test_a_correction_may_not_reuse_the_id_it_corrects(tmp_path):
    p = tmp_path / "reg.jsonl"
    ER.append(_ev("A"), path=p)
    with pytest.raises(ER.RegistryViolation):
        ER.append(_ev("A"), path=p)


def test_a_correction_must_name_something_that_exists(tmp_path):
    p = tmp_path / "reg.jsonl"
    with pytest.raises(ER.RegistryViolation):
        ER.append(_ev("B", supersedes="NOTHING"), path=p)


def test_an_evaluation_with_no_stated_reason_is_refused():
    with pytest.raises(Exception):
        ER.Evaluation(
            evaluation_id="X", supersedes="", reason="  ",
            method=ER.ROW_BOOTSTRAP, delta=0.0, ci_low=0.0, ci_high=0.0,
            raw_rows=1, unique_origins=1, effective_origins=1.0,
            independent_episodes=1, code_sha="", panel_hash="",
            preregistration_hash="", at="2026-08-27")


def test_a_registry_headline_carries_all_four_sample_numbers():
    h = _ev("C").headline()
    for word in ("rows", "origins", "effective", "episodes"):
        assert word in h


# =============================================================================
# §3 THE PANEL
# =============================================================================

def test_compaction_does_not_change_any_as_of_read():
    p = PN.Panel()
    vals = [("2020-02-01", 1.0), ("2020-03-01", 1.0), ("2020-04-01", 2.0),
            ("2020-05-01", 2.0), ("2020-06-01", 3.0)]
    for v, val in vals:
        p.add(PN.Cell(series_id="X", observed_at="2020-01-01", vintage_at=v,
                      value=val))
    p.finalise()
    reads = {d: p.latest_vintage_of("X", "2020-01-01", d).value
             for d in ("2020-02-15", "2020-03-15", "2020-04-15",
                       "2020-05-15", "2020-06-15")}
    n_before = len(p.cells["X"])
    p.compact()
    after = {d: p.latest_vintage_of("X", "2020-01-01", d).value
             for d in reads}
    assert after == reads
    assert len(p.cells["X"]) < n_before


def test_a_revising_series_may_not_carry_an_assumed_lag_cell():
    """The leak that overwrote the walled panel: today's value under a
    historical release date."""
    p = PN.Panel()
    p.add(PN.Cell(series_id="PSAVERT", observed_at="2008-06-01",
                  vintage_at="2008-07-31", value=4.6,
                  revision_state=PN.ASSUMED_LAG))
    p.finalise()
    with pytest.raises(PN.VintageLeak):
        p.assert_no_assumed_lag(["PSAVERT"])


def test_the_panel_reports_a_content_hash_so_a_baseline_can_name_its_panel():
    p = PN.Panel()
    p.add(PN.Cell(series_id="X", observed_at="2020-01-01",
                  vintage_at="2020-02-01", value=1.0))
    p.finalise()
    assert len(p.summarise()["content_hash"]) == 16


# =============================================================================
# STRUCTURAL GUARDS
# =============================================================================

def test_a_trending_level_is_refused_and_a_rate_level_is_not():
    EX.assert_no_trending_levels(["UNRATE_lvl", "DFF_lvl", "CPIAUCSL_yoy"])
    with pytest.raises(EX.BlockDefect):
        EX.assert_no_trending_levels(["CPIAUCSL_lvl"])


def test_a_block_that_lost_a_live_instrument_is_refused():
    EX.assert_all_live_instruments_present(["A", "B"], ["A", "B"])
    with pytest.raises(EX.BlockDefect):
        EX.assert_all_live_instruments_present(["A"], ["A", "B"])


def test_balanced_names_drops_a_feature_that_is_absent_at_some_origins():
    """A missing change feature becomes 0.0, which claims 'did not move'."""
    rows = [FC.Row(origin="2000-01-15", target="t", horizon_days=180,
                   features={"A_yoy": 1.0, "B_yoy": 1.0}, outcome=True),
            FC.Row(origin="2000-02-15", target="t", horizon_days=180,
                   features={"A_yoy": 1.0}, outcome=False)]
    kept, dropped = EX.balanced_names(rows, ("A", "B"))
    assert kept == ["A_yoy"] and dropped == ["B_yoy"]
