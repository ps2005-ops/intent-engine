"""Dated company financials from the regulator, with the date they became knowable.

WHY THIS EXISTS
---------------
History Rewind could describe a vintage but could not draw one. Every panel was
prose, because the only per-company dated series the product held was a list of
filing FORMS — "3 × 10-Q, 1 × 10-K" — which says a company reported and says
nothing about what it reported. A strategy simulator needs a quantity.

XBRL company facts are that quantity, and they are the right one for this
surface for a reason that is easy to miss: every fact carries TWO dates.

    end     the period the number describes          (2022-12-31)
    filed   the day the number entered the record    (2023-02-16)

`end` is what the number is about. `filed` is when a decision-maker could
possibly have known it. A vintage wall built on `end` leaks — on 2023-01-05 the
full-year 2022 revenue existed as a fact about the world and did NOT exist as
information anybody had. This module keeps both and the wall upstream keys on
`filed`, so "what was knowable then" means what had actually been published.

WHAT THIS IS NOT
----------------
Not a valuation, not an estimate, not a forecast. Every point here is a number
a company filed under penalty. Anything modelled from these lives in
`executive.market_expectation`, is labelled there, and never comes back through
this module wearing an observation's clothes.

FAILURE IS A STATE, NOT AN EXCEPTION
------------------------------------
Never raises. A company with no XBRL history (a private company, a foreign
issuer that files in another taxonomy, a filer too new to have two annual
points) returns an empty series carrying the REASON, which the resolution
ladder turns into the next rung rather than into an empty paragraph.
"""
from __future__ import annotations

import dataclasses
import datetime as _dt
import json
from typing import Dict, List, Optional, Sequence, Tuple

CONTRACT = "company_financial_series.v1"

CONCEPT_URL = ("https://data.sec.gov/api/xbrl/companyconcept/"
               "CIK{cik10}/us-gaap/{tag}.json")

#: Metric families, and the us-gaap tags that carry them, most specific first.
#:
#: The ladder is per FAMILY rather than per company: `Revenues` is the general
#: tag and most filers use it, but a filer that adopted ASC 606 reporting in
#: full uses `RevenueFromContractWithCustomerExcludingAssessedTax` and files
#: nothing under `Revenues` at all. Measured: Cloudflare and Shopify answer 404
#: on `Revenues`; Caterpillar and Bank of America answer 404 on the ASC 606
#: tag. Either alone loses half the golden set.
TAG_LADDER: Dict[str, Tuple[str, ...]] = {
    "revenue": (
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "SalesRevenueNet",
        "RevenuesNetOfInterestExpense",
    ),
    "earnings": (
        "NetIncomeLoss",
        "ProfitLoss",
    ),
    "operating_income": (
        "OperatingIncomeLoss",
    ),
    "cash_from_operations": (
        "NetCashProvidedByUsedInOperatingActivities",
    ),
    "research": (
        "ResearchAndDevelopmentExpense",
    ),
    "equity": (
        "StockholdersEquity",
    ),
}

#: The families worth drawing, by business model class. The FIRST that
#: resolves becomes the index; the rest are context on the date panel.
#:
#: This is a business-model rule (§62), not a company rule. A subscription
#: software company is indexed on revenue because contracted revenue is the
#: thing its strategy moves; a balance-sheet business is indexed on revenue
#: net of interest expense because gross interest income moves with rates
#: rather than with anything management decided.
INDEX_FAMILY: Dict[str, Tuple[str, ...]] = {
    "SUBSCRIPTION_SOFTWARE": ("revenue", "operating_income"),
    "DESIGN_AND_MANUFACTURE": ("revenue", "operating_income"),
    "COMMODITY_PRODUCER": ("revenue", "cash_from_operations"),
    "BRANDED_CONSUMER": ("revenue", "operating_income"),
    "CONTRACTED_OR_RATE_BASE_ASSETS": ("revenue", "cash_from_operations"),
    "BALANCE_SHEET_OR_NETWORK": ("revenue", "earnings"),
    "MANUFACTURE_AND_AFTERMARKET": ("revenue", "operating_income"),
    "PEOPLE_OR_ROUTE_BASED_SERVICES": ("revenue", "operating_income"),
    "REGULATED_PRODUCT_OR_PROVIDER": ("revenue", "research"),
}

_DEFAULT_FAMILIES = ("revenue", "earnings")

