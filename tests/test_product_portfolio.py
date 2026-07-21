"""T020 portfolio rollup, balance, readiness, bundles, and the roadmap wall.

Priority, sequencing, blocking, and readiness are four questions; balance
is measured against a human-declared band or withheld; and the roadmap
diff is emitted, never applied.
0 model calls. 0 network.
"""
from pathlib import Path

import pytest

from intent_engine.product import (
    ProductError, ProductService, balance_report, executive_summary,
    portfolio_rollup, readiness_report,
)
from intent_engine.product.roadmap_diff import (
    STATUS_NEEDS_SPEC, STATUS_PROPOSED, assert_never_runnable,
    build_roadmap_candidate, render_roadmap_diff,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
AS_OF = "2026-07-21T00:00:00+00:00"
REF = [{"kind": "crm_fact", "ref_id": "crm.churned:E1", "crm_entity_id": "E1"}]

SPEC = {
    "goals": ["reduce the time to first value"],
    "non_goals": ["redesigning pricing"],
    "requirements": ["the walkthrough is skippable"],
    "constraints": ["no change to the signup flow"],
    "acceptance_criteria": [
        "the walkthrough records a completion event for at least 1 account"],
    "unknowns": ["the UX is undecided"], "dependencies": [],
    "risks": ["users skip it"], "open_questions": ["how many steps"],
}


@pytest.fixture()
def rig(tmp_path):
    svc = ProductService(tmp_path / "product.jsonl")
    portfolio = svc.create_portfolio("Company", actor_id="founder")
    theme = svc.declare_theme(portfolio, "Retention", actor_id="founder")
    initiative = svc.create_initiative(theme, "Onboarding", actor_id="founder")
    problem = svc.record_problem(
        statement="Customers stop before reaching first value",
        evidence_references=REF, why_now="the facts are current",
        what_changes_if_ignored="the pattern repeats",
        first_observed_at=AS_OF, affected_customers=["E1", "E2"])
    opportunity = svc.register_opportunity(
        problem["problem_id"], title="A guided first run",
        evidence_references=REF, work_category="customer_work")
    svc.attach_opportunity(opportunity, initiative)
    return svc, portfolio, theme, initiative, problem["problem_id"], opportunity


def _draft(svc, opportunity, solution="Add a guided first run", **over):
    kwargs = dict(candidate_solution=solution, tradeoffs=["t"], risks=["r"],
                  known=["k"], unknown=["u"], assumptions=["a"],
                  work_category="customer_work")
    kwargs.update(over)
    return svc.draft_proposal(opportunity, **kwargs)


# =============================================================================
# Rollup
# =============================================================================

def test_the_portfolio_is_one_deterministic_call(rig):
    svc, portfolio, _, _, _, opportunity = rig
    _draft(svc, opportunity)
    first = svc.portfolio(portfolio, as_of=AS_OF)
    second = svc.portfolio(portfolio, as_of=AS_OF)
    assert first == second
    assert set(first) == {"rollup", "readiness", "balance",
                          "executive_summary"}


def test_the_rollup_walks_portfolio_theme_initiative_opportunity_proposal(rig):
    svc, portfolio, theme, initiative, _, opportunity = rig
    proposal = _draft(svc, opportunity)
    svc.draft_spec(proposal, SPEC)
    rollup = portfolio_rollup(svc.get_state(), svc.get_index(),
                              portfolio_id=portfolio, as_of=AS_OF)
    assert rollup["themes"][theme]["initiative_ids"] == [initiative]
    entry = rollup["initiatives"][initiative]
    assert entry["opportunity_count"] == 1
    assert entry["proposal_count"] == 1
    assert entry["proposal_count_by_status"] == {"drafted": 1}
    assert rollup["totals"] == {"themes": 1, "initiatives": 1,
                                "opportunities": 1, "proposals": 1,
                                "specs": 1}


def test_the_rollup_reports_aggregate_coverage_and_research_debt(rig):
    svc, portfolio, _, initiative, _, opportunity = rig
    _draft(svc, opportunity)
    rollup = portfolio_rollup(
        svc.get_state(), svc.get_index(), portfolio_id=portfolio,
        scores_by_proposal=svc.scores_by_proposal(as_of=AS_OF),
        research_debt_by_opportunity={opportunity: [{"kind": "need_experiment"}]},
        as_of=AS_OF)
    entry = rollup["initiatives"][initiative]
    assert entry["aggregate_research_debt"] == 1
    assert entry["research_debt_kinds"] == ["need_experiment"]
    # no research package is linked, so coverage is UNAVAILABLE, not 0
    assert entry["aggregate_evidence_coverage"] is None
    assert entry["aggregate_evidence_coverage_status"] == "UNAVAILABLE"


def test_an_unattached_opportunity_is_reported_rather_than_hidden(rig):
    svc, portfolio, _, _, problem, _ = rig
    loose = svc.register_opportunity(problem, title="A lifecycle email",
                                     evidence_references=REF)
    rollup = portfolio_rollup(svc.get_state(), svc.get_index(),
                              portfolio_id=portfolio, as_of=AS_OF)
    assert loose in rollup["unattached_opportunities"]


def test_themes_are_human_created(rig):
    svc, portfolio, _, _, _, _ = rig
    with pytest.raises(ProductError, match="human wall transition"):
        svc.declare_theme(portfolio, "Growth", actor_id="bot",
                          actor_type="agent")


# =============================================================================
# Priority, sequencing, blocking, readiness — four separate questions
# =============================================================================

def test_readiness_reports_the_four_questions_separately(rig):
    svc, _, _, _, _, opportunity = rig
    proposal = _draft(svc, opportunity)
    entry = readiness_report(svc.get_state(), svc.get_index())["entries"][proposal]
    assert set(entry) >= {"priority_rank", "sequence_position", "blocked_by",
                          "readiness", "depends_on", "alternatives"}


def test_a_dependency_can_sequence_ahead_of_priority(rig):
    """Highest priority does not imply build first."""
    svc, _, _, _, _, opportunity = rig
    first = _draft(svc, opportunity, "Foundational change")
    second = _draft(svc, opportunity, "The change everyone wants")
    svc.record_edge("depends_on", second, first)
    report = readiness_report(svc.get_state(), svc.get_index())
    order = report["sequence_order"]
    assert order.index(first) < order.index(second)
    assert report["entries"][second]["blocked_by"] == [first]
    assert report["entries"][second]["readiness"] == "BLOCKED"


def test_a_proposal_with_an_unavailable_composite_is_not_ranked(rig):
    svc, _, _, _, _, opportunity = rig
    proposal = _draft(svc, opportunity)
    report = readiness_report(
        svc.get_state(), svc.get_index(),
        scores_by_proposal=svc.scores_by_proposal(as_of=AS_OF))
    assert report["entries"][proposal]["priority_rank"] is None
    assert proposal in report["unrankable"]
    assert "rather than ranked against" in report["unrankable_note"]


def test_readiness_moves_through_needs_spec_then_needs_decision(rig):
    svc, _, _, _, _, opportunity = rig
    proposal = _draft(svc, opportunity)
    entries = readiness_report(svc.get_state(), svc.get_index())["entries"]
    assert entries[proposal]["readiness"] == "NEEDS_SPEC"
    svc.draft_spec(proposal, SPEC)
    svc.request_review(proposal)
    svc.record_review(proposal, disposition="accepted", actor_id="founder")
    entries = readiness_report(svc.get_state(), svc.get_index())["entries"]
    assert entries[proposal]["readiness"] == "NEEDS_DECISION"


# =============================================================================
# Balance
# =============================================================================

def test_balance_is_withheld_without_a_human_declared_band(rig):
    svc, portfolio, _, _, _, opportunity = rig
    _draft(svc, opportunity)
    report = balance_report(svc.get_state(), svc.get_index(),
                            portfolio_id=portfolio)
    assert report["status"] == "UNAVAILABLE"
    assert report["findings"] == []
    assert "strategy judgment" in report["note"]
    assert report["proposal_counts_by_category"]["customer_work"] == 1


def test_balance_is_measured_against_the_declared_band(rig):
    svc, portfolio, _, _, _, opportunity = rig
    _draft(svc, opportunity)
    svc.declare_balance_target(
        portfolio, {"customer_work": {"min": 0.1, "max": 0.5},
                    "technical_debt": {"min": 0.2, "max": 0.6}},
        actor_id="founder")
    report = balance_report(svc.get_state(), svc.get_index(),
                            portfolio_id=portfolio)
    assert report["status"] == "OK"
    findings = {f["category"]: f["finding"] for f in report["findings"]}
    assert findings["customer_work"] == "above the declared band"
    assert findings["technical_debt"] == "below the declared band"


def test_a_balance_target_is_human_declared(rig):
    svc, portfolio, _, _, _, _ = rig
    with pytest.raises(ProductError, match="human wall transition"):
        svc.declare_balance_target(portfolio, {}, actor_id="bot",
                                   actor_type="agent")


# =============================================================================
# The executive summary — Session 11's substrate
# =============================================================================

def test_the_executive_summary_answers_the_six_questions(rig):
    svc, portfolio, _, _, _, opportunity = rig
    proposal = _draft(svc, opportunity)
    svc.record_decision_debt(proposal, kind="waiting_for_founder",
                             detail="pricing posture is undecided")
    summary = executive_summary(
        svc.get_state(), svc.get_index(), portfolio_id=portfolio,
        scores_by_proposal=svc.scores_by_proposal(as_of=AS_OF))
    assert set(summary) >= {"biggest_opportunities", "biggest_risks",
                            "biggest_unknowns", "largest_evidence_gaps",
                            "most_blocked_initiatives",
                            "highest_decision_debt"}
    assert summary["highest_decision_debt"]["total"] == 1
    assert summary["highest_decision_debt"]["by_kind"]["waiting_for_founder"] \
        == [proposal]
    assert summary["largest_evidence_gaps"]


def test_an_unknown_decision_debt_kind_is_refused(rig):
    svc, _, _, _, _, opportunity = rig
    proposal = _draft(svc, opportunity)
    with pytest.raises(ProductError, match="unknown decision-debt kind"):
        svc.record_decision_debt(proposal, kind="waiting_for_vibes")


# =============================================================================
# Bundles
# =============================================================================

def test_a_bundle_reports_aggregate_state_and_changes_nothing(rig):
    svc, _, _, _, _, opportunity = rig
    a = _draft(svc, opportunity, "Foundational change")
    b = _draft(svc, opportunity, "The dependent change")
    svc.record_edge("depends_on", b, a)
    before = svc.get_state().proposals[a]["status"]
    bundle = svc.assemble_bundle("release-1", [a, b], as_of=AS_OF)
    assert bundle["internal_sequence"].index(a) < \
        bundle["internal_sequence"].index(b)
    assert bundle["blocked"] == [b]
    assert svc.get_state().proposals[a]["status"] == before


def test_a_bundle_naming_an_undrafted_proposal_is_refused(rig):
    svc, _, _, _, _, opportunity = rig
    _draft(svc, opportunity)
    with pytest.raises(ProductError, match="undrafted proposals"):
        svc.assemble_bundle("release-1", ["NOPE"], as_of=AS_OF)


# =============================================================================
# The roadmap wall
# =============================================================================

def test_a_candidate_with_checkable_bars_is_proposed_not_runnable(rig):
    svc, _, _, _, _, opportunity = rig
    proposal = _draft(svc, opportunity)
    svc.draft_spec(proposal, SPEC)
    candidate = svc.draft_roadmap_candidate(proposal, title="Guided first run")
    assert candidate["status"] == STATUS_PROPOSED
    assert "RUNNABLE" not in candidate["text"].split("**Status**:")[1].split("\n")[0]


def test_a_candidate_with_an_unverifiable_bar_stays_needs_spec():
    candidate = build_roadmap_candidate(
        proposal_id="P1", proposal_version=1, spec_id="S1", spec_version=1,
        title="Something", opportunity_id="O1", problem_id="PR1",
        spec={"acceptance_criteria": ["the flow works well"],
              "constraints": [], "non_goals": []})
    assert candidate["status"] == STATUS_NEEDS_SPEC
    assert candidate["unverifiable_bars"]


def test_the_agent_can_never_mark_a_candidate_runnable():
    text = "## CANDIDATE — x\n\n- **Status**: RUNNABLE\n"
    with pytest.raises(ProductError, match="does not move an item into the "
                                           "queue"):
        assert_never_runnable(text)


def test_the_candidate_leaves_file_scope_unresolved(rig):
    """A spec draft carries no file paths, so the candidate says so rather
    than inventing them."""
    svc, _, _, _, _, opportunity = rig
    proposal = _draft(svc, opportunity)
    svc.draft_spec(proposal, SPEC)
    candidate = svc.draft_roadmap_candidate(proposal, title="Guided first run")
    assert "Files in scope**: unresolved" in candidate["text"]


def test_the_diff_is_emitted_and_never_applied(rig):
    svc, _, _, _, _, opportunity = rig
    proposal = _draft(svc, opportunity)
    svc.draft_spec(proposal, SPEC)
    svc.draft_roadmap_candidate(proposal, title="Guided first run")
    original = (REPO_ROOT / "ROADMAP.md").read_bytes()
    diff = svc.emit_roadmap_diff(proposal, original.decode("utf-8"))
    assert diff["applied"] is False
    assert diff["diff"].startswith("---")
    assert diff["proposal_id"] == proposal
    assert diff["spec_version"] == 1
    assert (REPO_ROOT / "ROADMAP.md").read_bytes() == original


def test_the_roadmap_diff_module_holds_no_file_path_at_all():
    """The wall is structural: this module never opens a file, so a write
    cannot be added to it by accident later."""
    import ast
    import inspect

    from intent_engine.product import roadmap_diff as module
    tree = ast.parse(inspect.getsource(module))
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    names |= {node.attr for node in ast.walk(tree)
              if isinstance(node, ast.Attribute)}
    for banned in ("open", "Path", "write_text", "write_bytes", "writelines"):
        assert banned not in names, banned


def test_no_product_module_writes_the_roadmap():
    product = REPO_ROOT / "src/intent_engine/product"
    for source_file in sorted(product.glob("*.py")):
        text = source_file.read_text()
        assert "ROADMAP.md\", \"w" not in text
        assert "write_text" not in text
        assert "ROADMAP.md').write" not in text
