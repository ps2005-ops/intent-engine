"""Approval order prefers attested URLs over guessed ones.

The repair is an ORDERING change inside an already-approved candidate set.
The tests that matter are therefore of two kinds: that the order actually
changed, and that NOTHING about eligibility did. The second kind is the
security control, and it is written so that widening the candidate rules
would break it.
"""
from intent_engine.webapp.app import WebApp


def candidate(cid, *, method, source_type="about", why="", url=None,
              source_class=None):
    return {
        "candidate_id": cid,
        "url": url or f"https://acme.com/{cid}",
        "source_type": source_type,
        "discovery_method": method,
        "why_relevant": why,
        "source_class": source_class,
    }


def picked(candidates, **kw):
    return WebApp._recommended_candidate_ids(candidates, **kw)


# --- the repair --------------------------------------------------------------
def test_a_homepage_link_outranks_a_guessed_path_in_the_same_family():
    order = picked([candidate("guess", method="known_path"),
                    candidate("attested", method="homepage_link")])
    assert order.index("attested") < order.index("guess")


def test_the_order_does_not_depend_on_the_input_order():
    forward = picked([candidate("attested", method="homepage_link"),
                      candidate("guess", method="known_path")])
    backward = picked([candidate("guess", method="known_path"),
                       candidate("attested", method="homepage_link")])
    assert forward.index("attested") < forward.index("guess")
    assert backward.index("attested") < backward.index("guess")


def test_a_sitemap_url_still_outranks_an_attested_homepage_link():
    """The publisher's own canonical list stays above a rendered link."""
    order = picked([candidate("link", method="homepage_link"),
                    candidate("map", method="known_path",
                              why="listed in the sitemap")])
    assert order.index("map") < order.index("link")


def test_a_curated_official_url_still_wins_everything():
    order = picked([candidate("link", method="homepage_link"),
                    candidate("official", method="official_fallback")])
    assert order[0] == "official"


def test_an_edgar_filing_still_outranks_an_attested_link():
    order = picked([candidate("link", method="homepage_link"),
                    candidate("filing", method="external_proposed",
                              why="SEC EDGAR primary document")])
    assert order.index("filing") < order.index("link")


# --- guesses are demoted, never excluded -------------------------------------
def test_a_guess_is_still_selected_when_budget_remains():
    """Demotion must not silently drop evidence.

    A guessed path is often the ONLY route to a family on a site with a
    JavaScript homepage that renders no links. Ranking it last is the whole
    change; removing it would be a different and much worse one.
    """
    order = picked([candidate("guess", method="known_path")])
    assert order == ["guess"]


def test_guesses_fill_the_budget_after_attested_links_are_exhausted():
    cands = ([candidate(f"link{i}", method="homepage_link") for i in range(3)]
             + [candidate(f"guess{i}", method="known_path") for i in range(3)])
    order = picked(cands)
    assert len([c for c in order if c.startswith("guess")]) == 3


# --- NEGATIVE CONTROLS: eligibility must not have moved ----------------------
def test_a_refusing_host_is_still_ranked_below_every_guess():
    """A guess at a host we have watched refuse us may not take a slot.

    THIS USED TO ASSERT AN ORDER: the closed-door candidate had to sort below
    the reachable guess, because ranking it last was the strongest guarantee
    available. It is no longer the strongest -- such a candidate is now
    dropped from selection outright, since twenty-odd certain failures per
    run were being made after the door had already been observed shut
    (Union Pacific failed=27, 24 of them at up.com).

    The invariant this test exists for is unchanged and is asserted more
    directly: a guess aimed at a refusing host can never displace real
    evidence -- the Sony regression, restated.
    """
    order = picked([candidate("onbad", method="homepage_link",
                              url="https://bad.com/x"),
                    candidate("guess", method="known_path",
                              url="https://acme.com/y")],
                   refusing_hosts=("bad.com",))
    assert "onbad" not in order, order
    assert "guess" in order, order


def test_the_budget_is_unchanged():
    """Ordering must never let more sources through than the cap allows."""
    from intent_engine.company_ingestion import MAX_APPROVED_SOURCES
    cands = [candidate(f"link{i}", method="homepage_link",
                       source_type="product") for i in range(40)]
    assert len(picked(cands)) <= MAX_APPROVED_SOURCES


def test_no_candidate_becomes_eligible_that_was_not_before():
    """The selected set is a SUBSET of what was offered — always.

    This is the control that would fail if the ordering change were ever
    quietly turned into a discovery change that invents URLs.
    """
    cands = [candidate("a", method="homepage_link"),
             candidate("b", method="known_path"),
             candidate("c", method="external_proposed")]
    offered = {c["candidate_id"] for c in cands}
    assert set(picked(cands)) <= offered


def test_an_offsite_url_is_not_promoted_by_being_a_homepage_link():
    """`homepage_link` is a DISCOVERY fact, never a permission.

    A link on a company homepage points wherever the page's author chose,
    including at a host nobody approved. Promotion must not read as approval:
    whatever the host rules admitted before must be exactly what they admit
    now.
    """
    cands = [candidate("offsite", method="homepage_link",
                       url="https://evil.example/x"),
             candidate("onsite", method="known_path",
                       url="https://acme.com/about")]
    order = picked(cands)
    # Both are still merely ORDERED here; nothing in this function fetches or
    # authorises. The point of the control is that the set is unchanged.
    assert set(order) == {"offsite", "onsite"}
