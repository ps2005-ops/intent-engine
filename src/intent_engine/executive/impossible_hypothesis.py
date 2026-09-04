"""Hypotheses outside management's current assumption set. §5.

WHY THIS EXISTS
---------------
Measured across the 50-company gauntlet: `impossible_hypothesis` scored 0.0
on every company, because nothing produced one. Q&A had a route for the
question and the route pointed at `adversary`, which is a different object
answering a different question, so the board question "what could not be
true?" had no producer at all.

WHAT IT IS
----------
A heretical reading is not a prediction and not a claim. It is a proposition
management's own framing rules out by construction, stated with the economic
mechanism that would make it true, what would have to be observed for it to
be true, what argues against it, and the smallest experiment that would
settle it. Everything here is bounded and falsifiable; nothing is asserted.

HOW IT AVOIDS THE COLLAPSE THIS PROGRAMME KEEPS FINDING
-------------------------------------------------------
Template collapse is a SELECTION defect, not a wording one: five companies
got one sentence because one constant was interpolated five times. So the
selection here is a function of the SUBJECT'S OWN MEASURED ECONOMICS -- which
architecture fields the filing actually yielded, how many engines it runs,
whether a rival was established, what it says drives volume. Two companies
with different measured architectures cannot select the same set, and the
text carries the company's own particulars rather than a class noun.

A candidate whose precondition is not met is NOT emitted. Three companies
producing three, five and zero hypotheses is the correct behaviour: an
architecture nothing could be measured from cannot support a heresy either,
and saying so is better than inventing one.

NO MODEL CALL. NO CONSPIRACY. Every field is derived from measured inputs.
"""
from __future__ import annotations

import dataclasses
from typing import Optional, Tuple

CONTRACT = "impossible_hypothesis.v1"

#: Bounded plausibility. Never a number: nothing here supports a probability,
#: and §10 says name that rather than fabricate one.
CONCEIVABLE = "CONCEIVABLE"          #: the mechanism exists; little else
PLAUSIBLE = "PLAUSIBLE"              #: mechanism plus a supporting particular
LIVE = "LIVE"                        #: mechanism plus a contested position
BANDS = (CONCEIVABLE, PLAUSIBLE, LIVE)


@dataclasses.dataclass(frozen=True)
class ImpossibleHypothesis:
    """One proposition the current framing rules out, with its mechanism."""
    kind: str
    hypothesis: str
    mechanism: str
    why_missed: str
    evidence_for: str
    evidence_against: str
    plausibility: str = CONCEIVABLE
    upside: str = ""
    downside: str = ""
    falsifier: str = ""
    smallest_experiment: str = ""

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


def _lower(text: str) -> str:
    text = str(text or "").strip()
    return (text[0].lower() + text[1:]) if text else ""


#: A filing writes in the first person; this page writes about the filer.
#: Carrying "our customers" through unchanged makes the product sound like it
#: is speaking AS the company, which is exactly the voice a reader must be
#: able to distinguish from our own reading of it.
_FIRST_PERSON = (
    (" to our customers", ""), (" for our customers", ""),
    ("our customers", "its customers"), ("our clients", "its clients"),
    ("our products", "its products"), ("our services", "its services"),
    ("our solutions", "its solutions"), ("our network", "its network"),
    ("our business", "its business"), ("our ", "its "),
    ("we ", "it "), ("We ", "It "),
)


def _short(text: str, limit: int = 150) -> str:
    text = " ".join(str(text or "").split())
    for needle, replacement in _FIRST_PERSON:
        text = text.replace(needle, replacement)
    text = " ".join(text.split()).strip(" ,;:")
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "…"


def _band(supporting: bool, contested: bool) -> str:
    if contested and supporting:
        return LIVE
    return PLAUSIBLE if supporting else CONCEIVABLE


