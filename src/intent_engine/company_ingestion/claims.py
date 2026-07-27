"""V1.1 real-source claims — deterministic extraction into the existing
Founder Intelligence SourceClaim contract. ZERO model calls.

Rules enforced here:
- every claim cites real SourceRefs (subsystem "company_ingestion");
- every quoted phrase exists verbatim in the stored source text;
- direct evidence before inference; unsupported fields are UNAVAILABLE;
- a major insight needs >= 2 distinct sources (or is labelled direct);
- no synthetic ("demo_fixture") ref may enter a real run — hard invariant.
"""
from __future__ import annotations

import re
from collections import Counter

from intent_engine.company_ingestion.records import IngestionError
from intent_engine.personal.records import (
    AVAIL_PARTIAL, AVAIL_SUPPORTED, AVAIL_UNAVAILABLE, SourceClaim, SourceRef,
)

REAL_SUBSYSTEM = "company_ingestion"
SYNTHETIC_SUBSYSTEM = "demo_fixture"

_STOPWORDS = frozenset(
    "the a an and or of to in for with on your you we our us is are be that "
    "this it as at by from more get all can will how what its their they "
    "them out up new about into over than then so if no not do does did have "
    "has had but also just any every been being was were very such there "
    "here when where which would could should while during without within "
    "these those because other others some most much many like unlike once "
    "ever never always want wants needs need make makes made give gives "
    "take takes see sees say says use uses used using come comes way ways "
    "thing things something".split())

_OUTCOME_TERMS = ("faster", "save", "saving", "reduce", "reduces", "grow",
                  "growth", "automate", "automation", "secure", "security",
                  "reliable", "reliability", "simple", "simplify", "speed",
                  "efficiency", "insight", "insights", "privacy", "control",
                  "scale", "productivity", "compliance", "accuracy")

_AUDIENCE_PATTERNS = (
    r"for ([a-z][a-z\- ]{2,40}?(?:teams|developers|founders|businesses|"
    r"companies|startups|agencies|marketers|engineers|creators|"
    r"enterprises|operators))",
    r"built for ([a-z][a-z\- ]{2,40})\b",
)


def real_ref(doc: dict) -> SourceRef:
    return SourceRef(
        subsystem=REAL_SUBSYSTEM, artifact_type=doc["source_type"],
        artifact_id=doc["source_id"],
        replay_id=f"real:{doc['source_id']}:{doc['content_hash'][:12]}",
        as_of=doc["retrieved_at"], snapshot_version=doc["parser_version"],
        observed_at=doc["retrieved_at"],
        freshness_status=doc.get("freshness", "CURRENT"))


def assert_real_claims(claims_by_section: dict) -> None:
    """Hard invariant: a real run may not consume synthetic evidence."""
    for group in claims_by_section.values():
        if not isinstance(group, list):
            continue
        for claim in group:
            for ref in claim.source_refs:
                if ref.subsystem == SYNTHETIC_SUBSYSTEM:
                    raise IngestionError(
                        "REAL run received a synthetic SourceRef "
                        f"({ref.artifact_id}) — hard failure")


def assert_quotes_exist(text: str, docs_by_id: dict, source_ids: list) -> None:
    """Every quoted phrase in claim text must exist in a cited source."""
    for quoted in re.findall(r"[\"“]([^\"”]{4,120})[\"”]", text):
        if not any(quoted.lower() in
                   (docs_by_id[sid]["text_content"].lower()
                    + " " + (docs_by_id[sid].get("title") or "").lower()
                    + " " + (docs_by_id[sid].get("meta_description")
                             or "").lower())
                   for sid in source_ids if sid in docs_by_id):
            raise IngestionError(
                f"quoted phrase {quoted[:60]!r} does not exist in any "
                "cited source — rejected")


