"""Curated identity for companies no public register carries.

WHY A CATALOG EXISTS AT ALL
---------------------------
`suggest` draws on three sources: the entity registry, the validation manifest
and the SEC registrant table. Every one of them is a register of PUBLIC
companies, and the SEC table is the only one with breadth. So the product could
find ten thousand filers and could not find Highspot.

MEASURED LIVE 2026-09-11 on b88df2bb, `/api/companies?q=<name>`:

    Highspot 0   BigID 0   Cyera 0   Monte Carlo 0   Veeam 0   Druva 0
    Slalom 0   ZoomInfo 1 (correct)
    Sigma    1 -- "Sigma Lithium Corp", a lithium miner
    Point B  1 -- "Turning Point Brands, Inc.", a tobacco company

Seven found nothing, and TWO OFFERED THE WRONG COMPANY, which is worse than
nothing: a judge who accepts the only suggestion on screen gets a confident
report about a business with no relationship to the one they typed. "Point B"
reached Turning Point Brands because `_match` scores CONTAINS on a partial
final word and "point b" is a prefix of "point brands".

A private company is not an edge case. It is most companies.

WHAT A CATALOG ENTRY MAY CONTAIN, AND WHAT IT MAY NOT
-----------------------------------------------------
It carries IDENTITY and the company's own PUBLISHING SURFACE: legal name,
common name, country, canonical domain, the names a person might type, and
official URLs. That is the same contract `entities.py` already holds for
Palantir and Sony, and it is the thing that makes a run open on the right
company.

It carries NO ANALYSIS. No lens, no thesis, no business model, no conclusion,
no phrasing that could reach a report. Every sentence a reader sees is still
derived from documents retrieved at run time and would change if the company
changed its site tomorrow. An entry that pre-answered the analysis would make
the demo a puppet show, which is the opposite of what it is for.

EVERY URL HERE WAS FETCHED BEFORE IT WAS WRITTEN DOWN
-----------------------------------------------------
Guessed paths do not merely waste a fetch, they produce a measured zero that
reads as "this company publishes nothing". Each URL below returned 200 through
`safe_fetch` -- the product's own fetcher, not curl -- on 2026-09-11, and the
paths came from the publishers' own navigation rather than from a list of
plausible-looking slugs.

THE MONTE CARLO CASE, which is why `primary_domain` is canonical and not
merely correct: `montecarlodata.com` 301s to `montecarlo.ai`, and `safe_fetch`
refuses that hop -- `unsafe_redirect: redirect to montecarlo.ai leaves the
approved domain policy`. The refusal is right; SSRF protection that follows
redirects anywhere is not protection. But the run was opened on the stale
domain, retrieved nothing, and the product reported a company that "does not
say clearly enough what decision it serves". That was never a fact about Monte
Carlo. Recording where the company actually publishes today is the repair.

EXTENDING THIS
--------------
Add a dict to `CATALOG`. Nothing else -- `entities.REGISTRY` splices these in,
`suggest` reads them through the registry source, and the resolver finds them
by name, alias or domain. Verify each URL through `safe_fetch` first.
"""
from __future__ import annotations

from typing import List

from intent_engine.company_ingestion.entities import (
    AUTHORITY_OFFICIAL_PRIMARY,
    AUTHORITY_OFFICIAL_SECONDARY,
    EntityProfile,
    OfficialSource,
)

CATALOG_VERSION = "ci_catalog.v1"

#: Source kinds, matching the vocabulary `entities.py` already uses.
_CORPORATE = "corporate"
_SEGMENT = "segment"
_CUSTOMERS = "customers"
_NEWSROOM = "newsroom"
_PRICING = "pricing"
_INVESTOR = "investor"

#: PRIMARY = the company stating what it is and what it sells.
#: SECONDARY = news and customer proof, which is weaker but still its voice.
_P = AUTHORITY_OFFICIAL_PRIMARY
_S = AUTHORITY_OFFICIAL_SECONDARY


