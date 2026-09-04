"""Strategic interactions — and why the corpus does not yet support any.

The first version matched on shared SECTOR and produced three records, all
nonsense: ASML's semiconductor-equipment partnership paired with Infosys's
IT-services partnership because both are "Technology", emitted in both
directions because each fact carried several evidence ids.

These tests pin the refusals that replaced it. A module that returns nothing
for the right reason is worth more than one that returns three fabricated
interactions.
"""
import pytest

from intent_engine.market import interaction_binding as IB
from intent_engine.market import micro_evidence as ME
from intent_engine.market import strategic_interaction as SI


def _ev(subject, etype=ME.PRICING_SIGNAL, at="2026-08-01", fact="cut prices"):
    return ME.MicroEvidence(
        evidence_id=f"ev_{subject}_{at}", subject_company=subject,
        actor=subject, evidence_type=etype, observed_at=at, available_at=at,
        source="https://x.test", fact=fact)


IND = {"acme": "Retail", "wayne": "Retail", "stark": "Retail"}
RIVALS = {"acme": frozenset({"wayne"}), "wayne": frozenset({"acme"})}


def test_without_competitor_relationships_nothing_is_produced():
    """Sector is not rivalry, and falling back to it fabricated records."""
    out, refused = IB.bind([_ev("acme"), _ev("wayne", at="2026-08-02")],
                           industry_of=IND)
    assert out == ()
    assert refused["no_competitor_relationships_available"] == 1


def test_a_sector_neighbour_who_is_not_a_rival_is_refused():
    out, refused = IB.bind(
        [_ev("acme"), _ev("stark", at="2026-08-02")],
        industry_of=IND, competitors_of=RIVALS)
    assert out == ()
    assert refused["counterparty_is_not_a_named_competitor"] >= 1


def test_a_named_rival_moving_afterwards_is_recorded():
    out, _ = IB.bind([_ev("acme"), _ev("wayne", at="2026-08-02")],
                     industry_of=IND, competitors_of=RIVALS)
    assert len(out) == 1
    assert out[0].focal_actor == "acme"
    assert out[0].responding_actor == "wayne"


def test_a_pair_is_recorded_once_not_in_both_directions():
    out, _ = IB.bind(
        [_ev("acme"), _ev("wayne", at="2026-08-02"),
         _ev("acme", at="2026-08-03"), _ev("wayne", at="2026-08-04")],
        industry_of=IND, competitors_of=RIVALS)
    assert len(out) == 1


def test_a_different_kind_of_action_is_not_a_response():
    out, _ = IB.bind(
        [_ev("acme", etype=ME.PRICING_SIGNAL),
         _ev("wayne", etype=ME.MA_ACTIVITY, at="2026-08-02")],
        industry_of=IND, competitors_of=RIVALS)
    assert out == ()


def test_a_move_beyond_the_window_is_its_own_event():
    out, _ = IB.bind([_ev("acme", at="2026-01-01"),
                      _ev("wayne", at="2026-08-02")],
                     industry_of=IND, competitors_of=RIVALS)
    assert out == ()


def test_earnings_are_never_paired():
    """Every company reports on its own calendar; pairing those would
    manufacture an interaction out of the reporting season."""
    assert ME.EARNINGS_RESULT not in IB.RESPONSIVE_TYPES


def test_no_motive_is_ever_asserted():
    out, _ = IB.bind([_ev("acme"), _ev("wayne", at="2026-08-02")],
                     industry_of=IND, competitors_of=RIVALS)
    assert out[0].inferred_objective == ""
    assert out[0].payoff_change == SI.UNKNOWN


def test_the_same_conditions_explanation_is_always_alive():
    out, _ = IB.bind([_ev("acme"), _ev("wayne", at="2026-08-02")],
                     industry_of=IND, competitors_of=RIVALS)
    assert any("same market conditions" in a
               for a in out[0].alternative_explanations)


def test_the_contract_refuses_a_motive_without_an_alternative():
    with pytest.raises(SI.InteractionRejected):
        SI.record(focal_actor="acme", responding_actor="wayne",
                  initial_action="cut prices", at="2026-08-01",
                  inferred_objective="defend share",
                  evidence_ids=("ev_1",))
