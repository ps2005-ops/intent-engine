"""Fixture tests for core/headline_feed.py (item 3,
docs/BA_ACCELERATION_PROPOSAL.md — approved bars):
(a) recorded RSS payloads -> deterministic top-K, no network;
(c) zero qualifying headlines -> numeric-only degradation (provenance says
    so explicitly, nothing fabricated).
Bar (b) — live provenance lines in a real report run — is a Mac-side live
check, same convention as every other live bar in this repo."""

from datetime import date

from intent_engine.core.headline_feed import (
    DEFAULT_K,
    FEED_ALLOWLIST,
    Headline,
    parse_feed,
    render_provenance,
    score_title,
    select_headlines,
)

AS_OF = date(2026, 7, 20)


def _rss(*items: str) -> str:
    return (
        '<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>'
        + "".join(items)
        + "</channel></rss>"
    )


def _item(title: str, pub: str, link: str = "https://example.com/a") -> str:
    return f"<item><title>{title}</title><link>{link}</link><pubDate>{pub}</pubDate></item>"


FRESH = "Mon, 20 Jul 2026 09:00:00 GMT"
FRESH_MINUS_1 = "Sun, 19 Jul 2026 09:00:00 GMT"
STALE = "Mon, 01 Jun 2026 09:00:00 GMT"


def test_parse_rss_and_atom():
    rss_entries = parse_feed(_rss(_item("Fed holds rates steady", FRESH)))
    assert rss_entries[0]["title"] == "Fed holds rates steady"
    atom = (
        '<feed xmlns="http://www.w3.org/2005/Atom"><entry>'
        "<title>Treasury yields climb</title>"
        '<link href="https://example.com/b"/>'
        "<updated>2026-07-20T09:00:00Z</updated></entry></feed>"
    )
    atom_entries = parse_feed(atom)
    assert atom_entries[0]["title"] == "Treasury yields climb"
    assert atom_entries[0]["link"] == "https://example.com/b"
    assert parse_feed("not xml at all") == []


def test_selection_is_deterministic_and_ranked():
    payloads = [
        ("A", "https://a", _rss(
            _item("Fed signals possible rate hike as inflation stays hot", FRESH),  # high score
            _item("Celebrity opens new restaurant", FRESH),                          # score 0 -> excluded
            _item("Stocks rally on jobs data", FRESH_MINUS_1),
        )),
        ("B", "https://b", _rss(
            _item("Treasury yields and credit spreads widen", FRESH),
            _item("Old inflation story", STALE),                                     # stale -> excluded
        )),
    ]
    first = select_headlines(payloads, AS_OF, fetched_at="T")
    second = select_headlines(payloads, AS_OF, fetched_at="T")
    assert first == second  # bar (a): deterministic
    assert len(first) == 3
    titles = [h.title for h in first]
    assert "Celebrity opens new restaurant" not in titles
    assert "Old inflation story" not in titles
    # ranked by score desc: the 4-vocab-word headline outranks the 2-word ones
    assert first[0].title == "Fed signals possible rate hike as inflation stays hot"


def test_dedupe_by_normalized_title_best_ranked_wins():
    payloads = [
        ("A", "https://a", _rss(_item("Stocks rally on jobs data!", FRESH))),
        ("B", "https://b", _rss(_item("stocks rally on jobs data", FRESH_MINUS_1))),
    ]
    selected = select_headlines(payloads, AS_OF, fetched_at="T")
    assert len(selected) == 1
    assert selected[0].feed_name == "A"  # newer published ranks first, first occurrence kept


def test_undated_entries_are_excluded():
    xml = _rss("<item><title>Fed rate decision looms</title></item>")
    assert select_headlines([("A", "https://a", xml)], AS_OF) == []


def test_zero_qualifying_headlines_numeric_only_provenance():
    selected = select_headlines([("A", "https://a", _rss(_item("Cat wins pageant", FRESH)))], AS_OF)
    assert selected == []
    block = render_provenance(selected, AS_OF)
    assert "numeric-only mode" in block
    assert "fabricated" in block  # explicitly says nothing was substituted


def test_provenance_lines_carry_feed_url_and_dates():
    selected = select_headlines(
        [("Yahoo Finance", "https://y", _rss(_item("Markets slide as yields rise", FRESH)))],
        AS_OF, fetched_at="2026-07-20T12:00:00+00:00",
    )
    block = render_provenance(selected, AS_OF)
    assert "Markets slide as yields rise" in block
    assert "Yahoo Finance" in block and "published 2026-07-20" in block
    assert "https://example.com/a" in block


def test_score_title_counts_distinct_vocab_words():
    assert score_title("Fed fed FED rates") == 2  # {"fed","rates"}
    assert score_title("nothing relevant here") == 0


def test_allowlist_is_exactly_the_approved_set():
    # 2026-07-22: Reuters + AP dropped (both web-fetch-tool-blocked), NPR
    # Business added (verified working). Founder decision.
    assert [name for name, _ in FEED_ALLOWLIST] == ["NPR Business", "Yahoo Finance"]


def test_top_k_default_is_three():
    assert DEFAULT_K == 3
    payloads = [("A", "https://a", _rss(*[
        _item(f"Fed rates headline number {i}", FRESH) for i in range(6)
    ]))]
    assert len(select_headlines(payloads, AS_OF)) == 3
