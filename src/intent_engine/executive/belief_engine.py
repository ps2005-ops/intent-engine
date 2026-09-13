"""Form the market's beliefs about a company, then attack them.

WHERE A BELIEF COMES FROM, CONCRETELY
-------------------------------------
There is no consensus feed in this product and inventing one would be the
worst thing it could do. What there is, for a listed company, is the filed
record and its two dates -- so the market's belief is inferred the same way
the expectation model works: from what had actually been published.

    the record shows growth slowing and margin widening
        -> a holder of the consensus view expects the margin story to
           continue, because that is what the last two years rewarded
        -> that is a PROPOSITION, it implies OBSERVABLE THINGS, and a
           quarter can contradict it

That chain is labelled INFERRED and its derivation is written on the row. It
is never called a consensus, because nobody polled anyone.

HOW THIS AVOIDS SAYING THE SAME THING ABOUT EVERY COMPANY
----------------------------------------------------------
Template collapse in this programme has always come from keying output on
`business_model_class` alone, because twenty-one of the golden hundred are
subscription software and the class is the only thing they share. Every
proposition here is composed from FOUR inputs that vary within a class:

    the business model            (what kind of argument applies)
    the observed trajectory       (growth/margin, from the filed series)
    the contested ground          (the categories the company itself named)
    the metric the model turns on (what would show it first)

Cloudflare and Shopify are both subscription software. Their trajectories
differ, and their contested ground differs completely -- "on-premises network
hardware vendors" against a merchant's own storefront build. A proposition
naming both cannot be the same sentence twice.
"""
from __future__ import annotations

import hashlib
from typing import Optional, Sequence, Tuple

from . import assumption_graph as AG
from .beliefs import (
    ACTIVE, COMPETITIVE, COMPANY, CONFIDENCE_HIGH, CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM, CONTESTED, CUSTOMER, DOMINANT, ECONOMIC, HELD,
    INDUSTRY, INFERRED, MANAGEMENT, MARKET_EXPECTATION, MODELLED, OBSERVED,
    STRENGTHENED, TECHNOLOGY, UNRESOLVED, WEAKENED, BeliefChallenge,
    BeliefRefused, Explanation, ExplanationField, ImpossibleHypothesis,
    MarketBelief, MinimumViableExperiment,
)

CONTRACT = "belief_engine.v1"

ACCELERATING, SLOWING = "ACCELERATING", "SLOWING"
WIDENING, NARROWING = "WIDENING", "NARROWING"


def _belief_id(company: str, tag: str) -> str:
    digest = hashlib.sha1(f"{company}|{tag}".encode()).hexdigest()[:10]
    return f"mb_{digest}"


def _lower(text: str) -> str:
    """Lower the first letter — unless the word is a proper noun.

    "the contest Shopify has to win is against magento" reached the test
    output because the sentence frame lowered whatever it was handed, and
    what it was handed was a company name. A category may be lowered; a name
    may not.
    """
    text = (text or "").strip()
    if not text:
        return text
    first = text.split()[0]
    # A name keeps its capital: mixed case inside the token (eBay, PayPal), or
    # a capitalised word whose remaining letters are lower case and which is
    # followed by another capitalised word or nothing that looks like a noun
    # phrase. The conservative test is enough: leave anything capitalised that
    # is not a sentence-initial ordinary word.
    if first[:1].isupper() and (first[1:] != first[1:].lower()
                                or _looks_like_a_name(text)):
        return text
    return text[:1].lower() + text[1:]


#: Ordinary words that begin a category phrase and should be lowered. A
#: capitalised span that starts with one of these is a phrase, not a name.
_PHRASE_OPENERS = frozenset({
    "on-premises", "point", "public", "network", "content", "domain",
    "email", "the", "a", "an", "generic", "automation", "renewing",
    "non-bank", "independent", "keeping", "customers", "retailer",
    "substitute", "software", "scrap", "deferring", "rental",
})


def _looks_like_a_name(text: str) -> bool:
    first = text.split()[0].lower().strip(",.;:")
    return first not in _PHRASE_OPENERS


def _lc(text: str) -> str:
    """Lower the first letter of a SENTENCE FRAGMENT.

    Distinct from `_lower`, which protects proper nouns because it is handed
    identities. This one is handed observations — "Peers of the same class
    showing the same shape" — where the capital is only sentence position and
    keeping it mid-sentence reads as a typo.
    """
    text = (text or "").strip()
    return text[:1].lower() + text[1:] if text else text


#: Kinds where the alternative is genuinely NOT a company. "Banks" is a
#: category, but a category OF COMPANIES, and telling a bank that its real
#: competitor is not a company because it is banks is nonsense. What makes
#: the §5 question interesting is the customer's own team, their current
#: process, doing nothing, or a technology shift.
_NOT_A_COMPANY_KINDS = frozenset({
    "BUILD_IN_HOUSE", "MANUAL_WORKFLOW", "DO_NOTHING", "BEHAVIOUR_SHIFT",
    "AI_REPLACEMENT", "OPEN_SOURCE",
})


