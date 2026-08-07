"""A strategic reading may not fire on attributes the whole industry shares.

Twice now the same defect has been found one pattern at a time:

    buyer_concentration_exposure  fired on the word "defense" inside
                                  "defense-in-depth", and handed HubSpot and
                                  Snowflake the same conclusion.
    tool_to_system_of_record      fired on multi_product + developer_surface —
                                  several products and an API — and handed
                                  Palantir, HubSpot and Snowflake the same
                                  second sentence, name-substituted.

Both were fixed by requiring a CAUSAL MECHANISM: evidence of the thing the
reading actually asserts, not vocabulary that correlates with it. The gate
(`required_any_signals`) has been general infrastructure the whole time —
declared in `records.py`, enforced in `reasoning.py`.

This file exists so the third one is caught by a test instead of by three live
company runs. It does two things:

1. Fails when a NEW pattern ships with no applicability gate at all.
2. Records the patterns that predate the rule, and fails if that list GROWS.

The debt list is deliberately visible rather than a blanket exemption. Every
entry is a pattern that can still reach a reader on a generic signal count.
"""
from __future__ import annotations

import pytest

from intent_engine.strategic_intelligence.patterns import PATTERN_LIBRARY

PATTERNS = {p.pattern_id: p for p in PATTERN_LIBRARY}

#: Patterns that predate the causal-mechanism rule and have no applicability
#: gate. Each can still qualify on a generic signal count, which is the exact
#: shape that produced two live defects.
#:
#: THIS LIST MAY ONLY SHRINK. Adding to it means shipping a new reading that
#: can fire on attributes; fixing one means giving it either
#: `required_signals` (the subject the reading is about) or
#: `required_any_signals` (the mechanisms, any one of which makes it true).
_UNGATED_DEBT = frozenset({
    "capacity_ahead_of_demand",
    "differentiator_commoditization",
    "ecosystem_control_vs_openness",
    "human_to_agent_workflow",
    "single_product_to_ecosystem",
    "smb_wedge_to_enterprise",
})

#: The debt as it stood when the rule was written, and a closed historical
#: fact rather than a setting.
#:
#: WHY A SECOND LIST. "This list may only shrink" was enforced by a cap on its
#: length, and a break proof showed the cap does not hold: widening `<= 8` to
#: `<= 99` is one character, leaves every other assertion green, and re-opens
#: the exemption for anything. Size was never the property worth pinning —
#: MEMBERSHIP is. Nothing may join the debt list that was not already on it,
#: so a newly added pattern cannot be exempted at all, whatever the cap says.
#:
#: Editing this set is rewriting what was true on 2026-08-06, which is a
#: visible act in review rather than a number nudged upward.
_DEBT_WHEN_THE_RULE_WAS_WRITTEN = frozenset({
    "capacity_ahead_of_demand",
    "differentiator_commoditization",
    "ecosystem_control_vs_openness",
    "human_to_agent_workflow",
    "portfolio_run_as_one",
    "product_to_platform",
    "single_product_to_ecosystem",
    "single_to_multi_segment",
    "smb_wedge_to_enterprise",
})


def _gated(pattern):
    return bool(pattern.required_signals or pattern.required_any_signals)


def test_the_debt_list_names_only_real_patterns():
    """A stale entry would silently exempt nothing and hide a real gap."""
    unknown = _UNGATED_DEBT - set(PATTERNS)
    assert not unknown, f"debt list names patterns that no longer exist: {unknown}"


def test_no_new_pattern_ships_without_an_applicability_gate():
    """The rule going forward.

    If this fails for a pattern you just added, the fix is not to add it to
    `_UNGATED_DEBT`. It is to answer: what evidence would show this reading is
    actually true of this company, rather than true of everyone in the
    industry? That answer is `required_any_signals`.
    """
    ungated = {pid for pid, p in PATTERNS.items() if not _gated(p)}
    new = ungated - _UNGATED_DEBT
    assert not new, (
        f"pattern(s) {sorted(new)} can fire on a generic signal count with no "
        "causal mechanism required — see this file's docstring")


def test_the_debt_list_does_not_grow():
    """Records progress, and fails if someone 'fixes' a failure by widening
    the exemption instead of gating the pattern."""
    ungated = {pid for pid, p in PATTERNS.items() if not _gated(p)}
    assert _UNGATED_DEBT >= ungated, \
        "an ungated pattern is missing from the debt list"
    # Membership, not size. See `_DEBT_WHEN_THE_RULE_WAS_WRITTEN` for why the
    # length cap this replaced could be widened without failing anything.
    joined = _UNGATED_DEBT - _DEBT_WHEN_THE_RULE_WAS_WRITTEN
    assert not joined, (
        f"{sorted(joined)} was added to the ungated-pattern debt list. The "
        "list records what predates the rule; a pattern that did not predate "
        "it cannot be exempted from it — gate the pattern instead")


