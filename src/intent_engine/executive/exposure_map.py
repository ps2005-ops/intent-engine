"""Company economic exposure map: how a measured condition reaches THIS company.

WHY THIS EXISTS
---------------
MEASURED 2026-11-28 (prospect-98, 70 development companies): the economic
layer attached ONE sentence per business-model class -- every software
company read "rates set the discount rate on customers' own investment cases"
-- and 37 of 70 companies' own records cleared no decision archetype at all.
The economy was real; its connection to the company was a class default.

This map connects an economic VARIABLE the engine measures to a relationship
the company's OWN record states, with the sentence quoted. Each exposure is:

    external development -> economic variable -> company relationship
    -> transmission -> business consequence -> assumption it tests

WHAT IT MAY NOT DO
------------------
* An exposure exists only when the company's own material carries at least
  TWO distinct phrases of the relationship (one phrase is a coincidence -- the
  same gate the decision evidence uses). The matched sentence is returned so a
  reader can check it.
* "Observed" means the relationship is in the company's record; it never
  means the size of the effect is known. No coefficient, revenue share or
  probability is produced: there is no internal data to estimate one from.
* A variable the engine does not measure (enterprise cloud spending, security
  budgets) is labelled UNMEASURED, never silently treated as measured.
* A company's product DOMAIN is not its own exposure. A procurement-software
  vendor's pages say "supplier" because that is what its CUSTOMERS manage;
  that is mapped as customer-budget demand, never as the vendor facing a
  supply-chain decision (the false positive the decision lexicon makes).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, List, Sequence, Tuple

CONTRACT = "exposure_map.v1"

#: The founder-side join's own kind->channel table (one definition).
try:
    from intent_engine.external_intel.founder_economy import (
        KIND_CHANNEL as _KIND_CHANNEL)
except Exception:                                           # noqa: BLE001
    _KIND_CHANNEL = {}

OBSERVED = "OBSERVED_IN_COMPANY_RECORD"
#: The engine measures the channel this exposure transmits through.
MEASURED = "MEASURED"
UNMEASURED = "UNMEASURED_BY_THIS_ENGINE"
MIN_PHRASES = 2


@dataclass(frozen=True)
class ExposureSpec:
    key: str
    variable: str                 # the economic quantity
    channel: str                  # engine channel id, or "" when unmeasured
    relationship: str             # how this company stands to the variable
    phrases: Tuple[str, ...]      # first-party wording that evidences it
    transmission: str
    consequence: str
    assumption: str               # the management assumption it tests
    direction: str
    horizon: str
    conditions: str
    falsifier: str
    missing: str
    models: Tuple[str, ...] = ()  # business-model classes it applies to; () = any
    #: Distinct phrases required. CUSTOMER-DOMAIN exposures need more: a vendor
    #: whose customers ARE that function uses the vocabulary pervasively, while
    #: one use-case blog post (FalkorDB's "supply chain database guide",
    #: Writer's finance article) carries two or three phrases and is not one.
    min_phrases: int = 2
    #: The economic-state KIND this exposure joins in `founder_economy`
    #: (KIND_CHANNEL). "" where the engine publishes no such series -- that
    #: exposure is then UNMEASURED and says so, never silently measured.
    econ_kind: str = ""


_SOFTWARE = ("SUBSCRIPTION_SOFTWARE",)
_SERVICES = ("PEOPLE_OR_ROUTE_BASED_SERVICES",)

SPECS: Tuple[ExposureSpec, ...] = (
    ExposureSpec(
        "usage_priced_compute", "enterprise cloud and compute consumption", "",
        "revenue is priced on customer usage, so it moves with how much customers run",
        ("usage-based", "usage based", "consumption-based", "consumption based",
         "pay-as-you-go", "pay as you go", "per query", "metered", "usage pricing"),
        "a customer that cuts cloud spend reduces workloads, and usage-priced revenue falls with it inside the contract term",
        "net revenue retention and expansion move before bookings do",
        "that existing customers will keep growing the workloads they run",
        "revenue follows customer workload volume", "weeks to one quarter",
        "requires customers to be cost-cutting at the workload level, not only freezing new projects",
        "usage per customer holding or rising while customers report cloud cost optimisation",
        "usage per customer and expansion rate (internal data)", _SOFTWARE),
    ExposureSpec(
        "hyperscaler_channel", "hyperscaler marketplace and partner channel", "",
        "a material part of distribution runs through cloud marketplaces or hyperscaler partners",
        ("aws marketplace", "azure marketplace", "google cloud marketplace",
         "aws partner", "microsoft partner", "google cloud partner", "co-sell"),
        "marketplace terms and committed-spend drawdowns decide how customers buy, so platform policy reaches revenue directly",
        "deal timing and take-rate follow the platform's incentives",
        "that the platforms will keep promoting rather than competing with the product",
        "channel-dependent", "one to four quarters",
        "requires a meaningful share of deals to transact through the marketplace",
        "marketplace share of new bookings falling without a revenue effect",
        "share of bookings through each marketplace (internal data)", _SOFTWARE),
    ExposureSpec(
        "startup_customer_financing", "venture and growth financing conditions", "MARKET_RATE",
        "a material part of the customer base is early-stage or small companies",
        ("for startups", "startups and", "small businesses", "small and medium",
         "smb", "smbs", "growing companies", "early-stage companies"),
        "tighter funding conditions cut the budgets of venture-funded customers first and lift their failure rate",
        "logo churn and down-sell concentrate in the smallest customers",
        "that small-customer cohorts retain like enterprise ones",
        "financing tightens -> small-customer churn rises", "one to three quarters",
        "requires the rate move to reach venture funding volumes",
        "small-customer churn flat through a funding contraction",
        "churn and contraction by customer size (internal data)", econ_kind="financial_conditions"),
    ExposureSpec(
        "international_revenue", "exchange rates", "CURRENCY",
        "the company sells and operates across currencies",
        ("emea", "apac", "latin america", "latam", "international customers",
         "global customers", "customers worldwide", "customers in over", "local currency",
         "countries"),
        "a stronger home currency lowers translated non-home revenue and makes local-currency prices dearer for overseas buyers",
        "reported growth diverges from constant-currency growth",
        "that overseas pricing can hold in local currency",
        "home currency up -> translated revenue down", "immediate for translation; quarters for pricing",
        "requires revenue billed in other currencies (a single-currency biller is not exposed this way)",
        "reported and constant-currency growth staying equal through a currency move",
        "revenue by billing currency (internal data)", econ_kind="fx_dxy"),
    ExposureSpec(
        "delivery_labour", "wages and the market for skilled delivery staff", "LABOR",
        "revenue is delivered by people, so their cost and availability set margin and capacity",
        ("consultants", "consulting", "engineers", "nearshore", "offshore", "delivery centers",
         "delivery centres", "talent", "billable", "managed services", "practitioners"),
        "wage growth above price growth compresses margin; a tight labour market caps how much work can be taken on",
        "utilisation and margin per engagement move before revenue does",
        "that rate cards can rise at least as fast as delivery wages",
        "wages up faster than rates -> margin down", "two to four quarters",
        "requires a large share of cost to be delivery headcount",
        "margin held through a period of wage growth above bill-rate growth",
        "utilisation, bill rates and delivery wage cost (internal data)", _SERVICES, econ_kind="wages"),
    ExposureSpec(
        "customer_procurement_budgets", "corporate procurement and supply-chain activity", "INDUSTRIAL_DEMAND",
        "the product serves customers' procurement or supply-chain functions (the customers' domain, not the vendor's own supply chain)",
        ("procurement", "sourcing", "supplier", "suppliers", "spend management", "purchase order",
         "supply chain", "inventory", "demand planning", "tariff"),
        "when trade costs or supply disruption rise, customers' need to control spend rises while their budgets tighten: demand for the product can strengthen even as purchasing slows",
        "pipeline mix shifts toward cost-control use cases",
        "that cost pressure on customers raises rather than delays demand",
        "ambiguous: need up, budgets down", "one to three quarters",
        "requires customers' cost pressure to be large enough to justify new software",
        "deal cycles lengthening while cost-control demand is reported rising",
        "win rate and cycle length by use case (internal data)", _SOFTWARE, min_phrases=4, econ_kind="industrial_production"),
    ExposureSpec(
        "customer_finance_budgets", "corporate planning cycles and financing costs", "MARKET_RATE",
        "the product serves the finance function (planning, close, billing or cash)",
        ("fp&a", "cfo", "budgeting", "forecasting", "financial planning", "close process",
         "cash flow", "accounts receivable", "revenue recognition", "financial close"),
        "higher financing costs make cash and forecast accuracy a board priority, which raises the value of finance software while discretionary IT is cut",
        "finance-led purchases hold up better than other software in a downturn",
        "that the finance function keeps budget when other software is cut",
        "rates up -> finance-software priority up", "one to two quarters",
        "requires buyers to be finance leaders with their own budget",
        "finance-software deal volume falling as fast as other software in a rate rise",
        "pipeline by buyer function (internal data)", _SOFTWARE, min_phrases=4, econ_kind="policy_rate"),
    ExposureSpec(
        "public_sector_demand", "public-sector budgets and appropriations", "",
        "a material part of demand comes from government buyers",
        ("public sector", "government", "federal", "state and local", "fedramp", "defense",
         "department of"),
        "appropriations timing and fiscal tightening move deal timing, not only deal count",
        "quarterly bookings become lumpy around budget cycles",
        "that public-sector demand is as steady as commercial demand",
        "fiscal tightening -> delayed awards", "two to six quarters",
        "requires government buyers to be a material share of revenue",
        "public-sector bookings steady through a budget impasse",
        "public-sector share of bookings (internal data)", min_phrases=3),
    ExposureSpec(
        "compliance_driven_demand", "regulatory requirements on customers", "",
        "purchases are driven by customers' compliance obligations",
        ("compliance requirements", "regulatory requirements", "regulators", "nis2", "dora",
         "sec rule", "sec cybersecurity", "cmmc", "fedramp", "ai act", "audit readiness",
         "regulatory change"),
        "a new obligation pulls demand forward to its deadline; a relaxed one removes the forcing date",
        "bookings cluster around regulatory deadlines",
        "that compliance deadlines will keep forcing purchases on schedule",
        "new obligation -> demand pulled forward", "to the deadline",
        "requires the obligation to name controls the product supplies",
        "no bookings clustering around a major deadline",
        "bookings tagged by regulatory driver (internal data)", _SOFTWARE, min_phrases=3),
)


@dataclass(frozen=True)
class Exposure:
    key: str
    variable: str
    channel: str
    measurement: str
    relationship: str
    phrases: Tuple[str, ...]
    evidence: Tuple[str, ...]
    transmission: str
    consequence: str
    assumption: str
    direction: str
    horizon: str
    conditions: str
    falsifier: str
    missing: str
    status: str = OBSERVED

    def as_dict(self) -> dict:
        return dict(self.__dict__)


def _says(text: str, phrase: str) -> bool:
    if phrase not in text:
        return False
    return bool(re.search(r"(?<![0-9a-z])" + re.escape(phrase) + r"(?![0-9a-z])", text))


def _sentences_with(raw: str, phrases: Sequence[str], limit: int = 2) -> Tuple[str, ...]:
    out = []
    for s in re.split(r"(?<=[.!?])\s+", " ".join(raw.split())):
        low = s.lower()
        if 40 <= len(s) <= 400 and any(_says(low, p) for p in phrases):
            out.append(s)
            if len(out) >= limit:
                break
    return tuple(out)


def econ_kinds(emap: dict) -> tuple:
    """The economic-state kinds this company's evidenced exposures join."""
    by_key = {spec.key: spec.econ_kind for spec in SPECS}
    return tuple(dict.fromkeys(by_key.get(e["key"], "") for e in
                               (emap or {}).get("exposures", ()) if by_key.get(e["key"])))


