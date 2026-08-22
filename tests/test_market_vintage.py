"""The wall raises. A replay that can see one row it should not is worse than
no replay, because the wrong number it produces looks exactly like a right one.
"""
from __future__ import annotations

import pytest

from intent_engine.market import vintage as V


def row(observed="", occurred="", record="evidence", **kw):
    out = {"record": record}
    if observed:
        out["observed_at"] = observed
    if occurred:
        out["occurred_at"] = occurred
    out.update(kw)
    return out


# --- known-by vs happened-by ------------------------------------------------

def test_a_row_that_happened_before_but_was_observed_after_is_withheld():
    """The contract signed on the 3rd, announced on the 11th."""
    corpus = [row(observed="2026-08-11", occurred="2026-08-03")]
    got = V.freeze(corpus, as_of="2026-08-05")
    assert got.admitted == ()
    assert len(got.withheld_not_yet_known) == 1


def test_the_leak_surface_counts_what_occurrence_filtering_would_admit():
    corpus = [row(observed="2026-08-11", occurred="2026-08-03"),
              row(observed="2026-08-11", occurred="2026-08-10"),
              row(observed="2026-08-01", occurred="2026-07-30")]
    got = V.freeze(corpus, as_of="2026-08-05")
    assert len(got.admitted) == 1
    assert got.leak_surface == 1, (
        "only the row that had already happened by as_of is a leak an "
        "occurrence-time filter would have let through")


def test_admission_uses_observation_even_when_occurrence_is_absent():
    got = V.freeze([row(observed="2026-08-01")], as_of="2026-08-05")
    assert len(got.admitted) == 1


def test_an_undated_row_is_excluded_and_counted_never_admitted():
    got = V.freeze([row(occurred="2026-07-01")], as_of="2026-08-05")
    assert got.admitted == ()
    assert len(got.withheld_undated) == 1


def test_freezing_without_an_instant_is_refused():
    with pytest.raises(V.VintageViolation) as err:
        V.freeze([row(observed="2026-08-01")], as_of="")
    assert "admits everything" in str(err.value)


# --- the wall raises --------------------------------------------------------

def test_checking_a_future_row_raises_rather_than_filtering():
    wall = V.VintageWall([row(observed="2026-08-01")], as_of="2026-08-05")
    with pytest.raises(V.VintageViolation) as err:
        wall.check(row(observed="2026-08-09"))
    assert "nobody knew this yet" in str(err.value)


def test_the_violation_names_the_leak_when_occurrence_precedes_the_wall():
    wall = V.VintageWall([], as_of="2026-08-05")
    with pytest.raises(V.VintageViolation) as err:
        wall.check(row(observed="2026-08-11", occurred="2026-08-03"))
    assert "that is the leak" in str(err.value)


def test_an_undated_row_cannot_be_placed_against_the_wall():
    wall = V.VintageWall([], as_of="2026-08-05")
    with pytest.raises(V.VintageViolation) as err:
        wall.check(row(occurred="2026-08-03"))
    assert "would make the vintage a guess" in str(err.value)


def test_guarding_a_sequence_raises_on_the_first_bad_row():
    wall = V.VintageWall([], as_of="2026-08-05")
    with pytest.raises(V.VintageViolation):
        wall.guard([row(observed="2026-08-01"), row(observed="2026-08-09")])


def test_a_row_the_wall_handed_out_passes_its_own_check():
    wall = V.VintageWall([row(observed="2026-08-01")], as_of="2026-08-05")
    for got in wall.rows():
        assert wall.check(got) is got


# --- the wall cannot advance ------------------------------------------------

def test_moving_the_wall_forward_is_refused():
    wall = V.VintageWall([row(observed="2026-08-01")], as_of="2026-08-05")
    with pytest.raises(V.VintageViolation) as err:
        wall.at("2026-08-20")
    assert "reading the future one step at a time" in str(err.value)


def test_moving_the_wall_backward_narrows_the_corpus():
    corpus = [row(observed="2026-08-01"), row(observed="2026-08-04")]
    wall = V.VintageWall(corpus, as_of="2026-08-05")
    assert len(wall.rows()) == 2
    assert len(wall.at("2026-08-02").rows()) == 1


def test_narrowing_does_not_resurrect_rows_from_beyond_the_original_wall():
    corpus = [row(observed="2026-08-01"), row(observed="2026-09-01")]
    wall = V.VintageWall(corpus, as_of="2026-08-05")
    narrowed = wall.at("2026-08-03")
    assert all(V.observation_time(r) <= "2026-08-03" for r in narrowed.rows())


# --- reads are counted, and filtering by kind stays behind the wall ---------

def test_reads_are_counted_so_a_replay_can_show_it_used_the_wall():
    wall = V.VintageWall([row(observed="2026-08-01")], as_of="2026-08-05")
    assert wall.reads == 0
    wall.rows()
    wall.rows(record="evidence")
    assert wall.reads == 2


def test_filtering_by_record_kind_never_widens_the_vintage():
    corpus = [row(observed="2026-08-01", record="evidence"),
              row(observed="2026-09-01", record="evidence")]
    wall = V.VintageWall(corpus, as_of="2026-08-05")
    assert len(wall.rows(record="evidence")) == 1


# --- episode selection is blind to outcomes ---------------------------------

def test_episodes_are_a_fixed_cadence_not_a_selection_of_interesting_dates():
    corpus = [row(observed="2026-01-01")]
    got = V.episodes(corpus, starting="2026-01-01", ending="2026-04-01",
                     every_days=30)
    assert got == ["2026-01-01", "2026-01-31", "2026-03-02", "2026-04-01"]


def test_episodes_drop_only_instants_with_too_little_data():
    corpus = [row(observed="2026-03-01")]
    got = V.episodes(corpus, starting="2026-01-01", ending="2026-04-01",
                     every_days=30, minimum_rows=1)
    assert got == ["2026-03-02", "2026-04-01"], (
        "instants before any data exists carry no state to build from")


def test_episode_selection_reads_no_outcome_field():
    """Selection must not be able to see what happened next.

    Checked over the PARSED source, not the text. A substring search matches
    the docstring that explains why the field is absent, so the guard fails
    exactly when the code is best documented — a trap this project has walked
    into before.
    """
    import ast
    import inspect

    tree = ast.parse(textwrap_dedent(inspect.getsource(V.episodes)))
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    names |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    names |= {c.value for c in ast.walk(tree)
              if isinstance(c, ast.Constant) and isinstance(c.value, str)
              and "\n" not in c.value}
    forbidden = {"outcome", "outcomes", "result", "resolved", "correct",
                 "was_right", "realized"}
    leaked = forbidden & names
    assert not leaked, (
        f"episodes() reads {sorted(leaked)}; choosing episodes by what "
        "happened is choosing the ones the engine already knows the answer to")


def textwrap_dedent(text: str) -> str:
    import textwrap

    return textwrap.dedent(text)


def test_a_bad_episode_window_is_refused():
    with pytest.raises(V.VintageViolation):
        V.episodes([], starting="not-a-date", ending="2026-04-01")
    with pytest.raises(V.VintageViolation):
        V.episodes([], starting="2026-01-01", ending="2026-04-01",
                   every_days=0)
