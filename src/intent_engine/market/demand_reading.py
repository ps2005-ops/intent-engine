"""demand_reading.v2 (SHADOW): a demand belief needs a demand quantity.

WHY
---
`belief_formation.direction_of` reads ONE up/down word anywhere in a
sentence, and `_ROUTES` sends any DOWN earnings, surprise or guidance
sentence to `demand_weakening`. On the 15 demand-weakening expectations the
runtime graded through 2026-11-13, 2 confirmed. Traced one by one:

  * 5 were SURPRISES, not declines: "revenue falls short at $3,742M" while
    revenue grew (Shopify), "misses EPS" (Linde), "misses on revenue" (NextEra)
  * 6 were PROFIT, MARGIN OR COST: "revenue up, profitability falls" (Honda),
    "lowers profit forecast on deal costs" (J&J), "+36% revenue as
    restructuring widens GAAP loss" (Cloudflare)
  * 1 was a PRICE: "stock falls on Q2 earnings" after a beat-and-raise
  * 2 were stale or irrelevant (a 2017 tax-law sentence; an April headline)

So the family was not measuring demand, and reversing it would be wrong.

THE NECESSARY CONDITIONS
------------------------
A sentence opens a demand reading only if, in ONE clause:
  1. it names a demand quantity (revenue, sales, orders, bookings, volume,
     shipments, GMV, deposits, subscribers, traffic, units, backlog), AND
  2. that quantity moves, AND
  3. the comparison is to the company's own past (or to its own guidance),
     NOT to analysts' estimates. A miss or beat against estimates is a
     SURPRISE, recorded as such and kept apart, because it says what the
     market expected, not what customers did.
Everything else abstains with the reason: price moves, profit, margin, EPS,
cost, restructuring and headcount are not demand.

Grading (see `admissible_grade`): the falsifier says "the NEXT reported
figure". Evidence about the same reporting period as the basis is a second
description of one observation, not a test, so it may not grade.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Optional

CONTRACT = "demand_reading.v2.1"

WEAKENING, STRENGTHENING = "demand_weakening", "demand_strengthening"
SURPRISE_NEG, SURPRISE_POS = "negative_surprise", "positive_surprise"
ABSTAIN = "ABSTAIN"

# v2.1 (2026-11-25, from failures on held-out sample 1): user and buyer
# activity measures were missing.
_QTY = (r"revenue|revenues|sales|orders|order book|bookings|backlog|volume|"
        r"volumes|shipments|deliveries|gmv|gross merchandise|deposits?|"
        r"subscribers|subscriptions|users|dau|mau|daily active users|"
        r"paying customers|buyers|items per buyer|traffic|units|demand|"
        r"loan growth")
_Q = re.compile(rf"\b({_QTY})\b", re.I)
_UP = re.compile(r"\b(ris\w*|rose|grow\w*|grew|increas\w*|up|jump\w*|surg\w*|"
                 r"climb\w*|gain\w*|higher|expand\w*|accelerat\w*|record|"
                 r"rais\w*|lift\w*|boost\w*)\b", re.I)
_DN = re.compile(r"\b(fall\w*|fell|declin\w*|drop\w*|decreas\w*|lower\w*|"
                 r"down|shrank|shrink\w*|contract\w*|slump\w*|slow\w*|"
                 r"weak\w*|cut\w*|reduc\w*)\b", re.I)
# v2.1: bare "top" matched "on top of last year" and "Top ... Pick"; a top
# is a surprise only when it tops estimates/expectations/consensus.
_VS_EST = re.compile(r"\b(estimate\w*|expectation\w*|consensus|forecasts? of "
                     r"analysts|analysts?|street|short of|falls? short|fell short|"
                     r"beat\w*|miss\w*|tops? (?:estimates|expectations|consensus|"
                     r"forecasts?)|topped (?:estimates|expectations|consensus)|"
                     r"shy of)\b", re.I)
_BEAT = re.compile(r"\b(beat\w*|tops?|topped|exceed\w*|above)\b", re.I)
_MISS = re.compile(r"\b(miss\w*|short|shy|below|under)\b", re.I)
_NOT_DEMAND = re.compile(r"\b(stock|shares?|price target|fair value|profit\w*|"
                         r"margin\w*|eps|earnings per share|net income|loss\w*|"
                         r"cost\w*|restructur\w*|staff|jobs|layoffs?|"
                         r"headcount|tax)\b", re.I)
_CLAUSES = re.compile(r"[;,:]|\s[-–—]\s|\bbut\b|\bwhile\b|\bas\b|\band\b", re.I)


@dataclass(frozen=True)
class Reading:
    family: str           # WEAKENING / STRENGTHENING / SURPRISE_* / ABSTAIN
    quantity: str
    comparison: str       # "own_past" / "estimates" / ""
    reason: str


def read(text: str) -> Reading:
    text = text or ""
    found = []
    for clause in _CLAUSES.split(text):
        q = _Q.search(clause)
        if not q:
            continue
        up, dn = bool(_UP.search(clause)), bool(_DN.search(clause))
        if _VS_EST.search(clause):
            if _MISS.search(clause) and not _BEAT.search(clause):
                found.append(Reading(SURPRISE_NEG, q.group(1).lower(),
                                     "estimates", f"'{clause.strip()}' is a "
                                     "miss against estimates, not a decline"))
            elif _BEAT.search(clause) and not _MISS.search(clause):
                found.append(Reading(SURPRISE_POS, q.group(1).lower(),
                                     "estimates", f"'{clause.strip()}' is a "
                                     "beat against estimates, not growth"))
            continue
        if up and not dn:
            found.append(Reading(STRENGTHENING, q.group(1).lower(), "own_past",
                                 f"'{clause.strip()}'"))
        elif dn and not up:
            found.append(Reading(WEAKENING, q.group(1).lower(), "own_past",
                                 f"'{clause.strip()}'"))
    demand = {r.family for r in found} & {WEAKENING, STRENGTHENING}
    if len(demand) == 1:
        return next(r for r in found if r.family in demand)
    if len(demand) == 2:
        return Reading(ABSTAIN, "", "", "the sentence moves demand both ways")
    surprises = [r for r in found if r.comparison == "estimates"]
    if surprises:
        return surprises[0]
    if _NOT_DEMAND.search(text):
        return Reading(ABSTAIN, "", "", "names "
                       f"'{_NOT_DEMAND.search(text).group(1)}' but no demand "
                       "quantity moving against the company's own past; "
                       "price, profit, margin, cost and headcount are not demand")
    return Reading(ABSTAIN, "", "", "no demand quantity with a direction")


#: a later reporting period is at least this far after the basis
MIN_PERIOD_GAP_DAYS = 45


def admissible_grade(basis_observed_at: str, grade_observed_at: str) -> bool:
    """The falsifier names the NEXT reported figure. Evidence within one
    reporting period of the basis describes the same observation."""
    try:
        gap = (date.fromisoformat(grade_observed_at[:10])
               - date.fromisoformat(basis_observed_at[:10])).days
    except ValueError:
        return False
    return gap >= MIN_PERIOD_GAP_DAYS


_PERIOD = re.compile(r"\b(?:Q([1-4])|(first|second|third|fourth)[- ]quarter)\b"
                     r"[^0-9]{0,12}((?:19|20)\d\d)?|\bfy\s?((?:19|20)\d\d)\b", re.I)
_QWORD = {"first": "1", "second": "2", "third": "3", "fourth": "4"}


def reporting_period(text: str) -> Optional[str]:
    """'Q2 2026', 'Q1', 'FY2027' or None: the period a report names."""
    m = _PERIOD.search(text or "")
    if not m:
        return None
    q = m.group(1) or _QWORD.get((m.group(2) or "").lower())
    return f"Q{q} {m.group(3) or ''}".strip() if q else f"FY{m.group(4)}"


_RESULT_KINDS = {"EARNINGS_RESULT", "EARNINGS_SURPRISE"}
#: Results, guidance and coverage of one earnings release arrive together.
#: Measured on the audited grades: the same-release guidance followed the
#: result by 0-1 days (Duolingo, Honda, Shopify, Cloudflare); genuinely later
#: guidance or results came 11-35 days later (Etsy, P&G, Canadian National).
RELEASE_WINDOW_DAYS = 7


def same_reporting_event(basis_text: str, basis_at: str,
                         grade_text: str, grade_at: str,
                         basis_kind: str = "", grade_kind: str = "") -> bool:
    """Two accounts of ONE report.

    * The same named period ("Q2 2026" in both) is one report, however far
      apart the articles are.
    * Otherwise, under a reporting period apart AND the same kind of figure
      (a result and another account of a result) is one report.
    * A guidance revision after a result is a DIFFERENT figure: the
      falsifier itself names "the next reported revenue OR GUIDANCE figure".
    """
    pb, pg = reporting_period(basis_text), reporting_period(grade_text)
    if pb is not None and pb == pg:
        return True
    if admissible_grade(basis_at, grade_at):
        return False
    kinds = {basis_kind, grade_kind}
    try:
        gap = (date.fromisoformat(grade_at[:10])
               - date.fromisoformat(basis_at[:10])).days
    except ValueError:
        return True
    if basis_kind and grade_kind and basis_kind != grade_kind \
            and not kinds <= _RESULT_KINDS and gap > RELEASE_WINDOW_DAYS:
        return False
    return True
