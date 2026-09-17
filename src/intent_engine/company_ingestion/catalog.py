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
    # --- THE NEXT FORTY (Founder Target 50, #1-40) -------------------------
    #
    # MEASURED LIVE 2026-09-11 on b4db855b, `/api/companies?q=<name>`, before
    # a single analysis was spent: 33 of the 40 returned NOTHING AT ALL, and
    # of the seven that returned a row, TWO WERE THE WRONG COMPANY --
    #
    #   Clari    -> "Clarivate Plc" and "Claritev Corp", because the typed
    #               word is a prefix of both. Neither is Clari.
    #   Adastra  -> "Adastra Holdings Ltd.", a Canadian cannabis company,
    #               not the Toronto data consultancy.
    #
    # A wrong suggestion is worse than none: the only row on screen gets
    # accepted, and the product then writes a confident report about an
    # unrelated business. Same failure as Sigma/Point B above, at scale.
    #
    # EVERY URL BELOW WAS FETCHED THROUGH `safe_fetch` ON 2026-09-11 AND
    # RETURNED 200 WITH CONTENT OF ITS OWN. None was guessed: each came from
    # the publisher's own homepage links or its own sitemap, and each was then
    # checked to differ from that publisher's homepage. That second check is
    # not ceremony -- credera.com is a single-page app that answers HTTP 200
    # with its shell for ANY path, including /sitemap.xml, so "it fetched" is
    # not evidence a page exists, and five shell copies would have been read
    # as five sources.
    #
    # THREE ENTRIES CARRY NO SOURCES ON PURPOSE. rubrik.com, 6sense.com and
    # fiscalnote.com answered HTTP 403 to every path including robots.txt. A
    # refused host is not a company that publishes nothing, and writing down
    # URLs we could not read would turn our 403 into its silence. Rubrik and
    # FiscalNote file with the SEC, so their evidence arrives that way.
    {
        "entity_id": "rubrik",
        "legal_name": "Rubrik, Inc.",
        "common_name": "Rubrik",
        "country": "United States",
        "primary_domain": "rubrik.com",
        "aliases": ("rubrik", "rubrik inc"),
        "listings": (("NYSE", "RBRK"),),
        "sec_cik": "0001943896",
        "sec_relationship": "US domestic filer: Form 10-K annual, 10-Q quarterly.",
        "ambiguity_notes": (
            "rubrik.com refused this product's fetcher with HTTP 403 on every "
            "path including robots.txt when checked on 2026-09-11, so no "
            "company-owned page is listed. Its SEC filings remain reachable."
        ),
        "sources": (
            ("https://www.rubrik.com", _CORPORATE,
             "home — refused our reader (HTTP 403)", _P),
        ),
    },
    {
        "entity_id": "cohesity",
        "legal_name": "Cohesity, Inc.",
        "common_name": "Cohesity",
        "country": "United States",
        "primary_domain": "cohesity.com",
        "aliases": ("cohesity", "cohesity inc"),
        "ambiguity_notes": (
            "Combined with Veritas' data protection business in 2024; the "
            "Veritas brand may appear in its own material."
        ),
        "sources": (
            ("https://www.cohesity.com/company", _CORPORATE,
             "about", _P),
            ("https://www.cohesity.com/platform", _SEGMENT,
             "platform", _P),
            ("https://www.cohesity.com/customers", _CUSTOMERS,
             "customers", _S),
            ("https://www.cohesity.com/resources", _NEWSROOM,
             "news", _S),
            ("https://www.cohesity.com/company/investor-relations", _CORPORATE,
             "investors", _S),
        ),
    },
    {
        "entity_id": "project44",
        "legal_name": "project44, Inc.",
        "common_name": "project44",
        "country": "United States",
        "primary_domain": "project44.com",
        "aliases": ("project44", "project 44", "p44", "project44 inc"),
        "ambiguity_notes": (
            "Written lower-case by the company. \"Project 44\" and \"p44\" reach "
            "the same entity."
        ),
        "sources": (
            ("https://www.project44.com/company", _CORPORATE,
             "about", _P),
            ("https://www.project44.com/platform", _SEGMENT,
             "platform", _P),
            ("https://www.project44.com/customer-stories", _CUSTOMERS,
             "customers", _S),
            ("https://www.project44.com/blog", _NEWSROOM,
             "news", _S),
            ("https://www.project44.com/company/leadership", _CORPORATE,
             "leadership", _S),
        ),
    },
    {
        "entity_id": "kinaxis",
        "legal_name": "Kinaxis Inc.",
        "common_name": "Kinaxis",
        "country": "Canada",
        "primary_domain": "kinaxis.com",
        "aliases": ("kinaxis", "kinaxis inc"),
        "listings": (("TSX", "KXS"),),
        "ambiguity_notes": (
            "Listed in Toronto, not on a US exchange, so the SEC registrant "
            "table does not carry it."
        ),
        "sources": (
            ("https://www.kinaxis.com/en/about", _CORPORATE,
             "about", _P),
            ("https://www.kinaxis.com/en/solutions", _SEGMENT,
             "platform", _P),
            ("https://www.kinaxis.com/en/customers", _CUSTOMERS,
             "customers", _S),
            ("https://www.kinaxis.com/en/resources", _NEWSROOM,
             "news", _S),
            ("https://www.kinaxis.com/en/leadership", _CORPORATE,
             "leadership", _S),
        ),
    },
    {
        "entity_id": "alation",
        "legal_name": "Alation, Inc.",
        "common_name": "Alation",
        "country": "United States",
        "primary_domain": "alation.com",
        "aliases": ("alation", "alation inc"),
        "sources": (
            ("https://www.alation.com/our-story", _CORPORATE,
             "about", _P),
            ("https://www.alation.com/customers", _CUSTOMERS,
             "customers", _S),
            ("https://www.alation.com/blog", _NEWSROOM,
             "news", _S),
            ("https://www.alation.com/careers", _CORPORATE,
             "careers", _S),
        ),
    },
    {
        "entity_id": "workato",
        "legal_name": "Workato, Inc.",
        "common_name": "Workato",
        "country": "United States",
        "primary_domain": "workato.com",
        "aliases": ("workato", "workato inc"),
        "sources": (
            ("https://www.workato.com/platform", _SEGMENT,
             "platform", _P),
            ("https://www.workato.com/customers", _CUSTOMERS,
             "customers", _S),
            ("https://www.workato.com/resources", _NEWSROOM,
             "news", _S),
            ("https://www.workato.com/pricing", _PRICING,
             "pricing", _P),
            ("https://www.workato.com/careers", _CORPORATE,
             "careers", _S),
        ),
    },
    {
        "entity_id": "dataminr",
        "legal_name": "Dataminr, Inc.",
        "common_name": "Dataminr",
        "country": "United States",
        "primary_domain": "dataminr.com",
        "aliases": ("dataminr", "dataminr inc"),
        "sources": (
            ("https://www.dataminr.com/company", _CORPORATE,
             "about", _P),
            ("https://www.dataminr.com/company/customers", _CUSTOMERS,
             "customers", _S),
            ("https://www.dataminr.com/resources", _NEWSROOM,
             "news", _S),
            ("https://www.dataminr.com/company/leadership", _CORPORATE,
             "leadership", _S),
            ("https://www.dataminr.com/company/careers", _CORPORATE,
             "careers", _S),
        ),
    },
    {
        "entity_id": "adastra",
        "legal_name": "Adastra Corporation",
        "common_name": "Adastra",
        "country": "Canada",
        "primary_domain": "adastracorp.com",
        "aliases": ("adastra", "adastra corporation", "adastra corp"),
        "ambiguity_notes": (
            "\"Adastra\" also matches Adastra Holdings Ltd. in the SEC register, "
            "an unrelated Canadian cannabis company. Both are offered; this "
            "entry is the Toronto data and analytics consultancy."
        ),
        "sources": (
            ("https://adastracorp.com/who-we-are", _CORPORATE,
             "about", _P),
            ("https://adastracorp.com/services", _SEGMENT,
             "platform", _P),
            ("https://adastracorp.com/resources", _NEWSROOM,
             "news", _S),
            ("https://adastracorp.com/leadership", _CORPORATE,
             "leadership", _S),
            ("https://adastracorp.com/careers", _CORPORATE,
             "careers", _S),
        ),
    },
    {
        "entity_id": "hycu",
        "legal_name": "HYCU, Inc.",
        "common_name": "HYCU",
        "country": "United States",
        "primary_domain": "hycu.com",
        "aliases": ("hycu", "hycu inc"),
        "sources": (
            ("https://www.hycu.com/company", _CORPORATE,
             "about", _P),
            ("https://www.hycu.com/platform", _SEGMENT,
             "platform", _P),
            ("https://www.hycu.com/customers", _CUSTOMERS,
             "customers", _S),
            ("https://www.hycu.com/resources", _NEWSROOM,
             "news", _S),
            ("https://www.hycu.com/pricing", _PRICING,
             "pricing", _P),
        ),
    },
    {
        "entity_id": "nasuni",
        "legal_name": "Nasuni Corporation",
        "common_name": "Nasuni",
        "country": "United States",
        "primary_domain": "nasuni.com",
        "aliases": ("nasuni", "nasuni corporation"),
        "sources": (
            ("https://www.nasuni.com/about-us", _CORPORATE,
             "about", _P),
            ("https://www.nasuni.com/product", _SEGMENT,
             "platform", _P),
            ("https://www.nasuni.com/customers", _CUSTOMERS,
             "customers", _S),
            ("https://www.nasuni.com/about-us/news", _NEWSROOM,
             "news", _S),
            ("https://www.nasuni.com/pricing", _PRICING,
             "pricing", _P),
        ),
    },
    {
        "entity_id": "dataiku",
        "legal_name": "Dataiku, Inc.",
        "common_name": "Dataiku",
        "country": "United States",
        "primary_domain": "dataiku.com",
        "aliases": ("dataiku", "dataiku inc"),
        "ambiguity_notes": (
            "Founded in France; operates from New York."
        ),
        "sources": (
            ("https://www.dataiku.com/company", _CORPORATE,
             "about", _P),
            ("https://www.dataiku.com/product", _SEGMENT,
             "platform", _P),
            ("https://www.dataiku.com/company/customers", _CUSTOMERS,
             "customers", _S),
            ("https://www.dataiku.com/blog", _NEWSROOM,
             "news", _S),
            ("https://www.dataiku.com/company/careers", _CORPORATE,
             "careers", _S),
        ),
    },
    {
        "entity_id": "commvault",
        "legal_name": "Commvault Systems, Inc.",
        "common_name": "Commvault",
        "country": "United States",
        "primary_domain": "commvault.com",
        "aliases": ("commvault", "commvault systems"),
        "listings": (("NASDAQ", "CVLT"),),
        "sec_cik": "0001169561",
        "sec_relationship": "US domestic filer: Form 10-K annual, 10-Q quarterly.",
        "sources": (
            ("https://www.commvault.com/about-us", _CORPORATE,
             "about", _P),
            ("https://www.commvault.com/platform", _SEGMENT,
             "platform", _P),
            ("https://www.commvault.com/customers", _CUSTOMERS,
             "customers", _S),
            ("https://www.commvault.com/resources", _NEWSROOM,
             "news", _S),
            ("https://www.commvault.com/about-us/leadership", _CORPORATE,
             "leadership", _S),
        ),
    },
    {
        "entity_id": "boomi",
        "legal_name": "Boomi, LP",
        "common_name": "Boomi",
        "country": "United States",
        "primary_domain": "boomi.com",
        "aliases": ("boomi", "boomi lp"),
        "ambiguity_notes": (
            "Divested from Dell Technologies in 2021 and operates "
            "independently."
        ),
        "sources": (
            ("https://www.boomi.com/company", _CORPORATE,
             "about", _P),
            ("https://www.boomi.com/platform", _SEGMENT,
             "platform", _P),
            ("https://www.boomi.com/customers", _CUSTOMERS,
             "customers", _S),
            ("https://www.boomi.com/resources", _NEWSROOM,
             "news", _S),
            ("https://www.boomi.com/pricing", _PRICING,
             "pricing", _P),
        ),
    },
    {
        "entity_id": "snaplogic",
        "legal_name": "SnapLogic, Inc.",
        "common_name": "SnapLogic",
        "country": "United States",
        "primary_domain": "snaplogic.com",
        "aliases": ("snaplogic", "snap logic", "snaplogic inc"),
        "sources": (
            ("https://www.snaplogic.com/company", _CORPORATE,
             "about", _P),
            ("https://www.snaplogic.com/products", _SEGMENT,
             "platform", _P),
            ("https://www.snaplogic.com/customers", _CUSTOMERS,
             "customers", _S),
            ("https://www.snaplogic.com/resources", _NEWSROOM,
             "news", _S),
            ("https://www.snaplogic.com/pricing", _PRICING,
             "pricing", _P),
        ),
    },
    {
        "entity_id": "west_monroe",
        "legal_name": "West Monroe Partners, LLC",
        "common_name": "West Monroe",
        "country": "United States",
        "primary_domain": "westmonroe.com",
        "aliases": ("west monroe", "west monroe partners", "westmonroe"),
        "sources": (
            ("https://www.westmonroe.com/about", _CORPORATE,
             "about", _P),
            ("https://www.westmonroe.com/insights", _NEWSROOM,
             "news", _S),
            ("https://www.westmonroe.com/careers", _CORPORATE,
             "careers", _S),
        ),
    },
    {
        "entity_id": "guidehouse",
        "legal_name": "Guidehouse Inc.",
        "common_name": "Guidehouse",
        "country": "United States",
        "primary_domain": "guidehouse.com",
        "aliases": ("guidehouse", "guidehouse inc"),
        "sources": (
            ("https://www.guidehouse.com/about", _CORPORATE,
             "about", _P),
            ("https://www.guidehouse.com/services", _SEGMENT,
             "platform", _P),
            ("https://www.guidehouse.com/insights", _NEWSROOM,
             "news", _S),
            ("https://www.guidehouse.com/careers", _CORPORATE,
             "careers", _S),
        ),
    },
    {
        "entity_id": "collibra",
        "legal_name": "Collibra NV",
        "common_name": "Collibra",
        "country": "Belgium",
        "primary_domain": "collibra.com",
        "aliases": ("collibra", "collibra nv"),
        "ambiguity_notes": (
            "Belgian company; its largest office is in New York."
        ),
        "sources": (
            ("https://www.collibra.com/company/who-we-are", _CORPORATE,
             "about", _P),
            ("https://www.collibra.com/customer-stories", _CUSTOMERS,
             "customers", _S),
            ("https://www.collibra.com/blog", _NEWSROOM,
             "news", _S),
            ("https://www.collibra.com/company/leadership", _CORPORATE,
             "leadership", _S),
            ("https://www.collibra.com/company/careers", _CORPORATE,
             "careers", _S),
        ),
    },
    {
        "entity_id": "airbyte",
        "legal_name": "Airbyte, Inc.",
        "common_name": "Airbyte",
        "country": "United States",
        "primary_domain": "airbyte.com",
        "aliases": ("airbyte", "airbyte inc"),
        "sources": (
            ("https://www.airbyte.com/company/about-us", _CORPORATE,
             "about", _P),
            ("https://www.airbyte.com/success-stories", _CUSTOMERS,
             "customers", _S),
            ("https://www.airbyte.com/blog", _NEWSROOM,
             "news", _S),
            ("https://www.airbyte.com/pricing", _PRICING,
             "pricing", _P),
            ("https://www.airbyte.com/company/careers", _CORPORATE,
             "careers", _S),
        ),
    },
    {
        "entity_id": "onetrust",
        "legal_name": "OneTrust, LLC",
        "common_name": "OneTrust",
        "country": "United States",
        "primary_domain": "onetrust.com",
        "aliases": ("onetrust", "one trust", "onetrust llc"),
        "sources": (
            ("https://www.onetrust.com/content/onetrust/us/en/about-us", _CORPORATE,
             "about", _P),
            ("https://www.onetrust.com/solutions", _SEGMENT,
             "platform", _P),
            ("https://www.onetrust.com/content/onetrust/us/en/customers", _CUSTOMERS,
             "customers", _S),
            ("https://www.onetrust.com/content/onetrust/us/en/resources", _NEWSROOM,
             "news", _S),
            ("https://www.onetrust.com/content/onetrust/us/en/pricing", _PRICING,
             "pricing", _P),
        ),
    },
    {
        "entity_id": "samsara",
        "legal_name": "Samsara Inc.",
        "common_name": "Samsara",
        "country": "United States",
        "primary_domain": "samsara.com",
        "aliases": ("samsara", "samsara inc"),
        "listings": (("NYSE", "IOT"),),
        "sec_cik": "0001642896",
        "sec_relationship": "US domestic filer: Form 10-K annual, 10-Q quarterly.",
        "ambiguity_notes": (
            "Trades as IOT. Not Samsara Vision or any similarly named private "
            "firm."
        ),
        "sources": (
            ("https://www.samsara.com/company/about", _CORPORATE,
             "about", _P),
            ("https://www.samsara.com/products/platform", _SEGMENT,
             "platform", _P),
            ("https://www.samsara.com/resources/customers", _CUSTOMERS,
             "customers", _S),
            ("https://www.samsara.com/resources", _NEWSROOM,
             "news", _S),
            ("https://www.samsara.com/resources/plans", _PRICING,
             "pricing", _P),
        ),
    },
    {
        "entity_id": "fourkites",
        "legal_name": "FourKites, Inc.",
        "common_name": "FourKites",
        "country": "United States",
        "primary_domain": "fourkites.ai",
        "aliases": ("fourkites", "four kites", "fourkites inc"),
        "ambiguity_notes": (
            "The canonical domain is fourkites.ai: fourkites.com redirects "
            "there, and this product's fetcher refuses a redirect that leaves "
            "the approved domain, so the .com form cannot be used as the entry "
            "point."
        ),
        "sources": (
            ("https://www.fourkites.ai/company/about", _CORPORATE,
             "about", _P),
            ("https://www.fourkites.ai/platform", _SEGMENT,
             "platform", _P),
            ("https://www.fourkites.ai/case-studies", _CUSTOMERS,
             "customers", _S),
            ("https://www.fourkites.ai/newsroom", _NEWSROOM,
             "news", _S),
            ("https://www.fourkites.ai/company/leadership", _CORPORATE,
             "leadership", _S),
        ),
    },
    {
        "entity_id": "descartes",
        "legal_name": "The Descartes Systems Group Inc.",
        "common_name": "Descartes Systems",
        "country": "Canada",
        "primary_domain": "descartes.com",
        "aliases": ("descartes", "descartes systems", "descartes systems group"),
        "listings": (("NASDAQ", "DSGX"), ("TSX", "DSG")),
        "sec_cik": "0001050140",
        "sec_relationship": "Canadian issuer filing with the SEC: Form 40-F annual.",
        "sources": (
            ("https://www.descartes.com/who-we-are", _CORPORATE,
             "about", _P),
            ("https://www.descartes.com/solutions", _SEGMENT,
             "platform", _P),
            ("https://www.descartes.com/resources", _NEWSROOM,
             "news", _S),
            ("https://www.descartes.com/who-we-are/investor-relations", _CORPORATE,
             "investors", _S),
            ("https://www.descartes.com/who-we-are/leadership", _CORPORATE,
             "leadership", _S),
        ),
    },
    {
        "entity_id": "o9_solutions",
        "legal_name": "o9 Solutions, Inc.",
        "common_name": "o9 Solutions",
        "country": "United States",
        "primary_domain": "o9solutions.com",
        "aliases": ("o9", "o9 solutions", "o9solutions"),
        "ambiguity_notes": (
            "\"o9\" alone is the name the company uses."
        ),
        "sources": (
            ("https://www.o9solutions.com/about", _CORPORATE,
             "about", _P),
            ("https://www.o9solutions.com/solutions", _SEGMENT,
             "platform", _P),
            ("https://www.o9solutions.com/resources", _NEWSROOM,
             "news", _S),
            ("https://www.o9solutions.com/careers", _CORPORATE,
             "careers", _S),
        ),
    },
    {
        "entity_id": "thoughtspot",
        "legal_name": "ThoughtSpot, Inc.",
        "common_name": "ThoughtSpot",
        "country": "United States",
        "primary_domain": "thoughtspot.com",
        "aliases": ("thoughtspot", "thought spot"),
        "sources": (
            ("https://www.thoughtspot.com/solutions", _SEGMENT,
             "platform", _P),
            ("https://www.thoughtspot.com/customers", _CUSTOMERS,
             "customers", _S),
            ("https://www.thoughtspot.com/resources", _NEWSROOM,
             "news", _S),
            ("https://www.thoughtspot.com/pricing", _PRICING,
             "pricing", _P),
            ("https://www.thoughtspot.com/team", _CORPORATE,
             "leadership", _S),
        ),
    },
    {
        "entity_id": "starburst",
        "legal_name": "Starburst Data, Inc.",
        "common_name": "Starburst",
        "country": "United States",
        "primary_domain": "starburst.io",
        "aliases": ("starburst", "starburst data"),
        "ambiguity_notes": (
            "Canonical domain is starburst.io, not a .com."
        ),
        "sources": (
            ("https://www.starburst.io/about", _CORPORATE,
             "about", _P),
            ("https://www.starburst.io/customers", _CUSTOMERS,
             "customers", _S),
            ("https://www.starburst.io/resources", _NEWSROOM,
             "news", _S),
            ("https://www.starburst.io/pricing", _PRICING,
             "pricing", _P),
            ("https://www.starburst.io/careers", _CORPORATE,
             "careers", _S),
        ),
    },
    {
        "entity_id": "dremio",
        "legal_name": "Dremio Corporation",
        "common_name": "Dremio",
        "country": "United States",
        "primary_domain": "dremio.com",
        "aliases": ("dremio", "dremio corporation"),
        "sources": (
            ("https://www.dremio.com/about", _CORPORATE,
             "about", _P),
            ("https://www.dremio.com/platform", _SEGMENT,
             "platform", _P),
            ("https://www.dremio.com/customers", _CUSTOMERS,
             "customers", _S),
            ("https://www.dremio.com/newsroom", _NEWSROOM,
             "news", _S),
            ("https://www.dremio.com/pricing", _PRICING,
             "pricing", _P),
        ),
    },
    {
        "entity_id": "denodo",
        "legal_name": "Denodo Technologies, Inc.",
        "common_name": "Denodo",
        "country": "United States",
        "primary_domain": "denodo.com",
        "aliases": ("denodo", "denodo technologies"),
        "ambiguity_notes": (
            "Spanish origin; US operations from Palo Alto."
        ),
        "sources": (
            ("https://www.denodo.com/en/denodo-platform/overview", _CORPORATE,
             "about", _P),
            ("https://www.denodo.com/en/company/customers", _CUSTOMERS,
             "customers", _S),
            ("https://www.denodo.com/en/resources", _NEWSROOM,
             "news", _S),
            ("https://www.denodo.com/en/about-us/leadership", _CORPORATE,
             "leadership", _S),
            ("https://www.denodo.com/en/company/careers", _CORPORATE,
             "careers", _S),
        ),
    },
    {
        "entity_id": "geotab",
        "legal_name": "Geotab Inc.",
        "common_name": "Geotab",
        "country": "Canada",
        "primary_domain": "geotab.com",
        "aliases": ("geotab", "geotab inc"),
        "sources": (
            ("https://www.geotab.com/partners/overview", _CORPORATE,
             "about", _P),
            ("https://www.geotab.com/success-stories", _CUSTOMERS,
             "customers", _S),
            ("https://www.geotab.com/blog", _NEWSROOM,
             "news", _S),
            ("https://www.geotab.com/about/leadership", _CORPORATE,
             "leadership", _S),
        ),
    },
    {
        "entity_id": "clari",
        "legal_name": "Clari Inc.",
        "common_name": "Clari",
        "country": "United States",
        "primary_domain": "clari.com",
        "aliases": ("clari", "clari inc"),
        "ambiguity_notes": (
            "\"Clari\" in the SEC register returns only Clarivate Plc and "
            "Claritev Corp, neither of which is this company: the typed word is "
            "a prefix of both. All are offered; this entry is the "
            "revenue-platform company."
        ),
        "sources": (
            ("https://www.clari.com/about", _CORPORATE,
             "about", _P),
            ("https://www.clari.com/resources/customer-stories", _CUSTOMERS,
             "customers", _S),
            ("https://www.clari.com/blog", _NEWSROOM,
             "news", _S),
            ("https://www.clari.com/pricing", _PRICING,
             "pricing", _P),
            ("https://www.clari.com/careers", _CORPORATE,
             "careers", _S),
        ),
    },
    {
        "entity_id": "6sense",
        "legal_name": "6sense Insights, Inc.",
        "common_name": "6sense",
        "country": "United States",
        "primary_domain": "6sense.com",
        "aliases": ("6sense", "6 sense", "6sense insights"),
        "ambiguity_notes": (
            "6sense.com refused this product's fetcher with HTTP 403 on every "
            "path including robots.txt when checked on 2026-09-11, so no "
            "company-owned page is listed."
        ),
        "sources": (
            ("https://www.6sense.com", _CORPORATE,
             "home — refused our reader (HTTP 403)", _P),
        ),
    },
    {
        "entity_id": "gong",
        "legal_name": "Gong.io, Inc.",
        "common_name": "Gong",
        "country": "United States",
        "primary_domain": "gong.io",
        "aliases": ("gong", "gong io", "gong.io"),
        "ambiguity_notes": (
            "Canonical domain is gong.io."
        ),
        "sources": (
            ("https://www.gong.io/about", _CORPORATE,
             "about", _P),
            ("https://www.gong.io/platform", _SEGMENT,
             "platform", _P),
            ("https://www.gong.io/case-studies", _CUSTOMERS,
             "customers", _S),
            ("https://gong.io/press", _NEWSROOM,
             "news", _S),
            ("https://www.gong.io/pricing", _PRICING,
             "pricing", _P),
        ),
    },
    {
        "entity_id": "alphasense",
        "legal_name": "AlphaSense, Inc.",
        "common_name": "AlphaSense",
        "country": "United States",
        "primary_domain": "alpha-sense.com",
        "aliases": ("alphasense", "alpha sense", "alpha-sense"),
        "ambiguity_notes": (
            "Canonical domain is alpha-sense.com, with the hyphen."
        ),
        "sources": (
            ("https://www.alpha-sense.com/about", _CORPORATE,
             "about", _P),
            ("https://www.alpha-sense.com/platform", _SEGMENT,
             "platform", _P),
            ("https://www.alpha-sense.com/resources", _NEWSROOM,
             "news", _S),
            ("https://www.alpha-sense.com/pricing", _PRICING,
             "pricing", _P),
            ("https://www.alpha-sense.com/careers", _CORPORATE,
             "careers", _S),
        ),
    },
    {
        "entity_id": "fiscalnote",
        "legal_name": "FiscalNote Holdings, Inc.",
        "common_name": "FiscalNote",
        "country": "United States",
        "primary_domain": "fiscalnote.com",
        "aliases": ("fiscalnote", "fiscal note"),
        "listings": (("NYSE", "NOTE"),),
        "sec_cik": "0001823466",
        "sec_relationship": "US domestic filer: Form 10-K annual, 10-Q quarterly.",
        "ambiguity_notes": (
            "fiscalnote.com refused this product's fetcher with HTTP 403 on "
            "every path including robots.txt when checked on 2026-09-11, so no "
            "company-owned page is listed. Its SEC filings remain reachable."
        ),
        "sources": (
            ("https://www.fiscalnote.com", _CORPORATE,
             "home — refused our reader (HTTP 403)", _P),
        ),
    },
    {
        "entity_id": "recorded_future",
        "legal_name": "Recorded Future, Inc.",
        "common_name": "Recorded Future",
        "country": "United States",
        "primary_domain": "recordedfuture.com",
        "aliases": ("recorded future", "recordedfuture"),
        "ambiguity_notes": (
            "Acquired by Mastercard in 2024 and operated as a subsidiary; "
            "material published by Mastercard about it is a parent's account, "
            "not its own."
        ),
        "sources": (
            ("https://www.recordedfuture.com/solutions-overview", _SEGMENT,
             "platform", _P),
            ("https://www.recordedfuture.com/products/cyber-operations", _SEGMENT,
             "products", _P),
            ("https://www.recordedfuture.com/research/intelligence-reports", _NEWSROOM,
             "research", _S),
            ("https://www.recordedfuture.com/blog", _NEWSROOM,
             "news", _S),
            ("https://www.recordedfuture.com/careers", _CORPORATE,
             "careers", _S),
        ),
    },
    {
        "entity_id": "prewave",
        "legal_name": "Prewave GmbH",
        "common_name": "Prewave",
        "country": "Austria",
        "primary_domain": "prewave.com",
        "aliases": ("prewave", "prewave gmbh"),
        "sources": (
            ("https://www.prewave.com/company/our-story", _CORPORATE,
             "about", _P),
            ("https://www.prewave.com/resources/blog", _NEWSROOM,
             "news", _S),
            ("https://www.prewave.com/company/careers", _CORPORATE,
             "careers", _S),
        ),
    },
    {
        "entity_id": "protiviti",
        "legal_name": "Protiviti Inc.",
        "common_name": "Protiviti",
        "country": "United States",
        "primary_domain": "protiviti.com",
        "aliases": ("protiviti", "protiviti inc"),
        "ambiguity_notes": (
            "A subsidiary of Robert Half Inc. (NYSE: RHI); Robert Half's "
            "filings describe Protiviti as a segment and are a parent's account "
            "of it."
        ),
        "sources": (
            ("https://www.protiviti.com/ca-en/about-us", _CORPORATE,
             "about", _P),
            ("https://www.protiviti.com/ca-en/insights", _NEWSROOM,
             "news", _S),
            ("https://www.protiviti.com/ca-en/leadership", _CORPORATE,
             "leadership", _S),
            ("https://www.protiviti.com/ca-en/careers", _CORPORATE,
             "careers", _S),
        ),
    },
    {
        "entity_id": "credera",
        "legal_name": "Credera",
        "common_name": "Credera",
        "country": "United States",
        "primary_domain": "credera.com",
        "aliases": ("credera",),
        "ambiguity_notes": (
            "An Omnicom company. The site is a single-page app that returns its "
            "shell with HTTP 200 for any path, so the pages listed here were "
            "taken from its own sitemap and each was confirmed to return "
            "content different from the homepage."
        ),
        "sources": (
            ("https://www.credera.com/about-us", _CORPORATE,
             "about", _P),
            ("https://www.credera.com/about-us/company-history", _CORPORATE,
             "history", _P),
            ("https://www.credera.com/about-us/client-success", _CUSTOMERS,
             "customers", _S),
            ("https://www.credera.com/insights", _NEWSROOM,
             "insights", _S),
        ),
    },
    {
        "entity_id": "long_view",
        "legal_name": "Long View Systems Corporation",
        "common_name": "Long View Systems",
        "country": "Canada",
        "primary_domain": "longviewsystems.com",
        "aliases": ("long view", "long view systems", "longview", "longview systems"),
        "sources": (
            ("https://www.longviewsystems.com/about-us", _CORPORATE,
             "about", _P),
            ("https://www.longviewsystems.com/blog", _NEWSROOM,
             "news", _S),
            ("https://www.longviewsystems.com/careers", _CORPORATE,
             "careers", _S),
        ),
    },
    {
        "entity_id": "celigo",
        "legal_name": "Celigo, Inc.",
        "common_name": "Celigo",
        "country": "United States",
        "primary_domain": "celigo.com",
        "aliases": ("celigo", "celigo inc"),
        "sources": (
            ("https://www.celigo.com/about-us", _CORPORATE,
             "about", _P),
            ("https://www.celigo.com/platform", _SEGMENT,
             "platform", _P),
            ("https://www.celigo.com/customer-stories", _CUSTOMERS,
             "customers", _S),
            ("https://www.celigo.com/blog", _NEWSROOM,
             "news", _S),
            ("https://www.celigo.com/platform/pricing", _PRICING,
             "pricing", _P),
        ),
    },
    {
        "entity_id": "fivetran",
        "legal_name": "Fivetran, Inc.",
        "common_name": "Fivetran",
        "country": "United States",
        "primary_domain": "fivetran.com",
        "aliases": ("fivetran", "fivetran inc", "dbt", "dbt labs", "fivetran dbt labs", "fivetran / dbt labs"),
        "ambiguity_notes": (
            "Fivetran and dbt Labs are one company: dbt Labs' own site states "
            "\"Fivetran and dbt are one company\" (read 2026-09-11). Typing "
            "either name reaches this entry. getdbt.com is deliberately NOT "
            "listed as a source: a catalogued URL must sit on the identity's "
            "own declared domain, and routing a second brand's host through "
            "this entry would break the rule that a curated source is this "
            "company speaking as the entity it was filed as."
        ),
        "sources": (
            ("https://www.fivetran.com/about", _CORPORATE,
             "about", _P),
            ("https://www.fivetran.com/platform", _SEGMENT,
             "platform", _P),
        ),
    },
    # ------------------------------------------------------------------
    # THE TWENTY-FIVE (adaptive strategic intelligence V2).
    #
    # MEASURED LIVE before these rows existed, `/api/companies?q=<name>` on
    # db6946fa: 0 of 25 resolved. Nineteen returned NOTHING -- they are
    # private companies no public register carries -- and the six that
    # returned rows offered SEC registrant entries with no entity_id, no
    # domain and, for "Island", another company entirely (Orchid Island
    # Capital). A qualification run would have failed all twenty-five at the
    # identity gate without spending a single analysis.
    #
    # IDENTITY ONLY. Legal name, common name, canonical domain, the names a
    # person might type, and the company's own pages. No lens, no business
    # model, no decision, no conclusion: every sentence a reader sees is
    # still derived from documents retrieved at run time.
    #
    # EVERY URL BELOW RETURNED 200 THROUGH `safe_fetch` -- the product's own
    # fetcher, not curl -- and every candidate came from the publisher's own
    # navigation rather than from a list of plausible slugs. Where a site
    # refused the fetcher, the row carries NO sources and says so: a guessed
    # path produces a measured zero that reads as "this company publishes
    # nothing", which was never a fact about the company.
    # ------------------------------------------------------------------
    {
        "entity_id": "axonius",
        "legal_name": "Axonius Inc.",
        "common_name": "Axonius",
        "country": "United States",
        "primary_domain": "axonius.com",
        "aliases": ("axonius", "axonius inc"),
        "ambiguity_notes": (
            "Its own site refused retrieval when this row was written (HTTP 429), "
            "so the only URL it asserts is the company's own front door, which is "
            "not a guessed path. A run opens there and reports what it could and "
            "could not read."
        ),
        "sources": (
            ("https://axonius.com/",
             _CORPORATE, "home", _P),
        ),
    },
    {
        "entity_id": "arctic_wolf",
        "legal_name": "Arctic Wolf Networks, Inc.",
        "common_name": "Arctic Wolf",
        "country": "United States",
        "primary_domain": "arcticwolf.com",
        "aliases": ("arctic wolf", "arcticwolf", "arctic wolf networks"),
        "sources": (
            ("https://arcticwolf.com/company/faq",
             _CORPORATE, "about", _P),
            ("https://arcticwolf.com/solutions",
             _SEGMENT, "platform", _P),
            ("https://arcticwolf.com/customers",
             _CUSTOMERS, "customers", _S),
        ),
    },
    {
        "entity_id": "cribl",
        "legal_name": "Cribl, Inc.",
        "common_name": "Cribl",
        "country": "United States",
        "primary_domain": "cribl.io",
        "aliases": ("cribl", "cribl inc", "cribl stream"),
        "sources": (
            ("https://cribl.io/about-us",
             _CORPORATE, "about", _P),
            ("https://cribl.io/products",
             _SEGMENT, "platform", _P),
            ("https://cribl.io/pricing/plan",
             _PRICING, "pricing", _P),
            ("https://cribl.io/customers",
             _CUSTOMERS, "customers", _S),
            ("https://cribl.io/newsroom",
             _NEWSROOM, "news", _S),
        ),
    },
    {
        "entity_id": "onepassword",
        "legal_name": "AgileBits Inc.",
        "common_name": "1Password",
        "country": "United States",
        "primary_domain": "1password.com",
        "aliases": ("1password", "1 password", "onepassword", "agilebits"),
        "ambiguity_notes": (
            "The legal entity is AgileBits Inc.; the product and the company are "
            "presented as 1Password everywhere the company publishes."
        ),
        "sources": (
            ("https://1password.com/company",
             _CORPORATE, "about", _P),
            ("https://1password.com/platform",
             _SEGMENT, "platform", _P),
            ("https://1password.com/pricing",
             _PRICING, "pricing", _P),
            ("https://1password.com/customers/oracle-red-bull-racing-for-developers",
             _CUSTOMERS, "customers", _S),
            ("https://1password.com/press",
             _NEWSROOM, "news", _S),
        ),
    },
    {
        "entity_id": "illumio",
        "legal_name": "Illumio, Inc.",
        "common_name": "Illumio",
        "country": "United States",
        "primary_domain": "illumio.com",
        "aliases": ("illumio", "illumio inc"),
        "sources": (
            ("https://www.illumio.com/company/leadership",
             _CORPORATE, "about", _P),
            ("https://www.illumio.com/solutions",
             _SEGMENT, "platform", _P),
            ("https://www.illumio.com/customers",
             _CUSTOMERS, "customers", _S),
            ("https://www.illumio.com/company/news-awards",
             _NEWSROOM, "news", _S),
        ),
    },
    {
        "entity_id": "abnormal_ai",
        "legal_name": "Abnormal Security Corporation",
        "common_name": "Abnormal AI",
        "country": "United States",
        "primary_domain": "abnormal.ai",
        "aliases": ("abnormal ai", "abnormal security", "abnormal"),
        "ambiguity_notes": (
            "Renamed from Abnormal Security to Abnormal AI and publishes at "
            "abnormal.ai; both names resolve here."
        ),
        "sources": (
            ("https://abnormal.ai/about",
             _CORPORATE, "about", _P),
            ("https://abnormal.ai/platform/attune",
             _SEGMENT, "platform", _P),
            ("https://abnormal.ai/customers/love",
             _CUSTOMERS, "customers", _S),
            ("https://abnormal.ai/newsroom",
             _NEWSROOM, "news", _S),
        ),
    },
    {
        "entity_id": "netskope",
        "legal_name": "Netskope, Inc.",
        "common_name": "Netskope",
        "country": "United States",
        "primary_domain": "netskope.com",
        "aliases": ("netskope", "netskope inc"),
        "sources": (
            ("https://netskope.com/company",
             _CORPORATE, "about", _P),
            ("https://www.netskope.com/products",
             _SEGMENT, "platform", _P),
            ("https://netskope.com/customers",
             _CUSTOMERS, "customers", _S),
            ("https://www.netskope.com/company/newsroom",
             _NEWSROOM, "news", _S),
        ),
    },
    {
        "entity_id": "clio",
        "legal_name": "Themis Solutions Inc.",
        "common_name": "Clio",
        "country": "United States",
        "primary_domain": "clio.com",
        "aliases": ("clio", "themis solutions", "clio legal"),
        "ambiguity_notes": (
            "Its own site refused retrieval when this row was written (HTTP 403), "
            "so the only URL it asserts is the company's own front door, which is "
            "not a guessed path. A run opens there and reports what it could and "
            "could not read."
        ),
        "sources": (
            ("https://clio.com/",
             _CORPORATE, "home", _P),
        ),
    },
    {
        "entity_id": "coveo",
        "legal_name": "Coveo Solutions Inc.",
        "common_name": "Coveo",
        "country": "United States",
        "primary_domain": "coveo.com",
        "aliases": ("coveo", "coveo solutions"),
        "listings": (("TSX", "CVO"),),
        "ambiguity_notes": (
            "A public filer on the Toronto Stock Exchange (TSX: CVO)."
        ),
        "sources": (
            ("https://coveo.com/en/company/esg",
             _CORPORATE, "about", _P),
            ("https://coveo.com/en/platform",
             _SEGMENT, "platform", _P),
            ("https://coveo.com/en/pricing",
             _PRICING, "pricing", _P),
            ("https://coveo.com/en/company/customers",
             _CUSTOMERS, "customers", _S),
        ),
    },
    {
        "entity_id": "procore",
        "legal_name": "Procore Technologies, Inc.",
        "common_name": "Procore",
        "country": "United States",
        "primary_domain": "procore.com",
        "aliases": ("procore", "procore technologies"),
        "listings": (("NYSE", "PCOR"),),
        "sec_cik": "1611052",
        "ambiguity_notes": (
            "A public filer (NYSE: PCOR)."
        ),
        "sources": (
            ("https://procore.com/en-ca/about",
             _CORPORATE, "about", _P),
            ("https://procore.com/en-ca/products",
             _SEGMENT, "platform", _P),
            ("https://procore.com/en-ca/pricing",
             _PRICING, "pricing", _P),
        ),
    },
    {
        "entity_id": "servicetitan",
        "legal_name": "ServiceTitan, Inc.",
        "common_name": "ServiceTitan",
        "country": "United States",
        "primary_domain": "servicetitan.com",
        "aliases": ("servicetitan", "service titan"),
        "listings": (("NASDAQ", "TTAN"),),
        "sec_cik": "1638826",
        "ambiguity_notes": (
            "A public filer (NASDAQ: TTAN)."
        ),
        "sources": (
            ("https://servicetitan.com/company",
             _CORPORATE, "about", _P),
            ("https://servicetitan.com/products/convex",
             _SEGMENT, "platform", _P),
            ("https://servicetitan.com/pricing",
             _PRICING, "pricing", _P),
            ("https://servicetitan.com/case-studies",
             _CUSTOMERS, "customers", _S),
            ("https://servicetitan.com/press",
             _NEWSROOM, "news", _S),
        ),
    },
    {
        "entity_id": "motive",
        "legal_name": "Motive Technologies, Inc.",
        "common_name": "Motive",
        "country": "United States",
        "primary_domain": "gomotive.com",
        "aliases": ("motive", "gomotive", "motive technologies", "keeptruckin"),
        "ambiguity_notes": (
            "Publishes at gomotive.com, not motive.com, and was formerly KeepTruckin "
            "-- both are aliases so a person who types either reaches the same "
            "company."
        ),
        "sources": (
            ("https://gomotive.com/company/news",
             _CORPORATE, "about", _P),
            ("https://gomotive.com/products",
             _SEGMENT, "platform", _P),
            ("https://gomotive.com/customers",
             _CUSTOMERS, "customers", _S),
            ("https://gomotive.com/company/news",
             _NEWSROOM, "news", _S),
        ),
    },
    {
        "entity_id": "verkada",
        "legal_name": "Verkada Inc.",
        "common_name": "Verkada",
        "country": "United States",
        "primary_domain": "verkada.com",
        "aliases": ("verkada", "verkada inc"),
        "sources": (
            ("https://verkada.com/about",
             _CORPORATE, "about", _P),
            ("https://verkada.com/solutions/k-12",
             _SEGMENT, "platform", _P),
            ("https://verkada.com/newsroom",
             _NEWSROOM, "news", _S),
        ),
    },
    {
        "entity_id": "vanta",
        "legal_name": "Vanta Inc.",
        "common_name": "Vanta",
        "country": "United States",
        "primary_domain": "vanta.com",
        "aliases": ("vanta", "vanta inc"),
        "sources": (
            ("https://vanta.com/company/about",
             _CORPORATE, "about", _P),
            ("https://vanta.com/products/ai",
             _SEGMENT, "platform", _P),
            ("https://vanta.com/pricing",
             _PRICING, "pricing", _P),
            ("https://vanta.com/customers",
             _CUSTOMERS, "customers", _S),
            ("https://vanta.com/company/press",
             _NEWSROOM, "news", _S),
        ),
    },
    {
        "entity_id": "snyk",
        "legal_name": "Snyk Limited",
        "common_name": "Snyk",
        "country": "United States",
        "primary_domain": "snyk.io",
        "aliases": ("snyk", "snyk limited"),
        "sources": (
            ("https://snyk.io/about",
             _CORPORATE, "about", _P),
            ("https://snyk.io/platform",
             _SEGMENT, "platform", _P),
            ("https://snyk.io/plans",
             _PRICING, "pricing", _P),
            ("https://snyk.io/customers",
             _CUSTOMERS, "customers", _S),
            ("https://snyk.io/news",
             _NEWSROOM, "news", _S),
        ),
    },
    {
        "entity_id": "chainguard",
        "legal_name": "Chainguard, Inc.",
        "common_name": "Chainguard",
        "country": "United States",
        "primary_domain": "chainguard.dev",
        "aliases": ("chainguard", "chainguard inc"),
        "sources": (
            ("https://chainguard.dev/about-us",
             _CORPORATE, "about", _P),
            ("https://chainguard.dev/solutions/pci",
             _SEGMENT, "platform", _P),
            ("https://chainguard.dev/pricing",
             _PRICING, "pricing", _P),
            ("https://chainguard.dev/customers",
             _CUSTOMERS, "customers", _S),
            ("https://chainguard.dev/newsroom",
             _NEWSROOM, "news", _S),
        ),
    },
    {
        "entity_id": "island",
        "legal_name": "Island Technology Inc.",
        "common_name": "Island",
        "country": "United States",
        "primary_domain": "island.io",
        "aliases": ("island", "island io", "island browser", "island technology"),
        "ambiguity_notes": (
            "\"Island\" is a common word and the SEC registrant table answers a typed "
            "\"Island\" with Orchid Island Capital and Cayman-Islands filers. This row "
            "exists so the enterprise browser company resolves on its own name; the "
            "aliases are deliberately specific for the same reason."
        ),
        "sources": (
            ("https://island.io/about",
             _CORPORATE, "about", _P),
            ("https://island.io/product-support",
             _SEGMENT, "platform", _P),
            ("https://island.io/buyers-guide",
             _PRICING, "pricing", _P),
            ("https://www.island.io/case-study/hendrick-motorsports",
             _CUSTOMERS, "customers", _S),
            ("https://island.io/press",
             _NEWSROOM, "news", _S),
        ),
    },
    {
        "entity_id": "ninjaone",
        "legal_name": "NinjaOne, LLC",
        "common_name": "NinjaOne",
        "country": "United States",
        "primary_domain": "ninjaone.com",
        "aliases": ("ninjaone", "ninja one", "ninjarmm"),
        "sources": (
            ("https://ninjaone.com/about-us",
             _CORPORATE, "about", _P),
            ("https://ninjaone.com/platform",
             _SEGMENT, "platform", _P),
            ("https://ninjaone.com/pricing",
             _PRICING, "pricing", _P),
            ("https://ninjaone.com/press/customers-choice-2026-gartner-peer-insights-voice-of-the-customer",
             _CUSTOMERS, "customers", _S),
            ("https://ninjaone.com/press",
             _NEWSROOM, "news", _S),
        ),
    },
    {
        "entity_id": "huntress",
        "legal_name": "Huntress Labs Incorporated",
        "common_name": "Huntress",
        "country": "United States",
        "primary_domain": "huntress.com",
        "aliases": ("huntress", "huntress labs"),
        "sources": (
            ("https://huntress.com/company/press",
             _CORPORATE, "about", _P),
            ("https://huntress.com/platform",
             _SEGMENT, "platform", _P),
            ("https://huntress.com/pricing",
             _PRICING, "pricing", _P),
            ("https://huntress.com/why-huntress/case-studies",
             _CUSTOMERS, "customers", _S),
            ("https://huntress.com/company/press",
             _NEWSROOM, "news", _S),
        ),
    },
    {
        "entity_id": "veza",
        "legal_name": "Veza Technologies, Inc.",
        "common_name": "Veza",
        "country": "United States",
        "primary_domain": "veza.com",
        "aliases": ("veza", "veza technologies"),
        "sources": (
            ("https://veza.com/company",
             _CORPORATE, "about", _P),
            ("https://veza.com/product",
             _SEGMENT, "platform", _P),
            ("https://veza.com/customers",
             _CUSTOMERS, "customers", _S),
            ("https://veza.com/company/press-room",
             _NEWSROOM, "news", _S),
        ),
    },
    {
        "entity_id": "expel",
        "legal_name": "Expel, Inc.",
        "common_name": "Expel",
        "country": "United States",
        "primary_domain": "expel.com",
        "aliases": ("expel", "expel inc"),
        "sources": (
            ("https://expel.com/about",
             _CORPORATE, "about", _P),
            ("https://expel.com/solutions",
             _SEGMENT, "platform", _P),
            ("https://expel.com/customers",
             _CUSTOMERS, "customers", _S),
            ("https://expel.com/about/newsroom",
             _NEWSROOM, "news", _S),
        ),
    },
    {
        "entity_id": "dragos",
        "legal_name": "Dragos, Inc.",
        "common_name": "Dragos",
        "country": "United States",
        "primary_domain": "dragos.com",
        "aliases": ("dragos", "dragos inc"),
        "sources": (
            ("https://www.dragos.com/about",
             _CORPORATE, "about", _P),
            ("https://www.dragos.com/resources/press-release",
             _NEWSROOM, "news", _S),
        ),
    },
    {
        "entity_id": "material_security",
        "legal_name": "Material Security, Inc.",
        "common_name": "Material Security",
        "country": "United States",
        "primary_domain": "material.security",
        "aliases": ("material security", "material"),
        "ambiguity_notes": (
            "Publishes on the .security top-level domain, which is the company's own "
            "canonical domain and not a typo."
        ),
        "sources": (
            ("https://material.security/about",
             _CORPORATE, "about", _P),
            ("https://material.security/product",
             _SEGMENT, "platform", _P),
            ("https://material.security/pricing",
             _PRICING, "pricing", _P),
            ("https://material.security/customers",
             _CUSTOMERS, "customers", _S),
        ),
    },
    {
        "entity_id": "obsidian_security",
        "legal_name": "Obsidian Security, Inc.",
        "common_name": "Obsidian Security",
        "country": "United States",
        "primary_domain": "obsidiansecurity.com",
        "aliases": ("obsidian security", "obsidian"),
        "sources": (
            ("https://obsidiansecurity.com/company",
             _CORPORATE, "about", _P),
            ("https://obsidiansecurity.com/platform-overview",
             _SEGMENT, "platform", _P),
            ("https://obsidiansecurity.com/pricing",
             _PRICING, "pricing", _P),
            ("https://obsidiansecurity.com/customers",
             _CUSTOMERS, "customers", _S),
            ("https://obsidiansecurity.com/news-and-press",
             _NEWSROOM, "news", _S),
        ),
    },
    {
        "entity_id": "okta",
        "legal_name": "Okta, Inc.",
        "common_name": "Okta",
        "country": "United States",
        "primary_domain": "okta.com",
        "aliases": ("okta", "okta inc", "auth0"),
        "listings": (("NASDAQ", "OKTA"),),
        "sec_cik": "1660134",
        "ambiguity_notes": (
            "A public filer (CIK 1660134, NASDAQ: OKTA), so the SEC registrant table "
            "already answers a typed \"Okta\". This row adds the canonical domain and "
            "the Auth0 alias, which the registrant table does not carry."
        ),
        "sources": (
            ("https://www.okta.com/company",
             _CORPORATE, "about", _P),
            ("https://www.okta.com/solutions",
             _SEGMENT, "platform", _P),
            ("https://www.okta.com/pricing",
             _PRICING, "pricing", _P),
            ("https://okta.com/customers",
             _CUSTOMERS, "customers", _S),
            ("https://www.okta.com/newsroom",
             _NEWSROOM, "news", _S),
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
