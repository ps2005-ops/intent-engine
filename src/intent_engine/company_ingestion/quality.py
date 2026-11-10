"""Deterministic executive-report quality gate.

Retrieval succeeding is not the same as the report being useful. The 2026-07
incident shipped a run that was technically COMPLETE while telling a reader
nothing about the company: filings-only evidence, legal vocabulary presented as
insight, and most sections reading "Not available".

This module scores a finished report against explicit, deterministic rules and
says whether it may be published, should be retried with targeted rediscovery,
or must be labelled limited. It NEVER edits the report, invents evidence, or
suppresses an honest gap — it only measures and decides.

No model calls. Pure functions over the composed result + retrieved documents.
"""
from __future__ import annotations

import re

from intent_engine.company_ingestion.coverage import (
    CORE_FAMILIES, assess as assess_coverage,
)

QUALITY_RULES_VERSION = "report-quality.v1"

# Outcomes
REPORT_QUALITY_PASS = "REPORT_QUALITY_PASS"
REPORT_QUALITY_RETRYABLE = "REPORT_QUALITY_RETRYABLE"
REPORT_QUALITY_LIMITED = "REPORT_QUALITY_LIMITED"
REPORT_QUALITY_FAIL = "REPORT_QUALITY_FAIL"

# The executive sections a reader judges the report by. `evidence_and_analytics`
# and `conversation` are excluded: they are supporting surfaces, not findings.
MAJOR_SECTIONS = (
    "company_understanding", "what_stood_out", "market_view",
    "possible_blind_spots", "assumptions_to_investigate",
    "executive_attention", "executive_confidence",
    "what_we_do_not_believe_yet", "leadership_questions",
    "competitors", "opportunities",
)

# Text that means "we have nothing here" — a section built only from these is
# NOT meaningfully populated, however many cards it contains.
_PLACEHOLDER_MARKERS = (
    "not available", "unavailable", "out of scope", "insufficient",
    "not determinable", "no subsystem", "dependency gap", "not yet available",
    "no supported", "cannot be determined",
)

# Vocabulary that must never appear as a quoted business insight.
_LEGAL_TOKENS = (
    "pursuant", "hereunder", "registrant", "undersigned", "exchange act",
    "incorporated by reference", "herewith", "thereunto",
)

# Internal terminology that must never reach a reader.
_INTERNAL_MARKERS = (
    "company_ingestion", "demo_fixture", "subsystem", "claim_id",
    "source_id", "candidate_id", "traceback", "dependency-gap",
)

MAX_PLACEHOLDER_SHARE = 0.40      # >40% placeholder major sections fails
MIN_FAMILIES = 3
MAX_FAMILY_DOMINANCE = 0.75


def _section_text(section: dict) -> str:
    parts = [section.get("note", "") or ""]
    for card in section.get("cards", []) or []:
        parts.append(card.get("headline", "") or "")
        parts.append(card.get("why_it_matters", "") or "")
        for claim in card.get("claims", []) or []:
            parts.append(claim.get("text", "") or "")
    return " ".join(parts).strip()


def is_meaningfully_populated(section: dict) -> bool:
    """A section counts only when it carries real, non-placeholder content."""
    cards = section.get("cards") or []
    if not cards:
        return False
    text = _section_text(section).lower()
    if not text:
        return False
    # A section whose every card is a placeholder does not count.
    real_cards = 0
    for card in cards:
        card_text = " ".join(
            [card.get("headline", "") or ""]
            + [(c.get("text", "") or "") for c in card.get("claims", []) or []]
        ).lower().strip()
        if not card_text:
            continue
        if any(marker in card_text for marker in _PLACEHOLDER_MARKERS):
            continue
        # A card that only restates evidence scope is not a finding.
        if card_text.startswith("evidence scope:"):
            continue
        real_cards += 1
    return real_cards > 0


def quoted_terms(text: str) -> list:
    return [m.lower() for m in re.findall(r'"([^"]{2,60})"', text or "")]


