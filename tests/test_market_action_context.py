"""Context may complete an action's object. It may not borrow its neighbour's.

The failure this guards: a release-note INDEX page is a list of unrelated
announcements. Widen the window until a buyer appears and one always will —
belonging to a different product.
"""
from __future__ import annotations

from intent_engine.market import action_context as AC
from intent_engine.market import competitive_objects as CO

# Sentence A names a buyer for one product; sentence C announces a different
# one. This is the shape of every changelog index on the internet.
INDEX_PAGE = (
    "Shopify Bundles is built for enterprise retailers running high-volume "
    "catalogues. "
    "It reached general availability this quarter. "
    "Introducing Commerce Components. "
    "Read the documentation for more detail."
)

ENTRY_PAGE = (
    "For app developers, building merchant-facing analytics has always meant "
    "standing up your own stack. "
    "With these updates, Shopify Analytics becomes a full-stack analytics "
    "platform that apps can build on directly. "
    "The change is available today."
)


# --- the leak -------------------------------------------------------------

def test_a_neighbours_buyer_does_not_reach_this_action():
    """"enterprise retailers" belongs to Shopify Bundles. "Introducing
    Commerce Components" must not inherit it."""
    ctx = AC.build(INDEX_PAGE, "Introducing Commerce Components.",
                   action_id="a1")
    assert ctx is not None
    assert "enterprise retailers" not in ctx.window.lower()


def test_a_neighbouring_announcement_is_a_section_boundary():
    """Two announcements are two sections however close together they sit."""
    ctx = AC.build(INDEX_PAGE, "It reached general availability this quarter.",
                   action_id="a1")
    assert ctx.next_sentence == "", ctx.next_sentence
    assert any("section boundary" in p for p in ctx.provenance)


def test_the_object_is_not_established_from_a_neighbours_buyer():
    """The end-to-end version: the extractor run over the context window must
    still refuse, because the buyer in the window is somebody else's."""
    ctx = AC.build(INDEX_PAGE, "Introducing Commerce Components.",
                   action_id="a1")
    got, _ = CO.extract(ctx.window, action_id="a1", actor="Shopify",
                        source="s", created_at="2026-08-08",
                        action_type="PRODUCT_LAUNCH")
    assert got is None or got.standing != CO.ESTABLISHED
    assert got is None or "enterprise retailers" not in (got.buyer or "")


# --- what it is FOR -------------------------------------------------------

def test_a_buyer_one_sentence_earlier_is_reachable():
    """Shopify's developer changelog, live: the buyer is in the sentence
    before the product, and sentence-level extraction reads neither."""
    action = ("With these updates, Shopify Analytics becomes a full-stack "
              "analytics platform that apps can build on directly.")
    ctx = AC.build(ENTRY_PAGE, action, action_id="a1",
                   heading="Full-stack capabilities to power app analytics")
    assert "app developers" in ctx.window.lower()
    assert ctx.previous_sentence.startswith("For app developers")


def test_the_heading_is_carried_because_an_entry_page_is_about_one_thing():
    ctx = AC.build(ENTRY_PAGE, "The change is available today.",
                   action_id="a1",
                   heading="Full-stack capabilities to power app analytics")
    assert ctx.heading.startswith("Full-stack capabilities")
    assert ctx.window.startswith("Full-stack capabilities")


# --- boundaries -----------------------------------------------------------

def test_navigation_is_never_context():
    page = ("Skip to main content. "
            "Shopify Shipping expands to Italy and Spain. "
            "Cookie preferences and privacy policy.")
    ctx = AC.build(page, "Shopify Shipping expands to Italy and Spain.",
                   action_id="a1")
    assert ctx.previous_sentence == ""
    assert ctx.next_sentence == ""
    assert any("boilerplate" in p for p in ctx.provenance)


def test_a_boilerplate_heading_is_refused():
    ctx = AC.build(ENTRY_PAGE, "The change is available today.",
                   action_id="a1", heading="Sign in to your account")
    assert ctx.heading == ""


def test_a_sentence_the_document_does_not_contain_has_no_context():
    """Assembling a window around a sentence from somewhere else would be a
    context about a different document."""
    assert AC.build(ENTRY_PAGE, "Salesforce cut its Enterprise pricing.") is None


def test_the_window_never_reaches_two_sentences_away():
    page = ("Enterprise retailers are our fastest-growing segment. "
            "Our platform serves many kinds of business. "
            "Introducing Commerce Components. "
            "It is available today.")
    ctx = AC.build(page, "Introducing Commerce Components.", action_id="a1")
    assert "enterprise retailers" not in ctx.window.lower()


def test_context_carries_its_own_reasons():
    ctx = AC.build(ENTRY_PAGE, "The change is available today.",
                   action_id="a1", heading="Full-stack capabilities")
    assert ctx.provenance
    assert any(p.startswith("previous:") for p in ctx.provenance)
    assert any(p.startswith("next:") for p in ctx.provenance)
    assert ctx.as_dict()["action_id"] == "a1"


def test_summarise_counts_the_boundaries_it_enforced():
    contexts = [
        AC.build(INDEX_PAGE, "It reached general availability this quarter.",
                 action_id="a1"),
        AC.build(ENTRY_PAGE, "The change is available today.", action_id="a2",
                 heading="Full-stack capabilities"),
    ]
    got = AC.summarise([c for c in contexts if c])
    assert got["contexts"] == 2
    assert got["bounded_by_a_neighbouring_announcement"] >= 1
    assert got["with_heading"] == 1


# --- an index page's sentences are not context for one another ------------

def test_an_index_page_supplies_no_context_at_all():
    """Measured live on Shopify's /updates page, which announces seven
    things: the window gave "Introducing JavaScript for Shopify Functions"
    the workflow `checkout` from the entry above it, and gave another action
    the buyer "Sidekick app extensionsApp store" — two nav labels run
    together. Neither is a fact about the action it was attached to.
    """
    ctx = AC.build(INDEX_PAGE, "Introducing Commerce Components.",
                   action_id="a1", heading="Shopify Updates",
                   sibling_actions=6)
    assert ctx.previous_sentence == ""
    assert ctx.next_sentence == ""
    assert ctx.heading == ""
    assert ctx.window == "Introducing Commerce Components."
    assert any("index" in p for p in ctx.provenance)


def test_a_single_topic_page_still_gets_its_context():
    """The refusal is about indexes, not about context. An entry page
    announcing one thing keeps its neighbours."""
    action = ("With these updates, Shopify Analytics becomes a full-stack "
              "analytics platform that apps can build on directly.")
    ctx = AC.build(ENTRY_PAGE, action, action_id="a1",
                   heading="Full-stack capabilities to power app analytics",
                   sibling_actions=0)
    assert "app developers" in ctx.window.lower()


def test_the_index_refusal_beats_every_other_signal():
    """Even a clean, on-topic neighbour is refused on an index page: the
    rule is about what KIND of document this is."""
    ctx = AC.build(ENTRY_PAGE, "The change is available today.",
                   action_id="a1", heading="Full-stack capabilities",
                   sibling_actions=1)
    assert ctx.window == "The change is available today."
