"""A four-letter brand with no namesake is identified by its name.

Round 7: every article about Qlik, Deel, Brex and Pax8 needed the company's
domain printed in it to count, because the news channel treated every name
of four letters or fewer as a possible word or acronym.
"""
from __future__ import annotations

from intent_engine.company_ingestion import independent_reporting as IR
from intent_engine.company_ingestion.service import CompanyIngestionService

QLIK = ("Qlik debuts new agentic capabilities for its analytics platform, and "
        "Qlik said customers can now automate data pipelines.")


def test_a_namesake_free_brand_needs_no_anchor():
    assert not IR.needs_identity_anchor("Qlik", QLIK, namesake_free=True)


def test_without_the_registry_s_word_the_strict_rule_stands():
    """CONTROL: an unreviewed short name still needs an anchor."""
    assert IR.needs_identity_anchor("Qlik", QLIK)


def test_an_acronym_always_needs_an_anchor():
    assert IR.needs_identity_anchor("BILL", "BILL launched a card.",
                                    namesake_free=True)


def test_a_name_used_as_a_word_in_the_article_still_needs_one():
    """CONTROL: the per-article lowercase test applies to everyone."""
    assert IR.needs_identity_anchor(
        "Deel", "Deel raised prices, and in Dutch a deel is a part.",
        namesake_free=True)


def test_the_registry_answers_namesake_freedom():
    f = CompanyIngestionService._namesake_free
    assert f({"domain": "qlik.com"}) and f({"domain": "www.brex.com"})
    assert not f({"domain": "ramp.com"})          # LiveRamp, Ramp Network
    assert not f({"domain": "observeinc.com"})    # Observe.AI
    assert not f({"domain": "unknown-co.example"})
