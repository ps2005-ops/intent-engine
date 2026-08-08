"""Company-published announcements — the one place the corpus ever named a name.

WHY THIS FAMILY, AND WHY THE SEMANTICS ARE THE HARD PART
--------------------------------------------------------
Across ~11,000 measured sentences of periodic disclosure, one real
counterparty appeared, and it came from a partnership release. Filings say
"our competitors"; a partnership release exists to say who. So the retrieval
problem is nearly solved before it starts — the announcement WANTS to name
the other party.

Which moves the whole difficulty onto the predicate. These are all different
claims, and a family that collapses them produces a graph that looks rich and
means nothing:

    "X partners with Y"          a stated relationship of unstated content
    "X integrates with Y"        two products interoperate; possibly no
                                 commercial relationship of any kind
    "X selected Y to deliver Z"  Y sells to X
    "X distributes through Y"    Y carries X's product to market
    "X supplies Y"               X ships something Y consumes

`integrates with` is NOT `DEPENDS_ON`. `partners with` is NOT `SUPPLIES`. A
press release announcing an integration is often two vendors with a common
customer and no money moving between them, and promoting that to dependence
would put a load-bearing claim in the graph on the strength of a marketing
verb.

So the rule is: KEEP THE WEAKEST ACCURATE RELATION. Where a phrase is
genuinely ambiguous between two predicates, the weaker one is admitted, and
where it states no commercial relation at all it is refused with the reason
rather than rounded up to the nearest available predicate.

WHAT IS DELIBERATELY NOT EXTRACTED
----------------------------------
"X uses Y" and "X works with Y" are refused. Both are true of arrangements
with no relationship worth recording — a company "uses" a text editor. The
catalogue has no predicate weak enough to be accurate, and the correct
response to that is to refuse, not to pick the nearest one.

BOILERPLATE IS POSITIONAL, AND THIS FAMILY HAS ITS OWN KIND
-----------------------------------------------------------
A newsroom page carries navigation, an "About" trailer and a partner-logo
strip. The nav and the logo strip do not match, because every pattern here
requires a stated verb phrase with a named object; a bare "Partners" menu
item cannot produce an edge. The "About" trailer can, and is dropped by
position: it is the last block, it starts with "About", and it is the same
text on every release the company publishes.
"""
from __future__ import annotations

import re
from typing import Callable, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

from . import actor_relationships as AR
from . import counterparty_sources as CS

CONTRACT = "partnership_release.v1"

#: URL path needles that mark a company-published announcement. Matching the
#: ingestion layer's own newsroom family so this reuses a classification that
#: has already been tuned against real sites.
NEWSROOM_NEEDLES = ("/news", "/newsroom", "/press", "/media",
                    "/announcements", "/blog")

MAX_PAGES_PER_SUBJECT = 6

#: (pattern, predicate, subject_is_left, what the phrase actually licenses)
#:
#: Every entry is a claim about MEANING, not about matching. The fourth field
#: is carried into the relationship record so a disputed edge is argued about
#: in terms of what the verb was taken to mean.
_PATTERNS: Tuple[Tuple[str, str, bool, str], ...] = (
    (r"\bpartner(?:ed|ship|s|ing)?\s+with\b", AR.PARTNERS_WITH, True,
     "a stated partnership, of unstated commercial content"),
    (r"\b(?:strategic\s+)?alliance\s+with\b", AR.PARTNERS_WITH, True,
     "a stated alliance"),
    (r"\bcollaborat(?:es?|ed|ion|ing)\s+with\b", AR.PARTNERS_WITH, True,
     "a stated collaboration, which is weaker than a supply relationship"),
    # Interoperability. NOT dependence: two products can interoperate with no
    # money and no obligation between their makers.
    (r"\bintegrat(?:es?|ed|ion|ing)\s+with\b", AR.COMPLEMENTS, True,
     "products interoperate; this states no commercial relationship"),
    (r"\bavailable\s+(?:on|in|through)\s+the\b", AR.COMPLEMENTS, True,
     "a listing on another company's marketplace"),
    # Selection: the selector is buying, so the direction inverts.
    (r"\b(?:has\s+)?select(?:ed|s)\b", AR.SELLS_TO, False,
     "the selector is procuring, so the selected party is the seller"),
    (r"\b(?:has\s+)?chos(?:en|e)\b", AR.SELLS_TO, False,
     "the chooser is procuring, so the chosen party is the seller"),
    (r"\bdistribut(?:es?|ed|ion|ing)\s+(?:through|via)\b", AR.DISTRIBUTES,
     False, "the named party carries the subject's product to market"),
    (r"\bresell(?:er|s|ing)?\s+(?:of|for)\b", AR.DISTRIBUTES, False,
     "the named party resells the subject's product"),
    # `supplies`, the finite verb, only. `supply` and `supplying` collide
    # with "supply chain", and the first live measurement of this family
    # produced four edges to an actor called "Chain" because of it.
    (r"\bsupplies\s+(?:to\s+)?\b", AR.SUPPLIES, True,
     "the subject ships something the named party consumes"),
    (r"\bsupplier\s+(?:to|for)\b", AR.SUPPLIES, True,
     "a stated supply relationship"),
)
_COMPILED = tuple((re.compile(p, re.I), pred, left, meaning)
                  for p, pred, left, meaning in _PATTERNS)

