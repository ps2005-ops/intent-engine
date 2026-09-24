"""Many reports of one announcement are one observation, and must read as one.

WHAT THIS PREVENTS
------------------
The market layer has known since wave 8 that 143 claimed accounts are 55.5
effective ones, and that 133 of 155 events are SAME_ORIGIN. None of that
reached a reader. A founder page saying "three sources confirm this" about
three sites carrying one press release is not a rounding error — it is the
difference between a fact and a rumour repeated loudly.

TWO OUTPUTS, AND THE SECOND ONE IS THE POINT
--------------------------------------------
    weight    what the engine may CONCLUDE from the evidence
    language  what the reader is told about it

Changing only the second is theatre: the belief would still mature on three
copies of one announcement while the prose said otherwise. `weight` is
therefore computed first and the sentence is derived FROM it, so they cannot
disagree.

WHAT A FOUNDER NEVER SEES
-------------------------
`SAME_ORIGIN`, `PARTIALLY_INDEPENDENT`, dependency coefficients, effective
account counts. Those are how the engine decides; they are not how a person
is spoken to. The rendered sentence names the situation in ordinary words
and stops.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Sequence, Tuple

CONTRACT = "evidence_trust.v1"

# --- what a reader is told --------------------------------------------------
SINGLE_SOURCE = "SINGLE_SOURCE"
DEPENDENT_REREPORTING = "DEPENDENT_REREPORTING"
PARTIALLY_INDEPENDENT = "PARTIALLY_INDEPENDENT"
INDEPENDENTLY_CORROBORATED = "INDEPENDENTLY_CORROBORATED"
CONFLICTED = "CONFLICTED"

STANDINGS = (SINGLE_SOURCE, DEPENDENT_REREPORTING, PARTIALLY_INDEPENDENT,
             INDEPENDENTLY_CORROBORATED, CONFLICTED)

#: How much a standing is allowed to move a conclusion. One observation is
#: one observation however many sites carried it, so dependent re-reporting
#: weighs exactly what a single source weighs — not slightly more.
WEIGHT: Dict[str, float] = {
    SINGLE_SOURCE: 1.0,
    DEPENDENT_REREPORTING: 1.0,
    PARTIALLY_INDEPENDENT: 1.3,
    INDEPENDENTLY_CORROBORATED: 2.0,
    CONFLICTED: 0.5,
}

#: Internal vocabulary that must never reach a rendered page.
INTERNAL_TERMS = frozenset({
    "same_origin", "partially_independent", "dependent_rereporting",
    "independently_corroborated", "single_source", "conflicted",
    "design effect", "effective_accounts", "dependency_class",
    "source_dependency", "corroboration_state",
})

_SENTENCES: Dict[str, str] = {
    SINGLE_SOURCE:
        "One source reports this, so we are treating it as a single "
        "observation.",
    DEPENDENT_REREPORTING:
        "Several reports trace back to the same underlying announcement, so "
        "we treat them as one observation rather than independent "
        "confirmation.",
    PARTIALLY_INDEPENDENT:
        "Different outlets carry this, though they may share an origin, so "
        "we are treating it as a little more than a single observation.",
    INDEPENDENTLY_CORROBORATED:
        "Separate sources independently support the same point.",
    CONFLICTED:
        "Public sources disagree on this point, so we are keeping the "
        "conclusion bounded.",
}


@dataclass(frozen=True)
class EvidenceTrust:
    """One event's standing, the weight it earns, and what to say about it."""
    event_id: str
    standing: str
    accounts: int
    effective_accounts: float
    weight: float
    sentence: str
    #: The rows this occurrence was assembled from. Carried so normalization
    #: never costs provenance: the grouping is reversible, and a consumer can
    #: still walk from the occurrence back to every account of it.
    evidence_ids: Tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {
            "contract": CONTRACT, "event_id": self.event_id,
            "standing": self.standing, "accounts": self.accounts,
            "effective_accounts": round(self.effective_accounts, 2),
            "weight": self.weight, "sentence": self.sentence,
            "evidence_ids": list(self.evidence_ids),
        }


def assess(corroboration, *, evidence_ids: Sequence[str] = ()) -> EvidenceTrust:
    """Translate a market-layer corroboration into founder-facing trust.

    Reads `event_corroboration.EventCorroboration`, which already knows the
    dependency classes. Nothing is recomputed here: this is the seam where
    the market layer's answer becomes something a reader can be told.
    """
    def _get(name, default=None):
        if isinstance(corroboration, dict):
            return corroboration.get(name, default)
        return getattr(corroboration, name, default)

    market_standing = str(_get("standing", "") or "")
    accounts = int(_get("accounts", 0) or 0)
    effective = float(_get("effective_accounts", 0.0) or 0.0)
    independent = int(_get("independent_accounts", 0) or 0)
    conflicting = tuple(_get("conflicting_fields", ()) or ())

    if conflicting:
        standing = CONFLICTED
    elif accounts <= 1:
        standing = SINGLE_SOURCE
    elif market_standing == "CORROBORATED" and independent >= 2:
        standing = INDEPENDENTLY_CORROBORATED
    elif effective >= 1.5:
        standing = PARTIALLY_INDEPENDENT
    else:
        standing = DEPENDENT_REREPORTING

    return EvidenceTrust(
        event_id=str(_get("event_id", "") or ""), standing=standing,
        accounts=accounts, effective_accounts=effective,
        weight=WEIGHT[standing], sentence=_SENTENCES[standing],
        evidence_ids=tuple(str(e) for e in (evidence_ids or ())))


