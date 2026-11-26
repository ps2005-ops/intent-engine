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


# --- admissibility rules found in the 2026-11-26 qualification cycle --------
import pytest


@pytest.mark.parametrize("text", [
    "Caterpillar (CAT) Reports Next Week: Wall Street Expects Earnings Growth",
    "JPMorgan Chase & Co. Has Lowered Expectations for Costco Wholesale (NASDAQ:COST)",
    "Regions Financial (NYSE:RF) Stock Price Expected to Rise, JPMorgan Chase & Co. Analyst Says",
    "Grab Holdings Limited (GRAB) vs. Sea Limited (SE): Grab Raises Its Outlook",
])
def test_previews_comparisons_and_analyst_actions_never_grade(text):
    subject = "jpmorgan" if "JPMorgan" in text else ("sea_limited" if "Sea" in text else "caterpillar")
    assert DR.grading_admissible(subject, text, DR.STRENGTHENING)[0] is False


def test_a_customer_case_study_never_grades_the_vendor():
    t = ("FOOTDISTRICT grew revenue by 14%, returning customers by 28%, and "
         "average order value by 5% after moving from Magento 2 to Shopify.")
    assert DR.grading_admissible("shopify", t, DR.STRENGTHENING)[0] is False


def test_an_account_that_does_not_name_the_subject_never_grades():
    assert DR.grading_admissible("bhp", "Copper prices rose 8% this quarter", DR.STRENGTHENING)[0] is False


def test_supply_and_surprise_accounts_do_not_test_a_demand_belief():
    assert DR.grading_admissible("bhp", "BHP Group's Copper Output Falls in Q1 on Grade Declines",
                                 DR.STRENGTHENING)[0] is False
    assert DR.grading_admissible("mercadolibre", "MercadoLibre Earnings Missed Analyst Estimates",
                                 DR.STRENGTHENING)[0] is False


def test_a_recap_of_the_same_figure_is_the_same_report():
    assert DR.shares_a_reported_figure("Cloudflare Q2: Revenue Rises 36%",
                                       "Cloudflare stock reports 36 percent revenue growth")


def test_a_bare_quarter_matches_the_same_quarter_with_a_year():
    assert DR.same_reporting_event("posts Q2 2026 results", "2026-07-22",
                                   "3.1 percent Q2 revenue growth", "2026-09-24")


def test_an_unnamed_recap_inside_a_reporting_cycle_is_the_same_report():
    assert DR.same_reporting_event("Sea revenue growth story", "2026-07-21",
                                   "Sea Limited stock holds after revenue growth", "2026-09-22",
                                   "EARNINGS_RESULT", "EARNINGS_RESULT")


def test_an_explicitly_later_quarter_is_a_new_observation():
    assert not DR.same_reporting_event("Toyota Q2 vehicle sales up", "2026-08-05",
                                       "Toyota Motor US Reports Higher Q3 Vehicle Sales", "2026-10-01",
                                       "EARNINGS_RESULT", "EARNINGS_RESULT")
    ok, _ = DR.grading_admissible("shopify", "Shopify Reports Third-Quarter 2026 Revenue Up 32%",
                                  DR.STRENGTHENING)
    assert ok
