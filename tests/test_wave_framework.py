"""The 100-company loop and the persona acceptance — built now, run later.

These test the FRAMEWORK, not the product: whether the loop can tell a
cluster from an anecdote, whether it can tell a repair that held from one
that moved the mean, and whether a simulated persona score can be mistaken
for a customer. Every one of those has to be right before a hundred runs are
spent on it.
"""
from __future__ import annotations

from intent_engine.product_eval import company_matrix as CM
from intent_engine.product_eval import executive_personas as EP


def _row(company, model_class="SUBSCRIPTION_SOFTWARE", sector="TECH",
         overall=9.5, defects=(), sparse=False, public="PUBLIC"):
    return CM.CompanyRow(company=company, model_class=model_class,
                         sector=sector, public_private=public, sparse=sparse,
                         scores={"overall": overall, "history": 9.0},
                         defects=tuple(defects))


# ===========================================================================
# clustering
# ===========================================================================
def test_a_defect_on_one_company_is_not_a_cluster():
    """§103. The honest response to one failure is another observation.

    A cluster of one produces a special case, and a special case for a
    company whose score was red is exactly the per-company patch the
    programme forbids.
    """
    rows = [_row("A", defects=[("TEMPLATE_COLLAPSE", "intro")]),
            _row("B")]
    assert CM.cluster(rows) == []


def test_a_cluster_names_the_attribute_that_separates_it_from_the_rest():
    """Which decides whether the repair is a class rule or a universal one.

    The unaffected third company is what makes the business model a
    DISCRIMINATOR rather than a coincidence: two software companies failing
    while a miner does not is evidence about software; two failing when
    nothing else was measured is evidence about nothing.
    """
    rows = [_row("A", defects=[("TEMPLATE_COLLAPSE", "intro")]),
            _row("B", defects=[("TEMPLATE_COLLAPSE", "full")]),
            _row("C", model_class="COMMODITY_PRODUCER", sector="MATERIALS")]
    found = CM.cluster(rows)
    assert len(found) == 1
    assert found[0].shared.get("model_class") == "SUBSCRIPTION_SOFTWARE"
    assert "business-model rule" in found[0].scope


def test_an_attribute_the_unaffected_companies_also_have_explains_nothing():
    """Ninety of a hundred companies are public; "both are public" is not a
    finding, and scoping a repair on it aims it at the wrong path."""
    rows = [_row("A", defects=[("CUSTOMER_ABSENCE_COPY", "full")]),
            _row("B", model_class="COMMODITY_PRODUCER", sector="MATERIALS",
                 defects=[("CUSTOMER_ABSENCE_COPY", "intro")]),
            _row("C", model_class="BRANDED_CONSUMER", sector="CONSUMER")]
    found = CM.cluster(rows)
    assert "public_private" not in found[0].shared
    assert found[0].scope == "universal rule"


def test_a_defect_that_hit_every_company_is_explained_by_nothing():
    """With no unaffected group there is no contrast, so no attribute can be
    a discriminator — the honest scope is universal."""
    rows = [_row("A", model_class="COMMODITY_PRODUCER", sector="MATERIALS",
                 defects=[("CUSTOMER_ABSENCE_COPY", "full")]),
            _row("B", model_class="SUBSCRIPTION_SOFTWARE", sector="TECH",
                 defects=[("CUSTOMER_ABSENCE_COPY", "intro")])]
    assert CM.cluster(rows)[0].scope == "universal rule"


# ===========================================================================
# improvement
# ===========================================================================
def test_a_repair_that_raises_the_mean_while_the_defect_recurs_has_not_held():
    """§66. The measure that stops a programme congratulating itself."""
    before = CM.WaveResult("w1", (
        _row("A", overall=8.0, defects=[("TEMPLATE_COLLAPSE", "intro")]),
        _row("B", overall=8.0, defects=[("TEMPLATE_COLLAPSE", "intro")])))
    after = CM.WaveResult("w2", (
        _row("A", overall=9.5, defects=[("TEMPLATE_COLLAPSE", "intro")]),
        _row("B", overall=9.5, defects=[])))
    delta = CM.improvement(before, after)
    assert delta["mean_delta"] > 0
    assert not delta["held"]
    assert ("A", "TEMPLATE_COLLAPSE") in delta["recurring"]
    assert ("B", "TEMPLATE_COLLAPSE") in delta["fixed"]


def test_a_repair_that_opens_a_new_defect_has_not_held():
    before = CM.WaveResult("w1", (_row("A", overall=9.0),))
    after = CM.WaveResult("w2", (
        _row("A", overall=9.4, defects=[("WRONG_COMPANY", "intro")]),))
    delta = CM.improvement(before, after)
    assert ("A", "WRONG_COMPANY") in delta["new_classes"]


