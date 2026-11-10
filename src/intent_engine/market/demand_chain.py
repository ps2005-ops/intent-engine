"""Demand, as nine different things that are constantly mistaken for one.

WHY THIS IS NOT ONE NUMBER
--------------------------
"Demand is strengthening" is the conclusion a reader wants and almost never the
fact a document supports. The document says backlog rose, or bookings rose, or
revenue rose, and each of those is compatible with demand strengthening AND
with something else entirely:

    backlog UP        can be demand rising, or shipments slipping, or a
                      supply constraint holding orders unfulfilled
    revenue UP        can be new demand, or an acquisition, or price, or a
                      backlog being drained while orders fall
    bookings UP       can be demand, or a pull-forward ahead of a price rise
    shipments UP      can be demand, or a factory catching up

So the chain has nine distinct states, each link between them carries its own
standing, and NOTHING promotes one link on the strength of another. A chain
whose middle is missing is reported with a hole in it; it is not smoothed.

THE ONE INFERENCE THIS MODULE REFUSES
-------------------------------------
`implies_demand` raises. Every reader eventually wants to ask a backlog figure
what it means for demand, and the plausible answer is always available. It is
also the exact error the module exists to prevent: without the intermediate
states measured, a backlog number is evidence about a backlog.
"""
from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

CONTRACT = "demand_chain.v1"

# --- the nine states, in the order demand travels through them -----------------
END_DEMAND = "END_DEMAND"                # what final buyers actually want
CUSTOMER_INTENT = "CUSTOMER_INTENT"      # stated intention, not yet an order
ORDERS = "ORDERS"                        # placed, cancellable
BOOKINGS = "BOOKINGS"                    # recognised as won
COMMITTED_DEMAND = "COMMITTED_DEMAND"    # contractually committed
BACKLOG = "BACKLOG"                      # committed and not yet delivered
CANCELLATIONS = "CANCELLATIONS"          # committed and withdrawn
SHIPMENTS = "SHIPMENTS"                  # delivered
REVENUE = "REVENUE"                      # recognised
GUIDANCE = "GUIDANCE"                    # what the company says comes next

STATES = (END_DEMAND, CUSTOMER_INTENT, ORDERS, BOOKINGS, COMMITTED_DEMAND,
          BACKLOG, CANCELLATIONS, SHIPMENTS, REVENUE, GUIDANCE)

#: The links the chain models, in order. CANCELLATIONS is deliberately not on
#: the main path: it is a LEAK out of the committed pool, and modelling it as a
#: step would make a rise in cancellations look like progress along the chain.
LINKS = (
    (END_DEMAND, CUSTOMER_INTENT),
    (CUSTOMER_INTENT, ORDERS),
    (ORDERS, BOOKINGS),
    (BOOKINGS, COMMITTED_DEMAND),
    (COMMITTED_DEMAND, BACKLOG),
    (BACKLOG, SHIPMENTS),
    (SHIPMENTS, REVENUE),
    (REVENUE, GUIDANCE),
)

# --- how well a state or a link is known ---------------------------------------
OBSERVED = "OBSERVED"          # a document states a figure for it
INFERRED = "INFERRED"          # derived from measured neighbours by a rule
HYPOTHESIZED = "HYPOTHESIZED"  # asserted, not measured
CONTRADICTED = "CONTRADICTED"  # two measured states disagree
UNKNOWN = "UNKNOWN"            # nothing measures it

STANDINGS = (OBSERVED, INFERRED, HYPOTHESIZED, CONTRADICTED, UNKNOWN)
_RANK = {OBSERVED: 4, INFERRED: 3, HYPOTHESIZED: 2, CONTRADICTED: 1,
         UNKNOWN: 0}


class DemandRejected(ValueError):
    """A demand claim that outran what the documents establish."""


class UnmediatedInference(DemandRejected):
    """Raised when a downstream figure is asked what upstream demand did."""


