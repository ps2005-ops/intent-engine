"""Appended grade invalidations mask the grade and its belief update in the store VIEW."""
import json
from intent_engine.market import learning_store as LS, demand_reading as DR


def _ledger(tmp_path, rows):
    p = tmp_path / "ledger.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return p


REC = {"record": "reconciliation", "expectation_id": "x1", "evaluated_at": "2026-08-07",
       "outcome": "CONTRADICTED", "evidence_ids": ["ev2"], "subject": "acme"}
BU = {"record": "belief_update", "at": "2026-08-07", "belief_id": "b1",
      "basis": "preregistered expectation CONTRADICTED", "evidence_ids": ["x1"],
      "prior": 0.586, "posterior": 0.506}
INV = {"record": "grade_invalidation", "expectation_id": "x1",
       "invalidates": {"outcome": "CONTRADICTED", "evaluated_at": "2026-08-07"}}


def test_an_invalidated_grade_disappears_from_every_reconciliation_reader(tmp_path):
    p = _ledger(tmp_path, [REC, BU, INV])
    st = LS.LearningStore(p)
    assert st.reconciliations() == ()
    assert not [r for r in st._rows() if r.get("record") == "reconciliation"]
    assert not [r for r in st._rows() if r.get("record") == "belief_update"]
    assert json.loads(p.read_text().splitlines()[0])["record"] == "reconciliation"   # file untouched


def test_without_an_invalidation_nothing_is_masked(tmp_path):
    st = LS.LearningStore(_ledger(tmp_path, [REC, BU]))
    assert len(st.reconciliations()) == 1


def test_an_invalidation_of_another_date_does_not_mask_a_later_valid_grade(tmp_path):
    later = dict(REC, evaluated_at="2026-11-30", outcome="CONFIRMED")
    st = LS.LearningStore(_ledger(tmp_path, [REC, INV, later]))
    assert [r["outcome"] for r in st.reconciliations()] == ["CONFIRMED"]


def test_two_accounts_of_one_report_are_the_same_event():
    assert DR.same_reporting_event("Q3 2026 revenue up 6%", "2026-10-21",
                                   "Q3 2026: Claro posts revenue up", "2026-12-20")
    assert DR.same_reporting_event("revenue up", "2026-11-03", "revenue beat", "2026-11-04")
    assert not DR.same_reporting_event("Q2 2026 revenue up", "2026-08-05",
                                       "Q3 2026 revenue up", "2026-10-29")


def test_a_guidance_revision_after_a_result_is_a_different_figure():
    assert not DR.same_reporting_event("revenue rose 12%", "2026-08-01",
                                       "raised full-year guidance", "2026-08-20",
                                       "EARNINGS_RESULT", "GUIDANCE_REVISION")
    # guidance published with the result (same release) is the same event
    assert DR.same_reporting_event("revenue rose 12%", "2026-08-01",
                                   "raised full-year guidance", "2026-08-02",
                                   "EARNINGS_RESULT", "GUIDANCE_REVISION")
    assert DR.same_reporting_event("revenue rose 12%", "2026-08-01",
                                   "beats on revenue", "2026-08-03",
                                   "EARNINGS_RESULT", "EARNINGS_SURPRISE")
