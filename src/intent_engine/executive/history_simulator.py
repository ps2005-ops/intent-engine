"""The historical strategy simulator: three lines, three epistemic states.

WHAT THIS REPLACES
------------------
History Rewind changed blocks of PROSE when you moved the slider. It respected
the vintage wall, it named the filings, and a reader learned almost nothing
from it, because the question an executive actually asks about the past is
comparative and quantitative:

    where did this company go, where did the record at the time imply it was
    going, and where could it have gone under a better-supported strategy?

Three lines, on one chart, on one axis. That is the product.

THE THREE LINES ARE NOT THE SAME KIND OF THING (§19)
----------------------------------------------------
    ACTUAL              OBSERVED.       Filed with the regulator.
    MARKET EXPECTATION  MODELED.        Built from information published on or
                                        before the vintage date. Not a
                                        retrieved consensus, and never called
                                        one.
    BETTER STRATEGY     COUNTERFACTUAL. What an alternative available at the
                                        time plausibly implied. Never a claim
                                        about what would have happened.

They are drawn differently, labelled differently, and carry different badges,
because a chart that renders an inference and an observation identically is
lying with a legend. `resolution.py` owns those badges so a surface can show
one but cannot invent one.

THE VINTAGE WALL, IN ARITHMETIC (§31)
-------------------------------------
Every fact carries `knowable_from` — the day it was FILED, not the day the
period ended. Fiscal 2022 revenue is a fact about 2022 and was not information
anybody had until February 2023. The expectation and counterfactual paths at
vintage T are computed from `series.knowable_by(T)` and from nothing else;
they are pure functions of that prefix. Leakage is therefore not a matter of
discipline: a later fact is not in the argument list.

WHY THE INDEX IS NOT SHARE PRICE (§20)
--------------------------------------
Share price is one business model's outcome measure wearing the costume of a
universal one. For Caterpillar it is a bet on the cycle; for a bank it is a
bet on rates; for a private company it does not exist. The index here is
STRATEGIC VALUE — revenue adjusted by the operating margin it was earned at —
which is composed from what every filer reports and which moves for both of
the reasons a strategy can work: selling more, and earning more on what is
sold. A revenue-only index would score growth bought at any cost as a success,
which is exactly the reading this product exists to argue against.
"""
from __future__ import annotations

import dataclasses
import datetime as _dt
import math
import statistics
from typing import Dict, List, Optional, Sequence, Tuple

from intent_engine.executive import resolution as R

CONTRACT = "history_simulator.v1"

ACTUAL = "ACTUAL"
EXPECTATION = "MARKET_EXPECTATION"
COUNTERFACTUAL = "BETTER_STRATEGY"

SERIES_KINDS = (ACTUAL, EXPECTATION, COUNTERFACTUAL)

#: The name each line carries on the chart, in the legend, and in the text
#: alternative. One string, so they cannot drift apart.
SERIES_TITLE = {
    ACTUAL: "Actual path",
    EXPECTATION: "Market expectation",
    COUNTERFACTUAL: "Better strategy",
}

SERIES_BASIS = {
    ACTUAL: R.OBSERVED,
    EXPECTATION: R.MODELED,
    COUNTERFACTUAL: R.COUNTERFACTUAL,
}

# ===========================================================================
# THE EXPECTATION MODEL'S ECONOMICS, STATED (§24)
# ===========================================================================
#
# Two numbers per business model class and a sentence saying why they are what
# they are. They are not fitted, not tuned per company and not secret: an
# expectation model whose assumptions a reader cannot inspect is a black box
# asserting the future, which is the thing this page exists to refuse.
#
#   anchor      the growth rate this kind of business reverts toward once its
#               current position is competed away
#   persistence how much of THIS YEAR's excess growth survives into next year
#
# The reversion is the economics: a subscription base renews, so an unusual
# year decays slowly; a commodity producer's unusual year was a price, and
# prices mean-revert fast because supply responds to them.
@dataclasses.dataclass(frozen=True)
class ClassEconomics:
    anchor: float
    persistence: float
    why: str
    #: What the market watches for this kind of business, in reader's words.
    watched: str


CLASS_ECONOMICS: Dict[str, ClassEconomics] = {
    "ADVERTISING_PLATFORM": ClassEconomics(
        0.12, 0.70,
        "an auction reprices continuously, so a good year is a year when "
        "more advertisers competed for the same attention — that competition "
        "persists while the attention does, and disappears with it",
        "engagement and impressions delivered, against the price per "
        "impression the auction cleared at"),
    "MULTI_ENGINE_PLATFORM": ClassEconomics(
        0.10, 0.72,
        "the engines do not turn together: a commerce engine mean-reverts "
        "with the consumer while an infrastructure engine compounds on "
        "contracts, so the consolidated line reverts more slowly than "
        "retail and faster than software",
        "which engine produced the operating profit, and whether the "
        "high-margin engine is still growing faster than the whole"),
    "SCALE_RETAIL": ClassEconomics(
        0.03, 0.60,
        "share won on price is held only while the price is held, and the "
        "cost advantage that funds it moves slowly — so an unusual year "
        "persists about as long as the buying advantage behind it",
        "comparable sales and traffic, against the gross margin the volume "
        "was bought at"),
    "SUBSCRIPTION_SOFTWARE": ClassEconomics(
        0.15, 0.78,
        "contracted revenue renews, so an unusual year is carried into the "
        "next one by the installed base rather than competed away in it",
        "net retention and the rate new contracted revenue is added"),
    "DESIGN_AND_MANUFACTURE": ClassEconomics(
        0.06, 0.55,
        "a design win holds for a product cycle and then has to be won "
        "again, so growth persists for about as long as the cycle does",
        "design wins, unit volumes and the pricing that survives the next "
        "negotiation"),
    "COMMODITY_PRODUCER": ClassEconomics(
        0.03, 0.28,
        "the price is set by the market rather than by the producer, and an "
        "unusual price calls out supply that removes it",
        "realised price against cash cost, and volume"),
    "BRANDED_CONSUMER": ClassEconomics(
        0.04, 0.62,
        "brand strength decays slowly in both directions, so neither a good "
        "year nor a bad one settles the question quickly",
        "volume, price and mix — and whether price was taken without losing "
        "volume"),
    "CONTRACTED_OR_RATE_BASE_ASSETS": ClassEconomics(
        0.04, 0.82,
        "revenue is contracted or rate-regulated, so it moves with the asset "
        "base and almost nothing else moves it quickly",
        "the asset base, the contracted term remaining, and the allowed "
        "return"),
    "BALANCE_SHEET_OR_NETWORK": ClassEconomics(
        0.04, 0.48,
        "the spread earned on the balance sheet follows the rate cycle, "
        "which turns on a horizon measured in quarters",
        "net interest margin, balance growth and credit costs"),
    "MANUFACTURE_AND_AFTERMARKET": ClassEconomics(
        0.04, 0.52,
        "new-equipment demand is cyclical while the aftermarket that follows "
        "it is not, so growth reverts part of the way and no further",
        "order backlog, dealer inventory and the aftermarket attach rate"),
    "PEOPLE_OR_ROUTE_BASED_SERVICES": ClassEconomics(
        0.05, 0.60,
        "capacity is people or routes and both take time to add or remove, "
        "so a demand change shows up in utilisation before it shows up in "
        "capacity",
        "utilisation, bill rate and the cost of the capacity carried"),
    "REGULATED_PRODUCT_OR_PROVIDER": ClassEconomics(
        0.04, 0.72,
        "an approved product sells for as long as its exclusivity lasts, so "
        "growth is set years earlier by the pipeline rather than by this "
        "year's execution",
        "the approved portfolio, what loses exclusivity next, and what the "
        "pipeline replaces it with"),
}

