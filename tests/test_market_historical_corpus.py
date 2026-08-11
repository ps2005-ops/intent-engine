"""B-HIST-001. The T0 wall, and the attacks that must go through it.

EVERY EPISODE IN THIS FILE IS FIXTURE DATA AND SAYS SO
------------------------------------------------------
No real historical episode exists yet. The live macro corpus cannot supply one:
all 2,347 observations carry `retrieved_at` inside a single month while their
`published_at` spans three years, so at every historical instant the admitted
vintage is empty and there is no T0 at which the engine knew anything. That is
a fact about the corpus, and the corpus is reported as empty rather than seeded
with invented episodes.

So the fixtures here carry ids beginning `FIXTURE-` and observation times spread
the way a running engine's would be. They prove the machinery. They are not
evidence about any company, and nothing in this file writes to a real corpus
path.

THE ATTACK THAT MOTIVATES MOST OF THIS FILE
-------------------------------------------
Substituting `published_at` for `retrieved_at` would make the live corpus look
replayable overnight: 1,572 rows would be admitted at 2026-01-01 that the
engine had never seen, and every number computed from them would look healthy.
`test_published_at_may_never_admit_a_record` and its structural twin fail if
anyone makes that substitution, whether by editing the field lists or by
reading the wrong field in the builder.
"""
from __future__ import annotations

import json

import pytest

from intent_engine.market import historical_corpus as HC

T0 = "2025-06-01T00:00:00"
T1 = "2025-09-01T00:00:00"
BEFORE = "2025-05-30T00:00:00"
AFTER = "2025-06-01T00:00:01"


# --- fixtures, labelled -------------------------------------------------------

def _record(ident, *, known="", published="", occurred="",
            record="evidence", field="retrieved_at"):
    """One FIXTURE record. `field` chooses which knowledge field carries it."""
    row = {"record": record, "record_id": f"FIXTURE-{ident}"}
    if known:
        row[field] = known
    if published:
        row["published_at"] = published
    if occurred:
        row["occurred_at"] = occurred
    return row


def _episode(**overrides):
    """A FIXTURE episode that is valid unless an override breaks it."""
    payload = dict(
        subject="FIXTURE-SUBJECT",
        t0=T0, t1=T1,
        decision="acquire the filing before the quarter closes",
        declared_expectation="the disclosed backlog falls quarter on quarter",
        expected_observable="FIXTURE backlog line in the next 10-Q",
        actual_observable="backlog fell 11%",
        provenance=("FIXTURE-a",),
        rows=[_record("a", known=BEFORE)],
    )
    payload.update(overrides)
    return HC.build_episode(**payload)


# --- the shared reader, so the three shapes cannot drift ----------------------

def _read(shape, name):
    """One reader for a producer object, a persisted row and a consumer object.

    Written once and used by every shape test on purpose. Three readers that
    each `getattr` or each `.get` are three chances for one shape to grow a
    field the others silently lack — which is how a dict ledger folded into a
    single event the last time this codebase read a row two ways.
    """
    value = shape.get(name) if isinstance(shape, dict) else getattr(shape, name)
    if isinstance(value, (list, tuple)):
        return tuple(value)
    return value


EPISODE_FIELDS = (
    "subject", "t0", "t1", "decision", "declared_expectation",
    "expected_observable", "actual_observable", "provenance", "population",
    "outcome_revised_at", "t0_snapshot_id", "t0_rows_admitted",
    "t0_rows_refused", "note")


# --- what an episode must carry -----------------------------------------------

def test_an_episode_carries_every_field_the_node_requires():
    episode = _episode()
    assert episode.subject == "FIXTURE-SUBJECT"
    assert episode.t0 == T0 and episode.t1 == T1
    assert episode.decision
    assert episode.declared_expectation
    assert episode.expected_observable
    assert episode.actual_observable == "backlog fell 11%"
    assert episode.provenance == ("FIXTURE-a",)
    assert episode.population == HC.HISTORICAL
    assert episode.episode_id.startswith("he_")


