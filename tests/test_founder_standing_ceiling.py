"""This side may say less than the producer meant, and never more.

Two live defects are pinned here.

`test_the_wall_moves_with_the_standing` covers a certainty wall whose
standing-based exemption tested for OBSERVED and MEASURED — values from the
causal-hop vocabulary, which the plan's standing field never holds. The branch
was unreachable for every value production can put there, so one fixed word
list governed a tested reading and an abandoned one alike.

`test_an_abandoned_reading_is_not_a_supported_answer` covers `supported=True`
hard-coded into the current-state plan, which turned the mere presence of a
thesis row into support for its claim — including for readings the producer
had already refuted.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from intent_engine.external_intel import ceo_answers as CA
from intent_engine.external_intel import decision_impact as di
from intent_engine.external_intel import standing_ceiling as SC
from intent_engine.external_intel import strategic_contract as SCT

DOSSIERS = pathlib.Path(
    "/Users/prathamsharma/intent-engine-market/reports/market/strategic")


class Intel:
    """The consumer shape, built to the fields the planner actually reads."""

    def __init__(self, theses=(), revisions=(), history=None, limitations=()):
        self.economic_theses = tuple(theses)
        self.thesis_revisions = tuple(revisions)
        self.thesis_history = history
        self.limitations = tuple(limitations)
        self.source_constraints = ()


def thesis(standing="PROPOSED", **kw):
    row = {
        "thesis_id": "th_1", "claim": "input costs are rising",
        "standing": standing, "question": "are input costs rising?",
        "mechanism": "tariffs raise landed cost",
        "falsifier": "landed cost does not move within 90 days",
        "alternatives": ["the exposure was hedged"],
        "evidence_ids": ["ev1"], "macro_conditions": ["tariff"],
        "exposures": ["imports"], "decision_implication": "watch",
    }
    row.update(kw)
    return row


# --- the ceiling moves ------------------------------------------------------

def test_the_wall_moves_with_the_standing():
    """THE LADDER ITSELF HAS TO BE GRADED, not merely non-constant.

    An earlier version of this test asserted only that the hit counts were
    non-decreasing and not all equal. Break proof B — which collapses
    `banned_words` to one fixed list — passed it, because REFUTED returns
    through a separate early branch and supplied the variation on its own. The
    graded ladder could be entirely dead and the test stayed green.

    So the three LIVE standings are compared against each other, and REFUTED
    is checked separately. That is what "the ceiling narrows as the record
    weakens" actually claims.
    """
    # ONE PHRASE FROM EACH RUNG, or the test cannot see the rungs: a claim of
    # certainty (forbidden everywhere), a claim that the falsifier was tested
    # (lost at BOUNDED), a claim that evidence confirms it (lost at LEADING),
    # and a claim about the world at all (lost at NONE).
    sentence = ("The result is guaranteed, it withstood the test, it is "
                "established, and it indicates growth.")
    hits = {st: CA.violates_certainty_wall(
        sentence, CA.plan("What is happening?",
                          Intel(theses=[thesis(st)])))
        for st in ("TESTED", "SUPPORTED", "PROPOSED", "REFUTED")}
    live = [len(hits[st]) for st in ("TESTED", "SUPPORTED", "PROPOSED")]
    assert live == sorted(live)
    assert len(set(live)) == 3, hits
    assert len(hits["REFUTED"]) >= len(hits["PROPOSED"])


def test_the_hop_vocabulary_is_not_a_standing():
    """OBSERVED is a hop standing. It must not act as a thesis standing, which
    is what the removed exemption did."""
    assert SC.from_standing("OBSERVED") == SC.ASSERT_NONE
    assert not SC.may_assert(SC.from_standing("OBSERVED"))


@pytest.mark.parametrize("standing,ceiling", [
    ("PROPOSED", SC.ASSERT_LEADING),
    ("SUPPORTED", SC.ASSERT_BOUNDED),
    ("TESTED", SC.ASSERT_TESTED),
    ("WEAKENED", SC.ASSERT_LEADING),
    ("REFUTED", SC.ASSERT_NEGATIVE),
    ("SUPERSEDED", SC.ASSERT_NEGATIVE),
])
def test_the_mirror_matches_the_producer(standing, ceiling):
    """Pinned, because a mirror nobody compares is a guess with a comment."""
    assert SC.from_standing(standing) == ceiling


def test_an_unknown_standing_falls_to_silence_not_to_confidence():
    assert SC.from_standing("PRETTY_SURE") == SC.ASSERT_NONE
    assert SC.from_standing("") == SC.ASSERT_NONE


def test_the_stricter_ceiling_always_wins():
    assert SC.stricter_of(SC.ASSERT_TESTED, SC.ASSERT_LEADING) == \
        SC.ASSERT_LEADING
    assert SC.stricter_of(SC.ASSERT_TESTED, SC.ASSERT_NEGATIVE) == \
        SC.ASSERT_NEGATIVE
    assert SC.stricter_of() == SC.ASSERT_NONE


def test_a_transported_ceiling_cannot_loosen_a_local_one():
    """A producer claiming more than this side's own reading is not obeyed."""
    row = thesis("PROPOSED")
    row["ceiling"] = SC.ASSERT_TESTED
    assert SC.ceiling_for(row) == SC.ASSERT_LEADING


