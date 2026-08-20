"""The one bounded strategic read every customer-facing surface inherits.

THE DEFECT THIS CLOSES
----------------------
Live on `377ea63`, the first thing a CEO saw for Cloudflare was:

    "No strategic reading of Cloudflare, Inc. cleared the evidence bar, so
     none is asserted here."

or, worse, a reading that HAD cleared it and was about a different kind of
company entirely:

    "fixed cost is committed in large increments against demand that arrives
     in small ones ... take-or-pay terms ... capacity is being added to
     replace ageing lines"

for a business whose own X-Ray, two clicks away, correctly reads "recurring
software subscription ... HIGH operating leverage ... delivery cost rises far
more slowly than contracted revenue".

Both failures have the same cause: the run's own reasoning decided ALONE
whether there was a strategy to describe, from the text it happened to
retrieve, with no access to what kind of business it was reading about.
`executive.contract` fixed the CONTRADICTION between surfaces. It did not fix
what the surfaces then say, because both possible answers were bad: refuse, or
assert an industrial mechanism about a software network.

WHAT THIS MODULE IS
-------------------
A third answer, and the one the product is actually for. Given an
identifiable operating company and enough factual material to reason about
its business model, products, customers, growth, economics and competitive
position, it always produces a BOUNDED STRATEGIC READ:

    what the company is, in this system's words rather than the company's
    what it is really trying to do
    the economic mechanism that decides whether that works
    what a competitor does about it
    the decision management actually faces
    the bounded action available now
    the experiment that would resolve the rest

WHAT IT MAY NOT DO
------------------
Lower the evidence bar. Nothing here invents a market share, a retention
rate, a customer count, a unit economic, a competitor action or a revenue
effect. Every sentence carries one of four standings --

    OBSERVED             this run read it in a source
    STRONGLY_INFERRED    the business model determines it and the record
                         agrees
    BOUNDED_INFERENCE    the business model implies it; the record neither
                         confirms nor contradicts
    UNMEASURED           named because it matters and is not established

-- and a surface may render whatever it likes as long as it does not present
BOUNDED_INFERENCE as OBSERVED. Missing independent evidence reduces
confidence, causal strength and measured magnitude. It does not delete the
synthesis, the recommendation, the scenario or the experiment.

THE LADDER (§6). A weak claim at level 5 may not collapse levels 1-4. The
seven levels are produced independently and each states its own standing, so
"we cannot size the effect" costs the size and nothing else.

NO MODEL CALL. Every field below is composed from `company_profile`,
`analysis_selection`, the run's own decision, and counts of what was
retrieved. REQUIRED_ANTHROPIC_CALLS = 0 is a property of this file, not a
configuration of it.
"""
from __future__ import annotations

import dataclasses
import re
from typing import Optional, Sequence, Tuple

from intent_engine.executive.analysis_selection import (AnalysisSelection,
                                                        RecordFacts, select)
from intent_engine.executive.company_profile import (UNKNOWN,
                                                     CompanyIntelligenceProfile,
                                                     PROFILE_AVAILABLE,
                                                     PROFILE_SPARSE)

CONTRACT = "strategic_read.v1"

# --- how strongly one sentence is held (§5) ---------------------------------
OBSERVED = "OBSERVED"
STRONGLY_INFERRED = "STRONGLY_INFERRED"
BOUNDED_INFERENCE = "BOUNDED_INFERENCE"
UNMEASURED = "UNMEASURED"

STANDINGS = (OBSERVED, STRONGLY_INFERRED, BOUNDED_INFERENCE, UNMEASURED)

#: How each standing is said to a reader. The enum never reaches a page.
STANDING_PROSE = {
    OBSERVED: "read directly in a source",
    STRONGLY_INFERRED: "follows from how this business works, and the record "
                       "agrees",
    BOUNDED_INFERENCE: "follows from how this business works; the record "
                       "neither confirms nor contradicts it",
    UNMEASURED: "not established here",
}

# --- how strongly the whole read is held ------------------------------------
#: The record supports the reading directly.
READ_SUPPORTED = "SUPPORTED"
#: The business model and the record support the DIRECTION; the size is not
#: established. This is the ordinary state for a public company read from
#: public sources, and it is a real answer.
READ_BOUNDED = "BOUNDED"
#: Not enough is known about what kind of business this is to reason about it.
#: The only state in which the product does not put a strategy forward -- and
#: it is a statement about identification, never about evidence volume.
READ_UNIDENTIFIED = "UNIDENTIFIED"

#: Value of resolving the open parameter (§38). Bands, never a fabricated
#: dollar figure.
VOI_HIGH, VOI_MEDIUM, VOI_LOW, VOI_UNMEASURABLE = (
    "HIGH", "MEDIUM", "LOW", "UNMEASURABLE")

#: How likely a competitor is to respond. Words, not a fake probability --
#: QRE numbers require a payoff parameterisation nothing here observes.
LIKELIHOOD = ("LOW", "MEDIUM", "HIGH")


def _clean(text) -> str:
    """One line, no stray whitespace, no trailing ellipsis.

    The ellipsis strip is not cosmetic. A retrieval excerpt that ends "...
    services to businesses of all sizes and in all" was the FIRST SENTENCE a
    reader saw under the company name; product prose that trails off is
    indistinguishable from a product that stopped working.

    A trailing FULL STOP is left alone. Stripping it renamed the subject:
    "Cloudflare, Inc." became "Cloudflare, Inc" in the first line of the
    product, which is a wrong-company signal in a product whose first promise
    is that it identified the right one.
    """
    flat = " ".join(str(text or "").split())
    while flat.endswith(("…", "...")):
        flat = flat[:-1] if flat.endswith("…") else flat[:-3]
        flat = flat.rstrip(" ,;:")
    return flat.strip()


def _sentence(text) -> str:
    """`_clean`, ended properly, and never ended twice."""
    flat = _clean(text)
    if not flat:
        return ""
    if flat[-1] in ".?!":
        return flat
    return flat.rstrip(",;:—- ") + "."


def _lower_first(text: str) -> str:
    flat = _clean(text)
    if not flat:
        return ""
    # Never lowercase a proper noun or an initialism.
    head = flat.split(" ", 1)[0]
    if head.isupper() or (len(head) > 1 and head[1:].lower() != head[1:]):
        return flat
    return flat[0].lower() + flat[1:]


def _article(word: str) -> str:
    """"a" or "an". "a industrial business" in the first line of the product
    is the kind of error a reader generalises from."""
    return "an" if _clean(word)[:1].lower() in "aeiou" else "a"


#: Sentences the run's own reasoning produces when IT found nothing. They are
#: honest about that pass and they are not a strategic read, so they may not
#: be carried into one. Composing the read from them is how a refusal walked
#: back onto slide 1 wearing the bounded read's headings: "Confidence:
#: BOUNDED ... What is still open: what X has published is not enough to read
#: a strategy from."
_REFUSAL_SHAPED = re.compile(
    r"not enough to read a strategy"
    r"|puts no decision forward"
    r"|no decision is put forward"
    r"|cleared the evidence bar"
    r"|did not carry enough"
    r"|no curated transition pattern matched"
    r"|no reading is put forward", re.I)


def _usable(text) -> str:
    """The text, unless it is the run declining to reach a conclusion."""
    flat = _clean(text)
    return "" if not flat or _REFUSAL_SHAPED.search(flat) else flat


def _known(value) -> bool:
    return bool(value) and str(value) != UNKNOWN


def _first_clause(text: str) -> str:
    """The part of a profile line before its explanatory colon.

    Profile economics read "HIGH: delivery cost rises far more slowly than
    contracted revenue" -- the enum before the colon is internal vocabulary
    (§73) and the clause after it is the sentence a reader wants.
    """
    flat = _clean(text)
    if ":" in flat:
        head, _, tail = flat.partition(":")
        if head.strip().isupper() and tail.strip():
            return _clean(tail)
    return flat


def _enum_word(text: str) -> str:
    """The enum in front of a profile line, in ordinary words."""
    flat = _clean(text)
    head = flat.partition(":")[0].strip()
    return head.lower() if head.isupper() else ""


@dataclasses.dataclass(frozen=True)
class Statement:
    """One claim, and how strongly it is held."""
    text: str
    standing: str = BOUNDED_INFERENCE
    basis: str = ""

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class Mechanism:
    """One microeconomic mechanism this business actually runs on (§9)."""
    name: str
    how_it_works: str
    what_it_decides: str
    standing: str = BOUNDED_INFERENCE

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class MetricExpectation:
    """A metric this business model is judged on, and whether we have it."""
    metric: str
    why_it_matters: str
    state: str          #: OBSERVED | UNMEASURED
    observed_value: str = ""

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class CompetitorRead:
    """One rival, and what it does about the move under consideration."""
    name: str
    why_a_rival: str
    exposure: str
    likely_response: str
    response_likelihood: str
    counter_move: str
    signal_to_watch: str
    level: str = "L1"
    #: WHERE THE CLAIM CAME FROM, carried from the ladder.
    #
    # This field did not exist, and its absence made a repair inert: the
    # opening sentence tried to exclude rung 9 with `getattr(c, "rung", "")`
    # and silently kept everything, because `_level4` returns CompetitorRead
    # and the rung stopped at `Rival`. Provenance that dies at a projection
    # boundary cannot govern how the claim is rendered.
    rung: str = ""
    #: WHAT KIND OF ALTERNATIVE THIS IS, carried from the ladder for the same
    #: reason `rung` is: the opening sentence has to say "contested directly
    #: by" of a rival and something else of a substitute, and a projection
    #: that drops the kind leaves the renderer with one sentence for all of
    #: them. Meta's read is an in-house build, a rival surface and an
    #: automation threat, and calling all three "contested most directly by"
    #: is false about two.
    kind: str = ""

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class BoundedAction:
    """The refusal → bounded-action bridge (§7, §38).

    Every field is required. A bridge missing its kill switch is a
    recommendation with no way to stop, which is worse than no recommendation.
    """
    causal_confidence: str
    what_is_known: str
    what_remains_unknown: str
    why_it_matters: str
    action_now: str
    minimum_viable_experiment: str
    kill_switch: str
    falsifier: str
    voi_band: str = VOI_MEDIUM
    guardrail: str = ""

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class Chapter:
    """One block of the company's story (§25, §39)."""
    key: str
    title: str
    body: str
    standing: str = BOUNDED_INFERENCE


