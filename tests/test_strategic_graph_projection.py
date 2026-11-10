"""The strategic family in the Business Graph, and the founder path that reads it.

Three things are under test, and the third is the one that makes the other two
worth having:

1. the dossier projects onto the graph's EXISTING closed vocabulary, through
   roles, rather than by widening it;
2. the projection keeps the properties that make a projection safe -- pure,
   idempotent, provenance-carrying, refusing rather than guessing;
3. a founder-visible surface resolves belief provenance THROUGH the graph, so
   there is one derivation of "what supports this" rather than two that agree
   until they do not.

The payload is the real published dossier fixture, not a constructed one.
"""
import json
import pathlib

import pytest

from intent_engine.business_graph.model import (
    EDGE_KINDS, NODE_KINDS, BusinessGraph,
)
from intent_engine.external_intel import market_contract as MC
from intent_engine.external_intel import pack as PK
from intent_engine.external_intel import presenter as PS
from intent_engine.external_intel import projection as PJ
from intent_engine.external_intel import strategic_contract as SC

FIXTURE = (pathlib.Path(__file__).parent / "fixtures"
           / "published_dossier_microsoft.json")
TODAY = "2026-08-06"
COMPANY = "Microsoft Corporation"


def _payload(**over):
    payload = json.loads(FIXTURE.read_text())
    payload.update(over)
    return payload


def _context(payload=None, today=TODAY):
    intel = SC.consume(payload or _payload(), today=today)
    return PK.ExternalContext(market=MC.absent("not under test"),
                              strategic=intel, as_of=today)


def _project(context=None):
    return PJ.project(context or _context(), company=COMPANY)


def _roles(nodes):
    return [n.attrs.get("role") for n in nodes]


# --- the vocabulary was not widened -----------------------------------------
def test_the_projection_adds_no_new_node_or_edge_kinds():
    """The whole argument for roles: a closed vocabulary stays closed."""
    nodes, edges = _project()
    assert {n.kind for n in nodes} <= NODE_KINDS
    assert {e.kind for e in edges} <= EDGE_KINDS


def test_the_strategic_family_reaches_the_graph_at_all():
    nodes, _ = _project()
    assert PJ.STRATEGIC_BELIEF in _roles(nodes)
    assert PJ.STRATEGIC_MICRO_EVIDENCE in _roles(nodes)


def test_every_strategic_node_declares_a_role_from_the_declared_set():
    nodes, _ = _project()
    strategic = [n for n in nodes
                 if n.attrs.get("role") in PJ.STRATEGIC_ROLES]
    assert strategic
    for node in strategic:
        assert node.attrs["role"] in PJ.STRATEGIC_ROLES


def test_a_belief_is_a_hypothesis_and_its_evidence_supports_it():
    """The mapping argument, asserted rather than described: SUPPORTS already
    points evidence at a hypothesis, so no new edge kind is needed."""
    nodes, edges = _project()
    beliefs = {n.node_id for n in nodes
               if n.attrs.get("role") == PJ.STRATEGIC_BELIEF}
    assert all(n.kind == "hypothesis" for n in nodes
               if n.node_id in beliefs)
    supporting = [e for e in edges if e.kind == "supports"]
    assert supporting
    assert all(e.dst in beliefs for e in supporting)


def test_the_graph_accepts_the_projection():
    """`BusinessGraph` enforces its own invariants; this is not a dry run."""
    nodes, edges = _project()
    graph = BusinessGraph(nodes, edges)
    assert len(graph.nodes) == len(nodes)


# --- the properties that make a projection safe -----------------------------
def test_projecting_twice_produces_identical_ids():
    first, _ = _project()
    second, _ = _project()
    assert [n.node_id for n in first] == [n.node_id for n in second]


def test_re_projecting_creates_no_duplicate_logical_nodes():
    nodes, edges = _project()
    graph = BusinessGraph(nodes, edges)
    graph_again = BusinessGraph(list(nodes) + list(nodes),
                                list(edges) + list(edges))
    assert len(graph_again.nodes) == len(graph.nodes)
    assert len(graph_again.edges) == len(graph.edges)


def test_two_beliefs_sharing_one_basis_sentence_stay_two_pieces_of_evidence():
    """Content-derived ids collapse identical text. Evidence for DIFFERENT
    beliefs is not the same evidence, so the belief is part of the id."""
    payload = _payload()
    payload["strategic_beliefs"][1]["basis"] = \
        payload["strategic_beliefs"][0]["basis"]
    nodes, _ = _project(_context(payload))
    evidence = [n for n in nodes
                if n.attrs.get("role") == PJ.STRATEGIC_MICRO_EVIDENCE]
    assert len({n.node_id for n in evidence}) == 2


