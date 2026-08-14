"""A company name is enough to start an analysis.

The entry form used to require a website, which meant the user did the
identity resolution and the product did none.
"""
from __future__ import annotations

import pytest

from intent_engine.company_ingestion import name_entry as NE


@pytest.mark.parametrize("typed,expect_domain", [
    ("Cloudflare", "cloudflare.com"),
    ("Boeing", "boeing.com"),
    ("Stripe", "stripe.com"),
    ("Bank of America", "bankofamerica.com"),
    ("Johnson & Johnson", "jnj.com"),
    ("McKinsey", "mckinsey.com"),
])
def test_a_plain_company_name_resolves_to_a_real_domain(typed, expect_domain):
    r = NE.resolve(company_name=typed)
    assert r.resolved, typed
    assert r.website.endswith(expect_domain)


def test_a_short_name_meets_its_legal_name():
    # A CEO types "AMD", not "Advanced Micro Devices, Inc." Zero of the 100
    # manifest entries carry an alias, so exact-name lookup misses exactly
    # the forms people use.
    r = NE.resolve(company_name="AMD")
    assert r.resolved
    assert r.company_name == "Advanced Micro Devices, Inc."
    assert r.website.endswith("amd.com")


def test_leading_words_meet_a_longer_legal_name():
    r = NE.resolve(company_name="Agnico Eagle")
    assert r.resolved
    assert r.company_name.startswith("Agnico Eagle")


def test_corporate_suffixes_do_not_block_a_match():
    assert NE.resolve(company_name="Cloudflare, Inc.").resolved
    assert NE.resolve(company_name="The Boeing Company").resolved


def test_case_and_spacing_do_not_matter():
    assert NE.resolve(company_name="  cloudflare  ").resolved


def test_one_name_naming_two_companies_asks_rather_than_picks():
    r = NE.resolve(company_name="Sony")
    assert r.state == NE.AMBIGUOUS_COMPANY
    assert len(r.choices) >= 2
    # Picking one produces a confident report about the wrong company.
    assert not r.resolved


def test_an_unknown_name_is_a_state_not_an_error():
    r = NE.resolve(company_name="Zzzz Nonexistent Holdings")
    assert r.state == NE.COMPANY_NOT_FOUND
    assert not r.resolved
    assert "privately held" in r.reason or "not yet analysed" in r.reason


def test_a_website_alone_is_enough_for_a_company_nobody_has_registered():
    r = NE.resolve(company_name="Acme Widgets",
                   website="https://acme-widgets.example")
    assert r.resolved
    assert r.website == "https://acme-widgets.example"


def test_a_domain_is_never_invented_for_an_unknown_company():
    # Guessing acme.com for "Acme Industrial Supply" points the whole
    # retrieval pipeline at somebody else's website.
    r = NE.resolve(company_name="Acme Industrial Supply")
    assert r.website == ""


def test_an_empty_name_is_not_found_rather_than_a_crash():
    assert NE.resolve(company_name="").state == NE.COMPANY_NOT_FOUND


def test_resolution_carries_what_a_reader_needs_to_confirm_the_company():
    r = NE.resolve(company_name="Bank of America")
    assert r.ticker or r.sector
    assert r.public_private in ("PUBLIC", "PRIVATE", "")
    assert r.source


# --- the entry form ---------------------------------------------------------

def test_the_landing_form_requires_only_the_company_name():
    from intent_engine.founder_intelligence import presentation as P
    page = P.render_landing_html()
    company = page.split('name="company_name"')[1][:200]
    website = page.split('name="website"')[1][:200]
    assert "required" in company
    assert "required" not in website
