"""V1.2 strategic report quality gates.

A report is never silently emitted as a hollow "COMPLETE". The gate downgrades
to an explicit status and records why. It also carries a low-value detector
that captures the previous website-summarizer failure mode as a hard reject.
"""
from __future__ import annotations

import re

COMPLETE = "COMPLETE"
PARTIAL = "PARTIAL_STRATEGIC_EVIDENCE"
INSUFFICIENT = "INSUFFICIENT_STRATEGIC_EVIDENCE"
FAILED = "FAILED"
STRATEGIC_STATUSES = (COMPLETE, PARTIAL, INSUFFICIENT, FAILED)

_EXTERNAL_CLASSES = ("executive_statement", "investor_material",
                     "customer_voice", "competitor", "independent_reporting")
# a genuinely outside vantage point (not the company's own publishing). A
# COMPLETE report needs cross-source corroboration from at least one of these.
_INDEPENDENT_CLASSES = ("independent_reporting", "customer_voice", "competitor")

# transition/strategy cue words a real thesis must contain (not a description)
_STRATEGIC_CUES = ("appears to", "moving", "shift", "transition", "toward",
                   "becoming", "tension", "hypothesis", "repositioning",
                   "expansion")

# markers of the OLD failure mode (website-summarizer output)
_LOW_VALUE_MARKERS = (
    "most repeated words", "most frequent", "term frequency", "top terms",
    "word frequency", "the company talks about", "the website mentions",
    "uses growth language", "mentions customers", "mentions commerce",
    "visible audience", "out of scope", "not available",
)


def _f(code, message, severity="block"):
    return {"code": code, "message": message, "severity": severity}


def _thesis_is_strategic(thesis: dict) -> bool:
    view = (thesis or {}).get("view", "")
    if not view.strip() or not (thesis or {}).get("transition", "").strip():
        return False
    if not (thesis or {}).get("why_care", "").strip():
        return False
    lowered = view.lower()
    return any(cue in lowered for cue in _STRATEGIC_CUES)


def _empty_key_sections(report) -> list:
    empty = []
    if not report.hypotheses:
        empty.append("strategic_hypotheses")
    if not report.patterns:
        empty.append("comparable_patterns")
    if not report.blind_spots:
        empty.append("blind_spots")
    if not report.questions:
        empty.append("leadership_questions")
    if not report.shifts:
        empty.append("what_changed")
    if not report.decision_implications:
        empty.append("decision_implications")
    return empty


def evaluate_report(report) -> tuple:
    """Return (status, findings). ``findings`` is a list of {code, message,
    severity} dicts explaining every downgrade."""
    findings = []
    hyps = report.hypotheses

    if not _thesis_is_strategic(report.thesis):
        findings.append(_f("thesis_generic", "executive thesis is a generic "
                           "company description, not a strategic view"))
    if len(hyps) < 3:
        findings.append(_f("too_few_hypotheses",
                           f"only {len(hyps)} strategic hypotheses (need >= 3)"))
    for h in hyps:
        if not h.reasoning.strip():
            findings.append(_f("no_reasoning",
                               f"{h.hypothesis_id} lacks a reasoning chain"))
        if not h.counter_observation_ids and not h.evidence_gaps:
            findings.append(_f("no_counter_or_gap", f"{h.hypothesis_id} has "
                               "neither counter-evidence nor an evidence gap"))
        if not h.decision_implications:
            findings.append(_f("no_implication",
                               f"{h.hypothesis_id} has no decision implication"))
        if not h.falsification_questions:
            findings.append(_f("no_falsification",
                               f"{h.hypothesis_id} has no falsification test"))
    for q in report.questions:
        if not q.why_it_matters.strip():
            findings.append(_f("question_no_why", "a leadership question does "
                               "not explain why it matters"))
        if not q.decision_affected.strip():
            findings.append(_f("question_no_decision", "a leadership question "
                               "names no decision it affects"))
    for p in report.patterns:
        if not p.mechanism.strip():
            findings.append(_f("pattern_no_mechanism", f"comparable {p.name} "
                               "has no comparison mechanism"))
    # evidence must be human-readable, not artifact ids only
    thin = [o for o in report.observations if not (o.excerpt or o.text).strip()]
    if thin:
        findings.append(_f("evidence_ids_only", "an evidence view exposes only "
                           "identifiers with no human-readable excerpt"))
    # unsupported private/internal claims are refused
    internal = [o for o in report.observations
                if getattr(o, "source_class", "") not in
                ("company_owned",) + _EXTERNAL_CLASSES + ("historical_pattern",)]
    if internal:
        findings.append(_f("unsupported_internal", "an observation claims "
                           "internal/private knowledge with no public source",
                           "fatal"))
    empty = _empty_key_sections(report)
    if len(empty) > 1:
        findings.append(_f("too_many_empty_sections",
                           "empty key sections: " + ", ".join(empty)))

    external = [c for c in _EXTERNAL_CLASSES
                if report.source_class_coverage.get(c)]
    independent = [c for c in _INDEPENDENT_CLASSES
                   if report.source_class_coverage.get(c)]
    active_classes = [c for c, n in report.source_class_coverage.items() if n]
    company_only = not external

    blocking = [x for x in findings if x["severity"] in ("block", "fatal")]
    accepted = report.limited_scope_accepted

    if any(x["code"] == "unsupported_internal" for x in findings):
        status = FAILED
    elif not hyps or any(x["code"] == "evidence_ids_only" for x in findings) \
            or len(empty) > 1:
        status = FAILED if not hyps else INSUFFICIENT
    elif len(hyps) < 3 or not _thesis_is_strategic(report.thesis):
        status = INSUFFICIENT
    elif company_only and not accepted:
        findings.append(_f("single_source_class", "broad strategic claims rest "
                           "on company-owned pages only; independent "
                           "corroboration is missing", "warn"))
        status = PARTIAL
    elif not independent and not accepted:
        # exec/investor pages are still the company's own publishing; without an
        # independent, customer, or competitor source there is no cross-source
        # check, so this cannot be a full COMPLETE.
        findings.append(_f("no_independent_source", "evidence is all "
                           "company-published (owned/executive/investor); an "
                           "independent, customer, or competitor source is "
                           "needed to corroborate or challenge it", "warn"))
        status = PARTIAL
    elif len(active_classes) <= 1 and not accepted:
        status = PARTIAL
    elif blocking:
        status = PARTIAL
    else:
        status = COMPLETE
    return status, findings


def looks_low_value(payload) -> tuple:
    """Detect the previous website-summarizer failure mode. ``payload`` may be
    a rendered HTML string or any object with text. Returns (bool, reasons)."""
    text = payload if isinstance(payload, str) else str(payload)
    lowered = text.lower()
    reasons = []
    for marker in _LOW_VALUE_MARKERS:
        if marker in lowered:
            reasons.append(f"contains low-value marker: {marker!r}")
    # a block of bare artifact/replay ids presented as the evidence
    if re.search(r"(artifact|replay)[-_ ]?id", lowered) and \
            "interpretation" not in lowered and "reasoning" not in lowered:
        reasons.append("evidence is artifact/replay ids without interpretation")
    return (bool(reasons), reasons)
