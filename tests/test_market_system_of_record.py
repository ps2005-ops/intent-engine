"""One system of record, and it cannot be confused with the legacy pipeline.

These tests exist because of a specific incident: an exploration answering
"what has the market intelligence system learned this week?" read
`data/prediction_ledger.db` — last written twenty-three days earlier — and
reported that the learning system had learned nothing and its modules were
dormant. The canonical ledger held 4,921 rows at that moment and the canonical
cycle had completed that morning.

Nothing was broken. The wrong store was read. Every test below is aimed at
making that specific mistake impossible rather than merely documented.
"""
import json

import pytest

from intent_engine.market import learning_status as LS
from intent_engine.market import system_of_record as SOR


# --- the declaration ---------------------------------------------------------
def test_there_is_exactly_one_canonical_system():
    assert SOR.canonical_id() == "market_intelligence_learning_engine"
    assert SOR.classify(SOR.canonical_id()) == SOR.CANONICAL


def test_the_legacy_prediction_pipeline_is_declared_legacy():
    assert SOR.classify("daily_market_predictions") == SOR.LEGACY


def test_a_legacy_pipeline_cannot_identify_itself_as_canonical():
    """The load-bearing guard. A legacy path must never speak for the system."""
    assert not SOR.is_canonical("daily_market_predictions")
    with pytest.raises(SOR.SystemOfRecordError):
        SOR.assert_canonical("daily_market_predictions")


def test_an_undeclared_pipeline_is_refused_rather_than_assumed_canonical():
    """A script nobody classified is the exact shape that caused the incident.

    The default must be refusal. Silently accepting an unknown id would let
    the next `daily_market_predictions.py` inherit the authority the first one
    wrongly enjoyed.
    """
    assert SOR.classify("some_new_prediction_script") == SOR.UNDECLARED
    with pytest.raises(SOR.SystemOfRecordError):
        SOR.assert_canonical("some_new_prediction_script")


def test_every_legacy_pipeline_must_print_a_banner():
    for entry in SOR.legacy_pipelines():
        assert entry.get("banner_required") is True
        banner = SOR.legacy_banner(entry["id"])
        assert banner and "NOT THE MARKET INTELLIGENCE SYSTEM OF RECORD" in banner
        # A warning that does not name the replacement gets ignored.
        assert "python -m intent_engine.market" in banner


def test_the_canonical_system_gets_no_banner():
    assert SOR.legacy_banner(SOR.canonical_id()) is None


# --- the stores --------------------------------------------------------------
def test_the_canonical_ledger_is_not_the_legacy_database():
    """The single most important assertion in this file."""
    paths = SOR.stores("/tmp/whatever")
    ledger = str(paths["learning_ledger"])
    assert ledger.endswith("reports/market/learning_ledger.jsonl")
    assert "prediction_ledger.db" not in ledger


def test_learning_status_reads_the_root_it_is_given():
    """A wrong data root must be visible, not silently substituted."""
    status = LS.collect(root="/nonexistent-root", window="7d")
    assert status["system_of_record"]["ledger_exists"] is False
    assert "/nonexistent-root" in status["system_of_record"]["ledger"]


def test_a_stale_legacy_database_cannot_affect_canonical_health(tmp_path):
    """The incident, as a test.

    A legacy store that is arbitrarily old must not change a single number in
    the canonical reading, because the canonical reading never opens it.
    """
    root = tmp_path / "runtime"
    (root / "reports" / "market").mkdir(parents=True)
    (root / "status").mkdir(parents=True)
    ledger = root / "reports" / "market" / "learning_ledger.jsonl"
    ledger.write_text(json.dumps({
        "record": "knowledge_effect", "effect_type": "CREATED",
        "created_at": "2026-08-12"}) + "\n", encoding="utf-8")

    before = LS.collect(root=str(root), window="all")
    (root / "data").mkdir(parents=True, exist_ok=True)
    (root / "data" / "prediction_ledger.db").write_bytes(b"ancient garbage")
    after = LS.collect(root=str(root), window="all")

    assert before["channels"] == after["channels"]
    assert after["knowledge"]["effects_in_window"] == 1


# --- missing is not zero -----------------------------------------------------
def test_a_channel_with_no_rows_ever_reports_no_producer_not_zero(tmp_path):
    root = tmp_path / "runtime"
    (root / "reports" / "market").mkdir(parents=True)
    (root / "reports" / "market" / "learning_ledger.jsonl").write_text(
        "", encoding="utf-8")
    status = LS.collect(root=str(root), window="all")
    channel = status["channels"]["causal"]
    assert channel["status"] == LS.NO_PRODUCER
    assert channel["all_time"] == 0
    assert "no producer" in channel["reason"]


