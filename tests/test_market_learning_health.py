"""Market learning health — the contract, and the refusals that make it useful.

The tests that matter most here are the REFUSALS. A learning dashboard that
reports a number for everything is easy to build and worthless: every one of
these metrics has a state in which the honest answer is "not measurable yet",
and a dashboard that renders that state as `0.0` will be believed.

So the assertions below are mostly about what the module declines to say:
declines to call four days a trend, declines to call an untested belief
survived, declines to call a backlog drain a rate, declines to call a stage
healthy because the aggregate hides it.
"""
import json
import pathlib

import pytest

from intent_engine.market import learning_health as LH
from intent_engine.market import observation_binding as OB


# ===========================================================================
# helpers
# ===========================================================================
def obs(as_of, cycle="day", **kw):
    return LH.CycleObservation(as_of=as_of, cycle=cycle, **kw)


def series(n, *, start_day=1, **kw):
    return [obs(f"2026-08-{start_day + i:02d}", **kw) for i in range(n)]


class _FakeStore:
    """A ledger stand-in. `assess` reads rows, so rows are all it needs."""

    def __init__(self, rows):
        self._store_rows = rows

    def _rows(self):
        return self._store_rows


def _store(tmp_path, *, beliefs=0, expectations=0, reconciliations=0,
           contradicted=0):
    rows = []
    for i in range(beliefs):
        rows.append({"record": "belief", "belief_id": f"b{i}",
                     "subject": "acme", "last_updated": "2026-08-01",
                     "lifecycle_state": "ACTIVE"})
    for i in range(expectations):
        rows.append({"record": "expectation", "expectation_id": f"e{i}",
                     "hypothesis_id": f"b{i}", "subject": "acme",
                     "metric": "demand_strengthening",
                     "preregistered_at": "2026-08-01",
                     "evaluation_window_ends": "2026-12-01"})
    for i in range(reconciliations):
        rows.append({
            "record": "reconciliation", "expectation_id": f"e{i}",
            "hypothesis_id": f"b{i}", "subject": "acme",
            "evaluated_at": "2026-08-06",
            "outcome": "CONTRADICTED" if i < contradicted else "CONFIRMED"})
    return _FakeStore(rows)


def _write_reports(root, entries):
    """Persist minimal cycle reports carrying a learning block."""
    directory = root / "reports" / "market"
    directory.mkdir(parents=True, exist_ok=True)
    for as_of, cycle, counts in entries:
        payload = {
            "as_of": as_of, "cycle": cycle,
            "translation": {"documents_considered": 100,
                            "candidate_sentences": 200,
                            "classification_by_type": {"EARNINGS_RESULT": 10}},
            "learning": {
                "as_of": as_of,
                "belief_formation": {"candidates": counts.get("candidates", 0),
                                     "expectations": counts.get("new", 0)},
                "belief_learning": {"new": counts.get("new", 0),
                                    "beliefs_total": counts.get("new", 0)},
                "expected_vs_observed": {"evaluated": 0, "informative": 0,
                                         "by_outcome": {}},
            },
        }
        (directory / f"{as_of}_{cycle}.json").write_text(
            json.dumps(payload), encoding="utf-8")


# ===========================================================================
# UNMEASURABLE — the central discipline
# ===========================================================================
def test_rate_with_empty_denominator_is_unmeasurable_not_zero():
    """Zero over zero is not zero, and the difference is the whole point."""
    assert LH._rate(0, 0) == LH.UNMEASURABLE
    assert LH._rate(3, 0) == LH.UNMEASURABLE
    assert LH._rate(0, 4) == 0.0


def test_calibration_is_unmeasurable_below_the_minimum_sample(tmp_path):
    store = _store(tmp_path, beliefs=3, expectations=3, reconciliations=0)
    health = LH.assess(root=tmp_path, as_of="2026-08-07", store=store)
    cal = health.calibration
    assert cal["expectation_calibration"] == LH.UNMEASURABLE
    assert cal["false_positive_rate"] == LH.UNMEASURABLE
    assert cal["effective_sample_size"] == 0
    # and it says WHY, so nobody reads the sentinel as a bug
    assert "minimum" in cal["because"]


def test_calibration_becomes_measurable_at_the_threshold(tmp_path):
    store = _store(tmp_path, beliefs=6, expectations=6,
                   reconciliations=6, contradicted=2)
    health = LH.assess(root=tmp_path, as_of="2026-08-07", store=store)
    cal = health.calibration
    assert cal["effective_sample_size"] == 6
    assert cal["expectation_calibration"] == pytest.approx(4 / 6)
    assert cal["false_positive_rate"] == pytest.approx(2 / 6)


