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

#: The company's own annual report. `coverage.family_of` reads a 10-K as
#: `identity` -- Item 1. Business is the company's own account of what it is
#: and what it sells -- which is precisely the role a homepage and a product
#: page would have supplied.
_ANNUAL_FORMS = ("10-K", "10-K/A", "20-F", "20-F/A", "40-F")


def _subject_annual_report(candidate) -> bool:
    """The subject's OWN annual filing, by form.

    `investor_material` is the class the EDGAR adapter gives the subject's own
    filings; a third party's filing naming the subject is
    `independent_reporting` or `competitor`, so this cannot pick up someone
    else's annual report and call it the subject's identity.
    """
    if candidate.get("source_class") != "investor_material":
        return False
    return str(candidate.get("form") or "").upper().strip() in _ANNUAL_FORMS

# Which candidate shapes satisfy a missing evidence family. Ordered: the
# earlier a matcher appears, the more directly it supplies that family.
FAMILY_TARGETS = {
    "product": (
        lambda c: c["source_type"] == "product",
        # THE ROLE-PRESERVING FALLBACK when the company's own site refuses.
        # See `identity` below: the annual report describes the products.
        _subject_annual_report,
        lambda c: "docs" in c["url"].lower() or "developer" in c["url"].lower(),
        lambda c: "product" in c["url"].lower()
        or "platform" in c["url"].lower(),
    ),
    "customers": (
        lambda c: c["source_type"] == "customers",
        # AN ATTESTED THIRD PARTY, BEFORE A GUESSED COMPANY PAGE.
        #
        # The `independent` entry below is the only matcher that can select a
        # filing by ANOTHER registrant naming the subject -- and it is
        # unreachable: `quality.evidence_gaps` emits only identity, product,
        # customers, strategy and investor, never "independent". So whenever
        # the market/customer role was missing, the planner hunted for
        # `/customers`, `/case-studies` and `/partners` on the subject's own
        # domain -- guesses, and 404s for every company that is not a SaaS
        # vendor -- while an EDGAR full-text hit naming the subject sat in the
        # candidate list and could not be chosen by any code path.
        #
        # MEASURED 2026-09-03: `market_source` was the single most common
        # unmet readiness check (3 of 4 sub-threshold companies), and the only
        # other supplier of that role is three review-site URLs built by
        # slugifying the company name, which answered 403 on 29 of 29
        # attempts across the probe cohort.
        #
        # This ADDS a way to fill the role. It removes no matcher, admits no
        # document that the relevance and ownership gates would not admit
        # anyway, and keeps the established order: attested beats guessed.
        lambda c: c.get("source_class") in ("customer_voice",
                                            "independent_reporting",
                                            "competitor"),
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
        # WHEN THE COMPANY'S OWN SITE WILL NOT ANSWER, THE REGULATOR STILL
        # HOLDS ITS ACCOUNT OF ITSELF.
        #
        # Every matcher above and below this line looks for a page on the
        # subject's own domain -- /about, /company, /leadership, /team. For a
        # run whose website answered 403 seven times, those are the only
        # things the retry budget could ever be spent on, and every one of
        # them is another refusal. Measured 2026-09-03: eight companies whose
        # sites refused, seven of them blocked on `official_identity_or_product`
        # while holding five of the company's own SEC filings, and two retry
        # passes each that planned six sources and gained nothing.
        #
        # This does not lower the bar: `family_of` ALREADY reads a 10-K as
        # `identity`, so the document was always going to satisfy the role
        # once retrieved. It simply becomes selectable when the website is
        # the thing that is broken.
        _subject_annual_report,
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
               failed_urls, refusing_hosts=(), memory=None,
               limit=MAX_NEW_SOURCES_PER_PASS) -> list:
    """Choose additional candidate ids that could supply the missing families.

    Never re-approves an already-approved candidate and never retries a URL
    that already failed — a permanent failure (403, 404, policy block) does not
    become retrievable by asking again. Deterministic: ordered by family
    priority, then by matcher specificity, then by URL.

    ``refusing_hosts`` are hosts this run has already WATCHED refuse it. By the
    time a retry is planned that is no longer an inference: Sony's first pass
    put fourteen requests to sony.com and every one came back 403. Retrying a
    fifteenth path on the same host is not a second chance, it is the same
    answer again — and it consumed the entire retry budget while the company's
    SEC filings sat in the candidate list, retrievable, and were never tried.
    Candidates on such a host sort LAST rather than being dropped, so if a run
    has nothing else left it still tries and still records an honest failure.
    """
    approved = set(already_approved or ())
    failed = set(failed_urls or ())
    # A URL THIS PRODUCT ALREADY WATCHED DIE IS NOT A SECOND CHANCE.
    #
    # `failed_urls` covers only THIS run. Measured across the probe cohort,
    # the retry loop planned 27 additional sources for four companies and
    # gained two documents: it was re-approving addresses that had returned
    # 404 or 403 on previous runs, because nothing carried that forward. The
    # retry budget is four sources per pass, so each one spent this way is a
    # missing evidence family that stays missing.
    if memory is not None:
        from intent_engine.company_ingestion.acquisition_memory import ALLOW
        failed = failed | {
            c["url"] for c in candidates
            if memory.verdict(c.get("url") or "")["verdict"] != ALLOW}
    refused = {h for h in (refusing_hosts or ()) if h}
    chosen: list = []
    seen = set(approved)

    def _refused_host(candidate):
        from urllib.parse import urlparse
        host = urlparse(candidate.get("url") or "").hostname or ""
        return any(host == bad or host.endswith("." + bad) for bad in refused)

    # Families whose gap can actually be FILLED come first. The retry budget is
    # four sources; walking the families in a fixed order spent all four on
    # identity/product/customers guesses against a host that had just refused
    # fourteen requests, and never reached `investor`, whose SEC filings were
    # the only retrievable evidence in the whole candidate list. Ordering by
    # reachability is stable and changes nothing when every host is healthy.
    def _reachable_options(family):
        matchers = FAMILY_TARGETS.get(family) or ()
        return sum(1 for c in candidates
                   if c["candidate_id"] not in seen
                   and c["url"] not in failed
                   and not _refused_host(c)
                   and any(matcher(c) for matcher in matchers))

    ordered_families = sorted(
        missing_families,
        key=lambda f: (0 if _reachable_options(f) else 1,
                       list(missing_families).index(f)))

    for family in ordered_families:
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
                key=lambda c: (1 if _refused_host(c) else 0,
                               0 if "sitemap" in c.get("why_relevant", "")
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
