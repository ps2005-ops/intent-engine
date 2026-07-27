"""Targeted rediscovery after a failed report-quality gate.

A weak report is usually an EVIDENCE problem, not a synthesis problem: the run
never retrieved a product page, or any customer story, or anything about
strategy. Publishing "Not available" in that situation is honest but useless
when the missing evidence was reachable all along.

This module decides, deterministically, which additional candidates to approve
for a second (and at most a third) pass, based on exactly which evidence
families the quality gate found missing. It is bounded, never repeats a URL
that already failed, and never invents evidence.
"""
from __future__ import annotations

MAX_RETRY_PASSES = 2              # at most two ADDITIONAL discovery passes
MAX_NEW_SOURCES_PER_PASS = 4      # bounded extra retrievals per pass

# Which candidate shapes satisfy a missing evidence family. Ordered: the
# earlier a matcher appears, the more directly it supplies that family.
FAMILY_TARGETS = {
    "product": (
        lambda c: c["source_type"] == "product",
        lambda c: "docs" in c["url"].lower() or "developer" in c["url"].lower(),
        lambda c: "product" in c["url"].lower()
        or "platform" in c["url"].lower(),
    ),
    "customers": (
        lambda c: c["source_type"] == "customers",
        lambda c: any(k in c["url"].lower() for k in
                      ("customer", "case-stud", "partner", "success",
                       "stories")),
    ),
    "strategy": (
        lambda c: c.get("source_class") == "executive_statement",
        lambda c: c["source_type"] == "blog",
        lambda c: any(k in c["url"].lower() for k in
                      ("news", "press", "blog", "newsroom")),
    ),
    "investor": (
        lambda c: c.get("source_class") == "investor_material",
        lambda c: any(k in c["url"].lower() for k in
                      ("investor", "earnings", "shareholder", "sec.gov")),
    ),
    "identity": (
        lambda c: c["source_type"] in ("homepage", "about"),
        lambda c: any(k in c["url"].lower() for k in
                      ("about", "company", "leadership", "team")),
    ),
    "independent": (
        lambda c: c.get("source_class") in ("customer_voice",
                                            "independent_reporting",
                                            "competitor"),
    ),
}


def plan_retry(*, missing_families, candidates, already_approved,
               failed_urls, limit=MAX_NEW_SOURCES_PER_PASS) -> list:
    """Choose additional candidate ids that could supply the missing families.

    Never re-approves an already-approved candidate and never retries a URL
    that already failed — a permanent failure (403, 404, policy block) does not
    become retrievable by asking again. Deterministic: ordered by family
    priority, then by matcher specificity, then by URL.
    """
    approved = set(already_approved or ())
    failed = set(failed_urls or ())
    chosen: list = []
    seen = set(approved)

    for family in missing_families:
        matchers = FAMILY_TARGETS.get(family)
        if not matchers:
            continue
        for matcher in matchers:
            if len(chosen) >= limit:
                break
            # Prefer publisher-verified (sitemap) URLs over guessed known
            # paths: a guess is frequently a 404, and spending a bounded retry
            # budget on guesses is exactly how a gap stays unfilled.
            pool = sorted(
                (c for c in candidates
                 if c["candidate_id"] not in seen
                 and c["url"] not in failed
                 and matcher(c)),
                key=lambda c: (0 if "sitemap" in c.get("why_relevant", "")
                               else 1, len(c["url"]), c["url"]))
            for candidate in pool:
                chosen.append(candidate["candidate_id"])
                seen.add(candidate["candidate_id"])
                break                    # one per matcher, keep passes small
        if len(chosen) >= limit:
            break
    return chosen[:limit]


def retry_reason(assessment: dict) -> str:
    """A short, recordable explanation of why a retry pass happened."""
    rules = assessment.get("retryable_rules") or assessment.get(
        "failed_rules") or []
    return "; ".join(rules[:3]) or "report quality below threshold"
