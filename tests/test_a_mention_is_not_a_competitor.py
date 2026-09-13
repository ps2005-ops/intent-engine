"""Being named in a filing does not make you a rival.

MEASURED on the deployed product. Every filing EDGAR full-text search
returned for Meta Platforms arrived stamped `source_class: "competitor"` —
the class was a constant, not a finding — and graded DIRECTLY_RELEVANT,
because relevance counted passages instead of reading them:

    Oklo         "prepayment agreement with Meta Platforms, Inc."   CUSTOMER
    Network-1    "our case against Meta Platforms, Inc."            LITIGATION
    Enbridge     an excerpt that never named Meta at all            INCIDENTAL
    RingCentral  a list of the products it competes with            COMPETITOR

Three of the four were wrong, and a customer read the result as this
company's competitive position.

The tests below are adversarial by construction: each supplies a real
relationship that a "mentioned in a filing" rule would have called
competition, and requires that it does not.
"""
from __future__ import annotations

import pytest

from intent_engine.executive import relationship as R

SUBJECT = "Meta Platforms, Inc."


def _kind(text, subject=SUBJECT, counterparty="Other Co."):
    return R.classify_relationship(subject=subject, counterparty=counterparty,
                                   text=text).relationship_type


# ===========================================================================
# the four measured cases
# ===========================================================================
def test_a_supply_agreement_is_not_competition():
    """Oklo sells Meta power. Filed as a competitor."""
    assert _kind("prepayment agreement with Meta Platforms, Inc.") == R.CUSTOMER


def test_a_lawsuit_is_not_competition():
    """Network-1 sued Meta. A litigant is not a market."""
    assert _kind("Court of Appeals for the Federal Circuit of the District "
                 "Court judgment of non-infringement dismissing our case "
                 "against Meta Platforms, Inc.") == R.LITIGATION


def test_a_span_that_never_names_the_subject_establishes_nothing():
    """Enbridge's excerpt was capital-allocation boilerplate.

    A search hit guarantees the DOCUMENT names the subject. The span
    selected from it need not, and a span that does not name the subject
    cannot establish a relationship to the subject.
    """
    assert _kind("Extend growth through disciplined capital allocation. "
                 "Placed $5 billion of secured growth capital into service.") \
        == R.INCIDENTAL_MENTION


def test_a_rival_naming_its_market_is_competition():
    assert _kind("We compete with Google G-Suite and Meet, Meta Platforms, "
                 "Inc., Microsoft Teams and Slack Technologies, Inc.") \
        == R.COMPETITOR


# ===========================================================================
# adversarial: every non-competitive relationship (§1)
# ===========================================================================
@pytest.mark.parametrize("text,expected", [
    ("Our partnership with Meta Platforms, Inc. expanded this year.",
     R.PARTNER),
    ("We purchase advertising inventory from Meta Platforms, Inc.",
     R.SUPPLIER),
    ("Our largest customers include Meta Platforms, Inc. and others.",
     R.CUSTOMER),
    ("We hold an equity interest in Meta Platforms, Inc.", R.INVESTOR),
    ("Our applications are distributed through Meta Platforms, Inc.",
     R.DISTRIBUTION),
    ("Changes by mobile operating system providers such as Meta Platforms, "
     "Inc. may affect us.", R.INFRASTRUCTURE),
])
def test_a_non_competitive_relationship_never_reads_as_competition(text,
                                                                   expected):
    kind = _kind(text)
    assert kind == expected, f"{text[:40]!r} -> {kind}"
    assert kind not in R.COMPETITIVE


def test_only_competitive_relationships_reach_the_ladder():
    for kind in R.RELATIONSHIP_TYPES:
        competitive = kind in (R.COMPETITOR, R.SUBSTITUTE)
        assert (kind in R.COMPETITIVE) is competitive


def test_the_source_class_follows_the_relationship():
    """`competitor` lets a document's market claims speak for the subject."""
    assert R.source_class_for(R.COMPETITOR) == "competitor"
    assert R.source_class_for(R.SUBSTITUTE) == "competitor"
    for kind in (R.CUSTOMER, R.SUPPLIER, R.PARTNER, R.LITIGATION,
                 R.INCIDENTAL_MENTION, R.UNKNOWN):
        assert R.source_class_for(kind) == "independent_reporting"


# ===========================================================================
# the contract on the evidence itself
# ===========================================================================
def test_a_classification_must_quote_the_span_that_produced_it():
    """A verdict beside an excerpt that did not drive it justifies nothing."""
    with pytest.raises(ValueError):
        R.RelationshipEvidence(subject=SUBJECT, counterparty="X",
                               relationship_type=R.COMPETITOR, evidence="",
                               confidence="HIGH")


def test_an_unknown_relationship_needs_no_span_and_is_not_competitive():
    evidence = R.RelationshipEvidence(
        subject=SUBJECT, counterparty="X", relationship_type=R.UNKNOWN,
        evidence="", confidence="LOW")
    assert not evidence.is_competitive


def test_an_invalid_relationship_type_is_refused():
    with pytest.raises(ValueError):
        R.RelationshipEvidence(subject=SUBJECT, counterparty="X",
                               relationship_type="FRENEMY", evidence="x",
                               confidence="LOW")


def test_the_quoted_evidence_is_the_matching_clause_not_the_whole_excerpt():
    """One document carries many signals; one excerpt justifies at most one."""
    text = ("Revenue grew 14% in the period. Our case against Meta "
            "Platforms, Inc. was dismissed. Headcount fell.")
    evidence = R.classify_relationship(subject=SUBJECT, counterparty="X",
                                       text=text)
    assert evidence.relationship_type == R.LITIGATION
    assert "case against" in evidence.evidence
    assert "Headcount fell" not in evidence.evidence


# ===========================================================================
# the wiring — a fix with no caller stays green
# ===========================================================================
def test_the_adapter_derives_the_source_class_rather_than_asserting_it():
    from intent_engine.company_ingestion import third_party_filings as TPF
    candidate = {"url": "https://www.sec.gov/Archives/edgar/data/1/x/a.htm",
                 "filer": "Oklo Inc.", "filer_cik": "1", "form": "10-K",
                 "file_date": "2026-01-01"}
    emitted = TPF._emit(
        candidate, company_name=SUBJECT,
        assessment={"relevance": "DIRECTLY_RELEVANT", "reason": "r",
                    "excerpt": "prepayment agreement with Meta Platforms, "
                               "Inc.",
                    "counted_spans": ["prepayment agreement with Meta "
                                      "Platforms, Inc."],
                    "substantive_mentions": 7})
    assert emitted["relationship_type"] == R.CUSTOMER
    assert emitted["source_class"] == "independent_reporting"
