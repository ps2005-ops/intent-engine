"""A thesis, its rivals, its proof, and what would sink it.

WHY THE THESIS IS A RECORD AND NOT A PARAGRAPH
----------------------------------------------
Because prose cannot be checked. A well-written paragraph about a company's
margins carries a claim, an implied mechanism, an unstated alternative and a
confidence, all fused, and there is no way to ask it what would change its
mind. Once the paragraph is the source of truth, the slide, the briefing and
the answer to "why do you believe that" each get rewritten from scratch by
whoever renders them, and they drift.

So the thesis is a structure and every surface is a projection of it. A
presentation may say less than the thesis. It may never say more — and
`consistent_with` is where that is enforced rather than hoped for.

WHY LOSING THESES ARE KEPT
--------------------------
A thesis that was beaten is the record of what the engine considered and
rejected, and it is the only thing that makes a later reversal legible. Theses
supersede; they are not deleted.

OUTCOME AND MECHANISM ARE SCORED SEPARATELY
-------------------------------------------
"Margins will improve" can be right because the company raised prices, or
right because it laid off a quarter of its staff, and a thesis that predicted
the first while the second happened was WRONG in the way that matters — it
will be wrong again next quarter. Collapsing the two into "correct" is how a
system learns to be lucky.

WHAT A PROOF IS NOT
-------------------
It is not a pile of citations. A proof that cannot state the alternative it
ruled out, the evidence that argues against it, and the observation that would
end it, is a bibliography. `ProofPackage` refuses to report VERIFIED for a
claim whose falsifier has not been tested, however many sources agree.
"""
from __future__ import annotations

import dataclasses
import hashlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

CONTRACT = "economic_thesis.v1"

#: Separators for the identity hash, named rather than written inline because
#: a control character in a source file is invisible in every editor and this
#: one decides whether two theses are the same thesis. Not "|" or " ": a
#: mechanism key is free text here, and joining on a printable character lets
#: one field's content impersonate a field boundary — which is the identity
#: collision this whole derivation exists to prevent.
_FIELD_SEP = "\x00"
_LIST_SEP = "\x1f"

# --- how strongly a thesis is held ------------------------------------------
#
# There is no CONFIRMED. The strongest available standing says the falsifier
# was tested and survived, which is a different and smaller claim than truth.
PROPOSED = "PROPOSED"            # stated, nothing tested
SUPPORTED = "SUPPORTED"          # evidence consistent, falsifier untested
TESTED = "TESTED"                # falsifier tested and survived
WEAKENED = "WEAKENED"            # counterevidence, not yet fatal
REFUTED = "REFUTED"              # falsifier fired
SUPERSEDED = "SUPERSEDED"        # replaced by a later thesis
STANDINGS = (PROPOSED, SUPPORTED, TESTED, WEAKENED, REFUTED, SUPERSEDED)

#: Standings a surface may present as a conclusion rather than a question.
ASSERTABLE = frozenset({SUPPORTED, TESTED})

_ORDER = {PROPOSED: 0, WEAKENED: 1, SUPPORTED: 2, TESTED: 3,
          REFUTED: -1, SUPERSEDED: -2}

# --- what a proof came to ----------------------------------------------------
OPEN = "OPEN"                    # nothing has resolved it yet
BOUNDED = "BOUNDED"              # true within stated limits
VERIFIED = "VERIFIED"            # falsifier tested, evidence independent
FAILED = "FAILED"                # the claim did not survive
PROOF_STATUSES = (OPEN, BOUNDED, VERIFIED, FAILED)


class ThesisRejected(ValueError):
    """A thesis that asserted more than its structure supports."""


class Overclaim(ThesisRejected):
    """Raised when a surface would say more than the thesis it renders."""


