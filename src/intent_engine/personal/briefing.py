"""The morning brief — assembled, not authored (T023).

The brief is a deterministic composition of what the agents already
report: research highlights, executive decisions, risks, open questions,
and recommended INVESTIGATIONS (not recommendations — investigations, the
thing a founder acts on). Every line is a SourceClaim that cites its source
artifact; a gap is named, never filled. No model runs here — the brief is
facts the agents produced, grouped and cited.

An `InvestigationCandidate` is structured so the workspace cannot smuggle
advice through wording: it carries the source debt item, why it is
unresolved, the owning subsystem, the owner-supplied urgency/order, the
evidence needed, and the current limitation — and it uses no imperative
verb ("conduct", "launch", "change"). It says what is missing and what is
uncertain, never what to do.
"""
from __future__ import annotations

from intent_engine.personal.records import (
    AVAIL_UNAVAILABLE, BANNED_INVESTIGATION_VERBS, PersonalError, SourceClaim,
    SourceRef,
)

BRIEF_VERSION = "personal_brief.v1"
INVESTIGATION_VERSION = "investigation_candidate.v1"


def _assert_not_imperative(text: str) -> None:
    lowered = " ".join((text or "").lower().split())
    hits = sorted({v for v in BANNED_INVESTIGATION_VERBS if v in lowered})
    if hits:
        raise PersonalError(
            f"an investigation frames what is missing or uncertain, not an "
            f"instruction to act; drop the imperative verb(s) {hits}")


def investigation_candidate(*, source_debt_kind: str, why_unresolved: str,
                            owning_subsystem: str, owner_order,
                            evidence_needed: str, current_limitation: str,
                            source_ref: dict, owner_question: str = "") -> dict:
    """A structured investigation — never an imperative.

    The imperative wall applies to the WORKSPACE'S OWN framing
    (why_unresolved, evidence_needed, current_limitation), so the workspace
    cannot smuggle advice in as a command. It deliberately does NOT apply to
    `owner_question` — that is the owning agent's verbatim text, cited not
    authored, and quoting an agent's question is not the workspace giving an
    instruction. The urgency/order is whatever the owning agent supplied;
    the workspace synthesizes no ranking across debt types."""
    for text in (why_unresolved, evidence_needed, current_limitation):
        _assert_not_imperative(text)
    return {
        "investigation_version": INVESTIGATION_VERSION,
        "source_debt_kind": source_debt_kind,
        "why_unresolved": why_unresolved,
        "owning_subsystem": owning_subsystem,
        "owner_supplied_order": owner_order,
        "evidence_needed": evidence_needed,
        "current_limitation": current_limitation,
        "owner_question": owner_question,      # verbatim agent text, cited
        "source_ref": source_ref,
        "framing": "a question worth resolving — not an instruction to act",
    }


def _investigations_from_research(research_adapter) -> list:
    out = []
    for item in research_adapter.read_research_debt():
        out.append(investigation_candidate(
            source_debt_kind=item["kind"],
            why_unresolved="the research package reports this question is not "
                           "settled",
            owning_subsystem="research",
            owner_order=None,        # research debt carries no rank; preserved as None
            evidence_needed="a primary source or corroboration is missing",
            current_limitation="the current view rests on unsettled evidence",
            owner_question=item.get("question", ""),   # verbatim, cited
            source_ref=item["source_ref"]))
    return out


def _investigations_from_executive(executive_adapter) -> list:
    out = []
    for item in executive_adapter.open_decision_debt():
        out.append(investigation_candidate(
            source_debt_kind=item["kind"],
            why_unresolved="the executive layer reports this decision waits "
                           "on a person",
            owning_subsystem="executive",
            owner_order=None,
            evidence_needed=item.get("clears_when", "the blocking input"),
            current_limitation=item.get("detail", "unresolved decision debt"),
            source_ref=item["source_ref"]))
    return out


def assemble_brief(*, research_adapter, executive_adapter, product_adapter,
                   as_of: str, portfolio_id: str = None) -> dict:
    """Deterministic. The same adapter reads produce the same brief."""
    highlights = research_adapter.highlights(limit=5)
    decisions = executive_adapter.decision_load()
    top = executive_adapter.top_decisions(limit=3)

    # risks = the conflicts the executive layer already counted, named
    risks = [c for c in decisions
             if "conflict" in c.claim_id and not c.text.startswith("0 ")]

    investigations = (_investigations_from_research(research_adapter)
                      + _investigations_from_executive(executive_adapter))

    # open questions = research that is CONFLICTED, surfaced as questions
    open_questions = [c for c in highlights if c.availability == "CONFLICTED"]

    portfolio = (product_adapter.portfolio_summary(portfolio_id)
                 if portfolio_id else [])

    sections = {
        "research_highlights": [c.as_dict() for c in highlights],
        "executive_decisions": [c.as_dict() for c in decisions],
        "top_of_queue": [c.as_dict() for c in top],
        "risks": [c.as_dict() for c in risks],
        "open_questions": [c.as_dict() for c in open_questions],
        "recommended_investigations": investigations,
        "portfolio": [c.as_dict() for c in portfolio],
    }

    # a gap is named, not filled
    gaps = [name for name, claims in sections.items()
            if isinstance(claims, list) and not claims]

    return {
        "brief_version": BRIEF_VERSION,
        "as_of": as_of,
        "sections": sections,
        "gaps_named": gaps,
        "note": ("assembled from what the agents already report; every line "
                 "cites its source artifact, and a gap is named rather than "
                 "filled. Investigations state what is missing or uncertain, "
                 "never what to do."),
    }
