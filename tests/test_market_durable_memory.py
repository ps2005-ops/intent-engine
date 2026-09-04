"""Everything the engine must remember, proven across a process boundary.

Five of fifteen audited intelligence kinds were durable. This closes the
memory-critical ones and asserts each survives a FRESH store over the same
file — which is the only thing a restart can see.
"""
from __future__ import annotations

import pytest

from intent_engine.market import falsifiers as FL
from intent_engine.market import learning_store as LS
from intent_engine.market import response_watch as RW


@pytest.fixture()
def path(tmp_path):
    return tmp_path / "ledger.jsonl"


# --- counterfactual adjudication (was LOST) -------------------------------

def adjudication(**kw):
    base = dict(episode_id="cf_1", subject="cloudflare",
                observed_outcome="revenue rose 36%",
                leading_explanation="demand strengthening",
                strongest_alternative="one-off migration contract",
                resolution="LEADING_SURVIVED",
                lesson="a single quarter's beat does not separate these",
                adjudicated_at="2026-08-08")
    base.update(kw)
    return base


def test_an_adjudication_survives_a_fresh_process(path):
    assert LS.LearningStore(path).record_counterfactual_adjudication(
        adjudication()) == "written"
    reloaded = LS.LearningStore(path).counterfactual_adjudications()
    assert len(reloaded) == 1
    assert reloaded[0]["resolution"] == "LEADING_SURVIVED"
    assert reloaded[0]["lesson"].startswith("a single quarter")


def test_the_same_adjudication_twice_is_held_not_duplicated(path):
    store = LS.LearningStore(path)
    store.record_counterfactual_adjudication(adjudication())
    assert store.record_counterfactual_adjudication(adjudication()) == "held"
    assert len(store.counterfactual_adjudications()) == 1


def test_a_conflicting_adjudication_is_appended_never_overwritten(path):
    """"We changed our mind" is a different fact from "we always thought
    this", and the ledger is history."""
    store = LS.LearningStore(path)
    store.record_counterfactual_adjudication(adjudication())
    got = store.record_counterfactual_adjudication(
        adjudication(resolution="ALTERNATIVE_SURVIVED"))
    assert got == "conflict"
    rows = store.counterfactual_adjudications()
    assert len(rows) == 2
    assert rows[1]["supersedes"] == "cf_1"
    assert rows[1]["conflict_on"] == "resolution"
    # The original judgement is still readable.
    assert rows[0]["resolution"] == "LEADING_SURVIVED"


def test_an_adjudication_with_no_episode_id_is_refused(path):
    with pytest.raises(ValueError, match="cannot be stored"):
        LS.LearningStore(path).record_counterfactual_adjudication(
            adjudication(episode_id=""))


# --- falsifiers ------------------------------------------------------------

def falsifier():
    return FL.propose(
        subject="cloudflare", hypothesis_id="hyp_1",
        observation_needed="the next reported revenue growth falls below 20%",
        eligible_sources=("regulatory_filing", "investor_release"),
        resolution_window="2026-12-31", created_at="2026-08-08")


def test_a_falsifier_survives_a_fresh_process(path):
    assert LS.LearningStore(path).record_falsifier(falsifier()) == "written"
    reloaded = LS.LearningStore(path).falsifiers()
    assert len(reloaded) == 1
    assert reloaded[0]["standing"] == FL.OPEN
    assert "20%" in reloaded[0]["observation_needed"]


def test_a_falsifier_naming_no_observation_is_refused():
    """"the story changes" is a feeling. A source cannot report it, so the
    engine could never notice it arriving."""
    with pytest.raises(FL.FalsifierRejected, match="UNOBSERVABLE"):
        FL.propose(subject="x", hypothesis_id="h",
                   observation_needed="the narrative shifts against them",
                   eligible_sources=("investor_release",),
                   resolution_window="2026-12-31", created_at="2026-08-08")


def test_a_falsifier_satisfied_by_noise_is_refused():
    with pytest.raises(FL.FalsifierRejected, match="NOT_DISCRIMINATING"):
        FL.propose(subject="x", hypothesis_id="h",
                   observation_needed="the number moves",
                   eligible_sources=("investor_release",),
                   resolution_window="2026-12-31", created_at="2026-08-08")


def test_a_falsifier_with_no_window_is_refused():
    with pytest.raises(FL.FalsifierRejected, match="NO_WINDOW"):
        FL.propose(subject="x", hypothesis_id="h",
                   observation_needed="reported revenue growth falls below 20%",
                   eligible_sources=(), resolution_window="",
                   created_at="2026-08-08")


def test_the_research_question_is_neutral():
    """"Find evidence the belief is wrong" searches for confirmation of the
    opposite. The question asks for the OBSERVATION."""
    question = FL.research_question(falsifier()).lower()
    assert "retrieve the next reported observation" in question
    for banned in ("wrong", "disprove", "refute", "evidence against"):
        assert banned not in question