#: What the index MEANS, per class, in the reader's words. The chart's y-axis
#: is a normalised index and an unexplained index is a decoration.
INDEX_MEANING: Dict[str, str] = {
    "SUBSCRIPTION_SOFTWARE":
        "contracted revenue — the installed base plus what was added to it",
    "DESIGN_AND_MANUFACTURE":
        "revenue — units shipped at the prices they were sold for",
    "COMMODITY_PRODUCER":
        "revenue — volume at the prevailing price, which management sets "
        "neither of directly",
    "BRANDED_CONSUMER":
        "revenue — volume, price and mix across the brand portfolio",
    "CONTRACTED_OR_RATE_BASE_ASSETS":
        "revenue — contracted or rate-regulated, so it moves with the asset "
        "base rather than with demand",
    "BALANCE_SHEET_OR_NETWORK":
        "revenue net of interest expense — what the balance sheet earned "
        "after paying for its funding",
    "MANUFACTURE_AND_AFTERMARKET":
        "revenue — new equipment plus the aftermarket that follows it",
    "PEOPLE_OR_ROUTE_BASED_SERVICES":
        "revenue — billable capacity actually sold",
    "REGULATED_PRODUCT_OR_PROVIDER":
        "revenue — the products currently approved and on the market",
}

_UNKNOWN_MEANING = ("revenue — the top line the company reports to its "
                    "regulator")

_FAMILY_LABEL = {
    "revenue": "revenue",
    "earnings": "net income",
    "operating_income": "operating income",
    "cash_from_operations": "cash from operations",
    "research": "research and development spend",
    "equity": "shareholders' equity",
}


def _date(value) -> Optional[_dt.date]:
    try:
        return _dt.date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


@dataclasses.dataclass(frozen=True)
class Fact:
    """One filed number, and the two dates that matter.

    `knowable_from` is `filed` and is the only date the vintage wall consults.
    """
    end: _dt.date
    value: float
    knowable_from: _dt.date
    form: str = ""
    fiscal_year: int = 0
    period: str = ""
    accession: str = ""

    @property
    def year(self) -> int:
        """The year this period BELONGS to, not the year it ended in.

        A 52/53-week retailer's fiscal 2016 ends 1 January 2017. Keying on
        `end.year` filed it as 2017 and put two points on that year — measured
        on Johnson & Johnson, whose 2017-01-01 and 2017-12-31 rows are twelve
        months apart and describe different years. A period ending in the
        first half of a calendar year is that calendar year minus one.
        """
        return self.end.year - 1 if self.end.month <= 6 else self.end.year

    def as_dict(self) -> dict:
        return {"end": self.end.isoformat(), "value": self.value,
                "knowable_from": self.knowable_from.isoformat(),
                "form": self.form, "fiscal_year": self.fiscal_year,
                "period": self.period}


@dataclasses.dataclass(frozen=True)
class Series:
    """An annual series, or an honest account of why there isn't one."""
    family: str = ""
    tag: str = ""
    label: str = ""
    unit: str = "USD"
    points: Tuple[Fact, ...] = ()
    #: Why the series is empty or short. Never blank when `points` is short.
    note: str = ""
    source: str = "SEC XBRL company facts"

    @property
    def available(self) -> bool:
        return len(self.points) >= 2

    def knowable_by(self, cutoff: _dt.date) -> Tuple[Fact, ...]:
        """THE WALL. Facts published on or before `cutoff` — nothing else."""
        return tuple(f for f in self.points if f.knowable_from <= cutoff)

    def after(self, cutoff: _dt.date) -> Tuple[Fact, ...]:
        return tuple(f for f in self.points if f.knowable_from > cutoff)

    def as_dict(self) -> dict:
        return {"contract": CONTRACT, "family": self.family, "tag": self.tag,
                "label": self.label, "unit": self.unit, "note": self.note,
                "source": self.source,
                "points": [p.as_dict() for p in self.points]}


# ===========================================================================
# retrieval
# ===========================================================================
_CACHE: Dict[Tuple[str, str], Optional[dict]] = {}


def _concept(cik10: str, tag: str, *, transport=None, resolver=None,
             timeout: float = 8.0) -> Optional[dict]:
    """One us-gaap concept for one filer, or None. Never raises, cached."""
    key = (cik10, tag)
    if key in _CACHE:
        return _CACHE[key]
    payload = None
    try:
        from intent_engine.company_ingestion.edgar import _fetch_bytes
        raw = _fetch_bytes(CONCEPT_URL.format(cik10=cik10, tag=tag),
                           transport=transport, resolver=resolver,
                           timeout=timeout)
        payload = json.loads(raw.decode("utf-8", "replace"))
        if not isinstance(payload, dict) or "units" not in payload:
            payload = None
    except Exception:                                       # noqa: BLE001
        payload = None
    _CACHE[key] = payload
    return payload


