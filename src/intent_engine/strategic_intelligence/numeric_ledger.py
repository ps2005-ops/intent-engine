"""Every number the analyst is allowed to state, extracted before it runs.

WHY THIS EXISTS, MEASURED.

Across five live companies the critic rejected 16 figures. Fifteen of them
appeared in NO retrieved byte: the model wrote Datadog's revenue from memory
because it knows Datadog, and the evidence pack gave it no figure to use
instead. Retrieval volume cannot fix that -- the documents already carried 219
numbers for Datadog and the model still used its own.

So the numbers stop being something the model recalls and become something it
is handed. This module extracts them deterministically, normalises them, and
keeps what is uncertain uncertain. A claim whose figure is not in this ledger
has no support, and `contract.validate_numeric_claims` refuses it before the
critic ever sees it.

DELIBERATELY BOUNDED. A general financial ontology is not in scope; this
recognises a small, named metric set and labels everything else `unlabelled`
rather than guessing. A wrong label is worse than an honest absence, because a
wrong label is what lets an unsupported claim look supported.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

# Scale words, applied only when adjacent to the figure.
_SCALES = {"thousand": 1_000, "thousands": 1_000,
           "million": 1_000_000, "millions": 1_000_000, "m": 1_000_000,
           "billion": 1_000_000_000, "billions": 1_000_000_000,
           "bn": 1_000_000_000, "b": 1_000_000_000,
           "trillion": 1_000_000_000_000}

_CURRENCY = {"$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY"}

# The bounded metric set. Order matters: the first match wins, so more specific
# phrases precede the general ones.
_METRICS = (
    ("diluted_eps", ("diluted earnings per share", "diluted eps")),
    ("basic_eps", ("basic earnings per share", "basic eps")),
    ("eps", ("earnings per share",)),
    ("gross_profit", ("gross profit",)),
    ("operating_income", ("operating income", "income from operations",
                          "operating profit")),
    ("net_income", ("net income", "net earnings", "net loss")),
    ("operating_cash_flow", ("net cash provided by operating activities",
                             "cash flow from operations",
                             "operating cash flow")),
    ("capital_expenditure", ("capital expenditure", "capital expenditures",
                             "purchases of property and equipment")),
    ("cash_and_equivalents", ("cash and cash equivalents",)),
    ("arr", ("annual recurring revenue", "arr")),
    ("revenue", ("total revenue", "revenues", "revenue", "net sales")),
)

_GAAP_HINT = re.compile(r"\bnon-?gaap\b", re.I)
_GUIDANCE_HINT = re.compile(
    r"\b(guidance|we expect|outlook|anticipat\w+|forecast\w*)\b", re.I)
_ESTIMATE_HINT = re.compile(r"\b(analyst|consensus|estimate[sd]?)\b", re.I)

_PERIOD_RE = re.compile(
    r"\b(?:(Q[1-4])\s*(?:of\s*)?(?:FY)?\s*(\d{4})"
    r"|(?:FY|fiscal(?:\s+year)?)\s*(\d{4})"
    r"|(?:three|six|nine|twelve)\s+months\s+ended\s+[A-Z][a-z]+\s+\d{1,2},?\s*"
    r"(\d{4}))\b", re.I)

# A figure: optional currency, digits with separators, optional scale word or %.
_FIGURE_RE = re.compile(
    r"(?P<paren>\()?"
    r"(?P<neg>-)?"
    r"(?P<cur>[$€£¥])?\s?"
    r"(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"\s*(?P<scale>thousand[s]?|million[s]?|billion[s]?|trillion|bn|m|b)?"
    r"\s*(?P<pct>%|percent|percentage points?|basis points?)?"
    r"(?P<parenclose>\))?", re.I)


@dataclass
class NumericFact:
    fact_id: str
    raw: str                       # exactly as written in the source
    value: float                   # normalised magnitude
    unit: str                      # "currency" | "percent" | "count"
    currency: Optional[str]
    scale_applied: int
    metric: str                    # bounded set, or "unlabelled"
    period: str                    # "" when not established
    basis: str                     # "gaap" | "non_gaap" | "unstated"
    kind: str                      # "reported" | "guidance" | "estimate"
    directly_stated: bool
    confidence: str                # "high" | "medium" | "low"
    evidence_id: str
    source_title: str
    excerpt: str

    def as_dict(self) -> dict:
        return {k: getattr(self, k) for k in
                ("fact_id", "raw", "value", "unit", "currency", "metric",
                 "period", "basis", "kind", "directly_stated", "confidence",
                 "evidence_id", "source_title", "excerpt")}


def normalise_number(match) -> Optional[tuple]:
    """(value, unit, currency, scale) or None when it is not a real figure."""
    digits = match.group("num")
    if not digits:
        return None
    try:
        value = float(digits.replace(",", ""))
    except ValueError:
        return None
    negative = bool(match.group("neg")) or bool(
        match.group("paren") and match.group("parenclose"))
    scale = _SCALES.get((match.group("scale") or "").lower(), 1)
    pct = (match.group("pct") or "").lower()
    currency = _CURRENCY.get(match.group("cur") or "")
    if pct:
        unit = "percent"
        currency = None
        scale = 1
    elif currency:
        unit = "currency"
    else:
        unit = "count"
    value = value * scale
    if negative:
        value = -value
    return value, unit, currency, scale


def _metric_for(window: str, figure_at: Optional[int] = None) -> str:
    """The metric phrase NEAREST the figure, not the first one in the list.

    "Annual recurring revenue reached $500 million. Total revenue was $610
    million." -- both figures sit inside one window, and list order alone
    labelled the second one `arr`. Proximity is the only signal available
    here that distinguishes them, and a mislabelled metric is worse than
    `unlabelled`: it is what lets an unsupported claim look supported.
    """
    low = window.lower()
    anchor = len(low) // 2 if figure_at is None else figure_at
    best_name, best_distance = "unlabelled", None
    for name, phrases in _METRICS:
        for phrase in phrases:
            start = 0
            while True:
                at = low.find(phrase, start)
                if at < 0:
                    break
                distance = abs(at + len(phrase) - anchor)
                if best_distance is None or distance < best_distance:
                    best_name, best_distance = name, distance
                start = at + 1
    return best_name


def _period_for(window: str) -> str:
    m = _PERIOD_RE.search(window or "")
    if not m:
        return ""
    quarter, qyear, fyear, myear = m.groups()
    if quarter and qyear:
        return f"{quarter.upper()} {qyear}"
    return f"FY{fyear or myear}"


def extract(text: str, *, evidence_id: str, source_title: str = "",
            limit: int = 60) -> List[NumericFact]:
    """Numeric facts from one source. Never guesses a metric it cannot see."""
    facts: List[NumericFact] = []
    seen = set()
    for match in _FIGURE_RE.finditer(text or ""):
        if len(facts) >= limit:
            break
        parsed = normalise_number(match)
        if parsed is None:
            continue
        value, unit, currency, scale = parsed
        raw = match.group(0).strip()
        if not any(ch.isdigit() for ch in raw):
            continue
        start, end = match.span()
        left = max(0, start - 140)
        window = text[left:min(len(text), end + 140)]
        metric = _metric_for(window, figure_at=start - left)
        period = _period_for(window)
        basis = "non_gaap" if _GAAP_HINT.search(window) else "unstated"
        if _ESTIMATE_HINT.search(window):
            kind = "estimate"
        elif _GUIDANCE_HINT.search(window):
            kind = "guidance"
        else:
            kind = "reported"
        # Confidence is about EXTRACTION, not about the company. A figure whose
        # metric and period are both visible is safe to hand over; a bare
        # number in prose is not, and says so rather than being dropped.
        if metric != "unlabelled" and period:
            confidence = "high"
        elif metric != "unlabelled" or period:
            confidence = "medium"
        else:
            confidence = "low"
        key = (round(value, 6), unit, metric, period)
        if key in seen:
            continue
        seen.add(key)
        facts.append(NumericFact(
            fact_id=f"nf-{evidence_id}-{len(facts) + 1}",
            raw=raw, value=value, unit=unit, currency=currency,
            scale_applied=scale, metric=metric, period=period, basis=basis,
            kind=kind, directly_stated=True, confidence=confidence,
            evidence_id=evidence_id, source_title=source_title,
            excerpt=" ".join(window.split())[:240]))
    return facts


def build_ledger(observations, *, per_source: int = 60) -> List[NumericFact]:
    """The ledger for one run: every figure the analyst may cite."""
    ledger: List[NumericFact] = []
    for o in observations:
        text = " ".join(filter(None, [getattr(o, "text", "") or "",
                                      getattr(o, "excerpt", "") or ""]))
        ledger.extend(extract(
            text, evidence_id=getattr(o, "observation_id", "") or "?",
            source_title=getattr(o, "source_title", "") or "",
            limit=per_source))
    return ledger


def supported_values(ledger) -> set:
    """Every value a claim may state, in the forms a writer would use."""
    allowed = set()
    for fact in ledger:
        allowed.add(fact.raw.strip())
        allowed.add(fact.raw.strip().lstrip("$€£¥").strip())
        value = fact.value
        if value == int(value):
            allowed.add(str(int(abs(value))))
            allowed.add(f"{int(abs(value)):,}")
        allowed.add(f"{abs(value):g}")
    return {a for a in allowed if a}


def render_for_pack(ledger, *, limit: int = 80) -> str:
    """The NUMERIC_FACTS block. Labelled, periodised, and finite."""
    if not ledger:
        return ("NUMERIC_FACTS (0)\n"
                "  none. No figure was extracted from the retrieved evidence, "
                "so NO numeric claim can be supported in this analysis.\n")
    lines = [f"NUMERIC_FACTS ({len(ledger)}). You may state a number ONLY if "
             f"it appears here, and you must cite its fact_id.", ""]
    for fact in ledger[:limit]:
        parts = [f"[{fact.fact_id}]", f"value={fact.raw}"]
        if fact.metric != "unlabelled":
            parts.append(f"metric={fact.metric}")
        else:
            parts.append("metric=UNLABELLED(do not name it)")
        if fact.period:
            parts.append(f"period={fact.period}")
        else:
            parts.append("period=UNSTATED")
        parts.append(f"basis={fact.basis}")
        parts.append(f"kind={fact.kind}")
        parts.append(f"confidence={fact.confidence}")
        parts.append(f"evidence={fact.evidence_id}")
        lines.append("  " + "  ".join(parts))
        lines.append(f"      context: {fact.excerpt}")
    return "\n".join(lines) + "\n"