@dataclass(frozen=True)
class DemandReading:
    """One measured state of one company's demand, at one time."""

    company_id: str
    state: str
    direction: str          # UP, DOWN, FLAT
    standing: str = OBSERVED
    value: Optional[float] = None
    unit: str = ""
    period: str = ""
    basis: str = ""         # the words that established it
    evidence_ids: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.state not in STATES:
            raise DemandRejected(f"unknown demand state {self.state!r}")
        if self.standing not in STANDINGS:
            raise DemandRejected(f"unknown standing {self.standing!r}")
        if self.standing in (OBSERVED, INFERRED) and not self.basis.strip():
            raise DemandRejected(
                f"a {self.standing} demand reading needs the wording that "
                "established it")

    @property
    def known(self) -> bool:
        return self.standing != UNKNOWN

    def as_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d.update(contract=CONTRACT, known=self.known,
                 evidence_ids=list(self.evidence_ids))
        return d


@dataclass(frozen=True)
class DemandLink:
    """One step, its standing, and the other thing that would explain it."""

    upstream: str
    downstream: str
    standing: str
    reason: str
    alternative: str = ""
    falsifier: str = ""

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


# --- reading the states out of what a company actually said ----------------------

#: Each state, and the phrases that state a figure for it. Written to match a
#: company describing its OWN pipeline; a sentence about the market's demand is
#: not a sentence about this company's orders.
_PHRASES: Tuple[Tuple[str, str], ...] = (
    (BACKLOG, r"\b(backlog|order book|remaining performance obligations?|"
              r"\bRPO\b|contract liabilit\w+)\b"),
    (BOOKINGS, r"\b(bookings|net new bookings|new business booked)\b"),
    (ORDERS, r"\b(new orders|order intake|orders (?:received|placed))\b"),
    (CANCELLATIONS, r"\b(cancellations?|cancelled orders|churn(?:ed)?|"
                    r"de-?bookings?)\b"),
    (SHIPMENTS, r"\b(shipments|units? shipped|deliveries|delivered volume)\b"),
    (REVENUE, r"\b(revenue|net sales|total sales)\b"),
    (GUIDANCE, r"\b(guidance|outlook for the|we now expect|full[- ]year "
               r"expectations)\b"),
    (CUSTOMER_INTENT, r"\b(pipeline|qualified pipeline|customer interest|"
                      r"letters? of intent|requests? for proposal|\bRFP\b)\b"),
    (COMMITTED_DEMAND, r"\b(committed (?:volume|spend|contracts?)|"
                       r"contracted (?:revenue|volume)|take[- ]or[- ]pay)\b"),
    (END_DEMAND, r"\b(end[- ]market demand|consumer demand|end demand|"
                 r"underlying demand)\b"),
)
_COMPILED = tuple((state, re.compile(p, re.I)) for state, p in _PHRASES)

_UP = re.compile(r"\b(up|rose|increased?|grew|growth|higher|expand\w+|"
                 r"strengthen\w+|record)\b", re.I)
_DOWN = re.compile(r"\b(down|fell|declin\w+|decreased?|lower|weaken\w+|"
                   r"soften\w+|contract\w+)\b", re.I)

#: Source roles whose word establishes a company's own pipeline. A journalist
#: reporting a backlog figure is repeating the company; the standing follows
#: the origin of the claim, not the outlet that carried it.
_ESTABLISHING = frozenset({"regulatory_filing", "company_owned"})


def _direction(sentence: str) -> str:
    up, down = bool(_UP.search(sentence)), bool(_DOWN.search(sentence))
    if up and not down:
        return "UP"
    if down and not up:
        return "DOWN"
    return "FLAT"


def _sentences(text: str) -> List[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text or "")
            if s.strip()]


