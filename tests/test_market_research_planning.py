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

MEASURED = pathlib.Path(
    "/private/tmp/claude-501/-Users-prathamsharma/"
    "88a4600b-3357-43cf-9a33-f6b392f47edf/scratchpad/world_model.json")


def perf(family, *, retrieved=50, yield_=0.2, latency=10.0):
    return RP.SourceFamilyPerformance(
        source_family=family, retrieved=retrieved, attempts=28,
        useful=int(retrieved * yield_), relationship_yield=yield_,
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
    if not MEASURED.exists():                          # pragma: no cover
        return
    families = json.loads(MEASURED.read_text())["families"]
    got = [RP.from_yield(y, as_of="2026-08-07") for y in families.values()]
    assert {p.source_family for p in got} == {
        "government_award", "customer_case_study", "partnership_release"}
    awards = next(p for p in got if p.source_family == "government_award")
    assert awards.cost == "cheap"          # 16s over 64 documents
    studies = next(p for p in got if p.source_family == "customer_case_study")
    assert studies.cost == "expensive"     # 311s over 22
    assert all(p.maturity != RP.ESTABLISHED for p in got)
