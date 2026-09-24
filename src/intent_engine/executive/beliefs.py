"""What the market believes, and the machinery for attacking it.

THE CHANGE THIS MAKES TO THE PRODUCT
------------------------------------
Until now the product answered "what does the evidence say?" well and stopped
there. That is a good answer to the wrong question. A chief executive is not
choosing between our reading and no reading; they are choosing between our
reading and the one already in their head, which usually arrived from the
market, from their board, or from the last five years of being right.

So the unit of output stops being a finding and becomes a BELIEF UNDER
ATTACK:

    the market appears to believe X
    here is the strongest case that X is right
    here is the evidence that would break it
    here are the explanations that fit the same facts
    here is the possibility the current model excludes
    here is what we would watch
    here is the decision it changes

THE TWO RULES THAT KEEP THIS FROM BECOMING ASTROLOGY
-----------------------------------------------------
**A belief is not a price.** Market price is a number, not a proposition, and
mapping one to the other is where this kind of system starts inventing. A
`MarketBelief` is always labelled with how it was arrived at, and the only
labels available are OBSERVED (somebody wrote it down), INFERRED (it follows
from something filed) and MODELLED (it comes from our own expectation model).
There is no rung that means "everyone knows".

**Contrarianism is not a result.** The disposition of a challenge may be
STRENGTHENED, and a conventional belief that survives a serious attack is the
most valuable output this engine produces, because it is the one a chief
executive can act on without hedging. `BeliefChallenge` therefore refuses to
exist if it claims a belief is weakened without naming the evidence that
weakened it -- the check that stops the engine from manufacturing doubt to
look clever.
"""
from __future__ import annotations

import dataclasses
from typing import Optional, Tuple

CONTRACT = "market_belief.v1"
CHALLENGE_CONTRACT = "belief_challenge.v1"

# --- how a belief was arrived at -------------------------------------------
OBSERVED = "OBSERVED"        #: somebody wrote this down; we quote it
INFERRED = "INFERRED"        #: it follows from something filed
MODELLED = "MODELLED"        #: it comes from our own expectation model

BASES = (OBSERVED, INFERRED, MODELLED)

BASIS_LABEL = {
    OBSERVED: "Stated",
    INFERRED: "Inferred",
    MODELLED: "Modelled",
}

BASIS_MEANING = {
    OBSERVED: "somebody wrote this down and it is quoted here",
    INFERRED: "this follows from the company's own filed results; nobody "
              "said it in these words",
    MODELLED: "this is our expectation model's reading, not a consensus and "
              "not a forecast anyone published",
}

# --- what a belief is about -------------------------------------------------
COMPANY = "COMPANY"
INDUSTRY = "INDUSTRY"
COMPETITIVE = "COMPETITIVE"
ECONOMIC = "ECONOMIC"
CUSTOMER = "CUSTOMER"
TECHNOLOGY = "TECHNOLOGY"
MANAGEMENT = "MANAGEMENT"
MARKET_EXPECTATION = "MARKET_EXPECTATION"

BELIEF_TYPES = (COMPANY, INDUSTRY, COMPETITIVE, ECONOMIC, CUSTOMER,
                TECHNOLOGY, MANAGEMENT, MARKET_EXPECTATION)

TYPE_LABEL = {
    COMPANY: "about this company",
    INDUSTRY: "about the industry",
    COMPETITIVE: "about the competition",
    ECONOMIC: "about the economics",
    CUSTOMER: "about customers",
    TECHNOLOGY: "about the technology",
    MANAGEMENT: "about what management is doing",
    MARKET_EXPECTATION: "about what the market expects",
}

# --- belief status ----------------------------------------------------------
ACTIVE = "ACTIVE"
SUPERSEDED = "SUPERSEDED"
RETIRED = "RETIRED"
STATUSES = (ACTIVE, SUPERSEDED, RETIRED)

# --- consensus strength -----------------------------------------------------
DOMINANT = "DOMINANT"
COMMON = "COMMON"
CONTESTED = "CONTESTED"
CONSENSUS_STRENGTHS = (DOMINANT, COMMON, CONTESTED)

