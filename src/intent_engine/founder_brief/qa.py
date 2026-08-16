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

from intent_engine.external_intel import evidence_trust as _ET
from intent_engine.founder_brief.consistency import _looks_strategic
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
           observations: Optional[Sequence[dict]] = None,
           trust=None, contract=None) -> FounderAnswer:
    """Frame an answer using the shared object. Never invents a conclusion.

    `trust` is the CANONICAL standing produced by the market side, not a
    judgement made here. Absent it, this surface may still describe which
    accounts exist — it may not say they confirm each other.
    """
    observations = list(observations or ())
    trust = trust if trust is not None else _ET.UNRATED
    k = brief.key_insight
    # D25. WHETHER A READING EXISTS IS NOT DECIDED HERE.
    #
    # `brief.key_insight is None` measures what THIS RUN could establish, and
    # Q&A used it to refuse outright: live on 8f2ea0c it answered "I am not
    # going to give you a strategic read on this company, because the public
    # evidence does not support one -- the same reason the summary above
    # withheld it" while the X-Ray gave a supported pricing decision and the
    # summary above had stopped withholding. That trailing clause is the
    # tell: it cited a refusal no longer being made.
    #
    # Q&A was the FIFTH surface found deciding this for itself. It keeps
    # everything else it does -- the explanation, the citations, the
    # counter-evidence -- and gives up only the verdict.
    withheld = k is None
    if (contract is not None and getattr(contract, "reading_exists", False)
            and withheld):
        withheld = False
        out_contribution = getattr(contract, "run_contribution", "")
    else:
        out_contribution = ""

    out = FounderAnswer(question=question, direct_answer="",
                        confidence=brief.confidence,
                        limitations=tuple(brief.limitations),
                        withheld=withheld)

    # --- the refusal path ---------------------------------------------------
    if out_contribution and _intent(question, _STRATEGIC_INTENT):
        # The contract holds a reading this run did not strengthen. Say both
        # facts; refusing would contradict the X-Ray, and claiming this run
        # established it would be the opposite lie.
        out.direct_answer = (
            f"A supported reading of "
            f"{getattr(contract, 'company', '') or 'this company'} exists and "
            f"is set out on the Executive X-Ray.")
        out.so_what = out_contribution
        return out
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

    # THE ENGINE STILL HOLDS THE READING THE BRIEF REFUSED.
    #
    # `answer_strategic` answers from the strategic report, which keeps its
    # hypothesis whether or not the brief judged the evidence strong enough to
    # assert it. So an ordinary, non-strategic question -- "what does this
    # company do?" -- was enough to carry that hypothesis onto the page under
    # a brief that had just said no conclusion was being asserted. The refusal
    # above only inspects the QUESTION; the reading arrives in the ANSWER.
    if withheld and _looks_strategic(engine_answer):
        engine_answer = ""

    # D28. THE FALLBACK WAS ONE SENTENCE FOR EVERY QUESTION.
    #
    # Measured live on a28549c: "Biggest risk?", "What proves this wrong?",
    # "Did you find none or fail to find it?" and "Show me the source. Is it
    # independent?" all returned "There is not enough public evidence to
    # answer that confidently." Four different questions, one canned answer,
    # on a run whose X-Ray asserted a supported pricing decision.
    #
    # D25 fixed only the branch gated on _STRATEGIC_INTENT -- the case that
    # was tested. Everything that did not match that pattern fell through to
    # here and still contradicted the contract. Same defect, one branch over.
    _fallback = "There is not enough public evidence to answer that confidently."
    if k is None and contract is not None and getattr(
            contract, "reading_exists", False):
        _fallback = (
            f"A supported reading of "
            f"{getattr(contract, 'company', '') or 'this company'} exists and "
            f"is set out on the Executive X-Ray. "
            + (getattr(contract, "run_contribution", "") or
               "This run did not add enough independent evidence to "
               "strengthen it.")
            + " This particular question is not answerable from what this run "
              "retrieved.")
    out.direct_answer = _plain(engine_answer) or (k.fact if k else _fallback)

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
            out.direct_answer = _ablation(trust, independent)
        # The standing earns a limitation on the surface that asked about
        # evidence, whatever the question's exact wording. A reader who asks
        # how strong the evidence is has asked the one question the standing
        # answers, and answering it without the caveat is the omission.
        _caveat = _ET.limitation(trust)
        if _caveat and _caveat not in out.limitations:
            out.limitations = tuple(out.limitations) + (_caveat,)
        out.fact_or_interpretation = (
            "Interpretation. The dated events are verified facts; the reading "
            "of what they add up to is an inference, and it is labelled as "
            "one." if k else "Verified fact only — no interpretation is "
                             "offered because the evidence does not support "
                             "one.")
    return out


def _ablation(trust, accounts: Sequence[dict]) -> str:
    """Would the reading survive without its strongest source?

    THE DEFECT THIS CLOSES
    ----------------------
    This answered `len(independent) >= 2`, where `independent` was every row
    whose publisher was not the company, and reported the figure to a founder
    as "N independent source(s) support this". Publisher class is not source
    dependence: three outlets rewriting one press release are three non-company
    rows and one observation. So the surface that exists to say how strong the
    evidence is was the surface inflating it — and the answer it gave for a
    dependent cluster ("still leaves independent corroboration") also leaked a
    banned internal term straight onto the page, because it was written after
    `_plain` had already run.

    Trust is READ, never computed here. Where the market side established a
    standing, that standing answers. Where it did not, the honest answer names
    the accounts and refuses the independence claim rather than guessing it.
    """
    n = len(accounts)
    if not n:
        return ("No — removing the strongest one leaves it resting on the "
                "company describing itself.")

    if trust.known:
        if trust.standing == _ET.CONFLICTED:
            return ("No — public sources disagree on this point, so it "
                    "cannot carry a confident conclusion on its own.")
        if trust.standing == _ET.DEPENDENT_REREPORTING:
            return ("No — several reports repeat the same underlying "
                    "announcement, so removing the strongest one does not "
                    "leave a separate account behind it.")
        if trust.may_claim_independence and trust.independent_support >= 2:
            return ("Probably — separate sources support this on their own, "
                    "so removing the strongest one still leaves a second "
                    "account standing.")
        # SINGLE_SOURCE, PARTIALLY_INDEPENDENT, or independence that was
        # established but thin: one account carries it either way.
        return ("No — this rests on a single underlying account, so removing "
                "it removes the basis for the reading.")

    # UNRATED. The count is reportable; independence is not, because nobody
    # established it. Saying "N independent sources" here is the inflation.
    other = n - 1
    tail = (f"that leaves {other} other account(s), though whether they "
            "confirm each other on their own was not established."
            if other else "there is no second account behind it.")
    return f"Not established — {tail}"


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