def test_rows_that_cannot_be_dated_are_not_reported_as_no_change(tmp_path):
    """UNDATABLE_BY_READER, never RAN_NO_CHANGE.

    `expectation` and `reconciliation` rows carry no timestamp this reader
    resolves. Calling that "no change" would understate the system in exactly
    the way the incident did.
    """
    root = tmp_path / "runtime"
    (root / "reports" / "market").mkdir(parents=True)
    (root / "reports" / "market" / "learning_ledger.jsonl").write_text(
        "\n".join(json.dumps({"record": r, "id": i})
                  for i, r in enumerate(("expectation", "reconciliation"))),
        encoding="utf-8")
    status = LS.collect(root=str(root), window="7d")
    channel = status["channels"]["expectations"]
    # LEGACY_UNDATABLE, not UNDATABLE_BY_READER: `expectation` and
    # `reconciliation` ARE kinds this reader knows how to date (via
    # `preregistered_at` / `evaluated_at`), so rows lacking the stamp are
    # history rather than a live blind spot. Either way it is NOT a measured
    # zero, which is the property this test exists for.
    assert channel["status"] == LS.LEGACY_UNDATABLE
    assert channel["all_time"] == 2
    assert "NOT a measured zero" in channel["reason"]


def test_a_kind_this_reader_cannot_date_at_all_is_undatable_by_reader(
        tmp_path):
    """The other arm: an unknown kind is a READER gap, not legacy history."""
    root = tmp_path / "runtime"
    (root / "reports" / "market").mkdir(parents=True)
    (root / "reports" / "market" / "learning_ledger.jsonl").write_text(
        json.dumps({"record": "expectation", "expectation_id": "x"}),
        encoding="utf-8")
    channel = LS.collect(root=str(root), window="7d")["channels"][
        "expectations"]
    assert channel["status"] == LS.LEGACY_UNDATABLE


def test_dated_expectations_are_placed_in_the_window(tmp_path):
    """The repair itself: a stamped expectation must land in its window."""
    root = tmp_path / "runtime"
    (root / "reports" / "market").mkdir(parents=True)
    (root / "reports" / "market" / "learning_ledger.jsonl").write_text(
        "\n".join(json.dumps(r) for r in [
            {"record": "expectation", "preregistered_at": "2026-08-12",
             "expectation_id": "x"},
            {"record": "reconciliation", "evaluated_at": "2026-08-12",
             "expectation_id": "x"}]), encoding="utf-8")
    channel = LS.collect(root=str(root), window="all")["channels"][
        "expectations"]
    assert channel["status"] == LS.RUNNING
    assert channel["in_window"] == 2


def test_zero_effects_reports_unmeasurable_share_not_zero(tmp_path):
    root = tmp_path / "runtime"
    (root / "reports" / "market").mkdir(parents=True)
    (root / "reports" / "market" / "learning_ledger.jsonl").write_text(
        "", encoding="utf-8")
    status = LS.collect(root=str(root), window="all")
    assert status["knowledge"]["changing_share"] is None


# --- active learning ---------------------------------------------------------
def test_research_outcomes_are_read_from_the_field_the_producer_writes(
        tmp_path):
    """`status`, not `outcome`.

    The first version of this reader asked for `outcome`/`result`, got
    "?" for every row, and reported `zero_result_captured=False` while
    NO_RESULT and FAILED were both sitting in the ledger — a false negative on
    the guard that keeps the policy dataset from being survivorship-biased.
    """
    root = tmp_path / "runtime"
    (root / "reports" / "market").mkdir(parents=True)
    (root / "reports" / "market" / "learning_ledger.jsonl").write_text(
        "\n".join(json.dumps({"record": "research_outcome", "status": s,
                              "completed_at": "2026-08-12"})
                  for s in ("SUCCESS", "NO_RESULT", "FAILED")),
        encoding="utf-8")
    status = LS.collect(root=str(root), window="all")
    outcomes = status["active_learning"]["outcomes_all_time"]
    assert outcomes == {"SUCCESS": 1, "NO_RESULT": 1, "FAILED": 1}
    assert status["active_learning"]["zero_result_captured"] is True