def test_the_population_is_historical_and_cannot_be_relabelled():
    with pytest.raises(HC.EpisodeRefused) as caught:
        HC.HistoricalEpisode(
            subject="FIXTURE-SUBJECT", t0=T0, t1=T1, decision="d",
            declared_expectation="e", expected_observable="o",
            actual_observable="a", provenance=("FIXTURE-a",),
            population=HC.PROSPECTIVE)
    assert caught.value.reason == HC.INSUFFICIENT_PROVENANCE


# --- the wall -----------------------------------------------------------------

def test_the_snapshot_admits_only_what_was_knowable_at_t0():
    snapshot = HC.build_t0_snapshot(
        [_record("early", known=BEFORE),
         _record("late", known=AFTER)], t0=T0)
    assert [r["record_id"] for r in snapshot.admitted] == ["FIXTURE-early"]
    assert snapshot.standing == HC.POPULATED


def test_the_t0_comparison_is_inclusive_at_the_instant_itself():
    """THE MUTATION TARGET. Both sides of the comparison, one second apart.

    A record stamped exactly at T0 was knowable at T0 and a record stamped one
    second later was not. Flipping `<=` to `<` drops the first; flipping the
    refusal to `>=` admits the second. Pinning a comfortable case in the middle
    would survive either mutation.
    """
    snapshot = HC.build_t0_snapshot(
        [_record("at-the-instant", known=T0),
         _record("one-second-later", known=AFTER)], t0=T0)
    assert [r["record_id"] for r in snapshot.admitted] == [
        "FIXTURE-at-the-instant"]
    assert [r.row_ref for r in snapshot.refusals] == [
        "FIXTURE-one-second-later"]


def test_a_refused_record_is_counted_with_a_named_reason_never_dropped():
    rows = [
        _record("known-late", known=AFTER),
        _record("undated", published=BEFORE),
        _record("corrupt", known=BEFORE, published=AFTER),
        _record("fine", known=BEFORE),
    ]
    snapshot = HC.build_t0_snapshot(rows, t0=T0)
    assert len(snapshot.admitted) == 1
    assert len(snapshot.refusals) == 3
    assert len(snapshot.admitted) + len(snapshot.refusals) == len(rows)
    assert snapshot.refusals_by_reason == {
        HC.WALL_VIOLATION: 2,
        HC.INSUFFICIENT_PROVENANCE: 1,
        HC.NO_OBSERVABLE: 0,
        HC.REVISED_OUTCOME: 0,
    }
    assert set(snapshot.refusals_by_reason) == set(HC.REFUSAL_REASONS)
    for refusal in snapshot.refusals:
        assert refusal.reason in HC.REFUSAL_REASONS
        assert refusal.detail


def test_refusal_counts_can_report_the_clean_case_too():
    """NEGATIVE CONTROL for the refusal counter.

    A counter that always returned something non-zero would make every wall
    look like it fired. This is the run where it must report zero.
    """
    snapshot = HC.build_t0_snapshot([_record("a", known=BEFORE)], t0=T0)
    assert snapshot.refusals == ()
    assert snapshot.refusals_by_reason == {r: 0 for r in HC.REFUSAL_REASONS}
    assert snapshot.leak_surface == 0


def test_an_empty_snapshot_says_which_empty_it_is():
    """MISSING is not ZERO, at the one place the difference is invisible."""
    assert HC.build_t0_snapshot([], t0=T0).standing == HC.NO_INPUT
    starved = HC.build_t0_snapshot([_record("late", known=AFTER)], t0=T0)
    assert starved.standing == HC.NOTHING_KNOWN_AT_T0
    assert starved.admitted == ()
    assert len(starved.refusals) == 1


