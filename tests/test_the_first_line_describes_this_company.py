"""The first sentence under the company name must describe THIS company.

MEASURED ON THE DEPLOYED PREVIEW across twenty companies. Every page opened
with a label about our own signal vocabulary:

    "Palantir Technologies sells several distinct products rather than one,
     so attention and engineering are split across products that compete
     with each other for both."

Microsoft's was the same sentence with the name changed. `_what_it_does` says
in its own docstring that it draws on "the company's own description", then
fell back to `obs["text"]` — the sentence this system GENERATES from a signal
label. The description was in `excerpt` all along.

Fixing that surfaced a worse defect the label had been masking: Stripe's page
opened "Figma democratizes design through its collaborative design products."
A document about another company was in Stripe's observation set, and
`observation_sentence` had been pasting the right name onto the wrong content.
"""
from __future__ import annotations

import pytest

from intent_engine.founder_brief.build import _is_about, _what_it_does
from intent_engine.product_eval.harness import _compose

GOLDEN = ("palantir", "shopify", "notion", "linear", "brightledger")


@pytest.fixture(scope="module")
def openings():
    out = {}
    for key in GOLDEN:
        _, _, res = _compose(key)
        sr = res.get("strategic_report") or {}
        out[key] = _what_it_does(sr, sr.get("observations") or [],
                                 sr.get("company_name", ""))
    return out


@pytest.mark.parametrize("key", GOLDEN)
def test_the_opening_is_not_a_signal_label(key, openings):
    """The generated labels all take the form "<Company> <does X>, so <Y>",
    where <Y> is fixed per signal and identical for every company carrying
    it."""
    said = openings[key]
    assert said, f"{key} has no opening line"
    for label in ("sells several distinct products rather than one",
                  "exposes a surface others can build on",
                  "publishes named customers rather than logos alone",
                  "positions itself as replacing several separate tools"):
        assert label not in said, f"{key} still opens with a signal label"


def test_two_companies_do_not_share_an_opening(openings):
    """The defect in one assertion: Palantir and Microsoft opened identically
    because they carry the same signal."""
    values = [v for v in openings.values() if v]
    assert len(set(values)) == len(values), openings


@pytest.mark.parametrize("key", GOLDEN)
def test_the_opening_came_from_this_companys_own_documents(key, openings):
    """Provenance, which is the property that actually matters and the one
    `_is_about` checks with the document in hand. Re-testing the sentence
    alone would fail Brightledger's real description — "Connectors read payout
    files from payment processors" names nobody, because a product page does
    not need to."""
    _, _, res = _compose(key)
    sr = res.get("strategic_report") or {}
    said = openings[key].rstrip("…").strip()
    own = [(o.get("excerpt") or "") for o in (sr.get("observations") or [])
           if o.get("source_class") in ("company_owned", "executive_statement",
                                        "investor_material")]
    assert any(said[:60] in " ".join(e.split()) for e in own if e) or \
        said.startswith(sr.get("company_name", "")), said


def test_another_companys_description_is_rejected():
    """THE WORST DEFECT THIS CYCLE FOUND, live on Stripe."""
    assert not _is_about(
        "Figma democratizes design through its collaborative design products.",
        "Stripe")
    assert not _is_about(
        "Infinite Group is a developer of cybersecurity software.", "Stripe")


def test_the_companys_own_voice_is_accepted():
    assert _is_about("We provide an agentic customer platform.", "HubSpot")
    assert _is_about("Microsoft is a technology company.", "Microsoft")


def test_a_customer_review_is_not_a_description():
    """Shopify's highest-ranked excerpt is a merchant review praising fast
    setup. Real evidence, wrong voice for what a company does."""
    said = _what_it_does({}, [{
        "source_class": "customer_voice", "observation_type": "messaging",
        "excerpt": "Independent merchant reviews repeatedly praise fast setup "
                   "and simple day-to-day operation across many stores.",
        "text": ""}], "Shopify")
    assert "reviews repeatedly praise" not in said
