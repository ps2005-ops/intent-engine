"""The research programme: episodes, the founder gate, and the dashboard.

These cover the three surfaces that consume the collective layer. The
property each one is pinned against is the same: an untested construct must
not be able to reach a decision, and an absence must be legible as a decision
rather than as a blank.
"""
from __future__ import annotations

import pathlib

import pytest

from intent_engine.econ import (
    collective as CO, construct as CK, dashboard as DB, episodes as EP,
    founder_view as FV, incremental as inc, proxies as PX, series as SER,
    store as ST, transmission_seed as TS, vocabulary as V,
)


# =============================================================================
# Sections 19-20, 40-41: the historical programme
# =============================================================================

def test_no_construct_can_only_be_tested_on_the_holdout():
    """Otherwise testing it at all consumes the holdout."""
    EP.assert_partition_discipline()


def test_the_partition_guard_can_actually_fire():
    """Positive control for the assertion above.

    The production episode list satisfies the guard by construction, so
    calling it there proves only that it does not crash. This passes a set
    that violates the rule and requires the refusal -- without it, deleting
    the guard's body would leave the suite green."""
    violating = [e for e in EP.EPISODES
                 if "perceived_control" not in e.constructs
                 or e.partition == EP.HOLDOUT]
    assert any("perceived_control" in e.constructs for e in violating), (
        "the fixture must still contain the construct, or it tests nothing")
    with pytest.raises(V.EconError) as exc:
        EP.assert_partition_discipline(violating)
    assert "perceived_control" in str(exc.value)


def test_the_holdout_is_not_empty():
    assert EP.holdout(), "a partition scheme with no holdout is not one"
    assert EP.validation()
    assert EP.training()


def test_every_episode_can_embarrass_the_behavioural_account():
    for e in EP.EPISODES:
        assert e.falsifier.strip(), f"{e.key} cannot fail"
        assert e.consensus.strip(), f"{e.key} states no consensus to beat"


def test_there_is_at_least_one_negative_case():
    """A programme with no episode where the answer should be NO cannot
    distinguish a real signal from a flexible one."""
    negatives = EP.negative_cases()
    assert negatives, "every episode names constructs; nothing can disconfirm"
    for e in negatives:
        assert not e.constructs


def test_episodes_span_multiple_regimes():
    assert len(EP.regimes()) >= 4, (
        "a construct validated across one regime is a regime artefact, and "
        "the episode set must make that testable")


def test_a_construct_is_only_creditable_for_episodes_that_name_it():
    """The flattering error: run a construct against every episode, find it
    fits somewhere, report that it explains history."""
    for e in EP.testable("institutional_trust"):
        assert "institutional_trust" in e.constructs


def test_an_episode_naming_an_undeclared_construct_is_refused():
    with pytest.raises(V.EconError):
        EP.Episode(key="k", label="l", regime="R", start="2000-01-01",
                   end="2001-01-01", partition=EP.TRAINING,
                   consensus="c", behavioural_alternative="a",
                   constructs=("vibes",), falsifier="f")


def test_an_episode_with_no_falsifier_is_refused():
    with pytest.raises(V.EconError):
        EP.Episode(key="k", label="l", regime="R", start="2000-01-01",
                   end="2001-01-01", partition=EP.TRAINING,
                   consensus="c", behavioural_alternative="a",
                   constructs=(), falsifier="")


# =============================================================================
# Sections 13, 31, 50: the founder gate
# =============================================================================

def _state(dims):
    pop = CO.population("US_households", V.HOUSEHOLD)
    return CO.build(population=pop, as_of="2026-08-27", dimensions=[
        CO.DimensionEstimate(dimension=d, posterior_mean=m, uncertainty=u,
                             prior_mean=p, evidence=("n1",),
                             promotion_state=s)
        for d, m, u, p, s in dims])


def _register(pairs):
    return [CK.Construct(dimension=d, state=s, proposed_by="t")
            for d, s in pairs]


def test_an_untested_construct_never_reaches_a_founder_brief():
    state = _state([("financial_anxiety", 0.8, 0.05, 0.6, V.OBSERVED_C)])
    v = FV.for_company(company_id="WMT", state=state,
                       registry=TS.registry(),
                       register=_register([("financial_anxiety",
                                            V.OBSERVED_C)]))
    assert not v["shown"]
    assert v["withheld"][0]["gate"] == FV.NOT_PROMOTED


def test_a_promoted_construct_with_no_channel_does_not_reach_the_company():
    """Section 13's closing line, pinned: the same conclusion must not be
    dumped into every company."""
    state = _state([("financial_anxiety", 0.8, 0.05, 0.6, V.PROMOTED)])
    reg = _register([("financial_anxiety", V.PROMOTED)])
    v = FV.for_company(company_id="SNOW", state=state,
                       registry=TS.registry(), register=reg)
    assert not v["shown"]
    assert {w["gate"] for w in v["withheld"]} == {FV.NO_CHANNEL}


