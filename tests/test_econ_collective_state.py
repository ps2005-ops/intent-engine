"""The collective-human layer, tested where it can actually be wrong.

WHAT THESE TESTS ARE FOR
------------------------
Not "does the dataclass hold values". Every test below pins a property that
this specification names as a failure mode, and each one was written so that
removing the guard makes it fail. The ones that matter most:

  - the gate can conclude NO (a construct that predicts nothing is retired)
  - the gate can conclude YES (or the whole layer is unfalsifiable pessimism)
  - a psychological posterior cannot reach a decision surface untested
  - a posterior cannot be rendered as a headcount
  - the public core cannot build an individual's state
"""
from __future__ import annotations

import random

import pytest

from intent_engine.econ import (
    bayes, bleed, collective, construct as ck, estimator, incremental as inc,
    proxies, transmission as tx, transmission_seed, vocabulary as V,
)


# =============================================================================
# Section 3: the two vocabularies must not collapse into each other
# =============================================================================

def test_economic_and_collective_vocabularies_are_disjoint():
    """credit stress is not fear, and the spelling is what enforces it.

    The intersection is computed HERE, from the two source tuples, rather
    than by calling the helper. The earlier version asserted the helper
    returned empty, which a helper hardcoded to return empty also satisfies:
    the test was checking the reporter instead of the property."""
    economic = {k for kinds in V.NODE_KINDS.values() for k in kinds}
    collisions = economic & set(V.COLLECTIVE_DIMENSIONS)
    assert collisions == set(), (
        f"{sorted(collisions)} name both an economic quantity and a "
        "collective construct. One construct standing in for two different "
        "things means the incremental-value test compares a model to itself.")
    assert V.collective_dimension_collisions() == collisions, (
        "the helper disagrees with the vocabulary it reports on")


def test_behavioral_is_its_own_node_class():
    assert V.BEHAVIORAL in V.NODE_CLASSES
    assert V.NODE_KINDS[V.BEHAVIORAL], "the class exists with no kinds in it"
    macro = set(V.NODE_KINDS[V.MACRO])
    behav = set(V.NODE_KINDS[V.BEHAVIORAL])
    assert not (macro & behav), (
        "a kind filed as both macro and behavioural loses the ability to ask "
        "whether people knew something the aggregates had not yet shown")


# =============================================================================
# Section 6 / 52: every state names a population, and never an individual
# =============================================================================

def test_public_core_cannot_build_an_individual_state():
    with pytest.raises(V.CollectiveStateViolation):
        collective.population("some_person", V.INDIVIDUAL)


def test_a_population_must_name_a_scale():
    with pytest.raises(V.EconError):
        collective.population("people", "EVERYONE")


def test_two_cohorts_are_two_different_objects():
    a = collective.population("homebuyers", V.CONSUMER_COHORT,
                              cohort="first_time")
    b = collective.population("homebuyers", V.CONSUMER_COHORT,
                              cohort="repeat")
    assert a.key != b.key, (
        "Section 6: fear among first-time buyers is not fear among repeat "
        "buyers, and if their keys collide the second estimate overwrites "
        "the first")


# =============================================================================
# Section 5: the rendering rule is code, not a style guide
# =============================================================================

def test_a_posterior_may_not_be_rendered_as_a_headcount():
    with pytest.raises(V.UnsupportedInference):
        collective.assert_renderable("Americans are 73% afraid")


def test_narrate_never_produces_a_forbidden_sentence():
    pop = collective.population("US_households", V.HOUSEHOLD)
    for mean in (0.05, 0.25, 0.5, 0.73, 0.99):
        for prior in (None, 0.1, 0.5, 0.9):
            est = collective.DimensionEstimate(
                dimension="financial_anxiety", posterior_mean=mean,
                uncertainty=0.08, prior_mean=prior, evidence=("n1",))
            collective.assert_renderable(collective.narrate(est, pop))


