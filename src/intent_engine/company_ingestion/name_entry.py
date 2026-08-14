"""Resolve a typed company NAME to something the pipeline can analyse.

WHY THIS EXISTS
---------------
The entry form used to require a website, which meant the user did the
identity resolution and the product did none. Asking for a URL is asking
somebody to know the answer before they ask the question.

Removing the requirement exposed the real gap: `entities.resolve_entity` is
precise and handles the case that matters most -- one name, several real
companies -- but its registry carries five entities, so every demo company
resolved UNKNOWN. The validation manifest carries a hundred with domains,
sectors, tickers and public/private status, and nothing was consulting it for
entry.

So resolution is a CHAIN, strongest signal first:

    1. a website, if the user gave one -- a domain names exactly one company,
       and they had to have that company in mind to type it;
    2. the entity registry, which alone can say AMBIGUOUS and offer choices;
    3. the validation manifest, for breadth;
    4. NOT_FOUND, which is a state with a next step, never a 400.

WHAT IT WILL NOT DO
-------------------
Invent a domain. `cloudflare.com` for "Cloudflare" is a good guess and
`acme.com` for "Acme Industrial Supply" is a bad one, and the code cannot
tell them apart -- a guessed domain sends the whole retrieval pipeline at
somebody else's website and returns a confident report about the wrong
company. Every domain here comes from a record.
"""
from __future__ import annotations

from typing import Any, Optional

from intent_engine.company_ingestion.entities import (AMBIGUOUS, UNKNOWN,
                                                      resolve_entity)

CONTRACT = "company_name_entry.v1"

EXACT_MATCH = "EXACT_MATCH"
HIGH_CONFIDENCE_MATCH = "HIGH_CONFIDENCE_MATCH"
AMBIGUOUS_COMPANY = "AMBIGUOUS_COMPANY"
#: The company was identified with certainty -- it is a filing registrant and
#: the regulator names it -- but no source here carries its web domain.
#:
#: This exists because the alternative states are both lies. COMPANY_NOT_FOUND
#: told a customer typing "Toyota Motor Corporation" that we could not
#: identify it, which is false: it is one of the most heavily documented
#: registrants there is. And resolving it with a guessed domain would send
#: retrieval at somebody else's website. So the truthful state is "we know
#: exactly who this is, and we need the one thing we do not have".
IDENTIFIED_NO_DOMAIN = "IDENTIFIED_NO_DOMAIN"
COMPANY_NOT_FOUND = "COMPANY_NOT_FOUND"
STATES = (EXACT_MATCH, HIGH_CONFIDENCE_MATCH, AMBIGUOUS_COMPANY,
          IDENTIFIED_NO_DOMAIN, COMPANY_NOT_FOUND)


class NameEntry:
    """What a typed name resolved to, and how confidently."""

    __slots__ = ("state", "company_name", "website", "company_id", "ticker",
                 "country", "sector", "public_private", "choices", "reason",
                 "source")

    def __init__(self, state, *, company_name="", website="", company_id="",
                 ticker="", country="", sector="", public_private="",
                 choices=(), reason="", source=""):
        self.state = state
        self.company_name = company_name
        self.website = website
        self.company_id = company_id
        self.ticker = ticker
        self.country = country
        self.sector = sector
        self.public_private = public_private
        self.choices = tuple(choices)
        self.reason = reason
        self.source = source

    @property
    def resolved(self) -> bool:
        return self.state in (EXACT_MATCH, HIGH_CONFIDENCE_MATCH)

    def as_dict(self) -> dict:
        return {"contract": CONTRACT, "state": self.state,
                "company_name": self.company_name, "website": self.website,
                "company_id": self.company_id, "ticker": self.ticker,
                "country": self.country, "sector": self.sector,
                "public_private": self.public_private,
                "reason": self.reason, "source": self.source,
                "choices": list(self.choices)}


