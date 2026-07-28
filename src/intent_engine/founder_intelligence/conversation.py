"""Public follow-up conversation (T023.5) — built on the T023 chain.

The public conversation reuses T023's closed-ClaimSet contract exactly, so
the public UI and the internal workspace share one provenance model:

    domain artifact -> SourceRef -> SourceClaim -> composition ->
        closed ClaimSet -> optional model wording ->
        deterministic claim validation -> cited answer

The ClaimSet is scoped to ONE run's claims — a conversation can never use
another run's or another company's claims. A fabricated claim id, a
fabricated statistic, or an unsupported causal claim is rejected. Unknown
questions return an honest insufficient-evidence response. There is no
general planner.
"""
from __future__ import annotations

import re

from intent_engine.agentos.model_boundary import model_provenance
from intent_engine.personal.conversation import (
    ClaimSet, validate_narrative,
)
from intent_engine.personal.records import (
    AVAIL_OUT_OF_SCOPE, AVAIL_UNAVAILABLE,
)
from intent_engine.founder_intelligence.records import FounderIntelligenceError

CONVERSATION_VERSION = "fi_conversation.v1"
NARRATIVE_PROMPT_VERSION = "fi_narrative.v1"

# Topics a follow-up can be about, and the natural phrasings people actually
# use. This replaced a flat keyword whitelist that a first-time tester broke
# immediately: "What does this company actually do?" contained none of the
# magic words and was rejected as UNSUPPORTED — the most basic question anyone
# asks about a company.
#
# Matching a topic does two things: it decides that the question IS answerable,
# and it decides WHICH claims are relevant. The old code did only the first,
# so "Explain this in simple terms" matched on "explain" and then returned
# every claim in the run — which is how a request for a plain-English summary
# came back as "Pricing model: not determinable from the approved sources".
_TOPICS = {
    "identity": ("what does", "what do they", "what is this company",
                 "what's this company", "who are they", "who is this company",
                 "what does this company do", "about this company",
                 "describe the company", "explain the company"),
    "products": ("product", "sell", "offering", "service", "platform",
                 "what do they sell", "software"),
    "customers": ("customer", "who buys", "client", "user base", "audience",
                  "who uses", "use case"),
    "risks": ("risk", "threat", "concern", "weakness", "danger", "downside",
              "what could go wrong", "vulnerab"),
    "recent_change": ("recent", "changed", "change", "latest", "new",
                      "happening", "news", "development"),
    "opportunity": ("opportunit", "growth", "upside", "expand", "potential"),
    "evidence": ("evidence", "source", "proof", "cite", "citation",
                 "how do you know", "where did", "back this up"),
    "confidence": ("confidence", "confident", "how sure", "how certain",
                   "reliable", "trust this"),
    "contradiction": ("contradict", "counter", "disagree", "against this",
                      "change your view", "challenge"),
    "leadership": ("leadership", "board", "executive", "management",
                   "should i ask", "investigate", "questions for"),
    "market": ("market", "competitor", "compare", "industry", "landscape",
               "rivals", "alternatives"),
    "summary": ("summar", "overview", "tldr", "tl;dr", "in short", "brief",
                "simple terms", "simply", "simpler", "easier to understand",
                "plain english", "explain this", "eli5", "recap",
                "the gist", "key points", "main points", "takeaway"),
    "limitation": ("limitation", "limited", "why so short", "missing",
                   "what don't you know", "what do you not know", "gap",
                   "incomplete", "not enough evidence"),
    "persona": ("persona", "who is this for", "buyer"),
    # "Why does this matter?" is one of the commonest follow-ups and matched
    # nothing at all before.
    "implication": ("why is this important", "why does this matter",
                    "why it matters", "so what", "importance", "impact",
                    "what does this mean", "significance"),
    "assumption": ("assumption", "assume", "hypothes"),
}

# Topics that legitimately speak over the whole run rather than a slice of it.
_BROAD_TOPICS = ("summary", "identity", "limitation", "confidence", "evidence")

# Kept for backwards compatibility with callers that imported it.
_SUPPORTED = tuple(sorted({p for ps in _TOPICS.values() for p in ps}))


def detect_topics(question: str) -> tuple:
    """Which topics a question is about. Empty when nothing is recognised.

    Deterministic and offline on purpose: a follow-up must behave the same way
    every time, and must not depend on a model being reachable.
    """
    lowered = " ".join((question or "").lower().split())
    hits = [topic for topic, phrases in _TOPICS.items()
            if any(p in lowered for p in phrases)]
    # Longest-phrase wins for the common "explain this simply" case, which
    # matches both `identity` and `summary`; summary is the better answer.
    if "summary" in hits and len(hits) > 1:
        hits = ["summary"] + [h for h in hits if h != "summary"]
    return tuple(hits)


