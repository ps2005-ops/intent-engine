"""Mechanism calibration — grading transmission hypotheses against outcomes.

A belief family has always been a mechanism: a trigger, a claim, a committed
consequence and a falsifier. What never happened is anyone going back to ask
whether the transmission held. It could not happen before `observation_binding`,
because until then every reconciliation was TOO_EARLY and every mechanism had
a test count of zero.

The assertions here are mostly refusals, for the same reason as everywhere
else in this system: a reliability figure computed from one observation is a
prior with a decimal point on it.
"""
import pytest

from intent_engine.market import belief_formation as BF
from intent_engine.market import mechanism_calibration as MC
from intent_engine.market import observation_binding as OB


def _rows(family="demand_strengthening", *, confirmed=0, contradicted=0,
          subjects=None):
    """A ledger fragment: one belief, one expectation, N reconciliations."""
    subjects = subjects or ["acme"] * (confirmed + contradicted)
    rows = [
        {"record": "belief", "belief_id": "b1", "subject": "acme"},
        {"record": "expectation", "expectation_id": "e1",
         "hypothesis_id": "b1", "subject": "acme", "metric": family},
    ]
    outcomes = ["CONFIRMED"] * confirmed + ["CONTRADICTED"] * contradicted
    for i, outcome in enumerate(outcomes):
        rows.append({"record": "reconciliation", "expectation_id": "e1",
                     "hypothesis_id": "b1", "outcome": outcome,
                     "subject": subjects[i]})
    return rows


def _find(mechanisms, key):
    return next(m for m in mechanisms if m.key == key)


# ===========================================================================
# THE REFUSALS
# ===========================================================================
def test_reliability_is_unmeasurable_below_the_test_floor():
    """One confirmation is not a reliability of 1.0."""
    mechs = MC.calibrate(_rows(confirmed=1))
    m = _find(mechs, "demand_strengthening")
    assert m.tested == 1
    assert m.reliability == MC.UNMEASURABLE
    assert m.maturity == MC.EMERGING


def test_reliability_becomes_measurable_at_the_floor():
    mechs = MC.calibrate(_rows(confirmed=4, contradicted=1))
    m = _find(mechs, "demand_strengthening")
    assert m.tested == 5
    assert m.reliability == pytest.approx(0.8)


def test_an_untested_mechanism_is_not_graded_as_good():
    """Never tested and always right are opposite findings."""
    mechs = MC.calibrate([])
    m = _find(mechs, "demand_strengthening")
    assert m.tested == 0
    assert m.reliability == MC.UNMEASURABLE
    assert m.maturity == MC.UNTESTED


def test_an_unfalsifiable_mechanism_is_never_called_established():
    """A family nothing can refute has no grade, only a category.

    `capacity_expansion` is confirmed by a capex announcement and refuted by
    nothing observable. Calling it ESTABLISHED after ten confirmations would
    be a category error dressed as a grade.
    """
    mechs = MC.calibrate(_rows(family="capacity_expansion", confirmed=9))
    m = _find(mechs, "capacity_expansion")
    assert m.falsifiable_by_observation is False
    assert m.maturity == MC.UNFALSIFIABLE_BY_OBSERVATION


def test_contradictions_are_never_netted_against_confirmations():
    """8-right-2-wrong is a different object from 6-right-0-wrong."""
    noisy = _find(MC.calibrate(_rows(confirmed=8, contradicted=2)),
                  "demand_strengthening")
    clean = _find(MC.calibrate(_rows(confirmed=6)), "demand_strengthening")
    assert noisy.contradicted == 2 and clean.contradicted == 0
    assert noisy.tested == 10 and clean.tested == 6
    # The netted view would rank the noisy one HIGHER: +6 versus +6 on more
    # evidence. Grading refuses to, and the two do not even share a maturity.
    assert clean.maturity == MC.ESTABLISHED
    assert noisy.maturity == MC.CONTESTED
    # and the raw counts survive into the report rather than being summed away
    assert noisy.as_dict()["contradicted"] != clean.as_dict()["contradicted"]


def test_repeated_tests_on_one_company_are_not_independent_evidence():
    """Eight confirmations from one company is one observation repeated."""
    one = _find(MC.calibrate(_rows(confirmed=8, subjects=["acme"] * 8)),
                "demand_strengthening")
    many = _find(MC.calibrate(_rows(
        confirmed=8, subjects=list("abcdefgh"))), "demand_strengthening")
    assert one.independent_subjects == 1
    assert many.independent_subjects == 8


def test_a_mostly_contradicted_mechanism_is_reported_failing():
    mechs = MC.calibrate(_rows(confirmed=1, contradicted=5))
    assert _find(mechs, "demand_strengthening").maturity == MC.FAILING


def test_a_mixed_mechanism_is_contested_not_established():
    mechs = MC.calibrate(_rows(confirmed=4, contradicted=2))
    assert _find(mechs, "demand_strengthening").maturity == MC.CONTESTED


# ===========================================================================
# THE SUMMARY
# ===========================================================================
def test_summary_names_what_is_still_only_assumed():
    """The untested list is the point of the report.

    A mechanism proposing beliefs at full strength while never having been
    checked is exactly what this exists to surface.
    """
    summary = MC.summarise(MC.calibrate(_rows(confirmed=6)))
    assert summary["mechanisms_tested"] == 1
    assert "market_share_seeking" in summary["assumed_but_never_tested"]
    # and the unfalsifiable ones are listed separately, not as failures
    assert "capacity_expansion" in summary["unfalsifiable_by_observation"]
    assert "capacity_expansion" not in summary["assumed_but_never_tested"]


def test_summary_surfaces_the_most_contradicted_mechanism():
    """The mechanism the evidence argued with taught the engine the most."""
    rows = _rows(family="demand_weakening", contradicted=3)
    assert MC.summarise(MC.calibrate(rows))["most_contradicted"] == \
        "demand_weakening"


def test_every_family_is_covered_by_the_contract():
    """A mechanism missing from the report is a mechanism nobody grades."""
    keys = {m.key for m in MC.calibrate([])}
    assert keys == set(BF.FAMILIES)


def test_maturity_vocabulary_is_closed():
    for rows in ([], _rows(confirmed=1), _rows(confirmed=9),
                 _rows(confirmed=1, contradicted=9)):
        for m in MC.calibrate(rows):
            assert m.maturity in MC.MATURITIES


def test_falsifiable_set_agrees_with_observation_binding():
    """Two modules disagreeing about testability is how reports contradict."""
    graded = {m.key for m in MC.calibrate([])
              if m.falsifiable_by_observation}
    assert graded == set(OB.FALSIFIABLE) & set(BF.FAMILIES)