def test_an_estimate_with_a_posterior_must_name_evidence():
    with pytest.raises(V.CollectiveStateViolation):
        collective.DimensionEstimate(dimension="hope", posterior_mean=0.6,
                                     uncertainty=0.1, evidence=())


def test_an_unmeasured_dimension_is_unusable_not_neutral():
    """0.5 would render as a real middling reading. It is not one."""
    u = collective.unmeasured("hope", "no proxy fired")
    assert u.posterior_mean is None
    assert not u.usable


# =============================================================================
# Section 10: arrival is not learning
# =============================================================================

def test_the_same_node_twice_is_duplicate_not_learning():
    est = collective.unmeasured("financial_anxiety", "none")
    o = bayes.Observation(node_id="n1", value=0.7, noise=0.1,
                          as_of="2026-01-01")
    est = bayes.apply(est, bayes.update(est, [o], at="2026-01-01"))
    again = bayes.update(est, [o], at="2026-01-02")
    assert again.effect == V.DUPLICATE_EVIDENCE
    assert not again.informative
    assert bayes.summarise([again])["arrived_without_informing"] == 1


def test_a_surprising_observation_is_a_contradiction_not_a_confirmation():
    est = collective.DimensionEstimate(
        dimension="financial_anxiety", posterior_mean=0.75, uncertainty=0.05,
        evidence=("prior",))
    far = bayes.Observation(node_id="n9", value=0.15, noise=0.05,
                            as_of="2026-01-02")
    upd = bayes.update(est, [far], at="2026-01-02")
    assert upd.effect == V.CONTRADICTION
    assert "n9" in bayes.apply(est, upd).contradictory_evidence, (
        "Section 5 requires contradictory_evidence[]; a posterior that has "
        "quietly absorbed what disagreed with it cannot be audited")


def test_a_precise_instrument_moves_the_posterior_more_than_a_vague_one():
    est = collective.DimensionEstimate(
        dimension="risk_appetite", posterior_mean=0.5, uncertainty=0.1,
        evidence=("p",))
    tight = bayes.update(est, [bayes.Observation(
        node_id="tight", value=0.9, noise=0.02, as_of="d")], at="d")
    loose = bayes.update(est, [bayes.Observation(
        node_id="loose", value=0.9, noise=0.30, as_of="d")], at="d")
    assert abs(tight.delta) > abs(loose.delta)
    assert tight.posterior_uncertainty < loose.posterior_uncertainty


def test_uncertainty_never_grows_from_evidence_arriving():
    est = collective.DimensionEstimate(
        dimension="stress", posterior_mean=0.5, uncertainty=0.2,
        evidence=("p",))
    upd = bayes.update(est, [bayes.Observation(
        node_id="x", value=0.4, noise=0.2, as_of="d")], at="d")
    assert upd.posterior_uncertainty <= est.uncertainty


# =============================================================================
# Section 18 / 56: THE GATE, in both directions
# =============================================================================

def _episode(n, informative, regime, seed, dim="financial_anxiety"):
    rng = random.Random(seed)
    base, aug, outs = [], [], []
    for i in range(n):
        latent = rng.random()
        occurred = rng.random() < latent
        b = min(0.95, max(0.05, latent + rng.gauss(0, 0.25)))
        extra = (latent - b) * 0.6 if informative else rng.gauss(0, 0.25)
        a = min(0.95, max(0.05, b + extra))
        tid = f"{dim}/{regime}/t{i}"
        cut, occ = f"2020-01-{(i % 27) + 1:02d}", f"2020-06-{(i % 27) + 1:02d}"
        base.append(inc.Forecast(target_id=tid, probability=b,
                                 information_cutoff=cut, horizon_days=30,
                                 model="BASE", regime=regime))
        aug.append(inc.Forecast(target_id=tid, probability=a,
                                information_cutoff=cut, horizon_days=30,
                                model="BASE+CS", regime=regime))
        outs.append(inc.Outcome(target_id=tid, occurred=occurred,
                                occurred_at=occ, published_at=occ,
                                regime=regime))
    return base, aug, outs


