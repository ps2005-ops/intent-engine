"""The three-line simulator, the vintage wall, and the badges that hold it up.

Every test here is a defect that was found by looking at a rendered page in a
browser, written down so it cannot come back. Where a test pins a sentence it
says why; everywhere else it pins the INVARIANT, because the wording of this
surface is still being improved and a test that pins prose becomes a guard
against the next improvement.
"""
from __future__ import annotations

import datetime as _dt

import pytest

from intent_engine.company_ingestion import xbrl
from intent_engine.executive import history_simulator as HS
from intent_engine.executive import resolution as R
from intent_engine.founder_brief import absence, history_chart as HC, steps
from intent_engine.product_eval import defect_taxonomy as DT


def _fact(year, value, filed_year=None, month=12, day=31):
    return xbrl.Fact(end=_dt.date(year, month, day), value=float(value),
                     knowable_from=_dt.date(filed_year or year + 1, 2, 15),
                     form="10-K", fiscal_year=year, period="FY")


def _series(pairs, family="revenue"):
    return xbrl.Series(family=family, tag="Revenues",
                       points=tuple(_fact(y, v) for y, v in pairs),
                       label=family, note="fixture")


REVENUE = [(2017, 100.0), (2018, 140.0), (2019, 200.0), (2020, 260.0),
           (2021, 330.0), (2022, 400.0), (2023, 450.0)]
OPERATING = [(2017, -20.0), (2018, -22.0), (2019, -20.0), (2020, -10.0),
             (2021, 5.0), (2022, 30.0), (2023, 60.0)]


class _Profile:
    business_model_class = "SUBSCRIPTION_SOFTWARE"
    primary_management_levers = ("Pricing and packaging", "Sales capacity")


def _simulation(revenue=None, operating=None, profile=None):
    return HS.build(company="Fixture, Inc.",
                    profile=profile if profile is not None else _Profile(),
                    revenue=revenue if revenue is not None else _series(REVENUE),
                    operating=(operating if operating is not None
                               else _series(OPERATING, "operating_income")))


# ===========================================================================
# the wall
# ===========================================================================
def test_a_fact_is_knowable_on_the_day_it_was_filed_not_the_day_it_ended():
    """The distinction the whole surface rests on.

    Fiscal 2022 revenue is a fact ABOUT 2022 and was not information anybody
    held until it was filed in February 2023. A wall keyed on the period end
    would let a January-2023 vintage read the full year — hindsight arriving
    through a date field.
    """
    series = _series(REVENUE)
    on_new_year = _dt.date(2023, 1, 5)
    known = series.knowable_by(on_new_year)
    assert [f.year for f in known] == [2017, 2018, 2019, 2020, 2021]
    assert 2022 not in [f.year for f in known]
    assert [f.year for f in series.knowable_by(_dt.date(2023, 3, 1))][-1] == 2022


def test_the_expectation_at_a_vintage_cannot_see_a_later_filing():
    """ADVERSARIAL. Adding years AFTER the cutoff must change nothing.

    Not a check that the numbers look plausible — a check that the function
    is a pure function of the prefix. If a later fact could reach it by any
    path, appending later facts would move the answer.
    """
    early = _simulation(revenue=_series(REVENUE[:4]),
                        operating=_series(OPERATING[:4], "operating_income"))
    late = _simulation()
    cutoff = _dt.date(2021, 2, 15)          # knows 2017-2020 in both
    a = HS.expectation_path(early.index, cutoff, 3,
                            model_class="SUBSCRIPTION_SOFTWARE")
    b = HS.expectation_path(late.index, cutoff, 3,
                            model_class="SUBSCRIPTION_SOFTWARE")
    assert a is not None and b is not None
    assert [round(p.value, 6) for p in a.points] == \
        [round(p.value, 6) for p in b.points]


def test_the_counterfactual_is_built_from_the_expectation_and_nothing_later():
    sim = _simulation()
    vintage = sim.vintages[0]
    assert vintage.counterfactual is not None
    assert vintage.expectation is not None
    # Same anchor year, and never a point the expectation does not have.
    assert vintage.counterfactual.points[0].year == \
        vintage.expectation.points[0].year
    assert {p.year for p in vintage.counterfactual.points} == \
        {p.year for p in vintage.expectation.points}


# ===========================================================================
# the three states
# ===========================================================================
def test_each_series_declares_what_kind_of_claim_it_is():
    sim = _simulation()
    vintage = sim.vintages[0]
    assert vintage.actual.basis == R.OBSERVED
    assert vintage.expectation.basis == R.MODELED
    assert vintage.counterfactual.basis == R.COUNTERFACTUAL
    # And the badge a reader sees is derived from that, not chosen again.
    assert vintage.expectation.label == "Modelled"
    assert vintage.counterfactual.label == "Counterfactual"


