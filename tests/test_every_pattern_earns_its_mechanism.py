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
    assert len(_UNGATED_DEBT) <= 9, \
        "the ungated-pattern debt grew; gate the pattern instead"


def test_the_two_repaired_patterns_stay_repaired():
    """Both were found live, at real cost. Neither regresses silently."""
    for pid in ("buyer_concentration_exposure", "tool_to_system_of_record"):
        assert pid not in _UNGATED_DEBT
        assert PATTERNS[pid].required_any_signals, f"{pid} lost its gate"


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