def test_the_gate_says_no_to_a_construct_that_predicts_nothing():
    """Section 42's requirement, as a test: the engine must be able to
    conclude that a construct adds no incremental predictive value."""
    b, a, o = _episode(400, informative=False, regime="ALL", seed=7)
    c = inc.compare(name="noise", dimension="anger", population="US_households",
                    base=b, augmented=a, outcomes=o)
    assert c.verdict in (inc.NO_IMPROVEMENT, inc.NOT_ROBUST)
    assert not c.robust
    assert "did NOT improve" in c.statement() or "includes\nzero" in \
        c.statement() or "includes zero" in c.statement()


def test_the_gate_says_yes_to_a_construct_that_carries_signal():
    """The negative control above is worthless unless this passes too: a
    test that can only ever say no is not measuring anything."""
    b, a, o = _episode(400, informative=True, regime="ALL", seed=8)
    c = inc.compare(name="real", dimension="financial_anxiety",
                    population="US_households", base=b, augmented=a,
                    outcomes=o)
    assert c.verdict == inc.IMPROVEMENT
    assert c.delta > 0 and c.ci_low > 0


def test_a_positive_point_estimate_with_a_straddling_interval_is_not_value():
    """Deterministic, because the earlier version of this test asserted only
    inside `if verdict == NOT_ROBUST` -- which meant a build where the branch
    never fired passed without checking anything. Constructed so the mean
    difference is positive and driven by two observations, which is exactly
    the shape a bootstrap interval must refuse to call an effect."""
    base, aug, outs = [], [], []
    for i in range(60):
        # 58 targets where the two models are identical, one big win for the
        # augmented model and one smaller loss. Mean favours it; the interval
        # cannot, because almost every resample contains neither point.
        if i == 0:
            pb, pa, occurred = 0.95, 0.05, False
        elif i == 1:
            pb, pa, occurred = 0.20, 0.60, False
        else:
            pb = pa = 0.5
            occurred = bool(i % 2)
        base.append(inc.Forecast(target_id=f"s{i}", probability=pb,
                                 information_cutoff="2020-01-01",
                                 horizon_days=30, model="BASE"))
        aug.append(inc.Forecast(target_id=f"s{i}", probability=pa,
                                information_cutoff="2020-01-01",
                                horizon_days=30, model="BASE+CS"))
        outs.append(inc.Outcome(target_id=f"s{i}", occurred=occurred,
                                occurred_at="2020-06-01",
                                published_at="2020-06-01"))
    c = inc.compare(name="weak", dimension="hope", population="p", base=base,
                    augmented=aug, outcomes=outs)
    assert c.delta > 0, "the fixture must favour the augmented model on mean"
    assert c.verdict == inc.NOT_ROBUST, (
        f"a positive delta driven by two of sixty observations must not be "
        f"called an improvement; got {c.verdict}")
    assert c.ci_low <= 0 <= c.ci_high
    assert not c.robust


def test_a_small_sample_is_not_a_weak_result_it_is_no_result():
    b, a, o = _episode(12, informative=True, regime="ALL", seed=9)
    c = inc.compare(name="tiny", dimension="hope", population="p", base=b,
                    augmented=a, outcomes=o)
    assert c.verdict == inc.INSUFFICIENT_SAMPLE
    assert not c.robust


def test_fdr_suppresses_a_family_of_marginal_wins():
    """Every comparison here has verdict IMPROVEMENT, so nothing but the FDR
    correction can stop them.

    The earlier version of this test used pure-noise episodes, whose verdicts
    were NO_IMPROVEMENT anyway -- so disabling the correction entirely left
    the test green. It was checking the verdict, not the correction."""
    fam = [inc.Comparison(
        name=f"m{i}", dimension="stress", regime=f"R{i}", horizon_days=30,
        population="p", n_paired=200, base_score=0.25, augmented_score=0.245,
        delta=0.005, ci_low=0.0001, ci_high=0.01, p_value=0.5,
        verdict=inc.IMPROVEMENT) for i in range(20)]
    adjusted = inc.adjust(fam)
    assert all(c.verdict == inc.IMPROVEMENT for c in adjusted)
    assert sum(1 for c in adjusted if c.robust) == 0, (
        "twenty marginal wins at p=0.5 must not survive Benjamini-Hochberg "
        "at q=0.10; if they do, the correction is not being applied")


