"""A replay that can see the future is not history.

`historical_playback` was read by the X-Ray AND by the presentation, and was
written by nothing. Both surfaces carried a hardcoded sentence explaining its
absence -- so the product asserted, in prose, a fact about a producer that did
not exist. This is the same shape as the bare independent-origin zero and the
bare evidence family.

The tests that matter here are the ones that try to LEAK. A replay is only
worth anything if it is impossible for the outcome to inform the belief, and
the cheapest way to get that wrong is to filter on a date printed inside a
document rather than on when we actually observed it.
"""
import datetime as dt

from intent_engine.strategic_intelligence import economic_history as EH

TODAY = dt.date(2026, 8, 15)


def _obs(observed_at, **extra):
    return dict({"observed_at": observed_at, "text": "something"}, **extra)


# --- the vintage wall ----------------------------------------------------------


def test_only_what_was_observed_by_t0_survives_the_wall():
    kept = EH.observations_known_by(
        [_obs("2024-01-05"), _obs("2024-06-30"), _obs("2026-08-01")],
        "2024-12-31")
    assert [o["observed_at"] for o in kept] == ["2024-01-05", "2024-06-30"]


def test_a_document_about_the_past_read_today_does_not_survive():
    """THE LEAK THIS PREVENTS. A filing covering 2019, first read last week,
    was not available at a 2019 decision point. Filtering on any date INSIDE
    the document would admit it."""
    kept = EH.observations_known_by(
        [_obs("2026-08-01", period="2019-12-31", filed_for="FY2019")],
        "2020-01-01")
    assert kept == []


def test_an_undated_observation_is_excluded_not_admitted():
    """Strict direction on purpose: one missing timestamp must not reopen the
    entire future."""
    assert EH.observations_known_by([_obs(None), _obs("")], "2026-01-01") == []


def test_an_unparseable_t0_admits_nothing():
    assert EH.observations_known_by([_obs("2024-01-01")], "not-a-date") == []


# --- the three states, measured ------------------------------------------------


def test_a_young_archive_is_blocked_and_says_when_it_clears():
    got = EH.assess(observations=[_obs("2026-07-01"), _obs("2026-08-01")],
                    today=TODAY)
    assert got["state"] == EH.HISTORICAL_REPLAY_BLOCKED_DATA
    assert got["retrieval_months"] == 1
    assert got["required_months"] == EH.MIN_REPLAY_MONTHS
    assert got["next_eligible_date"] == "2027-01-01"
    assert "hindsight, not history" in got["why_blocked"]


def test_a_deep_archive_with_no_recorded_decision_is_descriptive_only():
    got = EH.assess(observations=[_obs("2025-01-05"), _obs("2025-09-09")],
                    today=TODAY)
    assert got["state"] == EH.DESCRIPTIVE_HISTORY_ONLY
    assert got["state"] not in EH.SUPPORTS_REPLAY
    assert "no decision of ours was on file" in got["statement"]


def test_only_a_real_episode_licenses_the_replay_state():
    got = EH.assess(observations=[_obs("2024-01-05"), _obs("2025-01-05")],
                    episodes=[{"t0": "2024-06-30"}], today=TODAY)
    assert got["state"] == EH.HISTORICAL_REPLAY_AVAILABLE
    assert got["state"] in EH.SUPPORTS_REPLAY


def test_an_empty_archive_is_blocked_and_says_so_without_a_date():
    got = EH.assess(observations=[], today=TODAY)
    assert got["state"] == EH.HISTORICAL_REPLAY_BLOCKED_DATA
    assert got["retrieval_months"] == 0
    assert "no archive depth" in got["statement"]


def test_the_blocked_state_is_still_useful_to_a_reader():
    """A blank card is not an honest refusal. Every number a reader needs to
    judge the gap has to be present."""
    got = EH.assess(observations=[_obs("2026-06-01")], today=TODAY)
    for key in ("retrieval_months", "required_months", "earliest_valid_t0",
                "next_eligible_date", "why_blocked"):
        assert got[key] != "" and got[key] is not None


