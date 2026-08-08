"""The founder side of normalized evidence trust: consume it, never re-derive it.

WHAT THIS IS FOR
----------------
The market engine decides how many things actually happened. It ships that
decision on every dossier as `evidence_trust`. This module is the only place
the founder side reads it, and it does three things with it:

    weight    how much a conclusion may lean on the evidence
    bound     whether the primary narrative must become more careful
    language  what a founder is told, in words

WHY IT DOES NOT RECOMPUTE
-------------------------
The obvious shortcut is to count `evidence_ids` here and classify locally.
That is the defect this whole layer exists to remove: counting rows is exactly
what says "three sources confirm" about one press release. Source dependence
is decided where the rows and their publishers live, which is the market side.
This side consumes a standing it did not compute — and when the producer sent
no standing, it says so rather than inventing one.

ABSENT IS NOT SINGLE
--------------------
A dossier with no trust block was produced by something that never normalized.
That is a different fact from "we normalized this and it rests on one
observation", and collapsing the two would let an un-normalized dossier read
as a carefully bounded one. `UNKNOWN` exists for exactly that case and earns
no confidence at all.

WHAT A FOUNDER NEVER SEES
-------------------------
The standing names in this module are wire vocabulary. `DEPENDENT_REREPORTING`
is how the two systems agree; it is not how a person is spoken to. Everything
rendered comes from `sentence()`, and `contains_internal_vocabulary` is the
guard that keeps the enum off the page.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence

CONTRACT = "evidence_trust.v1"

# --- the standings, as the producer names them ----------------------------
SINGLE_SOURCE = "SINGLE_SOURCE"
DEPENDENT_REREPORTING = "DEPENDENT_REREPORTING"
PARTIALLY_INDEPENDENT = "PARTIALLY_INDEPENDENT"
INDEPENDENTLY_CORROBORATED = "INDEPENDENTLY_CORROBORATED"
CONFLICTED = "CONFLICTED"
#: No standing arrived. Not a synonym for SINGLE_SOURCE.
UNKNOWN = "UNKNOWN"

STANDINGS = (SINGLE_SOURCE, DEPENDENT_REREPORTING, PARTIALLY_INDEPENDENT,
             INDEPENDENTLY_CORROBORATED, CONFLICTED, UNKNOWN)

#: Standings under which the primary narrative must not harden. A conclusion
#: may still be REACHED on one observation — companies act on single filings
#: every day — but it may not be stated as though several parties saw it.
_MUST_BOUND = frozenset({DEPENDENT_REREPORTING, CONFLICTED, UNKNOWN})

#: Only this standing licenses the language of independent confirmation.
_MAY_CLAIM_INDEPENDENCE = frozenset({INDEPENDENTLY_CORROBORATED})

#: Internal vocabulary that must never reach a rendered page. Checked as
#: lowercase substrings so `Standing: DEPENDENT_REREPORTING` is caught too.
INTERNAL_TERMS = frozenset({
    "single_source", "dependent_rereporting", "partially_independent",
    "independently_corroborated", "conflicted_evidence", "same_origin",
    "effective_accounts", "dependency_class", "dependency_classes",
    "source_dependency", "corroboration_state", "raw_accounts",
    "distinct_events", "independent_support", "evidence_trust",
    "design effect",
})

#: What a reader is told. Authored HERE rather than trusted from the wire for
#: the fallback cases only: the producer ships its own sentence and that one
#: wins, because the side that judged the evidence is the side that should say
#: what it judged. These cover a dossier that arrived without one.
_FALLBACK: Dict[str, str] = {
    SINGLE_SOURCE:
        "One source reports this, so we are treating it as a single "
        "observation.",
    DEPENDENT_REREPORTING:
        "Several reports repeat the same underlying announcement, so we treat "
        "this as one observation rather than independent confirmation.",
    PARTIALLY_INDEPENDENT:
        "Different outlets carry this, though they may share an origin, so we "
        "treat it as a little more than a single observation.",
    INDEPENDENTLY_CORROBORATED:
        "Separate sources independently support the same point.",
    CONFLICTED:
        "Public sources disagree on this point, so the conclusion remains "
        "bounded.",
    UNKNOWN: "",
}


@dataclass(frozen=True)
class Event:
    """One occurrence, and the rows that reported it."""
    event_id: str
    standing: str
    accounts: int
    weight: float
    evidence_ids: tuple


@dataclass(frozen=True)
class Trust:
    """One claim's standing, as this side will act on it."""
    standing: str
    raw_accounts: int
    distinct_events: int
    independent_support: int
    weight: float
    sentence: str
    #: The grouping, so a graph node can be an OCCURRENCE with its accounts
    #: hanging off it rather than one node per row.
    events: tuple = ()

    @property
    def known(self) -> bool:
        return self.standing != UNKNOWN

    @property
    def must_bound(self) -> bool:
        """Whether the primary narrative has to stay careful here."""
        return self.standing in _MUST_BOUND

    @property
    def may_claim_independence(self) -> bool:
        """Whether the page is allowed to say sources agree independently."""
        return self.standing in _MAY_CLAIM_INDEPENDENCE

    @property
    def inflation(self) -> int:
        """Rows that would have been counted as separate observations.

        The number a naive reader would have been given, minus the number of
        things that happened. This is the quantity the whole layer removes,
        and it is reported rather than merely avoided.
        """
        if not self.known:
            return 0
        return max(0, self.raw_accounts - self.distinct_events)

    def as_dict(self) -> dict:
        return {"contract": CONTRACT, "standing": self.standing,
                "raw_accounts": self.raw_accounts,
                "distinct_events": self.distinct_events,
                "independent_support": self.independent_support,
                "weight": self.weight, "sentence": self.sentence,
                "must_bound": self.must_bound,
                "may_claim_independence": self.may_claim_independence,
                "inflation": self.inflation}


