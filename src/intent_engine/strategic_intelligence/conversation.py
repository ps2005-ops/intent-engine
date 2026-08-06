"""V1.2 strategic follow-up conversation with query routing.

Answers reason over the strategic report's objects — observations,
hypotheses, counter-evidence, comparable patterns, evidence gaps, and decision
implications. A routing layer first detects the requested OPERATION (support,
contradiction, comparison, falsification, implication, summary) and the target
hypothesis / comparable company, so a "how is this like Stripe" question is
answered with the hypothesis whose pattern actually cites Stripe — using a
dedicated comparison structure that names and discusses Stripe — not whatever
hypothesis happens to share keywords.

Answers are selective (a few strongest observations, one or two counters), lead
with a direct answer, and never expose internal signal names or record ids in
the human-facing body.
"""
from __future__ import annotations

import re

CONVERSATION_VERSION = "strategic_conversation.v2"
_STOP = {"the", "a", "an", "is", "are", "do", "you", "think", "why", "how",
         "what", "of", "to", "in", "on", "and", "or", "does", "it", "its",
         "for", "about", "becoming", "toward", "into", "that", "this", "we",
         "similar", "compare", "comparison", "like", "where", "break", "breaks",
         "down", "different", "difference", "differ"}

# operation cue words
_OP_CUES = {
    "comparison": ("similar", "compare", "comparison", "like ", "versus", " vs",
                   "analog", "break down", "breaks down", "how is this like"),
    "contradiction": ("weaken", "against", "counter", "contradict", "argue "
                      "against", "disagree", "wrong", "risk to"),
    "falsification": ("falsify", "disprove", "what would change", "invalidate",
                      "prove it wrong"),
    "implication": ("decision", "implication", "so what", "should we", "affect",
                    "what does it mean"),
    "agenda": ("agenda", "leadership discuss", "being debated", "internally",
               "timely", "recent", "last six months", "changed"),
}


def _tokens(text: str) -> set:
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower())
            if w not in _STOP and len(w) > 2}


def _detect_operation(q: str) -> str:
    """Which operation the question is asking for.

    Comparison is tried LAST, and only ever wins when the caller can also name
    something to compare with. Its cues are the loosest in the set — a bare
    "like" appears in "this seems like a stretch, what argues against it?",
    which is a request for counter-evidence and was being routed to a
    comparison against nothing. The answer structure for comparison has no
    entry in the lead table, so that question did not degrade: it raised
    KeyError and the reader got an error page for asking a normal question.
    """
    low = " " + q.lower() + " "
    for op in ("falsification", "contradiction", "implication", "agenda",
               "comparison"):
        if any(cue in low for cue in _OP_CUES[op]):
            return op
    return "support"


def _all_comparables(report) -> dict:
    """name(lower) -> pattern_id, from the cited historical examples."""
    out = {}
    for p in report.get("patterns", []):
        for e in p.get("historical_examples", []):
            name = (e.get("name") or "").split("→")[0].split("(")[0].strip()
            for token in re.findall(r"[A-Za-z][A-Za-z0-9.\-]+", name):
                if len(token) > 2:
                    out[token.lower()] = p["pattern_id"]
    return out


def _detect_comparable(q: str, report) -> tuple:
    """Return (comparable_name, pattern_id) if the question names one of the
    report's cited comparison companies, else (None, None)."""
    comparables = _all_comparables(report)
    low = q.lower()
    for name, pattern_id in comparables.items():
        # word-boundary match so "stripe" matches but "strip" does not over-match
        if re.search(rf"\b{re.escape(name)}\b", low):
            return name, pattern_id
    return None, None


def _hyp_by_pattern(report, pattern_id):
    for h in report.get("hypotheses", []):
        if h.get("pattern_id") == pattern_id:
            return h
    return None


