"""§10/§30: the holdout cannot influence anything, and the wall proves it.

The guard here is not "we split the data". It is that the holdout is HASHED
when the partition is created, counted every time it is read, and re-checked
at the end -- so an extra peek, or a re-derivation from a different feature
set, is a refusal rather than a matter of discipline.
"""
from __future__ import annotations

import pytest

from intent_engine.econ import forecast as FC
from intent_engine.econ import panel as PN
from intent_engine.econ.vocabulary import EconError


def _rows(n=120, start_year=2000):
    """Deterministic rows with a real signal, so a fitted model is meaningful."""
    out = []
    for i in range(n):
        y = start_year + i // 4
        origin = f"{y}-{[2, 5, 8, 11][i % 4]:02d}-15"
        drive = (i % 7) / 7.0
        out.append(FC.Row(
            origin=origin, target="T/180d", horizon_days=180,
            features={"a_level": drive, "b_level": 1 - drive,
                      "c_level": (i % 3) / 3.0},
            outcome=drive > 0.5,
            regime="EARLY" if i < n // 2 else "LATE",
            outcome_knowable_at=f"{y + 1}-01-01"))
    return out


# =============================================================================
# The seal
# =============================================================================

def test_a_sealed_holdout_that_changed_is_refused():
    """Re-deriving the holdout from a different feature set is the quiet
    version of tuning on it, and it changes the hash."""
    rows = _rows()
    p = FC.split_by_date(rows, train_end="2010-01-01",
                         validation_end="2020-01-01")
    assert p.holdout, "the fixture must produce a holdout or this is vacuous"
    # Mutate one holdout row's features, as a re-derivation would.
    victim = p.holdout[0]
    p.holdout = (FC.Row(origin=victim.origin, target=victim.target,
                        horizon_days=victim.horizon_days,
                        features={**victim.features, "a_level": 99.0},
                        outcome=victim.outcome, regime=victim.regime),
                 ) + p.holdout[1:]
    p.read_holdout()
    with pytest.raises(FC.PartitionViolation) as e:
        p.assert_untouched(expected_reads=1)
    assert "changed after the partition was sealed" in str(e.value)


def test_an_extra_holdout_read_is_refused():
    """Every extra read is a chance for the holdout to have influenced a
    choice, and the guard does not distinguish deliberate from accidental."""
    p = FC.split_by_date(_rows(), train_end="2010-01-01",
                         validation_end="2020-01-01")
    p.read_holdout()
    p.read_holdout()
    with pytest.raises(FC.PartitionViolation) as e:
        p.assert_untouched(expected_reads=1)
    assert "read 2 time(s)" in str(e.value)


def test_a_holdout_never_read_is_also_refused():
    """A reported holdout score with no holdout read is fictional."""
    p = FC.split_by_date(_rows(), train_end="2010-01-01",
                         validation_end="2020-01-01")
    with pytest.raises(FC.PartitionViolation):
        p.assert_untouched(expected_reads=1)


def test_exactly_one_read_passes():
    """Positive control: the guard must be satisfiable, or nothing can use it."""
    p = FC.split_by_date(_rows(), train_end="2010-01-01",
                         validation_end="2020-01-01")
    p.read_holdout()
    p.assert_untouched(expected_reads=1)


# =============================================================================
# The split is chronological
# =============================================================================

def test_the_split_is_chronological_not_random():
    """A random split over a time series puts tomorrow in training and
    yesterday in test, which shows up as excellent performance."""
    rows = _rows()
    p = FC.split_by_date(rows, train_end="2010-01-01",
                         validation_end="2020-01-01")
    assert p.train and p.validation and p.holdout
    assert max(r.origin for r in p.train) < min(r.origin
                                                for r in p.validation)
    assert max(r.origin for r in p.validation) < min(r.origin
                                                     for r in p.holdout)


def test_walk_forward_never_trains_on_its_own_test_window():
    rows = _rows()
    for f in FC.walk_forward(rows, ["a_level", "b_level"], folds=4):
        tested = {k for k, *_ in f.predictions}
        trained = {r.key for r in sorted(rows, key=lambda r: (r.origin,
                                                              r.target))
                   [:f.n_train]}
        assert not (tested & trained), (
            f"fold {f.fold} tested on {len(tested & trained)} rows it "
            "trained on")


# =============================================================================
# Standardisation uses training rows only
# =============================================================================

def test_standardisation_comes_from_training_rows_only():
    """Computing means over the full sample is a nearly invisible leak worth
    a real amount of apparent skill."""
    train = _rows(80)
    model = FC.fit(train, ["a_level"])
    col = [r.features["a_level"] for r in train]
    assert abs(model.means[0] - sum(col) / len(col)) < 1e-9