#: What an absent standing is worth: nothing, and it says so.
UNRATED = Trust(standing=UNKNOWN, raw_accounts=0, distinct_events=0,
                independent_support=0, weight=0.0, sentence="")


def read(block: Optional[dict]) -> Trust:
    """Consume one producer trust block. A missing block is UNKNOWN.

    Deliberately total: every caller gets a `Trust`, so no call site has to
    remember the None case and quietly skip the check when it forgets.
    """
    if not isinstance(block, dict):
        return UNRATED
    standing = str(block.get("standing") or "").upper()
    if standing not in STANDINGS or standing == UNKNOWN:
        return UNRATED
    return Trust(
        standing=standing,
        raw_accounts=int(block.get("raw_accounts") or 0),
        distinct_events=int(block.get("distinct_events") or 0),
        independent_support=int(block.get("independent_support") or 0),
        weight=float(block.get("weight") or 0.0),
        sentence=str(block.get("sentence") or _FALLBACK.get(standing, "")),
        events=tuple(
            Event(event_id=str(e.get("event_id") or ""),
                  standing=str(e.get("standing") or "").upper(),
                  accounts=int(e.get("accounts") or 0),
                  weight=float(e.get("weight") or 0.0),
                  evidence_ids=tuple(str(x) for x in
                                     (e.get("evidence_ids") or ())))
            for e in (block.get("events") or ()) if isinstance(e, dict)),
    )


def of_belief(belief: Any) -> Trust:
    """The standing of one market belief, however it is carried."""
    if isinstance(belief, dict):
        return read(belief.get("evidence_trust"))
    return read(getattr(belief, "evidence_trust", None))


def sentence(trust: Trust) -> str:
    """What to put on the page, or nothing.

    Empty for the standings that do not change how a sentence should be read.
    A trust note on every claim is a methodology lecture, and a reader who is
    told about sourcing nine times stops reading the tenth — which is the one
    that mattered.
    """
    if not trust.known:
        return ""
    if trust.standing == SINGLE_SOURCE and trust.raw_accounts <= 1:
        # Nothing was inflated and nothing is being claimed. Silence is the
        # honest rendering.
        return ""
    return trust.sentence or _FALLBACK.get(trust.standing, "")


#: The caution a standing earns, when it earns one. Keyed by standing rather
#: than derived from `must_bound`, because those are different questions.
#:
#: UNKNOWN MUST NOT BORROW THE DEPENDENT SENTENCE. "The reports behind this do
#: not independently confirm each other" is a claim ABOUT THE SOURCES, and an
#: unrated dossier is one where nobody looked at the sources. Saying it anyway
#: would assert a fact not in evidence — and would collapse "we checked and it
#: is thin" into "we did not check", which is the exact distinction this
#: module exists to keep.
_LIMITATION: Dict[str, str] = {
    DEPENDENT_REREPORTING:
        "The reports behind this do not independently confirm each other, so "
        "it is weaker than the number of articles suggests.",
    CONFLICTED:
        "Public sources disagree on this point, so it cannot carry a "
        "confident conclusion on its own.",
    UNKNOWN:
        "How independent the sources behind this are was not established, so "
        "it is not treated as confirmed.",
}


def limitation(trust: Trust) -> str:
    """What to add to a block's limitations, or nothing.

    Each standing gets its own sentence or none. A single shared caution would
    say the same thing about evidence that was examined and found thin as
    about evidence nobody examined.
    """
    return _LIMITATION.get(trust.standing, "")


def contains_internal_vocabulary(text: str) -> Sequence[str]:
    """Which internal terms a rendered string leaks. Empty is the pass."""
    low = str(text or "").lower()
    return tuple(sorted(t for t in INTERNAL_TERMS if t in low))


def weigh(trusts: Sequence[Trust]) -> float:
    """The support a conclusion may take from several claims.

    Not `len(trusts)`. An unrated claim contributes nothing, which is why
    `UNRATED.weight` is 0.0 rather than 1.0: a dossier from a producer that
    never normalized must not silently earn the same standing as one that did.
    """
    return round(sum(t.weight for t in trusts), 3)


def weakest(trusts: Sequence[Trust]) -> Trust:
    """The standing a combined reading inherits.

    Same rule as the producer's: the weakest link, never the average. A
    conclusion that needs both a filing and a rumour is a conclusion resting
    on a rumour.
    """
    rated = [t for t in trusts if t.known]
    if not rated:
        return UNRATED
    order = {CONFLICTED: 0, DEPENDENT_REREPORTING: 1, SINGLE_SOURCE: 2,
             PARTIALLY_INDEPENDENT: 3, INDEPENDENTLY_CORROBORATED: 4}
    return min(rated, key=lambda t: order.get(t.standing, 9))
