"""V1.2 strategic follow-up conversation.

Answers reason over the strategic report's objects — observations,
hypotheses, counter-evidence, comparable patterns, evidence gaps, and decision
implications — instead of echoing a report card. A "why do you think X"
question returns the reasoning chain, cites the evidence, acknowledges
counter-evidence, states calibrated confidence, and explains what would
falsify the view.
"""
from __future__ import annotations

import re

CONVERSATION_VERSION = "strategic_conversation.v1"
_STOP = {"the", "a", "an", "is", "are", "do", "you", "think", "why", "how",
         "what", "of", "to", "in", "on", "and", "or", "does", "it", "its",
         "for", "about", "becoming", "toward", "into", "that", "this", "we"}


def _tokens(text: str) -> set:
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower())
            if w not in _STOP and len(w) > 2}


def _match_hypothesis(question: str, hypotheses: list, patterns: list):
    pat_by_id = {p["pattern_id"]: p for p in patterns}
    qtok = _tokens(question)
    best, best_score = None, 0
    for h in hypotheses:
        pat = pat_by_id.get(h.get("pattern_id", ""), {})
        htok = _tokens(" ".join([
            h.get("title", ""), h.get("statement", ""), h.get("reasoning", ""),
            pat.get("name", ""), pat.get("description", "")]))
        score = len(qtok & htok)
        if score > best_score:
            best, best_score = h, score
    return best if best_score else None


def answer_strategic(question: str, report) -> dict:
    """Return a structured, cited answer grounded in the strategic report."""
    r = report.as_dict() if hasattr(report, "as_dict") else report
    obs_by_id = {o["observation_id"]: o for o in r.get("observations", [])}
    hyp = _match_hypothesis(question, r.get("hypotheses", []),
                            r.get("patterns", []))

    if hyp is None:
        return {
            "conversation_version": CONVERSATION_VERSION, "intent": "UNMATCHED",
            "matched_hypothesis": None,
            "answer": {"reasoning": "I don't hold a strategic hypothesis that "
                       "matches that question. I can explain any of the "
                       "hypotheses in the report, the blind spots, or the "
                       "evidence gaps.",
                       "evidence": [], "counter_evidence": [],
                       "confidence": None, "confidence_reasons": [],
                       "falsification": [], "decision": ""},
            "citations": [],
        }

    def _cite(ids):
        out = []
        for i in ids:
            o = obs_by_id.get(i)
            if o:
                out.append({"observation_id": i,
                            "source_title": o.get("source_title", ""),
                            "source_class": o.get("source_class", ""),
                            "date": o.get("date", ""),
                            "excerpt": o.get("excerpt") or o.get("text", "")})
        return out

    supporting = _cite(hyp.get("supporting_observation_ids", []))
    counter = _cite(hyp.get("counter_observation_ids", []))
    counter_note = (counter and "There is genuine counter-evidence: "
                    + "; ".join(c["excerpt"] for c in counter[:2])
                    or "No direct counter-evidence was retrieved; the open "
                       "evidence gaps below temper the confidence instead.")

    reasoning = (
        f"I hold this as a {hyp['confidence']}-confidence hypothesis, not a "
        f"fact. {hyp['reasoning']} The strongest supporting evidence: "
        + "; ".join(f"{c['source_title']} ({c['source_class']})"
                    for c in supporting[:3]) + ".")

    return {
        "conversation_version": CONVERSATION_VERSION, "intent": "EXPLAINED",
        "matched_hypothesis": hyp["hypothesis_id"],
        "answer": {
            "reasoning": reasoning,
            "evidence": supporting,
            "counter_evidence": counter,
            "counter_note": counter_note,
            "confidence": hyp["confidence"],
            "confidence_reasons": hyp.get("confidence_reasons", []),
            "falsification": hyp.get("falsification_questions", []),
            "alternative_explanations": hyp.get("alternative_explanations", []),
            "decision": (hyp.get("decision_implications") or [""])[0],
        },
        "citations": [c["observation_id"] for c in supporting],
        "note": "Grounded in this run's approved observations and the curated "
                "pattern library; confidence and falsification are explicit.",
    }
