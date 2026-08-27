"""Attacking a belief — the same engine for market beliefs and company theses.

WHY ONE MODULE FOR BOTH
-----------------------
The founder product's most-praised capability is that it argues with the
company's own strategy. The market engine's weakest point is that its beliefs
accumulate support and are never attacked by anything except a resolution
that may be months away. These are the same capability pointed at different
propositions, and having two would guarantee the market side got the worse
one.

WHAT AN ATTACK IS, AND WHAT IT IS NOT
-------------------------------------
An attack is a STRUCTURED ALTERNATIVE, not a rebuttal and not a prediction.
It must carry all six of:

    mechanism            how the world would have to work for this instead
    evidence             what is already observed that is consistent with it
    contradiction        what it says that the incumbent belief denies
    observable_test      what would be seen, and when, if this were right
    probability          how likely, stated once, by whoever proposed it
    decision_implication what a reader would do differently

`propose` refuses anything missing one. That is the entire defence against
the failure mode here, which is not being wrong — it is being FLUENT. Plausible
contrarian sentences are the easiest thing in this system to generate and the
least valuable; an attack that cannot name what would be observed is a mood.

HYPOTHETICAL UNTIL TESTED, AND SAID SO
---------------------------------------
`status` starts at UNTESTED and there is no path from UNTESTED to SUPPORTED
that does not pass through an observation bound to `observable_test`. A
surface rendering an attack must render its status; `sentence()` carries it.

THE TEN CATEGORIES
------------------
They are not decoration either. Each category is a TRANSFORMATION of the
incumbent belief, and `for_belief` applies the ones that can actually be
formed from what the belief says — so a belief about a rate does not produce
a customer-inversion attack with a blank subject.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from .belief import EconomicBelief
from .vocabulary import EconError, require

CONTRACT = "econ_attack.v1"

# --- the five kinds Section 8 requires --------------------------------------
CONVENTIONAL = "CONVENTIONAL"
CONTRARIAN = "CONTRARIAN"
INVERSION = "INVERSION"
STRUCTURAL_BREAK = "STRUCTURAL_BREAK"
SUBSTITUTION = "SUBSTITUTION"
IMPOSSIBLE = "IMPOSSIBLE"
KINDS = (CONVENTIONAL, CONTRARIAN, INVERSION, STRUCTURAL_BREAK,
         SUBSTITUTION, IMPOSSIBLE)

# --- the ten categories Section 9 requires ----------------------------------
CUSTOMER_INVERSION = "CUSTOMER_INVERSION"
VALUE_DESTRUCTION = "VALUE_DESTRUCTION"
BUSINESS_MODEL_INVERSION = "BUSINESS_MODEL_INVERSION"
SUBSTITUTION_CATEGORY = "SUBSTITUTION"
INTERNALISATION = "INTERNALISATION"
PLATFORM_SHIFT = "PLATFORM_SHIFT"
AI_OBSOLESCENCE = "AI_OBSOLESCENCE"
NEW_MARKET_CREATION = "NEW_MARKET_CREATION"
CONSTRAINT_INVERSION = "CONSTRAINT_INVERSION"
PROFIT_ENGINE_INVERSION = "PROFIT_ENGINE_INVERSION"
CATEGORIES = (CUSTOMER_INVERSION, VALUE_DESTRUCTION,
              BUSINESS_MODEL_INVERSION, SUBSTITUTION_CATEGORY,
              INTERNALISATION, PLATFORM_SHIFT, AI_OBSOLESCENCE,
              NEW_MARKET_CREATION, CONSTRAINT_INVERSION,
              PROFIT_ENGINE_INVERSION)

#: What each category asks, phrased so the answer is allowed to be either way.
CATEGORY_QUESTIONS = {
    CUSTOMER_INVERSION:
        "what if the buyer stops being the buyer -- the decision moves to a "
        "different function, or the user starts choosing instead",
    VALUE_DESTRUCTION:
        "what if the thing being sold stops being worth paying for, rather "
        "than being sold by someone else",
    BUSINESS_MODEL_INVERSION:
        "what if the money is made at the other end -- the paid part becomes "
        "free and the free part becomes the product",
    SUBSTITUTION_CATEGORY:
        "what if demand is met by something that is not a competitor and not "
        "in the category at all",
    INTERNALISATION:
        "what if the largest customers build it themselves, and the supplier "
        "relationship ends rather than moves",
    PLATFORM_SHIFT:
        "what if the surface this is delivered on stops being the surface "
        "people use",
    AI_OBSOLESCENCE:
        "what if the work being sold is done well enough by a model that the "
        "price no longer supports the business",
    NEW_MARKET_CREATION:
        "what if the growth is somewhere nobody is measuring, and the "
        "measured market is the residual",
    CONSTRAINT_INVERSION:
        "what if the binding constraint moves -- the scarce input stops "
        "being scarce and something else becomes the bottleneck",
    PROFIT_ENGINE_INVERSION:
        "what if the segment that carries the margin becomes the one that "
        "loses money, while the low-margin one carries the firm",
}

# --- status -----------------------------------------------------------------
UNTESTED = "UNTESTED"
OBSERVED_CONSISTENT = "OBSERVED_CONSISTENT"
OBSERVED_INCONSISTENT = "OBSERVED_INCONSISTENT"
RETIRED = "RETIRED"
STATUSES = (UNTESTED, OBSERVED_CONSISTENT, OBSERVED_INCONSISTENT, RETIRED)


class AttackRejected(EconError):
    """An attack that cannot be tested is a mood; it is refused, not stored."""


@dataclass(frozen=True)
class Attack:
    """One structured alternative to a stated belief."""

    attack_id: str
    target: str                  # belief_id or thesis id
    target_proposition: str
    kind: str
    category: str
    claim: str
    mechanism: str
    evidence: str
    contradiction: str
    observable_test: str
    probability: float
    decision_implication: str
    created_at: str
    status: str = UNTESTED
    #: Evidence node ids that have since been bound to `observable_test`.
    observations: Tuple[str, ...] = ()
    resolved_at: str = ""
    note: str = ""

    def __post_init__(self) -> None:
        require(self.kind in KINDS, f"unknown attack kind {self.kind!r}")
        require(self.category in CATEGORIES,
                f"unknown category {self.category!r}")
        require(self.status in STATUSES, f"unknown status {self.status!r}")
        require(0.0 <= self.probability <= 1.0, "a probability")
        for name in ("claim", "mechanism", "evidence", "contradiction",
                     "observable_test", "decision_implication"):
            if not str(getattr(self, name)).strip():
                raise AttackRejected(
                    f"an attack without {name} is refused. Plausible "
                    "contrarian sentences are the easiest thing this system "
                    "can produce and the least valuable; the six fields are "
                    "what separates an alternative from a mood.")

    @property
    def tested(self) -> bool:
        return self.status in (OBSERVED_CONSISTENT, OBSERVED_INCONSISTENT)

    def sentence(self) -> str:
        """Carries the status, always. A surface cannot render it without."""
        label = {UNTESTED: "UNTESTED HYPOTHESIS",
                 OBSERVED_CONSISTENT: "consistent with what has been observed",
                 OBSERVED_INCONSISTENT: "inconsistent with what was observed",
                 RETIRED: "retired"}[self.status]
        return f"{self.claim} [{label}; test: {self.observable_test}]"

    def as_dict(self) -> dict:
        return {"contract": CONTRACT, "attack_id": self.attack_id,
                "target": self.target,
                "target_proposition": self.target_proposition,
                "kind": self.kind, "category": self.category,
                "category_question": CATEGORY_QUESTIONS[self.category],
                "claim": self.claim, "mechanism": self.mechanism,
                "evidence": self.evidence,
                "contradiction": self.contradiction,
                "observable_test": self.observable_test,
                "probability": round(self.probability, 3),
                "decision_implication": self.decision_implication,
                "created_at": self.created_at, "status": self.status,
                "tested": self.tested,
                "observations": list(self.observations),
                "resolved_at": self.resolved_at, "note": self.note,
                "sentence": self.sentence()}


def propose(*, target: str, target_proposition: str, kind: str,
            category: str, claim: str, mechanism: str, evidence: str,
            contradiction: str, observable_test: str, probability: float,
            decision_implication: str, at: str) -> Attack:
    """The only constructor. Every field is required; see `__post_init__`."""
    material = json.dumps([target, category, " ".join(claim.split()).lower()],
                          sort_keys=True)
    aid = "at-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return Attack(
        attack_id=aid, target=target, target_proposition=target_proposition,
        kind=kind, category=category, claim=claim, mechanism=mechanism,
        evidence=evidence, contradiction=contradiction,
        observable_test=observable_test, probability=probability,
        decision_implication=decision_implication, created_at=at)


def observe(a: Attack, *, consistent: bool, at: str,
            observations: Sequence[str], note: str = "") -> Attack:
    """Bind observations to the attack's own test. The ONLY path out of UNTESTED.

    `observations` must be non-empty. An attack marked tested with no bound
    observation is the failure this whole ledger exists to prevent: a
    hypothesis that graduated because somebody read it and nodded.
    """
    require(bool(observations),
            "a tested attack names the observations that tested it")
    return replace(a, status=(OBSERVED_CONSISTENT if consistent
                              else OBSERVED_INCONSISTENT),
                   observations=tuple(observations), resolved_at=at,
                   note=note)


def retire(a: Attack, *, at: str, reason: str) -> Attack:
    require(bool(reason.strip()), "a retirement states why")
    return replace(a, status=RETIRED, resolved_at=at, note=reason)


# --- generating attacks from a belief ---------------------------------------
#: Which categories can be FORMED from a belief about each subject type. A
#: belief about a policy rate cannot produce a customer-inversion attack with
#: a blank subject, and producing one anyway is how a heresy engine fills a
#: page with grammatical noise.
_MACRO_CATEGORIES = (CONSTRAINT_INVERSION, SUBSTITUTION_CATEGORY,
                     NEW_MARKET_CREATION, VALUE_DESTRUCTION)
_COMPANY_CATEGORIES = CATEGORIES


def applicable_categories(belief: EconomicBelief, *,
                          company_scoped: bool = False) -> Tuple[str, ...]:
    return _COMPANY_CATEGORIES if company_scoped else _MACRO_CATEGORIES


def for_belief(belief: EconomicBelief, *, at: str,
               company_scoped: bool = False,
               author: Optional[Callable[[str, str], Optional[dict]]] = None,
               ) -> List[Attack]:
    """The attack SLOTS this belief opens, filled by `author` or left empty.

    THIS FUNCTION WRITES NO CLAIMS. It enumerates the categories that can be
    formed against the belief and asks `author` -- an LLM caller, an analyst,
    a fixture -- for each. An author that returns None leaves the slot empty,
    and an empty slot is reported rather than filled with a template.

    That is deliberate and is the difference between this and a heresy
    generator. A template attack reads exactly like a real one and is
    indistinguishable downstream, so there is no template.
    """
    out: List[Attack] = []
    for category in applicable_categories(belief,
                                          company_scoped=company_scoped):
        if author is None:
            continue
        proposal = author(category, CATEGORY_QUESTIONS[category])
        if not proposal:
            continue
        out.append(accept_proposal(belief, proposal, category=category, at=at))
    return out


def accept_proposal(belief: EconomicBelief, proposal: dict, *,
                    category: str, at: str) -> Attack:
    """Take an externally-authored attack through the same gate as any other.

    An LLM is a perfectly good source of candidate alternatives and a
    terrible source of confidence. Everything it offers is refused unless it
    carries the six fields, and its `probability` is capped: a model that has
    observed nothing may not open at more than `MAX_UNEVIDENCED_PROBABILITY`.
    """
    probability = float(proposal.get("probability", 0.2) or 0.2)
    if not str(proposal.get("evidence", "")).strip():
        raise AttackRejected(
            "an attack with no evidence field is refused even as a "
            "hypothesis; 'what is already observed that is consistent with "
            "this' may be 'nothing yet', and saying so is the point")
    probability = min(probability, MAX_UNEVIDENCED_PROBABILITY)
    return propose(
        target=belief.belief_id, target_proposition=belief.proposition,
        kind=str(proposal.get("kind", CONTRARIAN)), category=category,
        claim=str(proposal.get("claim", "")),
        mechanism=str(proposal.get("mechanism", "")),
        evidence=str(proposal.get("evidence", "")),
        contradiction=str(proposal.get("contradiction", "")),
        observable_test=str(proposal.get("observable_test", "")),
        probability=probability,
        decision_implication=str(proposal.get("decision_implication", "")),
        at=at)


#: An attack nobody has observed anything for may not open above this. It is
#: a cap on ASSERTION, not a judgement: a good attack earns its probability by
#: being observed, through `observe`, and not by being well written.
MAX_UNEVIDENCED_PROBABILITY = 0.35


def most_dangerous(attacks: Sequence[Attack],
                   belief: EconomicBelief) -> Optional[Attack]:
    """Which live attack would cost the most if it were right.

    Probability times how far it would move the belief. An attack that
    contradicts a belief held at 0.9 is worth more attention than one that
    contradicts a belief already held at 0.5, because the latter is barely a
    belief.
    """
    live = [a for a in attacks if a.status in (UNTESTED, OBSERVED_CONSISTENT)]
    if not live:
        return None
    return max(live, key=lambda a: a.probability * belief.probability)


def summarise(attacks: Sequence[Attack]) -> dict:
    by_status: Dict[str, int] = {}
    by_category: Dict[str, int] = {}
    for a in attacks:
        by_status[a.status] = by_status.get(a.status, 0) + 1
        by_category[a.category] = by_category.get(a.category, 0) + 1
    return {"contract": CONTRACT, "attacks": len(attacks),
            "by_status": by_status, "by_category": by_category,
            "tested": sum(1 for a in attacks if a.tested),
            "untested": sum(1 for a in attacks if a.status == UNTESTED)}
