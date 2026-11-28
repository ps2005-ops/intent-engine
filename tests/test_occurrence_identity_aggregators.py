"""One article reached through two Google News redirects is one occurrence.

Strings are from the live ledger, 2026-11-26: 73 same-subject same-sentence
groups survived dedupe because `source` was a per-click redirect token.
"""
from intent_engine.market import micro_evidence as ME

G1 = "https://news.google.com/rss/articles/CBMibkFVX3lxTE9yTFB1Y0RGaFVsR2xV?oc=5"
G2 = "https://news.google.com/rss/articles/CBMic0FVX3lxTE9VbVZJS1pEWlFlYjFR?oc=5"


def key(fact, source, etype="LAYOFF", subject="etsy"):
    return ME.occurrence_key(subject_company=subject, evidence_type=etype,
                             fact=fact, source=source)


def test_two_redirects_to_one_article_are_one_occurrence():
    f = "Etsy Laying Off 12% of Staff in Bid to Streamline Business - Reuters"
    assert key(f, G1) == key(f, G2)


def test_publisher_spellings_are_one_outlet():
    assert key("Weil Company Reduces Position in JPMorgan - MarketBeat.", G1) == \
        key("Weil Company Reduces Position in JPMorgan - marketbeat.com.", G2)


def test_two_outlets_carrying_one_story_stay_two_items():
    f = "MercadoLibre Declines 11.9% Since Q3 Earnings: How to Play MELI Stock"
    assert key(f + " - Yahoo Finance.", G1) != key(f + " - The Globe and Mail", G2)


def test_a_non_aggregator_source_is_unchanged():
    f = "Etsy cuts 12% of workforce - Reuters"
    assert key(f, "https://reuters.com/a") != key(f, "https://reuters.com/b")


def test_evidence_ids_do_not_move():
    """Ids are cited by beliefs; occurrence identity may improve, ids may not."""
    f = "Etsy Laying Off 12% of Staff - Reuters"
    assert ME.evidence_id_for(subject_company="etsy", evidence_type="LAYOFF",
                              fact=f, source=G1) != ME.evidence_id_for(
        subject_company="etsy", evidence_type="LAYOFF", fact=f, source=G2)
