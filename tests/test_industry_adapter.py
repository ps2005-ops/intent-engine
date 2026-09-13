"""The industry evidence adapter.

Load-bearing tests, in order of what they protect:
  1. a company's own press release syndicated through a news feed is still the
     company speaking -- the specific gaming route this adapter must not open;
  2. publication dates are never inferred, substituted or clamped;
  3. independence and relevance are both required, never traded off.
"""
import pytest

from intent_engine.market.corroboration import Category
from intent_engine.market.industry import (
    IndustryDocument,
    IndustryUnavailable,
    classify_publisher,
    fetch_industry_evidence,
    independent_documents,
    is_relevant,
)

AS_OF = "2026-07-30"


def _feed(items):
    body = "".join(
        f"<item><title>{t}</title><link>{u}</link>"
        f"<pubDate>{d}</pubDate><source>{p}</source>"
        f"<description>{desc}</description></item>"
        for t, u, d, p, desc in items)
    return f"<rss><channel>{body}</channel></rss>".encode()


def _opener(items):
    def _open(url, timeout):
        return _feed(items)
    return _open


def _doc(title="Merchant adoption accelerates", publisher="Reuters",
         category=Category.INDUSTRY, excerpt=""):
    return IndustryDocument(url="https://x", publisher=publisher, title=title,
                            published_at="2026-07-20",
                            retrieved_at="2026-07-30T00:00:00+00:00",
                            category=category, excerpt=excerpt)


# --- authorship, not venue ---------------------------------------------------
def test_a_company_press_release_in_a_news_feed_is_still_the_company():
    """THE guard. Pulling a company's own releases through a third-party
    aggregator and counting them as independent corroboration is the exact
    gaming route this adapter must keep shut."""
    assert classify_publisher("Shopify", "Shopify Inc.") == Category.COMPANY
    assert classify_publisher("Shopify Newsroom", "Shopify Inc.") \
        == Category.COMPANY


def test_a_press_release_wire_is_the_company_speaking():
    for wire in ("GlobeNewswire", "PR Newswire", "Business Wire"):
        assert classify_publisher(wire, "Acme Corp") == Category.COMPANY, wire


def test_an_analyst_outlet_is_analyst_not_industry():
    for pub in ("Zacks", "The Motley Fool", "Simply Wall St"):
        assert classify_publisher(pub, "Acme Corp") == Category.ANALYST, pub


def test_a_journalist_is_industry():
    for pub in ("Reuters", "CBC", "Gizmodo", "Financial Times"):
        assert classify_publisher(pub, "Acme Corp") == Category.INDUSTRY, pub


def test_a_short_company_root_does_not_swallow_unrelated_publishers():
    """"BP" must not classify "BBC" as the company."""
    assert classify_publisher("BBC", "BP plc") == Category.INDUSTRY


# --- point in time -----------------------------------------------------------
def test_documents_published_after_as_of_are_rejected_not_clamped():
    docs = fetch_industry_evidence(
        "Acme", as_of=AS_OF, opener=_opener([
            ("Old news", "https://a", "Mon, 20 Jul 2026 10:00:00 GMT",
             "Reuters", ""),
            ("Tomorrow's news", "https://b", "Fri, 31 Jul 2026 10:00:00 GMT",
             "Reuters", ""),
        ]))
    assert [d.title for d in docs] == ["Old news"]
    assert all(d.published_at <= AS_OF for d in docs)


def test_an_unparseable_date_drops_the_document():
    """A fabricated publication time is the one error that would silently
    defeat every point-in-time guarantee downstream."""
    docs = fetch_industry_evidence(
        "Acme", as_of=AS_OF, opener=_opener([
            ("No date", "https://a", "not a date", "Reuters", ""),
            ("Good", "https://b", "Mon, 20 Jul 2026 10:00:00 GMT",
             "Reuters", ""),
        ]))
    assert [d.title for d in docs] == ["Good"]


def test_the_publication_date_is_the_feeds_own_never_the_retrieval_time():
    docs = fetch_industry_evidence(
        "Acme", as_of=AS_OF, opener=_opener([
            ("X", "https://a", "Mon, 20 Jul 2026 10:00:00 GMT", "Reuters", "")]))
    assert docs[0].published_at == "2026-07-20"
    assert docs[0].retrieved_at != docs[0].published_at


# --- metadata is preserved, not invented -------------------------------------
def test_every_document_carries_its_provenance():
    docs = fetch_industry_evidence(
        "Acme", as_of=AS_OF, opener=_opener([
            ("Title here", "https://example/a",
             "Mon, 20 Jul 2026 10:00:00 GMT", "Reuters", "an excerpt")]))
    d = docs[0]
    assert d.url and d.publisher and d.title and d.published_at
    assert d.retrieved_at and d.category and d.source


def test_a_transport_failure_raises_rather_than_returning_nothing():
    def _boom(url, timeout):
        raise OSError("network down")
    with pytest.raises(IndustryUnavailable):
        fetch_industry_evidence("Acme", as_of=AS_OF, opener=_boom)


def test_a_malformed_feed_raises():
    with pytest.raises(IndustryUnavailable):
        fetch_industry_evidence("Acme", as_of=AS_OF,
                                opener=lambda u, t: b"not xml")


# --- relevance ---------------------------------------------------------------
def test_relevance_is_per_hypothesis_not_global():
    adoption = _doc("Merchant adoption accelerates across the platform")
    assert is_relevant(adoption, "customer_adoption")
    assert not is_relevant(adoption, "governance")


def test_a_ceo_biography_does_not_corroborate_customer_adoption():
    """Industry-authored and silent on the claim."""
    bio = _doc("A profile of the chief executive's early career")
    assert not is_relevant(bio, "customer_adoption")


def test_a_governance_investigation_corroborates_governance_only():
    gov = _doc("Board faces activist investigation over proxy vote")
    assert is_relevant(gov, "governance")
    assert not is_relevant(gov, "customer_adoption")


# --- both conditions, never traded off ---------------------------------------
def test_independent_and_relevant_are_both_required():
    company_relevant = _doc("Merchant adoption accelerates",
                            publisher="Acme", category=Category.COMPANY)
    independent_irrelevant = _doc("A profile of the chief executive")
    both = _doc("Merchant adoption accelerates")

    kept = independent_documents(
        [company_relevant, independent_irrelevant, both], "customer_adoption")
    assert kept == [both]