CONFIDENCE_HIGH = "HIGH"
CONFIDENCE_MEDIUM = "MEDIUM"
CONFIDENCE_LOW = "LOW"
CONFIDENCES = (CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW)


class BeliefRefused(ValueError):
    """A belief or a challenge that cannot honestly be stated."""


@dataclasses.dataclass(frozen=True)
class MarketBelief:
    """One proposition the market appears to hold, and how we know.

    `proposition` is a SENTENCE THAT COULD BE FALSE. "Cloudflare is a network
    company" is not a belief, it is a description; "the growth Cloudflare has
    shown is durable at this margin" is a belief, because a year of results
    can contradict it. The constructor cannot check that in general, but it
    can and does refuse the two shapes that are never beliefs: an empty
    proposition, and one with no implied expectation -- a belief that implies
    nothing observable cannot be tested, and an untestable belief is a mood.
    """
    belief_id: str
    subject_id: str
    proposition: str
    belief_type: str
    #: OBSERVED / INFERRED / MODELLED, and what it rests on.
    source_basis: str
    basis_detail: str = ""
    supporting_evidence_ids: Tuple[str, ...] = ()
    contradicting_evidence_ids: Tuple[str, ...] = ()
    #: What a holder of this belief would expect to SEE. Required.
    implied_expectations: Tuple[str, ...] = ()
    confidence: str = CONFIDENCE_MEDIUM
    consensus_strength: str = COMMON
    knowable_as_of: str = ""
    first_observed_at: str = ""
    last_tested_at: str = ""
    #: What would show the belief is wrong. Required.
    falsifiers: Tuple[str, ...] = ()
    status: str = ACTIVE
    supersedes: str = ""
    superseded_by: str = ""

    def __post_init__(self):
        if not (self.proposition or "").strip():
            raise BeliefRefused("a belief must state a proposition")
        if self.belief_type not in BELIEF_TYPES:
            raise BeliefRefused(f"unknown belief type {self.belief_type!r}")
        if self.source_basis not in BASES:
            raise BeliefRefused(f"unknown basis {self.source_basis!r}")
        if not self.implied_expectations:
            raise BeliefRefused(
                f"{self.belief_id}: a belief that implies nothing observable "
                f"cannot be tested")
        if not self.falsifiers:
            raise BeliefRefused(
                f"{self.belief_id}: a belief with no falsifier is not a "
                f"belief, it is a mood")
        if self.source_basis != OBSERVED and not (self.basis_detail or "").strip():
            raise BeliefRefused(
                f"{self.belief_id}: basis {self.source_basis} must name what "
                f"it was derived from")

    @property
    def basis_label(self) -> str:
        return BASIS_LABEL.get(self.source_basis, self.source_basis)

    @property
    def type_label(self) -> str:
        return TYPE_LABEL.get(self.belief_type, self.belief_type)

    @property
    def is_stated(self) -> bool:
        return self.source_basis == OBSERVED

    def as_dict(self) -> dict:
        row = dataclasses.asdict(self)
        row["contract"] = CONTRACT
        row["basis_label"] = self.basis_label
        row["type_label"] = self.type_label
        return row


# --- the disposition of an attack ------------------------------------------
HELD = "HELD"
STRENGTHENED = "STRENGTHENED"
WEAKENED = "WEAKENED"
REVISED = "REVISED"
RETIRED_D = "RETIRED"
INCOMPARABLE = "INCOMPARABLE"
UNRESOLVED = "UNRESOLVED"

DISPOSITIONS = (HELD, STRENGTHENED, WEAKENED, REVISED, RETIRED_D,
                INCOMPARABLE, UNRESOLVED)

DISPOSITION_LABEL = {
    HELD: "held — the attack found nothing that moves it",
    STRENGTHENED: "strengthened — it survived a real attempt to break it",
    WEAKENED: "weakened — evidence was found that cuts against it",
    REVISED: "revised — the evidence supports a different statement",
    RETIRED_D: "retired — the evidence no longer supports holding it",
    INCOMPARABLE: "not comparable — the question changed, not the answer",
    UNRESOLVED: "open — the attack needs a measurement we do not have",
}