def test_a_snapshot_without_an_instant_is_refused():
    with pytest.raises(HC.EpisodeRefused) as caught:
        HC.build_t0_snapshot([_record("a", known=BEFORE)], t0="")
    assert caught.value.reason == HC.WALL_VIOLATION


# --- published_at may refuse, never admit -------------------------------------

def test_published_at_is_not_a_knowledge_field():
    """THE STRUCTURAL HALF of the substitution guard.

    Fails the moment anyone moves `published_at` into the list the builder
    admits on — the single edit that would make the live macro corpus appear
    replayable.
    """
    assert "published_at" not in HC.KNOWLEDGE_FIELDS
    assert "published_at" in HC.CONSTRAINT_FIELDS
    assert not set(HC.KNOWLEDGE_FIELDS) & set(HC.CONSTRAINT_FIELDS)
    assert HC.knowledge_time({"published_at": BEFORE}) == ""


def test_published_at_may_never_admit_a_record():
    """THE BEHAVIOURAL HALF, in the exact shape of the live macro corpus.

    Every one of these rows was published long before T0 and observed long
    after it — 2,347 of them exist on the live ledger. A builder that read
    publication time would admit all of them. This test fails if it does.
    """
    rows = [_record(f"macro-{i}", known="2026-08-01T00:00:00",
                    published=f"2025-0{i}-15T00:00:00") for i in range(1, 6)]
    snapshot = HC.build_t0_snapshot(rows, t0=T0)
    assert snapshot.admitted == ()
    assert snapshot.refusals_by_reason[HC.WALL_VIOLATION] == 5
    # And the size of the avoided error is measured, not asserted.
    assert snapshot.leak_surface == 5


def test_a_record_with_only_a_publication_stamp_is_insufficient_not_early():
    snapshot = HC.build_t0_snapshot([_record("undated", published=BEFORE)],
                                    t0=T0)
    assert snapshot.admitted == ()
    refusal = snapshot.refusals[0]
    assert refusal.reason == HC.INSUFFICIENT_PROVENANCE
    assert "substituting publication time" in refusal.detail


def test_a_record_published_after_t0_is_corrupt_rather_than_early():
    """Claimed observed before T0, published after it. Both cannot be true."""
    snapshot = HC.build_t0_snapshot(
        [_record("impossible", known=BEFORE, published=AFTER)], t0=T0)
    assert snapshot.admitted == ()
    assert snapshot.refusals[0].reason == HC.WALL_VIOLATION
    assert snapshot.refusals[0].field == "published_at"


def test_every_knowledge_field_admits_and_none_of_them_is_published_at():
    for field in HC.KNOWLEDGE_FIELDS:
        snapshot = HC.build_t0_snapshot(
            [_record(field, known=BEFORE, field=field)], t0=T0)
        assert len(snapshot.admitted) == 1, field


# --- the adversarial proof ----------------------------------------------------

def test_an_episode_seeded_with_a_post_t0_fact_is_refused():
    with pytest.raises(HC.EpisodeRefused) as caught:
        _episode(rows=[_record("a", known=BEFORE),
                       _record("leak", known=AFTER)],
                 provenance=("FIXTURE-a", "FIXTURE-leak"))
    assert caught.value.reason == HC.WALL_VIOLATION
    assert "FIXTURE-leak" in caught.value.detail


def test_an_episode_may_be_built_beside_a_refused_fact_it_does_not_cite():
    """NEGATIVE CONTROL for the citation guard: it must not refuse everything."""
    episode = _episode(rows=[_record("a", known=BEFORE),
                             _record("leak", known=AFTER)],
                       provenance=("FIXTURE-a",))
    assert episode.t0_rows_admitted == 1
    assert episode.t0_rows_refused == 1
    assert dict(episode.t0_refusals_by_reason)[HC.WALL_VIOLATION] == 1


