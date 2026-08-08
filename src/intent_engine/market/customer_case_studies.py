"""Named customer stories — where a vendor states who buys from it.

WHY THE PROVENANCE DOES THE WORK
--------------------------------
A case study is the one document class where the PUBLISHER's identity settles
the direction. A page on shopify.com under /customers describing what a named
company does with Shopify states, by the act of publishing it, that the named
company is a customer. No sentence has to be parsed to establish who sells to
whom — the host and the path do it.

That inverts the usual risk. The danger here is not direction; it is the
company's own marketing, and the discipline is about what the page does NOT
establish.

WHAT A CASE STUDY DOES NOT ESTABLISH
------------------------------------
    revenue contribution   a case study is chosen for how it reads
    dependence             in either direction
    endorsement            a logo is not a testimonial and a testimonial is
                           not a commitment
    renewal                the page outlives the contract, silently
    materiality            the customer may be 0.01% of revenue
    currency               there is no expiry on a marketing page

So exactly one predicate is admitted: `SELLS_TO`, vendor → customer, and only
when the page states that the customer USES a product or service. A page that
merely names a company — an award list, an event sponsor, a logo wall — is
refused, because a name on a page is not a transaction.

CONSENT AND PROVENANCE
----------------------
These are the customer's own name on the vendor's marketing, published by the
vendor with the customer's agreement. That makes them safe to cite, and the
citation must carry the vendor's URL: a founder-visible claim that "X is a
customer of Y" has to be traceable to the page Y published, not to this
engine's summary of it.
"""
from __future__ import annotations

import re
from typing import Callable, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

from . import actor_relationships as AR
from . import counterparty_sources as CS
from . import partnership_releases as PRel

CONTRACT = "customer_case_study.v1"

CASE_STUDY_NEEDLES = ("/customer", "/customers", "/case-stud", "/case_stud",
                      "/success-stor", "/success-stories", "/stories/",
                      "/client")

MAX_PAGES_PER_SUBJECT = 6

#: The page must state USE, not just mention a name. These are the verbs a
#: case study uses about its subject; a logo wall has none of them.
_USE = re.compile(
    r"\b(?:uses?|used|using|adopt(?:ed|s|ing)?|deploy(?:ed|s|ing)?|"
    r"implement(?:ed|s|ing)?|migrat(?:ed|es|ing)\s+to|built\s+on|"
    r"runs?\s+on|powered\s+by|relies\s+on|switch(?:ed|es)\s+to|"
    r"chose|selected|standardi[sz]ed\s+on)\b", re.I)

#: A named company on the page that is NOT the customer this study is about.
#: Case studies routinely mention the customer's own customers, its partners
#: and the analysts it quotes. The customer is the one in the TITLE.
_TITLE_SPLIT = re.compile(r"\s*[|–—:·-]\s*")