# ===========================================================================
# INSUFFICIENT HISTORY — never invent acceleration
# ===========================================================================
def test_classify_refuses_a_verdict_without_enough_cycles():
    """Two cycles is not a trend, and the operator is told which lack it is.

    The status alone under-specifies this: a missing prior window ALSO
    produces INSUFFICIENT_HISTORY, so asserting only the status leaves the
    cycle-count guard unpinned — a mutation deleting it stayed green until
    this test also read the reason. The two lacks take different responses
    (wait for more cycles vs. wait for a full window), so the explanation is
    the part that has to be right.
    """
    result = LH.classify(series(2, accepted_evidence=5), as_of="2026-08-07")
    assert result["status"] == LH.NO_HISTORY
    assert result["cycles_available"] == 2
    assert "comparable cycles on record" in result["because"]


def test_acceleration_without_a_prior_window_is_insufficient_history():
    # Four cycles all inside the CURRENT 7-day window: there is no prior
    # window, so no rate can be compared to anything.
    result = LH.acceleration(series(4, start_day=4, accepted_evidence=5),
                             as_of="2026-08-07", days=7)
    assert result["status"] == LH.NO_HISTORY
    assert result["series"] == {}


def test_ninety_day_window_is_unmeasurable_on_a_young_engine():
    v = LH.velocity(series(4, accepted_evidence=5), as_of="2026-08-07",
                    days=90, offset=1)
    assert v["measurable"] is False
    assert v["accepted_evidence"] == LH.UNMEASURABLE


# ===========================================================================
# BACKLOG DRAIN — quantity that is not a rate
# ===========================================================================
def test_backlog_drain_cycle_is_excluded_from_velocity():
    """35 -> 7 -> 3 -> 1 is not a collapse if the 35 was a standing pool.

    This is the real series the live engine produced on its first four
    pipeline cycles. Counting the first one as a daily rate makes every
    later cycle look like a degradation.
    """
    drain = obs("2026-08-04", beliefs_accepted=35, backlog_drain=True)
    normal = [obs("2026-08-05", beliefs_accepted=7),
              obs("2026-08-06", beliefs_accepted=3),
              obs("2026-08-07", beliefs_accepted=1)]
    v = LH.velocity([drain] + normal, as_of="2026-08-07", days=7)
    assert v["cycles"] == 3               # the drain is not counted
    assert v["beliefs_accepted"] == pytest.approx(11 / 7)


def test_loader_marks_only_the_first_belief_forming_cycle_as_drain(tmp_path):
    _write_reports(tmp_path, [
        ("2026-08-05", "night", {"new": 35, "candidates": 35}),
        ("2026-08-06", "day", {"new": 7, "candidates": 7}),
        ("2026-08-07", "day", {"new": 1, "candidates": 1}),
    ])
    loaded = LH.load_cycle_observations(tmp_path)
    assert [o.backlog_drain for o in loaded] == [True, False, False]


# ===========================================================================
# BOTTLENECK DETECTION
# ===========================================================================
def test_total_blockage_outranks_a_larger_absolute_loss():
    """A stage nothing leaves starves everything below it.

    The evidence stage loses far more items in absolute terms, but the
    expectation stage lets nothing through at all, and no amount of fixing
    evidence yield helps while that is true.
    """
    cycles = series(4, documents_considered=1000,
                    candidate_event_sentences=900, accepted_evidence=50,
                    belief_candidates=10, beliefs_accepted=10,
                    expectations_created=10, expectations_evaluated=10,
                    expectations_too_early=10)
    result = LH.funnel(cycles)
    assert result["bottleneck"]["stage"] == "expectations_due"
    assert result["bottleneck"]["total_blockage"] is True


def test_earliest_total_block_is_named_not_the_last():
    """A later empty stage is a symptom of the first, not a second fault."""
    cycles = series(4, documents_considered=100,
                    candidate_event_sentences=50, accepted_evidence=0)
    result = LH.funnel(cycles)
    assert result["bottleneck"]["stage"] == "accepted_evidence"