@dataclasses.dataclass(frozen=True)
class StrategicRead:
    """The canonical read. One per run; every surface projects from it."""
    contract: str = CONTRACT
    company: str = ""
    standing: str = READ_BOUNDED
    #: Why the standing is what it is, in a sentence a reader can act on.
    standing_reason: str = ""

    # --- the hero (§24) ----------------------------------------------------
    identity: str = ""              #: what this company is, synthesized
    economic_role: str = ""         #: what it does in its market
    strategic_position: str = ""    #: where it sits against rivals
    central_question: str = ""      #: the one decision worth arguing about
    what_matters_now: Tuple[Statement, ...] = ()

    # --- the ladder (§6) ---------------------------------------------------
    level1_facts: Tuple[Statement, ...] = ()
    level2_business_model: Tuple[Statement, ...] = ()
    level3_mechanism: Tuple[Mechanism, ...] = ()
    level4_competition: Tuple[CompetitorRead, ...] = ()
    level5_decision: Statement = dataclasses.field(
        default_factory=lambda: Statement("", UNMEASURED))
    level6_action: Optional[BoundedAction] = None
    level7_monitoring: Tuple[Statement, ...] = ()

    # --- the belief layer (§3-§7) -----------------------------------------
    #
    # ONE OBJECT PER RUN, PROJECTED BY EVERY SURFACE. Three surfaces deriving
    # their own competing explanations from whatever field happened to be
    # populated is how this programme produced a page that argued with the
    # page before it.
    competitive_ground: Optional[object] = None
    market_beliefs: Tuple[object, ...] = ()
    belief_challenges: Tuple[object, ...] = ()
    explanation_field: Optional[object] = None
    assumption_chain: Optional[object] = None
    belief_experiment: Optional[object] = None

    # --- supporting intelligence ------------------------------------------
    macro: Tuple[dict, ...] = ()            #: transmission chains (§11)
    metrics: Tuple[MetricExpectation, ...] = ()   #: §10
    story: Tuple[Chapter, ...] = ()          #: §25/§39
    #: The company's own account, quoted and attributed -- never the opener.
    own_words: str = ""
    own_words_source: str = ""
    #: The options the run's own decision weighed, when it reached one. Empty
    #: for a run that decided nothing -- and never invented, because a choice
    #: this product composed rather than derived is not a choice management
    #: faced.
    options: Tuple[dict, ...] = ()
    #: What this particular run added, separately from what is known.
    run_contribution: str = ""
    evidence_note: str = ""

    def as_dict(self) -> dict:
        return {
            "contract": self.contract,
            "company": self.company,
            "standing": self.standing,
            "standing_reason": self.standing_reason,
            "identity": self.identity,
            "economic_role": self.economic_role,
            "strategic_position": self.strategic_position,
            "central_question": self.central_question,
            "what_matters_now": [s.as_dict() for s in self.what_matters_now],
            "level1_facts": [s.as_dict() for s in self.level1_facts],
            "level2_business_model": [s.as_dict()
                                      for s in self.level2_business_model],
            "level3_mechanism": [m.as_dict() for m in self.level3_mechanism],
            "level4_competition": [c.as_dict()
                                   for c in self.level4_competition],
            "level5_decision": self.level5_decision.as_dict(),
            "level6_action": (self.level6_action.as_dict()
                              if self.level6_action else None),
            "level7_monitoring": [s.as_dict() for s in self.level7_monitoring],
            "macro": list(self.macro),
            "metrics": [m.as_dict() for m in self.metrics],
            "story": [dataclasses.asdict(c) for c in self.story],
            "options": list(self.options),
            "own_words": self.own_words,
            "own_words_source": self.own_words_source,
            "run_contribution": self.run_contribution,
            "evidence_note": self.evidence_note,
        }

    @property
    def puts_a_strategy_forward(self) -> bool:
        return self.standing in (READ_SUPPORTED, READ_BOUNDED)


# ===========================================================================
# §10 — what each business model is actually judged on
# ===========================================================================
#
# One list per model class, because "the metric is missing" is only a finding
# when the metric is one this KIND of business is judged on. Asking a mining
# company for net revenue retention and reporting its absence as a gap is how
# a report becomes noise.
#: THE THREE CLASSES ADDED ONE CYCLE AGO HAD NO ENTRY HERE, so Meta, Amazon
#: and Walmart were judged on no model-specific metric at all — dimension 3
#: of the scorecard, absent for three of eight companies and unnoticed because
#: nothing checked this table against the registry. See
#: `company_profile.MODEL_CLASSES` and `test_a_model_class_registry.py`.
_METRICS = {
    "ADVERTISING_PLATFORM": (
        ("impressions or engaged time",
         "the inventory being sold; without it there is nothing to auction"),
        ("price per impression",
         "the auction clearing price is the whole revenue line here"),
        ("advertiser count and spend per advertiser",
         "demand depth decides whether the auction clears at a good price"),
        ("engagement per user",
         "attention is the input to inventory, so it leads revenue"),
        ("compute and infrastructure spend",
         "recommendation quality is bought, and it is the largest cost line"),
        ("regulatory and platform-policy exposure",
         "targeting and data rules move revenue without any competitor acting"),
    ),
    "MULTI_ENGINE_PLATFORM": (
        ("segment revenue and segment operating income",
         "the engine carrying the revenue is not the one carrying the profit, "
         "and only the split shows which"),
        ("cloud or infrastructure growth and margin",
         "the highest-margin engine sets the group's earnings power"),
        ("advertising or take-rate revenue",
         "third-party monetisation earns without carrying the inventory"),
        ("fulfilment and logistics cost per unit",
         "the cost that scales with volume rather than with revenue"),
        ("capital expenditure by segment",
         "which engine the capital is actually going into"),
        ("paid unit or order growth",
         "the volume the whole structure is built to serve"),
    ),
    "SCALE_RETAIL": (
        ("comparable sales, split into traffic and basket",
         "thin margin means small comparable moves swing profit"),
        ("gross margin and markdown rate",
         "buying scale and inventory discipline show up here first"),
        ("inventory turns",
         "the return in this model comes from turns, not from price premium"),
        ("cost of goods and sourcing terms",
         "the buying side is where a discounter's advantage is made"),
        ("store and distribution operating cost",
         "a largely fixed base against thin unit margin"),
        ("membership, advertising and other high-margin income",
         "the part of profit that does not come from selling goods"),
    ),
    "SUBSCRIPTION_SOFTWARE": (
        ("revenue growth", "the rate the contracted base is compounding at"),
        ("large-customer growth",
         "expansion inside big accounts is where this model's margin is"),
        ("contracted backlog or remaining performance obligations",
         "revenue already signed decides how much of next year is discretionary"),
        ("gross margin",
         "delivery cost per unit served is what turns growth into profit here"),
        ("net revenue retention",
         "whether the installed base grows without a new sale"),
        ("sales efficiency",
         "what it costs to add a unit of recurring revenue"),
    ),
    "BALANCE_SHEET_OR_NETWORK": (
        ("net interest margin or take rate",
         "the spread the balance sheet or the network earns per unit"),
        ("volume through the network",
         "this model earns on flow, so flow is the growth variable"),
        ("deposit or float mix",
         "the cost of the funding side decides the spread"),
        ("credit quality or loss rate",
         "the cost that shows up late and decides the cycle"),
        ("capital position",
         "how much of the balance sheet can be put to work"),
        ("fee income",
         "the part of revenue that does not depend on the spread"),
    ),
    "DESIGN_AND_MANUFACTURE": (
        ("unit volume and mix", "price times mix is most of the revenue line"),
        ("backlog or order book", "what is already sold into the next period"),
        ("capacity utilisation", "fixed cost per unit is decided here"),
        ("gross margin", "whether pricing is holding against input cost"),
        ("design wins", "the leading indicator of the next cycle's volume"),
        ("capital expenditure intensity", "what growth costs up front"),
    ),
    "MANUFACTURE_AND_AFTERMARKET": (
        ("order backlog", "the committed half of next period's revenue"),
        ("dealer or channel inventory", "where demand and shipment diverge"),
        ("aftermarket and services revenue",
         "the counter-cyclical margin that carries the trough"),
        ("pricing realisation against input cost",
         "whether price is recovering cost or chasing it"),
        ("capacity utilisation", "fixed-cost absorption through the cycle"),
        ("installed base", "the annuity the aftermarket is sold into"),
    ),
    "COMMODITY_PRODUCER": (
        ("produced volume", "the half of revenue the company controls"),
        ("realised price versus benchmark",
         "the other half, which it does not"),
        ("unit cash cost", "position on the industry cost curve"),
        ("reserve life or resource base", "how long the volume lasts"),
        ("sustaining capital", "what it costs to keep volume flat"),
    ),
    "BRANDED_CONSUMER": (
        ("volume and price/mix split",
         "growth from more units and growth from better ones are different"),
        ("gross margin", "whether the brand is carrying input cost"),
        ("marketing spend as a share of revenue",
         "what the brand costs to maintain"),
        ("channel and geographic mix", "where the growth is actually coming from"),
        ("market share", "whether the category or the company is growing"),
    ),
    "CONTRACTED_OR_RATE_BASE_ASSETS": (
        ("contracted revenue and remaining term",
         "the visible, committed part of the future"),
        ("rate base or asset base growth",
         "the regulated engine that compounds earnings"),
        ("allowed return and the regulatory calendar",
         "the price is set by a regulator, so its schedule is the plan"),
        ("capital expenditure programme", "what the next increment of base costs"),
        ("counterparty quality", "a contract is only as good as who signed it"),
    ),
    "PEOPLE_OR_ROUTE_BASED_SERVICES": (
        ("utilisation or load factor", "the single variable this model turns on"),
        ("revenue per unit of capacity", "price realised against the asset"),
        ("cost per unit of capacity", "the other half of the same equation"),
        ("headcount or fleet", "the capacity being sold"),
        ("contract renewals", "the visibility on next period"),
    ),
    "REGULATED_PRODUCT_OR_PROVIDER": (
        ("product mix", "where the margin actually sits in the portfolio"),
        ("pipeline and regulatory milestones",
         "the future revenue, priced by probability"),
        ("reimbursement and payer mix",
         "who pays decides the realised price"),
        ("patent or exclusivity calendar",
         "the date the economics change, known in advance"),
        ("R&D as a share of revenue", "the cost of replacing the pipeline"),
    ),
}