@dataclass(frozen=True)
class Mechanism:
    """How the effect is supposed to travel, and what would show it did not."""

    description: str
    direction: str = ""
    lag_days: int = 0
    #: The observation that would end this mechanism's candidacy. Required:
    #: a mechanism nothing could disprove explains every outcome equally well
    #: and therefore explains none of them.
    falsifier: str = ""
    evidence_ids: Tuple[str, ...] = ()
    standing: str = PROPOSED
    #: WHICH ROUTE THIS IS, stable under rewording. `description` is the
    #: sentence a reader sees and is expected to be edited; a thesis whose
    #: identity is derived from it would become a different thesis the day
    #: somebody improved the wording, and its history would restart silently.
    #: Callers that select a mechanism from a fixed catalogue pass the
    #: catalogue's key here. Left empty, the description is the key, which is
    #: correct for one-off mechanisms nobody will reword.
    key: str = ""

    def __post_init__(self) -> None:
        if not self.description.strip():
            raise ThesisRejected("a mechanism needs a description")
        if not self.falsifier.strip():
            raise ThesisRejected(
                "a mechanism needs a falsifier: one that nothing could "
                "disprove fits every outcome and discriminates none")
        if self.standing not in STANDINGS:
            raise ThesisRejected(f"unknown standing {self.standing!r}")

    @property
    def identity_key(self) -> str:
        return self.key.strip() or self.description.strip()

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclass(frozen=True)
class EconomicThesis:
    """One dated answer to one question about one subject."""

    subject: str
    question: str
    claim: str
    leading_mechanism: Mechanism
    #: Every explanation still alive. Empty is not allowed for an assertable
    #: thesis — "nothing else could explain this" is a claim, and an empty
    #: list is that claim made silently.
    alternatives: Tuple[Mechanism, ...] = ()
    #: WHICH ECONOMY the condition was measured in. An `EconomicState` is
    #: keyed `(area, state_kind)` and always has been; the thesis built from
    #: one used to keep only the kind. A live cycle therefore held a thesis
    #: about Canadian market rates and a thesis about US market rates for the
    #: same company, gave them the same identity, and persisted one of them.
    area: str = ""
    macro_conditions: Tuple[str, ...] = ()
    exposures: Tuple[str, ...] = ()
    supporting_evidence: Tuple[str, ...] = ()
    contradicting_evidence: Tuple[str, ...] = ()
    unknowns: Tuple[str, ...] = ()
    horizon_days: int = 90
    standing: str = PROPOSED
    as_of: str = ""
    supersedes: str = ""
    note: str = ""

    def __post_init__(self) -> None:
        if self.standing not in STANDINGS:
            raise ThesisRejected(f"unknown standing {self.standing!r}")
        if not self.as_of:
            raise ThesisRejected("a thesis needs the date it was formed")
        if self.standing in ASSERTABLE and not self.alternatives:
            raise ThesisRejected(
                "a thesis may not be asserted without a live alternative; an "
                "empty list is the claim 'nothing else could explain this' "
                "made without saying so")
        if self.standing == TESTED and not self.supporting_evidence:
            raise ThesisRejected(
                "a tested thesis needs the evidence that tested it")

    @property
    def question_key(self) -> Tuple[str, str, str]:
        """The question this answers. Rival theses share it; others must not.

        Used to group competitions. It deliberately excludes the exposure and
        the mechanism, because two routes from one condition to one company
        ARE rival explanations and should meet. It includes `area`, because
        two different economies are two different questions, and grouping
        them together manufactured contests between theses that were never in
        disagreement — they were about different countries.
        """
        return (self.subject, self.area, self.question)

    @property
    def identity(self) -> Tuple[str, ...]:
        """What makes this THIS thesis, across cycles and across rewrites.

        THREE THINGS ARE DELIBERATELY ABSENT, and each was in the previous
        derivation:

        `as_of` — a thesis restated tomorrow is the same thesis. Keying on
        the date meant every thesis was new every night, which is the whole
        comparison this record exists to make.

        `claim` — the claim is the thing that MOVES. A thesis whose claim
        changed by one word became a different thesis with an empty history,
        so the one event worth recording was the one event that destroyed the
        record of it.

        `standing` and evidence — a thesis does not become a different thesis
        by being believed more, or by acquiring a citation.

        What remains is the question it answers and the route it answers it
        by: subject, economy, question, exposure, condition, mechanism. Two
        theses agreeing on all six are the same thesis. Two differing on any
        are rivals or strangers, and must reconcile separately.
        """
        return (
            self.subject,
            self.area,
            self.question,
            _LIST_SEP.join(sorted(self.exposures or ())),
            _LIST_SEP.join(sorted(self.macro_conditions or ())),
            self.leading_mechanism.identity_key,
        )

    @property
    def thesis_id(self) -> str:
        raw = _FIELD_SEP.join(self.identity)
        return "th_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    @property
    def falsifiers(self) -> Tuple[str, ...]:
        return tuple([self.leading_mechanism.falsifier]
                     + [m.falsifier for m in self.alternatives])

    @property
    def assertable(self) -> bool:
        return self.standing in ASSERTABLE

    def as_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d.update(contract=CONTRACT, thesis_id=self.thesis_id,
                 assertable=self.assertable, falsifiers=list(self.falsifiers))
        return d


