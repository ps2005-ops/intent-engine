"""The resolution ladder: what to say when the direct measurement is missing.

THE DEFECT THIS REPLACES
------------------------
A customer-facing page said:

    "No estimate or share-price series was retrieved, so what the market
     expected is not measured here."

That sentence is TRUE and it is a product failure. It reports the state of a
retrieval attempt to someone who asked a business question, and it terminates:
there is no next sentence, nothing to decide, nothing to do. A missing field
became an empty paragraph because the code had exactly two states — I have the
number, or I do not.

THE RULE THIS IMPOSES, AND ITS LIMIT
------------------------------------
A missing direct measurement is the START of the work, not the end of it. This
module makes the intermediate rungs first-class so that "unavailable" is a
LAST resort with a name, a reason and a next step, rather than a default.

    A  OBSERVED     a filed, measured or retrieved value
    B  SUPPORTED    a contemporaneous proxy that stands in for it, named
    C  MODELED      a structural economic inference — direction and a band
    D  BENCHMARK    a peer, sector or structural baseline, never a company fact
    E  BOUNDED      no central value, but the range is decision-relevant
    F  UNRESOLVED   nothing defensible — so a minimum viable experiment

**THIS IS NOT A LICENCE TO INVENT.** Every rung below OBSERVED must name what
it was derived FROM and carry a label the reader sees. A modelled expectation
is never called a consensus; a peer baseline is never called this company's
number; a counterfactual is never called what would have happened. The ladder
exists so that the honest answer is richer than silence — not so that silence
can be dressed as an answer. Rung F is a real rung and it is reached often; it
is still not an empty paragraph, because it carries the measurement that would
resolve it.

WHY IT IS ONE OBJECT
--------------------
Because "how do we know this?" must survive the trip to the page. Three
surfaces previously derived their own hedging language from whatever field
happened to be empty, and they disagreed with each other in the same run —
`/connect` said no independent source existed in the same paragraph that cited
one. A single `Resolved` carries the basis, the label and the prose together,
so a surface can render it but cannot re-decide it.
"""
from __future__ import annotations

import dataclasses
from typing import Optional, Sequence, Tuple

CONTRACT = "resolution_ladder.v1"

OBSERVED = "OBSERVED"
SUPPORTED = "SUPPORTED"
MODELED = "MODELED"
BENCHMARK = "BENCHMARK"
BOUNDED = "BOUNDED"
COUNTERFACTUAL = "COUNTERFACTUAL"
UNRESOLVED = "UNRESOLVED"

BASES = (OBSERVED, SUPPORTED, MODELED, BENCHMARK, BOUNDED, COUNTERFACTUAL,
         UNRESOLVED)

#: Rung order, strongest first. Used to compare two resolutions of the same
#: quantity and to score a surface's data resolution.
RANK = {basis: i for i, basis in enumerate(BASES)}

#: The badge a reader sees. Never an enum (§73), never "available".
LABEL = {
    OBSERVED: "Observed",
    SUPPORTED: "Supported",
    MODELED: "Modelled",
    BENCHMARK: "Benchmark",
    BOUNDED: "Bounded",
    COUNTERFACTUAL: "Counterfactual",
    UNRESOLVED: "Open question",
}

#: What the badge MEANS, for the legend and the tooltip. A badge whose meaning
#: is not on the page is decoration.
LABEL_MEANING = {
    OBSERVED: "a filed or retrieved measurement",
    SUPPORTED: "a contemporaneous stand-in for the measurement, named below",
    MODELED: "inferred from information available at the time, not retrieved",
    BENCHMARK: "a peer or sector baseline — not this company's own figure",
    BOUNDED: "no single value is defensible; the range is what can be said",
    COUNTERFACTUAL: "what an alternative strategy plausibly implied — never a "
                    "record of what happened",
    UNRESOLVED: "not established, and the measurement that would settle it",
}


@dataclasses.dataclass(frozen=True)
class Resolved:
    """One quantity or claim, and how far up the ladder it got."""
    question: str
    basis: str
    #: The reader-facing answer. NEVER empty — that is the whole contract.
    statement: str
    #: What it was derived from. Required below OBSERVED.
    derivation: str = ""
    value: Optional[float] = None
    low: Optional[float] = None
    high: Optional[float] = None
    unit: str = ""
    #: What would move this up the ladder. Required at UNRESOLVED.
    next_measurement: str = ""
    #: The decision this bears on, so a gap is never merely interesting.
    decision_relevance: str = ""
    drivers: Tuple[str, ...] = ()

    @property
    def label(self) -> str:
        return LABEL.get(self.basis, self.basis)

    @property
    def is_direct(self) -> bool:
        return self.basis == OBSERVED

    def as_dict(self) -> dict:
        out = dataclasses.asdict(self)
        out["contract"] = CONTRACT
        out["label"] = self.label
        out["label_meaning"] = LABEL_MEANING.get(self.basis, "")
        return out


class LadderViolation(AssertionError):
    """A resolution that would reach a customer without a defensible basis."""


