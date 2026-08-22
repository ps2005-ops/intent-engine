"""A belief cannot be better established than the rule it instantiates.

Both layers compute correctly from their own inputs and can still be
incoherent together, because maturity counts confirmations of ONE belief and
mechanism calibration counts how the RULE has fared everywhere.
"""
from __future__ import annotations

import json
import pathlib

from intent_engine.market import belief_maturity as BM
from intent_engine.market import calibration_consistency as CK
from intent_engine.market import causal_calibration as CC
from intent_engine.market import mechanism_calibration as MC

REAL_LEDGER = pathlib.Path(
    "/Users/prathamsharma/intent-engine-market/reports/market/"
    "learning_ledger.jsonl")


class Maturity:
    def __init__(self, state, belief_id="b1", subject="shopify"):
        self.state, self.belief_id, self.subject = state, belief_id, subject


class Mechanism:
    def __init__(self, key, maturity):
        self.key, self.maturity = key, maturity


class Causal:
    def __init__(self, family, status):
        self.causal_family, self.status = family, status


def test_a_contested_mechanism_caps_its_beliefs_at_supported():
    got = CK.check(
        maturities=[Maturity(BM.REPEATEDLY_SUPPORTED)],
        mechanisms=[Mechanism("demand_strengthening", MC.CONTESTED)],
        family_of={"b1": "demand_strengthening"})
    assert len(got) == 1
    assert got[0].kind == "BELIEF_ABOVE_ITS_MECHANISM_CEILING"
    assert got[0].permitted == BM.SUPPORTED
    assert "does not promote the rule" in got[0].why


def test_a_failing_mechanism_caps_its_beliefs_lower_still():
    got = CK.check(
        maturities=[Maturity(BM.SUPPORTED)],
        mechanisms=[Mechanism("demand_strengthening", MC.FAILING)],
        family_of={"b1": "demand_strengthening"})
    assert got and got[0].permitted == BM.WEAKENING


def test_an_unfalsifiable_mechanism_caps_its_beliefs_at_candidate():
    got = CK.check(
        maturities=[Maturity(BM.SUPPORTED)],
        mechanisms=[Mechanism("leadership_transition",
                              MC.UNFALSIFIABLE_BY_OBSERVATION)],
        family_of={"b1": "leadership_transition"})
    assert got and got[0].permitted == BM.CANDIDATE


def test_a_belief_at_or_below_its_ceiling_is_coherent():
    assert CK.check(
        maturities=[Maturity(BM.SUPPORTED)],
        mechanisms=[Mechanism("demand_strengthening", MC.CONTESTED)],
        family_of={"b1": "demand_strengthening"}) == ()


def test_a_contested_causal_family_caps_its_own_predictor():
    got = CK.check(
        mechanisms=[Mechanism("demand_strengthening", MC.ESTABLISHED)],
        causal_families=[Causal("demand_strengthening", CC.CONTESTED)])
    assert len(got) == 1
    assert got[0].kind == "MECHANISM_ABOVE_ITS_CAUSAL_CEILING"
    assert "may still predict" in got[0].why


def test_an_unmeasurable_causal_family_caps_nothing():
    """UNMEASURABLE is not a finding against the predictor."""
    assert CK.check(
        mechanisms=[Mechanism("demand_strengthening", MC.ESTABLISHED)],
        causal_families=[Causal("demand_strengthening",
                                CC.UNMEASURABLE)]) == ()


def test_a_belief_with_no_known_family_is_not_judged():
    assert CK.check(maturities=[Maturity(BM.REPEATEDLY_SUPPORTED)],
                    mechanisms=[Mechanism("x", MC.FAILING)],
                    family_of={}) == ()


def test_nothing_is_rewritten():
    """The checker reports; it never downgrades stored state."""
    maturity = Maturity(BM.REPEATEDLY_SUPPORTED)
    CK.check(maturities=[maturity],
             mechanisms=[Mechanism("demand_strengthening", MC.FAILING)],
             family_of={"b1": "demand_strengthening"})
    assert maturity.state == BM.REPEATEDLY_SUPPORTED


def test_precedence_is_stated_in_the_summary():
    got = CK.summarise(())
    assert "caps" in got["precedence"]
    assert got["incoherent_pairs"] == 0


def test_the_real_ledger_is_currently_coherent():
    """Zero is the finding, and the guard exists for when it is not."""
    if not REAL_LEDGER.exists():                       # pragma: no cover
        return
    from intent_engine.universe.companies import default_universe

    rows = [json.loads(line) for line in
            REAL_LEDGER.read_text().splitlines() if line.strip()]
    industry = {c.company_id: (getattr(c, "industry", "") or "")
                for c in default_universe().prediction_companies()}
    family_of = {r.get("hypothesis_id"): r.get("metric") for r in rows
                 if r.get("record") == "expectation"}
    got = CK.check(maturities=BM.classify(rows, as_of="2026-08-07"),
                   mechanisms=MC.calibrate(rows),
                   causal_families=CC.calibrate(rows, industry_of=industry),
                   family_of=family_of)
    assert got == ()
