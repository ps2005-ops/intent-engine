"""Industry evidence — third-party coverage of a company, point-in-time.

WHY THIS ONE
------------
Measured across 28 companies × 6 hypothesis kinds: `industry` blocks 84 of 168
decision paths, three times any other category, because it appears in the
required set of three hypothesis kinds where every other appears in one. It is
retrievable (HTTP 200) where customer_voice is not (403) and macro needs a
credential.

THE LIMITATION, STATED UP FRONT
-------------------------------
**Replay depth is 87 days.** Measured, not estimated. A news feed carries
recent items, so this cannot support the ten-year walk-forward evaluation that
is this project's only way to test a signal. It is a **live-path capability
only**, and the honest consequence is that industry evidence can unlock live
decisions and can never validate a signal.

That limitation is why this is one narrow adapter and not a research programme.

AUTHORSHIP DECIDES CATEGORY, NEVER THE VENUE
--------------------------------------------
A company press release syndicated through a news aggregator is still the
company speaking. The aggregator is a venue; the author is the subject. So
publisher is classified before anything else, and a release authored by the
company is COMPANY evidence no matter where it appears — which means it cannot
satisfy the corroboration gate, which is the entire point.

This is the specific gaming route this adapter must not open: pulling a
company's own press releases through a third-party feed and counting them as
independent corroboration.
"""
from __future__ import annotations

import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Callable, List, Optional, Sequence

from intent_engine.market.corroboration import Category

SOURCE = "google_news_rss.v1"
_ENDPOINT = ("https://news.google.com/rss/search?q=%22{query}%22"
             "&hl=en-US&gl=US&ceid=US:en")
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; intent-engine/1.0)"}

# Publishers that carry a company's OWN words. A press-release wire is a
# distribution channel for the subject, not an independent observer.
_WIRE_PUBLISHERS = (
    "globenewswire", "pr newswire", "prnewswire", "business wire",
    "businesswire", "accesswire", "newsfile", "einpresswire", "prweb",
)
# Publishers whose output is analyst opinion rather than reporting.
_ANALYST_PUBLISHERS = (
    "zacks", "morningstar", "seeking alpha", "simply wall st",
    "stockstotrade", "tradingview", "tradingkey", "the motley fool",
)


class IndustryUnavailable(RuntimeError):
    """The feed could not answer. Never swallowed into fabricated evidence."""


@dataclass(frozen=True)
class IndustryDocument:
    """One third-party document, with every field it actually carried."""
    url: str
    publisher: str
    title: str
    published_at: str          # ISO date, from the feed. NEVER inferred.
    retrieved_at: str
    category: str
    excerpt: str = ""
    author: str = ""
    confidence: float = 0.5
    source: str = SOURCE

    @property
    def is_independent(self) -> bool:
        return self.category != Category.COMPANY

    def as_evidence_row(self) -> dict:
        """The hosted-store shape, so this flows through the existing pipeline
        without a second evidence format."""
        return {"kind": _KIND_FOR_CATEGORY.get(self.category, "news"),
                "summary": self.title[:600], "source": self.url,
                "published_at": self.published_at,
                "confidence": self.confidence,
                "interpretation": f"{self.publisher} ({self.category})"}


_KIND_FOR_CATEGORY = {
    Category.INDUSTRY: "news",
    Category.ANALYST: "analyst",
    Category.COMPANY: "product",
}


def classify_publisher(publisher: str, company_name: str) -> str:
    """Category from AUTHORSHIP. The venue never overrides it.

    Order matters. The company's own name is checked first, because a release
    authored by the subject and syndicated through an aggregator is still the
    subject speaking — and admitting it as independent corroboration is exactly
    the gaming route this adapter exists to keep shut.
    """
    pub = (publisher or "").strip().lower()
    if not pub:
        return Category.INDUSTRY
    company = (company_name or "").strip().lower()
    # the company itself, or an obvious variant of its name
    root = re.split(r"[ ,.]", company)[0] if company else ""
    if root and len(root) > 2 and root in pub:
        return Category.COMPANY
    if any(w in pub for w in _WIRE_PUBLISHERS):
        return Category.COMPANY
    if any(a in pub for a in _ANALYST_PUBLISHERS):
        return Category.ANALYST
    return Category.INDUSTRY


