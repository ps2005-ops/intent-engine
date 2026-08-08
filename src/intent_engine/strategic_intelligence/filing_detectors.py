"""Filing-specific strategic detection, feeding the canonical observation.

WHY THIS EXISTS. `_detect_signals` runs the commerce library only
`if in_commerce_domain(text)`, plus a small always-on neutral set. That is the
right shape, and it left a gap: a 10-K from a company that sells observability
software matches no commerce phrase, so its prose contributed nothing even
after section extraction found it. The live Datadog decision therefore fell
back to a blog line.

THE ARCHITECTURE, WHICH IS DELIBERATE.

    source type -> source-specific detectors -> canonical proposition
                -> canonical Observation -> shared reasoning

This module is the second box for filings only. It does NOT bypass observation
admission, it does NOT introduce a filing-only observation type, and it does
NOT widen the commerce vocabulary. Commerce terms and filing disclosures are
different evidence mechanisms; merging them into one keyword bag would produce
false positives on unrelated sources, which is the failure the commerce
library was already narrowed to avoid.

WHY NOT SIMPLY ADMIT FILING PROSE. `derive_observations` records that
admitting signal-free documents was tried and broke the meaning of an
observation across 76 tests. An observation is the unit patterns match
against; a paragraph that merely comes from a legally accountable document is
not one. So these detectors fire on a STATED MECHANISM, not on provenance:
every rule below needs a subject, a direction of change or a dependence, and
in most cases a figure. Descriptive prose and generic risk boilerplate fail
closed.

WHAT A DETECTED PROPOSITION MAY AND MAY NOT SUPPORT is carried in
`PROPOSITIONS` and travels with the signal, because a filing can establish
what a company REPORTED without establishing that customers agree, that a
rival will respond, or that management's stated cause is the real one.
"""
from __future__ import annotations

import re

#: The closed taxonomy. `supports` / `cannot_prove` are the honesty contract:
#: a filing is accountable evidence, not independent confirmation.
PROPOSITIONS = {
    "revenue_trajectory": {
        "label": "reports a direction and rate for its own revenue",
        "type": "market_context",
        "supports": "what the company reported for the period",
        "cannot_prove": "that the trend continues, or why it happened",
        "relevance": "so the question moves from whether it is growing to whether that pace is bought with sales spend or earned by the product",
    },
    "expansion_within_customers": {
        "label": "attributes growth to deeper adoption inside existing "
                 "accounts rather than new logos",
        "type": "buyer_segment",
        "supports": "management's stated driver of reported growth",
        "cannot_prove": "customer satisfaction, retention, or durability",
        "relevance": "so acquisition cost is spread over a longer relationship, and the risk concentrates in a smaller set of accounts",
    },
    "recurring_revenue_base": {
        "label": "reports a recurring or contracted revenue base",
        "type": "monetization_ecosystem",
        "supports": "the reported contracted base at the stated date",
        "cannot_prove": "renewal behaviour after that date",
        "relevance": "so part of next year is already contracted, and the exposure shifts from winning deals to keeping them",
    },
    "margin_trajectory": {
        "label": "reports a direction for gross or operating margin",
        "type": "market_context",
        "supports": "reported margin for the period",
        "cannot_prove": "that the cause management gives is the operative one",
        "relevance": "so the operating-leverage story becomes testable rather than asserted",
    },
    "capital_intensity": {
        "label": "is committing capital at a scale it has to report",
        "type": "organizational",
        "supports": "the reported spend and its stated purpose",
        "cannot_prove": "the return that spend will earn",
        "relevance": "so cash leaves before the demand that would justify it arrives, and payback depends on utilisation nobody outside can see",
    },
    "acquisition_activity": {
        "label": "is buying capability rather than building it",
        "type": "organizational",
        "supports": "that the transaction was entered into",
        "cannot_prove": "that integration succeeds",
        "relevance": "so the timeline shortens, and integration risk replaces build risk",
    },
    "supplier_dependency": {
        "label": "has written down a dependence on specific suppliers or "
                 "infrastructure",
        "type": "infrastructure_platform",
        "supports": "a dependence management considers material",
        "cannot_prove": "that the dependence will be disrupted",
        "relevance": "so a supplier's outage or price rise becomes the company's, and switching is a project rather than a decision",
    },
    "pricing_exposure": {
        "label": "reports pressure on what it can charge",
        "type": "market_context",
        "supports": "pressure management has disclosed",
        "cannot_prove": "a competitor's future pricing behaviour",
        "relevance": "so growth has to come from volume or mix, because price is no longer available as a lever",
    },
    "competitive_intensity": {
        "label": "describes a market it expects to be contested",
        "type": "market_context",
        "supports": "management's description of competitive conditions",
        "cannot_prove": "any rival's motive or planned response",
        "relevance": "so any advantage has to be renewed rather than held, and the cost of defending it recurs",
    },
    "geographic_exposure": {
        "label": "reports material revenue from outside its home market",
        "type": "buyer_segment",
        "supports": "the reported geographic mix",
        "cannot_prove": "political or currency outcomes",
        "relevance": "so currency and local demand move the reported number independently of how the business performs",
    },
    "liquidity_position": {
        "label": "reports the cash and borrowing position it is operating from",
        "type": "organizational",
        "supports": "the reported balance at the stated date",
        "cannot_prove": "future funding conditions",
        "relevance": "so the runway for a downturn or a purchase is bounded by a figure rather than an intention",
    },
    "regulatory_constraint": {
        "label": "operates under a named regulatory or legal constraint",
        "type": "market_context",
        "supports": "a constraint management considers material",
        "cannot_prove": "the outcome of any proceeding",
        "relevance": "so the pace of change is capped by an approval nobody inside the company controls",
    },
}

