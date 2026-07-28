"""A second adversarial pass, sharing nothing with the first.

WHY A SECOND SET
----------------
The first suite reached a hundred per cent, which says the suite stopped
finding things — not that the product stopped having them. A suite that has
been optimised against is a suite that measures how well the code fits it.

So none of the ninety-one cases are reused. New companies, new pathologies,
and specifically the shapes the first set never contained: a site that is one
enormous page, a site whose every page is the same page, a company whose name
is a common English word, a page whose metadata contradicts its body, a
company that only exists in another language, a site that redirects in a loop,
a page whose evidence contradicts itself in consecutive sentences.

Each fixture below encodes a hypothesis about how the product breaks. Where
the hypothesis was right, the defect became a fix and a regression test; where
it was wrong, the fixture stays anyway, because tomorrow's change is what it
guards against.
"""
from __future__ import annotations

from intent_engine.product_eval.sites import Site, _page

# --- a company whose name is a common word ------------------------------------
# Identity resolution keys off the company name. "Apex" appears in the text of
# every page about anything, so any name-matching heuristic that is even
# slightly loose will find the company everywhere and nowhere.
APEX = Site(
    "apex", "Apex", "https://apex.example", "private",
    pages={
        "/": _page("Apex", [
            "Apex provides scheduling software for field service teams. "
            "Dispatchers assign jobs, technicians see their route, and the "
            "office sees where every job stands.",
        ]),
        "/about": _page("About Apex", [
            "Apex is a privately held company founded by two former field "
            "technicians. We build scheduling software for trades businesses "
            "with between five and two hundred vans on the road.",
        ]),
        "/products": _page("Apex scheduling", [
            "Dispatch board, route optimisation, mobile job cards and "
            "invoicing. One platform for scheduling and billing so an office "
            "manager does not rekey a job twice.",
        ]),
        "/customers": _page("Apex customers", [
            "Case studies describe an electrical contractor cutting drive "
            "time and a plumbing firm invoicing on the day of the job.",
        ]),
        "/pricing": _page("Apex pricing", [
            "Per-technician pricing starts at a low monthly price with volume "
            "discounts above fifty vans.",
        ]),
        "/docs": _page("Apex documentation", [
            "The API covers jobs, technicians, routes and webhooks. The "
            "changelog records monthly releases since 2024.",
        ]),
    },
    missing=("/investors", "/careers"),
)

# --- metadata that contradicts the body ---------------------------------------
# The brief prefers the meta description, on the reasoning that it is the one
# place a company describes itself in a sentence. A stale or copied meta tag is
# common, and following it blindly means describing the wrong business.
STALE_META = Site(
    "stale_meta", "Halcyon Data", "https://halcyon.example", "private",
    pages={
        "/": ('<html><head><title>Halcyon Data</title>'
              '<meta name="description" content="Halcyon Data is the leading '
              'provider of artificial intelligence solutions for every '
              'industry worldwide.">'
              "</head><body><main><h1>Halcyon Data</h1>"
              "<p>Halcyon Data builds data quality tooling for analytics "
              "teams. Pipelines are monitored for schema drift, null spikes "
              "and freshness, and owners are alerted before a dashboard "
              "goes wrong.</p></main></body></html>"),
        "/about": _page("About Halcyon Data", [
            "Halcyon Data is an eleven-person company building data quality "
            "monitoring for analytics teams. We are privately held and do not "
            "publish revenue.",
        ]),
        "/products": _page("Halcyon monitors", [
            "Schema drift detection, freshness checks, volume anomaly alerts "
            "and column-level lineage across warehouse tables.",
        ]),
        "/docs": _page("Halcyon documentation", [
            "The API covers monitors, incidents and webhooks. The changelog "
            "records fortnightly releases since 2025.",
        ]),
        "/pricing": _page("Halcyon pricing", [
            "Per-monitor pricing starts at a low monthly price. Volume "
            "pricing is quoted above one thousand monitors.",
        ]),
        "/customers": _page("Halcyon customers", [
            "Case studies describe an analytics team catching a broken "
            "upstream job before the weekly board pack was sent.",
        ]),
    },
    missing=("/investors", "/careers"),
)