_UNCLASSIFIED = ClassEconomics(
    0.04, 0.55,
    "no business-model class was established for this company, so the "
    "reversion used is the all-company average rather than a class rule",
    "growth, and the margin it was earned at")


def economics_for(model_class: str) -> ClassEconomics:
    return CLASS_ECONOMICS.get(str(model_class or ""), _UNCLASSIFIED)


# ===========================================================================
# THE INDEX
# ===========================================================================
@dataclasses.dataclass(frozen=True)
class IndexPoint:
    year: int
    value: float                 #: the index, 100 at the first year
    raw: float                   #: the composed strategic value, in currency
    revenue: float
    margin: Optional[float]
    knowable_from: _dt.date

    def as_dict(self) -> dict:
        return {"year": self.year, "value": round(self.value, 2),
                "revenue": self.revenue,
                "margin": None if self.margin is None else round(
                    self.margin, 4),
                "knowable_from": self.knowable_from.isoformat()}


@dataclasses.dataclass(frozen=True)
class Index:
    points: Tuple[IndexPoint, ...] = ()
    metric: str = ""
    #: What the index is, said once, in the reader's words.
    definition: str = ""
    margin_included: bool = False
    note: str = ""

    @property
    def available(self) -> bool:
        return len(self.points) >= 3

    def knowable_by(self, cutoff: _dt.date) -> Tuple[IndexPoint, ...]:
        """THE WALL."""
        return tuple(p for p in self.points if p.knowable_from <= cutoff)

    def at(self, year: int) -> Optional[IndexPoint]:
        return next((p for p in self.points if p.year == year), None)

    def as_dict(self) -> dict:
        return {"metric": self.metric, "definition": self.definition,
                "margin_included": self.margin_included, "note": self.note,
                "points": [p.as_dict() for p in self.points]}


def build_value_index(revenue, operating=None, *,
                      model_class: str = "") -> Index:
    """The strategic value index from filed series. Never raises.

    STRATEGIC VALUE = revenue x (1 + operating margin).

    Chosen over revenue alone because a strategy that buys growth with losses
    and a strategy that earns the same growth are not the same strategy, and
    an index that cannot tell them apart cannot score a counterfactual about
    operating discipline. Chosen over operating income itself because that
    goes negative — Cloudflare's has been for its whole public life — and a
    ratio to a negative base is not an index, it is a sign error waiting to
    reach a chart.

    A year enters only when EVERY input it uses is knowable, and its
    `knowable_from` is the LATER of them.
    """
    from intent_engine.company_ingestion import xbrl
    rev_points = list(getattr(revenue, "points", ()) or ())
    if len(rev_points) < 3:
        return Index(note=(getattr(revenue, "note", "") or
                           "No multi-year filed series was retrieved."))
    op_by_year = {}
    if operating is not None and getattr(operating, "family", "") in (
            "operating_income", "earnings"):
        op_by_year = {f.year: f for f in getattr(operating, "points", ()) or ()}
    composed: List[Tuple[int, float, float, Optional[float], _dt.date]] = []
    for fact in rev_points:
        if fact.value <= 0:
            continue
        margin = None
        knowable = fact.knowable_from
        value = fact.value
        op = op_by_year.get(fact.year)
        if op is not None:
            margin = op.value / fact.value
            # A margin outside this range is a tagging accident, not a
            # business: seen where a filer tags a segment total against a
            # consolidated revenue. Drop the adjustment, keep the year.
            if -3.0 <= margin <= 1.5:
                # THE MULTIPLIER IS FLOORED, AND THE INDEX NEVER INVERTS.
                #
                # An early-stage company can lose MORE than its revenue —
                # Palantir's 2018 operating loss exceeded its top line — and
                # `revenue x (1 + margin)` then goes negative. A negative
                # base is not a small index, it is a sign error: every later
                # year would plot upside down and the whole chart would be
                # wrong in a way that looks like a finding. Measured: it
                # refused to build at all, which is how it was caught.
                #
                # A floor of 0.10 says what is true — a business burning more
                # than it earns is worth a fraction of its revenue on this
                # index, not a negative amount — and keeps the axis
                # monotonic in both growth and margin, which is the only
                # property the counterfactual needs from it.
                value = fact.value * max(0.10, 1.0 + margin)
                knowable = max(knowable, op.knowable_from)
            else:
                margin = None
        composed.append((fact.year, value, fact.value, margin, knowable))
    if len(composed) < 3:
        return Index(note=("Fewer than three financial years with a positive "
                           "top line were retrieved, which is not enough to "
                           "draw a path."))
    base = composed[0][1]
    if base <= 0:
        # Unreachable with the floor above, and kept because an index built
        # on a non-positive base is meaningless rather than merely odd — and
        # a future producer could reintroduce one.
        return Index(note="The first retrieved year has no positive base to "
                          "index from.")
    margin_included = any(row[3] is not None for row in composed)
    points = tuple(
        IndexPoint(year=year, value=100.0 * value / base, raw=value,
                   revenue=rev, margin=margin, knowable_from=knowable)
        for year, value, rev, margin, knowable in composed)
    metric = xbrl.index_meaning(model_class)
    definition = (
        f"100 is {points[0].year}. The line is {metric}"
        + (", adjusted up or down by the operating margin it was earned at — "
           "so growth bought with losses counts for less than the same growth "
           "earned profitably." if margin_included else
           ". No operating-margin series was filed for every year, so this is "
           "the top line unadjusted."))
    return Index(points=points, metric=metric, definition=definition,
                 margin_included=margin_included,
                 note=(f"{len(points)} financial years, "
                       f"{points[0].year}-{points[-1].year}."))


