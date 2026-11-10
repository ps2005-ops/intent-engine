"""A bounded failure path, and never a competitor's mind.

The central test here is `test_a_rivals_existence_predicts_nothing`. Every
other test protects a field; that one protects the reason the module exists.
"A competitor will cut prices because it is a competitor" is the single most
common output of a competitive-intelligence layer, it is produced by code that
looks entirely reasonable — iterate the rivals, attach the obvious move — and
it is indistinguishable from a real warning at the moment somebody has to
decide.
"""
from __future__ import annotations

import pytest

from intent_engine.market import adversary_case as AC
from intent_engine.market import economic_thesis as ET


def thesis(falsifiers=True):
    mech = ET.Mechanism(
        description="tariffs raise landed cost",
        falsifier="landed cost does not move within 90 days", key="k")
    alt = ET.Mechanism(description="the exposure was hedged",
                       falsifier="the company states a hedge", key="a")
    return ET.EconomicThesis(
        subject="ACME", question="do costs rise?", claim="costs are rising",
        leading_mechanism=mech, alternatives=(alt,), as_of="2026-08-09",
        standing=ET.PROPOSED, supporting_evidence=("ev1",))


def case(**kw):
    base = dict(thesis_id="th_1", subject="ACME",
                failure_path="the supplier absorbs the tariff and the cost "
                             "never reaches us, so the capex cut we planned "
                             "was unnecessary",
                attacked_assumption="that the tariff is passed through in "
                                    "full",
                early_warning=("landed cost does not move within 90 days",),
                kill_condition="landed cost does not move within 90 days")
    base.update(kw)
    return AC.AdversaryCase(**base)


def response(**kw):
    base = dict(actor="RIVAL", action="cuts prices to hold share")
    base.update(kw)
    return AC.CounterpartyResponse(**base)


# --- the rule the module exists for -----------------------------------------

def test_a_rivals_existence_predicts_nothing():
    """The constructor that refuses, kept as a named function so the next
    person to write this path finds it instead of writing it again."""
    with pytest.raises(AC.UnevidencedResponse):
        AC.from_rival_existence("th_1", "ACME", "RIVAL")


def test_a_response_may_not_exceed_hypothesised_without_evidence():
    for standing in (AC.CAPABILITY, AC.INCENTIVE, AC.OBSERVED_ACTION):
        with pytest.raises(AC.UnevidencedResponse):
            response(standing=standing)


def test_a_hypothesised_response_needs_no_evidence_and_says_so():
    """The honest default has to be available, or the only way to record a
    thought is to dress it as an observation."""
    got = response(standing=AC.HYPOTHESIZED_RESPONSE)
    assert not got.evidenced
    assert "nothing observed" in got.reading


@pytest.mark.parametrize("standing", [AC.CAPABILITY, AC.INCENTIVE])
def test_evidence_lets_a_response_rise_but_only_that_far(standing):
    got = response(standing=standing, evidence_ids=("ev9",))
    assert got.evidenced
    assert got.standing == standing


def test_an_observed_action_must_say_when():
    """An undated action cannot be checked and cannot be aged out."""
    with pytest.raises(AC.AdversaryRejected):
        response(standing=AC.OBSERVED_ACTION, evidence_ids=("ev9",))
    got = response(standing=AC.OBSERVED_ACTION, evidence_ids=("ev9",),
                   observed_at="2026-05-01")
    assert got.standing == AC.OBSERVED_ACTION


def test_the_four_standings_read_differently():
    readings = {AC.RESPONSE_WORDS[s] for s in AC.RESPONSE_STANDINGS}
    assert len(readings) == 4


def test_capability_and_incentive_are_not_the_same_claim():
    """Means and motive are separate, and neither is an act."""
    assert AC.RESPONSE_WORDS[AC.CAPABILITY] != AC.RESPONSE_WORDS[AC.INCENTIVE]
    assert "means" in AC.RESPONSE_WORDS[AC.CAPABILITY]
    assert "reason" in AC.RESPONSE_WORDS[AC.INCENTIVE]


def test_a_response_needs_an_actor_and_an_action():
    with pytest.raises(AC.AdversaryRejected):
        response(actor="")
    with pytest.raises(AC.AdversaryRejected):
        response(action="")


# --- the case ---------------------------------------------------------------

def test_a_case_needs_a_named_assumption_to_attack():
    with pytest.raises(AC.AdversaryRejected):
        case(attacked_assumption="")


def test_a_case_needs_an_early_warning():
    """A failure nobody could see coming is not actionable, and listing it
    without one is a way of sounding careful."""
    with pytest.raises(AC.AdversaryRejected):
        case(early_warning=())


def test_a_case_needs_a_stopping_rule():
    with pytest.raises(AC.AdversaryRejected):
        case(kill_condition="")


def test_a_case_with_no_evidenced_response_is_speculative_and_says_so():
    got = case(responses=(response(),))
    assert got.standing == AC.SPECULATIVE
    assert not got.actionable


def test_one_evidenced_response_grounds_the_case():
    got = case(responses=(response(),
                          response(standing=AC.CAPABILITY,
                                   evidence_ids=("ev9",))))
    assert got.standing == AC.GROUNDED
    assert got.actionable