def test_an_expired_window_is_not_survival():
    """Nobody reported. Counting that as survival lets a belief harden on
    silence."""
    got = FL.expire(falsifier(), as_of="2027-01-15")
    assert got.standing == FL.EXPIRED
    assert got.standing != FL.RESOLVED_SURVIVED
    assert "not survival" in got.resolution


# --- response watch --------------------------------------------------------

def watch():
    return RW.open_watch(
        expectation_id="cax_1", counterparty="Salesforce",
        response_class="PRICE_CHANGE",
        competitive_object="enterprise commerce platform",
        eligible_source_families=("pricing_page", "release_notes"),
        start_at="2026-08-08", resolve_by="2026-11-08")


def test_a_watch_survives_a_fresh_process(path):
    assert LS.LearningStore(path).record_response_watch(watch()) == "written"
    reloaded = LS.LearningStore(path).response_watches()
    assert len(reloaded) == 1
    assert reloaded[0]["counterparty"] == "Salesforce"


def test_a_watch_without_a_preregistration_is_refused():
    """Whatever it found would read as confirmation of something nobody
    wrote down first."""
    with pytest.raises(RW.WatchRejected, match="preregistered"):
        RW.open_watch(expectation_id="", counterparty="Salesforce",
                      response_class="PRICE_CHANGE", competitive_object="x",
                      eligible_source_families=("pricing_page",),
                      start_at="2026-08-08", resolve_by="2026-11-08")


def test_a_watch_must_name_its_sources():
    with pytest.raises(RW.WatchRejected, match="crawl with a story"):
        RW.open_watch(expectation_id="cax_1", counterparty="Salesforce",
                      response_class="PRICE_CHANGE", competitive_object="x",
                      eligible_source_families=(),
                      start_at="2026-08-08", resolve_by="2026-11-08")


def test_a_window_closing_before_it_opens_is_refused():
    with pytest.raises(RW.WatchRejected, match="no future"):
        RW.open_watch(expectation_id="cax_1", counterparty="Salesforce",
                      response_class="PRICE_CHANGE", competitive_object="x",
                      eligible_source_families=("pricing_page",),
                      start_at="2026-11-08", resolve_by="2026-08-08")


def test_cadence_makes_a_watch_a_schedule_not_a_poll():
    got = watch()
    assert got.due("2026-08-08") is True
    assert got.due("2026-08-10", last_checked="2026-08-08") is False
    assert got.due("2026-08-16", last_checked="2026-08-08") is True


def test_a_closed_window_is_not_due():
    assert watch().due("2027-01-01") is False


def test_an_empty_watch_store_is_an_honest_state(path):
    got = RW.summarise(LS.LearningStore(path).response_watches(),
                       as_of="2026-08-08")
    assert got["watches"] == 0
    assert "EMPTY store is the honest state" in got["note"]


# --- strategic objectives --------------------------------------------------

def test_a_strategic_objective_survives_a_fresh_process(path):
    payload = {"hypothesis_id": "obj_1", "actor": "Salesforce",
               "objective": "MOVE_UPMARKET", "standing": "WEAK",
               "alternatives": ["EXPAND_SHARE", "REDUCE_CHURN"]}
    assert LS.LearningStore(path).record_strategic_objective(
        payload) == "written"
    reloaded = LS.LearningStore(path).strategic_objectives()
    assert len(reloaded) == 1
    assert reloaded[0]["alternatives"] == ["EXPAND_SHARE", "REDUCE_CHURN"]


def test_a_defeated_objective_is_not_erased_from_history(path):
    store = LS.LearningStore(path)
    base = {"hypothesis_id": "obj_1", "actor": "Salesforce",
            "objective": "MOVE_UPMARKET", "standing": "WEAK"}
    store.record_strategic_objective(base)
    store.record_strategic_objective({**base, "standing": "CONTRADICTED"})
    rows = store.strategic_objectives()
    assert len(rows) == 2
    assert rows[0]["standing"] == "WEAK"


# --- interaction and observed response episodes ---------------------------

def test_a_strategic_interaction_survives_a_fresh_process(path):
    payload = {"interaction_id": "int_1", "initiating_actor": "Shopify",
               "counterparty": "Salesforce", "standing": "CANDIDATE",
               "competitive_object": "enterprise commerce platform"}
    assert LS.LearningStore(path).record_strategic_interaction(
        payload) == "written"
    assert len(LS.LearningStore(path).strategic_interactions()) == 1


def test_an_observed_episode_cannot_claim_it_was_preregistered(path):
    """A historical sequence relabelled as a prediction is the one move that
    would make every strategic result untrustworthy at once."""
    with pytest.raises(ValueError, match="cannot be marked preregistered"):
        LS.LearningStore(path).record_actor_response_episode(
            {"episode_id": "ep_1", "preregistered": True})


def test_an_observed_episode_survives_a_fresh_process(path):
    payload = {"episode_id": "ep_1", "trigger_actor": "Shopify",
               "responder": "Salesforce", "standing": "CANDIDATE",
               "delay_days": 41}
    assert LS.LearningStore(path).record_actor_response_episode(
        payload) == "written"
    assert LS.LearningStore(path).actor_response_episodes()[0]["standing"] \
        == "CANDIDATE"