# ===========================================================================
# THE MARKET EXPECTATION MODEL (§23, §24)
# ===========================================================================
@dataclasses.dataclass(frozen=True)
class PathPoint:
    year: int
    value: float
    low: Optional[float] = None
    high: Optional[float] = None

    def as_dict(self) -> dict:
        return {"year": self.year, "value": round(self.value, 2),
                "low": None if self.low is None else round(self.low, 2),
                "high": None if self.high is None else round(self.high, 2)}


@dataclasses.dataclass(frozen=True)
class Path:
    """One line on the chart, and the epistemic state it is in."""
    kind: str
    title: str
    basis: str
    points: Tuple[PathPoint, ...] = ()
    #: What it was built from. Empty is a contract violation below OBSERVED.
    derivation: str = ""
    #: The reader-facing sentence for the legend and the date panel.
    statement: str = ""
    drivers: Tuple[str, ...] = ()

    @property
    def label(self) -> str:
        return R.LABEL.get(self.basis, self.basis)

    def as_dict(self) -> dict:
        return {"kind": self.kind, "title": self.title, "basis": self.basis,
                "label": self.label, "derivation": self.derivation,
                "statement": self.statement, "drivers": list(self.drivers),
                "points": [p.as_dict() for p in self.points]}


def _growth_rates(points: Sequence[IndexPoint]) -> List[float]:
    out = []
    for prev, nxt in zip(points, points[1:]):
        if prev.value > 0:
            out.append(nxt.value / prev.value - 1.0)
    return out


def _trailing(rates: Sequence[float], window: int = 3) -> float:
    """Compound average growth over the last `window` transitions."""
    tail = list(rates)[-window:]
    if not tail:
        return 0.0
    product = 1.0
    for rate in tail:
        product *= (1.0 + max(rate, -0.95))
    return product ** (1.0 / len(tail)) - 1.0


def expectation_path(index: Index, cutoff: _dt.date, horizon: int, *,
                     model_class: str = "", guidance: float = None,
                     macro: str = "") -> Optional[Path]:
    """What the record published by `cutoff` implied about the years after it.

    A DETERMINISTIC MODEL, NOT A FORECAST SERVICE. Trailing growth measured
    from the filed series, reverting toward the class anchor at the class
    persistence rate, with a band from the company's OWN realised volatility.
    Every input is knowable by `cutoff`; the function never sees a later
    point because the caller passes a wall-filtered index and the function
    reads nothing else.

    Returns None only when fewer than three years had been published by the
    cutoff — a state the caller must resolve on the ladder rather than print.
    """
    known = index.knowable_by(cutoff)
    if len(known) < 3:
        return None
    econ = economics_for(model_class)
    rates = _growth_rates(known)
    trailing = _trailing(rates)
    if guidance is not None:
        # Management's own guidance, where the run retrieved it, outranks the
        # trailing extrapolation: it is the company telling the market what to
        # expect, which is closer to an observation of expectation than any
        # model of it. Blended rather than substituted — guidance is a target
        # and the record of targets being met is what the trailing rate holds.
        trailing = 0.5 * trailing + 0.5 * guidance
    # VOLATILITY IS MEASURED ON LOG GROWTH, AND THE BAND WIDENS WITH sqrt(h).
    #
    # The first version added a per-year spread to the growth rate and
    # compounded it, so the band's width grew as h^1.5 rather than sqrt(h):
    # by year four Cloudflare's upper bound was an index of 7000 against a
    # central path of 1900, and the band was the only thing the chart showed.
    # Uncertainty that accumulates independently each year grows with the
    # square root of the horizon, so it is applied ONCE to the cumulative
    # path rather than folded into each step's rate.
    logs = [math.log(1.0 + max(rate, -0.95)) for rate in rates]
    volatility = (statistics.pstdev(logs) if len(logs) >= 3
                  else abs(math.log(1.0 + max(trailing, -0.95))) * 0.5)
    volatility = min(max(volatility, 0.02), 0.30)
    anchor, persistence = econ.anchor, econ.persistence
    last = known[-1]
    value = last.value
    excess = trailing - anchor
    points = [PathPoint(year=last.year, value=last.value, low=last.value,
                        high=last.value)]
    for step in range(1, horizon + 1):
        growth = anchor + excess * (persistence ** step)
        value *= (1.0 + growth)
        spread = math.exp(volatility * math.sqrt(step))
        points.append(PathPoint(year=last.year + step, value=value,
                                low=value / spread, high=value * spread))
    drivers = [f"trailing growth of {trailing * 100:.1f}% a year through "
               f"{last.year}",
               f"reversion toward {anchor * 100:.0f}% because {econ.why}",
               f"a band from this company's own realised volatility "
               f"({volatility * 100:.1f} points a year)"]
    if guidance is not None:
        drivers.insert(1, f"management's own guidance of "
                          f"{guidance * 100:.1f}%, blended with the record")
    if macro:
        drivers.append(macro)
    return Path(
        kind=EXPECTATION, title=SERIES_TITLE[EXPECTATION], basis=R.MODELED,
        points=tuple(points), drivers=tuple(drivers),
        derivation=(f"the {len(known)} financial years published on or before "
                    f"{cutoff.isoformat()}, and nothing filed after that date"),
        statement=(
            f"On the record as it stood in {cutoff.strftime('%B %Y')}, "
            f"continuing at {trailing * 100:.1f}% and reverting toward "
            f"{anchor * 100:.0f}% would have put the index near "
            f"{points[-1].value:.0f} by {points[-1].year}. This is modelled "
            f"from information published by that date — it is not a retrieved "
            f"consensus and no analyst said it."))


# ===========================================================================
# THE BETTER-STRATEGY COUNTERFACTUAL (§25, §26)
# ===========================================================================
@dataclasses.dataclass(frozen=True)
class Alternative:
    """The strategy the counterfactual line represents."""
    lever: str
    mechanism: str
    assumption: str
    benefit: str
    risk: str
    #: How much of the index it could move, per year, at the top of its range.
    magnitude: float = 0.0

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


