"""Replay under a vintage wall, and the attacks that must go through it.

D-REP-002. The live corpus cannot run this yet and the reason is measured
rather than assumed: all 2344 macro observations carry `retrieved_at` in a
single month, 2026-08, while their `published_at` spans 2024-2026. The engine
learned every historical figure at once. At any historical instant the
admitted vintage is EMPTY, so there is no T0 at which it knew anything.

That is BLOCKED_DATA, and the tempting repair is the exact defect D-REP-001
built the wall against: filtering on publication time instead of observation
time would admit 1572 rows at 2026-01-01 that nobody had seen, and the replay
would look entirely healthy.

So the fixtures here carry a REAL observation spread. They prove the
machinery on a corpus shaped like the one the engine will have after it has
been running for a year, and the leak attacks prove the wall stops the
shortcut that would make the live corpus appear usable today.
"""
from __future__ import annotations

import datetime as dt

import pytest

from intent_engine.market import macro_state as MS
from intent_engine.market import thesis_replay as TR
from intent_engine.market import vintage as V


def _observation(period, value, *, published, retrieved,
                 series_id="CA10Y", area="CA", kind="MARKET_RATE"):
    """A figure the engine saw on `retrieved`, about `period`."""
    return {
        "record": "macro_observation", "state_kind": kind,
        "series_id": series_id, "label": "CA 10-year yield", "value": value,
        "unit": "%", "measure": "LEVEL", "standing": "OBSERVED", "area": area,
        "reference_period": period, "published_at": published,
        "retrieved_at": retrieved, "publication_basis": "PUBLISHER",
        "source": "https://example.test/s",
    }


def _corpus(months=30, start=(2024, 1)):
    """A series the engine watched as it happened: retrieved ~ published.

    This is the shape the live ledger does NOT have, and the difference is
    the whole blocker.
    """
    rows = []
    year, month = start
    value = 3.0
    for i in range(months):
        period = f"{year}-{month:02d}-01"
        published = (dt.date(year, month, 1)
                     + dt.timedelta(days=14)).isoformat()
        # Observed the day after publication: a system that was running.
        retrieved = (dt.date(year, month, 1)
                     + dt.timedelta(days=15)).isoformat()
        value += 0.15 if i % 3 else -0.1
        rows.append(_observation(period, round(value, 4),
                                 published=published, retrieved=retrieved))
        month += 1
        if month > 12:
            month, year = 1, year + 1
    return rows


CORPUS = _corpus()
LAST = max(r["retrieved_at"] for r in CORPUS)


# --- the sample is chosen without reading the answer -------------------------

def test_episodes_are_chosen_by_a_stated_rule_over_a_stated_window():
    got = TR.select_episodes(CORPUS, starting="2024-06-01", ending=LAST,
                             horizon_days=90, every_days=90,
                             minimum_rows=3, selected_at="2026-08-09")
    assert got, "no episode survived selection on a corpus built to yield some"
    for episode in got:
        assert episode.t1 > episode.t0
        assert "No outcome is read during selection" in episode.selection_rule
        assert episode.rows_visible_at_t0 >= 3


def test_selection_never_reads_what_happened_next():
    """The rule must be a function of the calendar and the vintage only.

    Reversing every value in the corpus changes every outcome and must not
    change which instants were selected. If it did, the sample would be a
    sample of the engine's own successes.
    """
    flipped = [dict(r, value=-r["value"]) for r in CORPUS]
    a = TR.select_episodes(CORPUS, starting="2024-06-01", ending=LAST,
                           horizon_days=90, every_days=90, minimum_rows=3)
    b = TR.select_episodes(flipped, starting="2024-06-01", ending=LAST,
                           horizon_days=90, every_days=90, minimum_rows=3)
    assert [e.t0 for e in a] == [e.t0 for e in b]
    assert [e.replay_id for e in a] == [e.replay_id for e in b]


def test_an_episode_whose_horizon_runs_past_the_corpus_is_excluded():
    got = TR.select_episodes(CORPUS, starting="2024-06-01", ending=LAST,
                             horizon_days=3650, every_days=90,
                             minimum_rows=3)
    assert got == [], (
        "an episode that cannot resolve inside the window was kept; its "
        "absence must be a property of the calendar, not of the outcome")