def test_a_snapshot_borrowed_from_another_instant_is_refused():
    later = HC.build_t0_snapshot([_record("a", known=BEFORE)], t0=T1)
    with pytest.raises(HC.EpisodeRefused) as caught:
        _episode(snapshot=later, rows=())
    assert caught.value.reason == HC.WALL_VIOLATION


def test_an_episode_that_resolves_before_it_forms_is_a_wall_violation():
    with pytest.raises(HC.EpisodeRefused) as caught:
        _episode(t1=BEFORE)
    assert caught.value.reason == HC.WALL_VIOLATION


# --- the four refusal reasons, each reachable ---------------------------------

def test_no_observable_when_nothing_was_observed_at_t1():
    with pytest.raises(HC.EpisodeRefused) as caught:
        _episode(actual_observable=None)
    assert caught.value.reason == HC.NO_OBSERVABLE
    assert "unresolved" in caught.value.detail


def test_no_observable_distinguishes_absent_from_empty():
    """ABSENT is not NO_CHANGE. Same reason, different detail, on purpose."""
    with pytest.raises(HC.EpisodeRefused) as absent:
        _episode(actual_observable=None)
    with pytest.raises(HC.EpisodeRefused) as empty:
        _episode(actual_observable="   ")
    assert absent.value.reason == empty.value.reason == HC.NO_OBSERVABLE
    assert absent.value.detail != empty.value.detail


def test_no_observable_when_nothing_was_named_to_observe():
    with pytest.raises(HC.EpisodeRefused) as caught:
        _episode(expected_observable="")
    assert caught.value.reason == HC.NO_OBSERVABLE


@pytest.mark.parametrize("override", [
    {"provenance": ()},
    {"subject": " "},
    {"decision": ""},
    {"declared_expectation": ""},
])
def test_insufficient_provenance_for_an_untraceable_episode(override):
    with pytest.raises(HC.EpisodeRefused) as caught:
        _episode(**override)
    assert caught.value.reason == HC.INSUFFICIENT_PROVENANCE


def test_every_refusal_reason_is_reachable_from_the_public_api():
    """A closed vocabulary with an unreachable member is a docstring."""
    reached = set()
    for override in ({"t1": BEFORE}, {"actual_observable": None},
                     {"provenance": ()}):
        with pytest.raises(HC.EpisodeRefused) as caught:
            _episode(**override)
        reached.add(caught.value.reason)
    revised = _episode(outcome_revised_at="2025-10-01T00:00:00")
    _, excluded = HC.for_estimator_validation([revised])
    reached.add(excluded[0].reason)
    assert reached == set(HC.REFUSAL_REASONS)


# --- revised outcomes ---------------------------------------------------------

def test_a_revised_outcome_is_flagged_and_kept():
    episode = _episode(outcome_revised_at="2025-10-01T00:00:00",
                       revision_detail="the figure was restated")
    assert episode.revised is True
    assert episode.as_dict()["revised"] is True


def test_a_revised_outcome_is_excluded_from_estimator_validation():
    clean = _episode()
    revised = _episode(subject="FIXTURE-OTHER",
                       outcome_revised_at="2025-10-01T00:00:00")
    kept, excluded = HC.for_estimator_validation([clean, revised])
    assert [e.episode_id for e in kept] == [clean.episode_id]
    assert len(excluded) == 1
    assert excluded[0].reason == HC.REVISED_OUTCOME
    assert excluded[0].row_ref == revised.episode_id


def test_estimator_validation_can_report_the_all_eligible_case():
    """NEGATIVE CONTROL: the gate must be able to exclude nothing."""
    kept, excluded = HC.for_estimator_validation([_episode()])
    assert len(kept) == 1 and excluded == ()


def test_a_revision_at_or_before_t0_is_not_a_revision_of_the_outcome():
    assert _episode(outcome_revised_at=BEFORE).revised is False
    assert _episode(outcome_revised_at=T0).revised is False


# --- the three shapes ---------------------------------------------------------

