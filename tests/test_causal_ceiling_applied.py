"""A hit rate may not be published as a causal mechanism.

`calibration_consistency.check` could always SEE a mechanism sitting above its
causal ceiling. Nothing applied it: no module under `src/` imported that one,
so `learning_health` published `MC.summarise(MC.calibrate(rows))` unmodified
and `demand_strengthening` -- 19 confirmations, 1 contradiction, reliability
0.95 -- was published ESTABLISHED while its causal family stood at CONTESTED.

These tests pin the application, not the detection. The detection already had
nine deterministic tests in `test_market_calibration_consistency.py` and all
of them passed throughout.
"""
import collections

import pytest

from intent_engine.market import belief_maturity as BM
from intent_engine.market import calibration_consistency as CK
from intent_engine.market import causal_calibration as CC
from intent_engine.market import mechanism_calibration as MC


def _summary(**rows):
    """An `MC.summarise`-shaped dict with the fields the cap reads."""
    mechanisms = [
        dict(mechanism=key, maturity=maturity, confirmed=confirmed,
             contradicted=contradicted, reliability=reliability)
        for key, (maturity, confirmed, contradicted, reliability)
        in rows.items()]
    return {
        "mechanisms": mechanisms,
        "by_maturity": dict(collections.Counter(
            m["maturity"] for m in mechanisms)),
        "mechanisms_total": len(mechanisms),
    }


def _breach(family, *, causal=CC.CONTESTED, mechanism=MC.ESTABLISHED):
    return CK.Incoherence(
        kind="MECHANISM_ABOVE_ITS_CAUSAL_CEILING", family=family, subject="",
        upper_layer="causal_calibration", upper_state=causal,
        lower_layer="mechanism_calibration", lower_state=mechanism,
        permitted=CK._CAUSAL_CAP[causal],
        why=f"the causal family is {causal}")


# ===========================================================================
# THE CENTRAL PROPERTY
# ===========================================================================
def test_a_high_hit_rate_cannot_publish_above_a_contested_causal_ceiling():
    """19/20 and reliability 0.95 still publishes CONTESTED, not ESTABLISHED.

    This is the exact live shape that reached an operator screen.
    """
    summary = _summary(demand_strengthening=(MC.ESTABLISHED, 19, 1, 0.95))
    got = CK.cap_mechanism_summary(
        summary, (_breach("demand_strengthening"),))
    row, = got["mechanisms"]
    assert row["maturity"] == MC.CONTESTED
    assert row["maturity"] != MC.ESTABLISHED
    # the hit rate itself is untouched -- it was never the thing that was wrong
    assert row["confirmed"] == 19 and row["contradicted"] == 1
    assert row["reliability"] == 0.95


def test_the_overridden_grade_is_preserved_not_erased():
    """A cap that hides what it overrode is just a different wrong number."""
    got = CK.cap_mechanism_summary(
        _summary(demand_strengthening=(MC.ESTABLISHED, 19, 1, 0.95)),
        (_breach("demand_strengthening"),))
    row, = got["mechanisms"]
    assert row["maturity_uncapped"] == MC.ESTABLISHED
    assert row["capped_by"] == "causal_calibration"
    assert row["causal_standing"] == CC.CONTESTED
    assert "causal family" in row["capped_because"]


def test_the_published_counts_agree_with_the_published_rows():
    """`by_maturity` must not still be counting the uncapped grade."""
    got = CK.cap_mechanism_summary(
        _summary(demand_strengthening=(MC.ESTABLISHED, 19, 1, 0.95),
                 pricing_power=(MC.EMERGING, 2, 1, "UNMEASURABLE")),
        (_breach("demand_strengthening"),))
    assert got["by_maturity"].get(MC.ESTABLISHED) is None
    assert got["by_maturity"][MC.CONTESTED] == 1
    assert got["by_maturity"][MC.EMERGING] == 1
    recount = collections.Counter(m["maturity"] for m in got["mechanisms"])
    assert got["by_maturity"] == dict(recount)


# ===========================================================================
# The cap must not fire when there is nothing to cap
# ===========================================================================
def test_no_incoherence_leaves_every_grade_untouched():
    summary = _summary(demand_strengthening=(MC.ESTABLISHED, 19, 1, 0.95),
                       pricing_power=(MC.EMERGING, 2, 1, "UNMEASURABLE"))
    got = CK.cap_mechanism_summary(summary, ())
    assert [m["maturity"] for m in got["mechanisms"]] == [
        MC.ESTABLISHED, MC.EMERGING]
    assert got["capped_by_causal_ceiling"] == ()
    assert got["incoherent_pairs"] == 0
    for row in got["mechanisms"]:
        assert "maturity_uncapped" not in row
        assert "capped_by" not in row


