"""Independent reporting: discovered, verified, attributed. Never raises.

WHY THIS EXISTS. Measured on the prospect-100 pass (2026-11-09): 85 of 95
analysed companies had NO independent relevant origin. The only independent
channel was SEC full-text search for other registrants' filings, and private
companies -- most of the list -- are rarely named in filings. Every reading
for those companies rested on the company's own pages, so the product could
handle the gap honestly but never close it.

SEVERAL MECHANISMS, ONE CONTRACT. No single source is relied on:

  publisher feeds   trade publications' own per-tag / per-search RSS feeds,
                    ONLY for publishers whose robots.txt allows the path and
                    whose feed was verified to parse (see `PUBLISHERS`). A
                    publisher that refuses robots.txt is treated as refusing.
  wikipedia refs    the references of the company's Wikipedia article, found
                    through Wikidata and accepted ONLY when the Wikidata item's
                    official website is the company's own domain -- name
                    search alone matched "Jones Soda" for Soda.
  gdelt             the GDELT DOC API, paced to its published limit (one
                    request per 5 s, process-wide). From this machine it
                    answered 429 even to single paced requests on 2026-11-09,
                    so it is optional and its refusal is recorded, not hidden.

DISCOVERY IS NOT EVIDENCE. A feed item or a reference is a pointer. Every
article is fetched (robots-checked), read, and judged by the same relevance
adjudicator the filing channel uses before it becomes a candidate; a search
snippet is never quoted as if it were the article.

WHOSE ACCOUNT IS IT. A wire press release ("PRNewswire", "Business Wire",
"GlobeNewswire") is the company speaking through a distributor. It is marked
COMPANY_ISSUED and never counted as independent.
"""
from __future__ import annotations

import html as _html
import re
import threading
import time
import urllib.parse
import urllib.robotparser
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Callable, Dict, List, Optional, Sequence

CONTRACT = "independent_reporting.v1"
DISCOVERY_METHOD = "independent_reporting"

#: Articles fetched and judged per run. Each costs a request and a parse; the
#: approval step then chooses among them, so more than this buys little.
MAX_ARTICLES_FETCHED = 8
#: Pointers considered before fetching (feeds and references can be long).
MAX_POINTERS = 40
#: Oldest article worth reading for a CURRENT strategic reading.
MAX_AGE_DAYS = 3 * 365

_FEED_MIMES = ("application/rss+xml", "application/atom+xml",
               "application/xml", "text/xml")
_JSON_MIMES = ("application/json",)


@dataclass(frozen=True)
class Publisher:
    """A trade publication whose feeds were VERIFIED usable.

    `verified` records the probe that admitted it: robots.txt allows the feed
    path for our user agent AND the feed parsed with items. A publisher is
    added only by re-running that probe (`probe_publisher`), never by hand.
    """
    name: str
    host: str
    tag_feed: str = ""          # "/tag/{slug}/feed/"
    search_feed: str = ""       # "/?s={q}&feed=rss2"
    verified: str = ""


PUBLISHERS = (
    Publisher("SiliconANGLE", "siliconangle.com", "/tag/{slug}/feed/",
              "/?s={q}&feed=rss2",
              "2026-11-09: robots allow both paths; tag feeds returned 15 "
              "(Hammerspace), 15 (Reltio), 20 (Kaseya), 9 (Matillion) items"),
    Publisher("BetaKit", "betakit.com", "/tag/{slug}/feed/",
              "/?s={q}&feed=rss2",
              "2026-11-09: robots allow the search feed; 9 items for Auvik"),
    Publisher("Channel Insider", "www.channelinsider.com", "/tag/{slug}/feed/",
              "", "2026-11-09: robots allow; tag feed 10 items (Kaseya)"),
    Publisher("Help Net Security", "www.helpnetsecurity.com",
              "/tag/{slug}/feed/", "",
              "2026-11-09: robots allow; tag feed 10 (Kaseya), 3 (Hammerspace)"),
    Publisher("TechRepublic", "www.techrepublic.com", "", "/?s={q}&feed=rss2",
              "2026-11-09: robots allow; search feed 13 (Kaseya), 1 (Planful)"),
    Publisher("StorageReview", "www.storagereview.com", "",
              "/?s={q}&feed=rss2",
              "2026-11-09: robots allow; search feed 11 (Hammerspace), "
              "5 (Kaseya)"),
    Publisher("ZDNET", "www.zdnet.com", "", "/?s={q}&feed=rss2",
              "2026-11-09: robots allow; search feed returns a full page of "
              "loose matches, so items must name the subject"),
)

