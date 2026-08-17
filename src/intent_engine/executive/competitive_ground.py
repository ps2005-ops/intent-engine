"""Assemble the competitive ladder for one run.

WHAT THIS DOES THAT THE OLD PATH DID NOT
----------------------------------------
The old `_level4` had exactly two sources: firms the subject named (almost
always none, because filings name categories) and the manifest's structural
peers (always available, never this company's rivals). Two sources, one of
which was nearly always empty, is why five of seven golden companies fell to
the peer list and capped `company_specificity` at 8.0.

This assembles from five, in ladder order, and stops adding once the ground
is covered:

    1  firms the subject named            (competitor_finder, unchanged)
    2  what customers migrated off        (migration sentences)
    5  categories the subject contests    (the subject's own taxonomy)
    6/7/8  substitutes, build, displacement (from the subject's own language)
    9  structural peers                   (last, and labelled as such)

Rungs 3 and 4 -- a rival's filing, an analyst -- are reached by the existing
third-party filing path when it yields; they are not synthesised here.

WHY A MECHANISM IS COMPUTED AND NOT WRITTEN
-------------------------------------------
`Rival` refuses to exist without a mechanism and a disproof. Those could have
been one constant string each, which is how a named heuristic becomes a
constant. They are derived instead from the KIND of alternative and the
business model, because how a point-solution vendor takes a customer away is
genuinely different from how an in-house build does, and a reader who is told
both in the same words learns nothing from either.
"""
from __future__ import annotations

from typing import Optional, Sequence, Tuple

from .competitive_ladder import (
    ADJACENT, AI_ENTRANT, AI_REPLACEMENT, BEHAVIOUR_SHIFT, BUILD_IN_HOUSE,
    CHANNEL_SHIFT, CONFIDENCE_HIGH, CONFIDENCE_LOW, CONFIDENCE_MEDIUM,
    CONTESTED_CATEGORY, DIRECT, DISPLACEMENT, DO_NOTHING, INTERNAL_BUILD,
    MANUAL_WORKFLOW, NAMED_BY_ANALYST, NAMED_BY_CUSTOMER, NAMED_BY_RIVAL,
    NAMED_BY_SUBJECT, OPEN_SOURCE, PEER, PLATFORM_BUNDLE, REGULATORY,
    STRUCTURAL_PEER, SUBSTITUTE, UNRESOLVED, WORKFLOW_SUBSTITUTE,
    CompetitiveGround, Rival, RivalRefused,
    competition_text, contested_categories, migrations, named_threats,
    subject_text,
)

CONTRACT = "competitive_ground.v1"

#: HOW EACH KIND OF ALTERNATIVE TAKES THE DECISION AWAY. Keyed on the kind,
#: not on the company, and phrased so the sentence is about the customer's
#: choice rather than about the rival's virtue.
_MECHANISM = {
    DIRECT: "wins the same evaluation on the same criteria, so the decision "
            "is a straight comparison and price is the visible axis",
    ADJACENT: "solves one part of the job well enough that the customer never "
              "runs the evaluation for the whole of it",
    SUBSTITUTE: "changes what the customer is buying, so a feature comparison "
                "never happens",
    BUILD_IN_HOUSE: "turns the decision into buy-versus-build, where the "
                    "customer's own engineering time is the competing price "
                    "and it is not on anyone's budget line",
    MANUAL_WORKFLOW: "is already in place and nobody is paid to defend it, so "
                     "the alternative to buying is doing nothing differently",
    DO_NOTHING: "leaves the customer where they are, which costs them nothing "
                "this quarter and is the outcome most evaluations reach",
    PLATFORM_BUNDLE: "includes the capability in something the customer has "
                     "already bought, so the comparison is against zero "
                     "marginal price rather than against the product",
    OPEN_SOURCE: "sets the price the customer compares against to nothing, so "
                 "what is sold is support and assurance rather than function",
    CHANNEL_SHIFT: "reaches the customer without us, so the relationship "
                   "moves before the revenue does",
    AI_REPLACEMENT: "automates the task the product exists to support, so the "
                    "budget moves before the contract lapses",
    AI_ENTRANT: "builds the same outcome at a cost structure the incumbent "
                "cannot match without repricing its own base",
    REGULATORY: "is available on terms set outside the market, so the "
                "commercial comparison is not the one being made",
    BEHAVIOUR_SHIFT: "removes the occasion for the purchase rather than "
                     "winning it",
    PEER: "operates the same business model, which sets the terms investors "
          "compare us on even when no customer chooses between us",
}

