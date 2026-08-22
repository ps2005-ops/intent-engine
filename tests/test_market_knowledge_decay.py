"""Decay must separate three things time alone cannot tell apart.

Every test here is about a DISTINCTION, not a threshold. The thresholds are
the beliefs' own; the distinctions are what the module exists for:

    stale       != contradicted   (nothing argued vs something argued)
    stale       != old            (an open window is a prediction, not silence)
    cadence     != global         (120 days for demand, 365 for capital)
    retired     != stale          (outlived two chances, not one)
    revalidated != rewritten      (a new event, never an edited old one)
"""
from __future__ import annotations

import json
import pathlib

from intent_engine.market import knowledge_decay as KD
from intent_engine.market import learning_store as LS

REAL_LEDGER = pathlib.Path(
    "/Users/prathamsharma/intent-engine-market/reports/market/"
    "learning_ledger.jsonl")


def belief(bid, subject, *, declared, cadence=120, validated="",
           state="ACTIVE", eligible=True):
    return {"record": "belief", "belief_id": bid, "subject": subject,
            "proposition": f"{subject} is doing the thing",
            "last_updated": declared, "last_validated": validated,
            "review_interval_days": cadence, "decay_eligible": eligible,
            "lifecycle_state": state}


def expectation(bid, *, ends, subject="acme"):
    return {"record": "expectation", "expectation_id": f"exp_{bid}",
            "hypothesis_id": bid, "subject": subject,
            "evaluation_window_ends": ends, "metric": "demand_strengthening",
            "expected_event": "the next reported revenue figure"}


def reconciliation(bid, *, at, outcome="CONFIRMED", subject="acme"):
    return {"record": "reconciliation", "expectation_id": f"exp_{bid}",
            "hypothesis_id": bid, "subject": subject, "outcome": outcome,
            "evaluated_at": at, "informative": outcome in KD.INFORMATIVE}


def only(assessments, bid):
    return next(a for a in assessments if a.belief_id == bid)


# --- the gate: an open window is a prediction, not a silence ---------------

def test_open_expectation_window_blocks_decay_however_old():
    rows = [belief("b1", "acme", declared="2020-01-01", cadence=120),
            expectation("b1", ends="2030-01-01")]
    a = only(KD.assess(rows, as_of="2026-08-07"), "b1")
    assert not a.eligible
    assert a.reason_code == KD.WINDOW_OPEN
    # Ten years old and still not stale, because the engine said in advance
    # it would not know until 2030.
    assert a.days_since_anchor > 2000


def test_closed_window_past_cadence_is_stale():
    rows = [belief("b1", "acme", declared="2025-01-01", cadence=120),
            expectation("b1", ends="2025-05-01")]
    # 151 days: past one 120-day cadence, short of the two that retire it.
    a = only(KD.assess(rows, as_of="2025-06-01"), "b1")
    assert a.eligible and a.outcome == KD.STALE
    assert a.reason_code == KD.AGED_PAST_CADENCE


# --- stale is not contradicted, in both directions ------------------------

def test_a_tested_belief_is_never_stale_however_old():
    """Something argued about it. That is the opposite of nothing happening."""
    rows = [belief("b1", "acme", declared="2015-01-01", cadence=120),
            expectation("b1", ends="2015-05-01"),
            reconciliation("b1", at="2015-06-01", outcome="CONTRADICTED")]
    a = only(KD.assess(rows, as_of="2026-08-07"), "b1")
    assert not a.eligible
    assert a.reason_code == KD.TESTED
    assert a.outcome != KD.STALE


def test_an_aged_belief_is_never_reported_as_contradicted():
    rows = [belief("b1", "acme", declared="2026-01-01", cadence=120),
            expectation("b1", ends="2026-03-01")]
    a = only(KD.assess(rows, as_of="2026-06-01"), "b1")
    assert a.outcome == KD.STALE
    # Decay owns no contradiction vocabulary at all, which is the strongest
    # form of "it cannot say this".
    assert "CONTRADICT" not in a.outcome.upper()
    assert "CONTRADICT" not in a.reason.upper()


