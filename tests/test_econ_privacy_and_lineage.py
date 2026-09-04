"""The two walls: tenant privacy, and derived evidence corroborating itself.

Section 31 and Section 35. These are the two failures that are invisible when
they happen and expensive when they are found, so both are asserted from the
outside -- what a caller can and cannot get out of the API -- rather than by
inspecting internals.
"""
from __future__ import annotations

import pytest

from intent_engine.econ import aggregates as AG
from intent_engine.econ import company as CO
from intent_engine.econ import evidence as EV
from intent_engine.econ import lineage as LI
from intent_engine.econ import state as ES
from intent_engine.econ import vocabulary as V


def company_node(subject, kind="hiring", statement="rising: we added staff",
                 publisher=None, visibility=V.PUBLIC, at="2026-06-01"):
    return EV.node(node_class=V.COMPANY, kind=kind, subject=subject,
                   standing=V.OBSERVED, occurred_at=at, available_at=at,
                   publisher=publisher or subject, statement=statement,
                   visibility=visibility, producer="test")


def panel(kind="hiring", n=6, statement="rising: we added staff"):
    return [company_node(f"co{i}", kind=kind, statement=statement)
            for i in range(n)]


# --- privacy ---------------------------------------------------------------
def test_a_private_node_cannot_enter_an_aggregate():
    nodes = panel() + [company_node("secret-co", visibility=V.TENANT_PRIVATE)]
    with pytest.raises(V.PrivacyViolation, match="tenant-private"):
        AG.build("hiring_pressure_index", nodes=nodes, as_of="2026-08-24")


def test_the_privacy_check_refuses_rather_than_filtering():
    """The distinction that matters.

    A filter would build the index from the six public nodes and report a
    panel of six -- which is a breach that also lies about its own sample,
    because the caller believed it had offered seven.
    """
    nodes = panel() + [company_node("secret-co", visibility=V.TENANT_PRIVATE)]
    with pytest.raises(V.PrivacyViolation):
        AG.build("hiring_pressure_index", nodes=nodes, as_of="2026-08-24")


def test_a_private_belief_cannot_enter_a_shared_economic_state():
    from intent_engine.econ import belief as B
    private = B.declare(
        proposition="our own renewal book is softening", probability=0.7,
        mechanism="internal pipeline", falsifier="renewals recover",
        expected_observations=("the next two renewal cohorts",),
        at="2026-06-01", visibility=V.TENANT_PRIVATE)
    with pytest.raises(ES.StateViolation, match="tenant-private"):
        ES.EconomicState(as_of="2026-08-24", beliefs=(private,))


def test_a_company_state_may_hold_private_evidence_inside_a_tenant():
    private = company_node("acme", visibility=V.TENANT_PRIVATE)
    state = CO.build(company_id="acme", company_name="Acme", as_of="2026-08-24",
                     evidence=[private], tenant="tenant-1")
    assert len(state.evidence) == 1
    assert state.public_evidence() == []


def test_a_company_state_without_a_tenant_may_not_hold_private_evidence():
    private = company_node("acme", visibility=V.TENANT_PRIVATE)
    with pytest.raises(V.PrivacyViolation, match="no tenant"):
        CO.build(company_id="acme", company_name="Acme", as_of="2026-08-24",
                 evidence=[private])


def test_contribution_refuses_to_hand_a_private_node_upward():
    private = company_node("acme", visibility=V.TENANT_PRIVATE)
    public = company_node("acme", kind="capex",
                          statement="rising: capex increased")
    state = CO.build(company_id="acme", company_name="Acme",
                     as_of="2026-08-24", evidence=[private, public],
                     tenant="tenant-1")
    assert state.contribution([public.node_id]) == [public]
    with pytest.raises(V.PrivacyViolation):
        state.contribution([private.node_id, public.node_id])


