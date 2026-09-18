"""The half of a company's economics that never appears in a filing.

WHY THIS EXISTS BEFORE ANY CUSTOMER HAS SUPPLIED DATA
-----------------------------------------------------
The commercial claim behind this project is that external economic reasoning
becomes worth something when it meets what a company knows about itself: a rate
move matters differently to a business with a refinancing due in six months
than to one sitting on cash. That claim needs an architecture whether or not a
customer has handed over a spreadsheet, and building the architecture against
a synthetic company is honest as long as the synthetic company can never be
mistaken for a real one.

THE TWO WALLS
-------------
    PERMISSION   internal evidence belongs to one company and is readable only
                 for that company. There is no cross-company aggregate, not
                 even an anonymous one, because "companies like yours" is the
                 shape a leak takes.

    PROVENANCE   synthetic records are marked at the source and the marking is
                 checked at every join. A synthetic figure reaching a live
                 briefing is not a cosmetic error — it is a fabricated fact
                 with a real company's name on it.

WHAT AN INTERNAL FACT IS NOT
----------------------------
It is not more reliable than external evidence because it came from inside. A
sales pipeline is a forecast, a budget is an intention, and a board assumption
is an opinion held confidently. Each carries its own standing for that reason.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

CONTRACT = "internal_state.v1"

# --- what a company knows about itself ---------------------------------------
REVENUE_PLAN = "REVENUE_PLAN"
BUDGET = "BUDGET"
PIPELINE = "PIPELINE"
CUSTOMER_CONCENTRATION = "CUSTOMER_CONCENTRATION"
SUPPLIER_CONCENTRATION = "SUPPLIER_CONCENTRATION"
PRICING = "PRICING"
CASH = "CASH"
DEBT = "DEBT"
HEADCOUNT = "HEADCOUNT"
HIRING_PLAN = "HIRING_PLAN"
ROADMAP = "ROADMAP"
CAPACITY = "CAPACITY"
INVENTORY = "INVENTORY"
STRATEGIC_DECISION = "STRATEGIC_DECISION"

INTERNAL_KINDS = (REVENUE_PLAN, BUDGET, PIPELINE, CUSTOMER_CONCENTRATION,
                  SUPPLIER_CONCENTRATION, PRICING, CASH, DEBT, HEADCOUNT,
                  HIRING_PLAN, ROADMAP, CAPACITY, INVENTORY,
                  STRATEGIC_DECISION)

# --- how firmly the company itself knows it ----------------------------------
RECORDED = "RECORDED"      # a ledger figure: cash, headcount, a signed term
PLANNED = "PLANNED"        # an intention: a budget, a hiring plan
FORECAST = "FORECAST"      # a projection: pipeline, revenue plan
ASSUMED = "ASSUMED"        # somebody's belief, held confidently
INTERNAL_STANDINGS = (RECORDED, PLANNED, FORECAST, ASSUMED)

#: Only these may harden a decision. A pipeline number is a forecast made by
#: people who are paid to be optimistic about it.
FIRM = frozenset({RECORDED})

# --- where it came from --------------------------------------------------------
LIVE = "LIVE"
SYNTHETIC = "SYNTHETIC"
PROVENANCES = (LIVE, SYNTHETIC)


class InternalRejected(ValueError):
    """An internal record that would leak, or would pretend to be real."""


class PermissionRefused(InternalRejected):
    """Raised when one company's internals are read for another."""


class SyntheticLeak(InternalRejected):
    """Raised when invented data would reach a real company's conclusion."""


@dataclass(frozen=True)
class InternalFact:
    """One thing a company knows about itself, owned by that company."""

    company_id: str
    kind: str
    statement: str
    standing: str = RECORDED
    provenance: str = LIVE
    value: Optional[float] = None
    unit: str = ""
    as_of: str = ""
    horizon_days: int = 0
    source: str = ""

    def __post_init__(self) -> None:
        if self.kind not in INTERNAL_KINDS:
            raise InternalRejected(f"unknown internal kind {self.kind!r}")
        if self.standing not in INTERNAL_STANDINGS:
            raise InternalRejected(f"unknown standing {self.standing!r}")
        if self.provenance not in PROVENANCES:
            raise InternalRejected(
                f"unknown provenance {self.provenance!r}: a record that "
                "cannot say whether it is real must not be stored")
        if not self.company_id:
            raise InternalRejected(
                "an internal fact needs an owner; a record with no company "
                "cannot be permission-checked and will be read by everyone")
        if not self.as_of:
            raise InternalRejected("an internal fact needs its date")

    @property
    def firm(self) -> bool:
        return self.standing in FIRM

    @property
    def synthetic(self) -> bool:
        return self.provenance == SYNTHETIC

    def as_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d.update(contract=CONTRACT, firm=self.firm, synthetic=self.synthetic)
        return d


