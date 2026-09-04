"""How a thesis fails while still looking right, and who would have to act.

WHAT THE OTHER LAYERS ALREADY DO
--------------------------------
`economic_thesis` states what is believed and what would falsify it.
`reactions` builds a tree of how rivals might answer one strategic MOVE.
`alternative_explanations` holds the rival readings of the same evidence.

None of them answers the question an executive actually asks before committing:
not "might this be wrong" but "if I act on this and it goes badly, what will
the post-mortem say". A falsifier is an observation that would end the reading.
A failure path is a STORY — an assumption the thesis needs and does not state,
a counterparty with a reason to attack it, and the conditions under which the
mechanism holds right up until it does not.

WHY THIS IS NOT AN AGENT
------------------------
Deliberately not a simulation, not a model call, and not a competitor's mind.
An AdversaryCase is one analytical object assembled from records that already
exist: the thesis, its falsifiers, its mechanisms, its alternatives, and the
actor evidence the engine has actually seen. Generating plausible-sounding
adversaries is the easiest thing in this whole system to do and the least
worth doing, because a fluent attack with no evidence behind it is
indistinguishable from a real one at the moment somebody has to decide.

THE STANDING IS THE PRODUCT
---------------------------
Four standings, and the ordering between them is the whole guard:

    CAPABILITY            the rival CAN do this — evidence of means
    INCENTIVE             the rival has a REASON to — evidence of motive
    OBSERVED_ACTION       the rival HAS done this, here or before
    HYPOTHESIZED_RESPONSE nothing observed; this is a move we thought of

A response may not exceed HYPOTHESIZED_RESPONSE unless evidence names it. The
failure this prevents is the one every competitive-intelligence product makes:
"a competitor will cut prices" derived from the existence of a competitor.
Existence is not capability, capability is not incentive, and none of the three
is an action. `from_rival_existence` is a constructor that refuses.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

CONTRACT = "adversary_case.v1"


class AdversaryRejected(ValueError):
    """A failure path that asserted more than the record behind it."""


class UnevidencedResponse(AdversaryRejected):
    """A predicted action derived from a rival's existence."""


# --- how well a counterparty response is known ------------------------------
CAPABILITY = "CAPABILITY"                        # means, evidenced
INCENTIVE = "INCENTIVE"                          # motive, evidenced
OBSERVED_ACTION = "OBSERVED_ACTION"              # they did it
HYPOTHESIZED_RESPONSE = "HYPOTHESIZED_RESPONSE"  # we thought of it
RESPONSE_STANDINGS = (HYPOTHESIZED_RESPONSE, CAPABILITY, INCENTIVE,
                      OBSERVED_ACTION)

#: What each standing is entitled to say, so a renderer cannot promote one.
RESPONSE_WORDS = {
    HYPOTHESIZED_RESPONSE: "a move we have thought of; nothing observed "
                           "suggests they will make it",
    CAPABILITY: "they have the means to do this; nothing says they intend to",
    INCENTIVE: "they have a reason to do this; nothing says they can, or will",
    OBSERVED_ACTION: "they have done this, and the evidence names when",
}

#: Standings that require evidence naming the rival's means, motive or act. A
#: response at any of these without `evidence_ids` is the failure this module
#: exists to prevent.
EVIDENCED = frozenset({CAPABILITY, INCENTIVE, OBSERVED_ACTION})

# --- how strongly the case as a whole is held -------------------------------
SPECULATIVE = "SPECULATIVE"      # no evidenced response anywhere
GROUNDED = "GROUNDED"            # at least one evidenced response
DEMONSTRATED = "DEMONSTRATED"    # a response this rival has actually taken
CASE_STANDINGS = (SPECULATIVE, GROUNDED, DEMONSTRATED)


@dataclass(frozen=True)
class CounterpartyResponse:
    """One thing somebody else could do, and how well that is known."""

    actor: str
    action: str
    standing: str = HYPOTHESIZED_RESPONSE
    evidence_ids: Tuple[str, ...] = ()
    observed_at: str = ""
    note: str = ""

    def __post_init__(self) -> None:
        if not self.actor.strip():
            raise AdversaryRejected("a response needs the actor who makes it")
        if not self.action.strip():
            raise AdversaryRejected(
                f"{self.actor} is named without an action; a counterparty who "
                "does nothing in particular is not a failure path")
        if self.standing not in RESPONSE_STANDINGS:
            raise AdversaryRejected(f"unknown standing {self.standing!r}")
        if self.standing in EVIDENCED and not self.evidence_ids:
            raise UnevidencedResponse(
                f"{self.actor} is recorded at {self.standing} with no "
                "evidence naming it. Being a competitor is not a capability, "
                "a capability is not an incentive, and none of them is an "
                f"action — this response may be {HYPOTHESIZED_RESPONSE} and "
                "nothing more")
        if self.standing == OBSERVED_ACTION and not self.observed_at:
            raise AdversaryRejected(
                f"{self.actor} is recorded as having acted without a date; an "
                "undated action cannot be checked and cannot be aged out")

    @property
    def evidenced(self) -> bool:
        return self.standing in EVIDENCED

    @property
    def reading(self) -> str:
        return RESPONSE_WORDS[self.standing]

    def as_dict(self) -> dict:
        out = dataclasses.asdict(self)
        out.update(evidence_ids=list(self.evidence_ids),
                   evidenced=self.evidenced, reading=self.reading)
        return out