def read_states(rows: Sequence[dict], *, company_id: str,
                aliases: Sequence[str] = ()) -> Dict[str, DemandReading]:
    """Every demand state this company's own material states a figure for.

    A state claimed by a third party is INFERRED, not OBSERVED. A backlog is a
    number only the company can produce, so a report of one is a report of what
    the company said, which is a weaker fact than the company saying it.
    """
    from . import demand_extraction as DX
    from . import economic_quantity as EQ

    mine = [r for r in rows if r.get("record") == "evidence"
            and r.get("subject_company") == company_id]
    found: Dict[str, DemandReading] = {}
    for row in mine:
        role = str(row.get("source_role") or "")
        standing = OBSERVED if role in _ESTABLISHING else INFERRED
        eid = str(row.get("evidence_id") or "")
        period = str(row.get("observed_at") or "")[:10]
        for sentence in _sentences(str(row.get("fact") or "")):
            # THE PHRASE LIST USED TO DECIDE THIS ON ITS OWN, AND IT WAS
            # WRONG HALF THE TIME. Measured against a labelled corpus, using
            # `_PHRASES` as a detector scores precision 0.50: it admits "we
            # placed orders for new manufacturing equipment" as customer
            # ORDERS, a rival's bookings as ours, "we expect bookings to
            # improve" as an observed booking, and an engineering team's
            # ticket backlog as committed demand.
            #
            # `demand_extraction` asks the four questions separately —
            # object, standing, subject, role — and refuses with the reason
            # that applies. `_PHRASES` stays as the module's vocabulary and
            # no longer decides admission.
            reading = DX.read(sentence, aliases=aliases)
            if not reading.admitted:
                continue
            state = reading.state
            held = found.get(state)
            if held is not None and _RANK[held.standing] >= _RANK[standing]:
                continue
            quantities, _ = EQ.extract(sentence, evidence_id=eid,
                                       period=period)
            relevant = [q for q in quantities]
            found[state] = DemandReading(
                company_id=company_id, state=state,
                direction=reading.direction, standing=standing,
                value=relevant[0].value if relevant else None,
                unit=relevant[0].unit if relevant else "",
                period=period, basis=sentence[:240],
                evidence_ids=(eid,) if eid else ())
    return found


def unknown(company_id: str, state: str) -> DemandReading:
    return DemandReading(company_id=company_id, state=state, direction="FLAT",
                         standing=UNKNOWN)


# --- the chain -------------------------------------------------------------------

#: For each link: what the alternative explanation is, and what would show the
#: link did not hold. Written per link rather than generated, because the
#: alternative to "orders became bookings" is a different sentence from the
#: alternative to "shipments became revenue".
_LINK_STORIES = {
    (END_DEMAND, CUSTOMER_INTENT): (
        "the pipeline grew from more sales coverage rather than more demand",
        "pipeline grows while end-market demand is flat or falling"),
    (CUSTOMER_INTENT, ORDERS): (
        "orders were pulled forward ahead of a price increase",
        "orders rise while the pipeline that fed them shrinks"),
    (ORDERS, BOOKINGS): (
        "a booking policy change recognised existing orders differently",
        "bookings move without a corresponding change in orders"),
    (BOOKINGS, COMMITTED_DEMAND): (
        "bookings were recorded before contracts were signed",
        "committed volume is flat while bookings rise"),
    (COMMITTED_DEMAND, BACKLOG): (
        "backlog grew because deliveries slipped, not because commitments "
        "rose",
        "backlog rises while committed demand is unchanged"),
    (BACKLOG, SHIPMENTS): (
        "a supply constraint is holding committed volume undelivered",
        "backlog and shipments move the same way rather than opposite ways"),
    (SHIPMENTS, REVENUE): (
        "revenue moved on price or mix rather than on volume",
        "revenue and shipments move in opposite directions"),
    (REVENUE, GUIDANCE): (
        "guidance was set against an expectation, not against the quarter",
        "guidance moves opposite to the revenue that preceded it"),
}