def test_bottleneck_is_not_ranked_from_a_single_cycle():
    """One cycle cannot distinguish a broken stage from a quiet day."""
    single = [obs("2026-08-07", documents_considered=10,
                  candidate_event_sentences=10, accepted_evidence=10,
                  belief_candidates=10, beliefs_accepted=10,
                  expectations_created=10, expectations_evaluated=10,
                  expectations_too_early=10)]
    result = LH.classify(single, as_of="2026-08-07",
                         bottleneck=LH.funnel(single).get("bottleneck"))
    # A funnel exists, but the STATUS still refuses to generalise from one day.
    assert result["status"] == LH.NO_HISTORY


def test_maturity_and_observability_are_told_apart():
    """Same funnel, opposite fixes. Distinguished by whether evidence landed."""
    expectations = [{"expectation_id": "e1", "subject": "acme",
                     "preregistered_at": "2026-08-01",
                     "evaluation_window_ends": "2026-12-01"}]

    nothing_arrived = LH.why_unscoreable(expectations, [], as_of="2026-08-07")
    assert nothing_arrived["cause"] == "EXPECTATION_MATURITY"

    answer_was_there = LH.why_unscoreable(
        expectations,
        [{"subject_company": "acme", "observed_at": "2026-08-05"}],
        as_of="2026-08-07")
    assert answer_was_there["cause"] == "OUTCOME_OBSERVABILITY"
    assert answer_was_there["answerable_now"] == 1


def test_evidence_predating_preregistration_does_not_prove_observability():
    """Retrodiction is not an available observation."""
    expectations = [{"expectation_id": "e1", "subject": "acme",
                     "preregistered_at": "2026-08-05",
                     "evaluation_window_ends": "2026-12-01"}]
    result = LH.why_unscoreable(
        expectations,
        [{"subject_company": "acme", "observed_at": "2026-07-01"}],
        as_of="2026-08-07")
    assert result["cause"] == "EXPECTATION_MATURITY"


# ===========================================================================
# QUANTITY IS NOT QUALITY — cohort survival
# ===========================================================================
def test_untested_belief_does_not_count_as_survived():
    """A belief nothing has challenged has not survived anything."""
    beliefs = [{"belief_id": "b1", "subject": "acme",
                "last_updated": "2026-08-01", "lifecycle_state": "ACTIVE"}]
    (cohort,) = LH.cohorts(beliefs, [])
    assert cohort.size == 1
    assert cohort.tested == 0
    assert cohort.never_tested == 1
    # survival is a ratio over TESTED beliefs, so it is unmeasurable here
    assert cohort.as_dict()["survival_rate"] == LH.UNMEASURABLE
    assert cohort.as_dict()["test_rate"] == 0.0


def test_a_hundred_untested_beliefs_beat_nothing_on_no_quality_metric():
    """The cycle that adds 100 must not outrank the cycle that adds 2."""
    many = [{"belief_id": f"b{i}", "subject": "acme",
             "last_updated": "2026-08-01", "lifecycle_state": "ACTIVE"}
            for i in range(100)]
    (cohort,) = LH.cohorts(many, [])
    assert cohort.size == 100
    assert cohort.as_dict()["survival_rate"] == LH.UNMEASURABLE


def test_belief_supported_then_contradicted_is_a_reversal():
    beliefs = [{"belief_id": "b1", "subject": "acme",
                "last_updated": "2026-08-01", "lifecycle_state": "ACTIVE"}]
    recs = [{"hypothesis_id": "b1", "outcome": "CONFIRMED"},
            {"hypothesis_id": "b1", "outcome": "CONTRADICTED"}]
    (cohort,) = LH.cohorts(beliefs, recs)
    assert cohort.tested == 1
    assert cohort.reversed_later == 1
    assert cohort.still_supported == 0


# ===========================================================================
# ALERTS
# ===========================================================================
def test_no_alert_fires_below_the_minimum_cycle_count():
    health = LH.LearningHealth(as_of="2026-08-07")
    health.expectation = {"expectations_total": 10,
                          "expectations_confirmed": 0,
                          "expectations_contradicted": 0}
    assert LH.alerts(series(2), health) == []


def test_belief_testing_stalled_fires_when_nothing_ever_resolved():
    health = LH.LearningHealth(as_of="2026-08-07")
    health.expectation = {"expectations_total": 46,
                          "expectations_confirmed": 0,
                          "expectations_contradicted": 0}
    fired = {a["alert"] for a in LH.alerts(series(4), health)}
    assert LH.BELIEF_TESTING_STALLED in fired


