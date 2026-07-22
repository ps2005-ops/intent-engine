"""T021 packages, option sets, escalation, no-recommendation, override,
the triage queues, the portfolio, the health dashboard, and traceability.

0 model calls. 0 network.
"""
import pytest

from intent_engine.executive import (
    ExecutiveError, ExecutiveService, build_no_recommendation, build_option,
    build_package,
)
from intent_engine.executive.packages import assign_escalation
from intent_engine.executive.queue import build_entry, build_queues

REF = [{"kind": "product_proposal", "ref_id": "P1"}]


@pytest.fixture()
def svc(tmp_path):
    return ExecutiveService(tmp_path / "executive.jsonl")


def _ready_package(svc, origin_id="o1", *, decision_class="product",
                   horizon="short_term"):
    candidate = svc.register_candidate(
        references=REF, origin={"kind": "manual", "origin_id": origin_id})
    svc.build_context(candidate, decision_horizon=horizon,
                      decision_class=decision_class,
                      resolved_inputs={"x": {"a": 1}})
    package = svc.draft_package(candidate, decision_question="commit?",
                                references=REF, unknowns=["u"])
    svc.add_option(package, label="A", benefits=["b"], costs=["c"],
                   risks=["r"], unknowns=["u"], reversibility="easy")
    svc.add_option(package, label="B", benefits=["b"], costs=["c"],
                   risks=["r"], unknowns=["u"], reversibility="moderate")
    return candidate, package


# =============================================================================
# Options — all six parts, reversibility declared
# =============================================================================

@pytest.mark.parametrize("missing", ["benefits", "costs", "risks", "unknowns"])
def test_an_option_states_all_of_its_content_parts(missing):
    kwargs = dict(label="A", benefits=["b"], costs=["c"], risks=["r"],
                  unknowns=["u"], dependencies=[], reversibility="easy")
    kwargs[missing] = []
    with pytest.raises(ExecutiveError, match=f"states its {missing}"):
        build_option(**kwargs)


def test_an_option_declares_reversibility():
    with pytest.raises(ExecutiveError, match="declares reversibility"):
        build_option(label="A", benefits=["b"], costs=["c"], risks=["r"],
                     unknowns=["u"], dependencies=[], reversibility="maybe")


def test_an_option_may_have_no_dependencies_but_states_so():
    option = build_option(label="A", benefits=["b"], costs=["c"], risks=["r"],
                          unknowns=["u"], dependencies=[], reversibility="easy")
    assert option["dependencies"] == []      # stated, not omitted


# =============================================================================
# Packages
# =============================================================================

def test_a_package_with_no_unknown_is_rejected():
    with pytest.raises(ExecutiveError, match="claiming none is hiding them"):
        build_package(decision_question="q", references=REF, unknowns=[],
                      dependencies=[], risks=[])


def test_a_package_carrying_banned_language_is_rejected():
    with pytest.raises(ExecutiveError, match="overclaims"):
        build_package(decision_question="we must obviously do this",
                      references=REF, unknowns=["u"], dependencies=[], risks=[])


def test_certainty_language_is_blocked_on_conflicting_evidence():
    with pytest.raises(ExecutiveError, match="certainty language"):
        build_package(decision_question="this will certainly work",
                      references=REF, unknowns=["u"], dependencies=[], risks=[],
                      evidence_label="CONFLICTING")


def test_a_package_heading_to_review_requires_two_options(svc):
    candidate = svc.register_candidate(
        references=REF, origin={"kind": "manual", "origin_id": "o1"})
    svc.build_context(candidate, decision_horizon="short_term",
                      decision_class="product", resolved_inputs={"x": 1})
    package = svc.draft_package(candidate, decision_question="q",
                                references=REF, unknowns=["u"])
    with pytest.raises(ExecutiveError, match="at least two options"):
        svc.request_review(package)


# =============================================================================
# No recommendation — a first-class outcome
# =============================================================================

def test_no_recommendation_states_reason_gap_and_review_date():
    body = build_no_recommendation(reason="evidence is too thin",
                                   evidence_gap="no experiment has run",
                                   review_date="2026-09-01")
    assert body["outcome"] == "no_recommendation"