def supersede(previous: EconomicThesis, *, claim: str, as_of: str,
              standing: str = PROPOSED, **changes) -> Tuple[EconomicThesis,
                                                            EconomicThesis]:
    """A new thesis and the retired one, both returned.

    Returns both because the caller must store both. A revision that only
    hands back the new thesis makes it easy to drop the old one, and the
    record of what the engine used to believe is the only thing that makes a
    reversal legible instead of looking like the engine was always right.
    """
    retired = dataclasses.replace(previous, standing=SUPERSEDED)
    successor = dataclasses.replace(previous, claim=claim, as_of=as_of,
                                    standing=standing,
                                    supersedes=previous.thesis_id, **changes)
    # A SUPERSESSION MUST PRODUCE A DIFFERENT THESIS. Identity no longer
    # includes the claim or the date, so rewording a claim yields a successor
    # with the SAME id — which would make `supersedes` a self-reference, put
    # two rows with one id into the same Competition, and give reconciliation
    # two priors for one identity. A claim that moved while the question, the
    # exposure and the mechanism stayed put is a revision of this thesis, and
    # `thesis_history` is where that is recorded.
    if successor.thesis_id == previous.thesis_id:
        raise ThesisRejected(
            "this supersession changes only the wording: the successor has "
            f"the same identity ({previous.thesis_id}) as the thesis it "
            "claims to replace. A thesis is superseded by a DIFFERENT "
            "explanation — a different mechanism, exposure or question. Record "
            "a reworded claim as a revision in thesis_history instead")
    return successor, retired


# --- competition ----------------------------------------------------------------

@dataclass(frozen=True)
class Competition:
    """Several theses answering one question, ranked and none deleted."""

    question: str
    subject: str
    theses: Tuple[EconomicThesis, ...]

    @property
    def live(self) -> Tuple[EconomicThesis, ...]:
        return tuple(t for t in self.theses
                     if t.standing not in (REFUTED, SUPERSEDED))

    @property
    def leader(self) -> Optional[EconomicThesis]:
        """The strongest live thesis, or nothing when several tie.

        RETURNS NOTHING ON A TIE, deliberately. Two equally supported and
        mutually exclusive explanations is the most decision-relevant state
        this object can be in, and picking one by list order would hide it
        behind a confident sentence.
        """
        live = self.live
        if not live:
            return None
        best = max(_ORDER.get(t.standing, 0) for t in live)
        top = [t for t in live if _ORDER.get(t.standing, 0) == best]
        return top[0] if len(top) == 1 else None

    @property
    def contested(self) -> bool:
        return self.leader is None and len(self.live) > 1

    def as_dict(self) -> dict:
        leader = self.leader
        return {"contract": CONTRACT, "question": self.question,
                "subject": self.subject,
                "theses": [t.as_dict() for t in self.theses],
                "live": len(self.live), "retired": len(self.theses)
                - len(self.live),
                "leader": leader.thesis_id if leader else "",
                "contested": self.contested,
                "note": ("a tie returns no leader; two live explanations is "
                         "the answer, not a problem to be broken")}


# --- outcome and mechanism, scored apart ------------------------------------------

OUTCOME_CORRECT = "OUTCOME_CORRECT"
OUTCOME_WRONG = "OUTCOME_WRONG"
MECHANISM_CORRECT = "MECHANISM_CORRECT"
MECHANISM_WRONG = "MECHANISM_WRONG"
MECHANISM_UNTESTED = "MECHANISM_UNTESTED"

#: The result that looks like success and teaches nothing.
RIGHT_FOR_THE_WRONG_REASON = "RIGHT_FOR_THE_WRONG_REASON"