def test_belief_testing_alert_clears_once_something_resolves():
    """The alert must read the LEDGER, not the cycle reports.

    A reconciliation written this session is real even though the report
    mentioning it does not exist yet. An alert wired to the reports would go
    on insisting nothing had ever been tested.
    """
    health = LH.LearningHealth(as_of="2026-08-07")
    health.expectation = {"expectations_total": 46,
                          "expectations_confirmed": 8,
                          "expectations_contradicted": 2}
    fired = {a["alert"] for a in LH.alerts(series(4), health)}
    assert LH.BELIEF_TESTING_STALLED not in fired
    assert LH.EXPECTATION_BACKLOG_GROWING not in fired


def test_pipeline_stage_regression_is_visible_despite_healthy_totals():
    """One broken stage must not be hidden by the aggregate.

    Earlier cycles converted; recent ones convert nothing. The summed funnel
    still shows successes and looks fine.
    """
    early = [obs(f"2026-08-0{i}", beliefs_accepted=10,
                 expectations_created=10) for i in (1, 2)]
    late = [obs(f"2026-08-0{i}", beliefs_accepted=10,
                expectations_created=0) for i in (3, 4)]
    health = LH.LearningHealth(as_of="2026-08-07")
    health.expectation = {"expectations_total": 20,
                          "expectations_confirmed": 5,
                          "expectations_contradicted": 5}
    fired = {a["alert"] for a in LH.alerts(early + late, health)}
    assert LH.PIPELINE_STAGE_REGRESSION in fired


def test_founder_utility_alert_when_nothing_is_published():
    health = LH.LearningHealth(as_of="2026-08-07")
    health.expectation = {"expectations_total": 4,
                          "expectations_confirmed": 2,
                          "expectations_contradicted": 2}
    health.founder_utility = {"strategic_dossiers_written": 0}
    fired = {a["alert"] for a in LH.alerts(series(4), health)}
    assert LH.FOUNDER_UTILITY_DROPPING in fired


# ===========================================================================
# STATUS
# ===========================================================================
def test_accumulating_without_validating_is_a_plateau_not_health():
    """Rows rising while nothing is ever confirmed is not learning."""
    cycles = [obs(f"2026-07-{d:02d}", accepted_evidence=20,
                  beliefs_accepted=5, expectations_created=5)
              for d in (25, 26, 27, 28, 29, 30, 31)] + \
             [obs(f"2026-08-{d:02d}", accepted_evidence=20,
                  beliefs_accepted=5, expectations_created=5)
              for d in (1, 2, 3, 4, 5, 6, 7)]
    result = LH.classify(cycles, as_of="2026-08-07")
    assert result["status"] == LH.PLATEAU
    assert "accumulating" in result["because"]


def test_status_vocabulary_is_closed():
    for cycles in ([], series(2), series(8)):
        result = LH.classify(cycles, as_of="2026-08-07")
        assert result["status"] in LH.STATUS_CLASSES


def test_no_new_evidence_is_not_reported_as_degradation():
    """A quiet market is not a broken engine."""
    cycles = [obs(f"2026-07-{d:02d}", accepted_evidence=20, beliefs_accepted=2)
              for d in (25, 26, 27, 28)] + \
             [obs(f"2026-08-{d:02d}", accepted_evidence=0)
              for d in (5, 6, 7)]
    result = LH.classify(cycles, as_of="2026-08-07")
    assert result["status"] == LH.NO_NEW_EVIDENCE


# ===========================================================================
# GLOBAL vs WATCHLIST
# ===========================================================================
def test_watchlist_and_global_coverage_are_reported_separately():
    evidence = [{"subject_company": "acme", "evidence_type": "EARNINGS_RESULT"},
                {"subject_company": "wayne", "evidence_type": "LAYOFF"},
                {"subject_company": "stark", "evidence_type": "LAYOFF"}]
    result = LH.coverage(evidence, [], watchlist=["acme", "umbrella"])
    assert result["global"]["companies_observed"] == 3
    assert result["watchlist"]["companies_with_evidence"] == 1
    assert result["watchlist"]["coverage_rate"] == pytest.approx(0.5)
    # the two companies that are NOT on the watchlist stay visible
    assert result["off_watchlist_companies_observed"] == 2