# --- luck discipline -----------------------------------------------------------


def test_a_right_answer_for_a_wrong_reason_is_not_scored_as_skill():
    """The single most dangerous row in a track record: indistinguishable
    from skill the moment the two axes are averaged."""
    assert EH.judge(mechanism=EH.MECHANISM_CONTRADICTED,
                    outcome=EH.OUTCOME_AS_EXPECTED) == (
        EH.RIGHT_FOR_THE_WRONG_REASON)


def test_a_sound_mechanism_with_a_bad_outcome_is_kept_distinct():
    assert EH.judge(mechanism=EH.MECHANISM_CONFIRMED,
                    outcome=EH.OUTCOME_AGAINST) == EH.WRONG_BUT_SOUND


def test_a_right_answer_for_the_right_reason_is_the_only_hit():
    assert EH.judge(mechanism=EH.MECHANISM_CONFIRMED,
                    outcome=EH.OUTCOME_AS_EXPECTED) == (
        EH.RIGHT_FOR_THE_RIGHT_REASON)


def test_an_unresolved_axis_never_becomes_a_verdict():
    for kwargs in ({"mechanism": EH.MECHANISM_UNRESOLVED,
                    "outcome": EH.OUTCOME_AS_EXPECTED},
                   {"mechanism": EH.MECHANISM_CONFIRMED,
                    "outcome": EH.OUTCOME_UNRESOLVED}):
        assert EH.judge(**kwargs) == EH.UNRESOLVED


def test_the_sentence_is_carried_not_rebuilt_per_surface():
    """The hardcoded version drifted from any measurement at all, because two
    surfaces each owned their own copy of it."""
    blocked = EH.assess(observations=[_obs("2026-07-01")], today=TODAY)
    said = EH.plain_statement(blocked)
    assert "month(s) of our own observations" in said
    assert "hindsight, not history" in said


# --- the producer must reach the surfaces, or it is inert ---------------------


def test_the_measured_state_reaches_the_decision_and_the_xray():
    """PRODUCER -> REPORT -> DECISION -> SURFACE. `historical_playback` had
    two consumers and no producer, and both consumers carried a hardcoded
    sentence explaining its absence."""
    from intent_engine.founder_brief import xray as X
    from intent_engine.strategic_intelligence.reasoning import (
        build_strategic_report,
    )
    assessment = EH.assess(observations=[_obs("2026-08-01")], today=TODAY)
    report = build_strategic_report(company_name="Caterpillar Inc.",
                                    observations=[],
                                    economic_history=assessment)
    decision = report.thesis.get("decision") or {}
    assert decision["economic_history"]["state"] == (
        EH.HISTORICAL_REPLAY_BLOCKED_DATA)
    body = X._history_body(decision)
    assert "Replay not yet valid" in body
    assert "a replay needs 6" in body


def test_without_an_assessment_no_surface_invents_a_state():
    """NEGATIVE CONTROL. Absent must stay absent: a defaulted state would let
    the X-Ray label an archive it never measured."""
    from intent_engine.founder_brief import xray as X
    from intent_engine.strategic_intelligence.reasoning import (
        build_strategic_report,
    )
    report = build_strategic_report(company_name="X", observations=[])
    decision = report.thesis.get("decision") or {}
    assert decision["economic_history"] == {}
    assert "Replay not yet valid" not in X._history_body(decision)


def test_the_deck_slide_uses_the_measurement_too():
    """Two surfaces, one sentence -- the drift that produced two different
    hardcoded paragraphs is what this prevents."""
    from intent_engine.founder_brief import deep as D
    assessment = EH.assess(observations=[_obs("2026-08-01")], today=TODAY)
    decision = {"company": "Caterpillar Inc.", "standing": "",
                "economic_history": assessment}
    html = D.presentation(decision, company="Caterpillar Inc.")
    assert "a replay needs 6" in html