def test_the_three_shapes_agree_on_every_field(tmp_path):
    """Producer object, persisted row, transported consumer object.

    Read through ONE reader. An episode that reloads into a different shape
    from the one it was written from is a corpus whose consumers each see a
    slightly different past.
    """
    store = HC.HistoricalCorpusStore(tmp_path / "historical_corpus.jsonl")
    produced = _episode(note="FIXTURE note")
    assert store.record_episode(produced) is True

    persisted = store.rows()[0]
    transported = HC.from_dict(persisted)

    for name in EPISODE_FIELDS:
        values = [_read(shape, name)
                  for shape in (produced, persisted, transported)]
        assert values[0] == values[1] == values[2], name
    assert produced.as_dict() == transported.as_dict()
    assert _read(persisted, "record") == "historical_episode"
    assert _read(persisted, "population") == HC.HISTORICAL


def test_the_persisted_row_is_the_path_the_node_names(tmp_path):
    store = HC.HistoricalCorpusStore(tmp_path / "reports" / "market"
                                     / "historical_corpus.jsonl")
    store.record_episode(_episode())
    assert HC.DEFAULT_PATH == "reports/market/historical_corpus.jsonl"
    assert store.path.exists()
    line = store.path.read_text(encoding="utf-8").strip()
    assert json.loads(line)["contract"] == HC.CONTRACT


def test_a_missing_optional_field_reloads_as_its_declared_empty(tmp_path):
    row = _episode().as_dict()
    del row["note"]
    del row["selection_rule"]
    episode = HC.from_dict(row)
    assert episode.note == "" and episode.selection_rule == ""


def test_an_empty_list_is_refused_with_the_same_reason_as_a_missing_one():
    """`[]` and absent are both INSUFFICIENT_PROVENANCE, and neither crashes."""
    row = _episode().as_dict()
    row["provenance"] = []
    with pytest.raises(HC.EpisodeRefused) as empty:
        HC.from_dict(row)
    missing = _episode().as_dict()
    del missing["provenance"]
    with pytest.raises(HC.EpisodeRefused) as absent:
        HC.from_dict(missing)
    assert empty.value.reason == absent.value.reason == (
        HC.INSUFFICIENT_PROVENANCE)


def test_an_explicit_null_survives_as_absent_rather_than_empty():
    row = _episode().as_dict()
    row["actual_observable"] = None
    with pytest.raises(HC.EpisodeRefused) as caught:
        HC.from_dict(row)
    assert caught.value.reason == HC.NO_OBSERVABLE
    assert "unresolved" in caught.value.detail


def test_a_stale_producer_version_is_refused_not_reinterpreted():
    row = _episode().as_dict()
    row["contract"] = "historical_corpus.v0"
    with pytest.raises(HC.StaleContract) as caught:
        HC.from_dict(row)
    assert "historical_corpus.v0" in caught.value.detail
    unversioned = _episode().as_dict()
    del unversioned["contract"]
    with pytest.raises(HC.StaleContract):
        HC.from_dict(unversioned)


def test_an_untagged_corpus_row_is_refused_rather_than_defaulted():
    row = _episode().as_dict()
    del row["population"]
    with pytest.raises(HC.PopulationUnstated) as caught:
        HC.from_dict(row)
    assert caught.value.reason == HC.UNTAGGED_ROW_REFUSED


def test_the_corpus_reader_does_not_consult_the_legacy_ledger_bridge():
    """A corpus row may not inherit a population from `provenance`.

    `population_of` resolves ledger rows written before the field existed.
    That bridge must not reach a file this module writes, because a corpus row
    with no population and a prospective-looking field is exactly the row the
    separation exists to stop.
    """
    row = _episode().as_dict()
    del row["population"]
    row["record"] = "research_decision"
    row["provenance"] = ["PROSPECTIVE"]
    with pytest.raises(HC.PopulationUnstated):
        HC.from_dict(row)