def user_visible_text(result: dict) -> str:
    """Only the prose a reader actually sees.

    Checks for leaked internals must run against THIS, not the raw result dict:
    the dict legitimately carries plumbing (source_refs, claim ids, subsystem
    names) that the renderer never shows as prose. Scanning the whole dict
    would flag correct internal structure as a user-facing defect.
    """
    parts = [s.get("text", "") or "" for s in result.get("overview", []) or []]
    for section in result.get("sections", []) or []:
        parts.append(section.get("title", "") or "")
        parts.append(section.get("note", "") or "")
        for limitation in section.get("limitations", []) or []:
            parts.append(str(limitation))
        for card in section.get("cards", []) or []:
            parts.append(card.get("headline", "") or "")
            parts.append(card.get("why_it_matters", "") or "")
            parts.append(card.get("alternative_explanation", "") or "")
            parts.append(card.get("question_to_investigate", "") or "")
            for claim in card.get("claims", []) or []:
                parts.append(claim.get("text", "") or "")
    for group in (result.get("evidence_library") or {}).values():
        for entry in group or []:
            if isinstance(entry, dict):
                parts.append(str(entry.get("title") or ""))
                parts.append(str(entry.get("origin") or ""))
    return " ".join(parts)


def evidence_gaps(documents: list) -> dict:
    """Pre-synthesis view of what the evidence is still missing.

    The retry loop runs on THIS rather than on a composed report, so a run
    never synthesizes twice (which would duplicate the report run) — it gathers
    evidence to sufficiency first, then composes once. The rules mirror the
    retryable rules of the full gate.
    """
    usable = [d for d in documents
              if d.get("retrieval_status") == "OK"
              and (d.get("text_content") or "").strip()]
    coverage = assess_coverage(documents)
    families = coverage.get("families", [])
    # WHAT IS MISSING BY VENUE. This is the STOPPING condition and it is
    # deliberately unchanged: it decides how many acquisition passes the run
    # makes, and loosening it would make the product fetch LESS, which is the
    # opposite of the repair.
    venue_missing = []
    if not any(d.get("source_type") in ("homepage", "about") for d in usable):
        venue_missing.append("identity")
    if not any(d.get("source_type") == "product" for d in usable):
        venue_missing.append("product")
    if not any(d.get("source_type") == "customers"
               or d.get("source_class") in ("customer_voice",
                                            "independent_reporting")
               for d in usable):
        venue_missing.append("customers")
    if not any(d.get("source_class") in ("executive_statement",
                                         "investor_material")
               or d.get("source_type") == "blog" for d in usable):
        venue_missing.append("strategy")
    if not any(d.get("source_class") == "investor_material" for d in usable):
        venue_missing.append("investor")
    sufficient = (
        not venue_missing
        and len(families) >= MIN_FAMILIES
        and coverage.get("dominant_share", 1.0) <= MAX_FAMILY_DOMINANCE)

    # WHAT IS MISSING BY ROLE, which is what the bounded retry budget should
    # be SPENT on. These were the same list, and they are not the same
    # question.
    #
    # `venue_missing` asks where a document was published; `families` (from
    # `coverage.family_of`) asks what a reader learns from it -- and that is
    # the view `readiness.assess_readiness`, the gate that decides whether a
    # report may exist at all, actually consults.
    #
    # MEASURED 2026-09-03 on Advanced Micro Devices, whose own domain timed
    # out and whose run fell back entirely to EDGAR: nine documents, five
    # families, and `family_of` correctly reading the 10-K's Item 1 Business
    # as `identity`. `venue_missing` still said ['identity', 'product'],
    # because a 10-K is not a homepage -- so the four-source retry budget was
    # about to be spent guessing `/about` and `/products` against a host that
    # had just stopped answering, to fill a role the run already had.
    #
    # The ROLES are readiness's own: identity-or-product, direction, market.
    # A role that is already covered is not hunted; a role that is genuinely
    # empty is hunted first.
    covered = set(families)
    role_missing = []
    if not covered & {"identity", "product"}:
        role_missing += ["identity", "product"]
    if not covered & {"customers", "independent", "commercial"}:
        role_missing.append("customers")
    if not covered & {"strategy", "investor"}:
        role_missing += ["strategy", "investor"]
    # Anything the venue view wants that the role view has NOT ruled out
    # stays on the list, after the blocking roles. Nothing that used to be
    # attempted stops being attempted -- the budget is simply spent on the
    # gaps that can still refuse a report, in that order.
    for family in venue_missing:
        if family not in role_missing:
            role_missing.append(family)
    return {"missing_families": role_missing, "families": families,
            "venue_missing": venue_missing,
            "document_count": len(usable), "sufficient": sufficient,
            "dominant_share": coverage.get("dominant_share", 0.0)}