def test_an_informative_test_restarts_the_clock():
    rows = [belief("b1", "acme", declared="2024-01-01", cadence=120),
            expectation("b1", ends="2024-05-01"),
            reconciliation("b1", at="2026-08-01")]
    a = only(KD.assess(rows, as_of="2026-08-07"), "b1")
    assert a.days_since_anchor == 6
    assert a.anchor == "2026-08-01"


# --- the cadence is the belief's own, never the module's ------------------

def test_two_families_of_the_same_age_decay_differently():
    """A single global threshold would make these two the same. They are not."""
    rows = [
        belief("fast", "acme", declared="2025-06-01", cadence=120),
        expectation("fast", ends="2025-09-29"),
        belief("slow", "acme", declared="2025-06-01", cadence=365),
        expectation("slow", ends="2026-06-01"),
    ]
    got = KD.assess(rows, as_of="2025-11-01")
    assert only(got, "fast").outcome == KD.STALE
    slow = only(got, "slow")
    assert slow.outcome == "" and slow.reason_code == KD.WINDOW_OPEN
    assert "365" in slow.reason or slow.cadence_days == 365


def test_no_module_level_threshold_governs_any_belief():
    """The only day count in the module is a fallback for malformed rows."""
    rows = [belief("b1", "acme", declared="2025-01-01", cadence=400),
            expectation("b1", ends="2025-02-01")]
    a = only(KD.assess(rows, as_of="2026-01-01"), "b1")
    assert a.cadence_days == 400
    assert a.outcome == ""          # 365 days elapsed, cadence is 400
    assert a.reason_code == KD.WITHIN_CADENCE


def test_a_belief_with_no_cadence_falls_back_and_says_so():
    row = belief("b1", "acme", declared="2024-01-01")
    row.pop("review_interval_days")
    a = only(KD.assess([row, expectation("b1", ends="2024-03-01")],
                       as_of="2026-08-07"), "b1")
    assert a.cadence_days == KD.FALLBACK_INTERVAL_DAYS


# --- retirement is two chances missed, not one ----------------------------

def test_retirement_needs_two_full_refresh_windows():
    one = [belief("b1", "acme", declared="2026-01-01", cadence=120),
           expectation("b1", ends="2026-02-01")]
    assert only(KD.assess(one, as_of="2026-06-01"), "b1").outcome == KD.STALE
    two = [belief("b2", "acme", declared="2025-01-01", cadence=120),
           expectation("b2", ends="2025-02-01")]
    assert only(KD.assess(two, as_of="2026-08-07"), "b2").outcome == KD.RETIRED


def test_an_already_retired_belief_is_not_re_decayed():
    rows = [belief("b1", "acme", declared="2020-01-01", state="RETIRED")]
    a = only(KD.assess(rows, as_of="2026-08-07"), "b1")
    assert not a.eligible and a.reason_code == KD.ALREADY_RETIRED


# --- regime transition: eligibility without waiting for the clock ---------

def test_regime_change_makes_a_fresh_belief_stale_immediately():
    rows = [belief("b1", "acme", declared="2026-08-01", cadence=365),
            expectation("b1", ends="2027-08-01")]
    changes = [{"subject": "acme", "at": "2026-08-05",
                "what_changed": "the tariff regime it sells under"}]
    a = only(KD.assess(rows, as_of="2026-08-07", regime_changes=changes), "b1")
    assert a.outcome == KD.STALE
    assert a.reason_code == KD.REGIME_TRANSITION
    assert "tariff regime" in a.reason


def test_a_regime_change_before_the_evidence_does_not_decay_it():
    """The belief was declared knowing about the change. It is not stale."""
    rows = [belief("b1", "acme", declared="2026-08-06", cadence=365),
            expectation("b1", ends="2027-08-01")]
    changes = [{"subject": "acme", "at": "2026-01-01",
                "what_changed": "the tariff regime"}]
    a = only(KD.assess(rows, as_of="2026-08-07", regime_changes=changes), "b1")
    assert a.outcome == ""


def test_regime_change_is_scoped_to_its_subject():
    rows = [belief("b1", "acme", declared="2026-08-01", cadence=365),
            belief("b2", "other", declared="2026-08-01", cadence=365)]
    changes = [{"subject": "acme", "at": "2026-08-05", "what_changed": "x"}]
    got = KD.assess(rows, as_of="2026-08-07", regime_changes=changes)
    assert only(got, "b1").outcome == KD.STALE
    assert only(got, "b2").outcome == ""


