"""What a strategic conclusion rests on, and which support is weakest.

THE DEFECT THIS ADDRESSES
-------------------------
A recommendation arrives as a sentence. Underneath it is a chain -- enterprise
customers pay more, so ACV is higher, so churn is lower, so contribution
margin is higher, so put the resources there -- and every link in that chain
is a separate claim with a separate amount of evidence behind it. The
recommendation is exactly as strong as its weakest link, and nothing on the
page said which link that was.

So a reader could not do the one thing that makes a recommendation safe:
check the part most likely to be wrong.

WHAT "WEAKEST" MEANS HERE, AND WHY IT IS NOT JUST "LEAST EVIDENCE"
-------------------------------------------------------------------
An assumption is weak in the way that matters when it is BOTH poorly
supported AND load-bearing. A poorly supported claim that nothing depends on
is a footnote; a well-supported claim carrying the whole argument is a
strength. The weakest critical assumption is the one with the worst product
of the two, and both terms are computed from the graph rather than asserted:

    support  -- the standing of the edge, from OBSERVED down to ASSUMED
    load     -- how many conclusions stop following if it fails

An edge marked CONTRADICTED outranks everything regardless of load, because a
chain with a contradicted link is not weak, it is broken, and saying so is
more useful than ranking it.
"""
from __future__ import annotations

import dataclasses
from typing import Dict, List, Optional, Sequence, Tuple

CONTRACT = "assumption_graph.v1"

# --- how well an edge is established ---------------------------------------
OBSERVED = "OBSERVED"          #: measured or filed
INFERRED = "INFERRED"          #: follows from something observed
ASSUMED = "ASSUMED"            #: taken as given; nothing in the run tests it
UNTESTED = "UNTESTED"          #: could be tested, has not been
CONTRADICTED = "CONTRADICTED"  #: the run holds evidence against it

STANDINGS = (OBSERVED, INFERRED, UNTESTED, ASSUMED, CONTRADICTED)

#: Lower is better supported. CONTRADICTED sits outside the scale and is
#: handled before ranking.
SUPPORT_RANK = {OBSERVED: 0, INFERRED: 1, UNTESTED: 2, ASSUMED: 3,
                CONTRADICTED: 4}

STANDING_LABEL = {
    OBSERVED: "observed",
    INFERRED: "inferred",
    ASSUMED: "assumed",
    UNTESTED: "untested",
    CONTRADICTED: "contradicted",
}

STANDING_MEANING = {
    OBSERVED: "measured or filed, and cited",
    INFERRED: "follows from something measured, and the step is stated",
    ASSUMED: "taken as given — nothing in this run tests it",
    UNTESTED: "could be checked and has not been",
    CONTRADICTED: "this run holds evidence against it",
}


class GraphRefused(ValueError):
    """A dependency that cannot be stated."""


@dataclasses.dataclass(frozen=True)
class Link:
    """One step: because `frm`, therefore `to`."""
    frm: str
    to: str
    standing: str
    #: Why this step follows. A link with no reason is an assertion with an
    #: arrow drawn on it.
    because: str
    evidence: str = ""
    #: What would settle this step, in the producer's own words. A generic
    #: sentence composed from the two node labels read as
    #: "Measure the direction shown in the record persists into the next
    #: period against net revenue retention is the measure that moves first"
    #: on the deployed page -- the nodes are clauses, and clauses do not
    #: compose into a sentence by concatenation.
    settled_by: str = ""

    def __post_init__(self):
        if self.standing not in STANDINGS:
            raise GraphRefused(f"unknown standing {self.standing!r}")
        if not (self.because or "").strip():
            raise GraphRefused(
                f"{self.frm} -> {self.to}: a step with no reason is an arrow, "
                f"not an argument")

    @property
    def standing_label(self) -> str:
        return STANDING_LABEL.get(self.standing, self.standing)

    def as_dict(self) -> dict:
        row = dataclasses.asdict(self)
        row["standing_label"] = self.standing_label
        return row


