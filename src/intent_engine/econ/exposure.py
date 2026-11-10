"""Reading a company's economic exposures out of its own words.

WHY THIS IS IN THE SHARED CORE AND NOT IN EITHER PRODUCT
---------------------------------------------------------
`market.company_exposure` already does this, correctly, and states the rule
that matters: an exposure may not be inferred from a sector, because a sector
map says a payroll company and a chip designer are both technology with
opposite exposures to unemployment. That module is not the problem.

Its INPUT was. Measured on the live ledger, 2026-08-27:

    market corpus   131 evidence rows, 19,415 characters   ->  1 exposure
    founder corpus   46 documents, 3,564,390 characters    -> 39 exposures

Same patterns, same companies, 184x the text and 39x the exposures. The
market engine reads news headlines with a median length of 95 characters, and
these patterns need a sentence in which the company is the SUBJECT of a
dependency -- "our results are sensitive to fuel prices". Headlines never
contain that construction. The founder engine retrieves annual reports and
extracts Item 7 prose, where the construction is the house style.

So the capability was never broken and never had text it could work on. It
belongs where both sides can reach it: the founder side extracts at
translation time, when the whole document is in hand, and the market side
reads the result from the core instead of re-deriving it from headlines.

WHAT IS NOT MOVED HERE
----------------------
`market.company_exposure` keeps its ledger-shaped reader, its knowledge-effect
attribution and its standing rules; nothing there is deleted, and it will keep
finding what the ledger contains. This is the same judgement applied to a
better corpus, not a replacement for it.

THE SECTOR RULE TRAVELS WITH THE PATTERNS
------------------------------------------
`infer_from_sector` raises here too. A capability that refuses sector
inference in one package and allows it in another has not been shared; it has
been forked.
"""
from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .vocabulary import EconError, require

CONTRACT = "econ_exposure.v1"

RATE = "RATE_EXPOSURE"
CREDIT = "CREDIT_EXPOSURE"
FX = "FX_EXPOSURE"
COMMODITY = "COMMODITY_EXPOSURE"
ENERGY = "ENERGY_EXPOSURE"
LABOR = "LABOR_EXPOSURE"
SUPPLY = "SUPPLY_EXPOSURE"
CUSTOMER_CONCENTRATION = "CUSTOMER_CONCENTRATION"
CAPITAL_INTENSITY = "CAPITAL_INTENSITY"
REGULATORY = "REGULATORY_EXPOSURE"
DIMENSIONS = (RATE, CREDIT, FX, COMMODITY, ENERGY, LABOR, SUPPLY,
              CUSTOMER_CONCENTRATION, CAPITAL_INTENSITY, REGULATORY)

#: Which shared economic quantity each dimension is an exposure TO. This is
#: the join that makes `EconomicState` reach a company: without it an
#: exposure is a label, and `relevant_to` has nothing to look up.
QUANTITY_FOR: Dict[str, str] = {
    RATE: "policy_rate",
    CREDIT: "financial_conditions",
    FX: "fx_dxy",
    COMMODITY: "commodity_copper",
    ENERGY: "commodity_oil",
    LABOR: "labour",
    SUPPLY: "industrial_production",
    CAPITAL_INTENSITY: "business_investment",
    REGULATORY: "fiscal",
    # CUSTOMER_CONCENTRATION deliberately has no macro quantity. It is a
    # real exposure and it is not an exposure to the economy; mapping it to
    # one would put a company-specific risk under a macro heading.
}