#: Phrases that name a counterparty and state no relationship worth holding.
#: Counted, so "this family produced nothing" can be told apart from "this
#: family produced things we refused to round up".
_TOO_WEAK = re.compile(
    r"\b(?:uses?|using|works?\s+with|working\s+with|engag(?:es?|ed)\s+with|"
    r"together\s+with|alongside|in\s+conjunction\s+with)\b", re.I)

#: Words that pass the capitalised-token test and name nobody. Every one of
#: these came out of the first live measurement as an accepted edge:
#: "supply Chain", "across Europe", "our European customers".
_NOT_A_COMPANY = frozenset({
    "chain", "chains", "europe", "european", "america", "american", "asia",
    "asian", "africa", "african", "canada", "canadian", "india", "indian",
    "china", "chinese", "japan", "japanese", "germany", "german", "france",
    "french", "uk", "us", "usa", "eu", "emea", "apac", "latam", "global",
    "north", "south", "east", "west", "collaboration", "innovation",
    "technology", "solutions", "services", "customers", "communities",
    "community", "black", "women", "veterans", "students", "small",
    "the", "this", "these", "those", "their", "our", "its",
})

#: A real counterparty named in an 8,000-character release is named more than
#: once. A single-token name that appears exactly once is nearly always the
#: tail of a phrase the pattern cut in the wrong place.
MIN_MENTIONS_FOR_ONE_WORD_NAME = 2


def _plausible_counterparty(name: str, document_text: str) -> str:
    """Whether this string is a company, or the wreckage of a phrase.

    Returns "" when plausible, and the refusal reason otherwise, so the
    caller records WHICH filter rejected it rather than a single opaque
    count. The two filters fail in different ways and need different fixes.
    """
    tokens = name.split()
    if not tokens:
        return "counterparty_is_a_category"
    if all(t.lower().strip(".,") in _NOT_A_COMPANY for t in tokens):
        return "counterparty_is_a_common_noun_or_place"
    if len(tokens) == 1:
        occurrences = len(re.findall(r"\b" + re.escape(tokens[0]) + r"\b",
                                     document_text or ""))
        if occurrences < MIN_MENTIONS_FOR_ONE_WORD_NAME:
            return "one_word_name_appearing_once"
    return ""


#: The standing trailer every company release ends with. Positional: it is
#: identical across that company's releases, which is what makes it
#: boilerplate — not any phrase it happens to contain.
_ABOUT_TRAILER = re.compile(r"^\s*about\s+[A-Z]", re.I)

_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def _sentences(text: str) -> Tuple[str, ...]:
    out: List[str] = []
    for block in (text or "").splitlines():
        block = " ".join(block.split())
        if not block or _ABOUT_TRAILER.match(block):
            continue
        for piece in _SENTENCE.split(block):
            piece = piece.strip()
            if 30 <= len(piece) <= 600:
                out.append(piece)
    return tuple(out)


#: Conventional newsroom entry points, tried when a sitemap yields nothing.
#: Two of the first four companies measured had no usable sitemap, and a
#: source family that only works for companies with tidy XML is measuring the
#: sitemap rather than the family.
SEED_PATHS = ("/news", "/newsroom", "/press", "/press-releases", "/media",
              "/investors/news", "/about/news", "/en/news", "/blog")

#: An index page lists releases; a release states one. Extracting from the
#: index measures headlines and concludes the family is barren — which is
#: exactly what the first measurement of this family did, at 0.048/doc,
#: against pages averaging 700 characters. An article has a deeper path and
#: a slug with real words in it.
_ARTICLE_SLUG = re.compile(r"[a-z0-9]+(?:[-_][a-z0-9]+){2,}$")

#: A page this short is a shell, a redirect stub, or a listing. Nothing that
#: states a partnership is 400 characters long.
MIN_ARTICLE_CHARS = 900


def fetch(subject: str, aliases: Sequence[str], as_of: str = "", *,
          home_url: str = "", fetcher: Optional[Callable] = None,
          max_pages: int = MAX_PAGES_PER_SUBJECT
          ) -> Tuple[CS.Document, ...]:
    """Retrieve this company's own announcement ARTICLES, not its news index.

    Company-published, on the company's own domain, deliberately: a wire
    aggregator's rewrite of the same release loses the party that published
    it, and who published a claim is half of what makes it evidence.

    Two hops. The first finds index pages; the second follows them to the
    individual releases, which is where a counterparty is actually named.
    """
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
        if _is_newsroom(url):
            seeds.append(url)
    seeds.extend(home_url.rstrip("/") + path for path in SEED_PATHS)
    seeds = list(dict.fromkeys(seeds))[:len(SEED_PATHS) + 6]

    articles: List[str] = []
    pages: Dict[str, dict] = {}
    for url in seeds:
        result = read(url)
        if not (result or {}).get("ok"):
            continue
        parsed = P.parse_html(result.get("body") or result.get("text") or "")
        pages[url] = parsed
        for link in (parsed.get("links") or []):
            target = link if isinstance(link, str) else (link or {}).get(
                "href", "")
            target = _absolute(target, url)
            if not target or urlparse(target).hostname != host:
                continue
            if _is_article(target, seed=url):
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
        if len(text) < MIN_ARTICLE_CHARS:
            continue
        out.append(CS.Document(
            document_id=f"release:{url}", family=CS.PARTNERSHIP_RELEASE,
            subject=subject, title=str(parsed.get("title") or ""),
            text=text, url=url, published_at=as_of[:10],
            fields={"publisher_host": urlparse(url).hostname or ""}))
    return tuple(out)