def _annual_facts(payload: dict) -> Tuple[Tuple[Fact, ...], str]:
    """Full-year facts from a companyconcept payload, newest filing wins.

    ANNUAL MEANS A YEAR, MEASURED. A duration fact is annual when its period
    spans 340-400 days; the `frame` field would be easier and is absent on
    roughly a third of rows, and `fp == "FY"` is the FISCAL-YEAR LABEL of the
    filing, not of the fact — a 10-K carries the Q4 and the full-year figure
    under the same `fp`, so keying on it silently indexes a quarter.
    """
    units = (payload or {}).get("units") or {}
    unit = "USD"
    rows: Sequence[dict] = ()
    for candidate in ("USD", "USD/shares", "pure"):
        if units.get(candidate):
            unit, rows = candidate, units[candidate]
            break
    if not rows:
        for candidate, values in units.items():
            unit, rows = candidate, values
            break
    by_end: Dict[_dt.date, Fact] = {}
    for row in rows or ():
        if not isinstance(row, dict):
            continue
        end = _date(row.get("end"))
        start = _date(row.get("start"))
        filed = _date(row.get("filed"))
        if end is None or filed is None:
            continue
        if start is None:
            continue                    # an instant fact, not a flow
        span = (end - start).days
        if not 340 <= span <= 400:
            continue
        try:
            value = float(row.get("val"))
        except (TypeError, ValueError):
            continue
        fact = Fact(end=end, value=value, knowable_from=filed,
                    form=str(row.get("form") or ""),
                    fiscal_year=int(row.get("fy") or 0),
                    period=str(row.get("fp") or ""),
                    accession=str(row.get("accn") or ""))
        # A restated year is filed again later. Keep the EARLIEST publication
        # of each year: the wall asks what was knowable, and a 2024 restatement
        # of 2021 was not knowable in 2022. The later value is a different
        # fact, not a better one, for this surface's purpose.
        prior = by_end.get(end)
        if prior is None or fact.knowable_from < prior.knowable_from:
            by_end[end] = fact
    return tuple(sorted(by_end.values(), key=lambda f: f.end)), unit


def annual_series(cik: str, family: str = "revenue", *, transport=None,
                  resolver=None, timeout: float = 8.0) -> Series:
    """The annual series for one metric family. Never raises."""
    digits = "".join(ch for ch in str(cik or "") if ch.isdigit())
    if not digits:
        return Series(family=family, note=(
            "This company is not an SEC filer in this run, so the regulator "
            "holds no dated series for it."))
    cik10 = f"{int(digits):010d}"
    tried = []
    merged: Dict[int, Fact] = {}
    used_tags: List[str] = []
    unit = "USD"
    # EVERY TAG IN THE FAMILY, MERGED BY YEAR — not the first that answers.
    #
    # First-wins lost four years of Shopify: it filed under the ASC 606 tag as
    # a foreign private issuer and moved to `Revenues` when it became a
    # domestic filer, so the ladder stopped at a series that ended in 2023 for
    # a company whose 2025 revenue is public. A filer switches tags; it does
    # not report the same year twice under two of them, and where it does the
    # earliest publication wins on the same rule restatements do.
    for tag in TAG_LADDER.get(family, ()):
        tried.append(tag)
        payload = _concept(cik10, tag, transport=transport, resolver=resolver,
                           timeout=timeout)
        if payload is None:
            continue
        facts, tag_unit = _annual_facts(payload)
        if not facts:
            continue
        used_tags.append(tag)
        unit = tag_unit
        for fact in facts:
            prior = merged.get(fact.year)
            if prior is None or fact.knowable_from < prior.knowable_from:
                merged[fact.year] = fact
    if len(merged) >= 2:
        points = tuple(sorted(merged.values(), key=lambda f: f.year))
        return Series(
            family=family, tag=", ".join(used_tags), unit=unit, points=points,
            label=_FAMILY_LABEL.get(family, family.replace("_", " ")),
            note=(f"{len(points)} full financial year(s), "
                  f"{points[0].year}-{points[-1].year}, each dated by the day "
                  f"it was filed rather than the period it covers."))
    return Series(family=family, note=(
        "The regulator's structured data holds no multi-year annual series "
        "for this company under the tags this metric uses"
        + (f" ({', '.join(tried)})." if tried else ".")))


def index_series(cik: str, model_class: str = "", *, transport=None,
                 resolver=None, timeout: float = 8.0
                 ) -> Tuple[Series, Tuple[Series, ...]]:
    """(the series to index on, the supporting series). Never raises.

    Returns the first family that resolves as the index. The supporting
    series are fetched only when the index resolved — a company with no
    revenue series will not have an operating-income one either, and two
    more failed round trips is two more seconds of a customer waiting.
    """
    families = INDEX_FAMILY.get(str(model_class or ""), _DEFAULT_FAMILIES)
    primary = Series()
    used = ""
    for family in families:
        candidate = annual_series(cik, family, transport=transport,
                                  resolver=resolver, timeout=timeout)
        if candidate.available:
            primary, used = candidate, family
            break
        if not primary.note:
            primary = candidate
    if not used:
        return primary, ()
    supporting: List[Series] = []
    for family in families:
        if family == used:
            continue
        extra = annual_series(cik, family, transport=transport,
                              resolver=resolver, timeout=timeout)
        if extra.available:
            supporting.append(extra)
    return primary, tuple(supporting)


def index_meaning(model_class: str) -> str:
    return INDEX_MEANING.get(str(model_class or ""), _UNKNOWN_MEANING)
