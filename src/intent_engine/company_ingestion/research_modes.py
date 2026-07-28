"""What KIND of company this is, and therefore what evidence to expect.

WHY THIS EXISTS
---------------
Every gate in the pipeline was written against one company: a public one. It
wants five sources, three evidence families, a direction source and a market
source, and it is right to want them — of a company that files. Pointed at a
private startup it demands investor material that does not exist, and pointed
at a dental practice it demands a strategy page from a business whose entire
public footprint is a services list and opening hours.

The failure is not that those companies score badly. It is that they score
badly for reasons that are true of every company like them, which means the
score carries no information. "Bloom Dental has no investor relations page" is
not a finding.

So the evidence model becomes a function of the company, and the mode is
inferred from what the evidence itself looks like rather than declared by the
user — a user who knew enough to classify their own target correctly would not
need the product.

WHAT A MODE MAY AND MAY NOT CHANGE
----------------------------------
A mode may change what is EXPECTED: how many sources are enough, which
families are mandatory, whether a strategic hypothesis is required before a
brief may be shown.

A mode may never change what is TRUE. It cannot raise confidence, cannot
promote a company-owned page to independent corroboration, and cannot suppress
a limitation. A small company gets a fairer standard, not a friendlier one.
"""
from __future__ import annotations

RESEARCH_MODE_VERSION = "ci_research_modes.v1"

PUBLIC_COMPANY = "public_company"
PRIVATE_COMPANY = "private_company"
SMALL_BUSINESS = "small_business"

RESEARCH_MODES = (PUBLIC_COMPANY, PRIVATE_COMPANY, SMALL_BUSINESS)

# Reader-facing names. The mode is shown, because a reader judging a briefing
# needs to know which standard it was held to — but never as an identifier.
MODE_LABEL = {
    PUBLIC_COMPANY: "public company",
    PRIVATE_COMPANY: "private company",
    SMALL_BUSINESS: "small or local business",
}

MODE_EXPECTATION = {
    PUBLIC_COMPANY: "Filings, investor material and segment reporting are "
                    "expected, and their absence is a finding.",
    PRIVATE_COMPANY: "No filings exist. Product pages, documentation, "
                     "pricing, hiring and founder statements carry the "
                     "analysis, and financial questions stay open.",
    SMALL_BUSINESS: "Public evidence is a website, services, prices and "
                    "reviews. There is no strategy document to find, and "
                    "expecting one would only report that the business is "
                    "small.",
}

# Phrases that identify a filer. Deliberately narrow: these appear on companies
# that report to a regulator and essentially nowhere else.
_PUBLIC_MARKERS = (
    "form 10-k", "form 10-q", "form 8-k", "form 20-f", "form 6-k",
    "securities exchange act", "securities and exchange commission",
    "investor relations", "quarterly results", "annual report",
    "consolidated results", "shareholders", "earnings call",
    "business segments", "reportable segments", "sec filing",
)

# Phrases that identify a business serving people who physically turn up.
_LOCAL_MARKERS = (
    "opening hours", "open six days", "open seven days", "walk-in",
    "appointment", "appointments", "our location", "locations",
    "book a table", "in store", "call us on", "directions",
    "serving the", "family-run", "family run", "on-site parking",
    "saturday mornings", "surgeries", "clinic", "salon", "cafe", "restaurant",
)

# Phrases that identify a company that says it is NOT public.
_PRIVATE_MARKERS = (
    "privately held", "private company", "we do not publish revenue",
    "does not publish financial", "venture-backed", "seed round",
    "series a", "series b", "founded in",
)

# A small business publishes few pages. This is a floor on "small enough that
# strategy documents would not exist", not a judgement about the business.
SMALL_SITE_PAGES = 8


def _corpus(documents) -> str:
    parts = []
    for document in documents or ():
        parts.append(str(document.get("text_content") or ""))
        parts.append(str(document.get("title") or ""))
        parts.append(str(document.get("url") or ""))
    return " ".join(parts).lower()


def _hits(corpus: str, markers) -> int:
    return sum(1 for marker in markers if marker in corpus)