#: WHAT WOULD SHOW THIS IS NOT A REAL ALTERNATIVE. A disproof, per kind. Each
#: names something observable, because a disproof that cannot be observed is
#: a rhetorical hedge.
_DISPROOF = {
    DIRECT: "win rates hold in competitive deals where this category is on "
            "the shortlist",
    ADJACENT: "customers who buy the point product still buy the platform "
              "within the same budget cycle",
    SUBSTITUTE: "the substitute's share of the job does not rise as our "
                "renewals come up",
    BUILD_IN_HOUSE: "customers who built it in-house migrate back, or their "
                    "build never reaches production",
    MANUAL_WORKFLOW: "new logos come from teams who had a manual process, "
                     "rather than from teams replacing another vendor",
    DO_NOTHING: "the share of evaluations that close at all is stable rather "
                "than falling",
    PLATFORM_BUNDLE: "accounts that own the bundle renew with us anyway, "
                     "which says the bundled version is not sufficient",
    OPEN_SOURCE: "paid conversion from self-hosted deployments holds",
    CHANNEL_SHIFT: "direct volume does not grow at the channel's expense",
    AI_REPLACEMENT: "usage per customer holds as automation spreads through "
                    "the same accounts",
    AI_ENTRANT: "entrants do not appear on shortlists, or appear and lose on "
                "something other than price",
    REGULATORY: "the mandated alternative's share does not move after the "
                "rule changes",
    BEHAVIOUR_SHIFT: "the underlying occasion for the purchase holds in the "
                     "cohorts where behaviour has changed most",
    PEER: "our multiple moves on our own results rather than on the peer "
          "group's",
}

#: WHY A CHIEF EXECUTIVE SHOULD CARE, per kind. The decision it bears on.
_WHY = {
    DIRECT: "sets the discount you have to authorise to hold a deal",
    ADJACENT: "decides whether the roadmap defends the whole job or one part "
              "of it",
    SUBSTITUTE: "decides whether the category you lead is the category the "
                "customer is buying",
    BUILD_IN_HOUSE: "decides whether the product is priced against a vendor "
                    "or against a salary",
    MANUAL_WORKFLOW: "decides whether the sales motion argues value or argues "
                     "displacement, which are different teams",
    DO_NOTHING: "decides whether the pipeline problem is competitive or "
                "is a case-for-change problem",
    PLATFORM_BUNDLE: "decides whether to partner with the platform or to "
                     "differentiate away from it, and you cannot do both",
    OPEN_SOURCE: "decides what is actually being sold, and therefore what the "
                 "list price defends",
    CHANNEL_SHIFT: "decides whether to defend the channel or to go around it "
                   "first",
    AI_REPLACEMENT: "decides whether the roadmap absorbs the automation or is "
                    "absorbed by it",
    AI_ENTRANT: "decides how much of the base you would reprice to close the "
                "gap, and whether that is survivable",
    REGULATORY: "decides how much of the plan should depend on a rule holding",
    BEHAVIOUR_SHIFT: "decides whether the market is being lost or is shrinking",
    PEER: "sets the comparison investors make when results are read",
}

