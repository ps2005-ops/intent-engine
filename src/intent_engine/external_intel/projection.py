"""Project sanctioned external intelligence into the Business Graph.

WHY A PROJECTION RATHER THAN A SECOND STORE
--------------------------------------------
The graph is a VIEW of the contracts, rebuildable from them at any time. It is
not a second source of truth, and nothing reads back from it into the pack.
`project` is pure: same context in, same nodes out, no ids that depend on when
it ran. That is what makes "unchanged data does not create duplicate nodes"
true by construction rather than by a de-duplication pass -- a node's id is
derived from what it says, so re-projecting the same context produces the same
node.

WHAT MAY BE PROJECTED
---------------------
Only what the three contracts already sanctioned. This module cannot widen the
boundary: it reads an `ExternalContext`, and everything in one has been through
either the market allowlist, the macro exposure gate or the competitor
relevance classifier.

Every node carries provenance, an as-of date and its non-predictive role,
because `business_graph.Node` refuses a node with no source -- which is the
right refusal and the reason nothing here can be projected anonymously.
"""
from __future__ import annotations

import hashlib
from typing import Dict, List, Optional, Sequence, Tuple

from intent_engine.business_graph.model import (
    AFFECTS, ASSUMPTION, COMPANY, COMPETES_WITH, COMPETITOR, CONCERNS,
    CONTRADICTS, DECISION, EVENT, EVIDENCE, HYPOTHESIS, INFORMS, MARKET,
    MEASURES, RISK, SUPPORTS, Edge, Node,
)

#: The graph has no dedicated "assumption about the outside world" kind, and an
#: exposure mechanism is exactly that: a claim about how this company is
#: connected to a condition, which later evidence can support or contradict.
ASSUMPTION_KIND = ASSUMPTION

from . import strategic_contract as SC
from .competitor_contract import Competitor, corroborating
from .macro_contract import MacroFactor
from .pack import ExternalContext
from .strategic_contract import SCHEMA_VERSION

#: Node roles. The graph's kinds are generic, so the role says what a node IS
#: in this projection and, critically, that it is descriptive rather than
#: predictive.
MARKET_OBSERVATION = "MARKET_OBSERVATION"
MARKET_EXPECTATION = "MARKET_EXPECTATION"
VOLATILITY_CONTEXT = "VOLATILITY_CONTEXT"
BENCHMARK_COMPARISON = "BENCHMARK_COMPARISON"
REGIME_CONTEXT = "REGIME_CONTEXT"
MARKET_EVENT = "MARKET_EVENT"
MACRO_FACTOR = "MACRO_FACTOR"
EXPOSURE_MECHANISM = "EXPOSURE_MECHANISM"
COMPETITIVE_ALTERNATIVE = "COMPETITIVE_ALTERNATIVE"
LIMITATION = "LIMITATION"

# --- the strategic family ---------------------------------------------------
#
# WHY NO NEW NODE OR EDGE KINDS
# ------------------------------
# `NODE_KINDS` and `EDGE_KINDS` are closed frozensets, and the three families
# already here are modelled as a generic kind plus a `role`: a macro factor is
# a MARKET node with role MACRO_FACTOR, an exposure mechanism an ASSUMPTION
# with role EXPOSURE_MECHANISM. The strategic domain brings new NAMES, not new
# relationships, so it follows the same rule.
#
# Every distinction the strategic dossier makes survives the mapping:
#
#   a belief is a HYPOTHESIS -- something held with a confidence that evidence
#     can support or contradict, which is what the kind already means, and
#     what SUPPORTS/CONTRADICTS/INFORMS are already declared to point at.
#   an expectation is an ASSUMPTION -- taken as true pending a test.
#   an information priority is a DECISION with a role -- "what to go and find
#     out" is a choice, and INFORMS is the belief->decision edge already.
#
# Edge roles are carried by (edge kind, target node role) rather than on the
# edge, because `Edge` has no attrs field and `Edge.key()` is (src, dst, kind).
# This is not a workaround: BELIEF_SUPPORT and BELIEF_CONTRADICTION -- the two
# edge roles the design calls for -- ARE the difference between SUPPORTS and
# CONTRADICTS, and REQUIRES_INFORMATION is INFORMS pointing at a node whose
# role is INFORMATION_PRIORITY. Adding an `attrs` field to Edge to restate
# that would create two places to look for one fact.
#
# The bar for changing that: a distinction the dossier makes that (kind, role)
# cannot carry -- two edges of the same kind between the same pair meaning
# different things. None exists today.
STRATEGIC_BELIEF = "STRATEGIC_BELIEF"
STRATEGIC_MICRO_EVIDENCE = "STRATEGIC_MICRO_EVIDENCE"
BELIEF_LIMITATION = "BELIEF_LIMITATION"
INFORMATION_PRIORITY = "INFORMATION_PRIORITY"
HIDDEN_STATE_READING = "HIDDEN_STATE_READING"
CAUSAL_PATHWAY = "CAUSAL_PATHWAY"
EXPECTATION_OBSERVATION = "EXPECTATION_OBSERVATION"