#: Hosts that are never independent reporting about a company, whatever
#: links to them: reference infrastructure, social platforms, archives.
_NOT_REPORTING = re.compile(
    r"(^|\.)(catalogue\.bnf|bnf|loc|viaf|isni|id\.loc|"
    r"wikipedia|wikimedia|wikidata|archive|web\.archive|"
    r"twitter|x|facebook|linkedin|youtube|instagram|github|crunchbase|"
    r"google|bing|doi|worldcat|jstor|opencorporates)\.", re.I)

#: Regulators publish the COMPANY's own filings. Those belong to the filing
#: channel, which decides whose account each one is; counted here, a 10-K
#: cited on Wikipedia became "independent reporting" (Verisk, CDW).
_REGULATORY = re.compile(
    r"(^|\.)(sec\.gov|sedarplus\.ca|sedar\.com|companieshouse\.gov\.uk|"
    r"edgar|federalregister\.gov)$", re.I)

#: The company speaking through a distributor.
_WIRE = re.compile(
    r"(\bPRNewswire\b|/PRNewswire/|\bPR Newswire\b|\(BUSINESS WIRE\)|"
    r"\bBusiness Wire\b|\bGLOBE NEWSWIRE\b|\bGlobeNewswire\b|"
    r"\bACCESSWIRE\b|\bNewsfile Corp\b|\bEIN Presswire\b)", re.I)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")


def _host(url: str) -> str:
    return (urllib.parse.urlparse(url or "").hostname or "").lower()


def _registrable(host: str) -> str:
    parts = (host or "").lower().split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def subject_terms(company: str, aliases: Sequence[str] = ()) -> List[str]:
    """Names that identify the subject in running text, longest first."""
    terms = {t.strip() for t in [company, *aliases] if t and len(t.strip()) >= 3}
    return sorted(terms, key=len, reverse=True)


def mentions_subject(text: str, company: str, aliases=()) -> bool:
    """True when the text names the subject as a proper noun.

    A one-word name is matched CASE-SENSITIVELY: "Soda" the company is a
    proper noun, "soda" the drink is not, and casefolding is how a generic
    word becomes a company mention.
    """
    body = text or ""
    for term in subject_terms(company, aliases):
        flags = 0 if (" " not in term and len(term) <= 12) else re.I
        if re.search(rf"(?<![\w-]){re.escape(term)}(?![\w-])", body, flags):
            return True
    return False


def _date(text: str) -> str:
    """ISO date from RSS/Atom/GDELT date text, or ""."""
    text = (text or "").strip()
    if not text:
        return ""
    try:
        return parsedate_to_datetime(text).date().isoformat()
    except (TypeError, ValueError):
        pass
    m = re.match(r"(\d{4})-?(\d{2})-?(\d{2})", text)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else ""


def parse_feed(xml_text: str) -> List[dict]:
    """RSS 2.0 or Atom items as {title, url, published, summary}."""
    items = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return items

    def local(tag):
        return tag.rsplit("}", 1)[-1]
    for node in root.iter():
        if local(node.tag) not in ("item", "entry"):
            continue
        rec = {"title": "", "url": "", "published": "", "summary": ""}
        for child in node:
            name = local(child.tag)
            if name == "title":
                rec["title"] = " ".join((child.text or "").split())
            elif name == "link":
                rec["url"] = (child.get("href") or child.text or "").strip()
            elif name in ("pubDate", "published", "updated") and \
                    not rec["published"]:
                rec["published"] = _date(child.text or "")
            elif name in ("description", "summary"):
                rec["summary"] = " ".join(_html.unescape(re.sub(
                    r"<[^>]+>", " ", child.text or "")).split())[:600]
        if rec["url"]:
            items.append(rec)
    return items