def test_two_companies_get_different_sentences_for_the_same_construct():
    state = _state([("financial_anxiety", 0.8, 0.05, 0.6, V.PROMOTED)])
    reg = _register([("financial_anxiety", V.PROMOTED)])
    seen = {}
    for cid in ("WMT", "V", "JPM"):
        v = FV.for_company(company_id=cid, state=state,
                           registry=TS.registry(), register=reg)
        assert v["shown"], f"{cid} had a channel and got nothing"
        seen[cid] = v["shown"][0]["sentence"]
    assert len(set(seen.values())) == 3, (
        "three companies received the same sentence; that is the generic "
        f"psychology dump Section 13 forbids: {seen}")
    # Differing sentences are NOT sufficient. An earlier version of this test
    # stopped here, and passed when the channel was replaced by the word
    # "economy" for every company -- the sentences still differed, because
    # they name different observables. What Section 13 requires is that each
    # company's OWN channel is in its OWN sentence.
    reg = TS.registry()
    for cid, sentence in seen.items():
        channels = [e.channel for e in reg.exposures(cid, enforce=False)
                    if e.construct == "financial_anxiety"]
        assert channels, f"{cid} has no declared anxiety channel to check"
        assert any(ch in sentence for ch in channels), (
            f"{cid}'s sentence does not contain its own channel "
            f"{channels}; a company-specific reading that names a generic "
            f"channel is the dump wearing a different observable: "
            f"{sentence}")


def test_every_shown_reading_carries_a_company_specific_falsifier():
    state = _state([("financial_anxiety", 0.8, 0.05, 0.6, V.PROMOTED)])
    reg = _register([("financial_anxiety", V.PROMOTED)])
    v = FV.for_company(company_id="WMT", state=state,
                       registry=TS.registry(), register=reg)
    for s in v["shown"]:
        assert s["observable"] in s["falsifier"]
        assert s["channel"]
        assert s["lag_days"] is not None


def test_the_empty_reason_names_the_dominant_gate_not_the_first_one():
    """A company blocked by two missing channels and one untested construct
    has a COVERAGE problem, not a research problem. Naming the minority gate
    sends the reader to do the wrong work."""
    state = _state([("financial_anxiety", 0.8, 0.05, 0.6, V.PROMOTED),
                    ("risk_appetite", 0.4, 0.05, 0.6, V.PROMOTED),
                    ("stress", 0.7, 0.05, 0.5, V.OBSERVED_C)])
    reg = _register([("financial_anxiety", V.PROMOTED),
                     ("risk_appetite", V.PROMOTED),
                     ("stress", V.OBSERVED_C)])
    v = FV.for_company(company_id="CAT", state=state,
                       registry=TS.registry(), register=reg)
    assert not v["shown"]
    assert "exposure map" in v["empty_reason"], (
        f"expected the channel gap to be named first; got: "
        f"{v['empty_reason']}")
    assert "NOT_PROMOTED" in v["empty_reason"], (
        "the minority gate must still be reported, not dropped")


def test_a_private_estimate_cannot_reach_the_shared_founder_view():
    from dataclasses import replace
    state = replace(_state([("financial_anxiety", 0.8, 0.05, 0.6, V.PROMOTED)]),
                    visibility=V.TENANT_PRIVATE)
    with pytest.raises(V.PrivacyViolation):
        FV.for_company(company_id="WMT", state=state,
                       registry=TS.registry(),
                       register=_register([("financial_anxiety",
                                            V.PROMOTED)]))


def test_a_wide_reading_is_withheld_as_unusable_not_shown_hedged():
    state = _state([("financial_anxiety", 0.8, 0.45, 0.6, V.PROMOTED)])
    v = FV.for_company(company_id="WMT", state=state,
                       registry=TS.registry(),
                       register=_register([("financial_anxiety",
                                            V.PROMOTED)]))
    assert not v["shown"]
    assert v["withheld"][0]["gate"] == FV.NOT_USABLE


# =============================================================================
# Section 49: the dashboard
# =============================================================================

def test_the_dashboard_distinguishes_never_run_from_ran_and_found_nothing(
        tmp_path):
    payload = DB.build(tmp_path)
    assert payload["available"]
    assert not payload["has_run"], (
        "an engine that has never run must be distinguishable from one that "
        "ran and measured nothing")
    assert "starved" in payload["verdict"] or "Nothing is being measured" in \
        payload["verdict"]