#: The alternatives a business model always faces, whether or not its filing
#: mentions them. THESE ARE QUESTIONS THE LADDER MUST NOT SKIP -- §2 requires
#: internal build, do-nothing and displacement to be searched for explicitly
#: -- and they enter at rungs 6-8, labelled as readings of the model rather
#: than as anything the company said. When the subject's own words supply the
#: same kind, the subject's words win and this is not added.
_MODEL_ALTERNATIVES = {
    "SUBSCRIPTION_SOFTWARE": (
        ("The customer's own engineering", BUILD_IN_HOUSE, INTERNAL_BUILD),
        ("Renewing nothing and keeping the current process", DO_NOTHING,
         WORKFLOW_SUBSTITUTE),
    ),
    "BALANCE_SHEET_OR_NETWORK": (
        ("The customer's own treasury and banking desk", BUILD_IN_HOUSE,
         INTERNAL_BUILD),
        ("Non-bank providers reaching the customer directly", CHANNEL_SHIFT,
         DISPLACEMENT),
    ),
    "DESIGN_AND_MANUFACTURE": (
        ("Keeping the existing fleet running longer", DO_NOTHING,
         WORKFLOW_SUBSTITUTE),
        ("Rental and used equipment in place of a new purchase", SUBSTITUTE,
         WORKFLOW_SUBSTITUTE),
    ),
    "MANUFACTURE_AND_AFTERMARKET": (
        ("Independent service and will-fit parts", SUBSTITUTE,
         WORKFLOW_SUBSTITUTE),
        ("Deferring replacement and rebuilding instead", DO_NOTHING,
         WORKFLOW_SUBSTITUTE),
    ),
    "REGULATED_PRODUCT_OR_PROVIDER": (
        ("Generic and biosimilar entry after exclusivity", REGULATORY,
         DISPLACEMENT),
        ("The payer declining to reimburse the newer option", DO_NOTHING,
         WORKFLOW_SUBSTITUTE),
    ),
    "COMMODITY_PRODUCER": (
        ("Substitute materials at the customer's plant", SUBSTITUTE,
         DISPLACEMENT),
        ("Scrap, recycled and secondary supply", SUBSTITUTE,
         WORKFLOW_SUBSTITUTE),
    ),
    "BRANDED_CONSUMER": (
        ("Retailer own-label in the same aisle", SUBSTITUTE,
         WORKFLOW_SUBSTITUTE),
        ("The shopper trading down or buying nothing", BEHAVIOUR_SHIFT,
         DISPLACEMENT),
    ),
    "CONTRACTED_OR_RATE_BASE_ASSETS": (
        ("The counterparty self-supplying behind the meter", BUILD_IN_HOUSE,
         INTERNAL_BUILD),
        ("The contract not being renewed at the same terms", DO_NOTHING,
         WORKFLOW_SUBSTITUTE),
    ),
    "PEOPLE_OR_ROUTE_BASED_SERVICES": (
        ("The customer's own staff doing the work", BUILD_IN_HOUSE,
         INTERNAL_BUILD),
        ("Software removing the task from the route", AI_REPLACEMENT,
         DISPLACEMENT),
    ),
}

#: Every business model faces automation now. Carried separately so that a
#: model missing from the table above still gets the §2 AI question asked.
_AI_QUESTION = ("Automation absorbing the task itself", AI_REPLACEMENT,
                DISPLACEMENT)

