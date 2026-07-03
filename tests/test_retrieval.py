from intent_engine.simulator.retrieval import (
    RetrievedMatch,
    ReferenceDecision,
    format_retrieval_digest,
    retrieve_similar,
)


def test_retrieve_similar_ranks_closest_match_first():
    matches = retrieve_similar(
        "Hiring an outbound sales team before confirming product-market fit.", top_k=3
    )
    assert len(matches) == 3
    assert matches[0].reference.id == "ref-03"
    assert matches[0].similarity >= matches[1].similarity >= matches[2].similarity


def test_retrieve_similar_respects_top_k():
    matches = retrieve_similar("Raising prices to fix unit economics.", top_k=2)
    assert len(matches) == 2


_FAKE_REFERENCE = ReferenceDecision(
    id="ref-test",
    decision_text="Hired 3 salespeople before product-market fit.",
    context_at_decision={"team_size": 4, "runway_months": 9},
    outcome="Ran out of runway before pipeline materialized.",
    lesson="Founder-led validation should have come first.",
)


def test_format_retrieval_digest_buckets_and_deltas():
    matches = [RetrievedMatch(reference=_FAKE_REFERENCE, similarity=0.8)]
    digest = format_retrieval_digest(matches, current_team_size=6, current_runway_months=12)

    assert "[strong match, team 4 vs. your 6, runway 9mo vs. your 12mo]" in digest
    assert "Hired 3 salespeople before product-market fit." in digest
    assert "Lesson: Founder-led validation should have come first." in digest


def test_format_retrieval_digest_loose_match_below_threshold():
    matches = [RetrievedMatch(reference=_FAKE_REFERENCE, similarity=0.1)]
    digest = format_retrieval_digest(matches, current_team_size=6, current_runway_months=12)

    assert "[loose match" in digest
    assert "[strong match" not in digest


def test_format_retrieval_digest_omits_delta_when_current_context_missing():
    matches = [RetrievedMatch(reference=_FAKE_REFERENCE, similarity=0.8)]
    digest = format_retrieval_digest(matches, current_team_size=None, current_runway_months=None)

    assert "vs. your" not in digest
    assert digest.startswith("[strong match]")