# ===========================================================================
# §9 — the microeconomic mechanisms, chosen by business model
# ===========================================================================
_MECHANISMS = {
    "ADVERTISING_PLATFORM": (
        ("Auction density",
         "price per impression is set by how many advertisers bid for the "
         "same person, so revenue rises when competition for the impression "
         "rises rather than when inventory does",
         "whether to grow inventory or to grow the number of bidders "
         "competing for the inventory that already exists"),
        ("Attention supply",
         "inventory is time spent, which is produced by the product's "
         "ranking and recommendation quality rather than bought or built",
         "how much engineering goes to engagement versus to monetisation"),
        ("Measurement and signal",
         "an advertiser pays for outcomes it can attribute, so the ability "
         "to measure a conversion is itself a large part of the price",
         "what to build when a platform or a regulator removes a signal"),
        ("Advertiser concentration and mix",
         "small direct-response advertisers and large brand budgets respond "
         "to entirely different things, and a mix shift moves realised price "
         "without any change in demand for the product",
         "which advertiser cohort the next product decision is for"),
    ),
    "MULTI_ENGINE_PLATFORM": (
        ("Engine mix",
         "the consolidated margin is a weighted average of businesses whose "
         "own margins are not close to each other, so mix moves the reported "
         "result more than performance inside any one engine does",
         "which engine gets the next unit of capital and management "
         "attention"),
        ("Cross-subsidy",
         "a thin-margin engine can be run at scale because a fat-margin one "
         "carries the fixed cost, and the arrangement is invisible in "
         "consolidated statements",
         "whether an engine that loses money standalone is a strategy or a "
         "leak"),
        ("Shared infrastructure leverage",
         "capacity built for one engine is sold to the others and then to "
         "outsiders, so the same asset earns twice",
         "how much capacity to build ahead of the engine that needs it"),
        ("Third-party participation",
         "sellers, developers and advertisers on the platform add supply "
         "without adding cost, and take share of the economics in exchange",
         "how much of the platform to open, and on what terms"),
    ),
    "SCALE_RETAIL": (
        ("Buying scale",
         "volume bought at a lower unit cost can be given to the customer as "
         "price or kept as margin, and the choice compounds either into "
         "traffic or into earnings",
         "how much of a cost advantage to pass through"),
        ("Inventory turns",
         "return on capital in retail is margin times turns, so a thin "
         "margin earned four times beats a fat one earned once",
         "whether to hold assortment breadth or working capital"),
        ("Traffic and basket",
         "the store or site is a fixed cost that is amortised over visits, "
         "so an extra visit is close to pure contribution and an extra item "
         "in the basket is closer still",
         "what to spend to bring a customer back rather than to acquire a "
         "new one"),
        ("Private label and mix",
         "own-brand product earns a materially higher margin and moves the "
         "price the national brand can hold in the same aisle",
         "how far to push own-brand before the assortment stops being a "
         "destination"),
    ),
    "SUBSCRIPTION_SOFTWARE": (
        ("Operating leverage",
         "delivery cost rises far more slowly than contracted revenue, so "
         "each additional unit of revenue carries an unusually high share of "
         "its own margin",
         "whether growth should be bought with sales spend or with price"),
        ("Switching cost",
         "once a customer's workload depends on the platform, moving it costs "
         "engineering time the customer would rather spend elsewhere",
         "how much price the installed base will absorb before it shops"),
        ("Expansion economics",
         "revenue from an existing account costs a fraction of revenue from a "
         "new one, because the relationship, the integration and the trust "
         "already exist",
         "whether the next sales dollar goes to acquisition or expansion"),
        ("Price and packaging",
         "published, self-serve pricing sets a public reference that "
         "competitors price against and customers compare without a "
         "conversation",
         "how far list price can move before it becomes a competitive event"),
    ),
    "BALANCE_SHEET_OR_NETWORK": (
        ("Spread economics",
         "earnings are the difference between what the funding side costs and "
         "what the asset side earns, so both move with the same rate cycle "
         "and rarely at the same speed",
         "how much of the balance sheet to reprice, and when"),
        ("Network effects",
         "each additional participant makes the network more valuable to every "
         "other one, so share compounds and is expensive to attack",
         "whether to defend flow with price or with distribution"),
        ("Scale in fixed cost",
         "the platform, the compliance function and the risk apparatus cost "
         "roughly the same whatever the volume through them",
         "whether volume growth should be bought below the current take rate"),
        ("Credit and loss timing",
         "revenue is booked early and losses arrive late, so a good quarter "
         "and a good decision are not the same thing",
         "how much growth to accept at the current underwriting standard"),
    ),
    "DESIGN_AND_MANUFACTURE": (
        ("Capacity and utilisation",
         "fixed cost is committed in large increments and absorbed per unit, "
         "so utilisation decides the margin more than price does",
         "how much capacity to commit against a forecast, and when"),
        ("Learning curve",
         "unit cost falls with cumulative volume, so the first mover to scale "
         "holds a cost position a later entrant has to buy",
         "whether to price for share now or for margin later"),
        ("Mix",
         "two units of the same volume can carry very different margin, so "
         "the mix shift matters as much as the growth rate",
         "which products to prioritise when capacity is scarce"),
        ("Customer concentration",
         "a small number of buyers set the timing of demand, so their product "
         "cycles are effectively this company's plan",
         "how much of the order book one customer may represent"),
    ),
    "MANUFACTURE_AND_AFTERMARKET": (
        ("Installed-base annuity",
         "every unit sold creates years of parts and service demand that is "
         "far less cyclical, and far higher margin, than the machine itself",
         "how hard to price the machine to win the annuity behind it"),
        ("Operating leverage through the cycle",
         "fixed manufacturing cost is absorbed across volume that swings with "
         "the cycle, so the trough costs more than the peak earns",
         "how much capacity to hold through a downturn"),
        ("Channel inventory",
         "shipments to dealers and demand from end users diverge, and the gap "
         "unwinds violently",
         "when to slow production against a channel that is still ordering"),
        ("Price realisation",
         "input cost moves faster than list price, so realised price against "
         "cost is the real margin variable",
         "when to take price, and how much"),
    ),
    "COMMODITY_PRODUCER": (
        ("Cost-curve position",
         "the price is set by the market and the margin is set by where this "
         "producer sits on the industry cost curve",
         "which assets to run and which to idle at a given price"),
        ("Volume and grade",
         "produced volume is controllable and realised price is not, so the "
         "controllable half is where management earns its keep",
         "how much sustaining capital to spend to hold volume"),
        ("Capital cycle",
         "everyone expands at the top and cuts at the bottom, which is what "
         "creates the next price cycle",
         "whether to commit capital against the consensus"),
    ),
    "BRANDED_CONSUMER": (
        ("Brand pricing power",
         "a brand is the ability to raise price without losing the volume, "
         "and it depreciates when it is not spent on",
         "how much price the brand can carry this year"),
        ("Distribution advantage",
         "shelf, placement and search position decide how many people can buy "
         "at all, largely independently of how good the product is",
         "where to spend the next increment of trade investment"),
        ("Mix",
         "premiumisation grows revenue without a unit, and trade-down "
         "destroys it without losing one",
         "which price points to defend"),
    ),
    "CONTRACTED_OR_RATE_BASE_ASSETS": (
        ("Regulated or contracted return",
         "the price is set by a regulator or a long-term contract, so earnings "
         "grow with the asset base rather than with demand",
         "how much capital to put into the base, and how to fund it"),
        ("Cost of capital",
         "the asset is long-lived and debt-funded, so the funding rate is a "
         "direct input to the economics rather than a background condition",
         "when to refinance, and what to commit at the current rate"),
        ("Counterparty concentration",
         "contracted revenue is only as reliable as the entities that signed "
         "the contracts",
         "how much exposure to one counterparty is acceptable"),
    ),
    "PEOPLE_OR_ROUTE_BASED_SERVICES": (
        ("Utilisation",
         "capacity is paid for whether or not it is sold, so the load factor "
         "decides the margin",
         "how much capacity to carry into the next period"),
        ("Labour cost",
         "the largest cost is people, and it reprices on its own schedule "
         "rather than with demand",
         "when to change the capacity plan against wage pressure"),
        ("Route or contract economics",
         "profitability is decided per route or per contract, and the average "
         "hides both the winners and the losers",
         "which contracts to renew and which to let go"),
    ),
    "REGULATED_PRODUCT_OR_PROVIDER": (
        ("Portfolio and exclusivity",
         "revenue is a portfolio of products with known expiry dates, so the "
         "cliff is scheduled rather than uncertain",
         "how much to spend replacing revenue that is already dated"),
        ("Reimbursement",
         "the payer, not the patient, sets the realised price, so access "
         "decisions matter more than list price",
         "which indications and geographies to prioritise"),
        ("Pipeline risk",
         "development spend is committed years before the outcome is known, "
         "and most of it fails",
         "which programmes to fund and which to stop"),
    ),
}


def _facts_from(dossier: Optional[dict]) -> RecordFacts:
    """`RecordFacts` from a published market dossier, tolerating absence."""
    if not isinstance(dossier, dict):
        return RecordFacts(available=False)
    def _count(key):
        value = dossier.get(key)
        if isinstance(value, (list, tuple)):
            return len(value)
        if isinstance(value, int):
            return value
        return 0
    economics = dossier.get("economic_context") or dossier.get("economics")
    ids: Tuple[str, ...] = ()
    if isinstance(economics, (list, tuple)):
        ids = tuple(str((e or {}).get("economic_id") or (e or {}).get("id")
                        or "") for e in economics)
        ids = tuple(i for i in ids if i)
    return RecordFacts(
        evidence=_count("evidence"),
        beliefs=_count("beliefs"),
        expectations=_count("expectations"),
        contradictions=_count("contradictions"),
        theses=_count("theses"),
        causal_questions=_count("causal_questions"),
        economic_ids=ids,
        hidden_state=str(dossier.get("hidden_state") or ""),
        available=True,
    )