def _match_hypothesis(question: str, report):
    """Keyword-overlap fallback when no comparable/operation pins a hypothesis."""
    pat_by_id = {p["pattern_id"]: p for p in report.get("patterns", [])}
    qtok = _tokens(question)
    best, best_score = None, 0
    for h in report.get("hypotheses", []):
        pat = pat_by_id.get(h.get("pattern_id", ""), {})
        htok = _tokens(" ".join([
            h.get("title", ""), h.get("statement", ""),
            pat.get("name", ""), pat.get("description", "")]))
        score = len(qtok & htok)
        if score > best_score:
            best, best_score = h, score
    return best if best_score else None


def _cite(ids, obs_by_id, limit=None):
    out = []
    for i in ids:
        o = obs_by_id.get(i)
        if o:
            out.append({"observation_id": i,
                        "source_title": o.get("source_title", ""),
                        "source_class": o.get("source_class", ""),
                        "date": o.get("date", ""),
                        "excerpt": o.get("excerpt") or o.get("text", "")})
        if limit and len(out) >= limit:
            break
    return out


def _pattern_for(report, pattern_id):
    for p in report.get("patterns", []):
        if p["pattern_id"] == pattern_id:
            return p
    return {}


def _comparison_answer(question, report, hyp, comparable, obs_by_id):
    pat = _pattern_for(report, hyp["pattern_id"])
    support = _cite(hyp.get("strongest_support_ids")
                    or hyp.get("supporting_observation_ids", []), obs_by_id, 3)
    # find the cited example that matches the named comparable
    example = next((e for e in pat.get("historical_examples", [])
                    if comparable.lower() in (e.get("name", "").lower())), {})
    name = comparable.title()
    mechanism_head = pat.get("mechanism", "").split(".")[0]
    direct = (f"The comparison to {name} is apt for one specific reason: the "
              f"same mechanism — {mechanism_head}. It is a partial analogy, "
              f"not an identity.")
    example_note = example.get("note") or "followed the same transition"
    return {
        "direct_answer": direct,
        "shared_mechanism": pat.get("mechanism", ""),
        "key_similarities": [
            f"Both fit the '{pat.get('name', '')}' transition.",
            f"{name}: {example_note}.",
        ],
        "key_differences": [
            "Business model, customer, and where value is captured differ — a "
            "shared mechanism does not mean shared economics.",
            pat.get("when_it_does_not_apply", ""),
        ],
        "where_the_analogy_breaks": pat.get("limitations", "")
        or pat.get("when_it_does_not_apply", ""),
        "strategic_implication": (hyp.get("decision_implications") or [""])[0],
        "confidence": hyp.get("confidence"),
        "missing_evidence": (hyp.get("evidence_gaps") or [""])[0],
        "supporting_evidence": support,
        "comparable": comparable.title(),
    }