# --- one enormous page, everything else missing --------------------------------
# A single-page site. Every known path 404s, and the whole company is one long
# document — which is the opposite shape from everything the first suite had.
ONE_PAGER = Site(
    "one_pager", "Kettle", "https://kettle.example", "private",
    pages={
        "/": ("<html><head><title>Kettle</title></head><body><main>"
              "<h1>Kettle</h1>"
              "<p>Kettle runs payroll for restaurants. Hours come off the "
              "rota, tips are split by the rules the venue already uses, and "
              "staff are paid weekly.</p>"
              "<h2>Product</h2>"
              "<p>Rota import, tip distribution, weekly pay runs, and "
              "year-end filings. One platform for scheduling hours and "
              "paying for them.</p>"
              "<h2>Customers</h2>"
              "<p>Case studies describe a twelve-site group cutting payroll "
              "preparation from two days to two hours, and an independent "
              "restaurant paying staff weekly for the first time.</p>"
              "<h2>Pricing</h2>"
              "<p>Per-employee pricing starts at a low monthly price. Volume "
              "pricing is quoted above five hundred employees.</p>"
              "<h2>Company</h2>"
              "<p>Kettle is privately held, founded in 2022, and does not "
              "publish revenue. The team is nineteen people.</p>"
              "</main></body></html>"),
    },
    missing=("/about", "/products", "/customers", "/pricing", "/careers",
             "/investors", "/docs", "/news", "/blog"),
)

# --- every page is the same page ----------------------------------------------
# A misconfigured site that serves its homepage for every path. Source-count
# and family-coverage gates both read this as breadth; it is one document
# wearing seven hats, and a report built on it says one thing seven times.
_ECHO_BODY = _page("Vantage Systems", [
    "Vantage Systems is a technology company delivering innovative solutions "
    "for the modern enterprise. Contact us to learn more.",
])
ECHO_SITE = Site(
    "echo_site", "Vantage Systems", "https://vantage.example", "public",
    pages={path: _ECHO_BODY for path in
           ("/", "/about", "/products", "/customers", "/pricing", "/careers",
            "/investors", "/docs", "/news")},
)

# --- evidence that contradicts itself -----------------------------------------
# Consecutive sentences that cannot both be true. The product must not pick one
# silently, and must not average them into a claim neither source supports.
CONTRADICTORY = Site(
    "contradictory", "Northwind Freight", "https://northwind.example",
    "public",
    pages={
        "/": _page("Northwind Freight", [
            "Northwind Freight operates a temperature-controlled road network "
            "across northern Europe, moving pharmaceutical and food cargo "
            "under continuous monitoring.",
        ]),
        "/about": _page("About Northwind Freight", [
            "Northwind Freight is the largest cold-chain carrier in the "
            "region. Northwind Freight is a small independent operator "
            "competing against the largest carriers in the region.",
        ]),
        "/products": _page("Northwind services", [
            "Temperature-controlled linehaul, bonded warehousing and "
            "last-mile pharmaceutical delivery. One platform for booking and "
            "tracking every consignment.",
        ]),
        "/investors": _page("Northwind investor relations", [
            "Quarterly results report business segments for linehaul and "
            "warehousing. The annual report discloses risk factors including "
            "dependence on a limited number of customers in pharmaceutical "
            "distribution.",
            "Fleet capacity expansion was completed in 2026. Fleet capacity "
            "was reduced in 2026 in response to demand.",
        ]),
        "/customers": _page("Northwind customers", [
            "Case studies describe a vaccine distributor and a supermarket "
            "group. Independent trade press reports service failures during "
            "the 2026 summer peak.",
        ]),
        "/news": _page("Northwind newsroom", [
            "July 2026: Northwind announced capacity expansion, citing "
            "demand from pharmaceutical customers.",
        ]),
        "/careers": _page("Careers at Northwind", [
            "We are hiring drivers and warehouse staff across the network.",
        ]),
    },
)

