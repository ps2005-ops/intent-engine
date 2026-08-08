"""Who does this sentence belong to?

THE DEFECT THIS EXISTS FOR. Signal detection asked "does this phrase appear in
this document" and nothing else, so ownership was inferred from proximity.
Measured live at `037f805`, Microsoft's two-buyers reading was evidenced by:

    "Our competitors are developing new software and devices, while also
     deploying competing cloud-based services for consumers and businesses."

The pair phrase is there. The buyers belong to the competitors.

WHY A WHOLE-SENTENCE FILTER IS THE WRONG FIX, and was nearly written. Amazon's
evidence for the same reading came from the same section of its own 10-K:

    "Our competitors include ... producers of the products we offer and sell
     to consumers and businesses."

The outer subject is also "Our competitors", but the phrase sits in a relative
clause whose subject is "we" — Amazon really does sell to both, and the
sentence says so. Rejecting every sentence that mentions competitors would
have thrown that away and called it a fix.

So ownership is decided by the NEAREST GOVERNING SUBJECT to the left of the
match, not by anything about the sentence as a whole. In the Microsoft
sentence that is "competitors"; in the Amazon one it is "we".

Unknown fails closed. A phrase with no resolvable subject is not evidence
about anybody.
"""
from __future__ import annotations

import re
from functools import lru_cache

OWN = "own"
FOREIGN = "foreign"
UNKNOWN = "unknown"

#: Words that make the following clause about THIS company. `our` is here and
#: is also the weakest: "our competitors" is a foreign subject that opens with
#: it, which is exactly why the nearest marker wins rather than the first.
_OWN = (r"\bwe\b", r"\bour\b", r"\bus\b", r"\bthe\s+company\b",
        r"\bthe\s+group\b", r"\bthe\s+registrant\b")

#: Words that make the following clause about somebody else.
#:
#: NARROW ON PURPOSE, AND THE FIRST VERSION WAS NOT. It also listed customers,
#: clients, suppliers, vendors, partners, resellers and distributors, and that
#: cost ten tests and two real capabilities:
#:
#:   - "Our CUSTOMER platform includes a system of record…" — a compound noun,
#:     not a subject, sitting nearer the phrase than "Our". HubSpot's actual
#:     mechanism sentence was rejected as somebody else's.
#:   - "CUSTOMERS migrate off their old suite and retire legacy systems." —
#:     the customer is the actor, and their behaviour IS the evidence for
#:     `replaces_incumbent_systems`. Rejecting it deletes the mechanism.
#:
#: A counterparty acting on the company's product is evidence ABOUT the
#: company. What is not evidence about the company is a rival's business, or
#: an outside voice commenting on the market. Only those are listed.
#:
#: Head nouns only — `competing` is an adjective describing a product, so
#: matching `compet\w*` would reject a company naming its own competing offer.
_FOREIGN = (
    r"\bcompetitors?\b", r"\brivals?\b", r"\bpeers?\b",
    r"\bthird[\s-]part(?:y|ies)\b", r"\bother\s+companies\b",
    r"\banalysts?\b", r"\bregulators?\b",
    r"\bthe\s+industry\b", r"\bthe\s+market\b", r"\bthe\s+sector\b",
)


# TWO SCANS, NOT THIRTY. Resolving a subject by trying each marker pattern in
# turn cost +32% on detection — over the 10% budget this cycle is held to —
# because the work is per-MATCH and a filing has many. One alternation per
# role finds the nearest of that role in a single pass, and the common case
# (no foreign marker anywhere in the sentence) short-circuits on the first.
@lru_cache(maxsize=64)
def _patterns(extra: tuple = ()):
    own = list(_OWN) + [rf"\b{re.escape(n)}\b" for n in extra if n]
    return (re.compile("|".join(own), re.I),
            re.compile("|".join(_FOREIGN), re.I))


def _last_start(pattern, window):
    """Where the nearest marker of this kind sits, or -1."""
    at = -1
    for match in pattern.finditer(window):
        at = match.start()
    return at


@lru_cache(maxsize=256)
def _company_tokens(company: str) -> tuple:
    """The company's own name counts as an owner marker.

    "Palantir builds..." is as much a statement of ownership as "we build...",
    and filings alternate between the two freely. Short tokens are dropped:
    a two-letter fragment matches inside other words and would hand ownership
    to any sentence containing it.
    """
    words = re.findall(r"[A-Za-z][A-Za-z0-9&.-]{2,}", company or "")
    drop = {"inc", "corp", "corporation", "company", "plc", "ltd", "limited",
            "holdings", "group", "the", "and"}
    return tuple(w for w in words if w.lower() not in drop)[:3]


def subject_of(text: str, position: int, company: str = "") -> str:
    """Who owns the clause containing `position`.

    The nearest marker to the LEFT wins. "Our competitors ... for consumers
    and businesses" resolves foreign because `competitors` sits between `our`
    and the phrase; "the products we offer and sell to consumers and
    businesses" resolves own because `we` is nearest.
    """
    if position <= 0:
        return UNKNOWN
    window = text[:position]
    own_re, foreign_re = _patterns(_company_tokens(company))
    foreign_at = _last_start(foreign_re, window)
    if foreign_at < 0:
        # Nothing else could own this clause, so the only question left is
        # whether anyone does. This is the overwhelmingly common case and it
        # costs one scan.
        return OWN if own_re.search(window) else UNKNOWN
    return OWN if _last_start(own_re, window) > foreign_at else FOREIGN


def owns(text: str, position: int, company: str = "") -> bool:
    """Whether a claim at `position` may be attributed to this company.

    Fails closed: `unknown` is not ownership. A phrase with no resolvable
    subject is evidence about nobody, and attributing it anyway is the defect
    this module exists to remove.
    """
    return subject_of(text, position, company) == OWN
