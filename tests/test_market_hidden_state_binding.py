"""Posture inference — the third module production never fed.

hidden_state.py is complete and careful. learning_cycle.run accepts
`hidden_states=` and `hidden_state_observations=`. Production passed neither,
so companies_tracked read 0 since the subsystem was built and it was carried
as working the whole time.
"""
import pytest

from intent_engine.market import hidden_state as HS
from intent_engine.market import hidden_state_binding as HSB
from intent_engine.market import micro_evidence as ME


def _ev(etype, fact="Something happened", subject="acme", at="2026-08-01"):
    return ME.MicroEvidence(
        evidence_id=f"ev_{etype}_{at}", subject_company=subject, actor=subject,
        evidence_type=etype, observed_at=at, available_at=at,
        source="https://x.test", fact=fact)


def test_production_now_supplies_what_the_cycle_always_accepted():
    states, observations, _ = HSB.bind([_ev(ME.LAYOFF)], as_of="2026-08-07")
    assert len(states) == 1 and len(observations) == 1
    assert observations[0]["likelihoods"]


def test_an_action_that_says_nothing_about_posture_is_refused():
    _, observations, refused = HSB.bind([_ev(ME.MACRO_RELEASE)],
                                        as_of="2026-08-07")
    assert observations == []
    assert refused["action_says_nothing_about_posture"] == 1


def test_every_row_names_at_least_two_postures_pulling_apart():
    """`observe` refuses less, and it is right to.

    An action every posture explains equally is not evidence about posture,
    and one only a single posture could produce is the caller having stopped
    thinking.
    """
    for etype, table in HSB._LIKELIHOODS.items():
        assert len(table) >= 2, etype
        assert len(set(table.values())) >= 2, etype


def test_no_posture_is_ever_eliminated_only_argued_down():
    """A posture the action explains badly is argued down, never to zero.

    The first version of this test used the real LAYOFF likelihoods, whose
    lowest value is 0.35 — nothing could reach zero, so `all(p > 0)` held
    whatever the arithmetic did and a break proof against the probability
    floor went uncaught. A test that cannot fail is not a test.

    So this drives a posture with a likelihood near zero and asserts it
    still holds mass at the floor, which is what actually keeps a rival
    alive.
    """
    belief = HS.uniform("acme", at="2026-08-01",
                        states=HSB.TRACKED_STATES)
    crushing = {HS.COST_CUTTING: 50.0, HS.EXPANDING: 1e-9,
                HS.WAITING: 1.0}
    moved = HS.observe(belief, action="LAYOFF: cut 1200 roles",
                       likelihoods=crushing, at="2026-08-02")
    by_state = dict(moved.distribution)
    assert by_state[HS.EXPANDING] > 0, "a rival was eliminated outright"
    assert len(moved.distribution) == len(HSB.TRACKED_STATES)

    # and the real likelihoods keep every posture alive too
    ordinary = HS.observe(belief, action="LAYOFF: cut 1200 roles",
                          likelihoods=HSB.likelihoods_for(_ev(ME.LAYOFF)),
                          at="2026-08-02")
    assert all(p > 0 for _s, p in ordinary.distribution)


def test_a_price_cut_and_a_price_rise_say_opposite_things():
    down = HSB.likelihoods_for(_ev(ME.PRICING_SIGNAL, "The company cut prices"))
    up = HSB.likelihoods_for(_ev(ME.PRICING_SIGNAL, "The company raised prices"))
    assert down[HS.PRICE_AGGRESSIVE] > up[HS.PRICE_AGGRESSIVE]
    assert up[HS.GROWING] > down[HS.GROWING]


def test_capex_and_layoffs_move_expansion_in_opposite_directions():
    capex = HSB.likelihoods_for(_ev(ME.CAPEX_SIGNAL))
    layoff = HSB.likelihoods_for(_ev(ME.LAYOFF))
    assert capex[HS.EXPANDING] > layoff[HS.EXPANDING]
    assert layoff[HS.COST_CUTTING] > capex[HS.COST_CUTTING]


def test_the_prior_starts_undecided():
    states, _, _ = HSB.bind([_ev(ME.LAYOFF)], as_of="2026-08-07")
    probabilities = {round(p, 4) for _s, p in states[0].distribution}
    assert len(probabilities) == 1


def test_evidence_without_a_subject_is_refused():
    _, _, refused = HSB.bind([_ev(ME.LAYOFF, subject="")], as_of="2026-08-07")
    assert refused["no_subject"] == 1


def test_likelihoods_are_ordinal_not_estimated_frequencies():
    """Three decimal places here would be the 0.586-as-confidence error."""
    values = {v for table in HSB._LIKELIHOODS.values()
              for v in table.values()}
    assert values <= {HSB.TELLING, HSB.NEUTRAL, HSB.UNLIKELY}
