"""Demand is nine things; a number needs a subject; a slide may not overclaim."""
from __future__ import annotations

import pytest

from intent_engine.market import demand_chain as DC
from intent_engine.market import economic_quantity as EQ
from intent_engine.market import economic_thesis as ET
from intent_engine.market import presentation as PR


def row(fact, role="regulatory_filing", eid="e1", company="acme"):
    return {"record": "evidence", "subject_company": company,
            "evidence_id": eid, "fact": fact, "source_role": role,
            "observed_at": "2026-05-01"}


# --- a number needs an economic subject ------------------------------------------

def test_a_bare_percentage_is_not_a_quantity():
    got, refused = EQ.extract("The figure was 12%.")
    assert got == [] and "no_subject" in refused


def test_a_structural_reference_is_never_a_measurement():
    got, refused = EQ.extract("See Item 7 for revenue of 12 million.")
    assert got == []
    assert "structural_reference_not_a_measurement" in refused


def test_a_number_belonging_to_analysts_is_refused():
    got, refused = EQ.extract("Analysts expect revenue of $4 billion.")
    assert got == []
    assert "number_belongs_to_another_party" in refused


def test_a_buyback_is_not_revenue():
    """The live defect: the sentence names revenue and the number is a buyback."""
    got, _ = EQ.extract("Grows Q2 revenue and details $400M buyback")
    assert all(q.quantity_type != EQ.REVENUE or q.value != 400.0
               for q in got)


def test_the_nearest_number_wins_even_when_it_precedes_the_subject():
    """A forward-only scan read this as the net income figure."""
    got, _ = EQ.extract("ASML reports EUR 9.3 billion total net sales and "
                        "EUR 2.9 billion net income")
    revenue = [q for q in got if q.quantity_type == EQ.REVENUE]
    assert revenue and revenue[0].value == 9.3e9


def test_a_level_and_a_change_are_different_facts():
    level, _ = EQ.extract("Gross margin of 51.4% in the quarter.")
    change, _ = EQ.extract("Gross margin rose 140 basis points.")
    assert level[0].basis == EQ.LEVEL
    assert change[0].basis == EQ.CHANGE


def test_a_quantity_without_its_words_is_refused():
    with pytest.raises(EQ.QuantityRejected):
        EQ.EconomicQuantity(quantity_type=EQ.REVENUE, value=1.0, unit="$",
                            source_span="")


def test_a_quantity_without_a_unit_is_refused():
    with pytest.raises(EQ.QuantityRejected):
        EQ.EconomicQuantity(quantity_type=EQ.REVENUE, value=1.0, unit=" ",
                            source_span="revenue of one")


def test_the_summary_reports_the_refusals_not_just_the_keeps():
    got, refused = EQ.extract("The figure was 12%. Revenue of $4 billion.")
    summary = EQ.summarise(got, refused)
    assert summary["refused"] >= 1
    assert summary["yield"] is not None and summary["yield"] < 1.0
    assert "subject-first" in summary["note"]


# --- demand is nine states, not one ------------------------------------------------

def test_a_backlog_figure_refuses_to_speak_for_demand():
    reading = DC.DemandReading(company_id="acme", state=DC.BACKLOG,
                               direction="UP", basis="backlog rose")
    with pytest.raises(DC.UnmediatedInference) as err:
        DC.implies_demand(reading)
    assert "measured before the chain carries anything" in str(err.value)


def test_the_states_are_not_interchangeable():
    for name in ("END_DEMAND", "ORDERS", "BACKLOG", "SHIPMENTS", "REVENUE"):
        assert name in DC.STATES
    assert len(set(DC.STATES)) == len(DC.STATES)


def test_cancellations_are_a_leak_and_not_a_step():
    on_path = {s for pair in DC.LINKS for s in pair}
    assert DC.CANCELLATIONS not in on_path


def test_a_companys_own_filing_observes_and_a_report_only_infers():
    own = DC.read_states([row("Backlog rose to 3.2 billion.")],
                         company_id="acme")
    reported = DC.read_states(
        [row("Backlog rose to 3.2 billion.",
             role="independent_reporting")], company_id="acme")
    assert own[DC.BACKLOG].standing == DC.OBSERVED
    assert reported[DC.BACKLOG].standing == DC.INFERRED


def test_two_measured_states_moving_apart_is_contradicted():
    chain = DC.build([row("Backlog rose sharply this quarter.", eid="e1"),
                      row("Shipments declined in the period.", eid="e2")],
                     company_id="acme")
    link = [l for l in chain.links
            if (l.upstream, l.downstream) == (DC.BACKLOG, DC.SHIPMENTS)][0]
    assert link.standing == DC.CONTRADICTED


def test_two_states_moving_together_is_consistent_and_not_established():
    chain = DC.build([row("Shipments rose in the period.", eid="e1"),
                      row("Revenue rose in the period.", eid="e2")],
                     company_id="acme")
    link = [l for l in chain.links
            if (l.upstream, l.downstream) == (DC.SHIPMENTS, DC.REVENUE)][0]
    assert link.standing == DC.HYPOTHESIZED
    assert "does not establish it" in link.reason


