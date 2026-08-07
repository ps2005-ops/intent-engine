"""Projecting existing subsystems into the one graph.

WHY THIS IS THE FIRST THING BUILT ON THE GRAPH
----------------------------------------------
The graph shipped with no producers. Every subsystem still owned its own
truth, so the substrate was a fourth parallel structure rather than the
platform's spine -- which is worse than not having built it, because it looks
like integration from the outside.

This is the first real producer: a company-ingestion run becomes evidence,
hypotheses, assumptions and their contradictions, in the shared vocabulary.
Once one subsystem projects, "does everything read the same world?" becomes a
question with a testable answer instead of an intention.

RECONSTRUCTION, NOT DUPLICATION
-------------------------------
The projection is a pure function of the append-only log and the report the
run produced. It stores nothing and owns nothing. Run it twice on the same
run and you get the same graph; run it after the log grows and you get the
newer one. That is the property that keeps the graph from becoming a seventh
source of truth: it cannot disagree with its inputs, because it has none of
its own.

EVERY EDGE HERE IS DERIVED
--------------------------
Nothing in a retrieval log is a judgment. The documents were fetched, the
analyst cited specific observation ids, the blind spots named their own
tensions -- so every edge is recomputable from those rows and none is
recorded. A `recorded` edge appears the moment a human or a model asserts a
link that is not implied by the data, and it will carry an author when it does.
"""
from __future__ import annotations

from typing import Optional, Sequence

from intent_engine.business_graph.model import (
    ASSUMES,
    ASSUMPTION,
    COMPANY,
    CONTRADICTS,
    DOCUMENT,
    EVIDENCE,
    HYPOTHESIS,
    INFORMS,
    SUPPORTS,
    BusinessGraph,
    Edge,
    Node,
)


def _clip(text: str, limit: int = 160) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def from_ingestion_run(*, run_id: str, retrieved: Sequence[dict] = (),
                       report: Optional[dict] = None,
                       graph: Optional[BusinessGraph] = None) -> BusinessGraph:
    """One analysis run, in the shared vocabulary.

    `retrieved` is `IngestionStore.retrieved(run_id)`; `report` is the
    strategic report the run produced, or None for a run that never cleared
    the evidence bar. A bounded run still projects: its documents are real
    and the absence of hypotheses above them is exactly what a founder should
    be able to see.
    """
    graph = graph if graph is not None else BusinessGraph()
    report = report or {}

    # --- documents actually fetched ---------------------------------------
    for doc in retrieved or ():
        source_id = str(doc.get("source_id") or "").strip()
        if not source_id:
            continue
        url = str(doc.get("final_url") or "")
        graph.add_node(Node(
            node_id=f"doc-{source_id}",
            kind=DOCUMENT,
            label=_clip(doc.get("title") or url or source_id),
            # Provenance is the URL it came from, not the run that wanted it.
            source=url or f"ingestion:{run_id}",
            attrs={"run_id": run_id,
                   "source_class": doc.get("source_class") or "",
                   "retrieval_status": doc.get("retrieval_status") or ""}))

    # --- observations the analyst was allowed to cite ----------------------
    observations = [o for o in (report.get("observations") or ())
                    if isinstance(o, dict) and o.get("observation_id")]
    for obs in observations:
        obs_id = str(obs["observation_id"])
        graph.add_node(Node(
            node_id=obs_id,
            kind=EVIDENCE,
            label=_clip(obs.get("excerpt") or obs.get("text") or obs_id),
            source=str(obs.get("source_url") or f"ingestion:{run_id}"),
            as_of=str(obs.get("date") or ""),
            attrs={"run_id": run_id,
                   "source_class": obs.get("source_class") or ""}))

    known = {n.node_id for n in graph.nodes}

    # --- hypotheses, and the evidence under each ---------------------------
    for index, hyp in enumerate(h for h in (report.get("hypotheses") or ())
                                if isinstance(h, dict)):
        hyp_id = str(hyp.get("hypothesis_id") or f"hyp-{run_id}-{index}")
        graph.add_node(Node(
            node_id=hyp_id,
            kind=HYPOTHESIS,
            label=_clip(hyp.get("statement") or hyp.get("title") or hyp_id),
            source=f"analyst:{run_id}",
            confidence=str(hyp.get("confidence") or ""),
            attrs={"run_id": run_id}))
        supporting = (hyp.get("supporting_observation_ids")
                      or hyp.get("strongest_support_ids") or ())
        for obs_id in supporting:
            # A citation to evidence this run never retrieved is not a link
            # to draw -- it is a dangling claim, and the graph refuses those.
            if str(obs_id) in known:
                graph.add_edge(Edge(str(obs_id), hyp_id, SUPPORTS,
                                    derived=True))

    # --- blind spots become assumptions, with their contradictions ---------
    for index, spot in enumerate(b for b in (report.get("blind_spots") or ())
                                 if isinstance(b, dict)):
        spot_id = str(spot.get("blind_spot_id") or f"assume-{run_id}-{index}")
        graph.add_node(Node(
            node_id=spot_id,
            kind=ASSUMPTION,
            label=_clip(spot.get("observed_tension") or spot_id),
            source=f"analyst:{run_id}",
            attrs={"run_id": run_id,
                   "why_it_may_matter": spot.get("why_it_may_matter") or ""}))
        # The tension is what the leading hypothesis is assuming away.
        for hyp_node in graph.of_kind(HYPOTHESIS):
            if hyp_node.attrs.get("run_id") == run_id:
                graph.add_edge(Edge(hyp_node.node_id, spot_id, ASSUMES,
                                    derived=True))
                break
        for obs_id in (spot.get("supporting_observation_ids") or ()):
            if str(obs_id) in known:
                # Evidence under a blind spot is evidence AGAINST the
                # comfortable reading. Recording it as support would bury the
                # one thing the blind spot exists to surface.
                graph.add_edge(Edge(str(obs_id), spot_id, CONTRADICTS,
                                    derived=True))

    return graph