def _candidates(company, arch, rivals, belief) -> list:
    """Every heresy whose PRECONDITION this company's economics satisfies.

    Each entry is (precondition, builder). The precondition is a measured
    fact, so which heresies exist is a property of the company rather than of
    a class -- which is the whole difference between this and the collapse it
    was written after.
    """
    sold = _short(arch.what_is_sold) or ""
    customer = _short(arch.customer) or _short(arch.buyer) or ""
    unit = _short(arch.unit_of_sale) or ""
    volume = _short(arch.volume_driver) or ""
    pricing = _short(arch.pricing_mechanism) or ""
    growth_limit = _short(arch.growth_constraint) or ""
    rival = rivals[0] if rivals else ""
    contested = bool(rivals)
    segments = tuple(arch.segments or ())
    out = []

    # 1. Acquiring customers may destroy value.
    if volume or unit:
        driver = volume or f"adding {_lower(unit)}"
        out.append((
            "acquisition_destroys_value",
            f"Growth in {company}'s customer count may be reducing "
            f"enterprise value rather than building it.",
            f"{company} reports that volume comes from {_lower(driver)}. If "
            f"the cost of winning the marginal customer has risen faster "
            f"than what that customer returns over their life, every "
            f"additional one converts cash into a smaller claim on cash — "
            f"the income statement grows while the business shrinks.",
            "Management measures acquisition against revenue growth, which "
            "rises in exactly the case where this is true, so the metric "
            "that would show the damage is the metric being celebrated.",
            f"the filing attributes growth to {_lower(driver)} without "
            f"stating what that growth costs to obtain",
            "a rising contribution margin per cohort, or an acquisition "
            "cost falling in absolute terms, would each contradict it",
            _band(bool(volume), contested),
            "Stopping unprofitable acquisition raises free cash flow "
            "immediately and without a strategy change.",
            "Cutting acquisition in a market where share is durable "
            "forfeits a position that cannot be re-bought later.",
            "Cohort-level contribution margin, held flat or rising as "
            "acquisition spend rises, falsifies this.",
            "Rank the last four cohorts by fully-loaded acquisition cost "
            "and measure each one's gross profit to date."))

    # 2. Fewer customers may be worth more than more of them.
    if customer:
        out.append((
            "fewer_customers_worth_more",
            f"{company} may be worth more serving materially fewer "
            f"customers than it serves today.",
            f"Its customers are {_lower(customer)} — a population wide "
            f"enough that the cost to serve almost certainly is not uniform "
            f"across it. Where the dispersion is wide, a minority of "
            f"accounts can carry the whole contribution and the remainder "
            f"can consume it through support, delivery and churn.",
            "Customer count is reported as an achievement and rarely "
            "decomposed by profitability, so a shrinking count reads as "
            "failure whatever it does to profit.",
            "the filing describes a broad and heterogeneous customer base "
            "without stating what the least profitable part of it returns",
            "a flat cost-to-serve across account sizes would mean there is "
            "no unprofitable tail to shed",
            _band(bool(customer and (pricing or unit)), contested),
            "Retiring an unprofitable tail raises margin without winning a "
            "single new customer.",
            "The tail may be the funnel: today's small account can be next "
            "year's large one, and cutting it removes the pipeline.",
            "Cost-to-serve roughly equal across deciles falsifies this.",
            "Rank accounts into deciles by revenue and measure fully-loaded "
            "cost to serve for the top and bottom decile."))

    # 3. The highest-value customer may not be the one being served.
    if customer or segments:
        who = _lower(customer) if customer else \
            f"the buyers behind {segments[0]}"
        out.append((
            "wrong_customer",
            f"The most valuable customer for what {company} has built may "
            f"not be the customer it currently sells to.",
            f"The capability behind the product was built to serve "
            f"{who}. Capabilities are rarely specific to the buyer they "
            f"were built for, and an adjacent buyer with a more expensive "
            f"underlying problem can be worth more per unit of the same "
            f"delivered capability.",
            "The existing customer defines the roadmap, so the adjacent "
            "buyer never appears in the planning cycle that would find "
            "them.",
            "the filing describes the capability and the current buyer "
            "without evidence that alternatives were priced",
            "a capability tightly coupled to one buyer's workflow, or "
            "regulation that confines it, would each rule this out",
            _band(bool(customer and sold), contested),
            "A higher-value buyer reached with the existing capability "
            "changes unit economics without changing the product.",
            "Serving two buyers badly is a common way to lose the one that "
            "was working.",
            "A priced test with the adjacent buyer that returns no better "
            "than the current one falsifies this.",
            "Price the existing capability to one adjacent buyer segment "
            "and compare realised price per unit against today's."))

    # 4. The product may need to become a platform — or stop trying to be.
    if len(segments) > 1:
        out.append((
            "platform_inversion",
            f"{company}'s separately reported businesses may be worth more "
            f"as one platform others build on than as {len(segments)} "
            f"products it sells.",
            f"It reports {len(segments)} segments — "
            f"{', '.join(segments[:4])} — which means it already "
            f"operates the shared substrate underneath them. A substrate "
            f"that carries several first-party businesses can usually carry "
            f"third-party ones at close to zero marginal cost, and the "
            f"economics of the two are not the same.",
            "Segment reporting measures each business against its own "
            "P&L, so value created ACROSS segments has no line to appear "
            "on and is invisible to the reporting that governs investment.",
            f"the filing itself declares {len(segments)} reportable "
            f"segments over a common base",
            "genuinely unrelated segments with no shared substrate would "
            "mean there is nothing to open",
            _band(True, contested),
            "A platform monetises demand the first-party businesses would "
            "never have served themselves.",
            "Opening the substrate arms the competitors it currently "
            "excludes, and that is not reversible.",
            "No third party able to build anything of value on the shared "
            "base falsifies this.",
            "Expose one internal interface to a small set of external "
            "builders and measure what gets built in a quarter."))

    # 5. AI may remove the workflow the product sits inside.
    if sold or unit:
        thing = _lower(sold) if sold else _lower(unit)
        out.append((
            "workflow_eliminated",
            f"The workflow that {company}'s product sits inside may stop "
            f"existing rather than be improved.",
            f"It sells {thing}. A product priced against a human process "
            f"captures a share of that process's cost; when the process is "
            f"performed by a machine end to end, the customer is no longer "
            f"buying a better way to do it, and there is nothing left for "
            f"the price to be a share of.",
            "Competitive analysis compares against firms selling the same "
            "shape of product, and a workflow disappearing does not appear "
            "in any of them.",
            "the product is described in terms of the process it supports "
            "rather than the outcome it delivers",
            "a product priced against a measurable OUTCOME survives the "
            "process being automated and would contradict this",
            _band(bool(sold), contested),
            "Repricing against the outcome now, while the process still "
            "exists, is far cheaper than repricing after it does not.",
            "Repricing against outcomes exposes the firm to results it does "
            "not fully control.",
            "Customers continuing to buy the process-shaped product as "
            "automation spreads falsifies this.",
            "Offer one cohort outcome-based pricing and measure take-up "
            "against the existing basis."))

    # 6. The customer may internalise the work.
    if pricing or unit:
        basis = _lower(pricing) if pricing else _lower(unit)
        out.append((
            "customer_internalises",
            f"{company}'s most important competitor may be its own "
            f"customers deciding to do this themselves.",
            f"It charges on {basis}. A charge that scales with the "
            f"customer's own volume grows into a line item large enough to "
            f"justify a build, and the largest customers reach that "
            f"threshold first — which are the same accounts the revenue "
            f"depends on most.",
            "A customer who builds is recorded as churn, not as a "
            "competitive loss, so this never enters the competitive "
            "picture at all.",
            f"the pricing basis — {basis} — scales with the customer "
            f"rather than with what it costs to serve them",
            "a capability the customer cannot assemble — regulated, "
            "network-dependent, or data-dependent — would rule this out",
            _band(bool(pricing), contested),
            "Knowing the internalisation threshold lets the firm price "
            "underneath it deliberately rather than discover it in churn.",
            "Pricing to defeat a build can concede margin that was never "
            "actually at risk.",
            "Largest accounts showing no build activity at renewal "
            "falsifies this.",
            "Interview the five largest accounts about internal builds "
            "and compare their spend against a build's cost."))

    # 7. Doing nothing may be the real substitute.
    if growth_limit or not rivals:
        out.append((
            "do_nothing_substitute",
            f"The alternative most of {company}'s market chooses may be to "
            f"do nothing at all, not to buy from a competitor.",
            (f"Growth is described as depending on {_lower(growth_limit)}. "
             if growth_limit else
             "No rival was established from this company's own disclosures. ")
            + "Where the binding constraint is the buyer's willingness to "
              "change rather than a rival's offer, share is being taken "
              "from inertia, and inertia does not respond to competitive "
              "positioning.",
            "Win/loss analysis records losses against named competitors, "
            "so the largest category of loss — no decision — is not "
            "counted as a loss and never gets a strategy.",
            (f"the filing names {_lower(growth_limit)} rather than a rival "
             f"as what growth depends on" if growth_limit else
             "no competitor was established from the company's own filings"),
            "a market where most deals are contested by a named rival "
            "would contradict this",
            _band(bool(growth_limit), contested),
            "A strategy aimed at inertia addresses the largest available "
            "pool rather than the most visible one.",
            "Treating a genuinely contested market as an uncontested one "
            "loses deals that were winnable.",
            "A majority of losses going to named rivals falsifies this.",
            "Classify the last fifty closed-lost opportunities into "
            "'lost to a rival' and 'no decision'."))

    # 8. The profit engine may not be the revenue engine.
    if arch.revenue_engine and arch.profit_engine \
            and arch.revenue_engine != arch.profit_engine:
        out.append((
            "profit_engine_is_elsewhere",
            f"{company} may be a {arch.profit_engine} business that "
            f"finances itself by selling {arch.revenue_engine}.",
            f"Its own filing identifies {arch.revenue_engine} as the "
            f"largest business and {arch.profit_engine} as the one that "
            f"earns. When those differ, the segment that sets the "
            f"company's identity is not the segment that pays for it, and "
            f"investment tends to follow identity.",
            "Revenue is the number reported first and discussed most, so "
            "the smaller segment carrying the economics is managed as a "
            "supporting business.",
            f"the filing separates {arch.revenue_engine} and "
            f"{arch.profit_engine} into different reportable segments",
            "comparable margins across the two segments would mean there "
            "is no divergence to act on",
            LIVE if contested else PLAUSIBLE,
            "Capital allocated to the segment that actually earns "
            "compounds faster than capital following the revenue line.",
            "The revenue engine may be what makes the profit engine "
            "reachable, and starving it removes the access.",
            "Comparable operating margins across both segments falsify "
            "this.",
            "Compare three years of operating margin and incremental "
            "capital by segment, from the segment note."))

    # 9. The rival may be structurally unable to respond.
    if rival:
        out.append((
            "rival_cannot_respond",
            f"{rival} may be structurally unable to answer a move here, "
            f"which would make the contested position far cheaper to take "
            f"than a symmetric reading implies.",
            f"{rival} was established as a competitor from disclosure "
            f"rather than assumed. A rival with an existing business to "
            f"protect faces a cost in answering that a firm without one "
            f"does not — the response damages revenue it already books, so "
            f"the constraint is its own P&L rather than its capability.",
            "Competitive analysis assumes a rival can do whatever it is "
            "capable of, which is a statement about capability and not "
            "about what its own economics permit.",
            f"{rival} contests this company on evidence drawn from the "
            f"filings rather than from an assumed peer set",
            "a rival with no overlapping revenue to protect can respond "
            "freely, which would contradict this",
            LIVE,
            "A move a rival cannot answer holds, and can be sized larger "
            "than a contested one.",
            "Reading a constraint that is not there invites exactly the "
            "response the sizing assumed away.",
            "The rival making the same move without material damage to "
            "its own results falsifies this.",
            "Identify the revenue line the response would cannibalise and "
            "size it against the position being contested."))

    # 10. The market's belief may be right for the wrong reason.
    if belief:
        out.append((
            "right_answer_wrong_reason",
            f"The market's current reading of {company} may be arriving at "
            f"roughly the right conclusion through a mechanism that does "
            f"not hold.",
            f"The established expectation is {_lower(_short(belief))}. A "
            f"conclusion resting on the wrong mechanism survives while the "
            f"mechanism happens to co-move with the truth and inverts "
            f"without warning when it stops — and the inversion looks like "
            f"a surprise rather than a correction.",
            "Agreement between a forecast and an outcome is read as the "
            "forecast being right, so the mechanism underneath it is never "
            "audited while it is working.",
            "an established expectation exists for this company against "
            "which the stated mechanism can be checked",
            "an expectation whose stated mechanism matches the measured "
            "driver would contradict this",
            _band(True, contested),
            "Knowing which mechanism the consensus is actually using shows "
            "where it will break before it does.",
            "A mechanism that looks wrong from outside may be a proxy the "
            "holder understands better than the critic.",
            "The consensus mechanism matching the measured driver "
            "falsifies this.",
            "State the mechanism the expectation implies, then test it "
            "against the driver the filing names."))
    return out