def test_a_chain_is_worth_its_weakest_link():
    chain = DC.build([row("Revenue rose in the period.")], company_id="acme")
    assert chain.standing == DC.UNKNOWN
    # One measured state out of ten leaves seven links with nothing at either
    # end; the weakest is reported by name rather than averaged into a score.
    assert "is measured" in chain.weakest.reason
    assert chain.as_dict()["weakest_link"].startswith("END_DEMAND")


def test_every_link_carries_the_other_explanation():
    chain = DC.build([row("Backlog rose.")], company_id="acme")
    assert all(l.alternative and l.falsifier for l in chain.links)
    backlog_link = [l for l in chain.links
                    if l.downstream == DC.BACKLOG][0]
    assert "deliveries slipped" in backlog_link.alternative


def test_an_unmeasured_state_is_reported_rather_than_omitted():
    chain = DC.build([row("Revenue rose.")], company_id="acme")
    got = chain.as_dict()
    assert DC.END_DEMAND in got["unknown_states"]
    assert got["known_states"] == 1


def test_the_summary_never_averages_a_contradiction_away():
    chain = DC.build([row("Backlog rose sharply.", eid="e1"),
                      row("Shipments declined.", eid="e2")],
                     company_id="acme")
    got = DC.summarise([chain])
    assert got["contradicted_links"]
    assert got["every_link_has_an_alternative"] is True


# --- the deck is a view -------------------------------------------------------------

def mech(desc="a higher cost of capital raises the hurdle",
         falsifier="capital spending rises anyway"):
    return ET.Mechanism(description=desc, falsifier=falsifier, lag_days=270)


def thesis(standing=ET.PROPOSED, alternatives=None, **kw):
    kwargs = dict(subject="acme", question="what does the rate mean?",
                  claim="capex falls", leading_mechanism=mech(),
                  macro_conditions=("MARKET_RATE",),
                  exposures=("CAPITAL_INTENSITY",), horizon_days=270,
                  standing=standing, as_of="2026-08-08")
    if alternatives is None:
        alternatives = (mech("it was already committed", "it was not"),)
    kwargs["alternatives"] = tuple(alternatives)
    if standing == ET.TESTED:
        kwargs["supporting_evidence"] = ("e1",)
    kwargs.update(kw)
    return ET.EconomicThesis(**kwargs)


def test_a_slide_that_cannot_name_its_source_is_refused():
    with pytest.raises(PR.DeckRejected) as err:
        PR.Slide(section=PR.ANSWER, heading="h", bullets=("b",),
                 sourced_from="")
    assert "written rather than rendered" in str(err.value)


def test_certainty_language_is_refused_at_any_standing():
    with pytest.raises(PR.DeckRejected) as err:
        PR.Slide(section=PR.ANSWER, heading="This is guaranteed",
                 sourced_from="thesis.claim", bullets=("x",))
    assert "outlives the standing field" in str(err.value)


def test_the_headline_verb_is_bound_to_the_standing():
    weak = PR.build(thesis(standing=ET.PROPOSED))
    strong = PR.build(thesis(standing=ET.TESTED))
    weak_text = weak.slides[0].bullets[0]
    strong_text = strong.slides[0].bullets[0]
    assert "may be" in weak_text
    assert "tried to break" in strong_text


def test_the_alternatives_slide_is_never_empty():
    deck = PR.build(thesis())
    alts = [s for s in deck.slides if s.section == PR.ALTERNATIVES][0]
    assert alts.bullets


def test_a_thesis_with_no_alternatives_says_so_rather_than_omitting_the_slide():
    deck = PR.build(thesis(standing=ET.PROPOSED, alternatives=()))
    alts = [s for s in deck.slides if s.section == PR.ALTERNATIVES][0]
    assert "itself a weakness" in alts.bullets[0]


def test_an_empty_section_is_reported_not_filled():
    deck = PR.build(thesis())
    got = deck.as_dict()
    assert PR.SECOND_ORDER in got["empty_sections"]
    assert "never filled with prose" in PR.summarise([deck])["note"]


def test_the_deck_carries_the_falsifier():
    deck = PR.build(thesis())
    minds = [s for s in deck.slides if s.section == PR.CHANGE_OUR_MIND][0]
    assert "capital spending rises anyway" in minds.bullets


def test_a_deck_edited_afterwards_is_caught_by_check():
    t = thesis(standing=ET.PROPOSED)
    deck = PR.build(t)
    tampered = PR.Deck(
        subject=deck.subject, thesis_id=deck.thesis_id,
        standing=ET.TESTED,
        slides=tuple(PR.Slide(section=s.section, heading=s.heading,
                              bullets=s.bullets,
                              sourced_from=s.sourced_from,
                              standing=ET.TESTED) for s in deck.slides))
    got = PR.check(tampered, t)
    assert got["consistent"] is False
    assert any("never more" in p for p in got["problems"])


def test_a_deck_belonging_to_another_thesis_is_caught():
    got = PR.check(PR.build(thesis()), thesis(claim="something else"))
    assert got["consistent"] is False
    assert any("does not belong" in p for p in got["problems"])
