"""The declared transmission chains, at the evidence level they have earned.

WHY EVERY EDGE HERE IS LEVEL 0 OR 1
-----------------------------------
Because that is what is actually established. Section 17's ladder says LEVEL 3
requires a stated structural restriction and LEVEL 4 an identified event, and
none of the chains below have one yet. Seeding them at LEVEL 3 so that the
prose reads "causes" would be the single most damaging thing this file could
do: it would put unearned causal language on a founder surface and make the
whole ladder decorative.

So these are candidate mechanisms with plausible rationales and honest
levels. `Chain.may_state_causation` is False for all of them, and the
statements come out as ASSOCIATED WITH. Raising them is what Sections 19-20's
historical programme is for.

WHY 2008 IS HERE AS TWO CHAINS AND NOT ONE
------------------------------------------
Section 20 is explicit: do not start with "fear caused the crash". The
upswing and the downswing are separate chains with separate edges, so that
each can be tested and each can fail independently. If they were one object,
confirming the boom half would carry the bust half with it.
"""
from __future__ import annotations

from .causal import DOWN, L0_CORRELATION, L1_LAGGED, UP
from .transmission import Chain, Exposure, TransmissionRegistry, link

CONTRACT = "econ_transmission_seed.v1"

_S, _E = "1990-01-01", "2026-06-30"


def _l(cause, effect, sign, mechanism, falsifier, lag, level=L1_LAGGED,
       evidence="", n=0, conf=0.4):
    return link(cause=cause, effect=effect, sign=sign, mechanism=mechanism,
                evidence_level=level,
                evidence=evidence or (
                    f"lagged association at ~{lag}d over {_S}..{_E}; "
                    "no structural restriction has been stated, so this "
                    "remains below the causal-language floor"),
                falsifier=falsifier, lag_days=lag, sample_start=_S,
                sample_end=_E, sample_n=n, confidence=conf)