# --- events are transitions, and revalidation is an event -----------------

def test_events_are_emitted_once_per_transition():
    rows = [belief("b1", "acme", declared="2025-09-01", cadence=120),
            expectation("b1", ends="2025-11-01")]
    got = KD.assess(rows, as_of="2026-01-01")
    first = KD.events(got, as_of="2026-01-01")
    assert [e.event for e in first] == [KD.STALE]
    prior = [e.as_dict() for e in first]
    again = KD.events(got, as_of="2026-01-02", prior_events=prior)
    assert again == ()          # still stale is not a second transition


def test_returning_support_emits_revalidated_and_edits_nothing():
    rows = [belief("b1", "acme", declared="2025-09-01", cadence=120),
            expectation("b1", ends="2025-11-01")]
    stale = KD.events(KD.assess(rows, as_of="2026-01-01"), as_of="2026-01-01")
    prior = [e.as_dict() for e in stale]

    rows.append(reconciliation("b1", at="2026-02-01"))
    got = KD.events(KD.assess(rows, as_of="2026-02-02"), as_of="2026-02-02",
                    prior_events=prior)
    assert [e.event for e in got] == [KD.REVALIDATED]
    # The original stale event is untouched: append-only means the record of
    # having been stale survives being current again.
    assert prior[0]["event"] == KD.STALE
    assert prior[0]["at"] == "2026-01-01"


def test_retirement_is_terminal():
    rows = [belief("b1", "acme", declared="2025-01-01", cadence=120),
            expectation("b1", ends="2025-02-01")]
    retired = KD.events(KD.assess(rows, as_of="2026-08-07"),
                        as_of="2026-08-07")
    assert [e.event for e in retired] == [KD.RETIRED]
    rows.append(reconciliation("b1", at="2026-08-06"))
    after = KD.events(KD.assess(rows, as_of="2026-08-08"), as_of="2026-08-08",
                      prior_events=[e.as_dict() for e in retired])
    assert after == ()


def test_event_ids_are_deterministic_so_a_second_pass_writes_nothing(tmp_path):
    rows = [belief("b1", "acme", declared="2025-09-01", cadence=120),
            expectation("b1", ends="2025-11-01")]
    got = KD.events(KD.assess(rows, as_of="2026-01-01"), as_of="2026-01-01")
    assert got, "fixture must actually decay, or this proves nothing"
    store = LS.LearningStore(tmp_path / "ledger.jsonl")
    assert store.record_lifecycle(got[0]) is True
    assert store.record_lifecycle(got[0]) is False
    assert len(store.lifecycle_events()) == 1


# --- the summary reports refusals, because zero is a finding --------------

def test_summary_names_why_nothing_decayed():
    rows = [belief("b1", "acme", declared="2026-08-01", cadence=120),
            expectation("b1", ends="2026-12-01")]
    got = KD.assess(rows, as_of="2026-08-07")
    out = KD.summarise(got)
    assert out["stale"] == 0
    assert out["not_eligible_because"] == {KD.WINDOW_OPEN: 1}
    assert out["next_decay_window"] == "2026-12-01"


# --- against the real ledger ---------------------------------------------

def test_real_ledger_has_no_stale_beliefs_and_the_reason_is_the_window():
    if not REAL_LEDGER.exists():                     # pragma: no cover
        return
    rows = [json.loads(line) for line in
            REAL_LEDGER.read_text().splitlines() if line.strip()]
    got = KD.assess(rows, as_of="2026-08-07")
    out = KD.summarise(got, KD.events(got, as_of="2026-08-07"))
    assert out["beliefs"] >= 51   # append-only and growing; see note below
    assert out["stale"] == 0 and out["retired"] == 0
    # The zero is earned, not assumed: every belief is refused for a NAMED
    # reason, and none of those reasons is "we did not look".
    assert sum(out["not_eligible_because"].values()) == out["beliefs"]
    assert set(out["not_eligible_because"]) <= {
        KD.WINDOW_OPEN, KD.TESTED, KD.WITHIN_CADENCE}
    # Multiple cadences are genuinely in use, so a global rule would be wrong
    # about most of them.
    assert len(out["cadences_in_use"]) >= 3
    assert out["next_decay_window"] > "2026-08-07"