# ---------------------------------------------------------------------------
# What the record implies the market is expecting.
# ---------------------------------------------------------------------------

#: THE CENTRAL EXPECTATION, per observed state. What somebody reading only
#: the filed record would carry into next year -- and the metric that would
#: contradict it first, which is what makes it testable rather than a mood.
#: Each proposition is a COMPLETE CLAUSE that follows "That <Company>'s". A
#: first version stored fragments and composed them into "That Cloudflare's
#: the margin story continues", because half the entries began with a noun
#: and half with an article. The frame is fixed and every entry now fits it.
_EXPECTATION = {
    (ACCELERATING, WIDENING): (
        "growth and margin can improve together for another year, because "
        "they just did",
        "the incremental margin on the next block of revenue, which is what "
        "separates operating leverage from a favourable mix",
        "revenue growth holds while incremental margin falls — the shape of "
        "growth being bought rather than earned",
    ),
    (ACCELERATING, NARROWING): (
        "margin being given up now is buying a position that pays for "
        "itself later",
        "the cohort economics of the customers won during the spend, which "
        "is where 'later' either exists or does not",
        "a second year of the same spend without the retention or expansion "
        "it was supposed to buy",
    ),
    (SLOWING, WIDENING): (
        "margin improvement continues and carries the equity while growth "
        "recovers on its own",
        "whether there is a next growth vector being funded at all, which "
        "the investment line shows before the revenue line does",
        "margin flattening before growth reaccelerates, which would mean the "
        "cost was taken out of the thing that was going to grow",
    ),
    (SLOWING, NARROWING): (
        "current weakness is a cyclical trough rather than a structural "
        "reset, and the prior trajectory resumes",
        "whether the slowdown is arriving through volume or through price, "
        "because only one of those recovers with the cycle",
        "a third consecutive period of the same direction, which is longer "
        "than most cycles in this business take to turn",
    ),
}

#: HOW THE BUSINESS MODEL MAKES ITS MONEY, in the terms the belief needs.
#: Keyed on class, and combined with trajectory and contested ground so that
#: two companies of one class never produce one sentence.
_MODEL_ENGINE = {
    "ADVERTISING_PLATFORM": (
        "attention sold by auction to many independent bidders",
        "the price per impression the auction clears at, and how many "
        "impressions there are to sell",
        "impressions still growing while the price per impression falls"),
    "MULTI_ENGINE_PLATFORM": (
        "several businesses with different margins carried on one balance "
        "sheet",
        "which engine the operating profit came from, not what the "
        "consolidated top line did",
        "consolidated revenue growing while the high-margin engine slows"),
    "SCALE_RETAIL": (
        "buying scale converted into price, and price into traffic",
        "traffic and basket against the margin the volume was bought at",
        "comparable sales held only by giving back the margin"),
    "SUBSCRIPTION_SOFTWARE": (
        "renewal and expansion inside an installed base",
        "net revenue retention",
        "a cohort that renews at a lower rate than the one before it"),
    "BALANCE_SHEET_OR_NETWORK": (
        "the spread earned on flow across a balance sheet",
        "the spread earned against the cost of the deposits funding it",
        "deposit costs rising faster than asset yields reprice"),
    "DESIGN_AND_MANUFACTURE": (
        "design wins converting into volume at a defended price",
        "the order book and the price realised on it",
        "an order book that holds in units while price concedes"),
    "MANUFACTURE_AND_AFTERMARKET": (
        "an installed base that buys parts and service for decades",
        "the aftermarket attach rate on the installed fleet",
        "aftermarket revenue falling while the fleet is still growing"),
    "COMMODITY_PRODUCER": (
        "volume sold into a price nobody in the industry sets",
        "cash cost per unit against the marginal producer's",
        "the cost curve moving against us while price is flat"),
    "BRANDED_CONSUMER": (
        "a brand that supports a price the private label cannot",
        "the price gap held against own-label in the same aisle",
        "volume held only by narrowing the gap"),
    "REGULATED_PRODUCT_OR_PROVIDER": (
        "a protected position that ends on a known date",
        "the revenue concentrated in products nearing exclusivity loss",
        "the pipeline not replacing what exclusivity is about to remove"),
    "CONTRACTED_OR_RATE_BASE_ASSETS": (
        "contracted cash flows on assets with long lives",
        "the weighted remaining contract term",
        "renewals arriving at materially lower rates than the expiring book"),
    "PEOPLE_OR_ROUTE_BASED_SERVICES": (
        "utilisation of people or routes against a fixed cost base",
        "revenue per person or per route, against wage growth",
        "utilisation holding only because price was conceded"),
}

_DEFAULT_ENGINE = ("the core operating engine of the business",
                   "the operating metric the model turns on",
                   "the metric moving against the story for two periods")


def _engine_for(model: str) -> Tuple[str, str, str]:
    return _MODEL_ENGINE.get(model, _DEFAULT_ENGINE)