def test_fdr_still_admits_a_genuinely_strong_result():
    """The suppression test above is worthless if FDR rejects everything."""
    fam = [inc.Comparison(
        name="strong", dimension="financial_anxiety", regime="R", 
        horizon_days=30, population="p", n_paired=400, base_score=0.25,
        augmented_score=0.20, delta=0.05, ci_low=0.02, ci_high=0.08,
        p_value=0.0005, verdict=inc.IMPROVEMENT)]
    assert inc.adjust(fam)[0].robust


def test_hindsight_is_refused_not_scored():
    b, a, o = _episode(50, informative=True, regime="ALL", seed=11)
    leaky = [inc.Forecast(target_id=f.target_id, probability=f.probability,
                          information_cutoff="2021-12-31", horizon_days=30,
                          model="LEAK") for f in b]
    with pytest.raises(inc.HindsightLeak):
        inc.compare(name="leak", dimension="hope", population="p",
                    base=leaky, augmented=a, outcomes=o)


def test_delta_sign_convention_favours_the_better_model():
    """The easiest thing in this codebase to get backwards, pinned."""
    b, a, o = _episode(200, informative=True, regime="ALL", seed=12)
    c = inc.compare(name="s", dimension="financial_anxiety", population="p",
                    base=b, augmented=a, outcomes=o)
    assert c.augmented_score < c.base_score
    assert c.delta > 0, "positive delta must mean the collective model won"


# =============================================================================
# Section 42: the lifecycle, including the deletion
# =============================================================================

def test_a_construct_cannot_jump_to_promoted():
    c = ck.propose("hope", proposed_by="a-framework")
    with pytest.raises(ck.ConstructRefused):
        ck.promote(c, at="2026-01-01")


def test_the_state_check_is_not_redundant_with_the_regime_count():
    """A construct with enough passing regimes but the wrong STATE.

    The earlier version of this test used a CANDIDATE with zero regimes,
    which the regime count would have refused anyway -- so deleting the state
    check entirely left the test green. This fixture can only be refused by
    the state check."""
    passes = tuple(
        ck.Trial(at="d", regime=r, horizon_days=30, population="p",
                 n_paired=200, delta=0.02, verdict=inc.IMPROVEMENT,
                 survived_fdr=True)
        for r in ("EXPANSION", "CREDIT_CRISIS"))
    stuck = ck.Construct(dimension="risk_appetite", state=V.TESTED,
                         proposed_by="t", trials=passes)
    assert len(stuck.regimes_passed) >= ck.PASSES_FOR_PROMOTION
    with pytest.raises(ck.ConstructRefused) as e:
        ck.promote(stuck, at="d")
    # The transition table refuses this too, so the explicit check in
    # promote() is redundant for SAFETY. What it buys is the DIAGNOSTIC: the
    # table's message explains the shape of the state machine, while
    # promote()'s explains what promotion is FOR -- letting a psychological
    # variable into the causal graph that founder surfaces read.
    #
    # Asserting "REPLICATED" would not distinguish them: the table lists
    # REPLICATED among the legal moves, so that substring appears in both.
    # The consequence clause appears in only one.
    msg = str(e.value)
    assert "causal graph" in msg, (
        "the refusal must say what promotion would have granted, not only "
        f"that the transition is illegal; got: {msg}")


