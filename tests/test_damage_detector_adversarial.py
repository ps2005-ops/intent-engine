"""§9: DecisionDamage = 0 is a strong claim, so attack the detector.

WHY THIS FILE EXISTS
--------------------
Three of the eight declared damage kinds had no detector referencing them at
all — `FALSE_SPECIFICITY`, `WRONG_EXPOSURE`, `GENERIC_RECOMMENDATION`. "Zero
damages" was therefore in part a statement about a vocabulary rather than
about the analyses, which is the same defect as a test that cannot fail.

Every kind now has a detector, and every detector is attacked here with a case
built to trigger it. A zero from an instrument that has never been shown to
fire is not evidence.

AND THE INSTRUMENT ITSELF WAS WRONG ONCE
----------------------------------------
The first version of the two new detectors decided "is this an economic risk"
from an id prefix that only the product arm uses, so the research arm's risks
all read as non-economic and both fired on 25 of 25 material cases. A uniform
count is what a broken instrument looks like. The risk now DECLARES its
quantity, and `test_a_uniform_damage_count_is_refused` pins the property that
found it.
"""
from __future__ import annotations

import pytest

from intent_engine.econ import founder_ab as FA


def _risk(**kw):
    base = dict(risk_id="r", severity="MEDIUM", channel="c",
                mechanism="m", standing=FA.INFERRED, evidence=("e",))
    base.update(kw)
    return FA.Risk(**base)


def _analysis(variant=FA.A, **kw):
    base = dict(company_id="acme", as_of="2026-08-27", variant=variant,
                top_priority="p", action=FA.MONITOR, risks=(_risk(),),
                scenario="POSSIBLE", confidence="LOW",
                information_requests=("q",), evidence=("e",))
    base.update(kw)
    return FA.Analysis(**base)


def _kinds(damages):
    return {d.kind for d in damages}


# --- the coverage claim itself ----------------------------------------------
def test_every_declared_damage_kind_has_a_detector():
    """A kind nothing looks for makes the zero mean less than it appears to."""
    coverage = FA.damage_coverage()
    assert not coverage["without_detector"], (
        f"{coverage['without_detector']} are declared and undetectable, so a "
        "DecisionDamage of 0 is partly a statement about this tuple")


# --- one adversarial case per kind ------------------------------------------
def test_unsupported_mechanism_is_caught():
    a = _analysis()
    b = _analysis(FA.B, risks=(_risk(standing=FA.OBSERVED, evidence=()),))
    assert "UNSUPPORTED_MECHANISM" in _kinds(
        FA.detect_damage(a, b, regime="t"))


def test_excessive_confidence_is_caught():
    a = _analysis(confidence="LOW")
    b = _analysis(FA.B, confidence="HIGH")
    assert "EXCESSIVE_CONFIDENCE" in _kinds(
        FA.detect_damage(a, b, regime="t"))


def test_irrelevant_macro_is_caught():
    a = _analysis()
    b = _analysis(FA.B, risks=(_risk(), _risk(risk_id="r2")),
                  economic_inputs=("econ:policy_rate@2026-08-27",))
    assert "IRRELEVANT_MACRO" in _kinds(FA.detect_damage(a, b, regime="t"))


def test_stale_state_is_caught():
    a = _analysis()
    b = _analysis(FA.B, economic_inputs=("econ:policy_rate@2020-01-01",))
    assert "STALE_STATE" in _kinds(
        FA.detect_damage(a, b, regime="t", stale_days=600))


def test_duplicated_evidence_is_caught():
    a = _analysis()
    b = _analysis(FA.B, evidence=("e", "e"))
    assert "DUPLICATED_EVIDENCE" in _kinds(FA.detect_damage(a, b, regime="t"))


def test_wrong_exposure_is_caught():
    """A risk raised through a condition this company is not exposed to."""
    a = _analysis()
    b = _analysis(FA.B, risks=(_risk(risk_id="econ:commodity_oil",
                                     quantity="commodity_oil"),))
    assert "WRONG_EXPOSURE" in _kinds(FA.detect_damage(
        a, b, regime="t", evidenced_exposures=("policy_rate",)))


def test_a_risk_on_an_evidenced_exposure_is_not_wrong_exposure():
    """The check must be able to stay silent, or it is not a check."""
    a = _analysis()
    b = _analysis(FA.B, risks=(_risk(risk_id="econ:policy_rate",
                                     quantity="policy_rate"),))
    assert "WRONG_EXPOSURE" not in _kinds(FA.detect_damage(
        a, b, regime="t", evidenced_exposures=("policy_rate",)))


