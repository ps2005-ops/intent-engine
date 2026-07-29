"""The whole founder-facing Sentry deck, as a reader sees it.

Built from Sentry's actual retrieved evidence. Live, the deck opened with
"broadening from a focused tool toward being the place a team's work is
stored" -- the tool_to_system_of_record scaffold -- while the run had
retrieved a page titled "Sentry Acquires Codecov".

Everything here asserts RENDERED CONTENT, not source strings.
"""
import pytest

from intent_engine.strategic_intelligence.reasoning import (
    build_strategic_report,
)
from intent_engine.strategic_intelligence.records import StrategicObservation
from intent_engine.strategic_intelligence.slides import (
    build_slides, deck_is_presentable, render_deck,
)


def _obs(oid, title, excerpt, signals=("consolidation",)):
    return StrategicObservation(
        observation_id=oid, text=f"{title} shows a signal",
        observation_type="product_surface",
        source_refs=[{"subsystem": "company_ingestion",
                      "artifact_type": "retrieved_source",
                      "artifact_id": oid, "source_class": "company_owned"}],
        confidence="moderate", freshness="CURRENT", directly_observed=True,
        signals=tuple(signals), source_class="company_owned", excerpt=excerpt,
        source_title=title, origin=f"https://sentry.io/{oid}",
        date="2026-07-29",
        strategic_signal="positions itself as replacing several separate tools",
        relevance="context", entity="Sentry", weak=False,
        evidence_quality="strong")


# these titles are what the live run actually retrieved
SENTRY_OBS = [
    _obs("obs-1", "About Sentry | Sentry", "Bugs aren't great."),
    _obs("obs-2", "Sentry Acquires Codecov | Sentry",
         "Find current press releases."),
    _obs("obs-3", "Application Performance Monitoring & Error Tracking "
                  "Software | Sentry",
         "Application performance monitoring for developers.",
         ("multi_product", "consolidation")),
    _obs("obs-4", "Media Resources | Sentry", "Press releases and logos."),
]


@pytest.fixture(scope="module")
def deck():
    return build_slides(build_strategic_report(company_name="Sentry",
                                               observations=SENTRY_OBS))


@pytest.fixture(scope="module")
def visible(deck):
    return " ".join(b["text"] for s in deck for b in s["bullets"])


def test_the_deck_opens_with_the_acquisition(deck):
    first = deck[0]
    assert first["kind"] == "insight"
    assert first["bullets"][0]["text"] == "Sentry acquired Codecov."


def test_the_opening_cites_the_acquisition_source(deck):
    citations = deck[0]["bullets"][0]["evidence"]
    assert "obs-2" in citations, citations


@pytest.mark.parametrize("phrase", [
    "system of record",
    "tool-to-system-of-record",
    "broadening from a focused tool",
    "strategic signal",
    "adjacent tools",
])
def test_no_taxonomy_reaches_the_reader(visible, phrase):
    assert phrase.lower() not in visible.lower(), phrase


def test_no_build_version_reaches_the_reader(deck):
    html = render_deck(deck, company="Sentry", as_of="2026-07-29",
                       analysis_version="9.9.9-internal")
    assert "9.9.9-internal" not in html
    assert "analysis version" not in html.lower()


def test_confidence_and_uncertainty_survive(deck, visible):
    """Filtering the claim must not take the honesty with it."""
    assert any(s["kind"] == "gaps" for s in deck), [s["kind"] for s in deck]
    assert "lead rather than a finding" in visible


def test_the_counterargument_survives(deck):
    """Genuine counter-evidence is NOT filtered -- it legitimately names the
    mechanism being doubted."""
    assert any(s["kind"] == "counterargument" for s in deck)


def test_the_deck_is_presentable_so_slides_remains_the_default(deck):
    assert deck_is_presentable(deck)


def test_the_watch_screen_is_specific_or_honestly_absent(deck):
    """A watch item a reader cannot observe is worse than no watch screen.
    Sentry's only candidate was the pattern's own falsification question."""
    watch = [s for s in deck if s["kind"] == "monitor"]
    if not watch:
        return                              # honestly omitted
    for bullet in watch[0]["bullets"]:
        assert "system of record" not in bullet["text"].lower()


def test_no_screen_is_padded_to_reach_a_count(deck):
    for slide in deck:
        assert slide["bullets"], f"empty screen rendered: {slide['id']}"
        for bullet in slide["bullets"]:
            assert bullet["text"].strip()
