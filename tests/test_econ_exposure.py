"""The exposure capability, and the measurement that moved it into the core.

WHAT THIS PROTECTS
------------------
Two things that are easy to lose and expensive to lose quietly:

1. The two copies of the patterns must not drift. A shared capability whose
   copies diverge is worse than two capabilities, because the difference is
   invisible until the two sides disagree about a company.

2. The sector rule must hold in BOTH copies. A capability that refuses sector
   inference in one package and allows it in another has been forked, not
   shared.
"""
from __future__ import annotations

import pytest

from intent_engine.econ import company as CO
from intent_engine.econ import exposure as EX
from intent_engine.econ import evidence as EV
from intent_engine.econ import vocabulary as V


FILING = (
    "Item 7A. Quantitative and Qualitative Disclosures About Market Risk. "
    "Our results are sensitive to interest rates on our variable rate "
    "borrowings. We have a revolving credit facility maturing in 2029. "
    "Foreign exchange translation impact reduced reported revenue by 2%. "
    "We face labour cost inflation across our distribution network. "
    "Capital expenditures increased as we expanded capacity. "
    "Fuel prices rose during the year."
)

HEADLINE = (
    "Company shares jump 18% on revenue beat and raised full-year outlook - "
    "SiliconANGLE."
)


def test_the_two_copies_of_the_patterns_have_not_drifted():
    from intent_engine.market import company_exposure as CX
    assert tuple(EX.DIMENSIONS) == tuple(CX.DIMENSIONS)
    assert EX._PATTERNS == CX._PATTERNS, (
        "the shared exposure patterns have diverged from the market "
        "engine's. A shared capability whose copies drift is invisible until "
        "the two sides disagree about a company.")


def test_sector_inference_is_refused_here_too():
    with pytest.raises(V.EconError, match="least information"):
        EX.infer_from_sector(sector="airlines")


def test_filing_prose_establishes_exposures():
    got = EX.read([FILING], company_id="acme")
    dimensions = {r["dimension"] for r in got}
    assert EX.RATE in dimensions
    assert EX.FX in dimensions
    assert EX.LABOR in dimensions
    assert EX.CAPITAL_INTENSITY in dimensions


def test_the_company_must_be_the_subject_even_for_credit():
    """"We have a credit facility" does not rate; "our credit facility" does.

    The CREDIT pattern requires `our` or `its`, and that is the rule working
    rather than failing: a sentence that merely mentions a facility is a fact
    about the balance sheet, not a stated dependency on credit conditions.
    """
    assert EX.read(["We have a revolving credit facility maturing in 2029."],
                   company_id="acme") == []
    assert [r["dimension"] for r in EX.read(
        ["Our revolving credit facility matures in 2029."],
        company_id="acme")] == [EX.CREDIT]


def test_a_percentage_concentration_rates_and_used_not_to():
    """A DEAD BRANCH, found by running the patterns over real filings.

    `\\b(\\d+\\s*%|percent|majority)\\b` could never match a percentage: the
    alternative ends on "%", a non-word character, and the trailing boundary
    then required the next character to be a word character. In "22% of
    revenue" it is a space. Only the spelled-out forms ever rated, and the
    numeric form is what filings use.
    """
    assert [r["dimension"] for r in EX.read(
        ["Our largest customer accounted for 22% of revenue."],
        company_id="acme")] == [EX.CUSTOMER_CONCENTRATION]
    # the spellings that always worked must keep working
    for text in ("Our largest customer accounted for 22 percent of revenue.",
                 "Our top customers represented a majority of revenue."):
        assert EX.read([text], company_id="acme")


def test_the_plural_capital_expenditures_rates_and_used_not_to():
    """The singular matched and the plural did not; filings use the plural."""
    for text in ("Capital expenditures increased as we expanded capacity.",
                 "Capital expenditure increased as we expanded capacity.",
                 "Our capex rose sharply."):
        assert [r["dimension"] for r in EX.read([text], company_id="acme")] \
            == [EX.CAPITAL_INTENSITY], text