def test_an_episode_that_resolves_before_it_is_formed_is_refused():
    with pytest.raises(TR.ReplayRefused):
        TR.ReplaySelection(replay_id="r", t0="2025-06-01", t1="2025-01-01",
                           selection_rule="rule", selected_at="2025-06-01",
                           rows_visible_at_t0=10)


def test_an_episode_with_no_stated_rule_is_refused():
    with pytest.raises(TR.ReplayRefused) as err:
        TR.ReplaySelection(replay_id="r", t0="2025-01-01", t1="2025-06-01",
                           selection_rule="   ", selected_at="2025-01-01",
                           rows_visible_at_t0=10)
    assert "audited" in str(err.value)


# --- the prediction is locked before the answer is read ----------------------

def _episode():
    got = TR.select_episodes(CORPUS, starting="2024-06-01", ending=LAST,
                             horizon_days=120, every_days=120,
                             minimum_rows=3, selected_at="2026-08-09")
    assert got
    return got[0]


def test_a_replay_forms_a_prediction_and_resolves_it():
    locked, resolutions, meta = TR.run_episode(
        CORPUS, _episode(), series_id="CA10Y", area="CA",
        state_kind="MARKET_RATE")
    assert not meta.get("skipped"), meta.get("skipped")
    assert len(locked) == 1
    assert len(resolutions) == 1
    assert resolutions[0].verdict in TR.VERDICTS
    assert resolutions[0].observed_value is not None


def test_the_locked_prediction_digests_only_the_prediction():
    """A resolution appended later must not be able to change it."""
    locked, _, _ = TR.run_episode(CORPUS, _episode(), series_id="CA10Y",
                                  area="CA", state_kind="MARKET_RATE")
    before = locked[0].expectation_id
    again, _, _ = TR.run_episode(CORPUS, _episode(), series_id="CA10Y",
                                 area="CA", state_kind="MARKET_RATE")
    assert again[0].expectation_id == before


def test_an_expectation_without_a_falsifier_is_refused():
    with pytest.raises(TR.ReplayRefused) as err:
        TR.HistoricalExpectation(
            replay_id="r", thesis_id="t", subject="s", made_at="2025-01-01",
            condition="CA:MARKET_RATE", predicted_direction="UP",
            expected_mechanism="m", expected_observable="o",
            resolution_window_days=90, falsifier="")
    assert "teaches nothing" in str(err.value)


def test_an_expectation_must_name_what_would_show_the_mechanism_ran():
    with pytest.raises(TR.ReplayRefused) as err:
        TR.HistoricalExpectation(
            replay_id="r", thesis_id="t", subject="s", made_at="2025-01-01",
            condition="CA:MARKET_RATE", predicted_direction="UP",
            expected_mechanism="m", expected_observable="  ",
            resolution_window_days=90, falsifier="f")
    assert "UNTESTED for a reason nobody stated" in str(err.value)


# --- outcome and mechanism are scored apart ----------------------------------

def test_a_right_outcome_with_an_untested_mechanism_is_unresolved():
    """The verdict that stops the engine learning to be lucky."""
    assert TR.verdict_for(TR.RIGHT, TR.UNTESTED) == TR.UNRESOLVED
    assert TR.verdict_for(TR.RIGHT, TR.RIGHT) == \
        TR.OUTCOME_RIGHT_MECHANISM_RIGHT
    assert TR.verdict_for(TR.RIGHT, TR.WRONG) == \
        TR.OUTCOME_RIGHT_MECHANISM_WRONG


def test_a_wrong_outcome_with_a_real_mechanism_is_kept_apart():
    assert TR.verdict_for(TR.WRONG, TR.RIGHT) == \
        TR.OUTCOME_WRONG_MECHANISM_PLAUSIBLE
    assert TR.verdict_for(TR.WRONG, TR.WRONG) == \
        TR.OUTCOME_WRONG_MECHANISM_WRONG