# A figure: percentage, currency amount, or a scale word attached to a number.
_FIGURE = r"(?:\d[\d,.]*\s*(?:%|percent|million|billion|bps|basis points)|" \
          r"[$€£¥]\s?\d[\d,.]*)"
_UP = r"(?:increase[sd]?|grew|grow(?:th|n)?|rose|rising|up|expand(?:ed|ing)?|" \
      r"improv(?:ed|ement)|higher)"
_DOWN = r"(?:decrease[sd]?|declin(?:ed|e|ing)|fell|dropp?ed|down|lower|" \
        r"contract(?:ed|ion)|compress(?:ed|ion))"

#: Each rule needs a MECHANISM, not a topic word. Where a claim is quantitative
#: the figure is required, so "revenue was strong" does not qualify.
_RULES = (
    ("revenue_trajectory", re.compile(
        r"\b(?:revenue|net sales|total sales)\b[^.]{0,80}?\b"
        rf"(?:{_UP}|{_DOWN})\b[^.]{{0,60}}?{_FIGURE}"
        rf"|{_FIGURE}[^.]{{0,60}}?\b(?:revenue|net sales)\b[^.]{{0,60}}?"
        rf"\b(?:{_UP}|{_DOWN})\b", re.I)),
    ("expansion_within_customers", re.compile(
        r"\b(?:expansion|growth|increase)\b[^.]{0,60}?\bwithin\b[^.]{0,40}?"
        r"\bexisting\b[^.]{0,30}?\bcustomer"
        r"|\bexisting customers?\b[^.]{0,60}?\b(?:expand|purchas|adopt|"
        r"increas)\w*"
        r"|\bnet (?:dollar )?retention\b", re.I)),
    ("recurring_revenue_base", re.compile(
        r"\b(?:annual recurring revenue|recurring revenue|remaining "
        r"performance obligations|subscription revenue|deferred revenue)\b"
        rf"[^.]{{0,80}}?{_FIGURE}", re.I)),
    ("margin_trajectory", re.compile(
        r"\b(?:gross|operating|profit)\s+margin\b[^.]{0,70}?"
        rf"\b(?:{_UP}|{_DOWN})\b"
        rf"|\b(?:gross|operating)\s+margin\b[^.]{{0,40}}?{_FIGURE}", re.I)),
    ("capital_intensity", re.compile(
        r"\b(?:capital expenditures?|capex|purchases of property and "
        r"equipment|data cent(?:er|re) (?:capacity|investment))\b"
        rf"[^.]{{0,80}}?{_FIGURE}", re.I)),
    ("acquisition_activity", re.compile(
        r"\bwe (?:acquired|completed the acquisition of)\b"
        r"|\bacquisition of\b[^.]{0,60}?\bfor\b[^.]{0,30}?" + _FIGURE
        + r"|\bbusiness combination\b[^.]{0,60}?\bcompleted\b", re.I)),
    ("supplier_dependency", re.compile(
        r"\b(?:we (?:rely|depend)|reliance|dependent)\b[^.]{0,60}?\b"
        r"(?:on a (?:limited|single|small) number of|third-party (?:cloud|"
        r"providers|suppliers|manufacturers)|sole source)", re.I)),
    ("pricing_exposure", re.compile(
        r"\bpricing pressure\b|\bprice competition\b"
        r"|\b(?:reduce|lower|discount)\w*\b[^.]{0,40}?\bprices?\b[^.]{0,40}?"
        r"\b(?:competit|retain|win)\w*", re.I)),
    ("competitive_intensity", re.compile(
        r"\b(?:market|industry)\b[^.]{0,40}?\bis\b[^.]{0,20}?\b(?:intensely|"
        r"highly)\s+competitive\b"
        r"|\bwe (?:face|compete with)\b[^.]{0,60}?\bcompetit", re.I)),
    ("geographic_exposure", re.compile(
        r"\b(?:outside (?:the )?(?:united states|north america)|"
        r"international(?:ly)?|foreign)\b[^.]{0,60}?"
        rf"\b(?:revenue|sales|operations)\b[^.]{{0,40}}?{_FIGURE}"
        rf"|{_FIGURE}[^.]{{0,40}}?\bof (?:our )?(?:total )?revenue\b"
        r"[^.]{0,40}?\b(?:international|outside)", re.I)),
    ("liquidity_position", re.compile(
        r"\b(?:cash(?: and cash equivalents)?|marketable securities|"
        r"revolving credit facility|total debt|term loan)\b"
        rf"[^.]{{0,60}}?{_FIGURE}", re.I)),
    ("regulatory_constraint", re.compile(
        r"\b(?:GDPR|CCPA|HIPAA|Dodd-Frank|Basel|SOC 2|FedRAMP)\b"
        r"|\bsubject to\b[^.]{0,40}?\b(?:regulation|regulatory "
        r"(?:requirements|oversight)|supervision by)\b", re.I)),
)