# ===========================================================================
# the composer
# ===========================================================================
def compose(*, company: str = "", company_id: str = "", domain: str = "",
            profile: Optional[CompanyIntelligenceProfile] = None,
            selection: Optional[AnalysisSelection] = None,
            dossier: Optional[dict] = None,
            run_decision=None,
            observations: Optional[Sequence[dict]] = None,
            documents: Optional[Sequence[dict]] = None,
            own_words: str = "", own_words_source: str = "",
            manifest=None, registrant=None, evidence_text: str = "",
            simulation=None) -> StrategicRead:
    """The bounded strategic read for one company.

    Never raises and never returns None: a surface that has to handle "no
    read object" grows its own refusal, which is the defect this closes.
    """
    observations = list(observations or ())
    documents = list(documents or ())
    if selection is None:
        selection = select(company_id, name=company, domain=domain,
                           facts=_facts_from(dossier), profile=profile,
                           manifest=manifest, registrant=registrant,
                           evidence_text=evidence_text)
    profile = selection.profile or profile
    name = _clean(company or selection.company_name or company_id) or "This company"

    if profile is None or not profile.known:
        # AN UNCLASSIFIED COMPANY IS NOT A COMPANY WITH NO CONCLUSION.
        #
        # The classification supplies the ECONOMICS -- the mechanisms, the
        # metrics, the transmission channels, the peer set. It is not a
        # precondition for reporting what this run actually concluded. When
        # the run reached a decision of its own, dropping it because the
        # manifest has no row for this company would throw away the strongest
        # thing on the page and replace it with "could not be classified",
        # which is the refusal wearing a different hat.
        #
        # So: run decision present -> a bounded read built from IT, with the
        # missing classification stated as what it costs. Run decision absent
        # AND no classification -> genuinely nothing to reason from, and that
        # is the one state where no strategy is put forward.
        if _has_conclusion(run_decision):
            return _from_run_decision(name, profile, run_decision,
                                      observations, documents, own_words,
                                      own_words_source)
        return _unidentified(name, profile, observations, documents)

    model = profile.business_model_class
    standing, reason = _standing(profile, selection, observations, documents,
                                 run_decision)

    identity = _identity(name, profile, selection)
    economic_role = _economic_role(name, profile)
    question = _central_question(name, profile, selection)

    level1 = _level1(name, profile, observations, documents)
    level2 = _level2(name, profile)
    level3 = _level3(model)
    ground = _ground(name, profile, documents)
    level4 = _level4(name, profile, selection, documents, ground)
    position = _position(name, profile, selection, level4)
    level5 = _level5(name, selection, run_decision, standing)
    level6 = _level6(name, profile, selection, run_decision, standing,
                     observations)
    level7 = _level7(name, profile, selection, run_decision)
    macro = _macro(selection)
    metrics = _metrics(model, observations, documents)
    story = _story(name, profile, selection, run_decision, observations,
                   level4)
    belief = _belief_pass(name, profile, ground, simulation, level6)

    return StrategicRead(
        company=name, standing=standing, standing_reason=reason,
        identity=identity, economic_role=economic_role,
        strategic_position=position, central_question=question,
        what_matters_now=_what_matters_now(name, profile, selection, level6,
                                           macro),
        level1_facts=level1, level2_business_model=level2,
        level3_mechanism=level3, level4_competition=level4,
        level5_decision=level5, level6_action=level6,
        level7_monitoring=level7,
        macro=macro, metrics=metrics, story=story,
        options=_options(run_decision),
        own_words=_sentence(own_words) if own_words else "",
        own_words_source=_clean(own_words_source),
        run_contribution=_run_contribution(observations, documents),
        evidence_note=_evidence_note(observations, documents),
        competitive_ground=ground,
        market_beliefs=belief.get("beliefs", ()),
        belief_challenges=belief.get("challenges", ()),
        explanation_field=belief.get("explanations"),
        assumption_chain=belief.get("graph"),
        belief_experiment=belief.get("experiment"),
    )


def _ground(name, profile, documents):
    """The competitive ladder for this run.

    Never raises: a competitive read that disappears because an extractor
    threw is the failure mode the whole competitive module exists to remove,
    and an empty ground still renders — the surfaces handle `None`.
    """
    try:
        from intent_engine.executive import competitive_ground
        refused: list = []
        named = _named_rivals(name, documents, profile=profile,
                              refusals=refused)
        return competitive_ground.build(
            name, profile, documents, named_firms=named,
            other_relationships=_routed(refused))
    except Exception:                                       # noqa: BLE001
        return None


def _belief_pass(name, profile, ground, simulation, level6):
    """Form the market's beliefs and attack them.

    The conclusion handed to the assumption graph is the run's OWN action, so
    the chain that gets audited is the chain under the recommendation the
    reader is actually being given — not a restatement composed for the graph.
    """
    try:
        import datetime as _dt
        from intent_engine.executive import belief_engine
        conclusion = _clean(getattr(level6, "action_now", "")) or ""
        return belief_engine.analyse(
            company=name, profile=profile,
            state=observed_state_of(simulation), ground=ground,
            as_of=_dt.date.today().isoformat(), conclusion=conclusion)
    except Exception:                                       # noqa: BLE001
        return {}


def observed_state_of(simulation):
    """(growth, margin) from an ALREADY-BUILT simulation, or None.

    THE STATE IS NOT LOOKED UP HERE. Deriving it independently would mean a
    second set of XBRL round trips to the regulator on the critical path of
    every run — the exact omission that once took the suite from ten minutes
    to over an hour. The webapp already builds and caches one simulation per
    run behind the outbound-call gate; this reads that.

    `None` is a real answer: a private company has no filed series, gets no
    inferred market expectation, and is not given a fabricated one.
    """
    index = getattr(simulation, "index", None)
    points = list(getattr(index, "points", ()) or ())
    if len(points) < 3:
        return None
    try:
        from intent_engine.executive import history_simulator as HS
        return HS.observed_state(points)
    except Exception:                                       # noqa: BLE001
        return None


def _has_conclusion(run_decision) -> bool:
    """Did this run's own reasoning reach something worth reporting?"""
    if run_decision is None:
        return False
    return bool(_usable(getattr(run_decision, "mechanism", ""))
                or _usable(getattr(run_decision, "recommended_next_move", ""))
                or (getattr(run_decision, "options", ()) or ()))


def _from_run_decision(name, profile, run_decision, observations, documents,
                       own_words, own_words_source) -> StrategicRead:
    """A bounded read for a company this build cannot classify.

    Everything here comes from the run's own decision and from what it read.
    Nothing comes from a business-model table, because there is no row for
    this company -- and the absence is stated rather than papered over.
    """
    mechanism = _usable(getattr(run_decision, "mechanism", ""))
    move = _usable(getattr(run_decision, "recommended_next_move", ""))
    unknown = (_usable(getattr(run_decision, "unsafe_because", ""))
               or _usable(getattr(run_decision, "limitation", ""))
               or "the size of the effect is not disclosed")
    limitation = _clean(getattr(profile, "profile_limitation", ""))
    facts = _level1(name, profile, observations, documents)
    action = BoundedAction(
        causal_confidence="BOUNDED — supported in direction, not in size",
        what_is_known=_sentence(mechanism or "what this run read is set out "
                                             "below"),
        what_remains_unknown=_sentence(unknown),
        why_it_matters=_sentence(
            "it is the parameter that decides whether the move below is "
            "worth making now or worth deferring"),
        action_now=_sentence(move or "hold the decision open and run the "
                                     "check below before committing"),
        minimum_viable_experiment=_sentence(
            move or "establish the one measure named above on a single "
                    "segment before committing the rest"),
        kill_switch=_sentence(
            "stop if the check returns against the reading, rather than "
            "waiting for the next planning cycle"),
        falsifier=_sentence(_usable(getattr(run_decision, "falsifier", ""))
                            or "a disclosure showing the mechanism moving in "
                               "the opposite direction would overturn this"),
        voi_band=VOI_HIGH,
        guardrail=_sentence("commit no more than can be withdrawn inside one "
                            "planning cycle until that check returns"))
    return StrategicRead(
        company=name, standing=READ_BOUNDED,
        standing_reason=_sentence(
            "the reading below is this run's own, read from what it "
            "retrieved. What kind of business this is has not been "
            "established, so no industry economics are applied to it"
            + (f" — {_lower_first(limitation)}" if limitation else "")),
        identity=_sentence(
            f"{name} could not be matched to a business model in this build, "
            f"so what follows rests on this run's evidence alone"),
        central_question=_sentence(
            _clean(getattr(run_decision, "topic", ""))
            or "what to do about the reading below"),
        what_matters_now=tuple(
            Statement(_capitalised(t), BOUNDED_INFERENCE, "this run")
            for t in (mechanism, move) if t)[:3],
        level1_facts=facts,
        level5_decision=Statement(
            _sentence(mechanism or _clean(getattr(run_decision, "headline",
                                                  "")) or move),
            BOUNDED_INFERENCE, "this run's reasoning"),
        level6_action=action,
        options=_options(run_decision),
        own_words=_sentence(own_words) if own_words else "",
        own_words_source=_clean(own_words_source),
        run_contribution=_run_contribution(observations, documents),
        evidence_note=_evidence_note(observations, documents))


def _unidentified(name, profile, observations, documents) -> StrategicRead:
    """The ONE state in which no strategy is put forward.

    Note what it is not: it is not "the evidence was thin". It is "what kind
    of business this is has not been established", which is a different
    problem with a different fix, and it is the only honest reason to decline
    a strategic read for an operating company.
    """
    why = _clean(getattr(profile, "profile_limitation", "")) or (
        "what kind of business this is has not been established, so any "
        "economic reasoning below would be about a business model rather "
        "than about this company")
    # THE UNCLASSIFIED CASE IS STILL ABOUT ONE COMPANY.
    #
    # Measured: three companies with three different filings produced a
    # byte-identical step-4 page, because every sentence here was composed
    # from the classification -- and the classification is what is missing.
    # What is NOT missing is what this run read, which differs per company by
    # construction. So the facts go on the object even when the economics
    # cannot, and the surfaces render them.
    facts = _level1(name, profile, observations, documents)
    return StrategicRead(
        company=name, standing=READ_UNIDENTIFIED, standing_reason=_sentence(why),
        level1_facts=facts,
        identity=_sentence(f"{name} could not be classified into a business "
                           f"model from the public record"),
        economic_role="",
        central_question=_sentence(
            f"What kind of business {name} is, which decides every question "
            f"worth asking after it"),
        what_matters_now=(
            Statement(_sentence(why), UNMEASURED,
                      "company classification"),),
        level6_action=BoundedAction(
            causal_confidence="NOT ESTABLISHED",
            what_is_known=_sentence(
                f"{len(documents)} source(s) were retrieved for {name}"),
            what_remains_unknown=_sentence(
                "which business model this company operates, and therefore "
                "which economics govern it"),
            why_it_matters=_sentence(
                "every mechanism, metric and competitor below would be "
                "selected by that classification, so guessing it would make "
                "the whole analysis confidently wrong rather than incomplete"),
            action_now=_sentence(
                "classify the business before commissioning analysis: one "
                "annual report and one segment disclosure is enough"),
            minimum_viable_experiment=_sentence(
                "read the most recent annual filing's segment note and "
                "revenue recognition policy, and record the model class"),
            kill_switch=_sentence(
                "if the filing shows two materially different businesses, "
                "analyse them separately rather than as one company"),
            falsifier=_sentence(
                "a segment disclosure showing a single dominant revenue "
                "model would resolve this immediately"),
            voi_band=VOI_HIGH),
        run_contribution=_run_contribution(observations, documents),
        evidence_note=_evidence_note(observations, documents))


