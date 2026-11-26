"""A run that read real evidence produces at least a limited report.

Round 7 (2026-11-26) left 9 companies with no strategic report. Two shared
causes, each with its floor asserted on both sides:

  * OUTSIDE-IN. Lansweeper's own site refused us and five trade-press
    articles were read; every outside article is one family ("independent"),
    so the run tripped "dominant family" and "no official page" and produced
    nothing. Outside articles by >= 2 publishers (>= 3 of them) may carry a
    LIMITED report -- never a full one.
  * THE READABLE PART. BlackLine's five English sources (three filings, its
    blog, an outside article) sat beside six German pages; the run was
    refused on the English SHARE alone. A substantive English subset that
    clears the limited floor carries a limited report on its own.
"""
from __future__ import annotations

from intent_engine.company_ingestion import readiness as R

ID = {"entity_resolved": True}
PARA = ("The company announced a new product line for enterprise finance "
        "teams this quarter and said the release extends its planning "
        "platform to mid-sized customers across North America and Europe. ")


def _article(n, host, sid=None):
    return {"source_id": sid or f"{host}-{n}", "retrieval_status": "OK",
            "source_class": "independent_reporting", "source_type": "article",
            "final_url": f"https://www.{host}/2026/0{n}/story-{n}",
            "published_date": f"2026-0{n}-1{n}",
            "title": f"Story {n} about Acme",
            "text_content": f"Acme item {n}. " + PARA * 3 + f" Detail {n}."}


def _own(kind, n, text):
    return {"source_id": f"own-{n}", "retrieval_status": "OK",
            "source_class": "company_owned", "source_type": kind,
            "final_url": f"https://acme.example/{kind}-{n}",
            "title": kind, "text_content": text}


def test_outside_articles_from_two_publishers_carry_a_limited_report():
    docs = [_article(1, "siliconangle.com"), _article(2, "betakit.com"),
            _article(3, "siliconangle.com")]
    a = R.assess_readiness(documents=docs, identity=ID)
    assert a["material_level"] == "limited" and a["may_synthesize"]
    assert not a["full_report_allowed"]


def test_one_publisher_is_not_an_outside_account():
    """CONTROL: three articles from ONE publisher are one voice."""
    docs = [_article(n, "siliconangle.com") for n in (1, 2, 3)]
    assert not R.assess_readiness(documents=docs, identity=ID)["may_synthesize"]


def test_two_articles_are_below_the_outside_in_floor():
    """CONTROL: Epicor/Softchoice-sized evidence still stays honest."""
    docs = [_article(1, "siliconangle.com"), _article(2, "betakit.com")]
    assert not R.assess_readiness(documents=docs, identity=ID)["may_synthesize"]


GERMAN = ("Die Gesellschaft fertigt Getriebe für Windkraftanlagen und "
          "industrielle Antriebe an drei Standorten in Deutschland und Polen, "
          "und der Vorstand berichtet über die Entwicklung der Segmente. ") * 4


def test_a_substantive_english_part_carries_a_limited_report():
    english = [_own("homepage", 1, "Homepage. " + PARA * 8),
               _own("blog", 2, "Our blog. " + PARA * 8),
               _article(3, "siliconangle.com")]
    german = [_own("about", 10 + n, GERMAN + f" Seite {n}.") for n in range(5)]
    a = R.assess_readiness(documents=english + german, identity=ID)
    assert a["readable_share"] < R.MIN_ENGLISH_SHARE
    assert a["material_level"] == "limited" and a["may_synthesize"]
    assert not a["full_report_allowed"]


def test_a_few_english_words_do_not_stand_for_the_company():
    """CONTROL: the a3 adversarial shape -- tiny pages that pass as English."""
    english = [_own("homepage", 1, "Acme products. Gearboxes, service."),
               _own("product", 2, "Planetary gearboxes and service plans.")]
    german = [_own("about", 10 + n, GERMAN + f" Seite {n}.") for n in range(5)]
    a = R.assess_readiness(documents=english + german, identity=ID)
    assert not a["may_synthesize"]
    assert "readable_language" in a["failed_checks"]