@dataclass(frozen=True)
class Chain:
    """One company's demand chain, holes included."""

    company_id: str
    readings: Dict[str, DemandReading]
    links: Tuple[DemandLink, ...]
    as_of: str = ""

    @property
    def known_states(self) -> int:
        return sum(1 for r in self.readings.values() if r.known)

    @property
    def weakest(self) -> Optional[DemandLink]:
        if not self.links:
            return None
        return min(self.links, key=lambda l: _RANK[l.standing])

    @property
    def standing(self) -> str:
        """The chain is worth its weakest link. Never an average.

        Averaging standings is how a chain with one measured link and seven
        holes reports as half-known.
        """
        if not self.links:
            return UNKNOWN
        return min((l.standing for l in self.links), key=lambda s: _RANK[s])

    def as_dict(self) -> dict:
        weakest = self.weakest
        return {
            "contract": CONTRACT, "company_id": self.company_id,
            "as_of": self.as_of,
            "states": {s: self.readings[s].as_dict() for s in STATES
                       if s in self.readings},
            "known_states": self.known_states,
            "unknown_states": [s for s in STATES
                               if not self.readings.get(s, unknown(
                                   self.company_id, s)).known],
            "links": [l.as_dict() for l in self.links],
            "standing": self.standing,
            "weakest_link": (f"{weakest.upstream} -> {weakest.downstream}: "
                             f"{weakest.reason}" if weakest else ""),
            "note": ("a chain is worth its weakest link; a backlog figure is "
                     "evidence about a backlog and about nothing upstream"),
        }


def build(rows: Sequence[dict], *, company_id: str, as_of: str = "",
          aliases: Sequence[str] = ()) -> Chain:
    """Assemble the chain from what the company's own material states."""
    readings = read_states(rows, company_id=company_id, aliases=aliases)
    full = {s: readings.get(s) or unknown(company_id, s) for s in STATES}
    links: List[DemandLink] = []
    for upstream, downstream in LINKS:
        up, down = full[upstream], full[downstream]
        alternative, falsifier = _LINK_STORIES[(upstream, downstream)]
        if not up.known and not down.known:
            standing, reason = UNKNOWN, (
                f"neither {upstream} nor {downstream} is measured")
        elif not up.known:
            standing, reason = UNKNOWN, f"no evidence for {upstream}"
        elif not down.known:
            standing, reason = UNKNOWN, f"no evidence for {downstream}"
        elif up.direction == down.direction and up.direction != "FLAT":
            standing, reason = HYPOTHESIZED, (
                f"{upstream} and {downstream} both moved {up.direction}, "
                "which is consistent with the link and does not establish it")
        elif up.direction != down.direction and "FLAT" not in (up.direction,
                                                               down.direction):
            standing, reason = CONTRADICTED, (
                f"{upstream} moved {up.direction} while {downstream} moved "
                f"{down.direction}")
        else:
            standing, reason = HYPOTHESIZED, (
                "one end of the link did not move, so the step is neither "
                "supported nor contradicted")
        links.append(DemandLink(upstream=upstream, downstream=downstream,
                                standing=standing, reason=reason,
                                alternative=alternative, falsifier=falsifier))
    return Chain(company_id=company_id, readings=full, links=tuple(links),
                 as_of=as_of)


def implies_demand(reading: DemandReading, *_a, **_k):
    """Deliberately not implemented, and deliberately present.

    Backlog rose. Does that mean demand rose? The plausible answer is always
    available and it is wrong at least as often as it is right: a backlog grows
    when orders rise AND when shipments slip, and those are opposite facts
    about the business. Answering would let the one figure a company reliably
    discloses stand in for the eight states it does not.
    """
    raise UnmediatedInference(
        f"{reading.state} is a measured state, not a statement about demand; "
        "the states between them have to be measured before the chain "
        "carries anything")


def summarise(chains: Sequence[Chain]) -> dict:
    by_standing: Dict[str, int] = {}
    for c in chains:
        by_standing[c.standing] = by_standing.get(c.standing, 0) + 1
    measured = [c for c in chains if c.known_states]
    contradicted = [l for c in chains for l in c.links
                    if l.standing == CONTRADICTED]
    return {
        "contract": CONTRACT,
        "companies": len(chains),
        "companies_with_any_state": len(measured),
        "by_chain_standing": by_standing,
        "states_measured": sum(c.known_states for c in chains),
        "states_possible": len(chains) * len(STATES),
        "contradicted_links": [
            f"{c.company_id}: {l.upstream}->{l.downstream}"
            for c in chains for l in c.links if l.standing == CONTRADICTED],
        "every_link_has_an_alternative": all(
            l.alternative for c in chains for l in c.links),
        "note": (f"{len(contradicted)} link(s) where two measured states "
                 "disagree; a contradiction is the most informative state a "
                 "link can be in and is never averaged away"),
    }