@dataclass(frozen=True)
class ThesisScore:
    """What a resolved thesis actually got right."""

    thesis_id: str
    outcome: str
    mechanism: str
    verdict: str
    note: str = ""

    def as_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d.update(contract=CONTRACT)
        return d


def score(thesis: EconomicThesis, *, outcome_matched: bool,
          mechanism_matched: Optional[bool]) -> ThesisScore:
    """Grade an outcome and a mechanism separately, and name the dangerous case.

    `mechanism_matched=None` is untested, not false. A thesis whose mechanism
    nobody checked is not a thesis that was wrong about it, and treating the
    two alike would let an unexamined explanation accumulate a track record.
    """
    out = OUTCOME_CORRECT if outcome_matched else OUTCOME_WRONG
    if mechanism_matched is None:
        mech = MECHANISM_UNTESTED
    else:
        mech = MECHANISM_CORRECT if mechanism_matched else MECHANISM_WRONG
    if outcome_matched and mech == MECHANISM_WRONG:
        verdict = RIGHT_FOR_THE_WRONG_REASON
        note = ("the prediction landed and the explanation did not; this "
                "thesis will be wrong again on the same reasoning")
    elif outcome_matched and mech == MECHANISM_CORRECT:
        verdict = "CORRECT"
        note = "outcome and mechanism both survived"
    elif outcome_matched:
        verdict = "OUTCOME_ONLY"
        note = "the outcome landed; nobody checked why"
    else:
        verdict = "WRONG"
        note = "the outcome did not land"
    return ThesisScore(thesis_id=thesis.thesis_id, outcome=out,
                       mechanism=mech, verdict=verdict, note=note)


# --- proof ----------------------------------------------------------------------

@dataclass(frozen=True)
class ProofPackage:
    """What can honestly be said for one claim, and what is still open."""

    claim: str
    evidence_ids: Tuple[str, ...]
    independent_sources: int
    causal_basis: str
    alternative_explanations: Tuple[str, ...]
    counterevidence: Tuple[str, ...]
    falsifier: str
    falsifier_tested: bool
    prediction: str = ""
    limitations: Tuple[str, ...] = ()
    as_of: str = ""

    @property
    def status(self) -> str:
        """VERIFIED is rare on purpose.

        Agreement among sources is not proof; three outlets repeating one
        press release is one source. VERIFIED requires the falsifier to have
        been tested AND more than one independent source AND no live
        counterevidence, and anything short of that is BOUNDED or OPEN.
        """
        if self.counterevidence and not self.falsifier_tested:
            return OPEN
        if not self.evidence_ids:
            return OPEN
        if self.falsifier_tested and self.independent_sources >= 2 \
                and not self.counterevidence:
            return VERIFIED
        if self.independent_sources >= 1:
            return BOUNDED
        return OPEN

    def as_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d.update(contract=CONTRACT, status=self.status,
                 note=("status is a statement about what was tested, not "
                       "about how many sources agreed"))
        return d


def prove(thesis: EconomicThesis, *, falsifier_tested: bool = False,
          independent_sources: int = 0, as_of: str = "") -> ProofPackage:
    """Build the proof a thesis currently supports. Never more than that."""
    return ProofPackage(
        claim=thesis.claim,
        evidence_ids=thesis.supporting_evidence,
        independent_sources=independent_sources,
        causal_basis=thesis.leading_mechanism.description,
        alternative_explanations=tuple(m.description
                                       for m in thesis.alternatives),
        counterevidence=thesis.contradicting_evidence,
        falsifier=thesis.leading_mechanism.falsifier,
        falsifier_tested=falsifier_tested,
        limitations=thesis.unknowns,
        as_of=as_of or thesis.as_of)


# --- consequences beyond the first hop ---------------------------------------------

FIRST_ORDER = 1
SECOND_ORDER = 2
THIRD_ORDER = 3

#: V4 stops at three. Depth is cheap to generate and expensive to justify: a
#: fourth-order consequence is four unverified conditionals in a row, and the
#: standing of the chain is the standing of its weakest link anyway.
MAX_ORDER = THIRD_ORDER


