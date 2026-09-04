"""Discovery generates hypotheses. It is never allowed to generate facts."""
from __future__ import annotations

import datetime

import pytest

from intent_engine.market import macro_state as MS
from intent_engine.market import unsupervised as U


def month_series(values, *, series_id="S", kind=MS.INFLATION, area=MS.CA,
                 lag_days=30):
    out = []
    for i, v in enumerate(values):
        year, m = 2024 + i // 12, i % 12 + 1
        period = f"{year}-{m:02d}-01"
        pub = (datetime.date.fromisoformat(period)
               + datetime.timedelta(days=lag_days)).isoformat()
        out.append(MS.MacroObservation(
            state_kind=kind, area=area, series_id=series_id, label=series_id,
            value=float(v), unit="index", reference_period=period,
            published_at=pub, publication_basis=MS.ASSUMED_LAG, source="t"))
    return out


# --- the wall ----------------------------------------------------------------

def test_a_cluster_cannot_become_a_fact():
    found = U.Discovery(kind=U.REGIME, method=U.KMEANS, label="REGIME_1",
                        members=("2025-01",), research_question="q?")
    with pytest.raises(U.NotEvidence) as err:
        found.as_fact()
    assert "not something a source stated" in str(err.value)


def test_a_discovery_without_a_research_question_is_refused():
    with pytest.raises(U.DiscoveryRejected) as err:
        U.Discovery(kind=U.REGIME, method=U.KMEANS, label="R1")
    assert "picture" in str(err.value)


def test_a_discovery_has_exactly_one_standing():
    with pytest.raises(U.DiscoveryRejected):
        U.Discovery(kind=U.REGIME, method=U.KMEANS, label="R1",
                    research_question="q?", standing="OBSERVED")


def test_labels_are_ordinals_not_economic_names():
    obs = (month_series([100 + i for i in range(24)], series_id="A")
           + month_series([50 + (i % 5) for i in range(24)], series_id="B",
                          kind=MS.MARKET_RATE)
           + month_series([3 + (i % 3) for i in range(24)], series_id="C",
                          kind=MS.EMPLOYMENT))
    got = U.discover_regimes(obs, as_of="2026-06-01", groups=2,
                             methods=(U.KMEANS,))
    fitted = [d for d in got["discoveries"] if d["method"] == U.KMEANS]
    assert fitted and all(d["label"].startswith("REGIME_") for d in fitted)
    assert all("stagflation" not in d["label"].lower() for d in fitted)


# --- the panel ----------------------------------------------------------------

def test_the_panel_never_shows_a_month_a_figure_that_was_not_published_yet():
    obs = month_series([float(i) for i in range(24)], series_id="A",
                       lag_days=45)
    periods, series, values = U.monthly_panel(obs, as_of="2026-12-31",
                                              min_series=1)
    # January's figure (0.0) publishes mid-February, so the earliest row the
    # panel can hold is February's, carrying January's number.
    assert periods[0] == "2024-02" and values[0][0] == 0.0
    # Every row lags: the month's own figure is never in it.
    for month, row in zip(periods, values):
        assert row[0] < float(int(month[5:7]) - 1) + 12 * (
            int(month[:4]) - 2024) + 0.5


def test_a_slow_publisher_costs_a_month_not_a_column():
    """The defect: one absent early cell deleted the whole series."""
    fast = month_series([float(i) for i in range(24)], series_id="FAST",
                        lag_days=5)
    slow = month_series([float(i) for i in range(24)], series_id="SLOW",
                        lag_days=45, kind=MS.MARKET_RATE)
    _, series, _ = U.monthly_panel(fast + slow, as_of="2026-12-31",
                                   min_series=1)
    assert "SLOW" in series and "FAST" in series


def test_an_empty_ledger_yields_an_empty_panel_not_a_crash():
    assert U.monthly_panel([], as_of="2026-01-01") == ([], [], [])


def test_too_short_a_history_is_reported_as_unmeasurable():
    got = U.discover_regimes(month_series([1, 2, 3], series_id="A"),
                             as_of="2026-01-01")
    assert got["discoveries"] == []
    assert "not enough" in got["note"]


# --- scoring ------------------------------------------------------------------

def test_alternating_labels_score_no_better_than_shuffling():
    assert U.coherence([0, 1] * 8) <= 1.05


def test_persistent_labels_score_above_shuffling():
    assert U.coherence([0] * 8 + [1] * 8) > 1.5


def test_coherence_of_one_group_is_undefined_not_perfect():
    assert U.coherence([0] * 10) is None


def test_utility_is_none_when_it_cannot_be_measured():
    assert U.utility([0, 1, 0], [1.0, 2.0, 3.0]) is None


def test_utility_is_positive_only_when_the_group_predicts():
    labels = [0] * 8 + [1] * 8
    informative = [1.0, 1.1, 0.9, 1.0, 1.05, 0.95, 1.0, 1.1,
                   9.0, 9.1, 8.9, 9.0, 9.05, 8.95, 9.0, 9.1]
    noise = [1.0, 9.0] * 8
    assert U.utility(labels, informative) > 0.5
    assert U.utility(labels, noise) < 0