#: What a better-supported alternative looks like FOR THIS KIND OF BUSINESS.
#:
#: A business-model rule, not a company rule (§62). The alternative is chosen
#: by what the class's economics make available, and its magnitude is bounded
#: by the same economics: a subscription business can convert growth into
#: operating leverage because its cost base is largely fixed, and a commodity
#: producer cannot, because its cost base is the ore.
CLASS_ALTERNATIVE: Dict[str, Alternative] = {
    "ADVERTISING_PLATFORM": Alternative(
        lever="raise auction density before raising inventory",
        mechanism=(
            "price per impression is set by how many advertisers bid for the "
            "same person, so bringing more bidders — smaller advertisers, "
            "new formats, better measurement — lifts the price on inventory "
            "that already exists, at no incremental cost of supply"),
        assumption=(
            "that engagement holds while monetisation rises, which is true "
            "when the extra load is priced into ranking and false when ad "
            "load is simply increased"),
        benefit="the same attention sold for more, with no capital spent",
        risk=(
            "pushing price or ad load past what the experience carries costs "
            "the engagement that produced the inventory, and attention lost "
            "to another product does not come back on a price cut"),
        magnitude=0.040),
    "MULTI_ENGINE_PLATFORM": Alternative(
        lever="fund the high-margin engine ahead of the consolidated line",
        mechanism=(
            "the engines earn very different margins on the same capital, so "
            "moving investment toward the infrastructure engine raises "
            "operating profit faster than the same investment spread across "
            "the whole — and the index here counts profit, not revenue"),
        assumption=(
            "that the commerce engine can hold its position without the "
            "capital being redirected, which is true where the customer "
            "relationship is already established and false in a land grab"),
        benefit="a materially higher margin on a similar revenue path",
        risk=(
            "starving the engine that produces the customer relationship "
            "eventually starves the one that monetises it, and the two are "
            "connected in ways consolidated statements do not show"),
        magnitude=0.050),
    "SCALE_RETAIL": Alternative(
        lever="take the cost advantage as turns rather than as margin",
        mechanism=(
            "return on capital in retail is margin times turns, so passing a "
            "buying advantage through as price buys traffic, and traffic "
            "raises turns on the same fixed store and logistics base"),
        assumption=(
            "that the cost advantage is structural and durable, which is "
            "true where it comes from scale and distribution and false where "
            "it came from a one-off buying cycle"),
        benefit=(
            "a lower margin earned more times a year, on the same invested "
            "capital"),
        risk=(
            "price passed through that the cost base cannot fund is a margin "
            "reduction that competitors match within a quarter, leaving the "
            "traffic unbought and the margin gone"),
        magnitude=0.025),
    "SUBSCRIPTION_SOFTWARE": Alternative(
        lever="convert growth into operating leverage a year earlier",
        mechanism=(
            "the cost base of a subscription business is largely fixed, so "
            "holding hiring flat while contracted revenue keeps compounding "
            "turns the same top line into a materially higher margin — and "
            "the index here counts the margin the growth was earned at"),
        assumption=(
            "that net retention holds while sales and marketing spend is held "
            "flat, which is true when the product is bought by the installed "
            "base and false when growth was being bought"),
        benefit="the same revenue path at a higher margin, compounding",
        risk=(
            "under-investing into a land-grab market hands the installed base "
            "to a competitor who kept spending, and the loss is permanent "
            "because switching costs work against the loser too"),
        magnitude=0.045),
    "MANUFACTURE_AND_AFTERMARKET": Alternative(
        lever="shift mix toward the aftermarket ahead of the cycle turning",
        mechanism=(
            "the installed base generates parts and service revenue that does "
            "not fall with new-equipment demand, so weighting the sales and "
            "service organisation toward it before the downturn holds revenue "
            "up exactly when the cycle is taking it down"),
        assumption=(
            "that the installed base is large enough for the aftermarket to "
            "matter, which is true for a long-lived capital good and false "
            "for a consumable"),
        benefit="a shallower trough, and a margin that improves through it "
                "because aftermarket work carries a higher one",
        risk=(
            "capacity built for new equipment is idle either way, and moving "
            "the commercial organisation early costs share when the cycle "
            "turns up sooner than expected"),
        magnitude=0.035),
    "COMMODITY_PRODUCER": Alternative(
        lever="hold capital discipline through the price upswing",
        mechanism=(
            "a producer cannot set the price, so the only durable lever is "
            "cash cost per unit and the timing of capital committed; capacity "
            "added at the top of a cycle arrives into the trough it helped "
            "create"),
        assumption=(
            "that the price signal at the time was cyclical rather than "
            "structural — the distinction the whole decision turns on"),
        benefit="the same volume at a lower cost base, and cash retained "
                "through the trough",
        risk=("a genuinely structural shift in demand punishes discipline: "
              "the capacity is not there when the higher price persists"),
        magnitude=0.030),
    "BALANCE_SHEET_OR_NETWORK": Alternative(
        lever="reposition the balance sheet ahead of the rate turn",
        mechanism=(
            "the spread earned is set by the duration of assets against the "
            "cost of funding, so shortening or lengthening duration before "
            "the turn changes the whole earnings path rather than one line "
            "of it"),
        assumption=(
            "that the rate path implied by forward markets at the time was "
            "approximately right about direction, which is a weaker claim "
            "than being right about level"),
        benefit="a materially higher net interest margin through the turn",
        risk=("duration is a two-sided bet and the loss is realised on the "
              "securities portfolio immediately, in public"),
        magnitude=0.040),
    "REGULATED_PRODUCT_OR_PROVIDER": Alternative(
        lever="fund the pipeline against the exclusivity cliff earlier",
        mechanism=(
            "revenue from an approved product is contractual until "
            "exclusivity lapses and then falls quickly; the only thing that "
            "replaces it is a product funded years before, so the decision "
            "and its consequence sit in different decades"),
        assumption=(
            "that the pipeline had a candidate worth accelerating, which is "
            "a clinical question the record at the time can answer"),
        benefit="a replacement on the market before the cliff rather than "
                "after it",
        risk=("development spend is expensed against a margin the market is "
              "already watching, and the candidate may fail anyway"),
        magnitude=0.030),
    "DESIGN_AND_MANUFACTURE": Alternative(
        lever="commit to the next process node ahead of the design cycle",
        mechanism=(
            "a design win locks revenue for the life of the product, and the "
            "win is decided by what is available when the customer designs — "
            "so capacity and process readiness a year early converts into "
            "revenue years later"),
        assumption="that the customer's design cycle timing was readable "
                   "from its own published roadmap",
        benefit="a share of the next product generation rather than the "
                "current one",
        risk="capacity committed to a node the market skips is a write-down",
        magnitude=0.040),
    "BRANDED_CONSUMER": Alternative(
        lever="take price earlier and defend volume with mix",
        mechanism=(
            "brand strength is the ability to raise price without losing "
            "volume; taking it early in an inflationary period holds real "
            "revenue, and taking it late means absorbing the cost increase "
            "in margin first"),
        assumption="that the brand's pricing power was intact, which the "
                   "prior year's volume response shows",
        benefit="real revenue held and margin protected through the cost "
                "spike",
        risk="price taken beyond what the brand supports loses volume "
             "permanently to private label",
        magnitude=0.030),
    "CONTRACTED_OR_RATE_BASE_ASSETS": Alternative(
        lever="accelerate the rate-base investment programme",
        mechanism=(
            "revenue is the allowed return on the asset base, so the only "
            "growth lever is the size of the base and the speed it is "
            "approved and built at"),
        assumption="that the regulator would allow the investment into the "
                   "base, which the prior rate case shows",
        benefit="a larger base earning the allowed return, compounding",
        risk="capital committed ahead of an approval that is refused or "
             "reduced is a return earned on nothing",
        magnitude=0.025),
    "PEOPLE_OR_ROUTE_BASED_SERVICES": Alternative(
        lever="hold capacity through the demand dip",
        mechanism=(
            "capacity is people and routes and both take a year to rebuild, "
            "so cutting into a dip trades a small saving now for the "
            "inability to serve the recovery"),
        assumption="that the dip was cyclical, which the order or booking "
                   "record at the time indicates",
        benefit="full participation in the recovery at existing cost",
        risk="a structural demand loss leaves the capacity carried against "
             "nothing",
        magnitude=0.035),
}