def test_no_recommendation_requires_all_three_parts():
    for missing in ("reason", "evidence_gap", "review_date"):
        kwargs = dict(reason="r", evidence_gap="g", review_date="d")
        kwargs[missing] = ""
        with pytest.raises(ExecutiveError, match=f"states its {missing}"):
            build_no_recommendation(**kwargs)


def test_a_no_recommendation_package_can_go_to_review_without_options(svc):
    candidate = svc.register_candidate(
        references=REF, origin={"kind": "manual", "origin_id": "o1"})
    svc.build_context(candidate, decision_horizon="short_term",
                      decision_class="product", resolved_inputs={"x": 1})
    package = svc.draft_package(candidate, decision_question="q",
                                references=REF, unknowns=["u"])
    svc.record_no_recommendation(package, reason="thin evidence",
                                 evidence_gap="no experiment",
                                 review_date="2026-09-01")
    svc.request_review(package)               # permitted without options


# =============================================================================
# Escalation — who should decide
# =============================================================================

def test_escalation_raises_a_transformational_irreversible_to_board():
    from intent_engine.executive.readiness import readiness_block
    block = readiness_block(
        {"research": {"stances": ["SUPPORTED"]},
         "references": REF, "product": {"spec_present": True},
         "alignment": {"level": "core", "declared_by": "f"},
         "budget": {"amount_available": 1, "declared_by": "f"},
         "owner": "f", "affected_customers": [f"E{i}" for i in range(20)],
         "downstream_decisions": ["D1", "D2", "D3"],
         "initiatives": ["I1", "I2"], "needs_budget": False},
        options=[{"reversibility": "irreversible"}])
    result = assign_escalation(readiness_block=block, impact=block["impact"],
                               conflict_summary={"total": 0},
                               decision_class="governance")
    assert result["level"] == "needs_board"


def test_escalation_monitors_a_not_ready_candidate_with_no_conflict():
    from intent_engine.executive.readiness import readiness_block
    block = readiness_block({"research": {"stances": []}},
                            options=[{"reversibility": "easy"}])
    result = assign_escalation(readiness_block=block, impact=block["impact"],
                               conflict_summary={"total": 0},
                               decision_class="operational")
    assert result["level"] in ("review_scheduled", "monitor")


# =============================================================================
# Override — both choices survive
# =============================================================================

def test_founder_override_retains_both_choices(svc):
    candidate, package = _ready_package(svc)
    svc.request_review(package)
    svc.record_review(package, disposition="accepted", actor_id="founder",
                      chosen_option_id="B")
    svc.record_override(package, chosen_option_id="B", preferred_option_id="A",
                        reason="the delay is not worth it", actor_id="founder")
    state = svc.get_state()
    override = state.overrides[f"{package}:1"]
    assert override["chosen_option_id"] == "B"
    assert override["preferred_option_id"] == "A"
    assert override["reason"]
    # nothing overwritten — the review still records the founder's choice
    assert state.reviews[f"{package}:1"]["chosen_option_id"] == "B"


def test_an_override_requires_a_prior_review(svc):
    candidate, package = _ready_package(svc)
    with pytest.raises(ExecutiveError, match="the review comes first"):
        svc.record_override(package, chosen_option_id="B",
                            preferred_option_id="A", reason="x",
                            actor_id="founder")


# =============================================================================
# The triage queues — the primary artifact
# =============================================================================

