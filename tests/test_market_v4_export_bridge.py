"""The producing end of the economic bridge, and what it refuses to ship."""
from __future__ import annotations

import pytest

from intent_engine.market import economic_thesis as ET
from intent_engine.market import macro_state as MS
from intent_engine.market import strategic_export as SE


def state(kind=MS.POLICY_RATE, area=MS.CA, known=True):
    if not known:
        return MS.unknown(kind, area=area)
    obs = MS.MacroObservation(
        state_kind=kind, area=area, series_id="S", label="rate", value=2.25,
        unit="%", reference_period="2026-08-01", published_at="2026-08-05",
        publication_basis=MS.ASSUMED_LAG, source="t")
    return MS.EconomicState(state_kind=kind, standing=MS.OBSERVED, area=area,
                            observation=obs, reason="rate 2.25%")


def thesis(**kw):
    kwargs = dict(
        subject="acme", question="what does the rate mean?",
        claim="capex falls",
        leading_mechanism=ET.Mechanism(description="hurdle rises",
                                       falsifier="capex rises anyway"),
        alternatives=(ET.Mechanism(description="already committed",
                                   falsifier="it was not"),),
        macro_conditions=("MARKET_RATE",), exposures=("CAPITAL_INTENSITY",),
        as_of="2026-08-08")
    kwargs.update(kw)
    return ET.EconomicThesis(**kwargs)


def test_the_economic_block_passes_the_producers_own_allowlist():
    payload = SE.build_export(company_id="acme", as_of="2026-08-08",
                              economic_states=[state()],
                              economic_theses=[thesis()])
    assert payload["economic_theses"][0]["claim"] == "capex falls"
    assert payload["economic_context"]["conditions_known"] == 1


def test_unknown_conditions_are_counted_and_not_shipped_as_rows():
    payload = SE.build_export(
        company_id="acme", as_of="2026-08-08",
        economic_states=[state(), state(MS.INFLATION, known=False)])
    ctx = payload["economic_context"]
    assert ctx["conditions_tracked"] == 2 and ctx["conditions_known"] == 1
    assert len(ctx["conditions"]) == 1
    assert "never a condition that did not move" in ctx["note"]


def test_alternatives_are_shipped_rather_than_summarised_away():
    payload = SE.build_export(company_id="acme", as_of="2026-08-08",
                              economic_theses=[thesis()])
    assert payload["economic_theses"][0]["alternatives"] == \
        ["already committed"]
    assert payload["economic_theses"][0]["falsifier"]


def test_an_absent_economy_omits_the_block_rather_than_shipping_an_empty_one():
    payload = SE.build_export(company_id="acme", as_of="2026-08-08")
    assert "economic_context" not in payload
    assert "economic_theses" not in payload


def test_a_thesis_carrying_trading_language_fails_the_export():
    with pytest.raises(SE.ExportLeak):
        SE.build_export(company_id="acme", as_of="2026-08-08",
                        economic_theses=[thesis(claim="a clear buy signal")])