_UNCLASSIFIED_ALTERNATIVE = Alternative(
    lever="the opposite end of the lever actually pulled",
    mechanism=("no business-model class was established, so the alternative "
               "is stated structurally: the decision at this date had another "
               "side, and it was available on the same information"),
    assumption="that the choice made was a choice rather than a constraint",
    benefit="a different path, not a better-informed one",
    risk="an alternative argued without the class's economics is weaker than "
         "one argued with them",
    magnitude=0.020)


# ===========================================================================
# THE STATE THE COMPANY IS ACTUALLY IN (§62, §77, §78)
# ===========================================================================
#
# A business-model class picks the MECHANISM — what levers exist and why they
# work. It cannot pick which lever is live, because two companies of the same
# class are usually at different points in their own history. Measured:
# Cloudflare in 2019 was accelerating on a -37.6% margin and Shopify in 2019
# was decelerating on a -8.9% one, and both were handed the identical
# alternative because both are subscription software. Their date panels came
# out 94% identical — a template, from a rule that was right about the class
# and blind to the company.
#
# So the lever is chosen by OBSERVED trajectory and the mechanism by class.
# Both halves are general rules; neither mentions a company.
ACCELERATING, SLOWING = "ACCELERATING", "SLOWING"
WIDENING, NARROWING = "WIDENING", "NARROWING"


def observed_state(points: Sequence[IndexPoint]) -> Tuple[str, str]:
    """(growth direction, margin direction) from the filed record."""
    rates = _growth_rates(points)
    growth = ACCELERATING if len(rates) < 2 or rates[-1] >= rates[-2] \
        else SLOWING
    margins = [p.margin for p in points if p.margin is not None]
    margin = WIDENING if len(margins) < 2 or margins[-1] >= margins[-2] \
        else NARROWING
    return growth, margin


#: What the live decision IS, given where the company actually is. The
#: mechanism sentence still comes from the class; this replaces the lever,
#: the assumption it rests on and what would invalidate it.
STATE_ALTERNATIVE = {
    (ACCELERATING, NARROWING): (
        "convert the growth already won into operating leverage a year "
        "earlier",
        "that the growth was being bought rather than earned, which a "
        "widening gap between revenue growth and margin is evidence of",
        "pulling back into a market still being decided hands the position "
        "to whoever kept spending, and positions of this kind do not come "
        "back",
        1.0),
    (ACCELERATING, WIDENING): (
        "press the advantage: fund the next expansion while the cost base "
        "is still absorbing the current one",
        "that the cost base absorbing this year's growth will absorb next "
        "year's, which holds while the margin is widening and stops the "
        "moment it is not",
        "an expansion funded on the strength of one good year is a bet that "
        "the year was structural, and a cycle turning underneath it is "
        "exactly what makes it look structural",
        1.15),
    (SLOWING, NARROWING): (
        "stop paying for growth that has already stopped arriving, and take "
        "the cost out before the market prices the slowdown in",
        "that the slowdown is structural rather than a single weak period — "
        "the distinction the whole decision turns on, and one the next two "
        "quarters settle",
        "cutting into a cyclical trough removes the capacity needed to "
        "serve the recovery, and capacity of this kind takes a year to "
        "rebuild",
        0.85),
    (SLOWING, WIDENING): (
        "redeploy the margin now being earned into the next growth vector, "
        "before the current one finishes decaying",
        "that there is a next vector to fund, which the company's own "
        "investment and product disclosure at the time either shows or does "
        "not",
        "a business that has just learned to earn a margin is being asked "
        "to spend it again, and the market rewarded the margin",
        1.05),
}


def alternative_for(model_class: str, selection=None,
                    state: Optional[Tuple[str, str]] = None) -> Alternative:
    """The alternative: what kind of business it is, and where it currently is.

    AN ALTERNATIVE IS A QUADRUPLE, AND IT IS AUTHORED AS ONE.

    A first version preferred a scenario the run had produced, on the
    reasoning that a company-specific fragment beats a class default. What
    reached the deployed page was:

        BETTER ALTERNATIVE       A pricing action.
        WHY IT MIGHT HAVE WORKED Operating leverage reads HIGH, so more of
                                 the gain reaches margin than revenue.
        WHAT COULD HAVE INVALIDATED IT
                                 Cutting into a cyclical trough removes the
                                 capacity needed to serve the recovery.

    The lever is about price, the risk is about capacity, and the mechanism
    prints an internal enum. Each field was individually defensible and the
    three together argue about different decisions — because they came from
    different producers and nothing required them to agree.

    So the quadruple is taken WHOLE. The class supplies the mechanism, which
    is its economics; the observed trajectory supplies the lever, the
    assumption and the risk, which is where the company actually is. Both
    are general rules and neither names a company. A run scenario is a
    fragment and the product shows it elsewhere, in a section built for
    fragments.
    """
    base = CLASS_ALTERNATIVE.get(str(model_class or ""),
                                 _UNCLASSIFIED_ALTERNATIVE)
    if state is not None and state in STATE_ALTERNATIVE:
        lever, assumption, risk, weight = STATE_ALTERNATIVE[state]
        base = dataclasses.replace(
            base, lever=lever, assumption=assumption, risk=risk,
            magnitude=round(base.magnitude * weight, 4))
    return base