def _claim(claim_id, text, availability, docs, *, confidence=None,
           transformation="direct", docs_by_id=None) -> SourceClaim:
    refs = tuple(real_ref(d) for d in docs) \
        if availability != AVAIL_UNAVAILABLE else ()
    if docs_by_id is not None and docs:
        assert_quotes_exist(text, docs_by_id, [d["source_id"] for d in docs])
    claim = SourceClaim(claim_id=claim_id, text=text,
                        availability=availability, source_refs=refs,
                        confidence=confidence, transformation=transformation,
                        freshness_status=min(
                            (d.get("freshness", "CURRENT") for d in docs),
                            default="CURRENT",
                            key=lambda f: 0 if f == "STALE" else 1))
    return claim


def _q(term: str) -> str:
    """Double-quote a source-derived term (source material, not voice)."""
    return '"' + term + '"'


# Procedural / legal-filing vocabulary. SEC filings (esp. 8-K cover pages) are
# dense with this; it is never a business insight, so it is excluded from every
# term-frequency signal — otherwise "pursuant, rule, exchange" surfaces as the
# company's "emphasized language" (2026-07 report-quality incident).
_LEGAL_STOP = frozenset(
    "pursuant rule under communications exchange act registrant hereby "
    "hereunder herein thereof thereto whereas exhibit exhibits incorporated "
    "reference signature signatures dated furnished section sections item "
    "items form forms filing filed commission securities shall undersigned "
    "duly authorized behalf date title statements statement report reports "
    "quarterly annual fiscal amended".split())


def _terms(text: str, *, top=8) -> list:
    words = re.findall(r"[a-z][a-z\-]{3,}", (text or "").lower())
    counts = Counter(w for w in words
                     if w not in _STOPWORDS and w not in _LEGAL_STOP)
    return [w for w, _ in counts.most_common(top)]


def _outcome_terms(text: str) -> list:
    lowered = (text or "").lower()
    return [t for t in _OUTCOME_TERMS if t in lowered]