def test_every_listed_debt_is_still_genuinely_ungated():
    """A repaired pattern must LEAVE the list, not sit on it as a spare
    exemption. Together with the subset check above this pins the list to
    exactly the ungated set — it cannot grow, and it cannot keep a pattern it
    no longer describes."""
    stale = {pid for pid in _UNGATED_DEBT if _gated(PATTERNS[pid])}
    assert not stale, (
        f"{sorted(stale)} now has an applicability gate and must be removed "
        "from the debt list")


#: A repaired pattern leaves the debt list permanently. The gate each one
#: needs differs, because what makes a reading true differs: two are true when
#: any ONE of several mechanisms is evidenced, and one is true only when its
#: SUBJECT is named. Both are recorded so neither can quietly become a
#: threshold again.
_REPAIRED = {
    # found live: fired on the word "defense" inside "defense-in-depth"
    "buyer_concentration_exposure": "required_any_signals",
    # found live: fired on multi_product + developer_surface, and handed
    # Palantir, HubSpot and Snowflake the same name-substituted sentence
    "tool_to_system_of_record": "required_any_signals",
    # found by measurement rather than by a live run: `regulated_buyer +
    # pricing_gated` qualified it without naming a second buyer at all, which
    # its own `when_it_does_not_apply` forbids
    "single_to_multi_segment": "required_signals",
    # measured worst of the seven remaining: fired on ordinary
    # multi-product-suite copy, reached HubSpot, Microsoft and Stripe
    # live, and declared no disconfirmers at all
    "portfolio_run_as_one": "required_any_signals",
    # found live on Shopify: `when_it_applies` required "third parties
    # increasingly build on it" and no signal measured that, so the gate was
    # two of four attributes — one of which, `product_breadth`, the pattern
    # itself lists under `when_it_does_not_apply`
    "product_to_platform": "required_any_signals",
}


@pytest.mark.parametrize("pid,field", sorted(_REPAIRED.items()))
def test_a_repaired_pattern_stays_repaired(pid, field):
    """Each was paid for once. None regresses silently."""
    assert pid not in _UNGATED_DEBT
    assert getattr(PATTERNS[pid], field), f"{pid} lost its {field} gate"


@pytest.mark.parametrize("pid", sorted(_REPAIRED))
def test_a_repaired_pattern_keeps_its_counter_evidence(pid):
    """FOUND BY A BREAK PROOF THAT DID NOT HOLD.

    Deleting `portfolio_run_as_one`'s only disconfirmer left the whole guard
    green: the gate was pinned and the counter-evidence was not. Every pattern
    here was repaired precisely because it asserted more than it measured, and
    a reading nobody can argue with is one nobody has tested — so the
    disconfirmers are part of the repair, not decoration on it.
    """
    assert PATTERNS[pid].disconfirming_signals, (
        f"{pid} was repaired and has lost its counter-evidence; the gate "
        "alone does not make a reading arguable")


def test_a_repaired_pattern_may_not_be_returned_to_the_debt_list():
    """The exemption list is the tempting fix for a failing gate, and it is
    never the right one."""
    assert not (_UNGATED_DEBT & set(_REPAIRED)), \
        "a repaired pattern was added back to the ungated debt list"


@pytest.mark.parametrize("pid", sorted(PATTERNS))
def test_a_disconfirmer_is_never_also_required(pid):
    """A pattern cannot both require a signal and be argued with by it —
    declared that way the gate and the counter-evidence describe opposite
    readings, and one of the two is wrong."""
    p = PATTERNS[pid]
    required = set(p.required_signals) | set(p.required_any_signals)
    assert not (required & set(p.disconfirming_signals)), \
        f"{pid} both requires and is disconfirmed by the same signal"


@pytest.mark.parametrize("pid", sorted(PATTERNS))
def test_every_pattern_states_what_it_cannot_prove(pid):
    """A reading that names no limitation is asserting more than it measured.
    This one already holds for the whole library — it is pinned so it keeps
    holding."""
    assert PATTERNS[pid].limitations.strip(), f"{pid} declares no limitation"


@pytest.mark.parametrize("pid", sorted(PATTERNS))
def test_every_pattern_states_its_mechanism(pid):
    """`validate()` enforces non-empty; this additionally requires that the
    mechanism is a sentence about cause, not a restatement of the name."""
    p = PATTERNS[pid]
    assert len(p.mechanism.split()) >= 12, \
        f"{pid} mechanism is too short to describe a cause: {p.mechanism!r}"
    assert p.mechanism.strip().lower() != p.name.strip().lower()


@pytest.mark.parametrize("pid", sorted(PATTERNS))
def test_every_gated_pattern_declares_its_mechanisms_as_qualifying(pid):
    """A required signal that is not qualifying can never be observed, so the
    gate would close the pattern permanently rather than gate it."""
    p = PATTERNS[pid]
    for signal in tuple(p.required_any_signals) + tuple(p.required_signals):
        assert signal in p.qualifying_signals, \
            f"{pid} requires {signal!r}, which it never qualifies on"