@dataclasses.dataclass(frozen=True)
class WeakestAssumption:
    """The link a chief executive should check first, and why it is that one."""
    link: Link
    load: int
    reason: str
    what_would_settle_it: str

    def as_dict(self) -> dict:
        return {"link": self.link.as_dict(), "load": self.load,
                "reason": self.reason,
                "what_would_settle_it": self.what_would_settle_it}


@dataclasses.dataclass(frozen=True)
class AssumptionGraph:
    """The chain under one conclusion."""
    conclusion: str
    links: Tuple[Link, ...] = ()

    def downstream(self, node: str) -> Tuple[str, ...]:
        """Everything that stops following if `node` fails."""
        out: List[str] = []
        frontier = [node]
        seen = {node}
        while frontier:
            current = frontier.pop()
            for link in self.links:
                if link.frm == current and link.to not in seen:
                    seen.add(link.to)
                    out.append(link.to)
                    frontier.append(link.to)
        return tuple(out)

    @property
    def contradicted(self) -> Tuple[Link, ...]:
        return tuple(l for l in self.links if l.standing == CONTRADICTED)

    @property
    def weakest_critical(self) -> Optional[WeakestAssumption]:
        if not self.links:
            return None
        # A broken link is not ranked against weak ones; it is reported.
        broken = self.contradicted
        if broken:
            link = broken[0]
            load = len(self.downstream(link.to)) + 1
            return WeakestAssumption(
                link=link, load=load,
                reason=(f"This run holds evidence against it, and "
                        f"{load} step(s) of the argument follow from it — so "
                        f"it is the first thing to reconcile."),
                what_would_settle_it=_settle(link))
        ranked = sorted(
            self.links,
            key=lambda l: (-(SUPPORT_RANK.get(l.standing, 9)
                             * (len(self.downstream(l.to)) + 1)),
                           SUPPORT_RANK.get(l.standing, 9)))
        link = ranked[0]
        if SUPPORT_RANK.get(link.standing, 9) <= SUPPORT_RANK[INFERRED]:
            # Everything load-bearing is observed or inferred. Say so rather
            # than promoting a well-supported link to "weakest", which reads
            # as a warning about the strongest part of the argument.
            return None
        load = len(self.downstream(link.to)) + 1
        return WeakestAssumption(
            link=link, load=load,
            # NOT "...more weight than anything else that is not
            # established" -- true, and it reads as a dead end, which is what
            # the customer-copy sweep flagged it as. What a reader needs is
            # the consequence and the action, and the action is the next line.
            reason=(f"It is {link.standing_label}, and {load} step(s) of the "
                    f"argument follow from it — so it is the first thing to "
                    f"check."),
            what_would_settle_it=_settle(link))

    def as_dict(self) -> dict:
        weakest = self.weakest_critical
        return {"contract": CONTRACT, "conclusion": self.conclusion,
                "links": [l.as_dict() for l in self.links],
                "weakest_critical": weakest.as_dict() if weakest else None}


def _settle(link: Link) -> str:
    """What would settle this step.

    The producer's own sentence wins. The fallback asks whether the step held
    historically, phrased so that a CLAUSE can be dropped into it -- the two
    node labels are clauses, and composing them into one sentence produced
    grammatical wreckage on the deployed page.
    """
    if (link.settled_by or "").strip():
        return link.settled_by.strip()
    if link.standing == CONTRADICTED:
        return (f"Reconcile the contradiction directly: check whether "
                f"{_lower(link.to)}, in the periods where the contrary "
                f"evidence sits.")
    return (f"Check the last four reported periods for whether "
            f"{_lower(link.to)}. If it did not hold there, the step does not "
            f"hold now.")


def _lower(text: str) -> str:
    text = (text or "").strip()
    return text[:1].lower() + text[1:] if text else text


def build(conclusion: str, steps: Sequence[Tuple[str, str, str, str]]
          ) -> AssumptionGraph:
    """`steps` is (from, to, standing, because)."""
    links = tuple(Link(frm=row[0], to=row[1], standing=row[2],
                       because=row[3],
                       settled_by=(row[4] if len(row) > 4 else ""))
                  for row in steps)
    return AssumptionGraph(conclusion=conclusion, links=links)