# --- standing ---------------------------------------------------------------
def _standing(profile, selection, observations, documents, run_decision):
    """SUPPORTED / BOUNDED, and why.

    A missing third-party source reduces the standing to BOUNDED. It never
    reaches UNIDENTIFIED -- that state is about classification, not evidence,
    and conflating them is the whole defect (§4).
    """
    independent = sum(1 for o in observations
                      if str((o or {}).get("source_class") or "")
                      not in ("company_owned", "executive_statement",
                              "investor_material", ""))
    filings = sum(1 for d in documents
                  if "10-K" in str((d or {}).get("document_type") or "")
                  or "10-Q" in str((d or {}).get("document_type") or "")
                  or "sec.gov" in str((d or {}).get("url") or ""))
    if independent >= 2 and filings >= 1:
        return READ_SUPPORTED, _sentence(
            f"the reading rests on this company's own regulatory disclosure "
            f"and on {independent} source(s) it does not control")
    if filings >= 1:
        return READ_BOUNDED, _sentence(
            "the direction of the reading is supported by this company's own "
            "regulatory disclosure and by how this kind of business works; "
            "its size is not established, because no independent source "
            "measured it")
    # THE REASON MUST AGREE WITH THE COUNT PRINTED BESIDE IT.
    #
    # Measured on the live Caterpillar Connect page, one paragraph said both
    # "no independent source corroborated it in this run" and "1 of the
    # passages read came from a source the company does not control." Both
    # sentences came from this module. The count is the fact; the reason has
    # to be written from it rather than from the branch that produced it.
    corroboration = (
        f"{independent} source(s) outside the company's control were read, "
        f"which is not enough to size the effect"
        if independent else
        "no source outside the company's control was read in this run")
    if profile.profile_state == PROFILE_AVAILABLE:
        return READ_BOUNDED, _sentence(
            f"the reading follows from an established classification of this "
            f"business and from what the company publishes about itself; "
            f"{corroboration}, so it is held in direction only")
    return READ_BOUNDED, _sentence(
        f"the reading follows from how this kind of business works; "
        f"{corroboration}, so it is held in direction only")


# --- the hero (§24) ---------------------------------------------------------
def _identity(name, profile, selection) -> str:
    """What this company IS -- synthesized, never the company's own copy.

    §22. The opener used to be the first qualifying sentence off the
    company's website, which is marketing the reader has already seen and,
    when it was clipped to fit, marketing that trailed off mid-clause.
    """
    sector = _pretty(profile.sector)
    model = _lower_first(_first_clause(profile.business_model))
    if sector and model:
        return _sentence(f"{name} is {_article(sector)} {sector} business "
                         f"that runs on {model}")
    if model:
        return _sentence(f"{name} runs on {model}")
    return _sentence(f"{name} is an operating company")


def _economic_role(name, profile) -> str:
    structure = _lower_first(_first_clause(profile.industry_structure))
    demand = _lower_first(_first_clause(profile.demand_model))
    parts = []
    if structure:
        parts.append(f"It competes in a market of {structure}")
    if demand:
        parts.append(f"demand reaches it {demand}")
    return _sentence("; ".join(parts)) if parts else ""


def _position(name, profile, selection, rivals_read=()) -> str:
    """Where this company sits, named by the SAME rivals level 4 names.

    The header used to list the manifest's structural peers -- Adobe,
    Constellation, Databricks for Cloudflare -- while the competitive section
    below it listed the rivals Cloudflare's own filing names. One page, two
    competitor sets, and the wrong one first.
    """
    # RUNG 9 IS NOT A DIRECT CONTEST. STRUCTURAL_PEER is defined as "same
    # business model; not a stated rival" — it is the ladder's honest bottom
    # rung, reached when nothing better was found. Letting it fill this
    # sentence told a reader it was the company's most direct competition.
    #
    # MEASURED across Batch A: Meta's opening named 37signals LLC and Exxon's
    # named Agnico Eagle Mines Limited — a project-management tool and a gold
    # miner, both manifest sector-mates promoted into "contested most
    # directly by". A rung the ladder itself calls weakest may not be
    # rendered as the strongest claim on the page.
    ranked = [c for c in (rivals_read or ())
              if getattr(c, "rung", "") != "STRUCTURAL_PEER"]
    rivals = [c.name for c in ranked][:3]
    # §8. THE WORDING IS A CLAIM, AND IT MUST MATCH WHAT WAS ESTABLISHED.
    #
    # "Contested most directly by" said of an in-house build, a do-nothing
    # and an automation threat is false about all three, and those are what
    # the ladder legitimately returns for a company whose filing names no
    # firm. Meta's opening read "contested most directly by The advertiser
    # spending the budget on its own channels" — a true alternative, given
    # the wrong grammar. The kind decides the verb.
    grouped = _by_alternative_kind(ranked)
    if grouped:
        bits = [grouped_clause for grouped_clause in grouped]
        leverage = _enum_word(profile.operating_leverage)
        if leverage:
            bits.append(f"the economics that decide the contest are "
                        f"{leverage} operating leverage — "
                        f"{_lower_first(_first_clause(profile.operating_leverage))}")
        return _sentence(", and ".join(bits))
    # "CONTESTED MOST DIRECTLY BY" IS A STRONG CLAIM AND NEEDS A STRONG BASIS.
    #
    # With no ladder rows this fell through to the manifest's structural
    # peers — INCLUDING the weak ones, whose own stated basis is "same sector
    # but a different business model: it competes for the same end demand
    # WITHOUT THE SAME ECONOMICS". The sentence promoted that to the most
    # direct contest in the company's opening paragraph. Measured live on
    # Meta, whose model class has no manifest peer at all: "contested most
    # directly by AT&T Inc, Alphabet Inc and Automation absorbing the task
    # itself". One of those three was right.
    #
    # A same-model peer still earns the strong sentence. A sector-mate gets a
    # sentence that says what it actually is.
    hedged = False
    if not rivals:
        peers = list(profile.strategic_competitors or ())
        strong = [c for c in peers
                  if getattr(c, "basis", "") == "SAME_MODEL_AND_SECTOR"]
        rivals = [c.name for c in (strong or peers)][:3]
        hedged = not strong
    leverage = _enum_word(profile.operating_leverage)
    bits = []
    if rivals and hedged:
        bits.append("It sits in the same sector as "
                    + _join(rivals)
                    + ", which earn differently and so are a weaker "
                      "comparison than a direct rival")
    elif rivals:
        # §8. ONE VOICE. This is the manifest peer fallback, reached only
        # when the ladder returned nothing, and it said "contested MOST
        # directly by" while the ladder path above says "contested directly
        # by" — two claims of different strength for the same thing, decided
        # by which producer happened to answer.
        bits.append("Its position is contested directly by "
                    + _join(rivals))
    if leverage:
        bits.append(f"and the economics that decide the contest are "
                    f"{leverage} operating leverage — "
                    f"{_lower_first(_first_clause(profile.operating_leverage))}")
    return _sentence(", ".join(bits)) if bits else ""


#: §8. ONE CLAUSE PER KIND OF ALTERNATIVE, in the order a reader needs them:
#: who beats us in a deal, what the customer buys instead, what they build,
#: and what happens when they do nothing. Keyed on the ladder's kind, never
#: on the company (§43).
_DIRECT_KINDS = ("DIRECT", "ADJACENT")
_SUBSTITUTE_KINDS = ("SUBSTITUTE", "PLATFORM_BUNDLE", "OPEN_SOURCE",
                     "CHANNEL_SHIFT", "AI_ENTRANT", "AI_REPLACEMENT",
                     "REGULATORY", "BEHAVIOUR_SHIFT")
_BUILD_KINDS = ("BUILD_IN_HOUSE",)
_INERTIA_KINDS = ("MANUAL_WORKFLOW", "DO_NOTHING")


#: A retrieved firm keeps its capital letter; a phrase read off the business
#: model is a common noun and mid-sentence it must read like one. "customers
#: can substitute Another surface holding the same attention hour" is the
#: kind of sentence that tells a reader the text was assembled rather than
#: written.
_ATTRIBUTED_RUNGS = ("NAMED_BY_SUBJECT", "NAMED_BY_CUSTOMER",
                     "NAMED_BY_RIVAL", "NAMED_BY_ANALYST")


def _identity_in_sentence(row, frame_verb: str = "") -> str:
    """The alternative's name as it reads inside the clause.

    MEASURED LIVE on c719979, Exxon: "customers can substitute substitute
    materials at the customer's plant". The frame supplies the verb and the
    ladder's identity begins with the same word, and two layers each writing
    it produces the stutter this codebase has produced before with lead-ins.
    """
    name = str(getattr(row, "name", "") or "")
    if str(getattr(row, "rung", "") or "") in _ATTRIBUTED_RUNGS:
        return name
    name = _lower_first(name)
    first = name.split(" ", 1)
    if frame_verb and first[0].rstrip("s") == frame_verb.rstrip("s") \
            and len(first) > 1:
        name = first[1]
    return name


def _by_alternative_kind(rows) -> list:
    """The opening sentence's clauses, one per kind that has a row.

    THE FIRST CLAUSE CARRIES THE SUBJECT. A company whose filing names no
    firm still has real alternatives, and the sentence has to say what they
    are without either claiming a rival it does not have or reading as an
    absence notice.
    """
    buckets = {"direct": [], "substitute": [], "build": [], "inertia": []}
    for row in rows:
        kind = str(getattr(row, "kind", "") or "")
        if kind in _DIRECT_KINDS or not kind:
            buckets["direct"].append(_identity_in_sentence(row))
        elif kind in _BUILD_KINDS:
            buckets["build"].append(_identity_in_sentence(row))
        elif kind in _INERTIA_KINDS:
            buckets["inertia"].append(_identity_in_sentence(row))
        else:
            # The substitute clause's verb is "substitute"; an identity that
            # opens with the same word must not repeat it.
            buckets["substitute"].append(
                _identity_in_sentence(row, frame_verb="substitute"))
    lead_taken = bool(buckets["direct"])
    out, budget = [], 3
    for key, frame in (
            ("direct", "Its position is contested directly by {}"),
            ("substitute", "customers can substitute {}"),
            ("build", "customers can internalise the work themselves — {}"),
            ("inertia", "the alternative may be delaying the purchase "
                        "altogether — {}")):
        names = buckets[key][:budget]
        if not names:
            continue
        budget -= len(names)
        clause = frame.format(_join(names))
        if not out and not lead_taken:
            # No firm was retrieved, so the sentence leads with the economic
            # truth rather than with a name it does not have.
            clause = ("Its position is contested less by a named firm than "
                      "by the alternatives its customers already have: "
                      + clause)
        out.append(clause)
        if budget <= 0:
            break
    return out


