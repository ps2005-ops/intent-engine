"""Qualifying for a pattern must not be sufficient to determine the reading.

MEASURED LIVE on 31e6138. Caterpillar and Exxon Mobil are DIFFERENT
business-model classes — MANUFACTURE_AND_AFTERMARKET and COMMODITY_PRODUCER —
and render different business models on the page:

    "an industrial business that runs on sale of a long-lived manufactured
     product followed by a higher-margin service and parts stream"
    "a materials energy business that runs on production of an
     undifferentiated output sold at a price the producer does not set"

and they answered EIGHT OF TEN board questions with the identical sentence:
"committing capital to capacity ahead of uncertain demand". Amazon, on a
different pattern, answered 1/10 alike.

NEITHER QUALIFYING IS THE DEFECT. Both genuinely commit capital to physical
capacity, and `capacity_ahead_of_demand` reaching them is correct — it is the
repair that stopped it reaching Meta. The defect is that qualifying is
SUFFICIENT to determine the whole reading, because every field of the composed
decision comes from the pattern's static text with only `{company}`
substituted. `compose_decision`'s own docstring says it: "nothing here is
per-company".

CLASS IS NOT THE AXIS. This is the cross-class form of what was measured
offline WITHIN a class (NVIDIA/AMD identical on 8 of 12 projected read
fields). One statement covers both: wherever two companies share a top
pattern, they share the reading. A seventeenth table row keyed on class
cannot fix it — these two are already in different classes.

This file pins the part that is repaired and states, as an executable
expectation, the part that is not.
"""
import pytest

from intent_engine.strategic_intelligence.decision import (
    compose_decision, grounding_of, mechanism_sentence,
)
from intent_engine.strategic_intelligence.records import (
    MechanismEvidence, StrategicHypothesis,
)

PATTERN = "capacity_ahead_of_demand"


def hypothesis(company, quote, source):
    """Two filers, one pattern, each with its OWN qualifying sentence."""
    return StrategicHypothesis(
        hypothesis_id=f"h-{company.lower().split()[0]}",
        title="committing capital to capacity ahead of uncertain demand",
        statement=f"{company} appears to be committing capital to capacity "
                  f"ahead of demand it does not control.",
        reasoning="Stated capacity investment and a written-down dependence "
                  "on a few buyers match the capacity-ahead-of-demand "
                  "mechanism: fixed cost is committed in large increments "
                  "against demand that arrives in small ones.",
        supporting_observation_ids=["o1"], counter_observation_ids=[],
        alternative_explanations=["The capacity is pre-sold under long-term "
                                  "agreements."],
        confidence="moderate", confidence_reasons=["two independent signals"],
        evidence_gaps=["Segment revenue is not disaggregated."],
        decision_implications=["Whether a supply commitment is fixed or "
                               "renegotiable."],
        falsification_questions=["Disclosed segment revenue showing no "
                                 "concentration."],
        pattern_id=PATTERN,
        mechanism_evidence=(MechanismEvidence(
            signal="capacity_investment",
            label="is committing capital to capacity ahead of the demand "
                  "for it",
            quote=quote, observation_id="o1", source_title=source),))


CAT = hypothesis(
    "Caterpillar Inc.",
    "Dealer inventory levels and machine backlog set the production plan "
    "before end-user demand is observed",
    "SEC 10-K (2026-02-11)")
XOM = hypothesis(
    "Exxon Mobil Corporation",
    "Major projects are sanctioned years ahead of first production and "
    "capital is committed against a price the company does not set",
    "SEC 10-K (2026-02-28)")


# --- what the repair closes ---------------------------------------------

def test_each_company_has_its_own_qualifying_sentence():
    """The per-company evidence exists. `reasoning._mechanism_evidence`
    captures it at the only point that still knows which signal qualified."""
    cat = grounding_of(CAT)
    xom = grounding_of(XOM)
    assert cat and xom and cat != xom
    assert "Dealer inventory" in cat and "Dealer inventory" not in xom
    assert "sanctioned" in xom and "sanctioned" not in cat


def test_the_mechanism_itself_stays_the_shared_one():
    """DELIBERATELY NOT GROUNDED. Appending the quote here turned
    `test_no_sentence_is_printed_twice_in_either_document` red — the Full
    Analysis already prints it via `mechanism.because_line` — and did nothing
    for the surface that was measured identical, because board answers route
    off topic, falsifier and recommendation, never off the mechanism. A change
    that duplicated on one surface and did not reach the other was not half a
    fix; it was neither half."""
    assert mechanism_sentence(CAT) == mechanism_sentence(XOM)
    assert "Dealer inventory" not in mechanism_sentence(CAT)