def test_only_the_breaching_family_is_capped():
    got = CK.cap_mechanism_summary(
        _summary(demand_strengthening=(MC.ESTABLISHED, 19, 1, 0.95),
                 other_rule=(MC.ESTABLISHED, 9, 0, 0.9)),
        (_breach("demand_strengthening"),))
    by_key = {m["mechanism"]: m for m in got["mechanisms"]}
    assert by_key["demand_strengthening"]["maturity"] == MC.CONTESTED
    assert by_key["other_rule"]["maturity"] == MC.ESTABLISHED
    assert got["capped_by_causal_ceiling"] == ("demand_strengthening",)


def test_a_belief_level_incoherence_does_not_cap_a_mechanism():
    """Only the MECHANISM_ABOVE_ITS_CAUSAL_CEILING kind caps a mechanism."""
    belief_breach = CK.Incoherence(
        kind="BELIEF_ABOVE_ITS_MECHANISM_CEILING",
        family="demand_weakening", subject="johnson_johnson",
        upper_layer="mechanism_calibration", upper_state=MC.FAILING,
        lower_layer="belief_maturity", lower_state=BM.SUPPORTED,
        permitted=BM.WEAKENING, why="one belief cannot carry the rule")
    got = CK.cap_mechanism_summary(
        _summary(demand_weakening=(MC.FAILING, 1, 6, 0.14)),
        (belief_breach,))
    row, = got["mechanisms"]
    assert row["maturity"] == MC.FAILING          # unchanged
    assert "maturity_uncapped" not in row
    # but it is still REPORTED, because it is still a real finding
    assert got["incoherent_pairs"] == 1
    assert got["incoherences"][0]["subject"] == "johnson_johnson"


# ===========================================================================
# Every incoherence stays visible
# ===========================================================================
def test_the_contradiction_is_reported_not_swallowed():
    got = CK.cap_mechanism_summary(
        _summary(demand_strengthening=(MC.ESTABLISHED, 19, 1, 0.95)),
        (_breach("demand_strengthening"),))
    assert got["incoherent_pairs"] == 1
    kinds = {i["kind"] for i in got["incoherences"]}
    assert kinds == {"MECHANISM_ABOVE_ITS_CAUSAL_CEILING"}


def test_the_input_summary_is_not_mutated():
    """Append-only discipline: the producer's own object is left alone."""
    summary = _summary(demand_strengthening=(MC.ESTABLISHED, 19, 1, 0.95))
    before = summary["mechanisms"][0]["maturity"]
    CK.cap_mechanism_summary(summary, (_breach("demand_strengthening"),))
    assert summary["mechanisms"][0]["maturity"] == before
    assert "maturity_uncapped" not in summary["mechanisms"][0]


# ===========================================================================
# The ceiling table itself
# ===========================================================================
@pytest.mark.parametrize("causal,permitted", [
    (CC.CONTESTED, MC.CONTESTED),
    (CC.SUPPORTED, MC.ESTABLISHED),
    (CC.REPEATEDLY_SUPPORTED, MC.ESTABLISHED),
    (CC.EMERGING, MC.ESTABLISHED),
    (CC.UNMEASURABLE, MC.ESTABLISHED),
])
def test_only_a_contested_causal_family_lowers_the_ceiling(causal, permitted):
    """An unmeasured causal family is not evidence against the rule."""
    assert CK._CAUSAL_CAP[causal] == permitted


# ===========================================================================
# WIRED, not merely importable -- the defect was an unimported module
# ===========================================================================
def test_learning_health_actually_applies_the_cap(tmp_path):
    """Guards the regression that originally shipped: a correct, unused cap."""
    import inspect
    from intent_engine.market import learning_health as LH
    source = inspect.getsource(LH.assess)
    assert "cap_mechanism_summary" in source, (
        "learning_health must publish through the cap; publishing "
        "MC.summarise() directly is the defect this replaced")
    # and the publication line must not ALSO assign the uncapped summary
    assert "health.mechanisms = MC.summarise(" not in source


def test_some_module_under_src_imports_calibration_consistency():
    """The original defect was that nothing did."""
    import pathlib
    src = pathlib.Path(CK.__file__).parent
    importers = [p.name for p in src.glob("*.py")
                 if p.name != "calibration_consistency.py"
                 and "calibration_consistency" in p.read_text()]
    assert importers, ("calibration_consistency has no consumer under src/; "
                       "a ceiling nothing applies is not a ceiling")
