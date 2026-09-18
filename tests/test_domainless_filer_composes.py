"""A company identified by CIK alone is still a company.

Typed entry resolves any SEC registrant, and the regulator records no web
domain — so a run legitimately opens with an empty website. Composition then
raised `UnsafeURLRejected: a company website URL is required` for every one of
them, which is why Meta, Toyota and Vale produced bounded, empty analyses
while their own 10-Ks sat retrieved in the store.

The second half of this file covers what happens once such a run DOES
compose: the regulator's industry code is not fine-grained enough to say what
kind of business the filer runs, and taking its word for it is how an
advertising platform gets analysed as a subscription business.
"""
from __future__ import annotations

import pytest

from intent_engine.founder_intelligence.records import (
    CompanyInput, UnsafeURLRejected,
)
from intent_engine.executive.company_profile import (
    profile_for, revenue_model_hint,
)

CONSENT = CompanyInput.__dataclass_fields__["consent_version"].default


def _input(**kw):
    base = dict(company_name="Meta Platforms, Inc.", website="",
                consent_version=CONSENT)
    base.update(kw)
    return CompanyInput(**base)


# ===========================================================================
# a run may have no website
# ===========================================================================
def test_a_filer_with_no_website_still_validates():
    """MEASURED: this raised, and every domainless company failed here."""
    _input().validate()                     # must not raise


def test_a_company_still_needs_a_name():
    with pytest.raises(Exception):
        _input(company_name="").validate()


def test_a_website_that_IS_given_is_still_walled():
    """The SSRF wall is not weakened — it guards URLs we fetch."""
    with pytest.raises(UnsafeURLRejected):
        _input(website="http://localhost/admin").validate()
    with pytest.raises(UnsafeURLRejected):
        _input(website="file:///etc/passwd").validate()


def test_two_domainless_companies_do_not_share_a_run_identity():
    """With no domain the seed prefix is empty for every filer on earth.

    MEASURED while writing this: `analysis_fingerprint` covers the approved
    source set and the pipeline version and NOT the company name, so two
    domainless companies with the same source shape produce an identical
    digest. Keyed on domain alone, that is two different companies sharing
    one run id.
    """
    from intent_engine.founder_intelligence.service import (
        analysis_fingerprint, run_subject_key,
    )
    assert run_subject_key("", "Toyota Motor Corp") != \
        run_subject_key("", "Vale S.A.")
    # The fingerprint alone would NOT have separated them:
    assert analysis_fingerprint(_input(company_name="Toyota Motor Corp")) == \
        analysis_fingerprint(_input(company_name="Vale S.A."))
    # A company that HAS a domain keys on it, unchanged.
    assert run_subject_key("cloudflare.com", "Cloudflare, Inc.") == \
        "cloudflare.com"


# ===========================================================================
# what kind of business it is
# ===========================================================================
_META_SENTENCE = ("Currently, we generate substantially all of our revenue "
                  "from selling advertising placements on our family of apps "
                  "to marketers, which is reflected in FoA.")

_SUBSCRIPTION_FILING = (
    "We sell subscriptions to our platform. Advertising expense was $412 "
    "million for the year, recorded in sales and marketing. Our revenue is "
    "recognised rateably over the contract term.")

_SIC_7370 = {"sic": "7370",
             "sic_description": "Services-Computer Programming, Data "
                                "Processing, Etc."}


def test_meta_is_not_read_as_a_subscription_business():
    """SIC 7370 holds Salesforce AND Meta, whose economics are opposite.

    Classifying from the code alone makes one of them wrong every time, and
    a wrong business model is worse than none: every mechanism, metric and
    competitor downstream is selected from it.
    """
    profile = profile_for(name="Meta Platforms, Inc.", registrant=_SIC_7370,
                          evidence_text=_META_SENTENCE)
    assert profile.known
    assert profile.business_model_class == "ADVERTISING_PLATFORM"


def test_a_subscription_filer_is_not_reclassified_by_an_ad_expense():
    """"Advertising expense" is a COST line in nearly every filing.

    A rule loose enough to match it would reclassify every consumer brand on
    earth as an advertising platform.
    """
    assert revenue_model_hint(_SUBSCRIPTION_FILING) is None
    profile = profile_for(name="Testco, Inc.", registrant=_SIC_7370,
                          evidence_text=_SUBSCRIPTION_FILING)
    assert profile.business_model_class == "SUBSCRIPTION_SOFTWARE"


def test_the_hint_never_promotes_an_unclassified_company():
    """It corrects a classification; it does not manufacture one."""
    profile = profile_for(name="Nobody Ltd", registrant={},
                          evidence_text=_META_SENTENCE)
    assert not profile.known


def test_an_advertising_platform_has_its_own_economics():
    """A tenth row, not a relabelled ninth."""
    from intent_engine.executive.company_profile import _ECONOMICS
    ads = _ECONOMICS["ADVERTISING_PLATFORM"]
    subs = _ECONOMICS["SUBSCRIPTION_SOFTWARE"]
    assert ads["business_model"] != subs["business_model"]
    assert ads["pricing_model"] != subs["pricing_model"]
    # The distinguishing fact: nothing is contracted forward.
    assert "auction" in ads["pricing_model"].lower()
    assert "engagement" in " ".join(ads["revenue_drivers"]).lower()
