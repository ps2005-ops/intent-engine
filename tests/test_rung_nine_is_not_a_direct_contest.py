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


# ===========================================================================
# the seam that made the first attempt inert
# ===========================================================================
def test_the_read_carries_the_rung_from_the_ladder():
    """PROVENANCE MUST SURVIVE THE PROJECTION.

    The first version of this repair filtered on `getattr(c, "rung", "")` and
    shipped completely inert: `_position` receives CompetitorRead, the rung
    lived only on Rival, and the getattr default silently kept every row. The
    deployed page was unchanged and the tests were green, because the tests
    constructed rows that had the field.

    So assert the FIELD EXISTS on the object the renderer actually sees.
    """
    from intent_engine.executive.strategic_read import CompetitorRead
    assert "rung" in CompetitorRead.__dataclass_fields__


def test_every_ladder_row_reaching_the_read_keeps_its_rung():
    """The ladder -> read projection must not drop provenance."""
    import inspect

    from intent_engine.executive import strategic_read as SR
    source = inspect.getsource(SR._from_ground)
    assert "rung=rival.rung" in source, (
        "_from_ground builds CompetitorRead without carrying the rung; the "
        "rung-9 exclusion in _position becomes a no-op")
