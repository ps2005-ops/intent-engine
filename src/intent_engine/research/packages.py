"""Evidence packages, coverage, budget accounting, research debt, and
uncertainty-labelled conclusions (T019).

Two separations matter here:

  * COVERAGE over counts. "22 evidence items" tells the founder nothing;
    "1 covered, 1 partially covered, 1 contradicted, 2 not investigated"
    tells them exactly where the gaps are.
  * STRUCTURED conclusion (immutable, machine-checkable) is separate from
    NARRATIVE (regenerable prose). The narrative may be rewritten forever;
    the structured conclusion is the record.
"""
from __future__ import annotations

from intent_engine.research.graph import rank_evidence, stance_for_claim
from intent_engine.research.records import (
    DEBT_KINDS, QUALITY_HIGH, STANCE_CONTRADICTED, STANCE_INSUFFICIENT,
    STANCE_MIXED, STANCE_NOT_INVESTIGATED, STANCE_SUPPORTED, STANCE_UNKNOWN,
    UNCERTAINTY_CONFLICTING, UNCERTAINTY_KNOWN, UNCERTAINTY_LIKELY,
    UNCERTAINTY_SPECULATIVE, UNCERTAINTY_UNKNOWN, ResearchError,
    assert_research_language,
)

PACKAGE_VERSION = "evidence_package.v1"
CONCLUSION_VERSION = "research_conclusion.v1"


def coverage_report(index, plan: dict, claim_map: dict) -> dict:
    """Improvement 4: per-question coverage, not a bare item count.

    `claim_map` maps each plan question to the claim keys investigated for
    it. A question absent from the map was NEVER INVESTIGATED — which is
    different from investigated-and-found-nothing.
    """
    requirements = plan.get("evidence_requirements", {})
    per_question, buckets = {}, {"covered": [], "partially_covered": [],
                                 "contradicted": [], "not_covered": [],
                                 "not_investigated": []}
    for question in plan.get("questions", []):
        keys = claim_map.get(question, [])
        investigated = question in claim_map
        stances = [stance_for_claim(index, key, requirements=requirements,
                                    investigated=investigated)
                   for key in keys] or [
            stance_for_claim(index, f"none:{question}",
                             requirements=requirements,
                             investigated=investigated)]
        labels = [s["stance"] for s in stances]
        if not investigated:
            bucket = "not_investigated"
        elif STANCE_MIXED in labels or STANCE_CONTRADICTED in labels:
            bucket = "contradicted"
        elif all(l == STANCE_SUPPORTED for l in labels):
            bucket = "covered"
        elif STANCE_SUPPORTED in labels:
            bucket = "partially_covered"
        elif all(l in (STANCE_UNKNOWN, STANCE_NOT_INVESTIGATED)
                 for l in labels):
            bucket = "not_covered"
        else:
            bucket = "partially_covered" if STANCE_INSUFFICIENT in labels \
                else "not_covered"
        buckets[bucket].append(question)
        per_question[question] = {"bucket": bucket, "stances": stances}
    return {"per_question": per_question, "buckets": buckets,
            "totals": {k: len(v) for k, v in buckets.items()},
            "note": ("NOT INVESTIGATED means nobody searched; NOT COVERED "
                     "means somebody searched and found nothing")}


def budget_report(session_rows, plan: dict) -> dict:
    """Improvement 9: session accounting AgentOS will later schedule on."""
    budget = plan.get("budget", {})
    used = {"sources_registered": 0, "sources_rejected": 0,
            "evidence_indexed": 0, "evidence_rejected": 0, "model_calls": 0,
            "extraction_failures": 0}
    for row in session_rows:
        et = row.event_type
        if et == "research.source_registered":
            used["sources_registered"] += 1
        elif et == "research.source_rejected":
            used["sources_rejected"] += 1
        elif et == "research.evidence_indexed":
            used["evidence_indexed"] += 1
        elif et == "research.evidence_rejected":
            used["evidence_rejected"] += 1
        elif et == "research.extraction_failed":
            used["extraction_failures"] += 1
        if (row.provenance or {}).get("model_version"):
            used["model_calls"] += 1
    limits = {"max_sources": budget.get("max_sources"),
              "max_model_calls": budget.get("max_model_calls")}
    remaining = {
        "sources": (None if limits["max_sources"] is None
                    else limits["max_sources"] - used["sources_registered"]),
        "model_calls": (None if limits["max_model_calls"] is None
                        else limits["max_model_calls"] - used["model_calls"]),
    }
    return {"used": used, "limits": limits, "remaining": remaining,
            "exhausted": any(v is not None and v <= 0
                             for v in remaining.values())}


