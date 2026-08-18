"""The ladder's weakest rung may not be rendered as its strongest claim.

MEASURED across Batch A, on the deployed product:

    Meta  "contested most directly by S&P, Automation absorbing the task
           itself and 37signals LLC"
    Exxon "contested most directly by Substitute materials at the customer's
           plant, Automation absorbing the task itself and Agnico Eagle
           Mines Limited"

37signals is a project-management tool; Agnico Eagle is a gold miner. Both
arrived as STRUCTURAL_PEER — rung 9, whose own definition is "same business
model; not a stated rival". It is the honest bottom of the ladder, reached
when nothing better was found, and the opening paragraph was presenting it as
the company's most direct competition.
"""
from __future__ import annotations

import dataclasses

from intent_engine.executive.strategic_read import _position


@dataclasses.dataclass(frozen=True)
class _Row:
    name: str
    rung: str


@dataclasses.dataclass(frozen=True)
class _Peer:
    name: str
    basis: str = "SAME_SECTOR_DIFFERENT_MODEL"


@dataclasses.dataclass(frozen=True)
class _Profile:
    operating_leverage: str = "HIGH: delivery cost rises slowly."
    strategic_competitors: tuple = ()


def test_a_structural_peer_is_not_a_direct_contest():
    sentence = _position("Exxon Mobil Corporation", _Profile(), None, (
        _Row("Substitute materials at the customer's plant",
             "CONTESTED_CATEGORY"),
        _Row("Agnico Eagle Mines Limited", "STRUCTURAL_PEER"),
    ))
    assert "Agnico Eagle" not in sentence, sentence
    assert "Substitute materials" in sentence


def test_an_attributed_rung_still_earns_the_strong_sentence():
    sentence = _position("NVIDIA Corporation", _Profile(), None, (
        _Row("Huawei Technologies Co", "NAMED_BY_SUBJECT"),
    ))
    assert "contested most directly by" in sentence
    assert "Huawei" in sentence


def test_only_structural_peers_falls_through_to_the_hedge():
    """With nothing but rung 9, the page must not claim a direct contest."""
    sentence = _position("Meta Platforms, Inc.",
                         _Profile(strategic_competitors=(
                             _Peer("37signals LLC"),)), None,
                         (_Row("37signals LLC", "STRUCTURAL_PEER"),))
    assert "contested most directly by" not in sentence, sentence
    assert "same sector" in sentence


def test_a_rival_with_no_rung_attribute_is_kept():
    """Defensive: an object without `rung` must not be silently dropped."""
    sentence = _position("Testco", _Profile(), None,
                         (_Row("Realrival Inc.", "NAMED_BY_SUBJECT"),))
    assert "Realrival" in sentence
