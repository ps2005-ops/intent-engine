"""One founder-facing product, whichever reasoning path produced it.

Before this, a grounded run rendered the founder deck and every other run
rendered a different deck opening with "{company} in one minute" and closing
on "Key strategic signals". Which product a visitor saw depended on whether an
API key happened to be configured -- and since it is not configured in
production, the weaker one was the live product.
"""
from test_strategic_evidence_integrity import COMMERCE_DOCS

from intent_engine.strategic_intelligence.observations import (
    derive_observations,
)
from intent_engine.strategic_intelligence.reasoning import (
    build_strategic_report,
)
from intent_engine.strategic_intelligence.slides import (
    build_slides, founder_view_from_report,
)


# The deterministic founder deck is only taken over when a concrete company
# development was retrieved -- that is the rule protecting thin and
# adversarial companies. So this fixture contains one.
_ACQUISITION = dict(
    source_id="m9", title="Examplecorp Acquires Ledgerly",
    final_url="https://example.com/press/acquires-ledgerly",
    meta_description="",
    text_content="Examplecorp has acquired Ledgerly, adding reconciliation "
                 "to the commerce platform used by merchants and sellers "
                 "for storefront and checkout operations.",
    retrieved_at="2026-07-20T00:00:00Z", freshness="CURRENT")


def _report():
    return build_strategic_report(
        company_name="Examplecorp",
        observations=derive_observations(list(COMMERCE_DOCS) + [_ACQUISITION]))


def _deck():
    return build_slides(_report())


def test_the_deterministic_path_renders_the_founder_deck():
    kinds = [s["kind"] for s in _deck()]
    assert "insight" in kinds, kinds
    # the old deterministic deck's own slide kinds must be gone
    for legacy in ("thesis", "company", "signals"):
        assert legacy not in kinds, f"old deterministic deck still rendering: {legacy}"


def test_the_first_screen_is_a_concrete_fact_not_a_company_overview():
    first = _deck()[0]
    assert first["kind"] == "insight"
    assert "in one minute" not in first["title"].lower()
    # the lead is the retrieved development, not a pattern title
    lead = first["bullets"][0]["text"]
    assert "Examplecorp acquired Ledgerly" in lead, lead


def test_no_internal_vocabulary_reaches_the_reader():
    text = " ".join(b["text"] for s in _deck()
                    for b in s["bullets"]).lower()
    titles = " ".join(s["title"] for s in _deck()).lower()
    for word in ("signal", "hypothesis", "pattern", "observation",
                 "schema", "availability", "source_class"):
        assert word not in titles, f"title says {word!r}"
    assert "strategic signals" not in text


def test_the_tension_reaches_a_screen():
    """The tension is one of the few things the deterministic path can state
    honestly, and the five-questions rebuild had left it nowhere to appear."""
    kinds = [s["kind"] for s in _deck()]
    assert "tension" in kinds
    tension = [s for s in _deck() if s["kind"] == "tension"][0]
    assert any("trade-off" in b["text"].lower() for b in tension["bullets"])


def test_screens_the_deterministic_path_cannot_fill_are_omitted():
    """A shorter honest presentation, not the same shape padded out."""
    kinds = [s["kind"] for s in _deck()]
    for unsupported in ("business_model", "game", "mental_model",
                        "competitive", "assumption"):
        assert unsupported not in kinds, \
            f"{unsupported} rendered with nothing honest to put in it"


def test_the_deterministic_path_never_claims_something_deserves_today():
    """Urgency is a grounded-only judgement. Deterministic reasoning cannot
    tell how reversible or urgent a decision is."""
    assert "today" not in [s["kind"] for s in _deck()]
    assert founder_view_from_report(_report())["supports_urgency"] is False


def test_a_run_with_no_concrete_development_keeps_the_existing_path():
    """The governing rule: only replace the fallback when there is a real fact
    strong enough to earn the takeover. COMMERCE_DOCS alone reports no company
    ACTION -- only product and marketing pages -- so the adapter declines and
    every existing behaviour is untouched."""
    plain = build_strategic_report(
        company_name="Examplecorp",
        observations=derive_observations(COMMERCE_DOCS))
    assert founder_view_from_report(plain) == {}


def test_why_now_withholds_provenance_instead_of_rephrasing_it():
    """CONTRACT CORRECTED after live customer feedback.

    This test previously required the date and page name to SURVIVE into
    "why now" -- it asserted `"2026-07-20" in out and "Pricing page" in out`.
    That contract is what produced "The most recent evidence is About
    Palantir." on the deployed Palantir result, which a real user reported as
    meaningless.

    Both readings agree the pipeline's own vocabulary ("signal") must go. They
    disagree on what remains: the old one said rephrase the provenance, this
    one says a publication date is not a reason the situation is urgent, so
    there is no "why now" to state and the line is omitted.

    The test was not weakened to let the code pass -- the expectation was
    wrong, and keeping it would have preserved the defect the customer saw.
    """
    from intent_engine.strategic_intelligence.slides import (
        _why_now_in_plain_words,
    )
    out = _why_now_in_plain_words(
        "Recent public signal (2026-07-20, Pricing page) keeps this timely.")
    assert "signal" not in out.lower()
    assert out == "", f"provenance was rendered as a reason: {out!r}"

    # A genuine reason is still passed through untouched.
    real = ("Two of the three largest customers renewed on shorter terms this "
            "quarter, which changes the revenue base.")
    assert _why_now_in_plain_words(real) == real


def test_a_report_with_nothing_to_say_produces_no_founder_deck():
    empty = founder_view_from_report({"thesis": {}, "hypotheses": []})
    assert empty == {}


def test_no_build_version_is_printed_under_every_slide():
    """Seen live: "analysis version 1.5.0-executive-intelligence" repeated on
    every screen of a deck meant to be shown in a meeting."""
    from intent_engine.strategic_intelligence.slides import render_deck
    html = render_deck(_deck(), company="Examplecorp", as_of="2026-07-29",
                       analysis_version="9.9.9-internal-build")
    assert "9.9.9-internal-build" not in html
    assert "analysis version" not in html.lower()