def counterfactual_path(expectation: Optional[Path], alternative: Alternative,
                        *, model_class: str = "") -> Optional[Path]:
    """Where the better-supported alternative plausibly led, from the same date.

    Built ON the expectation path rather than beside it, deliberately: the
    counterfactual is not a different view of the future, it is the SAME view
    with one decision changed. Expressing it as an increment to the modelled
    path is what makes the gap between the two lines readable as the value of
    the decision — which is the only number on this chart an executive can
    actually use.

    The increment ramps rather than steps, because a strategy takes effect
    through a mechanism and mechanisms have a period. It is bounded by the
    class magnitude and never compounds beyond the horizon it was argued for.
    """
    if expectation is None or not expectation.points:
        return None
    econ = economics_for(model_class)
    anchor = expectation.points[0]
    points = [PathPoint(year=anchor.year, value=anchor.value)]
    uplift = 1.0
    for step, base in enumerate(expectation.points[1:], start=1):
        # Ramp in over three years: a strategy changed today does not show
        # its full effect this year, and one that claims to is not a
        # mechanism, it is a wish.
        ramp = min(step / 3.0, 1.0)
        uplift *= (1.0 + alternative.magnitude * ramp)
        points.append(PathPoint(
            year=base.year, value=base.value * uplift,
            low=base.value,
            high=(base.high or base.value) * uplift))
    gain = (points[-1].value / expectation.points[-1].value - 1.0) * 100
    return Path(
        kind=COUNTERFACTUAL, title=SERIES_TITLE[COUNTERFACTUAL],
        basis=R.COUNTERFACTUAL, points=tuple(points),
        derivation=(f"the modelled expectation path, with one decision "
                    f"changed: {alternative.lever}"),
        drivers=(f"mechanism — {alternative.mechanism}",
                 f"assumption — {alternative.assumption}",
                 f"expected benefit — {alternative.benefit}",
                 f"principal risk — {alternative.risk}"),
        statement=(
            f"The alternative available on the same information — "
            f"{_lower(alternative.lever)} — puts the index about "
            f"{gain:.0f}% above the expected path by {points[-1].year} on "
            f"that model. A bounded counterfactual, not a claim about what "
            f"would have happened: it holds only while "
            f"{_lower(alternative.assumption)}"))


# ===========================================================================
# ONE VINTAGE, ASSEMBLED
# ===========================================================================
@dataclasses.dataclass(frozen=True)
class Card:
    """§28. One of the date panel's readings."""
    key: str
    title: str
    body: str
    basis: str = R.OBSERVED

    @property
    def label(self) -> str:
        return R.LABEL.get(self.basis, self.basis)

    def as_dict(self) -> dict:
        return {"key": self.key, "title": self.title, "body": self.body,
                "basis": self.basis, "label": self.label}


@dataclasses.dataclass(frozen=True)
class SimVintage:
    """One selectable date: three lines and the cards that explain them."""
    date: str
    year: int
    label: str
    actual: Path
    expectation: Optional[Path]
    counterfactual: Optional[Path]
    cards: Tuple[Card, ...] = ()
    #: The ladder result for the expectation, whatever rung it reached.
    expectation_resolution: Optional[R.Resolved] = None

    @property
    def paths(self) -> Tuple[Path, ...]:
        return tuple(p for p in (self.actual, self.expectation,
                                 self.counterfactual) if p is not None)

    def as_dict(self) -> dict:
        return {"date": self.date, "year": self.year, "label": self.label,
                "paths": [p.as_dict() for p in self.paths],
                "cards": [c.as_dict() for c in self.cards],
                "expectation_resolution": (
                    self.expectation_resolution.as_dict()
                    if self.expectation_resolution else None)}


@dataclasses.dataclass(frozen=True)
class Simulation:
    company: str
    contract: str = CONTRACT
    index: Index = dataclasses.field(default_factory=Index)
    vintages: Tuple[SimVintage, ...] = ()
    model_class: str = ""
    #: Why the simulation is as rich or as thin as it is. Never silent.
    coverage: str = ""
    #: When there is no chart: the strategic alternative anyway (§16 rung D).
    bounded_alternative: Optional[Alternative] = None
    bounded_cards: Tuple[Card, ...] = ()
    #: The ladder result when there is no chart at all — rung F, with a
    #: measurement that would produce one.
    fallback: Optional[R.Resolved] = None

    @property
    def available(self) -> bool:
        return bool(self.vintages)

    def vintage(self, year: int) -> Optional[SimVintage]:
        return next((v for v in self.vintages if v.year == year), None)

    def as_dict(self) -> dict:
        return {"contract": self.contract, "company": self.company,
                "model_class": self.model_class, "coverage": self.coverage,
                "bounded_cards": [c.as_dict() for c in self.bounded_cards],
                "index": self.index.as_dict(),
                "vintages": [v.as_dict() for v in self.vintages],
                "fallback": (self.fallback.as_dict() if self.fallback
                             else None)}


def _actual_path(index: Index) -> Path:
    return Path(
        kind=ACTUAL, title=SERIES_TITLE[ACTUAL], basis=R.OBSERVED,
        points=tuple(PathPoint(year=p.year, value=p.value)
                     for p in index.points),
        derivation="",
        statement=("Filed with the regulator. Each point is a full financial "
                   "year as the company reported it."))