def build_claims(*, documents: list, company_name: str, domain: str,
                 competitor_approved: bool = False) -> dict:
    """documents = stored retrieved/pasted records (dicts). Returns the
    claims_by_section dict the Founder Intelligence service composes."""
    docs = {d["source_id"]: d for d in documents
            if d.get("retrieval_status") == "OK"}
    by_type: dict = {}
    for d in docs.values():
        by_type.setdefault(d["source_type"], []).append(d)

    # Identity evidence: the homepage when it is readable, otherwise the
    # about/company page. A JavaScript-blocked homepage must not leave the
    # report unable to say what the company is — the about page is the same
    # first-party, directly-observed evidence.
    home = (by_type.get("homepage") or by_type.get("about") or [None])[0]
    site_docs = [d for d in docs.values()
                 if d["source_type"] not in ("pasted", "external_approved",
                                             "uploaded")]
    external_docs = [d for d in docs.values()
                     if d["source_type"] in ("pasted", "external_approved",
                                             "uploaded")]
    # SEC / investor-material filings are NOT customer or market "language" —
    # feeding them into term-frequency emphasis produced the legal-boilerplate
    # "strongest observation". Separate them: customer_docs carry independent
    # customer/market voice; investor_docs are financial/regulatory disclosure.
    investor_docs = [d for d in external_docs
                     if d.get("source_class") == "investor_material"]
    customer_docs = [d for d in external_docs
                     if d.get("source_class") in ("customer_voice",
                                                  "independent_reporting",
                                                  "competitor")
                     or d["source_type"] == "pasted"]

    understanding, analytics, market, persona = [], [], [], []
    blind, assumption, attention, stale = [], [], [], []

    # --- understanding: direct observation first ------------------------------
    if home:
        title = (home.get("title") or "").strip()
        if title:
            understanding.append(_claim(
                "u.identity",
                f'Company identity: the homepage presents itself as '
                f'"{title}" at {domain}.',
                AVAIL_SUPPORTED, [home], confidence="High",
                docs_by_id=docs))
        meta = (home.get("meta_description") or "").strip()
        if meta:
            understanding.append(_claim(
                "u.offering",
                f'What the company appears to sell (directly observed): '
                f'"{meta[:220]}"',
                AVAIL_SUPPORTED, [home], confidence="High",
                docs_by_id=docs))
        first_heading = next(
            (line for line in home["text_content"].split("\n")
             if len(line.split()) >= 3), "")
        if first_heading and first_heading.lower() != meta.lower():
            understanding.append(_claim(
                "u.value_prop",
                f'Visible value proposition (homepage): '
                f'"{first_heading[:200]}"',
                AVAIL_SUPPORTED, [home], confidence="Moderate",
                docs_by_id=docs))
        audience = None
        for pattern in _AUDIENCE_PATTERNS:
            m = re.search(pattern, home["text_content"].lower())
            if m:
                audience = m.group(1).strip()
                break
        if audience:
            understanding.append(_claim(
                "u.customer",
                f"Visible audience language: the homepage speaks to "
                f"{audience} (supported inference from page language).",
                AVAIL_PARTIAL, [home], confidence="Moderate",
                transformation="summarized"))
            persona.append(_claim(
                "p.homepage_audience",
                f"The homepage appears primarily oriented toward "
                f"{audience}. We do not yet know whether this is "
                f"intentional.", AVAIL_PARTIAL, [home],
                confidence="Moderate", transformation="summarized"))
    # --- products / platform: what the company actually offers ---------------
    # Without this, a retrieved product or documentation page contributed
    # nothing to the report and the offering stayed "Not available" even though
    # the evidence was sitting in the approved set (2026-07 incident).
    for product_doc in by_type.get("product", [])[:2]:
        headline = (product_doc.get("title") or "").strip()
        body_line = next(
            (line for line in product_doc["text_content"].split("\n")
             if len(line.split()) >= 3), "")
        if headline:
            understanding.append(_claim(
                f"u.product.{product_doc['source_id']}",
                f'Product/platform evidence (directly observed): '
                f'"{headline[:120]}"'
                + (f' — "{body_line[:200]}"' if body_line else ""),
                AVAIL_SUPPORTED, [product_doc], confidence="High",
                docs_by_id=docs))
    # If identity came from the about page, the "homepage" wording would be
    # wrong; the claims above phrase themselves generically enough, but a
    # missing homepage is itself worth stating honestly.
    if not by_type.get("homepage") and home is not None:
        understanding.append(_claim(
            "u.identity_source",
            "The homepage could not be read (it requires JavaScript or "
            "refused automated access); identity and offering above come "
            "from the company's about/company page instead.",
            AVAIL_PARTIAL, [home], confidence="High",
            transformation="summarized"))
    for customer_doc in by_type.get("customers", [])[:1]:
        line = next((ln for ln in customer_doc["text_content"].split("\n")
                     if len(ln.split()) >= 5), "")
        if line:
            understanding.append(_claim(
                "u.customers",
                f'Customer/use-case evidence (company-published): '
                f'"{line[:220]}"',
                AVAIL_SUPPORTED, [customer_doc], confidence="Moderate",
                docs_by_id=docs))
    if by_type.get("pricing"):
        pricing = by_type["pricing"][0]
        understanding.append(_claim(
            "u.pricing",
            "A public pricing page exists; pricing is presented publicly "
            f"under \"{(pricing.get('title') or 'Pricing')[:80]}\".",
            AVAIL_SUPPORTED, [pricing], confidence="High",
            docs_by_id=docs))
    else:
        understanding.append(_claim(
            "u.pricing", "Pricing model: not determinable from the "
            "approved sources.", AVAIL_UNAVAILABLE, []))
    understanding.append(_claim(
        "u.scope", f"Evidence scope: {len(site_docs)} company page(s) and "
                   f"{len(external_docs)} user-approved external/pasted "
                   f"source(s) were analyzed.",
        AVAIL_SUPPORTED, list(docs.values())[:10], confidence="High",
        transformation="grouped"))

    # --- analytics: language distributions (counts as evidence, not strategy)
    if site_docs:
        combined = " ".join(d["text_content"] for d in site_docs)
        top = _terms(combined)
        if top:
            analytics.append(_claim(
                "a.language_terms",
                f"Most repeated site language: "
                f"{', '.join(_q(t) for t in top[:6])} "
                f"(term frequency across {len(site_docs)} approved pages; "
                f"not a strategy conclusion).",
                AVAIL_SUPPORTED, site_docs[:6], confidence="Moderate",
                transformation="grouped"))
        outcomes = _outcome_terms(combined)
        if outcomes:
            analytics.append(_claim(
                "a.outcome_language",
                f"Outcome language present on company pages: "
                f"{', '.join(_q(t) for t in outcomes[:6])}.",
                AVAIL_SUPPORTED, site_docs[:6], confidence="Moderate",
                transformation="grouped"))
    blog_docs = by_type.get("blog", [])
    if blog_docs:
        analytics.append(_claim(
            "a.publication_activity",
            f"Publication activity: {len(blog_docs)} blog/news page(s) in "
            "the approved set.", AVAIL_SUPPORTED, blog_docs[:4],
            confidence="Moderate", transformation="grouped"))
    analytics.append(_claim(
        "a.engagement", "Public engagement metrics: UNAVAILABLE — no "
        "supported engagement source was approved.", AVAIL_UNAVAILABLE, []))

    # --- market view: company vs external language ----------------------------
    if site_docs:
        market.append(_claim(
            "mv.company_language",
            f"Your company pages emphasize: "
            f"{', '.join(_q(t) for t in _terms(' '.join(d['text_content'] for d in site_docs), top=5))}.",
            AVAIL_SUPPORTED, site_docs[:6], confidence="Moderate",
            transformation="grouped"))
    if customer_docs:
        market.append(_claim(
            "mv.customer_language",
            f"Independent/customer evidence emphasizes: "
            f"{', '.join(_q(t) for t in _terms(' '.join(d['text_content'] for d in customer_docs), top=5))} "
            f"(user-approved external sources).",
            AVAIL_SUPPORTED, customer_docs[:6], confidence="Moderate",
            transformation="grouped"))
    if investor_docs:
        market.append(_claim(
            "mv.investor_disclosure",
            f"Financial/regulatory disclosure: {len(investor_docs)} official "
            f"filing(s) (SEC / investor material) were analyzed as financial "
            f"and risk evidence — not as product or customer messaging.",
            AVAIL_SUPPORTED, investor_docs[:6], confidence="Moderate",
            transformation="grouped"))

    # --- blind spot: only when two distinct sources genuinely diverge --------
    customers_docs = by_type.get("customers", [])
    def _home_terms(h):
        return (set(_terms(h["text_content"], top=10))
                | set(_terms((h.get("title") or "") + " "
                             + (h.get("meta_description") or ""), top=25)))

    if home and customers_docs:
        home_terms = _home_terms(home)
        cust_terms = set(_terms(" ".join(d["text_content"]
                                         for d in customers_docs), top=10))
        divergent = list(cust_terms - home_terms)[:4]
        if divergent:
            blind.append(_claim(
                "b.emphasis_gap",
                f"Customer-facing pages repeatedly use language the "
                f"homepage does not emphasize: "
                f"{', '.join(_q(t) for t in divergent)}. "
                f"This may be intentional.", AVAIL_SUPPORTED,
                [home, customers_docs[0]], confidence="Moderate",
                transformation="grouped"))
    if home and customer_docs and not blind:
        home_terms = _home_terms(home)
        ext_terms = set(_terms(" ".join(d["text_content"]
                                        for d in customer_docs), top=10))
        divergent = list(ext_terms - home_terms)[:4]
        if divergent:
            blind.append(_claim(
                "b.external_gap",
                f"Approved external evidence emphasizes language the "
                f"homepage does not: "
                f"{', '.join(_q(t) for t in divergent)}. This may be "
                f"intentional.", AVAIL_SUPPORTED,
                [home, external_docs[0]], confidence="Moderate",
                transformation="grouped"))

    # --- assumption worth testing ---------------------------------------------
    if home:
        home_outcomes = _outcome_terms(home["text_content"])
        if home_outcomes:
            assumption.append(_claim(
                "as.emphasis.feature",
                f"Visible assumption: buyers respond to the emphasized "
                f"outcome language ({', '.join(_q(t) for t in home_outcomes[:3])}).",
                AVAIL_PARTIAL, [home], confidence="Moderate",
                transformation="summarized"))
        if customer_docs:
            ext_outcomes = _outcome_terms(
                " ".join(d["text_content"] for d in customer_docs))
            complicating = [t for t in ext_outcomes
                            if t not in home_outcomes]
            if complicating:
                assumption.append(_claim(
                    "as.external.speed",
                    f"Complicating evidence: external sources emphasize "
                    f"{', '.join(_q(t) for t in complicating[:3])}, which the homepage "
                    f"does not.", AVAIL_PARTIAL, external_docs[:2],
                    confidence="Moderate", transformation="summarized"))

    # --- attention: evidence gaps ----------------------------------------------
    if not customer_docs:
        attention.append(_claim(
            "at.external_evidence",
            "No independent customer/market evidence was approved — the market "
            "view is one-sided (SEC/investor filings are not customer voice) "
            "until review, interview, or news evidence is added.",
            AVAIL_PARTIAL,
            (site_docs or investor_docs or list(docs.values()))[:2],
            confidence="Moderate", transformation="summarized"))
    failed_note = [d for d in documents
                   if d.get("retrieval_status") not in ("OK", None)]
    if failed_note:
        attention.append(_claim(
            "at.failed_sources",
            f"{len(failed_note)} approved source(s) could not be "
            "retrieved; their absence is a gap, not evidence.",
            AVAIL_PARTIAL, site_docs[:1] if site_docs else [],
            confidence="High", transformation="summarized"))

    # --- stale ------------------------------------------------------------------
    for d in docs.values():
        if d.get("freshness") == "STALE":
            stale.append(_claim(
                f"s.{d['source_id']}",
                f"Source \"{(d.get('title') or d['source_id'])[:60]}\" is "
                f"stale; conclusions from it carry its as-of date.",
                AVAIL_PARTIAL, [d], confidence="High",
                docs_by_id=docs))

    claims_by_section = {
        "understanding": understanding, "analytics": analytics,
        "market_view": market, "persona": persona, "blind_spot": blind,
        "assumption": assumption, "attention": attention,
        "opportunity": [], "stale": stale,
        "competitor_request": bool(competitor_approved),
        "note": "REAL COMPANY ANALYSIS — based only on the approved "
                "sources listed in the evidence library; it does not "
                "represent internal company knowledge",
    }
    assert_real_claims(claims_by_section)
    return claims_by_section


