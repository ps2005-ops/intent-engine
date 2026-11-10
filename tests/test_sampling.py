"""Effective sample size — the correction that killed Day 2's false discovery.

The load-bearing tests are the ones that stop a result being credited to rows
it does not actually rest on.
"""
from intent_engine.market.sampling import (
    HIGH,
    LOW,
    MEDIUM,
    SampleSize,
    band,
    measure,
    merge_windows,
)


def _row(company, entry, exit_, event=None):
    return {"company_id": company, "entry_day": entry, "exit_day": exit_,
            "event_key": event}


# --- windows -----------------------------------------------------------------
def test_overlapping_windows_collapse_into_one():
    """Two companies held over the same fortnight share whatever the market
    did; they are not two independent tests."""
    assert merge_windows([("2026-01-01", "2026-01-21"),
                          ("2026-01-10", "2026-01-30")]) == \
        [("2026-01-01", "2026-01-30")]


def test_disjoint_windows_stay_separate():
    assert len(merge_windows([("2026-01-01", "2026-01-21"),
                              ("2026-03-01", "2026-03-21")])) == 2


def test_touching_windows_are_treated_as_overlapping():
    """A position exiting the day another enters still shares the market
    conditions at the join."""
    assert len(merge_windows([("2026-01-01", "2026-01-21"),
                              ("2026-01-21", "2026-02-10")])) == 1


def test_the_month_proxy_it_replaces_was_wrong_at_the_edges():
    """Two filings three days apart across a month boundary are highly
    correlated; calendar-month clustering called them independent."""
    across_boundary = merge_windows([("2026-01-30", "2026-02-20"),
                                     ("2026-02-02", "2026-02-23")])
    assert len(across_boundary) == 1, "month clustering would have said 2"


# --- the three counts --------------------------------------------------------
def test_n_eff_is_the_smallest_of_the_three_counts():
    """A result cannot be better supported than its most correlated dimension
    allows."""
    rows = [_row(f"c{i}", "2026-01-01", "2026-01-21") for i in range(20)]
    size = measure(rows)
    assert size.observations == 20
    assert size.windows == 1
    assert size.n_eff == 1


def test_several_signals_from_one_disclosure_count_as_one_event():
    rows = [_row("a", "2026-01-01", "2026-01-21", event="a:8-K:2026-01-01"),
            _row("a", "2026-01-01", "2026-01-21", event="a:8-K:2026-01-01")]
    assert measure(rows).events == 1


def test_design_effect_shows_how_much_the_naive_count_overstates():
    """Day 2's actual numbers: 64 rows, ~15 independent windows."""
    rows = []
    for w in range(15):
        for i in range(4):
            start = f"2026-{w+1:02d}-01" if w < 12 else f"2027-{w-11:02d}-01"
            end = f"2026-{w+1:02d}-21" if w < 12 else f"2027-{w-11:02d}-21"
            rows.append(_row(f"c{i}", start, end))
    size = measure(rows)
    assert size.observations == 60
    assert size.design_effect and size.design_effect > 3


# --- the verdict -------------------------------------------------------------
def test_day_2s_false_discovery_is_now_refused_automatically():
    """0.359 over 64 rows sitting in 15 windows. The naive band excludes
    0.500; the honest one does not. This had to be caught by hand that day."""
    rows = []
    for w in range(15):
        for i in range(4):
            rows.append(_row(f"c{i}", f"2026-{w % 12 + 1:02d}-0{i+1}",
                             f"2026-{w % 12 + 1:02d}-2{i+1}"))
    result = band(0.359, measure(rows))
    lo, hi = result["band"]
    assert lo <= 0.359 <= hi, "the honest band must contain the result"
    naive_lo, naive_hi = result["naive_band"]
    assert not (naive_lo <= 0.359 <= naive_hi), \
        "the fixture no longer reproduces the naive false positive"


def test_a_result_below_the_a_m5_threshold_is_unmeasurable_not_a_finding():
    rows = [_row("a", f"2026-{m:02d}-01", f"2026-{m:02d}-21")
            for m in range(1, 6)]
    assert "unmeasurable" in band(0.9, measure(rows))["verdict"]


def test_confidence_is_graded_on_n_eff_not_on_rows():
    """Thirty rows sharing three windows is three observations wearing a
    larger number."""
    crowded = measure([_row(f"c{i}", "2026-01-01", "2026-01-21")
                       for i in range(30)])
    assert crowded.observations == 30 and crowded.confidence == LOW

    spread = measure([_row("a", f"20{20+i//12:02d}-{i % 12 + 1:02d}-01",
                           f"20{20+i//12:02d}-{i % 12 + 1:02d}-21")
                      for i in range(30)])
    assert spread.confidence == HIGH


def test_no_observations_is_unmeasurable_not_zero():
    size = measure([])
    assert size.n_eff == 0 and size.design_effect is None
    assert band(None, size)["verdict"] == "unmeasurable"
