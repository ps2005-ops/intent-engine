"""Who wrote it, how authoritative it is, and whether it is independent.

THE VENUE DOES NOT DETERMINE THE AUTHOR.

A company's 10-Q reaches us through SEC EDGAR. EDGAR is a primary regulatory
venue, which makes the document authoritative and hard to fake -- and says
nothing at all about who wrote it. The company wrote it. It is not independent
corroboration of anything the company claims.

That distinction was lost once already, and the cost was a false metric: a
five-company study reported "EDGAR supplied 10 independent sources" because
the counter treated every class except `company_owned` and
`executive_statement` as independent, and EDGAR filings carry
`investor_material`. `reasoning.py` had the correct set the whole time; two
other call sites had their own, and disagreed.

So the predicate lives here once, and the four questions stay separate:

    authorship    who produced the words
    authority     how strong a record it is
    independence  whether the author is separate from the subject company
    venue         where it was hosted -- never an input to the other three
"""
from __future__ import annotations

# --- authorship --------------------------------------------------------------
COMPANY = "COMPANY"
EXECUTIVE = "COMPANY_EXECUTIVE"
CUSTOMER = "CUSTOMER"
COMPETITOR = "COMPETITOR"
THIRD_PARTY = "THIRD_PARTY_PUBLISHER"
PATTERN = "ANALYTICAL_PATTERN"
UNKNOWN = "UNKNOWN"

_AUTHORSHIP = {
    "company_owned": COMPANY,
    # A 10-K/10-Q/8-K is written BY the company. The regulator is the venue and
    # the enforcement, not the author.
    "investor_material": COMPANY,
    "executive_statement": EXECUTIVE,
    "customer_voice": CUSTOMER,
    "competitor": COMPETITOR,
    "independent_reporting": THIRD_PARTY,
    "historical_pattern": PATTERN,
    "unavailable_or_failed": UNKNOWN,
}

# --- authority ---------------------------------------------------------------
PRIMARY_REGULATORY_RECORD = "PRIMARY_REGULATORY_RECORD"
SELF_PUBLISHED = "SELF_PUBLISHED"
THIRD_PARTY_PUBLISHED = "THIRD_PARTY_PUBLISHED"
UNVERIFIED = "UNVERIFIED"

_REGULATORY_VENUES = ("sec.gov",)

# --- independence ------------------------------------------------------------
# Everything the company or its officers authored, whatever venue carried it.
COMPANY_AUTHORED = frozenset({COMPANY, EXECUTIVE})
# Authors that are separate from the subject company.
INDEPENDENT_AUTHORS = frozenset({CUSTOMER, COMPETITOR, THIRD_PARTY})


def authorship(source_class: str) -> str:
    return _AUTHORSHIP.get((source_class or "").strip(), UNKNOWN)


def authority(source_class: str, url: str = "") -> str:
    """Venue raises AUTHORITY only. It never changes authorship."""
    host = (url or "").split("/")[2].lower() if (url or "").count("/") > 2 \
        else (url or "").lower()
    if any(venue in host for venue in _REGULATORY_VENUES):
        return PRIMARY_REGULATORY_RECORD
    author = authorship(source_class)
    if author in COMPANY_AUTHORED:
        return SELF_PUBLISHED
    if author in INDEPENDENT_AUTHORS:
        return THIRD_PARTY_PUBLISHED
    return UNVERIFIED


def is_independent_of_subject(source_class: str) -> bool:
    """Can this corroborate a company claim from outside the company?

    The one predicate. A company filing hosted by a regulator answers False,
    however authoritative the venue.
    """
    return authorship(source_class) in INDEPENDENT_AUTHORS


def independent_count(source_classes) -> int:
    return sum(1 for c in source_classes if is_independent_of_subject(c))


def describe(source_class: str, url: str = "") -> dict:
    """All four answers, kept apart, for diagnostics and operator metrics."""
    return {"source_class": source_class,
            "authorship": authorship(source_class),
            "authority": authority(source_class, url),
            "independent_of_subject": is_independent_of_subject(source_class),
            "venue_host": (url or "").split("/")[2].lower()
            if (url or "").count("/") > 2 else ""}
