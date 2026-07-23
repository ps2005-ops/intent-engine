"""V2.0 — learning acceptance, metric-gaming walls, briefing contract,
channel policies, fixture, adapters."""
import pytest

from intent_engine.growth_studio.adapters import funnel_metrics_from_fi_store
from intent_engine.growth_studio.briefing import compose_brief, statement
from intent_engine.growth_studio.channels import check_draft
from intent_engine.growth_studio.fixtures import build_fixture
from intent_engine.growth_studio.learning import validate_candidate
from intent_engine.growth_studio.records import StudioError
from intent_engine.growth_studio.service import GrowthStudioService

EXPERIMENT = {"experiment_id": "exp-1", "randomized": False,
              "success_metric": "signup_rate"}

GOOD = {"statement": "cited posts get more expansions",
        "success_metric": "signup_rate", "baseline": "control (6 posts)",
        "observation_window": {"start": "2026-07-07", "end": "2026-07-20"},
        "baseline_window": {"start": "2026-06-23", "end": "2026-07-06"},
        "sample_size": 6, "confounders": ["weekday mix"],
        "channel_context": "reddit", "confidence": "MODERATE",
        "counterevidence": "one post underperformed"}


# --- learning acceptance ------------------------------------------------------

def test_good_candidate_passes():
    validate_candidate(dict(GOOD), experiment=EXPERIMENT)


def test_missing_fields_rejected():
    bad = dict(GOOD)
    del bad["counterevidence"]
    with pytest.raises(StudioError, match="missing"):
        validate_candidate(bad, experiment=EXPERIMENT)


def test_metric_change_after_results_rejected():
    bad = dict(GOOD, success_metric="impressions")
    with pytest.raises(StudioError, match="no changing"):
        validate_candidate(bad, experiment=EXPERIMENT)


def test_impressions_as_conversions_rejected():
    exp = dict(EXPERIMENT, success_metric="impressions")
    bad = dict(GOOD, success_metric="impressions",
               statement="impressions prove conversion works")
    with pytest.raises(StudioError, match="impressions treated as"):
        validate_candidate(bad, experiment=exp)


def test_unequal_windows_rejected():
    bad = dict(GOOD, baseline_window={"start": "2026-06-01",
                                      "end": "2026-07-06"})
    with pytest.raises(StudioError, match="unequal time windows"):
        validate_candidate(bad, experiment=EXPERIMENT)


def test_single_observation_rejected():
    bad = dict(GOOD, sample_size=1)
    with pytest.raises(StudioError, match="one observation never proves"):
        validate_candidate(bad, experiment=EXPERIMENT)


def test_winner_from_unavailable_data_rejected():
    bad = dict(GOOD, data_availability="UNAVAILABLE")
    with pytest.raises(StudioError, match="unavailable data"):
        validate_candidate(bad, experiment=EXPERIMENT)


def test_causal_claim_without_randomization_rejected():
    bad = dict(GOOD, statement="the campaign caused a signup lift")
    with pytest.raises(StudioError, match="causal claim from correlation"):
        validate_candidate(bad, experiment=EXPERIMENT)


def test_attribution_requires_experiment_design():
    with pytest.raises(StudioError, match="without an experiment design"):
        validate_candidate(dict(GOOD), experiment={"randomized": False,
                                                   "success_metric":
                                                       "signup_rate"})


def test_only_a_human_accepts_learning(tmp_path):
    svc = GrowthStudioService(tmp_path / "s.jsonl")
    with pytest.raises(StudioError, match="only a human"):
        svc.accept_learning("lid-1", actor_id="bot", actor_type="system")


def test_growth_memory_is_append_only_accepted_only(tmp_path):
    built = build_fixture(tmp_path / "s.jsonl")
    svc = built["service"]
    accepted = svc.store.accepted_learnings()
    assert len(accepted) == 1                    # only the human-accepted one
    proposed = [r for r in svc.store.read_all()
                if r.event_type == "studio.learning_proposed"]
    assert len(proposed) >= 1                    # proposals exist separately


# --- briefing -----------------------------------------------------------------

def test_statement_requires_evidence_unless_insufficient():
    statement("x performed", evidence=["obs-1"], timeframe="last 7 days",
              confidence="MODERATE")
    statement("nothing conclusive", evidence=[], timeframe="last 7 days",
              confidence="INSUFFICIENT_EVIDENCE")
    with pytest.raises(StudioError, match="requires evidence"):
        statement("x performed", evidence=[], timeframe="last 7 days",
                  confidence="HIGH")


def test_briefing_structure_and_unknown_section():
    with pytest.raises(StudioError, match="unknown briefing sections"):
        compose_brief(as_of_date="2026-07-21",
                      sections={"vibes": []})
    brief = compose_brief(as_of_date="2026-07-21", sections={
        "what_performed": [statement("cited posts outperformed",
                                     evidence=["obs-2"],
                                     timeframe="2026-07-07..20",
                                     confidence="MODERATE")]})
    assert set(brief["sections"]) >= {"what_performed", "decisions_needed"}