def executive_overview(claims_by_section: dict, *, company_name: str,
                       source_count: int, failure_count: int) -> list:
    """<=250-word overview; every sentence resolves to the ClaimSet."""
    def first(section, prefix=None):
        for claim in claims_by_section.get(section, []):
            if claim.availability != AVAIL_UNAVAILABLE and \
                    (prefix is None or claim.claim_id.startswith(prefix)):
                return claim
        return None

    sentences = []
    offering = first("understanding", "u.offering") or \
        first("understanding", "u.identity")
    if offering:
        sentences.append({"text": offering.text,
                          "claim_ids": [offering.claim_id]})
    audience = first("understanding", "u.customer")
    if audience:
        sentences.append({"text": audience.text,
                          "claim_ids": [audience.claim_id]})
    scope = first("understanding", "u.scope")
    if scope:
        sentences.append({"text": scope.text, "claim_ids": [scope.claim_id]})
    strongest = first("blind_spot") or first("market_view") or \
        first("analytics")
    if strongest:
        sentences.append({"text": f"Strongest supported observation: "
                                  f"{strongest.text}",
                          "claim_ids": [strongest.claim_id]})
    limitation = {"text": "Most important limitation: this analysis uses "
                          f"only {source_count} approved source(s)"
                          + (f"; {failure_count} approved source(s) failed "
                             f"to retrieve" if failure_count else "")
                          + ". Public information can be incomplete.",
                  "claim_ids": ["u.scope"]}
    sentences.append(limitation)
    return sentences
