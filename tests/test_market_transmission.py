"""The join between an economy and a company, and why it stays a hypothesis.

The temptation is to treat the join as a conclusion: rates rose, this company
said it is rate-sensitive, therefore its costs are rising. That is usually
reasonable and it is not an observation — the company may have hedged,
refinanced early, or be sitting on cash.
"""
from __future__ import annotations

import pytest

from intent_engine.market import company_exposure as CX
from intent_engine.market import macro_state as MS
from intent_engine.market import transmission as TX


def state(kind=MS.MARKET_RATE, standing=MS.OBSERVED):
    o = MS.MacroObservation(
        state_kind=kind, series_id="S1", label="rate", value=4.0, unit="%",
        reference_period="2026-06-30", published_at="2026-07-15",
        standing=standing)
    return MS.state_of(kind, [o], as_of="2026-08-01")


def exposure(dimension=CX.RATE, standing=CX.OBSERVED):
    return CX.Exposure(company_id="acme", dimension=dimension,
                       standing=standing, basis="our rate exposure is material",
                       evidence_ids=("ev_1",))


# --- it stays a hypothesis --------------------------------------------------

def test_a_transmission_is_born_hypothesized_and_untested():
    t = TX.propose(exposure=exposure(), state=state())
    assert t.standing == TX.HYPOTHESIZED
    assert not t.tested


def test_every_transmission_carries_a_falsifier():
    """A link nothing could disprove is a belief, not a hypothesis."""
    t = TX.propose(exposure=exposure(), state=state())
    assert t.falsifier.strip()
    assert t.alternative_explanation.strip()


def test_a_transmission_without_a_falsifier_is_refused():
    with pytest.raises(TX.TransmissionRejected, match="falsifier"):
        TX.Transmission(company_id="acme", state_kind=MS.MARKET_RATE,
                        dimension=CX.RATE, mechanism="rates matter",
                        direction=TX.RAISES, lag_days=90, falsifier="  ",
                        alternative_explanation="something else")


def test_a_transmission_without_a_mechanism_is_refused():
    """Without one it is a correlation with a company's name attached."""
    with pytest.raises(TX.TransmissionRejected, match="mechanism"):
        TX.Transmission(company_id="acme", state_kind=MS.MARKET_RATE,
                        dimension=CX.RATE, mechanism="   ",
                        direction=TX.RAISES, lag_days=90,
                        falsifier="expense is flat",
                        alternative_explanation="hedged")


def test_an_effect_may_not_precede_its_cause():
    with pytest.raises(TX.TransmissionRejected, match="negative lag"):
        TX.Transmission(company_id="acme", state_kind=MS.MARKET_RATE,
                        dimension=CX.RATE, mechanism="m", direction=TX.RAISES,
                        lag_days=-1, falsifier="f",
                        alternative_explanation="a")


def test_a_lag_makes_silence_readable():
    """Without a due date, "nothing happened" cannot be told apart from "not
    yet", and a transmission that is never due is never wrong."""
    t = TX.propose(exposure=exposure(), state=state())
    assert t.lag_days > 0
    assert t.due_at("2026-08-01") > "2026-08-01"


# --- both ends must be real -------------------------------------------------

def test_an_unestablished_exposure_proposes_nothing():
    """Otherwise this is a sector prior that renders as confidently as a
    measured one."""
    assert TX.propose(exposure=CX.unknown("acme", CX.RATE),
                      state=state()) is None


def test_an_unmeasured_economy_proposes_nothing():
    assert TX.propose(exposure=exposure(),
                      state=MS.unknown(MS.MARKET_RATE)) is None


def test_an_opinion_about_the_economy_proposes_nothing():
    """An opinion about an opinion."""
    assert TX.propose(exposure=exposure(),
                      state=state(standing=MS.HYPOTHESIZED)) is None


def test_an_unrelated_condition_proposes_nothing():
    assert TX.propose(exposure=exposure(dimension=CX.LABOR),
                      state=state(MS.MARKET_RATE)) is None


def test_an_inferred_exposure_still_proposes_but_records_its_standing():
    """Third-party reporting is weaker evidence, not absent evidence."""
    e = CX.Exposure(company_id="acme", dimension=CX.RATE,
                    standing=CX.INFERRED, basis="reported rate sensitivity",
                    evidence_ids=("ev_news",))
    t = TX.propose(exposure=e, state=state())
    assert t is not None
    assert t.exposure_standing == CX.INFERRED


# --- provenance walks to both ends ------------------------------------------

def test_provenance_reaches_the_series_and_the_companys_own_words():
    t = TX.propose(exposure=exposure(), state=state())
    assert t.macro_observation_id.startswith("macro_")
    assert t.exposure_evidence_ids == ("ev_1",)


def test_identity_is_stable_across_dates():
    """The same route for the same company is one hypothesis, whether it was
    proposed today or last month."""
    a = TX.propose(exposure=exposure(), state=state(), as_of="2026-08-01")
    b = TX.propose(exposure=exposure(), state=state(), as_of="2026-09-01")
    assert a.transmission_id == b.transmission_id


# --- the mechanism table ----------------------------------------------------

def test_every_exposure_dimension_has_one_stated_mechanism():
    """Written once, centrally, so a mechanism cannot be invented at the call
    site to fit a company — which is how a model starts explaining
    everything."""
    for dimension in CX.DIMENSIONS:
        assert dimension in TX._MECHANISM, dimension
        mechanism, direction, lag, falsifier, alternative = \
            TX._MECHANISM[dimension]
        assert mechanism.strip() and falsifier.strip() and alternative.strip()
        assert direction in TX.DIRECTIONS
        assert lag > 0


def test_capital_intensity_lowers_spending_when_capital_costs_more():
    """Direction is stated, not guessed: a higher hurdle defers a programme."""
    t = TX.propose(exposure=exposure(dimension=CX.CAPITAL_INTENSITY),
                   state=state())
    assert t.direction == TX.LOWERS


def test_currency_is_ambiguous_rather_than_pretending_to_a_sign():
    e = CX.Exposure(company_id="acme", dimension=CX.FX, standing=CX.OBSERVED,
                    basis="currency translation affects reported revenue",
                    evidence_ids=("ev_1",))
    t = TX.propose(exposure=e, state=state(MS.CURRENCY))
    assert t.direction == TX.AMBIGUOUS


# --- summary ----------------------------------------------------------------

def test_the_summary_does_not_turn_a_count_into_a_finding():
    txs = [TX.propose(exposure=exposure(), state=state())]
    got = TX.summarise(txs)
    assert got["by_standing"] == {TX.HYPOTHESIZED: 1}
    assert got["tested"] == 0
    assert got["every_one_falsifiable"]
    assert "not a count of findings" in got["note"]
    assert "confidence" not in got


def test_proposing_across_companies_keeps_them_separate():
    profiles = {
        "a": {CX.RATE: CX.Exposure(company_id="a", dimension=CX.RATE,
                                   standing=CX.OBSERVED, basis="x",
                                   evidence_ids=("e1",))},
        "b": {CX.RATE: CX.unknown("b", CX.RATE)},
    }
    got = TX.propose_all(profiles, [state()])
    assert [t.company_id for t in got] == ["a"]