def test_daily_briefing_idempotent_no_duplicate(tmp_path):
    svc = GrowthStudioService(tmp_path / "s.jsonl")
    sections = {"what_changed": [statement(
        "first early-access account created", evidence=["web-1"],
        timeframe="2026-07-21", confidence="HIGH")]}
    first = svc.produce_briefing(as_of_date="2026-07-21", sections=sections)
    again = svc.produce_briefing(as_of_date="2026-07-21", sections=sections)
    assert first["briefing_id"] == again["briefing_id"]
    assert len(svc.store.briefings()) == 1       # safe rerun, no duplicate
    # a different day is a different briefing (missed-run handling)
    svc.produce_briefing(as_of_date="2026-07-22", sections=sections)
    assert len(svc.store.briefings()) == 2


def test_zero_model_calls_in_deterministic_operation(tmp_path):
    built = build_fixture(tmp_path / "s.jsonl")
    assert built["service"].model_calls == 0


# --- channel policies ---------------------------------------------------------

def test_reddit_requires_disclosure():
    v = check_draft(channel="reddit", body="Check out our product!",
                    statements=[{"class": "HYPOTHESIS", "text": "x"}])
    assert any("disclosed" in x for x in v)
    assert not check_draft(
        channel="reddit",
        body="Disclosure: I built this. Happy to answer questions.",
        statements=[{"class": "FOUNDER_OPINION", "text": "x"}])


def test_hackernews_needs_substance_no_bait():
    v = check_draft(channel="hackernews", body="Click here! Limited time!",
                    statements=[{"class": "HYPOTHESIS", "text": "x"}])
    assert any("engagement-bait" in x for x in v)
    assert any("technical substance" in x for x in v)


def test_newsletter_requires_unsubscribe():
    v = check_draft(channel="newsletter", body="Our weekly digest.",
                    statements=[{"class": "SUPPORTED_PRODUCT_FACT",
                                 "text": "x"}])
    assert any("unsubscribe" in x for x in v)


def test_producthunt_no_vote_solicitation():
    v = check_draft(channel="producthunt", body="Please upvote us!",
                    statements=[{"class": "FOUNDER_OPINION", "text": "x"}])
    assert any("vote" in x for x in v)


def test_unsupported_statement_and_unconsented_quote_rejected():
    v = check_draft(channel="linkedin", body="body",
                    statements=[
                        {"class": "UNSUPPORTED_REJECT", "text": "we are #1"},
                        {"class": "CUSTOMER_QUOTE", "text": "great",
                         "consented": False}])
    assert any("unsupported statement" in x for x in v)
    assert any("consent" in x for x in v)


def test_superiority_claim_needs_support():
    v = check_draft(channel="x", body="Definitely the best tool.",
                    statements=[{"class": "HYPOTHESIS", "text": "y"}])
    assert any("superiority" in x for x in v)


def test_noncompliant_draft_cannot_be_referenced(tmp_path):
    svc = GrowthStudioService(tmp_path / "s.jsonl")
    item = svc.create_item("GrowthHypothesis", {
        "audience": "founders", "channel": "reddit", "objective": "o",
        "evidence_window": "w", "approval_state": "P",
        "measurement_state": "P",
        "funnel_target": "landing_viewed->analysis_started"})
    with pytest.raises(StudioError, match="channel policy violations"):
        svc.reference_draft(item, channel="reddit", body="Buy our stuff",
                            statements=[{"class": "HYPOTHESIS", "text": "x"}],
                            campaign_id="camp-1")


# --- fixture ------------------------------------------------------------------

def test_fixture_contains_all_required_elements(tmp_path):
    summary = build_fixture(tmp_path / "s.jsonl")["summary"]
    assert "unequal exposure" in summary["invalidated_winner"]
    assert "INCONCLUSIVE" in summary["inconclusive_experiment"]["conclusion"]
    assert "one observation never proves" in summary["rejected_learning"]
    assert summary["accepted_learning"]
    assert summary["awaiting_approval"]
    assert summary["customer_objection"]
    assert summary["competitor_request"]
    assert summary["stale_insight"]
    assert len(summary["channels_used"]) >= 3
    assert "SYNTHETIC" in summary["note"]


# --- adapters: product analytics separation -----------------------------------

def test_funnel_adapter_reads_without_rewriting(tmp_path):
    from intent_engine.founder_intelligence.service import (
        FounderIntelligenceService,
    )
    fi = FounderIntelligenceService(tmp_path / "fi.jsonl")
    fi.record_telemetry("run-1", "demo.example", "landing_viewed")
    fi.record_telemetry("run-1", "demo.example", "result_viewed")
    before = [r.content_fingerprint() for r in fi.store.read_all()]
    metrics = funnel_metrics_from_fi_store(
        fi.store, window={"start": "2026-07-07", "end": "2026-07-20"})
    after = [r.content_fingerprint() for r in fi.store.read_all()]
    assert before == after                        # raw events untouched
    by_metric = {m["metric"]: m for m in metrics}
    assert by_metric["landing_viewed"]["value"] == 1
    assert by_metric["landing_viewed"]["evidence_refs"]
    # an absent stage is UNAVAILABLE with value None — never zero
    assert by_metric["signup_intent"]["availability"] == "UNAVAILABLE"
    assert by_metric["signup_intent"]["value"] is None