def test_a_modelled_expectation_never_claims_a_consensus():
    """§24. The one sentence this feature must never produce."""
    sim = _simulation()
    for vintage in sim.vintages:
        text = vintage.expectation.statement.lower()
        assert "consensus" not in text or "not a retrieved consensus" in text
        assert "wall street" not in text
        assert "analysts expect" not in text


def test_a_counterfactual_never_claims_what_would_have_happened():
    sim = _simulation()
    joined = " ".join(v.counterfactual.statement for v in sim.vintages)
    assert "would have grown" not in joined.lower()
    assert "bounded counterfactual" in joined.lower()
    findings = DT.scan(joined, surface="history")
    assert not [f for f in findings
                if f.code == "COUNTERFACTUAL_PRESENTED_AS_FACT"], findings


# ===========================================================================
# the rendered page
# ===========================================================================
def test_the_history_page_carries_three_labelled_series():
    """§76, §89. The gate that a text-only history rewind would fail."""
    sim = _simulation()
    html = steps.render_history(sim, None, run_id="r", company="Fixture, Inc.")
    assert "ln-actual" in html and "ln-expect" in html and "ln-counter" in html
    assert "Actual path" in html
    assert "Market expectation" in html
    assert "Better strategy" in html
    assert not DT.scan_history_chart(html)


def test_the_chart_is_readable_without_colour():
    """§86. Three ways to tell the lines apart, not one."""
    sim = _simulation()
    html = steps.render_history(sim, None, run_id="r", company="Fixture, Inc.")
    assert "stroke-dasharray" in html          # dash pattern
    assert "polygon" in html and "circle" in html and "rect" in html  # markers
    assert 'role="img"' in html and "aria-label" in html
    assert "The same figures as a table" in html


def test_the_date_control_is_a_real_keyboard_control():
    sim = _simulation()
    html = steps.render_history(sim, None, run_id="r", company="Fixture, Inc.")
    assert html.count('type="radio"') == len(sim.vintages)
    assert 'role="group"' in html
    assert "<script" not in html      # the slider is CSS, and stays CSS


def test_moving_the_date_changes_the_argument_not_only_the_numbers():
    """§96. A slider that changes numbers alone is a chart with a scrollbar."""
    sim = _simulation()
    levers = {next(c.body for c in v.cards if c.key == "alternative")
              for v in sim.vintages}
    assert len(levers) > 1, "every vintage offered the same alternative"


# ===========================================================================
# the ladder, where there is no chart
# ===========================================================================
def test_a_company_with_no_filed_series_gets_an_argument_not_an_apology():
    """§16 rung D. The Stripe case.

    A private company has no filed series and never will. The page must not
    say "no history exists" and must not draw one anyway; it says what the
    decision is, what would measure it, and why it matters.
    """
    sim = _simulation(revenue=xbrl.Series(family="revenue",
                                          note="no series was retrieved"),
                      operating=None)
    assert not sim.available
    assert sim.fallback is not None
    assert sim.fallback.basis == R.UNRESOLVED
    assert sim.fallback.next_measurement
    assert sim.bounded_cards, "a bounded page still argues the alternative"
    html = steps.render_history(sim, None, run_id="r", company="Fixture, Inc.")
    assert "What would draw this chart" in html
    assert not absence.adjudicate(html), "the fallback page dead-ends"


def test_the_wrong_companys_history_can_never_be_drawn():
    """The Stripe SEV1: a chart of somebody else's revenue.

    The simulator draws whatever series it is handed, so the guard belongs at
    the identity boundary — an empty CIK must produce no chart rather than a
    chart from a default.
    """
    sim = HS.build(company="Private Co", cik="", profile=_Profile(),
                   revenue=xbrl.Series(family="revenue", note="not a filer"))
    assert not sim.available
    assert not sim.index.points


# ===========================================================================
# the modelled present expectation
# ===========================================================================
def test_the_present_expectation_is_labelled_and_bounded():
    sim = _simulation()
    resolved = HS.present_expectation(sim, company="Fixture, Inc.",
                                      today=_dt.date(2024, 6, 1))
    assert resolved is not None
    assert resolved.basis == R.MODELED
    assert resolved.derivation
    assert "not a retrieved analyst consensus" in resolved.statement
    assert resolved.decision_relevance


def test_there_is_no_present_expectation_without_a_series():
    sim = _simulation(revenue=xbrl.Series(family="revenue", note="none"))
    assert HS.present_expectation(sim, company="X") is None


# ===========================================================================
# the resolution ladder's own contract
# ===========================================================================
def test_a_resolution_below_observed_must_name_what_it_came_from():
    with pytest.raises(R.LadderViolation):
        R.modeled("q", "a statement", derivation="")


def test_an_unresolved_question_must_carry_a_next_measurement():
    with pytest.raises(R.LadderViolation):
        R.check(R.Resolved(question="q", basis=R.UNRESOLVED,
                           statement="not known", derivation="why"))


def test_a_resolution_can_never_be_an_empty_statement():
    with pytest.raises(R.LadderViolation):
        R.observed("q", "")
