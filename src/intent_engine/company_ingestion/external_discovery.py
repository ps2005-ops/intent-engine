"""V1.2 bounded external-source discovery.

Proposes a small, generic, company-agnostic set of OFF-domain candidate
sources so a live run can reach beyond company-owned pages. This is NOT a
search engine: it emits a fixed set of well-known public evidence endpoints
built from the company's name/domain. Every proposal is a *candidate* that:
  - carries its strategic source class and why it is relevant,
  - is marked EXTERNAL and UNVERIFIED,
  - requires explicit approval before anything is fetched,
  - is fetched (if approved) through the same SSRF-guarded retrieval path.

Independent-reporting and competitor evidence, which cannot be located
generically without a search engine, are added by the founder through the
bounded, explicit paste/add-source step on the approval page (also classified).
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

# generic public customer-voice endpoints (a check on the company's own claims)
_REVIEW_TEMPLATES = (
    ("https://www.g2.com/products/{slug}/reviews", "G2 — customer reviews"),
    ("https://www.trustpilot.com/review/{domain}", "Trustpilot — customer "
                                                    "reviews"),
    ("https://www.capterra.com/p/{slug}/", "Capterra — customer reviews"),
)

MAX_EXTERNAL_PROPOSALS = 4


def _slug(company_name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (company_name or "").lower()).strip("-")
    return s or "company"


def propose_external_candidates(*, company_name: str, domain: str) -> list:
    """Return generic off-domain customer-voice candidates. Deterministic and
    bounded; no crawling, no query expansion, no company-specific rules."""
    slug = _slug(company_name)
    out = []
    for template, title in _REVIEW_TEMPLATES:
        url = template.format(slug=slug, domain=domain)
        out.append({
            "url": url,
            "source_type": "external_approved",
            "discovery_method": "external_proposed",
            "same_domain": False,
            "source_class": "customer_voice",
            "why_useful": "third-party customer reviews",
            "why_relevant": "independent customer voice — corroborates or "
                            "challenges the company's own positioning",
            "availability": "UNVERIFIED",
            "title": title,
        })
        if len(out) >= MAX_EXTERNAL_PROPOSALS:
            break
    return out


def is_external_candidate(candidate: dict) -> bool:
    return candidate.get("discovery_method") == "external_proposed" or \
        not candidate.get("same_domain", True)


def hostname(url: str) -> str:
    return (urlparse(url).hostname or "").lower()