# Vocabulary per hypothesis kind. Relevance is explicit and per-document: a CEO
# biography is industry-authored and says nothing about customer adoption, and
# admitting it would corroborate a claim it cannot speak to.
_RELEVANCE_TERMS = {
    "customer_adoption": ("adopt", "customer", "merchant", "user", "subscriber",
                          "churn", "retention", "demand", "orders", "usage",
                          "market share", "growth"),
    "governance": ("board", "governance", "activist", "proxy", "shareholder",
                   "executive", "ceo steps", "resign", "investigation",
                   "lawsuit", "regulator", "compliance"),
    "macro_sensitivity": ("rates", "inflation", "recession", "tariff",
                          "currency", "fx", "consumer spending", "macro",
                          "gdp", "unemployment"),
    "expectation_shift": ("estimate", "guidance", "forecast", "outlook",
                          "upgrade", "downgrade", "target price", "consensus",
                          "beats", "misses", "revised"),
    "competitive_position": ("competitor", "rival", "versus", " vs ", "share",
                             "compet", "entrant", "displace", "wins", "loses"),
    "price_behaviour": (),
}


def is_relevant(document: IndustryDocument, hypothesis_kind: str) -> bool:
    """Does this document speak to THIS claim?

    Explicit rather than assumed. Industry evidence cannot satisfy an unrelated
    hypothesis, however independent its author.
    """
    terms = _RELEVANCE_TERMS.get(hypothesis_kind)
    if terms is None:
        return False
    if not terms:                      # price_behaviour asserts nothing here
        return False
    text = f"{document.title} {document.excerpt}".lower()
    return any(t in text for t in terms)


def _fetch(url: str, timeout: float) -> bytes:
    request = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def _published_iso(raw: Optional[str]) -> Optional[str]:
    """Parse the feed's own timestamp, or return None.

    Never infers, never substitutes 'now'. A document whose date cannot be read
    is dropped, because a fabricated publication time is the one error that
    would silently defeat every point-in-time guarantee downstream.
    """
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw).astimezone(timezone.utc)\
            .date().isoformat()
    except (TypeError, ValueError):
        return None


def fetch_industry_evidence(company_name: str, *, as_of: str,
                            limit: int = 25, timeout: float = 25.0,
                            opener: Optional[Callable] = None
                            ) -> List[IndustryDocument]:
    """Third-party coverage of `company_name` published on or before `as_of`.

    `opener` is injectable so the offline suite exercises the parsing, the
    authorship rules and the point-in-time filter without a network call.
    """
    if not company_name:
        return []
    url = _ENDPOINT.format(query=urllib.request.quote(company_name))
    try:
        payload = (opener or _fetch)(url, timeout)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise IndustryUnavailable(
            f"{company_name}: {type(exc).__name__}") from exc

    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise IndustryUnavailable(f"{company_name}: malformed feed") from exc

    retrieved = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cutoff = as_of[:10]
    out: List[IndustryDocument] = []
    for item in root.findall(".//item"):
        published = _published_iso(item.findtext("pubDate"))
        if published is None:
            continue                    # no readable date -> not usable
        # POINT-IN-TIME. Rejected, never clamped: moving the date back would
        # assert the document existed then, which is what is not known.
        if published > cutoff:
            continue
        source_el = item.find("{*}source")
        publisher = ((source_el.text if source_el is not None else None)
                     or item.findtext("source") or "")
        title = " ".join((item.findtext("title") or "").split())
        if not title:
            continue
        out.append(IndustryDocument(
            url=item.findtext("link") or "",
            publisher=publisher.strip(),
            title=title,
            published_at=published,
            retrieved_at=retrieved,
            category=classify_publisher(publisher, company_name),
            excerpt=" ".join(
                re.sub(r"<[^>]+>", " ",
                       item.findtext("description") or "").split())[:400],
            confidence=0.6))
        if len(out) >= limit:
            break
    return out


def independent_documents(documents: Sequence[IndustryDocument],
                          hypothesis_kind: str) -> List[IndustryDocument]:
    """Documents that are BOTH independent of the subject and relevant to the
    claim. Both conditions, never traded off."""
    return [d for d in documents
            if d.is_independent and is_relevant(d, hypothesis_kind)]