def test_watchlist_gain_cannot_hide_global_collapse():
    """Perfect watchlist coverage over a collapsed universe must be visible."""
    evidence = [{"subject_company": "acme", "evidence_type": "LAYOFF"}]
    result = LH.coverage(evidence, [], watchlist=["acme"])
    assert result["watchlist"]["coverage_rate"] == 1.0
    assert result["global"]["companies_observed"] == 1
    assert result["off_watchlist_companies_observed"] == 0


# ===========================================================================
# HISTORY
# ===========================================================================
def test_snapshot_is_append_only_and_idempotent_per_day(tmp_path):
    health = LH.LearningHealth(as_of="2026-08-07")
    health.status = {"status": LH.PLATEAU}
    assert LH.append_snapshot(health, root=tmp_path) is True
    assert LH.append_snapshot(health, root=tmp_path) is False
    assert len(LH.read_history(tmp_path)) == 1

    later = LH.LearningHealth(as_of="2026-08-08")
    later.status = {"status": LH.HEALTHY}
    assert LH.append_snapshot(later, root=tmp_path) is True

    history = LH.read_history(tmp_path)
    assert [r["as_of"] for r in history] == ["2026-08-07", "2026-08-08"]
    # yesterday is not rewritten by today
    assert history[0]["status"] == LH.PLATEAU


def test_history_survives_a_corrupt_line(tmp_path):
    path = tmp_path / LH.HISTORY_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"as_of": "2026-08-01"}\nnot json\n', encoding="utf-8")
    assert len(LH.read_history(tmp_path)) == 1


# ===========================================================================
# OBSERVATION BINDING — the bottleneck fix
# ===========================================================================
def test_only_falsifiable_families_are_bound():
    """A test that cannot fail is not a test.

    `capacity_expansion` is confirmed by a capex announcement and refuted by
    nothing observable, so binding it would build a ratchet that drives every
    posterior to 1.0 and calls it learning.
    """
    assert "demand_strengthening" in OB.FALSIFIABLE
    assert "demand_weakening" in OB.FALSIFIABLE
    assert "capacity_expansion" not in OB.FALSIFIABLE
    assert "procurement_momentum" not in OB.FALSIFIABLE


def test_relevance_comes_from_type_and_verdict_from_direction():
    """The contradicting observation must be reachable.

    `routes_for` answers "what would this evidence propose" — a DOWN earnings
    result proposes demand_weakening and so would never be offered as a test
    of demand_strengthening, which is exactly the belief it refutes. Measured
    when this was wrong: 8 bound, 8 confirmed, 0 contradicted.
    """
    types = OB.types_testing("demand_strengthening")
    assert "EARNINGS_RESULT" in types
    assert "GUIDANCE_REVISION" in types


def _evidence(evidence_id, fact, *, etype="EARNINGS_RESULT",
              subject="acme", observed_at="2026-08-05"):
    from intent_engine.market import micro_evidence as ME
    return ME.MicroEvidence(
        evidence_id=evidence_id, subject_company=subject, actor=subject,
        evidence_type=etype, observed_at=observed_at,
        available_at=observed_at, source="https://example.test/x", fact=fact)


def _expectation(expectation_id, *, metric="demand_strengthening",
                 direction="UP", basis=(), subject="acme"):
    from intent_engine.market import expectation as EXP
    return EXP.ExpectedObservation(
        expectation_id=expectation_id, hypothesis_id="b1", subject=subject,
        expected_event="the next reported revenue figure",
        expected_direction=direction, preregistered_at="2026-08-01",
        evaluation_window_ends="2026-12-01", falsifier="a lower figure",
        metric=metric, evidence_basis=tuple(basis))


def test_binding_produces_a_contradiction_when_evidence_points_the_other_way():
    """The whole point: a bound observation must be able to refute."""
    from intent_engine.market import expectation as EXP
    exp = _expectation("e1")
    ev = [_evidence("ev1", "Revenue fell sharply and guidance was cut")]
    bound, _ = OB.bind([exp], ev, as_of="2026-08-07")
    assert bound["e1"]["observed_direction"] == EXP.DOWN

    result = EXP.reconcile(exp, as_of="2026-08-07", **{
        k: v for k, v in bound["e1"].items() if k != "binding"})
    assert result.outcome == EXP.CONTRADICTED


def test_binding_confirms_when_evidence_points_the_expected_way():
    from intent_engine.market import expectation as EXP
    exp = _expectation("e1")
    ev = [_evidence("ev1", "Revenue rose and the company raised guidance")]
    bound, _ = OB.bind([exp], ev, as_of="2026-08-07")
    result = EXP.reconcile(exp, as_of="2026-08-07", **{
        k: v for k, v in bound["e1"].items() if k != "binding"})
    assert result.outcome == EXP.CONFIRMED