def _belief_ids(context):
    nodes, _ = _project(context)
    return {n.node_id for n in nodes
            if n.attrs.get("role") == PJ.STRATEGIC_BELIEF}


def test_a_belief_updated_later_is_a_distinct_reading():
    """The same proposition held on two dates is two readings.

    The time context that matters is the BELIEF's, not the dossier's: a
    belief carries `last_updated`, and that is when this reading came to be
    held. Keying on it is what keeps a revision from overwriting the position
    it revised.
    """
    payload = _payload()
    for belief in payload["strategic_beliefs"]:
        belief["last_updated"] = "2026-09-14"
    assert not (_belief_ids(_context()) & _belief_ids(_context(payload,
                                                               "2026-09-14")))


def test_republishing_an_unchanged_belief_does_not_create_a_second_node():
    """The other half, and the one that would bloat the graph if it failed.

    A dossier republished on a later date whose beliefs did not move describes
    the same readings. A new node per cycle would report our publishing
    schedule as if it were strategic change.
    """
    later = _payload(as_of="2026-08-20", generated_at="2026-08-20T00:00:00+00:00")
    assert _belief_ids(_context()) == _belief_ids(_context(later, "2026-08-20"))


def test_every_strategic_node_carries_its_provenance_and_lineage():
    nodes, _ = _project()
    for node in [n for n in nodes
                 if n.attrs.get("role") in PJ.STRATEGIC_ROLES]:
        assert node.source, node.label
        assert node.attrs["dossier_company_id"]
        assert node.attrs["schema_version"] == SC.SCHEMA_VERSION
        assert node.attrs["dossier_as_of"]


def test_belief_nodes_keep_their_evidence_ids():
    nodes, _ = _project()
    beliefs = [n for n in nodes
               if n.attrs.get("role") == PJ.STRATEGIC_BELIEF]
    assert all(n.attrs["evidence_ids"] for n in beliefs)


# --- refusals ---------------------------------------------------------------
def test_an_unavailable_dossier_projects_no_strategic_node():
    context = PK.ExternalContext(
        market=MC.absent("not under test"),
        strategic=SC.unavailable("no dossier was published"), as_of=TODAY)
    nodes, _ = PJ.project(context, company=COMPANY)
    assert not [n for n in nodes
                if n.attrs.get("role") in PJ.STRATEGIC_ROLES]


def test_a_dossier_with_no_material_projects_no_strategic_node():
    """Validated cleanly and saying nothing is an absence, not a section."""
    context = _context(_payload(strategic_beliefs=[]))
    assert not context.has_strategic
    nodes, _ = PJ.project(context, company=COMPANY)
    assert not [n for n in nodes
                if n.attrs.get("role") in PJ.STRATEGIC_ROLES]


def test_an_unsafe_dossier_never_reaches_the_projection():
    """The contract refuses it on the way in, so there is nothing to project."""
    payload = _payload()
    payload["strategic_beliefs"][0]["proposition"] = \
        "The paper book shows a sharpe of 1.8 on this name"
    with pytest.raises(SC.StrategicLeak):
        SC.validate(payload)


def test_a_belief_with_no_proposition_is_skipped_not_guessed_at():
    payload = _payload()
    payload["strategic_beliefs"][0]["proposition"] = "  "
    nodes, _ = _project(_context(payload))
    assert len([n for n in nodes
                if n.attrs.get("role") == PJ.STRATEGIC_BELIEF]) == 1


# --- maturity and confidence semantics --------------------------------------
def test_a_declared_belief_is_newly_declared_and_carries_no_percentage():
    belief = _payload()["strategic_beliefs"][0]
    assert SC.belief_maturity(belief) == SC.NEWLY_DECLARED
    assert not SC.confidence_is_numeric(belief)
    assert "%" not in SC.confidence_language(belief)


def test_an_empirical_bayes_posterior_may_state_its_number():
    """Numbers are not removed reflexively -- a measured one is kept."""
    belief = dict(_payload()["strategic_beliefs"][0],
                  update_method="EMPIRICAL_BAYES", confidence=0.62)
    assert SC.confidence_is_numeric(belief)
    assert "62%" in SC.confidence_language(belief)


def test_an_unrecognised_update_method_is_treated_as_untested():
    belief = dict(_payload()["strategic_beliefs"][0],
                  update_method="SOMETHING_NEW_UPSTREAM")
    assert SC.belief_maturity(belief) == SC.NEWLY_DECLARED
    assert not SC.confidence_is_numeric(belief)


def test_a_weakened_belief_reads_as_weakened():
    belief = dict(_payload()["strategic_beliefs"][0],
                  update_method="CALIBRATED_HEURISTIC",
                  direction_of_last_change="down")
    assert SC.belief_maturity(belief) == SC.WEAKENED