def _central_question(name, profile, selection) -> str:
    """The strategic tension, phrased as the argument worth having.

    `decision_question` is already the company's own decision in its own
    variables; this frames it as a tension rather than a form field.
    """
    question = _bare_question(name, selection.decision_question)
    if question:
        return _sentence(question)
    subject = _lower_first(_first_clause(profile.business_model))
    return _sentence(f"What {name} should do next about {subject}")


def _what_matters_now(name, profile, selection, action, macro):
    """Three points, each one a thing a CEO would act on (§24)."""
    out = []
    drivers = [_lower_first(d) for d in (profile.primary_revenue_drivers or ())]
    if drivers:
        # NOT "the variable to watch is customer count -- revenue moves with
        # customer count". A restated definition is not a finding; the useful
        # version says which drivers management can actually move and which
        # it cannot.
        out.append(Statement(
            _sentence(f"Growth here has to come from {_join(drivers[:3])} — "
                      f"there is no fourth source, so a plan that does not "
                      f"name one of those is not a growth plan"),
            STRONGLY_INFERRED, "business model"))
    if macro:
        first = macro[0]
        out.append(Statement(
            _sentence(f"{first.get('factor', 'The economic backdrop')} reaches "
                      f"this business through "
                      f"{_lower_first(first.get('mechanism', ''))}"),
            first.get("standing", BOUNDED_INFERENCE), "economic channel"))
    if action is not None:
        out.append(Statement(_capitalised(action.action_now),
                             BOUNDED_INFERENCE, "bounded action"))
    if not out:
        out.append(Statement(
            _sentence(f"The decision in front of {name} is "
                      f"{_lower_first(selection.decision_question)}"),
            BOUNDED_INFERENCE, "business model"))
    return tuple(out[:3])


# --- the ladder -------------------------------------------------------------
def _level1(name, profile, observations, documents) -> Tuple[Statement, ...]:
    """OBSERVED facts only. Counts and named artefacts, never prose."""
    out = []
    # WHAT WAS READ, BY NAME. A count is the same sentence for every company
    # that retrieved the same number of things -- measured: three companies
    # with three different filings ("Form 6-K", "Annual report on Form 20-F",
    # "Notice of annual general meeting") produced a byte-identical page,
    # because every sentence on it was a count. The titles are facts, they are
    # already on the record, and they differ by construction.
    titles = []
    for document in documents:
        title = _clean((document or {}).get("title")
                       or (document or {}).get("source_title"))
        if title and title not in titles:
            titles.append(title)
    if titles:
        out.append(Statement(
            _sentence(f"What was read for {name}: {_join(titles[:4])}"),
            OBSERVED, "this run's retrieval"))
    filings = [d for d in documents
               if "sec.gov" in str((d or {}).get("url")
                                   or (d or {}).get("final_url") or "")]
    if filings:
        kinds = sorted({str((d or {}).get("document_type") or "filing")
                        for d in filings})
        out.append(Statement(
            _sentence(f"{len(filings)} regulatory filing(s) for {name} were "
                      f"read in this run ({_join(kinds)})"),
            OBSERVED, "SEC EDGAR"))
    own = [o for o in observations
           if str((o or {}).get("source_class") or "") == "company_owned"]
    if own:
        out.append(Statement(
            _sentence(f"{len(own)} page(s) {name} publishes about itself were "
                      f"read"), OBSERVED, "company website"))
    third = [o for o in observations
             if str((o or {}).get("source_class") or "")
             not in ("company_owned", "executive_statement",
                     "investor_material", "")]
    if third:
        out.append(Statement(
            _sentence(f"{len(third)} source(s) outside {name}'s control "
                      f"referred to it"), OBSERVED, "independent sources"))
    else:
        out.append(Statement(
            _sentence(f"No source outside {name}'s control was retrieved in "
                      f"this run, so nothing below is corroborated by a third "
                      f"party"), UNMEASURED, "retrieval coverage"))
    return tuple(out)


def _level2(name, profile) -> Tuple[Statement, ...]:
    """The business-model interpretation. STRONGLY_INFERRED by construction:
    the classification is established and the economics follow from it."""
    rows = (
        (profile.business_model, "how the business makes money"),
        (profile.customer_structure, "who the customers are"),
        (profile.pricing_model, "how it prices"),
        (profile.operating_leverage, "what growth does to margin"),
        (profile.supplier_structure, "what it depends on"),
    )
    out = []
    for value, label in rows:
        if _known(value):
            out.append(Statement(
                _sentence(f"{label.capitalize()}: {_first_clause(value)}"),
                STRONGLY_INFERRED,
                f"{_pretty(profile.business_model_class)} economics"))
    return tuple(out)


def _level3(model) -> Tuple[Mechanism, ...]:
    return tuple(Mechanism(name=n, how_it_works=_sentence(h),
                           what_it_decides=_sentence(d),
                           standing=BOUNDED_INFERENCE)
                 for n, h, d in _MECHANISMS.get(model, ()))


def _level4(name, profile, selection, documents=(), ground=None
            ) -> Tuple[CompetitorRead, ...]:
    """The competitive read, projected from the ladder.

    WHY THIS IS A PROJECTION AND NOT A REPLACEMENT. `CompetitorRead` is what
    six surfaces already render. Changing its shape would have meant changing
    all of them in one commit, and the last time a producer and its consumers
    moved together in this codebase the surfaces that had no fallback broke
    silently. So the ladder is the producer, `CompetitorRead` stays the wire
    format, and each row now carries the rung it came from in the sentence a
    reader sees.
    """
    if ground is not None and getattr(ground, "rivals", ()):
        return _from_ground(name, profile, selection, ground)
    return _level4_legacy(name, profile, selection, documents)


def _from_ground(name, profile, selection, ground) -> Tuple[CompetitorRead, ...]:
    from intent_engine.executive.competitive_ladder import (
        CONTESTED_CATEGORY, NAMED_BY_SUBJECT, STRUCTURAL_PEER)
    moves = {str(getattr(m, "actor", "")).lower(): m
             for m in (selection.adversary or ())}
    out = []
    for rival in ground.rivals:
        move = moves.get(rival.identity.lower())
        # WHY IT IS A RIVAL IS THE RUNG, STATED. A reader must be able to see
        # the difference between "the company named this" and "we read this
        # off the business model", because those carry different weight and
        # the old page presented both in the same voice.
        if rival.rung == NAMED_BY_SUBJECT:
            why = (f"{name} names it as a competitor in its own filing — "
                   f"{_lower_first(rival.evidence[:180])}")
        elif rival.rung == CONTESTED_CATEGORY:
            why = (f"{name} names this as a category it competes with, in "
                   f"its own words. {_capitalise(rival.mechanism)}")
        elif rival.rung == STRUCTURAL_PEER:
            why = (f"Not named by {name} in what this run read. It is carried "
                   f"as a structural peer rather than a stated rival: "
                   f"{_lower_first(rival.mechanism)}")
        elif rival.is_attributed:
            why = (f"{_capitalise(rival.rung_label)}. "
                   f"{_capitalise(rival.mechanism)}")
        else:
            why = (f"Not a company — {rival.kind_label}, read from how this "
                   f"business model works rather than from a retrieved "
                   f"source. {_capitalise(rival.mechanism)}")
        out.append(CompetitorRead(
            name=rival.identity,
            rung=rival.rung,
            kind=rival.kind,
            why_a_rival=_sentence(why),
            exposure=_sentence(getattr(move, "impact", "")
                               or _capitalise(rival.why_it_matters)),
            # THE LADDER'S OWN REACTION WINS over the class default. The
            # default is authored for a single named firm and produced "banks
            # defends flow with distribution" on the deployed page, because a
            # contested category is plural and the class default cannot know
            # that. The ladder builds its sentence from the KIND, which does.
            likely_response=_sentence(
                _clean(getattr(move, "action", ""))
                or rival.likely_response
                or _default_response(profile.business_model_class,
                                     rival.identity)),
            response_likelihood=(_clean(rival.response_likelihood)
                                 or _likelihood(profile, move)),
            counter_move=_sentence(getattr(move, "countermeasure", "")
                                   or _capitalise(rival.counter_move)
                                   or _default_counter(profile)),
            signal_to_watch=_sentence(getattr(move, "observable_signal", "")
                                      or _capitalise(rival.signal_to_watch)
                                      or _capitalise(rival.disproof)),
            level=str(getattr(move, "level", "") or "L1")))
    return tuple(out[:6])


def _capitalise(text: str) -> str:
    text = (text or "").strip()
    return text[:1].upper() + text[1:] if text else text


