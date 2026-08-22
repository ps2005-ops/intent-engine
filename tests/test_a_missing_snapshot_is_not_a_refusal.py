"""A company the market bundle does not cover has not been refused.

MEASURED LIVE, NIKE's Q&A on 16bc5af. Asked "What should management do?",
a company that composed eleven documents across five families and reached
FULL_ANALYSIS answered:

    "Do not act on this reading. Re-run once the market engine publishes a
     snapshot this side will read."

`_standing_of` read `availability not in (AVAILABLE, STALE) -> REFUSED`, and
the market bundle carries snapshots for 26 companies out of the 50 in the
gauntlet. So for 24 of them the WHOLE reading was refused on the strength of
a separate bundle's coverage, and the reader was told not to act on their own
company's analysis.

REFUSED is for a snapshot that EXISTS and cannot be read -- which is what
that sentence describes. Absence is not refusal.
"""
import dataclasses

import pytest

from intent_engine.executive.decision_synthesis import (
    BOUNDED, REFUSED, UNMEASURABLE, _standing_of,
)


class _Dossier:
    """The shape `_standing_of` reads: counts live under market_block.blocks."""

    def __init__(self, market):
        self.market_block = market


def _dossier(block, *, evidence=3, beliefs=2):
    market = dict(block)
    market["blocks"] = {
        "evidence": {"state": "AVAILABLE", "count": evidence},
        "beliefs": {"state": "AVAILABLE", "count": beliefs},
    }
    return _Dossier(market)


def test_no_snapshot_published_is_not_a_refusal():
    """THE DEFECT. NIKE's shape: real evidence, no market coverage."""
    standing = _standing_of(_dossier({"availability": "UNAVAILABLE"}))
    assert standing != REFUSED, standing


def test_a_degraded_block_is_not_a_refusal_either():
    assert _standing_of(_dossier({"availability": "DEGRADED"})) != REFUSED


def test_a_published_snapshot_that_cannot_be_read_is_still_refused():
    """THE CONTROL, and it must be able to fail: this is what REFUSED is
    for, and the copy the reader gets describes exactly this case."""
    # REFUSED is the market block's OWN state for a snapshot it found and
    # rejected -- for the wrong company, or in a form it will not read. It
    # is read here rather than inferred, which is what let absence be
    # mistaken for rejection in the first place.
    assert _standing_of(_dossier({"availability": "REFUSED"})) == REFUSED


def test_an_available_snapshot_is_unaffected():
    assert _standing_of(_dossier({"availability": "AVAILABLE"})) != REFUSED
    assert _standing_of(_dossier({"availability": "STALE"})) != REFUSED


def test_a_run_with_no_evidence_keeps_the_page_it_had():
    """THE REROUTE IS CONFINED TO RUNS WITH SOMETHING TO STAND ON.

    A first version let every uncovered company fall through, and a run that
    derived NO observations then landed on UNMEASURABLE -- whose sentence is
    "No evidence has been published for this company". For a run that
    retrieved ten sources and matched no signal that is false, and the page
    it replaced said the true thing: the sources were read and none carried
    dated, checkable material. Two existing tests hold that page, and they
    were right to.
    """
    assert _standing_of(
        _dossier({"availability": "UNAVAILABLE"}, evidence=0)) == REFUSED


def test_a_run_with_no_evidence_and_no_market_is_not_promoted():
    """Whatever it is called, an empty run may not reach a recommendation."""
    standing = _standing_of(_dossier({"availability": "UNAVAILABLE"},
                                     evidence=0))
    assert standing in (REFUSED, UNMEASURABLE)


def test_evidence_without_beliefs_is_bounded_not_refused():
    assert _standing_of(
        _dossier({"availability": "UNAVAILABLE"}, beliefs=0)) == BOUNDED