def test_serialisation_withholds_private_evidence_by_default():
    private = company_node("acme", visibility=V.TENANT_PRIVATE)
    public = company_node("acme", kind="capex", statement="rising: capex up")
    state = CO.build(company_id="acme", company_name="Acme",
                     as_of="2026-08-24", evidence=[private, public],
                     tenant="tenant-1")
    payload = state.as_dict()
    assert payload["private_evidence_withheld"] == 1
    assert len(payload["evidence"]) == 1
    assert all(n["visibility"] == V.PUBLIC for n in payload["evidence"])


def test_a_document_with_no_provenance_is_treated_as_private():
    """Fails closed. The unlabelled document is the dangerous one."""
    from intent_engine.external_intel import econ_evidence as EE
    out = EE.translate(
        [{"signals": ("capital_intensity",), "date": "2026-02-14",
          "excerpt": "Capital spending increased sharply.",
          "source_refs": [{"artifact_id": "d1"}]}],
        company_id="acme", company_name="Acme", as_of="2026-08-24")
    assert out["translated"] == 0
    assert out["declined"]["tenant_private"] == 1


# --- the double-counting wall ----------------------------------------------
def test_a_derived_index_is_not_independent_evidence_of_its_own_input():
    nodes = panel()
    graph = EV.EvidenceGraph(nodes)
    agg = AG.build("hiring_pressure_index", nodes=nodes, as_of="2026-08-24")
    index_node = graph.add(AG.as_node(agg, as_of="2026-08-24"))

    verdict = LI.independent(graph, index_node.node_id, nodes[0].node_id)
    assert not verdict.independent
    assert "own input" in verdict.reason
    assert nodes[0].node_id in verdict.shared_inputs


def test_two_indices_over_the_same_panel_are_one_witness():
    nodes = panel()
    graph = EV.EvidenceGraph(nodes)
    a = graph.add(AG.as_node(AG.build("hiring_pressure_index", nodes=nodes,
                                      as_of="2026-08-24"),
                             as_of="2026-08-24"))
    # A second index over the same panel, on a different signal from the same
    # companies. Overlapping inputs, so not two witnesses.
    other = [company_node(f"co{i}", kind="capex",
                          statement="rising: capex increased")
             for i in range(6)]
    for n in other:
        graph.add(n)
    b = graph.add(AG.as_node(AG.build("capex_intention_index", nodes=other,
                                      as_of="2026-08-24"),
                             as_of="2026-08-24"))
    # These two have DISJOINT inputs, so they are independent -- the
    # positive control for the negative one below.
    assert LI.independent(graph, a.node_id, b.node_id).independent

    # A third index sharing five of the first index's six companies. The
    # newcomer has to be in the graph first: the graph refuses lineage that
    # names a parent it does not hold, because unverifiable lineage is worse
    # than none.
    newcomer = graph.add(company_node("co9",
                                      statement="rising: we added staff"))
    overlapping = graph.add(AG.as_node(
        AG.build("hiring_pressure_index", nodes=nodes[:5] + [newcomer],
                 as_of="2026-08-25"), as_of="2026-08-25"))
    verdict = LI.independent(graph, a.node_id, overlapping.node_id)
    assert not verdict.independent
    assert "one panel" in verdict.reason


def test_one_publisher_saying_something_twice_is_one_source():
    graph = EV.EvidenceGraph()
    a = graph.add(company_node("acme", kind="hiring", publisher="Acme Inc",
                               statement="rising: we added staff"))
    b = graph.add(company_node("acme", kind="capex", publisher="Acme Inc",
                               statement="rising: capex increased"))
    assert not LI.independent(graph, a.node_id, b.node_id).independent


def test_two_different_publishers_are_two_witnesses():
    graph = EV.EvidenceGraph()
    a = graph.add(company_node("acme", publisher="Acme Inc",
                               statement="rising: we added staff"))
    b = graph.add(company_node("acme", kind="capex", publisher="A Reporter",
                               statement="rising: capex increased"))
    assert LI.independent(graph, a.node_id, b.node_id).independent


