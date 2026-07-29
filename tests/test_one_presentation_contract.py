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


def _report():
    return build_strategic_report(
        company_name="Examplecorp",
        observations=derive_observations(COMMERCE_DOCS))


def _deck():
    return build_slides(_report())


def test_the_deterministic_path_renders_the_founder_deck():
    kinds = [s["kind"] for s in _deck()]
    assert "insight" in kinds, kinds
    # the old deterministic deck's own slide kinds must be gone
    for legacy in ("thesis", "company", "signals"):
        assert legacy not in kinds, f"old deterministic deck still rendering: {legacy}"


def test_the_first_screen_is_a_conclusion_not_a_company_overview():
    first = _deck()[0]
    assert first["kind"] == "insight"
    assert "in one minute" not in first["title"].lower()
    assert "overview" not in first["title"].lower()
    # and it says something specific about this company
    assert "Examplecorp" in first["bullets"][0]["text"]


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


def test_why_now_is_stated_in_plain_words():
    """The reasoning layer says "Recent public signal (2026-07-20, Pricing)
    keeps this timely" -- the system describing its own inputs."""
    from intent_engine.strategic_intelligence.slides import (
        _why_now_in_plain_words,
    )
    out = _why_now_in_plain_words(
        "Recent public signal (2026-07-20, Pricing page) keeps this timely.")
    assert "signal" not in out.lower()
    assert "2026-07-20" in out and "Pricing page" in out


def test_a_report_with_nothing_to_say_produces_no_founder_deck():
    empty = founder_view_from_report({"thesis": {}, "hypotheses": []})
    assert empty == {}
