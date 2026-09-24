"""Health becomes an action, and a source is chosen by predicate first.

The two properties worth holding:

  - a family that cannot answer a question is excluded however well it
    scores, because the families are not substitutes;
  - a DEGRADING learning status whose dominant self-test class is
    re-reading actually CHANGES the plan. A health metric that changes no
    behaviour is a dashboard.
"""
from __future__ import annotations

import json
import pathlib

from intent_engine.market import learning_acceleration as LA
from intent_engine.market import observation_binding as OB
from intent_engine.market import research_planning as RP

# Vendored into the repo in wave 8. It previously pointed at another
# session's scratchpad behind an `if not exists: return`, so the day that
# directory was cleaned the assertions below would have stopped running
# without anything going red.
MEASURED = pathlib.Path(__file__).resolve().parents[1] / \
    "reports/market/strategic/source_family_measurement.json"
ACQUIRED = pathlib.Path(__file__).resolve().parents[1] / \
    "reports/market/strategic/wave8_acquisition.json"


def perf(family, *, retrieved=50, yield_=0.2, latency=10.0, actors=3):
    return RP.SourceFamilyPerformance(
        source_family=family, retrieved=retrieved, attempts=28,
        useful=int(retrieved * yield_), relationship_yield=yield_,
        distinct_actors=actors,
        latency_seconds=latency, last_updated="2026-08-07")


REAL = [perf("government_award", retrieved=64, yield_=0.172, latency=16.5),
        perf("customer_case_study", retrieved=22, yield_=0.500, latency=311.0),
        perf("partnership_release", retrieved=59, yield_=0.051, latency=521.0)]


# --- predicate first, yield second ---------------------------------------

def test_a_family_that_cannot_answer_is_excluded_however_good_it_is():
    """Case studies score 0.500/doc and cannot name a government buyer."""
    got = RP.plan(RP.NEEDS_GOVERNMENT_BUYER, performance=REAL)
    assert got.families == ("government_award",)
    assert "customer_case_study" in got.excluded
    assert "cannot answer" in got.excluded["customer_case_study"]


def test_awards_cannot_answer_a_competitor_question():
    got = RP.plan(RP.NEEDS_COMPETITOR, performance=REAL)
    assert "government_award" in got.excluded
    assert "partnership_release" in got.excluded


def test_yield_ranks_only_within_the_families_that_could_answer():
    got = RP.plan(RP.NEEDS_CUSTOMER, performance=REAL)
    assert got.families == ("customer_case_study", "government_award")
    assert "0.500" in got.reasons["customer_case_study"]


def test_every_question_type_names_at_least_one_family():
    for question in RP.QUESTION_TYPES:
        assert RP.CAN_ANSWER[question]


# --- one measurement is not a permanent preference -----------------------

def test_a_provisional_family_is_kept_ahead_of_its_measured_rank():
    thin = perf("customer_case_study", retrieved=4, yield_=0.0)
    fat = perf("government_award", retrieved=200, yield_=0.9)
    got = RP.plan(RP.NEEDS_CUSTOMER, performance=[thin, fat])
    assert thin.maturity == RP.PROVISIONAL
    assert got.families[0] == "customer_case_study"
    assert "sample is small" in got.reasons["customer_case_study"]


def test_maturity_needs_a_real_sample():
    assert perf("x", retrieved=4).maturity == RP.PROVISIONAL
    assert perf("x", retrieved=50).maturity == RP.INDICATIVE
    assert perf("x", retrieved=500).maturity == RP.ESTABLISHED


def test_documents_alone_never_promote_a_family():
    """Wave 10 expanded release_notes from 3 documents to 11 and found only
    TWO of four tracked actors published anything reachable, and only ONE
    produced an object. The family's apparent yield was one company's
    changelog, and a document count is promotable by re-reading it."""
    one_vendor = perf("release_notes", retrieved=500, actors=1)
    assert one_vendor.maturity == RP.PROVISIONAL
    assert "1 actor against 2" in one_vendor.maturity_reason

    two_vendors = perf("release_notes", retrieved=500, actors=2)
    assert two_vendors.maturity == RP.INDICATIVE

    three_vendors = perf("release_notes", retrieved=500, actors=3)
    assert three_vendors.maturity == RP.ESTABLISHED


def test_the_maturity_reason_names_which_floor_is_short():
    thin = perf("release_notes", retrieved=11, actors=2)
    assert thin.maturity == RP.PROVISIONAL
    assert "11 documents against 20" in thin.maturity_reason


def test_an_unmeasured_family_is_sampled_rather_than_assumed_useless():
    got = RP.plan(RP.NEEDS_COMPETITOR, performance=REAL)
    assert "comparison_page" in got.families
    assert "never measured" in got.reasons["comparison_page"]


def test_even_an_established_family_leaves_room_to_keep_sampling():
    assert 0 < RP.EXPLORATION_FLOOR < 1


# --- health changes the plan ---------------------------------------------

def test_degrading_on_re_reads_reorders_the_same_question():
    healthy = RP.plan(RP.NEEDS_FRESH_OBSERVATION, performance=REAL)
    degraded = RP.plan(
        RP.NEEDS_FRESH_OBSERVATION, performance=REAL,
        learning_status=LA.DEGRADING,
        dominant_self_test_class=OB.SAME_SOURCE_REPACKAGING)
    assert healthy.families != degraded.families
    # The cheap source that produces NEW documents every day moves to the
    # front; the marketing pages that change once a quarter move to the back.
    assert degraded.families[0] == "government_award"
    assert degraded.families[-1] == "comparison_page"
    assert "SAME_SOURCE_REPACKAGING" in degraded.health_adjustment