CATALOG: tuple = (
    {
        "entity_id": "highspot",
        "legal_name": "Highspot",
        "common_name": "Highspot",
        "country": "United States",
        "primary_domain": "highspot.com",
        "aliases": ("highspot", "high spot", "highspot inc",
                    "highspot by seismic"),
        # ITS OWN SITE SAYS SO, in the nav and twice in the body:
        # "Highspot is part of Seismic." Retrieved 2026-09-11. A reader told
        # only "Highspot, a sales enablement company" has been told something
        # that stopped being the whole truth, and ownership is exactly the
        # fact the registry exists to get right (see the Sony case).
        "ambiguity_notes": (
            "Highspot's own site presents it as \"Highspot by Seismic\" and "
            "states \"Highspot is part of Seismic\" (highspot.com, retrieved "
            "2026-09-11). Read its published material as that of a company "
            "inside Seismic, not a standalone independent vendor. The legal "
            "form is not recorded here because no Highspot page states it."),
        "sources": (
            ("https://highspot.com/about/", _CORPORATE, "about", _P),
            ("https://highspot.com/product/", _SEGMENT, "product", _P),
            ("https://highspot.com/product/sales-enablement-platform-overview/",
             _SEGMENT, "platform overview", _P),
            ("https://highspot.com/solutions/enterprise-sales-enablement/",
             _SEGMENT, "enterprise solution", _P),
            # HOW IT IS PAID is a question the analysis asks directly, and a
            # pricing page answers it in the company's own words.
            ("https://highspot.com/pricing/", _PRICING, "pricing", _P),
            ("https://highspot.com/services-and-support/", _SEGMENT,
             "services and support", _S),
        ),
    },
    {
        "entity_id": "bigid",
        "legal_name": "BigID, Inc.",
        "common_name": "BigID",
        "country": "United States",
        "primary_domain": "bigid.com",
        "aliases": ("bigid", "big id", "bigid inc"),
        "sources": (
            ("https://bigid.com/about/", _CORPORATE, "about", _P),
            ("https://bigid.com/platform/", _SEGMENT, "platform", _P),
            ("https://bigid.com/news/", _NEWSROOM, "news", _S),
        ),
    },
    {
        "entity_id": "cyera",
        "legal_name": "Cyera",
        "common_name": "Cyera",
        "country": "United States",
        "primary_domain": "cyera.com",
        "aliases": ("cyera", "cyera inc", "cyera ltd"),
        "ambiguity_notes": (
            "No Cyera page states a legal form, so none is recorded here."),
        "sources": (
            ("https://www.cyera.com/about", _CORPORATE, "about", _P),
            ("https://www.cyera.com/platform", _SEGMENT, "platform", _P),
            ("https://www.cyera.com/customers", _CUSTOMERS, "customers", _S),
            ("https://www.cyera.com/news", _NEWSROOM, "news", _S),
        ),
    },
    {
        "entity_id": "monte_carlo_data",
        "legal_name": "Monte Carlo Data, Inc.",
        "common_name": "Monte Carlo",
        "country": "United States",
        # CANONICAL, NOT MERELY CORRECT. See the module docstring: the old
        # domain 301s here and the redirect guard refuses the hop, so a run
        # opened on montecarlodata.com retrieves nothing at all.
        "primary_domain": "montecarlo.ai",
        "aliases": ("monte carlo", "montecarlo", "monte carlo data",
                    "montecarlodata", "monte carlo data inc"),
        "ambiguity_notes": (
            "Publishes at montecarlo.ai; the earlier montecarlodata.com "
            "redirects there. \"Monte Carlo\" is also a simulation method and "
            "a district of Monaco, so the data-observability company is the "
            "one meant here."),
        "sources": (
            ("https://montecarlo.ai/about/", _CORPORATE, "about", _P),
            ("https://montecarlo.ai/platform/", _SEGMENT, "platform", _P),
            ("https://montecarlo.ai/customers/", _CUSTOMERS, "customers", _S),
            ("https://montecarlo.ai/pricing/", _PRICING, "pricing", _P),
        ),
    },
    {
        "entity_id": "veeam",
        "legal_name": "Veeam Software Group GmbH",
        "common_name": "Veeam",
        "country": "Switzerland",
        "primary_domain": "veeam.com",
        "aliases": ("veeam", "veeam software", "veeam software group"),
        "sources": (
            ("https://www.veeam.com/platform.html", _SEGMENT, "platform", _P),
            ("https://www.veeam.com/products/veeam-data-platform.html",
             _SEGMENT, "Veeam Data Platform", _P),
            ("https://www.veeam.com/products/workloads.html", _SEGMENT,
             "workloads covered", _P),
            ("https://www.veeam.com/news.html", _NEWSROOM, "news", _S),
        ),
    },
    {
        "entity_id": "druva",
        "legal_name": "Druva",
        "common_name": "Druva",
        "country": "United States",
        "primary_domain": "druva.com",
        "aliases": ("druva", "druva inc"),
        "ambiguity_notes": (
            "No Druva page states a legal form, so none is recorded here."),
        "sources": (
            ("https://www.druva.com/about", _CORPORATE, "about", _P),
            ("https://www.druva.com/products", _SEGMENT, "products", _P),
            ("https://www.druva.com/customers", _CUSTOMERS, "customers", _S),
        ),
    },
    {
        "entity_id": "slalom",
        "legal_name": "Slalom, Inc.",
        "common_name": "Slalom",
        "country": "United States",
        "primary_domain": "slalom.com",
        "aliases": ("slalom", "slalom inc", "slalom consulting"),
        "ambiguity_notes": (
            "slalom.com geo-routes by visitor country (/us/en, /ca/en and "
            "others). The US pages are recorded so one run does not describe "
            "a different regional practice than the next."),
        "sources": (
            ("https://www.slalom.com/us/en/who-we-are", _CORPORATE,
             "who we are", _P),
            ("https://www.slalom.com/us/en/services", _SEGMENT,
             "services", _P),
            ("https://www.slalom.com/us/en/services/artificial-intelligence",
             _SEGMENT, "AI practice", _P),
            ("https://www.slalom.com/us/en/insights", _NEWSROOM,
             "insights", _S),
        ),
    },
    {
        "entity_id": "sigma_computing",
        "legal_name": "Sigma Computing, Inc.",
        "common_name": "Sigma Computing",
        "country": "United States",
        "primary_domain": "sigmacomputing.com",
        "aliases": ("sigma", "sigma computing", "sigma computing inc"),
        # WHY THE ALIAS "sigma" IS HERE AND IS NOT A LAND GRAB: without it the
        # only answer to "Sigma" was Sigma Lithium Corp, a miner. With it the
        # customer sees both -- this one first, because a registry EXACT beats
        # a registrant LEADING -- and picks. That is the chooser working.
        "ambiguity_notes": (
            "\"Sigma\" alone also matches Sigma Lithium Corp (NASDAQ: SGML), "
            "an unrelated mining company in the SEC register. Both are "
            "offered; this entry is the cloud analytics company."),
        "sources": (
            ("https://www.sigmacomputing.com/about", _CORPORATE, "about", _P),
            ("https://www.sigmacomputing.com/product", _SEGMENT,
             "product", _P),
            ("https://www.sigmacomputing.com/customers", _CUSTOMERS,
             "customers", _S),
            ("https://www.sigmacomputing.com/pricing", _PRICING,
             "pricing", _P),
            ("https://www.sigmacomputing.com/news", _NEWSROOM, "news", _S),
        ),
    },
    {
        # PUBLIC, and the one of the ten the SEC register already knew. The
        # entry adds what the register does not carry: a domain, and the
        # company's own product pages. CIK and ticker are the regulator's.
        "entity_id": "zoominfo",
        "legal_name": "ZoomInfo Technologies Inc.",
        "common_name": "ZoomInfo",
        "country": "United States",
        "primary_domain": "zoominfo.com",
        "aliases": ("zoominfo", "zoom info", "zoominfo technologies"),
        "listings": (("NASDAQ", "GTM"),),
        "sec_cik": "0001794515",
        "sec_relationship": "US domestic filer: Form 10-K annual, 10-Q "
                            "quarterly.",
        "ambiguity_notes": (
            "Not Zoom Communications (NASDAQ: ZM), a different company with a "
            "similar name. ZoomInfo trades as GTM."),
        "sources": (
            ("https://www.zoominfo.com/about", _CORPORATE, "about", _P),
            ("https://www.zoominfo.com/platform", _SEGMENT, "platform", _P),
            ("https://www.zoominfo.com/products", _SEGMENT, "products", _P),
            ("https://www.zoominfo.com/products/sales", _SEGMENT,
             "sales product", _P),
        ),
    },
    {
        "entity_id": "point_b",
        "legal_name": "Point B, LLC",
        "common_name": "Point B",
        "country": "United States",
        "primary_domain": "pointb.com",
        "aliases": ("point b", "pointb", "point b llc", "point b inc"),
        "ambiguity_notes": (
            "\"Point B\" also matches Turning Point Brands, Inc. (NYSE: TPB) "
            "in the SEC register, because the typed words are a prefix of "
            "\"Point Brands\". Both are offered; this entry is the Seattle "
            "consulting firm."),
        "sources": (
            ("https://www.pointb.com/about", _CORPORATE, "about", _P),
            ("https://www.pointb.com/insights", _NEWSROOM, "insights", _S),
            ("https://www.pointb.com/careers", _CORPORATE,
             "careers — how the firm describes its work", _S),
            ("https://www.pointb.com/contact", _CORPORATE, "contact", _S),
        ),
    },
)


def _profile(row: dict) -> EntityProfile:
    return EntityProfile(
        entity_id=row["entity_id"],
        legal_name=row["legal_name"],
        common_name=row["common_name"],
        country=row.get("country", ""),
        primary_domain=row["primary_domain"],
        aliases=tuple(row.get("aliases", ())),
        ir_domain=row.get("ir_domain", ""),
        listings=tuple(row.get("listings", ())),
        sec_relationship=row.get("sec_relationship", ""),
        sec_cik=row.get("sec_cik", ""),
        identity_confidence=row.get("identity_confidence", "HIGH"),
        ambiguity_notes=row.get("ambiguity_notes", ""),
        official_sources=tuple(
            OfficialSource(url, kind, label, authority)
            for (url, kind, label, authority) in row.get("sources", ())),
    )


def catalog_profiles() -> List[EntityProfile]:
    """Every catalog row as an EntityProfile, in declaration order."""
    return [_profile(row) for row in CATALOG]


CATALOG_REGISTRY: tuple = tuple(catalog_profiles())
