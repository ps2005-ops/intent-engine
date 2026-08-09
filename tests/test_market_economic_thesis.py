"""The thesis is the truth; every surface is a projection that may say less."""
from __future__ import annotations

import pytest

from intent_engine.market import economic_thesis as ET


def mech(desc="cost of capital rises so capex falls", falsifier="capex rises",
         **kw):
    return ET.Mechanism(description=desc, falsifier=falsifier, **kw)


def thesis(standing=ET.PROPOSED, alternatives=None, **kw):
    kwargs = dict(subject="acme", question="what does the rate mean?",
                  claim="capex falls", leading_mechanism=mech(),
                  as_of="2026-08-08", standing=standing)
    if alternatives is None and standing in ET.ASSERTABLE:
        alternatives = (mech("it was already committed", "it was not"),)
    kwargs["alternatives"] = tuple(alternatives or ())
    if standing == ET.TESTED:
        kwargs["supporting_evidence"] = ("e1",)
    kwargs.update(kw)
    return ET.EconomicThesis(**kwargs)


# --- the structure refuses what prose would hide ------------------------------

def test_a_mechanism_without_a_falsifier_is_refused():
    with pytest.raises(ET.ThesisRejected) as err:
        ET.Mechanism(description="things happen", falsifier="")
    assert "discriminates none" in str(err.value)


def test_a_thesis_cannot_be_asserted_without_a_live_alternative():
    with pytest.raises(ET.ThesisRejected) as err:
        thesis(standing=ET.SUPPORTED, alternatives=())
    assert "made without saying so" in str(err.value)


def test_a_tested_thesis_needs_the_evidence_that_tested_it():
    with pytest.raises(ET.ThesisRejected):
        ET.EconomicThesis(subject="a", question="q", claim="c",
                          leading_mechanism=mech(),
                          alternatives=(mech("alt", "no"),),
                          standing=ET.TESTED, as_of="2026-08-08")


def test_there_is_no_confirmed_standing():
    assert "CONFIRMED" not in ET.STANDINGS
    assert ET.summarise([])["note"].startswith("no thesis is ever CONFIRMED")


def test_an_undated_thesis_is_refused():
    with pytest.raises(ET.ThesisRejected):
        thesis(as_of="")


# --- competition ------------------------------------------------------------------

def test_a_beaten_thesis_is_retired_not_deleted():
    original = thesis()
    successor, retired = ET.supersede(original, claim="prices rose",
                                      as_of="2026-09-01")
    assert retired.standing == ET.SUPERSEDED
    assert successor.supersedes == original.thesis_id
    assert successor.thesis_id != original.thesis_id


def test_two_equally_supported_rivals_produce_no_leader():
    """The tie IS the answer, and picking one would hide it."""
    a = thesis(standing=ET.SUPPORTED, claim="pricing power")
    b = thesis(standing=ET.SUPPORTED, claim="cost cutting")
    comp = ET.Competition(question="why did margin improve?", subject="acme",
                          theses=(a, b))
    assert comp.leader is None
    assert comp.contested is True


def test_a_stronger_thesis_leads():
    a = thesis(standing=ET.TESTED, claim="pricing power")
    b = thesis(standing=ET.PROPOSED, claim="cost cutting")
    comp = ET.Competition(question="q", subject="acme", theses=(a, b))
    assert comp.leader is a and comp.contested is False


def test_refuted_theses_stay_in_the_record_and_out_of_the_running():
    live = thesis(standing=ET.PROPOSED)
    dead = thesis(standing=ET.REFUTED, claim="mix shift")
    comp = ET.Competition(question="q", subject="acme", theses=(live, dead))
    assert comp.live == (live,)
    assert comp.as_dict()["retired"] == 1
    assert len(comp.as_dict()["theses"]) == 2


# --- outcome and mechanism, apart -----------------------------------------------

def test_right_for_the_wrong_reason_is_its_own_verdict():
    got = ET.score(thesis(), outcome_matched=True, mechanism_matched=False)
    assert got.verdict == ET.RIGHT_FOR_THE_WRONG_REASON
    assert "wrong again" in got.note


def test_an_unchecked_mechanism_is_untested_not_wrong():
    got = ET.score(thesis(), outcome_matched=True, mechanism_matched=None)
    assert got.mechanism == ET.MECHANISM_UNTESTED
    assert got.verdict == "OUTCOME_ONLY"


def test_both_right_is_the_only_correct():
    got = ET.score(thesis(), outcome_matched=True, mechanism_matched=True)
    assert got.verdict == "CORRECT"


# --- proof -------------------------------------------------------------------------

def test_agreement_among_sources_is_not_proof():
    """Three outlets repeating one release is one source."""
    proof = ET.ProofPackage(
        claim="c", evidence_ids=("a", "b", "c"), independent_sources=1,
        causal_basis="m", alternative_explanations=("x",), counterevidence=(),
        falsifier="f", falsifier_tested=False)
    assert proof.status == ET.BOUNDED


def test_verified_requires_the_falsifier_to_have_been_tested():
    tested = ET.ProofPackage(
        claim="c", evidence_ids=("a",), independent_sources=2,
        causal_basis="m", alternative_explanations=("x",), counterevidence=(),
        falsifier="f", falsifier_tested=True)
    assert tested.status == ET.VERIFIED


def test_live_counterevidence_reopens_a_proof():
    proof = ET.ProofPackage(
        claim="c", evidence_ids=("a",), independent_sources=3,
        causal_basis="m", alternative_explanations=("x",),
        counterevidence=("z",), falsifier="f", falsifier_tested=False)
    assert proof.status == ET.OPEN