# ---------------------------------------------------------------------------
# polite access
# ---------------------------------------------------------------------------
class Robots:
    """robots.txt policy per host, cached for the run.

    Missing (404) allows; refused (401/403) or unreadable DISALLOWS -- a site
    that will not show us its rules has told us what we need to know.
    """

    def __init__(self, fetch_text: Callable[[str], dict], agent: str):
        self._fetch, self._agent, self._cache = fetch_text, agent, {}

    def allows(self, url: str) -> bool:
        host = _host(url)
        if not host:
            return False
        if host not in self._cache:
            result = self._fetch(f"https://{host}/robots.txt")
            code = result.get("status_code")
            if result.get("ok"):
                parser = urllib.robotparser.RobotFileParser()
                parser.parse(str(result.get("body") or "").splitlines())
                self._cache[host] = parser
            elif code == 404:
                self._cache[host] = True
            else:
                self._cache[host] = False
        policy = self._cache[host]
        if policy is True or policy is False:
            return policy
        return policy.can_fetch(self._agent, url)


#: OFF by default. From this host the DOC API answered 429 to single paced
#: requests (2026-11-09), and a paced, refused call cost the whole channel
#: its budget (verification started past its deadline and read 0 of 12
#: articles). Turn on where the deployment's address is not refused.
GDELT_ENABLED = False

_GDELT_LOCK = threading.Lock()
_GDELT_LAST = [0.0]
GDELT_MIN_INTERVAL_S = 5.5


# ---------------------------------------------------------------------------
# channels -> pointers
# ---------------------------------------------------------------------------
#: Articles kept per publisher. Spreads the budget across origins (one
#: publisher's account is one origin however many articles it writes) and
#: bounds the time spent pacing requests to a single host.
MAX_PER_PUBLISHER = 3


def _feed_pointers(company, aliases, fetch, robots, report) -> List[dict]:
    """Every admitted publisher's feeds, read CONCURRENTLY (one host each)."""
    import concurrent.futures as _cf
    parts = []
    with _cf.ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(_one_publisher, pub, company, aliases, fetch,
                               robots, report) for pub in PUBLISHERS]
        for fut in futures:
            try:
                parts.append(fut.result())
            except Exception:                            # noqa: BLE001
                report["rejection_reasons"]["FEED_CHANNEL_RAISED"] += 1
    return [p for part in parts for p in part]


def _one_publisher(pub, company, aliases, fetch, robots, report) -> List[dict]:
    out = []
    if True:
        paths = []
        if pub.tag_feed:
            paths.append(pub.tag_feed.format(slug=_slug(company)))
        if pub.search_feed:
            paths.append(pub.search_feed.format(
                q=urllib.parse.quote_plus(f'"{company}"')))
        for path in paths:
            # A TAG FEED is the publisher's own statement that the article
            # concerns the company, so its items are not re-filtered on their
            # title; a SEARCH feed matches words, so its items must name the
            # subject. Every article is relevance-judged on its full text
            # either way.
            tagged = bool(pub.tag_feed) and path == pub.tag_feed.format(
                slug=_slug(company))
            url = f"https://{pub.host}{path}"
            if not robots.allows(url):
                report["rejection_reasons"]["FEED_DISALLOWED_BY_ROBOTS"] += 1
                continue
            result = fetch(url, _FEED_MIMES)
            if not result.get("ok"):
                # COULD NOT LOOK is not FOUND NOTHING; say which.
                report["rejection_reasons"][
                    f"FEED_UNAVAILABLE_{result.get('status_code') or 'ERR'}"] += 1
                continue
            for item in parse_feed(str(result.get("body") or "")):
                if not tagged and not mentions_subject(
                        f"{item['title']} {item['summary']}", company, aliases):
                    report["rejection_reasons"]["FEED_ITEM_NOT_ABOUT_SUBJECT"] += 1
                    continue
                out.append(dict(item, publisher=pub.name,
                                channel="publisher_feed"))
        report["channels_attempted"].append(f"publisher_feed:{pub.host}")
    return out