def _brief_for(company):
    """A real brief carrying a reading, as production does when a pattern
    matched. A brief with no `key_insight` is WITHHELD and returns early —
    which is correct, and would make this test measure the withheld path
    rather than the grounding."""
    from intent_engine.founder_brief import build as fb
    from intent_engine.founder_brief.contract import FounderInsight
    brief = fb.build(company=company, mode=fb.classify_mode(
        is_public=True, evidence_count=1, independent_sources=1,
        has_thesis=True), report={}, observations=[])
    brief.key_insight = FounderInsight(
        fact=f"{company} is committing capital to capacity ahead of demand.",
        interpretation="Fixed cost is committed in large increments against "
                       "demand that arrives in small ones.",
        so_what="A supply commitment may be less renegotiable than assumed.",
        decision="Whether to treat the commitment as fixed.",
        watch="Segment revenue disaggregation.",
        confidence="moderate")
    return brief


def test_the_qa_answer_carries_whose_filing_made_it_true():
    """THROUGH `answer()`, NOT THE HELPER. Calling `_pattern_grounding`
    directly would walk straight past the call site that is the actual
    repair; that mistake has already been made twice this session.

    Q&A reads the DECISION, because the brief carries a projected
    `FounderInsight` that has no hypothesis on it at all — which is exactly
    why this surface had no access to the quote."""
    from intent_engine.founder_brief import qa as fqa

    cat = fqa.answer("What should management do?",
                     _brief_for("Caterpillar Inc."),
                     decision=compose_decision("Caterpillar Inc.",
                                               CAT).as_dict())
    xom = fqa.answer("What should management do?",
                     _brief_for("Exxon Mobil Corporation"),
                     decision=compose_decision("Exxon Mobil Corporation",
                                               XOM).as_dict())
    assert cat.strongest_evidence and xom.strongest_evidence
    assert cat.strongest_evidence != xom.strongest_evidence
    assert "Dealer inventory" in cat.strongest_evidence
    assert "sanctioned" in xom.strongest_evidence


def test_the_decision_carries_the_grounding():
    cat = compose_decision("Caterpillar Inc.", CAT)
    xom = compose_decision("Exxon Mobil Corporation", XOM)
    assert cat.grounded_in and xom.grounded_in
    assert cat.grounded_in != xom.grounded_in
    assert "grounded_in" in cat.as_dict()


def test_an_answer_that_chose_its_own_evidence_keeps_it():
    """The grounding fills a gap; it does not overwrite a choice. An evidence
    question picks its own source and must keep it."""
    from intent_engine.founder_brief import qa as fqa

    observations = [{"source_class": "independent_reporting",
                     "text": "An independent review of dealer channels.",
                     "date": "2026-03-01", "observation_id": "o9"}]
    answered = fqa.answer("What is the strongest evidence?",
                          _brief_for("Caterpillar Inc."),
                          decision=compose_decision("Caterpillar Inc.",
                                                    CAT).as_dict(),
                          observations=observations)
    assert "Dealer inventory levels and machine backlog" not in \
        (answered.strongest_evidence or ""), \
        "the grounding overwrote evidence the answer had already chosen"
    assert "independent review of dealer channels" in \
        (answered.strongest_evidence or "")


# --- what the repair does NOT close, stated as an expectation -----------

@pytest.mark.xfail(strict=True, reason=(
    "KNOWN DEFECT, measured live on 31e6138: two companies sharing a pattern "
    "share topic, alternatives, falsifier and implications, because those are "
    "the pattern's static text. Grounding the answer's evidence was the "
    "produced-and-never-read half; this is the template itself. Recorded as "
    "an executable expectation so the day it passes is visible."))
def test_two_companies_sharing_a_pattern_do_not_share_the_whole_decision():
    cat = compose_decision("Caterpillar Inc.", CAT)
    xom = compose_decision("Exxon Mobil Corporation", XOM)
    shared = [f for f in ("topic", "falsifier", "limitation",
                          "recommendation_reason")
              if getattr(cat, f) and getattr(cat, f) == getattr(xom, f)]
    assert not shared, f"identical across two different filers: {shared}"
