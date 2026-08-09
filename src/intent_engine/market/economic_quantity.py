"""A number with an economic subject, or nothing.

WHY `numeric_values` IS EMPTY ON EVERY ROW
------------------------------------------
Because the only easy way to fill it is wrong. A document is full of digits —
page numbers, section references, dates, employer identification numbers,
percentages belonging to somebody else's business — and a parser that harvests
them produces a field that looks populated and means nothing. An empty field is
better than a populated one nobody can trust, and whoever left it empty was
right to.

WHAT MAKES A NUMBER A QUANTITY
------------------------------
A subject and a unit. "12%" is not a quantity; "gross margin of 12% in the
quarter" is. So extraction runs from the SUBJECT outward: the vocabulary below
lists the economic things this engine can reason about, each with the words
that name it, and a digit that no phrase in that vocabulary claims is
discarded. That is the opposite of the usual direction and it is why the yield
is low and the precision is worth having.

REJECTION IS THE MAJORITY CASE AND IS COUNTED
---------------------------------------------
`extract` returns what it refused alongside what it kept. A silent filter that
drops 95% of candidates is indistinguishable from a broken one.
"""
from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

CONTRACT = "economic_quantity.v1"

# --- what kind of economic thing the number measures --------------------------
CPI_LEVEL = "CPI_LEVEL"
UNEMPLOYMENT_RATE = "UNEMPLOYMENT_RATE"
POLICY_RATE = "POLICY_RATE"
MARKET_RATE = "MARKET_RATE"
CREDIT_SPREAD = "CREDIT_SPREAD"
REVENUE = "REVENUE"
MARGIN = "MARGIN"
BACKLOG = "BACKLOG"
BOOKINGS = "BOOKINGS"
ORDERS = "ORDERS"
CANCELLATIONS = "CANCELLATIONS"
CAPEX = "CAPEX"
GUIDANCE = "GUIDANCE"
PRICE = "PRICE"
WAGE = "WAGE"
HEADCOUNT = "HEADCOUNT"

QUANTITY_TYPES = (CPI_LEVEL, UNEMPLOYMENT_RATE, POLICY_RATE, MARKET_RATE,
                  CREDIT_SPREAD, REVENUE, MARGIN, BACKLOG, BOOKINGS, ORDERS,
                  CANCELLATIONS, CAPEX, GUIDANCE, PRICE, WAGE, HEADCOUNT)

# --- what the number is measured against --------------------------------------
#
# LEVEL and CHANGE have been confused in this engine before. "Revenue of 4.1bn"
# and "revenue up 4.1%" are different facts and support different conclusions,
# and a field that holds 4.1 for both is worse than no field.
LEVEL = "LEVEL"
CHANGE = "CHANGE"
BASES = (LEVEL, CHANGE)

NOMINAL = "NOMINAL"
REAL = "REAL"
UNSTATED = "UNSTATED"
PRICE_BASES = (NOMINAL, REAL, UNSTATED)


class QuantityRejected(ValueError):
    """A number that could not be shown to measure anything."""


@dataclass(frozen=True)
class EconomicQuantity:
    """One number, and everything needed to know what it is a number OF."""

    quantity_type: str
    value: float
    unit: str
    basis: str = LEVEL
    period: str = ""
    currency: str = ""
    nominal_real: str = UNSTATED
    seasonal_adjustment: str = UNSTATED
    scope: str = ""
    #: The exact words the number was read from. Required: a quantity with no
    #: span cannot be checked by a person, and an unverifiable number in a
    #: field called `value` is the most dangerous shape data can take here.
    source_span: str = ""
    evidence_id: str = ""

    def __post_init__(self) -> None:
        if self.quantity_type not in QUANTITY_TYPES:
            raise QuantityRejected(
                f"unknown quantity type {self.quantity_type!r}")
        if self.basis not in BASES:
            raise QuantityRejected(f"unknown basis {self.basis!r}")
        if self.nominal_real not in PRICE_BASES:
            raise QuantityRejected(
                f"unknown price basis {self.nominal_real!r}")
        if not self.unit.strip():
            raise QuantityRejected(
                "a quantity needs its unit; 4.1 is not a fact until it is "
                "4.1 per cent or 4.1 billion dollars")
        if not self.source_span.strip():
            raise QuantityRejected(
                "a quantity needs the words it was read from, or nobody can "
                "check it and nobody will")

    def as_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d.update(contract=CONTRACT)
        return d