def _wikipedia_pointers(company, domain, fetch_json, report) -> List[dict]:
    """References of the company's Wikipedia article, identity-checked."""
    report["channels_attempted"].append("wikipedia_references")
    if not domain:
        return []
    search = fetch_json(
        "https://www.wikidata.org/w/api.php?" + urllib.parse.urlencode(
            {"action": "wbsearchentities", "search": company,
             "language": "en", "type": "item", "limit": 5, "format": "json"}))
    if search is None:
        report["rejection_reasons"]["WIKIDATA_UNAVAILABLE"] += 1
        return []
    ids = [s.get("id") for s in search.get("search", [])][:5]
    if not ids:
        report["rejection_reasons"]["WIKIDATA_NO_MATCHING_NAME"] += 1
        return []
    ents = fetch_json(
        "https://www.wikidata.org/w/api.php?" + urllib.parse.urlencode(
            {"action": "wbgetentities", "ids": "|".join(ids),
             "props": "claims|sitelinks", "sitefilter": "enwiki",
             "format": "json"})) or {}
    title = ""
    want = _registrable(domain)
    for qid in ids:
        ent = (ents.get("entities") or {}).get(qid) or {}
        sites = []
        for claim in (ent.get("claims") or {}).get("P856", []):
            value = (((claim.get("mainsnak") or {}).get("datavalue") or {})
                     .get("value"))
            if isinstance(value, str):
                sites.append(_registrable(_host(value)))
        # THE IDENTITY GATE: the item's official website is the company's.
        if want in sites:
            title = ((ent.get("sitelinks") or {}).get("enwiki") or {}).get(
                "title", "")
            break
    if not title:
        report["rejection_reasons"]["WIKIDATA_NO_ITEM_WITH_THIS_WEBSITE"] += 1
        return []
    links = fetch_json(
        "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode(
            {"action": "query", "prop": "extlinks", "titles": title,
             "ellimit": 200, "format": "json"})) or {}
    out = []
    for page in ((links.get("query") or {}).get("pages") or {}).values():
        for link in page.get("extlinks", []):
            url = link.get("*") or link.get("url") or ""
            host = _host(url)
            if not url.startswith("http") or _NOT_REPORTING.search(host + "."):
                continue
            if _registrable(host) == want:
                continue                     # the company's own pages
            out.append({"title": "", "url": url, "published": "",
                        "summary": "", "publisher": host,
                        "channel": "wikipedia_references"})
    report["channels_successful"].append("wikipedia_references")
    return out


def _gdelt_pointers(company, fetch_json, report, *, sleeper=time.sleep,
                    clock=time.monotonic) -> List[dict]:
    report["channels_attempted"].append("gdelt")
    with _GDELT_LOCK:
        wait = GDELT_MIN_INTERVAL_S - (clock() - _GDELT_LAST[0])
        if wait > 0:
            sleeper(wait)
        data = fetch_json(
            "https://api.gdeltproject.org/api/v2/doc/doc?" +
            urllib.parse.urlencode({"query": f'"{company}"', "mode": "artlist",
                                    "maxrecords": 50, "format": "json",
                                    "timespan": "12months",
                                    "sourcelang": "english"}))
        _GDELT_LAST[0] = clock()
    if data is None:
        report["rejection_reasons"]["GDELT_UNAVAILABLE_OR_RATE_LIMITED"] += 1
        return []
    report["channels_successful"].append("gdelt")
    return [{"title": a.get("title", ""), "url": a.get("url", ""),
             "published": _date(a.get("seendate", "")), "summary": "",
             "publisher": a.get("domain", ""), "channel": "gdelt"}
            for a in (data.get("articles") or []) if a.get("url")]