def test_an_unrecognised_transported_ceiling_is_not_mapped_to_the_nearest():
    row = thesis("TESTED")
    row["ceiling"] = "ASSERT_PRETTY_SURE"
    assert SC.ceiling_for(row) == SC.ASSERT_NONE


# --- an abandoned reading -----------------------------------------------------

@pytest.mark.parametrize("standing", ["REFUTED", "SUPERSEDED"])
def test_an_abandoned_reading_is_not_a_supported_answer(standing):
    """`supported` was hard-coded True: the presence of a thesis row was read
    as support for its claim."""
    got = CA.plan("What is happening?", Intel(theses=[thesis(standing)]))
    assert got.supported is False
    assert got.ceiling == SC.ASSERT_NEGATIVE


def test_an_abandoned_reading_is_reported_rather_than_hidden():
    """The executive who was told this last month is owed the correction."""
    got = CA.plan("What is happening?", Intel(theses=[thesis("REFUTED")]))
    assert "no longer holds" in got.direct_answer
    assert "input costs are rising" in got.direct_answer


def test_a_live_reading_is_still_supported():
    for standing in ("PROPOSED", "SUPPORTED", "TESTED", "WEAKENED"):
        got = CA.plan("What is happening?", Intel(theses=[thesis(standing)]))
        assert got.supported is True, standing


# --- the thesis hop is translated, not copied -------------------------------

def test_the_thesis_hop_speaks_the_hop_vocabulary():
    got = CA.plan("Why?", Intel(theses=[thesis("TESTED")]))
    hop = next(h for h in got.hops if h.name == "THESIS")
    assert hop.standing in (CA.OBSERVED, CA.SUPPORTED, CA.HYPOTHESIZED,
                            CA.CONTRADICTED, CA.MISSING)


def test_an_abandoned_thesis_hop_is_contradicted_not_missing():
    """The hop is known, and what is known is that it failed. That is not the
    same as nothing being known."""
    got = CA.plan("Why?", Intel(theses=[thesis("REFUTED")]))
    hop = next(h for h in got.hops if h.name == "THESIS")
    assert hop.standing == CA.CONTRADICTED


def test_a_claimless_thesis_hop_is_missing():
    got = CA.plan("Why?", Intel(theses=[thesis("PROPOSED", claim="")]))
    hop = next(h for h in got.hops if h.name == "THESIS")
    assert hop.standing == CA.MISSING


# --- the fourth history state -------------------------------------------------

def test_zero_revisions_is_not_a_settled_view():
    """22 of 25 published dossiers said "nothing has changed this view yet"
    about companies for which no view had ever been formed."""
    intel = Intel(history={"status": di.HISTORY_AVAILABLE_NO_MOVEMENT,
                           "revisions": 0}, revisions=())
    assert di.mind_change_state(intel) == di.HISTORY_AVAILABLE_NO_THESIS


def test_a_real_no_movement_still_reads_as_no_movement():
    intel = Intel(history={"status": di.HISTORY_AVAILABLE_NO_MOVEMENT,
                           "revisions": 1},
                  revisions=({"revision_id": "r1", "transition": "CREATED"},))
    assert di.mind_change_state(intel) == di.HISTORY_AVAILABLE_NO_MOVEMENT