def test_a_regression_on_one_company_is_reported_even_when_the_mean_rises():
    before = CM.WaveResult("w1", (_row("A", overall=9.0),
                                  _row("B", overall=9.0)))
    after = CM.WaveResult("w2", (_row("A", overall=9.9),
                                 _row("B", overall=8.2)))
    delta = CM.improvement(before, after)
    assert delta["mean_delta"] > 0
    assert delta["regressed"] and delta["regressed"][0][0] == "B"
    assert not delta["held"]


def test_the_worst_company_is_reported_not_only_the_mean():
    wave = CM.WaveResult("w", (_row("A", overall=9.9), _row("B", overall=8.1)))
    assert wave.worst.company == "B"
    assert wave.as_dict()["worst_score"] == 8.1


# ===========================================================================
# cohorts
# ===========================================================================
def test_a_wave_meets_more_than_one_kind_of_business():
    """A deterministic selector that sorts by id accumulates easy companies."""
    cohort = CM.cohort("BREAKER_10")
    assert len(cohort) == 10
    assert len({c["model_class"] for c in cohort}) >= 5


def test_a_cohort_is_deterministic():
    assert CM.cohort("BREAKER_10") == CM.cohort("BREAKER_10")


def test_a_larger_wave_contains_the_smaller_one_is_not_assumed():
    """Recorded rather than asserted: the selector spreads across classes, so
    a wave of thirty is not a superset of ten and must not be assumed to be.
    What IS required is that both are deterministic and diverse."""
    ten, thirty = CM.cohort("BREAKER_10"), CM.cohort("WAVE_30")
    assert len(thirty) == 30
    assert len({c["model_class"] for c in thirty}) >= 5


# ===========================================================================
# persona acceptance
# ===========================================================================
_GOOD = {
    "intro": ("The question worth arguing about is what to charge. Acme, "
              "Inc. is a software business that runs on recurring "
              "subscription. Our read: bounded. What we recommend: the move "
              "is to change price. Guardrail: reversible. Stopping rule: "
              "stop if. How to test it: an experiment. What would change "
              "this view: a disclosure. NASDAQ ACME United States acme.com "
              "SEC 10-K."),
    "slides": ("Acme action the move risk evidence what to watch. "
               "Acme, Inc. NASDAQ."),
    "full": ("Acme mechanism confidence guardrail experiment competitor "
             "falsif margin revenue growth cost index 20% operating "
             "leverage source evidence observed modelled public record "
             "Acme Acme Acme."),
    "story": "Acme Acme Acme grew.",
    "history": ("Actual path Market expectation Better strategy decision "
                "point mechanism assumption principal risk counterfactual "
                "invalidated margin revenue growth cost index 20%."),
    "connect": ("Connect your documents. Feedback: how useful was this "
                "analysis. Start private company intelligence. Your own "
                "numbers. Source evidence observed modelled public record."),
}


def test_a_complete_flow_clears_the_bar():
    result = EP.score(company="Acme, Inc.", pages=_GOOD)
    assert result.overall >= EP.BAR_OVERALL, result.failures()


def test_a_missing_history_step_is_visible_in_the_persona_score():
    pages = dict(_GOOD, history="")
    result = EP.score(company="Acme, Inc.", pages=pages)
    assert result.by_dimension("history_simulator") < 2.5
    assert not result.passes


def test_a_deal_breaker_stops_the_reader_rather_than_deducting_a_point():
    pages = dict(_GOOD, full=_GOOD["full"] + " unavailable")
    result = EP.score(company="Acme, Inc.", pages=pages)
    assert result.by_executive("cfo") <= 2.5
    assert result.by_executive("cso") > 3.0    # scoped to the reader it hit


def test_a_persona_result_can_never_be_reported_as_customer_feedback():
    """§72. The rule that survives aggregation."""
    result = EP.score(company="Acme, Inc.", pages=_GOOD)
    payload = result.as_dict()
    assert payload["simulated"] is True
    assert "not customer feedback" in payload["note"].lower() or \
        "no customer was asked" in payload["note"].lower()
    aggregate = EP.aggregate([result])
    assert aggregate["simulated"] is True
    assert "not customer feedback" in aggregate["note"].lower()


def test_an_evidence_group_is_satisfied_by_any_of_its_members():
    """A company is an Inc or a Corp or a plc — never all three."""
    for dimension, groups in EP.EVIDENCE.items():
        for group in groups:
            assert isinstance(group, tuple), (dimension, group)
            assert group, dimension