@dataclass(frozen=True)
class ConsequenceHypothesis:
    """One mediated reaction to something that already happened."""

    trigger: str
    order: int
    actor: str
    mechanism: str
    direction: str
    horizon_days: int
    falsifier: str
    #: What has to be true for this to follow. A second-order consequence
    #: whose first-order step failed is not weakly supported; it is void.
    depends_on: str = ""
    alternative: str = ""
    standing: str = PROPOSED
    evidence_ids: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not 1 <= self.order <= MAX_ORDER:
            raise ThesisRejected(
                f"order {self.order} is outside 1..{MAX_ORDER}: depth past "
                "the third hop is generated, not reasoned")
        if self.order > FIRST_ORDER and not self.depends_on:
            raise ThesisRejected(
                "a consequence past the first hop must name the step it "
                "depends on, or it is a first-order claim wearing a number")
        if not self.falsifier.strip():
            raise ThesisRejected("a consequence needs a falsifier")
        if not self.alternative.strip():
            raise ThesisRejected(
                "a consequence needs the other thing that could produce the "
                "same observation")

    def as_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d.update(contract=CONTRACT)
        return d


def propagate(chain: Sequence[ConsequenceHypothesis]) -> dict:
    """Standing of a consequence path: the weakest link, never the average.

    Averaging is how a chain with one broken hop reports as mostly fine. The
    path is worth what its worst step is worth, and the worst step is named.
    """
    if not chain:
        return {"contract": CONTRACT, "hops": 0, "standing": PROPOSED,
                "weakest": "", "note": "no path"}
    ordered = sorted(chain, key=lambda c: c.order)
    weakest = min(ordered, key=lambda c: _ORDER.get(c.standing, 0))
    broken = [c for c in ordered if c.standing == REFUTED]
    return {
        "contract": CONTRACT,
        "hops": len(ordered),
        "max_order": max(c.order for c in ordered),
        "standing": REFUTED if broken else weakest.standing,
        "weakest": f"order {weakest.order}: {weakest.mechanism}",
        "void_below": (f"order {broken[0].order}" if broken else ""),
        "falsifiers": [c.falsifier for c in ordered],
        "note": ("the path is worth its weakest hop; a refuted step voids "
                 "everything downstream rather than weakening it"),
    }


# --- scenarios --------------------------------------------------------------------

BASE = "BASE"
UPSIDE = "UPSIDE"
DOWNSIDE = "DOWNSIDE"
ALTERNATIVE_MECHANISM = "ALTERNATIVE_MECHANISM"
SCENARIOS = (BASE, UPSIDE, DOWNSIDE, ALTERNATIVE_MECHANISM)


@dataclass(frozen=True)
class Scenario:
    """A world, its assumptions, and what it would mean — never a number.

    NO FABRICATED PRECISION. "Revenue falls 12%" from an uncalibrated model is
    a decimal place invented to look rigorous. Scenarios carry direction,
    magnitude words and a decision implication; a number appears only when a
    calibrated parameter produced it, and `calibrated` says which.
    """

    kind: str
    assumptions: Tuple[str, ...]
    direction: str
    magnitude: str = "UNQUANTIFIED"
    decision_implication: str = ""
    calibrated: bool = False
    inconsistencies: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.kind not in SCENARIOS:
            raise ThesisRejected(f"unknown scenario {self.kind!r}")
        if self.magnitude not in ("UNQUANTIFIED", "SMALL", "MODERATE",
                                  "LARGE") and not self.calibrated:
            raise ThesisRejected(
                f"magnitude {self.magnitude!r} looks quantified but no "
                "calibrated parameter produced it")

    def as_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d.update(contract=CONTRACT)
        return d


#: Pairs of conditions that cannot both move that way without a third thing
#: happening. Not a ban — each is possible — but each demands an explanation,
#: and a scenario that asserts one silently is asserting a mechanism it has
#: not stated.
#: Each entry is (left condition, right condition, why, the terms that would
#: show the third thing was stated).
#:
#: THE EXEMPTION TERMS ARE LISTED, NOT DERIVED. The first version took the
#: last three words of the explanation and looked for them in the assumptions;
#: one of those words was "a", substring matching found it in every sentence
#: ever written, and the check silently exempted everything it was built to
#: catch. A guard whose exemption is computed from its own message is a guard
#: that can be talked out of itself.
_NEEDS_EXPLAINING = (
    (("rates", "down"), ("financing cost", "up"),
     "falling policy rates with rising financing cost requires a widening "
     "credit spread or a downgrade",
     ("credit spread", "downgrade", "spread widening")),
    (("inflation", "down"), ("input cost", "up"),
     "disinflation with rising input cost requires a relative price shift, "
     "not a general one",
     ("relative price", "input mix", "commodity specific")),
    (("demand", "down"), ("backlog", "up"),
     "weakening demand with a growing backlog requires a supply constraint "
     "or a change in cancellation behaviour",
     ("supply constraint", "capacity", "cancellation")),
)