def form_beliefs(*, company: str, profile=None, state=None, ground=None,
                 as_of: str = "", stated: Sequence[dict] = ()
                 ) -> Tuple[MarketBelief, ...]:
    """The beliefs a reader of the record would be carrying.

    `state` is (growth, margin) from the filed series, or None when there is
    no series -- a private company. Absence degrades the basis and the
    confidence; it never produces a fabricated consensus.
    """
    model = getattr(profile, "business_model_class", "") or ""
    engine, metric, engine_break = _engine_for(model)
    out = []

    # --- 1. what the market expects, from the filed record -----------------
    if state and state in _EXPECTATION:
        proposition, watch, contradiction = _EXPECTATION[state]
        growth, margin = state
        try:
            out.append(MarketBelief(
                belief_id=_belief_id(company, "expectation"),
                subject_id=company,
                proposition=(
                    f"That {company}'s {proposition}."),
                belief_type=MARKET_EXPECTATION,
                source_basis=INFERRED,
                basis_detail=(
                    f"{company}'s own filed results show growth "
                    f"{growth.lower()} and margin {margin.lower()}. This is "
                    f"what a reader of that record carries into next year; "
                    f"nobody published it in these words and it is not a "
                    f"consensus estimate."),
                implied_expectations=(
                    f"{watch.capitalize()}.",
                    f"{engine.capitalize()} continues to behave as it has.",
                ),
                falsifiers=(f"{contradiction.capitalize()}.",),
                confidence=CONFIDENCE_MEDIUM,
                consensus_strength=DOMINANT,
                knowable_as_of=as_of,
                first_observed_at=as_of))
        except BeliefRefused:
            pass

    # --- 2. what the market believes about the competition ------------------
    if ground is not None and getattr(ground, "rivals", ()):
        rivals = ground.rivals
        grounded = [r for r in rivals if r.from_subject_words]
        headline = (grounded or list(rivals))[0]
        substitutes = [r for r in rivals if not r.is_a_firm
                       and r.rung not in ("STRUCTURAL_PEER",)]
        try:
            out.append(MarketBelief(
                belief_id=_belief_id(company, "competition"),
                subject_id=company,
                proposition=(
                    f"That the contest {company} has to win is against "
                    f"{_lower(headline.identity)}, and that holding that "
                    f"ground is what protects the economics."),
                belief_type=COMPETITIVE,
                source_basis=(OBSERVED if headline.is_attributed
                              or headline.from_subject_words else INFERRED),
                basis_detail=(
                    f"{headline.independence}. "
                    + (f"{company} names it directly."
                       if headline.from_subject_words else
                       "Read from how this business model competes.")),
                supporting_evidence_ids=(),
                implied_expectations=(
                    f"Wins and losses are decided against "
                    f"{_lower(headline.identity)} rather than somewhere else.",
                    f"{headline.why_it_matters.capitalize()}.",
                ),
                falsifiers=(
                    f"{headline.disproof.capitalize()}.",
                    (f"Deals are being lost to "
                     f"{_lower(substitutes[0].identity)} rather than to a "
                     f"vendor at all." if substitutes else
                     f"Losses cluster somewhere this reading does not name."),
                ),
                confidence=(CONFIDENCE_HIGH if headline.from_subject_words
                            else CONFIDENCE_LOW),
                consensus_strength=DOMINANT if headline.from_subject_words
                else CONTESTED,
                knowable_as_of=as_of, first_observed_at=as_of))
        except BeliefRefused:
            pass

    # --- 3. what management appears to believe, from its own words ---------
    for row in (stated or ())[:1]:
        quote = str(row.get("quote") or "").strip()
        source = str(row.get("source") or "the company's own material")
        if not quote:
            continue
        try:
            out.append(MarketBelief(
                belief_id=_belief_id(company, "management"),
                subject_id=company,
                proposition=(
                    f"That {company}'s own account of its position is the one "
                    f"the strategy is being run on."),
                belief_type=MANAGEMENT,
                source_basis=OBSERVED,
                basis_detail=f"Quoted from {source}.",
                supporting_evidence_ids=(str(row.get("evidence_id") or ""),),
                implied_expectations=(
                    "Capital and hiring follow the priority the company "
                    "states, rather than a different one.",
                    f"The measure that would show it — {metric} — moves in "
                    f"the direction the statement implies.",
                ),
                falsifiers=(
                    f"Spending and hiring disclosed in the next filing point "
                    f"somewhere the statement does not mention.",),
                confidence=CONFIDENCE_MEDIUM,
                consensus_strength="COMMON",
                knowable_as_of=as_of, first_observed_at=as_of))
        except BeliefRefused:
            pass

    # --- 4. the economic belief under the model ----------------------------
    try:
        out.append(MarketBelief(
            belief_id=_belief_id(company, "economics"),
            subject_id=company,
            proposition=(
                f"That {company}'s economics rest on {engine}, so that is "
                f"where a change would show up first."),
            belief_type=ECONOMIC,
            source_basis=INFERRED,
            basis_detail=(
                f"Follows from how a {_pretty(model)} business earns its "
                f"return; not a statement {company} made."),
            implied_expectations=(
                f"{metric.capitalize()} is the measure that moves before the "
                f"headline does.",),
            falsifiers=(f"{engine_break.capitalize()}.",),
            confidence=CONFIDENCE_MEDIUM,
            consensus_strength="COMMON",
            knowable_as_of=as_of, first_observed_at=as_of))
    except BeliefRefused:
        pass
    return tuple(out)