# ---------------------------------------------------------------------------
# pointers -> verified candidates
# ---------------------------------------------------------------------------
def _normal_title(title: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", (title or "").lower()))[:90]


def dedupe(pointers: Sequence[dict]) -> List[dict]:
    """One pointer per URL, and one per story: a syndicated copy shares its
    title, and counting it twice would count one publisher's account twice."""
    seen_url, seen_title, out = set(), set(), []
    for p in pointers:
        url = p["url"].split("#")[0].rstrip("/")
        title = _normal_title(p.get("title", ""))
        if url in seen_url or (title and title in seen_title):
            continue
        seen_url.add(url)
        if title:
            seen_title.add(title)
        out.append(p)
    return out


def _too_old(published: str, today: str) -> bool:
    if not published or not today:
        return False
    try:
        from datetime import date
        return (date.fromisoformat(today[:10])
                - date.fromisoformat(published[:10])).days > MAX_AGE_DAYS
    except ValueError:
        return False


def needs_identity_anchor(company: str, text: str) -> bool:
    """Does the NAME alone fail to identify the company in this text?

    Decided from the text, not from a list of names: a one-word name that the
    same article also uses as an ordinary lowercase word ("ramp up", "a
    cube") collides with the language, and a short or all-capital name
    (BILL, IFS, KX) is an acronym or a word by construction. Distinctive
    names ("Hammerspace") are unaffected.
    """
    name = (company or "").strip()
    if not name or " " in name:
        return False
    if len(name) <= 4 or name.isupper():
        return True
    return bool(re.search(rf"(?<![\w-]){re.escape(name.lower())}(?![\w-])",
                          text or ""))


def identity_anchors(company: str, domain: str, aliases=()) -> List[str]:
    """Strings that name THIS company and nothing else: its domain, and any
    multi-word name it is known by."""
    out = []
    if domain:
        out.append(_registrable(domain))
    for name in (company, *aliases):
        core = re.sub(r",?\s+(inc|llc|ltd|corp|corporation|limited|plc|gmbh|"
                      r"co|company|holdings?)\.?$", "", (name or "").strip(),
                      flags=re.I)
        if " " in core.strip():
            out.append(core.strip())
    return [a for a in dict.fromkeys(out) if a]


def verify(pointer, *, company, domain, aliases, fetch, robots,
           report) -> Optional[dict]:
    """Fetch, read and judge one article. A candidate, or None with a reason."""
    from intent_engine.company_ingestion import relevance as REL
    from intent_engine.company_ingestion.parsing import parse_html

    url = pointer["url"]
    if domain and _registrable(_host(url)) == _registrable(domain):
        report["rejection_reasons"]["COMPANY_OWN_DOMAIN"] += 1
        return None
    if _REGULATORY.search(_host(url)):
        report["rejection_reasons"]["REGULATORY_FILING_NOT_REPORTING"] += 1
        return None
    if not robots.allows(url):
        report["rejection_reasons"]["ARTICLE_DISALLOWED_BY_ROBOTS"] += 1
        return None
    result = fetch(url, ())
    report["candidates_fetched"] += 1
    if not result.get("ok"):
        report["rejection_reasons"][
            f"FETCH_{result.get('failure_type') or 'FAILED'}".upper()] += 1
        return None
    final = result.get("final_url") or url
    page = parse_html(str(result.get("body") or ""))
    # A WIKIPEDIA REFERENCE IS ANY PAGE AN EDITOR CITED: measured on the
    # prospect-100 coverage run it admitted a national-library catalogue
    # (catalogue.bnf.fr) and investors' portfolio pages (oakhill.com,
    # amplify.la) as "independent reporting". An investor has an interest
    # in the company and a catalogue says nothing. A reference counts only
    # when the page carries its own publication date -- the mark of an
    # article -- which portfolio and catalogue pages do not.
    if pointer.get("channel") == "wikipedia_references" and not (
            page.get("modified_date") or page.get("published_date")):
        report["rejection_reasons"]["REFERENCE_NOT_A_DATED_ARTICLE"] += 1
        return None
    text = page.get("text") or page.get("text_content") or ""
    title = pointer.get("title") or page.get("title") or ""
    if needs_identity_anchor(company, text):
        anchors = identity_anchors(company, domain, aliases)
        if not any(a.lower() in text.lower() for a in anchors):
            report["rejection_reasons"]["AMBIGUOUS_NAME_NO_IDENTITY_ANCHOR"] += 1
            return None
    wire = bool(_WIRE.search(text[:4000]))
    verdict = REL.adjudicate({"text_content": text}, subject_name=company,
                             subject_domain=domain or "", aliases=aliases,
                             author_name=pointer.get("publisher", ""))
    if verdict["state"] not in (REL.DIRECTLY_RELEVANT,
                                REL.CONTEXTUALLY_RELEVANT):
        report["rejection_reasons"][f"RELEVANCE_{verdict['state']}"] += 1
        return None
    spans = [" ".join(str(s).split())[:800]
             for s in (verdict.get("counted_spans") or [])[:8]]
    publisher = pointer.get("publisher") or _host(final)
    return {
        "url": final,
        "source_type": "external_approved",
        "discovery_method": DISCOVERY_METHOD,
        "channel": pointer.get("channel", ""),
        "same_domain": False,
        # A wire release is the company's own account through a distributor.
        "source_class": "company_owned" if wire else "independent_reporting",
        "independence": ("COMPANY_ISSUED_VIA_WIRE" if wire
                         else "INDEPENDENT_OF_SUBJECT"),
        "evidence_family": ("company_announcement" if wire
                            else "independent_reporting"),
        "publisher": publisher,
        "published": pointer.get("published", ""),
        "title": title or final,
        "why_useful": f"{publisher} reports on {company}",
        "why_relevant": (f"an account of {company} by {publisher}, which it "
                         f"did not write" if not wire else
                         f"{company}'s own announcement, distributed by a "
                         f"newswire"),
        "availability": "UNVERIFIED",
        "relevance": verdict["state"],
        "relevance_reason": verdict.get("reason", ""),
        "excerpt": spans[0] if spans else "",
        "counted_spans": spans,
    }


def discover(*, company: str, domain: str = "", aliases: Sequence[str] = (),
             fetch: Callable, fetch_json: Callable,
             robots: Optional[Robots] = None, today: str = "",
             use_gdelt: Optional[bool] = None, use_wikipedia: bool = True,
             limit: int = MAX_ARTICLES_FETCHED,
             deadline: Optional[float] = None,
             clock=time.monotonic) -> dict:
    """Independent reporting about `company`: candidates plus the search record.

    `fetch(url, extra_mimes) -> {ok, status_code, body, final_url,
    failure_type}` and `fetch_json(url) -> dict | None` are injected, so the
    suite never touches the network. `deadline` is an absolute `clock()`
    value; past it, verification stops between articles.
    """
    report = {
        "contract": CONTRACT, "query": company,
        "channels_attempted": [], "channels_successful": [],
        "pointers_found": 0, "candidates_considered": 0,
        "candidates_fetched": 0, "candidates": [],
        "rejection_reasons": _Counter(), "independent_relevant_origins": 0,
        "budget_exhausted": False,
    }
    if not company:
        return _finish(report)
    robots = robots or Robots(lambda u: fetch(u, ("text/plain",)),
                              _agent())
    if use_gdelt is None:
        use_gdelt = GDELT_ENABLED
    # THE CHANNELS RUN SIDE BY SIDE. Sequentially, a slow or refused channel
    # spent the budget the verification step needed.
    import concurrent.futures as _cf
    jobs = {"FEED": lambda: _feed_pointers(company, aliases, fetch, robots,
                                           report)}
    if use_wikipedia:
        jobs["WIKIPEDIA"] = lambda: _wikipedia_pointers(company, domain,
                                                        fetch_json, report)
    if use_gdelt:
        jobs["GDELT"] = lambda: _gdelt_pointers(company, fetch_json, report)
    pointers = []
    with _cf.ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        futures = {name: pool.submit(job) for name, job in jobs.items()}
        for name, fut in futures.items():
            try:
                got = fut.result()
            except Exception:                            # noqa: BLE001
                report["rejection_reasons"][f"{name}_CHANNEL_RAISED"] += 1
                continue
            if name == "FEED" and got:
                report["channels_successful"].append("publisher_feed")
            pointers += got
    pointers = [p for p in dedupe(pointers) if not _too_old(
        p.get("published", ""), today)]
    report["pointers_found"] = len(pointers)
    # Newest first; undated pointers (references) after dated ones.
    pointers.sort(key=lambda p: p.get("published") or "", reverse=True)
    # AT MOST `MAX_PER_PUBLISHER` per publisher, then verified CONCURRENTLY
    # (different hosts in parallel; one host's requests stay paced).
    per_pub, chosen = {}, []
    for pointer in pointers[:MAX_POINTERS]:
        key = pointer.get("publisher") or _host(pointer["url"])
        if per_pub.get(key, 0) >= MAX_PER_PUBLISHER:
            continue
        per_pub[key] = per_pub.get(key, 0) + 1
        chosen.append(pointer)
        if len(chosen) >= limit:
            break

    def _check(pointer):
        if deadline is not None and clock() >= deadline:
            report["budget_exhausted"] = True
            return None
        report["candidates_considered"] += 1
        try:
            return verify(pointer, company=company, domain=domain,
                          aliases=aliases, fetch=fetch, robots=robots,
                          report=report)
        except Exception:                                # noqa: BLE001
            report["rejection_reasons"]["VERIFY_RAISED"] += 1
            return None

    import concurrent.futures as _cf
    with _cf.ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(_check, chosen))
    candidates, origins = [], set()
    for cand in results:
        if cand is None:
            continue
        candidates.append(cand)
        if cand["source_class"] == "independent_reporting":
            origins.add(_registrable(_host(cand["url"])))
    # MOST ABOUT THE SUBJECT FIRST, then newest. A run usually has one
    # independent slot, and measured on Hammerspace the newest article was a
    # summit round-up that mentions it twice, chosen over "Hammerspace nabs
    # $100M" because it was a month newer.
    candidates.sort(key=lambda c: (len(c.get("counted_spans") or []),
                                   c.get("relevance") == "DIRECTLY_RELEVANT",
                                   c.get("published") or ""), reverse=True)
    report["candidates"] = candidates
    report["independent_relevant_origins"] = len(origins)
    return _finish(report)


