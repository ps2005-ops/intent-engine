"""Several products is not a portfolio run as one.

MEASURED WORST OF THE SEVEN remaining ungated patterns: it fired on ordinary
multi-product-suite copy, reached HubSpot, Microsoft and Stripe live, and
declared no disconfirmers at all.

`when_it_applies` is a CONJUNCTION — the company "reports several segments AND
describes owning both the content or product and the channel that distributes
it". The gate was any two of `segment_reporting`, `content_and_channel` and
`multi_product`, so "operating segments" plus "our product portfolio"
qualified, which is every multi-product filer.

BOTH HALVES ARE NOW REQUIRED, and the second half was added only after the
first deploy of this gate found a new false positive live. See
`test_a_coupling_without_separate_disclosure_is_just_good_engineering`.
"""
from __future__ import annotations

import pytest

from intent_engine.strategic_intelligence.observations import derive_observations
from intent_engine.strategic_intelligence.patterns import (
    HYPOTHESIS_SCAFFOLDS, PATTERN_LIBRARY,
)
from intent_engine.strategic_intelligence.reasoning import _hypothesis_for

PATTERNS = {p.pattern_id: p for p in PATTERN_LIBRARY}
PRAO = PATTERNS["portfolio_run_as_one"]
SCAFFOLD = HYPOTHESIS_SCAFFOLDS["portfolio_run_as_one"]
COUPLINGS = ("content_and_channel", "cross_product_coupling",
             "shared_data_model")


def _fires(text, company="Acme"):
    obs = derive_observations([{
        "source_id": "s1", "source_type": "product", "title": company,
        "final_url": "https://acme.example/", "meta_description": "",
        "text_content": text, "retrieval_status": "OK", "freshness": "CURRENT",
        "content_hash": "s1", "retrieved_at": "2026-08-07",
        "parser_version": "p1"}], company=company)
    return _hypothesis_for(PRAO, SCAFFOLD, obs, company)


# --- the contract mirrors the prose ------------------------------------------

def test_both_halves_of_the_conjunction_are_required():
    assert PRAO.required_signals == ("segment_reporting",)
    assert set(PRAO.required_any_signals) == set(COUPLINGS)
    assert "reports several segments AND" in PRAO.when_it_applies


def test_the_pattern_can_be_argued_with():
    """It declared no disconfirmers at all, while its own
    `when_it_does_not_apply` described exactly one."""
    assert "independently_operated" in PRAO.disconfirming_signals
    assert "unrelated holdings" in PRAO.when_it_does_not_apply


# --- attributes are not the coupling -----------------------------------------

def test_segments_plus_a_product_list_is_every_multi_product_filer():
    """The measured false positive: HubSpot, Microsoft and Stripe all had it."""
    assert _fires("We report three operating segments. Our product portfolio "
                  "spans the customer lifecycle.") is None


def test_a_coupling_without_separate_disclosure_is_just_good_engineering():
    """FOUND LIVE, AFTER THE FIRST DEPLOY OF THIS GATE.

    Requiring only the coupling qualified Datadog. It genuinely runs "a common
    data model" across its products — but it reports ONE segment, so "reports
    distinct segments while describing them as one connected portfolio" is not
    true of it, and neither is the consequence the statement draws.
    """
    assert _fires("One platform, many products, powered by a common data "
                  "model that is extensible across use cases. Our product "
                  "portfolio keeps growing.") is None


def test_a_decentralised_holding_company_is_the_stated_counter_case():
    assert _fires("We are a holding company. Our businesses operate "
                  "independently as standalone businesses with autonomous "
                  "business units.") is None


# --- three ways the coupling is evidenced ------------------------------------

@pytest.mark.parametrize("coupling", [
    # the media shape the mechanism was written from
    "Xbox first-party content and the hardware it plays on drive each other.",
    # the same coupling in a software company
    "Customers use one account across our products, with unified billing.",
    "Every product runs on a shared data model.",
])
def test_segments_plus_a_real_coupling_still_qualifies(coupling):
    """The gate must not be a mute button."""
    assert _fires("We report operating segments for each business. "
                  + coupling) is not None


def test_the_reading_quotes_the_coupling_that_earned_it():
    from intent_engine.strategic_intelligence import mechanism as MECH
    fired = _fires("Segment results are reported. Customers use one account "
                   "across our products with unified billing.")
    assert fired is not None
    assert MECH.is_explained(fired)
    assert "one account across" in MECH.because_line(fired).lower()


# --- it stays distinct from its neighbours -----------------------------------

def test_this_pattern_is_not_a_synonym_for_the_platform_ones():
    """`product_to_platform` is about outsiders depending on you;
    `portfolio_run_as_one` is about your own businesses being coupled while
    disclosed apart. If their gates ever coincide, one of them is redundant
    and a company would receive both for the same evidence."""
    p2p = set(PATTERNS["product_to_platform"].required_any_signals)
    prao = set(PRAO.required_any_signals)
    assert not (p2p & prao), "the two gates have collapsed into synonyms"