def test_false_specificity_is_caught():
    """A figure asserted as observed that no cited evidence carries."""
    a = _analysis()
    b = _analysis(FA.B, risks=(_risk(
        standing=FA.OBSERVED,
        mechanism="margin falls 37.5% as funding repricing lands",
        evidence=("econ:policy_rate@2026-08-27",)),),
        evidence=("econ:policy_rate@2026-08-27",))
    assert "FALSE_SPECIFICITY" in _kinds(FA.detect_damage(a, b, regime="t"))


def test_a_figure_the_evidence_carries_is_not_false_specificity():
    a = _analysis()
    b = _analysis(FA.B, risks=(_risk(
        standing=FA.OBSERVED, mechanism="the rate stands at 4.33",
        evidence=("econ:policy_rate@4.33",)),),
        evidence=("econ:policy_rate@4.33",))
    assert "FALSE_SPECIFICITY" not in _kinds(FA.detect_damage(a, b, regime="t"))


def test_unnecessary_change_is_caught():
    """The recommendation moved with nothing behind it."""
    a = _analysis(action=FA.MONITOR)
    b = _analysis(FA.B, action=FA.ACT)
    assert "UNNECESSARY_CHANGE" in _kinds(FA.detect_damage(a, b, regime="t"))


def test_missed_material_risk_is_caught():
    """An adverse condition moved and B raised nothing."""
    a = _analysis()
    b = _analysis(FA.B)
    assert "MISSED_MATERIAL_RISK" in _kinds(FA.detect_damage(
        a, b, regime="t", adverse_conditions=("policy_rate",)))


def test_wrong_sign_is_caught():
    """A risk raised on a condition moving the way that helps."""
    a = _analysis()
    b = _analysis(FA.B, risks=(_risk(risk_id="econ:labour",
                                     quantity="labour",
                                     standing=FA.OBSERVED),))
    assert "WRONG_SIGN" in _kinds(FA.detect_damage(
        a, b, regime="t", adverse_conditions=("policy_rate",)))


def test_generic_recommendation_is_caught():
    """No pairwise check can see this; it is a property of a corpus."""
    same = [_analysis(FA.B, company_id=f"c{i}", top_priority="cost of funds")
            for i in range(5)]
    assert "GENERIC_RECOMMENDATION" in _kinds(FA.detect_generic(same))


def test_a_differentiated_corpus_is_not_generic():
    varied = [_analysis(FA.B, company_id=f"c{i}", top_priority=f"channel {i}")
              for i in range(5)]
    assert FA.detect_generic(varied) == []


# --- the instrument's own failure mode --------------------------------------
def test_an_economic_risk_declares_its_quantity_rather_than_encoding_it():
    """The detector decided "is this economic" from an id prefix only one arm
    used, so the other arm's risks all read as non-economic and two kinds
    fired on 25 of 25 material cases."""
    r = _risk(risk_id="econ:policy_rate", quantity="policy_rate")
    assert r.quantity == "policy_rate"
    assert r.as_dict()["quantity"] == "policy_rate"
    # An economic risk identified WITHOUT the prefix still counts.
    a = _analysis()
    b = _analysis(FA.B, action=FA.ACT,
                  risks=(_risk(risk_id="walmart:UNRATE", quantity="UNRATE"),))
    assert "UNNECESSARY_CHANGE" not in _kinds(
        FA.detect_damage(a, b, regime="t"))


def test_a_uniform_damage_count_is_refused_as_a_finding():
    """Every material case producing exactly one damage of one kind is what a
    broken instrument looks like. Asserted on the real 60-case run's record so
    it cannot be satisfied by a fixture."""
    import json
    import pathlib
    path = pathlib.Path("reports/decision_value.json")
    if not path.exists():
        pytest.skip("the decision-value record has not been produced here")
    payload = json.loads(path.read_text())
    summary = payload["summary"]
    by_kind = summary.get("damage_by_kind") or {}
    material = summary.get("material") or 0
    for kind, n in by_kind.items():
        assert not (material and n == material), (
            f"{kind} fired on exactly {n} of {material} material cases; a "
            "uniform count is an instrument tell, not a finding")
