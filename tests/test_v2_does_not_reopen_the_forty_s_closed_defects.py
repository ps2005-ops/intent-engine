"""§18 regression control: the false differentiation must stay gone.

WHY A NEW LAYER NEEDS THIS FILE
-------------------------------
The V2 repair makes the decision question sensitive to the company's own
text for the first time. Everything the frozen 40 closed was closed by making
the reading LESS sensitive to text that looks decisive and is not: ASC 805
business-combination boilerplate, go-to-market vocabulary, disclosed SaaS
metrics, compliance words, an alphabetical tie-break. A layer that reads more
text is exactly the layer that reopens them.

So each test below states one closed defect and proves it is still closed
THROUGH THE NEW PATH. The positive controls are here too: a repair that fixes
the collapse by breaking the three companies that worked is not a repair.
"""
from __future__ import annotations

from intent_engine.executive import decision_object as DO
from intent_engine.executive import strategic_delta as SD
from intent_engine.executive.analysis_selection import select

_SUB = ("We sell software on an annual subscription and recognise revenue "
        "ratably over the contract term.")


def _run(name, text):
    body = f"{text} {_SUB}"
    return select(name=name, published_text=body, evidence_text=body)


# --- the positive controls still work --------------------------------------

def test_a_logistics_vendor_still_reaches_an_off_menu_supply_chain_decision():
    """project44's reading must survive the repair.

    It is on the list because its own record discusses carriers, freight and
    lead times in many distinct terms -- an archetype a subscription software
    menu does not propose.
    """
    sel = _run("project44", (
        "project44 connects shippers and carriers. Our network covers freight "
        "visibility, customs clearance, logistics execution, shipment "
        "tracking, carrier onboarding, procurement workflows, supplier "
        "collaboration, lead time prediction and supply chain resilience."))
    assert sel.archetype == "SUPPLY_CHAIN", (
        f"the off-menu path stopped working: {sel.archetype}")


def test_the_three_controls_no_longer_share_one_byte_identical_question():
    """The repair's whole purpose, measured on the companies that passed.

    All three were EVIDENCE_LED on the frozen 40 and all three received the
    SAME decision question. Being right about the archetype is not being
    about the company.
    """
    a = _run("project44", (
        "project44 is built for shippers and carriers. Pricing is based on "
        "the number of tracked shipments. Our network covers freight "
        "visibility, customs, logistics, shipment tracking, carrier "
        "onboarding, procurement, suppliers and lead time."))
    b = _run("o9 Solutions", (
        "o9 is built for supply chain planners. Pricing is based on planned "
        "units. We cover logistics, shipment, supplier, procurement, freight, "
        "lead time, customs and supply chain planning."))
    assert a.decision_question != b.decision_question


# --- what must NOT come back ------------------------------------------------

def test_asc_805_boilerplate_does_not_become_an_m_and_a_decision():
    """The one that shipped: Rubrik, on the wording of a standard note."""
    sel = _run("Filer Inc", (
        "The acquisition of the business was accounted for as a business "
        "combination. The acquisition of certain assets and the combination "
        "with the acquired entity were recorded at fair value. Goodwill "
        "arising from the acquisition of these operations is not deductible."))
    assert sel.archetype != "M&A", (
        "a business-combination note chose the company's central decision")


def test_go_to_market_vocabulary_does_not_choose_the_sales_motion():
    sel = _run("B2B Co", (
        "Our go-to-market strategy spans channel partners and direct sales. "
        "We work with channel partners across our go-to-market motion."))
    assert sel.archetype != "SALES_MOTION"


def test_disclosed_saas_metrics_do_not_become_a_retention_decision():
    """A number a filer must report is not a decision it is facing."""
    sel = _run("SaaS Co", (
        "Net revenue retention was 118%. Churn was 6%. Our renewal rate "
        "improved and expansion revenue grew year over year."))
    assert sel.archetype != "RETENTION"


def test_compliance_words_do_not_choose_a_regulatory_decision():
    sel = _run("Trusty Co", (
        "We are SOC 2 Type II certified and ISO 27001 compliant. Our platform "
        "supports GDPR and HIPAA compliance requirements for our customers."))
    assert sel.archetype != "REGULATORY_RESPONSE"


def test_a_tie_is_not_evidence_outranking_the_prior():
    """Two archetypes on one score must not be separated by the alphabet.

    MEASURED on the forty: Rubrik's PRICING tied an off-menu M&A at 5 and
    lost because "M&A" sorts before "PRICING". The standing menu holds on a
    tie, in its own order.
    """
    sel = _run("Tied Co", "We provide software to enterprises.")
    rows = sel.considered
    assert rows, "no archetypes were considered"
    top = rows[0]
    ties = [r for r in rows if r["score"] == top["score"]]
    if len(ties) > 1:
        standing = tuple(sel.profile.decision_archetypes or ())
        assert top["archetype"] in standing, (
            "an off-menu archetype won a tie against the standing menu")


# --- the new layer must not become a vocabulary either ----------------------

def test_a_billing_unit_does_not_change_which_decision_is_faced():
    """The unit MEASURES the decision; it must not SELECT it.

    If stating a price unit could move the archetype, the repair would be a
    new keyword channel into the one place the forty proved must not have
    one.
    """
    plain = _run("Unit Co", "We provide software to enterprises.")
    priced = _run("Unit Co", "We provide software to enterprises. Pricing is "
                             "based on the number of managed endpoints.")
    assert plain.archetype == priced.archetype, (
        "stating a billing unit changed which decision the company faces")
    assert plain.decision_question != priced.decision_question, (
        "stating a billing unit changed nothing at all")


def test_a_buyer_does_not_reach_a_decision_it_does_not_bear_on():
    """Naming a customer inside a capital question adds a noun, not meaning."""
    from intent_engine.executive.analysis_selection import (_BUYER_BEARS_ON,
                                                            question_basis)
    obj = DO.build(company="Anyco",
                   published_text="Anyco is built for law firms.")
    basis = question_basis(type("P", (), {
        "primary_revenue_drivers": ("customer count",),
        "business_model_class": "SUBSCRIPTION_SOFTWARE"})(),
        "CAPITAL_ALLOCATION", obj)
    assert not basis["buyer_used"]
    assert "CAPITAL_ALLOCATION" not in _BUYER_BEARS_ON


def test_an_unreadable_company_is_not_given_a_manufactured_ground():
    """A bounded outcome must stay bounded."""
    sel = _run("Silent Co", "Access to this site is restricted.")
    assert sel.delta.grounding.verdict in (SD.NAME_ONLY, SD.GENERIC)
    assert sel.information_priorities, (
        "nothing was established and nothing was asked for")


def test_a_same_class_peer_is_not_called_a_competitor():
    """Shared economics is not rivalry, and the page must not say it is."""
    sel = _run("Peer Co", "We provide software to enterprises.")
    for rival in (sel.profile.strategic_competitors or ()):
        basis = " ".join(str(v) for v in
                         (rival.as_dict() if hasattr(rival, "as_dict")
                          else rival).values()).lower()
        assert "same" in basis or "peer" in basis or "class" in basis or \
               "model" in basis, (
            f"a peer was presented without its basis: {basis[:200]}")
