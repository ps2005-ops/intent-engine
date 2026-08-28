"""§4-§7: a blind spot must be a tension THIS company can actually have.

WHAT WAS WRONG
--------------
A tension fired whenever two SIGNAL NAMES were both present in a company's
observations. Signal names are generic — `platform_control` and
`partner_ecosystem_enablement` describe a marketplace and also match a chip
designer's partner-programme language — so NVIDIA's founder analysis carried

    "Consolidating checkout/identity/data rails may encroach on layers
     partners currently monetize."

as its leading company risk, and through Baseline A's fallback that sentence
became its `top_priority`. Measured on the deployed preview.

WHY THE FIX IS NOT A STOPLIST
-----------------------------
Nothing about the words was wrong; they are a real tension for a commerce
platform. What was missing was the second condition: the tension has to be one
this KIND of business can have. So each tension declares `applies_to`, keyed on
the same business-model vocabulary the transmission table uses, and
`tension_applies` fails closed when applicability is undeclared or the model
could not be read.

THE COVERAGE FACT THIS EXPOSES
------------------------------
All three tensions in the library describe a multi-sided commerce platform —
one or two of the ten model classes the validation manifest carries. That is
written down rather than hidden by letting them fire everywhere. Widening the
library means writing tensions that are true of the other classes, which is
research and not a filter change.
"""
from __future__ import annotations

import pytest

from intent_engine.strategic_intelligence import patterns as P
from intent_engine.strategic_intelligence.reasoning import _build_blind_spots


class _Obs:
    """The minimum a tension reads. Deliberately not the full record: this
    tests the GATE, and a fuller fixture would let the rest of the pipeline
    decide the outcome instead."""

    def __init__(self, signals, oid="obs-1"):
        self.signals = tuple(signals)
        self.observation_id = oid
        self.weak = False
        self.source_class = "company_owned"
        self.date = "2026-01-01"
        self.excerpt = self.text = "x"
        self.source_title = "t"


def _both_sides(tension):
    return [_Obs(tension["left"] + tension["right"])]


# --- §5 the contract --------------------------------------------------------
def test_every_tension_declares_which_businesses_it_applies_to():
    """An undeclared tension cannot fire at all, so this is not cosmetic."""
    assert P.TENSIONS, "the library is empty; this guard would be vacuous"
    undeclared = [t["tension_id"] for t in P.TENSIONS
                  if not t.get("applies_to")]
    assert not undeclared, (
        f"{undeclared} declare no applicability and can therefore never "
        "fire; a tension with no business model is a sentence looking for a "
        "company")


def test_the_library_states_which_models_it_can_speak_about():
    coverage = P.tension_model_coverage()
    assert coverage["tensions"] == len(P.TENSIONS)
    assert coverage["models_covered"]
    assert not coverage["undeclared"]


# --- §4 the defect that was measured live -----------------------------------
def test_a_semiconductor_does_not_receive_a_commerce_tension():
    """The live defect, as a test. NVIDIA is DESIGN_AND_MANUFACTURE."""
    commerce = next(t for t in P.TENSIONS
                    if t["tension_id"] == "control_vs_partner_openness")
    blind, refused = _build_blind_spots(_both_sides(commerce),
                                        "DESIGN_AND_MANUFACTURE")
    assert blind == [], (
        "a chip designer was handed "
        f"{[b.observed_tension[:60] for b in blind]}")
    assert refused and refused[0]["kind"] == P.NOT_APPLICABLE


def test_a_bank_does_not_receive_a_retail_or_marketplace_tension():
    for tension in P.TENSIONS:
        blind, refused = _build_blind_spots(_both_sides(tension),
                                            "BALANCE_SHEET_OR_NETWORK")
        assert blind == [], f"{tension['tension_id']} fired for a bank"
        assert refused


def test_the_business_this_tension_is_about_still_receives_it():
    """A gate that refuses everything is not a gate, it is a deletion."""
    commerce = next(t for t in P.TENSIONS
                    if t["tension_id"] == "control_vs_partner_openness")
    blind, refused = _build_blind_spots(_both_sides(commerce),
                                        "SUBSCRIPTION_SOFTWARE")
    assert len(blind) == 1 and not refused
    assert blind[0].kind == P.INFERRED_INFORMATION_GAP


# --- §6 failure semantics ---------------------------------------------------
def test_an_unread_business_model_is_a_coverage_gap_not_a_tension():
    """Fail closed, and say which kind of absence it is: a model we could not
    read and a model that rules the tension out are different findings."""
    commerce = P.TENSIONS[0]
    blind, refused = _build_blind_spots(_both_sides(commerce), "")
    assert blind == []
    assert refused[0]["kind"] == P.MODEL_COVERAGE_GAP
    assert refused[0]["business_model"] == "UNKNOWN"


def test_a_tension_with_only_one_side_observed_is_not_refused_it_is_absent():
    """Never fabricate a gap to populate the section — and never report an
    unobserved tension as one the model ruled out."""
    commerce = P.TENSIONS[0]
    blind, refused = _build_blind_spots([_Obs(commerce["left"])],
                                        "SUBSCRIPTION_SOFTWARE")
    assert blind == [] and refused == []


@pytest.mark.parametrize("kind", P.BLIND_SPOT_KINDS)
def test_every_declared_kind_is_a_real_string(kind):
    assert isinstance(kind, str) and kind.isupper()


def test_a_blind_spot_carries_the_kind_of_gap_it_is():
    commerce = P.TENSIONS[0]
    blind, _refused = _build_blind_spots(_both_sides(commerce),
                                         "SUBSCRIPTION_SOFTWARE")
    assert blind and blind[0].kind in P.BLIND_SPOT_KINDS
    assert blind[0].as_dict()["kind"] == blind[0].kind


# --- the same gate on the other two producers -------------------------------
def test_surprises_and_opportunities_are_gated_by_the_same_rule():
    """Blind spots were not the only surface these reached. Surprises and
    opportunities are built from the same tensions, so an ungated tension
    leaked commerce language onto every surface that renders them."""
    from intent_engine.strategic_intelligence import insights as I
    commerce = next(t for t in P.TENSIONS
                    if t["tension_id"] == "control_vs_partner_openness")
    obs = _both_sides(commerce)
    assert I._live_tensions(obs, "DESIGN_AND_MANUFACTURE") == []
    assert I._live_tensions(obs, "") == []
    assert len(I._live_tensions(obs, "SUBSCRIPTION_SOFTWARE")) == 1


def test_every_applicable_class_is_a_real_business_model():
    """A tension gated on a class that does not exist is a silent deletion.

    The first version of the table declared `MARKETPLACE_OR_PLATFORM`, which
    is not one of the classes `company_profile` carries — so the tension it
    gated could never fire for any real company, and the gate looked like a
    filter while behaving like a delete.
    """
    from intent_engine.executive import company_profile as CPF
    real = {k[1] for k in CPF._TRANSMISSION} | {
        k[1] for k in CPF._ADVERSE_DIRECTION}
    declared = {m for t in P.TENSIONS for m in (t.get("applies_to") or ())}
    invented = sorted(declared - real)
    assert not invented, (
        f"{invented} are not business-model classes this product assigns, so "
        "any tension gated on them can never fire for a real company")
