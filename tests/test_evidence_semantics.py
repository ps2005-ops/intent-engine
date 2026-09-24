"""Two-dimensional evidence semantics.

The single most important property here is a NEGATIVE one: adding the subject
dimension must change no decision. It exists to preserve information for future
reasoning, and a semantics change that quietly widens a gate would be the worst
possible outcome.
"""
from intent_engine.market.corroboration import (
    Category, Subject, assess, describe, subjects_of,
)


# --- the case that motivated it ----------------------------------------------
def test_a_journalist_reporting_an_analyst_action_carries_both():
    """Day 10: Investing.com reporting "Scotiabank raises Duolingo price
    target". Authorship says INDUSTRY; content says analyst opinion. Both true,
    and one category loses half of it."""
    s = describe("independent_reporting",
                 "Scotiabank raises Duolingo stock price target on user growth")
    assert s.source == Category.INDUSTRY          # who wrote it
    assert Subject.ANALYST_OPINION in s.subjects  # what it is about
    assert s.is_independent


def test_an_analyst_outlet_writing_about_earnings_carries_both():
    s = describe("analyst_coverage", "Quarterly results beat on revenue")
    assert s.source == Category.ANALYST
    assert Subject.EARNINGS in s.subjects


def test_a_document_may_carry_several_subjects():
    """19% of real classified documents did."""
    subs = subjects_of("Board faces activist probe as quarterly revenue misses")
    assert Subject.GOVERNANCE in subs and Subject.EARNINGS in subs


def test_a_document_with_no_recognised_subject_reports_none_not_a_guess():
    assert subjects_of("An unrelated headline about nothing in particular") == ()


# --- THE guard: no gate moved -------------------------------------------------
def test_subjects_grant_nothing_that_source_did_not_already_grant():
    """A semantics change that quietly widened a gate would be the worst
    possible outcome of this cycle."""
    # institutional source, subject that a customer-adoption claim wants
    s = describe("third_party_filing",
                 "Merchant adoption accelerates across the platform")
    assert Subject.CUSTOMER_ADOPTION in s.subjects
    # ...and it still cannot corroborate a customer-adoption claim
    assert not assess(["third_party_filing"],
                      hypothesis_kind="customer_adoption").satisfied


def test_a_company_document_stays_non_independent_whatever_it_is_about():
    s = describe("company_owned",
                 "Analyst upgrades and merchant adoption and governance")
    assert s.source == Category.COMPANY
    assert not s.is_independent
    assert len(s.subjects) >= 2, "the subjects are recorded"
    assert not assess(["company_owned"],
                      hypothesis_kind="customer_adoption").satisfied


def test_corroboration_is_unchanged_across_every_hypothesis_kind():
    """Ablation: the same source classes must produce the same verdict as
    before the subject dimension existed."""
    for classes, kind, expected in (
            (["customer_voice"], "customer_adoption", True),
            (["customer_voice"], "governance", False),
            (["third_party_filing"], "governance", True),
            (["macro_series"], "macro_sensitivity", True),
            (["macro_series"], "customer_adoption", False),
            (["company_owned"], "customer_adoption", False),
            ([], "price_behaviour", True)):
        assert assess(classes, hypothesis_kind=kind).satisfied is expected, \
            (classes, kind)
