"""Eight of the ten questions this programme asks had no route.

MEASURED across all eight Batch-A companies captured on one SHA (fdbfe77).
Of the ten board questions the programme itself asks of every company, only
TWO reached `intent_of`: "What's the biggest risk?" and "Who's the real
competitor?". The other eight fell to the strategic catch-all, which answers
from the matched pattern's own text.

That one gap produced everything we had been treating as three defects:

  Caterpillar / NVIDIA   9 of 10 answers identical   (same pattern)
  Exxon      / NVIDIA    8 of 10                     (same pattern)
  Caterpillar/ Exxon     8 of 10                     (same pattern)
  Amazon     / Meta      8 of 10                     (same pattern)
  Eli Lilly  / Walmart   7 of 10                     (both REFUSED)

and the refusal is the sharpest of them: Lilly and Walmart answered eight
questions with "I am not going to give you a strategic read on this company,
because the public evidence does not support one — the same reason the
summary above withheld it", while their OWN introductions rendered "Our read:
Bounded" and a real central question. The trailing clause is the tell; it
cites a refusal no longer being made.

The two questions that DID route are the two that did not collapse:
"Who's the real competitor?" was identical on 0 of 28 pairs.

Two of the misses were a single character and a single word. The falsifier
marker required "proveS this wrong" and the question asks "What WOULD prove
this wrong?". The monitoring marker knew "monitor next" and not "measure
next".
"""
import pytest

from intent_engine.founder_brief.qa import INTENT_ROUTES, intent_of
from intent_engine.pre100.capture import BOARD_QUESTIONS


@pytest.mark.parametrize("question", BOARD_QUESTIONS)
def test_every_board_question_routes(question):
    """The programme may not ask a question its own router cannot hear."""
    assert intent_of(question), (
        f"{question!r} reaches no intent, so it falls to the catch-all and "
        f"is answered from the matched pattern's text — which is identical "
        f"for every company on that pattern")


def test_the_two_that_used_to_route_still_do():
    assert intent_of("What's the biggest risk?") == "biggest_risk"
    assert intent_of("Who's the real competitor?") == "competitor"


def test_the_falsifier_marker_matches_the_question_actually_asked():
    """One character. The marker required "proves"; the board asks "would
    prove"."""
    assert intent_of("What would prove this wrong?") == "falsifier"
    assert intent_of("What proves this wrong?") == "falsifier"


def test_the_monitoring_marker_knows_measure_as_well_as_monitor():
    assert intent_of("What should we measure next?") == "monitoring"
    assert intent_of("What should we monitor next?") == "monitoring"


def test_the_specific_intent_still_beats_the_catch_all():
    """"What should we monitor next" contains a recommendation marker AND a
    monitoring one. Ordered routing, first match wins, specific listed
    first — a property that predates this repair and must survive it."""
    assert intent_of("What should we monitor next?") == "monitoring"


def test_management_and_the_board_both_ask_for_the_recommendation():
    for question in ("What should management do?",
                     "What would you tell the board?",
                     "What should we do?"):
        assert intent_of(question) == "recommendation", question


def test_no_two_intents_declare_the_same_field():
    """Two intents on one field answer identically by construction, which is
    the collapse this repair exists to remove."""
    fields = [field for _n, _m, field, _a in INTENT_ROUTES]
    duplicated = {f for f in fields if fields.count(f) > 1}
    assert not duplicated, duplicated


def test_every_intent_declares_markers_and_an_absent_sentence():
    for name, markers, field, absent in INTENT_ROUTES:
        assert markers, f"{name} declares no markers"
        assert field, f"{name} routes to no field"
        assert absent and absent.endswith("."), (
            f"{name} has no honest sentence for when the field is empty")


def test_a_marker_is_not_a_bare_common_word():
    """"next" matched inside "What should we measure NEXT?" — a bare common
    word as a marker matches the QUESTION rather than the intent."""
    bare = {"next", "back", "risk", "do", "now", "board", "market"}
    for name, markers, _f, _a in INTENT_ROUTES:
        for marker in markers:
            assert marker.lower() not in bare, (
                f"{name} routes on the bare word {marker!r}")
