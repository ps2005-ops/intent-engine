"""Direction is a measurement of CHANGE, not the sign of a level.

THE DEFECT, MEASURED ON THE FIRST PUBLISHED STATE
--------------------------------------------------
`build` computed `direction = UP if (value or 0) > 0 else FLAT`. A consumer
price index of 333.918 is greater than zero in every month that has ever
existed, so all five measured conditions reported UP, and a founder-facing
reasoning block read "inflation is rising at 333.918 index" whatever inflation
had actually done.

Uniformity across every condition is the tell. A real economy does not move
one way in five out of five, and when an instrument says it did, the
instrument is what to check.

The change was computable the whole time: 23 to 46 dated observations per
condition were already in the graph.
"""
from __future__ import annotations

import pytest

from intent_engine.econ import evidence as EV
from intent_engine.econ import state as ES
from intent_engine.econ import vocabulary as V


def macro(kind, value, occurred, available=None, subject="US"):
    return EV.node(node_class=V.MACRO, kind=kind, subject=subject,
                   standing=V.OBSERVED, occurred_at=occurred,
                   available_at=available or occurred,
                   publisher="a statistical agency", value=value,
                   unit="index", producer="test")


def test_direction_is_computed_against_the_previous_observation():
    state = ES.build(as_of="2026-08-27", nodes=[
        macro("inflation", 330.0, "2026-06-01"),
        macro("inflation", 333.9, "2026-07-01")])
    reading = state.reading("inflation")
    assert reading.direction == V.UP
    assert reading.value == 333.9
    assert reading.prior_value == 330.0
    assert reading.prior_as_of == "2026-06-01"


def test_a_falling_series_reports_falling_however_large_the_level():
    state = ES.build(as_of="2026-08-27", nodes=[
        macro("inflation", 333.9, "2026-06-01"),
        macro("inflation", 330.0, "2026-07-01")])
    assert state.reading("inflation").direction == V.DOWN


def test_a_large_positive_level_alone_is_not_a_rise():
    """The exact shape of the defect."""
    state = ES.build(as_of="2026-08-27",
                     nodes=[macro("inflation", 333.918, "2026-07-01")])
    reading = state.reading("inflation")
    assert reading.direction == V.NO_PRIOR, (
        "a single observation of a large positive level was reported as a "
        "rise; that is the sign of the level wearing the word 'rising'")
    assert reading.value == 333.918
    assert not reading.moved


def test_no_prior_is_not_flat():
    """The distinction this codebase keeps having to relearn."""
    unchanged = ES.build(as_of="2026-08-27", nodes=[
        macro("inflation", 333.9, "2026-06-01"),
        macro("inflation", 333.9, "2026-07-01")])
    unknown = ES.build(as_of="2026-08-27",
                       nodes=[macro("inflation", 333.9, "2026-07-01")])
    assert unchanged.reading("inflation").direction == V.FLAT
    assert unknown.reading("inflation").direction == V.NO_PRIOR
    assert not unchanged.reading("inflation").moved
    assert not unknown.reading("inflation").moved
    assert (unchanged.reading("inflation").direction
            != unknown.reading("inflation").direction)


def test_a_revision_of_the_same_period_is_not_a_movement():
    """Two prints of one period are a revision; comparing against one would
    report a statistical revision as an economic change."""
    state = ES.build(as_of="2026-08-27", nodes=[
        macro("inflation", 333.9, "2026-07-01", available="2026-08-01"),
        macro("inflation", 334.4, "2026-07-01", available="2026-08-15")])
    assert state.reading("inflation").direction == V.NO_PRIOR
    assert state.reading("inflation").value == 334.4


def test_a_claimed_direction_must_carry_the_prior_it_was_computed_from():
    with pytest.raises(V.EconError, match="sign of a level"):
        ES.ConditionReading(kind="inflation", standing=V.OBSERVED,
                            direction=V.UP, value=333.9, node_id="en-1")


def test_the_direction_travels_to_the_founder_block_without_becoming_flat():
    from intent_engine.external_intel import econ_context as EC
    from intent_engine.external_intel import pack as EP

    state = ES.build(as_of="2026-08-27",
                     nodes=[macro("inflation", 333.918, "2026-07-01")])
    context = EC.EconContext(
        available=True, as_of="2026-08-27", area="US",
        conditions={k: r.as_dict()
                    for k, r in state.conditions.items()})
    ctx = EP.build_context(economy=context, economy_exposures=("inflation",),
                           as_of="2026-08-27")
    facts = [b for b in EP.reasoning_pack(ctx)["blocks"]
             if b["context"] == EP.ECONOMY][0]["facts"]
    assert facts
    assert "no change is computable" in facts[0]
    assert "rising" not in facts[0]
    assert "broadly flat" not in facts[0]