def _relevant_claims(topics: tuple, speakable: tuple) -> tuple:
    """Narrow the run's claims to the ones the question is actually about.

    Returning everything is what produced an answer about pricing to a request
    for a simple explanation.
    """
    if not topics or any(t in _BROAD_TOPICS for t in topics):
        return speakable
    wanted = tuple(w for t in topics for w in _TOPICS[t])
    scoped = tuple(
        c for c in speakable
        if any(w in (getattr(c, "claim_id", "") or "").lower()
               or w in (getattr(c, "text", "") or "").lower()
               for w in wanted))
    # Never answer with something unrelated just to have an answer.
    return scoped


# Causal phrasings the workspace may not assert unless a source supports it.
_CAUSAL = ("reduces", "reducing", "causes", "causing", "because of you",
           "is lowering", "drives down", "hurts")


def run_claim_set(question: str, run_claims: list) -> ClaimSet:
    """Build a closed ClaimSet from THIS run's claims only."""
    topics = detect_topics(question)
    speakable = tuple(c for c in run_claims
                      if c.availability not in (AVAIL_OUT_OF_SCOPE,))

    if not topics:
        # Not "unsupported" — just not understood. The reply names things the
        # user can actually ask instead of describing our internals.
        from intent_engine.personal.adapters.base import out_of_scope_claim
        return ClaimSet(intent="UNRECOGNISED", claims=(out_of_scope_claim(
            "fi.unrecognised",
            "I can answer questions about this company and this analysis. I "
            "could not tell what you meant. Try \"What does this company "
            "do?\", \"Who are its customers?\", \"What are the main risks?\", "
            "or \"Summarise this simply\"."),))

    if not speakable:
        from intent_engine.personal.adapters.base import unavailable_claim
        return ClaimSet(intent="INSUFFICIENT", claims=(unavailable_claim(
            "fi.insufficient",
            "there is not yet enough supported evidence to answer this"),))

    relevant = _relevant_claims(topics, speakable)
    if not relevant:
        # Understood, but this run holds nothing on that subject. Saying so is
        # the honest answer; substituting an unrelated claim is not.
        from intent_engine.personal.adapters.base import unavailable_claim
        subject = topics[0].replace("_", " ")
        return ClaimSet(intent="INSUFFICIENT", claims=(unavailable_claim(
            "fi.insufficient",
            f"this analysis does not yet contain evidence about {subject} "
            f"for this company; the evidence library shows which sources "
            f"were retrieved and which failed"),))
    return ClaimSet(intent="SUPPORTED", claims=relevant)


def answer(question: str, *, run_claims: list, llm_client=None,
           model_version="fake-model.v0") -> dict:
    """A public follow-up turn. Rejects fabricated claims and unsupported
    causality; preserves disagreement."""
    lowered = " ".join((question or "").lower().split())
    claim_set = run_claim_set(question, run_claims)

    provenance = None
    if llm_client is not None and claim_set.intent == "SUPPORTED":
        provenance = model_provenance(NARRATIVE_PROMPT_VERSION, model_version,
                                      authority="paraphrase over a closed, "
                                                "run-scoped ClaimSet")
        candidate = llm_client.call_tool(
            prompt_version=NARRATIVE_PROMPT_VERSION,
            user_message={"question": question,
                          "claims": claim_set.model_view()})
        body = validate_narrative(claim_set, candidate)
        # an unsupported causal claim in model prose is rejected
        joined = " ".join(p["text"] for p in body["paragraphs"]).lower()
        if any(marker in joined for marker in _CAUSAL) and not any(
                "caus" in c.text.lower() for c in claim_set.claims):
            raise FounderIntelligenceError(
                "the answer asserts a causal relationship no source supports "
                "— only the supported observation is permitted")
    else:
        body = {"paragraphs": [{"text": c.text, "availability": c.availability,
                                "citations": [r.as_dict()
                                              for r in c.source_refs],
                                "claim_ids": [c.claim_id]}
                               for c in claim_set.claims], "validated": True}

    conflicted = [c.claim_id for c in claim_set.claims
                  if c.availability == "CONFLICTED"]
    return {
        "conversation_version": CONVERSATION_VERSION,
        "intent": claim_set.intent,
        "answer": body,
        "preserved_conflicts": conflicted,
        "model_provenance": provenance,
        "note": "every paragraph cites a run-scoped source artifact; "
                "conflicts and unavailable results are preserved",
    }
