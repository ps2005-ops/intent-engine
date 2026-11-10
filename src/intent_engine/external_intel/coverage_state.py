"""What kind of nothing this is, when a company has no view yet.

THE DEFECT THIS CLOSES
----------------------
Measured before it was written. At T0 the CEO surface answers every question
about an unanalysed company with one sentence:

    "No economic view is recorded for this company yet."

That sentence is honest and it is also the SAME sentence for six different
situations, only two of which mean the company is uninteresting:

    we have never looked at this company
    we looked and the sources returned nothing
    we are looking right now and are not finished
    we have some evidence and not enough to conclude
    we had evidence and the source that fed it went dark
    we have priors about companies like this and no facts about this one

An executive reading it cannot tell "we have no view" from "we have lost
visibility", and those call for opposite actions: the first is a research
task, the last is a risk. This is the ABSENT / SOURCE_DEGRADED distinction the
engine already enforces per source, applied where it had never been applied —
to the company.

AND THE ONE THING THAT MUST NOT HAPPEN
--------------------------------------
The pressure at T0 is to say something useful, and the useful-sounding thing
is a sector prior: "industrials like this are exposed to rates". That claim is
about a CLASS and it renders in exactly the voice of a claim about a COMPANY.
`macro_exposure` already refuses to derive an exposure from a sector, and this
module carries the same rule up to the surface: every field carries where it
came from, and a field whose origin is a prior may not be rendered in the
voice of an observation. `refuse_prior_as_observation` raises rather than
returning a flag, because a flag is something a renderer can fail to read.

WHAT THIS IS NOT
----------------
Not a hydration transport. There is no streaming layer on this branch and
inventing one would be a fake progress bar over a synchronous call. What is
built is the STATE and the PROVENANCE contract — the part that has to be right
before any transport is worth adding, and the part a later transport will need
to report against.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence, Tuple

from intent_engine.external_intel import standing_ceiling as SC

CONTRACT = "coverage_state.v1"


class CoverageRejected(ValueError):
    """A view that would present a prior as a fact about this company."""


# --- how much is actually known about THIS company --------------------------
#
# Ordered by how much company-specific evidence stands behind the view. The
# order matters for one thing only — deciding whether coverage improved — and
# is deliberately NOT used to rank certainty, because DEGRADED can carry more
# evidence than PARTIALLY_OBSERVED and still deserve less confidence.
NEVER_ANALYSED = "NEVER_ANALYSED"        # no record at all; nobody has looked
PRIOR_ONLY = "PRIOR_ONLY"                # priors exist, company facts do not
HYDRATING = "HYDRATING"                  # retrieval is in flight
PARTIALLY_OBSERVED = "PARTIALLY_OBSERVED"  # some company evidence, no thesis
OBSERVED = "OBSERVED"                    # company evidence carries a view
DEGRADED = "DEGRADED"                    # we had visibility and lost it

COVERAGE_STATES = (NEVER_ANALYSED, PRIOR_ONLY, HYDRATING, PARTIALLY_OBSERVED,
                   OBSERVED, DEGRADED)

#: What each state licenses a surface to assert. Every state short of OBSERVED
#: is ASSERT_NONE: priors and partial evidence support saying what we have,
#: never what is true of the company.
_CEILING = {
    NEVER_ANALYSED: SC.ASSERT_NONE,
    PRIOR_ONLY: SC.ASSERT_NONE,
    HYDRATING: SC.ASSERT_NONE,
    PARTIALLY_OBSERVED: SC.ASSERT_NONE,
    OBSERVED: SC.ASSERT_LEADING,
    DEGRADED: SC.ASSERT_NONE,
}

#: One sentence per state, and they are all different on purpose. If two of
#: these were the same the state would not be worth distinguishing.
STATE_WORDS = {
    NEVER_ANALYSED:
        "We have not analysed this company. Nothing here is a finding about "
        "it — there is no record to have a finding in.",
    PRIOR_ONLY:
        "We have general expectations for companies like this and no facts "
        "about this one. Everything below describes the class, not the "
        "company.",
    HYDRATING:
        "We are still gathering this company's evidence. What is here is "
        "incomplete, and the gaps are not findings.",
    PARTIALLY_OBSERVED:
        "We have some of this company's evidence and not enough to form a "
        "view. What is missing is listed rather than filled in.",
    OBSERVED:
        "We have this company's own evidence, and the view below is drawn "
        "from it.",
    DEGRADED:
        "We had visibility on this company and have lost it. The silence "
        "since is a gap in our sources, not quiet from the company.",
}

#: What a reader must NOT take from each state. The DEGRADED line is the one
#: this module exists for.
MUST_NOT_CONCLUDE = {
    NEVER_ANALYSED:
        "an absence of analysis is not a finding; nothing here says this "
        "company is quiet, safe or uninteresting",
    PRIOR_ONLY:
        "a expectation about companies like this is not a measurement of this "
        "one, and must not be repeated as though it were",
    HYDRATING:
        "an incomplete picture is not a negative one; what is not here yet "
        "has not been looked for and found absent",
    PARTIALLY_OBSERVED:
        "the evidence we have is not the evidence there is; a gap is a gap in "
        "our retrieval before it is a gap in the company",
    OBSERVED:
        "having this company's evidence is not having all of it",
    DEGRADED:
        "fewer observations is reduced visibility, never reduced activity; "
        "this company has not been shown to have stopped doing anything",
}

# --- where a single value came from -----------------------------------------
GLOBAL_PRIOR = "GLOBAL_PRIOR"                # true of companies in general
SECTOR_PRIOR = "SECTOR_PRIOR"                # true of this sector
COMPANY_OBSERVATION = "COMPANY_OBSERVATION"  # this company's own evidence
INFERRED = "INFERRED"                        # derived, not stated anywhere
UNAVAILABLE = "UNAVAILABLE"                  # we looked and have nothing
ORIGINS = (GLOBAL_PRIOR, SECTOR_PRIOR, COMPANY_OBSERVATION, INFERRED,
           UNAVAILABLE)

#: Origins that are claims about a CLASS rather than about this company. The
#: sector prior is the dangerous one: it is specific enough to sound
#: researched and general enough to be true of a company that has just done
#: the opposite.
PRIORS = frozenset({GLOBAL_PRIOR, SECTOR_PRIOR})

#: The only origin that may be spoken in the indicative about this company.
OBSERVATIONS = frozenset({COMPANY_OBSERVATION})

#: How each origin must be introduced. A renderer that drops the lead-in is
#: caught by `refuse_prior_as_observation`, not by review.
ORIGIN_VOICE = {
    GLOBAL_PRIOR: "for companies in general",
    SECTOR_PRIOR: "for companies in this sector",
    COMPANY_OBSERVATION: "",
    INFERRED: "inferred, not stated in any source",
    UNAVAILABLE: "not available",
}


@dataclass(frozen=True)
class Attributed:
    """One value and where it came from. The pair travels or neither does."""

    field: str
    value: Any
    origin: str
    evidence_ids: Tuple[str, ...] = ()
    note: str = ""

    def __post_init__(self) -> None:
        if self.origin not in ORIGINS:
            raise CoverageRejected(f"unknown origin {self.origin!r}")
        if self.origin == COMPANY_OBSERVATION and not self.evidence_ids:
            raise CoverageRejected(
                f"{self.field} claims to be this company's own observation "
                "and cites nothing. An observation without an evidence id is "
                "indistinguishable from a prior somebody relabelled, which is "
                "the one substitution this contract exists to prevent")
        if self.origin in PRIORS and self.evidence_ids:
            raise CoverageRejected(
                f"{self.field} is a {self.origin} carrying evidence ids. If "
                "this company's documents establish it, its origin is "
                f"{COMPANY_OBSERVATION}; if they do not, the ids belong to "
                "some other company and must not travel with it")

    @property
    def is_prior(self) -> bool:
        return self.origin in PRIORS

    @property
    def speakable(self) -> bool:
        """Whether this may be stated as a fact about the company."""
        return self.origin in OBSERVATIONS

    def as_dict(self) -> dict:
        out = dataclasses.asdict(self)
        out.update(evidence_ids=list(self.evidence_ids),
                   is_prior=self.is_prior, speakable=self.speakable,
                   voice=ORIGIN_VOICE[self.origin])
        return out


def refuse_prior_as_observation(fields: Sequence[Attributed],
                                *, surface: str = "surface") -> None:
    """Raise if anything not observed would be spoken as observed.

    A raise rather than a flag. The failure mode here is a renderer that reads
    the value and not the origin, and a flag is exactly what such a renderer
    fails to read.
    """
    offenders = [f.field for f in fields
                 if not f.speakable and f.origin != UNAVAILABLE
                 and not str(f.note or "").strip()]
    if offenders:
        raise CoverageRejected(
            f"{surface} would present {', '.join(sorted(offenders))} as "
            "though observed. A value that is not this company's own evidence "
            "must carry the lead-in that says so")


# --- classification ---------------------------------------------------------

def classify(intel, *, hydrating: bool = False,
             degraded_sources: Sequence[str] = ()) -> str:
    """Which kind of nothing — or something — this is.

    `hydrating` and `degraded_sources` are passed in rather than inferred,
    because neither is knowable from the dossier alone: a partially-filled
    dossier looks identical whether retrieval is still running or finished
    empty, and that is precisely the pair this module refuses to collapse.
    """
    theses = tuple(getattr(intel, "economic_theses", ()) or ())
    evidence = tuple(getattr(intel, "evidence_ids", ()) or ())
    beliefs = tuple(getattr(intel, "beliefs", ()) or ())
    available = getattr(intel, "available", None)

    if degraded_sources and (theses or evidence or beliefs):
        # Had visibility, lost some. Checked BEFORE the positive states: a
        # dossier that still carries yesterday's theses while today's source
        # is dark is exactly the case that reads as OBSERVED and is not.
        return DEGRADED
    if hydrating:
        return HYDRATING
    if theses:
        return OBSERVED
    if evidence or beliefs:
        return PARTIALLY_OBSERVED
    if available is False:
        return NEVER_ANALYSED
    return NEVER_ANALYSED


def ceiling_for(state: str) -> str:
    if state not in _CEILING:
        # An unrecognised coverage state licenses nothing, for the same reason
        # an unrecognised standing does: not knowing how much we know is not
        # evidence that we know a lot.
        return SC.ASSERT_NONE
    return _CEILING[state]


@dataclass(frozen=True)
class Coverage:
    """The T0 baseline: what state this company is in, and what may be said."""

    company: str
    state: str
    fields: Tuple[Attributed, ...] = ()
    missing: Tuple[str, ...] = ()
    degraded_sources: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.state not in COVERAGE_STATES:
            raise CoverageRejected(f"unknown coverage state {self.state!r}")
        if self.state == DEGRADED and not self.degraded_sources:
            raise CoverageRejected(
                "DEGRADED without naming which source went dark; an unnamed "
                "degradation cannot be chased, recovered or aged out")
        if self.state == OBSERVED and not any(
                f.speakable for f in self.fields):
            raise CoverageRejected(
                "OBSERVED with no field drawn from this company's own "
                "evidence; the state claims exactly what the fields deny")

    @property
    def ceiling(self) -> str:
        return ceiling_for(self.state)

    @property
    def speakable_fields(self) -> Tuple[Attributed, ...]:
        return tuple(f for f in self.fields if f.speakable)

    @property
    def prior_fields(self) -> Tuple[Attributed, ...]:
        return tuple(f for f in self.fields if f.is_prior)

    @property
    def reading(self) -> str:
        return STATE_WORDS[self.state]

    @property
    def must_not_conclude(self) -> str:
        return MUST_NOT_CONCLUDE[self.state]

    def as_dict(self) -> dict:
        return {
            "contract": CONTRACT,
            "company": self.company,
            "state": self.state,
            "ceiling": self.ceiling,
            "reading": self.reading,
            "must_not_conclude": self.must_not_conclude,
            "fields": [f.as_dict() for f in self.fields],
            "observed_fields": len(self.speakable_fields),
            "prior_fields": len(self.prior_fields),
            "missing": list(self.missing),
            "degraded_sources": list(self.degraded_sources),
            "note": ("state describes how much of THIS COMPANY we have seen; "
                     "it is not a judgement about the company"),
        }


def baseline(intel, *, company: str = "", hydrating: bool = False,
             degraded_sources: Sequence[str] = (),
             fields: Sequence[Attributed] = (),
             missing: Sequence[str] = ()) -> Coverage:
    """The T0 view, with every element carrying where it came from."""
    state = classify(intel, hydrating=hydrating,
                     degraded_sources=degraded_sources)
    return Coverage(
        company=company or str(getattr(intel, "company_id", "") or ""),
        state=state, fields=tuple(fields),
        missing=tuple(missing), degraded_sources=tuple(degraded_sources))


def improved(before: str, after: str) -> bool:
    """Whether coverage genuinely improved, for a hydration step.

    DEGRADED is excluded from the ladder rather than placed at the bottom:
    going from DEGRADED to PARTIALLY_OBSERVED is not an improvement in the
    same sense as going from NEVER_ANALYSED to PARTIALLY_OBSERVED, because
    the first means a source came back and the second means one arrived.
    """
    ladder = (NEVER_ANALYSED, PRIOR_ONLY, HYDRATING, PARTIALLY_OBSERVED,
              OBSERVED)
    if before not in ladder or after not in ladder:
        return False
    return ladder.index(after) > ladder.index(before)


def replacements(before: Sequence[Attributed],
                 after: Sequence[Attributed]) -> Tuple[dict, ...]:
    """Which priors company evidence has replaced, stated rather than silent.

    A prior quietly becoming an observation is the moment the page starts
    saying something new without saying that it changed. Hydration has to be
    visible or it is indistinguishable from the engine having always known.
    """
    was = {f.field: f for f in before}
    out = []
    for field in after:
        old = was.get(field.field)
        if old is None or old.origin == field.origin:
            continue
        out.append({
            "field": field.field,
            "from_origin": old.origin,
            "to_origin": field.origin,
            "from_value": old.value,
            "to_value": field.value,
            "evidence_ids": list(field.evidence_ids),
            "note": (f"was {ORIGIN_VOICE[old.origin] or 'this company'}, "
                     f"now {ORIGIN_VOICE[field.origin] or 'this company'}"),
        })
    return tuple(out)
