"""Known-entity registry and bounded official-source fallback.

WHY THIS EXISTS
---------------
"Sony" broke the product in two distinct ways at once:

1. IDENTITY. A large multinational is not its US operating subsidiary and not
   whichever legal entity happens to file a document. `sony.com` returning 403
   left the run with a single SEC 6-K, and the report then described Sony as
   though that one filing were the company. Resolving a name to *an* entity is
   not the same as resolving it to the RIGHT entity.

2. REACH. When the primary domain refuses automated access, generic path
   guessing has nothing left to guess. A multinational publishes an enormous
   amount of official material — investor relations, earnings releases, annual
   and integrated reports, corporate strategy, newsroom, segment pages — most
   of it at stable, well-known URLs that are *not* derivable from the homepage.

So this module holds two things, both deterministic and offline:

- a small registry of entities we can state facts about with confidence, each
  carrying its canonical legal name, common name, country, domains, listing and
  regulatory identifiers, and its curated official sources; and
- the resolution rules that turn user input into either ONE entity, an explicit
  ambiguity that the user must settle, or an honest "unknown".

It NEVER guesses between a parent and a subsidiary. Silently choosing the
subsidiary is precisely the failure this replaces: the answer looks confident
and is wrong, which is worse than asking.

Nothing here fetches anything. Every URL is a *candidate* that still passes
through the ordinary approval + SSRF-guarded retrieval path.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

ENTITY_REGISTRY_VERSION = "ci_entities.v1"

# --- resolution outcomes -----------------------------------------------------
RESOLVED = "RESOLVED"
AMBIGUOUS = "AMBIGUOUS"
UNKNOWN = "UNKNOWN"

# --- source authority (how much weight a source can carry) -------------------
# The company speaking about itself in a regulated or investor context is the
# strongest non-regulatory evidence; marketing pages are weaker; a subsidiary's
# site speaks only for the subsidiary unless it is clearly attributed.
AUTHORITY_REGULATORY = "regulatory_filing"
AUTHORITY_OFFICIAL_PRIMARY = "official_primary"
AUTHORITY_OFFICIAL_SECONDARY = "official_secondary"
AUTHORITY_SUBSIDIARY_OFFICIAL = "subsidiary_official"

# --- entity relationship (whose voice is this, relative to the subject) ------
REL_SELF = "self"
REL_SUBSIDIARY = "subsidiary"
REL_PARENT = "parent"
REL_LISTING = "listing_or_adr"

_TOKEN = re.compile(r"[a-z0-9]+")
_LEGAL_SUFFIXES = {
    "inc", "llc", "ltd", "limited", "co", "corp", "corporation", "company",
    "plc", "sa", "nv", "ag", "gmbh", "kk", "kabushiki", "kaisha", "group",
    "holdings", "holding", "the",
}


def _tokens(text: str) -> tuple:
    return tuple(t for t in _TOKEN.findall((text or "").lower())
                 if t not in _LEGAL_SUFFIXES)


def _host(url: str) -> str:
    host = (urlparse(url if "//" in (url or "") else f"//{url}").hostname
            or "").lower()
    return host[4:] if host.startswith("www.") else host


@dataclass(frozen=True)
class OfficialSource:
    """One curated, official URL for an entity, classified before use."""
    url: str
    kind: str                    # corporate | investor | earnings | ...
    title: str
    authority: str
    entity_relationship: str = REL_SELF
    note: str = ""

    def as_dict(self) -> dict:
        return {"url": self.url, "kind": self.kind, "title": self.title,
                "authority": self.authority,
                "entity_relationship": self.entity_relationship,
                "note": self.note}


@dataclass(frozen=True)
class EntityProfile:
    """A company we can name precisely, with its official publishing surface."""
    entity_id: str
    legal_name: str
    common_name: str
    country: str
    primary_domain: str
    aliases: tuple = ()
    ir_domain: str = ""
    # (exchange, ticker) pairs — a multinational is usually listed twice.
    listings: tuple = ()
    sec_relationship: str = ""       # e.g. "foreign private issuer (20-F/6-K)"
    sec_cik: str = ""
    parent_entity_id: str = ""
    identity_confidence: str = "HIGH"
    ambiguity_notes: str = ""
    official_sources: tuple = field(default_factory=tuple)
    # Sibling/child entities a bare common name could also mean.
    disambiguation_group: str = ""

    # -- derived ------------------------------------------------------------
    @property
    def domains(self) -> tuple:
        seen, out = set(), []
        for d in (self.primary_domain, self.ir_domain):
            host = _host(d)
            if host and host not in seen:
                seen.add(host)
                out.append(host)
        for source in self.official_sources:
            host = _host(source.url)
            if host and host not in seen:
                seen.add(host)
                out.append(host)
        return tuple(out)

    def as_dict(self) -> dict:
        return {
            "entity_id": self.entity_id,
            "legal_name": self.legal_name,
            "common_name": self.common_name,
            "country": self.country,
            "primary_domain": self.primary_domain,
            "ir_domain": self.ir_domain,
            "listings": [{"exchange": e, "ticker": t} for e, t in
                         self.listings],
            "sec_relationship": self.sec_relationship,
            "sec_cik": self.sec_cik,
            "parent_entity_id": self.parent_entity_id,
            "identity_confidence": self.identity_confidence,
            "ambiguity_notes": self.ambiguity_notes,
            "aliases": list(self.aliases),
            "official_sources": [s.as_dict() for s in self.official_sources],
            "registry_version": ENTITY_REGISTRY_VERSION,
        }

    def describe(self) -> str:
        """One plain sentence a non-technical reader can check."""
        listing = ", ".join(f"{e}: {t}" for e, t in self.listings)
        bits = [f"{self.legal_name} ({self.country})"]
        if listing:
            bits.append(f"listed as {listing}")
        return " — ".join(bits)


# --- the registry ------------------------------------------------------------
# Deliberately small. An entity earns a place here only when we can state its
# canonical identity and official sources without guessing. Everything else
# flows through ordinary discovery, which is the honest default.

_SONY_GROUP = EntityProfile(
    entity_id="sony-group",
    legal_name="Sony Group Corporation",
    common_name="Sony",
    country="Japan",
    primary_domain="sony.com",
    aliases=("sony group", "sony group corporation", "sony corporation",
             "sony corp", "ソニーグループ株式会社", "sony kk"),
    ir_domain="sony.com",
    listings=(("TSE", "6758"), ("NYSE", "SONY")),
    sec_relationship=(
        "Foreign private issuer: files an annual report on Form 20-F and "
        "furnishes interim reports on Form 6-K. Its NYSE listing is an "
        "American Depositary Receipt, not a domestic common-stock listing, so "
        "there is no 10-K or 10-Q."),
    sec_cik="0000313838",
    disambiguation_group="sony",
    ambiguity_notes=(
        "\"Sony\" alone is ambiguous. Sony Group Corporation is the Japanese "
        "parent; PlayStation is Sony Interactive Entertainment; consumer "
        "electronics in the US is Sony Electronics Inc.; there are also Sony "
        "Pictures and Sony Music entities. A statement about one is not a "
        "statement about the group."),
    official_sources=(
        OfficialSource(
            "https://www.sony.com/en/SonyInfo/CorporateInfo/",
            "corporate", "Sony Group — corporate information",
            AUTHORITY_OFFICIAL_PRIMARY),
        OfficialSource(
            "https://www.sony.com/en/SonyInfo/IR/",
            "investor", "Sony Group — investor relations",
            AUTHORITY_OFFICIAL_PRIMARY),
        OfficialSource(
            "https://www.sony.com/en/SonyInfo/IR/library/presen/er/",
            "earnings", "Sony Group — earnings releases",
            AUTHORITY_OFFICIAL_PRIMARY),
        OfficialSource(
            "https://www.sony.com/en/SonyInfo/IR/library/report/",
            "annual_report", "Sony Group — annual and integrated reports",
            AUTHORITY_OFFICIAL_PRIMARY),
        OfficialSource(
            "https://www.sony.com/en/SonyInfo/csr/library/",
            "integrated_report", "Sony Group — sustainability/integrated "
                                 "reporting library",
            AUTHORITY_OFFICIAL_SECONDARY),
        OfficialSource(
            "https://www.sony.com/en/SonyInfo/News/",
            "newsroom", "Sony Group — official newsroom",
            AUTHORITY_OFFICIAL_SECONDARY),
        OfficialSource(
            "https://www.sony.com/en/SonyInfo/CorporateInfo/Data/",
            "segment", "Sony Group — business segments and financial data",
            AUTHORITY_OFFICIAL_PRIMARY),
        OfficialSource(
            "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany"
            "&CIK=0000313838&type=20-F&dateb=&owner=include&count=10",
            "filing", "SEC EDGAR — Sony Group Form 20-F annual reports",
            AUTHORITY_REGULATORY, REL_LISTING,
            note="ADR issuer filings; annual 20-F carries the business "
                 "description, 6-K carries interim announcements."),
    ),
)

_SONY_INTERACTIVE = EntityProfile(
    entity_id="sony-interactive-entertainment",
    legal_name="Sony Interactive Entertainment LLC",
    common_name="Sony Interactive Entertainment",
    country="United States / Japan",
    primary_domain="sonyinteractive.com",
    aliases=("sony interactive", "sony interactive entertainment",
             "playstation", "sie"),
    parent_entity_id="sony-group",
    disambiguation_group="sony",
    identity_confidence="HIGH",
    ambiguity_notes=(
        "A wholly-owned subsidiary of Sony Group Corporation covering the "
        "PlayStation business. It does not file separately with the SEC and "
        "its results appear inside the group's Game & Network Services "
        "segment."),
    official_sources=(
        OfficialSource(
            "https://www.sonyinteractive.com/en/",
            "corporate", "Sony Interactive Entertainment — corporate site",
            AUTHORITY_SUBSIDIARY_OFFICIAL, REL_SELF),
        OfficialSource(
            "https://www.sonyinteractive.com/en/news/",
            "newsroom", "Sony Interactive Entertainment — newsroom",
            AUTHORITY_SUBSIDIARY_OFFICIAL, REL_SELF),
        OfficialSource(
            "https://www.sony.com/en/SonyInfo/IR/",
            "investor", "Sony Group investor relations (parent)",
            AUTHORITY_OFFICIAL_PRIMARY, REL_PARENT,
            note="Segment results for PlayStation are reported by the parent, "
                 "not by this entity."),
    ),
)

_SONY_ELECTRONICS = EntityProfile(
    entity_id="sony-electronics",
    legal_name="Sony Electronics Inc.",
    common_name="Sony Electronics",
    country="United States",
    primary_domain="electronics.sony.com",
    aliases=("sony electronics", "sony electronics inc",
             "sony north america"),
    parent_entity_id="sony-group",
    disambiguation_group="sony",
    identity_confidence="HIGH",
    ambiguity_notes=(
        "The US electronics sales and marketing subsidiary of Sony Group "
        "Corporation. It is not the group and not the manufacturer of record "
        "for every Sony product line."),
    official_sources=(
        OfficialSource(
            "https://electronics.sony.com/",
            "corporate", "Sony Electronics — US product site",
            AUTHORITY_SUBSIDIARY_OFFICIAL, REL_SELF),
        OfficialSource(
            "https://www.sony.com/en/SonyInfo/CorporateInfo/",
            "corporate", "Sony Group corporate information (parent)",
            AUTHORITY_OFFICIAL_PRIMARY, REL_PARENT),
    ),
)

_PALANTIR = EntityProfile(
    entity_id="palantir",
    legal_name="Palantir Technologies Inc.",
    common_name="Palantir",
    country="United States",
    primary_domain="palantir.com",
    aliases=("palantir", "palantir technologies", "palantir technologies inc"),
    ir_domain="investors.palantir.com",
    listings=(("NASDAQ", "PLTR"),),
    sec_relationship="US domestic filer: Form 10-K annual, 10-Q quarterly.",
    sec_cik="0001321655",
    official_sources=(
        OfficialSource("https://www.palantir.com/platforms/foundry/",
                       "segment", "Palantir — Foundry platform",
                       AUTHORITY_OFFICIAL_PRIMARY),
        OfficialSource("https://www.palantir.com/platforms/gotham/",
                       "segment", "Palantir — Gotham platform",
                       AUTHORITY_OFFICIAL_PRIMARY),
        OfficialSource("https://www.palantir.com/platforms/aip/",
                       "segment", "Palantir — AIP platform",
                       AUTHORITY_OFFICIAL_PRIMARY),
        OfficialSource("https://investors.palantir.com/",
                       "investor", "Palantir — investor relations",
                       AUTHORITY_OFFICIAL_PRIMARY),
        OfficialSource("https://www.palantir.com/newsroom/",
                       "newsroom", "Palantir — newsroom",
                       AUTHORITY_OFFICIAL_SECONDARY),
    ),
)

_SHOPIFY = EntityProfile(
    entity_id="shopify",
    legal_name="Shopify Inc.",
    common_name="Shopify",
    country="Canada",
    primary_domain="shopify.com",
    aliases=("shopify", "shopify inc"),
    ir_domain="investors.shopify.com",
    listings=(("NYSE", "SHOP"), ("TSX", "SHOP")),
    sec_relationship="Files an annual report on Form 40-F/10-K with the SEC.",
    sec_cik="0001594805",
    official_sources=(
        OfficialSource("https://www.shopify.com/about",
                       "corporate", "Shopify — about",
                       AUTHORITY_OFFICIAL_PRIMARY),
        OfficialSource("https://investors.shopify.com/",
                       "investor", "Shopify — investor relations",
                       AUTHORITY_OFFICIAL_PRIMARY),
        OfficialSource("https://www.shopify.com/news",
                       "newsroom", "Shopify — newsroom",
                       AUTHORITY_OFFICIAL_SECONDARY),
    ),
)

REGISTRY = (_SONY_GROUP, _SONY_INTERACTIVE, _SONY_ELECTRONICS, _PALANTIR,
            _SHOPIFY)


def _by_id(entity_id: str):
    for profile in REGISTRY:
        if profile.entity_id == entity_id:
            return profile
    return None


@dataclass(frozen=True)
class EntityResolution:
    """The outcome of resolving user input to a registry entity."""
    status: str
    profile: EntityProfile | None = None
    choices: tuple = ()
    reason: str = ""

    @property
    def resolved(self) -> bool:
        return self.status == RESOLVED

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "reason": self.reason,
            "profile": self.profile.as_dict() if self.profile else None,
            "choices": [{"entity_id": c.entity_id,
                         "legal_name": c.legal_name,
                         "common_name": c.common_name,
                         "country": c.country,
                         "primary_domain": c.primary_domain,
                         "describe": c.describe(),
                         "note": c.ambiguity_notes}
                        for c in self.choices],
        }


def _domain_match(profile: EntityProfile, host: str) -> bool:
    if not host:
        return False
    for known in profile.domains:
        if host == known or host.endswith("." + known):
            return True
    return False


def _name_match(profile: EntityProfile, name: str) -> str:
    """'' | 'alias' | 'exact' — how strongly a typed name names this entity."""
    normalized = " ".join((name or "").lower().split())
    if not normalized:
        return ""
    candidates = {profile.legal_name.lower(), profile.common_name.lower()}
    candidates |= {a.lower() for a in profile.aliases}
    if normalized in candidates:
        return "exact"
    typed = _tokens(normalized)
    if not typed:
        return ""
    for candidate in candidates:
        if typed == _tokens(candidate):
            return "exact"
    return ""


def resolve_entity(*, company_name: str = "", website: str = "") \
        -> EntityResolution:
    """Resolve typed input to exactly one registry entity, or say why not.

    Precedence, and the reasoning behind it:

    - A DOMAIN is the strongest signal a user can give, because they had to
      have the specific entity in mind to type it. `electronics.sony.com`
      means Sony Electronics even though the person typed "Sony".
    - A name that matches exactly one entity resolves.
    - A name that matches several entities in the same disambiguation group is
      AMBIGUOUS and is returned as a choice, never silently narrowed.
    - Anything else is UNKNOWN, and ordinary discovery handles it.
    """
    host = _host(website)

    if host:
        # Prefer the most specific domain owner: a subsidiary on its own
        # hostname beats the parent whose registry entry also lists that host.
        matches = [p for p in REGISTRY if _domain_match(p, host)]
        if matches:
            matches.sort(key=lambda p: (-len(_host(p.primary_domain)),
                                        p.entity_id))
            exact = [p for p in matches if _host(p.primary_domain) == host]
            chosen = exact[0] if exact else matches[0]
            return EntityResolution(
                RESOLVED, profile=chosen,
                reason=f"the website {host} is {chosen.legal_name}'s own "
                       f"domain")

    # A bare common name shared by a family of entities ("Sony") DOES match the
    # parent — its common name is exactly that string. Matching is not the same
    # as meaning: the user may well have meant PlayStation. So the group check
    # runs BEFORE the single-name match, or the parent would win by accident
    # and we would be right only by luck. Parent is listed first because it is
    # the likeliest reading, but it is offered, never assumed.
    group = _common_name_group(company_name)
    if len(group) > 1:
        return EntityResolution(
            AMBIGUOUS, choices=group,
            reason=f"\"{company_name}\" could mean the parent company or one "
                   f"of its subsidiaries")

    named = [p for p in REGISTRY if _name_match(p, company_name)]
    if len(named) == 1:
        return EntityResolution(
            RESOLVED, profile=named[0],
            reason=f"\"{company_name}\" is the registered name of "
                   f"{named[0].legal_name}")
    if len(named) > 1:
        return EntityResolution(
            AMBIGUOUS, choices=tuple(named),
            reason=f"\"{company_name}\" matches more than one company")

    return EntityResolution(
        UNKNOWN,
        reason="not a company in the verified registry; ordinary source "
               "discovery applies")


def _common_name_group(company_name: str) -> tuple:
    """Entities a bare, unqualified common name could denote."""
    normalized = " ".join((company_name or "").lower().split())
    if not normalized:
        return ()
    group_ids = {p.disambiguation_group for p in REGISTRY
                 if p.disambiguation_group
                 and normalized == p.common_name.lower()}
    if not group_ids:
        return ()
    members = [p for p in REGISTRY if p.disambiguation_group in group_ids]
    # Parent first, then subsidiaries alphabetically — a stable, explainable
    # order the UI can present without re-sorting.
    members.sort(key=lambda p: (bool(p.parent_entity_id), p.legal_name))
    return tuple(members)


def resolve_choice(entity_id: str) -> EntityResolution:
    """Settle an ambiguity from the user's explicit pick."""
    profile = _by_id(entity_id)
    if profile is None:
        return EntityResolution(UNKNOWN, reason="unknown company selection")
    return EntityResolution(RESOLVED, profile=profile,
                            reason="selected by the user")


