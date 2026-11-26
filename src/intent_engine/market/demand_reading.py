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
from typing import Optional, Tuple

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


#: An account that names no period is "the next reported figure" only a
#: reporting cycle later. 45 days admitted recaps of the same quarter
#: published 47-57 days after it (ad-hoc-news "stock reports X percent
#: revenue growth"); quarterly reports arrive about 90 days apart.
MIN_PERIOD_GAP_DAYS = 75


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


def _quarter_end(q: int, year: int) -> date:
    return date(year, 3 * q, 31 if q in (1, 4) else 30)


def names_an_already_reported_quarter(grade_text: str, basis_at: str,
                                      grade_at: str) -> bool:
    """A grade naming quarter Qn is OLD NEWS if Qn had ended before the
    basis was written (its results were the basis's subject or earlier).
    A bare "Q2" takes the latest year whose Q2 ended before the grade."""
    p = reporting_period(grade_text)
    if not p or not p.startswith("Q"):
        return False
    q = int(p[1]); yr = p[3:].strip()
    try:
        g = date.fromisoformat(grade_at[:10]); b = date.fromisoformat(basis_at[:10])
    except ValueError:
        return False
    y = int(yr) if yr else g.year
    if not yr and _quarter_end(q, y) > g:
        y -= 1
    return _quarter_end(q, y) <= b


def names_a_later_quarter(grade_text: str, basis_at: str, grade_at: str) -> bool:
    p = reporting_period(grade_text)
    if not p or not p.startswith("Q"):
        return False
    return not names_an_already_reported_quarter(grade_text, basis_at, grade_at)


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
    if pb is not None and pg is not None and pb[:2] == pg[:2] and (
            pb == pg or len(pb) == 2 or len(pg) == 2):
        return True          # same quarter, with or without the year written
    if names_an_already_reported_quarter(grade_text, basis_at, grade_at):
        return True
    if names_a_later_quarter(grade_text, basis_at, grade_at):
        return False         # an explicitly later period is a new observation
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


#: Accounts that are not an observation of the subject's own business.
_NOT_AN_OBSERVATION = re.compile(
    r"\b(reports? next week|earnings preview|preview\b|what to expect|"
    r"expected to report|wall street expects|ahead of (its |q\d )?earnings|"
    r"has (lowered|raised|boosted|cut) (its )?(expectations|price target) for|"
    r"analysts? says?|stock price expected|price target|"
    r"\bvs\.?\b|versus)\b", re.I)
_CASE_STUDY = re.compile(
    r"\b(mov(?:ed|ing)\b[^.]{0,40}\bto|migrat\w*\b[^.]{0,40}\bto|"
    r"switch\w*\b[^.]{0,40}\bto|on shopify|with stripe|"
    r"using (shopify|stripe)|partners? with|"
    r"helping (enterprises|merchants|brands)|our (customers?|merchants?) )", re.I)


_PCT = re.compile(r"(\d+(?:\.\d+)?)\s*(?:%|percent|per cent)", re.I)


def shares_a_reported_figure(basis_text: str, grade_text: str) -> bool:
    """The same percentage in opener and grade ("36%" / "36 percent") is a
    recap of the same report, whatever the date."""
    norm = lambda t: {f"{float(x):g}" for x in _PCT.findall(t or "")}
    return bool(norm(basis_text) & norm(grade_text))


def names_the_subject(subject: str, text: str) -> bool:
    """Third-party accounts must name the subject; first-person filings count."""
    t = (text or "").lower()
    if re.search(r"\b(we|our)\b", t):
        return True
    tokens = [w for w in re.split(r"[_\-\s]+", (subject or "").lower()) if len(w) > 2]
    return any(re.search(rf"\b{re.escape(w)}", t) for w in tokens[:1])


def grading_admissible(subject: str, grade_text: str, family: str) -> Tuple[bool, str]:
    """May this account grade an expectation about `subject`?

    Refuses previews and expectations (not observations), comparisons with
    other companies, analyst actions on other companies, and customer case
    studies. For demand families the account must also READ as a demand
    movement under demand_reading (surprises, price, profit and cost do not
    test a demand belief).
    """
    t = grade_text or ""
    if not names_the_subject(subject, t):
        return False, "the account does not name the subject (another company's result)"
    if _NOT_AN_OBSERVATION.search(t):
        return False, "preview, comparison or analyst action, not an observation of the subject"
    if _CASE_STUDY.search(t):
        return False, "a customer or partner case study, not the subject's own result"
    if family in (WEAKENING, STRENGTHENING):
        r = read(t)
        if r.family not in (WEAKENING, STRENGTHENING):
            return False, f"no demand movement in the account ({r.family}: {r.reason[:60]})"
    return True, ""
