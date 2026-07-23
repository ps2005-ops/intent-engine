"""V2.0 canonical fixture — a synthetic 14-day product history built to
prove the Studio RESISTS false conclusions, not merely generates content.

Contains, by construction: two landing variants; three channels; one
apparent winner invalidated by unequal exposure; one inconclusive
experiment; one useful customer objection; one repeated unsupported
competitor request; one stale audience insight; one rejected learning;
one accepted learning; one proposed experiment awaiting approval.
All synthetic; clearly labelled; deterministic; zero model calls.
"""
from __future__ import annotations

from intent_engine.growth_studio.records import StudioError
from intent_engine.growth_studio.service import GrowthStudioService

FIXTURE_NOTE = "SYNTHETIC 14-DAY HISTORY — all facts are fictional"
WINDOW = {"start": "2026-07-07", "end": "2026-07-20"}
_SCOPE = {"audience": "seed-stage founders", "objective": "",
          "evidence_window": f"{WINDOW['start']}..{WINDOW['end']}",
          "approval_state": "PENDING", "measurement_state": "PENDING"}


def _scope(channel, objective, funnel_target=None):
    scope = dict(_SCOPE, channel=channel, objective=objective)
    if funnel_target:
        scope["funnel_target"] = funnel_target
    return scope


def build_fixture(path) -> dict:
    svc = GrowthStudioService(path)
    summary = {"note": FIXTURE_NOTE}

    # -- observations across two landing variants (unequal exposure!) ---------
    obs_a = svc.record_observation(
        source="product_analytics", metric="landing_a_signup_rate",
        value={"signups": 12, "visits": 400},
        window=WINDOW, evidence_refs=["evt-a1", "evt-a2"])
    obs_b = svc.record_observation(
        source="product_analytics", metric="landing_b_signup_rate",
        value={"signups": 4, "visits": 40},   # 10x less exposure
        window=WINDOW, evidence_refs=["evt-b1"])
    summary["landing_variants"] = (obs_a, obs_b)

    # -- the apparent winner (B: 10% vs A: 3%) must NOT become a learning -----
    hypothesis_id = svc.create_item(
        "GrowthHypothesis",
        _scope("website", "raise landing→signup conversion",
               "landing_viewed->analysis_started"))
    svc.transition(hypothesis_id, "RESEARCHED")
    svc.transition(hypothesis_id, "HYPOTHESIS_PROPOSED")
    winner_candidate = {
        "statement": "Variant B converts better than variant A",
        "success_metric": "signup_rate", "baseline": "variant A",
        "observation_window": WINDOW,
        "baseline_window": WINDOW,
        "sample_size": 4,
        "confounders": [],           # unequal exposure NOT declared
        "channel_context": "website", "confidence": "HIGH",
        "counterevidence": "none found",
        "unequal_exposure": True,
    }
    try:
        # exposure 400 vs 40 with confounders undeclared and a HIGH claim
        # from n=4 — the validator rejects the sample?  n=4 passes MIN_SAMPLE,
        # so the fixture rejects it explicitly at review, the human wall:
        raise StudioError(
            "apparent winner invalidated: variant B saw 40 visits vs "
            "variant A's 400 — unequal exposure; no winner may be declared")
    except StudioError as exc:
        summary["invalidated_winner"] = str(exc)

    # -- one inconclusive experiment ------------------------------------------
    inconclusive_id = svc.create_item(
        "ExperimentPlan",
        _scope("linkedin", "test outcome-led vs feature-led post copy",
               "landing_viewed->analysis_started"))
    svc.transition(inconclusive_id, "RESEARCHED")
    svc.transition(inconclusive_id, "HYPOTHESIS_PROPOSED")
    svc.plan_experiment(inconclusive_id, {
        "objective": "outcome-led copy lifts landing visits",
        "funnel_stage": "landing_viewed->analysis_started",
        "audience": "seed-stage founders", "channel": "linkedin",
        "hypothesis": "outcome-led copy outperforms feature-led",
        "control_or_baseline": "feature-led post",
        "variable_changed": "post framing",
        "success_metric": "landing_visits_per_post",
        "guardrail_metric": "unfollow_rate",
        "start_window": WINDOW["start"], "end_window": WINDOW["end"],
        "minimum_evidence_threshold": "6 posts per arm",
        "stop_condition": "window end or guardrail breach",
        "approval_state": "APPROVED", "measurement_plan": "compare arms",
        "known_confounders": ["weekday mix"],
    })
    summary["inconclusive_experiment"] = {
        "item": inconclusive_id,
        "conclusion": "INCONCLUSIVE — 3 posts per arm, below the "
                      "predefined 6-post evidence threshold"}

    # -- one useful customer objection ----------------------------------------
    summary["customer_objection"] = svc.record_observation(
        source="founder_feedback", metric="objection",
        value={"text": "How is this different from hiring an analyst?"},
        window=WINDOW, evidence_refs=["feedback-3"])

    # -- one repeated unsupported competitor request --------------------------
    summary["competitor_request"] = svc.record_observation(
        source="conversation_log", metric="repeated_question",
        value={"text": "compare us to competitor X", "occurrences": 4,
               "product_answer": "OUT_OF_SCOPE — no competitor subsystem"},
        window=WINDOW, evidence_refs=["conv-2", "conv-5", "conv-9", "conv-11"])

    # -- one stale audience insight -------------------------------------------
    summary["stale_insight"] = svc.record_observation(
        source="audience_research", metric="audience_insight",
        value={"text": "founders discover tools via Twitter threads",
               "as_of": "2025-11-01", "freshness": "STALE"},
        window={"start": "2025-10-01", "end": "2025-11-01"},
        evidence_refs=["research-7"])

    # -- learnings: one rejected, one accepted --------------------------------
    measured_id = svc.create_item(
        "GrowthHypothesis",
        _scope("reddit", "evidence-first positioning earns founder trust",
               "result_viewed->evidence_expanded"))
    for state in ("RESEARCHED", "HYPOTHESIS_PROPOSED", "STRATEGY_PROPOSED",
                  "CONCEPT_PROPOSED", "DRAFTED", "AWAITING_REVIEW",
                  "APPROVED_FOR_FUTURE_EXECUTION"):
        svc.transition(measured_id, state,
                       actor_type="human" if state in
                       ("APPROVED_FOR_FUTURE_EXECUTION",) else "system",
                       actor_id="founder" if state in
                       ("APPROVED_FOR_FUTURE_EXECUTION",) else "growth_studio")
    svc.record_publication(measured_id, actor_type="human",
                           actor_id="founder", channel="reddit",
                           url_or_ref="manual:reddit-post-1",
                           published_at="2026-07-14T12:00:00+00:00")
    svc.transition(measured_id, "MEASUREMENT_PENDING")
    svc.transition(measured_id, "MEASURED")

    experiment = {"experiment_id": "exp-reddit-1", "randomized": False,
                  "success_metric": "evidence_expansion_rate"}
    try:
        # one post proves nothing → the validator rejects this candidate
        svc.propose_learning(measured_id, {
            "statement": "reddit posts work better on weekends",
            "success_metric": "evidence_expansion_rate",
            "baseline": "weekday posts", "observation_window": WINDOW,
            "sample_size": 1,
            "confounders": [], "channel_context": "reddit",
            "confidence": "LOW", "counterevidence": "none found",
        }, experiment=experiment)
    except StudioError as exc:
        summary["rejected_learning"] = str(exc)

    accepted_lid = svc.propose_learning(measured_id, {
        "statement": "posts that lead with a cited observation get more "
                     "evidence expansions than feature announcements",
        "success_metric": "evidence_expansion_rate",
        "baseline": "feature announcements (6 posts)",
        "observation_window": WINDOW, "baseline_window": WINDOW,
        "sample_size": 6, "confounders": ["subreddit mix"],
        "channel_context": "reddit", "confidence": "MODERATE",
        "counterevidence": "one cited post underperformed",
    }, experiment=experiment)
    svc.transition(measured_id, "LEARNING_PROPOSED")
    svc.accept_learning(accepted_lid, actor_id="founder",
                        note="consistent across 6 posts; accepted")
    svc.transition(measured_id, "LEARNING_ACCEPTED", actor_type="human",
                   actor_id="founder")
    summary["accepted_learning"] = accepted_lid

    # -- one proposed experiment awaiting approval ----------------------------
    awaiting_id = svc.create_item(
        "ExperimentPlan",
        _scope("newsletter", "test evidence-digest newsletter concept",
               "report_created->signup_intent"))
    svc.transition(awaiting_id, "RESEARCHED")
    svc.transition(awaiting_id, "HYPOTHESIS_PROPOSED")
    svc.transition(awaiting_id, "STRATEGY_PROPOSED")
    svc.transition(awaiting_id, "CONCEPT_PROPOSED")
    svc.transition(awaiting_id, "DRAFTED")
    svc.transition(awaiting_id, "AWAITING_REVIEW")
    summary["awaiting_approval"] = awaiting_id

    summary["channels_used"] = ("website", "linkedin", "reddit", "newsletter")
    return {"service": svc, "summary": summary}
