"""Batch 14: the confidence gate counts ORIGINS, and uses ONE definition.

Batch 13 built an origin-level independence model and wired it into candidate
selection, the dossier and the wave. Tracing its consumers found it had never
reached the reasoning layer: the critic — the last gate before a founder is
told something with high confidence — decided independence from per-document
source CLASSES, which cannot see syndication.

Two defects, both measured live at `46027cc` and both silent:

  1. nine copies of one wire story, all `independent_reporting`, one origin,
     satisfied "one vantage point cannot corroborate itself";
  2. the critic's private copy of the independent-class set had drifted WIDER
     than the canonical one — it counted `investor_material`, the company
     addressing its own investors, as an outside vantage point.

The positive controls matter as much as the negatives here: this finding
REJECTS an entire analysis, so a gate that over-fires destroys real work.
"""
import pytest

from intent_engine.company_ingestion.records import INDEPENDENT_CLASSES
from intent_engine.strategic_intelligence.analyst.critic import (
    _INDEPENDENT_CLASSES, verify_analysis,
)
from intent_engine.strategic_intelligence.records import StrategicObservation


def _obs(index, source_class, url):
    return StrategicObservation(
        observation_id=f"o{index}",
        text="Acme opened a plant in Ohio this quarter.",
        observation_type="messaging", source_class=source_class, origin=url,
        excerpt="Acme opened a plant in Ohio this quarter.",
        source_title="Acme Ohio plant")


def _analysis(citations, confidence="high"):
    return {
        "the_insight": {
            "sentence": "Acme is buying capacity ahead of demand it has "
                        "not yet won.",
            "paragraph": "The Ohio plant commits fixed cost before the "
                         "contracts that would fill it exist.",
            "why_now": "The plant opened this quarter.",
            "citations": list(citations)},
        "strongest_case_we_are_wrong": "Demand may arrive on schedule.",
        "decisions": [{"decision": "capacity planning",
                       "confidence": confidence,
                       "confidence_rationale":
                           "several independent accounts agree on the plant",
                       "citations": list(citations)}],
    }


def _flagged(observations, confidence="high"):
    findings = verify_analysis(
        _analysis([o.observation_id for o in observations], confidence),
        observations=observations, company_name="Acme")
    return "confidence_exceeds_evidence" in [f.check for f in findings]


# --- one definition of independent ------------------------------------------
def test_critic_uses_the_canonical_independent_class_set():
    """No private copy. Two definitions of one word is the defect."""
    assert set(_INDEPENDENT_CLASSES) == set(INDEPENDENT_CLASSES)


def test_investor_material_is_not_an_outside_vantage_point():
    """THE DRIFTED COPY. The company addressing investors is the company."""
    assert "investor_material" not in _INDEPENDENT_CLASSES
    assert _flagged([_obs(i, "investor_material", "https://acme.example/ir")
                     for i in range(3)])


# --- origins, not classes ---------------------------------------------------
def test_nine_syndicated_copies_are_one_vantage_point():
    """THE MEASURED DEFECT. Nine documents, one class, ONE origin."""
    assert _flagged([_obs(i, "independent_reporting", "https://wire.example/s")
                     for i in range(9)])


def test_two_independent_classes_on_one_origin_are_one_vantage_point():
    """ISOLATES THE ORIGIN AXIS from the two-origin threshold beside it.

    The syndication test above is defended twice — origins are counted AND
    two are required — so counting classes instead would still flag nine
    copies of one class. Here one publisher carries a news piece and a
    customer testimonial: TWO independent classes, ONE origin. Class-counting
    passes it; only the origin axis catches it.
    """
    assert _flagged([
        _obs(0, "independent_reporting", "https://outlet.example/story"),
        _obs(1, "customer_voice", "https://outlet.example/testimonial")])


def test_two_independent_origins_support_high_confidence():
    """POSITIVE CONTROL. This finding rejects the whole analysis, so a gate
    that cannot pass genuine corroboration is worse than the defect."""
    assert not _flagged([
        _obs(0, "independent_reporting", "https://wire.example/a"),
        _obs(1, "competitor",
             "https://www.sec.gov/Archives/edgar/data/99/x.htm")])


def test_one_independent_origin_still_supports_moderate_confidence():
    """NEGATIVE CONTROL. The repair constrains HIGH, not every claim."""
    assert not _flagged(
        [_obs(0, "independent_reporting", "https://wire.example/a")],
        confidence="moderate")


def test_two_filings_by_different_registrants_are_two_origins():
    """The author axis reaches reasoning, not just the dossier."""
    assert not _flagged([
        _obs(0, "competitor",
             "https://www.sec.gov/Archives/edgar/data/100517/ual.htm"),
        _obs(1, "competitor",
             "https://www.sec.gov/Archives/edgar/data/1362468/algt.htm")])


def test_two_filings_by_the_SAME_registrant_are_one_origin():
    """The corresponding negative control, at the reasoning gate."""
    assert _flagged([
        _obs(0, "competitor",
             "https://www.sec.gov/Archives/edgar/data/100517/a.htm"),
        _obs(1, "competitor",
             "https://www.sec.gov/Archives/edgar/data/100517/b.htm")])


def test_an_observation_with_no_origin_cannot_supply_independence():
    """UNKNOWN IS NOT INDEPENDENT, at this gate too.

    One real outside origin plus one observation whose origin was never
    recorded. If the blank counted, this would reach two origins and pass —
    which is ignorance converted into corroboration, the exact substitution
    the lineage model refuses one layer down.
    """
    assert _flagged([_obs(0, "independent_reporting", "https://wire.example/a"),
                     _obs(1, "independent_reporting", "")])


def test_company_owned_sources_alone_still_fail_as_they_always_did():
    """REGRESSION. The original behaviour this check existed for."""
    assert _flagged([_obs(i, "company_owned", "https://acme.example/about")
                     for i in range(4)])


@pytest.mark.parametrize("confidence", ["low", "moderate"])
def test_the_gate_constrains_only_high_confidence(confidence):
    assert not _flagged(
        [_obs(0, "company_owned", "https://acme.example/about")],
        confidence=confidence)