#: Roles whose nodes came from the strategic dossier. A consumer asking "is
#: this reading grounded in published strategic evidence?" checks membership
#: here rather than pattern-matching on labels.
STRATEGIC_ROLES = frozenset({
    STRATEGIC_BELIEF, STRATEGIC_MICRO_EVIDENCE, BELIEF_LIMITATION,
    INFORMATION_PRIORITY, HIDDEN_STATE_READING, CAUSAL_PATHWAY,
    EXPECTATION_OBSERVATION,
})

NON_PREDICTIVE = ("descriptive: records what has been observed, and is not a "
                  "forecast or a recommendation")


def _nid(*parts) -> str:
    """A content-derived id, so re-projecting is idempotent."""
    raw = "|".join(str(p) for p in parts)
    return "ext-" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _node(kind, label, *, role, source, as_of, company, extra=None) -> Node:
    return Node(
        node_id=_nid(role, company, label), kind=kind, label=label,
        source=source, as_of=as_of or "",
        attrs={"role": role, "subject_company": company,
               "non_predictive": NON_PREDICTIVE, **(extra or {})})


def _snode(kind, label, *, role, source, as_of, company, extra=None,
           distinct=()) -> Node:
    """A strategic node, whose id includes its as-of date.

    The other families key on (role, company, label) alone, and that is right
    for them: a market measurement restated later carries the new date inside
    its own label, because the number moved. A belief's proposition does not --
    the same sentence held on two dates is two readings, and collapsing them
    would make a dossier republished a month later indistinguishable from the
    one it replaced.

    `distinct` adds whatever else makes two nodes different despite identical
    text: two beliefs opened by the same basis sentence are two pieces of
    evidence, not one shared between them.
    """
    return Node(
        node_id=_nid(role, company, label, as_of, *distinct), kind=kind,
        label=label, source=source, as_of=as_of or "",
        attrs={"role": role, "subject_company": company,
               "non_predictive": NON_PREDICTIVE, **(extra or {})})


