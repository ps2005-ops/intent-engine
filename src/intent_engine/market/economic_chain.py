"""The transmission written out, including the parts that are missing.

WHY A CHAIN AND NOT A CONCLUSION
--------------------------------
"Honda's demand is strengthening" is a conclusion. What a reader needs is the
route the claim travels and the point at which it stops being carried:

    macro -> customer -> orders -> backlog -> revenue -> margin -> guidance

Written out, the gap becomes the finding. This engine has no orders data, no
backlog data and no customer-state data for any company, so those nodes are
UNKNOWN — and a chain that says UNKNOWN in three places is worth more than a
complete-looking one, because the complete one would have had to invent them.

A CHAIN WITH UNKNOWN LINKS IS VALID. A FABRICATED COMPLETE CHAIN IS NOT.

WHY NO LINK IS EVER `OBSERVED`
------------------------------
`OBSERVED` is in the vocabulary because the concept has to be nameable, and
it is STRUCTURALLY UNREACHABLE: no constructor in this module can produce it,
and a test proves it. Events are observed. The link between two events is
inferred, always, and a status vocabulary that offers `OBSERVED` for links
invites exactly the promotion this project has repeatedly had to take back.

Even when the company itself states the attribution — Honda's filing says
operating profit rose "due mainly to the impact of EV-related..." — that is
an OBSERVED STATEMENT by an interested party about a link, not an observed
link. It raises the link to SUPPORTED and simultaneously supplies the
alternative explanation, which is the most useful thing a filing can do.

THE WEAKEST LINK IS THE OUTPUT
------------------------------
Not the conclusion, not the confidence. A reader's next action is decided by
where the chain is thinnest, so `weakest_link` is computed rather than
narrated, and it names the evidence that would resolve it.
"""
from __future__ import annotations

import collections
import hashlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

CONTRACT = "economic_chain.v1"

# --- node types -------------------------------------------------------------
MACRO_STATE = "MACRO_STATE"
CUSTOMER_STATE = "CUSTOMER_STATE"
SUPPLIER_STATE = "SUPPLIER_STATE"
COMPANY_DEMAND = "COMPANY_DEMAND"
ORDERS = "ORDERS"
BACKLOG = "BACKLOG"
PRICING = "PRICING"
MARGIN = "MARGIN"
CAPEX = "CAPEX"
HIRING = "HIRING"
GUIDANCE = "GUIDANCE"
OUTCOME = "OUTCOME"

# --- states above the company ----------------------------------------------
# The roadmap needs macro, credit and capital conditions to sit on the SAME
# graph as the company chain, or transmission has to cross two models and
# every link between them becomes untyped. `MACRO_STATE` already existed and
# already carries the shape: a dated condition, evidenced, that a link can
# run from. These four extend that vocabulary and nothing else — no new
# graph, no parallel store, no second set of link rules.
#
# They are DECLARED and currently UNPOPULATED, which is the same position
# `COMPETES_WITH` held before wave 5. A node type with no instances is not a
# claim that the data exists.
ECONOMIC_FACTOR = "ECONOMIC_FACTOR"   # an input price, a rate, a tariff
CREDIT_STATE = "CREDIT_STATE"         # spreads, issuance, covenant pressure
CAPITAL_STATE = "CAPITAL_STATE"       # funding availability and its cost
INDUSTRY_STATE = "INDUSTRY_STATE"     # a condition shared by a whole sector

NODE_TYPES = (MACRO_STATE, CUSTOMER_STATE, SUPPLIER_STATE, COMPANY_DEMAND,
              ORDERS, BACKLOG, PRICING, MARGIN, CAPEX, HIRING, GUIDANCE,
              OUTCOME,
              ECONOMIC_FACTOR, CREDIT_STATE, CAPITAL_STATE, INDUSTRY_STATE)

# --- statuses ---------------------------------------------------------------
KNOWN = "KNOWN"                # a node: the engine has dated evidence for it
OBSERVED = "OBSERVED"          # a link: NAMEABLE, STRUCTURALLY UNREACHABLE
SUPPORTED = "SUPPORTED"        # a link: evidence at both ends + a stated
                               #         mechanism + a discriminating test
HYPOTHESIZED = "HYPOTHESIZED"  # a link: evidence at both ends, no test
UNKNOWN = "UNKNOWN"            # a link or node: one end has no evidence

LINK_STATUSES = (OBSERVED, SUPPORTED, HYPOTHESIZED, UNKNOWN)
NODE_STATUSES = (KNOWN, UNKNOWN)

#: Ranked worst-first. The weakest link is a lookup, not a judgement call.
_WEAKNESS = {UNKNOWN: 0, HYPOTHESIZED: 1, SUPPORTED: 2, OBSERVED: 3}


