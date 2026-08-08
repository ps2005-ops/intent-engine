"""What a source family actually yields, counted as objects and not actions.

Wave 6 read "Salesforce: 6 documents, 12 actions" as productivity. Every one
of those actions established no object, so the number was measuring the
announcement patterns rather than the source. The metric that decides where
budget goes is established objects per document.
"""
from __future__ import annotations

import pytest

from intent_engine.market import action_object_acquisition as AQ
from intent_engine.market import action_object_queries as Q
from intent_engine.market import competitive_objects as CO


def page(text, title="t"):
    return {"ok": True, "body": f"<html><head><title>{title}</title>"
                                f"</head><body><p>{text}</p></body></html>"}


PRICING_UPDATE = (
    "BigCommerce Plan and Pricing Updates. "
    "Starting June 1, 2026, BigCommerce is updating its plan structure and "
    "pricing. " + ("Details of the change follow below. " * 20))

RELEASE_NOTE = (
    "Shopify Shipping expands to Italy and Spain. " +
    ("Merchants can now buy labels in more places. " * 20))


def fetcher_for(mapping):
    def read(url, **_kw):
        for fragment, body in mapping.items():
            if fragment in url:
                return page(body)
        return {"ok": False}
    return read


# --- a static price is not a price change ---------------------------------

def test_a_static_pricing_page_yields_no_action():
    """The distinction the whole pricing family lives on. A page stating
    what a plan costs today is a fact about the world; nobody did anything
    and no counterparty could respond to it."""
    static = ("Basic. CA$37/mo. For solo entrepreneurs. Grow. CA$99/mo. For "
              "small teams. " + ("Compare plans and features below. " * 20))
    documents, report = AQ.retrieve(
        "Shopify", "https://shopify.test", Q.PRICING_PAGE, as_of="2026-08-08",
        fetcher=fetcher_for({"/pricing": static}), max_pages=2)
    assert report.retrieved >= 1
    actions, objects, _ = AQ.actions_and_objects(documents[0])
    assert actions == ()


def test_a_dated_pricing_update_yields_an_action():
    documents, report = AQ.retrieve(
        "BigCommerce", "https://bigcommerce.test", Q.PRICING_PAGE,
        as_of="2026-08-08", fetcher=fetcher_for({"/pricing": PRICING_UPDATE}),
        max_pages=2)
    actions, objects, _ = AQ.actions_and_objects(documents[0])
    assert any(a.action_type == "PRICE_CHANGE" for a in actions)


def test_an_action_is_never_marked_established_by_the_harness():
    """`object_established` stays False unless the DOCUMENT established one.
    The harness that fetched the page is exactly who must not decide."""
    documents, _ = AQ.retrieve(
        "BigCommerce", "https://bigcommerce.test", Q.PRICING_PAGE,
        as_of="2026-08-08", fetcher=fetcher_for({"/pricing": PRICING_UPDATE}),
        max_pages=2)
    actions, _objects, _ = AQ.actions_and_objects(
        documents[0], competitive_object_label="E-commerce platform")
    assert actions
    assert all(not a.object_established for a in actions)


def test_the_label_passed_through_never_reaches_the_object():
    """A caller may label an evaluation set. It may not supply an object."""
    documents, _ = AQ.retrieve(
        "Shopify", "https://shopify.test", Q.RELEASE_NOTES,
        as_of="2026-08-08",
        fetcher=fetcher_for({"/release-notes": RELEASE_NOTE}), max_pages=2)
    _actions, objects, _ = AQ.actions_and_objects(
        documents[0], competitive_object_label="E-commerce platform")
    for obj in objects.values():
        blob = " ".join(str(v) for v in obj.as_dict().values()).lower()
        assert "e-commerce platform" not in blob


# --- the object comes from the action's own type --------------------------

def test_the_action_type_reaches_the_object_extractor():
    """A migration programme must name what it displaces. If the acquisition
    forgets to pass the type, every action is graded on the generic rule and
    the per-type requirement is dead code."""
    documents, _ = AQ.retrieve(
        "Shopify", "https://shopify.test", Q.RELEASE_NOTES,
        as_of="2026-08-08",
        fetcher=fetcher_for({"/release-notes": RELEASE_NOTE}), max_pages=2)
    actions, objects, _ = AQ.actions_and_objects(documents[0])
    entry = [a for a in actions if a.action_type == "MARKET_ENTRY"]
    assert entry
    obj = objects[entry[0].action_id]
    assert obj.action_type == "MARKET_ENTRY"
    assert obj.dimensions_required == (CO.WHAT, CO.WHERE)


# --- counting -------------------------------------------------------------

def test_established_per_document_is_the_reported_ratio():
    report = AQ.FamilyYield(family=Q.PRICING_PAGE, retrieved=4,
                            actions_found=12, objects_established=1)
    assert report.established_per_document == pytest.approx(0.25)
    assert report.actions_per_document == pytest.approx(3.0)
    assert report.as_dict()["established_per_document"] == 0.25


def test_a_family_can_produce_actions_and_no_objects():
    """The two counts are separate on purpose: 12 actions and 0 objects is
    the exact shape of wave 7's finding, and one number hides it."""
    report = AQ.FamilyYield(family=Q.PRICING_PAGE, retrieved=15,
                            actions_found=12, objects_established=0)
    assert report.actions_per_document > 0
    assert report.established_per_document == 0.0