#: Corporate furniture. Stripped before comparing, so "Agnico Eagle" can meet
#: "Agnico Eagle Mines Limited" without "Limited" being treated as a word the
#: user forgot.
_SUFFIXES = frozenset({
    "inc", "inc.", "incorporated", "corp", "corp.", "corporation", "co",
    "co.", "company", "ltd", "ltd.", "limited", "plc", "llc", "lp", "nv",
    "n.v.", "sa", "s.a.", "ag", "se", "group", "holdings", "holding",
    "the", "&", "and",
})


def _words(text: str):
    out = []
    for raw in str(text or "").lower().replace(",", " ").split():
        word = raw.strip(".,&")
        if word and word not in _SUFFIXES:
            out.append(word)
    return out


def _initialism(text: str) -> str:
    return "".join(w[0] for w in _words(text))


def _manifest_candidates(man, typed: str):
    """Companies a typed short name could mean, by two STATED rules.

    Neither rule guesses. A leading-word match is what a person does when
    they say "Agnico Eagle" for "Agnico Eagle Mines Limited"; an initialism
    is what they do when they say "AMD". Both are checked against every
    company, and a name matching more than one is returned as AMBIGUOUS
    rather than narrowed -- picking one produces a confident report about
    the wrong company, which is the failure mode this whole path exists to
    avoid.
    """
    typed_words = _words(typed)
    if not typed_words:
        return []
    typed_initials = "".join(typed_words) if len(typed_words) == 1 else ""
    hits = []
    for c in man.companies:
        canonical = _words(c.canonical_name)
        if not canonical:
            continue
        # Rule 1: the typed words are the leading words of the legal name.
        if len(typed_words) <= len(canonical) \
                and canonical[:len(typed_words)] == typed_words:
            hits.append(c)
            continue
        # Rule 2: a single typed token is the legal name's initialism.
        if typed_initials and len(typed_initials) >= 2 \
                and _initialism(c.canonical_name) == typed_initials:
            hits.append(c)
    return hits


def _manifest():
    try:
        from intent_engine.validation import manifest as M
        return M.load()
    except Exception:                                       # noqa: BLE001
        # A manifest that cannot be read is not a company that does not
        # exist. The chain simply loses one link and says NOT_FOUND, which
        # is recoverable, rather than claiming the company is unknown.
        return None


#: The SEC lookup is the only source here that touches the network, so it is
#: OFF unless a deployment turns it on. A resolver that silently makes an
#: outbound call every time an unrecognised name is typed is not something a
#: test suite or an offline run should discover by getting slower.
_REGISTRANT_LOOKUP_ENABLED = False

#: Resolved names, so a repeated entry costs nothing. The SEC's ticker table
#: is one ~1MB fetch and a registrant's identity does not change between two
#: page loads.
_REGISTRANT_CACHE: dict = {}


def enable_registrant_lookup(enabled: bool = True) -> None:
    """Turn the SEC registrant source on. Called by the web app at startup."""
    global _REGISTRANT_LOOKUP_ENABLED
    _REGISTRANT_LOOKUP_ENABLED = bool(enabled)


def _registrant(company_name: str):
    """{cik, title, ticker} for a filer of this name, or None. Never raises."""
    if not _REGISTRANT_LOOKUP_ENABLED or not company_name:
        return None
    key = company_name.strip().lower()
    if key in _REGISTRANT_CACHE:
        return _REGISTRANT_CACHE[key]
    try:
        from intent_engine.company_ingestion.edgar import resolve_cik
        found = resolve_cik(company_name)
    except Exception:                                       # noqa: BLE001
        found = None
    _REGISTRANT_CACHE[key] = found
    return found