def _pretty(token: str) -> str:
    return (token or "").replace("_", " ").lower() or "business"


# ---------------------------------------------------------------------------
# The attack.
# ---------------------------------------------------------------------------

#: The families §5 requires the search to cover. Each entry is a QUESTION and
#: the mechanism that would make it true; the engine binds them to the
#: company's own contested ground and trajectory before they become
#: hypotheses, and discards any it cannot bind.
_FAMILIES = (
    ("growth_destroys_value",
     "that winning more customers of the kind recently won destroys value "
     "rather than creating it",
     "acquisition cost is recovered over a life that has been shortening, so "
     "each additional customer of that type consumes cash the cohort never "
     "returns",
     "cohort payback lengthening while the headline customer count rises"),
    ("fewer_customers",
     "that the better business serves fewer customers at a higher price",
     "serving the long tail consumes support and roadmap capacity priced for "
     "a segment that cannot pay for it",
     "gross margin by segment, where the smallest tier is the one that dilutes"),
    ("price_not_volume",
     "that price, not acquisition, is the constraint on growth",
     "the product is under-priced relative to the value it defends, so every "
     "additional unit of demand arrives at a margin that cannot fund the "
     "capacity to serve it",
     "win rates that barely move when discount depth changes"),
    ("onboarding_not_acquisition",
     "that activation rather than acquisition is where the growth is lost",
     "customers are bought and then fail to reach the point where the "
     "product becomes hard to remove, so the funnel's leak is behind the sale "
     "rather than in front of it",
     "time-to-first-value diverging between cohorts that renew and cohorts "
     "that do not"),
    ("complexity_kills_expansion",
     "that product breadth is suppressing expansion rather than driving it",
     "each additional capability raises the cost of the decision to expand, "
     "so the customer stops at the module they understand",
     "expansion concentrated in the first two products regardless of how many "
     "are sold"),
    ("become_infrastructure",
     "that the business is worth more as infrastructure others build on than "
     "as the application itself",
     "the durable position is the layer everyone needs and nobody wants to "
     "run, and application margin is competed away above it",
     "usage growing faster through programmatic access than through the "
     "product's own interface"),
    ("competitor_is_not_a_company",
     "that the real competitor is not a company at all",
     "the customer's alternative is their own team, their current process, or "
     "doing nothing, none of which appears in a competitive win/loss review",
     "closed-lost reasons dominated by no-decision rather than by a named "
     "vendor"),
    ("ai_removes_the_need",
     "that automation removes the need for this product rather than expanding "
     "it",
     "the task the product supports is absorbed into a general capability the "
     "customer already pays for, so the budget line disappears before the "
     "contract does",
     "usage per seat falling in the accounts that adopted automation earliest"),
    ("ai_expands_the_market",
     "that automation expands this market faster than it erodes it",
     "the cost of the work falls far enough that buyers who never could "
     "justify it now can, and volume arrives from outside the current market",
     "new logos arriving from segments the current ICP excludes"),
    ("moat_becomes_liability",
     "that what protects the position today is what will trap it",
     "the asset that makes the product hard to replace is also what makes it "
     "hard to change, and the switching cost that holds customers holds the "
     "roadmap too",
     "the longest-tenured accounts adopting new capability slowest"),
)


