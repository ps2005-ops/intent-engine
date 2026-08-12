"""Canonical learning reports: windows, identity, and missing-vs-zero.

The window tests are the load-bearing ones. A report that quietly lets a
post-period row in, or quietly drops an undatable one, produces a number that
looks authoritative and is wrong — and unlike a crash, nobody finds out.
"""
import datetime
import json

import pytest

from intent_engine.market import learning_report as LR
from intent_engine.market import learning_status as LS


def ledger(tmp_path, rows):
    root = tmp_path / "runtime"
    (root / "reports" / "market").mkdir(parents=True)
    (root / "reports" / "market" / "learning_ledger.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return root


def effect(day, kind="CREATED", evidence_id="e1"):
    return {"record": "knowledge_effect", "effect_type": kind,
            "created_at": day, "evidence_id": evidence_id}


AUG12 = datetime.date(2026, 8, 12)


# --- §13 window semantics ----------------------------------------------------
def test_a_row_after_the_period_cannot_enter_the_report(tmp_path):
    root = ledger(tmp_path, [effect("2026-08-12"), effect("2026-08-13")])
    report = LR.build(LR.DAY, root=str(root), as_of=AUG12)
    assert report["rows"]["in_period"] == 1
    assert report["channels"]["evidence"]["knowledge_effects"] == 1


def test_a_row_before_the_period_cannot_enter_the_report(tmp_path):
    root = ledger(tmp_path, [effect("2026-08-11"), effect("2026-08-12")])
    report = LR.build(LR.DAY, root=str(root), as_of=AUG12)
    assert report["rows"]["in_period"] == 1


def test_undatable_rows_are_counted_not_silently_dropped(tmp_path):
    """A row this reader cannot place must stay visible.

    Silently excluding it understates learning; silently including it
    fabricates recency. It is reported in its own field instead.
    """
    root = ledger(tmp_path, [effect("2026-08-12"),
                             {"record": "causal_estimate", "state": "X"}])
    report = LR.build(LR.DAY, root=str(root), as_of=AUG12)
    assert report["rows"]["in_period"] == 1
    assert report["rows"]["undatable_all_time"] == 1
    assert report["rows"]["undatable_by_kind"]["causal_estimate"] == 1


def test_an_incomplete_month_is_marked_partial(tmp_path):
    root = ledger(tmp_path, [effect("2026-08-12")])
    report = LR.build(LR.MONTH, root=str(root), as_of=AUG12)
    assert report["partial_month"] is True
    assert report["partial_period"] is True


def test_an_incomplete_week_is_marked_partial(tmp_path):
    """Wednesday-of-the-week is week-to-date, not a week."""
    root = ledger(tmp_path, [effect("2026-08-12")])
    report = LR.build(LR.WEEK, root=str(root), as_of=AUG12)
    assert report["partial_period"] is True


def test_a_finished_week_is_not_partial(tmp_path):
    root = ledger(tmp_path, [effect("2026-08-12")])
    report = LR.build(LR.WEEK, root=str(root),
                      as_of=datetime.date(2026, 8, 16))
    assert report["partial_period"] is False


def test_a_finished_month_is_not_partial(tmp_path):
    root = ledger(tmp_path, [effect("2026-07-15")])
    report = LR.build(LR.MONTH, root=str(root),
                      as_of=datetime.date(2026, 7, 31))
    assert report["partial_month"] is False


def test_a_complete_day_is_never_partial(tmp_path):
    root = ledger(tmp_path, [effect("2026-08-12")])
    assert LR.build(LR.DAY, root=str(root),
                    as_of=AUG12)["partial_period"] is False


def test_the_week_window_covers_monday_to_sunday(tmp_path):
    root = ledger(tmp_path, [effect("2026-08-12")])
    report = LR.build(LR.WEEK, root=str(root), as_of=AUG12)
    assert report["start"] == "2026-08-10"      # Monday
    assert report["end"] == "2026-08-16"        # Sunday


# --- identity, not summation -------------------------------------------------
def test_the_same_evidence_changing_twice_is_one_changed_row(tmp_path):
    """One evidence row producing several effects must not count as several.

    This program has already shipped a rate whose numerator counted effects
    and whose denominator counted rows — not a fraction, and unreadable as
    one.
    """
    root = ledger(tmp_path, [
        effect("2026-08-12", "CREATED", "same-evidence"),
        effect("2026-08-12", "SUPPORTED", "same-evidence"),
        effect("2026-08-12", "RESOLVED", "same-evidence")])
    report = LR.build(LR.DAY, root=str(root), as_of=AUG12)
    evidence = report["channels"]["evidence"]
    assert evidence["knowledge_effects"] == 3
    assert evidence["evidence_that_changed_something"] == 1


def test_a_re_observation_is_not_new_information(tmp_path):
    root = ledger(tmp_path, [
        {"record": "evidence", "available_at": "2026-08-12", "id": "a"},
        {"record": "evidence_seen", "seen_at": "2026-08-12", "id": "b"},
        {"record": "evidence_seen", "seen_at": "2026-08-12", "id": "c"}])
    evidence = LR.build(LR.DAY, root=str(root),
                        as_of=AUG12)["channels"]["evidence"]
    assert evidence["evidence_rows"] == 1
    assert evidence["re_observations"] == 2
    # Rounded to 4dp by the producer, so compared at that precision.
    assert evidence["new_information_share"] == 0.3333


# --- missing is not zero -----------------------------------------------------
def test_an_empty_period_reports_unmeasurable_not_zero(tmp_path):
    root = ledger(tmp_path, [effect("2026-01-01")])
    evidence = LR.build(LR.DAY, root=str(root),
                        as_of=AUG12)["channels"]["evidence"]
    assert evidence["new_information_share"] == LR.UNMEASURABLE
    assert evidence["changing_effect_share"] == LR.UNMEASURABLE


def test_independent_evidence_is_unavailable_not_zero(tmp_path):
    """The market ledger has no independence column.

    Reporting 0 would assert that no evidence was independent — a far
    stronger claim than "nothing measured it".
    """
    root = ledger(tmp_path, [effect("2026-08-12")])
    evidence = LR.build(LR.DAY, root=str(root),
                        as_of=AUG12)["channels"]["evidence"]
    assert evidence["independent_evidence_rows"] == LR.UNAVAILABLE
    assert evidence["independent_evidence_note"]


# --- the bottleneck must be computed, and must name its cause ----------------
def test_no_arrivals_is_a_source_coverage_bottleneck(tmp_path):
    root = ledger(tmp_path, [effect("2026-01-01")])
    report = LR.build(LR.DAY, root=str(root), as_of=AUG12)
    assert report["bottleneck"]["bottleneck"] == "SOURCE_COVERAGE"
    assert report["bottleneck"]["reason"]


def test_mostly_re_observations_is_an_independence_bottleneck(tmp_path):
    # The evidence must PRODUCE effects, otherwise "evidence arrived and
    # nothing was typed" is the more severe finding and correctly outranks
    # repetitiveness.
    rows = [{"record": "evidence", "available_at": "2026-08-12", "id": "a"}]
    rows += [{"record": "evidence_seen", "seen_at": "2026-08-12", "id": i}
             for i in range(9)]
    rows += [effect("2026-08-12", "CREATED", "a")]
    # A research action too: an absent research policy is itself a starved
    # stage and would rightly outrank a merely repetitive evidence stream.
    rows += [{"record": "research_decision", "chosen_at": "2026-08-12",
              "decision_id": "d1"}]
    report = LR.build(LR.DAY, root=str(ledger(tmp_path, rows)), as_of=AUG12)
    assert report["bottleneck"]["bottleneck"] == "EVIDENCE_INDEPENDENCE"
    # And the runner-up list keeps the other findings visible rather than
    # discarding them.
    assert isinstance(report["bottleneck"]["runners_up"], list)


def test_preregistered_and_never_reconciled_is_a_reconciliation_bottleneck(
        tmp_path):
    # Healthy evidence flow, so the only failing conversion is reconciliation.
    # Without arrivals, SOURCE_COVERAGE is the true bottleneck and rightly
    # wins — a stage with nothing to convert outranks one converting badly.
    rows = [{"record": "expectation", "preregistered_at": "2026-08-12",
             "expectation_id": f"x{i}"} for i in range(3)]
    rows += [{"record": "evidence", "available_at": "2026-08-12", "id": i}
             for i in range(5)]
    rows += [effect("2026-08-12", "CREATED", f"e{i}") for i in range(5)]
    report = LR.build(LR.DAY, root=str(ledger(tmp_path, rows)), as_of=AUG12)
    assert report["bottleneck"]["bottleneck"] == "RECONCILIATION"


def test_every_bottleneck_yields_an_actionable_priority(tmp_path):
    root = ledger(tmp_path, [effect("2026-01-01")])
    priority = LR.build(LR.DAY, root=str(root),
                        as_of=AUG12)["next_research_priority"]
    assert priority["missing_fact"] and priority["suggested_action"]
    # A research action whose success condition is a conclusion cannot
    # disconfirm anything, so the report says so explicitly.
    assert "refused" in priority["forbidden_shape"]


# --- persistence -------------------------------------------------------------
def test_each_period_persists_to_its_own_canonical_path(tmp_path):
    root = ledger(tmp_path, [effect("2026-08-12")])
    for period, expected in ((LR.DAY, "daily/2026-08-12.json"),
                             (LR.WEEK, "weekly/2026-W33.json"),
                             (LR.MONTH, "monthly/2026-08.json")):
        report = LR.build(period, root=str(root), as_of=AUG12)
        path = LR.persist(report, root=str(root))
        assert str(path).endswith(expected)
        assert json.loads(path.read_text())["period"] == period


def test_the_report_names_the_canonical_store_it_read(tmp_path):
    root = ledger(tmp_path, [effect("2026-08-12")])
    report = LR.build(LR.DAY, root=str(root), as_of=AUG12)
    assert report["data_root"].endswith("learning_ledger.jsonl")
    assert "prediction_ledger.db" not in report["data_root"]


def test_an_unknown_period_is_refused():
    with pytest.raises(ValueError):
        LR.build("fortnight")
