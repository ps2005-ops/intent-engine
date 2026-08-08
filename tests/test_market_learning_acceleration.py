"""Volume never sets the status. Quality gates it, in both directions.

The two tests that matter most are the ones about BLIND SPOTS, because both
came out of running this module on production's real history:

  - `self_test_rate` read 0.0 for a window in which the guard fired twenty
    times, because the module was reading belief formation's refusals
    instead of observation binding's;
  - it then read 0.8 without changing the status, because only TRENDS were
    checked and a rate that goes from undefined to 0.8 has no trend.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from intent_engine.market import learning_acceleration as LA
from intent_engine.market import learning_health as LH

MARKET_ROOT = pathlib.Path("/Users/prathamsharma/intent-engine-market")


class Obs:
    """A cycle, with only the fields a rate needs."""

    def __init__(self, **kwargs):
        defaults = dict(
            as_of="2026-08-01", cycle="night", accepted_evidence=10,
            duplicate_evidence=0, self_tests_refused=0, beliefs_accepted=1,
            beliefs_strengthened=0, beliefs_weakened=0, beliefs_retired=0,
            beliefs_decayed=0, expectations_created=1,
            expectations_evaluated=10, expectations_resolved=1,
            hidden_states_moved=0, causal_edges=0, interactions_observed=0,
            information_priorities=0, dossiers_written=1,
            companies_with_new_evidence=1, candidate_event_sentences=10,
            documents_considered=1, refused={}, binding_refused={},
            backlog_drain=False)
        defaults.update(kwargs)
        for key, value in defaults.items():
            setattr(self, key, value)


def real_observations():
    return LH.load_cycle_observations(MARKET_ROOT)


def real_ledger():
    path = MARKET_ROOT / "reports" / "market" / "learning_ledger.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()
            if line.strip()]


# --- volume alone is never acceleration ----------------------------------

def test_volume_up_with_quality_falling_is_degrading_not_accelerating():
    quiet = [Obs(accepted_evidence=5, beliefs_accepted=1,
                 expectations_resolved=1, expectations_evaluated=10)
             for _ in range(2)]
    loud = [Obs(accepted_evidence=100, beliefs_accepted=10,
                expectations_resolved=1, expectations_evaluated=10,
                self_tests_refused=50) for _ in range(2)]
    got = LA.window(quiet + loud, name="w", size=4)
    assert got.volume_direction == "UP"
    assert got.status == LA.DEGRADING
    assert got.status != LA.ACCELERATING
    assert any("self_test_rate" in d for d in got.degradations)


def test_volume_up_with_quality_steady_can_accelerate():
    quiet = [Obs(accepted_evidence=5, beliefs_accepted=1) for _ in range(2)]
    loud = [Obs(accepted_evidence=50, beliefs_accepted=5) for _ in range(2)]
    got = LA.window(quiet + loud, name="w", size=4)
    assert got.volume_direction == "UP"
    assert got.status == LA.ACCELERATING
    assert got.degradations == ()


def test_a_window_with_no_new_knowledge_is_plateauing():
    flat = [Obs(beliefs_accepted=0, expectations_resolved=0)
            for _ in range(4)]
    got = LA.window(flat, name="w", size=4)
    assert got.status == LA.PLATEAUING
    assert "nothing moved" in got.reason


# --- the things that must not count as learning --------------------------

def test_duplicate_evidence_does_not_raise_new_knowledge():
    unique = [Obs(accepted_evidence=10, duplicate_evidence=0)
              for _ in range(2)]
    dupes = [Obs(accepted_evidence=10, duplicate_evidence=90)
             for _ in range(2)]
    got = LA.window(unique + dupes, name="w", size=4)
    # Freshness collapses even though `evidence_ingested` grew tenfold.
    assert got.quality["knowledge_freshness"] < 0.5
    assert got.status == LA.DEGRADING


def test_a_backlog_drain_is_excluded_from_every_rate():
    drain = Obs(accepted_evidence=500, beliefs_accepted=50,
                backlog_drain=True)
    normal = [Obs() for _ in range(4)]
    got = LA.window([drain] + normal, name="w", size=4)
    assert got.cycles_available == 4
    assert got.metrics["unique_evidence"] == 40      # not 540
    assert LA.classify_cycle(LA._observation_metrics(drain),
                             backlog=True) == LA.RESTATEMENT


def test_a_self_test_is_read_from_observation_binding_not_formation():
    """The exact field mix-up that reported 0.0 while the guard fired 20x."""
    formation_only = Obs(
        refused={"restates_the_evidence_that_opened_it": 20})
    assert LA._observation_metrics(formation_only)["self_tests_refused"] == 0
    binding = Obs(self_tests_refused=20)
    assert LA._observation_metrics(binding)["self_tests_refused"] == 20


def test_the_real_report_sees_the_twenty_self_tests():
    got = LA.report(real_observations(), ledger=real_ledger())
    # The production runtime appends nightly, so this constant has an
    # expiry date. What is durable is that the self-tests are SEEN.
    assert got["windows"]["recent"]["metrics"]["self_tests_refused"] >= 20.0


# --- levels, not only trends ---------------------------------------------

def test_a_rate_that_was_undefined_and_is_now_bad_still_degrades():
    """No trend exists from `None`, and 0.8 is still unacceptable."""
    before = [Obs(self_tests_refused=0, expectations_resolved=0,
                  beliefs_accepted=1) for _ in range(2)]
    after = [Obs(self_tests_refused=8, expectations_resolved=1)
             for _ in range(2)]
    now = LA.quality(after)
    assert LA.degradations(LA.quality(before), now) == []   # no trend
    assert LA.absolute_failures(now)                        # but a level
    # The level fires. On this fixture's tiny denominator the verdict is
    # EARLY_WARNING rather than DEGRADING — which is the sample-size rule
    # working, not the signal being suppressed.
    got = LA.window(before + after, name="w", size=4)
    assert got.status == LA.EARLY_WARNING_STATUS
    assert got.status not in (LA.STABLE, LA.ACCELERATING)


def test_the_same_level_on_a_mature_sample_reaches_degrading():
    before = [Obs(self_tests_refused=0, expectations_resolved=0,
                  beliefs_accepted=1, expectations_evaluated=200)
              for _ in range(2)]
    after = [Obs(self_tests_refused=400, expectations_resolved=100,
                 expectations_evaluated=200) for _ in range(2)]
    got = LA.window(before + after, name="w", size=4)
    assert got.status == LA.DEGRADING


def test_absolute_limits_are_skipped_where_they_would_be_meaningless():
    """A zero contradiction rate over two reconciliations says nothing."""
    now = {"contradiction_reachability": 0.0}
    assert LA.absolute_failures(now, reconciliations=2) == []
    assert LA.absolute_failures(now, reconciliations=9)


def test_no_quality_dimension_can_exceed_one():
    for name, value in LA.quality(real_observations(),
                                  ledger=real_ledger()).items():
        if value is None or name == "source_diversity" \
                or name.startswith("_"):
            continue
        assert 0.0 <= float(value) <= 1.0, name


def test_a_share_above_one_raises_rather_than_being_clamped():
    """Found by a break proof, not by a test.

    `independent_confirmation` divided the LEDGER's distinct subjects by the
    WINDOW's reconciliations. On the real ledger the two happened to be
    equal, so nothing showed; nine subjects over one reconciliation is a
    share of 9.0. Both halves now come from the same population, which makes
    THAT dimension structurally safe — so what is proved here is the
    remaining reachable mismatch, and that the helper raises rather than
    clamping. Clamping would have turned a population error into a plausible
    number.
    """
    # More expectations refused as unfalsifiable than were ever examined.
    mismatched = [Obs(expectations_evaluated=1,
                      binding_refused={
                          "family_not_falsifiable_by_observation": 9})
                  for _ in range(2)]
    # The denominator widens to cover the numerator, so this is consistent...
    got = LA.quality(mismatched)
    assert 0.0 <= got["false_positive_rate"] <= 1.0
    # ...and the helper itself still refuses an inconsistent pair.
    with pytest.raises(ValueError, match="two different populations"):
        LA.quality([Obs(expectations_evaluated=1, expectations_resolved=9)])


# --- windows are computed only where the history defends them ------------

def test_windows_beyond_the_history_report_insufficient_with_the_real_count():
    got = LA.report(real_observations(), ledger=real_ledger())
    for name in ("7_cycle", "14_cycle", "30_cycle"):
        window = got["windows"][name]
        assert window["status"] == LA.INSUFFICIENT_HISTORY
        assert window["cycles_available"] < window["cycles_required"]
        assert str(window["cycles_available"]) in window["reason"]


def test_the_recent_window_is_the_shortest_that_can_carry_a_direction():
    assert dict(LA.WINDOWS)[LA.RECENT] == LA.MIN_CYCLES_FOR_TREND
    got = LA.window([Obs() for _ in range(4)], name="w", size=1)
    assert got.status == LA.INSUFFICIENT_HISTORY
    assert "no two halves" in got.reason
    assert got.metrics                       # counts are still reported


# --- the real history -----------------------------------------------------

def test_the_real_history_reads_degrading_on_the_self_test_rate():
    got = LA.report(real_observations(), ledger=real_ledger())
    assert got["cycles_total"] >= 6
    assert got["backlog_cycles_excluded"] == 1
    assert got["windows_computed"] == [LA.RECENT]
    assert got["status"] == LA.DEGRADING
    assert any("self_test_rate" in d for d in got["degradations"])
    assert got["quality"]["self_test_rate"] >= 0.8


# --- a rate without its denominator is not a measurement -----------------

def test_every_rate_carries_the_pair_it_came_from():
    got = LA.quality(real_observations(), ledger=real_ledger())
    pairs = got["_denominators"]
    for name in LA.QUALITY_NAMES:
        if got.get(name) is None or name == "source_diversity":
            continue
        assert name in pairs, name
        numerator, denominator = pairs[name]
        assert numerator <= denominator


def test_sample_maturity_separates_two_events_from_a_finding():
    assert LA.sample_maturity(5) == LA.INSUFFICIENT_SAMPLE
    assert LA.sample_maturity(25) == LA.EARLY
    assert LA.sample_maturity(50) == LA.USABLE
    assert LA.sample_maturity(500) == LA.MATURE


def test_a_verdict_resting_only_on_immature_samples_is_softened():
    """0.400 over five is two events. The LEVELS are unchanged; what the
    engine claims to know from them is what changes."""
    immature = ["self_test_rate=0.8 (>0.5) [4/5, INSUFFICIENT_SAMPLE]: x",
                "no_op_rate=0.9 (>0.5) [9/10, EARLY]: y"]
    assert LA._all_immature(immature)
    got, reason = LA._status("FLAT", "DOWN", immature,
                             __import__("collections").Counter(
                                 {LA.NEW_KNOWLEDGE: 1}))
    assert got == LA.EARLY_WARNING_STATUS
    assert "not softened" in reason


def test_one_mature_failure_still_justifies_degrading():
    mixed = ["self_test_rate=0.8 (>0.5) [4/5, INSUFFICIENT_SAMPLE]: x",
             "false_positive_rate 0.0 -> 0.3 [23/90, USABLE]"]
    assert not LA._all_immature(mixed)
    got, _ = LA._status("FLAT", "DOWN", mixed,
                        __import__("collections").Counter(
                            {LA.NEW_KNOWLEDGE: 1}))
    assert got == LA.DEGRADING


def test_a_trend_degradation_is_tagged_with_its_maturity_too():
    """An untagged trend would be read as mature by default."""
    got = LA.report(real_observations(), ledger=real_ledger())
    assert any("USABLE]" in d or "MATURE]" in d or "EARLY]" in d
               for d in got["degradations"])


def test_the_real_verdict_still_degrades_and_says_on_which_dimension():
    """DEGRADING is retained, and now for a stated reason: it rests on
    false_positive_rate at 23/90 (USABLE), not on the EARLY self-test rate."""
    got = LA.report(real_observations(), ledger=real_ledger())
    assert got["status"] == LA.DEGRADING
    mature = [d for d in got["degradations"]
              if "USABLE]" in d or "MATURE]" in d]
    assert mature, got["degradations"]
    assert any("self_test_rate" in d
               for d in got["degradations"])