class ChainRejected(ValueError):
    """The chain was asked to assert something its evidence cannot carry."""


@dataclass(frozen=True)
class Node:
    node_id: str
    node_type: str
    statement: str
    status: str
    evidence_ids: Tuple[str, ...] = ()
    observed_at: str = ""

    def as_dict(self) -> dict:
        return {"node_id": self.node_id, "node_type": self.node_type,
                "statement": self.statement, "status": self.status,
                "evidence_ids": list(self.evidence_ids),
                "observed_at": self.observed_at}


@dataclass(frozen=True)
class Link:
    source: str
    target: str
    status: str
    evidence: str
    alternative_explanation: str
    falsifier: str
    mechanism: str = ""

    def as_dict(self) -> dict:
        return {"source": self.source, "target": self.target,
                "status": self.status, "mechanism": self.mechanism,
                "evidence": self.evidence,
                "alternative_explanation": self.alternative_explanation,
                "falsifier": self.falsifier}


@dataclass(frozen=True)
class EconomicChain:
    chain_id: str
    subject: str
    nodes: Tuple[Node, ...]
    links: Tuple[Link, ...]
    overall_status: str
    weakest_link: Optional[Link]
    decision_relevance: str
    provenance: Dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "contract": CONTRACT, "chain_id": self.chain_id,
            "subject": self.subject,
            "nodes": [n.as_dict() for n in self.nodes],
            "links": [l.as_dict() for l in self.links],
            "overall_status": self.overall_status,
            "weakest_link": (self.weakest_link.as_dict()
                             if self.weakest_link else None),
            "decision_relevance": self.decision_relevance,
            "provenance": dict(self.provenance),
            "known_nodes": sum(1 for n in self.nodes if n.status == KNOWN),
            "unknown_nodes": sum(1 for n in self.nodes if n.status == UNKNOWN),
            "by_link_status": dict(collections.Counter(
                l.status for l in self.links)),
        }

    def founder_translation(self) -> dict:
        """What is established, what is plausible, what is missing, and why."""
        known = [n for n in self.nodes if n.status == KNOWN]
        unknown = [n for n in self.nodes if n.status == UNKNOWN]
        supported = [l for l in self.links if l.status == SUPPORTED]
        hypothesised = [l for l in self.links if l.status == HYPOTHESIZED]
        weakest = self.weakest_link
        return {
            "established": [f"{n.node_type}: {n.statement}" for n in known],
            "plausible_mechanism": [
                f"{l.source} → {l.target}: {l.mechanism}"
                for l in supported + hypothesised],
            "missing": [f"{n.node_type}: nothing in the ledger measures this"
                        for n in unknown],
            "weakest_link": (f"{weakest.source} → {weakest.target}"
                             if weakest else ""),
            "what_would_resolve_it": weakest.falsifier if weakest else "",
            "why_it_matters": self.decision_relevance,
            "caution": ("every link below SUPPORTED is a route the evidence "
                        "does not yet carry; an UNKNOWN node is a gap in the "
                        "engine's sources, not a statement that nothing is "
                        "happening there"),
        }


def node(*, node_type: str, statement: str, evidence_ids: Sequence[str] = (),
         observed_at: str = "") -> Node:
    """A node is KNOWN when dated evidence names it, and UNKNOWN otherwise.

    There is no third option and no way to assert a node without evidence:
    "we believe orders are strong" is a node the chain refuses to hold.
    """
    if node_type not in NODE_TYPES:
        raise ChainRejected(f"unknown node type {node_type!r}")
    ids = tuple(e for e in evidence_ids if e)
    return Node(
        node_id=f"{node_type.lower()}",
        node_type=node_type, statement=statement,
        status=(KNOWN if ids else UNKNOWN), evidence_ids=ids,
        observed_at=observed_at)