def _project_strategic(intel, *, company, subject) -> Tuple[List[Node],
                                                            List[Edge]]:
    """The strategic dossier as graph, using only existing kinds and roles.

    Fails closed twice over: the caller projects nothing unless the dossier is
    both available and carrying material, and every item here is skipped
    rather than guessed at when the text it needs is absent. A node with an
    empty label would be refused by `Node` anyway -- this makes the refusal a
    decision rather than an exception.
    """
    nodes: List[Node] = []
    edges: List[Edge] = []
    source = "market-learning engine, from public evidence"
    dossier_as_of = intel.as_of
    #: Proposition -> node id, so the things that reference a belief by its
    #: words can attach to it. Only EXACT matches attach: a fuzzy match here
    #: would silently bind a falsifier to the wrong belief, which is the same
    #: class of error as binding a dossier to the wrong company.
    by_proposition = {}

    common = {"dossier_company_id": intel.company_id,
              "dossier_as_of": dossier_as_of,
              "schema_version": SCHEMA_VERSION,
              "dossier_stale": intel.stale}

    for belief in intel.beliefs:
        proposition = str(belief.get("proposition") or "").strip()
        if not proposition:
            continue
        as_of = str(belief.get("last_updated") or dossier_as_of)
        evidence_ids = [str(e) for e in (belief.get("evidence_ids") or ()) if e]
        node = _snode(
            HYPOTHESIS, proposition, role=STRATEGIC_BELIEF, source=source,
            as_of=as_of, company=company,
            extra={"confidence": belief.get("confidence"),
                   "update_method": belief.get("update_method"),
                   # Derived in the contract, carried here, so a consumer
                   # reading the graph and one reading the dossier cannot
                   # disagree about how mature the same belief is.
                   "maturity": SC.belief_maturity(belief),
                   "confidence_is_numeric": SC.confidence_is_numeric(belief),
                   "evidence_ids": evidence_ids, **common})
        nodes.append(node)
        by_proposition[proposition] = node.node_id
        edges.append(Edge(node.node_id, subject, AFFECTS, derived=False,
                          source=source))

        basis = str(belief.get("basis") or "").strip()
        if basis or evidence_ids:
            ev = _snode(
                EVIDENCE,
                basis or f"{len(evidence_ids)} strategic evidence item(s)",
                role=STRATEGIC_MICRO_EVIDENCE, source=source, as_of=as_of,
                company=company, distinct=(proposition,),
                extra={"evidence_ids": evidence_ids,
                       "evidence_count": len(evidence_ids), **common})
            nodes.append(ev)
            edges.append(Edge(ev.node_id, node.node_id, SUPPORTS,
                              derived=False, source=source))

        for limitation in belief.get("limitations") or ():
            text = str(limitation).strip()
            if not text:
                continue
            lim = _snode(RISK, text, role=BELIEF_LIMITATION, source=source,
                         as_of=as_of, company=company,
                         distinct=(proposition,), extra=dict(common))
            nodes.append(lim)
            edges.append(Edge(lim.node_id, node.node_id, CONCERNS,
                              derived=False, source=source))

    # A preregistered expectation that did not hold is the only CONTRADICTING
    # evidence a dossier currently carries. It attaches to a belief only when
    # the falsifier names one word for word.
    for mismatch in intel.mismatches:
        expected = str(mismatch.get("expected_event") or "").strip()
        if not expected:
            continue
        as_of = str(mismatch.get("evaluated_at") or dossier_as_of)
        node = _snode(
            ASSUMPTION_KIND, expected, role=EXPECTATION_OBSERVATION,
            source=source, as_of=as_of, company=company,
            extra={"expected_direction": mismatch.get("expected_direction"),
                   "observed_direction": mismatch.get("observed_direction"),
                   "outcome": mismatch.get("outcome"),
                   "preregistered_at": mismatch.get("preregistered_at"),
                   "evidence_ids": [str(e) for e in
                                    (mismatch.get("evidence_ids") or ()) if e],
                   **common})
        nodes.append(node)
        target = by_proposition.get(str(mismatch.get("falsifier") or "").strip())
        if target:
            edges.append(Edge(node.node_id, target, CONTRADICTS,
                              derived=False, source=source))
        else:
            edges.append(Edge(node.node_id, subject, AFFECTS, derived=False,
                              source=source))

    # What would most reduce an uncertainty: a choice about where to look, so
    # a DECISION, reached from the belief it would settle.
    for priority in intel.priorities:
        candidate = str(priority.get("candidate_observation") or "").strip()
        if not candidate:
            continue
        node = _snode(
            DECISION, candidate, role=INFORMATION_PRIORITY, source=source,
            as_of=str(priority.get("expected_date") or dossier_as_of),
            company=company,
            extra={"priority": priority.get("priority"),
                   "observation_kind": priority.get("observation_kind"),
                   "falsifies": priority.get("falsifies"),
                   "limitation": priority.get("limitation"), **common})
        nodes.append(node)
        origin = by_proposition.get(str(priority.get("falsifies") or "").strip())
        if origin:
            edges.append(Edge(origin, node.node_id, INFORMS, derived=False,
                              source=source))
        else:
            edges.append(Edge(node.node_id, subject, AFFECTS, derived=False,
                              source=source))

    # A stated mechanism connecting one factor to another: an assumption the
    # dossier is making, which later evidence can support or contradict.
    for pathway in intel.pathways:
        name = str(pathway.get("name") or "").strip()
        narrative = str(pathway.get("narrative") or "").strip()
        if not (name or narrative):
            continue
        node = _snode(
            ASSUMPTION_KIND, name or narrative, role=CAUSAL_PATHWAY,
            source=source, as_of=dossier_as_of, company=company,
            extra={"narrative": narrative,
                   "status": pathway.get("status"),
                   "total_lag_days": pathway.get("total_lag_days"),
                   "weakest_link": pathway.get("weakest_link"), **common})
        nodes.append(node)
        edges.append(Edge(node.node_id, subject, AFFECTS, derived=False,
                          source=source))

    # `postures` is what the contract calls the dossier's `hidden_states`: a
    # reading of a state nobody can observe directly, which is a hypothesis.
    for posture in intel.postures:
        leading = str(posture.get("leading_state") or "").strip()
        if not leading:
            continue
        node = _snode(
            HYPOTHESIS, leading, role=HIDDEN_STATE_READING, source=source,
            as_of=str(posture.get("as_of") or dossier_as_of), company=company,
            extra={"leading_probability": posture.get("leading_probability"),
                   "alternatives": list(posture.get("alternatives") or ()),
                   "certainty_note": posture.get("certainty_note"),
                   "evidence_ids": [str(e) for e in
                                    (posture.get("evidence_ids") or ()) if e],
                   **common})
        nodes.append(node)
        edges.append(Edge(node.node_id, subject, AFFECTS, derived=False,
                          source=source))

    return nodes, edges


