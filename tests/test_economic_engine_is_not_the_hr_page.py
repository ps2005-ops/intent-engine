"""What a company offers its STAFF is not what it sells.

MEASURED LIVE, deployed preview f8c183f, 2026-08-22. Meta Platforms' economic
engine -- the first sentence a chief executive reads -- rendered as:

    "Meta Platforms, Inc. is a software platform business that runs on
     competitive compensation and a wide range of benefits, including many
     learning and development resources; revenue by displaying ad products
     on Facebook, Instagram, Messenger and third-party mobile applications."

That is the Human Capital section of Meta's own 10-K, read as its product.
`We offer ...` matched, and Item 1 states the employment offer before it
states the product one.

The VERB was already guarded here -- "operate IS NOT SELLING", after "We
operate in a very competitive and rapidly changing environment" shipped as
what Cloudflare sells. The OBJECT was not, so the same defect came back
through a different verb.
"""
from __future__ import annotations

from intent_engine.executive.economic_architecture import (architecture_of,
                                                            describe)

CIK = "1326801"


def _doc(text: str) -> list:
    """One filing, attributed to the subject the way production attributes
    it: by the CIK in the EDGAR URL."""
    return [{"source_id": "s1", "text_content": text,
             "final_url": f"https://www.sec.gov/Archives/edgar/data/{CIK}/x.htm",
             "source_class": "investor_material"}]


def measure(documents, *, company=""):
    return architecture_of(documents, company=company, subject_cik=CIK)


META_HUMAN_CAPITAL = (
    "Human Capital. We believe our employees are our most important asset. "
    "We offer competitive compensation and a wide range of benefits, "
    "including many learning and development resources, to attract and "
    "retain talent. "
)
META_PRODUCT = (
    "We generate substantially all of our revenue from advertising. "
    "We sell ad placements to marketers across Facebook, Instagram, "
    "Messenger and third-party applications. "
)


def _sold(text, company="Meta Platforms, Inc."):
    return measure(_doc(text), company=company).what_is_sold


# --- the defect -----------------------------------------------------------

def test_the_hr_offer_is_not_what_the_company_sells():
    assert _sold(META_HUMAN_CAPITAL) == ""


def test_the_product_sentence_is_found_past_the_hr_one():
    """Vetoing must not trade a wrong answer for an empty one.

    The employment offer comes FIRST in Item 1, so a veto that stopped at
    `re.search`'s first hit would lose the real sentence sitting below it.
    """
    sold = _sold(META_HUMAN_CAPITAL + META_PRODUCT)
    assert sold, "the product sentence below the HR one was not reached"
    assert "compensation" not in sold.lower()
    assert "ad placements" in sold.lower()


def test_the_rendered_sentence_no_longer_carries_the_hr_clause():
    """The defect as the reader met it, end to end."""
    arch = measure(_doc(META_HUMAN_CAPITAL + META_PRODUCT),
                   company="Meta Platforms, Inc.")
    line = describe(arch, name="Meta Platforms, Inc.",
                    sector="software platform")
    assert "competitive compensation" not in line
    assert "learning and development" not in line


# --- controls: what must still be read as a product -----------------------

def test_a_real_product_sentence_is_unaffected():
    sold = _sold("We sell subscriptions to our design software to "
                 "enterprise customers and individual creators.")
    assert "subscriptions" in sold.lower()


def test_an_insurer_still_sells_benefits():
    """`benefits` is not on the stoplist on its own, deliberately.

    A word that a real company's real product is named with cannot be
    refused outright -- that is how a substring wall starts refusing real
    companies.
    """
    sold = _sold("We offer health and dental benefits to members and "
                 "participating employer groups across the United States.",
                 company="Acme Health, Inc.")
    assert "benefits" in sold.lower()


def test_a_manufacturer_that_makes_equipment_is_unaffected():
    sold = _sold("We design and manufacture construction and mining "
                 "equipment, diesel engines and industrial gas turbines.")
    assert "equipment" in sold.lower()


def test_hr_text_alone_does_not_fabricate_a_different_field():
    """The veto must not push the HR sentence into a neighbouring slot."""
    arch = measure(_doc(META_HUMAN_CAPITAL), company="Meta Platforms, Inc.")
    for field in (arch.what_is_sold, arch.revenue_basis, arch.customer):
        assert "compensation" not in (field or "").lower()


# --- the real filing, positionally ----------------------------------------

def test_the_human_capital_section_is_out_of_scope_for_what_is_sold():
    """The discriminator is POSITIONAL, and this pins the boundary.

    MEASURED on Meta's 2025 10-K: "Human Capital" occurs exactly once, at
    character 55,533, and all five employment matches fall between 55,962 and
    59,041 -- immediately after it. A word list would have to grow once per
    filing; the heading does not.
    """
    from intent_engine.executive.economic_architecture import _business_text
    body = "x" * 3000 + " We sell widgets to industrial buyers worldwide. "
    hr = "Human Capital. We offer competitive compensation and benefits. "
    assert "Human Capital" not in _business_text(body + hr)
    assert "sell widgets" in _business_text(body + hr)


def test_a_short_document_is_not_truncated_by_the_heading():
    """The guard exists so a table-of-contents line cannot empty the section."""
    from intent_engine.executive.economic_architecture import _business_text
    short = "Human Capital. We sell widgets to industrial buyers."
    assert _business_text(short) == short


def test_a_hypothetical_is_not_what_the_company_sells():
    """Vetoing the HR sentences and continuing walked into Item 1A."""
    sold = _sold("We provide services that from time to time have had, and "
                 "in the future may have, quality issues resulting from the "
                 "design or manufacture of the products.")
    assert sold == ""