# --- the vocabulary, subject first ----------------------------------------------
#
# Each entry names an economic subject and the words that claim a number for
# it. Extraction walks THESE, not the digits: a number nothing in this table
# claims is discarded, which is why the yield is low.
_SUBJECTS: Tuple[Tuple[str, str, Tuple[str, ...]], ...] = (
    (REVENUE, "revenue", ("revenue", "net sales", "total sales", "turnover")),
    (MARGIN, "margin", ("gross margin", "operating margin", "net margin",
                        "margin")),
    (BACKLOG, "backlog", ("backlog", "order book",
                          "remaining performance obligation")),
    (BOOKINGS, "bookings", ("bookings", "new bookings", "net bookings")),
    (ORDERS, "orders", ("orders", "new orders", "order intake")),
    (CANCELLATIONS, "cancellations", ("cancellation", "cancellations",
                                      "cancelled orders")),
    (CAPEX, "capital expenditure", ("capital expenditure", "capital spending",
                                    "capex")),
    (GUIDANCE, "guidance", ("guidance", "outlook for", "we now expect")),
    (HEADCOUNT, "headcount", ("headcount", "employees", "workforce")),
    (WAGE, "wages", ("wages", "average hourly earnings",
                     "average weekly earnings")),
    (PRICE, "price", ("price increase", "price reduction", "list price",
                      "realised pricing", "realized pricing")),
)

#: A number, with an optional scale word and an optional unit.
_NUMBER = re.compile(
    r"(?P<currency>[$€£¥]|US\$|C\$)?\s*"
    r"(?P<value>\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)\s*"
    r"(?P<scale>billion|bn|B\b|million|mn|M\b|thousand|k\b)?\s*"
    r"(?P<unit>%|per cent|percent|basis points|bps)?",
    re.I)

_SCALE = {"billion": 1e9, "bn": 1e9, "b": 1e9, "million": 1e6,
          "mn": 1e6, "m": 1e6, "thousand": 1e3, "k": 1e3}

#: Shapes that are digits and never quantities. Checked before the vocabulary,
#: because "Item 1A" and "Section 13(d)" sit inside sentences that also mention
#: revenue, and a subject-first parser is not by itself enough.
_NEVER = (
    re.compile(r"\bitem\s+\d", re.I),
    re.compile(r"\bsection\s+\d", re.I),
    re.compile(r"\bpage\s+\d", re.I),
    re.compile(r"\bnote\s+\d+\s+to\b", re.I),
    re.compile(r"\b\d{2}-\d{7}\b"),            # employer identification
    re.compile(r"\bcik\s*[:#]?\s*\d+", re.I),
    re.compile(r"\b(19|20)\d{2}[-/]\d{1,2}[-/]\d{1,2}\b"),
    re.compile(r"\bform\s+\d+-?[a-z]?\b", re.I),
)

#: Words that mean the number belongs to somebody else's business.
_NOT_OURS = re.compile(
    r"\b(analysts?|consensus|the market|peers?|competitors?|the index|"
    r"the sector)\b", re.I)

#: Money that belongs to a named use other than the subject. A buyback, a
#: dividend or an acquisition price sits in the same sentence as revenue often
#: enough that it is worth stopping the scan at one.
_OTHER_MONEY = re.compile(
    r"\b(buy ?back|repurchase|dividend|acquisition|acquire\w*|"
    r"investment in|impairment|charge of|settlement)\b", re.I)

_CHANGE_WORDS = re.compile(
    r"\b(up|down|rose|fell|increased?|decreased?|declined?|grew|growth of|"
    r"higher|lower)\b", re.I)


#: How far from its subject a number may sit and still belong to it.
_NEAR = 60


def _nearest_number(sentence: str, start: int, length: int):
    """The number closest to the subject, and whether something else owns it.

    BOTH DIRECTIONS. "€9.3 billion total net sales" puts the figure BEFORE the
    subject and "revenue of $4.1 billion" puts it after; a forward-only scan
    read the first as 2.9 billion because that was the next number after the
    words it matched. Nearest wins, and a tie goes to the following number,
    which is the more common English order.

    A number is disowned when a use word — buyback, dividend, acquisition —
    sits between it and the subject, or immediately after it.
    """
    after = sentence[start + length:]
    before = sentence[:start]
    forward = _NUMBER.search(after)
    backward = None
    for m in _NUMBER.finditer(before):
        backward = m
    candidates = []
    if forward and forward.group("value"):
        candidates.append((forward.start(), forward, after, "after"))
    if backward and backward.group("value"):
        candidates.append((len(before) - backward.end(), backward, before,
                           "before"))
    if not candidates:
        return None
    distance, found, region, side = min(candidates, key=lambda c: (c[0],
                                                                   c[3]))
    if distance > _NEAR:
        return None
    if side == "after":
        between = region[:found.start()]
        trailing = region[found.end():found.end() + 24]
    else:
        between = region[found.end():]
        trailing = ""
    claimed = bool(_OTHER_MONEY.search(between)
                   or _OTHER_MONEY.search(trailing))
    return found, claimed


