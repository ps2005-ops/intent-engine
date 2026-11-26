"""The economic state reader reads the economic state, not the last row.

Measured on the live market root (2026-11-25): `state_snapshot.jsonl` held an
`economic_state.v1` row followed by an `econ_shock_set.v1` row under the same
kind. Both readers took the last row; the founder side then refused it as a
contract violation and showed no economic state at all.
"""
from __future__ import annotations

from intent_engine.econ import store as EST
from intent_engine.external_intel import econ_context as EC
from intent_engine.market import econ_bridge as EB

STATE = {"contract": "economic_state.v1", "as_of": "2026-11-25", "area": "US",
         "conditions": {}, "beliefs": [], "shocks": [], "uncertainty": {},
         "provenance": {}}
SHOCKS = {"contract": "econ_shock_set.v1", "as_of": "2026-11-25",
          "shocks": []}


def _root(tmp_path, rows):
    for row in rows:
        EST.append(tmp_path, "state_snapshot", row, written_at="2026-11-25")
    return tmp_path


def _valid_state():
    from intent_engine.econ import state as ES
    return ES.build(as_of="2026-11-25", area="US", nodes=[], beliefs=[],
                    producer="market", graph_summary={}).as_dict()


def test_a_shock_set_after_the_state_does_not_hide_it(tmp_path):
    root = _root(tmp_path, [_valid_state(), SHOCKS])
    context = EC._load_uncached(root, as_of="2026-11-25")
    assert context.available, context.reason
    # The shock set PASSES the state validator (its keys are allowlisted), so
    # "available" alone cannot tell them apart: on the unrepaired reader the
    # page showed an economy with zero conditions and zero beliefs. What was
    # read must be the state itself.
    assert context.provenance.get("contract") == "economic_state.v1"


def test_the_market_side_reader_agrees(tmp_path):
    root = _root(tmp_path, [_valid_state(), SHOCKS])
    assert EB.read_state(root, as_of="2026-11-25")["contract"] == \
        "economic_state.v1"


def test_only_a_shock_set_is_still_no_state(tmp_path):
    """POSITIVE CONTROL: nothing is invented when no state was published."""
    root = _root(tmp_path, [SHOCKS])
    context = EC._load_uncached(root, as_of="2026-11-25")
    assert not context.available
    assert EB.read_state(root, as_of="2026-11-25") is None