def test_a_success_only_policy_dataset_is_reported_as_biased(tmp_path):
    root = tmp_path / "runtime"
    (root / "reports" / "market").mkdir(parents=True)
    (root / "reports" / "market" / "learning_ledger.jsonl").write_text(
        json.dumps({"record": "research_outcome", "status": "SUCCESS",
                    "completed_at": "2026-08-12"}), encoding="utf-8")
    status = LS.collect(root=str(root), window="all")
    assert status["active_learning"]["zero_result_captured"] is False


# --- learning without trading ------------------------------------------------
def test_learning_is_measured_with_zero_trades(tmp_path):
    """Market learning must not require a position.

    A ledger with knowledge effects and no trading rows at all still reports
    RUNNING; a system that reported "no learning" because nothing traded would
    make PAPER mode look like death.
    """
    root = tmp_path / "runtime"
    (root / "reports" / "market").mkdir(parents=True)
    (root / "reports" / "market" / "learning_ledger.jsonl").write_text(
        "\n".join(json.dumps({"record": "knowledge_effect",
                              "effect_type": t, "created_at": "2026-08-12"})
                  for t in ("CREATED", "SUPPORTED", "NO_CHANGE")),
        encoding="utf-8")
    status = LS.collect(root=str(root), window="all")
    assert status["channels"]["knowledge"]["status"] == LS.RUNNING
    assert status["knowledge"]["changed_something"] == 2
    assert status["knowledge"]["changed_nothing"] == 1


# --- the scheduler -----------------------------------------------------------
def test_the_declared_scheduler_targets_the_canonical_entrypoint():
    scheduler = SOR.canonical()["scheduler"]
    assert scheduler["trading_mode"] == "PAPER"
    assert scheduler["jobs"]
    entry = SOR.canonical()["entrypoint"]
    assert entry == "python -m intent_engine.market"
    # No legacy script may appear as a scheduled canonical job.
    for legacy in SOR.legacy_pipelines():
        assert legacy.get("scheduled") is False
        for path in legacy.get("entrypoints", []):
            assert path not in str(scheduler["jobs"])


# --- population mismatch in the acquisition counters -------------------------
def test_legacy_rows_are_excluded_from_a_yield_rather_than_rewritten(
        tmp_path):
    """Rows written before the counter repair carried SUBJECTS in
    `documents_attempted`. They are append-only history: excluded from any
    yield, never edited to make the metric look better."""
    root = tmp_path / "runtime"
    (root / "reports" / "market").mkdir(parents=True)
    (root / "reports" / "market" / "learning_ledger.jsonl").write_text(
        json.dumps({"record": "research_outcome", "status": "SUCCESS",
                    "completed_at": "2026-08-12",
                    "documents_attempted": 28, "documents_retrieved": 64}),
        encoding="utf-8")
    integrity = LS.collect(root=str(root), window="all")[
        "active_learning"]["acquisition_counter_integrity"]
    assert integrity["state"] == LS.LEGACY_INCOMPATIBLE_POPULATION
    assert integrity["legacy_rows"] == 1
    assert integrity["safe_to_compute_yield"] is False


def test_a_repaired_row_carries_both_populations_and_permits_a_yield(tmp_path):
    root = tmp_path / "runtime"
    (root / "reports" / "market").mkdir(parents=True)
    (root / "reports" / "market" / "learning_ledger.jsonl").write_text(
        json.dumps({"record": "research_outcome", "status": "SUCCESS",
                    "completed_at": "2026-08-12", "subjects_attempted": 7,
                    "documents_attempted": 64, "documents_retrieved": 28}),
        encoding="utf-8")
    integrity = LS.collect(root=str(root), window="all")[
        "active_learning"]["acquisition_counter_integrity"]
    assert integrity["state"] == "CONSISTENT"
    assert integrity["repaired_rows"] == 1
    assert integrity["safe_to_compute_yield"] is True


def test_a_repaired_row_that_still_inverts_is_a_regression_not_legacy(tmp_path):
    """If the producer ever regresses after the repair, that is a NEW defect
    and must not hide behind the legacy label."""
    root = tmp_path / "runtime"
    (root / "reports" / "market").mkdir(parents=True)
    (root / "reports" / "market" / "learning_ledger.jsonl").write_text(
        json.dumps({"record": "research_outcome", "status": "SUCCESS",
                    "completed_at": "2026-08-12", "subjects_attempted": 7,
                    "documents_attempted": 28, "documents_retrieved": 64}),
        encoding="utf-8")
    integrity = LS.collect(root=str(root), window="all")[
        "active_learning"]["acquisition_counter_integrity"]
    assert integrity["state"] == "POPULATION_MISMATCH"
    assert integrity["safe_to_compute_yield"] is False