def _sentences(text: str) -> List[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text or "")
            if s.strip()]


def extract(text: str, *, evidence_id: str = "", period: str = ""
            ) -> Tuple[List[EconomicQuantity], Dict[str, int]]:
    """Quantities this text actually states, and a count of what was refused.

    Subject-first: each sentence is searched for a named economic subject, and
    only then for a number near it. A sentence with digits and no subject
    contributes nothing and is counted as `no_subject` — which is the majority
    outcome on real filings and is meant to be.
    """
    kept: List[EconomicQuantity] = []
    refused: Dict[str, int] = {}

    def refuse(reason: str) -> None:
        refused[reason] = refused.get(reason, 0) + 1

    for sentence in _sentences(text):
        if any(p.search(sentence) for p in _NEVER):
            refuse("structural_reference_not_a_measurement")
            continue
        if _NOT_OURS.search(sentence):
            refuse("number_belongs_to_another_party")
            continue
        lowered = sentence.lower()
        matched = [(qt, name, word) for qt, name, words in _SUBJECTS
                   for word in words if word in lowered]
        if not matched:
            if any(ch.isdigit() for ch in sentence):
                refuse("no_subject")
            continue
        # The most specific subject wins: "gross margin" before "margin".
        quantity_type, _label, word = max(matched, key=lambda m: len(m[2]))
        start = lowered.index(word)
        # THE NUMBER MUST STILL BELONG TO THE SUBJECT WHEN IT IS REACHED.
        # "grows Q2 revenue and details $400M buyback" contains the word
        # revenue and a number, and the number is the buyback. Scanning
        # forward from the subject until ANY other economic noun appears is
        # what keeps the two apart; before this, a share repurchase was
        # extracted as revenue of 400.
        found = _nearest_number(sentence, start, len(word))
        if found is None:
            refuse("subject_without_a_number")
            continue
        found, claimed_by_another = found
        if claimed_by_another:
            # "grows Q2 revenue and details $400M buyback" contains the word
            # revenue and a number, and the number is the buyback. Before this
            # check a share repurchase was extracted as revenue of 400.
            refuse("number_claimed_by_another_use")
            continue
        raw = found.group("value").replace(",", "")
        try:
            value = float(raw)
        except ValueError:
            refuse("unparseable_number")
            continue
        scale = _SCALE.get((found.group("scale") or "").lower(), 1.0)
        unit_word = (found.group("unit") or "").lower()
        percentage = unit_word in ("%", "per cent", "percent")
        if unit_word in ("basis points", "bps"):
            unit, value = "bps", value
        elif percentage:
            unit = "%"
        elif found.group("currency"):
            unit = found.group("currency")
            value *= scale
        elif scale != 1.0:
            unit = "count"
            value *= scale
        else:
            refuse("number_without_a_unit")
            continue
        # Read from the whole sentence: the direction word may sit on
        # either side of the figure it qualifies.
        basis = CHANGE if _CHANGE_WORDS.search(sentence) else LEVEL
        try:
            kept.append(EconomicQuantity(
                quantity_type=quantity_type, value=value, unit=unit,
                basis=basis, period=period,
                currency=(found.group("currency") or ""),
                source_span=sentence[:240], evidence_id=evidence_id))
        except QuantityRejected:
            refuse("failed_the_contract")
    return kept, refused


def summarise(quantities: Sequence[EconomicQuantity],
              refused: Optional[Dict[str, int]] = None) -> dict:
    by_type: Dict[str, int] = {}
    for q in quantities:
        by_type[q.quantity_type] = by_type.get(q.quantity_type, 0) + 1
    total_refused = sum((refused or {}).values())
    return {
        "contract": CONTRACT,
        "quantities": len(quantities),
        "by_type": dict(sorted(by_type.items())),
        "by_basis": {b: sum(1 for q in quantities if q.basis == b)
                     for b in BASES},
        "refused": total_refused,
        "refused_reasons": dict(sorted((refused or {}).items())),
        "yield": (round(len(quantities) / (len(quantities) + total_refused), 4)
                  if (len(quantities) + total_refused) else None),
        "note": ("extraction runs subject-first, so a low yield is the "
                 "design and a high one would mean digits are being "
                 "harvested without an economic subject"),
    }
