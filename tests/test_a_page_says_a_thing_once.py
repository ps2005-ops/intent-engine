"""One screen, one sentence, once -- for the two notices round 8 repeated."""
from __future__ import annotations

from intent_engine.founder_brief import render, xray
from intent_engine.founder_brief.layers import APPROVAL_NOTICE


def _action(title, approval=APPROVAL_NOTICE):
    return {"title": title, "intelligence": "x", "recommended_action": "y",
            "why": "z", "expected_result": "w", "approval_required": approval}


def test_the_approval_notice_appears_once_and_every_card_is_labelled():
    html = render.render_actions([_action("A"), _action("B"), _action("C")])
    assert html.count(APPROVAL_NOTICE) == 1
    assert html.count("Approval required.") == 3


def test_a_card_with_its_own_approval_text_keeps_it():
    """CONTROL: a non-standard condition is never hidden behind the label."""
    html = render.render_actions([_action("A", "Needs legal sign-off first.")])
    assert "Needs legal sign-off first." in html


def test_a_single_unchanged_line_is_not_repeated_below_the_grid():
    line = ("Nothing in the published market record changed since the "
            "previous reading.")
    assert line not in xray._beliefs_body({"what_changed": [line]})


def test_several_changes_are_still_listed():
    """CONTROL: a real list of changes is the detail the grid cannot hold."""
    body = xray._beliefs_body({"what_changed": ["evidence rows: 3 -> 5",
                                                "beliefs: 2 -> 4"]})
    assert "evidence rows: 3 -&gt; 5" in body or "evidence rows: 3 -> 5" in body
    assert "beliefs: 2" in body