def build(own_texts: Iterable[str], *, business_model_class: str = "",
          measured_channels: Iterable[str] = ()) -> dict:
    """The exposure map for one company. Never raises.

    `own_texts` are documents the company AUTHORED (its pages, its filings);
    third-party text is excluded on purpose -- an exposure is a fact about the
    company's own relationship to a variable.
    """
    raw = " ".join(t for t in own_texts if t)
    text = " ".join(raw.lower().split())
    channels = {str(c or "").split(":")[-1].upper() for c in measured_channels if c}
    out: List[Exposure] = []
    if len(text) >= 200:
        for spec in SPECS:
            if spec.models and business_model_class not in spec.models:
                continue
            hits = tuple(sorted({p for p in spec.phrases if _says(text, p)}))
            if len(hits) < max(MIN_PHRASES, spec.min_phrases):
                continue
            measurement = (MEASURED if spec.econ_kind and (
                               spec.channel in channels or
                               _KIND_CHANNEL.get(spec.econ_kind, "") in channels)
                           else UNMEASURED)
            out.append(Exposure(
                key=spec.key, variable=spec.variable, channel=spec.channel,
                measurement=measurement, relationship=spec.relationship,
                phrases=hits[:6], evidence=_sentences_with(raw, hits),
                transmission=spec.transmission, consequence=spec.consequence,
                assumption=spec.assumption, direction=spec.direction,
                horizon=spec.horizon, conditions=spec.conditions,
                falsifier=spec.falsifier, missing=spec.missing))
    out.sort(key=lambda e: (e.measurement != MEASURED, -len(e.phrases)))
    return {"contract": CONTRACT, "business_model_class": business_model_class,
            "measured_channels": sorted(channels),
            "exposures": [e.as_dict() for e in out],
            "state": "EXPOSURES_OBSERVED" if out else "NO_EXPOSURE_EVIDENCED",
            "limitation": ("Each exposure is a relationship stated in the company's own "
                           "material; its size is not known without internal data, and "
                           "none is estimated.")}