def check(resolved: Resolved) -> Resolved:
    """Enforce the contract at construction. Raises rather than shipping.

    A silent repair here would be the worst possible behaviour: it would let a
    modelled figure reach a page with an observation's badge. The producer is
    wrong and must be fixed, so this raises in the producer's own test.
    """
    if resolved.basis not in BASES:
        raise LadderViolation(f"unknown basis {resolved.basis!r}")
    if not (resolved.statement or "").strip():
        raise LadderViolation(
            f"{resolved.question!r} resolved to an empty statement; the "
            f"ladder exists so that this is impossible")
    if resolved.basis != OBSERVED and not (resolved.derivation or "").strip():
        raise LadderViolation(
            f"{resolved.question!r} is {resolved.basis} without naming what it "
            f"was derived from")
    if resolved.basis == UNRESOLVED and not (
            resolved.next_measurement or "").strip():
        raise LadderViolation(
            f"{resolved.question!r} is UNRESOLVED without a next measurement; "
            f"an open question with no way to close it is a dead end")
    return resolved


# ===========================================================================
# constructors — one per rung, so the basis cannot be set by accident
# ===========================================================================
def observed(question: str, statement: str, *, value=None, unit="",
             decision_relevance="", drivers=()) -> Resolved:
    return check(Resolved(question=question, basis=OBSERVED,
                          statement=statement, value=value, unit=unit,
                          decision_relevance=decision_relevance,
                          drivers=tuple(drivers)))


def supported(question: str, statement: str, *, derivation: str, value=None,
              unit="", decision_relevance="", drivers=()) -> Resolved:
    return check(Resolved(question=question, basis=SUPPORTED,
                          statement=statement, derivation=derivation,
                          value=value, unit=unit,
                          decision_relevance=decision_relevance,
                          drivers=tuple(drivers)))


def modeled(question: str, statement: str, *, derivation: str, value=None,
            low=None, high=None, unit="", decision_relevance="",
            drivers=()) -> Resolved:
    return check(Resolved(question=question, basis=MODELED,
                          statement=statement, derivation=derivation,
                          value=value, low=low, high=high, unit=unit,
                          decision_relevance=decision_relevance,
                          drivers=tuple(drivers)))


def benchmark(question: str, statement: str, *, derivation: str, value=None,
              low=None, high=None, unit="", decision_relevance="",
              drivers=()) -> Resolved:
    return check(Resolved(question=question, basis=BENCHMARK,
                          statement=statement, derivation=derivation,
                          value=value, low=low, high=high, unit=unit,
                          decision_relevance=decision_relevance,
                          drivers=tuple(drivers)))


def bounded(question: str, statement: str, *, derivation: str, low=None,
            high=None, unit="", decision_relevance="", drivers=()) -> Resolved:
    return check(Resolved(question=question, basis=BOUNDED,
                          statement=statement, derivation=derivation,
                          low=low, high=high, unit=unit,
                          decision_relevance=decision_relevance,
                          drivers=tuple(drivers)))


def counterfactual(question: str, statement: str, *, derivation: str,
                   value=None, low=None, high=None, unit="",
                   decision_relevance="", drivers=()) -> Resolved:
    return check(Resolved(question=question, basis=COUNTERFACTUAL,
                          statement=statement, derivation=derivation,
                          value=value, low=low, high=high, unit=unit,
                          decision_relevance=decision_relevance,
                          drivers=tuple(drivers)))


def unresolved(question: str, *, why: str, next_measurement: str,
               decision_relevance: str = "", statement: str = "") -> Resolved:
    """Rung F. The honest end of the ladder — and still not an empty page.

    `statement` is composed rather than required, because the failure mode
    this module exists to remove is a producer that had nothing to say and
    therefore said nothing. Here, having nothing to say produces a sentence
    about what is not known, what it would take to know it, and why it
    matters — which is a usable answer to a business question.
    """
    said = (statement or "").strip()
    if not said:
        said = (f"{why.rstrip('.')}. This is an open question rather than a "
                f"finding")
        if decision_relevance:
            said += f", and it bears on {decision_relevance.rstrip('.')}"
        said += f". What would settle it: {next_measurement.rstrip('.')}."
    return check(Resolved(question=question, basis=UNRESOLVED, statement=said,
                          derivation=why, next_measurement=next_measurement,
                          decision_relevance=decision_relevance))


def best(*candidates: Optional[Resolved]) -> Optional[Resolved]:
    """The strongest rung among several attempts at the same question."""
    live = [c for c in candidates if c is not None]
    if not live:
        return None
    return min(live, key=lambda r: RANK.get(r.basis, len(BASES)))


def profile(resolutions: Sequence[Resolved]) -> dict:
    """How well a surface resolved what it needed. Feeds the defect matrix."""
    counts = {basis: 0 for basis in BASES}
    for item in resolutions or ():
        counts[item.basis] = counts.get(item.basis, 0) + 1
    total = sum(counts.values()) or 1
    resolved_count = total - counts[UNRESOLVED]
    return {"contract": CONTRACT, "total": sum(counts.values()),
            "by_basis": counts,
            "direct_rate": round(counts[OBSERVED] / total, 3),
            "resolution_rate": round(resolved_count / total, 3),
            "open_questions": counts[UNRESOLVED]}
