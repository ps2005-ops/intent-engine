"""Typed corroboration: independence and relevance, never traded off.

The load-bearing tests are the anti-gaming ones. This framework exists partly
because Day 6 found a relabelling that would have unlocked trading without
improving anything, and the point is to make that structurally impossible
rather than a matter of restraint.
"""
from intent_engine.market.corroboration import (
    Category,
    assess,
    category_of,
    is_independent,
)


# --- independence is about authorship ----------------------------------------
def test_a_company_filing_is_not_independent_however_official():
    """A 10-Q is legally binding and still the company speaking about itself."""
    assert category_of("investor_material") == Category.COMPANY
    assert not is_independent(Category.COMPANY)


def test_a_third_party_filing_about_the_company_is_independent():
    """An SC 13D is authored by an activist, not by the subject. The old gate
    rejected it because the class was not on a hardcoded list."""
    assert category_of("third_party_filing") == Category.INSTITUTIONAL
    assert is_independent(Category.INSTITUTIONAL)


def test_every_non_company_category_is_independent():
    for source in ("customer_voice", "independent_reporting",
                   "analyst_coverage", "regulator_filing",
                   "third_party_filing", "macro_series", "alternative_data"):
        assert is_independent(category_of(source)), source


# --- relevance is about the claim --------------------------------------------
def test_customer_reviews_do_not_corroborate_a_governance_claim():
    """Independent and irrelevant. The old gate accepted this."""
    result = assess(["customer_voice"], hypothesis_kind="governance")
    assert not result.satisfied
    assert Category.CUSTOMER_VOICE in result.independent_present
    assert set(result.missing) == {Category.REGULATORY, Category.INSTITUTIONAL}


def test_the_same_evidence_satisfies_the_claim_it_speaks_to():
    assert assess(["customer_voice"],
                  hypothesis_kind="customer_adoption").satisfied


def test_macro_data_cannot_corroborate_a_company_specific_claim():
    """Independent, but not about this company."""
    assert not assess(["macro_series"],
                      hypothesis_kind="customer_adoption").satisfied
    assert assess(["macro_series"],
                  hypothesis_kind="macro_sensitivity").satisfied


def test_required_categories_are_alternatives_not_a_conjunction():
    """A customer-adoption claim is corroborated by customers OR by an
    industry observer reporting the same adoption."""
    assert assess(["independent_reporting"],
                  hypothesis_kind="customer_adoption").satisfied


# --- the anti-gaming property ------------------------------------------------
def test_relabelling_institutional_evidence_cannot_unlock_a_customer_claim():
    """THE guard. Day 6 found that reclassifying SC 13G as an outside source
    would move independent_source from 0/28 to ~28/28 and unlock trading while
    improving the capability by nothing. It is now impossible by construction:
    a 13G is INSTITUTIONAL, and no relabelling makes institutional evidence
    speak to customer adoption."""
    ownership_only = ["third_party_filing", "investor_material"]
    result = assess(ownership_only, hypothesis_kind="customer_adoption")
    assert not result.satisfied
    assert Category.INSTITUTIONAL in result.independent_present, \
        "the filing IS recognised as independent -- that was never the issue"
    assert Category.CUSTOMER_VOICE in result.missing


def test_a_company_only_run_is_never_corroborated_for_any_claim():
    """The original guarantee, preserved for every hypothesis kind."""
    company_only = ["company_owned", "executive_statement", "investor_material"]
    for kind in ("customer_adoption", "governance", "macro_sensitivity",
                 "expectation_shift", "competitive_position"):
        assert not assess(company_only, hypothesis_kind=kind).satisfied, kind


def test_an_unknown_hypothesis_kind_gets_the_strict_default_not_a_free_pass():
    """An unclassified hypothesis must not become the easy path to a position."""
    assert not assess(["investor_material"], hypothesis_kind="nonsense").satisfied
    assert assess([], hypothesis_kind="nonsense").hypothesis_kind \
        == "customer_adoption"


# --- the refusal explains itself ---------------------------------------------
def test_the_refusal_names_what_is_missing_and_what_is_present():
    """"no_outside_source" could not distinguish "we found nothing
    independent" from "we found plenty of the wrong kind"."""
    result = assess(["third_party_filing", "macro_series"],
                    hypothesis_kind="customer_adoption")
    assert "customer_voice" in result.reason
    assert "institutional" in result.reason and "macro" in result.reason
    d = result.as_dict()
    assert d["missing"] and d["independent_present"] and d["required"]


def test_a_price_claim_requires_no_company_corroboration():
    """A momentum claim asserts nothing about the business, so no company
    evidence could corroborate it -- and none is demanded. It is gated
    elsewhere, on dated evidence and on the market signal."""
    assert assess([], hypothesis_kind="price_behaviour").satisfied