def link(*, source: Node, target: Node, mechanism: str,
         alternative_explanation: str, falsifier: str,
         discriminating_test: str = "") -> Link:
    """Admit a link at the strongest status its evidence actually supports.

    The ladder, and there is no argument that climbs it:

        UNKNOWN       either end has no evidence. Nothing to link.
        HYPOTHESIZED  both ends observed, a mechanism stated, no test.
        SUPPORTED     the above, plus a test that could have come back the
                      other way and did not.

    `OBSERVED` is never returned. See the module docstring.
    """
    if not mechanism.strip():
        raise ChainRejected(
            "a link without a stated mechanism is an arrow, and an arrow is "
            "not a claim anybody can argue with")
    if not alternative_explanation.strip():
        raise ChainRejected(
            "a link without a competing explanation cannot be wrong, and a "
            "link that cannot be wrong is not evidence of anything")
    if not falsifier.strip():
        raise ChainRejected("a link must name what would break it")

    if source.status == UNKNOWN or target.status == UNKNOWN:
        status = UNKNOWN
        evidence = (f"no evidence for "
                    f"{source.node_type if source.status == UNKNOWN else target.node_type}")
    elif discriminating_test.strip():
        status = SUPPORTED
        evidence = discriminating_test
    else:
        status = HYPOTHESIZED
        evidence = (f"both ends observed "
                    f"({', '.join(source.evidence_ids[:2])} → "
                    f"{', '.join(target.evidence_ids[:2])}), no test has "
                    f"separated this route from the alternative")
    return Link(source=source.node_type, target=target.node_type,
                status=status, evidence=evidence, mechanism=mechanism,
                alternative_explanation=alternative_explanation,
                falsifier=falsifier)


def chain(*, subject: str, nodes: Sequence[Node], links: Sequence[Link],
          decision_relevance: str,
          provenance: Optional[Dict[str, str]] = None) -> EconomicChain:
    """Assemble a chain and compute — never assert — its overall standing."""
    if not nodes:
        raise ChainRejected("a chain with no nodes describes nothing")
    # Weakest first; among equally weak links, the one FURTHEST along the
    # route. Three consecutive UNKNOWN links at the start of a chain are one
    # finding, and the useful place to name it is the boundary — the last
    # unmeasured step before the measured ones — because that is where
    # resolving one link would first change what a reader can rely on.
    ranked = sorted(enumerate(links),
                    key=lambda pair: (_WEAKNESS.get(pair[1].status, 0),
                                      -pair[0]))
    weakest = ranked[0][1] if ranked else None
    statuses = {l.status for l in links}
    if UNKNOWN in statuses:
        overall = UNKNOWN
    elif statuses == {SUPPORTED}:
        overall = SUPPORTED
    else:
        overall = HYPOTHESIZED
    raw = f"{subject}|{'|'.join(n.node_type for n in nodes)}"
    return EconomicChain(
        chain_id="chain_" + hashlib.sha256(raw.encode()).hexdigest()[:12],
        subject=subject, nodes=tuple(nodes), links=tuple(links),
        overall_status=overall, weakest_link=weakest,
        decision_relevance=decision_relevance,
        provenance=dict(provenance or {}))