def readable(facts: Sequence[InternalFact], *, for_company: str
             ) -> Tuple[InternalFact, ...]:
    """Only this company's own records. No aggregate, not even anonymous.

    An aggregate over internal facts is the shape a leak takes: "companies
    like yours are seeing pipeline weakness" is derived from named companies'
    private data, and with a small customer list it is re-identifiable. There
    is no function here that crosses companies, deliberately.
    """
    if not for_company:
        raise PermissionRefused(
            "internal facts cannot be read without naming whose they are")
    return tuple(f for f in facts if f.company_id == for_company)


def assert_no_synthetic(facts: Sequence[InternalFact], *, context: str
                        ) -> None:
    """Refuse a live conclusion built on invented data.

    Called at the join, not at the boundary. A synthetic record is harmless
    while it is labelled and sitting in a demo; it becomes a fabrication the
    moment it is combined with a real company's real economics and rendered
    as one finding.
    """
    bad = [f for f in facts if f.synthetic]
    if bad:
        raise SyntheticLeak(
            f"{context} would combine {len(bad)} synthetic record(s) with "
            "live economics; a demonstration and a finding are different "
            "objects and must not share a briefing")


# --- the demonstration company -------------------------------------------------

#: Deliberately named so nobody can mistake it for a registrant. Every fact
#: below is invented and every one is marked.
SYNTHETIC_COMPANY = "SYNTHETIC_NORTHWIND_INDUSTRIAL"


def synthetic_enterprise(as_of: str = "2026-08-08") -> List[InternalFact]:
    """One rich, deliberately conflicted internal picture.

    THE CONFLICTS ARE THE POINT. A demo company whose facts all agree proves
    that the pipeline runs; it proves nothing about reasoning. This one has a
    refinancing due into a rising cost of capital, a pipeline that is growing
    in value while slowing in conversion, a supplier it cannot easily replace,
    and a board assumption that contradicts its own sales data — so the
    architecture has to hold an argument rather than a summary.
    """
    def fact(kind, statement, standing=RECORDED, **kw):
        return InternalFact(company_id=SYNTHETIC_COMPANY, kind=kind,
                            statement=statement, standing=standing,
                            provenance=SYNTHETIC, as_of=as_of,
                            source="synthetic demonstration data", **kw)

    return [
        fact(DEBT, "term loan of 240m matures 2027-03; currently floating "
                   "over the benchmark with no hedge in place",
             value=240.0, unit="m USD"),
        fact(CASH, "unrestricted cash 61m, covering roughly five months of "
                   "operating outflow", value=61.0, unit="m USD"),
        fact(PIPELINE, "qualified pipeline 310m, up 14% on the quarter",
             standing=FORECAST, value=310.0, unit="m USD"),
        fact(PIPELINE, "median days from qualified to signed has moved from "
                       "74 to 103 over two quarters", standing=RECORDED,
             value=103.0, unit="days"),
        fact(CUSTOMER_CONCENTRATION,
             "the three largest customers are 41% of trailing revenue",
             value=41.0, unit="%"),
        fact(SUPPLIER_CONCENTRATION,
             "one supplier provides the drive assembly; requalifying a "
             "second is an 11-month programme", value=11.0, unit="months"),
        fact(PRICING, "list prices were raised 6% in March and realised "
                      "pricing rose 3.4%", value=3.4, unit="%"),
        fact(HIRING_PLAN, "42 open requisitions, of which 19 are in the "
                          "field sales organisation", standing=PLANNED,
             value=42.0, unit="people"),
        fact(CAPACITY, "the second line runs at 71% and cannot absorb a "
                       "step change without a shift pattern change",
             value=71.0, unit="%"),
        fact(STRATEGIC_DECISION,
             "the board approved a 90m capacity expansion, first draw "
             "scheduled for Q1 next year", standing=PLANNED, value=90.0,
             unit="m USD"),
        fact(REVENUE_PLAN, "the plan assumes 9% growth, unchanged since it "
                           "was set", standing=ASSUMED, value=9.0, unit="%"),
    ]


def combined_picture(external_thesis, facts: Sequence[InternalFact], *,
                     for_company: str) -> dict:
    """Where an external condition meets what the company knows about itself.

    Refuses to mix provenances. If the thesis is about a real company and the
    facts are synthetic, this raises rather than producing the impressive
    output — which is the whole reason the check lives at the join.
    """
    mine = readable(facts, for_company=for_company)
    if for_company != SYNTHETIC_COMPANY:
        assert_no_synthetic(mine, context="combined internal/external picture")
    firm = [f for f in mine if f.firm]
    soft = [f for f in mine if not f.firm]
    return {
        "contract": CONTRACT,
        "company": for_company,
        "provenance": SYNTHETIC if any(f.synthetic for f in mine) else LIVE,
        "external_claim": getattr(external_thesis, "claim", ""),
        "external_standing": getattr(external_thesis, "standing", ""),
        "internal_recorded": [f.statement for f in firm],
        "internal_softer": [f"{f.statement} [{f.standing}]" for f in soft],
        "kinds_held": sorted({f.kind for f in mine}),
        "note": ("a recorded internal figure is firm; a pipeline is a "
                 "forecast made by people paid to be optimistic about it, and "
                 "the two are never merged into one confidence"),
    }