def check_consistency(scenario: Scenario) -> Scenario:
    """Flag assumption pairs that need a mechanism nobody stated.

    Deliberately not a veto. Each pair really happens; what must not happen is
    a scenario asserting one WITHOUT the third thing that makes it coherent,
    because a reader takes the pair as jointly established.
    """
    lowered = [a.lower() for a in scenario.assumptions]
    joined = " ".join(lowered)
    flags = []
    for (left, l_dir), (right, r_dir), why, exemptions in _NEEDS_EXPLAINING:
        has_left = any(left in a and l_dir in a for a in lowered)
        has_right = any(right in a and r_dir in a for a in lowered)
        if has_left and has_right and not any(term in joined
                                              for term in exemptions):
            flags.append(why)
    return dataclasses.replace(scenario, inconsistencies=tuple(flags))


# --- the invariant every surface inherits --------------------------------------------

def consistent_with(thesis: EconomicThesis, *, rendered_standing: str,
                    drops_alternatives: bool = False,
                    surface: str = "surface") -> None:
    """Refuse a rendering that says more than the thesis it renders.

    THE FAILURE THIS EXISTS FOR. A bounded thesis becomes a confident slide
    headline, the headline becomes what the room remembers, and the
    qualification lives on in a record nobody opens. Slides, briefings and
    answers all pass through here, so overclaiming is a raised exception in
    one place rather than a habit in three.
    """
    if rendered_standing not in STANDINGS:
        raise ThesisRejected(f"unknown standing {rendered_standing!r}")
    if _ORDER.get(rendered_standing, 0) > _ORDER.get(thesis.standing, 0):
        raise Overclaim(
            f"{surface} presents {rendered_standing} for a thesis that is "
            f"{thesis.standing}: a rendering may say less than its source and "
            "never more")
    if drops_alternatives and thesis.alternatives and thesis.assertable:
        raise Overclaim(
            f"{surface} drops {len(thesis.alternatives)} live alternative "
            "explanation(s); removing them converts a leading explanation "
            "into the only one")


# --- built from what the engine actually measured ------------------------------------

#: Explanations that fit any transmission and are almost never ruled out.
#: Carried as standing alternatives so no thesis is ever asserted with an
#: empty rival list — the point is not that they are likely, it is that
#: nothing in the corpus has excluded them.
_STANDING_ALTERNATIVES = (
    ("the exposure was hedged, refinanced or contracted away before the "
     "condition moved",
     "the company states a hedge, a fixed-rate structure or a forward "
     "contract covering the period"),
    ("the company absorbed the move out of cash or margin rather than "
     "changing the behaviour the mechanism predicts",
     "the predicted behaviour is unchanged while the cash or margin line "
     "moves instead"),
)