def independent_support_count(trusts: Sequence[EvidenceTrust]) -> int:
    """How many INDEPENDENT observations a conclusion may claim.

    Not `len(trusts)`. Five events that are each dependent re-reporting are
    five observations of five things, and each counts once — but a single
    event carried by five sites is ONE, and this is where that stops being
    inflated on the way to a belief.
    """
    return sum(1 for t in trusts
               if t.standing in (INDEPENDENTLY_CORROBORATED,
                                 PARTIALLY_INDEPENDENT, SINGLE_SOURCE,
                                 DEPENDENT_REREPORTING))


def total_weight(trusts: Sequence[EvidenceTrust]) -> float:
    return round(sum(t.weight for t in trusts), 3)


def render(trusts: Sequence[EvidenceTrust]) -> str:
    """One sentence for a reader, naming the weakest thing worth naming."""
    if not trusts:
        return ""
    # Same ordering as `weakest`, read from one table: two copies of this
    # ranking is two things that can disagree about which fact is the weak one.
    worst = min(trusts, key=lambda t: _WEAKEST_FIRST.get(t.standing, 9))
    return worst.sentence


#: The order that decides which of several standings a claim inherits.
#: Weakest first: a claim resting on one dependent cluster and one solid
#: independent event is only as sound as the weakest thing it needs.
_WEAKEST_FIRST = {CONFLICTED: 0, DEPENDENT_REREPORTING: 1, SINGLE_SOURCE: 2,
                  PARTIALLY_INDEPENDENT: 3, INDEPENDENTLY_CORROBORATED: 4}


def weakest(trusts: Sequence[EvidenceTrust]) -> str:
    """The standing a claim inherits from the events beneath it."""
    if not trusts:
        return ""
    return min(trusts, key=lambda t: _WEAKEST_FIRST.get(t.standing, 9)).standing


def for_claim(trusts: Sequence[EvidenceTrust]) -> dict:
    """What ONE claim's supporting evidence is actually worth.

    THIS IS THE OBJECT THAT CROSSES TO THE FOUNDER SIDE, and it is shaped for
    a consumer that must not do this arithmetic itself. It carries the raw
    count and the normalized one side by side, because the whole failure this
    module exists to prevent is a reader — human or machine — seeing only the
    first number.

    `raw_accounts` is what a naive count would have said. `distinct_events` is
    how many things actually happened. When those two disagree, the gap is the
    inflation, and `sentence` is what to say about it.

    The standing is the WEAKEST of the events, not the average and not the
    best: averaging lets one well-sourced filing launder a rumour that the
    same claim also depends on.
    """
    trusts = list(trusts)
    return {
        "contract": CONTRACT,
        "standing": weakest(trusts),
        "raw_accounts": sum(t.accounts for t in trusts),
        "distinct_events": len(trusts),
        "independent_support": independent_support_count(trusts),
        "weight": total_weight(trusts),
        "sentence": render(trusts),
        # THE GROUPING ITSELF, not only its size. Counts alone would let the
        # consumer know that three rows are one occurrence without knowing
        # WHICH three, so it could not build a graph that walks from a
        # rendered sentence back to the rows underneath it. Provenance is the
        # reason normalization is safe: nothing is deleted, it is grouped.
        "events": [
            {"event_id": t.event_id, "standing": t.standing,
             "accounts": t.accounts, "weight": t.weight,
             "evidence_ids": list(t.evidence_ids)}
            for t in trusts
        ],
    }


def summarise(trusts: Sequence[EvidenceTrust]) -> dict:
    from collections import Counter
    by_standing = Counter(t.standing for t in trusts)
    return {
        "contract": CONTRACT,
        "events": len(trusts),
        "by_standing": {s: by_standing.get(s, 0) for s in STANDINGS
                        if by_standing.get(s, 0)},
        "independent_support": independent_support_count(trusts),
        "total_weight": total_weight(trusts),
        "sentence": render(trusts),
        "note": ("weight is computed first and the sentence is derived from "
                 "it, so the prose cannot say 'one observation' while a "
                 "belief matures on three copies of it"),
    }