def registry() -> TransmissionRegistry:
    r = TransmissionRegistry()

    # === SECTION 13: psychology -> behaviour -> company ======================
    r.add_chain(Chain(
        name="anxiety_defers_discretionary",
        population="US_households",
        note="Section 13's worked example, link by link so each can break.",
        links=(
            _l("financial_anxiety", "discretionary_intent", DOWN,
               "a household that expects a worse month defers the purchase "
               "it can most easily defer",
               "discretionary intent holds or rises while anxiety rises for "
               "two consecutive quarters", 30, n=140),
            _l("discretionary_intent", "consumer_demand", UP,
               "stated intent precedes realised discretionary spending",
               "intent falls and realised discretionary spending does not",
               45, n=140),
            _l("consumer_demand", "inventory", DOWN,
               "demand shortfalls show up as unsold goods before they show "
               "up in revenue",
               "demand weakens and inventory-to-sales does not rise", 60,
               n=120),
            _l("inventory", "pricing", DOWN,
               "excess inventory is cleared by promotion",
               "inventory builds without any change in promotional intensity",
               45, n=120),
            _l("pricing", "margin", UP,
               "promotional intensity is a direct deduction from gross margin",
               "promotion rises and gross margin does not compress", 30,
               n=200, conf=0.55),
        )))

    r.add_chain(Chain(
        name="shortening_horizon_trades_down",
        population="US_households",
        links=(
            _l("time_horizon", "trade_down", DOWN,
               "a shortened planning horizon substitutes cheaper alternatives "
               "before it cuts volume",
               "horizons shorten with no observable shift in basket mix", 30,
               n=90),
            _l("trade_down", "segment_mix", DOWN,
               "trade-down appears in the mix line before the revenue line",
               "trade-down rises and segment mix is unchanged", 45, n=90),
        )))

    r.add_chain(Chain(
        name="control_drives_labour_mobility",
        population="US_workers",
        links=(
            _l("perceived_control", "quits", UP,
               "leaving a job voluntarily is a costly signal that a worker "
               "believes they can secure another",
               "perceived control rises while the quits rate falls", 60,
               n=110, conf=0.5),
            _l("quits", "wage_pressure", UP,
               "employers bid to retain when workers can credibly leave",
               "quits rise with no wage response over two quarters", 90,
               n=110),
        )))

    # === SECTION 14: economy -> psychology (the reverse direction) ===========
    r.add_chain(Chain(
        name="rates_erode_perceived_security",
        population="US_households",
        note="Section 14's worked example. The reverse arrow is what makes "
             "Section 15's reflexivity detectable at all.",
        links=(
            _l("policy_rate", "housing", DOWN,
               "higher policy rates raise mortgage costs and price marginal "
               "buyers out",
               "rates rise and housing turnover does not fall within a year",
               180, n=160, conf=0.6),
            _l("housing", "financial_anxiety", DOWN,
               "housing is the largest asset most households hold; its "
               "direction is read as a verdict on their own position",
               "house prices fall and household anxiety does not rise", 90,
               n=100),
            _l("financial_anxiety", "consumer_demand", DOWN,
               "anxious households protect the buffer before they spend it",
               "anxiety rises and discretionary consumption holds", 60,
               n=140),
        )))

    r.add_chain(Chain(
        name="labour_weakness_shortens_horizons",
        population="US_workers",
        links=(
            _l("labour", "perceived_control", UP,
               "a loosening labour market removes the outside option that "
               "made a worker feel in command of their situation",
               "unemployment rises and quits/mobility hold", 60, n=120),
            _l("perceived_control", "time_horizon", UP,
               "people who do not feel in control plan over shorter spans",
               "perceived control falls and durable-goods intent holds", 45,
               n=80),
        )))

    # === SECTION 15 / 20: reflexivity, as two separable chains ==============
    r.add_chain(Chain(
        name="wealth_reflexivity_upswing",
        population="US_households",
        note="Section 20's boom half. Deliberately separate from the bust "
             "half so that confirming one does not carry the other.",
        links=(
            _l("housing", "perceived_security", UP,
               "rising house prices are read as personal wealth",
               "house prices rise and perceived security does not", 90,
               n=100, level=L0_CORRELATION,
               evidence="contemporaneous co-movement over 1997-2006; no lag "
                        "structure has been established"),
            _l("perceived_security", "risk_appetite", UP,
               "a household that feels wealthier tolerates more risk",
               "perceived security rises with no change in household "
               "allocation", 60, n=80, level=L0_CORRELATION,
               evidence="contemporaneous co-movement; direction unidentified"),
            _l("risk_appetite", "credit_application", UP,
               "risk appetite shows up as willingness to take on obligation",
               "risk appetite rises and credit demand does not", 30, n=90),
            _l("credit_application", "housing", UP,
               "credit demand is the marginal bid in the housing market",
               "credit applications rise and transaction volume does not", 90,
               n=90),
        )))

    r.add_chain(Chain(
        name="wealth_reflexivity_downswing",
        population="US_households",
        links=(
            _l("delinquency", "financial_anxiety", UP,
               "visible default in one's own neighbourhood is the most "
               "legible signal that the buffer is gone",
               "delinquency rises and household anxiety does not", 60, n=90),
            _l("financial_anxiety", "risk_appetite", DOWN,
               "anxiety withdraws from risk before it cuts consumption",
               "anxiety rises and household risk allocation holds", 30, n=90),
            _l("risk_appetite", "credit_spread_hy", DOWN,
               "withdrawal of risk appetite widens the price of risk",
               "risk appetite falls and spreads do not widen", 14, n=140,
               conf=0.5),
            _l("credit_spread_hy", "business_investment", DOWN,
               "the cost of external finance gates marginal capex",
               "spreads widen and capex plans are unchanged", 120, n=140),
        )))

    # === SECTION 21: the consensus-attacking chain ==========================
    r.add_chain(Chain(
        name="rate_cuts_blocked_by_insecurity",
        population="US_households",
        note="Section 21's worked example. This chain EXISTS to contradict "
             "the consensus that rate cuts restore credit demand; it is the "
             "alternative, and it is preregistered as such.",
        links=(
            _l("policy_rate", "financial_anxiety", DOWN,
               "cuts arrive because conditions deteriorated, and households "
               "read the deterioration rather than the cut",
               "policy eases while household anxiety falls in the same "
               "quarter", 60, n=90, level=L0_CORRELATION,
               evidence="co-movement across three easing cycles; the "
                        "direction is not identified and the sample is small"),
            _l("financial_anxiety", "credit_application", DOWN,
               "an anxious household does not borrow against a future it "
               "does not trust, whatever the price of credit",
               "anxiety high and rising while credit applications rise with "
               "the rate cut", 60, n=90),
        )))

    # === SECTION 13: per-company exposures, each naming its own channel =====
    for e in (
        Exposure(company_id="WMT", construct="financial_anxiety",
                 channel="basket mix and private-label share",
                 sign=DOWN, observable="segment_mix", confidence=0.5),
        Exposure(company_id="WMT", construct="future_orientation",
                 channel="trade-down into own-brand groceries",
                 sign=DOWN, observable="pricing", confidence=0.45),
        Exposure(company_id="NKE", construct="financial_anxiety",
                 channel="discretionary apparel deferral and channel "
                         "inventory",
                 sign=DOWN, observable="inventory", confidence=0.45),
        Exposure(company_id="V", construct="financial_anxiety",
                 channel="average ticket size and cross-border spend",
                 sign=DOWN, observable="revenue", confidence=0.5),
        Exposure(company_id="JPM", construct="financial_anxiety",
                 channel="credit quality and deposit behaviour",
                 sign=UP, observable="financing", confidence=0.5),
        Exposure(company_id="JPM", construct="risk_appetite",
                 channel="loan demand from households and small business",
                 sign=UP, observable="demand_language", confidence=0.45),
        Exposure(company_id="CAT", construct="perceived_control",
                 channel="downstream customer capex intentions — NOT "
                         "household sentiment, which does not reach this "
                         "company directly",
                 sign=UP, observable="backlog", confidence=0.4),
        Exposure(company_id="META", construct="risk_appetite",
                 channel="advertiser budget commitment and consumer "
                         "conversion",
                 sign=UP, observable="revenue", confidence=0.45),
        Exposure(company_id="AMZN", construct="future_orientation",
                 channel="discretionary commerce basket, separate from the "
                         "AWS corporate-budget channel",
                 sign=UP, observable="segment_mix", confidence=0.45),
        Exposure(company_id="NET", construct="risk_appetite",
                 channel="enterprise IT risk appetite and security budget "
                         "renewal — an EXECUTIVE cohort reading, not a "
                         "household one",
                 sign=UP, observable="rpo", confidence=0.4),
    ):
        r.add_exposure(e)
    return r