def test_a_fit_below_the_row_floor_is_refused():
    with pytest.raises(EconError) as e:
        FC.fit(_rows(10), ["a_level"])
    assert "below the floor" in str(e.value)


def test_a_fitted_model_beats_the_base_rate_on_a_real_signal():
    """The positive control for the whole harness. If a model with a planted
    signal cannot beat the base rate, the comparison measures nothing."""
    rows = _rows(160)
    folds = FC.walk_forward(rows, ["a_level", "b_level", "c_level"], folds=4)
    preds = [p for f in folds for p in f.predictions]
    assert preds
    assert FC.directional_accuracy(preds) > 0.6, (
        "the harness cannot recover a planted signal, so any null result it "
        "produces would be uninterpretable")


def test_both_models_see_identical_rows():
    """Fairness is a property of the harness. Two feature blocks, one loop."""
    rows = _rows(120)
    a = FC.walk_forward(rows, ["a_level"], folds=3)
    b = FC.walk_forward(rows, ["a_level", "b_level"], folds=3)
    assert [f.n_train for f in a] == [f.n_train for f in b]
    assert [{k for k, *_ in f.predictions} for f in a] == \
           [{k for k, *_ in f.predictions} for f in b]


# =============================================================================
# The panel's own vintage wall (§6)
# =============================================================================

def test_as_known_at_reads_the_vintage_not_the_period():
    """The mistake that looks correct: a wall keyed on the reference date
    lets a figure published later through."""
    p = PN.Panel()
    p.add(PN.Cell(series_id="X", observed_at="2008-06-01",
                  vintage_at="2008-09-15", value=2.5))
    p.finalise()
    assert p.as_known_at("2008-07-01") == {}, (
        "a June figure published in September is not knowable in July")
    assert p.as_known_at("2008-10-01")["X"].value == 2.5


def test_the_latest_knowable_revision_wins():
    p = PN.Panel()
    for vintage, value in (("2008-09-15", 2.5), ("2010-01-04", 3.5),
                           ("2026-01-02", 4.6)):
        p.add(PN.Cell(series_id="X", observed_at="2008-06-01",
                      vintage_at=vintage, value=value))
    p.finalise()
    assert p.latest_vintage_of("X", "2008-06-01", "2009-01-01").value == 2.5
    assert p.latest_vintage_of("X", "2008-06-01", "2011-01-01").value == 3.5
    assert p.latest_vintage_of("X", "2008-06-01", "2027-01-01").value == 4.6


def test_a_cell_published_before_its_own_period_is_refused():
    with pytest.raises(EconError):
        PN.Cell(series_id="X", observed_at="2008-06-01",
                vintage_at="2008-01-01", value=1.0)


def test_assert_no_leak_catches_a_value_read_too_early():
    p = PN.Panel()
    p.add(PN.Cell(series_id="X", observed_at="2008-06-01",
                  vintage_at="2008-09-15", value=2.5))
    p.finalise()
    used = {"X": p.cells["X"][0]}
    with pytest.raises(PN.VintageLeak):
        p.assert_no_leak("2008-07-01", used)
    p.assert_no_leak("2008-10-01", used)          # positive control


def test_absence_distinguishes_its_three_reasons():
    p = PN.Panel()
    p.add(PN.Cell(series_id="X", observed_at="2020-01-01",
                  vintage_at="2020-03-01", value=1.0))
    p.finalise()
    assert p.absence("X", "2010-01-01") == PN.NOT_STARTED
    assert p.absence("X", "2020-02-01") == PN.NOT_YET_PUBLISHED
    assert p.absence("NEVER_SEEN", "2020-01-01") == PN.NOT_STARTED


def test_a_node_with_no_availability_cannot_enter_the_panel():
    class _P:
        document_id = "X"

    class _N:
        node_id = "n1"
        kind = "saving_rate"
        node_class = "BEHAVIORAL"
        occurred_at = "2008-06-01"
        available_at = ""
        value = 2.5
        unit = "%"
        provenance = _P()

    with pytest.raises(PN.VintageLeak):
        PN.Panel().add_nodes([_N()])


def test_the_panel_round_trips_through_disk(tmp_path):
    p = PN.Panel()
    p.add(PN.Cell(series_id="X", observed_at="2008-06-01",
                  vintage_at="2008-09-15", value=2.5, kind="saving_rate"))
    p.finalise()
    dest = p.write(tmp_path / "panel.jsonl")
    back = PN.Panel.read(dest)
    assert back.summarise()["cells"] == 1
    assert back.as_known_at("2009-01-01")["X"].value == 2.5
