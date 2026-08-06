"""A run that reaches no hypothesis still owes the reader something.

WHERE THIS CAME FROM. Gating `tool_to_system_of_record` on a causal mechanism
(see `test_system_of_record_needs_a_mechanism`) correctly stopped it firing on
Brightledger — an eleven-person tool that reconciles payouts AGAINST an
accounting ledger, i.e. one whose whole product depends on the record living
somewhere else. It is the textbook negative case and the gate is right about
it.

What the gate exposed is that four founder-facing surfaces were being carried
entirely by whichever reading happened to fire, and had no behaviour at all
without one. Brightledger publishes four dated findings and fell to a
two-screen deck; Linear's follow-up answer became a dead end. Both had been
passing on a sentence that should never have been there, which is the same
shape as the defect being fixed one layer down.

The rule these tests hold: a bounded run says less, not nothing. Everything
asserted here is built from evidence the run actually retrieved — no screen is
padded, and a company with nothing to show still gets nothing.
"""
from __future__ import annotations

import pytest

from intent_engine.product_eval.harness import _compose
from intent_engine.strategic_intelligence.brief import build_brief
from intent_engine.strategic_intelligence.slides import (
    build_slides, deck_is_presentable, meaningful_slide_count,
)

BOUNDED = "brightledger"


@pytest.fixture(scope="module")
def report():
    _, _, result = _compose(BOUNDED)
    return result.get("strategic_report") or {}


@pytest.fixture(scope="module")
def deck(report):
    return build_slides(report)


@pytest.fixture(scope="module")
def brief(report):
    return build_brief(report, as_of="2026-08-06")


def test_the_premise_this_file_rests_on(report):
    """If a hypothesis starts firing here again, these tests stop measuring
    the bounded path and the failure would be silent."""
    assert not report.get("hypotheses"), \
        "brightledger is the no-hypothesis fixture; it now has one"
    assert report.get("shifts"), "and it must still have findings to show"


# --- the four surfaces that had no behaviour without a hypothesis ------------

def test_the_run_shows_what_it_found(deck):
    """The findings were computed and then dropped.

    A concrete development is what routes a company to the founder deck rather
    than the fallback one — and the fallback builds a "what changed" screen
    from these while the founder deck had nowhere to put them. Having MORE
    evidence produced a WORSE deck.
    """
    found = [s for s in deck if s["kind"] == "findings"]
    assert found, [s["kind"] for s in deck]
    text = " ".join(b["text"] for b in found[0]["bullets"])
    assert "Brightledger" in text
    assert found[0]["bullets"], "a findings screen with no findings is a heading"


def test_the_reader_is_left_something_to_check(deck):
    """Every question this layer builds comes FROM a hypothesis, so a bounded
    run offered nothing to investigate. The replacement names something the
    run actually retrieved."""
    watch = [s for s in deck if s["kind"] == "monitor"]
    assert watch, [s["kind"] for s in deck]
    text = " ".join(b["text"] for b in watch[0]["bullets"])
    assert "Confirm with an independent or customer source" in text
    assert "Brightledger" in text


def test_the_bounded_position_is_stated_not_dropped(deck):
    """`decision_of` already composed "no decision is put forward, because X".
    Both the deck and the brief threw it away, so the reader was told nothing
    rather than told that nothing can be decided yet."""
    bounded = [s for s in deck if s["kind"] == "investigation"]
    assert bounded, [s["kind"] for s in deck]
    text = " ".join(b["text"] for b in bounded[0]["bullets"])
    assert "not enough to read a strategy from" in text


def test_the_brief_carries_a_counterpoint_that_is_not_its_limitation(brief):
    """"A brief with no counterpoint is advocacy" is this module's own rule,
    and every source of one was hypothesis-derived.

    The bounded counter must be a DIFFERENT fact from the limitation — taking
    the same sentence twice would put one line under two headings, which is
    the defect this codebase fixes elsewhere rather than introduces here.
    """
    assert brief.counterpoint.strip(), "a bounded brief still argues with itself"
    assert brief.limitation.strip()
    assert brief.counterpoint.strip() != brief.limitation.strip()


def test_a_vague_follow_up_is_not_a_dead_end(report):
    """"I don't yet hold a hypothesis that matches that question." was the
    whole reply. A reader cannot know what this run holds, so they cannot ask
    a better question."""
    from intent_engine.strategic_intelligence.conversation import (
        answer_strategic,
    )
    answer = answer_strategic("hm", report)
    direct = (answer.get("answer") or {}).get("direct_answer", "")
    assert "can be asked about" in direct
    assert "Brightledger" in direct


# --- and the deck is still allowed to be short -------------------------------

def test_the_bounded_deck_is_presentable_without_being_padded(deck):
    assert deck_is_presentable(deck)
    for slide in deck:
        assert slide["bullets"], f"empty screen rendered: {slide['id']}"
        for bullet in slide["bullets"]:
            assert bullet["text"].strip()


def test_no_screen_repeats_another(deck):
    """The bounded position, the limitation and the counterpoint are three
    different sentences or they are one sentence shown three times."""
    seen = {}
    for slide in deck:
        for bullet in slide["bullets"]:
            key = bullet["text"].strip().lower().rstrip(".")
            assert key not in seen, \
                f"{slide['id']} repeats {seen.get(key)}: {bullet['text'][:60]}"
            seen[key] = slide["id"]


def test_a_run_with_nothing_found_is_still_not_presentable():
    """THE GUARD ON EVERYTHING ABOVE.

    Each fix here is conditioned on the run having found something, so none of
    them can dress an empty analysis up as a finished one. A report with no
    findings and no hypothesis must still fail to reach a deck — otherwise
    "say less, not nothing" has quietly become "always say something".
    """
    empty = {"company_name": "Nothing Co", "hypotheses": [], "shifts": [],
             "observations": [], "timeline": [], "evidence_gaps": [],
             "quality_findings": [], "surprises": [], "vulnerabilities": [],
             "blind_spots": [], "questions": [],
             "source_class_coverage": {}}
    assert not deck_is_presentable(build_slides(empty))
    assert meaningful_slide_count(build_slides(empty)) < 4