def research_debt(index, coverage: dict, plan: dict) -> list:
    """Improvement 13: what this package still needs, in a form Growth and
    the PM Agent can consume directly."""
    debt = []
    for question in coverage["buckets"]["not_investigated"]:
        debt.append({"kind": "need_newer_evidence", "question": question,
                     "detail": "not searched in this session"})
    for question in coverage["buckets"]["not_covered"]:
        debt.append({"kind": "need_primary_source", "question": question,
                     "detail": "searched; no source addresses it"})
    for question in coverage["buckets"]["contradicted"]:
        debt.append({"kind": "need_experiment", "question": question,
                     "detail": "conflicting evidence the sources cannot settle"})
    for question, detail in coverage["per_question"].items():
        for stance in detail["stances"]:
            if stance["stance"] == STANCE_INSUFFICIENT:
                debt.append({"kind": "need_independent_corroboration",
                             "question": question,
                             "detail": "independent corroboration below the "
                                       "plan's minimum"})
            if stance.get("independent_support", 0) == 1:
                debt.append({"kind": "need_replication", "question": question,
                             "detail": "a single independent source"})
    for item in debt:
        if item["kind"] not in DEBT_KINDS:
            raise ResearchError(f"unknown debt kind: {item['kind']!r}")
    seen, unique = set(), []
    for item in debt:
        key = (item["kind"], item["question"])
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def assemble_package(index, plan: dict, claim_map: dict, session_rows,
                     *, as_of: str) -> dict:
    """The reviewable artifact. Contradictions lead; prose does not."""
    index.assert_invariants()
    coverage = coverage_report(index, plan, claim_map)
    usable = index.usable_evidence()
    ranked = rank_evidence(index, usable)
    accepted_sources = [s for s in index.sources.values()
                        if s["source_id"] not in index.retired_sources]
    stale = [s["source_id"] for s in accepted_sources
             if s.get("freshness", {}).get("freshness") == "STALE"]
    unverified = [s["source_id"] for s in accepted_sources
                  if s.get("verified") is False]
    oldest = min((s.get("freshness", {}).get("age_days") or 0
                  for s in accepted_sources), default=0)

    return {
        "package_version": PACKAGE_VERSION,
        "index_version": index.index_version,
        "as_of": as_of,
        "coverage": coverage,
        "contradictions": [dict(c) for c in index.contradictions],
        "ranked_evidence": [{"evidence_id": e["evidence_id"],
                             "claim_key": e.get("claim_key"),
                             "evidence_class": e.get("evidence_class"),
                             "rank_score": e["rank_score"],
                             "rank_inputs": e["rank_inputs"]}
                            for e in ranked],
        "sources": {"accepted": sorted(s["source_id"] for s in accepted_sources),
                    "retired": sorted(index.retired_sources),
                    "unverified": sorted(unverified),
                    "stale": sorted(stale)},
        "freshness": {"oldest_load_bearing_age_days": oldest,
                      "stale_sources": len(stale)},
        "budget": budget_report(session_rows, plan),
        "research_debt": research_debt(index, coverage, plan),
        "limitations": [
            "every claim here resolves to a registered source; nothing was "
            "written from model memory",
            "corroboration counts INDEPENDENT sources, so outlets repeating "
            "one origin count once",
            "stale sources are labelled, not removed; retired sources are "
            "excluded entirely",
        ],
    }


