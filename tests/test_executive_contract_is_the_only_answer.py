"""D17. One question, one answer: does a supported reading of this company exist?

Live on `fbb62ff`, one Cloudflare run said all three of these at once:

    X-Ray:   "Supported in direction, not in size · Pricing decision"
    Brief:   "No strategic reading of Cloudflare, Inc. cleared the evidence
              bar, so none is asserted here."
    Slide 1: "not enough to read a strategy from."

Two decision objects, each internally honest, each deciding SEPARATELY whether
there was anything to say. Bank of America, which has no market snapshot,
showed both surfaces agreeing — which is what identified the trigger.

This file pins the contract, not the prose. A surface may still be richer or
terser than its neighbour; none of them may reach its own verdict on whether a
reading exists.
"""
import pytest

from intent_engine.executive import contract as ec
from intent_engine.strategic_intelligence.decision import (
    DECISION_READY, FounderDecision, WITHHELD)


def _run(supported):
    return FounderDecision(
        readiness=DECISION_READY if supported else WITHHELD,
        standing="SUPPORTED" if supported else "REFUSED")


def _market(supported):
    return {"readiness": DECISION_READY if supported else WITHHELD,
            "standing": "SUPPORTED" if supported else "REFUSED"}


# --- §14, the eight cases -------------------------------------------------

def test_case_1_run_supports_market_unavailable():
    c = ec.decide(run_decision=_run(True), market_decision=None)
    assert c.merge_state == ec.CURRENT_RUN_SUPPORTED and c.reading_exists


def test_case_2_run_bounded_market_supports():
    """The case that WAS D17."""
    c = ec.decide(run_decision=_run(False), market_decision=_market(True))
    assert c.merge_state == ec.MARKET_SUPPORTED
    assert c.reading_exists, (
        "a run that did not clear its own bar erased a market reading that "
        "did; that is the contradiction D17 named")
    assert c.run_contribution, (
        "the contract must say what THIS run failed to do, or the surfaces "
        "have nothing honest to put in place of the refusal")


def test_case_3_both_support():
    c = ec.decide(run_decision=_run(True), market_decision=_market(True))
    assert c.merge_state == ec.BOTH_SUPPORTED and c.reading_exists


def test_case_4_and_5_stale_or_invalid_market_is_never_inherited():
    stale = ec.decide(run_decision=_run(False), market_decision=_market(True),
                      market_usable=False, market_reason="snapshot is stale")
    assert not stale.reading_exists, (
        "a stale market snapshot was inherited as a supported reading")
    assert stale.market_note, "a snapshot ignored without a reason is silent"

    invalid = ec.decide(run_decision=_run(False),
                        market_decision=_market(True), market_usable=False)
    assert not invalid.reading_exists


def test_case_7_no_market_no_run_support_is_no_reading():
    """The Bank of America control. It must keep agreeing."""
    c = ec.decide(run_decision=_run(False), market_decision=None)
    assert not c.reading_exists
    assert c.merge_state == ec.MARKET_UNAVAILABLE


def test_a_supported_run_survives_an_unusable_market():
    """The market must not be able to DOWNGRADE a run that stands on its own."""
    c = ec.decide(run_decision=_run(True), market_decision=_market(True),
                  market_usable=False, market_reason="stale")
    assert c.reading_exists and c.merge_state == ec.CURRENT_RUN_SUPPORTED


# --- §15, the surfaces may not disagree -----------------------------------

def test_the_brief_does_not_deny_a_reading_the_contract_asserts():
    """The exact sentence pair that was live."""
    from intent_engine.founder_brief import dossier as fd

    decision = FounderDecision(readiness=WITHHELD, company_name="Cloudflare",
                               unsafe_because="no outside account tested it")
    contract = ec.decide(company="Cloudflare", run_decision=decision,
                         market_decision=_market(True))

    lead = fd.render_decision_lead(decision, "Cloudflare", contract=contract)
    assert "No strategic reading of Cloudflare cleared" not in lead, (
        "the brief denies a reading the X-Ray asserts")
    assert "exists" in lead.lower()
    # and it must still say what this run failed to do, not paper over it
    assert "did not add enough independent evidence" in lead


def test_the_brief_still_refuses_when_the_contract_refuses():
    """The fix must not turn every refusal into a claim."""
    from intent_engine.founder_brief import dossier as fd

    decision = FounderDecision(readiness=WITHHELD, company_name="Nowhere")
    contract = ec.decide(company="Nowhere", run_decision=decision,
                         market_decision=None)
    lead = fd.render_decision_lead(decision, "Nowhere", contract=contract)
    assert "No strategic reading of Nowhere cleared" in lead, (
        "a company with nothing behind it stopped saying so")


def test_without_a_contract_the_old_wording_stands():
    """None must mean "ask the old way", never a blank page."""
    from intent_engine.founder_brief import dossier as fd

    decision = FounderDecision(readiness=WITHHELD, company_name="Nowhere")
    lead = fd.render_decision_lead(decision, "Nowhere", contract=None)
    assert "No strategic reading of Nowhere cleared" in lead


@pytest.mark.parametrize("supported", [True, False])
def test_the_narrative_and_the_brief_reach_the_same_verdict(supported):
    """§15. Render two surfaces from ONE fixture and require agreement."""
    from intent_engine.founder_brief import build as fb
    from intent_engine.founder_brief import dossier as fd
    from intent_engine.founder_brief import narrative as fn

    decision = FounderDecision(readiness=WITHHELD, company_name="Acme")
    contract = ec.decide(company="Acme", run_decision=decision,
                         market_decision=_market(True) if supported else None)
    brief = fb.build(company="Acme", mode=fb.classify_mode(
        is_public=False, evidence_count=0, independent_sources=0,
        has_thesis=False), report={}, observations=[])
    lead = fd.render_decision_lead(decision, "Acme", contract=contract)
    story = fn.build_narrative(company="Acme", brief=brief, report={},
                               decision=decision, contract=contract)
    text = " ".join(p for s in story.sections for p in s.paragraphs)

    denies_lead = "No strategic reading of Acme cleared" in lead
    denies_story = "No strategic reading of Acme cleared" in text
    assert denies_lead == denies_story, (
        f"the brief and the primary screen disagree about whether a reading "
        f"exists (brief denies={denies_lead}, screen denies={denies_story})")
    assert denies_lead is not supported
