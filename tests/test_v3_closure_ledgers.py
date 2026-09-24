"""§17/§34/§61: the ledgers must agree with the records they describe.

WHY A TEST AND NOT A REPORT
---------------------------
A dashboard that maintains counters beside the ledger it describes is how a
report and its source come to disagree without either being wrong on its own
terms. `close_v3.reconcile` re-derives every displayed count from the
canonical record; this pins that it is actually doing so, and that it can
fail.
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

from intent_engine.econ import forward_engine as FE
from intent_engine.econ import founder_ab as FA


def _closure():
    import close_v3
    return close_v3


# --- §34 reconciliation -----------------------------------------------------
def test_the_learning_ledger_reconciles_with_the_forward_ledger():
    c = _closure()
    learning = c.learning_ledger()
    assert c.reconcile(learning)["reconciles"], \
        c.reconcile(learning)["problems"]


def test_a_report_that_disagrees_with_the_ledger_is_refused():
    """The check has to be able to fail, or it is decoration."""
    c = _closure()
    learning = c.learning_ledger()
    learning["expectations"]["real_open"] += 7
    out = c.reconcile(learning)
    assert not out["reconciles"]
    assert any("real_open" in p for p in out["problems"])


def test_calibration_may_not_be_pre_calibration_with_resolutions_on_file():
    c = _closure()
    learning = c.learning_ledger()
    learning["expectations"]["real_resolved"] = 3
    out = c.reconcile(learning)
    assert not out["reconciles"]
    assert any("PRE_CALIBRATION" in p for p in out["problems"])


def test_a_declared_damage_kind_with_no_detector_fails_reconciliation():
    """A zero from an instrument that was not looking is not evidence."""
    c = _closure()
    learning = c.learning_ledger()
    real = FA.damage_coverage
    try:
        FA.damage_coverage = lambda: {"declared": list(FA.DAMAGE_KINDS),
                                      "with_detector": [],
                                      "without_detector": ["WRONG_EXPOSURE"]}
        out = c.reconcile(learning)
        assert not out["reconciles"]
        assert any("no detector" in p for p in out["problems"])
    finally:
        FA.damage_coverage = real


# --- §13 the relation ledger carries what it must ---------------------------
REQUIRED = ("source", "target", "sign", "lag_days", "regime", "evidence",
            "counterevidence", "uncertainty", "falsifier", "lineage",
            "status", "last_evaluated", "next_eligible_evaluation")


@pytest.mark.parametrize("field", REQUIRED)
def test_every_relation_carries_the_field(field):
    rows = _closure().relation_ledger()["rows"]
    assert rows, "the relation ledger is empty; this guard would be vacuous"
    missing = [r["relation"] for r in rows if field not in r]
    assert not missing, f"{field} missing from {missing}"


def test_a_relation_whose_driver_did_not_move_is_not_reported_as_failing():
    """§13: a lag that has not elapsed and a driver that did not move are not
    failures of the relation, and the ledger has to say which it is."""
    rows = _closure().relation_ledger()["rows"]
    untested = [r for r in rows if r["status"] == "CANDIDATE"]
    for r in untested:
        assert r["why_not_supported"], r["relation"]
        assert "not a failure" in r["why_not_supported"] or \
            "against the declared sign" in r["why_not_supported"] or \
            "could not be read" in r["why_not_supported"] or \
            "not evaluated" in r["why_not_supported"] or \
            "regime" in r["why_not_supported"], r["why_not_supported"]


def test_every_relation_states_when_it_can_next_be_judged():
    rows = _closure().relation_ledger()["rows"]
    for r in rows:
        if r["status"] in ("CANDIDATE", "PENDING_LAG"):
            assert "next_eligible_evaluation" in r


# --- §11 the dimension ledger separates live from useful --------------------
def test_a_dimension_can_be_live_and_useless_and_the_ledger_says_which():
    from intent_engine.econ import panel as PN
    c = _closure()
    ledger = c.dimension_ledger(
        PN.Panel.read("reports/panel/historical_panel.jsonl"))
    assert ledger["dimensions"] >= 10
    values = set(ledger["by_value"])
    assert "BLOCKED" in values, "no dimension is blocked; the denominator " \
                                "has been quietly narrowed"
    assert values & {"LIVE_DECISION_RELEVANT", "LIVE_CONTEXT_ONLY",
                     "LIVE_UNPROVEN_VALUE"}, \
        "every live dimension is being counted the same way"


# --- §17 the FIRST_RELEASE wall ---------------------------------------------
def test_a_first_release_contract_cannot_be_resolved_from_a_later_revision():
    """Release-blocking. A prediction made against the first print, scored
    against a restatement published afterwards, is scored on information the
    prediction could not have had."""
    import inspect
    src = inspect.getsource(FE)
    assert "FIRST_RELEASE" in src and "LATEST_REVISION" in src
    readable = inspect.getsource(FE._readable)
    assert "vintage_policy == FIRST_RELEASE" in readable, (
        "the resolver does not branch on the vintage policy, so a "
        "FIRST_RELEASE contract would be scored against whatever the panel "
        "holds now")
    assert FE.VINTAGE_POLICIES == (FE.FIRST_RELEASE, FE.LATEST_REVISION)


def test_every_real_expectation_declares_a_resolution_rule():
    from intent_engine.econ import forward_ledger as FL
    for record in FL.by_id().values():
        assert str(record.get("resolution_rule", "")).strip(), \
            record.get("expectation_id")
        assert record.get("information_cutoff") <= record.get("created_at", "")


def test_a_cutoff_after_the_creation_date_is_refused(tmp_path):
    """Hindsight enters exactly here: a prediction that claims to have used
    evidence dated after it was written down."""
    from intent_engine.econ import forward_ledger as FL
    from intent_engine.econ.vocabulary import EconError
    p = tmp_path / "fwd.jsonl"
    FL.append([{"expectation_id": "ex-leak", "created_at": "2026-01-01",
                "information_cutoff": "2026-08-27", "horizon_days": 180,
                "expires_at": "2027-02-23", "resolution_rule": "r",
                "confidence": 0.5, "quantity": "q",
                "expected_direction": "UP", "outcome": "OPEN"}], path=p)
    with pytest.raises(EconError) as exc:
        FL.assert_lifecycle(p)
    assert "AFTER the date they were made" in str(exc.value)