def link_decision(graph: BusinessGraph, *, decision_id: str,
                  hypothesis_ids: Sequence[str], author: str) -> BusinessGraph:
    """Attach a decision to the hypotheses that informed it.

    RECORDED, not derived: nothing in the evidence says a founder decided
    anything because of a hypothesis. That is a judgment, so it carries an
    author and is stored as one -- which is the whole point of the
    distinction.
    """
    if not author:
        raise ValueError("a decision link is a judgment and needs an author")
    for hyp_id in hypothesis_ids:
        graph.add_edge(Edge(hyp_id, decision_id, INFORMS, derived=False,
                            source=author))
    return graph


# ---------------------------------------------------------------------------
# the market-learning engine's strategic dossier
# ---------------------------------------------------------------------------
#: How a market belief's numeric confidence becomes a founder-facing word.
#:
#: The producer states a probability -- 0.586 on every belief in the current
#: corpus, because that is the prior a single evidence item opens a belief at.
#: Printing "59% confident" would be the defect this whole layer exists to
#: prevent: a prior rendered as a measurement. The engine's own mechanism
#: calibration refuses to grade below five informative tests for the same
#: reason.
#:
#: So the word is chosen by TESTING STATUS first and probability second, and
#: an untested belief cannot reach the top band however high its prior.
_DECLARED = "opened by evidence, not yet tested"
_SUPPORTED = "supported by later evidence"
_CONTESTED = "contested by later evidence"


def belief_standing(belief: dict) -> str:
    """The honest one-line standing of a market belief.

    `update_method` is the producer's own record of how the belief reached its
    current state: DECLARED means one evidence item opened it and nothing has
    argued with it since. That is a hypothesis, and it is rendered as one.
    """
    method = str(belief.get("update_method") or "").upper()
    direction = str(belief.get("direction_of_last_change") or "").upper()
    if method == "DECLARED" or not direction:
        return _DECLARED
    if direction in ("DOWN", "WEAKENED", "CONTRADICTED"):
        return _CONTESTED
    return _SUPPORTED


def from_strategic_dossier(*, company_id: str, company_label: str = "",
                           beliefs: Sequence[dict] = (),
                           as_of: str = "", dossier_revision: str = "",
                           graph: Optional[BusinessGraph] = None
                           ) -> BusinessGraph:
    """A market dossier's beliefs, in the shared vocabulary.

    WHY THIS EXISTS
    ---------------
    The market engine publishes beliefs. The founder's strategic renderer read
    interactions, postures, mismatches, reactions and priorities -- everything
    EXCEPT beliefs. So a dossier whose only content was a belief passed
    validation, was counted as carrying material, opened a strategic section,
    and put nothing under it. Three layers of the same disconnection: a schema
    the consumer rejected, a refusal indistinguishable from absence, and a
    renderer that did not read the one kind of content the producer makes.

    A market belief is a HYPOTHESIS about a COMPANY, SUPPORTED by EVIDENCE.
    That is already the graph's vocabulary, so nothing new is invented here --
    which is the point. Routing through the graph rather than rendering the
    dossier JSON directly is what makes a founder-visible sentence traceable
    back to an evidence id.

    Pure, like every other projection: it stores nothing and owns nothing, so
    it cannot disagree with the dossier it was built from.
    """
    graph = graph or BusinessGraph()
    company_node = f"company:{company_id}"
    graph.add_node(Node(
        node_id=company_node, kind=COMPANY,
        label=company_label or company_id,
        source=f"market dossier {dossier_revision or as_of}".strip(),
        as_of=as_of))

    for index, belief in enumerate(beliefs):
        proposition = _clip(belief.get("proposition") or "", 240)
        if not proposition:
            continue
        # Keyed on the dossier revision so a later revision is a NEW node
        # rather than a silent overwrite of what a founder was previously
        # shown. The graph is append-only about what was believed when.
        belief_node = f"market-belief:{company_id}:{dossier_revision or as_of}:{index}"
        graph.add_node(Node(
            node_id=belief_node, kind=HYPOTHESIS, label=proposition,
            source=f"market dossier {dossier_revision or as_of}".strip(),
            confidence=belief_standing(belief),
            as_of=str(belief.get("last_updated") or as_of),
            attrs={
                "origin": "market_learning_engine",
                "company_id": company_id,
                "subject": belief.get("subject") or company_label,
                "basis": _clip(belief.get("basis") or "", 240),
                "update_method": belief.get("update_method") or "",
                "limitations": list(belief.get("limitations") or ()),
                "dossier_revision": dossier_revision or as_of,
            }))
        # Derived: the dossier says this belief is about this company, so
        # nobody asserted the link and nobody can be wrong about it.
        graph.add_edge(Edge(src=belief_node, dst=company_node,
                            kind=INFORMS, derived=True,
                            source="market dossier"))

        for evidence_id in (belief.get("evidence_ids") or ()):
            evidence_node = f"market-evidence:{evidence_id}"
            graph.add_node(Node(
                node_id=evidence_node, kind=EVIDENCE,
                label=f"market evidence {evidence_id}",
                source="market learning ledger", as_of=as_of,
                attrs={"evidence_id": evidence_id,
                       "origin": "market_learning_engine"}))
            graph.add_edge(Edge(src=evidence_node, dst=belief_node,
                                kind=SUPPORTS, derived=True,
                                source="market dossier"))
    return graph