def resolve(company_name: str = "", website: str = "") -> NameEntry:
    """Resolve typed entry. Never raises, never invents a domain."""
    company_name = " ".join(str(company_name or "").split())
    website = str(website or "").strip()

    # 1 + 2. The registry. It owns AMBIGUOUS, which no other source can
    # express, so it is consulted even when a website was supplied.
    entity = resolve_entity(company_name=company_name, website=website)
    if entity.status == AMBIGUOUS:
        return NameEntry(
            AMBIGUOUS_COMPANY, company_name=company_name,
            choices=[{"entity_id": c.entity_id, "legal_name": c.legal_name,
                      "describe": c.describe(), "note": c.ambiguity_notes}
                     for c in entity.choices],
            reason=entity.reason, source="entity registry")
    if entity.resolved:
        profile = entity.profile
        return NameEntry(
            EXACT_MATCH, company_name=profile.legal_name,
            website=website or f"https://{profile.primary_domain}",
            country=getattr(profile, "country", ""),
            reason="matched the curated entity registry",
            source="entity registry")

    # A website the registry does not know is still a usable identity: the
    # user named the company by the strongest identifier there is.
    if website:
        return NameEntry(
            HIGH_CONFIDENCE_MATCH, company_name=company_name, website=website,
            reason="identified by the website supplied",
            source="user-supplied domain")

    # 3. The validation manifest -- a hundred companies with real domains.
    man = _manifest()
    row = man.resolve(name=company_name) if man is not None else None
    if row is None and man is not None:
        # The legal name did not match. A CEO types the name they know --
        # "AMD", "Agnico Eagle" -- and zero of the hundred manifest entries
        # carry an alias, so the exact-name lookup misses precisely the
        # forms people actually use.
        hits = _manifest_candidates(man, company_name)
        if len(hits) == 1:
            row = hits[0]
        elif len(hits) > 1:
            return NameEntry(
                AMBIGUOUS_COMPANY, company_name=company_name,
                choices=[{"entity_id": c.company_id,
                          "legal_name": c.canonical_name,
                          "describe": f"{c.sector or 'company'}, "
                                      f"{c.country or 'unknown country'}"
                                      f"{', ' + c.ticker if c.ticker else ''}",
                          "note": f"{c.public_private or ''}".lower()}
                         for c in hits],
                reason=(f"{len(hits)} companies in the register begin with "
                        f"that name"),
                source="validation manifest")
    if row is not None and row.domain:
        return NameEntry(
            HIGH_CONFIDENCE_MATCH, company_name=row.canonical_name,
            website=f"https://{row.domain}", company_id=row.company_id,
            ticker=row.ticker or "", country=row.country or "",
            sector=row.sector or "", public_private=row.public_private or "",
            reason="matched the company validation manifest",
            source="validation manifest")

    # 4. The SEC registrant table -- every filer, not a curated hundred.
    #
    # WHY IT IS LAST AND WHY IT IS HERE AT ALL. The three sources above carry
    # about 105 companies between them, so every other real company on earth
    # came back COMPANY_NOT_FOUND. Sixteen of the twenty-six companies the
    # market engine publishes live intelligence for -- Toyota, Vale, ASML,
    # Infosys -- could not be typed into the product that was analysing them.
    #
    # It is last because it can say neither AMBIGUOUS nor a domain, and both
    # of those are worth more than breadth when a source has them.
    filer = _registrant(company_name)
    if filer:
        # EDGAR titles carry filing-index artifacts -- "TOYOTA MOTOR CORP/"
        # ends in a slash because the index path did. Strip the punctuation
        # the registrant did not put in its own name; leave the casing, which
        # is how the registrant is actually recorded.
        title = str(filer.get("title") or "").strip().rstrip("/ .,-").strip()
        return NameEntry(
            IDENTIFIED_NO_DOMAIN, company_name=title or company_name,
            ticker=filer.get("ticker") or "",
            company_id=str(filer.get("cik") or ""),
            reason=("identified as a filing registrant with the SEC, which "
                    "records no web domain; supplying the website is what "
                    "lets the analysis read the company's own material"),
            source="SEC registrant table")

    return NameEntry(
        COMPANY_NOT_FOUND, company_name=company_name,
        reason=("no company by that name is in the register; it may be "
                "privately held, spelled differently in its filings, or not "
                "yet analysed here"),
        source="none")