def test_unknown_lineage_is_not_independence():
    """Fails closed: a node the graph does not hold has unknown lineage."""
    graph = EV.EvidenceGraph([company_node("acme")])
    verdict = LI.independent(graph, "en-missing",
                             graph.nodes()[0].node_id)
    assert not verdict.independent
    assert "not in the graph" in verdict.reason


def test_independent_support_reports_what_it_dropped():
    nodes = panel()
    graph = EV.EvidenceGraph(nodes)
    index = graph.add(AG.as_node(
        AG.build("hiring_pressure_index", nodes=nodes, as_of="2026-08-24"),
        as_of="2026-08-24"))
    kept, refusals = LI.independent_support(
        graph, nodes[0].node_id, [index.node_id, nodes[1].node_id])
    assert kept == [nodes[1].node_id]
    assert refusals and "own input" in refusals[0].reason


def test_a_lineage_cycle_cannot_hang_the_wall():
    """A malformed lineage must not hang the founder-facing independence count."""
    graph = EV.EvidenceGraph()
    n = company_node("acme")
    graph.add(n)
    object.__setattr__(n, "depends_on", (n.node_id,))
    assert n.node_id in graph.ancestors(n.node_id)


def test_the_assertion_form_raises_for_a_publishing_surface():
    nodes = panel()
    graph = EV.EvidenceGraph(nodes)
    index = graph.add(AG.as_node(
        AG.build("hiring_pressure_index", nodes=nodes, as_of="2026-08-24"),
        as_of="2026-08-24"))
    with pytest.raises(V.LineageViolation, match="not independent"):
        LI.assert_not_self_corroborating(
            graph, claim_node=nodes[0].node_id, support=[index.node_id],
            where="a founder-facing independence count")


# --- the aggregate's own honesty -------------------------------------------
def test_a_thin_panel_refuses_to_become_an_index():
    got = AG.build("hiring_pressure_index", nodes=panel(n=3),
                   as_of="2026-08-24")
    assert not got.sufficient
    assert got.score is None
    assert "5" in got.reason


def test_an_insufficient_index_cannot_become_an_evidence_node():
    thin = AG.build("hiring_pressure_index", nodes=panel(n=2),
                    as_of="2026-08-24")
    with pytest.raises(V.EconError, match="worse than a stated absence"):
        AG.as_node(thin, as_of="2026-08-24")


def test_no_index_is_ever_tradable():
    agg = AG.build("hiring_pressure_index", nodes=panel(), as_of="2026-08-24")
    assert agg.tradable is False
    with pytest.raises(Exception):
        object.__setattr__(agg, "tradable", True) or agg.__setattr__(
            "tradable", True)


def test_one_company_cannot_dominate_a_panel():
    """Eleven observations from one company are still one vote."""
    loud = [company_node("loud-co", statement="rising: we added staff")
            for _ in range(11)]
    # ids are content-derived, so identical statements collapse; vary them.
    loud = [company_node("loud-co", statement=f"rising: we added staff {i}")
            for i in range(11)]
    nodes = panel(n=5) + loud
    agg = AG.build("hiring_pressure_index", nodes=nodes, as_of="2026-08-24")
    assert agg.sufficient
    assert agg.concentration <= AG.MAX_CONTRIBUTOR_SHARE
    loud_contribution = [c for c in agg.contributors
                         if c.company_id == "loud-co"][0]
    assert loud_contribution.raw_count == 11
    assert loud_contribution.weight <= AG.MAX_CONTRIBUTOR_SHARE


def test_an_index_node_carries_its_whole_panel_as_lineage():
    nodes = panel()
    agg = AG.build("hiring_pressure_index", nodes=nodes, as_of="2026-08-24")
    node = AG.as_node(agg, as_of="2026-08-24")
    assert set(node.depends_on) == {n.node_id for n in nodes}
    assert node.standing == V.INFERRED, (
        "a derived index entered the graph as OBSERVED; nobody published it")
