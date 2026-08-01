"""Q&A answered from the SHARED founder intelligence object.

THE SPLIT THIS CLOSES
---------------------
Q&A independently re-interpreted the deterministic report. Two interpreters over
one report is two products: the brief could say the evidence is thin while the
assistant answered with confidence, and both were "correct" according to their
own path. A founder who reads one and asks the other gets contradictions and no
way to tell which to trust.

So this does NOT reason. It takes the answer text the existing conversation
engine produced and frames it with the shared object's implication, decision,
confidence and limitations. One interpretation, five surfaces.

    DIRECT ANSWER            from the existing conversation engine
    SO WHAT                  from the shared insight
    DECISION AFFECTED        from the shared insight
    EVIDENCE                 the shared insight's evidence ids
    WHAT COULD CHANGE IT     the shared insight's next check + limitations

THE REFUSAL THAT MATTERS
------------------------
When the primary experience WITHHELD a strategic reading -- sparse companies,
marketing-only sites -- the assistant must not supply one. That is the single
easiest way for this product to become dishonest: the report says "not enough
evidence", the user asks "but what do you think?", and a chatty model obliges.
`withheld` short-circuits every strategic intent to a refusal that still helps.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from intent_engine.founder_brief.contract import INTERNAL_VOCABULARY

# Questions that ask for a strategic conclusion rather than a fact.
_STRATEGIC_INTENT = ("what do you think", "what is the main point",
                     "main point", "so what", "what should", "why does it "
                     "matter", "what is the strategy", "what is going on",
                     "your view", "conclusion", "is it working")

# Questions asking which evidence carries the claim.
_EVIDENCE_INTENT = ("what evidence", "what is this based on", "strongest",
                    "weakest", "without that source", "how do you know",
                    "verified fact or", "fact or interpretation")


@dataclass
class FounderAnswer:
    """One answer, in the same shape as every other founder-facing surface."""
    question: str
    direct_answer: str
    so_what: str = ""
    decision_affected: str = ""
    evidence_ids: tuple = ()
    what_could_change: str = ""
    confidence: str = ""
    limitations: tuple = ()
    withheld: bool = False
    strongest_evidence: str = ""
    weakest_evidence: str = ""
    fact_or_interpretation: str = ""

    def as_dict(self) -> dict:
        return {"question": self.question, "direct_answer": self.direct_answer,
                "so_what": self.so_what,
                "decision_affected": self.decision_affected,
                "evidence_ids": list(self.evidence_ids),
                "what_could_change": self.what_could_change,
                "confidence": self.confidence,
                "limitations": list(self.limitations),
                "withheld": self.withheld,
                "strongest_evidence": self.strongest_evidence,
                "weakest_evidence": self.weakest_evidence,
                "fact_or_interpretation": self.fact_or_interpretation}


def _intent(question: str, markers) -> bool:
    low = (question or "").lower()
    return any(m in low for m in markers)


def answer(question: str, brief, *, engine_answer: str = "",
           observations: Optional[Sequence[dict]] = None) -> FounderAnswer:
    """Frame an answer using the shared object. Never invents a conclusion."""
    observations = list(observations or ())
    k = brief.key_insight
    withheld = k is None

    out = FounderAnswer(question=question, direct_answer="",
                        confidence=brief.confidence,
                        limitations=tuple(brief.limitations),
                        withheld=withheld)

    # --- the refusal path ---------------------------------------------------
    if withheld and _intent(question, _STRATEGIC_INTENT):
        out.direct_answer = (
            "I am not going to give you a strategic read on this company, "
            "because the public evidence does not support one — the same "
            "reason the summary above withheld it.")
        out.so_what = (
            "What can be established is what a customer, partner or investor "
            "can verify from outside. That is a different and smaller "
            "question, and it is answerable.")
        out.decision_affected = (
            "Whether to publish more verifiable proof, or accept that every "
            "buyer conversation starts from zero.")
        out.what_could_change = (
            "Independent coverage, dated customer evidence, or public pricing "
            "would all move this.")
        return out

    out.direct_answer = _plain(engine_answer) or (
        k.fact if k else "There is not enough public evidence to answer that "
                         "confidently.")

    if k:
        out.so_what = k.so_what
        out.decision_affected = k.decision
        out.evidence_ids = tuple(k.evidence_ids)
        out.what_could_change = k.watch
        out.confidence = k.confidence or brief.confidence

    # --- evidence questions -------------------------------------------------
    if _intent(question, _EVIDENCE_INTENT):
        independent = [o for o in observations
                       if o.get("source_class") not in
                       ("company_owned", "executive_statement", None, "")]
        company = [o for o in observations
                   if o.get("source_class") in ("company_owned",
                                                "executive_statement")]
        out.strongest_evidence = _describe(
            independent[0] if independent else None,
            "No independent source was found; everything rests on the "
            "company's own material.")
        out.weakest_evidence = _describe(
            company[0] if company else None,
            "No company-stated material is being relied on.")
        # Source-ablation: would the reading survive without the best source?
        if "without" in (question or "").lower():
            # Precomputed: Python 3.9 cannot carry a multi-line expression
            # inside an f-string, and a conditional this long is unreadable
            # inline regardless.
            survives = len(independent) >= 2
            verdict = "Probably — " if survives else "No — "
            consequence = (
                "Removing the strongest one still leaves independent "
                "corroboration." if survives else
                "Removing the strongest one leaves it resting on the company "
                "describing itself.")
            out.direct_answer = (
                f"{verdict}{len(independent)} independent source(s) support "
                f"this. {consequence}")
        out.fact_or_interpretation = (
            "Interpretation. The dated events are verified facts; the reading "
            "of what they add up to is an inference, and it is labelled as "
            "one." if k else "Verified fact only — no interpretation is "
                             "offered because the evidence does not support "
                             "one.")
    return out


def _describe(observation, fallback: str) -> str:
    if not observation:
        return fallback
    text = " ".join(str(observation.get("text")
                        or observation.get("summary") or "").split())
    when = str(observation.get("date") or "")[:10]
    return f"{when + ': ' if when else ''}{text[:180]}"


def _plain(text: str) -> str:
    """Strip internal vocabulary from an engine answer before a founder sees
    it. The conversation engine predates the founder-language rules."""
    out = " ".join((text or "").split())
    for term in INTERNAL_VOCABULARY:
        out = re.sub(re.escape(term), "", out, flags=re.I)
    return " ".join(out.split())


def leaked_terms(answer_obj) -> List[str]:
    fields = " ".join([answer_obj.direct_answer, answer_obj.so_what,
                       answer_obj.decision_affected,
                       answer_obj.what_could_change]).lower()
    return [t for t in INTERNAL_VOCABULARY if t in fields]