#: Generic caveat language every filing carries. A rule matching only inside
#: one of these is boilerplate, not a disclosure about THIS company.
_BOILERPLATE = re.compile(
    r"\bcould (?:adversely )?affect\b.{0,40}\bbusiness, financial condition\b"
    r"|\bthere can be no assurance\b"
    r"|\bmay be (?:materially )?adversely affected\b"
    r"|\bfactors beyond our control\b"
    r"|\bamong other (?:things|factors)\b", re.I)

_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_MIN_LEN = 45


def detect(text: str) -> list:
    """Canonical proposition keys evidenced by this filing text.

    Sentence-scoped so a subject and its mechanism must appear together: a
    document-wide match would let "revenue" in one paragraph and "increased"
    in another combine into a claim neither makes.
    """
    found, seen = [], set()
    for raw in _SENTENCE.split(text or ""):
        sentence = " ".join(raw.split())
        if len(sentence) < _MIN_LEN or _BOILERPLATE.search(sentence):
            continue
        for key, rule in _RULES:
            if key not in seen and rule.search(sentence):
                seen.add(key)
                found.append(key)
    return found


def limitation_for(keys) -> str:
    """What the detected propositions may not establish, for the reader."""
    parts = [PROPOSITIONS[k]["cannot_prove"] for k in keys
             if k in PROPOSITIONS]
    if not parts:
        return ""
    unique = list(dict.fromkeys(parts))
    return ("the filing is accountable evidence of what the company reported; "
            "it does not establish " + "; ".join(unique[:3]))