def answer_strategic(question: str, report) -> dict:
    """Route the question, then answer with the right structure. ``report`` may
    be a StrategicReport or its ``as_dict()``."""
    r = report.as_dict() if hasattr(report, "as_dict") else report
    obs_by_id = {o["observation_id"]: o for o in r.get("observations", [])}
    operation = _detect_operation(question)
    comparable, cmp_pattern = _detect_comparable(question, r)
    # A comparison with nothing to compare against is not a comparison. Read it
    # as the question underneath: what does the evidence say.
    if operation == "comparison" and not comparable:
        operation = "support"

    # routing: a named comparable pins the hypothesis whose pattern cites it
    hyp = _hyp_by_pattern(r, cmp_pattern) if cmp_pattern else None
    if hyp is None:
        hyp = _match_hypothesis(question, r)
    if hyp is None and r.get("hypotheses"):
        hyp = r["hypotheses"][0]            # fall back to the leading thesis

    routing = {"operation": operation,
               "selected_hypothesis": hyp["hypothesis_id"] if hyp else None,
               "selected_comparable": comparable.title() if comparable else None}

    if hyp is None:
        # A DEAD END IS NOT AN ANSWER.
        #
        # "I don't yet hold a hypothesis that matches that question." was the
        # whole reply, and a reader who typed "hm" or "tell me more" was left
        # with nowhere to go — they cannot know what this run does hold, so
        # they cannot ask a better question. Reachable for any run that
        # produced no hypothesis, which stopped being rare the moment readings
        # had to earn their evidence rather than clear a signal count.
        #
        # What follows names what the run DID find, from the run's own dated
        # findings, so the next question is one the reader can actually form.
        # Nothing is invented: if there is nothing to offer, the sentence stays
        # as it was rather than promising material that does not exist.
        found = [s.get("title", "") for s in (r.get("shifts") or ())
                 if s.get("title")][:3]
        answer = "I don't yet hold a hypothesis that matches that question."
        if found:
            answer += (" What this run did find, and can be asked about: "
                       + "; ".join(t.rstrip(".") for t in found) + ".")
        return {"conversation_version": CONVERSATION_VERSION,
                "intent": "UNMATCHED", "routing": routing,
                "answer": {"direct_answer": answer, "evidence": [],
                           "counter_evidence": [], "confidence": None,
                           "confidence_reasons": [], "falsification": [],
                           "decision": ""}, "citations": []}

    # comparison questions get the dedicated comparison structure
    if operation == "comparison" and comparable:
        comp = _comparison_answer(question, r, hyp, comparable, obs_by_id)
        return {"conversation_version": CONVERSATION_VERSION,
                "intent": "COMPARISON", "routing": routing,
                "matched_hypothesis": hyp["hypothesis_id"],
                "comparison": comp,
                "citations": [c["observation_id"]
                              for c in comp["supporting_evidence"]],
                "note": "Comparison grounded in the cited historical pattern; "
                        "shared mechanism, differences, and where the analogy "
                        "breaks are stated explicitly."}

    # selective support / contradiction / falsification / implication answer
    support = _cite(hyp.get("strongest_support_ids")
                    or hyp.get("supporting_observation_ids", []), obs_by_id, 4)
    counter = _cite(hyp.get("strongest_counter_ids")
                    or hyp.get("counter_observation_ids", []), obs_by_id, 2)
    against = counter[0]["excerpt"] if counter else \
        "mainly the open evidence gaps below"
    lead = {
        "support": f"Yes — on balance the evidence supports that "
                   f"{hyp['title'].lower()} ({hyp['confidence']} confidence).",
        "contradiction": f"The strongest case against it: {against}.",
        "falsification": "It would be wrong if the falsification tests below "
                         "came back negative.",
        "implication": "The decision this most affects: "
                       + (hyp.get("decision_implications") or [""])[0],
        "agenda": "This is likely on the current leadership agenda because "
                  + (hyp.get("why_now") or "recent public signals point to it")
                  + ".",
    }
    # Total by construction. A routing layer that can name an operation the
    # answer layer cannot render is one new cue word away from an error page,
    # and the reader who finds it will have asked something perfectly ordinary.
    lead = lead.get(operation, lead["support"])

    return {
        "conversation_version": CONVERSATION_VERSION, "intent": "EXPLAINED",
        "routing": routing, "matched_hypothesis": hyp["hypothesis_id"],
        "answer": {
            "direct_answer": lead,
            "reasoning": hyp.get("reasoning", ""),
            "evidence": support,
            "counter_evidence": counter,
            "counter_note": (counter and "Genuine counter-evidence above."
                             or "No strong counter-evidence retrieved; the "
                                "evidence gaps temper confidence instead."),
            "confidence": hyp.get("confidence"),
            "confidence_reasons": hyp.get("confidence_reasons", []),
            "falsification": hyp.get("falsification_questions", []),
            "alternative_explanations": hyp.get("alternative_explanations", []),
            "decision": (hyp.get("decision_implications") or [""])[0],
        },
        "citations": [c["observation_id"] for c in support],
        "note": "Selective by design — strongest evidence only; full evidence "
                "is available in the report's source library.",
    }
