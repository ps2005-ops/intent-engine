"""Did intelligence change the decision, and can we say why this company?

THREE QUESTIONS THIS MODULE ANSWERS
-----------------------------------
    STRATEGIC DELTA        what would the class prior alone have said, and
                           what changed once this company's own record was
                           read?
    WHY THIS COMPANY       can we name one thing in this reading that is
                           this company's and not its category's?
    INFORMATION PRIORITY   when the answer to the second is "no", what is
                           the highest-value thing to learn next?

WHY THEY ARE ONE MODULE
-----------------------
Because they are one measurement taken three ways. A reading that changed
nothing when the company's record was read, and that names nothing the
company itself said, IS the generic reading -- and the only honest thing
left to produce is what would have to be learned to move it. Splitting them
lets a surface report the first and quietly omit the third, which is the
shape of every "confident-sounding pricing question for a company we knew
nothing about" on the frozen 40.

THE GENERICITY TEST IS A NAME-SWAP TEST
---------------------------------------
Section 8's question is literal: would this statement stay substantially
true if the company name were replaced with ten other companies? So the test
is: remove the name, then ask whether anything ESTABLISHED FROM THIS
COMPANY'S OWN RECORD survives in the sentence.

    GROUNDED    at least one term the company itself published is load-
                bearing in the statement
    NAME_ONLY   the only thing distinguishing this statement from the same
                statement about a competitor is the name in it
    GENERIC     not even the name distinguishes it

`NAME_ONLY` is the verdict that matters. It is what 22 of the frozen 40
would have received, and it is invisible to every measurement that looks at
one company at a time -- which is why it went twenty-two times unnoticed.

WHAT THIS MODULE MAY NOT DO
---------------------------
Manufacture a ground. If nothing the company published is in the statement,
the verdict is NAME_ONLY and the reading is downgraded. It may not reach for
a synonym, reorder a clause, or add an adjective to escape the finding --
that is the differentiation theatre the 40 companies proved must not be
done.
"""
from __future__ import annotations

import dataclasses
import re
from typing import Optional, Tuple

CONTRACT = "strategic_delta.v1"

GROUNDED = "GROUNDED"
NAME_ONLY = "NAME_ONLY"
GENERIC = "GENERIC"

#: StrategicDelta outcomes (§13).
NO_CHANGE = "NO_CHANGE"
REINFORCED = "REINFORCED"
REFRAMED = "REFRAMED"
WEAKENED = "WEAKENED"
REVERSED = "REVERSED"
NEW_OPTION = "NEW_OPTION"
ABSTAINED = "ABSTAINED"

#: Words carrying no discriminating content. Kept short deliberately: a long
#: stoplist starts deciding which real words count.
_STOP = frozenset("""
a an the and or but if then than that this these those which who whom whose
is are was were be been being am do does did done doing have has had having
it its they them their we us our you your i me my he she his her
to of in on at by for with from as so such very more most much many any
all some each every other another not no nor only just also both either
what when where how why whether can could should would may might must will
shall about over under into onto out up down off between during before after
company companies business businesses what's
""".split())


def _terms(text: str):
    """Lowercase content words, for overlap tests."""
    words = re.findall(r"[a-z][a-z\-']+", str(text or "").lower())
    return [w for w in words if w not in _STOP and len(w) > 2]


@dataclasses.dataclass(frozen=True)
class Grounding:
    """Whether one statement is this company's, or anybody's."""
    verdict: str = GENERIC
    statement: str = ""
    company: str = ""
    grounds: Tuple[str, ...] = ()      #: the company-published terms present
    sources: Tuple[str, ...] = ()      #: where each ground was established
    reason: str = ""

    @property
    def grounded(self) -> bool:
        return self.verdict == GROUNDED

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


def company_terms(decision_object=None, evidence_terms=()) -> Tuple[tuple,
                                                                    tuple]:
    """Every term this company itself established, and where from.

    Returns (terms, sources) in step, so a ground can always name its own
    provenance. A ground that cannot say where it came from is an assertion.
    """
    terms, sources = [], []

    def _add(value, source):
        for word in _terms(value):
            if word not in terms:
                terms.append(word)
                sources.append(source)

    unit = getattr(decision_object, "billing_unit", None)
    if getattr(unit, "known", False):
        _add(unit.value, "what this company says it charges for")
    buyer = getattr(decision_object, "buyer", None)
    if getattr(buyer, "known", False):
        _add(buyer.value, "who this company says decides to buy it")
    for dep in getattr(decision_object, "dependencies", ()) or ():
        if getattr(dep, "known", False):
            _add(dep.value, "what this company says it depends on")
    for term in evidence_terms or ():
        _add(term, "a decision this company's own record discusses")
    return tuple(terms), tuple(sources)