def _level4_legacy(name, profile, selection, documents=()
                   ) -> Tuple[CompetitorRead, ...]:
    """§13/§14/§15. Never "no competitor's own account was retrieved".

    TWO SOURCES OF A RIVAL, AND THEY ARE NOT INTERCHANGEABLE.

    First, the rivals THIS COMPANY NAMED. `external_intel.competitor_finder`
    reads the Competition discussion out of the periodic filing the run
    already retrieved and returns the names with the overlap sentence
    attached. That is the company's own account of its market -- signed,
    dated and quotable -- and it is the only source that produces
    Cloudflare's actual rivals rather than a list of firms that happen to
    share its business model.

    Second, and only to fill a gap, the manifest's classified peers. Those
    are peers, not rivals, and the row says so: for Cloudflare the peer set
    is Adobe, Constellation and Databricks, none of which a Cloudflare
    customer is choosing between. Presenting them as competitors was the
    company-specificity defect in miniature -- correct by construction,
    wrong about the company.

    A competitive read is still a statement about market STRUCTURE, so it is
    produced whether or not either source yields a name. What retrieval
    decides is the standing, which is carried on every row.
    """
    moves = {str(getattr(m, "actor", "")).lower(): m
             for m in (selection.adversary or ())}
    out, seen = [], set()

    for named in _named_rivals(name, documents):
        rival_name = _clean(named.get("name"))
        if not rival_name or rival_name.lower() in seen:
            continue
        seen.add(rival_name.lower())
        move = moves.get(rival_name.lower())
        out.append(CompetitorRead(
            name=rival_name,
            why_a_rival=_sentence(
                f"{name} names it as a competitor in its own filing — "
                f"{_lower_first(named.get('overlap', ''))}"),
            exposure=_sentence(named.get("decision_implication", "")
                               or _default_exposure(profile, rival_name)),
            likely_response=_sentence(
                _clean(getattr(move, "action", ""))
                or _default_response(profile.business_model_class, rival_name)),
            response_likelihood=_likelihood(profile, move),
            counter_move=_sentence(getattr(move, "countermeasure", "")
                                   or _default_counter(profile)),
            signal_to_watch=_sentence(getattr(move, "observable_signal", "")
                                      or _default_signal(profile)),
            level=str(getattr(move, "level", "") or "L1")))

    for rival in (profile.strategic_competitors or ()):
        if len(out) >= 4:
            break
        if rival.name.lower() in seen:
            continue
        seen.add(rival.name.lower())
        move = moves.get(rival.name.lower())
        out.append(CompetitorRead(
            name=rival.name,
            why_a_rival=_sentence(
                f"Not named by {name} in what this run read. It is carried "
                f"as a structural peer rather than a stated rival: "
                f"{_lower_first(rival.why)}"),
            exposure=_sentence(getattr(move, "impact", "")
                               or _default_exposure(profile, rival.name)),
            likely_response=_sentence(
                _clean(getattr(move, "action", ""))
                or _default_response(profile.business_model_class, rival.name)),
            response_likelihood=_likelihood(profile, move),
            counter_move=_sentence(getattr(move, "countermeasure", "")
                                   or _default_counter(profile)),
            signal_to_watch=_sentence(getattr(move, "observable_signal", "")
                                      or _default_signal(profile)),
            level=str(getattr(move, "level", "") or "L1")))
    return tuple(out[:5])


def _routed(refusals) -> Tuple[tuple, ...]:
    """§6. The refused candidates, grouped under the section they belong to.

    Building the routing and never calling it would be the shape of defect
    this codebase keeps finding: a capability with no production caller reads
    as done and shows a reader nothing.
    """
    try:
        from intent_engine.executive.competitive_qualification import routed
        out = []
        for section, rows in sorted(routed(refusals or ()).items()):
            for row in rows[:3]:
                out.append((section, row.candidate, row.reason))
        return tuple(out[:8])
    except Exception:                                       # noqa: BLE001
        return ()


def _named_rivals(company: str, documents, profile=None,
                  refusals=None) -> Tuple[dict, ...]:
    """Rivals this company named, from evidence the run already holds.

    Never raises: a competitive read that disappears because an extractor
    threw is the failure mode this whole module exists to remove.
    """
    if not documents:
        return ()
    # ONLY THE SUBJECT'S OWN DOCUMENTS MAY NAME THE SUBJECT'S RIVALS.
    #
    # MEASURED LIVE on ebd0a6f: Meta's introduction read "contested most
    # directly by AT&T Inc, Alphabet Inc". Neither is in the validation
    # manifest and neither was named by Meta. They are the FILERS of
    # third-party filings the run retrieved because those filings mention
    # Meta — and this extractor was handed every document in the run, so it
    # read AT&T's own 10-K, found "AT&T Inc" written throughout it, and
    # returned the author as the subject's competitor.
    #
    # A claim belongs to whoever made it. `competitive_ladder.competition_text`
    # already documents this discriminator for the same reason — a third
    # party's Competition section describes THEIR market — and this producer,
    # which feeds rung 1 and therefore outranks everything, never got it.
    own = [d for d in documents
           if str((d or {}).get("source_class") or "")
           in ("investor_material", "executive_statement", "company_owned")]
    if not own:
        return ()
    try:
        from intent_engine.external_intel.competitor_finder import (
            find_competitors)
        # §7. THE BUSINESS MODEL DECIDES WHETHER A LENDER IS A RIVAL. It is
        # passed rather than inferred here because the qualification asks
        # what the SUBJECT sells, and only the profile knows.
        found = find_competitors(
            own, subject=company, limit=4,
            refusals=refusals,
            business_model=str(getattr(profile, "business_model_class", "")
                               or ""))
    except Exception:                                       # noqa: BLE001
        return ()
    out = []
    for competitor in found or ():
        name = _clean(getattr(competitor, "name", ""))
        if not name or name.lower() == company.lower():
            continue
        out.append({
            "name": name,
            "overlap": _clean(getattr(competitor, "overlap", "")),
            "decision_implication": _clean(
                getattr(competitor, "decision_implication", "")),
            "relationship": _clean(getattr(competitor, "relationship", "")),
        })
    return tuple(out)


def _default_response(model, rival) -> str:
    return {
        "SUBSCRIPTION_SOFTWARE":
            f"{rival} matches on capability rather than on headline price, "
            f"because a public price cut is visible to its whole installed "
            f"base and a feature is not",
        "BALANCE_SHEET_OR_NETWORK":
            f"{rival} defends flow with distribution and incentives before it "
            f"moves the spread, because the spread is visible and hard to "
            f"restore",
        "DESIGN_AND_MANUFACTURE":
            f"{rival} responds on capacity and design wins rather than on "
            f"price, because price concessions persist across a product cycle",
        "MANUFACTURE_AND_AFTERMARKET":
            f"{rival} competes on total cost of ownership and dealer support "
            f"rather than machine price, because the annuity is worth more "
            f"than the unit",
        "COMMODITY_PRODUCER":
            f"{rival} responds with volume, not price, because it does not set "
            f"the price",
        "BRANDED_CONSUMER":
            f"{rival} answers with trade investment and promotion before list "
            f"price, because list price is hard to take back",
        "CONTRACTED_OR_RATE_BASE_ASSETS":
            f"{rival} competes for the next contract or rate case rather than "
            f"for existing volume, because existing volume is contracted",
        "PEOPLE_OR_ROUTE_BASED_SERVICES":
            f"{rival} competes on capacity and service level, because "
            f"utilisation is the constraint on both sides",
        "REGULATED_PRODUCT_OR_PROVIDER":
            f"{rival} competes on access and evidence rather than price, "
            f"because the payer decides the realised price",
    }.get(model, f"{rival} responds within the same competitive structure")


def _default_exposure(profile, rival) -> str:
    drivers = profile.primary_revenue_drivers or ()
    if drivers:
        return (f"the exposure is on {drivers[0]}, which is where this "
                f"business's revenue is decided")
    return "the exposure is on the revenue drivers of this business model"


def _default_counter(profile) -> str:
    levers = profile.primary_management_levers or ()
    if levers:
        return (f"the available counter-move is {levers[0]}, which management "
                f"controls directly")
    return "the counter-move is whichever lever management controls directly"


def _default_signal(profile) -> str:
    evidence = profile.relevant_evidence_types or ()
    if evidence:
        return (f"watch {evidence[0]} — that is where a move of this kind "
                f"becomes visible from outside the company")
    return "watch for the first public disclosure of a change in terms"


def _likelihood(profile, move) -> str:
    """LOW/MEDIUM/HIGH, never a fabricated probability (§14).

    A QRE-style number needs a payoff parameterisation, and nothing in the
    public record supplies one. A band with a stated reason is defensible;
    "62%" is not.
    """
    if move is not None and getattr(move, "evidence", ""):
        return "HIGH"
    structure = str(profile.industry_structure or "").lower()
    if "few" in structure or "concentrated" in structure:
        return "HIGH"
    if "many" in structure:
        return "MEDIUM"
    return "MEDIUM"


def _as_clause(text: str) -> str:
    """A question embedded mid-sentence, without its question mark.

    "The open question is what to charge?. The lever ..." -- a question mark
    and a full stop touching is the signature of a template that concatenated
    two finished sentences.
    """
    return _clean(text).rstrip("?.!")


def _bare_question(name: str, question: str) -> str:
    """The decision question without its "For <Company>:" prefix.

    `decision_question` is authored to stand alone in a panel, so it carries
    the company name. Embedded in a sentence that already names the company
    it read "The decision is for Cloudflare, Inc.: what to charge" -- the
    company introduced twice in nine words.
    """
    flat = _clean(question)
    match = re.match(r"^for\s+.{1,80}?:\s*(.+)$", flat, re.I)
    return _clean(match.group(1)) if match else flat


def _level5(name, selection, run_decision, standing) -> Statement:
    """The strategic decision. Bounded is still a decision (§4)."""
    headline = _usable(getattr(run_decision, "headline", ""))
    mechanism = _usable(getattr(run_decision, "mechanism", ""))
    question = _bare_question(name, selection.decision_question)
    if mechanism:
        # `question` ends in a question mark. Welding it into the middle of a
        # sentence produced "... what to charge, and for what? the decision
        # worth arguing about now." -- a question mark mid-clause followed by
        # a lower-case continuation.
        return Statement(
            _sentence(f"{_sentence(mechanism)} That is what puts "
                      f"{_as_clause(_lower_first(question))} in front of "
                      f"management now"),
            STRONGLY_INFERRED if standing == READ_SUPPORTED
            else BOUNDED_INFERENCE,
            "this run's reasoning over the retrieved record")
    if headline:
        return Statement(_sentence(headline), BOUNDED_INFERENCE,
                         "this run's reasoning")
    return Statement(
        _sentence(f"The decision in front of management is "
                  f"{_lower_first(question)}"),
        BOUNDED_INFERENCE, "business model and published record")