#: Dispositions that assert the belief moved. Each one must name the evidence
#: that moved it, or the engine is manufacturing doubt.
MOVED = frozenset({WEAKENED, REVISED, RETIRED_D})


@dataclasses.dataclass(frozen=True)
class ImpossibleHypothesis:
    """A possibility outside the current model, bounded by evidence.

    "IMPOSSIBLE" DESCRIBES THE SEARCH, NOT THE PERMISSION. The engine widens
    the hypothesis space deliberately -- what if acquiring customers destroys
    value, what if the competitor is a spreadsheet -- and then narrows it with
    exactly the same discipline as everything else: evidence for, evidence
    against, an expected observation, a falsifier and a test.

    A hypothesis that cannot name what would settle it is rejected. That is
    the difference between this and a brainstorm.
    """
    hypothesis: str
    mechanism: str
    why_plausible: str
    evidence_for: Tuple[str, ...] = ()
    evidence_against: Tuple[str, ...] = ()
    expected_observations: Tuple[str, ...] = ()
    falsifier: str = ""
    confidence: str = CONFIDENCE_LOW
    decision_relevance: str = ""
    test: str = ""
    information_value: str = "MEDIUM"

    def __post_init__(self):
        for field, label in (("hypothesis", "a hypothesis"),
                             ("mechanism", "a mechanism"),
                             ("falsifier", "a falsifier"),
                             ("test", "a test"),
                             ("decision_relevance", "a decision it bears on")):
            if not (getattr(self, field) or "").strip():
                raise BeliefRefused(
                    f"an unconventional hypothesis without {label} is "
                    f"provocation, not analysis")
        if not self.expected_observations:
            raise BeliefRefused(
                f"{self.hypothesis[:60]}: name what would be observed if this "
                f"were true, or it cannot be investigated")

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class BeliefChallenge:
    """One belief, attacked, and what the attack did to it."""
    belief_id: str
    strongest_support: str
    strongest_contradiction: str
    hidden_assumptions: Tuple[str, ...] = ()
    alternative_explanations: Tuple[str, ...] = ()
    unconventional_hypotheses: Tuple[ImpossibleHypothesis, ...] = ()
    falsifier: str = ""
    expected_observation: str = ""
    missing_information: str = ""
    value_of_information: str = "MEDIUM"
    cheapest_test: str = ""
    confidence_before: str = CONFIDENCE_MEDIUM
    confidence_after: str = CONFIDENCE_MEDIUM
    disposition: str = HELD

    def __post_init__(self):
        if self.disposition not in DISPOSITIONS:
            raise BeliefRefused(f"unknown disposition {self.disposition!r}")
        if not (self.strongest_support or "").strip():
            raise BeliefRefused(
                f"{self.belief_id}: an attack that cannot state the best case "
                f"FOR the belief has not attacked it, it has dismissed it")
        if not (self.falsifier or "").strip():
            raise BeliefRefused(
                f"{self.belief_id}: a challenge must name what would settle "
                f"the belief")
        # THE ANTI-CONTRARIANISM CHECK. Claiming a belief moved is a claim
        # about evidence, and it needs one.
        if self.disposition in MOVED and not \
                (self.strongest_contradiction or "").strip():
            raise BeliefRefused(
                f"{self.belief_id}: disposition {self.disposition} asserts the "
                f"belief moved, so it must name the evidence that moved it")
        if not (self.cheapest_test or "").strip():
            raise BeliefRefused(
                f"{self.belief_id}: uncertainty without a test is a hedge")

    @property
    def disposition_label(self) -> str:
        return DISPOSITION_LABEL.get(self.disposition, self.disposition)

    @property
    def survived(self) -> bool:
        return self.disposition in (HELD, STRENGTHENED)

    def as_dict(self) -> dict:
        row = dataclasses.asdict(self)
        row["contract"] = CHALLENGE_CONTRACT
        row["disposition_label"] = self.disposition_label
        return row


