"""B-HIST-002. HISTORICAL may not touch the number that says how tested we are.

WHAT THIS FILE IS DEFENDING
---------------------------
The prospective decision gate is the one measurement that says how much of this
engine has actually been exercised against a world that had not answered yet.
It stands at 34 of 100 and it rises a few a night. A historical corpus is worth
building precisely because it does NOT rise that way — and the day one of its
rows reaches that counter, the counter stops meaning anything and nothing in
the output says so.

So the guard runs the REAL measurement function, `docs/execution/v4/metrics.py`
`measure()`, against a temporary ledger. Not a reimplementation: a
reimplementation would pass while the file the frontier actually reads counted
whatever it liked, which is the failure this repository already has on record
under "a caller is not a call".

THE DEFECT THIS NODE FOUND
--------------------------
`prospective_outcomes` was `len(outcomes)` over every `research_outcome` row in
the ledger, with no population filter and no provenance filter. So did
`prospective_empty_handed` and `prospective_failed`, which read the same list.
Appending 1,000 historical outcome rows would have moved all three by 1,000.
`test_the_gate_could_move_if_the_filter_were_absent` is the negative control
that shows the guard can see that state rather than being vacuously true.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib

import pytest

from intent_engine.market import historical_corpus as HC
from intent_engine.market import research_decision as RD

REPO = pathlib.Path(__file__).resolve().parents[1]
METRICS_PY = REPO / "docs" / "execution" / "v4" / "metrics.py"


def _load_metrics():
    """Import the REAL metrics.py from this worktree, by path.

    By path because it is a script, not a package module, and from THIS
    worktree because pinning the live runtime's copy would test whatever
    another session happened to have deployed.
    """
    spec = importlib.util.spec_from_file_location("v4_metrics", METRICS_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


METRICS = _load_metrics()

PROSPECTIVE_GATES = ("prospective_decisions", "prospective_outcomes",
                     "prospective_with_forgone_option",
                     "prospective_empty_handed", "prospective_failed",
                     "logged_exploration_events")


# --- FIXTURE ledger rows ------------------------------------------------------

def _decision(ident, *, population=None, provenance=RD.PROSPECTIVE,
              forgone=("filing",)):
    row = {"record": "research_decision", "decision_id": f"FIXTURE-rd-{ident}",
           "provenance": provenance, "forgone": list(forgone),
           "subject": "FIXTURE-SUBJECT", "chosen_action": "customer_case_study",
           "selection_probability_status": "DETERMINISTIC"}
    if population is not None:
        row["population"] = population
    return row


def _outcome(ident, *, status="SUCCESS"):
    return {"record": "research_outcome", "decision_id": f"FIXTURE-rd-{ident}",
            "status": status}


def _write(path, rows):
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def _baseline_ledger(tmp_path, count=34):
    """A ledger shaped like the live one: prospective rows, paired outcomes."""
    path = tmp_path / "learning_ledger.jsonl"
    rows = []
    for i in range(count):
        rows.append(_decision(i, population=RD.PROSPECTIVE))
        rows.append(_outcome(i))
    _write(path, rows)
    return path


def _gates(path):
    got = METRICS.measure(ledger=path)
    assert got["readable"] is True
    return {k: v for k, v in got["metrics"].items()
            if k.startswith("prospective_") or k == "logged_exploration_events"}


# --- THE GUARD ----------------------------------------------------------------

def test_injecting_1000_historical_rows_cannot_move_a_prospective_gate(
        tmp_path):
    """THE ADVERSARIAL PROOF, through the real measurement function.

    1,000 historical decisions, each with a paired outcome, each carrying the
    forgone option and the KNOWN propensity that would otherwise clear three
    separate gates, and each wearing `provenance=PROSPECTIVE` — the disguise
    that would work if population were resolved by anything other than the
    population field first.
    """
    path = _baseline_ledger(tmp_path)
    before = _gates(path)
    assert before["prospective_decisions"] == 34

    injected = []
    for i in range(1000):
        row = _decision(f"hist-{i}", population=HC.HISTORICAL,
                        provenance=RD.PROSPECTIVE)
        row["selection_probability_status"] = "KNOWN"
        injected.append(row)
        injected.append(_outcome(f"hist-{i}", status="NO_RESULT"))
    _write(path, injected)

    after = _gates(path)
    assert after == before
    for gate in PROSPECTIVE_GATES:
        assert after[gate] == before[gate], gate
    # Stated as the node states it: not by one.
    assert after["prospective_decisions"] - before["prospective_decisions"] == 0
    # And the historical rows are visible somewhere, so this is separation
    # rather than a silent drop.
    assert METRICS.measure(ledger=path)["metrics"]["historical_decisions"] \
        == 1000


def test_the_gate_could_move_if_the_filter_were_absent(tmp_path):
    """NEGATIVE CONTROL. The guard above must be capable of failing.

    The same 1,000 rows, tagged PROSPECTIVE instead of HISTORICAL, move every
    gate they were built to move. Without this the guard would pass on a
    measurement function that had simply stopped counting.
    """
    path = _baseline_ledger(tmp_path)
    before = _gates(path)
    rows = []
    for i in range(1000):
        row = _decision(f"pros-{i}", population=RD.PROSPECTIVE)
        row["selection_probability_status"] = "KNOWN"
        rows.append(row)
        rows.append(_outcome(f"pros-{i}", status="NO_RESULT"))
    _write(path, rows)
    after = _gates(path)
    assert after["prospective_decisions"] == before["prospective_decisions"] \
        + 1000
    assert after["prospective_outcomes"] == before["prospective_outcomes"] \
        + 1000
    assert after["prospective_empty_handed"] == 1000
    assert after["logged_exploration_events"] == 1000


def test_one_historical_row_cannot_move_the_gate_by_one(tmp_path):
    path = _baseline_ledger(tmp_path)
    before = _gates(path)
    _write(path, [_decision("solo", population=HC.HISTORICAL,
                            provenance=RD.PROSPECTIVE),
                  _outcome("solo")])
    assert _gates(path) == before


def test_historical_outcomes_alone_cannot_move_the_outcome_gates(tmp_path):
    """The defect this node found, pinned directly.

    `prospective_outcomes`, `prospective_empty_handed` and `prospective_failed`
    all read one list of outcome rows. Before this node that list was every
    outcome row in the ledger.
    """
    path = _baseline_ledger(tmp_path)
    before = _gates(path)
    rows = []
    for i in range(1000):
        rows.append(_decision(f"h-{i}", population=HC.HISTORICAL,
                              provenance=RD.RECONSTRUCTED))
        rows.append(_outcome(f"h-{i}", status="FAILED"))
        rows.append(_outcome(f"h-{i}", status="NO_RESULT"))
    _write(path, rows)
    after = _gates(path)
    assert after["prospective_outcomes"] == before["prospective_outcomes"]
    assert after["prospective_failed"] == 0
    assert after["prospective_empty_handed"] == 0


def test_an_untagged_row_is_refused_by_the_gate_and_counted(tmp_path):
    """A row declaring neither population and no legacy declaration either."""
    path = _baseline_ledger(tmp_path)
    before = _gates(path)
    _write(path, [_decision("mystery", population=None,
                            provenance=RD.RECONSTRUCTED)])
    assert _gates(path) == before
    assert METRICS.measure(ledger=path)["metrics"][
        "population_untagged_rows"] == 1


def test_an_orphan_outcome_belongs_to_no_population(tmp_path):
    path = _baseline_ledger(tmp_path)
    before = _gates(path)
    _write(path, [_outcome("nobody-made-this")])
    assert _gates(path)["prospective_outcomes"] == before["prospective_outcomes"]
    assert METRICS.measure(ledger=path)["metrics"]["orphan_outcomes"] == 1


def test_an_unreadable_ledger_reports_unknown_rather_than_zero(tmp_path):
    """MISSING is not ZERO, at the gate as well as in the corpus."""
    got = METRICS.measure(ledger=tmp_path / "there-is-no-ledger.jsonl")
    assert got["readable"] is False
    assert got["metrics"] == {}


# --- the legacy declaration, which is a translation and not a default ---------

def test_a_legacy_prospective_row_still_counts(tmp_path):
    """The live ledger's 34 rows predate the population field.

    They carry `provenance=PROSPECTIVE`, written by the live engine before the
    call in the only field the schema then had. Refusing them would convert a
    measurement that exists into an UNKNOWN, which is the mirror image of the
    error this node is about.
    """
    path = tmp_path / "learning_ledger.jsonl"
    _write(path, [_decision(i, population=None) for i in range(34)]
           + [_outcome(i) for i in range(34)])
    gates = _gates(path)
    assert gates["prospective_decisions"] == 34
    assert gates["prospective_outcomes"] == 34
    assert METRICS.measure(ledger=path)["metrics"][
        "population_untagged_rows"] == 0


def test_a_reconstructed_row_resolves_to_no_population(tmp_path):
    """RECONSTRUCTED is deliberately absent from the legacy table."""
    assert HC.population_of(_decision(1, population=None,
                                      provenance=RD.RECONSTRUCTED)) == ""


def test_the_population_field_beats_a_legacy_declaration():
    """The attack, at the resolver: HISTORICAL wearing provenance=PROSPECTIVE."""
    row = _decision("x", population=HC.HISTORICAL,
                    provenance=RD.PROSPECTIVE)
    assert HC.population_of(row) == HC.HISTORICAL
    assert METRICS._population_of(row) == HC.HISTORICAL


def test_the_legacy_table_does_not_generalise_to_other_record_kinds():
    row = {"record": "research_outcome", "provenance": RD.PROSPECTIVE}
    assert HC.population_of(row) == ""
    assert METRICS._population_of(row) == ""


# --- the vocabulary is declared twice and must not drift ----------------------

ADVERSARIAL_ROWS = [
    {},
    {"record": "research_decision"},
    {"record": "research_decision", "provenance": "PROSPECTIVE"},
    {"record": "research_decision", "provenance": "RECONSTRUCTED"},
    {"record": "research_decision", "provenance": "PROSPECTIVE",
     "population": "HISTORICAL"},
    {"record": "research_decision", "population": "HISTORICAL"},
    {"record": "research_decision", "population": "PROSPECTIVE"},
    {"record": "research_decision", "population": "prospective"},
    {"record": "research_decision", "population": ""},
    {"record": "research_decision", "population": None,
     "provenance": "PROSPECTIVE"},
    {"record": "research_decision", "population": "SYNTHETIC"},
    {"record": "research_outcome", "provenance": "PROSPECTIVE"},
    {"record": "historical_episode", "population": "HISTORICAL"},
    {"record": "macro_observation", "provenance": "PROSPECTIVE"},
]


@pytest.mark.parametrize("row", ADVERSARIAL_ROWS)
def test_both_declarations_of_the_resolver_agree(row):
    """metrics.py restates the vocabulary because it must stay stdlib-only.

    Two copies drift. This is the thing that stops them: the same rows through
    both, including the ones designed to be resolved wrongly.
    """
    assert HC.population_of(row) == METRICS._population_of(row), row


def test_both_declarations_of_the_vocabulary_agree():
    assert set(METRICS.POPULATIONS) == set(HC.POPULATIONS)
    assert METRICS.HISTORICAL == HC.HISTORICAL
    assert METRICS.PROSPECTIVE == HC.PROSPECTIVE
    assert (METRICS.LEGACY_POPULATION_DECLARATIONS
            == HC.LEGACY_POPULATION_DECLARATIONS)
    assert set(RD.POPULATIONS) == set(HC.POPULATIONS)


# --- a mixed query must name both populations ---------------------------------

def test_a_query_that_names_no_population_is_refused():
    rows = [_decision(1, population=HC.HISTORICAL,
                      provenance=RD.RECONSTRUCTED),
            _decision(2, population=RD.PROSPECTIVE)]
    with pytest.raises(HC.PopulationUnstated) as caught:
        HC.select(rows)
    assert caught.value.reason == HC.MIXED_QUERY_UNSPECIFIED


def test_a_mixed_query_must_name_both_populations():
    rows = [_decision(1, population=HC.HISTORICAL,
                      provenance=RD.RECONSTRUCTED),
            _decision(2, population=RD.PROSPECTIVE)]
    kept, census = HC.select(rows, populations=[HC.HISTORICAL,
                                                HC.PROSPECTIVE])
    assert len(kept) == 2
    assert census == {HC.HISTORICAL: 1, HC.PROSPECTIVE: 1,
                      HC.UNTAGGED_ROW_REFUSED: 0}
    single, _ = HC.select(rows, populations=[HC.PROSPECTIVE])
    assert len(single) == 1


@pytest.mark.parametrize("populations", [[], ["EVERYTHING"],
                                         [HC.PROSPECTIVE, "EVERYTHING"]])
def test_an_empty_or_unknown_population_list_is_refused(populations):
    with pytest.raises(HC.PopulationUnstated) as caught:
        HC.select([], populations=populations)
    assert caught.value.reason == HC.MIXED_QUERY_UNSPECIFIED


def test_the_census_counts_untagged_rows_rather_than_assigning_them():
    rows = [_decision(1, population=HC.HISTORICAL,
                      provenance=RD.RECONSTRUCTED),
            {"record": "evidence", "evidence_id": "FIXTURE-e"}]
    counts = HC.census(rows)
    assert counts[HC.UNTAGGED_ROW_REFUSED] == 1
    assert counts[HC.HISTORICAL] == 1
    assert sum(counts.values()) == len(rows)


def test_require_population_refuses_rather_than_defaulting():
    with pytest.raises(HC.PopulationUnstated) as caught:
        HC.require_population({"record": "evidence", "evidence_id": "FIXTURE"})
    assert caught.value.reason == HC.UNTAGGED_ROW_REFUSED
    assert HC.require_population(
        {"record": "research_decision",
         "population": HC.HISTORICAL}) == HC.HISTORICAL


# --- population on the decision producer --------------------------------------

def _candidates():
    return (RD.CandidateAction(source_family="regulatory_filing"),
            RD.CandidateAction(source_family="customer_case_study"))


def test_a_decision_writes_its_population_into_every_row():
    decision = RD.ResearchDecision(
        subject="FIXTURE", question_type="exposure",
        chosen_action="regulatory_filing", candidates=_candidates(),
        selection_policy="voi")
    assert decision.population == RD.PROSPECTIVE
    row = decision.as_dict()
    assert row["population"] == RD.PROSPECTIVE
    assert HC.population_of(row) == RD.PROSPECTIVE
    assert METRICS._population_of(row) == RD.PROSPECTIVE


def test_an_unknown_population_on_a_decision_is_refused():
    with pytest.raises(RD.DecisionRejected) as caught:
        RD.ResearchDecision(
            subject="FIXTURE", question_type="exposure",
            chosen_action="regulatory_filing", candidates=_candidates(),
            selection_policy="voi", population="SYNTHETIC")
    assert "unknown population" in str(caught.value)


def test_a_historical_decision_may_not_claim_prospective_provenance():
    """The relabelled-import shape, refused at construction."""
    with pytest.raises(RD.DecisionRejected) as caught:
        RD.ResearchDecision(
            subject="FIXTURE", question_type="exposure",
            chosen_action="regulatory_filing", candidates=_candidates(),
            selection_policy="voi", population=RD.HISTORICAL,
            provenance=RD.PROSPECTIVE)
    assert "relabelled import" in str(caught.value)


def test_a_historical_decision_with_reconstructed_provenance_is_allowed():
    """NEGATIVE CONTROL for the coherence lock: it must not refuse everything."""
    decision = RD.ResearchDecision(
        subject="FIXTURE", question_type="exposure",
        chosen_action="regulatory_filing", candidates=_candidates(),
        selection_policy="voi", population=RD.HISTORICAL,
        provenance=RD.RECONSTRUCTED)
    assert decision.as_dict()["population"] == RD.HISTORICAL
    assert HC.population_of(decision.as_dict()) == RD.HISTORICAL


def test_a_historical_decision_row_is_refused_by_both_walls(tmp_path):
    """Even correctly formed, it reaches no prospective gate."""
    path = _baseline_ledger(tmp_path)
    before = _gates(path)
    decision = RD.ResearchDecision(
        subject="FIXTURE", question_type="exposure",
        chosen_action="regulatory_filing", candidates=_candidates(),
        selection_policy="voi", population=RD.HISTORICAL,
        provenance=RD.RECONSTRUCTED)
    _write(path, [decision.as_dict()])
    assert _gates(path) == before


# --- the corpus does not write to the ledger ----------------------------------

def test_the_historical_corpus_lives_in_its_own_file():
    """Separation at rest, not only in the filter.

    The corpus is a different file from the learning ledger, so a gate reading
    the ledger cannot reach it even if every filter in this file were deleted.
    """
    from intent_engine.market import learning_store as LS

    assert HC.DEFAULT_PATH != LS.DEFAULT_PATH
    assert HC.DEFAULT_PATH == "reports/market/historical_corpus.jsonl"
    assert "historical_episode" not in LS.RECORD_KINDS
