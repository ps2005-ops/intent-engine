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

# Supported public follow-up intents (closed).
_SUPPORTED = (
    "why do you think", "show", "evidence", "how fresh", "contradict",
    "confidence", "change your view", "persona", "market", "assumption",
    "investigate", "explain", "board", "brief",
)
# Causal phrasings the workspace may not assert unless a source supports it.
_CAUSAL = ("reduces", "reducing", "causes", "causing", "because of you",
           "is lowering", "drives down", "hurts")


def run_claim_set(question: str, run_claims: list) -> ClaimSet:
    """Build a closed ClaimSet from THIS run's claims only."""
    lowered = " ".join((question or "").lower().split())
    if not any(marker in lowered for marker in _SUPPORTED):
        from intent_engine.personal.adapters.base import out_of_scope_claim
        return ClaimSet(intent="UNSUPPORTED", claims=(out_of_scope_claim(
            "fi.unsupported",
            "this question is outside the supported follow-up capabilities; "
            "ask about the evidence, confidence, freshness, personas, market "
            "view, or assumptions"),))
    # a supported follow-up speaks only over this run's supported claims
    speakable = tuple(c for c in run_claims
                      if c.availability not in (AVAIL_OUT_OF_SCOPE,))
    if not speakable:
        from intent_engine.personal.adapters.base import unavailable_claim
        return ClaimSet(intent="INSUFFICIENT", claims=(unavailable_claim(
            "fi.insufficient",
            "there is not yet enough supported evidence to answer this"),))
    return ClaimSet(intent="SUPPORTED", claims=speakable)


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