#: §9. LEVEL-K: what the other side does, and what we do after that.
#:
#: Keyed on the KIND of alternative, because the reaction is a property of
#: what the alternative IS. A direct competitor can cut price; a spreadsheet
#: cannot, and modelling both with one sentence is the generic competitor
#: analysis §32 forbids. L0 is the current environment, L1 our move, L2 their
#: response, L3 our adaptation.
#:
#: NO NUMERIC PROBABILITIES. §9 forbids fabricating them and there is nothing
#: here to estimate one from.
_REACTION = {
    DIRECT: (
        "matches on capability rather than on headline price, because a "
        "public price cut is visible to its whole installed base and a "
        "feature is not",
        "hold list price and compete on the part of the job they have to "
        "build rather than buy",
        "discounting that appears in their public pricing rather than in "
        "individual deals"),
    ADJACENT: (
        "goes deeper on the one use case it already wins, and prices it "
        "below the platform's per-module equivalent",
        "price the platform against the SUM of the point products a customer "
        "would otherwise run, not against any one of them",
        "customers renewing the point product alongside us rather than "
        "instead of us"),
    SUBSTITUTE: (
        "does not respond at all, because it is not watching this market — "
        "which is what makes it dangerous",
        "compete on the outcome rather than on the category, since the "
        "customer is not comparing categories",
        "the substitute's share of the job rising in accounts where our "
        "usage is flat"),
    BUILD_IN_HOUSE: (
        "gets funded for one quarter, ships something that works, and then "
        "meets the maintenance cost nobody budgeted",
        "price against the fully-loaded cost of the build including the "
        "second year, and sell to the person who owns that budget",
        "build projects appearing in the accounts with the largest "
        "engineering teams first"),
    MANUAL_WORKFLOW: (
        "does nothing, because a process has no vendor to defend it — the "
        "decision simply never gets made",
        "sell the case for change to the person who owns the outcome, not "
        "the feature comparison to the person who owns the process",
        "deals closing as no-decision rather than as competitive losses"),
    DO_NOTHING: (
        "reasserts itself every time a budget cycle tightens, without anyone "
        "choosing it",
        "make the cost of the status quo visible in the customer's own "
        "numbers before the renewal conversation",
        "the share of evaluations reaching a decision at all"),
    PLATFORM_BUNDLE: (
        "includes a sufficient version at no marginal price, and does not "
        "need it to be good",
        "differentiate on the depth the bundle will not fund, and partner "
        "where the bundle is the distribution",
        "the bundled version's feature announcements, which telegraph the "
        "depth they intend to reach"),
    OPEN_SOURCE: (
        "improves at the rate of its community, which does not respond to "
        "our pricing at all",
        "sell assurance, support and the cost of not running it, and make "
        "the paid tier the operational one",
        "self-hosted deployments converting to paid, or not"),
    CHANNEL_SHIFT: (
        "reaches the customer directly and keeps the relationship, whether "
        "or not the economics are better",
        "decide whether to defend the channel or go around it first — doing "
        "both loses the channel and the customer",
        "direct volume growing at the channel's expense in the same cohort"),
    AI_REPLACEMENT: (
        "absorbs the task into something the customer already pays for, "
        "without ever entering this market",
        "move up to the decision the task supports, rather than defending "
        "the task",
        "usage per seat in the accounts that adopted automation earliest"),
    AI_ENTRANT: (
        "prices at a cost structure we cannot match without repricing our "
        "own base",
        "decide how much of the base is worth repricing, and whether the "
        "answer is survivable, before the entrant reaches the shortlist",
        "entrants appearing on shortlists at all, and what they win on"),
    REGULATORY: (
        "arrives on a known date and on terms set outside the market",
        "plan the revenue that depends on the rule separately from the "
        "revenue that does not",
        "the rule-making calendar rather than any competitor's behaviour"),
    BEHAVIOUR_SHIFT: (
        "does not respond, because it is customers changing rather than a "
        "rival acting",
        "find whether the occasion for the purchase is shrinking or moving, "
        "because those need opposite responses",
        "the underlying occasion in the cohorts that changed first"),
    PEER: (
        "reports on the same calendar and sets the comparison investors make",
        "control the comparison by disclosing the measure our model actually "
        "turns on, before the peer group's measure becomes the standard",
        "which metric analysts lead with when the peer group reports"),
}

#: How likely the response is, in words. A DIRECT competitor with a sales
#: force responds; a process does not respond at all, and saying "likely" of
#: it would be false.
_LIKELIHOOD = {
    DIRECT: "Likely, and quickly — this is a contested market with an "
            "incentive to respond",
    ADJACENT: "Likely, in the part of the market they already hold",
    SUBSTITUTE: "Unlikely as a deliberate response — the risk is that they "
                "are not responding to us at all",
    BUILD_IN_HOUSE: "Not a response — it is a decision made inside the "
                    "customer, on the customer's calendar",
    MANUAL_WORKFLOW: "No response is possible; there is nobody to respond",
    DO_NOTHING: "No response is possible; this is the default outcome",
    PLATFORM_BUNDLE: "Likely on the platform's own roadmap calendar, not on "
                     "ours",
    OPEN_SOURCE: "Not a response — the project does not price against us",
    CHANNEL_SHIFT: "Likely where the channel's economics are already thin",
    AI_REPLACEMENT: "Not a response — it is a shift in what is being bought",
    AI_ENTRANT: "Likely, and it will be visible in pricing before it is "
                "visible in share",
    REGULATORY: "Determined by the rule-making calendar",
    BEHAVIOUR_SHIFT: "Not a response — it is the market changing shape",
    PEER: "Not directed at us; it is how we are read",
}

