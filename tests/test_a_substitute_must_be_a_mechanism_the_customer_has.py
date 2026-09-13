"""Nobody rents second-hand DRAM instead of buying it.

MEASURED across 22 live companies on 589518f: eight distinct substitution
clauses served all 22, keyed on the business-model CLASS. "Rental and used
equipment in place of a new purchase" was asserted for NVIDIA, Broadcom,
Qualcomm, Micron, Intel, AMD and Texas Instruments -- every
DESIGN_AND_MANUFACTURE filer -- because that class conflates the people who
BUILD capital equipment with the people who sell them chips.

The named-rival half of the same dimension works and is genuinely
company-specific (Qualcomm gets HiSilicon and MediaTek, Visa gets UnionPay and
WeChat Pay), so the repair is to the substitution clause only.
"""
from __future__ import annotations

import pytest

from intent_engine.executive import competitive_ground as CG

USED = "Rental and used equipment in place of a new purchase"
PARTS = "Independent service and will-fit parts"
AI = "Automation absorbing the task itself"
BUILD = "The customer's own engineering"

CAT_WORDS = ("Our Resource Industries segment supports customers with the "
             "remanufacturing of Caterpillar engines and components, and "
             "dealers carry used equipment for customers who defer a new "
             "purchase.")
NVDA_WORDS = ("We design and manufacture accelerated computing platforms. "
              "Our customers purchase GPUs, systems and networking for data "
              "centres, and we license software for AI workloads.")


# --- the defect -----------------------------------------------------------

def test_a_chip_maker_is_not_told_its_customers_can_rent_used_equipment():
    assert not CG._mechanism_supported(USED, NVDA_WORDS)


def test_a_capital_equipment_maker_keeps_the_second_hand_alternative():
    """The control that stops the fix becoming 'delete the alternative'.

    Caterpillar's real 10-K carries this mechanism 21 times; a repair that
    removed it for Caterpillar too would be worse than the defect.
    """
    assert CG._mechanism_supported(USED, CAT_WORDS)


def test_the_aftermarket_alternative_is_gated_the_same_way():
    assert CG._mechanism_supported(
        PARTS, "Independent service providers and will-fit parts compete for "
               "the maintenance spend on installed machines.")
    assert not CG._mechanism_supported(PARTS, NVDA_WORDS)


# --- controls: what must NEVER be gated -----------------------------------

@pytest.mark.parametrize("identity", [
    AI, BUILD,
    "Renewing nothing and keeping the current process",
    "Another surface holding the same attention hour",
    "The shopper buying the same basket somewhere cheaper",
])
def test_universal_alternatives_are_never_gated(identity):
    """§2 requires internal build, do-nothing and automation to be ASKED of
    every company. They are available to every customer of every business, so
    gating them on evidence would silence the questions the ladder exists to
    force."""
    assert CG._mechanism_supported(identity, "")
    assert CG._mechanism_supported(identity, NVDA_WORDS)


def test_property_refurbishment_is_not_a_customer_substitute():
    """Costco's filing says "remodels, refurbishments and improvements" about
    its OWN property. That is accounting, not something a shopper can buy
    instead, and a bare "refurbish" pattern matched it."""
    assert not CG._mechanism_supported(
        USED, "Expenditures for remodels, refurbishments and improvements "
              "that add to or change asset function are capitalised.")


def test_an_empty_filing_does_not_assert_a_mechanism():
    """Absence of evidence is not evidence of the mechanism."""
    assert not CG._mechanism_supported(USED, "")


# --- the registry is wired, not decorative --------------------------------

def test_every_gated_alternative_names_a_known_mechanism():
    for identity, mechanism in CG._ALTERNATIVE_REQUIRES.items():
        assert mechanism in CG._MECHANISM_EVIDENCE, identity


def test_every_gated_alternative_exists_in_the_model_table():
    """A gate on a clause nothing emits is a gate that never runs."""
    emitted = {identity
               for rows in CG._MODEL_ALTERNATIVES.values()
               for identity, _k, _r in rows}
    for identity in CG._ALTERNATIVE_REQUIRES:
        assert identity in emitted, f"{identity} is gated but never emitted"


def test_the_emission_site_calls_the_gate():
    """STRUCTURAL, and it reads the running code -- a gate the call site does
    not consult is exactly how a repair ships inert."""
    import inspect
    src = inspect.getsource(CG)
    assert "_mechanism_supported(identity, own_words)" in src