def test_an_untested_mechanism_must_say_why():
    with pytest.raises(TR.ReplayRefused) as err:
        TR.ReplayResolution(
            replay_id="r", thesis_id="t", expectation_id="e",
            resolved_at="2025-06-01", outcome=TR.RIGHT,
            mechanism=TR.UNTESTED, verdict=TR.UNRESOLVED)
    assert "different findings" in str(err.value)


def test_the_summary_reports_counts_and_refuses_to_divide_them():
    _, resolutions, _ = TR.run_episode(CORPUS, _episode(), series_id="CA10Y",
                                       area="CA", state_kind="MARKET_RATE")
    got = TR.summarise(resolutions)
    assert got["mechanism_tested"] == 0
    assert "outcome_right" in got and "outcome_tested" in got
    assert not any("rate" in k or "accuracy" in k for k in got), (
        "a hit rate computed while the mechanism leg is untested on every "
        "row reads as accuracy and is not")


# --- leak attacks: each must be refused ---------------------------------------

def test_a_figure_published_before_t0_but_seen_after_it_is_withheld():
    """The exact shape of the live corpus, and the exact reason it is blocked."""
    late = _observation("2024-03-01", 9.9, published="2024-03-15",
                        retrieved="2026-08-01")
    wall = V.VintageWall(CORPUS + [late], as_of="2025-01-01", label="attack")
    assert late not in wall.rows(record="macro_observation")
    with pytest.raises(V.VintageViolation) as err:
        wall.check(late)
    assert "that is the leak" in str(err.value)


def test_the_leak_surface_counts_what_a_publication_filter_would_admit():
    late = [_observation(f"2024-0{i}-01", 5.0, published=f"2024-0{i}-15",
                         retrieved="2026-08-01") for i in range(1, 5)]
    frozen = V.freeze(CORPUS + late, as_of="2025-01-01")
    assert frozen.leak_surface == 4, (
        "the number of rows an occurrence-time filter would have used must be "
        "counted, not assumed small")


def test_a_replay_cannot_advance_its_own_wall():
    wall = V.VintageWall(CORPUS, as_of="2025-01-01", label="attack")
    with pytest.raises(V.VintageViolation) as err:
        wall.at("2025-06-01")
    assert "one step at a time" in str(err.value)


def test_scoring_a_figure_that_was_already_public_is_refused():
    """A forecast of something already printed measures the ability to read."""
    from intent_engine.market import macro_expectation as ME

    history = [MS.from_dict(r) for r in CORPUS]
    target = sorted({o.reference_period for o in history})[5]
    published = [o for o in history if o.reference_period == target][0]
    expectation = ME.forecast(history, series_id="CA10Y",
                              target_period=target,
                              made_at=published.published_at, method=ME.AR1)
    if expectation is not None:
        with pytest.raises(ME.Foresight):
            ME.reconcile(expectation, history, as_of=LAST)


def test_an_undated_row_cannot_be_placed_against_a_wall():
    undated = {"record": "macro_observation", "series_id": "X", "value": 1.0}
    wall = V.VintageWall(CORPUS, as_of="2025-01-01", label="attack")
    with pytest.raises(V.VintageViolation) as err:
        wall.check(undated)
    assert "make the vintage a guess" in str(err.value)


# --- the live corpus, and why it is blocked -----------------------------------

def test_a_corpus_retrieved_all_at_once_admits_nothing_historically():
    """The measured blocker, pinned so a later ingest is noticed.

    Every live macro row carries `retrieved_at` in one month. At any earlier
    instant the admitted vintage is empty, so no historical T0 exists at which
    the engine knew anything. This test states that shape; when real
    observation history accumulates, the live replay becomes runnable and
    nothing here has to change.
    """
    all_at_once = [_observation(f"2024-{m:02d}-01", 3.0 + m * 0.1,
                                published=f"2024-{m:02d}-15",
                                retrieved="2026-08-05")
                   for m in range(1, 13)]
    frozen = V.freeze(all_at_once, as_of="2025-06-01")
    assert frozen.admitted == ()
    assert frozen.leak_surface == 12
    assert TR.select_episodes(all_at_once, starting="2024-06-01",
                              ending="2026-01-01", horizon_days=90,
                              every_days=90, minimum_rows=1) == []
