from intent_engine.simulator.causal_model import CAUSAL_RELATIONSHIPS, relevant_relationships


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