# --- candidate scoring ------------------------------------------------------
#
# Which subject deserves a chain is a measurement, not a preference. Fame is
# explicitly excluded: the most-covered company is the one whose story is
# already priced, and the engine's job is not to restate it.
def score_candidates(rows: Sequence[dict]) -> Tuple[dict, ...]:
    """Rank subjects by how much of a chain their real evidence could carry."""
    evidence = collections.defaultdict(list)
    for row in rows:
        if row.get("record") == "evidence" and row.get("subject_company"):
            evidence[row["subject_company"]].append(row)
    resolved = collections.Counter(
        r.get("subject") for r in rows
        if r.get("record") == "reconciliation"
        and r.get("outcome") in ("CONFIRMED", "CONTRADICTED",
                                 "PARTIALLY_CONFIRMED"))

    out: List[dict] = []
    for subject, items in evidence.items():
        types = {str(e.get("evidence_type") or "") for e in items}
        primary = sum(1 for e in items
                      if e.get("source_role") == "regulatory_filing")
        stages = len(types & {"EARNINGS_RESULT", "GUIDANCE_REVISION",
                              "PRICING_SIGNAL", "CAPEX_SIGNAL",
                              "PROCUREMENT_SIGNAL", "CONTRACT_AWARD"})
        out.append({
            "subject": subject, "observations": len(items),
            "distinct_event_types": len(types),
            "primary_source_observations": primary,
            "sequence_stages_covered": stages,
            "resolved_expectations": resolved.get(subject, 0),
            # Weighted so a company with a RESOLVED expectation and PRIMARY
            # sources outranks one with more headlines. Coverage of the chain
            # matters more than volume, and a filing outranks a rewrite.
            "score": (stages * 4 + resolved.get(subject, 0) * 3
                      + primary + len(items) // 10),
        })
    return tuple(sorted(out, key=lambda r: -r["score"]))


# --- building a chain from the real ledger ---------------------------------
#
# Which node an observation lands on, and nothing else. An event type this map
# does not name contributes no node, because guessing which stage of the
# transmission an unclassified headline belongs to is how a chain acquires
# links its evidence never supported.
_NODE_OF_EVENT: Dict[str, str] = {
    "EARNINGS_RESULT": COMPANY_DEMAND,
    "EARNINGS_SURPRISE": OUTCOME,
    "GUIDANCE_REVISION": GUIDANCE,
    "PRICING_SIGNAL": MARGIN,
    "CAPEX_SIGNAL": CAPEX,
    "PROCUREMENT_SIGNAL": ORDERS,
    "CONTRACT_AWARD": ORDERS,
}

#: The route, in order, with each step's mechanism, its competing story and
#: what would break it. Written once, here, so a chain cannot acquire a link
#: nobody wrote down the reasoning for.
_ROUTE: Tuple[Tuple[str, str, str, str, str], ...] = (
    (MACRO_STATE, CUSTOMER_STATE,
     "conditions in the economy move the budgets of the company's customers",
     "the customers' budgets moved for a reason specific to their own "
     "industry and not to the macro state",
     "customer spending diverges from the macro series over a full cycle"),
    (CUSTOMER_STATE, ORDERS,
     "customers with larger budgets place more orders",
     "orders moved on a pricing or share change rather than on customer "
     "budgets",
     "order intake moves while customer budgets are flat"),
    (ORDERS, COMPANY_DEMAND,
     "order intake precedes recognised revenue by roughly a quarter",
     "revenue moved on a mix or currency effect with no change in units",
     "revenue moves in the opposite direction to order intake"),
    (COMPANY_DEMAND, MARGIN,
     "volume growth spreads fixed cost over more units, so margin follows "
     "revenue when price and cost are steady",
     "margin moved on an input cost, a currency effect, or a one-off item "
     "in the base period, with demand contributing nothing",
     "margin moves while revenue is flat, or the company attributes the "
     "margin move to something other than volume"),
    (MARGIN, GUIDANCE,
     "a company raises its own forecast when the quarter's margin gives it "
     "room to",
     "guidance was raised on currency, on a divestiture, or to manage "
     "expectations, independent of the quarter's margin",
     "guidance is raised in a quarter where margin fell"),
    (GUIDANCE, OUTCOME,
     "raised guidance is the company committing to a level the next period "
     "must clear",
     "the outcome was decided by the market's prior expectation rather "
     "than by the guidance itself",
     "the next reported period misses the raised guidance"),
)


#: A MAGNITUDE, not any digit. "for the fiscal first quarter ended June 30,
#: 2026" is full of digits and states no quantity; a node needs the sentence
#: that carries the number the chain is about.
_FIGURE = __import__("re").compile(
    r"(?:\d[\d,.]*\s*%|\b\d[\d,.]*\s*(?:billion|million|bn|mn|trillion)\b"
    r"|[$€£¥]\s?\d|\b(?:JPY|USD|EUR|GBP|CAD|CNY|INR)\s?\d)",
    __import__("re").I)
#: A company naming a cause for its own numbers. Deliberately narrow: these
#: are attribution phrases, not any use of "because".
_BECAUSE = __import__("re").compile(
    r"\b(?:due (?:mainly |primarily |largely )?to|attributable to|"
    r"driven (?:mainly |primarily |largely )?by|reflecting|as a result of|"
    r"owing to|on account of)\b(.{10,180})", __import__("re").I)


def _carries_a_figure(row: dict) -> bool:
    if row.get("numeric_values"):
        return True
    return bool(_FIGURE.search(str(row.get("fact") or "")))


def _stated_cause(text: str) -> str:
    hit = _BECAUSE.search(text or "")
    if not hit:
        return ""
    return " ".join((hit.group(0)).split())[:200]


def build(rows: Sequence[dict], *, subject: str,
          attributions: Sequence[Tuple[str, str]] = (),
          macro=None) -> EconomicChain:
    """Build one subject's chain from its real evidence, gaps included.

    `macro` is a `macro_state.EconomicState` — the condition this chain hangs
    from. WITHOUT IT EVERY CHAIN IS DECAPITATED: the ledger only holds
    company-scoped evidence, so MACRO_STATE had no possible source and stood
    UNKNOWN on every subject, which pinned the first link at UNKNOWN and the
    whole chain with it. Measured on the live ledger before this existed:
    4 known nodes, 3 unknown, and not one SUPPORTED link.

    It is passed in rather than read from `rows` because a macro observation
    is deliberately not company-scoped. A national figure filed under a
    company would be read as a fact about that company, which is the exact
    confusion the macro contract refuses to allow.

    A macro state that does not ANCHOR (hypothesised, or unknown) leaves the
    node UNKNOWN. Somebody's opinion about the economy is not a measurement of
    it, and a chain resting on an opinion must not read as a measured one.

    `attributions` are (node_type, statement) pairs where the SOURCE DOCUMENT
    ITSELF attributes one node's movement to something. Honda's filing says
    operating profit rose "due mainly to the impact of EV-related" items —
    the company naming a cause for its own margin move. That does not promote
    the demand→margin link; it is the strongest available statement of the
    ALTERNATIVE, and it is what makes that link the weakest one.
    """
    mine = [r for r in rows if r.get("record") == "evidence"
            and r.get("subject_company") == subject]
    by_node: Dict[str, List[dict]] = collections.defaultdict(list)
    for row in mine:
        target = _NODE_OF_EVENT.get(str(row.get("evidence_type") or ""))
        if target:
            by_node[target].append(row)

    stated = dict(attributions)
    # A document that attributes its own movement is the strongest available
    # statement of the ALTERNATIVE, and it is read off the evidence rather
    # than supplied by a caller — a chain that only knows what it was told
    # is not reading the ledger.
    for node_type, items in by_node.items():
        if node_type in stated:
            continue
        for row in items:
            because = _stated_cause(str(row.get("fact") or ""))
            if because:
                stated[node_type] = (
                    f"the source document itself attributes this: "
                    f"\u201c{because}\u201d")
                break
    nodes: Dict[str, Node] = {}
    for node_type in NODE_TYPES:
        items = by_node.get(node_type, [])
        # A node is a QUANTITY, so the observation that carries one outranks
        # the observation that announces it. "Honda announced its results" and
        # "revenue increased by 13.5% to JPY 6,061.5 billion" are the same
        # filing on the same day; only the second is a node. Primary source
        # first, then the one with figures in it.
        items.sort(key=lambda e: (e.get("source_role") != "regulatory_filing",
                                  not _carries_a_figure(e),
                                  e.get("observed_at", "")))
        statement = (str(items[0].get("fact") or "")[:240] if items
                     else f"no observation in the ledger measures {node_type}")
        nodes[node_type] = node(
            node_type=node_type, statement=statement,
            evidence_ids=tuple(str(e.get("evidence_id") or "")
                               for e in items[:3]),
            observed_at=str(items[0].get("observed_at") or "")[:10]
            if items else "")

    # The economy, if the engine measured it. This REPLACES the placeholder
    # built above, which can only ever be UNKNOWN: no company-scoped evidence
    # row describes a national condition, so the top of every chain was
    # structurally unreachable rather than merely unobserved.
    if macro is not None and getattr(macro, "anchors", False):
        seen = macro.observation
        nodes[MACRO_STATE] = node(
            node_type=MACRO_STATE,
            statement=macro.reason or f"{macro.state_kind} was measured",
            evidence_ids=(seen.observation_id,) if seen else (),
            observed_at=(seen.reference_period[:10] if seen else ""))

    links: List[Link] = []
    for source, target, mechanism, alternative, falsifier in _ROUTE:
        if target in stated:
            alternative = stated[target]
        links.append(link(source=nodes[source], target=nodes[target],
                          mechanism=mechanism,
                          alternative_explanation=alternative,
                          falsifier=falsifier))

    used = [n for n in nodes.values()
            if n.node_type in {s for s, *_ in _ROUTE} |
            {t for _, t, *_ in _ROUTE}]
    known = [n for n in used if n.status == KNOWN]
    return chain(
        subject=subject, nodes=tuple(used), links=tuple(links),
        decision_relevance=(
            f"{len(known)} of {len(used)} stages of the transmission are "
            f"measured for {subject}; a reader acting on the conclusion is "
            f"relying on the unmeasured ones holding"),
        provenance={"source": "market learning ledger",
                    "observations": str(len(mine)),
                    "primary_source_observations": str(sum(
                        1 for e in mine
                        if e.get("source_role") == "regulatory_filing"))})


def summarise(chains: Sequence[EconomicChain]) -> dict:
    links = [l for c in chains for l in c.links]
    return {
        "contract": CONTRACT,
        "chains": len(chains),
        "subjects": sorted({c.subject for c in chains}),
        "links": len(links),
        "by_link_status": dict(collections.Counter(l.status for l in links)),
        "observed_links": sum(1 for l in links if l.status == OBSERVED),
        "weakest_links": [
            {"subject": c.subject,
             "link": f"{c.weakest_link.source} → {c.weakest_link.target}",
             "status": c.weakest_link.status,
             "resolved_by": c.weakest_link.falsifier}
            for c in chains if c.weakest_link],
        "note": ("a chain with UNKNOWN links is valid; a complete-looking "
                 "chain built over missing nodes is not. No link is ever "
                 "OBSERVED: events are observed, links are inferred"),
    }