_MAX_RIVALS = 6

#: HOW MANY ROWS ONE KIND MAY TAKE. Bank of America's filing lists fifteen
#: categories of direct competitor, and without this the whole ladder was six
#: rows of one kind -- an enumeration of a single sentence, which tells a
#: reader nothing they could not read in the filing. §2 asks the ladder to
#: cover the GROUND: a direct rival, a substitute, the in-house build and the
#: displacement are four different decisions, and a table that answers one of
#: them four times has answered one.
_MAX_PER_KIND = 2


def _confidence(rung: str) -> str:
    from .competitive_ladder import ATTRIBUTED, FROM_SUBJECT_WORDS
    if rung in ATTRIBUTED:
        return CONFIDENCE_HIGH
    if rung in FROM_SUBJECT_WORDS:
        return CONFIDENCE_HIGH
    if rung in (WORKFLOW_SUBSTITUTE, INTERNAL_BUILD, DISPLACEMENT):
        return CONFIDENCE_MEDIUM
    return CONFIDENCE_LOW


def _independence(rung: str, company: str) -> str:
    if rung == NAMED_BY_SUBJECT:
        return f"{company}'s own filing — not independent, and under an "\
               f"obligation to be accurate"
    if rung == CONTESTED_CATEGORY:
        return f"{company}'s own words — not independent, and it is the "\
               f"company's account of its market"
    if rung == NAMED_BY_CUSTOMER:
        return f"a customer account {company} published — the customer's "\
               f"experience, {company}'s choice to publish it"
    if rung == NAMED_BY_RIVAL:
        return "another filer's own document — independent of this company"
    if rung == NAMED_BY_ANALYST:
        return "an independent source"
    if rung == STRUCTURAL_PEER:
        return "the classified manifest — a peer set, not a retrieved claim"
    return "read from the business model, not retrieved"


def _make(identity, kind, rung, company, evidence="") -> Optional[Rival]:
    response, counter, signal = _REACTION.get(kind, _REACTION[DIRECT])
    try:
        return Rival(
            identity=identity, kind=kind, rung=rung,
            mechanism=_MECHANISM.get(kind, _MECHANISM[DIRECT]),
            evidence=evidence,
            independence=_independence(rung, company),
            confidence=_confidence(rung),
            why_it_matters=_WHY.get(kind, _WHY[DIRECT]),
            disproof=_DISPROOF.get(kind, _DISPROOF[DIRECT]),
            # §9. The row carries the reaction, so every consumer gets it —
            # the projection into `CompetitorRead` had it and the ladder
            # itself did not, which is how a detector reading the ladder
            # reported that no rival carried a response while the page showed
            # one.
            likely_response=f"{identity} {response}"
            if kind not in (MANUAL_WORKFLOW, DO_NOTHING, BEHAVIOUR_SHIFT,
                            AI_REPLACEMENT, OPEN_SOURCE)
            else f"This {response}",
            counter_move=counter,
            signal_to_watch=signal,
            response_likelihood=_LIKELIHOOD.get(kind, _LIKELIHOOD[DIRECT]),
            level="L2")
    except RivalRefused:
        return None