def test_the_promotion_refusal_is_the_one_promote_writes():
    """Positive control for the assertion above.

    Without this, `"causal graph" in msg` is a spelling test that would also
    pass if the phrase moved into the transition table's message."""
    import inspect
    src = inspect.getsource(ck.promote)
    assert "causal graph" in src
    assert "causal graph" not in inspect.getsource(ck._move)


def test_promotion_requires_two_distinct_regimes():
    c = ck.observe(ck.propose("financial_anxiety", proposed_by="f"),
                   proxy="p", at="d")
    same = ck.Trial(at="d", regime="EXPANSION", horizon_days=30,
                    population="p", n_paired=200, delta=0.02,
                    verdict=inc.IMPROVEMENT, survived_fdr=True)
    c = ck.record(c, same)
    c = ck.record(c, same)
    assert c.state == V.TESTED, (
        "passing twice in the SAME regime is one finding observed twice; "
        "replication means a different regime")
    with pytest.raises(ck.ConstructRefused):
        ck.promote(c, at="d")


def test_a_failing_construct_is_retired_and_removed():
    reg = [ck.observe(ck.propose("anger", proposed_by="a-taxonomy"),
                      proxy="public_language", at="d")]
    fails = [inc.Comparison(
        name=f"f{i}", dimension="anger", regime=r, horizon_days=30,
        population="p", n_paired=200, base_score=0.2, augmented_score=0.22,
        delta=-0.02, ci_low=-0.04, ci_high=-0.01, p_value=0.01,
        verdict=inc.NO_IMPROVEMENT, fdr_adjusted=True, survives_fdr=False)
        for i, r in enumerate(("EXPANSION", "CREDIT_CRISIS"))]
    out = ck.apply_report(reg, fails, at="d")
    assert ck.retired_dimensions(out) == ["anger"]
    assert "anger" not in ck.active_dimensions(out)
    assert not out[0].usable_in_causal_graph


def test_a_retired_construct_is_not_estimated_at_all():
    """Filtering at the surface is not removal."""
    reg = [ck.retire(ck.propose("anger", proposed_by="t"), at="d",
                     reason="no incremental value")]
    node = _behavioural_node("public_language", 0.9)
    est, ups, diag = estimator.estimate(
        population=collective.population("US_households", V.HOUSEHOLD),
        as_of="2026-08-27", nodes=[node], register=reg)
    assert "anger" in diag["skipped_retired"]
    assert "anger" not in est.dimensions
    assert not any(u.dimension == "anger" for u in ups)


def test_a_revived_construct_comes_back_as_a_candidate():
    c = ck.retire(ck.propose("hope", proposed_by="t"), at="d", reason="none")
    back = ck.revive(c, at="d2", reason="a new proxy exists")
    assert back.state == V.CANDIDATE
    assert not back.usable_in_causal_graph


# =============================================================================
# Sections 13-15: transmission, and the gate on it
# =============================================================================

class _Prov:
    publisher = "test"


class _Node:
    def __init__(self, kind, value):
        self.node_class = V.BEHAVIORAL
        self.kind = kind
        self.value = value
        self.node_id = f"beh/{kind}"
        self.occurred_at = "2026-08-01"
        self.available_at = "2026-08-02"
        self.provenance = _Prov()


def _behavioural_node(kind, value):
    return _Node(kind, value)


def test_transmission_is_bidirectional():
    s = transmission_seed.registry().summarise(register=[])
    assert s["links_by_crossing"][tx.PSYCH_TO_ECON] > 0
    assert s["links_by_crossing"][tx.ECON_TO_PSYCH] > 0
    assert s["bidirectional"], (
        "Section 14: without the reverse arrow, Section 15's reflexive loops "
        "are undetectable by construction")


def test_no_seeded_chain_claims_causation():
    """The ladder is decorative the moment a seed file sets level 3."""
    for ch in transmission_seed.registry().chains(enforce=False):
        assert not ch.may_state_causation, (
            f"{ch.name} claims causal language it has not earned")
        assert "ASSOCIATED WITH" in ch.statement()


