"""A page may not say no reading exists while rendering one.

MEASURED, Pfizer Inc. on 743df06 and cb9e6b7. Twelve usable documents across
five families, and `/full` said:

    "No strategic reading of Pfizer Inc. cleared the evidence bar, so none is
     asserted here."

while `/intro`, `/story` and `/connect` on the SAME run said Pfizer "runs on a
product or service that may only be sold once a regulator permits it and a
payer agrees to pay for it", named generic competition to Xtandi and Xeljanz
as the substitution, and set out rebate economics.

The curated transition library matching nothing is a fact about a twelve-entry
library. `executive.contract` -- the one place that answers "does a reading
exist" -- knew about two producers, the run's transition decision and the
published market reading, and never about the third: the bounded economic read
the surfaces were already projecting.
"""
from intent_engine.executive.contract import (
    BOUNDED_READ_ONLY, MARKET_UNAVAILABLE, NO_SUPPORTED_READING,
    CURRENT_RUN_SUPPORTED, decide,
)


def test_a_bounded_read_is_a_reading():
    c = decide(company="Pfizer Inc.", run_decision=None,
               market_decision=None, bounded_read=True)
    assert c.merge_state == BOUNDED_READ_ONLY
    assert c.reading_exists is True


def test_a_genuinely_empty_run_still_refuses():
    """THE CONTROL. This must be able to fail, or the fix is a rubber stamp."""
    c = decide(company="Nobody Ltd.", run_decision=None,
               market_decision=None, bounded_read=False)
    assert c.merge_state == MARKET_UNAVAILABLE
    assert c.reading_exists is False


def test_a_supported_run_is_unchanged_by_the_new_input():
    """A transition that matched outranks the bounded fallback, both ways."""
    supported = {"readiness": "DECISION_READY", "standing": "SUPPORTED"}
    for bounded in (True, False):
        c = decide(company="X", run_decision=supported, market_decision=None,
                   bounded_read=bounded)
        assert c.merge_state == CURRENT_RUN_SUPPORTED, bounded
        assert c.reading_exists is True


def test_the_bounded_state_does_not_claim_to_be_supported():
    """Bounded is not supported, and the state has to keep them apart."""
    c = decide(company="Pfizer Inc.", bounded_read=True)
    assert c.merge_state != CURRENT_RUN_SUPPORTED
    assert c.merge_state != NO_SUPPORTED_READING


def test_the_answer_section_stops_denying_the_page_it_is_on():
    """END TO END, through the section a customer actually reads."""
    from intent_engine.founder_brief import narrative as N
    from intent_engine.founder_brief.build import FounderBrief
    from intent_engine.strategic_intelligence.decision import decision_of

    brief = FounderBrief(company="Pfizer Inc.", mode="public_company",
                         what_it_does="Pfizer Inc. is a healthcare business.")
    decision = decision_of({})              # nothing matched -> WITHHELD
    contract = decide(company="Pfizer Inc.", bounded_read=True)
    story = N.build_narrative(company="Pfizer Inc.", brief=brief,
                              report={}, decision=decision, contract=contract)
    answer = " ".join(
        p for s in story.sections if s.title == "The answer"
        for p in s.paragraphs)
    assert "cleared the evidence bar" not in answer, answer
    assert "none is asserted here" not in answer, answer
    # And it must not send the reader somewhere else for what is on this page.
    assert "Executive X-Ray" not in answer, answer
    assert "no curated transition pattern matched" in answer.lower(), answer


def test_an_empty_run_still_gets_the_refusal_in_the_answer_section():
    """THE CONTROL, end to end. Honest refusal must survive the repair."""
    from intent_engine.founder_brief import narrative as N
    from intent_engine.founder_brief.build import FounderBrief
    from intent_engine.strategic_intelligence.decision import decision_of

    brief = FounderBrief(company="Nobody Ltd.", mode="public_company")
    contract = decide(company="Nobody Ltd.", bounded_read=False)
    story = N.build_narrative(company="Nobody Ltd.", brief=brief, report={},
                              decision=decision_of({}), contract=contract)
    answer = " ".join(
        p for s in story.sections if s.title == "The answer"
        for p in s.paragraphs)
    assert "cleared the evidence bar" in answer, answer