def test_the_projection_and_the_contract_agree_about_maturity():
    """Two readers of one belief may not disagree about how mature it is."""
    nodes, _ = _project()
    beliefs = {n.label: n for n in nodes
               if n.attrs.get("role") == PJ.STRATEGIC_BELIEF}
    for raw in _payload()["strategic_beliefs"]:
        node = beliefs[raw["proposition"]]
        assert node.attrs["maturity"] == SC.belief_maturity(raw)


def test_break_a_heuristic_confidence_presented_as_empirical_precision():
    block = PS.strategic_blocks(_context())[0]
    for banned in ("62%", "61%", "0.618", "0.6089"):
        assert banned not in block.fact
        assert banned not in block.text_alternative


def test_break_a_new_belief_presented_as_a_tested_fact():
    block = PS.strategic_blocks(_context())[0]
    assert "newly formed reading" in block.fact
    assert "not a tested conclusion" in block.fact


# --- the founder path that reads the graph ----------------------------------
def test_belief_provenance_resolves_support_through_the_graph():
    provenance = PJ.belief_provenance(_context(), company=COMPANY)
    assert provenance
    for entry in provenance.values():
        assert entry["supports"], "a projected belief has its basis attached"
        assert entry["evidence_ids"]


def test_support_and_contradiction_never_merge():
    """A contradicted belief and an asserted one must not read the same."""
    payload = _payload()
    proposition = payload["strategic_beliefs"][0]["proposition"]
    payload["expectation_mismatches"] = [{
        "subject": COMPANY, "expected_event": "Bookings growth continues",
        "expected_direction": "up", "observed_direction": "down",
        "outcome": "contradicted", "rationale": "The quarter came in lower.",
        "evaluated_at": TODAY, "preregistered_at": "2026-07-01",
        "falsifier": proposition, "evidence_ids": ["ev_x"]}]
    provenance = PJ.belief_provenance(_context(payload), company=COMPANY)
    entry = provenance[proposition]
    assert entry["contradicts"], "the mismatch attached to the belief"
    assert entry["supports"], "and did not consume the supporting evidence"
    assert not set(s["label"] for s in entry["supports"]) & \
        set(c["label"] for c in entry["contradicts"])


def test_a_mismatch_naming_no_belief_does_not_attach_to_one():
    """Binding a falsifier to the wrong belief is the same class of error as
    binding a dossier to the wrong company. Only exact names attach."""
    payload = _payload()
    payload["expectation_mismatches"] = [{
        "subject": COMPANY, "expected_event": "Something unrelated",
        "expected_direction": "up", "observed_direction": "down",
        "outcome": "contradicted", "rationale": "n/a", "evaluated_at": TODAY,
        "preregistered_at": "2026-07-01",
        "falsifier": "a proposition no belief states", "evidence_ids": []}]
    provenance = PJ.belief_provenance(_context(payload), company=COMPANY)
    assert all(not e["contradicts"] for e in provenance.values())


def test_the_founder_block_states_the_support_it_read_from_the_graph():
    block = PS.strategic_blocks(_context())[0]
    assert "rests on 4 piece(s) of public evidence" in block.fact


def test_the_founder_block_reports_a_contradiction_when_the_graph_holds_one():
    payload = _payload()
    payload["expectation_mismatches"] = [{
        "subject": COMPANY, "expected_event": "Bookings growth continues",
        "expected_direction": "up", "observed_direction": "down",
        "outcome": "contradicted", "rationale": "The quarter came in lower.",
        "evaluated_at": TODAY, "preregistered_at": "2026-07-01",
        "falsifier": payload["strategic_beliefs"][0]["proposition"],
        "evidence_ids": ["ev_x"]}]
    block = PS.strategic_blocks(_context(payload))[0]
    assert "gone against it" in block.fact


def test_break_the_projection_never_being_invoked():
    """The defect this slice exists to fix: a projection nothing calls.

    Asserted through the PRESENTER, so it fails if the founder path stops
    reading the graph -- not through a direct call, which would pass whether
    or not anything was wired up.
    """
    calls = []
    original = PJ.belief_provenance

    def counting(*a, **kw):
        calls.append(1)
        return original(*a, **kw)

    PJ.belief_provenance = counting
    try:
        PS.strategic_blocks(_context())
    finally:
        PJ.belief_provenance = original
    assert calls, "the founder surface did not read the graph"


def test_break_provenance_being_lost():
    provenance = PJ.belief_provenance(_context(), company=COMPANY)
    for entry in provenance.values():
        for item in entry["supports"]:
            assert item["source"], "evidence with no source is unattributable"


def test_a_belief_absent_from_the_graph_yields_no_provenance_claim():
    """Fails closed: absence of a key means "no provenance", and the caller
    must not read it as "no support"."""
    provenance = PJ.belief_provenance(_context(), company=COMPANY)
    assert provenance.get("a belief nobody published") is None
