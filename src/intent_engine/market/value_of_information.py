"""What should the engine go and look at next, and why that rather than more?

WHY THIS EXISTS
---------------
Research is currently pulled by AVAILABILITY: the sweep reads the same
twenty-eight companies every cycle and takes whatever the wire produced. That
is a coverage strategy, not a learning strategy, and it means the engine spends
identical effort on a belief nothing can change and on a belief two of three
tests have argued against.

WHAT MAKES SOMETHING WORTH LOOKING FOR
--------------------------------------
Not how interesting it is. An observation is worth acquiring when it would
DISCRIMINATE between explanations the engine currently cannot separate. A fact
that every live hypothesis already predicts costs the same to fetch and
changes nothing when it arrives.

So priority is built from the state that already exists — contested
mechanisms, contradicted beliefs, hidden-state distributions that stayed flat,
expectations whose windows are open — and every entry has to name the
observation that would settle it and where that observation would appear.

THE CONFIRMATION WALL
---------------------
A research question may never name the conclusion it wants. This is not a
style rule. The engine's own belief-formation routes evidence by direction, so
a query written as "find evidence demand is strengthening" would return
exactly the evidence that opens `demand_strengthening` and nothing that opens
its opposite — the search would manufacture its own confirmation and every
downstream test would inherit it.

`neutral_question` enforces this, and `research_priority` refuses anything it
rejects. That refusal is the most load-bearing line in this module.
"""
from __future__ import annotations

import collections
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

CONTRACT = "value_of_information.v1"

HIGH = "VOI_HIGH"
MEDIUM = "VOI_MEDIUM"
LOW = "VOI_LOW"
PRIORITIES = (HIGH, MEDIUM, LOW)

# --- what makes an item valuable -------------------------------------------
CONTRADICTED_BELIEF = "CONTRADICTED_BELIEF"
CONTESTED_MECHANISM = "CONTESTED_MECHANISM"
AMBIGUOUS_HIDDEN_STATE = "AMBIGUOUS_HIDDEN_STATE"
UNRESOLVED_EXPECTATION = "UNRESOLVED_EXPECTATION"
MISSING_RELATIONSHIP = "MISSING_RELATIONSHIP"
STALE_BELIEF = "STALE_BELIEF"

SOURCES_OF_VALUE = frozenset({
    CONTRADICTED_BELIEF, CONTESTED_MECHANISM, AMBIGUOUS_HIDDEN_STATE,
    UNRESOLVED_EXPECTATION, MISSING_RELATIONSHIP, STALE_BELIEF})

#: Language that names the answer it wants. Refused outright.
_CONFIRMATION_SEEKING = re.compile(
    r"\b(?:find|show|prove|confirm|demonstrate|establish|verify)\b[^.?]*?"
    r"\b(?:that|proof|evidence)\b[^.?]*?"
    r"\b(?:is|are|remains?|continues?|will)\b", re.I)
_LOADED = re.compile(
    r"\b(?:proof|prove|confirm(?:ing|ation)?|validate|justif\w+|"
    r"support(?:ing)? (?:the|our) (?:view|thesis|case)|"
    r"remains? strong|still strong|continues? to grow)\b", re.I)


class ConfirmationSeeking(ValueError):
    """The question named the conclusion it wanted."""


def neutral_question(text: str) -> str:
    """Return the question, or refuse it.

    A neutral question names the OBSERVATION and the alternatives it would
    separate. It never names the outcome it hopes for.
    """
    question = " ".join((text or "").split())
    if not question:
        raise ConfirmationSeeking("an empty question discriminates nothing")
    if _CONFIRMATION_SEEKING.search(question) or _LOADED.search(question):
        raise ConfirmationSeeking(
            f"the question names the conclusion it wants: {question!r}. "
            f"Ask for the observation and the alternatives it would "
            f"separate, not for evidence of an answer")
    return question


@dataclass(frozen=True)
class WatchItem:
    """One thing the engine does not know and could find out."""
    item_id: str
    subject: str
    source_of_value: str
    uncertain: str
    why_it_matters: str
    competing_explanations: Tuple[str, ...]
    discriminating_observation: str
    where_it_would_appear: Tuple[str, ...]
    when_available: str
    priority: str
    reason: str

    def as_dict(self) -> dict:
        return {
            "contract": CONTRACT, "item_id": self.item_id,
            "subject": self.subject, "source_of_value": self.source_of_value,
            "what_is_uncertain": self.uncertain,
            "why_it_matters": self.why_it_matters,
            "competing_explanations": list(self.competing_explanations),
            "discriminating_observation": self.discriminating_observation,
            "where_it_would_appear": list(self.where_it_would_appear),
            "when_available": self.when_available,
            "priority": self.priority, "reason": self.reason,
        }


@dataclass(frozen=True)
class ResearchPriority:
    """A watch item turned into something the next sweep can act on."""
    priority_id: str
    subject: str
    question: str
    why_it_matters: str
    hypotheses_discriminated: Tuple[str, ...]
    eligible_sources: Tuple[str, ...]
    priority: str
    resolution_window: str
    status: str = "OPEN"

    def as_dict(self) -> dict:
        return {
            "contract": CONTRACT, "priority_id": self.priority_id,
            "subject": self.subject, "question": self.question,
            "why_it_matters": self.why_it_matters,
            "hypotheses_discriminated": list(self.hypotheses_discriminated),
            "eligible_sources": list(self.eligible_sources),
            "priority": self.priority,
            "resolution_window": self.resolution_window,
            "status": self.status,
        }


