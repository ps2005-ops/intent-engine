"""The seven derived learning channels, and the substitutions that fake them.

Every test here corresponds to a way this layer can be made to look healthy
without the engine knowing anything more than it did:

  - count accepted evidence instead of state changes;
  - count NO_CHANGE as gain;
  - count engineering work as economic learning;
  - count published dossiers as decision value;
  - count a tidy partition as a discovery;
  - divide by a link nothing populates and call the result zero.

The last one is not hypothetical. The first version of `research_channel`
reported `0 of 14` research outcomes productive on live data, and all 14
outcomes carry an EMPTY `knowledge_effect_ids`. It was dividing by an absent
instrument and reporting the answer as a finding about research.

`test_market_learning_channels.py` covers the DECLARED movements. This file
covers the measurements DERIVED from the ledger; both use one vocabulary.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from intent_engine.market import learning_acceleration as LA
from intent_engine.market import learning_channels as LC

MARKET_ROOT = pathlib.Path("/Users/prathamsharma/intent-engine-market")
LIVE_LEDGER = MARKET_ROOT / "reports" / "market" / "learning_ledger.jsonl"


def effect(**kwargs) -> dict:
    row = dict(record="knowledge_effect", effect_id="ke_x",
               evidence_id="ev_1", target_type="BELIEF", target_id="b1",
               effect_type="CREATED", reason="because",
               created_at="2026-08-01", occurred_at="2026-08-01",
               discriminating=False)
    row.update(kwargs)
    row["changed"] = row["effect_type"] in LA.CHANGING_EFFECTS
    return row


def effects(n: int, *, effect_type: str, target_type: str = "BELIEF",
            start: int = 0) -> list:
    return [effect(effect_id=f"ke_{i + start}", evidence_id=f"ev_{i + start}",
                   effect_type=effect_type, target_type=target_type,
                   target_id=("" if effect_type == "NO_CHANGE"
                              else f"t{i + start}"))
            for i in range(n)]


# --- one vocabulary ----------------------------------------------------------

def test_the_channel_names_come_from_one_place():
    """Two vocabularies for one idea disagree the week either gains a member."""
    assert LA.CHANNELS is LC.ALL_CHANNELS
    assert LA.ECONOMIC == LC.ECONOMIC_KNOWLEDGE
    assert set(LC.MOVEMENT_CHANNELS) <= set(LA.CHANNELS)


def test_every_channel_maps_to_a_bottleneck():
    assert {channel for _, channel in LA.BOTTLENECKS} == set(LA.CHANNELS)


def test_founder_and_research_targets_are_not_economic_objects():
    """The channels are only independent if their populations are disjoint.

    A break proof caught this: widening `ECONOMIC_TARGETS` to admit
    FOUNDER_DECISION_COMPONENT and RESEARCH_QUESTION changed the economic
    numerator and nothing failed, because every test asserted names and
    counts and none asserted MEMBERSHIP. A Founder rewrite would have been
    reported as economic learning.
    """
    assert "FOUNDER_DECISION_COMPONENT" not in LA.ECONOMIC_TARGETS
    assert "RESEARCH_QUESTION" not in LA.ECONOMIC_TARGETS

    ledger = (effects(10, effect_type="CREATED",
                      target_type="FOUNDER_DECISION_COMPONENT")
              + effects(10, effect_type="CREATED",
                        target_type="RESEARCH_QUESTION", start=100))
    # Twenty state changes, none of them economic.
    assert LA.economic_channel(ledger).status == LA.UNMEASURABLE
    # And they land in the channels that own them.
    assert LA.founder_channel(ledger).numerator == 10.0


# --- the substitutions -------------------------------------------------------

def test_accepted_evidence_is_not_economic_gain():
    """300 accepted rows with no attribution is not 300 things learned."""
    ledger = [{"record": "evidence", "evidence_id": f"ev_{i}"}
              for i in range(300)]
    report = LA.economic_channel(ledger)
    assert report.status == LA.UNMEASURABLE
    assert report.rate is None
    assert "absent telemetry" in report.reason


def test_no_change_is_never_counted_as_gain():
    report = LA.economic_channel(effects(50, effect_type="NO_CHANGE"))
    assert report.numerator == 0.0
    assert report.denominator == 50.0
    assert report.rate == 0.0
    assert report.status == LA.DEGRADING


def test_system_capability_is_not_economic_gain():
    """Twenty engineering wins do not move the economic channel at all."""
    execution = [{"kind": "task", "at": "2026-08-09"} for _ in range(20)]
    combined = LA.channels(effects(50, effect_type="NO_CHANGE"),
                           execution_ledger=execution)
    assert combined[LA.SYSTEM].numerator == 20.0
    assert combined[LA.ECONOMIC].numerator == 0.0
    assert combined[LA.ECONOMIC].rate == 0.0


def test_published_dossiers_are_not_founder_value():
    """`report()` takes an int for the legacy half; the channel must not see it."""
    report = LA.report([], ledger=effects(20, effect_type="CREATED"),
                       decision_impacts=99)
    founder = report["channels"][LA.FOUNDER]
    assert founder["status"] == LA.UNMEASURABLE
    assert founder["rate"] is None
    assert "count of publications is not an answer" in founder["reason"]


def test_founder_value_reads_graded_impact_when_one_exists():
    report = LA.founder_channel(
        [], [{"impact": "DECISION_CHANGING"}, {"impact": "PRESENTATIONAL"}])
    assert report.numerator == 1.0
    assert report.denominator == 2.0
    assert report.status != LA.UNMEASURABLE


def test_unsupervised_utility_is_not_geometry():
    tidy = [{"method": "kmeans", "separation": 0.9, "coherence": 0.8,
             "stability": 0.9, "utility": None}]
    report = LA.unsupervised_channel(tidy)
    assert report.status == LA.UNMEASURABLE
    assert "not its worth" in report.reason

    report = LA.unsupervised_channel(
        tidy + [{"method": "rule", "separation": 0.2, "utility": 0.05}])
    assert report.numerator == 1.0
    # The unscored partition is not a denominator: it was never tested.
    assert report.denominator == 1.0


def test_an_absent_link_is_not_a_measured_zero():
    """The live defect: outcomes that name no effects cannot be graded."""
    ledger = ([{"record": "research_decision", "decision_id": f"d{i}"}
               for i in range(14)]
              + [{"record": "research_outcome", "decision_id": f"d{i}",
                  "status": "SUCCESS", "accepted_evidence": 11,
                  "knowledge_effect_ids": []} for i in range(14)])
    report = LA.research_channel(ledger)
    assert report.status == LA.UNMEASURABLE
    assert report.rate is None
    assert report.detail["missing_link"] == \
        "research_outcome.knowledge_effect_ids"


def test_a_populated_link_is_graded():
    ledger = ([{"record": "research_decision", "decision_id": f"d{i}"}
               for i in range(150)]
              + [{"record": "research_outcome", "decision_id": "d0",
                  "status": "SUCCESS", "knowledge_effect_ids": ["ke_0"]},
                 {"record": "research_outcome", "decision_id": "d1",
                  "status": "SUCCESS", "knowledge_effect_ids": ["ke_1"]},
                 effect(effect_id="ke_0", effect_type="CREATED"),
                 effect(effect_id="ke_1", effect_type="NO_CHANGE",
                        target_id="")])
    report = LA.research_channel(ledger)
    assert report.numerator == 1.0
    assert report.denominator == 2.0


def test_research_policy_is_blocked_below_the_decision_floor():
    ledger = ([{"record": "research_decision", "decision_id": f"d{i}"}
               for i in range(14)]
              + [{"record": "research_outcome", "decision_id": "d0",
                  "status": "SUCCESS", "knowledge_effect_ids": ["ke_0"]},
                 effect(effect_id="ke_0")])
    report = LA.research_channel(ledger)
    assert report.status == LA.INSUFFICIENT_HISTORY
    assert report.detail["policy_maturity"] == "BLOCKED_DATA"


# --- windows come from append order -----------------------------------------

def test_windows_come_from_append_order_never_from_created_at():
    """Effects dated months apart, appended in ONE cycle, are one cycle."""
    ledger = [effect(effect_id="ke_a", created_at="2026-02-10"),
              effect(effect_id="ke_b", created_at="2026-05-10"),
              effect(effect_id="ke_c", created_at="2026-08-10"),
              {"record": "cycle", "cycle_id": "2026-08-10|night"}]
    assert len(LA.cycle_segments(ledger)) == 1
    assert LA.economic_channel(ledger).detail["cycles_with_effects"] == 1


def test_an_open_cycle_is_kept_as_its_own_segment():
    ledger = [effect(effect_id="ke_a"),
              {"record": "cycle", "cycle_id": "c1"},
              effect(effect_id="ke_b")]
    segments = LA.cycle_segments(ledger)
    assert len(segments) == 2
    assert segments[-1][-1]["effect_id"] == "ke_b"


def test_a_cycle_that_attributed_nothing_is_still_a_cycle():
    ledger = [{"record": "evidence"}, {"record": "cycle", "cycle_id": "c1"},
              effect(effect_id="ke_a"), {"record": "cycle", "cycle_id": "c2"}]
    assert len(LA._effect_cycles(ledger)) == 2
    assert LA._effect_cycles(ledger)[0] == []


# --- rates, denominators, maturity ------------------------------------------

def test_a_rate_never_exceeds_one():
    report = LA.economic_channel(effects(10, effect_type="CREATED"))
    assert report.rate == 1.0
    assert report.numerator <= report.denominator


def test_zero_denominator_is_unmeasurable_not_zero():
    for channel in (LA.economic_channel([]), LA.calibration_channel([]),
                    LA.retention_channel([]), LA.research_channel([]),
                    LA.unsupervised_channel([]), LA.system_channel([])):
        assert channel.status == LA.UNMEASURABLE
        assert channel.rate is None


def test_a_small_sample_cannot_carry_degrading():
    """Five NO_CHANGE effects look terrible and prove nothing."""
    report = LA.economic_channel(effects(5, effect_type="NO_CHANGE"))
    assert report.rate == 0.0
    assert report.status == LA.EARLY_WARNING_STATUS
    assert report.maturity == LA.INSUFFICIENT_SAMPLE


def test_maturity_thresholds_are_carried_not_assumed():
    assert LA.sample_maturity(9) == LA.INSUFFICIENT_SAMPLE
    assert LA.sample_maturity(10) == LA.EARLY
    assert LA.sample_maturity(30) == LA.USABLE
    assert LA.sample_maturity(100) == LA.MATURE


# --- retention ---------------------------------------------------------------

def test_an_orphaned_change_is_a_retention_failure():
    ledger = effects(40, effect_type="CREATED")
    for row in ledger[:20]:
        row["target_id"] = ""
    report = LA.retention_channel(ledger)
    assert report.detail["orphaned"] == 20
    assert report.status == LA.DEGRADING


def test_a_duplicate_id_is_a_storage_fault():
    ledger = effects(20, effect_type="CREATED")
    ledger.append(dict(ledger[0]))
    assert LA.retention_channel(ledger).detail["duplicate_ids"] == 1


# --- high activity, low learning --------------------------------------------

def test_high_activity_low_learning_is_named():
    ledger = ([{"record": "evidence", "evidence_id": f"ev_{i}"}
               for i in range(120)]
              + effects(105, effect_type="NO_CHANGE")
              + effects(5, effect_type="CREATED", start=200))
    activity = LA.high_activity_low_learning(ledger)
    assert activity["detected"] is True
    assert activity["effects_that_changed_nothing"] == 105
    assert activity["thesis_transitions"] == 0


def test_a_healthy_share_is_not_flagged():
    ledger = (effects(50, effect_type="NO_CHANGE")
              + effects(50, effect_type="CREATED", start=100))
    assert LA.high_activity_low_learning(ledger)["detected"] is False


def test_low_share_on_a_tiny_sample_is_not_flagged():
    assert LA.high_activity_low_learning(
        effects(5, effect_type="NO_CHANGE"))["detected"] is False


# --- bottleneck --------------------------------------------------------------

def test_the_bottleneck_is_computed_not_declared():
    """An UNMEASURABLE channel outranks a DEGRADING one."""
    limit = LA.bottleneck(LA.channels(effects(50, effect_type="NO_CHANGE")))
    assert limit["status"] == LA.UNMEASURABLE
    assert limit["bottleneck"] in {name for name, _ in LA.BOTTLENECKS}
    assert len(limit["ranking"]) == len(LA.BOTTLENECKS)


def test_the_bottleneck_moves_when_the_dark_channels_light_up():
    ledger = (effects(50, effect_type="NO_CHANGE")
              + [{"record": "reconciliation", "outcome": "CONFIRMED"}])
    lit = LA.channels(
        ledger,
        execution_ledger=[{"kind": "task", "at": "2026-08-08"},
                          {"kind": "task", "at": "2026-08-09"}],
        decision_impacts=[{"impact": "MEANINGFUL"}],
        discoveries=[{"method": "rule", "utility": 0.1}])
    assert LA.bottleneck(lit)["bottleneck"] != \
        LA.bottleneck(LA.channels(ledger))["bottleneck"]


# --- the report contract -----------------------------------------------------

def test_report_carries_all_seven_channels_independently():
    report = LA.report([], ledger=effects(20, effect_type="CREATED"))
    assert set(report["channels"]) == set(LA.CHANNELS)
    assert "bottleneck" in report
    assert "high_activity_low_learning" in report
    # No blended score anywhere: a mean of seven is a way of not answering.
    assert "composite" not in report
    assert "overall_score" not in report


def test_channels_are_split_into_measurable_and_dark():
    report = LA.report([], ledger=effects(20, effect_type="CREATED"))
    measurable = set(report["channels_measurable"])
    dark = set(report["channels_unmeasurable"])
    assert measurable | dark == set(LA.CHANNELS)
    assert not (measurable & dark)


def test_operator_summary_names_the_dark_channels():
    report = LA.report([], ledger=effects(20, effect_type="CREATED"))
    text = " ".join(report["operator_summary"])
    assert "Nothing measures" in text
    assert "absent instruments, not zero results" in text


def test_the_legacy_windows_still_report():
    """The channels are additive: the volume/quality half is untouched."""
    report = LA.report([], ledger=effects(20, effect_type="CREATED"))
    assert set(report["windows"]) == {name for name, _ in LA.WINDOWS}
    assert report["contract"] == LA.CONTRACT


# --- against the real ledger -------------------------------------------------

@pytest.mark.skipif(not LIVE_LEDGER.exists(), reason="no live ledger")
def test_the_live_ledger_reads_as_high_activity_low_learning():
    """Production, pinned as a SHAPE rather than as numbers.

    The counts move every night, so this asserts what must remain true of
    them rather than a snapshot that goes red on an ordinary cycle.
    """
    rows = [json.loads(line) for line in
            LIVE_LEDGER.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    reports = LA.channels(rows)
    economic = reports[LA.ECONOMIC]
    assert economic.denominator >= 100
    assert reports[LA.FOUNDER].status == LA.UNMEASURABLE
    for channel in reports.values():
        if channel.rate is not None:
            assert channel.rate <= 1.0
            assert channel.numerator <= channel.denominator


@pytest.mark.skipif(not LIVE_LEDGER.exists(), reason="no live ledger")
def test_live_effects_span_one_write_cycle_not_seven_months():
    """`created_at` spans months; append order says the log is much younger.

    If this fails because the segment count rose, that is real history
    accumulating and the assertion should be revisited. If it fails because
    it jumped to dozens, someone started reading a date field.
    """
    rows = [json.loads(line) for line in
            LIVE_LEDGER.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    effect_rows = [r for r in rows if r.get("record") == "knowledge_effect"]
    months = {str(r.get("created_at"))[:7] for r in effect_rows}
    cycles_with_effects = sum(1 for c in LA._effect_cycles(rows) if c)
    assert len(months) > 3, "the live corpus should still span months"
    assert cycles_with_effects < len(months)


# --- the founder channel's three states -------------------------------------

def _impact(materiality: str, n: int = 0) -> dict:
    return {"record": "decision_impact", "materiality": materiality,
            "decision_impact_id": f"di_{materiality}_{n}",
            "company_id": f"c{n}", "changed": materiality not in
            ("NONE", "FIRST_OBSERVATION")}


def test_no_impact_record_at_all_is_unmeasurable():
    report = LA.founder_channel([], [])
    assert report.status == LA.UNMEASURABLE
    assert "count of publications is not an answer" in report.reason


def test_only_first_observations_is_a_different_unmeasurable():
    """The instrument exists and has no second revision to compare against.

    Collapsing this into the reason above would hide that it clears itself
    on the next dossier that differs.
    """
    report = LA.founder_channel(
        [], [_impact("FIRST_OBSERVATION", i) for i in range(25)])
    assert report.status == LA.UNMEASURABLE
    assert "first observation" in report.reason
    assert report.detail["first_observations"] == 25
    assert report.detail["impact_claims"] == 0


def test_a_first_observation_enters_neither_side_of_the_rate():
    """Counting it in the numerator produced 25 of 25; counting it in the
    denominator would swing the same metric to near zero on a first run."""
    report = LA.founder_channel(
        [], [_impact("DECISION_CHANGING", 1), _impact("NONE", 2)]
        + [_impact("FIRST_OBSERVATION", i) for i in range(20)])
    assert report.numerator == 1.0
    assert report.denominator == 2.0
    assert report.detail["first_observations"] == 20


def test_the_channel_reads_materiality():
    report = LA.founder_channel([], [_impact("MEANINGFUL", 1)])
    assert report.numerator == 1.0
    assert report.denominator == 1.0