def test_retrieval_of_nothing_is_zero_not_a_crash():
    documents, report = AQ.retrieve(
        "Nobody", "https://nowhere.test", Q.PRICING_PAGE, as_of="2026-08-08",
        fetcher=lambda url, **_kw: {"ok": False}, max_pages=2)
    assert documents == ()
    assert report.retrieved == 0
    assert report.established_per_document == 0.0
    assert report.refusal_reasons["fetch_not_ok"] >= 1


def test_a_short_page_is_refused_as_a_document():
    documents, report = AQ.retrieve(
        "Shopify", "https://shopify.test", Q.PRICING_PAGE, as_of="2026-08-08",
        fetcher=fetcher_for({"/pricing": "Too short."}), max_pages=2)
    assert documents == ()
    assert report.refusal_reasons["too_short_to_be_a_document"] >= 1


def test_the_performance_table_is_what_the_planner_consumes():
    yields = {
        "Shopify|pricing_page": AQ.FamilyYield(
            family=Q.PRICING_PAGE, retrieved=10, objects_established=0),
        "BigCommerce|pricing_page": AQ.FamilyYield(
            family=Q.PRICING_PAGE, retrieved=5, objects_established=0),
        "Shopify|release_notes": AQ.FamilyYield(
            family=Q.RELEASE_NOTES, retrieved=9, objects_established=5),
    }
    table = AQ.performance_table(yields)
    assert table[Q.PRICING_PAGE] == (0, 15)
    assert table[Q.RELEASE_NOTES] == (5, 9)

    # And feeding it back must demote the family measured at zero.
    plans = Q.plan(actor="Shopify", action_id="a1",
                   missing_dimensions=["WHAT"], performance=table,
                   limit=len(Q.FAMILIES))
    families = [p.candidate_source_family for p in plans]
    assert families.index(Q.RELEASE_NOTES) < families.index(Q.PRICING_PAGE)


# --- one page is one document, one announcement is one action -------------

def test_a_fragment_is_the_same_document():
    """The wave-8 grid's denominator inflator.

    Following a page's own in-page links produced /updates, /updates#main and
    /updates#one-page-checkout as three retrievals of one page. A fragment
    identifies a position INSIDE a document and never a different document.
    """
    assert AQ._canonical("https://x.com/updates#one-page-checkout") == \
        AQ._canonical("https://x.com/updates") == "https://x.com/updates"
    assert AQ._canonical("https://x.com/updates/") == "https://x.com/updates"


def test_an_anchor_link_is_not_followed_as_a_new_page():
    """The live shape: a changelog whose own table of contents links to
    positions inside itself.

    Two things this test learned the hard way. The body must be in BLOCK
    tags and each block distinct, or the parser drops it, the document is
    refused as too short, and every assertion below passes over an empty
    list. And the duplicate check must not use `_canonical` — verifying a
    function with itself is satisfied by any function at all.
    """
    blocks = "".join(
        f"<p>Release note number {i}: unrelated filler carrying this page "
        f"past the minimum parsed length.</p>" for i in range(8))
    page = ('<html><head><title>Updates</title></head><body>'
            '<a href="#main">skip to content</a>'
            '<a href="#one-page-checkout">one-page checkout</a>'
            '<p>Shopify Shipping expands to Italy and Spain.</p>'
            + blocks + '</body></html>')
    calls = []

    def fetcher(url, **kw):
        calls.append(url)
        return {"ok": True, "body": page}

    docs, report = AQ.retrieve("Shopify", "https://www.shopify.com",
                               "release_notes", as_of="2026-08-08",
                               fetcher=fetcher)
    assert docs, "fixture was refused before the behaviour could be tested"
    assert report.retrieved == len(docs)
    # Stripped with a literal, not with the function under test.
    stripped = [u.split("#", 1)[0].rstrip("/") for u in calls]
    assert len(set(stripped)) == len(calls), \
        f"the same page was fetched under several anchors: {calls}"
    assert not [u for u in calls if "#" in u]
    assert all("#" not in d.url for d in docs)


def test_one_announcement_on_five_pages_is_one_action():
    """`action_id` was already stable across duplicate retrievals and nothing
    counted on it, so five readings of one sentence were reported as five
    established objects while `all_objects` deduped them to one."""
    # Each filler block must be DISTINCT: the parser collapses identical
    # blocks, so repeating one sentence leaves the document under the
    # minimum length and it is refused before any action is read.
    filler = "".join(
        f"<p>Filler block number {i} carrying this document past the "
        f"minimum parsed length so it is read rather than refused.</p>"
        for i in range(8))
    body = ("<html><head><title>Updates</title></head><body>"
            "<p>Shopify Shipping expands to Italy and Spain.</p>"
            + filler + "</body></html>")

    def fetcher(url, **kw):
        # Every page of the family carries the SAME announcement, which is
        # exactly the live shape: a changelog and its index page.
        return {"ok": True, "body": body}

    yields, actions, objects = AQ.measure(
        [("Shopify", "https://www.shopify.com")], ["release_notes"],
        as_of="2026-08-08", fetcher=fetcher)
    report = yields["Shopify|release_notes"]
    assert len({a.action_id for a in actions}) == len(actions), \
        "the same announcement was returned as several actions"
    assert report.actions_found == len({a.action_id for a in actions})
    # The counters and the stored objects must agree — they did not before.
    assert report.objects_established + report.objects_partial + \
        report.objects_unknown == report.actions_found
    assert report.objects_established <= len(objects)
    assert report.duplicate_action_sightings > 0, \
        "this fixture repeats one announcement across pages; that must show"
