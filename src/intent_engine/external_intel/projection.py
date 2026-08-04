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
from typing import List, Optional, Sequence, Tuple

from intent_engine.business_graph.model import (
    AFFECTS, ASSUMPTION, COMPANY, COMPETES_WITH, COMPETITOR, CONCERNS,
    DECISION, EVENT, MARKET, MEASURES, RISK, Edge, Node,
)

#: The graph has no dedicated "assumption about the outside world" kind, and an
#: exposure mechanism is exactly that: a claim about how this company is
#: connected to a condition, which later evidence can support or contradict.
ASSUMPTION_KIND = ASSUMPTION

from .competitor_contract import Competitor, corroborating
from .macro_contract import MacroFactor
from .pack import ExternalContext

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
    return nodes, edges