def _level6(name, profile, selection, run_decision, standing,
            observations) -> BoundedAction:
    """§7 — the bridge. Always produced, never a dead end."""
    scenario = (selection.scenarios or (None,))[0]
    lever = _clean(getattr(scenario, "lever", "")) or _clean(
        (profile.primary_management_levers or ("the primary lever",))[0])
    unknown = _usable(getattr(run_decision, "unsafe_because", "")) or _usable(
        getattr(run_decision, "limitation", ""))
    if not unknown:
        metrics = _METRICS.get(profile.business_model_class, ())
        unknown = (f"{metrics[0][0]} is not disclosed at the granularity the "
                   f"decision needs" if metrics else
                   "the size of the effect is not disclosed")
    known = _usable(getattr(run_decision, "mechanism", "")) or _clean(
        _first_clause(profile.business_model))
    confidence = ("SUPPORTED IN DIRECTION AND SIZE" if standing == READ_SUPPORTED
                  else "BOUNDED — supported in direction, not in size")
    # ONE RECOMMENDED MOVE, NOT TWO (§56, §91).
    #
    # When the run's own reasoning reached a decision it carries a
    # recommended next move -- "One check separates them: does a rising..."
    # -- and composing a second one here from the profile's levers put two
    # different recommendations in one product, on adjacent pages. The run's
    # move WINS whenever it exists: it is the one derived from this run's
    # evidence, and the composed one is the fallback for a run that reached
    # no decision at all.
    recommended = _usable(getattr(run_decision, "recommended_next_move", ""))
    return BoundedAction(
        causal_confidence=confidence,
        what_is_known=_sentence(known),
        what_remains_unknown=_sentence(unknown),
        why_it_matters=_sentence(
            f"it is the parameter that decides whether {_lower_first(lever)} "
            f"is worth making now or worth deferring, and the two answers "
            f"lead to different plans"),
        action_now=_sentence(recommended
                             or _action_now(profile, selection, lever)),
        minimum_viable_experiment=_sentence(_mve(profile, selection, unknown)),
        kill_switch=_sentence(getattr(scenario, "kill_switch", "")
                              or _kill_switch(profile)),
        falsifier=_sentence(_falsifier(profile, selection, run_decision)),
        voi_band=_voi(profile, standing, observations),
        guardrail=_sentence(
            f"commit no more than can be withdrawn inside one planning cycle "
            f"until the check below returns"))


def _action_now(profile, selection, lever) -> str:
    """A bounded action, in this company's own variables."""
    levers = profile.primary_management_levers or ()
    first = _lower_first(levers[0]) if levers else _lower_first(lever)
    return (f"move on {first} at a size that can be reversed inside one "
            f"planning cycle, and instrument it so the result is readable "
            f"before the next commitment")


def _mve(profile, selection, unknown) -> str:
    signals = selection.signals or ()
    target = (_lower_first(getattr(signals[0], "name", "")) if signals
              else "the primary revenue driver")
    return (f"run the change on one segment or one cohort, hold the rest "
            f"constant, and read {target} against the unchanged group for one "
            f"full cycle — that isolates the effect without committing the "
            f"whole book")


def _kill_switch(profile) -> str:
    drivers = profile.primary_revenue_drivers or ()
    driver = _lower_first(drivers[0]) if drivers else "the primary revenue driver"
    return (f"stop and reverse if {driver} moves against the treated group "
            f"while the control group holds — that is the change doing harm, "
            f"not the market")


def _falsifier(profile, selection, run_decision) -> str:
    """What would change our mind. Never "nothing"."""
    for candidate in (getattr(run_decision, "falsifier", ""),
                      getattr(run_decision, "next_test", "")):
        text = _usable(candidate)
        if text:
            return text
    evidence = profile.relevant_evidence_types or ()
    if evidence:
        return (f"a disclosure in {evidence[0]} showing the mechanism moving "
                f"in the opposite direction would overturn this reading")
    return ("a disclosure showing the mechanism moving in the opposite "
            "direction would overturn this reading")


def _voi(profile, standing, observations) -> str:
    if standing == READ_SUPPORTED:
        return VOI_LOW
    independent = sum(1 for o in observations
                      if str((o or {}).get("source_class") or "")
                      not in ("company_owned", "executive_statement",
                              "investor_material", ""))
    return VOI_HIGH if independent == 0 else VOI_MEDIUM


def _level7(name, profile, selection, run_decision) -> Tuple[Statement, ...]:
    out = []
    for signal in (selection.signals or ())[:3]:
        out.append(Statement(
            _sentence(f"{getattr(signal, 'name', '')} — "
                      f"{_lower_first(getattr(signal, 'why', ''))}"),
            STRONGLY_INFERRED, "business model"))
    for evidence in (profile.relevant_evidence_types or ())[:2]:
        out.append(Statement(
            _sentence(f"{evidence} — this is where a change in this business "
                      f"becomes visible from outside it"),
            STRONGLY_INFERRED, "business model"))
    return tuple(out[:5])


# --- §11 macro, with a transmission or not at all ---------------------------
def _macro(selection) -> Tuple[dict, ...]:
    """Only channels with a mechanism into THIS business.

    §11's rule is the whole point: a macro series attached because it exists
    is noise wearing a chart. `analysis_selection` already refuses a channel
    with no transmission, so this is a projection rather than a second filter.
    """
    out = []
    for t in (selection.transmission or ()):
        mechanism = _clean(getattr(t, "mechanism", ""))
        variable = _clean(getattr(t, "business_variable", ""))
        if not mechanism or not variable:
            continue
        out.append({
            "factor": _pretty(getattr(t, "channel", "")),
            "mechanism": mechanism,
            "business_variable": variable,
            "consequence": _clean(getattr(t, "decision_implication", "")),
            "standing": (OBSERVED if getattr(t, "observed_ids", ())
                         else BOUNDED_INFERENCE),
        })
    return tuple(out)


# --- §10 metrics ------------------------------------------------------------
def _metrics(model, observations, documents) -> Tuple[MetricExpectation, ...]:
    """What this KIND of business is judged on, and whether we have it.

    A metric absent here is an information priority, not a failure: §10's
    "never fail simply because one preferred metric is undisclosed".
    """
    haystack = " ".join(
        str((o or {}).get("excerpt") or "") for o in observations).lower()
    out = []
    for metric, why in _METRICS.get(model, ()):
        head = metric.split(" or ")[0].split(" and ")[0].lower()
        seen = head in haystack
        out.append(MetricExpectation(
            metric=metric, why_it_matters=_sentence(why),
            state=OBSERVED if seen else UNMEASURED))
    return tuple(out)


# --- §25/§39 the story ------------------------------------------------------
def _story(name, profile, selection, run_decision,
           observations, rivals_read=()) -> Tuple[Chapter, ...]:
    """Four blocks: what the model is, what made it scale, what changed,
    where it is exposed. No methodology language, no enums (§25).

    Deliberately NOT a founding history -- this composer has no dated
    corporate history and will not invent one. `history_rewind` handles dated
    material, under a vintage wall.
    """
    model = _lower_first(_first_clause(profile.business_model))
    leverage = _lower_first(_first_clause(profile.operating_leverage))
    structure = _lower_first(_first_clause(profile.industry_structure))
    rivals = _join([c.name for c in (rivals_read or ())][:3]
                   or [c.name for c in
                       (profile.strategic_competitors or ())][:3])
    lever = _lower_first((profile.primary_management_levers or ("its "
                          "primary lever",))[0])
    drivers = _join([_lower_first(d)
                     for d in (profile.primary_revenue_drivers or ())][:3])
    costs = _join([_lower_first(c)
                   for c in (profile.primary_cost_drivers or ())][:2])
    # NOTHING HERE REPEATS THE HEADER. The identity line already said what
    # the business runs on and who contests it; a chapter that says it again
    # is the reader paying twice for one sentence, and it was the first thing
    # a CEO read after the strategic read.
    out = [
        Chapter("model", "Where the money actually comes from",
                _sentence(f"Revenue is decided by "
                          f"{drivers or 'a small number of operating drivers'}, "
                          f"and whether that revenue becomes margin is decided "
                          f"by {costs or 'the cost base behind it'}. There is "
                          f"no other lever on the top line"),
                STRONGLY_INFERRED),
        Chapter("scale", "Why growth and profitability are one question",
                _sentence(f"{_capitalised(leverage)} So a decision that moves "
                          f"volume moves margin with it, and the two cannot be "
                          f"planned separately here"),
                STRONGLY_INFERRED),
        Chapter("market", "What the market rewards",
                _sentence(f"It sells into {structure}"
                          + (f", where the contest is most direct with "
                             f"{rivals}" if rivals else "")),
                STRONGLY_INFERRED),
    ]
    # THE TENSION IS A BUSINESS SENTENCE, NOT A NOTE ABOUT THE ANALYSIS.
    # `why_this_question` explains the SELECTION -- "it was ranked above
    # retention on the same evidence" -- which is methodology (§25) and read
    # as the product talking about itself in the middle of the story.
    tension = _usable(getattr(run_decision, "mechanism", ""))
    question = _lower_first(_bare_question(name, selection.decision_question))
    out.append(Chapter(
        "tension", "Where the strategy is exposed",
        _sentence(f"{_sentence(tension)} The lever management holds against "
                  f"that is {lever}") if tension else
        _sentence(f"The open question is {_as_clause(question)}. The lever "
                  f"management "
                  f"holds is {lever}, and the cost of pulling it is that the "
                  f"effect is visible to competitors before it is measurable "
                  f"internally"),
        BOUNDED_INFERENCE))
    return tuple(out)


# --- helpers ----------------------------------------------------------------
def _options(run_decision) -> Tuple[dict, ...]:
    """The two courses the run weighed, verbatim. Never composed."""
    out = []
    for option in (getattr(run_decision, "options", ()) or ())[:2]:
        label = _clean(getattr(option, "label", ""))
        if not label:
            continue
        out.append({
            "label": label,
            "what_it_means": _clean(getattr(option, "what_it_means", "")
                                    or getattr(option, "description", "")),
            "upside": _clean(getattr(option, "upside", "")),
            "cost": _clean(getattr(option, "cost", "")),
            "assumes": _clean(getattr(option, "assumes", "")),
        })
    return tuple(out)


def _run_contribution(observations, documents) -> str:
    if not documents and not observations:
        return _sentence("this run retrieved no source of its own, so the "
                         "reading rests on the established classification of "
                         "the business")
    return _sentence(f"this run read {len(documents)} document(s) and "
                     f"{len(observations)} passage(s) from them")


def _evidence_note(observations, documents) -> str:
    independent = sum(1 for o in observations
                      if str((o or {}).get("source_class") or "")
                      not in ("company_owned", "executive_statement",
                              "investor_material", ""))
    if independent:
        return _sentence(f"{independent} of the passages read came from a "
                         f"source the company does not control")
    return _sentence("no source outside the company's control was retrieved, "
                     "so magnitudes below are bounded rather than measured")


def _pretty(token) -> str:
    text = _clean(token)
    if not text or text == UNKNOWN:
        return ""
    if text.isupper() or "_" in text:
        return text.replace("_", " ").lower()
    return text


def _capitalised(text) -> str:
    """A sentence that starts like one. Bullets are composed from clauses
    that read correctly inside a sentence and wrongly at the start of one."""
    flat = _sentence(text)
    return flat[0].upper() + flat[1:] if flat else ""


def _join(items) -> str:
    items = [i for i in (items or ()) if i]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]
