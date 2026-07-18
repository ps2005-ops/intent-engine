"""Headline sourcing — item 3 of docs/BA_ACCELERATION_PROPOSAL.md, APPROVED
2026-07-18 with the proposed feed allowlist (Reuters Business, AP Business,
Yahoo Finance market headlines).

Design, per the approved spec:
- RSS only, fixed allowlist, no vendor, ZERO model calls — selection is
  deterministic code (recency filter <=7 days, dedupe by normalized title,
  top-K by keyword-overlap score against a fixed regime vocabulary,
  deterministic tie-breaks).
- Provenance: every selected headline carries (feed name, URL, published
  date, fetch timestamp) for the report header.
- Degradation: a dead/unreachable feed is a warning, never a crash; zero
  qualifying headlines means the caller runs numeric-only (the existing
  correct-silence path) — a stale or fabricated headline is never produced.
- stdlib parsing only (xml.etree + email.utils) — no new dependencies,
  per house rule.

Honest note on the allowlist, recorded rather than glossed over: as of
2026-07-18 the Yahoo feed was verified live (application/xml). The Reuters
feed URL below is the historical public one and could NOT be verified from
the implementing sandbox (fetch blocked); AP likewise unverified. Both are
kept exactly as approved, and the dead-feed degradation path is what makes
that safe — but if the first live runs warn on them persistently, swapping
URLs is a human allowlist decision, not something this module does itself.
"""

from __future__ import annotations

import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Dict, List, NamedTuple, Optional, Sequence, Tuple

# --- approved allowlist (change requires a new written decision) ------------

FEED_ALLOWLIST: Tuple[Tuple[str, str], ...] = (
    ("Reuters Business", "https://feeds.reuters.com/reuters/businessNews"),
    ("AP Business", "https://apnews.com/hub/business?output=rss"),
    ("Yahoo Finance", "https://finance.yahoo.com/news/rssindex"),
)

RECENCY_DAYS = 7
DEFAULT_K = 3
FETCH_TIMEOUT_SECONDS = 15

# Fixed vocabulary: regime/market terms a relevant headline plausibly
# contains. Deterministic constant — scoring is a word-overlap count, not a
# model call. Widening this list is a code change reviewed like any other.
REGIME_VOCAB: Tuple[str, ...] = (
    "fed", "rate", "rates", "yield", "yields", "treasury", "bond", "bonds",
    "inflation", "cpi", "unemployment", "jobs", "payrolls", "labor",
    "recession", "curve", "spread", "credit", "default", "stocks", "equities",
    "market", "markets", "selloff", "rally", "drawdown", "volatility", "vix",
    "earnings", "gdp", "dollar", "oil", "tariff", "tariffs", "hike", "cut",
)

_WORD_RE = re.compile(r"[a-z']+")
# Dedupe keeps digits: "CPI rises 3.1%" and "CPI rises 2.9%" are different
# headlines, not duplicates. Scoring still uses _WORD_RE (vocab is letters-only).
_NORM_RE = re.compile(r"[a-z0-9']+")


class Headline(NamedTuple):
    title: str
    feed_name: str
    feed_url: str
    link: Optional[str]
    published: Optional[str]  # ISO date
    score: int
    fetched_at: str  # ISO timestamp


def _normalize_title(title: str) -> str:
    return " ".join(_NORM_RE.findall(title.lower()))


def score_title(title: str) -> int:
    words = set(_WORD_RE.findall(title.lower()))
    return len(words & set(REGIME_VOCAB))