def _is_newsroom(url: str) -> bool:
    path = (urlparse(url or "").path or "").lower()
    return bool(path) and any(n in path for n in NEWSROOM_NEEDLES)


def _absolute(target: str, base: str) -> str:
    from urllib.parse import urljoin
    if not target or target.startswith(("mailto:", "tel:", "#", "javascript:")):
        return ""
    return urljoin(base, target)


def _is_article(url: str, *, seed: str) -> bool:
    """Deeper than the index it was linked from, and slugged like a story."""
    path = (urlparse(url).path or "").rstrip("/")
    seed_path = (urlparse(seed).path or "").rstrip("/")
    if not _is_newsroom(url) or path == seed_path:
        return False
    if len([p for p in path.split("/") if p]) <= \
            len([p for p in seed_path.split("/") if p]):
        return False
    last = path.rsplit("/", 1)[-1].lower()
    return bool(_ARTICLE_SLUG.match(last))


def extract(document: CS.Document, subject: str, aliases: Sequence[str]
            ) -> Tuple[Tuple[AR.ActorRelationship, ...],
                       Dict[str, int], Dict[str, int]]:
    """Pull stated relationships out of one announcement, preserving strength.

    The subject side is the company that PUBLISHED the page, which the URL
    settles. A sentence alone cannot say which end of it the author is, and
    guessing is how "ASML responds to Infosys" got into a graph once.
    """
    refused: Dict[str, int] = {}
    counts: Dict[str, int] = {"named_actor_mentions": 0,
                              "relationship_candidates": 0,
                              "identity_resolved": 0}
    found: List[AR.ActorRelationship] = []
    seen: set = set()

    subject_name = _display_name(aliases, subject)
    for sentence in _sentences(document.text):
        matched = False
        for pattern, predicate, subject_is_left, meaning in _COMPILED:
            hit = pattern.search(sentence)
            if not hit:
                continue
            matched = True
            counts["relationship_candidates"] += 1
            tail = re.sub(r"^(?:the|a|an)\s+", "",
                          sentence[hit.end():].lstrip(" ,:"), flags=re.I)
            other = AR._ACTOR.match(tail)
            if not other:
                refused["no_named_counterparty"] = refused.get(
                    "no_named_counterparty", 0) + 1
                break
            counterparty = other.group(1).strip(" .,;:")
            if not AR.is_named_actor(counterparty):
                refused["counterparty_is_a_category"] = refused.get(
                    "counterparty_is_a_category", 0) + 1
                break
            counts["named_actor_mentions"] += 1
            implausible = _plausible_counterparty(counterparty, document.text)
            if implausible:
                refused[implausible] = refused.get(implausible, 0) + 1
                break
            # The counterparty must not be the subject under another name;
            # "Shopify partners with Shopify Payments" is one company.
            if CS.resolves_to(counterparty, list(aliases) + [subject]):
                refused["counterparty_is_the_subject"] = refused.get(
                    "counterparty_is_the_subject", 0) + 1
                break
            counts["identity_resolved"] += 1
            left, right = ((subject_name, counterparty) if subject_is_left
                           else (counterparty, subject_name))
            key = (left.lower(), predicate, right.lower())
            if key in seen:
                refused["duplicate_in_document"] = refused.get(
                    "duplicate_in_document", 0) + 1
                break
            try:
                found.append(AR.relationship(
                    subject_actor=left, predicate=predicate,
                    object_actor=right,
                    evidence_ids=(document.document_id,),
                    source_document=document.url,
                    subject_span=subject_name, object_span=counterparty,
                    relationship_span=f"{sentence[:240]} [{meaning}]",
                    epistemic_status=AR.OBSERVED,
                    valid_from=document.published_at,
                    created_at=document.published_at))
                seen.add(key)
            except AR.RelationshipRejected:
                refused["rejected_by_contract"] = refused.get(
                    "rejected_by_contract", 0) + 1
            break
        if not matched and _TOO_WEAK.search(sentence):
            # Named somebody, stated nothing holdable. Counted so the
            # difference between "found nothing" and "refused to round up"
            # stays visible.
            refused["states_no_commercial_relation"] = refused.get(
                "states_no_commercial_relation", 0) + 1
    return tuple(found), refused, counts


def _display_name(aliases: Sequence[str], subject: str) -> str:
    """The longest alias — the form a reader would recognise."""
    candidates = [a for a in aliases if len(a) >= 4]
    return max(candidates, key=len) if candidates else subject