def from_transmission(transmission, *, as_of: str = "",
                      surprise=None) -> EconomicThesis:
    """Turn a measured transmission into a thesis with rivals and a falsifier.

    A transmission already carries a mechanism, a lag, a falsifier and one
    alternative. What it does not carry is the standing alternatives that fit
    every transmission — a hedge, or absorption — and asserting a thesis
    without them is asserting that the engine checked and they were false.
    Nothing in a press-release corpus checks either, so they are attached
    here and the thesis is left PROPOSED until something tests one.
    """
    subject = getattr(transmission, "company_id", "")
    kind = getattr(transmission, "state_kind", "")
    area = str(getattr(transmission, "area", "") or "")
    dimension = getattr(transmission, "dimension", "")
    lag = int(getattr(transmission, "lag_days", 0) or 0)
    leading = Mechanism(
        description=str(getattr(transmission, "mechanism", "")),
        direction=str(getattr(transmission, "direction", "")),
        lag_days=lag,
        falsifier=str(getattr(transmission, "falsifier", "")) or
        f"{dimension} does not move as predicted within {lag} days",
        evidence_ids=tuple(getattr(transmission, "exposure_evidence_ids", ())),
        # The catalogue slot, not the sentence. `transmission._MECHANISM` is
        # keyed by exposure dimension and its descriptions are prose that will
        # be edited; identity must survive that edit.
        key=f"transmission:{dimension}")
    stated = str(getattr(transmission, "alternative_explanation", "") or "")
    alternatives = []
    if stated.strip():
        alternatives.append(Mechanism(
            description=stated, direction="", lag_days=lag,
            falsifier=f"evidence establishes that {stated} did not hold"))
    for text, falsifier in _STANDING_ALTERNATIVES:
        alternatives.append(Mechanism(description=text, lag_days=lag,
                                      falsifier=falsifier))
    verb = {"RAISES": "raise", "LOWERS": "lower"}.get(
        str(getattr(transmission, "direction", "")), "move")
    claim = (f"the move in {kind} is expected to {verb} {dimension} for "
             f"{subject} within {lag} days")
    unknowns = ["no outcome has been observed for this transmission yet"]
    if surprise is not None:
        unknowns.append(
            "the condition's move was "
            f"{getattr(surprise, 'direction', 'unmeasured')} relative to "
            "expectation, which the mechanism does not distinguish")
    # THE AREA IS IN THE QUESTION, not only in the identity. Two briefings
    # headed "what does MARKET_RATE mean for america_movil?" — one about
    # Canada, one about the US — are indistinguishable on the page, and a
    # reader resolves the ambiguity by assuming there is only one.
    where = f" in {area}" if area else ""
    return EconomicThesis(
        subject=subject,
        question=f"what does {kind}{where} mean for {subject}?",
        claim=claim,
        leading_mechanism=leading,
        alternatives=tuple(alternatives),
        area=area,
        macro_conditions=(kind,),
        exposures=(dimension,),
        supporting_evidence=tuple(
            getattr(transmission, "exposure_evidence_ids", ())),
        unknowns=tuple(unknowns),
        horizon_days=lag,
        # PROPOSED, not SUPPORTED. Both ends of the transmission are real and
        # neither the mechanism nor a single alternative has been tested, and
        # a standing that reads as evidence would be the whole point of the
        # layer thrown away at the last step.
        standing=PROPOSED,
        as_of=as_of or str(getattr(transmission, "as_of", "")) or "",
        note="built from a measured macro state and a documented exposure")


def build_all(transmissions: Sequence, *, as_of: str) -> List[EconomicThesis]:
    return [from_transmission(t, as_of=as_of) for t in transmissions]


def competitions(theses: Sequence[EconomicThesis]) -> List[Competition]:
    """Group theses by the question they answer, so rivals meet.

    Grouped on `question_key`, which carries the area. Grouping on the
    question TEXT alone put a thesis about Canadian rates and a thesis about
    US rates for one company into the same contest, and a live cycle reported
    four contested questions on that basis. They were not disagreeing; they
    were about different economies, and each was the only answer to its own
    question.
    """
    grouped: Dict[Tuple[str, str, str], List[EconomicThesis]] = {}
    for thesis in theses:
        grouped.setdefault(thesis.question_key, []).append(thesis)
    return [Competition(question=question, subject=subject,
                        theses=tuple(group))
            for (subject, _area, question), group in sorted(grouped.items())]


def summarise(theses: Sequence[EconomicThesis]) -> dict:
    by_standing: Dict[str, int] = {}
    for t in theses:
        by_standing[t.standing] = by_standing.get(t.standing, 0) + 1
    return {
        "contract": CONTRACT,
        "theses": len(theses),
        "by_standing": by_standing,
        "assertable": sum(1 for t in theses if t.assertable),
        "with_alternatives": sum(1 for t in theses if t.alternatives),
        "falsifiers": sum(len(t.falsifiers) for t in theses),
        "note": ("no thesis is ever CONFIRMED; the strongest standing says a "
                 "falsifier was tested and survived"),
    }