def _parse_datetime(text: Optional[str]) -> Optional[datetime]:
    if not text:
        return None
    text = text.strip()
    try:  # RFC-822 (RSS pubDate)
        dt = parsedate_to_datetime(text)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        pass
    try:  # ISO-8601 (Atom)
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _strip_ns(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_feed(xml_text: str) -> List[Dict[str, Optional[str]]]:
    """RSS 2.0 <item> and Atom <entry> — title / link / published only.
    Malformed XML returns [] (caller warns); a malformed single entry is
    skipped, never fatal."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    entries = []
    for el in root.iter():
        if _strip_ns(el.tag) not in ("item", "entry"):
            continue
        title = link = published = None
        for child in el:
            tag = _strip_ns(child.tag)
            if tag == "title" and child.text:
                title = child.text.strip()
            elif tag == "link":
                link = (child.text or "").strip() or child.attrib.get("href")
            elif tag in ("pubDate", "published", "updated") and child.text:
                published = published or child.text.strip()
        if title:
            entries.append({"title": title, "link": link, "published": published})
    return entries


def select_headlines(
    feed_payloads: Sequence[Tuple[str, str, str]],  # (feed_name, feed_url, xml_text)
    as_of: date,
    k: int = DEFAULT_K,
    fetched_at: Optional[str] = None,
) -> List[Headline]:
    """Pure, deterministic selection. Qualifying = published within
    RECENCY_DAYS of as_of (entries with NO parseable date are excluded —
    an undated headline can't prove it isn't stale) AND vocab score >= 1.
    Order: score desc, published desc, normalized title asc. Dedupe by
    normalized title, first (i.e. best-ranked) occurrence wins."""
    fetched_at = fetched_at or datetime.now(timezone.utc).isoformat()
    cutoff = as_of - timedelta(days=RECENCY_DAYS)
    scored: List[Headline] = []
    for feed_name, feed_url, xml_text in feed_payloads:
        for entry in parse_feed(xml_text):
            pub_dt = _parse_datetime(entry["published"])
            if pub_dt is None:
                continue
            pub_date = pub_dt.date()
            if pub_date < cutoff or pub_date > as_of:
                continue
            s = score_title(entry["title"])
            if s < 1:
                continue
            scored.append(Headline(
                title=entry["title"], feed_name=feed_name, feed_url=feed_url,
                link=entry["link"], published=pub_date.isoformat(),
                score=s, fetched_at=fetched_at,
            ))

    scored.sort(key=lambda h: (-h.score, _reverse_date_key(h.published), _normalize_title(h.title)))

    selected: List[Headline] = []
    seen = set()
    for h in scored:
        key = _normalize_title(h.title)
        if key in seen:
            continue
        seen.add(key)
        selected.append(h)
        if len(selected) >= k:
            break
    return selected


def _reverse_date_key(iso_date: str) -> int:
    """Newer first inside an ascending sort: negate the ordinal."""
    return -date.fromisoformat(iso_date).toordinal()


def fetch_feeds(
    allowlist: Sequence[Tuple[str, str]] = FEED_ALLOWLIST,
    timeout: int = FETCH_TIMEOUT_SECONDS,
) -> List[Tuple[str, str, str]]:
    """Live fetcher (<= len(allowlist) fetches per run, per the approved
    budget). A failed feed warns and is omitted — never fatal, never
    retried within a run."""
    payloads = []
    for name, url in allowlist:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "intent-engine-headline-feed/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payloads.append((name, url, resp.read().decode("utf-8", errors="replace")))
        except Exception as exc:  # noqa: BLE001 — any transport failure degrades, never crashes
            print(f"WARNING: feed {name!r} ({url}) unavailable ({exc.__class__.__name__}: {exc}) -- omitted.")
    return payloads


def render_provenance(selected: Sequence[Headline], as_of: date) -> str:
    lines = [f"HEADLINE SOURCES -- selected {len(selected)} of top-{DEFAULT_K}, as of {as_of.isoformat()}",
             "-" * 70]
    if not selected:
        lines.append("No qualifying headlines (recent + regime-relevant) -- numeric-only mode, "
                     "per the approved degradation rule. Nothing stale or fabricated was substituted.")
    for h in selected:
        lines.append(f'- "{h.title}" [{h.feed_name}, published {h.published}, fetched {h.fetched_at}]')
        lines.append(f"  {h.link or h.feed_url}")
    return "\n".join(lines)