# --- bounded official-source fallback ----------------------------------------
# Cap: enough to restore a real evidence spread, small enough that a blocked
# primary domain cannot turn into an unbounded crawl.
MAX_FALLBACK_SOURCES = 8

_KIND_TO_SOURCE_TYPE = {
    "corporate": "about",
    "investor": "investor",
    "earnings": "investor",
    "annual_report": "investor",
    "integrated_report": "investor",
    "strategy": "blog",
    "newsroom": "blog",
    "segment": "product",
    "filing": "external_approved",
}

_KIND_TO_SOURCE_CLASS = {
    "corporate": "company_owned",
    "investor": "investor_material",
    "earnings": "investor_material",
    "annual_report": "investor_material",
    "integrated_report": "investor_material",
    "strategy": "executive_statement",
    "newsroom": "executive_statement",
    "segment": "company_owned",
    "filing": "investor_material",
}


def official_fallback_candidates(profile: EntityProfile, *,
                                 exclude_urls=(),
                                 limit: int = MAX_FALLBACK_SOURCES) -> list:
    """Candidate records for an entity's curated official sources.

    Used when ordinary discovery cannot reach the company — most often because
    the primary domain refuses automated access (HTTP 403), which is exactly
    what `sony.com` does. These are still ordinary candidates: approval-gated,
    SSRF-guarded, and individually attributed, so a subsidiary page can never
    be read as the parent speaking.

    `exclude_urls` lets a caller skip URLs a previous attempt already failed
    on, so a retry explores new ground instead of repeating a known failure.
    """
    excluded = {u.rstrip("/") for u in exclude_urls}
    out = []
    for source in profile.official_sources:
        if len(out) >= limit:
            break
        if source.url.rstrip("/") in excluded:
            continue
        kind = source.kind
        parent = _by_id(profile.parent_entity_id)
        attribution = {
            REL_SELF: f"published by {profile.legal_name} itself",
            REL_PARENT: (f"published by the parent, {parent.legal_name}, and "
                         f"attributed to the parent — not to "
                         f"{profile.legal_name}"
                         if parent else "published by the parent company"),
            REL_SUBSIDIARY: "published by a subsidiary and attributed as such",
            REL_LISTING: "regulatory filing tied to the company's listing",
        }[source.entity_relationship]
        out.append({
            "url": source.url,
            "source_type": _KIND_TO_SOURCE_TYPE.get(kind, "about"),
            "discovery_method": "official_fallback",
            "same_domain": _host(source.url) == _host(profile.primary_domain),
            "source_class": _KIND_TO_SOURCE_CLASS.get(kind, "company_owned"),
            "availability": "UNVERIFIED",
            "title": source.title,
            "why_useful": f"official {kind.replace('_', ' ')} material",
            "why_relevant": (
                f"{attribution} — {source.note}" if source.note else
                f"{attribution}; official {kind.replace('_', ' ')} source"),
            # classification carried through so nothing downstream has to
            # re-derive whose voice this is
            "authority": source.authority,
            "entity_relationship": source.entity_relationship,
            "entity_id": profile.entity_id,
        })
    return out


def entity_identity_facts(profile: EntityProfile) -> dict:
    """The stored identity record for a resolved entity.

    This is what stops "Sony" from collapsing into one 6-K: the canonical
    identity is asserted from the registry and is independent of whichever
    documents a given run happened to retrieve.
    """
    return {
        "canonical_legal_name": profile.legal_name,
        "common_name": profile.common_name,
        "country": profile.country,
        "primary_domain": profile.primary_domain,
        "investor_relations_domain": profile.ir_domain or
        profile.primary_domain,
        "listings": [{"exchange": e, "ticker": t} for e, t in
                     profile.listings],
        "sec_relationship": profile.sec_relationship,
        "sec_cik": profile.sec_cik,
        "parent_entity_id": profile.parent_entity_id,
        "identity_confidence": profile.identity_confidence,
        "ambiguity_notes": profile.ambiguity_notes,
        "official_source_count": len(profile.official_sources),
        "registry_version": ENTITY_REGISTRY_VERSION,
    }