def belief_provenance(context: ExternalContext, *,
                      company: str) -> Dict[str, dict]:
    """For each projected belief: what supports it, what contradicts it.

    THE POINT OF READING THIS BACK FROM THE GRAPH
    ----------------------------------------------
    A surface could compute the same thing straight off `intel.beliefs`, and
    for a while that would agree. It would be a SECOND derivation of one fact,
    and the moment the projection learned something the surface did not -- a
    mismatch attaching to a belief by its falsifier, say -- the page and the
    graph would disagree while both looked right.

    So the support/contradiction structure has exactly one derivation, here,
    from the edges. Support and contradiction stay separate all the way out:
    they are different edge kinds, and nothing merges them into an "evidence"
    count that would let a contradicted belief look corroborated.

    Keyed by proposition, which is what a founder-facing caller has. Absence of
    a key is meaningful and callers must treat it as "no provenance", never as
    "no support" -- the two are different, and only one of them is a finding.
    """
    nodes, edges = project(context, company=company)
    by_id = {n.node_id: n for n in nodes}
    out: Dict[str, dict] = {}
    for node in nodes:
        if node.attrs.get("role") != STRATEGIC_BELIEF:
            continue
        out[node.label] = {
            "node_id": node.node_id, "supports": [], "contradicts": [],
            "limitations": [], "informs": [],
            "maturity": node.attrs.get("maturity"),
            "confidence_is_numeric": node.attrs.get("confidence_is_numeric"),
            "evidence_ids": list(node.attrs.get("evidence_ids") or ()),
            "as_of": node.as_of, "dossier_as_of": node.attrs.get(
                "dossier_as_of"), "schema_version": node.attrs.get(
                "schema_version")}
    ids = {entry["node_id"]: label for label, entry in out.items()}
    for edge in edges:
        label = ids.get(edge.dst)
        if label is not None:
            src = by_id.get(edge.src)
            if src is None:
                continue
            if edge.kind == SUPPORTS:
                out[label]["supports"].append(
                    {"label": src.label,
                     "evidence_ids": list(src.attrs.get("evidence_ids") or ()),
                     "source": src.source})
            elif edge.kind == CONTRADICTS:
                out[label]["contradicts"].append(
                    {"label": src.label,
                     "evidence_ids": list(src.attrs.get("evidence_ids") or ()),
                     "source": src.source})
            elif edge.kind == CONCERNS:
                out[label]["limitations"].append(src.label)
        elif edge.kind == INFORMS and edge.src in ids:
            target = by_id.get(edge.dst)
            if target is not None:
                out[ids[edge.src]]["informs"].append(target.label)
    return out


