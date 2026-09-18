"""Two companies of the same model class may not get the same sentence.

MEASURED across the 50-company gauntlet: the business-model sentence was
written per MODEL CLASS, and 79 of 990 pairs came out BYTE-IDENTICAL.

    Adobe == Cloudflare == Microsoft == Salesforce == Shopify
    Alphabet == Meta
    Amazon == The Home Depot

    "software platform business that runs on recurring software
     subscription: revenue is contracted and renews"              x5
    "semiconductor business that runs on design and manufacture of a
     physical product sold into a capacity-constrained supply chain"  x6

The class stays as a PRIOR -- it is how the engine knows which questions this
kind of business is judged on. It may no longer BE the answer. The particulars
come from the subject's own filings, and there is no table keyed on a company
name anywhere in this path.
"""
import re

from intent_engine.executive.economic_architecture import (
    EconomicArchitecture, architecture_of, describe, _segment_names,
)

CIK_ADOBE, CIK_CLOUDFLARE = "796343", "1477333"

#: Real sentences, from the two 10-Ks that produced the identical output.
ADOBE = (
    "Adobe is a global technology company. We deliver end-to-end "
    "professional creative and marketing solutions to our customers. "
    "We have three reportable segments: Digital Media, Digital Experience "
    "and Publishing and Advertising. Revenue is derived from the sale of "
    "cloud-enabled software subscriptions, term-based, royalty, and "
    "perpetual software licenses, associated software maintenance and "
    "support plans. Our customers are creative professionals, marketers "
    "and enterprises of every size across many industries. ")
CLOUDFLARE = (
    "We provide a broad range of services to businesses of all sizes and "
    "in all geographies, making them more secure and enhancing the "
    "performance of their business-critical applications. Revenue is "
    "generated from pay-as-you-go and contracted customers and is "
    "comprised of subscription fees to access its network and products, "
    "support services, and usage-based fees. We operate in a very "
    "competitive and rapidly changing environment. ")
CLASS_PRIOR = "recurring software subscription: revenue is contracted and renews"


def _doc(cik, text, source_id="s1"):
    return {"source_id": source_id, "text_content": text,
            "final_url": f"https://www.sec.gov/Archives/edgar/data/{cik}/x/a.htm"}


def _arch(cik, text, company):
    return architecture_of([_doc(cik, text)], company=company,
                           subject_cik=cik)


def test_two_companies_of_one_class_do_not_share_a_sentence():
    """THE DEFECT, end to end."""
    a = describe(_arch(CIK_ADOBE, ADOBE, "Adobe Inc."), name="Adobe Inc.",
                 sector="software platform", class_prior=CLASS_PRIOR)
    c = describe(_arch(CIK_CLOUDFLARE, CLOUDFLARE, "Cloudflare, Inc."),
                 name="Cloudflare, Inc.", sector="software platform",
                 class_prior=CLASS_PRIOR)
    assert a and c
    assert a != c
    # And neither is the class prior wearing a name.
    assert CLASS_PRIOR not in a, a
    assert CLASS_PRIOR not in c, c


def test_each_sentence_carries_that_company_s_own_economics():
    a = describe(_arch(CIK_ADOBE, ADOBE, "Adobe Inc."), name="Adobe Inc.",
                 sector="software platform", class_prior=CLASS_PRIOR)
    c = describe(_arch(CIK_CLOUDFLARE, CLOUDFLARE, "Cloudflare, Inc."),
                 name="Cloudflare, Inc.", sector="software platform",
                 class_prior=CLASS_PRIOR)
    # BOTH halves of the sentence, because each is a separate producer and
    # a test that only reads one leaves the other unguarded.
    assert "creative and marketing solutions" in a, a   # what_is_sold
    assert "perpetual software licenses" in a, a        # revenue_basis
    assert "broad range of services" in c, c            # what_is_sold
    assert "pay-as-you-go" in c, c                      # revenue_basis
    assert "usage-based" in c, c


def test_the_class_prior_still_serves_a_company_that_says_nothing():
    """THE CONTROL. A filing with no readable business section is exactly as
    well served as it was before, never worse."""
    bare = _arch(CIK_ADOBE, "This filing contains only exhibits. " * 12,
                 "Adobe Inc.")
    assert bare.is_specific is False
    out = describe(bare, name="Adobe Inc.", sector="software platform",
                   class_prior=CLASS_PRIOR)
    assert CLASS_PRIOR in out, out


def test_a_rivals_filing_never_describes_the_subject():
    """Ownership is checked: a sentence in someone else's 10-K is theirs."""
    arch = architecture_of([_doc(CIK_CLOUDFLARE, CLOUDFLARE, "s9")],
                           company="Adobe Inc.", subject_cik=CIK_ADOBE)
    assert arch.measured == ()
    assert arch.is_specific is False


def test_no_cik_reads_nothing_rather_than_guessing():
    arch = architecture_of([_doc(CIK_ADOBE, ADOBE)], company="Adobe Inc.",
                           subject_cik="")
    assert arch.is_specific is False


def test_we_operate_in_a_market_is_not_what_a_company_sells():
    """It matched "We operate in a very competitive and rapidly changing
    environment" and rendered a risk factor as Cloudflare's product.

    THE FIXTURE HAS NO OTHER CANDIDATE. Cloudflare's real filing says "We
    provide a broad range of services" earlier in the text, so that sentence
    wins on position whatever the verb list allows -- and a first version of
    this test therefore passed with "operate" put back. The risk is a filing
    whose ONLY matching sentence is the risk factor, which is what this is.
    """
    only_a_risk_factor = (
        "We operate in a very competitive and rapidly changing environment "
        "that could harm our business. Competition is intense across every "
        "market we address and we expect it to increase over time. ") * 6
    arch = _arch(CIK_CLOUDFLARE, only_a_risk_factor, "Cloudflare, Inc.")
    assert "competitive and rapidly changing" not in arch.what_is_sold, arch
    assert arch.what_is_sold == "", arch.what_is_sold

    # And the real filing is still read correctly.
    real = _arch(CIK_CLOUDFLARE, CLOUDFLARE, "Cloudflare, Inc.")
    assert "broad range of services" in real.what_is_sold, real.what_is_sold


def test_segments_use_the_count_the_filing_states():
    """Adobe's third segment is "Publishing and Advertising", one segment."""
    assert _segment_names(
        "three", "Digital Media, Digital Experience and Publishing and "
                 "Advertising") == ("Digital Media", "Digital Experience",
                                    "Publishing and Advertising")
    assert _segment_names(
        "three", "Productivity and Business Processes, Intelligent Cloud "
                 "and More Personal Computing") == (
        "Productivity and Business Processes", "Intelligent Cloud",
        "More Personal Computing")
    assert _segment_names("two", "Consumer and Commercial") == (
        "Consumer", "Commercial")


def test_a_listing_that_disagrees_with_its_count_reports_nothing():
    """A guess about how many segments a company has is worse than silence."""
    assert _segment_names("four", "Alpha, Beta") == ()


def test_several_segments_are_several_engines():
    """§5. A multi-segment company may not be flattened into one class."""
    arch = _arch(CIK_ADOBE, ADOBE, "Adobe Inc.")
    assert arch.segments == ("Digital Media", "Digital Experience",
                             "Publishing and Advertising")
    assert arch.multi_engine is True
    assert _arch(CIK_CLOUDFLARE, CLOUDFLARE,
                 "Cloudflare, Inc.").multi_engine is False


def test_it_never_raises_on_junk():
    for documents in ([], [{}], [{"text_content": None}], None):
        assert architecture_of(documents, company="X",
                               subject_cik="1").company == "X"