@dataclass(frozen=True)
class AdversaryCase:
    """One way this thesis fails while still looking right on the day.

    `required_conditions` is the field that does the work. A mechanism holds
    subject to things nobody wrote down — a supplier staying solvent, a
    contract renewing, a rival staying out. Those are the conditions the
    thesis SILENTLY requires, and naming them is most of what a premortem is
    for.
    """

    thesis_id: str
    subject: str
    #: The story, in one sentence: how this ends badly.
    failure_path: str
    #: The premise the thesis rests on without saying so.
    attacked_assumption: str
    #: What somebody else would have to do. May be empty — not every failure
    #: needs an adversary, and inventing one is worse than having none.
    responses: Tuple[CounterpartyResponse, ...] = ()
    #: What has to stay true for the thesis to hold.
    required_conditions: Tuple[str, ...] = ()
    #: What would be visible FIRST if this were happening.
    early_warning: Tuple[str, ...] = ()
    #: What could be done about it now, while it is still cheap.
    mitigation: Tuple[str, ...] = ()
    #: The observation that says stop, and the one that says reverse.
    kill_condition: str = ""
    reversal_condition: str = ""
    as_of: str = ""

    def __post_init__(self) -> None:
        for name in ("failure_path", "attacked_assumption"):
            if not str(getattr(self, name)).strip():
                raise AdversaryRejected(
                    f"an adversary case needs a {name}; without one it is a "
                    "worry rather than an analysis")
        if not self.early_warning:
            raise AdversaryRejected(
                "an adversary case needs at least one early warning: a "
                "failure nobody could see coming is not actionable, and "
                "listing it without one is a way of sounding careful")
        if not self.kill_condition.strip():
            raise AdversaryRejected(
                "an adversary case needs a kill condition; a risk with no "
                "stopping rule is a risk nobody will act on")

    @property
    def standing(self) -> str:
        """How well the case as a whole is grounded.

        SPECULATIVE is the honest and common answer, and it is deliberately
        not hidden: a case built entirely from moves we thought of is worth
        reading and is not worth acting on, and the two need different words.
        """
        if any(r.standing == OBSERVED_ACTION for r in self.responses):
            return DEMONSTRATED
        if any(r.evidenced for r in self.responses):
            return GROUNDED
        return SPECULATIVE

    @property
    def actionable(self) -> bool:
        """Whether this case may drive a decision rather than a watch item."""
        return self.standing in (GROUNDED, DEMONSTRATED)

    def as_dict(self) -> dict:
        out = dataclasses.asdict(self)
        out.update(contract=CONTRACT, standing=self.standing,
                   actionable=self.actionable,
                   responses=[r.as_dict() for r in self.responses],
                   required_conditions=list(self.required_conditions),
                   early_warning=list(self.early_warning),
                   mitigation=list(self.mitigation),
                   note=("standing describes how well the ATTACK is "
                         "evidenced, not how likely the thesis is to fail"))
        return out


# --- construction from records that already exist ---------------------------

def _field(obj, name: str, default=""):
    """Read a field from an OBJECT or a PERSISTED ROW, because both reach here.

    The cycle holds `EconomicThesis` objects; the store returns the dicts it
    wrote. A getattr-only reader folds every persisted row to empty and
    produces zero cases silently — which looks exactly like a corpus with no
    alternatives in it, and this engine has shipped that confusion more than
    once.
    """
    if isinstance(obj, dict):
        value = obj.get(name, default)
    else:
        value = getattr(obj, name, default)
    return default if value is None else value

def from_rival_existence(thesis_id: str, subject: str, rival: str,
                         action: str = "cut prices") -> CounterpartyResponse:
    """The constructor that refuses. Kept as a named function on purpose.

    "A competitor will cut prices because it is a competitor" is the single
    most common thing a competitive-intelligence layer produces, and it is
    produced by code that looks entirely reasonable: iterate the rivals,
    attach the obvious move. Making that path a function that raises means the
    next person to write it finds this instead of writing it again.
    """
    raise UnevidencedResponse(
        f"{rival} is a competitor of {subject}; that is not evidence it will "
        f"{action}. Existence is not capability, capability is not incentive, "
        "and neither is an action. Build the response at "
        f"{HYPOTHESIZED_RESPONSE} and say so, or cite the evidence that names "
        "the means, the motive or the act")