def research_priority(item: WatchItem, *, question: str,
                      eligible_sources: Sequence[str],
                      resolution_window: str = "") -> ResearchPriority:
    """Turn a watch item into a neutral, actionable research question."""
    return ResearchPriority(
        priority_id=f"rp_{item.item_id}",
        subject=item.subject,
        question=neutral_question(question),
        why_it_matters=item.why_it_matters,
        hypotheses_discriminated=item.competing_explanations,
        eligible_sources=tuple(eligible_sources),
        priority=item.priority,
        resolution_window=resolution_window or item.when_available)


# ---------------------------------------------------------------------------
# building the watchlist from real state
# ---------------------------------------------------------------------------
def _priority(source: str, *, independent_subjects: int = 0) -> Tuple[str, str]:
    """Ordinal, and it says why. No score, because nothing here is calibrated.

    A contradicted belief outranks everything: the engine has already been
    shown to be wrong about it once, so the next observation is worth more
    there than anywhere it has merely never looked.
    """
    if source == CONTRADICTED_BELIEF:
        return HIGH, ("the engine held this and later evidence argued "
                      "against it; the next observation decides whether that "
                      "was the company or the mechanism")
    if source == CONTESTED_MECHANISM:
        return HIGH, ("this mechanism has been right and wrong; another test "
                      "moves a rule the engine applies to every company")
    if source == AMBIGUOUS_HIDDEN_STATE:
        return MEDIUM, ("two postures explain the evidence equally well and "
                        "imply different behaviour next")
    if source == MISSING_RELATIONSHIP:
        return MEDIUM, ("without a named counterparty no interaction can be "
                        "learned for this actor at all")
    if source == STALE_BELIEF:
        return LOW, "nothing has argued either way; a test would refresh it"
    return LOW if independent_subjects else MEDIUM, (
        "an open expectation whose window has not resolved")


def from_state(*, maturities: Sequence = (), mechanisms: Sequence = (),
               hidden_states: Sequence = (), subject_names:
               Optional[Dict[str, str]] = None) -> Tuple[WatchItem, ...]:
    """Build the watchlist from what the engine already measured."""
    names = subject_names or {}
    out: List[WatchItem] = []

    for m in maturities:
        state = getattr(m, "state", "")
        subject = getattr(m, "subject", "")
        if state not in ("WEAKENING", "CONTESTED", "STALE"):
            continue
        source = (CONTRADICTED_BELIEF if state in ("WEAKENING", "CONTESTED")
                  else STALE_BELIEF)
        priority, reason = _priority(source)
        out.append(WatchItem(
            item_id=f"voi_{getattr(m, 'belief_id', '')[:12]}",
            subject=names.get(subject, subject), source_of_value=source,
            uncertain=getattr(m, "proposition", ""),
            why_it_matters=(
                "this reading is carried into every founder analysis of this "
                "company until something settles it"),
            competing_explanations=(
                "the mechanism is wrong in general",
                "the mechanism is right but does not apply to this company",
                "the mechanism is right and the test observation was noise"),
            discriminating_observation=getattr(
                m, "what_would_revalidate", "a later observation"),
            where_it_would_appear=("quarterly results", "guidance update",
                                   "investor presentation"),
            when_available="next reported period",
            priority=priority, reason=reason))

    for mech in mechanisms:
        if getattr(mech, "maturity", "") not in ("CONTESTED", "FAILING"):
            continue
        priority, reason = _priority(CONTESTED_MECHANISM)
        out.append(WatchItem(
            item_id=f"voi_mech_{getattr(mech, 'key', '')[:16]}",
            subject="(mechanism)", source_of_value=CONTESTED_MECHANISM,
            uncertain=getattr(mech, "proposition", ""),
            why_it_matters=("this mechanism is applied to every company; a "
                            "wrong rule is wrong everywhere at once"),
            competing_explanations=(
                "the transmission does not operate as stated",
                "it operates only under conditions not yet identified"),
            discriminating_observation=getattr(mech, "expected_event", ""),
            where_it_would_appear=("results across several subjects",),
            when_available="as further tests resolve",
            priority=priority, reason=reason))

    for state in hidden_states:
        dist = sorted(getattr(state, "distribution", ()),
                      key=lambda p: -p[1])[:2]
        if len(dist) < 2 or (dist[0][1] - dist[1][1]) > 0.10:
            continue          # the evidence already separates them
        priority, reason = _priority(AMBIGUOUS_HIDDEN_STATE)
        subject = getattr(state, "subject", "")
        out.append(WatchItem(
            item_id=f"voi_hs_{subject[:16]}",
            subject=names.get(subject, subject),
            source_of_value=AMBIGUOUS_HIDDEN_STATE,
            uncertain=f"whether {subject} is {dist[0][0]} or {dist[1][0]}",
            why_it_matters=("the two postures imply different next moves, so "
                            "any expectation about this company is currently "
                            "unfounded"),
            competing_explanations=(dist[0][0], dist[1][0]),
            discriminating_observation=(
                f"an action that {dist[0][0]} predicts and {dist[1][0]} does "
                f"not — capital commitment, hiring, or a pricing move"),
            where_it_would_appear=("capex disclosure", "hiring announcement",
                                   "pricing action"),
            when_available="next disclosure",
            priority=priority, reason=reason))
    return tuple(out)


def summarise(items: Sequence[WatchItem],
              priorities: Sequence[ResearchPriority] = ()) -> dict:
    counts = collections.Counter(i.priority for i in items)
    return {
        "contract": CONTRACT,
        "items": len(items),
        "by_priority": {p: counts.get(p, 0) for p in PRIORITIES},
        "by_source": dict(collections.Counter(i.source_of_value
                                              for i in items)),
        "research_priorities": len(priorities),
        "highest_value_open_question": (
            next((i.uncertain for i in items if i.priority == HIGH), None)),
        "note": ("priority is ordinal; nothing here is calibrated and a "
                 "numeric score would imply a sample that does not exist"),
    }