def draft_conclusion(package: dict, *, question: str) -> dict:
    """Structured conclusion (immutable) — the narrative is separate.

    Uncertainty is computed from the package, never asserted.
    """
    detail = package["coverage"]["per_question"].get(question)
    if detail is None:
        raise ResearchError(f"question not in this package: {question!r}")
    stances = detail["stances"]
    labels = [s["stance"] for s in stances]

    supported = [e for s in stances for e in s.get("supporting", [])]
    contradicted = [e for s in stances for e in s.get("contradicting", [])]

    if STANCE_NOT_INVESTIGATED in labels:
        uncertainty = UNCERTAINTY_UNKNOWN
        basis = "this question was never investigated"
    elif STANCE_MIXED in labels or STANCE_CONTRADICTED in labels:
        uncertainty = UNCERTAINTY_CONFLICTING
        basis = "conflicting evidence that the sources cannot settle"
    elif STANCE_UNKNOWN in labels and not supported:
        uncertainty = UNCERTAINTY_UNKNOWN
        basis = "no source addresses this question"
    elif STANCE_SUPPORTED in labels:
        strong = max((s.get("independent_support", 0) for s in stances),
                     default=0)
        high_quality = any(
            r["rank_inputs"]["source_quality"] == QUALITY_HIGH
            and r["rank_inputs"]["freshness"] == "FRESH"
            for r in package["ranked_evidence"])
        if strong >= 3 and high_quality:
            uncertainty, basis = UNCERTAINTY_KNOWN, (
                "multiple independent, high-quality, fresh sources converge "
                "with no unresolved contradiction")
        else:
            uncertainty, basis = UNCERTAINTY_LIKELY, (
                "converging evidence with a stated gap in independence, "
                "quality, or freshness")
    else:
        uncertainty, basis = UNCERTAINTY_SPECULATIVE, (
            "thin or indirect evidence only")

    not_addressed = (package["coverage"]["buckets"]["not_covered"]
                     + package["coverage"]["buckets"]["not_investigated"])
    return {
        "conclusion_version": CONCLUSION_VERSION,
        "question": question,
        "uncertainty_label": uncertainty,
        "basis": basis,
        "supported_by": sorted(set(supported)),
        "contradicted_by": sorted(set(contradicted)),
        "not_addressed": sorted(set(not_addressed)),
        "conflict_reasons": sorted({s.get("conflict_reason")
                                    for s in stances
                                    if s.get("conflict_reason")}),
        "research_debt": package["research_debt"],
        "what_would_change_this": _what_would_change(uncertainty, stances),
        "structured": True,
    }


def _what_would_change(uncertainty: str, stances: list) -> list:
    if uncertainty == UNCERTAINTY_CONFLICTING:
        return ["a primary source using one stated population and "
                "methodology that both sides accept",
                "a registered experiment that separates the two accounts"]
    if uncertainty == UNCERTAINTY_UNKNOWN:
        return ["any source that directly addresses the question",
                "a primary measurement from our own data"]
    if uncertainty == UNCERTAINTY_SPECULATIVE:
        return ["one independent high-quality source",
                "replication from a second origin"]
    return ["a contradicting high-quality independent source",
            "newer evidence if the current sources age past their policy"]


def render_narrative(conclusion: dict) -> str:
    """Regenerable prose. NEVER the record — the structured conclusion is.

    Deliberately templated rather than model-written in V1: a narrative
    that can drift from its structured source is the exact failure this
    subsystem exists to prevent.
    """
    label = conclusion["uncertainty_label"]
    opener = {
        UNCERTAINTY_KNOWN: "Current evidence suggests, consistently:",
        UNCERTAINTY_LIKELY: "Current evidence suggests, with a stated gap:",
        UNCERTAINTY_SPECULATIVE: "Limited evidence only:",
        UNCERTAINTY_CONFLICTING: "Conflicting evidence:",
        UNCERTAINTY_UNKNOWN: "Insufficient evidence:",
    }[label]
    lines = [f"{label} — {conclusion['question']}", "", opener,
             f"  {conclusion['basis']}.", "",
             f"Supported by: {len(conclusion['supported_by'])} evidence item(s)",
             f"Contradicted by: {len(conclusion['contradicted_by'])} evidence item(s)"]
    if conclusion["conflict_reasons"]:
        lines.append("Conflict attributed to: "
                     + ", ".join(conclusion["conflict_reasons"]))
    if conclusion["not_addressed"]:
        lines.append("No source addresses: "
                     + "; ".join(conclusion["not_addressed"]))
    lines += ["", "What would change this:"]
    lines += [f"  - {item}" for item in conclusion["what_would_change_this"]]
    if conclusion["research_debt"]:
        lines += ["", "Research debt:"]
        lines += [f"  - {d['kind']}: {d['detail']}"
                  for d in conclusion["research_debt"]]
    text = "\n".join(lines)
    assert_research_language(text, where="narrative")
    return text
