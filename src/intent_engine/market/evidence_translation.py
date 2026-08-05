"""Turn retrieved observations into MicroEvidence — or refuse, and say why.

WHERE THE EVIDENCE COMES FROM
-----------------------------
`market.evidence` already wires Founder Intelligence's ingestion into the daily
sweep: it discovers public sources, retrieves them, and derives dated
observations carrying a source class. That pipeline is production-verified and
this module does not duplicate it.

What it does is the last mile the sweep never had. `_live_research` reduced
each company to counts — `"evidence": len(out["evidence"])` — and dropped the
observations themselves. The learning layer needs the objects, because a count
cannot update a belief.

CLASSIFICATION IS CONSERVATIVE BY DESIGN
----------------------------------------
An observation becomes a typed evidence item only when its text actually
carries the marker. Everything else becomes a generic `MARKET_REACTION` or is
dropped. The alternative — guessing a type from the source class — would put
`EARNINGS_SURPRISE` on a blog post, and a mistyped item is worse than a missing
one because it updates the wrong belief with full confidence.

CONTRADICTION ROLE IS NEVER GUESSED
-----------------------------------
Whether an item supports or contradicts a belief depends on the belief, not on
the item. `translate` therefore returns NEUTRAL unless a caller supplies the
mapping, and `beliefs.update` ignores NEUTRAL items. An engine that inferred
"this sounds negative, so it contradicts" would be doing sentiment analysis and
calling it inference.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from . import micro_evidence as ME

# Founder Intelligence source classes → the independence roles this layer
# scores with. Mirrors `market.evidence._SOURCE_CLASS_TO_KIND` so an item does
# not get reclassified on the way through.
_SOURCE_CLASS_TO_ROLE = {
    "investor_material": "regulatory_filing",
    "executive_statement": "executive_statement",
    "independent_reporting": "independent_reporting",
    "analyst_coverage": "analyst_coverage",
    "customer_voice": "customer_voice",
    "competitor_statement": "competitor_statement",
    "company_owned": "company_owned",
    "government_statistic": "government_statistic",
}

# Markers that must be PRESENT in the text for a type to be assigned. Ordered:
# the first match wins, so the more specific patterns are listed first.
_TYPE_MARKERS: Tuple[Tuple[str, str], ...] = (
    (ME.GUIDANCE_REVISION,
     r"\b(raise[sd]?|lower(?:ed|s)?|cut|updat(?:ed|es)|revis(?:ed|es))\s+"
     r"(?:its\s+|the\s+|full[- ]year\s+|fy\s*\d*\s*)?(?:outlook|guidance|"
     r"forecast)\b"),
    (ME.EARNINGS_SURPRISE,
     r"\b(beat|missed|exceeded|fell short of)\s+(?:analyst[s']*\s+|"
     r"consensus\s+|street\s+)?(?:estimates?|expectations?|forecasts?)\b"),
    (ME.LAYOFF, r"\b(lay(?:ing|s)? off|laid off|redundanc|job cuts|"
                r"workforce reduction|reduce[sd]? (?:its )?headcount)\b"),
    (ME.HIRING, r"\b(hiring|headcount growth|expanded (?:its )?team|"
                r"added \d+ (?:employees|engineers|staff))\b"),
    (ME.CONTRACT_AWARD,
     r"\b(awarded|won)\s+(?:a|an|the)?\s*(?:\$[\d.,]+\s*)?"
     r"(?:[a-z-]+\s+)?(?:contract|deal|agreement|task order)\b"),
    (ME.REGULATORY_ACTION,
     r"\b(regulator|antitrust|investigation|consent decree|fined|"
     r"sanction|injunction|subpoena)\w*\b"),
    (ME.PRICING_SIGNAL,
     r"\b(price (?:cut|increase|reduction|change)|cut (?:its )?prices?|"
     r"raised (?:its )?prices?|repricing|list price)\b"),
    (ME.PRODUCT_LAUNCH,
     r"\b(launch(?:ed|es|ing)?|unveil(?:ed|s)?|general availability|"
     r"released)\s+(?:a |an |its |the )?(?:new )?(?:product|platform|"
     r"service|feature|model|version)\b"),
    (ME.CAPEX_SIGNAL,
     r"\b(capital expenditure|capex|new (?:plant|factory|data cent)|"
     r"capacity expansion)\w*\b"),
    (ME.COMPETITOR_ACTION,
     r"\b(competitor|rival)\w*\s+\w+(?:ed|s)?\b"),
    (ME.PROCUREMENT_SIGNAL,
     r"\b(sealed bid|reverse auction|request for proposal|\brfp\b|"
     r"tender|procurement (?:process|vehicle|award))\b"),
    (ME.INVENTORY_CHANGE,
     r"\b(inventory (?:build|drawdown|levels?|glut)|destocking|restocking)\b"),
    (ME.SUPPLIER_COMMENT,
     r"\b(supplier|vendor)\w*\s+(?:said|reported|noted|warned)\b"),
    (ME.CUSTOMER_COMMENT,
     r"\b(customers?|merchants?|users?)\s+(?:said|reported|complained|"
     r"switched|churned)\b"),
    (ME.MACRO_RELEASE,
     r"\b(consumer price index|\bcpi\b|unemployment rate|nonfarm payrolls|"
     r"federal funds rate|gdp growth)\b"),
)


def classify_type(text: str) -> Optional[str]:
    """The evidence type this text actually evidences, or None.

    Returns None rather than a default. A default type is a claim about what
    the observation is, and getting that wrong points a real belief update at
    the wrong proposition.
    """
    low = " ".join((text or "").lower().split())
    if not low:
        return None
    for etype, pattern in _TYPE_MARKERS:
        if re.search(pattern, low):
            return etype
    return None


def translate(observations: Sequence[Any], *, subject_company: str,
              as_of: str, default_type: Optional[str] = None,
              roles: Optional[Dict[str, str]] = None
              ) -> Tuple[List[ME.MicroEvidence], List[str]]:
    """Convert observations into evidence. Returns (evidence, rejections).

    Rejections are returned rather than logged and forgotten: a sweep that
    silently drops nine observations in ten looks identical to a sweep that
    found nothing, and those are very different problems.
    """
    out: List[ME.MicroEvidence] = []
    rejected: List[str] = []
    for obs in observations:
        text = _field(obs, "text", "text_content", "fact", "summary",
                      "content")
        source = _field(obs, "source", "url", "source_url", "citation")
        observed = _field(obs, "observed_at", "date", "published_at",
                          "as_of") or as_of
        source_class = _field(obs, "source_class", "kind", "class")
        author = _field(obs, "source_author", "author", "publisher")

        etype = classify_type(text) or default_type
        if etype is None:
            rejected.append(f"unclassifiable: {(text or '')[:60]!r}")
            continue
        role = (roles or {}).get(source_class) or _SOURCE_CLASS_TO_ROLE.get(
            source_class, "independent_reporting")
        try:
            out.append(ME.build(
                subject_company=subject_company, actor=subject_company,
                evidence_type=etype, observed_at=_date_or(observed, as_of),
                available_at=_date_or(observed, as_of), source=source,
                fact=text, source_author=author, source_role=role,
                reliability=_reliability(role), relevance=0.6,
                contradiction_role=ME.NEUTRAL))
        except ME.EvidenceRejected as exc:
            rejected.append(str(exc))
    return out, rejected


def _field(obj: Any, *names: str) -> str:
    """Read the first present attribute or key.

    Tries several names because the two stores disagree: retrieved documents
    carry `text_content` while observations carry `text`. That exact mismatch
    made both founder extractors blind to a retrieved 10-Q last cycle, so the
    lookup is deliberately tolerant rather than assuming one shape.
    """
    for name in names:
        value = None
        if isinstance(obj, dict):
            value = obj.get(name)
        else:
            value = getattr(obj, name, None)
        if value:
            return str(value)
    return ""


def _reliability(role: str) -> float:
    return {"regulatory_filing": 0.9, "government_statistic": 0.9,
            "independent_reporting": 0.75, "analyst_coverage": 0.6,
            "customer_voice": 0.6, "competitor_statement": 0.55,
            "supplier_statement": 0.55, "executive_statement": 0.5,
            "company_owned": 0.45}.get(role, 0.5)


def _date_or(value: str, fallback: str) -> str:
    from datetime import date
    try:
        date.fromisoformat((value or "")[:10])
        return value[:10]
    except (TypeError, ValueError):
        return fallback[:10]