def _has_investor_family(documents) -> bool:
    from intent_engine.company_ingestion.coverage import INVESTOR, family_of
    return any(family_of(d) == INVESTOR for d in documents or ())


def infer_mode(documents, *, identity=None) -> dict:
    """Which evidence model this company should be held to, and why.

    Returns the mode with the evidence that chose it, so the decision is
    auditable rather than a bare label — a reader who disagrees with the mode
    can see what led to it.
    """
    corpus = _corpus(documents)
    public_hits = _hits(corpus, _PUBLIC_MARKERS)
    # A retrieved page the taxonomy already classified as investor material is
    # a stronger public signal than any phrase, because it survived
    # classification rather than merely appearing in prose. Shopify's fixture
    # says "investor relations" exactly once and was read as private on that
    # count alone — and a public company assessed as private is not held to
    # the financial disclosure it actually has.
    if _has_investor_family(documents):
        public_hits += 1
    local_hits = _hits(corpus, _LOCAL_MARKERS)
    private_hits = _hits(corpus, _PRIVATE_MARKERS)
    page_count = len(list(documents or ()))

    # A registered filer is a public company however small its website is.
    # This is checked first because it is the only signal that comes from a
    # regulator rather than from marketing copy.
    if public_hits >= 2:
        mode, why = PUBLIC_COMPANY, (
            f"{public_hits} filing or investor-reporting markers in the "
            f"retrieved evidence")
    elif local_hits >= 2 and page_count <= SMALL_SITE_PAGES:
        mode, why = SMALL_BUSINESS, (
            f"{local_hits} markers of a business serving people in one place, "
            f"across {page_count} page(s)")
    elif private_hits >= 1 or page_count <= SMALL_SITE_PAGES:
        mode, why = PRIVATE_COMPANY, (
            f"{private_hits} marker(s) of a privately-held company and no "
            f"filing or investor reporting")
    else:
        mode, why = PRIVATE_COMPANY, "no filing or investor reporting found"

    return {
        "mode": mode,
        "label": MODE_LABEL[mode],
        "expectation": MODE_EXPECTATION[mode],
        "why": why,
        "signals": {"public": public_hits, "local": local_hits,
                    "private": private_hits, "pages": page_count},
        "research_mode_version": RESEARCH_MODE_VERSION,
    }


# --- what each mode expects ---------------------------------------------------
# Public-company numbers are exactly the existing gate. They are repeated here
# rather than relaxed, so that adding modes changed nothing about the companies
# the gate was already right about.
MODE_EXPECTATIONS = {
    PUBLIC_COMPANY: {
        "min_sources_full": 5,
        "min_families_full": 3,
        "min_slide_units": 5,
        "requires_direction_source": True,
        "requires_market_source": True,
        "requires_hypothesis": True,
        "expects_financial_disclosure": True,
    },
    PRIVATE_COMPANY: {
        # A private company has no investor family to find, so demanding three
        # families is demanding one that cannot exist. Documentation, pricing
        # and hiring are the direction evidence here.
        "min_sources_full": 4,
        "min_families_full": 3,
        "min_slide_units": 5,
        "requires_direction_source": False,
        "requires_market_source": True,
        "requires_hypothesis": True,
        "expects_financial_disclosure": False,
    },
    SMALL_BUSINESS: {
        # A dental practice publishes a services page, prices, hours and
        # reviews. That is a complete public footprint, not a thin one, and a
        # useful briefing can be built from it — but a strategic hypothesis in
        # the venture sense would be invented rather than observed, so it is
        # not required before the reader may be shown anything.
        "min_sources_full": 3,
        "min_families_full": 2,
        "min_slide_units": 3,
        "requires_direction_source": False,
        "requires_market_source": False,
        "requires_hypothesis": False,
        "expects_financial_disclosure": False,
    },
}


def expectations_for(mode: str) -> dict:
    return dict(MODE_EXPECTATIONS.get(mode, MODE_EXPECTATIONS[PUBLIC_COMPANY]))
