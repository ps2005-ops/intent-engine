"""An unresolved ticker must never reach the page as "private".

MEASURED on the deployed preview 2026-08-02: Tesla's dashboard rendered "For a
private company there is no market to read". Tesla is listed. The market card
had two branches -- snapshot, or no snapshot -- so every failure of listing
resolution came out as a claim about the company's ownership.

These tests drive the four states through the real dashboard builder.
"""
import pytest

from intent_engine.founder_brief import layers as L
from tests.test_founder_layers_v3 import _sparse


def _market_card(footing):
    modules = {m.key: m for m in L.build_dashboard(_sparse(), footing=footing)}
    card = modules["market_trajectory"]
    return " ".join(
        [card.unavailable_reason, card.so_what, card.what_to_watch])


def test_a_listed_company_without_a_snapshot_is_never_called_private():
    """THE BREAK PROOF."""
    text = _market_card({"ticker": "TSLA", "listing_exchange": "Nasdaq",
                         "listing_status": "PUBLIC_LISTING_RESOLVED"})
    assert "private" not in text.lower(), text
    assert "TSLA" in text


def test_a_listed_company_whose_symbol_is_unresolved_says_exactly_that():
    text = _market_card({"listing_status": "PUBLIC_LISTING_UNRESOLVED"})
    assert "appears to be publicly listed" in text
    assert "private" not in text.lower(), text


def test_a_genuinely_private_company_is_told_plainly():
    text = _market_card({"listing_status": "PRIVATE"})
    assert "no public share-price series" in text
    # and it is not left looking like something is still pending
    assert "not available for this run" not in text


def test_an_unknown_listing_does_not_assert_either_way():
    text = _market_card({"listing_status": "UNKNOWN"})
    low = text.lower()
    assert "no listing could be verified" in low
    # It may name the private POSSIBILITY, but must not assert it as fact.
    assert "this company has no public share-price series" not in low


@pytest.mark.parametrize("status", ["PUBLIC_LISTING_RESOLVED",
                                    "PUBLIC_LISTING_UNRESOLVED",
                                    "PRIVATE", "UNKNOWN"])
def test_every_state_reads_differently(status):
    """Four states that render the same text are one state with four names."""
    footing = {"listing_status": status}
    if status == "PUBLIC_LISTING_RESOLVED":
        footing["ticker"] = "TSLA"
    others = []
    for other in ("PUBLIC_LISTING_RESOLVED", "PUBLIC_LISTING_UNRESOLVED",
                  "PRIVATE", "UNKNOWN"):
        if other == status:
            continue
        f = {"listing_status": other}
        if other == "PUBLIC_LISTING_RESOLVED":
            f["ticker"] = "TSLA"
        others.append(_market_card(f))
    assert _market_card(footing) not in others