# --- hostile HTML -------------------------------------------------------------
# Unclosed tags, a nav that never ends, script that looks like content, and a
# body wrapped in a region the parser is told to drop. A parser that trusts
# markup structure loses this page entirely.
BROKEN_MARKUP = Site(
    "broken_markup", "Ironbark", "https://ironbark.example", "private",
    pages={
        "/": ("<html><head><title>Ironbark<body>"
              "<nav><a href=/about>About<a href=/products>Products"
              "<div><p>Ironbark builds inspection drones for utility "
              "networks. Operators fly transmission corridors and the "
              "software flags vegetation encroachment and damaged hardware."
              "<p>The fleet is managed from one console with automated "
              "flight logs for regulators."
              "</body>"),
        "/about": ("<html><head><title>About Ironbark</title></head><body>"
                   "<header><p>Ironbark is privately held and was founded in "
                   "2021 by two aerospace engineers. The company builds "
                   "inspection drones and the analysis software that reads "
                   "what they capture.</p></header></body></html>"),
        "/products": _page("Ironbark platform", [
            "Autonomous flight planning, defect detection and a regulator-"
            "ready flight log. One platform for inspection and reporting.",
        ]),
        "/docs": _page("Ironbark documentation", [
            "The API covers flights, defects and webhooks. The changelog "
            "records monthly releases since 2024.",
        ]),
        "/pricing": _page("Ironbark pricing", [
            "Per-aircraft pricing starts at a monthly price with volume "
            "discounts above twenty aircraft.",
        ]),
        "/customers": _page("Ironbark customers", [
            "Case studies describe a distribution network operator reducing "
            "helicopter inspection hours.",
        ]),
    },
    missing=("/investors", "/careers"),
)

# --- a company that publishes in another language -----------------------------
# Nothing is in English. The product must not describe it in English it
# invented, and must not treat unreadable evidence as absent evidence.
NON_ENGLISH = Site(
    "non_english", "Sonnenberg Werke", "https://sonnenberg.example", "public",
    pages={
        "/": _page("Sonnenberg Werke", [
            "Die Sonnenberg Werke fertigen Präzisionsgetriebe für "
            "Windkraftanlagen und industrielle Antriebe an drei Standorten "
            "in Deutschland und Polen.",
        ]),
        "/about": _page("Über uns", [
            "Sonnenberg Werke ist ein Familienunternehmen in dritter "
            "Generation mit rund zwölfhundert Mitarbeitenden.",
        ]),
        "/investors": _page("Investor Relations", [
            "Der Geschäftsbericht weist die Segmente Getriebe und Service "
            "getrennt aus. Die Risikofaktoren nennen die Abhängigkeit von "
            "wenigen Grosskunden.",
        ]),
        "/products": _page("Produkte", [
            "Planetengetriebe, Stirnradgetriebe und Serviceverträge für "
            "Bestandsanlagen.",
        ]),
    },
    missing=("/customers", "/pricing", "/careers", "/docs"),
)

# --- a marketing site with no substance ---------------------------------------
# Every page is real, well-formed, and says nothing. This is the commonest
# company on the internet and the hardest honest case: there is plenty to
# retrieve and nothing to conclude.
ALL_SIZZLE = Site(
    "all_sizzle", "Momentum Global", "https://momentum.example", "private",
    pages={
        "/": _page("Momentum Global", [
            "Momentum Global is a leading provider of next-generation "
            "solutions that empower organisations to unlock their full "
            "potential in a rapidly changing world.",
        ]),
        "/about": _page("About Momentum Global", [
            "Our mission is to transform how the world works. We believe in "
            "excellence, partnership and relentless innovation.",
        ]),
        "/products": _page("Momentum solutions", [
            "Our suite of best-in-class offerings delivers measurable value "
            "across the enterprise, at scale, with confidence.",
        ]),
        "/customers": _page("Momentum customers", [
            "Trusted by industry leaders around the globe. Join thousands of "
            "organisations already transforming with Momentum.",
        ]),
        "/pricing": _page("Momentum pricing", [
            "Contact sales for a tailored quote built around your needs.",
        ]),
        "/careers": _page("Careers at Momentum Global", [
            "Join a team of passionate people doing the best work of their "
            "careers.",
        ]),
    },
    missing=("/investors", "/docs"),
)

ADVERSARIAL_SITES = {s.key: s for s in (
    APEX, STALE_META, ONE_PAGER, ECHO_SITE, CONTRADICTORY, BROKEN_MARKUP,
    NON_ENGLISH, ALL_SIZZLE,
)}