def test_an_untested_construct_cannot_reach_a_decision_surface():
    r = transmission_seed.registry()
    assert r.chains(register=[], enforce=True) == []
    refused = r.refused_chains(register=[])
    assert refused and all(x["blocked_by"] for x in refused), (
        "the gate must name WHICH construct blocks each chain; a wall with "
        "no work list behind it is just a wall")


def test_a_promoted_construct_opens_exactly_its_own_chains():
    r = transmission_seed.registry()
    promoted = ck.Construct(dimension="perceived_control", state=V.PROMOTED,
                            proposed_by="t")
    usable = r.chains(register=[promoted], enforce=True)
    assert usable, "promotion opened nothing"
    for ch in usable:
        assert set(ch.constructs) <= {"perceived_control"}


def test_a_company_exposure_must_name_its_own_channel():
    with pytest.raises(V.EconError):
        tx.Exposure(company_id="X", construct="financial_anxiety", channel="",
                    sign="UP", observable="revenue")


def test_exposures_are_not_the_same_conclusion_dumped_everywhere():
    r = transmission_seed.registry()
    channels = {}
    for cid in r.companies():
        for e in r.exposures(cid, enforce=False):
            channels.setdefault(e.construct, set()).add(e.channel)
    for cdim, chans in channels.items():
        if len(chans) > 1:
            assert len(chans) > 1
    anxiety = {e.channel for cid in r.companies()
               for e in r.exposures(cid, enforce=False)
               if e.construct == "financial_anxiety"}
    assert len(anxiety) >= 3, (
        "Section 13: the same psychological conclusion reaching every "
        "company through the same words is the generic dump it forbids")


def test_a_chain_is_only_as_causal_as_its_weakest_link():
    ch = transmission_seed.registry()._chains["wealth_reflexivity_upswing"]
    assert ch.weakest.edge.evidence_level == min(
        l.edge.evidence_level for l in ch.links)
    assert not ch.may_state_causation


def test_a_broken_chain_is_refused():
    with pytest.raises(V.EconError):
        tx.Chain(name="broken", links=(
            tx.link(cause="financial_anxiety", effect="consumer_demand",
                    sign="DOWN", mechanism="m", evidence_level=1,
                    evidence="e", falsifier="f", lag_days=30),
            tx.link(cause="inventory", effect="margin", sign="UP",
                    mechanism="m", evidence_level=1, evidence="e",
                    falsifier="f", lag_days=30)))


# =============================================================================
# Sections 21-22: bleeds
# =============================================================================

def test_a_bleed_cannot_blame_something_nobody_measures():
    with pytest.raises(V.EconError):
        bleed.CausalBleed(
            bleed_id="b", mechanism="m", expected_transition="a->b",
            source_state="a", target_state="b", observed_behavior="flat",
            expected_probability=0.7, observed_probability=0.2,
            candidate_interruption="vibes", falsifier="f", as_of="d")


def test_a_bleed_above_suspected_must_name_a_candidate():
    with pytest.raises(bleed.BleedRefused):
        bleed.CausalBleed(
            bleed_id="b", mechanism="m", expected_transition="a->b",
            source_state="a", target_state="b", observed_behavior="flat",
            expected_probability=0.7, observed_probability=0.2,
            candidate_interruption="", falsifier="f", as_of="d",
            level=bleed.CORROBORATED)


def test_a_mechanism_that_delivered_produces_no_bleed():
    ch = transmission_seed.registry()._chains["anxiety_defers_discretionary"]
    assert bleed.detect(chain=ch, expected_probability=0.70,
                        observed_probability=0.68, as_of="d") is None


def test_priority_is_a_product_so_uncontrollable_bleeds_sink():
    ch = transmission_seed.registry()._chains["rate_cuts_blocked_by_insecurity"]
    big = bleed.detect(chain=ch, expected_probability=0.8,
                       observed_probability=0.2, as_of="d",
                       candidate_interruption="financial_anxiety",
                       impact=0.9, controllability=0.9, confidence=0.6)
    stuck = bleed.detect(chain=ch, expected_probability=0.8,
                         observed_probability=0.2, as_of="d",
                         candidate_interruption="financial_anxiety",
                         impact=0.9, controllability=0.02, confidence=0.6)
    assert big.priority > stuck.priority * 10