def _unspecific_claims(result: dict, documents: list, *,
                       company_name: str = "") -> list:
    """Strategic claims the specificity gate rejects outright.

    Only outright REJECTs are surfaced here. Downgrades (a claim that merely
    survives substitution) are a matter of degree and are handled by ranking,
    not by refusing to publish — treating them as hard failures would block
    honest, if unremarkable, findings.
    """
    report = result.get("strategic_report")
    if not report:
        return []
    from intent_engine.strategic_intelligence.specificity import (
        REJECT, distinctive_terms, evaluate_claim,
    )
    terms = distinctive_terms(documents, company=company_name)
    statements = []
    for hypothesis in report.get("hypotheses", []) or []:
        statements.append(hypothesis.get("statement")
                          or hypothesis.get("title", ""))
    for surprise in report.get("surprises", []) or []:
        statements.append(surprise.get("finding", ""))
    for opportunity in report.get("opportunities", []) or []:
        statements.append(opportunity.get("statement", ""))
    thesis = report.get("thesis") or {}
    statements.append(thesis.get("view", ""))

    rejected = []
    for statement in statements:
        if not (statement or "").strip():
            continue
        verdict = evaluate_claim(statement, company=company_name,
                                 evidence_terms=terms)
        if verdict["verdict"] == REJECT:
            reason = next((f["message"] for f in verdict["findings"]
                           if f["verdict"] == REJECT), "")
            rejected.append(f"{statement[:60]} — {reason}")
    return rejected


