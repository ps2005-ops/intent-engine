"""Is this passage the company describing itself?

WHY A FOUR-STATE ANSWER
-----------------------
The previous rule was binary and deliberately strict: a passage counted as a
self-description only if it spoke in the first person or named the company.
That rule exists because of a measured leak — Stripe's page opened with

    "Figma democratizes design through its collaborative design products."

a customer story hosted on stripe.com, about somebody else, which the old
provenance logic had labelled a Stripe company claim. Strictness fixed that,
and the fix was right.

But strictness has a cost, and it was also measured. Brightledger's product
page says

    "Connectors read payout files from payment processors, match them to
     ledger entries, and raise an exception when a difference persists."

which is the single best sentence anyone has written about what Brightledger
does — and it neither says "we" nor says "Brightledger", so it was rejected
and the page fell back to something duller. Shopify loses a good opening the
same way. A binary rule has to choose which error to make everywhere, and
both errors are real.

So the answer has four states. CONFIRMED and NOT are unchanged in strength;
PROBABLE is the new middle, and it is only reachable through evidence that the
old rule was not looking at.

WHAT MAKES A PASSAGE *PROBABLE*
-------------------------------
Not the host. First-party hosting is necessary and nowhere near sufficient —
that is precisely the assumption that shipped Figma's description under
Stripe's name, and it is refused explicitly below.

The signal that actually separates Brightledger from Figma is **product
ownership**, read from the company's own site taxonomy. "Connectors" is a page
on Brightledger's own site, so a sentence whose subject is Connectors is
Brightledger describing its own product. "Figma" is not a page on Stripe's
site; it appears in the *title of a customer story*, which is a page class
that is rejected outright.

This is the signal the last attempt reached for and could not get. It tried to
read the other company's name out of the title, which turned "Connectors and
matches | Brightledger docs" into "Brightledger writing about Connectors" —
a common noun at a title's start is indistinguishable from a company name
without a lexicon. The lexicon was available the whole time: it is the
company's own sitemap.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Optional, Sequence, Tuple
from urllib.parse import urlparse

IDENTITY_VERSION = "self_description.v1"

CONFIRMED = "SELF_DESCRIPTION_CONFIRMED"
PROBABLE = "SELF_DESCRIPTION_PROBABLE"
NOT_SELF = "NOT_SELF_DESCRIPTION"
UNKNOWN = "UNKNOWN"

STATES = frozenset({CONFIRMED, PROBABLE, NOT_SELF, UNKNOWN})

#: States a caller may use as "the company's own account of itself".
USABLE = frozenset({CONFIRMED, PROBABLE})

# --- page classes that are never the focal company describing itself -------
#
# Each of these is a page a company publishes ABOUT SOMEONE ELSE, or about
# nothing. They live on the first-party domain, which is exactly why the host
# cannot be the test.
_REJECT_PATH = re.compile(
    r"/(customers?|case[-_]stud(y|ies)|success[-_]stor(y|ies)|stories|"
    r"partners?|integrations?|marketplace|directory|"
    r"compare|comparisons?|alternatives?|vs|versus|"
    r"legal|terms|privacy|cookie|dpa|sla|trust/legal)(/|$)", re.I)

_REJECT_TITLE = re.compile(
    r"\b(case study|customer story|success story|our customers|"
    r"customer spotlight|partner (story|spotlight|profile)|"
    r"integration|integrates with|works with|"
    r"vs\.?|versus|compared to|alternative to|alternatives|"
    r"terms of service|privacy policy|cookie policy)\b", re.I)

#: Pricing pages describe a price list, not a business. Separated from the
#: rejects above because a pricing page IS about the focal company — it just
#: never answers "what does this company do", and opening with a price list
#: was a measured defect (Notion, Linear and Brightledger all did it).
_PRICING = re.compile(r"/(pricing|plans?|buy)(/|$)|\bpricing\b", re.I)

#: Page classes whose whole purpose is to state what the company is.
_IDENTITY_PATH = re.compile(
    r"/(about|about[-_]us|company|who[-_]we[-_]are|our[-_]story|"
    r"platform|product|products|solutions?|overview|what[-_]we[-_]do|"
    r"docs?|documentation)(/|$)", re.I)

_FIRST_PERSON = re.compile(r"\b(we|our|us|ours)\b", re.I)

#: Site furniture and function words. A sentence opening with one of these is
#: not naming a product even if the word is in the site's paths.
#:
#: PRODUCT-SHAPED NOUNS MUST NOT BE ADDED HERE. An earlier draft listed
#: "connectors" as an example of a common noun that only looks like a name —
#: which silently blocked the single case this whole module was built to
#: recover, and turned Brightledger's best sentence back into UNKNOWN. The
#: point is not to decide whether a word is a product name; it is to check
#: whether the COMPANY treats it as one, and only the site's own taxonomy
#: gets to answer that.
_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "for", "with", "how", "what", "why",
    "when", "your", "you", "get", "start", "build", "use", "using", "this",
    "docs", "documentation", "overview", "home", "blog", "contact",
    "careers", "login", "signup", "index", "page", "www", "com",
})


def _tokens(text: str) -> Tuple[str, ...]:
    from intent_engine.strategic_intelligence.subject import _company_tokens
    return tuple(t.lower() for t in _company_tokens(text or "") if t)


def _path(url: str) -> str:
    try:
        return urlparse(url or "").path or ""
    except ValueError:
        return ""


def _host(url: str) -> str:
    try:
        return (urlparse(url or "").hostname or "").lower()
    except ValueError:
        return ""


def owned_vocabulary(observations: Sequence[dict], *,
                     company: str = "") -> frozenset:
    """The company's own product/section names, from its own site.

    This is the lexicon the previous attempt needed and did not have. It is
    built from first-party URL path segments and the topic half of first-party
    page titles — that is, from pages the company publishes about itself —
    so "Connectors" is in Brightledger's vocabulary and "Figma" is not in
    Stripe's.

    Pages that are rejected outright (customer stories, partner pages,
    comparisons) contribute NOTHING. Without that exclusion a customer story
    at /customers/figma would put "figma" into Stripe's vocabulary and
    re-open the exact leak this module exists to close.
    """
    focal = set(_tokens(company))
    vocabulary = set()
    for obs in observations:
        origin = obs.get("origin") or ""
        if not origin:
            continue
        path = _path(origin)
        if _REJECT_PATH.search(path):
            continue
        title = obs.get("source_title") or ""
        if _REJECT_TITLE.search(title):
            continue
        for segment in path.split("/"):
            segment = re.sub(r"\.(html?|php|aspx?)$", "", segment.strip())
            segment = segment.replace("_", "-")
            for word in segment.split("-"):
                word = word.strip().lower()
                if len(word) > 2 and word.isalpha() and word not in focal:
                    vocabulary.add(word)
        # The topic half of "Connectors and matches | Brightledger docs".
        topic = re.split(r"\s[|–—-]\s", title)[0]
        for word in re.findall(r"[A-Za-z][A-Za-z0-9]+", topic):
            low = word.lower()
            if len(low) > 2 and low not in focal:
                vocabulary.add(low)
    return frozenset(vocabulary)


@dataclass(frozen=True)
class Identity:
    state: str
    because: str
    signals: Tuple[str, ...] = ()

    @property
    def usable(self) -> bool:
        return self.state in USABLE

    def as_dict(self) -> dict:
        return {"state": self.state, "because": self.because,
                "signals": list(self.signals), "version": IDENTITY_VERSION}


def classify(excerpt: str, *, company: str = "", origin: str = "",
             title: str = "", source_class: str = "",
             observation_type: str = "",
             vocabulary: frozenset = frozenset(),
             company_host: str = "") -> Identity:
    """Four-state identity verdict for one passage.

    Order matters. Rejections are checked BEFORE any positive signal, because
    a customer story that happens to contain the word "we" is still a customer
    story — and "we" in a customer story is the customer's voice, which is the
    single most dangerous string in this whole problem.
    """
    text = " ".join((excerpt or "").split())
    low = text.lower()
    path = _path(origin)
    signals = []

    # --- 1. classes that are never the focal company's self-description ---
    if source_class in ("competitor", "customer_voice"):
        return Identity(NOT_SELF,
                        f"source class {source_class!r} is another party's "
                        f"voice by construction", ("source_class",))
    if _REJECT_PATH.search(path) or _REJECT_TITLE.search(title or ""):
        return Identity(
            NOT_SELF,
            "the page is a customer story, partner page, integration page or "
            "comparison — published by the company, about someone else",
            ("page_class",))

    if not text:
        return Identity(UNKNOWN, "no passage to classify", ())

    # --- 2. confirmed: the passage settles it by itself -------------------
    # First person, or the company's own name. Both are properties of the
    # TEXT, so neither depends on trusting the host.
    if _FIRST_PERSON.search(low):
        signals.append("first_person")
        return Identity(CONFIRMED,
                        "the passage speaks in the company's own voice",
                        tuple(signals))
    focal = _tokens(company)
    if any(t in low for t in focal):
        signals.append("names_the_company")
        return Identity(CONFIRMED, "the passage names the company",
                        tuple(signals))

    # --- 3. probable: identity evidence outside the sentence --------------
    # FIRST-PARTY HOSTING IS NOT ENOUGH AND IS NOT ACCEPTED ALONE.
    # It is the assumption that published Figma's description under Stripe's
    # name. It appears here only as one of several required conditions.
    first_party = bool(source_class in ("company_owned", "executive_statement")
                       or (company_host and _host(origin) == company_host))
    if not first_party:
        return Identity(UNKNOWN,
                        "not the company's own page, and the passage neither "
                        "names the company nor speaks in its voice",
                        tuple(signals))
    signals.append("first_party_host")

    identity_page = bool(_IDENTITY_PATH.search(path)) or \
        observation_type in ("product_surface", "messaging")
    if identity_page:
        signals.append("identity_page_class")

    # The subject the sentence is actually about, taken as its opening noun.
    # This is NOT used to guess a company name — it is only ever looked up in
    # the company's own vocabulary, so an unknown word proves nothing either
    # way and simply fails to raise confidence.
    opening = re.match(r"([A-Za-z][A-Za-z0-9]*)", text)
    subject_word = (opening.group(1).lower() if opening else "")
    owns_subject = bool(subject_word and subject_word in vocabulary
                        and subject_word not in _STOPWORDS)
    if owns_subject:
        signals.append("subject_is_an_owned_product")

    pricing_only = bool(_PRICING.search(path)) and not owns_subject
    if pricing_only:
        return Identity(NOT_SELF,
                        "a pricing page states a price list, not what the "
                        "company does", ("pricing_only",))

    if identity_page and owns_subject:
        return Identity(
            PROBABLE,
            f"an identity page on the company's own site, describing "
            f"{subject_word!r}, which is one of the company's own sections",
            tuple(signals))

    # Everything else on a first-party domain. This is the Figma case with
    # the customer-story path stripped off, and it stays UNKNOWN on purpose:
    # a company's own site is full of other companies.
    return Identity(
        UNKNOWN,
        "on the company's own site, but nothing establishes that this "
        "passage is about the company rather than about someone it writes "
        "about", tuple(signals))
