"""Conversation — the heart of the workspace (T023).

The canonical chain, and the reason the workspace can be trusted:

    domain artifact -> SourceRef -> SourceClaim -> composition ->
        optional model wording (over a CLOSED ClaimSet) ->
        deterministic claim validation -> cited answer

NOT: question -> model writes a plausible answer -> scan it for bad fields.

Concretely: deterministic code assembles the SourceClaims for a turn (a
closed **ClaimSet**). If a model is used for prose, it receives ONLY the
claim ids and their safe text, and it returns a **NarrativeCandidate** —
paragraphs that reference claim ids. Deterministic code then validates
that every referenced claim id is in the ClaimSet and attaches the
SourceRefs itself. The model never writes a citation, an identifier, or a
replay id into prose; any unknown claim id is rejected and recorded. With
no model, the answer is a deterministic composition of the same claims.

Composition may improve readability. It may never erase disagreement: a
CONFLICTED claim stays CONFLICTED in the answer.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from intent_engine.agentos.model_boundary import model_provenance
from intent_engine.personal.records import (
    AVAIL_CONFLICTED, AVAIL_OUT_OF_SCOPE, AVAIL_UNAVAILABLE, PersonalError,
    assert_workspace_language,
)
from intent_engine.personal.router import (
    CHALLENGE_ASSUMPTION, DRAFT_INVESTOR_EXPLANATION, EXPLAIN_FINDING,
    LIST_INVESTIGATIONS, SHOW_EVIDENCE, SUMMARIZE_COMPETITORS, TRACE_DECISION,
    UNKNOWN, classify, resolve_subsystems, supported_capabilities,
)

CONVERSATION_VERSION = "personal_conversation.v1"
NARRATIVE_PROMPT_VERSION = "personal_narrative.v1"


@dataclass(frozen=True)
class ClaimSet:
    """The closed set of claims a turn may speak about. The model may
    paraphrase only these; nothing else may enter the answer."""
    intent: str
    claims: tuple = ()          # tuple[SourceClaim]

    def ids(self) -> set:
        return {c.claim_id for c in self.claims}

    def by_id(self) -> dict:
        return {c.claim_id: c for c in self.claims}

    def model_view(self) -> list:
        """What the model is allowed to see: claim id + safe text +
        availability. No source refs, no identifiers to echo."""
        return [{"claim_id": c.claim_id, "text": c.text,
                 "availability": c.availability} for c in self.claims]


def build_claim_set(question: str, *, adapters: dict, package_id: str = None,
                    portfolio_id: str = None) -> ClaimSet:
    """Deterministic: route the question, read the owning adapters, and
    collect the SourceClaims. No model runs here."""
    intent = classify(question)
    claims = []

    if intent == UNKNOWN:
        from intent_engine.personal.adapters.base import out_of_scope_claim
        claims.append(out_of_scope_claim(
            "router.unknown",
            "this request is outside the workspace's supported capabilities: "
            + ", ".join(supported_capabilities())))
        return ClaimSet(intent=intent, claims=tuple(claims))

    if intent == SUMMARIZE_COMPETITORS:
        # dependency gap 1 — no subsystem owns competitor intelligence
        from intent_engine.personal.adapters.base import out_of_scope_claim
        claims.append(out_of_scope_claim(
            "competitors.none",
            "no subsystem reports competitor intelligence yet; this arrives "
            "with the public intelligence pass (T023.5)"))
        return ClaimSet(intent=intent, claims=tuple(claims))

    if intent in (EXPLAIN_FINDING, SHOW_EVIDENCE):
        claims.extend(adapters["research"].highlights(limit=5))
    if intent == TRACE_DECISION and package_id:
        resolved = adapters["executive"].trace_decision(package_id)
        from intent_engine.personal.adapters.base import unavailable_claim
        if resolved.get("available"):
            from intent_engine.personal.records import (
                AVAIL_SUPPORTED, SourceClaim, SourceRef,
            )
            ref = SourceRef(**resolved["source_ref"])
            trace = resolved["trace"]
            claims.append(SourceClaim(
                claim_id=f"trace.{package_id}",
                text=f"decision {package_id} is {trace.get('state')} — "
                     f"{trace.get('reason', '')}",
                availability=AVAIL_SUPPORTED, source_refs=(ref,),
                transformation="direct"))
        else:
            claims.append(unavailable_claim(
                f"trace.{package_id}", resolved.get("reason", "unavailable")))
    if intent == LIST_INVESTIGATIONS:
        claims.extend(adapters["research"].highlights(limit=3))
        # executive debt is surfaced as claims too
        for item in adapters["executive"].open_decision_debt():
            from intent_engine.personal.records import (
                AVAIL_SUPPORTED, SourceClaim, SourceRef,
            )
            claims.append(SourceClaim(
                claim_id=f"debt.{item.get('candidate_id')}.{item.get('kind')}",
                text=f"open decision debt ({item.get('kind')}): "
                     f"{item.get('detail', '')}",
                availability=AVAIL_SUPPORTED,
                source_refs=(SourceRef(**item["source_ref"]),),
                transformation="direct"))
    if intent == CHALLENGE_ASSUMPTION:
        # retrieve + compose only: supporting + contradicting evidence and
        # the gaps. The workspace generates NO new counterclaim.
        claims.extend(adapters["research"].highlights(limit=5))
    if intent == DRAFT_INVESTOR_EXPLANATION:
        from intent_engine.personal.adapters.base import out_of_scope_claim
        claims.append(out_of_scope_claim(
            "profile.investor",
            "the investor profile is registered but not yet a supported "
            "report profile in T023"))

    if not claims:
        from intent_engine.personal.adapters.base import unavailable_claim
        claims.append(unavailable_claim(
            f"{intent}.empty",
            "the owning agents report nothing for this request yet"))
    return ClaimSet(intent=intent, claims=tuple(claims))


def validate_narrative(claim_set: ClaimSet, narrative_candidate: dict) -> dict:
    """Deterministic validation of a model NarrativeCandidate.

    Every paragraph's claim_ids must be in the ClaimSet. An unknown claim
    id is a rejection. The workspace attaches the SourceRefs itself — the
    model never writes an identifier or a citation.
    """
    allowed = claim_set.ids()
    by_id = claim_set.by_id()
    paragraphs = narrative_candidate.get("paragraphs")
    if not isinstance(paragraphs, list):
        raise PersonalError("a NarrativeCandidate has a list of paragraphs")
    composed = []
    for para in paragraphs:
        text = para.get("text", "")
        claim_ids = tuple(para.get("claim_ids", ()))
        unknown = sorted(set(claim_ids) - allowed)
        if unknown:
            raise PersonalError(
                f"model narrative references claim id(s) not in the closed "
                f"ClaimSet: {unknown} — invented citations are rejected")
        assert_workspace_language(text, where="narrative paragraph")
        composed.append({
            "text": text,
            "citations": [by_id[cid].source_refs[0].as_dict()
                          for cid in claim_ids
                          if by_id[cid].source_refs],
            "claim_ids": list(claim_ids),
        })
    return {"paragraphs": composed, "validated": True}


def _deterministic_answer(claim_set: ClaimSet) -> dict:
    """The no-model composition: one paragraph per claim, cited. Readable
    enough to be useful; disagreement preserved."""
    paragraphs = []
    for claim in claim_set.claims:
        paragraphs.append({
            "text": claim.text,
            "availability": claim.availability,
            "citations": [r.as_dict() for r in claim.source_refs],
            "claim_ids": [claim.claim_id],
        })
    return {"paragraphs": paragraphs, "validated": True}


def answer(question: str, *, adapters: dict, llm_client=None,
           model_version="fake-model.v0", package_id: str = None,
           portfolio_id: str = None) -> dict:
    """A full turn: deterministic ClaimSet -> optional validated model
    prose -> cited answer. Disagreement is preserved; nothing is invented."""
    claim_set = build_claim_set(question, adapters=adapters,
                                package_id=package_id,
                                portfolio_id=portfolio_id)
    provenance = None
    if llm_client is not None and claim_set.claims:
        provenance = model_provenance(NARRATIVE_PROMPT_VERSION, model_version,
                                      authority="paraphrase over a closed "
                                                "ClaimSet; the workspace "
                                                "attaches citations")
        candidate = llm_client.call_tool(
            prompt_version=NARRATIVE_PROMPT_VERSION,
            user_message={"question": question,
                          "claims": claim_set.model_view()})
        body = validate_narrative(claim_set, candidate)
    else:
        body = _deterministic_answer(claim_set)

    conflicted = [c.claim_id for c in claim_set.claims
                  if c.availability == AVAIL_CONFLICTED]
    unavailable = [c.claim_id for c in claim_set.claims
                   if c.availability in (AVAIL_UNAVAILABLE, AVAIL_OUT_OF_SCOPE)]
    return {
        "conversation_version": CONVERSATION_VERSION,
        "intent": claim_set.intent,
        "answer": body,
        "claim_ids": sorted(claim_set.ids()),
        "preserved_conflicts": conflicted,
        "unavailable_or_out_of_scope": unavailable,
        "model_provenance": provenance,
        "routing": resolve_subsystems(claim_set.intent),
        "note": ("every paragraph cites a source artifact the agents "
                 "produced; conflicts and unavailable results are preserved, "
                 "never smoothed"),
    }


def challenge_assumption(package_id_or_question: str, *, adapters: dict) -> dict:
    """"Challenge this assumption" = retrieve and compose, NOT generate a
    new substantive counterclaim.

    It returns the owning assumption's supporting evidence, existing
    contradictions the research already surfaced, confidence and unresolved
    gaps, and the evidence that would change the current view — all read
    from the agents, none authored by the workspace.
    """
    highlights = adapters["research"].highlights(limit=8)
    supporting = [c.as_dict() for c in highlights
                  if c.availability in ("SUPPORTED", "PARTIALLY_SUPPORTED")]
    contradictions = [c.as_dict() for c in highlights
                      if c.availability == AVAIL_CONFLICTED]
    debt = adapters["research"].read_research_debt()
    return {
        "conversation_version": CONVERSATION_VERSION,
        "mode": "challenge_by_retrieval",
        "supporting_evidence": supporting,
        "existing_contradictions": contradictions,
        "unresolved_gaps": [d for d in debt],
        "evidence_that_would_change_the_view": [
            {"kind": d.get("kind"), "detail": d.get("detail", ""),
             "source_ref": d.get("source_ref")} for d in debt],
        "note": ("the workspace retrieves the assumption's support, the "
                 "contradictions research already found, and the gaps — it "
                 "does not generate a new counterclaim of its own"),
    }