def ground(statement: str, *, company: str, decision_object=None,
           evidence_terms=()) -> Grounding:
    """Is this statement about THIS company, or about anybody like it?"""
    text = str(statement or "")
    name = " ".join(str(company or "").split())
    if not text.strip():
        return Grounding(verdict=GENERIC, company=name,
                         reason="there is no statement to test")
    # Remove the name; a name is an identity, never a ground.
    stripped = text
    if name:
        for token in sorted({name} | set(name.split()), key=len, reverse=True):
            if len(token) > 2:
                stripped = re.sub(re.escape(token), " ", stripped,
                                  flags=re.IGNORECASE)
    terms, sources = company_terms(decision_object, evidence_terms)
    present = tuple(t for t in terms if re.search(
        r"(?<![a-z])" + re.escape(t) + r"(?![a-z])", stripped.lower()))
    if present:
        where = tuple(sources[terms.index(t)] for t in present)
        return Grounding(
            verdict=GROUNDED, statement=text, company=name,
            grounds=present, sources=where,
            reason=(f"This reading turns on {', '.join(present[:3])}, which "
                    f"is {where[0]} -- so it is about this company and not "
                    f"about its category."))
    name_present = bool(name) and name.lower() in text.lower()
    if name_present:
        return Grounding(
            verdict=NAME_ONLY, statement=text, company=name,
            reason=("Nothing in this reading comes from what this company "
                    "published. Replace the name and it would read the same "
                    "for any business of the same kind."))
    return Grounding(
        verdict=GENERIC, statement=text, company=name,
        reason=("This reading names neither this company nor anything it "
                "published."))


@dataclasses.dataclass(frozen=True)
class StrategicDelta:
    """What the class prior alone would have said, and what changed (§13)."""
    company: str = ""
    change_type: str = NO_CHANGE
    prior_archetype: str = ""
    final_archetype: str = ""
    prior_question: str = ""
    final_question: str = ""
    moved_by: Tuple[str, ...] = ()     #: evidence / econ / posture / causal
    grounding: Optional[Grounding] = None
    why: str = ""
    contract: str = CONTRACT

    @property
    def changed(self) -> bool:
        return self.change_type not in (NO_CHANGE, ABSTAINED)

    def as_dict(self) -> dict:
        return {
            "contract": self.contract, "company": self.company,
            "change_type": self.change_type,
            "prior_archetype": self.prior_archetype,
            "final_archetype": self.final_archetype,
            "prior_question": self.prior_question,
            "final_question": self.final_question,
            "moved_by": list(self.moved_by),
            "grounding": (self.grounding.as_dict()
                          if self.grounding is not None else None),
            "changed": self.changed, "why": self.why,
        }


def _movers(considered) -> Tuple[str, ...]:
    """Which non-prior contributions moved the winning archetype."""
    if not considered:
        return ()
    contrib = (considered[0] or {}).get("contributions") or {}
    return tuple(k for k in ("evidence", "econ", "posture", "causal")
                 if contrib.get(k))


def build_delta(*, company: str, selection=None, prior_question: str = "",
                prior_archetype: str = "", decision_object=None,
                evidence_terms=()) -> StrategicDelta:
    """Compare the reading against the reading the class prior alone gives.

    `prior_question` is the SAME question builder run with the company's own
    record withheld. Comparing against a placeholder measures the
    placeholder, so the comparator is a real second state.
    """
    name = str(company or "")
    if selection is None:
        return StrategicDelta(company=name, change_type=ABSTAINED,
                              why="no decision was reached for this company")
    final_q = str(getattr(selection, "decision_question", "") or "")
    final_a = str(getattr(selection, "archetype", "") or "")
    prior_a = str(prior_archetype or final_a)
    movers = _movers(getattr(selection, "considered", ()))
    grounding = ground(final_q, company=name, decision_object=decision_object,
                       evidence_terms=evidence_terms)

    if not final_q:
        change, why = ABSTAINED, "no decision question was composed"
    elif final_a != prior_a:
        change = REVERSED
        why = (f"The class prior alone would have asked about "
               f"{prior_a.replace('_', ' ').lower()}. This company's own "
               f"record moved the decision to "
               f"{final_a.replace('_', ' ').lower()}.")
    elif prior_question and final_q != prior_question:
        change = REFRAMED
        why = (f"The decision is the one this kind of business normally "
               f"faces, but it is measured in this company's own terms "
               f"rather than the category's.")
    elif movers:
        change = REINFORCED
        why = (f"The class prior chose this decision and this company's own "
               f"record supports it ({', '.join(movers)}); nothing moved it.")
    else:
        change = NO_CHANGE
        why = ("Nothing this company published changed the decision. It is "
               "the decision a business of this kind normally faces, and it "
               "is reported as that.")
    return StrategicDelta(
        company=name, change_type=change, prior_archetype=prior_a,
        final_archetype=final_a, prior_question=str(prior_question or ""),
        final_question=final_q, moved_by=movers, grounding=grounding, why=why)