def test_a_proof_with_no_evidence_is_open_not_failed():
    proof = ET.ProofPackage(
        claim="c", evidence_ids=(), independent_sources=0, causal_basis="m",
        alternative_explanations=(), counterevidence=(), falsifier="f",
        falsifier_tested=True)
    assert proof.status == ET.OPEN


# --- consequences -------------------------------------------------------------------

def cons(order=1, standing=ET.PROPOSED, depends_on=""):
    return ET.ConsequenceHypothesis(
        trigger="rates up", order=order, actor="supplier",
        mechanism="orders fall", direction="DOWN", horizon_days=180,
        falsifier="orders rise", alternative="the backlog absorbed it",
        depends_on=depends_on or ("hop %d" % (order - 1) if order > 1 else ""),
        standing=standing)


def test_depth_past_the_third_hop_is_refused():
    with pytest.raises(ET.ThesisRejected) as err:
        cons(order=4)
    assert "generated, not reasoned" in str(err.value)


def test_a_second_order_claim_must_name_what_it_rests_on():
    with pytest.raises(ET.ThesisRejected):
        ET.ConsequenceHypothesis(
            trigger="t", order=2, actor="a", mechanism="m", direction="DOWN",
            horizon_days=90, falsifier="f", alternative="alt", depends_on="")


def test_a_consequence_needs_the_other_thing_that_looks_the_same():
    with pytest.raises(ET.ThesisRejected):
        ET.ConsequenceHypothesis(
            trigger="t", order=1, actor="a", mechanism="m", direction="DOWN",
            horizon_days=90, falsifier="f", alternative="")


def test_a_path_is_worth_its_weakest_hop_not_its_average():
    path = [cons(1, ET.TESTED), cons(2, ET.PROPOSED), cons(3, ET.TESTED)]
    got = ET.propagate(path)
    assert got["standing"] == ET.PROPOSED
    assert "order 2" in got["weakest"]


def test_a_refuted_hop_voids_the_rest_rather_than_weakening_it():
    path = [cons(1, ET.REFUTED), cons(2, ET.TESTED)]
    got = ET.propagate(path)
    assert got["standing"] == ET.REFUTED
    assert got["void_below"] == "order 1"


# --- scenarios -----------------------------------------------------------------------

def test_a_number_needs_a_calibrated_parameter_behind_it():
    with pytest.raises(ET.ThesisRejected) as err:
        ET.Scenario(kind=ET.DOWNSIDE, assumptions=("rates up",),
                    direction="DOWN", magnitude="-12%")
    assert "no calibrated parameter" in str(err.value)


def test_an_uncalibrated_scenario_speaks_in_words():
    got = ET.Scenario(kind=ET.DOWNSIDE, assumptions=("rates up",),
                      direction="DOWN", magnitude="MODERATE")
    assert got.as_dict()["calibrated"] is False


def test_a_contradictory_pair_is_flagged_rather_than_banned():
    got = ET.check_consistency(ET.Scenario(
        kind=ET.BASE,
        assumptions=("rates DOWN through the year",
                     "financing cost UP for this issuer"),
        direction="DOWN"))
    assert got.inconsistencies
    assert "credit spread" in got.inconsistencies[0]


def test_a_pair_with_its_explanation_is_not_flagged():
    got = ET.check_consistency(ET.Scenario(
        kind=ET.BASE,
        assumptions=("rates DOWN", "financing cost UP",
                     "because of a downgrade"),
        direction="DOWN"))
    assert got.inconsistencies == ()


# --- the invariant every surface inherits ----------------------------------------------

def test_a_slide_cannot_be_more_confident_than_its_thesis():
    with pytest.raises(ET.Overclaim) as err:
        ET.consistent_with(thesis(standing=ET.PROPOSED),
                           rendered_standing=ET.TESTED, surface="slide")
    assert "may say less than its source and never more" in str(err.value)


def test_a_surface_may_say_less():
    ET.consistent_with(thesis(standing=ET.TESTED, alternatives=(mech(),)),
                       rendered_standing=ET.PROPOSED)


def test_dropping_the_alternatives_is_an_overclaim():
    strong = thesis(standing=ET.SUPPORTED)
    with pytest.raises(ET.Overclaim) as err:
        ET.consistent_with(strong, rendered_standing=ET.SUPPORTED,
                           drops_alternatives=True, surface="deck")
    assert "into the only one" in str(err.value)


# --- built from measurement ------------------------------------------------------------

class _Tx:
    company_id = "acme"
    state_kind = "MARKET_RATE"
    dimension = "CAPITAL_INTENSITY"
    mechanism = "a higher cost of capital raises the hurdle"
    direction = "LOWERS"
    lag_days = 270
    falsifier = "capital spending is raised through a rising cost of capital"
    alternative_explanation = "the programme was already committed"
    exposure_evidence_ids = ("e1",)
    as_of = "2026-08-08"


def test_a_transmission_becomes_a_thesis_with_more_than_one_rival():
    got = ET.from_transmission(_Tx())
    assert len(got.alternatives) == 3
    assert any("hedged" in a.description for a in got.alternatives)
    assert got.standing == ET.PROPOSED


def test_a_built_thesis_is_never_born_assertable():
    """Both ends measured is not the same as anything tested."""
    assert ET.from_transmission(_Tx()).assertable is False


def test_every_alternative_carries_its_own_falsifier():
    got = ET.from_transmission(_Tx())
    assert all(a.falsifier.strip() for a in got.alternatives)
    assert len(got.falsifiers) == 4