def project(context: ExternalContext, *, company: str,
            company_node_id: str = "") -> Tuple[List[Node], List[Edge]]:
    """Sanctioned nodes and edges for one company's external context."""
    nodes: List[Node] = []
    edges: List[Edge] = []
    subject = company_node_id or _nid("COMPANY", company, company)
    if not company_node_id:
        # Every edge below points at the subject, so it has to exist. When a
        # caller already has a company node it passes the id and this is
        # skipped, which keeps the projection attachable to a larger graph
        # rather than owning a second copy of the company.
        nodes.append(Node(
            node_id=subject, kind=COMPANY, label=company,
            source="the analysis subject", as_of=context.as_of,
            attrs={"role": "SUBJECT_COMPANY"}))

    payload = (context.market.payload or {}) if context.has_market else {}
    if context.has_market:
        source = ((payload.get("source_lineage") or {}).get("provider")
                  or "public market data")
        as_of = context.market.as_of

        for label, m in (payload.get("price_periods") or {}).items():
            if m.get("value") is None:
                continue
            node = _node(
                MARKET, f"Share price {m['value']:+.2f}% over {m['period']}",
                role=MARKET_OBSERVATION, source=source, as_of=as_of,
                company=company,
                extra={"value": m["value"], "unit": m["unit"],
                       "period": m["period"], "freshness_days":
                           context.market.age_days, "stale":
                           context.market.stale})
            nodes.append(node)
            edges.append(Edge(node.node_id, subject, AFFECTS,
                              derived=False, source=source))

        for label, m in (payload.get("benchmark_relative_periods")
                         or {}).items():
            if m.get("value") is None:
                continue
            bench = (payload.get("benchmark") or {}).get("name", "the market")
            node = _node(
                MARKET,
                f"{abs(m['value']):.2f}pp "
                f"{'ahead of' if m['value'] > 0 else 'behind'} {bench} over "
                f"{m['period']}",
                role=BENCHMARK_COMPARISON, source=source, as_of=as_of,
                company=company,
                extra={"value": m["value"], "unit": m["unit"],
                       "period": m["period"]})
            nodes.append(node)
            edges.append(Edge(node.node_id, subject, AFFECTS,
                              derived=False, source=source))

        vol = payload.get("annualized_volatility") or {}
        if vol.get("value") is not None:
            node = _node(
                RISK, f"Annualised volatility {vol['value']:.1f}%",
                role=VOLATILITY_CONTEXT, source=source, as_of=as_of,
                company=company,
                extra={"value": vol["value"], "unit": vol["unit"],
                       "period": vol["period"], "note": vol.get("note", "")})
            nodes.append(node)
            edges.append(Edge(node.node_id, subject, AFFECTS,
                              derived=False, source=source))

        regime = payload.get("market_regime") or {}
        if regime.get("label"):
            node = _node(
                MARKET, f"The wider market is {regime['label']}",
                role=REGIME_CONTEXT, source=source,
                as_of=regime.get("observation_date", as_of), company=company,
                extra={"basis": regime.get("basis", "")})
            nodes.append(node)
            edges.append(Edge(node.node_id, subject, AFFECTS,
                              derived=False, source=source))

        for event in payload.get("relevant_market_events") or ():
            node = _node(EVENT, event.get("label", ""), role=MARKET_EVENT,
                         source=event.get("source", source),
                         as_of=event.get("date", ""), company=company)
            nodes.append(node)
            edges.append(Edge(node.node_id, subject, AFFECTS,
                              derived=False, source=source))

        for limitation in payload.get("limitations") or ():
            node = _node(RISK, limitation, role=LIMITATION, source=source,
                         as_of=as_of, company=company)
            nodes.append(node)
            edges.append(Edge(node.node_id, subject, CONCERNS,
                              derived=False, source=source))

    # MACRO_FACTOR -affects-> COMPANY -through-> EXPOSURE_MECHANISM
    #                                            -impacts-> DECISION
    for factor in context.macro:
        d = factor.as_dict()
        macro_node = _node(
            MARKET, f"{d['factor']}: {d['change_text']}", role=MACRO_FACTOR,
            source=d["source"], as_of=d["observation_date"], company=company,
            extra={"series_id": d["series_id"], "direction": d["direction"],
                   "unit": d["unit"], "frequency": d["frequency"],
                   "source_url": d["source_url"]})
        mechanism_node = _node(
            ASSUMPTION_KIND, d["company_exposure_mechanism"],
            role=EXPOSURE_MECHANISM, source=d["source"],
            as_of=d["observation_date"], company=company,
            extra={"evidence_ids": list(d["evidence_ids"]),
                   "matched_on": d["matched_on"]})
        decision_node = _node(
            DECISION, d["affected_kpi_or_decision"], role="DECISION",
            source=d["source"], as_of=d["observation_date"], company=company)
        nodes.extend([macro_node, mechanism_node, decision_node])
        edges.append(Edge(macro_node.node_id, subject, AFFECTS,
                              derived=False, source=d["source"]))
        edges.append(Edge(mechanism_node.node_id, macro_node.node_id, CONCERNS,
                              derived=False, source=d["source"]))
        edges.append(Edge(mechanism_node.node_id, decision_node.node_id, MEASURES,
                              derived=False, source=d["source"]))

    for competitor in corroborating(context.competitors):
        d = competitor.as_dict()
        node = _node(
            COMPETITOR, d["name"], role=COMPETITIVE_ALTERNATIVE,
            source=(", ".join(t for t in d["source_titles"] if t)
                    or "retrieved evidence"),
            as_of=d["date"], company=company,
            extra={"relationship": d["relationship"],
                   "overlap": d["overlap"],
                   "evidence_ids": list(d["evidence_ids"]),
                   "relevance": d["relevance"]})
        nodes.append(node)
        edges.append(Edge(node.node_id, subject, COMPETES_WITH,
                              derived=False, source=node.source))

    # Strategic last, and only when the dossier both resolved and carries
    # something. `has_strategic` is the same gate the presenter uses, so a
    # dossier that cannot be shown cannot be projected either -- an unsafe or
    # ambiguously-identified one never reaches here at all, because `resolve`
    # refuses to return it.
    if context.has_strategic:
        s_nodes, s_edges = _project_strategic(
            context.strategic, company=company, subject=subject)
        nodes.extend(s_nodes)
        edges.extend(s_edges)
    return nodes, edges
