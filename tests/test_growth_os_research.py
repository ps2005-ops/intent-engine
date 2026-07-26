"""Growth Research (§1) — understood intent, evolution over time, and
proposed-only learning candidates. Offline, deterministic."""
import pytest

from intent_engine.growth_os.foundation import Confidence, GrowthOSError, IntelStore, Provenance
from intent_engine.growth_os.research import GrowthResearchService


def _svc(tmp_path):
    return GrowthResearchService(IntelStore(tmp_path / "research.jsonl"))


def _prov():
    return Provenance(source="reddit", method="api", uri="https://reddit.com/r/startups")


def _obs(svc, text, day, intent="problem_aware", conf=0.7):
    return svc.observe(
        kind="pain_point", domain="founders", text=text, intent=intent,
        provenance=_prov(), confidence=Confidence(conf, basis="thread volume"),
        observed_at=f"{day}T12:00:00+00:00")


def test_observe_validates_taxonomy(tmp_path):
    svc = _svc(tmp_path)
    with pytest.raises(GrowthOSError):
        svc.observe(kind="not_a_kind", domain="ai", text="x", intent="informational",
                    provenance=_prov(), confidence=Confidence(0.5, basis="b"))
    with pytest.raises(GrowthOSError):
        svc.observe(kind="topic", domain="not_a_domain", text="x", intent="informational",
                    provenance=_prov(), confidence=Confidence(0.5, basis="b"))


def test_same_observation_same_day_dedupes(tmp_path):
    svc = _svc(tmp_path)
    _obs(svc, "forecasting is hard for founders", "2026-07-20")
    _obs(svc, "Forecasting is HARD for founders!", "2026-07-20")  # same topic, same day
    evo = svc.topic_evolution("forecasting is hard for founders")
    assert evo.observations == 1                      # deduped within the day


def test_topic_evolution_tracks_rising_trend(tmp_path):
    svc = _svc(tmp_path)
    # sparse early, dense late -> rising
    for day in ("2026-07-01", "2026-07-10", "2026-07-11", "2026-07-12"):
        _obs(svc, "AI agents for decision making", day)
    evo = svc.topic_evolution("AI agents for decision making")
    assert evo.observations == 4 and evo.distinct_days == 4
    assert evo.trend == "rising"
    assert evo.first_seen < evo.last_seen


def test_emerging_candidates_are_proposed_only_and_thresholded(tmp_path):
    svc = _svc(tmp_path)
    # a recurring, rising topic across 3 distinct days
    for day in ("2026-07-01", "2026-07-08", "2026-07-09", "2026-07-10"):
        _obs(svc, "founders distrust black-box forecasts", day, conf=0.8)
    # a one-off topic that should NOT become a candidate
    _obs(svc, "random one-off idea", "2026-07-05")

    cands = svc.emerging_candidates(min_observations=3, min_distinct_days=2)
    statements = " ".join(c.statement for c in cands)
    assert "black box forecasts" in statements        # normalized (hyphen stripped)
    assert "random one-off" not in statements
    # every candidate is proposed (never auto-accepted) and carries evidence
    assert all(c.status == "proposed" for c in cands)
    assert all(c.evidence and c.confidence.basis for c in cands)


def test_top_topics_ranks_by_recurrence(tmp_path):
    svc = _svc(tmp_path)
    for day in ("2026-07-01", "2026-07-02", "2026-07-03"):
        _obs(svc, "recurring pain", day)
    _obs(svc, "rare pain", "2026-07-01")
    top = svc.top_topics(domain="founders", limit=5)
    assert top[0].topic == "recurring pain"
