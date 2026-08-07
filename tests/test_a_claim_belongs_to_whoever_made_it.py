"""Correct mechanism, wrong subject — the last reasoning class to close.

WHAT WAS MEASURED. On the deployed build at `037f805`, Microsoft's two-buyers
reading was evidenced by its own 10-K:

    "Our competitors are developing new software and devices, while also
     deploying competing cloud-based services for consumers and businesses."

The pair phrase is present. The buyers are the competitors'. Signal detection
asked only "does this phrase appear in this document", so ownership was
inferred from proximity and nothing else.

WHY THE OBVIOUS FIX IS WRONG, and was nearly written. Amazon's evidence for
the same reading came from the same kind of paragraph:

    "Our competitors include ... producers of the products we offer and sell
     to consumers and businesses."

Outer subject also "Our competitors" — but the phrase sits in a relative
clause whose subject is "we", and Amazon really does sell to both. A filter
that rejected any sentence mentioning competitors would have deleted a true
signal and been called a fix. So ownership is decided by the NEAREST
GOVERNING SUBJECT to the left of the match.

This file is the adversarial suite: every way a foreign actor can appear next
to a phrase this system reads.
"""
from __future__ import annotations

import pytest

from intent_engine.strategic_intelligence import subject as SUBJ
from intent_engine.strategic_intelligence.observations import (
    _NEUTRAL_SIGNAL_KEYWORDS, _detect_signals, derive_observations,
    owned_match, phrase_span, signal_spans,
)

PHRASE = "consumers and businesses"          # a `segment_split` pair phrase
SOR = "system of record for"                 # a mechanism phrase


def _at(sentence, needle=PHRASE):
    return sentence.lower().find(needle.lower())


# --- the two live cases, kept exactly as measured ----------------------------

MICROSOFT = ("Our competitors are developing new software and devices, while "
             "also deploying competing cloud-based services for consumers and "
             "businesses.")
AMAZON = ("Our competitors include (1) physical, e-commerce, and omnichannel "
          "retailers, publishers, vendors, distributors, manufacturers, and "
          "producers of the products we offer and sell to consumers and "
          "businesses.")


def test_the_microsoft_sentence_belongs_to_its_competitors():
    assert SUBJ.subject_of(MICROSOFT, _at(MICROSOFT), "Microsoft") == SUBJ.FOREIGN


def test_the_amazon_sentence_belongs_to_amazon():
    """The near-miss. A whole-sentence competitor filter fails this."""
    assert SUBJ.subject_of(AMAZON, _at(AMAZON), "Amazon") == SUBJ.OWN


def test_the_two_live_cases_are_distinguished_end_to_end():
    ms = "Microsoft builds software. " + MICROSOFT
    az = "Amazon sells online. " + AMAZON
    assert "segment_split" not in _detect_signals(ms, "company_owned",
                                                  "Microsoft")
    assert "segment_split" in _detect_signals(az, "company_owned", "Amazon")


# --- every way somebody else can own the clause ------------------------------

@pytest.mark.parametrize("role,sentence", [
    ("competitor",
     "Our competitors sell to consumers and businesses."),
    ("rival",
     "Rivals in this space target consumers and businesses."),
    ("analyst",
     "Analysts expect vendors to court consumers and businesses."),
    ("regulator",
     "Regulators supervise firms serving consumers and businesses."),
    ("third party",
     "Third parties build integrations for consumers and businesses."),
    ("industry",
     "The industry has shifted toward consumers and businesses."),
    ("other companies",
     "Other companies in the sector serve consumers and businesses."),
])
def test_a_claim_owned_by_someone_else_is_not_evidence_about_us(role, sentence):
    assert SUBJ.subject_of(sentence, _at(sentence), "Acme") == SUBJ.FOREIGN, role
    assert "segment_split" not in _detect_signals(sentence, "company_owned",
                                                  "Acme"), role


@pytest.mark.parametrize("sentence", [
    "We sell to consumers and businesses.",
    "Acme sells to consumers and businesses.",
    "The company serves consumers and businesses alike.",
    "Our platform is used by consumers and businesses.",
    # the shape that matters most: a foreign subject earlier in the sentence,
    # our own subject nearer the phrase
    "Unlike our competitors, we serve consumers and businesses directly.",
    "Where rivals focus on one, the company sells to consumers and businesses.",
])
def test_a_claim_we_made_is_still_ours(sentence):
    assert SUBJ.subject_of(sentence, _at(sentence), "Acme") == SUBJ.OWN
    assert "segment_split" in _detect_signals(sentence, "company_owned", "Acme")


@pytest.mark.parametrize("sentence", [
    # A COUNTERPARTY ACTING ON OUR PRODUCT IS EVIDENCE ABOUT US.
    # The first version of the foreign list included customers, suppliers,
    # partners and resellers, and it cost two real capabilities.
    "Customers migrate off their old suite and retire legacy systems.",
    "Our customer platform is used by consumers and businesses.",
    "Partners build integrations that reach consumers and businesses.",
])
def test_a_counterparty_acting_on_our_product_is_still_evidence_about_us(
        sentence):
    """`Customers migrate off their old suite` IS the mechanism for
    `replaces_incumbent_systems`; the customer is the actor and the claim is
    about us. And "our CUSTOMER platform" is a compound noun, not a subject —
    treating it as one rejected HubSpot's real mechanism sentence."""
    assert SUBJ.subject_of(sentence, _at(sentence, "consumers and businesses")
                           if "consumers" in sentence else _at(sentence,
                                                               "migrate off"),
                           "Acme") != SUBJ.FOREIGN