def build(company: str, profile, documents: Sequence[dict] = (),
          named_firms: Sequence[dict] = ()) -> CompetitiveGround:
    """The competitive ground for one run, assembled up the ladder."""
    documents = list(documents or ())
    rivals: list = []
    taken_kinds: dict = {}
    seen: set = set()

    def add(rival: Optional[Rival]) -> None:
        if rival is None or len(rivals) >= _MAX_RIVALS:
            return
        key = rival.identity.strip().lower()
        if not key or key in seen:
            return
        if taken_kinds.get(rival.kind, 0) >= _MAX_PER_KIND:
            return
        seen.add(key)
        taken_kinds[rival.kind] = taken_kinds.get(rival.kind, 0) + 1
        rivals.append(rival)

    # --- rung 1: firms the subject named ----------------------------------
    for firm in named_firms or ():
        name = str(firm.get("name") or "").strip()
        if not name:
            continue
        add(_make(name, DIRECT, NAMED_BY_SUBJECT, company,
                  evidence=str(firm.get("overlap") or "")))

    own_words = subject_text(documents)

    # --- rung 1: a dated threat the subject names against its own asset ----
    #
    # A filing may decline to name a competitor and still name the threat
    # exactly. Johnson & Johnson's Competition section says only that its
    # subsidiaries "compete with companies both locally and globally"; the
    # same document says biosimilar versions of STELARA are launching and
    # will keep reducing sales of it. The second is the competitive fact.
    for row in named_threats(own_words, company):
        add(_make(row["identity"], row["kind"], NAMED_BY_SUBJECT, company,
                  evidence=row["evidence"]))

    # --- rung 2: what customers migrated off ------------------------------
    for row in migrations(own_words, company):
        add(_make(row["left_behind"], row["kind"], row["rung"], company,
                  evidence=row["evidence"]))

    # --- rung 5: categories the subject says it contests -------------------
    all_categories = contested_categories(competition_text(documents, company),
                                          limit=12)
    for row in all_categories:
        add(_make(row["category"], row["kind"], CONTESTED_CATEGORY, company,
                  evidence=row["evidence"]))

    # --- rungs 6/7/8: the alternatives the model always faces --------------
    #
    # §2 requires internal build, do-nothing and displacement to be SEARCHED
    # FOR, not merely accepted when a filing volunteers them. They are added
    # only where the subject's own words have not already covered that kind,
    # so a company that named its in-house alternative keeps its own sentence.
    model = getattr(profile, "business_model_class", "") or ""
    for identity, kind, rung in (_MODEL_ALTERNATIVES.get(model, ())
                                 + (_AI_QUESTION,)):
        if taken_kinds.get(kind):
            continue
        add(_make(identity, kind, rung, company))

    # --- rung 9: structural peers, last and labelled -----------------------
    for peer in (getattr(profile, "strategic_competitors", ()) or ()):
        if len(rivals) >= _MAX_RIVALS:
            break
        add(_make(getattr(peer, "name", ""), PEER, STRUCTURAL_PEER, company))

    # THE NOTE DESCRIBES THE TABLE UNDER IT. Deriving it from one predicate
    # produced "No competitive statement by Shopify was retrieved" directly
    # above a row reading "Magento — named by a customer", which is a
    # contradiction on one screen. Attributed rows and the company's own
    # categories are different claims and the note now counts both.
    attributed = [r for r in rivals if r.is_attributed]
    categories = [r for r in rivals if r.rung == CONTESTED_CATEGORY]
    read_off_model = len(rivals) - len(attributed) - len(categories)
    parts = []
    if attributed:
        parts.append(f"{len(attributed)} named in evidence this run read")
    if categories:
        # The table is capped for breadth; the reader is told the real size of
        # the company's own list rather than being left to infer it.
        extra = (f" (of {len(all_categories)} it names)"
                 if len(all_categories) > len(categories) else "")
        parts.append(f"{len(categories)}{extra} quoted from {company}'s own "
                     f"account of the categories it competes with")
    if read_off_model:
        parts.append(f"{read_off_model} read from how this business model "
                     f"works, rather than from anything {company} said")
    # `str.capitalize` lower-cases the remainder, which turned "Bank of
    # America" into "bank of america" inside its own basis note.
    basis = (f"Of {len(rivals)} alternatives below: " + "; ".join(parts) + ".") \
        if parts else (
        f"Nothing about {company}'s competition was established in this run.")

    if attributed or categories:
        measurement = ""
    else:
        measurement = (
            f"Retrieve the Competition discussion from {company}'s most "
            f"recent annual filing, or a customer account naming what they "
            f"used before. Either moves this from a reading of the business "
            f"model to {company}'s own statement.")
    return CompetitiveGround(company=company, rivals=tuple(rivals),
                             next_measurement=measurement, basis_note=basis)