def test_the_four_history_states_answer_differently():
    answers = set()
    forbids = set()
    for state, revisions in (
            (di.HISTORY_UNAVAILABLE, ()),
            (di.HISTORY_AVAILABLE_NO_THESIS, ()),
            (di.HISTORY_AVAILABLE_NO_MOVEMENT,
             ({"revision_id": "r1", "transition": "CREATED"},)),
            (di.HISTORY_AVAILABLE_MOVED,
             ({"revision_id": "r2", "transition": "STRENGTHENED",
               "changed_at": "2026-08-01", "knowledge_effect_ids": ["k1"],
               "triggering_evidence": ["e1"], "previous_standing": "PROPOSED",
               "new_standing": "SUPPORTED", "reason": "a filing"},)),):
        intel = Intel(history={"status": state}, revisions=revisions)
        plan = CA.plan("What changed your mind?", intel)
        answers.add(plan.direct_answer)
        forbids.add(plan.must_not_conclude)
    assert len(answers) == 4
    assert len(forbids) == 4


def test_an_unknown_history_status_is_unavailable_not_settled():
    """A producer this side cannot read is not a producer reporting calm."""
    intel = Intel(history={"status": "HISTORY_PROBABLY_FINE"})
    assert di.mind_change_state(intel) == di.HISTORY_UNAVAILABLE


def test_a_history_state_asserts_nothing_about_the_world():
    """The state is a fact about the record. A renderer handed it as a
    standing would say "it did not move" where the record says "we cannot
    see"."""
    for state in (di.HISTORY_UNAVAILABLE, di.HISTORY_AVAILABLE_NO_THESIS,
                  di.HISTORY_AVAILABLE_NO_MOVEMENT):
        intel = Intel(history={"status": state})
        plan = CA.plan("What changed your mind?", intel)
        assert plan.ceiling == SC.ASSERT_NONE


# --- three representations --------------------------------------------------

def test_the_consumer_re_decides_the_ceiling_after_it_downgrades():
    """A row downgraded on this side would otherwise keep a ceiling computed
    against the standing that was sent."""
    payload = {"economic_theses": [
        {"thesis_id": "t", "claim": "c", "standing": "TESTED",
         "alternatives": [], "ceiling": SC.ASSERT_TESTED}]}
    rows = SCT._economic_theses(payload)
    assert rows[0]["standing"] == "PROPOSED"
    assert rows[0]["ceiling"] == SC.ASSERT_LEADING


def test_a_row_without_a_transported_ceiling_still_gets_one():
    """Older producers send no ceiling, and the answer still has to be
    decided rather than left open."""
    payload = {"economic_theses": [
        {"thesis_id": "t", "claim": "c", "standing": "SUPPORTED",
         "alternatives": ["hedged"]}]}
    rows = SCT._economic_theses(payload)
    assert rows[0]["ceiling"] == SC.ASSERT_BOUNDED


@pytest.mark.parametrize("row", [
    {},
    {"standing": None},
    {"standing": "PROPOSED", "ceiling": None},
    {"standing": "PROPOSED", "ceiling": ""},
])
def test_every_empty_shape_reaches_a_decided_ceiling(row):
    assert SC.ceiling_for(row) in SC.CEILINGS


def test_a_non_dict_row_is_silence_rather_than_a_crash():
    assert SC.ceiling_for("PROPOSED") == SC.ASSERT_NONE
    assert SC.ceiling_for(None) == SC.ASSERT_NONE


# --- against the live corpus ------------------------------------------------

@pytest.mark.skipif(not DOSSIERS.exists(), reason="no published dossiers")
def test_every_live_dossier_reaches_a_decided_ceiling():
    """Real payloads, through the real consumer, into the real planner."""
    seen = set()
    for path in sorted(DOSSIERS.glob("*.json")):
        payload = json.loads(path.read_text())
        if not isinstance(payload.get("thesis_history"), dict):
            continue
        intel = SCT.consume(payload)
        for row in (intel.economic_theses or ()):
            assert row["ceiling"] in SC.CEILINGS
            seen.add(row["ceiling"])
        plan = CA.plan("What changed your mind?", intel)
        assert plan.ceiling == SC.ASSERT_NONE
    assert seen, "no live thesis row was exercised"


@pytest.mark.skipif(not DOSSIERS.exists(), reason="no published dossiers")
def test_no_live_dossier_claims_a_settled_view_it_never_formed():
    """The defect as it stood in the corpus, caught on the consumer side
    without waiting for a republish."""
    for path in sorted(DOSSIERS.glob("*.json")):
        payload = json.loads(path.read_text())
        if not isinstance(payload.get("thesis_history"), dict):
            continue
        intel = SCT.consume(payload)
        state = di.mind_change_state(intel)
        if not list(getattr(intel, "thesis_revisions", ()) or ()):
            assert state != di.HISTORY_AVAILABLE_NO_MOVEMENT, path.name
