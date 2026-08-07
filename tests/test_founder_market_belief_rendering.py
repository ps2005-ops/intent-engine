"""Market beliefs reaching founder reasoning — and what must never survive.

Three layers of disconnection had to be removed before a market belief could
reach a founder at all: a schema the consumer rejected, a refusal
indistinguishable from absence, and a renderer that read every kind of
strategic content EXCEPT the one kind the producer makes.

Now that beliefs do arrive, the risk inverts. The dangerous failure is no
longer silence — it is a market hypothesis rendered as a fact, a prior
rendered as a measurement, or a reading rendered as advice. Most of this file
is about those.
"""
import pytest

from intent_engine.business_graph import projections as bgp
from intent_engine.business_graph.model import (
    EVIDENCE, HYPOTHESIS, SUPPORTS,
)
from intent_engine.external_intel import pack as ep
from intent_engine.external_intel import strategic_contract as sc


def _belief(**kw):
    row = {
        "proposition": "Acme Corp is seeing demand strengthen rather than "
                       "plateau",
        "subject": "Acme Corp",
        "confidence": 0.586,
        "direction_of_last_change": None,
        "last_updated": "2026-08-05",
        "basis": "opened by 1 translated evidence item(s) of type "
                 "EARNINGS_RESULT, effective sample 0.90",
        "update_method": "DECLARED",
        "evidence_ids": ["ev_abc123"],
        "limitations": ["one period's result is a data point, not a trend"],
    }
    row.update(kw)
    return row


def _intel(beliefs=None, **kw):
    return sc.StrategicIntel(
        available=True, company_id="acme", as_of="2026-08-07",
        beliefs=tuple(beliefs if beliefs is not None else [_belief()]), **kw)


def _blocks(intel):
    pack = ep.reasoning_pack(ep.build_context(strategic=intel,
                                              as_of="2026-08-07"))
    return [b for b in pack["blocks"] if b["context"] == ep.STRATEGIC]


# ===========================================================================
# THE DEFECT THAT WAS CLOSED
# ===========================================================================
def test_a_belief_only_dossier_now_produces_a_block():
    """`has_material` counted beliefs; the renderer did not read them.

    A real dossier validated, was counted as carrying material, opened a
    strategic section, and put nothing under it.
    """
    intel = _intel()
    assert intel.has_material is True
    assert len(_blocks(intel)) == 1


def test_an_empty_dossier_still_produces_nothing():
    assert _blocks(_intel(beliefs=[])) == []


def test_a_belief_with_no_proposition_is_skipped():
    assert _blocks(_intel(beliefs=[_belief(proposition="")])) == []


# ===========================================================================
# PROVENANCE — the chain must survive to the rendered block
# ===========================================================================
def test_the_rendered_block_carries_the_market_evidence_id():
    """Sentence → hypothesis node → supports edge → evidence → ledger id.

    The first version walked `neighbours(node, EVIDENCE)`, but that argument
    filters EDGE kind, not node kind, so it matched nothing and the block
    shipped with no provenance at all — silently, which is the worst way for
    a provenance chain to break.
    """
    assert _blocks(_intel())[0]["evidence_ids"] == ["ev_abc123"]


def test_the_belief_is_projected_into_the_canonical_graph():
    graph = bgp.from_strategic_dossier(
        company_id="acme", beliefs=[_belief()], as_of="2026-08-07",
        dossier_revision="2026-08-07")
    hypotheses = graph.of_kind(HYPOTHESIS)
    assert len(hypotheses) == 1
    evidence = graph.of_kind(EVIDENCE)
    assert [n.attrs["evidence_id"] for n in evidence] == ["ev_abc123"]
    # and the edge runs evidence -> hypothesis, not the other way
    edges = graph.in_edges(hypotheses[0].node_id, SUPPORTS)
    assert [e.src for e in edges] == [evidence[0].node_id]


def test_a_later_revision_is_a_new_node_not_an_overwrite():
    """What a founder was shown last week must stay recoverable."""
    graph = bgp.from_strategic_dossier(
        company_id="acme", beliefs=[_belief()], as_of="2026-08-06",
        dossier_revision="2026-08-06")
    graph = bgp.from_strategic_dossier(
        company_id="acme", beliefs=[_belief()], as_of="2026-08-07",
        dossier_revision="2026-08-07", graph=graph)
    assert len(graph.of_kind(HYPOTHESIS)) == 2


# ===========================================================================
# EPISTEMIC STATUS — what must never survive rendering
# ===========================================================================
def test_a_probability_is_never_rendered_as_a_percentage():
    """0.586 is the prior a single evidence item opens a belief at.

    Every belief in the real corpus carries it. Printing "59% confident"
    turns a prior into a measurement — the same error the market's own
    mechanism calibration refuses by declining to grade below five tests.
    """
    text = " ".join(_blocks(_intel())[0]["facts"])
    for forbidden in ("59%", "58.6", "0.586", "59 percent"):
        assert forbidden not in text


def test_an_untested_belief_says_so():
    block = _blocks(_intel())[0]
    assert "not yet tested" in " ".join(block["facts"]).lower()


def test_a_belief_is_never_rendered_as_a_settled_fact():
    block = _blocks(_intel())[0]
    text = " ".join(block["facts"] + block["limitations"] + [block["role"]])
    low = text.lower()
    assert "reading" in low or "hypothesis" in low
    for forbidden in ("proves", "guarantees", "definitely", "will certainly",
                      "the market knows"):
        assert forbidden not in low


def test_a_belief_never_becomes_a_recommendation():
    """A reading is not advice, and this is the boundary that keeps it so."""
    block = _blocks(_intel())[0]
    low = " ".join(block["facts"] + block["limitations"]).lower()
    assert "does not by itself recommend an action" in low
    for forbidden in ("you should", "the company should", "we recommend",
                      "buy", "sell"):
        assert forbidden not in low


def test_the_producers_own_limitation_survives_to_the_founder():
    block = _blocks(_intel())[0]
    assert any("data point, not a trend" in l for l in block["limitations"])


def test_the_role_marks_it_as_external_and_under_test():
    role = _blocks(_intel())[0]["role"].lower()
    assert "hypothesis under test" in role
    assert "not a finding" in role


# ===========================================================================
# STANDING reflects testing status, not the prior
# ===========================================================================
def test_standing_is_decided_by_testing_status():
    assert "not yet tested" in bgp.belief_standing(_belief())
    assert "supported" in bgp.belief_standing(
        _belief(update_method="REVISED", direction_of_last_change="UP"))
    assert "contested" in bgp.belief_standing(
        _belief(update_method="REVISED", direction_of_last_change="DOWN"))


def test_a_high_prior_cannot_promote_an_untested_belief():
    """Confidence 0.99 and never tested is still never tested."""
    assert "not yet tested" in bgp.belief_standing(
        _belief(confidence=0.99))