# --- the store ----------------------------------------------------------------

def test_the_store_is_idempotent_on_episode_id(tmp_path):
    store = HC.HistoricalCorpusStore(tmp_path / "c.jsonl")
    episode = _episode()
    assert store.record_episode(episode) is True
    assert store.record_episode(episode) is False
    assert len(store.episodes()) == 1


def test_the_store_counts_what_it_refused_on_reload(tmp_path):
    path = tmp_path / "c.jsonl"
    store = HC.HistoricalCorpusStore(path)
    store.record_episode(_episode())
    untagged = _episode(subject="FIXTURE-B").as_dict()
    del untagged["population"]
    stale = _episode(subject="FIXTURE-C").as_dict()
    stale["contract"] = "historical_corpus.v0"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(untagged, sort_keys=True) + "\n")
        handle.write(json.dumps(stale, sort_keys=True) + "\n")
        handle.write("{not json\n")
    health = store.health()
    assert health["episodes"] == 1
    assert health["untagged_rows_refused"] == 1
    assert health["stale_contract_rows_refused"] == 1
    assert health["corrupt_lines_skipped"] == 1
    assert health["standing"] == HC.POPULATED


def test_the_store_reports_an_absent_file_apart_from_an_empty_one(tmp_path):
    store = HC.HistoricalCorpusStore(tmp_path / "missing.jsonl")
    assert store.health()["standing"] == HC.NO_INPUT
    assert store.health()["exists"] is False
    (tmp_path / "empty.jsonl").write_text("", encoding="utf-8")
    empty = HC.HistoricalCorpusStore(tmp_path / "empty.jsonl")
    assert empty.health()["standing"] == HC.NOTHING_KNOWN_AT_T0
    assert empty.health()["exists"] is True


class _SmuggledEpisode:
    """An episode-shaped object that did not come through the constructor.

    `HistoricalEpisode.__post_init__` already refuses a PROSPECTIVE population,
    so the only way to reach the write-side guard is with an object built
    elsewhere. Both locks matter: the constructor stops the honest mistake, and
    the store stops whatever a future producer hands it.
    """

    population = HC.PROSPECTIVE
    episode_id = "he_smuggled"


def test_the_store_refuses_to_write_a_non_historical_episode(tmp_path):
    store = HC.HistoricalCorpusStore(tmp_path / "c.jsonl")
    with pytest.raises(HC.PopulationUnstated) as caught:
        store.record_episode(_SmuggledEpisode())
    assert caught.value.reason == HC.UNTAGGED_ROW_REFUSED
    assert not store.path.exists()


# --- the corpus, and the honest zero ------------------------------------------

def test_build_corpus_keeps_its_refusals(tmp_path):
    good = {"subject": "FIXTURE-A", "t0": T0, "t1": T1, "decision": "d",
            "declared_expectation": "e", "expected_observable": "o",
            "actual_observable": "a", "provenance": ["FIXTURE-a"],
            "rows": [_record("a", known=BEFORE)]}
    bad = dict(good, subject="FIXTURE-B", actual_observable=None)
    corpus = HC.build_corpus([good, bad], built_at=T1)
    assert len(corpus.episodes) == 1
    assert len(corpus.refusals) == 1
    assert corpus.refusals[0].reason == HC.NO_OBSERVABLE
    assert corpus.refusals[0].row_ref == "FIXTURE-B"
    assert corpus.as_dict()["refusals_by_reason"][HC.NO_OBSERVABLE] == 1


def test_an_empty_corpus_is_reported_as_empty_not_seeded():
    corpus = HC.build_corpus([])
    assert corpus.standing == HC.NO_INPUT
    assert corpus.episodes == ()
    summary = corpus.as_dict()
    assert summary["episodes"] == 0
    assert summary["counts_toward_prospective_gate"] == 0
    assert summary["population"] == HC.HISTORICAL