#: Each pattern demands the company be the SUBJECT of the dependency rather
#: than merely nearby in the sentence. "Our results are sensitive to fuel
#: prices" rates; "fuel prices rose this year" does not, because the second is
#: a fact about the world that happens to appear in a company's document.
#:
#: Kept deliberately identical to `market.company_exposure._PATTERNS`. A
#: shared capability whose two copies drift is worse than two capabilities,
#: because the difference is invisible until the two sides disagree about a
#: company; `test_econ_exposure.py` asserts they stay the same.
_PATTERNS: Tuple[Tuple[str, str], ...] = (
    (RATE, r"\b(our|the compan\w+|its)\b[^.]{0,80}\b(interest rate|"
           r"floating rate|variable rate|rate)\s+(exposure|risk|sensitiv\w+)"),
    (RATE, r"\b(exposed|sensitive)\s+to\b[^.]{0,40}\binterest rates?\b"),
    (CREDIT, r"\b(our|its)\b[^.]{0,60}\b(refinanc\w+|debt maturit\w+|"
             r"credit facilit\w+|covenant\w*)\b"),
    (FX, r"\b(currency|exchange[- ]rate|foreign exchange|FX)\s+"
         r"(exposure|risk|translation|headwind|impact)\b"),
    (COMMODITY, r"\b(raw material|commodity|input)\s+(cost|price)\w*\b"
                r"[^.]{0,60}\b(our|its|impact\w*|pressur\w+)\b"),
    (ENERGY, r"\b(energy|fuel|electricity)\s+(cost|price)\w*\b"
             r"[^.]{0,60}\b(our|its|impact\w*|pressur\w+)\b"),
    (LABOR, r"\b(labou?r|wage|hiring|headcount)\s+"
            r"(cost|inflation|pressur\w+|shortage)\b"),
    (SUPPLY, r"\b(supply chain|supplier|component|semiconductor)\b"
             r"[^.]{0,60}\b(constraint|shortage|disrupt\w+|depend\w+)\b"),
    # TWO DEAD BRANCHES, FOUND BY RUNNING THE PATTERNS OVER REAL FILINGS.
    #
    # `\b(\d+\s*%|...)\b` could never match a percentage: the group ends on
    # "%", a non-word character, and the trailing \b then requires the NEXT
    # character to be a word character. In "22% of revenue" it is a space, so
    # the boundary fails. Only the "percent" and "majority" spellings ever
    # rated, and "22% of revenue" is the form filings actually use. The
    # boundary now belongs to the alternatives that are words.
    (CUSTOMER_CONCENTRATION,
     r"\b(largest|top|single)\s+(customer|client)s?\b[^.]{0,60}"
     r"(?:\b\d+\s*%|\bpercent\b|\bmajority\b)"),
    # `capital expenditure` did not match "capital expenditures", which is
    # the form nearly every filing uses -- the trailing \b fails against the
    # plural "s". Measured on six annual reports: the singular appears twice
    # and the plural forty-one times.
    (CAPITAL_INTENSITY, r"\b(capital expenditures?|capex|capital intensity|"
                        r"capital[- ]intensive)\b"),
    (REGULATORY, r"\b(regulat\w+|tariff|sanction)\w*\b[^.]{0,60}"
                 r"\b(our|its)\b[^.]{0,40}\b(business|operations|results)\b"),
)

_COMPILED = tuple((dim, re.compile(pat, re.I)) for dim, pat in _PATTERNS)

#: How much of one document is scanned. Bounded so a 300-page filing cannot
#: turn one company into a whole cycle's work, and far past the excerpt an
#: observation carries: Item 7 begins well after the cover page.
SCAN_CHARS = 400_000


def infer_from_sector(*_args, **_kwargs):
    """Never. The rule travels with the patterns; see the module docstring."""
    raise EconError(
        "an exposure may not be inferred from a company's sector; find the "
        "sentence in this company's own material, or record nothing. A "
        "sector map produces the SAME claim for every company in the sector, "
        "so the most specific-sounding output carries the least information.")


def _sentences(text: str) -> List[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text or "")
            if s.strip()]


def read(texts: Sequence[str], *, company_id: str,
         scan_chars: int = SCAN_CHARS) -> List[dict]:
    """Every exposure these documents establish, with the sentence that did it.

    Returns plain dicts rather than `MacroExposure` objects: the evidence node
    id that anchors an exposure is not known here (this reads text, not the
    graph), and constructing a `MacroExposure` without one would defeat the
    invariant that an exposure names its evidence. `company.build` is where
    the two are joined.

    FIRST SENTENCE WINS per dimension, and the sentence is kept. An exposure
    with no quotable basis is unreviewable, and "the model says this company
    is rate-exposed" is exactly the claim this whole design refuses.
    """
    require(bool(company_id), "an exposure belongs to a company")
    found: Dict[str, dict] = {}
    for text in texts:
        for sentence in _sentences(str(text or "")[:scan_chars]):
            for dimension, pattern in _COMPILED:
                if dimension in found:
                    continue
                if pattern.search(sentence):
                    found[dimension] = {
                        "dimension": dimension,
                        "quantity": QUANTITY_FOR.get(dimension, ""),
                        "basis": sentence[:240],
                        "company_id": company_id,
                    }
    return [found[d] for d in DIMENSIONS if d in found]


def macro_exposures(rows: Sequence[dict], *, evidence_node: str,
                    confidence: float = 0.5) -> List:
    """Turn `read` output into `company.MacroExposure` objects.

    Only dimensions with a macro quantity cross. `CUSTOMER_CONCENTRATION` is
    a real exposure to something that is not the economy, and it stays out of
    the macro join rather than being given a quantity that fits.
    """
    from .company import MacroExposure
    out = []
    for row in rows:
        quantity = row.get("quantity") or ""
        if not quantity:
            continue
        out.append(MacroExposure(
            quantity=quantity, mechanism=row.get("basis", ""),
            direction="UP", evidence_node=evidence_node,
            confidence=confidence,
            falsifier=("the company stops stating this dependency in its own "
                       "filings, or states it has been hedged away")))
    return out


def summarise(rows: Sequence[dict]) -> dict:
    return {"contract": CONTRACT, "exposures": len(rows),
            "dimensions": [r["dimension"] for r in rows],
            "macro_linked": sum(1 for r in rows if r.get("quantity")),
            "note": ("read from the company's own documents; an exposure "
                     "this text does not state is absent, not zero")}
