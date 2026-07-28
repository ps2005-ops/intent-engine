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

    # no strong evidence at all — only titles/marketing — is not strategic
    strong_obs = [o for o in report.observations
                  if not getattr(o, "weak", False)]
    if report.observations and not strong_obs:
        findings.append(_f("evidence_titles_only", "no strong strategic "
                           "observation was extracted; only weak page-title / "
                           "marketing snippets"))

    # hypothesis-LEVEL coverage: the strongest hypothesis must actually have
    # curated strong support (not merely a source-class label being present).
    top = report.hypotheses[0] if report.hypotheses else None
    hyp_coverage_ok = bool(top and getattr(top, "strongest_support_ids", ())
                           and (top.counter_observation_ids or top.evidence_gaps))
    if report.hypotheses and not hyp_coverage_ok:
        findings.append(_f("weak_hypothesis_coverage", "the leading hypothesis "
                           "lacks curated strong support with a counterpoint "
                           "or explicit evidence gap"))
    # temporal coverage: a current view needs at least some dated evidence
    temporal_ok = bool(report.timeline)
    if report.hypotheses and not temporal_ok:
        findings.append(_f("no_temporal_coverage", "no dated evidence, so "
                           "'what changed' and timeliness cannot be assessed",
                           "warn"))

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
    elif not hyps or any(x["code"] in ("evidence_ids_only",
                                       "evidence_titles_only")
                         for x in findings) or len(empty) > 1:
        status = FAILED if not hyps else INSUFFICIENT
    elif len(hyps) < 3 or not _thesis_is_strategic(report.thesis) \
            or not hyp_coverage_ok:
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


def executive_insight_quality(report, documents=None) -> tuple:
    """Reject/downgrade insights that merely restate positioning, lack a
    mechanism/decision, or could apply to any company. Returns (ok, findings).

    Two layers, deliberately. `insights.passes_specificity` is a fixed
    vocabulary check written while looking at one company, so it certifies
    sentences shaped like that company's and has nothing to say about a
    conglomerate or a chip maker. When `documents` are supplied, the stronger
    gate in `specificity` runs as well: it grounds "specific" in THIS run's own
    evidence, which is the only place that word can be defined, and it catches
    the shapes a word list structurally cannot — a filing acting as a business
    subject, movement with no destination, advice with no evidence.
    """
    from intent_engine.strategic_intelligence.insights import (
        is_generic_insight, passes_specificity,
    )
    r = report.as_dict() if hasattr(report, "as_dict") else report
    company = r.get("company_name", "")
    findings = []
    for s in r.get("surprises", []):
        if is_generic_insight(s["finding"]) or \
                not passes_specificity(s["finding"], company):
            findings.append(_f("generic_surprise",
                               f"surprise reads generically: {s['finding'][:60]}",
                               "warn"))
    for o in r.get("opportunities", []):
        if not passes_specificity(o["statement"], company):
            findings.append(_f("generic_opportunity", "opportunity is not "
                               "company-specific", "warn"))
    for h in r.get("hypotheses", []):
        if is_generic_insight(h.get("statement", "")):
            findings.append(_f("generic_hypothesis", "hypothesis restates "
                               "generic positioning", "warn"))
    findings.extend(_evidence_grounded_findings(r, company, documents))
    return (not findings, findings)


def _evidence_grounded_findings(r, company, documents) -> list:
    """The substitution test, run against the company's own evidence."""
    if documents is None:
        return []
    from intent_engine.strategic_intelligence.specificity import (
        REJECT, distinctive_terms, evaluate_claim,
    )
    terms = distinctive_terms(documents, company=company)
    findings, seen = [], []
    sections = (
        ("surprise", [s.get("finding", "") for s in r.get("surprises", [])]),
        ("opportunity", [o.get("statement", "")
                         for o in r.get("opportunities", [])]),
        ("hypothesis", [h.get("statement", "")
                        for h in r.get("hypotheses", [])]),
    )
    for label, statements in sections:
        for statement in statements:
            if not statement:
                continue
            result = evaluate_claim(statement, company=company,
                                    evidence_terms=terms,
                                    seen_statements=list(seen))
            seen.append(statement)
            for finding in result["findings"]:
                findings.append(_f(
                    f"{label}_{finding['code']}",
                    f"{label}: {finding['message']}",
                    "block" if finding["verdict"] == REJECT else "warn"))
    return findings


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