def _cards(company, profile, index, vintage_year, cutoff, expectation,
           counterfactual, alternative, econ) -> Tuple[Card, ...]:
    known = index.knowable_by(cutoff)
    later = [p for p in index.points if p.knowable_from > cutoff]
    rates = _growth_rates(known)
    out: List[Card] = []

    if known:
        last = known[-1]
        trend = (f"growing {rates[-1] * 100:.1f}% a year" if rates and
                 rates[-1] >= 0 else
                 (f"shrinking {abs(rates[-1]) * 100:.1f}% a year" if rates
                  else "on its first published year"))
        margin_clause = ""
        if last.margin is not None:
            margin_clause = (f", earned at a {last.margin * 100:.1f}% "
                             f"operating margin")
        out.append(Card(
            "true", "What was true then",
            f"By {cutoff.strftime('%B %Y')} the record showed "
            f"{len(known)} published financial year(s), the most recent "
            f"{last.year} at an index of {last.value:.0f}{margin_clause} — "
            f"{trend}. That is what a decision at this date had to work from.",
            R.OBSERVED))

    levers = tuple(getattr(profile, "primary_management_levers", ()) or ())
    if known:
        # WHAT IT DID IS READ OFF THE NUMBERS, NOT ASSERTED.
        #
        # The first version said "it stayed on the course the filings
        # describe" for every company at every date, which is a sentence that
        # survives being wrong. Growth and margin moving in opposite
        # directions IS the choice — a business adding capacity shows
        # accelerating revenue against a falling margin, and one taking
        # leverage shows the reverse. That is inference from filed figures,
        # and it is stated as such.
        margins = [p.margin for p in known if p.margin is not None]
        chose = ""
        if len(rates) >= 2:
            faster = rates[-1] > rates[-2]
            if len(margins) >= 2:
                fatter = margins[-1] > margins[-2]
                chose = {
                    (True, False): "revenue growth accelerated while the "
                                   "operating margin fell — the shape of a "
                                   "business buying growth",
                    (True, True): "revenue growth accelerated and the margin "
                                  "widened with it — growth the cost base was "
                                  "absorbing",
                    (False, True): "revenue growth slowed while the margin "
                                   "widened — the shape of a business taking "
                                   "operating leverage",
                    (False, False): "revenue growth slowed and the margin "
                                    "narrowed with it — cost was not coming "
                                    "out as fast as demand",
                }[(faster, fatter)]
            else:
                chose = ("revenue growth accelerated" if faster else
                         "revenue growth slowed")
        body = (f"The choice is legible in the figures it filed: {chose}."
                if chose else
                "Only one published year precedes this date, so what it was "
                "choosing between is not yet legible in the figures.")
        if levers:
            body += (f" For this kind of business the levers available were "
                     f"{_join([_lower(l) for l in levers[:3]])}.")
        out.append(Card("did", "What management did", body, R.OBSERVED))

    if expectation is not None:
        out.append(Card("expected", "What the market expected",
                        expectation.statement, R.MODELED))
    if later:
        realised = later[-1]
        clause = ""
        if expectation is not None:
            projected = next((p for p in expectation.points
                              if p.year == realised.year), None)
            if projected is not None and projected.value > 0:
                miss = (realised.value / projected.value - 1.0) * 100
                direction = "ahead of" if miss >= 0 else "behind"
                clause = (f" — {abs(miss):.0f}% {direction} what the record at "
                          f"the time implied")
        out.append(Card(
            "happened", "What happened",
            f"By {realised.year} the index reached {realised.value:.0f}"
            f"{clause}. This card is the only one on this page built from "
            f"material filed after {cutoff.strftime('%B %Y')}.", R.OBSERVED))

    out.append(Card("alternative", "Better alternative",
                    f"{_capitalise(alternative.lever)}. "
                    f"{_capitalise(alternative.benefit)}.",
                    R.COUNTERFACTUAL))
    out.append(Card("why", "Why it might have worked",
                    _capitalise(alternative.mechanism) + ".", R.COUNTERFACTUAL))
    out.append(Card(
        "invalidate", "What could have invalidated it",
        f"{_capitalise(alternative.risk)}. The assumption it rests on is "
        f"{_lower(alternative.assumption)} — and that was checkable at the "
        f"time, which is what makes this an argument rather than a "
        f"preference.", R.COUNTERFACTUAL))
    return tuple(out)


