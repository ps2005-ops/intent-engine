"""The founder insight contract — "so what?" enforced in the data, not the CSS.

WHY THIS IS A DATA CONTRACT AND NOT A TEMPLATE
----------------------------------------------
The obvious way to add "so what?" to a product is to add a heading to the
renderer and let a language model fill it. That fails in a specific and
predictable way: the model writes a sentence that restates the fact in
different words ("Revenue increased 18%, which shows revenue is growing"), the
heading is populated, the template is satisfied, and the reader has learned
nothing. The failure is invisible to every test that checks the field exists.

So the implication is a REQUIRED FIELD on the object, and the object refuses to
be constructed without one that is distinguishable from the fact. A renderer
cannot invent an implication because it never receives an insight that lacks
one — `validate` raises first.

THE FIVE FIELDS
---------------
    fact            what happened, in plain language
    interpretation  what it suggests, and why
    so_what         why a founder should care
    decision        the choice, risk or priority it changes
    watch           what would confirm or contradict it

All five must exist for every MAJOR insight. They are not all rendered on every
small card -- a card showing four labels is a form, not a brief -- but the
meanings are always present in the data, which is what lets the brief, the
narrative and the Q&A all speak from one source without drifting apart.

WHAT GETS REJECTED
------------------
* an implication that merely repeats the fact (measured by token overlap, not
  by hoping)
* a decision that names no choice, risk or priority
* an insight with no evidence behind it
* internal vocabulary reaching a founder-facing string

Rejection is the point. A major insight that cannot say why it matters is not a
formatting problem to be styled around; it is a claim that should not be on the
first screen.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

CONTRACT_VERSION = "founder_insight.v1"

# Vocabulary that belongs to the machine, never to the reader. Checked on every
# founder-facing string, because these leak through prose far more often than
# through labels -- a sentence like "the strategic_report hypothesis h3 was
# withheld" passes every structural test and is unreadable.
INTERNAL_VOCABULARY = (
    "run_id", "strategic_report", "hypothesis_id", "claim_id", "source_class",
    "observation_id", "entity_id", "pipeline", "readiness_state", "enum",
    "schema", "traceback", "null", "none-type", "paper_control",
    "baseline_momentum", "n_eff", "blocked_by", "no_strategic_reading",
    "view_withheld", "corroboration", "funnel", "idempotency",
)

# A decision has to name something a founder can actually decide about.
_DECISION_SIGNALS = (
    "invest", "hire", "build", "buy", "cut", "delay", "prioritis",
    "prioritiz", "raise", "lower", "expand", "narrow", "focus", "stop",
    "start", "keep", "switch", "renegotiat", "defend", "price", "pricing",
    "resource", "headcount", "roadmap", "budget", "partner", "acquire",
    "whether", "should", "risk", "priority", "commit", "spend", "allocate",
    "position", "target", "scope", "launch", "retain", "churn",
)

# A decision needs an alternative. Without one it is an instruction.
_TRADEOFF_MARKERS = ("whether", " vs", "versus", " or ", "rather than",
                     "instead of", "without", "before", "trade-off",
                     "tradeoff", "at the expense of", "while still")

# Advice that applies to every company and therefore informs about none.
_GENERIC = ("monitor this", "monitor closely", "keep an eye", "watch this",
            "stay informed", "continue to monitor", "review regularly",
            "track progress", "be aware", "consider carefully")

_STOPWORDS = frozenset("""
a an and are as at be been but by for from had has have in into is it its of
on or over that the their there this to was were what which who will with
""".split())


class InsightRejected(ValueError):
    """An insight that may not be shown to a founder, and why."""


def _tokens(text: str) -> set:
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower())
            if w not in _STOPWORDS and len(w) > 2}


def _overlap(a: str, b: str) -> float:
    """How much of `b` is just `a` again.

    Jaccard over content words. Crude on purpose: the failure it catches is not
    subtle paraphrase but wholesale restatement, and a cheap check that runs on
    every insight beats a clever one that runs on none.
    """
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


# Above this, the implication is a restatement rather than an implication.
MAX_RESTATEMENT_OVERLAP = 0.6


@dataclass(frozen=True)
class FounderInsight:
    """One thing worth a founder's attention, with its consequence attached.

    Complete and renderer-independent: every field a layer could need is here,
    so the dashboard, decision story, executive brief and Q&A all speak from
    one object. A renderer that had to fill a gap would fill it differently
    each time, and the layers would quietly start contradicting each other.
    """
    fact: str
    interpretation: str
    so_what: str
    decision: str
    watch: str
    evidence_ids: tuple = ()
    confidence: str = ""
    major: bool = True
    source_label: str = ""
    # completed contract
    next_action: str = ""
    confidence_reason: str = ""
    limitations: tuple = ()
    company_mode: str = ""
    audience_relevance: str = ""

    # aliases the spec names differently from the internal field
    @property
    def decision_affected(self) -> str:
        return self.decision

    @property
    def next_check(self) -> str:
        return self.watch

    def as_dict(self) -> dict:
        return {"fact": self.fact, "interpretation": self.interpretation,
                "so_what": self.so_what, "decision": self.decision,
                "decision_affected": self.decision,
                "next_action": self.next_action,
                "watch": self.watch, "next_check": self.watch,
                "evidence_ids": list(self.evidence_ids),
                "confidence": self.confidence,
                "confidence_reason": self.confidence_reason,
                "limitations": list(self.limitations),
                "company_mode": self.company_mode,
                "audience_relevance": self.audience_relevance,
                "major": self.major, "source_label": self.source_label,
                "contract": CONTRACT_VERSION}


def validate(insight: FounderInsight, *, require_evidence: bool = True
             ) -> FounderInsight:
    """Raise unless this insight may be shown to a founder.

    Called at CONSTRUCTION time by `build`, not at render time, so a rejected
    insight never reaches a template and no renderer has to decide what to do
    with a half-formed one.
    """
    problems: List[str] = []

    for name in ("fact", "so_what", "decision"):
        value = (getattr(insight, name) or "").strip()
        if not value:
            problems.append(f"{name} is empty")
        elif len(value) < 12:
            problems.append(f"{name} is too short to mean anything")

    if insight.major:
        if not (insight.watch or "").strip():
            problems.append("a major insight must say what would change it")
        if require_evidence and not insight.evidence_ids:
            problems.append("a major insight must cite evidence")

    # THE CHECK THAT MATTERS. An implication that restates the fact satisfies
    # every "is the field populated" test and teaches nothing.
    if insight.fact and insight.so_what:
        overlap = _overlap(insight.fact, insight.so_what)
        if overlap > MAX_RESTATEMENT_OVERLAP:
            problems.append(
                f"'so what' restates the fact (overlap {overlap:.0%}); an "
                f"implication has to add a consequence, not rephrase")

    if insight.decision and not any(
            s in insight.decision.lower() for s in _DECISION_SIGNALS):
        problems.append("the decision names no choice, risk or priority a "
                        "founder could act on")

    # A DECISION IS A TRADE-OFF. "Improve onboarding" is a task; "whether to
    # fund enterprise delivery OR protect self-serve" is a decision. Without
    # the alternative there is nothing to decide, and the reader is being told
    # what to do rather than what to weigh.
    if insight.major and insight.decision and not any(
            m in insight.decision.lower() for m in _TRADEOFF_MARKERS):
        problems.append("the decision states no trade-off (no 'whether', "
                        "'vs', 'or', 'without', 'before'); a recommendation "
                        "is not a decision")

    # Generic advice that survives every edit because it applies to anything.
    for text, label in ((insight.next_action, "next_action"),
                        (insight.watch, "watch")):
        low = (text or "").lower().strip()
        if low and any(low.startswith(g) or low == g.rstrip() for g in _GENERIC):
            problems.append(f"{label} is generic advice ({low[:40]!r}); it "
                            f"names no concrete investigation")

    if insight.confidence and insight.major:
        strong = insight.confidence.lower() in ("high", "strong", "certain")
        if strong and len(insight.evidence_ids) < 3:
            problems.append(
                f"confidence '{insight.confidence}' is stronger than its "
                f"evidence ({len(insight.evidence_ids)} item(s))")

    for name in ("fact", "interpretation", "so_what", "decision", "watch"):
        leaked = _internal_terms(getattr(insight, name) or "")
        if leaked:
            problems.append(f"{name} contains internal vocabulary: {leaked}")

    if problems:
        raise InsightRejected("; ".join(problems))
    return insight


def _internal_terms(text: str) -> List[str]:
    low = (text or "").lower()
    return [t for t in INTERNAL_VOCABULARY if t in low]


def founder_readable(text: str) -> Tuple[bool, List[str]]:
    """Is this string fit to show a non-technical first-time reader?"""
    leaked = _internal_terms(text)
    return (not leaked), leaked


def safe_insights(candidates: Sequence[FounderInsight], *,
                  require_evidence: bool = True) -> Tuple[list, list]:
    """Split candidates into what may be shown and what was rejected, with
    reasons kept so the omission is auditable rather than silent."""
    keep, dropped = [], []
    for candidate in candidates:
        try:
            keep.append(validate(candidate, require_evidence=require_evidence))
        except InsightRejected as exc:
            dropped.append({"fact": candidate.fact, "reason": str(exc)})
    return keep, dropped