def hypotheses_for(company: str, architecture, *, rivals: Tuple[str, ...] = (),
                   market_belief: str = "", limit: int = 5
                   ) -> Tuple[ImpossibleHypothesis, ...]:
    """3-5 heresies for THIS company, or fewer. Never raises, never invents.

    An architecture nothing was measured from yields nothing, which is the
    honest state: a heresy about a company we could not read is a heresy
    about nobody.
    """
    try:
        if architecture is None or not architecture.measured:
            return ()
        # AN UNREADABLE COMPANY GETS NOTHING, and the guard is the MEASURED
        # set rather than any single field. Caught by the negative control
        # while it was being written: `do_nothing_substitute` fires when no
        # rival was established, and "no rival" is true of a company nothing
        # could be read from -- so an empty architecture emitted a heresy
        # made entirely of constants, which is the class-level collapse this
        # producer exists to avoid, arriving on its first day.
        rivals = tuple(r for r in (rivals or ()) if r)
        rows = _candidates(company or "This company", architecture, rivals,
                           market_belief)
        # RANKED BY STANDING, so a company that supports a LIVE heresy leads
        # with it rather than with whatever happened to be listed first.
        order = {LIVE: 0, PLAUSIBLE: 1, CONCEIVABLE: 2}
        rows.sort(key=lambda r: order.get(r[6], 3))
        return tuple(
            ImpossibleHypothesis(
                kind=k, hypothesis=h, mechanism=m, why_missed=w,
                evidence_for=ef, evidence_against=ea, plausibility=p,
                upside=up, downside=dn, falsifier=fa, smallest_experiment=se)
            for (k, h, m, w, ef, ea, p, up, dn, fa, se) in rows[:max(0, limit)])
    except Exception:                                       # noqa: BLE001
        # A heretical reading is worth having and never worth a page.
        return ()