def assess(result: dict, documents: list, *, company_name: str = "") -> dict:
    """Score a composed report. Returns a diagnostic dict with `outcome`,
    `failed_rules`, `metrics`, and `missing_families` (what a retry should go
    looking for). Deterministic and side-effect free."""
    sections = result.get("sections", []) or []
    by_kind = {s.get("kind"): s for s in sections}
    visible = user_visible_text(result)
    flat = visible.lower()
    coverage = result.get("coverage") or assess_coverage(documents)

    # The denominator is every EXPECTED major section, not merely the ones
    # that happen to be present. Scoring against present sections meant a
    # report that dropped ten of its eleven sections scored populated_share
    # 1.0 — identical to a complete report — because both the numerator and
    # the denominator shrank together. Absent sections are now counted as
    # unpopulated, which is what they are to a reader.
    present = [by_kind[k] for k in MAJOR_SECTIONS if k in by_kind]
    missing_sections = [k for k in MAJOR_SECTIONS if k not in by_kind]
    populated = [s for s in present if is_meaningfully_populated(s)]
    expected = len(MAJOR_SECTIONS)
    placeholder_share = 1.0 - (len(populated) / expected)

    # --- evidence quality ---------------------------------------------------
    families = coverage.get("families", [])
    usable_docs = [d for d in documents
                   if d.get("retrieval_status") == "OK"
                   and (d.get("text_content") or "").strip()]

    # --- report usefulness --------------------------------------------------
    overview_text = " ".join(s.get("text", "")
                             for s in result.get("overview", []) or [])
    has_description = bool(
        re.search(r"(appears to sell|company identity|directly observed)",
                  overview_text, re.I))
    has_product = any(d.get("source_type") == "product" for d in usable_docs)
    has_customer = any(d.get("source_type") == "customers"
                       or d.get("source_class") in ("customer_voice",
                                                    "independent_reporting")
                       for d in usable_docs)
    has_strategy = any(d.get("source_class") in ("executive_statement",
                                                 "investor_material")
                       or d.get("source_type") == "blog"
                       for d in usable_docs)

    # legal boilerplate presented as insight = a legal token inside quotes in
    # the prose the reader actually sees
    legal_as_insight = sorted(
        {t for t in quoted_terms(visible)
         if any(token == t or token in t for token in _LEGAL_TOKENS)})

    opaque_ids = bool(re.search(r"cand-[0-9a-f]{6,}", visible))
    internal_leak = sorted({m for m in _INTERNAL_MARKERS if m in flat})

    # Claims that are not about this company. More evidence cannot repair
    # these, so they are a HARD rule rather than a retryable one: "SEC 6-K is
    # shifting where demand is captured" does not become true with a sixth
    # source. It has to not be published.
    unspecific = _unspecific_claims(result, documents,
                                    company_name=company_name)

    metrics = {
        "successful_sources": len(usable_docs),
        "source_families": len(families),
        "families": families,
        "family_dominance": coverage.get("dominant_share", 0.0),
        "major_sections": expected,
        "present_sections": len(present),
        "missing_sections": missing_sections,
        "populated_sections": len(populated),
        "populated_share": round(len(populated) / expected, 3),
        "placeholder_share": round(placeholder_share, 3),
        "has_company_description": has_description,
        "has_product_evidence": has_product,
        "has_customer_evidence": has_customer,
        "has_strategy_evidence": has_strategy,
        "legal_as_insight": legal_as_insight,
        "opaque_ids": opaque_ids,
        "internal_leak": internal_leak,
        "unspecific_claims": unspecific,
        "rules_version": QUALITY_RULES_VERSION,
    }

    # --- rules --------------------------------------------------------------
    # HARD rules: publishing would be misleading or embarrassing.
    hard: list = []
    if legal_as_insight:
        hard.append(f"legal boilerplate presented as insight: "
                    f"{', '.join(legal_as_insight[:4])}")
    if opaque_ids:
        hard.append("opaque internal candidate IDs appear in the report")
    if internal_leak:
        hard.append(f"internal implementation terms exposed: "
                    f"{', '.join(internal_leak[:3])}")
    if unspecific:
        hard.append(f"claim is not about this company: "
                    f"{'; '.join(unspecific[:3])}")

    # RETRYABLE rules: more/better evidence would plausibly fix them.
    retryable: list = []
    if not has_description:
        retryable.append("the report does not clearly explain what the "
                         "company does")
    if not has_product:
        retryable.append("no official product/platform/documentation evidence")
    if not has_customer:
        retryable.append("no customer or use-case evidence")
    if not has_strategy:
        retryable.append("no strategy, newsroom, or financial evidence")
    if len(families) < MIN_FAMILIES:
        retryable.append(f"only {len(families)} evidence family/families; "
                         f"at least {MIN_FAMILIES} are needed")
    if coverage.get("dominant_share", 0) > MAX_FAMILY_DOMINANCE:
        retryable.append(
            f"one source family supplies "
            f"{int(coverage['dominant_share'] * 100)}% of the evidence")
    if placeholder_share > MAX_PLACEHOLDER_SHARE:
        retryable.append(
            f"{int(placeholder_share * 100)}% of major sections are "
            "placeholders")

    missing_families = [f for f in CORE_FAMILIES if f not in families]

    if hard:
        outcome = REPORT_QUALITY_FAIL
    elif retryable:
        outcome = REPORT_QUALITY_RETRYABLE
    else:
        outcome = REPORT_QUALITY_PASS

    return {"outcome": outcome, "failed_rules": hard + retryable,
            "hard_rules": hard, "retryable_rules": retryable,
            "metrics": metrics, "missing_families": missing_families,
            "rules_version": QUALITY_RULES_VERSION}


def downgrade_to_limited(assessment: dict) -> dict:
    """After the retry budget is spent, a still-imperfect report is published
    as explicitly LIMITED rather than presented as complete."""
    out = dict(assessment)
    if out["outcome"] == REPORT_QUALITY_RETRYABLE:
        out["outcome"] = REPORT_QUALITY_LIMITED
    return out