def test_an_observed_action_demonstrates_it():
    got = case(responses=(response(standing=AC.OBSERVED_ACTION,
                                   evidence_ids=("ev9",),
                                   observed_at="2026-05-01"),))
    assert got.standing == AC.DEMONSTRATED


def test_a_case_with_no_adversary_at_all_is_allowed():
    """Not every failure needs an opponent, and inventing one is worse than
    having none."""
    got = case(responses=())
    assert got.standing == AC.SPECULATIVE


# --- built from the thesis rather than composed -----------------------------

def test_the_early_warning_comes_from_the_thesis_falsifiers():
    """Composing a fresh list of warning signs would be writing rather than
    reading, and the two would drift."""
    subject = thesis()
    got = AC.from_thesis(subject, failure_path="the supplier absorbs it",
                         attacked_assumption="full pass-through")
    assert got.early_warning == subject.falsifiers
    assert got.kill_condition == subject.falsifiers[0]


def test_a_thesis_with_no_falsifier_is_refused_rather_than_filled_in():
    """The gap is in the thesis, and filling it here would hide that."""
    class Bare:
        thesis_id = "th_x"
        subject = "ACME"
        falsifiers = ()
        as_of = "2026-08-09"

    with pytest.raises(AC.AdversaryRejected):
        AC.from_thesis(Bare(), failure_path="x", attacked_assumption="y")


def test_the_case_inherits_the_thesis_identity():
    subject = thesis()
    got = AC.from_thesis(subject, failure_path="x", attacked_assumption="y")
    assert got.thesis_id == subject.thesis_id
    assert got.subject == subject.subject


# --- ranking ----------------------------------------------------------------

def test_the_strongest_case_is_the_best_evidenced_not_the_worst_outcome():
    """Ranking by severity puts a speculative catastrophe above an observed
    erosion, and the speculative one is the one nobody can act on."""
    catastrophe = case(
        failure_path="the market disappears entirely and the company fails",
        responses=(response(),))
    erosion = case(
        failure_path="a rival takes two points of share over a year",
        responses=(response(standing=AC.OBSERVED_ACTION,
                            evidence_ids=("ev9",), observed_at="2026-05-01"),))
    assert AC.strongest([catastrophe, erosion]) is erosion


def test_strongest_of_nothing_is_nothing_rather_than_an_empty_case():
    assert AC.strongest([]) is None


def test_the_summary_states_the_speculative_share():
    got = AC.summarise([case(responses=(response(),)),
                        case(responses=(response(standing=AC.CAPABILITY,
                                                 evidence_ids=("ev9",)),))])
    assert got["by_standing"][AC.SPECULATIVE] == 1
    assert got["by_standing"][AC.GROUNDED] == 1
    assert got["actionable"] == 1


# --- the production constructor, in three representations -------------------

def test_the_attacked_assumption_is_read_from_the_alternatives():
    """A rival reading the engine could not exclude IS an assumption the
    leading reading relies on without saying so."""
    got = AC.from_alternatives(thesis())
    assert len(got) == 1
    assert "the exposure was hedged" in got[0].attacked_assumption
    assert got[0].kill_condition == "the company states a hedge"


def test_every_live_case_is_speculative_and_says_so():
    """A press-release corpus carries no evidence of a counterparty's means
    or motive, so this is the honest output — reported, not dressed up."""
    for one in AC.from_alternatives(thesis()):
        assert one.standing == AC.SPECULATIVE
        assert not one.actionable


def test_the_constructor_reads_an_object_and_a_persisted_row_alike():
    """The cycle holds objects; the store returns the dicts it wrote. A
    getattr-only reader folds every row to empty and produces zero cases
    silently, which looks exactly like a corpus with no alternatives."""
    live = AC.from_alternatives(thesis())
    persisted = AC.from_alternatives({
        "thesis_id": "th_1", "subject": "ACME", "as_of": "2026-08-09",
        "alternatives": [{"description": "the exposure was hedged",
                          "falsifier": "the company states a hedge"}]})
    assert len(live) == len(persisted) == 1
    assert live[0].attacked_assumption == persisted[0].attacked_assumption


@pytest.mark.parametrize("payload,expected", [
    ({}, 0),
    ({"alternatives": []}, 0),
    ({"alternatives": None}, 0),
    # Alternatives are plain strings on some persisted rows. A string carries
    # no falsifier, and a case with an invented one would be worse than none.
    ({"alternatives": ["hedged"], "subject": "A", "as_of": "x"}, 0),
    ({"alternatives": [{"description": "", "falsifier": "f"}],
      "subject": "A", "as_of": "x"}, 0),
])
def test_every_empty_shape_produces_no_case_rather_than_a_blank_one(
        payload, expected):
    assert len(AC.from_alternatives(payload)) == expected


def test_the_standing_describes_the_attack_and_not_the_thesis():
    """A well-evidenced attack on a strong thesis is not a weak thesis, and
    a reader who confuses the two will act on the wrong one."""
    got = AC.summarise([case(responses=(response(),))])
    assert "not how likely the thesis is to fail" in \
        got["strongest"]["note"]