def test_the_evidence_that_proposed_a_belief_never_tests_it():
    """Otherwise every belief confirms itself the moment it is declared."""
    exp = _expectation("e1", basis=("ev1",))
    ev = [_evidence("ev1", "Revenue rose strongly")]
    bound, refused = OB.bind([exp], ev, as_of="2026-08-07")
    assert bound == {}
    assert refused["evidence_proposed_this_expectation"] == 1


def test_evidence_about_another_company_never_binds():
    exp = _expectation("e1", subject="acme")
    ev = [_evidence("ev1", "Revenue rose strongly", subject="wayne")]
    bound, _ = OB.bind([exp], ev, as_of="2026-08-07")
    assert bound == {}


def test_evidence_predating_preregistration_never_binds():
    """Retrodiction is refused before reconcile is even asked."""
    exp = _expectation("e1")
    ev = [_evidence("ev1", "Revenue rose strongly", observed_at="2026-07-01")]
    bound, _ = OB.bind([exp], ev, as_of="2026-08-07")
    assert bound == {}


def test_the_earliest_qualifying_observation_wins_not_the_kindest():
    """Choosing among candidates is where scoring becomes flattering."""
    exp = _expectation("e1")
    ev = [_evidence("ev_late", "Revenue rose strongly",
                    observed_at="2026-08-06"),
          _evidence("ev_early", "Revenue fell and guidance was cut",
                    observed_at="2026-08-02")]
    bound, _ = OB.bind([exp], ev, as_of="2026-08-07")
    assert bound["e1"]["evidence_ids"] == ("ev_early",)


def test_unfalsifiable_family_is_refused_with_a_reason():
    exp = _expectation("e1", metric="capacity_expansion")
    ev = [_evidence("ev1", "The company raised capex plans",
                    etype="CAPEX_SIGNAL")]
    bound, refused = OB.bind([exp], ev, as_of="2026-08-07")
    assert bound == {}
    assert refused["family_not_falsifiable_by_observation"] == 1


def test_evidence_with_no_readable_direction_is_not_a_verdict():
    exp = _expectation("e1")
    ev = [_evidence("ev1", "The company reported its quarterly results")]
    bound, refused = OB.bind([exp], ev, as_of="2026-08-07")
    assert bound == {}
    assert refused["no_readable_direction"] == 1


# ===========================================================================
# BREAK-PROOF TARGETS — each of these is the assertion a specific mutation
# must trip. They are listed together because they are the ones that would
# let the engine flatter itself.
# ===========================================================================
def test_a_declared_belief_is_not_validated_knowledge():
    """Declaring is not learning. Only a tested belief counts.

    Otherwise the fastest way to a rising knowledge curve is to lower the
    bar for declaring beliefs, which is the exact opposite of learning.
    """
    declared = obs("2026-08-07", beliefs_accepted=50)
    assert declared.validated_knowledge == 0

    tested = obs("2026-08-07", beliefs_accepted=0, beliefs_strengthened=1,
                 beliefs_weakened=1, beliefs_retired=1)
    assert tested.validated_knowledge == 3


def test_duplicate_evidence_is_not_counted_as_new_knowledge():
    """A cycle that re-ingests the same facts has learned nothing."""
    duplicates = obs("2026-08-07", accepted_evidence=100,
                     duplicate_evidence=100)
    assert duplicates.validated_knowledge == 0


def test_stale_and_never_validated_beliefs_are_reported(tmp_path):
    """A belief nothing has revisited must be visibly stale, not silently ok."""
    store = _store(tmp_path, beliefs=4, expectations=4)
    health = LH.assess(root=tmp_path, as_of="2026-08-07", store=store)
    assert health.belief["beliefs_without_recent_support"] == 4
    assert health.belief["beliefs_never_tested"] == 4
    assert health.knowledge["revalidated_knowledge"] == 0


def test_expectation_backlog_alert_fires_when_nothing_ever_resolves():
    health = LH.LearningHealth(as_of="2026-08-07")
    health.expectation = {"expectations_total": 46,
                          "expectations_confirmed": 0,
                          "expectations_contradicted": 0}
    fired = {a["alert"] for a in LH.alerts(series(4), health)}
    assert LH.EXPECTATION_BACKLOG_GROWING in fired