def _hypotheses(company: str, model: str, ground, state) -> Tuple[
        ImpossibleHypothesis, ...]:
    """Bind the families to THIS company, and drop the ones that will not bind.

    §5 says these are questions, not findings, and §21 adds
    IMPOSSIBLE_HYPOTHESIS_GENERIC as a defect. A family that cannot be
    attached to something this run actually holds -- a contested category, a
    trajectory, a business model -- produces exactly the generic sentence that
    defect names, so it is not produced at all.
    """
    rivals = list(getattr(ground, "rivals", ()) or ())
    non_firm = [r for r in rivals if r.kind in _NOT_A_COMPANY_KINDS]
    named = [r for r in rivals if r.from_subject_words or r.is_attributed]
    engine, metric, _break = _engine_for(model)
    growth = (state or ("", ""))[0]
    out = []

    def make(hypothesis, mechanism, plausible, observation, falsifier,
             relevance, test, value=CONFIDENCE_MEDIUM):
        try:
            out.append(ImpossibleHypothesis(
                hypothesis=hypothesis, mechanism=mechanism,
                why_plausible=plausible,
                expected_observations=(observation,),
                falsifier=falsifier, decision_relevance=relevance,
                test=test, confidence=CONFIDENCE_LOW,
                information_value=value))
        except BeliefRefused:
            pass

    # The competitor-is-not-a-company family binds only when the ladder
    # actually found a non-firm alternative for THIS company.
    if non_firm:
        alt = non_firm[0]
        make(
            f"What if what actually takes {company}'s decisions away is not "
            f"a competing vendor at all — it is {_lower(alt.identity)}?",
            alt.mechanism,
            (f"The competitive ladder for {company} reaches "
             f"{_lower(alt.identity)} without needing a vendor to exist, and "
             f"{alt.why_it_matters}."),
            "Closed-lost reasons dominated by no-decision rather than by a "
            "named vendor.",
            alt.disproof,
            "It decides whether the answer is a better product or a better "
            "case for change, which are different investments.",
            "Re-code the last two quarters of closed-lost by whether a "
            "competing vendor was actually evaluated.",
            value="HIGH")

    # Price-versus-acquisition binds to the trajectory: it is only an
    # interesting question when growth is the thing being managed.
    if growth:
        make(
            f"What if price rather than acquisition is what limits "
            f"{company}?",
            "the product is priced below what it defends, so incremental "
            "demand arrives at a margin that cannot fund serving it",
            (f"{company}'s record shows growth {growth.lower()}, and the "
             f"lever being pulled is usually volume because it is the one "
             f"that shows up fastest."),
            "Win rates that barely move when discount depth changes.",
            "Win rate falls materially in the discount bands where price was "
            "held.",
            "It decides whether the next quarter's plan adds capacity or "
            "changes the price book.",
            "Hold list price in one segment for a quarter and compare win "
            "rate against the discounted control.",
            value="HIGH")

    # The moat family binds where there is a stated contested ground to have
    # a moat against.
    if named:
        make(
            f"What if what protects {company} against "
            f"{_lower(named[0].identity)} is also what will trap it?",
            "the switching cost that holds customers holds the roadmap too, "
            "so the position becomes harder to defend the longer it is held",
            (f"{company}'s defensibility rests on {engine}, and the same "
             f"property that makes it hard to leave makes it hard to change."),
            "The longest-tenured accounts adopting new capability slowest.",
            "Tenured accounts adopt new capability at or above the rate of "
            "newer ones.",
            "It decides whether the roadmap defends the base or is "
            "constrained by it.",
            f"Compare adoption of the two most recent releases across tenure "
            f"deciles.")

    # Automation binds to every business, in both directions, because §5 asks
    # for both and answering only one is the biased half.
    make(
        f"What if automation removes the need for what {company} sells?",
        "the task is absorbed into a general capability the customer already "
        "pays for, so the budget line disappears before the contract does",
        f"{engine.capitalize()} assumes the work continues to be done the way "
        f"it is done now.",
        f"{metric.capitalize()} falling first in the accounts that adopted "
        f"automation earliest.",
        f"{metric.capitalize()} holds in exactly those accounts.",
        "It decides whether the roadmap absorbs the automation or is absorbed "
        "by it.",
        f"Split {metric} by adoption cohort and compare the earliest adopters "
        f"against the rest.",
        value="HIGH")
    make(
        f"What if automation expands {company}'s market faster than it erodes "
        f"it?",
        "the cost of the work falls far enough that buyers who could never "
        "justify it now can, so volume arrives from outside the current market",
        "The same shift that threatens the task also removes the reason most "
        "of the market never bought at all.",
        "New logos arriving from segments the current definition of the "
        "customer excludes.",
        "New logos continue to come from the existing segment definition.",
        "It decides whether to defend the current segment or to go and take "
        "the new one first.",
        "Classify one quarter of new logos against the current ICP and count "
        "how many fall outside it.")
    return tuple(out)