def build(*, company: str, cik: str = "", profile=None, selection=None,
          revenue=None, operating=None, max_vintages: int = 6,
          transport=None, resolver=None) -> Simulation:
    """The simulation. Never raises; an empty one climbs the ladder instead.

    `revenue`/`operating` are injectable so the whole model is testable with
    no network, which is also how the zero-credential proof exercises it.
    """
    model_class = str(getattr(profile, "business_model_class", "") or "")
    if revenue is None:
        from intent_engine.company_ingestion import xbrl
        revenue, supporting = xbrl.index_series(
            cik, model_class, transport=transport, resolver=resolver)
        if operating is None:
            operating = supporting[0] if supporting else None
    index = build_value_index(revenue, operating,
                              model_class=model_class)
    econ = economics_for(model_class)
    if not index.available:
        # NO CHART IS NOT NO ANALYSIS (§16 rung D, §38).
        #
        # A private company has no filed series and never will have one, so
        # the three lines cannot be drawn — and the strategic question the
        # page exists to raise is unchanged. The alternative available to a
        # business of this kind, the mechanism that would make it work and
        # what would invalidate it are all class economics, none of which
        # needs a number. They are carried here, labelled COUNTERFACTUAL,
        # with no path attached, because a counterfactual without a
        # magnitude is an argument and a magnitude without a series would be
        # a fabrication.
        alternative = alternative_for(model_class, selection)
        econ = economics_for(model_class)
        return Simulation(
            company=company, model_class=model_class,
            coverage=(getattr(revenue, "note", "") or index.note),
            bounded_alternative=alternative,
            bounded_cards=(
                Card("alternative", "The alternative on the table",
                     f"{_capitalise(alternative.lever)}. "
                     f"{_capitalise(alternative.benefit)}.",
                     R.COUNTERFACTUAL),
                Card("why", "Why it might work",
                     _capitalise(alternative.mechanism) + ".",
                     R.COUNTERFACTUAL),
                Card("invalidate", "What could have invalidated it",
                     f"{_capitalise(alternative.risk)}. It rests on "
                     f"{_lower(alternative.assumption)}.", R.COUNTERFACTUAL),
                Card("watched", "What the market watches for this business",
                     f"{_capitalise(econ.watched)}. Those are the measures "
                     f"a business of this kind is judged on, and each one "
                     f"turns a bounded reading here into a measured one.",
                     R.MODELED)),
            fallback=R.unresolved(
                f"How has {company} actually performed, year by year?",
                why=(index.note or "no multi-year filed series was retrieved "
                                   "for this company"),
                next_measurement=(
                    "three or more years of the company's own reported "
                    "revenue and operating result — audited accounts, an "
                    "investor update, or a data room extract are all "
                    "sufficient, and any one of them turns this page into a "
                    "path"),
                decision_relevance=(
                    "whether the strategy on the table is a change of "
                    "direction or a continuation of one already working")))

    actual = _actual_path(index)
    years = [p.year for p in index.points]
    # The dates worth stopping at: spread across the span, and never one so
    # early that fewer than three years had been published by it (the
    # expectation model has nothing to work from there, and a vintage whose
    # centre panel is empty is the defect this rebuild exists to remove).
    # A VINTAGE IS A PUBLICATION DATE, AND ITS YEAR IS THE LAST YEAR KNOWN BY
    # IT — not the year of the point that produced the date.
    #
    # A first annual report publishes three years at once under one filing
    # date, so the vintage generated by the 2017 point already knows 2019.
    # Labelling it 2017 put the "decision point" marker two years behind the
    # knowledge the panel beside it was built from, and the expectation line
    # started in a year the chart said had not happened yet. Caught in a
    # browser, invisible in the data.
    by_cutoff: Dict[_dt.date, int] = {}
    for point in index.points:
        known = index.knowable_by(point.knowable_from)
        if len(known) >= 3:
            by_cutoff[point.knowable_from] = known[-1].year
    eligible = sorted(by_cutoff.items())
    if len(eligible) > max_vintages:
        step = len(eligible) / max_vintages
        eligible = [eligible[int(i * step)] for i in range(max_vintages)]
    vintages: List[SimVintage] = []
    for cutoff, vintage_year in eligible:
        # THE ALTERNATIVE IS CHOSEN PER VINTAGE, NOT PER COMPANY.
        #
        # A company accelerating in 2019 and decelerating in 2023 faced two
        # different decisions, and a page that offers the same alternative at
        # both dates is a page where moving the slider changes the numbers
        # and not the argument.
        alternative = alternative_for(
            model_class, selection,
            state=observed_state(index.knowable_by(cutoff)))
        # Never project past the last year the company has actually filed:
        # an expectation line running into a year with no outcome beside it
        # is a forecast, and this page is not a forecasting product.
        horizon = max(years[-1] - vintage_year, 1)
        expectation = expectation_path(index, cutoff, horizon,
                                       model_class=model_class)
        counter = counterfactual_path(expectation, alternative,
                                      model_class=model_class)
        if expectation is not None:
            expectation_res = R.modeled(
                f"What did the market expect of {company} in {vintage_year}?",
                expectation.statement,
                derivation=expectation.derivation,
                drivers=expectation.drivers,
                decision_relevance=("whether the result that followed beat "
                                    "the bar the record had already set"))
        else:
            expectation_res = R.unresolved(
                f"What did the market expect of {company} in {vintage_year}?",
                why=("fewer than three financial years had been published by "
                     "this date, so there is no trailing record to extrapolate"),
                next_measurement=("one more published financial year before "
                                  "this date"),
                decision_relevance="how ambitious the plan of the day was")
        vintages.append(SimVintage(
            date=cutoff.isoformat(), year=vintage_year,
            label=f"{vintage_year} — as the record stood in "
                  f"{cutoff.strftime('%B %Y')}",
            actual=actual, expectation=expectation, counterfactual=counter,
            expectation_resolution=expectation_res,
            cards=_cards(company, profile, index, vintage_year, cutoff,
                         expectation, counter, alternative, econ)))
    return Simulation(
        company=company, index=index, vintages=tuple(vintages),
        model_class=model_class,
        coverage=(
            f"{len(index.points)} filed financial years, {years[0]} to "
            f"{years[-1]}, and {len(vintages)} selectable date(s). A date is "
            f"selectable once three years had been published by it, because "
            f"below that there is no trailing record for the expectation to "
            f"be built from."))


def present_expectation(sim: Simulation, *, company: str = "",
                        horizon: int = 3, today: Optional[_dt.date] = None
                        ) -> Optional[R.Resolved]:
    """§15, §23. What the record as it stands NOW implies about the next years.

    THE DEFECT THIS EXISTS FOR. The Full Analysis said, of a company whose
    every annual report is public:

        "No market snapshot has been published for this company, so there is
         no read on what investors currently expect."

    That is true about our price feed and useless to a reader, who asked what
    the market expects and was told which of our integrations is switched off.
    The same model that draws the expectation line at a historical vintage
    draws it at today's date, from the same filed series, and the answer is a
    real one: this is what the published record implies, and it is a bar the
    company's next result can be measured against.

    It is a MODELLED expectation and is labelled one everywhere it appears. It
    is not a consensus, no analyst said it, and this function will not produce
    anything when there is no filed series to build it from — the absence of
    data is still an absence, and rung F still exists.
    """
    if not sim.index.available:
        return None
    cutoff = today or _dt.date.today()
    expectation = expectation_path(sim.index, cutoff, horizon,
                                   model_class=sim.model_class)
    if expectation is None:
        return None
    known = sim.index.knowable_by(cutoff)
    last, target = known[-1], expectation.points[-1]
    implied = (target.value / last.value) ** (1.0 / max(horizon, 1)) - 1.0
    econ = economics_for(sim.model_class)
    name = company or sim.company
    return R.modeled(
        f"What does the published record imply the market should expect of "
        f"{name}?",
        (f"On {name}'s own filed results through {last.year}, the bar its "
         f"next few years have to clear is about {implied * 100:.0f}% a year "
         f"on the strategic value index — growth continuing from where it is "
         f"and reverting toward {econ.anchor * 100:.0f}%, which is what this "
         f"kind of business settles at once its current position is competed "
         f"away. By {target.year} that puts it between "
         f"{(target.low or last.value) / last.value:.2f}x and "
         f"{(target.high or last.value) / last.value:.2f}x its {last.year} "
         f"level, which is the range its own year-to-year variation has "
         f"produced. This is modelled from the public record, not a retrieved "
         f"analyst consensus — no analyst said it, and it is stated so that "
         f"the next result has something to be measured against rather than "
         f"being read on its own."),
        derivation=(f"{len(known)} filed financial years through "
                    f"{last.year}, reverting toward the "
                    f"{econ.anchor * 100:.0f}% anchor for this business model"),
        value=round(implied, 4), low=round(target.low or 0.0, 1),
        high=round(target.high or 0.0, 1),
        drivers=expectation.drivers,
        decision_relevance=("whether the strategy on the table is expected to "
                            "beat the path the company is already on"))


# --- small helpers ---------------------------------------------------------
def _lower(text: str) -> str:
    flat = " ".join(str(text or "").split())
    if not flat:
        return ""
    head = flat.split(" ", 1)[0]
    if head.isupper() or (len(head) > 1 and head[1:].lower() != head[1:]):
        return flat
    return flat[0].lower() + flat[1:]


def _capitalise(text: str) -> str:
    flat = " ".join(str(text or "").split())
    return flat[0].upper() + flat[1:] if flat else ""


def _join(items) -> str:
    items = [i for i in (items or ()) if i]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]