def fetch(subject: str, aliases: Sequence[str], as_of: str = "", *,
          home_url: str = "", fetcher: Optional[Callable] = None,
          max_pages: int = MAX_PAGES_PER_SUBJECT) -> Tuple[CS.Document, ...]:
    """Retrieve the vendor's own customer pages, two hops as for releases."""
    from intent_engine.company_ingestion import fetch as F
    from intent_engine.company_ingestion import parsing as P
    from intent_engine.company_ingestion import sitemap as SM

    if not home_url:
        return ()
    read = fetcher or (lambda url, **kw: F.safe_fetch(url, **kw))
    host = urlparse(home_url).hostname or ""

    seeds: List[str] = []
    try:
        discovered = SM.discover_from_sitemap(
            home_url, fetcher=lambda url: read(
                url, extra_mime_prefixes=("application/xml", "text/xml")))
    except Exception:                                       # noqa: BLE001
        discovered = []
    for entry in discovered:
        url = entry if isinstance(entry, str) else (entry or {}).get("url", "")
        if _is_case_study_path(url):
            seeds.append(url)
    seeds.extend(home_url.rstrip("/") + p for p in
                 ("/customers", "/case-studies", "/customer-stories",
                  "/success-stories", "/clients"))
    seeds = list(dict.fromkeys(seeds))[:10]

    articles: List[str] = []
    for url in seeds:
        result = read(url)
        if not (result or {}).get("ok"):
            continue
        parsed = P.parse_html(result.get("body") or result.get("text") or "")
        for link in (parsed.get("links") or []):
            target = link if isinstance(link, str) else (link or {}).get(
                "href", "")
            target = PRel._absolute(target, url)
            if not target or urlparse(target).hostname != host:
                continue
            if _is_case_study_path(target) and \
                    target.rstrip("/") != url.rstrip("/"):
                articles.append(target)
        if len(articles) >= max_pages * 3:
            break
    articles = list(dict.fromkeys(articles))[:max_pages]

    out: List[CS.Document] = []
    for url in articles:
        result = read(url)
        if not (result or {}).get("ok"):
            continue
        parsed = P.parse_html(result.get("body") or result.get("text") or "")
        text = str(parsed.get("text") or "")
        if len(text) < PRel.MIN_ARTICLE_CHARS:
            continue
        out.append(CS.Document(
            document_id=f"case_study:{url}", family=CS.CUSTOMER_CASE_STUDY,
            subject=subject, title=str(parsed.get("title") or ""),
            text=text, url=url, published_at=as_of[:10],
            fields={"publisher_host": urlparse(url).hostname or ""}))
    return tuple(out)


def _is_case_study_path(url: str) -> bool:
    path = (urlparse(url or "").path or "").lower()
    return bool(path) and any(n in path for n in CASE_STUDY_NEEDLES)


def extract(document: CS.Document, subject: str, aliases: Sequence[str]
            ) -> Tuple[Tuple[AR.ActorRelationship, ...],
                       Dict[str, int], Dict[str, int]]:
    """One page, at most one relationship: the vendor sells to the customer.

    The customer is taken from the TITLE, not from the body. A case study's
    body names the customer's own customers, its partners and the analysts it
    quotes, and any of those would become a spurious edge under a
    first-name-in-the-text rule.
    """
    refused: Dict[str, int] = {}
    counts: Dict[str, int] = {"named_actor_mentions": 0,
                              "relationship_candidates": 0,
                              "identity_resolved": 0}

    def refuse(reason: str):
        refused[reason] = refused.get(reason, 0) + 1
        return (), refused, counts

    vendor = PRel._display_name(aliases, subject)
    customer = _customer_from_title(document.title, aliases, subject,
                                    body=document.text)
    if not customer:
        return refuse("title_names_no_customer")
    counts["named_actor_mentions"] += 1
    if not _USE.search(document.text):
        # A name with no stated use is a logo wall, an award list or an event
        # page. Naming somebody is not transacting with them.
        return refuse("page_states_no_use_of_a_product_or_service")
    counts["relationship_candidates"] += 1
    if CS.resolves_to(customer, list(aliases) + [subject]):
        return refuse("named_party_is_the_vendor")
    counts["identity_resolved"] += 1

    hit = _USE.search(document.text)
    sentence = _sentence_around(document.text, hit.start()) if hit else ""
    try:
        row = AR.relationship(
            subject_actor=vendor, predicate=AR.SELLS_TO,
            object_actor=customer,
            evidence_ids=(document.document_id,),
            source_document=document.url,
            subject_span=f"published by {document.fields.get('publisher_host', '')}",
            object_span=customer,
            relationship_span=(
                f"{document.title[:120]} — {sentence[:200]} "
                f"[a stated customer relationship; states nothing about "
                f"revenue contribution, dependence, materiality or renewal]"),
            epistemic_status=AR.OBSERVED,
            valid_from=document.published_at,
            created_at=document.published_at)
    except AR.RelationshipRejected:
        return refuse("rejected_by_contract")
    return (row,), refused, counts