def _explanations(company: str, model: str, state, ground) -> Optional[
        ExplanationField]:
    """Competing causes for the fact the record actually shows.

    §7 forbids evidence -> conclusion in one step. The observation is taken
    from the filed trajectory so that the field is about something real, and
    the candidates are the ones that fit THAT trajectory rather than a
    standing list.
    """
    if not state:
        return None
    growth, margin = state
    engine, metric, _b = _engine_for(model)
    rivals = list(getattr(ground, "rivals", ()) or ())
    named = next((r for r in rivals if r.from_subject_words
                  or r.is_attributed), None)
    non_firm = next((r for r in rivals if not r.is_a_firm), None)

    if growth == SLOWING:
        question = f"Why is growth at {company} slowing?"
        observation = (f"{company}'s filed record shows growth slowing and "
                       f"margin {margin.lower()}.")
        candidates = [
            Explanation(
                hypothesis="Demand saturation in the segment already served",
                mechanism=("the addressable set of buyers who match the "
                           "current definition has largely been reached, so "
                           "the same motion returns less"),
                expected_if_true=("New logos falling while win rate holds.",),
                confidence=CONFIDENCE_MEDIUM,
                decision_implication="The answer is a new segment, not a "
                                     "bigger sales team.",
                cost_if_missed=("Hiring against a market that is already "
                                "served turns a growth problem into a cost "
                                "problem that takes a year to unwind."),
                severity="HIGH",
                test_cost="LOW"),
            Explanation(
                hypothesis="Pricing friction rather than demand",
                mechanism=("the price is above what the marginal buyer will "
                           "authorise without a business case they cannot "
                           "build"),
                expected_if_true=("Longer cycles concentrated in the smallest "
                                  "deal band.",),
                confidence=CONFIDENCE_MEDIUM,
                decision_implication="The answer is the price book, not the "
                                     "pipeline.",
                cost_if_missed="Discounting to fix a demand problem "
                               "permanently resets the price the base pays.",
                severity="MEDIUM",
                test_cost="LOW"),
            Explanation(
                hypothesis="Activation, not acquisition",
                mechanism=("customers are being won and are not reaching the "
                           "point where the product becomes hard to remove"),
                expected_if_true=("Retention diverging between cohorts with "
                                  "different time-to-first-value.",),
                confidence=CONFIDENCE_MEDIUM,
                decision_implication="The investment is in onboarding, which "
                                     "is not where growth budget usually goes.",
                cost_if_missed="Every additional customer bought while this "
                               "is true leaks at the same rate.",
                severity="HIGH",
                test_cost="MEDIUM"),
        ]
        if named:
            candidates.append(Explanation(
                hypothesis=f"Competitive displacement by "
                           f"{_lower(named.identity)}",
                mechanism=named.mechanism,
                supporting=((named.evidence[:200],) if named.evidence else ()),
                expected_if_true=("Losses concentrating in deals where this "
                                  "alternative was evaluated.",),
                confidence=(CONFIDENCE_MEDIUM if named.from_subject_words
                            else CONFIDENCE_LOW),
                decision_implication="The answer is product or packaging "
                                     "against a specific alternative.",
                cost_if_missed=("A position conceded in the segment that sets "
                                "the reference price for every other one."),
                severity="HIGH",
                test_cost="MEDIUM"))
        if non_firm:
            candidates.append(Explanation(
                hypothesis=f"The buyer is choosing "
                           f"{_lower(non_firm.identity)} instead",
                mechanism=non_firm.mechanism,
                expected_if_true=("Closed-lost dominated by no-decision "
                                  "rather than by a competitor.",),
                confidence=CONFIDENCE_LOW,
                decision_implication="The answer is a case for change, which "
                                     "is a different sales motion entirely.",
                cost_if_missed=("The whole competitive response is aimed at "
                                "an opponent that is not taking the deals."),
                severity="HIGH",
                test_cost="LOW"))
        candidates.append(Explanation(
            hypothesis="Budget pressure outside the company's control",
            mechanism=("the customer's own spending is constrained, so the "
                       "decision is deferred rather than lost"),
            expected_if_true=("Deferred deals returning when the constraint "
                              "lifts, rather than closing elsewhere.",),
            confidence=CONFIDENCE_LOW,
            decision_implication="The answer is to hold capacity rather than "
                                 "cut it.",
            cost_if_missed="Cutting into a deferral removes the capacity "
                           "needed to serve the recovery.",
            severity="MEDIUM",
            test_cost="LOW"))
    else:
        question = f"Why is growth at {company} holding up?"
        observation = (f"{company}'s filed record shows growth accelerating "
                       f"and margin {margin.lower()}.")
        candidates = [
            Explanation(
                hypothesis="The product is winning on its merits",
                mechanism=(f"{engine} is compounding, and each period's wins "
                           f"make the next period's easier"),
                expected_if_true=(f"{metric.capitalize()} improving alongside "
                                  f"the headline.",),
                confidence=CONFIDENCE_MEDIUM,
                decision_implication="Fund it further.",
                cost_if_missed="",
                severity="LOW",
                test_cost="LOW"),
            Explanation(
                hypothesis="Growth is being bought",
                mechanism=("spend is converting into revenue at a cost that "
                           "the cohort will not return over its life"),
                expected_if_true=("Incremental margin falling while revenue "
                                  "growth holds.",),
                confidence=(CONFIDENCE_MEDIUM if margin == NARROWING
                            else CONFIDENCE_LOW),
                decision_implication="The spend has to be earned back before "
                                     "it is repeated.",
                cost_if_missed=("A year of spend compounds into a cost base "
                                "sized for revenue that does not persist."),
                severity="HIGH",
                test_cost="MEDIUM"),
            Explanation(
                hypothesis="A cycle is flattering the result",
                mechanism=("demand in this market moves with a cycle, and the "
                           "current period is on the favourable side of it"),
                expected_if_true=("Peers of the same class showing the same "
                                  "shape in the same quarters.",),
                confidence=CONFIDENCE_LOW,
                decision_implication="Plan the cost base for the middle of "
                                     "the cycle, not this point in it.",
                cost_if_missed=("Capacity added at the top of a cycle is the "
                                "hardest cost to remove at the bottom."),
                severity="HIGH",
                test_cost="LOW"),
            Explanation(
                hypothesis="Mix, not performance",
                mechanism=("the improvement comes from what is being sold "
                           "rather than from selling it better"),
                expected_if_true=("The change concentrated in one product or "
                                  "geography rather than spread.",),
                confidence=CONFIDENCE_LOW,
                decision_implication="Do not generalise the win to the whole "
                                     "portfolio.",
                cost_if_missed="A plan built on a portfolio-wide improvement "
                               "that only one line actually delivered.",
                severity="MEDIUM",
                test_cost="LOW"),
        ]
    return ExplanationField(question=question, observation=observation,
                            explanations=tuple(candidates))


