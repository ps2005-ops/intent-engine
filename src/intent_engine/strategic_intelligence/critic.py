"""The last read before a stranger sees it.

WHAT THIS IS FOR
----------------
The quality gate asks whether the evidence was sufficient. The scorecard asks
whether the output is shaped like a product. Neither reads the report the way
a sceptical person would, looking for the specific ways an analysis can be
wrong while every structural check passes:

  * a leadership question that could be asked of any company;
  * a historical analogy quietly doing the work of evidence;
  * a claim resting on a document's title rather than anything in it;
  * a claim written more confidently than the sources behind it;
  * two sections of the same report disagreeing.

WHAT IT DOES NOT DO
-------------------
It does not rewrite. A critic that edits is a second author with less context
than the first, and its "improvements" arrive unreviewed in the reader's copy.
This produces findings — each naming what is wrong, where, and what would fix
it — and the caller decides. Where a finding cannot be fixed automatically it
becomes a stated limitation, which is worth more to a reader than a silent
correction.

It runs once. A critique loop that re-critiques its own output converges on
whatever the critic likes rather than on what is true, and it has no budget.
"""
from __future__ import annotations

import re

CRITIC_VERSION = "si_critic.v1"

# Severities. `block` means a reader should not be shown this as it stands;
# `note` means it should be said out loud rather than fixed.
BLOCK = "block"
NOTE = "note"

# Questions that survive replacing the company with any other company. The
# test is deliberately about the QUESTION, not about its wording: "what is the
# competitive landscape?" is generic whoever asks it.
_GENERIC_QUESTION_STEMS = (
    "what is the competitive landscape",
    "what are the key risks",
    "what is the growth strategy",
    "how is the market changing",
    "what are the main challenges",
    "who are the competitors",
    "what is the long-term vision",
    "how will they scale",
    "what is the total addressable market",
)

# Language that presents an analogy as though it were an observation about
# this company.
_ANALOGY_AS_EVIDENCE = (
    "as stripe did", "just as aws", "exactly as slack", "the same way that",
    "history shows that this company", "which proves this company",
)

_HEDGES = ("appears to", "suggests", "may ", "might ", "could ", "seems to",
           "indicates", "points to")
_ABSOLUTES = ("will ", "must ", "always", "never", "certainly", "proves",
              "guarantees", "undoubtedly", "clearly shows", "confirms that")


def _as_dict(report):
    return report.as_dict() if hasattr(report, "as_dict") else (report or {})


def _finding(code, severity, message, *, where="", remedy=""):
    return {"code": code, "severity": severity, "message": message,
            "where": where, "remedy": remedy}


def critique(report, *, documents=()) -> dict:
    """Read the finished report as a sceptical person would.

    Deterministic and offline. Returns findings and a verdict; never a rewrite.
    """
    r = _as_dict(report)
    company = r.get("company_name", "")
    findings = []
    findings += _generic_questions(r)
    findings += _analogy_as_evidence(r)
    findings += _title_only_claims(r, documents)
    findings += _claims_stronger_than_sources(r)
    findings += _sections_that_disagree(r)
    findings += _company_missing_from_its_own_thesis(r, company)

    blocking = [f for f in findings if f["severity"] == BLOCK]
    return {
        "critic_version": CRITIC_VERSION,
        "findings": findings,
        "blocking": [f["code"] for f in blocking],
        "publishable": not blocking,
        # What a reader should be told about the things that were not fixed.
        "limitations": [f["message"] for f in findings
                        if f["severity"] == NOTE],
    }


def _generic_questions(r) -> list:
    out = []
    for question in r.get("questions") or ():
        text = str((question or {}).get("question", "")).lower()
        if any(stem in text for stem in _GENERIC_QUESTION_STEMS):
            out.append(_finding(
                "generic_leadership_question", BLOCK,
                "a question for leadership could be asked of any company and "
                "tells the reader nothing about this one",
                where=text[:80],
                remedy="ask about something the evidence in this run "
                       "actually raised"))
    return out


def _analogy_as_evidence(r) -> list:
    out = []
    for h in r.get("hypotheses") or ():
        text = " ".join([str(h.get("statement", "")),
                         str(h.get("reasoning", ""))]).lower()
        for phrase in _ANALOGY_AS_EVIDENCE:
            if phrase in text:
                out.append(_finding(
                    "analogy_used_as_evidence", BLOCK,
                    "a historical comparison is doing the work of evidence: "
                    "what another company did is not an observation about "
                    "this one",
                    where=h.get("hypothesis_id", ""),
                    remedy="state the comparison as a comparison, and cite "
                           "this company's own evidence for the claim"))
                break
    return out


def _title_only_claims(r, documents) -> list:
    """A claim whose only support is a document nothing could be read from.

    "SEC 6-K is shifting where demand is captured" came from a filing whose
    text never loaded: the title was the evidence.
    """
    metadata_only = {d.get("source_id") or d.get("final_url")
                     for d in documents or ()
                     if d.get("extraction_mode") == "metadata"}
    if not metadata_only:
        return []
    out = []
    observations = {o.get("observation_id"): o
                    for o in r.get("observations") or ()}
    for h in r.get("hypotheses") or ():
        support = [observations.get(i) for i in
                   h.get("supporting_observation_ids") or ()]
        support = [o for o in support if o]
        if support and all(
                (o.get("source_url") or o.get("source_title"))
                in metadata_only for o in support):
            out.append(_finding(
                "claim_rests_on_a_title", BLOCK,
                "every source behind this claim is a document whose text "
                "could not be read — the claim rests on a title",
                where=h.get("hypothesis_id", ""),
                remedy="retrieve the document body, or withdraw the claim"))
    return out


def _claims_stronger_than_sources(r) -> list:
    """Absolute language on a claim the report itself calls uncertain."""
    out = []
    for h in r.get("hypotheses") or ():
        confidence = str(h.get("confidence", "")).lower()
        if confidence not in ("speculative", "low"):
            continue
        statement = str(h.get("statement", ""))
        low = " " + statement.lower() + " "
        if any(a in low for a in _ABSOLUTES) and \
                not any(hedge in low for hedge in _HEDGES):
            out.append(_finding(
                "claim_stronger_than_its_confidence", BLOCK,
                f"a {confidence}-confidence claim is written as a certainty",
                where=h.get("hypothesis_id", ""),
                remedy="write the claim at the strength the evidence "
                       "supports"))
    return out


def _sections_that_disagree(r) -> list:
    """The thesis saying one thing while the hypotheses say another.

    Cheap and specific on purpose: a report that declines to form a view while
    also presenting hypotheses is telling the reader two different things on
    the same page, and that has happened.
    """
    thesis = r.get("thesis") or {}
    hypotheses = r.get("hypotheses") or []
    if thesis.get("view_withheld") and hypotheses:
        return [_finding(
            "thesis_contradicts_its_own_hypotheses", BLOCK,
            "the report says no view can be supported while also presenting "
            "hypotheses",
            where="thesis",
            remedy="either lead with the strongest hypothesis or withdraw "
                   "them all")]
    return []


def _company_missing_from_its_own_thesis(r, company) -> list:
    """A central view that never names the company it is about."""
    thesis = r.get("thesis") or {}
    view = str(thesis.get("view", ""))
    if not view or thesis.get("view_withheld"):
        return []
    first = (company or "").split()[0] if company else ""
    if first and not re.search(rf"\b{re.escape(first)}\b", view, re.I):
        return [_finding(
            "thesis_does_not_name_the_company", NOTE,
            "the central view never names the company it is about",
            where="thesis",
            remedy="name the subject in the sentence a reader reads first")]
    return []