@dataclasses.dataclass(frozen=True)
class Explanation:
    """One candidate cause, in a field of candidates for the same fact."""
    hypothesis: str
    mechanism: str
    supporting: Tuple[str, ...] = ()
    contradicting: Tuple[str, ...] = ()
    expected_if_true: Tuple[str, ...] = ()
    confidence: str = CONFIDENCE_MEDIUM
    decision_implication: str = ""
    #: How bad it is if this one is true and we acted as though it were not.
    cost_if_missed: str = ""
    #: HOW BAD, as a band. Ranking "most dangerous" by the LENGTH of the
    #: cost sentence made the four readings collapse onto one explanation for
    #: three of four test companies -- the longest prose won, which is a
    #: property of the writing and not of the risk.
    severity: str = "MEDIUM"
    #: How cheaply it can be told apart from the others.
    test_cost: str = "MEDIUM"

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class ExplanationField:
    """Competing explanations for one observed fact, and the four readings a
    chief executive actually wants out of them."""
    question: str
    observation: str
    explanations: Tuple[Explanation, ...] = ()

    def _rank(self, key, order) -> Optional[Explanation]:
        if not self.explanations:
            return None
        return sorted(self.explanations,
                      key=lambda e: order.index(getattr(e, key))
                      if getattr(e, key) in order else len(order))[0]

    @property
    def most_likely(self) -> Optional[Explanation]:
        return self._rank("confidence", [CONFIDENCE_HIGH, CONFIDENCE_MEDIUM,
                                         CONFIDENCE_LOW])

    @property
    def most_dangerous(self) -> Optional[Explanation]:
        """Highest cost if true and ignored -- NOT the most likely.

        The two are different questions, and a report that answers only the
        first leaves the reader exposed to exactly the case they should hedge.
        So when the severity ranking would return the same row as
        `most_likely`, the next-most-severe is returned instead: the value of
        this reading is that it points somewhere ELSE.
        """
        ranked = [e for e in self.explanations if e.cost_if_missed]
        if not ranked:
            return None
        order = ["HIGH", "MEDIUM", "LOW"]
        ranked = sorted(ranked, key=lambda e: order.index(e.severity)
                        if e.severity in order else len(order))
        likely = self.most_likely
        if likely is not None and len(ranked) > 1 \
                and ranked[0].hypothesis == likely.hypothesis:
            return ranked[1]
        return ranked[0]

    @property
    def most_under_investigated(self) -> Optional[Explanation]:
        """The one with the least evidence either way. Absence of evidence is
        what makes it under-investigated, not evidence against it."""
        if not self.explanations:
            return None
        return sorted(self.explanations,
                      key=lambda e: len(e.supporting) + len(e.contradicting))[0]

    @property
    def cheapest_to_test(self) -> Optional[Explanation]:
        """The cheapest DISCRIMINATING test.

        Same trap as above: if the cheapest thing to test is the reading we
        already think is true, testing it discriminates nothing. The reader is
        pointed at the cheapest test that could actually change the answer.
        """
        ranked = sorted(self.explanations,
                        key=lambda e: ["LOW", "MEDIUM", "HIGH"].index(
                            e.test_cost) if e.test_cost in
                        ("LOW", "MEDIUM", "HIGH") else 3)
        if not ranked:
            return None
        likely = self.most_likely
        if likely is not None and len(ranked) > 1 \
                and ranked[0].hypothesis == likely.hypothesis:
            return ranked[1]
        return ranked[0]

    def as_dict(self) -> dict:
        return {"question": self.question, "observation": self.observation,
                "explanations": [e.as_dict() for e in self.explanations]}


@dataclasses.dataclass(frozen=True)
class MinimumViableExperiment:
    """§10. Uncertainty, converted into something a team can run on Monday."""
    strategic_question: str
    competing_hypotheses: Tuple[str, ...]
    test: str
    required_data: str
    cost_band: str
    time_band: str
    discriminating_power: str
    expected_information_gain: str
    decision_unlocked: str
    stopping_rule: str
    #: What each outcome would mean. An experiment whose results do not have
    #: pre-stated readings is a data-collection exercise.
    if_result_a: str = ""
    if_result_b: str = ""

    def __post_init__(self):
        if len(self.competing_hypotheses) < 2:
            raise BeliefRefused(
                "an experiment that does not separate at least two "
                "hypotheses is a measurement, not a test")
        if not (self.stopping_rule or "").strip():
            raise BeliefRefused("an experiment without a stopping rule cannot "
                                "end")

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)