def challenge(belief: MarketBelief, *, company: str, model: str = "",
              ground=None, state=None, contradictions: Sequence[str] = ()
              ) -> Optional[BeliefChallenge]:
    """Attack one belief and report honestly what the attack did.

    THE DISPOSITION IS COMPUTED, NOT CHOSEN. A belief moves only when this
    run holds something that cuts against it. With no contradiction the
    disposition is STRENGTHENED when the attack was real and the belief
    survived it, and HELD when the attack could not be pressed -- and neither
    of those is a failure. A conventional belief that survives is the most
    usable thing a chief executive can be handed.
    """
    engine, metric, _b = _engine_for(model)
    hypotheses = _hypotheses(company, model, ground, state)
    contradiction = "; ".join(c for c in contradictions if c).strip()

    # THE CASE *FOR* THE BELIEF, NOT A RESTATEMENT OF WHERE IT CAME FROM.
    # The first version returned `basis_detail`, which the block already
    # prints under the belief itself, so the deployed page carried the same
    # paragraph twice under two different headings.
    support = (
        f"A holder of this view is reading the record correctly as far as it "
        f"goes: what it implies is "
        f"{_lc(belief.implied_expectations[0]).rstrip('.')}, and nothing in "
        f"what this run retrieved contradicts that."
        if belief.implied_expectations else
        f"Nothing in what this run retrieved contradicts it.")
    hidden = [
        f"That {_lower(engine)} continues to work the way it has.",
        f"That {metric} is measured the same way across the periods being "
        f"compared.",
    ]
    if ground is not None and getattr(ground, "rivals", ()):
        weak = [r for r in ground.rivals if not r.from_subject_words
                and not r.is_attributed]
        if weak:
            hidden.append(
                f"That {_lower(weak[0].identity)} behaves as this reading "
                f"assumes — nothing retrieved in this run establishes it.")

    alternatives = tuple(
        f"{h.hypothesis} {h.why_plausible}" for h in hypotheses[:3])

    if contradiction:
        disposition = WEAKENED
        confidence_after = CONFIDENCE_LOW
    elif hypotheses and belief.falsifiers:
        disposition = STRENGTHENED
        confidence_after = belief.confidence
    else:
        disposition = HELD
        confidence_after = belief.confidence

    try:
        return BeliefChallenge(
            belief_id=belief.belief_id,
            strongest_support=support,
            strongest_contradiction=(
                contradiction or
                (f"Nothing retrieved in this run cuts against it. The "
                 f"strongest available challenge is a possibility rather "
                 f"than evidence: {hypotheses[0].hypothesis}"
                 if hypotheses else
                 "Nothing retrieved in this run cuts against it, and no "
                 "alternative could be bound to what this run holds.")),
            hidden_assumptions=tuple(hidden),
            alternative_explanations=alternatives,
            unconventional_hypotheses=hypotheses[:3],
            falsifier=belief.falsifiers[0],
            expected_observation=(belief.implied_expectations[0]
                                  if belief.implied_expectations else ""),
            missing_information=(
                f"{metric.capitalize()} is not disclosed at the granularity "
                f"that would settle this from outside the company."),
            value_of_information="HIGH" if disposition == WEAKENED else
            "MEDIUM",
            cheapest_test=(hypotheses[0].test if hypotheses else
                           f"Track {metric} across the next two reported "
                           f"periods against the direction this belief "
                           f"implies."),
            confidence_before=belief.confidence,
            confidence_after=confidence_after,
            disposition=disposition)
    except BeliefRefused:
        return None