def from_thesis(thesis, *, failure_path: str, attacked_assumption: str,
                responses: Sequence[CounterpartyResponse] = (),
                required_conditions: Sequence[str] = (),
                mitigation: Sequence[str] = (),
                as_of: str = "") -> AdversaryCase:
    """Build a case whose early warnings come from the thesis's own falsifiers.

    The early warning is NOT invented here. A thesis already carries the
    observations that would end it; the first of those to appear is, by
    construction, the earliest visible sign that this failure is happening.
    Composing a fresh list of warning signs would be writing rather than
    reading, and the two would drift.
    """
    falsifiers = tuple(getattr(thesis, "falsifiers", ()) or ())
    if not falsifiers:
        raise AdversaryRejected(
            "this thesis carries no falsifier, so there is nothing that would "
            "show the failure happening; the gap is in the thesis and filling "
            "it here would hide that")
    mechanism = getattr(thesis, "leading_mechanism", None)
    return AdversaryCase(
        thesis_id=str(getattr(thesis, "thesis_id", "")),
        subject=str(getattr(thesis, "subject", "")),
        failure_path=failure_path,
        attacked_assumption=attacked_assumption,
        responses=tuple(responses),
        required_conditions=tuple(required_conditions),
        early_warning=falsifiers,
        mitigation=tuple(mitigation),
        kill_condition=falsifiers[0],
        reversal_condition=str(getattr(mechanism, "falsifier", "")
                               or falsifiers[0]),
        as_of=as_of or str(getattr(thesis, "as_of", "")))


def from_alternatives(thesis, *, as_of: str = "") -> List[AdversaryCase]:
    """One case per live alternative, with both fields READ rather than written.

    THIS IS THE PRODUCTION CONSTRUCTOR, and it composes nothing. A thesis's
    alternatives are already the rival readings the engine could not exclude —
    which means each one is precisely an assumption the leading reading relies
    on without saying so. "The exposure was hedged" is a rival explanation and
    also the unstated premise "it was not hedged"; the failure path is what
    happens when the rival reading turns out to have been the right one.

    Every case built here is SPECULATIVE, because a press-release corpus
    carries no evidence of a counterparty's means or motive. That is the
    honest output and it is not hidden: a speculative case is worth reading
    and is not actionable, and `standing` says which.
    """
    alternatives = tuple(_field(thesis, "alternatives", ()) or ())
    out: List[AdversaryCase] = []
    for alternative in alternatives:
        description = str(_field(alternative, "description", "") or "").strip()
        falsifier = str(_field(alternative, "falsifier", "") or "").strip()
        if not description or not falsifier:
            # A blank alternative is a gap in the thesis, not a failure path.
            # Rendering one produced "the strongest recorded alternative is: "
            # with nothing after the colon on a live dossier once already.
            continue
        out.append(AdversaryCase(
            thesis_id=str(_field(thesis, "thesis_id", "")),
            subject=str(_field(thesis, "subject", "")),
            failure_path=(f"the reading holds up until it does not: "
                          f"{description}, and the decision taken on the "
                          "leading explanation was taken for the wrong "
                          "reason"),
            attacked_assumption=f"that it is not the case that {description}",
            responses=(),
            required_conditions=(f"not the case that {description}",),
            early_warning=(falsifier,),
            kill_condition=falsifier,
            reversal_condition=falsifier,
            as_of=as_of or str(getattr(thesis, "as_of", ""))))
    return out


def strongest(cases: Sequence[AdversaryCase]) -> Optional[AdversaryCase]:
    """The most defensible case, which is not the most alarming one.

    Ordered by how well the ATTACK is evidenced, never by how bad the outcome
    would be. Ranking by severity is how a speculative catastrophe outranks an
    observed erosion, and the speculative one is the one nobody can act on.
    """
    if not cases:
        return None
    order = {DEMONSTRATED: 2, GROUNDED: 1, SPECULATIVE: 0}
    return max(cases, key=lambda c: (order[c.standing],
                                     sum(1 for r in c.responses if r.evidenced),
                                     len(c.early_warning)))


def summarise(cases: Sequence[AdversaryCase]) -> dict:
    """Counts by standing, with the speculative share stated rather than hidden."""
    by_standing = {s: sum(1 for c in cases if c.standing == s)
                   for s in CASE_STANDINGS}
    best = strongest(cases)
    return {
        "contract": CONTRACT,
        "cases": len(cases),
        "by_standing": by_standing,
        "actionable": sum(1 for c in cases if c.actionable),
        "strongest": best.as_dict() if best else None,
        "note": ("cases are ranked by how well the attack is evidenced, never "
                 "by how bad the outcome would be; ranking by severity puts a "
                 "speculative catastrophe above an observed erosion"),
    }
