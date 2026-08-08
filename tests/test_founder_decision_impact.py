"""Did market learning change a decision, or just make the page longer?

RENDERED_TO_FOUNDER reached 22 of 22 and proved nothing about value. A
strategic block can be perfectly provenanced, appear on the page, and leave
every risk, assumption and falsifier exactly where it was.

The obvious way to build this metric is to wire it to "something changed",
and it would then read 100% forever, because something always changes when a
block is added. So most of this file is the controls: the same dossier applied
twice, a change with no evidence behind it, a longer field with identical
content, a caution that would fit any company. Each has an obvious reading
that inflates impact, and each must come back NONE.
"""
import pytest

from intent_engine.external_intel import decision_impact as DI


def _state(**kw):
    return {k: v for k, v in kw.items()}


# ===========================================================================
# THE CONTROLS — these are the tests that make the metric mean anything
# ===========================================================================
def test_the_same_content_twice_is_not_an_impact():
    """Re-applying a dossier is not new learning."""
    state = _state(ASSUMPTION=["demand appears to be strengthening"])
    impact = DI.assess(analysis_id="a", company_id="acme", before=state,
                       after=state, provenance=["ev_1"])
    assert impact.changed is False
    assert impact.materiality == DI.NONE


def test_a_change_with_no_provenance_is_not_credited():
    """An unattributable change might be sampling noise, not learning.

    Crediting it would corrupt the one metric that says whether the market
    engine's output is worth anything.
    """
    impact = DI.assess(
        analysis_id="a", company_id="acme",
        before=_state(ASSUMPTION=[]),
        after=_state(ASSUMPTION=["demand appears to be strengthening"]),
        provenance=[])
    assert impact.materiality == DI.NONE
    assert "no market evidence is cited" in impact.reason


def test_a_longer_field_with_the_same_content_is_unchanged():
    """Word count is not impact."""
    delta = DI.compare_field(
        DI.RISK, ["Concentration risk in one customer"],
        ["  concentration   risk  in one CUSTOMER  "])
    assert delta.change == DI.UNCHANGED


def test_a_repeated_item_is_not_a_new_item():
    delta = DI.compare_field(DI.RISK, ["a risk"], ["a risk", "A RISK"])
    assert delta.change == DI.UNCHANGED


@pytest.mark.parametrize("boilerplate", [
    "This may be important to consider.",
    "It is important to monitor developments.",
    "Further evidence would be helpful.",
    "The company should monitor the situation.",
    "In general, conditions vary.",
])
def test_generic_caution_is_never_an_impact(boilerplate):
    """A sentence that would fit any company says nothing about this one."""
    delta = DI.compare_field(DI.RISK, [], [boilerplate])
    assert delta.change == DI.UNCHANGED


def test_an_added_citation_alone_is_not_an_impact():
    """Provenance on a claim that already stood is better hygiene, not a
    different decision."""
    delta = DI.compare_field(DI.ASSUMPTION, ["demand is strengthening"],
                             ["demand is strengthening"])
    assert delta.change == DI.UNCHANGED


# ===========================================================================
# WHAT DOES COUNT
# ===========================================================================
def test_a_new_assumption_is_meaningful():
    impact = DI.assess(
        analysis_id="a", company_id="acme", before=_state(ASSUMPTION=[]),
        after=_state(ASSUMPTION=["demand appears to be strengthening"]),
        provenance=["ev_1"])
    assert impact.materiality == DI.MEANINGFUL
    assert DI.ASSUMPTION in impact.as_dict()["impact_types"]


def test_a_changed_recommendation_is_decision_changing():
    """A headline that moves is not a nuance."""
    impact = DI.assess(
        analysis_id="a", company_id="acme",
        before=_state(RECOMMENDATION=["expand capacity now"]),
        after=_state(RECOMMENDATION=["hold capacity until demand confirms"]),
        provenance=["ev_1"])
    assert impact.materiality == DI.DECISION_CHANGING


def test_replaced_content_is_reversed_not_added():
    delta = DI.compare_field(DI.ASSUMPTION, ["demand is weakening"],
                             ["demand is strengthening"])
    assert delta.change == DI.REVERSED


def test_losing_a_field_entirely_is_weakened():
    delta = DI.compare_field(DI.FALSIFIER, ["a lower revenue figure"], [])
    assert delta.change == DI.WEAKENED


# ===========================================================================
# CONTRACT
# ===========================================================================
def test_materiality_vocabulary_is_closed():
    for after in ([], ["x"], ["y", "z"]):
        impact = DI.assess(analysis_id="a", company_id="c",
                           before=_state(RISK=["y"]), after=_state(RISK=after),
                           provenance=["ev"])
        assert impact.materiality in DI.MATERIALITY


def test_an_unknown_impact_type_is_refused():
    with pytest.raises(ValueError):
        DI.compare_field("VIBES", [], ["something"])


def test_the_impact_id_is_stable_for_the_same_inputs():
    kw = dict(analysis_id="a", company_id="acme", dossier_revision="2026-08-07",
              belief_id="b1", before=_state(RISK=[]), after=_state(RISK=["r"]),
              provenance=["ev"])
    assert DI.assess(**kw).decision_impact_id == DI.assess(**kw).decision_impact_id


def test_a_new_dossier_revision_is_a_different_impact():
    base = dict(analysis_id="a", company_id="acme", belief_id="b1",
                before=_state(RISK=[]), after=_state(RISK=["r"]),
                provenance=["ev"])
    first = DI.assess(dossier_revision="2026-08-06", **base)
    second = DI.assess(dossier_revision="2026-08-07", **base)
    assert first.decision_impact_id != second.decision_impact_id