def experiment_for(challenge_row: BeliefChallenge, field: Optional[
        ExplanationField], *, company: str) -> Optional[
            MinimumViableExperiment]:
    """§10. The cheapest thing that would separate the live hypotheses."""
    if field is None or len(field.explanations) < 2:
        return None
    cheapest = field.cheapest_to_test or field.explanations[0]
    dangerous = field.most_dangerous or field.explanations[-1]
    if cheapest.hypothesis == dangerous.hypothesis and \
            len(field.explanations) > 1:
        dangerous = next(e for e in field.explanations
                         if e.hypothesis != cheapest.hypothesis)
    # THE TEST SEPARATES THESE TWO READINGS, NOT WHATEVER THE FIRST
    # HYPOTHESIS HAPPENED TO SUGGEST. Taking the challenge's own cheapest
    # test produced one identical sentence for four different companies with
    # four different questions -- template collapse in the field §32 forbids
    # it in. What discriminates is the observation the two readings disagree
    # about, so the test is built from that.
    separator = (cheapest.expected_if_true[0] if cheapest.expected_if_true
                 else "")
    test = (
        f"Measure, for {company}, whether {_lc(separator).rstrip('.')} — "
        f"the one observation on which “{_lc(cheapest.hypothesis)}” and "
        f"“{_lc(dangerous.hypothesis)}” predict different things."
    ) if separator else challenge_row.cheapest_test
    try:
        return MinimumViableExperiment(
            strategic_question=field.question,
            competing_hypotheses=(cheapest.hypothesis, dangerous.hypothesis),
            test=test,
            required_data=(challenge_row.missing_information or
                           "Data the company already holds internally."),
            cost_band="LOW",
            time_band="One reporting period",
            discriminating_power=(
                f"The two readings predict different things: "
                f"{cheapest.expected_if_true[0] if cheapest.expected_if_true else 'one pattern'} "
                f"against "
                f"{dangerous.expected_if_true[0] if dangerous.expected_if_true else 'the other'}"),
            expected_information_gain="HIGH",
            decision_unlocked=cheapest.decision_implication or
            "which of the two responses to fund",
            stopping_rule=(
                f"Stop when one period's data separates the two. If it does "
                f"not separate them, stop anyway and record that the test "
                f"lacked the power — do not extend it looking for the answer "
                f"you expected."),
            if_result_a=cheapest.decision_implication,
            if_result_b=dangerous.decision_implication)
    except BeliefRefused:
        return None


def graph_for(*, company: str, model: str, state, ground,
              conclusion: str) -> AG.AssumptionGraph:
    """The chain under the run's own recommendation."""
    engine, metric, _b = _engine_for(model)
    growth = (state or ("", ""))[0]
    rivals = list(getattr(ground, "rivals", ()) or ())
    grounded = [r for r in rivals if r.from_subject_words or r.is_attributed]
    top = rivals[0] if rivals else None

    steps = [
        (f"{company}'s filed results",
         f"{engine.capitalize()} is what the economics rest on",
         AG.OBSERVED if state else AG.INFERRED,
         "The filed series is what this reading is computed from."),
        (f"{engine.capitalize()} is what the economics rest on",
         f"{metric.capitalize()} is the measure that moves first",
         AG.INFERRED,
         "Follows from how this business model earns its return."),
    ]
    if growth:
        steps.append((
            f"{metric.capitalize()} is the measure that moves first",
            f"The direction shown in the record ({growth.lower()}) persists "
            f"into the next period",
            AG.ASSUMED,
            "Nothing in this run tests whether the current direction "
            "continues; it is the step the whole recommendation rests on.",
            f"Take the last four reported periods for {company} and count how "
            f"often the direction of {metric} carried into the following one. "
            f"A direction that persisted in fewer than three of four is not a "
            f"trend the plan can lean on."))
    if top is not None:
        steps.append((
            f"The direction shown in the record ({growth.lower()}) persists "
            f"into the next period" if growth else
            f"{metric.capitalize()} is the measure that moves first",
            f"{top.identity} is where the contest is actually decided",
            AG.OBSERVED if (grounded and top in grounded) else AG.UNTESTED,
            (f"{top.independence}." if (grounded and top in grounded) else
             f"Read from the business model — no retrieved source in this "
             f"run establishes it."),
            (f"Re-code one quarter of closed-lost deals by which alternative "
             f"was actually evaluated. If {top.identity} appears in fewer "
             f"than a fifth of them, the contest is being fought somewhere "
             f"else.")))
        steps.append((
            f"{top.identity} is where the contest is actually decided",
            conclusion,
            AG.INFERRED,
            "The recommendation follows from where the contest is and which "
            "measure moves first."))
    else:
        steps.append((
            f"{metric.capitalize()} is the measure that moves first",
            conclusion, AG.INFERRED,
            "The recommendation follows from which measure moves first."))
    return AG.build(conclusion, steps)


def analyse(*, company: str, profile=None, state=None, ground=None,
            as_of: str = "", stated: Sequence[dict] = (),
            conclusion: str = "") -> dict:
    """The whole belief pass for one run, as one object every surface reads.

    ONE OBJECT, BECAUSE THE SURFACES MUST NOT RE-DECIDE. Three surfaces
    deriving their own competing explanations from whatever field happened to
    be populated is exactly how this programme produced a page that argued
    with the page before it.
    """
    model = getattr(profile, "business_model_class", "") or ""
    beliefs = form_beliefs(company=company, profile=profile, state=state,
                           ground=ground, as_of=as_of, stated=stated)
    challenges = []
    for belief in beliefs:
        row = challenge(belief, company=company, model=model, ground=ground,
                        state=state)
        if row is not None:
            challenges.append(row)
    field = _explanations(company, model, state, ground)
    primary = challenges[0] if challenges else None
    experiment = (experiment_for(primary, field, company=company)
                  if primary else None)
    graph = graph_for(company=company, model=model, state=state, ground=ground,
                      conclusion=conclusion or
                      f"What {company} should do about it") if conclusion \
        else None
    return {
        "contract": CONTRACT,
        "company": company,
        "beliefs": beliefs,
        "challenges": tuple(challenges),
        "explanations": field,
        "experiment": experiment,
        "graph": graph,
    }