def test_the_dashboard_reports_measured_promoted_and_retired_together(
        tmp_path):
    pop = CO.population("US_households", V.HOUSEHOLD)
    est = CO.build(population=pop, as_of="2026-08-27", dimensions=[
        CO.DimensionEstimate(dimension="perceived_control",
                             posterior_mean=0.62, uncertainty=0.09,
                             prior_mean=0.71, evidence=("n1",),
                             promotion_state=V.OBSERVED_C)])
    ST.append(tmp_path, "collective_state", est.as_dict(),
              written_at="2026-08-27")
    reg = [CK.observe(CK.propose("perceived_control", proposed_by="s"),
                      proxy="quits", at="d"),
           CK.retire(CK.propose("anger", proposed_by="t"), at="d",
                     reason="no incremental value")]
    ST.append_many(tmp_path, "construct", [c.as_dict() for c in reg],
                   written_at="2026-08-27")

    p = DB.build(tmp_path, as_of="2026-08-27")
    h = p["headline"]
    assert h["measured"] == 1
    assert h["promoted"] == 0
    assert h["retired"] == 1
    assert h["vocabulary"] == len(V.COLLECTIVE_DIMENSIONS)
    assert h["measurable_today"] <= h["with_a_proxy"] <= h["vocabulary"]
    assert p["retired"][0]["reason"], "a retirement with no reason"


def test_the_dashboard_says_no_delta_has_been_measured_when_none_has(tmp_path):
    p = DB.build(tmp_path)
    inc_block = p["incremental_value"]
    assert inc_block["status"] == "NOT_YET_MEASURED"
    assert inc_block["incremental_delta"] is None, (
        "a delta of 0.0 would read as 'measured, no effect'; None is the "
        "only honest value before any comparison has run")
    assert "Section 18" in inc_block["reason"]


def test_the_dashboard_never_renders_a_headcount_sentence(tmp_path):
    pop = CO.population("US_households", V.HOUSEHOLD)
    est = CO.build(population=pop, as_of="d", dimensions=[
        CO.DimensionEstimate(dimension="financial_anxiety",
                             posterior_mean=0.73, uncertainty=0.06,
                             prior_mean=0.6, evidence=("n",))])
    ST.append(tmp_path, "collective_state", est.as_dict(), written_at="d")
    p = DB.build(tmp_path)
    for pop_block in p["populations"]:
        for r in pop_block["readings"]:
            CO.assert_renderable(r["sentence"])


def test_a_measured_but_unusable_reading_is_reported_not_dropped(tmp_path):
    pop = CO.population("US_households", V.HOUSEHOLD)
    est = CO.build(population=pop, as_of="d", dimensions=[
        CO.DimensionEstimate(dimension="stress", posterior_mean=0.6,
                             uncertainty=0.45, evidence=("n",))])
    ST.append(tmp_path, "collective_state", est.as_dict(), written_at="d")
    p = DB.build(tmp_path)
    block = p["populations"][0]
    assert block["readings"] == []
    assert "stress" in block["measured_but_unusable"], (
        "a too-uncertain reading and no reading at all are different states")


# =============================================================================
# Section 27: never fabricate unavailable data
# =============================================================================

def test_every_unavailable_behavioural_series_says_why():
    for s in SER.BEHAVIOURAL:
        if s.availability in (SER.UNAVAILABLE, SER.KEYED):
            assert s.reason.strip(), (
                f"{s.key} is {s.availability} with no reason; an unexplained "
                "gap is indistinguishable from a series nobody thought of")


def test_an_unreadable_series_with_no_reason_is_refused():
    """The test above reads a fully-populated registry, so it stays green
    with the requirement deleted. This one exercises the guard."""
    with pytest.raises(V.EconError):
        SER.SeriesSpec(key="k", kind="quits", label="l", unit="%",
                       frequency="monthly", availability=SER.UNAVAILABLE,
                       reason="")


def test_a_derivable_series_must_state_its_rule_and_inputs():
    with pytest.raises(V.EconError):
        SER.SeriesSpec(key="k", kind="quits", label="l", unit="%",
                       frequency="monthly", availability=SER.DERIVABLE)


def test_behavioural_coverage_does_not_flatter_itself():
    """The measurable count must be derived from series this engine can
    actually read, not from the proxies it happens to have declared."""
    c = SER.behavioural_coverage()
    assert len(c["dimensions_measurable_now"]) <= len(
        PX.covered_dimensions())
    assert c["dimensions_with_no_proxy_at_all"], (
        "this assertion is vacuous if every construct has a proxy")
    overlap = (set(c["dimensions_measurable_now"])
               & set(c["dimensions_with_no_proxy_at_all"]))
    assert not overlap, f"{overlap} is both measurable and unproxied"
