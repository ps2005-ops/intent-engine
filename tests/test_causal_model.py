from intent_engine.simulator.causal_model import (
    CAUSAL_RELATIONSHIPS,
    evaluate_extraction_flags,
    relevant_relationships,
)


def test_relevant_relationships_matches_by_keyword():
    results = relevant_relationships(
        "We're raising prices 30% across all tiers.",
        "Market: price-competitive SMB scheduling software",
        limit=4,
    )
    triggers = [r.trigger for r in results]
    assert "Prices increase" in triggers


def test_relevant_relationships_matches_expansion_context():
    results = relevant_relationships(
        "We're expanding into Asia with $2M investment.",
        "Market: B2B SaaS, competitive position: two larger incumbents",
        limit=4,
    )
    triggers = [r.trigger for r in results]
    assert "Entering a new market or geography" in triggers
    assert "Competitive pressure increases" in triggers


def test_relevant_relationships_respects_limit():
    results = relevant_relationships(
        "We're hiring aggressively and raising prices while entering new markets.",
        "Team size: 12, runway: 10 months, competitive position: crowded",
        limit=2,
    )
    assert len(results) <= 2


def test_relevant_relationships_falls_back_when_nothing_matches():
    results = relevant_relationships("Completely unrelated decision text.", "no matching context", limit=3)
    assert len(results) == 3
    assert results == CAUSAL_RELATIONSHIPS[:3]


def test_extraction_flags_fires_no_leverage_ceiling_on_growth_with_none_apparent():
    flags = evaluate_extraction_flags(
        leverage_type=["none_apparent"],
        scale_efficiency="unclear",
        market_timing_signal="uncertain",
        primary_priority="growth",
    )
    triggers = [f.trigger for f in flags]
    assert "Growth-oriented decision with no identified leverage mechanism" in triggers
    assert len(flags) == 1  # the other two conditions are not met


def test_extraction_flags_does_not_fire_no_leverage_ceiling_when_leverage_present():
    flags = evaluate_extraction_flags(
        leverage_type=["financial", "people"],
        scale_efficiency="unclear",
        market_timing_signal="uncertain",
        primary_priority="growth",
    )
    assert flags == []


def test_extraction_flags_fires_cost_outpacing_output_on_growth():
    flags = evaluate_extraction_flags(
        leverage_type=["people"],
        scale_efficiency="cost_outpacing_output",
        market_timing_signal="uncertain",
        primary_priority="growth",
    )
    triggers = [f.trigger for f in flags]
    assert "Cost growing faster than output in a growth-oriented decision" in triggers
    assert len(flags) == 1


def test_extraction_flags_does_not_fire_cost_outpacing_output_off_growth_priority():
    """Same scale_efficiency signal, but a non-growth priority -- must not fire."""
    flags = evaluate_extraction_flags(
        leverage_type=["people"],
        scale_efficiency="cost_outpacing_output",
        market_timing_signal="uncertain",
        primary_priority="survival",
    )
    assert flags == []


def test_extraction_flags_fires_saturated_market_timing_on_growth():
    flags = evaluate_extraction_flags(
        leverage_type=["financial"],
        scale_efficiency="proportional",
        market_timing_signal="saturated",
        primary_priority="growth",
    )
    triggers = [f.trigger for f in flags]
    assert "Growth-oriented decision entering an already-saturated market" in triggers
    assert len(flags) == 1


def test_extraction_flags_can_fire_multiple_simultaneously():
    flags = evaluate_extraction_flags(
        leverage_type=["none_apparent"],
        scale_efficiency="cost_outpacing_output",
        market_timing_signal="saturated",
        primary_priority="growth",
    )
    # 4, not 3: the 3 growth-gated rules from the prior checkpoint all fire, plus
    # the new cost-outpacing/no-leverage rule below, which isn't gated on
    # primary_priority and also matches this input.
    assert len(flags) == 4


def test_extraction_flags_fires_cost_outpacing_no_leverage_regardless_of_priority():
    """New this pass: unlike the growth-gated rules above, this one has no
    primary_priority condition -- cost outpacing output with no leverage is a
    risk regardless of what the founder is optimizing for."""
    flags = evaluate_extraction_flags(
        leverage_type=["none_apparent"],
        scale_efficiency="cost_outpacing_output",
        market_timing_signal="uncertain",
        primary_priority="survival",
    )
    triggers = [f.trigger for f in flags]
    assert "Cost outpacing output with no identified leverage mechanism" in triggers
    assert len(flags) == 1


def test_extraction_flags_does_not_fire_cost_outpacing_no_leverage_when_leverage_present():
    flags = evaluate_extraction_flags(
        leverage_type=["technology"],
        scale_efficiency="cost_outpacing_output",
        market_timing_signal="uncertain",
        primary_priority="survival",
    )
    assert flags == []


def test_extraction_flags_fires_rising_tide_no_leverage_regardless_of_priority():
    flags = evaluate_extraction_flags(
        leverage_type=["none_apparent"],
        scale_efficiency="proportional",
        market_timing_signal="rising_tide",
        primary_priority="optionality",
    )
    triggers = [f.trigger for f in flags]
    assert "Favorable market timing with no identified leverage mechanism" in triggers
    assert len(flags) == 1


def test_extraction_flags_does_not_fire_rising_tide_when_leverage_present():
    flags = evaluate_extraction_flags(
        leverage_type=["media"],
        scale_efficiency="proportional",
        market_timing_signal="rising_tide",
        primary_priority="optionality",
    )
    assert flags == []


def test_extraction_flags_none_fire_on_honest_unclear_signals():
    """The whole point of 'unclear'/'uncertain'/'none_apparent' as valid answers:
    they must not accidentally satisfy a flag condition."""
    flags = evaluate_extraction_flags(
        leverage_type=[],
        scale_efficiency=None,
        market_timing_signal=None,
        primary_priority="profitability",
    )
    assert flags == []
