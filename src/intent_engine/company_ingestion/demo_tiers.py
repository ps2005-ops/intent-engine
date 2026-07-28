"""What the product promises for a given company, and what it does not.

WHY TIERS
---------
The demo made one promise for every company: type a name, get a briefing. That
promise is true for Palantir, roughly true for Shopify, and false for a Japanese
conglomerate whose site refuses automated access — and the tester had no way to
know which case they were in until the result was already disappointing.

The honest fix is not to make every company work; some companies genuinely do
not publish enough, and no amount of engineering changes that. It is to say in
advance which kind of company this is, so the result matches what was promised.

Four modes:

  GOLDEN — validated end to end, repeatedly. Presentation-ready, safe to open
  in front of someone.

  TAILORED — researched and reviewed before a meeting, then frozen. Shown with
  its research date, and it does not depend on live retrieval while you are
  presenting.

  OPEN — anything else. The readiness gate applies; it may come back limited or
  refuse. That is the deal, stated up front rather than discovered.

  LIMITED — the company publishes too little. Says so, shows what it did find,
  and names what is missing.

Membership is earned, not asserted. A company joins the golden list only after
it passes the end-to-end suite repeatedly, which is why Sony is not on it: it
resolves correctly and recovers from a blocked domain, and that is not the same
as being safe to open in a meeting.
"""
from __future__ import annotations

DEMO_TIERS_VERSION = "ci_demo_tiers.v1"

GOLDEN = "GOLDEN"
TAILORED = "TAILORED"
OPEN = "OPEN"
LIMITED = "LIMITED"

TIERS = (GOLDEN, TAILORED, OPEN, LIMITED)

# Reader-facing text. Raw tier names never reach a page — "OPEN" tells a
# business reader nothing, and "GOLDEN" sounds like a pricing plan.
_PRESENTATION = {
    GOLDEN: {
        "label": "Prepared example",
        "summary": "This company has been checked end to end and is safe to "
                   "open in front of someone.",
        "promise": "A full briefing, a presentation, and follow-up questions "
                   "that work.",
    },
    TAILORED: {
        "label": "Researched for you",
        "summary": "This briefing was researched and reviewed ahead of time, "
                   "then frozen so it cannot change mid-meeting.",
        "promise": "A reviewed briefing as of its research date; nothing is "
                   "fetched live while you present.",
    },
    OPEN: {
        "label": "Live analysis",
        "summary": "Any company can be analysed, but public evidence varies. "
                   "If there is not enough, this will say so rather than "
                   "guess.",
        "promise": "A briefing when the evidence supports one, and an honest "
                   "account of what was missing when it does not.",
    },
    LIMITED: {
        "label": "Limited public evidence",
        "summary": "This company publishes too little for a full briefing.",
        "promise": "What was found, what was missing, and what would close "
                   "the gap.",
    },
}

# Earned by passing the end-to-end suite repeatedly. Adding a name here without
# that evidence is how a demo breaks in front of someone.
GOLDEN_COMPANIES = (
    {"entity_id": "palantir", "name": "Palantir Technologies",
     "website": "https://www.palantir.com",
     "why": "Government and commercial software platforms — Foundry, Gotham "
            "and AIP."},
    {"entity_id": "shopify", "name": "Shopify",
     "website": "https://www.shopify.com",
     "why": "Commerce infrastructure, with a clear upmarket transition to "
            "reason about."},
)

# Sony is deliberately absent. It resolves correctly and recovers from a
# blocked domain, which is not the same as being presentation-ready.
_EXCLUDED_FROM_GOLDEN = {"sony-group", "sony-interactive-entertainment",
                         "sony-electronics"}


def is_golden(entity_id: str = "", website: str = "") -> bool:
    from intent_engine.company_ingestion.entities import _host
    host = _host(website)
    for company in GOLDEN_COMPANIES:
        if entity_id and company["entity_id"] == entity_id:
            return True
        if host and _host(company["website"]) == host:
            return True
    return False


def classify(*, entity_id: str = "", website: str = "", frozen: bool = False,
             readiness_state: str = "") -> str:
    """Which mode this company is being served in.

    `frozen` marks a pre-researched snapshot (the tailored path).
    `readiness_state` downgrades to LIMITED once the gate has spoken — a
    company can be OPEN when the run starts and LIMITED by the time it ends,
    and the label must follow the evidence rather than the intent.
    """
    if entity_id in _EXCLUDED_FROM_GOLDEN and not frozen:
        pass                        # explicitly not golden; falls through
    elif is_golden(entity_id=entity_id, website=website):
        return GOLDEN
    if frozen:
        return TAILORED
    if readiness_state in ("READY_FOR_LIMITED_REPORT", "INSUFFICIENT_EVIDENCE",
                           "RETRYABLE_EVIDENCE_GAP"):
        return LIMITED
    return OPEN


def presentation(tier: str) -> dict:
    """The reader-facing label, summary and promise for a tier."""
    return dict(_PRESENTATION.get(tier, _PRESENTATION[OPEN]),
                tier_version=DEMO_TIERS_VERSION)