class _Counter(dict):
    def __missing__(self, key):
        return 0


def _finish(report: dict) -> dict:
    report["rejection_reasons"] = dict(report["rejection_reasons"])
    report["channels_attempted"] = list(dict.fromkeys(
        report["channels_attempted"]))
    report["channels_successful"] = list(dict.fromkeys(
        report["channels_successful"]))
    return report


def _agent() -> str:
    from intent_engine.company_ingestion.fetch import USER_AGENT
    return USER_AGENT


# ---------------------------------------------------------------------------
# production wiring
# ---------------------------------------------------------------------------
#: One request per host per this many seconds, process-wide. Measured: four
#: concurrent runs drew 429s from Wikidata and a publisher within minutes,
#: and a run that is refused learns nothing.
PER_HOST_INTERVAL_S = 1.2
_HOST_LOCK = threading.Lock()
_HOST_NEXT: Dict[str, float] = {}


def _polite(url: str, *, clock=time.monotonic, sleeper=time.sleep) -> None:
    host = _host(url)
    with _HOST_LOCK:
        now = clock()
        start = max(now, _HOST_NEXT.get(host, 0.0))
        _HOST_NEXT[host] = start + PER_HOST_INTERVAL_S
    if start > now:
        sleeper(start - now)


def live_fetchers():
    """(fetch, fetch_json) over the product's SSRF-guarded `safe_fetch`,
    paced per host."""
    import json as _json

    from intent_engine.company_ingestion.fetch import safe_fetch

    from intent_engine.company_ingestion.transient import RetryPolicy

    # NO RETRIES IN DISCOVERY. A refusal is recorded and the run moves on;
    # backing off inside a 15 s branch is how a 429 ate the whole budget.
    once = RetryPolicy(max_attempts=1)

    def fetch(url, extra_mimes=()):
        _polite(url)
        return safe_fetch(url, extra_mime_prefixes=tuple(extra_mimes),
                          accept_truncated=True, retry_policy=once,
                          timeout=6.0)

    def fetch_json(url):
        _polite(url)
        result = safe_fetch(url, extra_mime_prefixes=_JSON_MIMES,
                            retry_policy=once, timeout=6.0)
        if not result.get("ok"):
            return None
        try:
            return _json.loads(result.get("body") or "")
        except ValueError:
            return None
    return fetch, fetch_json


def probe_publisher(pub: Publisher, sample_company: str, *, fetch,
                    robots: Optional[Robots] = None) -> dict:
    """Re-run the admission probe for one publisher (used by a script)."""
    robots = robots or Robots(lambda u: fetch(u, ("text/plain",)), _agent())
    out = {"publisher": pub.name}
    for kind, tmpl in (("tag", pub.tag_feed), ("search", pub.search_feed)):
        if not tmpl:
            continue
        url = f"https://{pub.host}" + tmpl.format(
            slug=_slug(sample_company),
            q=urllib.parse.quote_plus(f'"{sample_company}"'))
        allowed = robots.allows(url)
        items = 0
        if allowed:
            result = fetch(url, _FEED_MIMES)
            items = len(parse_feed(str(result.get("body") or ""))) \
                if result.get("ok") else -1
        out[kind] = {"robots_allows": allowed, "items": items}
    return out