def test_a_headline_establishes_nothing_and_that_is_the_measurement():
    """The defect that moved this capability into the shared core.

    Measured live on 2026-08-27 across six companies: the market engine's
    corpus of 131 headline rows (19,415 characters) produced ONE exposure;
    the same patterns over the founder engine's 46 retrieved documents
    (3,564,390 characters) produced 39. The patterns need a sentence in which
    the company is the subject of a dependency, and a headline never contains
    one.
    """
    assert EX.read([HEADLINE], company_id="acme") == []


def test_a_fact_about_the_world_is_not_an_exposure():
    """The rule the patterns encode, asserted directly."""
    assert EX.read(["Fuel prices rose this year."], company_id="acme") == []
    assert EX.read(["Fuel costs pressured our margins."],
                   company_id="acme")


def test_every_exposure_carries_the_sentence_that_established_it():
    for row in EX.read([FILING], company_id="acme"):
        assert row["basis"].strip()
        assert row["company_id"] == "acme"


def test_customer_concentration_is_an_exposure_to_something_that_is_not_macro():
    text = ("Our largest customer accounted for 22% of revenue.")
    rows = EX.read([text], company_id="acme")
    assert rows and rows[0]["dimension"] == EX.CUSTOMER_CONCENTRATION
    assert rows[0]["quantity"] == "", (
        "a company-specific concentration risk was given a macro quantity; "
        "it would then render under an economic heading it does not belong to")
    assert EX.macro_exposures(rows, evidence_node="en-1") == []


def test_macro_exposures_require_an_evidence_node():
    rows = EX.read([FILING], company_id="acme")
    built = EX.macro_exposures(rows, evidence_node="en-1")
    assert built and all(e.evidence_node == "en-1" for e in built)
    assert all(e.mechanism.strip() for e in built)
    assert all(e.falsifier.strip() for e in built)


def test_the_exposures_reach_a_company_state_and_are_checkable():
    node = EV.node(node_class=V.COMPANY, kind="capex", subject="acme",
                   standing=V.OBSERVED, occurred_at="2026-02-14",
                   available_at="2026-02-14", publisher="Acme Inc",
                   statement="rising: capital expenditures increased",
                   producer="test")
    rows = EX.read([FILING], company_id="acme")
    state = CO.build(company_id="acme", company_name="Acme",
                     as_of="2026-08-27", evidence=[node],
                     exposures=EX.macro_exposures(rows,
                                                  evidence_node=node.node_id))
    assert state.exposure_map()["acme"]
    assert "policy_rate" in state.exposure_map()["acme"]


def test_an_exposure_naming_absent_evidence_is_refused():
    rows = EX.read([FILING], company_id="acme")
    with pytest.raises(V.EconError, match="sector guess with an id"):
        CO.build(company_id="acme", company_name="Acme", as_of="2026-08-27",
                 evidence=[],
                 exposures=EX.macro_exposures(rows, evidence_node="en-absent"))


def test_the_founder_translation_extracts_exposures_from_the_document():
    from intent_engine.external_intel import econ_evidence as EE
    out = EE.translate(
        [{"signals": ("capital_intensity",),
          "excerpt": "Capital expenditures increased sharply.",
          "date": "2026-02-14", "origin": "https://www.sec.gov/x",
          "source_refs": [{"artifact_id": "d1"}]}],
        company_id="acme", company_name="Acme", as_of="2026-08-27",
        documents=[{"source_id": "d1", "origin": "https://www.sec.gov/x",
                    "text_content": FILING}])
    quantities = {r["quantity"] for r in out["exposures"] if r["quantity"]}
    assert "policy_rate" in quantities
    assert "labour" in quantities
    assert out["translated"] >= 1


def test_translation_without_documents_reports_no_exposures_rather_than_failing():
    from intent_engine.external_intel import econ_evidence as EE
    out = EE.translate([], company_id="acme", company_name="Acme",
                       as_of="2026-08-27")
    assert out["exposures"] == []
