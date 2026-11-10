"""Company evidence -> shared economic nodes (the company->market direction).

WHAT CROSSES, AND WHAT EXPLICITLY DOES NOT
-------------------------------------------
What crosses: statements companies made in public about hiring, pricing,
capacity, inventories, demand, financing, guidance and supply. Those are
attributable, checkable, and exactly what a macro analyst would read if they
had the patience for four hundred filings.

What does not cross, ever: anything about who used the product. Which
companies visitors typed into the demo, how often a name was searched, how
long anyone read a page. That would be a signal about who linked to the
product this week, and using it would create a privacy exposure, an
uncorrectable sampling bias, and a manipulation surface -- anyone who can type
into a public box could move a "macro indicator". There is no function in
this module that takes a query, a session, a visitor or a count of either.

PUBLIC ONLY, DECIDED HERE
-------------------------
`visibility` is set from the document's own provenance. A retrieved public
filing or web page is PUBLIC. Anything a tenant supplied is TENANT_PRIVATE
and `assert_public` downstream will refuse it -- which is the intended
behaviour: private material informs that tenant's own CompanyEconomicState
and may never reach an aggregate.

THE PUBLISHER IS THE AUTHOR, NOT THE VENUE
-------------------------------------------
This has cost this repository twice. Grouping by host made every SEC filing
one origin, so twenty companies' filings counted as one independent source.
The node's `publisher` is the company that WROTE the statement; `venue` is
where it appeared. `lineage.independent` reads the publisher.

A THIRD PARTY'S FILING IS NOT THE SUBJECT'S STATEMENT
------------------------------------------------------
A filing by another registrant that mentions the subject is evidence, and it
is evidence AUTHORED BY THAT REGISTRANT. `publisher` is set to the filer, not
to the subject, so a rival's description of the market does not enter the
graph as the subject's own account of itself.
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from intent_engine.econ import evidence as EV
from intent_engine.econ import exposure as EXP
from intent_engine.econ import vocabulary as V

CONTRACT = "econ_evidence_bridge.v1"

PRODUCER = "founder"

#: Filing propositions and strategic signals -> shared COMPANY node kinds.
#:
#: Only signals that carry ECONOMIC content are mapped. A signal about how a
#: company words its pricing page tells you about its go-to-market and
#: nothing about the price level, so `pricing_published` is absent while
#: `pricing_exposure` is present. An unmapped signal does not cross, and
#: `translate` counts what it declined.
SIGNAL_MAP = {
    # filing propositions (`strategic_intelligence.filing_detectors`)
    "revenue_trajectory": "revenue",
    "margin_trajectory": "margin",
    "capital_intensity": "capex",
    "expansion_within_customers": "demand_language",
    "recurring_revenue_base": "rpo",
    "supplier_dependency": "supply_constraint",
    "pricing_exposure": "pricing",
    "liquidity_position": "financing",
    "geographic_exposure": "regional_weakness",
    "competitive_intensity": "pricing",
    "acquisition_activity": "capex",
    # strategic signals with economic content
    "hiring": "hiring",
    "capacity_expansion": "capex",
    "inventory": "inventory",
    "guidance": "guidance",
    "wage_pressure": "wage_pressure",
    "customer_concentration": "customer_concentration",
}

#: Direction words the founder-side detectors already emit, normalised to the
#: prefixes `aggregates._direction_of` reads. A statement with no direction
#: contributes to no index -- which is correct, because "the company
#: discussed hiring" is not a reading of hiring.
_RISING = ("increas", "grew", "grow", "rose", "rising", "expand", "added",
           "accelerat", "higher", "up ", "strengthen", "tighten")
_FALLING = ("decreas", "fell", "declin", "falling", "contract", "reduc",
            "slow", "lower", "cut", "weaken", "soften", "eas")


def _direction_prefix(text: str) -> str:
    """Turn a company statement into the direction prefix the index reads.

    Returns "" when the statement does not state a direction, and "" is a
    real answer: an observation with no direction is not a reading, and
    defaulting it to flat would make silence look like stability.
    """
    low = " " + text.lower()
    first_rise = min((low.find(w) for w in _RISING if w in low), default=-1)
    first_fall = min((low.find(w) for w in _FALLING if w in low), default=-1)
    if first_rise < 0 and first_fall < 0:
        return ""
    if first_fall < 0 or (0 <= first_rise < first_fall):
        return "rising: "
    return "falling: "


def _visibility(doc: dict) -> str:
    """PUBLIC unless the document came from a tenant.

    Fails CLOSED: a document with no provenance at all is treated as private,
    because an unlabelled document of unknown origin is exactly the one that
    must not enter a public aggregate.
    """
    if doc.get("tenant") or doc.get("tenant_private"):
        return V.TENANT_PRIVATE
    if not (doc.get("origin") or doc.get("final_url") or doc.get("url")):
        return V.TENANT_PRIVATE
    return V.PUBLIC


def _publisher(doc: dict, *, subject_name: str) -> str:
    """Who WROTE this. The filer for a third-party filing; else the subject.

    `source_class == "competitor"` is how this codebase labels a document
    authored by someone other than the subject. Its author is that someone,
    and recording the subject as the publisher would let a rival's account of
    the market corroborate the subject's own.
    """
    if (doc.get("source_class") or "") == "competitor":
        return (str(doc.get("filer") or doc.get("source_title") or "").strip()
                or "another registrant")
    return subject_name or str(doc.get("source_title") or "").strip()


def translate(observations: Sequence[dict], *, company_id: str,
              company_name: str, as_of: str,
              documents: Sequence[dict] = ()) -> dict:
    """Founder-side observations -> shared COMPANY evidence nodes.

    Returns the nodes AND an account of what did not cross. A translator that
    returns only its output makes a 90% loss rate invisible, and this
    project's funnel work exists because that happened.
    """
    by_id = {str(d.get("source_id") or d.get("document_id") or ""): d
             for d in documents}
    nodes: List[EV.EconomicNode] = []
    unmapped: Dict[str, int] = {}
    directionless = 0
    private = 0
    undated = 0

    for obs in observations:
        if not isinstance(obs, dict):
            continue
        signals = [s for s in (obs.get("signals") or ()) if s]
        mapped = [(s, SIGNAL_MAP[s]) for s in signals if s in SIGNAL_MAP]
        if not mapped:
            for s in signals:
                unmapped[s] = unmapped.get(s, 0) + 1
            continue

        source_ref = ((obs.get("source_refs") or [{}])[0]
                      if obs.get("source_refs") else {})
        doc = by_id.get(str(source_ref.get("artifact_id") or ""), {})
        doc = dict(doc, **{k: v for k, v in obs.items()
                           if k in ("origin", "source_class", "date")})

        visibility = _visibility(doc)
        if visibility != V.PUBLIC:
            private += 1
            continue

        occurred = str(obs.get("date") or doc.get("date") or "")[:10]
        if not occurred:
            undated += 1
            continue

        text = " ".join(str(x) for x in
                        (obs.get("excerpt") or "", obs.get("text") or ""))
        prefix = _direction_prefix(text)
        if not prefix:
            directionless += 1
            continue

        publisher = _publisher(doc, subject_name=company_name)
        for signal, kind in mapped:
            nodes.append(EV.node(
                node_class=V.COMPANY, kind=kind, subject=company_id,
                standing=V.OBSERVED, occurred_at=occurred,
                # A retrieved public document was knowable the day it was
                # dated. `available_at` is not the retrieval date: reading it
                # late does not make it unknowable earlier, and using the
                # retrieval date would let a backfill invent foresight in the
                # other direction.
                available_at=occurred, publisher=publisher,
                statement=(prefix + str(obs.get("excerpt")
                                        or obs.get("text") or "")[:400]),
                confidence=0.6 if obs.get("evidence_quality") == "strong"
                else 0.4,
                visibility=V.PUBLIC,
                venue=str(doc.get("origin") or obs.get("origin") or ""),
                url=str(obs.get("origin") or ""),
                document_id=str(source_ref.get("artifact_id") or ""),
                producer=PRODUCER))

    # THE EXPOSURES, READ FROM THE WHOLE DOCUMENT.
    #
    # This is the repair the cross-domain measurement asked for. The market
    # engine conditions a macro state on a company through
    # `company_exposure`, and its corpus is news headlines: 131 rows and
    # 19,415 characters across six companies produced ONE exposure. The same
    # patterns over the documents this function already holds -- 46 filings,
    # 3,564,390 characters -- produce 39.
    #
    # It happens HERE rather than downstream because this is the last place
    # the full document exists. An observation carries a 400-character
    # excerpt, and the sentence that establishes an exposure is usually not
    # in it: Item 7A is not what a marketing page's excerpt selector picks.
    exposures = EXP.read([d.get("text_content") or "" for d in documents],
                         company_id=company_id) if documents else []

    return {
        "contract": CONTRACT, "company_id": company_id, "as_of": as_of,
        "nodes": nodes,
        "exposures": exposures,
        "offered": len(observations),
        "translated": len(nodes),
        # Every reason a document did not cross, named. The sum of these plus
        # `translated` must account for everything offered, and
        # `test_econ_bridges.py` asserts that it does -- an unexplained
        # residue is where a silent loss hides.
        "declined": {
            "no_economic_signal": sum(unmapped.values()),
            "unmapped_signals": unmapped,
            "no_direction_stated": directionless,
            "tenant_private": private,
            "undated": undated,
        },
    }
