"""Why the strategic conclusion was withheld, in words a founder can act on.

A reader must never see "invented_number x20". That is the system describing
its own rule set, and it tells a founder nothing about their company. It is
also, on its own, the wrong reason: the generic
STRATEGICALLY_INSUFFICIENT text says the pages were "descriptive rather than
strategic", which was measurably NOT why these runs were withheld -- they were
withheld because the analysis reached for figures the retrieved sources did
not contain.

Four things a founder can use, and nothing else:

    what was available      what the run genuinely established
    what was missing        the specific evidence that was absent
    why it was withheld     in plain terms
    what would fix it       the cheapest thing that changes the answer

This is an EXPLANATION of a refusal, never a substitute for an analysis that
passed. Nothing here asserts a strategic reading.
"""
from __future__ import annotations

from typing import Dict, List, Sequence

# Critic/schema check names -> the founder-facing cause they represent.
_NUMERIC = ("invented_number", "unsupported_numeric_claim")
_THIN = ("no_decision", "no_decisions", "no_counterargument",
         "unexplained_confidence")


def classify(findings: Sequence[dict]) -> str:
    """The dominant reason, from the findings. Never shown to the reader."""
    kinds = [f.get("check", "") for f in (findings or ())]
    if any(k in _NUMERIC for k in kinds):
        return "unsupported_figures"
    if any(k in _THIN for k in kinds):
        return "no_decision_supported"
    if kinds:
        return "other_refusal"
    return "insufficient_evidence"


_WHY = {
    "unsupported_figures":
        "We found useful evidence, but the analysis introduced financial "
        "figures that the retrieved sources do not contain. We withheld the "
        "strategic conclusion rather than present a number we cannot show you "
        "the source for.",
    "no_decision_supported":
        "The evidence supported description but not a decision. Rather than "
        "dress a summary up as advice, we stopped short of a conclusion.",
    "other_refusal":
        "The draft analysis did not meet our evidence standard, so it was not "
        "published. What was verified is shown below.",
    "insufficient_evidence":
        "Not enough could be retrieved to support a strategic reading. What "
        "was verified is shown below; nothing is inferred beyond it.",
}

_FIX = {
    "unsupported_figures": (
        "A filing or earnings release whose figures we can quote directly — "
        "revenue, margin and cash flow for a named period — would let the "
        "same analysis be stated with its sources attached."),
    "no_decision_supported": (
        "Independent coverage or a dated customer outcome would give the "
        "analysis something to weigh a decision against."),
    "other_refusal": (
        "Independent reporting, a dated customer outcome, or published "
        "pricing would each strengthen this."),
    "insufficient_evidence": (
        "Independent reporting, a dated customer outcome, or published "
        "pricing would each strengthen this."),
}


#: source classes and coverage families, as a reader would say them
_IN_WORDS = {
    "company_owned": "the company's own pages",
    "executive_statement": "executive statements",
    "investor_material": "investor material",
    "customer_voice": "customer accounts",
    "competitor": "competitors",
    "independent_reporting": "independent reporting",
    "historical_pattern": "historical comparisons",
}


def explain(*, findings: Sequence[dict] = (), families: Sequence[str] = (),
            independent_sources: int = 0, document_count: int = 0,
            numeric_facts: int = 0) -> Dict[str, object]:
    """The four founder-facing parts, plus the machine cause for operators."""
    cause = classify(findings)
    available: List[str] = []
    if document_count:
        available.append(f"{document_count} source(s) retrieved and read")
    if families:
        # In a reader's words. The deployed Palantir page told a founder its
        # evidence covered "company_owned, executive_statement,
        # investor_material" -- three enum members, on the screen that exists
        # to explain honestly what was and was not found.
        available.append("evidence covering " + ", ".join(
            _IN_WORDS.get(f, str(f).replace("_", " "))
            for f in sorted(families)))
    if numeric_facts:
        available.append(f"{numeric_facts} figure(s) we could quote directly")
    if not available:
        available.append("no source could be retrieved and read")

    missing: List[str] = []
    if independent_sources == 0:
        missing.append("anything written by someone other than the company — "
                       "every source here is the company's own account")
    if not numeric_facts:
        missing.append("any figure we could quote from a retrieved source")
    if cause == "unsupported_figures":
        missing.append("a filing or release carrying the specific figures the "
                       "analysis wanted to use")
    if not missing:
        missing.append("enough independent corroboration to support a "
                       "conclusion")

    return {"cause": cause,
            "what_was_available": available,
            "what_was_missing": missing,
            "why_withheld": _WHY[cause],
            "what_would_help": _FIX[cause]}


def render_text(explanation: Dict[str, object]) -> str:
    """Plain prose. No rule names, no counts of internal findings."""
    return " ".join([
        str(explanation["why_withheld"]),
        "What we did have: " + "; ".join(
            explanation["what_was_available"]) + ".",
        "What was missing: " + "; ".join(explanation["what_was_missing"]) + ".",
        str(explanation["what_would_help"]),
    ])