def test_candidates_are_partitioned_into_three_queues():
    entries = [
        build_entry(candidate_id="C1", queue="strategic", decision_ready=True,
                    escalation="needs_founder", conflict_count=0,
                    impact="large", open_debt_count=0, age_days=1,
                    horizon="strategic", decision_class="strategic",
                    rankable=True),
        build_entry(candidate_id="C2", queue="operational", decision_ready=True,
                    escalation="needs_founder", conflict_count=1,
                    impact="medium", open_debt_count=0, age_days=1,
                    horizon="short_term", decision_class="product",
                    rankable=True),
        build_entry(candidate_id="C3", queue="maintenance", decision_ready=True,
                    escalation="monitor", conflict_count=0, impact="small",
                    open_debt_count=0, age_days=1, horizon="immediate",
                    decision_class="technical", rankable=True),
    ]
    queues = build_queues(entries)
    assert queues["queues"]["strategic"]["order"] == ["C1"]
    assert queues["queues"]["operational"]["order"] == ["C2"]
    assert queues["queues"]["maintenance"]["order"] == ["C3"]


def test_ordering_is_deterministic_and_by_stated_precedence():
    entries = [
        build_entry(candidate_id="C_ready", queue="operational",
                    decision_ready=True, escalation="needs_founder",
                    conflict_count=0, impact="small", open_debt_count=0,
                    age_days=1, horizon="short_term", decision_class="product",
                    rankable=True),
        build_entry(candidate_id="C_notready", queue="operational",
                    decision_ready=False, escalation="needs_founder",
                    conflict_count=5, impact="large", open_debt_count=3,
                    age_days=99, horizon="short_term",
                    decision_class="product", rankable=True),
    ]
    first = build_queues(entries)["queues"]["operational"]["order"]
    second = build_queues(entries)["queues"]["operational"]["order"]
    assert first == second
    # decision-ready comes first, regardless of the other's higher conflict
    # and impact
    assert first[0] == "C_ready"


def test_an_unrankable_candidate_is_listed_separately_with_its_gap():
    entries = [
        build_entry(candidate_id="C1", queue="operational",
                    decision_ready=False, escalation=None, conflict_count=0,
                    impact=None, open_debt_count=0, age_days=1,
                    horizon="short_term", decision_class="product",
                    rankable=False, gaps=["readiness has not been computed"]),
    ]
    block = build_queues(entries)["queues"]["operational"]
    assert block["order"] == []
    assert block["unrankable"][0]["candidate_id"] == "C1"
    assert block["unrankable"][0]["gaps"]


def test_ordering_does_not_depend_on_age():
    """Age is reported but must not drive the order."""
    young = build_entry(candidate_id="C1", queue="operational",
                        decision_ready=True, escalation="needs_founder",
                        conflict_count=0, impact="medium", open_debt_count=0,
                        age_days=1, horizon="short_term",
                        decision_class="product", rankable=True)
    old = build_entry(candidate_id="C2", queue="operational",
                      decision_ready=True, escalation="needs_founder",
                      conflict_count=0, impact="medium", open_debt_count=0,
                      age_days=999, horizon="short_term",
                      decision_class="product", rankable=True)
    order = build_queues([young, old])["queues"]["operational"]["order"]
    # identical except age and id -> tie broken by id, NOT by age
    assert order == ["C1", "C2"]


# =============================================================================
# Traceability
# =============================================================================

def test_a_rejected_recommendation_is_a_legitimate_terminal(svc):
    candidate, package = _ready_package(svc)
    svc.request_review(package)
    svc.record_review(package, disposition="rejected", actor_id="founder")
    trace = svc.trace(package)
    assert trace["terminal"] is True
    assert trace["state"] == "rejected"
    assert svc.assert_no_dead_ends()["ok"] is True


def test_an_accepted_unlinked_recommendation_is_a_dead_end(svc):
    candidate, package = _ready_package(svc)
    svc.request_review(package)
    svc.record_review(package, disposition="accepted", actor_id="founder",
                      chosen_option_id="A")
    trace = svc.trace(package)
    assert trace["terminal"] is False
    assert trace["state"] == "accepted_unlinked"
    assert svc.assert_no_dead_ends()["ok"] is False


def test_a_deferred_recommendation_is_a_legitimate_terminal(svc):
    candidate, package = _ready_package(svc)
    svc.request_review(package)
    svc.record_review(package, disposition="deferred", actor_id="founder",
                      deferred_until_condition="after the next cohort")
    assert svc.trace(package)["terminal"] is True
    assert svc.assert_no_dead_ends()["ok"] is True