def test_an_unmeasured_utility_is_not_a_negative_result():
    score = U.DiscoveryScore(method=U.KMEANS, groups=2, separation=0.9,
                             utility=None)
    assert score.economically_useful is False
    assert score.as_dict()["utility"] is None


def test_geometry_alone_never_makes_a_discovery_useful():
    """The live finding, as a guard.

    On the real panel the fitted models score 0.46 on silhouette and NEGATIVE
    on utility, while the stated rule scores below zero on silhouette and
    +0.23 on utility. Whatever `economically_useful` reads, it must be reading
    utility and not separation.
    """
    tidy = U.DiscoveryScore(method=U.KMEANS, groups=2, separation=0.99,
                            coherence=3.0, stability=1.0, utility=-0.1)
    ugly = U.DiscoveryScore(method=U.RULE, groups=5, separation=-0.09,
                            coherence=1.02, stability=1.0, utility=0.23)
    assert tidy.economically_useful is False
    assert ugly.economically_useful is True


# --- the rule is scored alongside ---------------------------------------------

def test_the_deterministic_rule_is_scored_as_a_method():
    obs = (month_series([100 + i for i in range(24)], series_id="P",
                        kind=MS.INFLATION)
           + month_series([2 + (i % 4) for i in range(24)], series_id="R",
                          kind=MS.MARKET_RATE)
           + month_series([6 + (i % 3) for i in range(24)], series_id="E",
                          kind=MS.EMPLOYMENT))
    got = U.discover_regimes(obs, as_of="2026-12-31", groups=2,
                             methods=(U.KMEANS,))
    methods = {s["method"] for s in got["scores"]}
    assert U.RULE in methods and U.KMEANS in methods


def test_the_rule_refuses_to_classify_what_it_cannot_read():
    assert U.rule_regime([]) == "UNCLASSIFIED"
    only_rates = [MS.EconomicState(state_kind=MS.MARKET_RATE,
                                   standing=MS.OBSERVED, moved=MS.UP)]
    assert U.rule_regime(only_rates) == "UNCLASSIFIED"


def test_the_rule_names_the_four_combinations_it_can_read():
    def state(kind, moved):
        return MS.EconomicState(state_kind=kind, standing=MS.OBSERVED,
                                moved=moved)
    up_up = [state(MS.MARKET_RATE, MS.UP), state(MS.INFLATION, MS.UP)]
    assert U.rule_regime(up_up) == "RULE_TIGHTENING_INTO_PRICES"
    down_up = [state(MS.MARKET_RATE, MS.DOWN), state(MS.INFLATION, MS.UP)]
    assert U.rule_regime(down_up) == "RULE_ACCOMMODATIVE"


# --- exposure clusters ---------------------------------------------------------

def test_clustering_mostly_empty_profiles_is_refused():
    profiles = {f"c{i}": {} for i in range(6)}
    got = U.discover_exposure_clusters(profiles, as_of="2026-01-01")
    assert got["discoveries"] == []
    assert "emptiness" in got["note"]


def test_an_exposure_cluster_says_it_cannot_attest_a_rating():
    from intent_engine.market import company_exposure as CX

    def rated(company, dim):
        return CX.Exposure(company_id=company, dimension=dim,
                           standing=CX.OBSERVED, basis="we borrow at floating",
                           evidence_ids=("e1",))

    profiles = {
        "a": {CX.RATE: rated("a", CX.RATE)},
        "b": {CX.RATE: rated("b", CX.RATE)},
        "c": {CX.FX: rated("c", CX.FX)},
        "d": {CX.FX: rated("d", CX.FX)},
        "e": {CX.LABOR: rated("e", CX.LABOR)},
        "f": {},
    }
    got = U.discover_exposure_clusters(profiles, as_of="2026-01-01", groups=3)
    assert got["discoveries"]
    assert "not a rating" in got["note"]
    for d in got["discoveries"]:
        assert "filings" in d["research_question"]


# --- anomalies -----------------------------------------------------------------

def test_a_flat_series_produces_no_anomalies():
    got = U.find_anomalies(month_series([5.0] * 12, series_id="A"),
                           as_of="2026-12-31")
    assert got["discoveries"] == []


def test_a_single_jump_is_found_and_carries_a_question():
    # A series that sits still and then jumps: the shape whose median
    # absolute deviation is zero, which used to make it invisible.
    values = [5.0] * 10 + [50.0] + [5.0] * 3
    got = U.find_anomalies(month_series(values, series_id="A"),
                           as_of="2027-12-31")
    labels = [d["label"] for d in got["discoveries"]]
    assert any("2024-11" in lab for lab in labels), labels
    assert all(d["research_question"] for d in got["discoveries"])
    assert "revision" in got["note"]


def test_a_short_series_is_not_examined_for_anomalies():
    got = U.find_anomalies(month_series([1, 99, 1], series_id="A"),
                           as_of="2026-12-31")
    assert got["series_examined"] == 0


def test_the_summary_counts_hypotheses_not_knowledge():
    got = U.summarise(U.find_anomalies(
        month_series([5.0] * 10 + [50.0] + [5.0] * 3, series_id="A"),
        as_of="2027-12-31"))
    assert got["by_kind"][U.ANOMALY] >= 1
    assert got["all_have_a_research_question"] is True
    assert "not of things learned" in got["note"]