#: Case-study titles open with a narrative word far more often than not:
#: "How Cocunat...", "From zero to...", "Behind the scenes at...". The actor
#: matcher is happy to swallow the opener as the first token of the name, and
#: the first live measurement produced customers called "How Cocunat", "From"
#: and "Behind" because of it.
_TITLE_OPENER = re.compile(
    r"^(?:how|why|what|when|where|meet|inside|behind|from|see|watch|read|"
    r"discover|introducing|the\s+story\s+of|case\s+study:?|customer\s+story:?"
    r")\s+", re.I)

#: A title that opens with the VENDOR's own name is the vendor talking about
#: itself: "Shopify Case Studies", "Olo Case Study", "Stripe Supports Rivian".
#: The whole-token resolver does not catch these — a one-token alias may not
#: claim a three-token name, which is the rule that stops "Linear" claiming
#: "Linear Minerals" — so the vendor prefix is stripped separately.
#:
#: A title that opens with a VERB is the headline's predicate, not a name:
#: "Jobber Expands With New..." carries a customer and four words of copy.
_TITLE_VERB = re.compile(
    r"^(?:expands?|supports?|grows?|builds?|scales?|uses?|powers?|drives?|"
    r"boosts?|cuts?|increases?|achieves?|delivers?|launches?|migrates?|"
    r"chooses?|partners?|helps?|brings?|takes?|turns?|moves?|goes?|adds?|"
    r"with|and|for|in|on|to|at|by|from|case|stor(?:y|ies)|stud(?:y|ies))$",
    re.I)


def _trim_to_the_name(candidate: str, vendor_tokens: frozenset) -> str:
    """Drop a leading vendor name and any leading verb, then stop at the next.

    "Stripe Supports Rivian" is the vendor, its verb, and the customer, in
    that order. Stopping at the FIRST verb would return nothing; skipping
    leading verbs and stopping at the next returns "Rivian".
    """
    tokens = candidate.split()
    while tokens and tokens[0].lower().strip(".,") in vendor_tokens:
        tokens.pop(0)
    while tokens and _TITLE_VERB.match(tokens[0].strip(".,")):
        tokens.pop(0)
    kept = []
    for token in tokens:
        if _TITLE_VERB.match(token.strip(".,")):
            break
        kept.append(token)
    return " ".join(kept).strip(" .,;:")


#: A landing page, not a study. These titles name the SECTION, and a customer
#: called "Case Studies" is the section heading wearing a company's schema.
_SECTION_TITLE = re.compile(
    r"^(?:case\s+stud(?:y|ies)|customer\s+stor(?:y|ies)|success\s+stor"
    r"(?:y|ies)|customers?|clients?|our\s+customers?|testimonials?|"
    r"contact|supplying|partners?)\b", re.I)


def _customer_from_title(title: str, aliases: Sequence[str],
                         subject: str, body: str = "") -> str:
    """The first titled segment that names somebody other than the vendor."""
    for piece in _TITLE_SPLIT.split(title or ""):
        piece = _TITLE_OPENER.sub("", piece.strip())
        if not piece or _SECTION_TITLE.match(piece):
            continue
        match = AR._ACTOR.match(piece)
        if not match:
            continue
        vendor_tokens = frozenset(
            t.lower().strip(".,")
            for alias in list(aliases) + [subject]
            for t in CS.normalise_actor(alias).split())
        candidate = _trim_to_the_name(match.group(1).strip(" .,;:"),
                                      vendor_tokens)
        if not candidate or not AR.is_named_actor(candidate):
            continue
        if CS.resolves_to(candidate, list(aliases) + [subject]):
            continue
        if _SECTION_TITLE.match(candidate):
            continue
        # A one-word customer name has to recur in the BODY, not just in the
        # title — same rule as the release family, and checked against the
        # page rather than the headline so a real one-word customer like
        # "Figma" survives while a cut phrase does not.
        if PRel._plausible_counterparty(candidate, body or title):
            continue
        return candidate
    return ""


def _sentence_around(text: str, index: int) -> str:
    start = max(text.rfind(".", 0, index), text.rfind("\n", 0, index)) + 1
    end = text.find(".", index)
    return " ".join(text[start:(end + 1 if end > 0 else len(text))].split())