def test_an_untested_construct_cannot_corroborate_a_bleed():
    ch = transmission_seed.registry()._chains["rate_cuts_blocked_by_insecurity"]
    b = bleed.detect(chain=ch, expected_probability=0.8,
                     observed_probability=0.2, as_of="d",
                     candidate_interruption="financial_anxiety")
    pop = collective.population("US_households", V.HOUSEHOLD)
    est = collective.build(population=pop, as_of="d", dimensions=[
        collective.DimensionEstimate(dimension="financial_anxiety",
                                     posterior_mean=0.8, uncertainty=0.05,
                                     prior_mean=0.6, evidence=("n",))])
    out = bleed.corroborate(b, state=est, register=[
        ck.Construct(dimension="financial_anxiety", state=V.CANDIDATE,
                     proposed_by="t")])
    assert out.level == bleed.CANDIDATE_NAMED
    assert "CANDIDATE" in out.note or "candidate" in out.note


def test_a_construct_moving_the_wrong_way_does_not_corroborate():
    ch = transmission_seed.registry()._chains["rate_cuts_blocked_by_insecurity"]
    b = bleed.detect(chain=ch, expected_probability=0.8,
                     observed_probability=0.2, as_of="d",
                     candidate_interruption="financial_anxiety")
    pop = collective.population("US_households", V.HOUSEHOLD)
    falling = collective.build(population=pop, as_of="d", dimensions=[
        collective.DimensionEstimate(dimension="financial_anxiety",
                                     posterior_mean=0.4, uncertainty=0.05,
                                     prior_mean=0.7, evidence=("n",))])
    out = bleed.corroborate(b, state=falling, register=[
        ck.Construct(dimension="financial_anxiety", state=V.PROMOTED,
                     proposed_by="t")])
    assert out.level == bleed.CANDIDATE_NAMED
    assert out.human_state_contribution == 0.0


# =============================================================================
# Sections 4-5: the producer
# =============================================================================

def test_every_proxy_states_why_it_loads_on_its_construct():
    for p in proxies.REGISTRY:
        assert p.rationale.strip(), f"{p.kind}->{p.dimension} has no rationale"
        assert p.noise > 0.0


def test_a_proxy_with_no_rationale_is_refused():
    """The test above reads the registry, which is fully populated -- so it
    stays green even with the requirement deleted. This one exercises the
    guard: an unexplained loading is an assumption wearing a number."""
    with pytest.raises(V.EconError):
        proxies.Proxy(kind="delinquency", dimension="financial_anxiety",
                      sign=proxies.POSITIVE, low=0.0, high=1.0, noise=0.1,
                      rationale="")


def test_a_proxy_with_a_zero_noise_instrument_is_refused():
    with pytest.raises(V.EconError):
        proxies.Proxy(kind="delinquency", dimension="financial_anxiety",
                      sign=proxies.POSITIVE, low=0.0, high=1.0, noise=0.0,
                      rationale="an exact instrument would pin the posterior")


def test_dimensions_with_no_proxy_are_reported_not_hidden():
    uncovered = proxies.uncovered_dimensions()
    assert uncovered, "this test is vacuous if every construct has a proxy"
    for d in uncovered:
        assert d in V.COLLECTIVE_DIMENSIONS


def test_a_contested_only_construct_gets_a_wider_posterior():
    pop = collective.population("US_households", V.HOUSEHOLD)
    contested, clean = None, None
    est_c, _, _ = estimator.estimate(
        population=pop, as_of="d",
        nodes=[_behavioural_node("saving_rate", 10.0)])
    est_k, _, _ = estimator.estimate(
        population=pop, as_of="d",
        nodes=[_behavioural_node("delinquency", 6.0)])
    a = est_c.dimension("financial_anxiety")
    b = est_k.dimension("financial_anxiety")
    assert a.uncertainty > b.uncertainty, (
        "a construct supported only by ambiguous instruments must not report "
        "the same precision as one supported by a discriminating instrument")


