"""Certainty may not be gained by travelling between surfaces.

The central test here is `test_a_refuted_thesis_cannot_produce_a_verified_proof`.
That one was a live defect: `ProofPackage.status` was derived from evidence
counts alone, so a thesis the engine had abandoned reported VERIFIED and the
deck printed it in the appendix. Everything else in this file protects a rule;
that one protects the reason the module exists.

The second theme is that facts about the RECORD are not weak facts about the
world. `HISTORY_UNAVAILABLE` and `HISTORY_AVAILABLE_NO_MOVEMENT` are not two
points on one scale, and the tests below assert that asking which is stronger
raises rather than answers.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from intent_engine.market import economic_thesis as ET
from intent_engine.market import presentation as P
from intent_engine.market import standing_wall as SW
from intent_engine.market import strategic_export as SE

MARKET_ROOT = pathlib.Path("/Users/prathamsharma/intent-engine-market")
DOSSIERS = MARKET_ROOT / "reports/market/strategic"


def _mechanism(**kw):
    base = dict(description="rates raise the cost of capital",
                falsifier="capex does not fall within 270 days", key="k")
    base.update(kw)
    return ET.Mechanism(**base)


def thesis(standing=ET.PROPOSED, *, alternatives=None, evidence=("ev1",)):
    alts = alternatives if alternatives is not None else (
        _mechanism(description="the exposure was hedged",
                   falsifier="the company states a hedge", key="alt"),)
    return ET.EconomicThesis(
        subject="ACME", question="does capex fall?", claim="capex falls",
        leading_mechanism=_mechanism(), alternatives=alts,
        as_of="2026-08-09", standing=standing, supporting_evidence=evidence)


# --- the proof may not outrank the thesis it proves --------------------------

def test_a_refuted_thesis_cannot_produce_a_verified_proof():
    """The live defect. Two independent sources and a tested falsifier used to
    report VERIFIED for a reading the engine had already abandoned."""
    proof = ET.prove(thesis(ET.REFUTED), falsifier_tested=True,
                     independent_sources=2)
    assert proof.evidential_status == ET.VERIFIED
    assert proof.status == ET.FAILED
    assert proof.capped_by_thesis


@pytest.mark.parametrize("standing,expected", [
    (ET.PROPOSED, ET.OPEN),
    (ET.SUPPORTED, ET.BOUNDED),
    (ET.TESTED, ET.VERIFIED),
    (ET.WEAKENED, ET.OPEN),
    (ET.REFUTED, ET.FAILED),
    (ET.SUPERSEDED, ET.FAILED),
])
def test_the_cap_is_graded_rather_than_binary(standing, expected):
    """Every standing gets its own ceiling. A cap with two outcomes would let
    PROPOSED and SUPPORTED report the same proof."""
    proof = ET.prove(thesis(standing), falsifier_tested=True,
                     independent_sources=2)
    assert proof.status == expected


def test_the_evidential_status_survives_the_cap():
    """"The sources would have carried VERIFIED and the thesis did not" is the
    diagnostic, and it is lost if the cap overwrites rather than caps.

    The second half is what makes this load-bearing. Asserting only that the
    capped case keeps its diagnostic leaves the cap free to ignore the
    evidence entirely — a cap that always returns OPEN satisfies it. So the
    UNCAPPED case is asserted too: where the thesis permits it, the status is
    the evidence's own reading and nothing else.
    """
    capped = ET.prove(thesis(ET.PROPOSED), falsifier_tested=True,
                      independent_sources=2)
    assert capped.evidential_status == ET.VERIFIED
    assert capped.as_dict()["evidential_status"] == ET.VERIFIED
    assert capped.as_dict()["capped_by_thesis"] is True

    uncapped = ET.prove(thesis(ET.TESTED), falsifier_tested=True,
                        independent_sources=2)
    assert uncapped.status == uncapped.evidential_status == ET.VERIFIED
    assert uncapped.capped_by_thesis is False


def test_an_unbound_proof_package_is_unchanged():
    """Every caller predating the wall passes no standing, and none of them
    silently changed behaviour."""
    legacy = ET.ProofPackage(
        claim="c", evidence_ids=("e",), independent_sources=2,
        causal_basis="b", alternative_explanations=(), counterevidence=(),
        falsifier="f", falsifier_tested=True)
    assert legacy.thesis_standing == ""
    assert legacy.status == ET.VERIFIED
    assert legacy.capped_by_thesis is False


def test_a_proof_is_never_raised_by_the_thesis():
    """The cap only ever lowers. A TESTED thesis with one source stays
    BOUNDED; standing is not a substitute for evidence."""
    proof = ET.prove(thesis(ET.TESTED), falsifier_tested=False,
                     independent_sources=1)
    assert proof.status == ET.BOUNDED


# --- record states are not weak world states --------------------------------

def test_a_record_state_licenses_no_assertion():
    for state in SW.RECORD_STATES:
        assert SW.ceiling(state) == SW.ASSERT_NONE


def test_history_unavailable_and_no_movement_are_not_interchangeable():
    """The substitution this engine keeps making: "we cannot see" rendered as
    "we looked and it held still"."""
    assert not SW.interchangeable(SW.HISTORY_UNAVAILABLE,
                                  SW.HISTORY_AVAILABLE_NO_MOVEMENT)
    assert SW.RECORD_STATE_WORDS[SW.HISTORY_UNAVAILABLE] != \
        SW.RECORD_STATE_WORDS[SW.HISTORY_AVAILABLE_NO_MOVEMENT]


def test_no_two_record_states_are_interchangeable():
    for a in SW.RECORD_STATES:
        for b in SW.RECORD_STATES:
            assert SW.interchangeable(a, b) is (a == b)


def test_every_record_state_has_a_distinct_reading():
    readings = [SW.RECORD_STATE_WORDS[s] for s in SW.RECORD_STATES]
    assert len(set(readings)) == len(readings)


def test_ranking_a_negative_ceiling_is_a_category_error():
    """"This reading does not hold" is not a weaker version of "it holds"."""
    with pytest.raises(SW.CategoryError):
        SW.rank(SW.ASSERT_NEGATIVE)


def test_a_hop_standing_is_rejected_rather_than_mapped():
    """The two vocabularies overlap at SUPPORTED and nowhere else; a slot that
    takes both silently loses the difference."""
    with pytest.raises(SW.StandingViolation):
        SW.ceiling("HYPOTHESIZED")
    with pytest.raises(SW.StandingViolation):
        SW.ceiling("CONTRADICTED")


def test_an_unknown_state_raises_rather_than_defaulting():
    with pytest.raises(SW.StandingViolation):
        SW.ceiling("PRETTY_SURE")


# --- the certainty ceiling has to move --------------------------------------

def test_the_forbidden_vocabulary_narrows_as_the_record_weakens():
    """A word list that does not change with the standing is a constant
    wearing the name of a ceiling."""
    sizes = [len(SW.banned_words(c)) for c in
             (SW.ASSERT_TESTED, SW.ASSERT_BOUNDED, SW.ASSERT_LEADING,
              SW.ASSERT_NONE)]
    assert sizes == sorted(sizes)
    assert len(set(sizes)) == len(sizes)


def test_the_strongest_standing_still_forbids_something():
    """The strongest thing this engine can say is that it tried to break a
    reading and could not, so no standing licenses "guaranteed"."""
    assert "guaranteed" in SW.banned_words(SW.ASSERT_TESTED)


def test_a_weaker_ceiling_inherits_every_stronger_prohibition():
    strong = set(SW.banned_words(SW.ASSERT_TESTED))
    assert strong <= set(SW.banned_words(SW.ASSERT_NONE))


def test_every_rung_of_the_ladder_forbids_something_new():
    """A rung that adds nothing is a rung that is not there.

    The first arrangement of this table put the truth-claim words at
    ASSERT_BOUNDED while a separate flat list also held them, so BOUNDED
    forbade exactly what TESTED did and the middle of the ladder was dead. A
    break proof collapsing the whole table passed against it.
    """
    ladder = (SW.ASSERT_TESTED, SW.ASSERT_BOUNDED, SW.ASSERT_LEADING,
              SW.ASSERT_NONE)
    for stronger, weaker in zip(ladder, ladder[1:]):
        added = set(SW.banned_words(weaker)) - set(SW.banned_words(stronger))
        assert added, f"{weaker} forbids nothing {stronger} allows"


def test_wording_is_caught_at_the_standing_that_forbids_it():
    """The claim that the falsifier was tested is what SUPPORTED loses."""
    assert SW.words_beyond("this withstood the test", ET.TESTED) == ()
    assert "withstood" in SW.words_beyond("this withstood the test",
                                          ET.SUPPORTED)


def test_the_truth_claim_is_refused_at_every_standing():
    for standing in (ET.TESTED, ET.SUPPORTED, ET.PROPOSED, ET.WEAKENED):
        assert "proves" in SW.words_beyond("this proves the effect", standing)


# --- the cross-surface adjudication -----------------------------------------

def test_a_proposed_thesis_cannot_become_a_confirmed_slide():
    report = SW.check(ET.PROPOSED, [
        SW.SurfaceClaim("deck", ET.TESTED),
    ])
    assert not report.consistent
    assert "deck" in report.violations[0]


def test_a_surface_may_always_say_less():
    report = SW.check(ET.TESTED, [SW.SurfaceClaim("deck", ET.PROPOSED)])
    assert report.consistent


def test_an_abandoned_reading_may_not_be_reported_as_holding():
    for weaker in (ET.PROPOSED, ET.SUPPORTED, ET.TESTED):
        report = SW.check(ET.REFUTED, [SW.SurfaceClaim("answer", weaker)])
        assert not report.consistent


def test_every_disagreement_is_reported_not_just_the_first():
    """A wall that stops at the first violation gets fixed one surface at a
    time, and the next cycle finds the next."""
    report = SW.check(ET.PROPOSED, [
        SW.SurfaceClaim("deck", ET.TESTED),
        SW.SurfaceClaim("answer", ET.SUPPORTED),
        SW.SurfaceClaim("brief", ET.PROPOSED, keeps_alternatives=False),
    ])
    assert len(report.violations) == 3


def test_a_dropped_alternative_is_caught_at_every_standing():
    """`consistent_with` only guards assertable theses. A PROPOSED thesis
    rendered without its rivals is the same failure one standing down."""
    report = SW.check(ET.PROPOSED, [
        SW.SurfaceClaim("deck", ET.PROPOSED, keeps_alternatives=False)])
    assert not report.consistent


def test_a_dropped_falsifier_is_caught():
    report = SW.check(ET.SUPPORTED, [
        SW.SurfaceClaim("deck", ET.SUPPORTED, keeps_falsifiers=False)])
    assert not report.consistent


def test_certainty_language_is_adjudicated_with_the_rest():
    report = SW.check(ET.PROPOSED, [
        SW.SurfaceClaim("answer", ET.PROPOSED,
                        text="this is confirmed and definitely happening")])
    assert not report.consistent


# --- what crosses to a consumer that cannot import this module --------------

def test_the_export_carries_the_decision_not_the_input():
    got = SW.export(ET.SUPPORTED)
    assert got["ceiling"] == SW.ASSERT_BOUNDED
    assert "proves" in got["forbidden_words"]
    assert got["thesis_standing"] == ET.SUPPORTED


def test_exporting_an_overclaiming_proof_is_refused_at_the_boundary():
    with pytest.raises(SW.StandingViolation):
        SW.export(ET.PROPOSED, proof_status=ET.VERIFIED)


def test_a_record_state_exports_its_own_reading():
    got = SW.export(SW.HISTORY_UNAVAILABLE)
    assert got["is_record_state"] is True
    assert got["ceiling"] == SW.ASSERT_NONE
    assert "readable" in got["reading"]


# --- three representations: object, persisted row, transported payload ------

def test_the_ceiling_survives_the_export_projection():
    """A. live producer object -> C. transported consumer representation."""
    row = SE._economic_thesis(thesis(ET.SUPPORTED))
    assert row["ceiling"] == SW.ASSERT_BOUNDED
    assert "proves" in row["forbidden_words"]


def test_the_ceiling_is_the_same_from_a_persisted_row():
    """B. persisted/reloaded dict -> C, and it must agree with A.

    The projector reads objects on the cycle and dicts from the store. A
    ceiling that differed by shape would put two readings of one thesis on two
    surfaces, which is the failure this wall exists to prevent.
    """
    live = SE._economic_thesis(thesis(ET.SUPPORTED))
    persisted = SE._economic_thesis(json.loads(json.dumps(
        {"thesis_id": live["thesis_id"], "claim": live["claim"],
         "standing": ET.SUPPORTED, "question": live["question"],
         "horizon_days": 90, "macro_conditions": [], "exposures": [],
         "alternatives": ["the exposure was hedged"], "unknowns": [],
         "decision_implication": "", "evidence_ids": ["ev1"]})))
    assert persisted["ceiling"] == live["ceiling"]
    assert persisted["forbidden_words"] == live["forbidden_words"]


def test_an_unknown_standing_crosses_as_no_ceiling_rather_than_a_guess():
    """An unrecognised standing is not mapped onto the nearest known one: the
    producer failing to name its standing is not evidence the claim is weak."""
    row = SE._economic_thesis({"standing": "PRETTY_SURE", "claim": "c"})
    assert row["ceiling"] == ""
    assert row["forbidden_words"] == []


@pytest.mark.parametrize("shape", ["object", "dict", "empty", "missing"])
def test_the_projector_survives_every_alternatives_shape(shape):
    """`alternatives` are Mechanism objects live and strings persisted, and
    both have reached this projector in production."""
    payloads = {
        "object": thesis(ET.PROPOSED),
        "dict": {"standing": ET.PROPOSED, "claim": "c",
                 "alternatives": ["hedged"]},
        "empty": {"standing": ET.PROPOSED, "claim": "c", "alternatives": []},
        "missing": {"standing": ET.PROPOSED, "claim": "c"},
    }
    row = SE._economic_thesis(payloads[shape])
    assert row["ceiling"] == SW.ASSERT_LEADING
    assert isinstance(row["alternatives"], list)


# --- the fourth history state, found on the live corpus ---------------------

def test_zero_revisions_is_not_a_finding_about_movement():
    """22 of 25 published dossiers said "nothing has changed this view yet"
    about companies for which no view had ever been formed."""
    got = SE._thesis_history([], available=True)
    assert got["status"] == SE.HISTORY_AVAILABLE_NO_THESIS
    assert got["revisions"] == 0


def test_the_four_history_states_stay_four():
    assert len(set(SE.HISTORY_STATES)) == 4
    assert SE.HISTORY_AVAILABLE_NO_THESIS in SE.HISTORY_STATES


def test_an_opened_but_unmoved_thesis_still_reports_no_movement():
    """The fix must not collapse the state it was distinguishing itself from."""
    got = SE._thesis_history(
        [{"revision_id": "r1", "transition": "CREATED"}], available=True)
    assert got["status"] == SE.HISTORY_AVAILABLE_NO_MOVEMENT
    assert got["revisions"] == 1


def test_an_unreadable_history_is_still_unavailable():
    got = SE._thesis_history([], available=False)
    assert got["status"] == SE.HISTORY_UNAVAILABLE


# --- against the live corpus ------------------------------------------------

@pytest.mark.skipif(not DOSSIERS.exists(), reason="no published dossiers")
def test_live_revision_lists_never_produce_a_movement_claim_from_nothing():
    """Every published dossier's own revision list, back through the producer.

    An invariant over live inputs rather than a snapshot of live outputs: the
    counts in the corpus move with every cycle, and a test that pinned them
    would go red on a night nobody touched the code. What is asserted is the
    implication — an empty list can only produce NO_THESIS, and a non-empty
    one can never produce it — which holds for any corpus.
    """
    seen_empty = seen_full = False
    for path in sorted(DOSSIERS.glob("*.json")):
        payload = json.loads(path.read_text())
        if not isinstance(payload.get("thesis_history"), dict):
            continue
        revisions = list(payload.get("thesis_revisions") or ())
        status = SE._thesis_history(revisions, available=True)["status"]
        if revisions:
            seen_full = True
            assert status != SE.HISTORY_AVAILABLE_NO_THESIS
        else:
            seen_empty = True
            assert status == SE.HISTORY_AVAILABLE_NO_THESIS
    # Both branches must actually have been exercised, or this test passed by
    # iterating over nothing.
    assert seen_empty and seen_full


@pytest.mark.skipif(not DOSSIERS.exists(), reason="no published dossiers")
def test_every_live_thesis_standing_is_one_this_wall_knows():
    seen = set()
    for path in sorted(DOSSIERS.glob("*.json")):
        payload = json.loads(path.read_text())
        for row in (payload.get("economic_theses") or ()):
            seen.add(str(row.get("standing") or ""))
    for standing in seen:
        assert SW.ceiling(standing) in SW.CEILINGS