def test_an_unattributed_phrase_resolves_to_nobody():
    """Fails closed at the resolver. Detection is more permissive on purpose
    — see `owned_match` — but the resolver must not invent an owner."""
    assert SUBJ.subject_of("Serving consumers and businesses.",
                           _at("Serving consumers and businesses."),
                           "Acme") == SUBJ.UNKNOWN


def test_subjectless_marketing_copy_still_counts_on_the_companys_own_page():
    """The deliberate exception, stated so it cannot drift.

    Product pages are largely imperative and subjectless. Requiring an
    explicit owner would silence most of what a company publishes about
    itself; provenance already establishes whose page it is.
    """
    assert "consolidation" in _detect_signals(
        "Replace several separate tools with one workspace where all of your "
        "team's work lives in one place.", "company_owned", "Acme")


# --- the mechanism evidence must obey the same rule --------------------------

def test_a_mechanism_is_not_quoted_from_a_competitors_sentence():
    text = ("Acme builds tools. Our competitors position themselves as the "
            "system of record for the enterprise. We integrate with them.")
    assert "system_of_record_claim" not in _detect_signals(
        text, "company_owned", "Acme")
    assert not phrase_span(
        text, _NEUTRAL_SIGNAL_KEYWORDS["system_of_record_claim"], "Acme")


def test_a_mechanism_we_do_claim_is_still_quoted():
    text = ("Acme builds tools. We are the system of record for your customer "
            "data.")
    span = phrase_span(text, _NEUTRAL_SIGNAL_KEYWORDS["system_of_record_claim"],
                       "Acme")
    assert "system of record for your customer data" in span


def test_the_span_skips_the_foreign_occurrence_and_finds_ours():
    """Both in one document, which is the realistic case for a filing."""
    text = ("Our competitors claim to be the system of record for the "
            "enterprise. Acme is the system of record for your customer data.")
    span = phrase_span(text, _NEUTRAL_SIGNAL_KEYWORDS["system_of_record_claim"],
                       "Acme")
    assert "Acme is the system of record for your customer data" in span
    assert "competitors" not in span


def test_the_observation_records_only_owned_spans():
    doc = {"source_id": "s1", "source_type": "product", "title": "Acme",
           "final_url": "https://acme.example/", "meta_description": "",
           "text_content": "Our competitors are the system of record for the "
                           "enterprise. We sell to consumers and businesses.",
           "retrieval_status": "OK", "freshness": "CURRENT",
           "content_hash": "s1", "retrieved_at": "2026-08-06",
           "parser_version": "p1"}
    obs = derive_observations([doc], company="Acme")
    assert obs
    spans = obs[0].signal_spans
    assert "system_of_record_claim" not in spans
    assert "consumers and businesses" in spans.get("segment_split", "")


# --- properties of the resolver itself ---------------------------------------

def test_the_nearest_subject_wins_not_the_first():
    """The whole design in one assertion. `our` opens both live sentences;
    what differs is which subject sits closest to the phrase."""
    near_foreign = "Our team noted that competitors serve consumers and businesses."
    near_own = "Competitors exist, but we serve consumers and businesses."
    assert SUBJ.subject_of(near_foreign, _at(near_foreign), "Acme") == SUBJ.FOREIGN
    assert SUBJ.subject_of(near_own, _at(near_own), "Acme") == SUBJ.OWN


def test_an_adjective_is_not_a_subject():
    """`competing` describes a product; matching `compet\\w*` would reject the
    sentence in which a company names its OWN competing offer."""
    s = "We launched a competing product for consumers and businesses."
    assert SUBJ.subject_of(s, _at(s), "Acme") == SUBJ.OWN


def test_a_short_company_token_cannot_grant_ownership():
    """A two-letter fragment matches inside other words and would hand
    ownership to any sentence containing it."""
    assert SUBJ._company_tokens("TD Bank Group") == ("Bank",)
    assert "TD" not in SUBJ._company_tokens("TD Bank Group")


def test_the_search_is_bounded_so_a_filing_cannot_stall_it():
    from intent_engine.strategic_intelligence.observations import (
        _MAX_OCCURRENCES,
    )
    assert _MAX_OCCURRENCES >= 5
    crowd = ("Our competitors serve consumers and businesses. " * 400
             + "We serve consumers and businesses.")
    # the owned sentence is far past the cap, so this fails CLOSED
    assert owned_match(crowd, ("consumers and businesses",), "Acme") is None


def test_ownership_is_not_decided_by_the_document_it_appears_in():
    """The property the old detector violated: a phrase anywhere in the text
    qualified the signal, whatever the sentence said."""
    text = ("Acme builds developer tools. " * 3
            + "Our competitors serve consumers and businesses.")
    assert "consumers and businesses" in text
    assert "segment_split" not in _detect_signals(text, "company_owned", "Acme")