def test_the_estimator_places_readings_and_flags_clamping():
    pop = collective.population("US_households", V.HOUSEHOLD)
    est, ups, diag = estimator.estimate(
        population=pop, as_of="2026-08-27",
        nodes=[_behavioural_node("delinquency", 99.0)])
    assert diag["readings"]["clamped"] == 1, (
        "a series pinning the top of its declared range means the range is "
        "wrong, and silently saturating it hides that")


def test_estimating_many_populations_does_not_share_evidence():
    """Section 6's failure mode, pinned: handing every population the same
    nodes reproduces 'the market is fearful' with more objects."""
    households = collective.population("US_households", V.HOUSEHOLD)
    execs = collective.population("US_executives", V.EXECUTIVE_COHORT)
    states, ups, diag = estimator.estimate_many(
        populations=[households, execs], as_of="d",
        nodes_by_population={households.key: [
            _behavioural_node("delinquency", 6.0)]})
    by_key = {s.population.key: s for s in states}
    assert by_key[households.key].measured
    assert not by_key[execs.key].measured, (
        "the executive cohort had no evidence and must have no reading")


def test_the_estimate_reports_its_own_coverage_against_the_vocabulary():
    pop = collective.population("US_households", V.HOUSEHOLD)
    est, _, _ = estimator.estimate(
        population=pop, as_of="d",
        nodes=[_behavioural_node("delinquency", 5.0)])
    cov = est.coverage
    assert cov["vocabulary"] == len(V.COLLECTIVE_DIMENSIONS)
    assert cov["measured"] < cov["vocabulary"]
    assert cov["unmeasured"]


# =============================================================================
# Section 29: collective human state is NOT market participant state
# =============================================================================

def test_a_market_participant_is_not_a_population():
    """A dealer's gamma is not a mood.

    They interact -- consumer fear -> spending down -> retailer earnings down
    -> analyst revisions -> systematic factor flows -- but one is not the
    other, and a vocabulary that spelled them the same way would let a
    positioning reading be handed back as a collective estimate.
    """
    from intent_engine.econ import levelk

    participants = set(V.PARTICIPANT_CLASSES)
    constructs = set(V.COLLECTIVE_DIMENSIONS)
    assert not (participants & constructs), (
        f"{sorted(participants & constructs)} names both a market "
        "participant class and a human construct")

    # And the participant classes the level-k engine actually reacts for are
    # the ones the vocabulary declares -- not a second, drifting list.
    engine_classes = {c.lower() for c in getattr(levelk, "PARTICIPANTS", ())}
    if engine_classes:
        assert engine_classes <= participants, (
            f"{sorted(engine_classes - participants)} is a participant the "
            "level-k engine models and the shared vocabulary does not "
            "declare; two spellings of one participant is how a reflexive "
            "loop goes undetected")


def test_a_participant_class_cannot_be_used_as_a_collective_dimension():
    with pytest.raises(V.EconError):
        collective.DimensionEstimate(dimension="dealer", posterior_mean=0.5,
                                     uncertainty=0.1, evidence=("n",))


def test_a_behavioral_kind_is_not_a_market_structure_kind():
    """Retail speculation is a BEHAVIORAL observation of households; dealer
    gamma is a MARKET_STRUCTURE reading. Filing either as the other would
    make the incremental-value test compare a model to itself."""
    behavioural = set(V.NODE_KINDS[V.BEHAVIORAL])
    structure = set(V.NODE_KINDS[V.MARKET_STRUCTURE])
    assert not (behavioural & structure), (
        f"{sorted(behavioural & structure)} is filed as both")