def test_degrading_for_another_reason_does_not_reorder():
    """The response is specific to the diagnosis, not to the alarm."""
    got = RP.plan(RP.NEEDS_FRESH_OBSERVATION, performance=REAL,
                  learning_status=LA.DEGRADING,
                  dominant_self_test_class=OB.WIRE_DUPLICATE)
    assert got.health_adjustment == ""
    assert got.families == RP.plan(RP.NEEDS_FRESH_OBSERVATION,
                                   performance=REAL).families


def test_ingestion_is_never_disabled_wholesale():
    """Degrading reorders the mix; it never empties it."""
    got = RP.plan(RP.NEEDS_FRESH_OBSERVATION, performance=REAL,
                  learning_status=LA.DEGRADING,
                  dominant_self_test_class=OB.SAME_SOURCE_REPACKAGING)
    assert set(got.families) == set(
        RP.plan(RP.NEEDS_FRESH_OBSERVATION, performance=REAL).families)


# --- against the real measured yields ------------------------------------

def test_the_real_measurements_load_into_performance_records():
    families = json.loads(MEASURED.read_text())["families"]
    got = [RP.from_yield(y, as_of="2026-08-07") for y in families.values()]
    assert {p.source_family for p in got} == {
        "government_award", "customer_case_study", "partnership_release"}
    awards = next(p for p in got if p.source_family == "government_award")
    assert awards.cost == "cheap"          # 16s over 64 documents
    studies = next(p for p in got if p.source_family == "customer_case_study")
    assert studies.cost == "expensive"     # 311s over 22
    assert all(p.maturity != RP.ESTABLISHED for p in got)


# --- ACTION_OBJECT is scored on objects, never on actions -----------------

def test_the_object_question_is_scored_on_objects_not_on_actions():
    """The live grid's exact trap.

    Pricing pages returned 12 actions and established nothing. Release notes
    returned fewer documents and established five objects. A planner ranking
    this question by action count would send the next budget to the family
    that produced the most text about the fewest decidable things.
    """
    pricing = RP.from_object_yield(
        {"family": "pricing_page", "attempted": 27, "retrieved": 15,
         "actions_found": 12, "objects_established": 0,
         "latency_seconds": 52.6}, as_of="2026-08-08")
    notes = RP.from_object_yield(
        {"family": "release_notes", "attempted": 23, "retrieved": 9,
         "actions_found": 89, "objects_established": 5,
         "latency_seconds": 47.7}, as_of="2026-08-08")
    assert pricing.relationship_yield == 0.0
    assert notes.relationship_yield > 0.5
    assert notes.question_type == RP.NEEDS_ACTION_OBJECT
    got = RP.plan(RP.NEEDS_ACTION_OBJECT, performance=[pricing, notes])
    assert got.families[0] == "release_notes"


def test_an_unknown_object_is_not_counted_as_a_false_positive():
    """A document that did not say who the thing was for is the finding.

    Scoring it as an error would let a family look precise by extracting
    nothing at all.
    """
    got = RP.from_object_yield(
        {"family": "pricing_page", "attempted": 8, "retrieved": 5,
         "objects_established": 0, "objects_partial": 4,
         "objects_unknown": 1, "latency_seconds": 2.9}, as_of="2026-08-08")
    assert got.false_positive_rate is None


def test_a_family_is_summed_across_actors_before_it_is_divided():
    """Two cells, one family. Averaging the rates would let the cell that
    retrieved one document count as much as the cell that retrieved nine."""
    got = RP.merge_object_yields([
        {"family": "release_notes", "actor": "Shopify", "attempted": 12,
         "retrieved": 1, "objects_established": 1, "latency_seconds": 5.0},
        {"family": "release_notes", "actor": "BigCommerce", "attempted": 11,
         "retrieved": 9, "objects_established": 0, "latency_seconds": 42.0},
    ], as_of="2026-08-08")
    assert len(got) == 1
    assert got[0].retrieved == 10 and got[0].useful == 1
    assert got[0].relationship_yield == 0.1        # 1/10, not (1.0 + 0.0)/2


def test_the_plan_reports_the_unit_the_question_is_scored_in():
    got = RP.plan(RP.NEEDS_ACTION_OBJECT, performance=[
        RP.from_object_yield({"family": "release_notes", "attempted": 23,
                              "retrieved": 9, "objects_established": 5,
                              "latency_seconds": 47.7}, as_of="2026-08-08")])
    assert "established objects/document" in got.reasons["release_notes"]
    assert "relationships/document" not in got.reasons["release_notes"]


def test_the_live_grid_moves_release_notes_from_last_to_first():
    """§17 -> §18: the measurement has to change where the budget goes, or
    it is a table nobody acts on."""
    rows = list(json.loads(ACQUIRED.read_text())["yields"].values())
    perf = RP.merge_object_yields(rows, as_of="2026-08-08")
    before = RP.plan(RP.NEEDS_ACTION_OBJECT).families
    after = RP.plan(RP.NEEDS_ACTION_OBJECT, performance=perf).families
    assert before[-1] == "release_notes"        # the editorial prior
    assert after[0] == "release_notes"          # what 66 documents measured
    # Only release_notes established anything; nothing else may claim it.
    producing = [p.source_family for p in perf if p.useful]
    assert producing == ["release_notes"]