@dataclasses.dataclass(frozen=True)
class InformationPriority:
    """The highest-value thing to learn next, and what it would change (§14)."""
    question: str = ""
    why_it_matters: str = ""
    which_decision_it_changes: str = ""
    current_uncertainty: str = ""
    expected_information_value: str = ""   #: HIGH / MEDIUM / LOW
    best_source_type: str = ""

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


def information_priorities(*, company: str, selection=None,
                           decision_object=None,
                           delta: Optional[StrategicDelta] = None,
                           limit: int = 3) -> Tuple[InformationPriority, ...]:
    """What to learn next, ranked by what it would change.

    A good abstention tells an executive what to find out. The frozen 40
    handed 29 companies a confident pricing question composed entirely from
    their category; the honest version of that page names the two or three
    facts that would make it their own.
    """
    name = str(company or "the company")
    archetype = str(getattr(selection, "archetype", "") or "").replace(
        "_", " ").lower() or "the decision above"
    rows = []
    unit = getattr(decision_object, "billing_unit", None)
    buyer = getattr(decision_object, "buyer", None)
    deps = getattr(decision_object, "dependencies", ()) or ()

    if not getattr(unit, "known", False):
        rows.append(InformationPriority(
            question=f"What does {name} actually charge for -- what is one "
                     f"unit of its revenue counted in?",
            why_it_matters=("Every question about price is measured in the "
                            "unit sold. Without it the pricing decision is "
                            "stated in the unit a business of this kind is "
                            "assumed to sell, which may not be this one."),
            which_decision_it_changes=archetype,
            current_uncertainty=str(getattr(unit, "reason", "") or
                                    "not established"),
            expected_information_value="HIGH",
            best_source_type="the company's own pricing page or order form"))
    if not getattr(buyer, "known", False):
        rows.append(InformationPriority(
            question=f"Who inside a customer signs {name}'s contract?",
            why_it_matters=("Retention, segment and sales-motion decisions "
                            "all turn on who is buying, and a buyer stated "
                            "as 'enterprises' names nobody."),
            which_decision_it_changes=archetype,
            current_uncertainty=str(getattr(buyer, "reason", "") or
                                    "not established"),
            expected_information_value="MEDIUM",
            best_source_type="customer stories, or the buyer named in the "
                             "company's own positioning"))
    if not deps:
        rows.append(InformationPriority(
            question=f"What does {name}'s delivery rest on that it does not "
                     f"own?",
            why_it_matters=("A dependency is where an outside change reaches "
                            "this business. With none established, no "
                            "economic or competitive mechanism can be "
                            "traced to a consequence here."),
            which_decision_it_changes=archetype,
            current_uncertainty="no first-party dependency statement was read",
            expected_information_value="MEDIUM",
            best_source_type="risk factors, a trust or subprocessor page"))
    if delta is not None and delta.change_type in (NO_CHANGE, ABSTAINED):
        rows.append(InformationPriority(
            question=(f"What is {name} doing right now that a business of "
                      f"its kind would not?"),
            why_it_matters=("Nothing read so far moved this reading off the "
                            "category default, so the first fact that does "
                            "is worth more than any further confirmation of "
                            "the default."),
            which_decision_it_changes=archetype,
            current_uncertainty="the reading is the category's, not this "
                                "company's",
            expected_information_value="HIGH",
            best_source_type="a dated first-party announcement or filing"))
    return tuple(rows[:limit])
