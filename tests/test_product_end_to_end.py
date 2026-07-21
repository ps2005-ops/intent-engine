"""T020 end-to-end: the golden path, four refusals, the model boundary,
the consumer, replay, snapshots, the language wall over a whole run, and
the repository invariants.

The golden path runs against the REAL T019, T018, and T014 services
rather than stand-ins, because the point of this subsystem is that it
reads what those subsystems already know instead of restating it.

0 real model calls (fake client). 0 network.
"""
import importlib.util
import json
import re
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from intent_engine.core.decision_record import DecisionService
from intent_engine.crm import CRMService
from intent_engine.events import CompanyEventBus, drain, replay
from intent_engine.growth import NAMESPACE_PRODUCTION, GrowthService
from intent_engine.knowledge import KnowledgeService
from intent_engine.product import (
    PRODUCT_PRINCIPLES, ProductError, ProductService,
    capture_portfolio_snapshot, capture_proposal_snapshot, scan_banned_language,
)
from intent_engine.product.service import ModelOverreach
from intent_engine.research import ResearchService, claim_key

REPO_ROOT = Path(__file__).resolve().parents[1]
AS_OF = "2026-07-21T00:00:00+00:00"

PAPER_TEXT = ("Reply rate rose from 4% to 9% after the subject line was "
              "shortened in a controlled trial of 800 messages.")
CONTRA_TEXT = ("Shortening the subject line reduced replies in our sample "
               "of small accounts.")
QUESTIONS = ["Does a shorter first-run flow change activation?",
             "Does send time change activation?",
             "Does audience overlap explain the difference?"]

CANDIDATES = {
    PAPER_TEXT: [{"claim_text": "Activation rose from 4% to 9%",
                  "evidence_class": "observation",
                  "quote_span": "Reply rate rose from 4% to 9%"}],
    CONTRA_TEXT: [{"claim_text": "Activation rose from 4% to 9%",
                   "evidence_class": "observation",
                   "quote_span": "Shortening the subject line reduced replies"}],
}


def _load_sibling(name):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).resolve().parent / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_reg = _load_sibling("test_growth_registration")
_res = _load_sibling("test_growth_results")


def _research_client():
    client = MagicMock()

    def call_tool(**kwargs):
        text = kwargs["user_message"]
        for needle, candidates in CANDIDATES.items():
            if needle in text:
                return {"candidates": candidates}
        return {"candidates": []}

    client.call_tool.side_effect = call_tool
    return client


SPEC = {
    "goals": ["reduce the time to first value for a new account"],
    "non_goals": ["redesigning the pricing page"],
    "requirements": ["the walkthrough is skippable at every step"],
    "constraints": ["no change to the signup flow"],
    "acceptance_criteria": [
        "the walkthrough records a completion event for at least 1 account",
        "the skip control emits a skip event within the same session"],
    "unknowns": ["the UX of the walkthrough is undecided",
                 "whether customers want guidance at this point"],
    "dependencies": [],
    "risks": ["accounts skip the walkthrough and gain nothing"],
    "open_questions": ["how many steps the walkthrough should carry"],
}


@pytest.fixture()
def world(tmp_path):
    """Three real upstream subsystems, plus product wired to read them."""
    decisions = DecisionService(str(tmp_path / "decisions.db"))
    crm = CRMService(tmp_path / "crm.jsonl")
    knowledge = KnowledgeService(tmp_path / "feedback.jsonl",
                                 tmp_path / "knowledge.jsonl")
    bus = CompanyEventBus(tmp_path / "events")
    research = ResearchService(tmp_path / "research.jsonl",
                               knowledge_service=knowledge,
                               llm_client=_research_client(),
                               model_version="fake.v0")
    growth = GrowthService(tmp_path, NAMESPACE_PRODUCTION, crm_service=crm,
                           knowledge_service=knowledge,
                           decision_service=decisions, event_bus=bus,
                           ledger_path=tmp_path / "ledger.db")
    product = ProductService(tmp_path / "product.jsonl",
                             research_service=research, growth_service=growth,
                             crm_service=crm, decision_service=decisions,
                             knowledge_service=knowledge, event_bus=bus,
                             model_version="fake.v0")
    return product, research, growth, crm, decisions, knowledge, bus, tmp_path


# =============================================================================
# Upstream fixtures — real artifacts from T014, T018, T019
# =============================================================================

def _churned_customers(crm, count=3):
    """Three customers who reached a churn or at-risk fact."""
    entities = []
    for i in range(count):
        entity = crm.create_prospect(email=f"c{i}@example.com")
        for event in ("crm.qualified", "crm.opportunity_opened", "crm.won",
                      "crm.customer_activated"):
            crm.record(entity, event, actor_type="human", actor_id="founder")
        crm.record(entity, "crm.customer_at_risk", actor_type="human",
                   actor_id="founder", payload={"reason": "usage stopped"})
        if i < 2:
            crm.record(entity, "crm.churned", actor_type="human",
                       actor_id="founder", payload={"reason": "did not renew"})
        entities.append(entity)
    return entities


def _conflicting_research_package(research):
    """A real T019 package whose conclusion is CONFLICTING and which
    carries research debt."""
    request = research.create_request(
        "Why do new accounts stall before activation?",
        motivation="three at-risk customers", constraints=["2026-Q3"],
        scope="activation")
    rid = request["request_id"]
    research.draft_plan(
        rid, goal="explain the activation stall", questions=QUESTIONS,
        evidence_requirements={"minimum_sources": 2,
                               "minimum_quality": "MEDIUM"},
        stopping_conditions={"max_sources": 12, "corroborated_per_question": 2},
        failure_definition="if no source addresses a question, say so and stop",
        tool_allowlist=["supplied"],
        budget={"max_sources": 12, "max_model_calls": 10})
    research.submit_plan(rid)
    research.approve_plan(rid, actor_id="founder")
    session = research.start_session(rid)

    def _register(source_class, text, locator, **over):
        return research.register_source(
            rid, session, source_class=source_class, title="A study",
            text=text, locator=locator, retrieved_at=AS_OF,
            acquisition_method="supplied", acquisition_tool="supplied",
            author="Author", publisher="Publisher",
            published_date="2026-07-01T00:00:00+00:00", domain="product",
            **over)

    paper = _register("peer_reviewed", PAPER_TEXT, "https://example.com/paper")
    press = _register("reputable_press", CONTRA_TEXT,
                      "https://example.com/press", population="small accounts")
    research.extract_evidence(rid, session, paper, PAPER_TEXT,
                              question=QUESTIONS[0], stance="supports")
    research.extract_evidence(rid, session, press, CONTRA_TEXT,
                              question=QUESTIONS[0], stance="contradicts")

    index = research.get_index(rid, as_of=AS_OF)
    key = claim_key("Activation rose from 4% to 9%")
    supporting = [e["evidence_id"] for e in index.evidence_for_claim(key)
                  if e["stance"] == "supports"]
    contradicting = [e["evidence_id"] for e in index.evidence_for_claim(key)
                     if e["stance"] == "contradicts"]
    research.record_contradiction(rid, session, claim_key_=key,
                                  evidence_id=contradicting[0],
                                  counterpart=supporting[0],
                                  conflict_reason="different_populations")
    research.close_session(rid, session)
    package_id = research.assemble_package(
        rid, session, claim_map={QUESTIONS[0]: [key], QUESTIONS[1]: []},
        as_of=AS_OF)
    conclusion = research.draft_conclusion(rid, package_id,
                                           question=QUESTIONS[0])
    assert conclusion["uncertainty_label"] == "CONFLICTING"
    return rid, package_id, research.get_package(rid, package_id)


def _inconclusive_experiment(growth):
    experiment = _reg.register(growth, minimum=20)
    growth.start_experiment(experiment, actor_id="founder")
    _res._populate(growth, experiment, per_arm=40, control_successes=13,
                   treatment_successes=14)
    assert growth.get_result(experiment)["label"] == "INCONCLUSIVE"
    return experiment


def _publish_result_labelled(bus, growth, experiment):
    """`growth.result_labelled` is in the company-event taxonomy with
    producer `growth_platform`, but no T018 code path emits it yet (T018
    publishes only experiment_started / experiment_stopped). The consumer
    is tested against a real event on the real bus, published under the
    declared producer, rather than by changing T018 from this session."""
    return bus.publish(
        "growth.result_labelled", subject_type="experiment",
        subject_id=experiment, producer="growth_platform",
        actor_type="system", actor_id="growth_platform", source="system",
        payload={"label": growth.get_result(experiment)["label"]},
        idempotency_key=f"labelled:{experiment}")


# =============================================================================
# The golden path
# =============================================================================

def test_golden_path(world):
    product, research, growth, crm, decisions, knowledge, bus, tmp = world

    # --- three real origins ------------------------------------------------
    entities = _churned_customers(crm, 3)
    request_id, package_id, package = _conflicting_research_package(research)
    experiment = _inconclusive_experiment(growth)
    assert package["research_debt"]

    # --- intake creates candidates from ALL THREE origins ------------------
    from_research = product.intake_from_research_package(
        request_id=request_id, package_id=package_id, as_of=AS_OF)
    from_growth = product.intake_from_growth_result(experiment, as_of=AS_OF)
    from_crm = product.intake_from_crm(entities, as_of=AS_OF)

    assert from_research and from_growth and from_crm
    index = product.get_index()
    origins = {o["origin"]["kind"] for o in index.opportunities.values()}
    assert origins == {"research_package", "growth_result", "crm_facts"}
    for created in from_research + from_growth + from_crm:
        opportunity = index.opportunities[created["opportunity_id"]]
        assert opportunity["origin"], "every intake candidate cites its origin"

    # --- a problem statement is recorded with all four required parts ------
    portfolio = product.create_portfolio("Company", actor_id="founder")
    theme = product.declare_theme(portfolio, "Activation", actor_id="founder")
    initiative = product.create_initiative(theme, "First value",
                                           actor_id="founder")
    problem = product.record_problem(
        statement="New accounts stall before reaching first value",
        evidence_references=[
            {"kind": "research_conclusion", "ref_id": package_id,
             "request_id": request_id, "observed_at": AS_OF},
            {"kind": "experiment", "ref_id": experiment,
             "experiment_id": experiment, "label": "INCONCLUSIVE"},
            {"kind": "crm_fact", "ref_id": f"crm.churned:{entities[0]}",
             "crm_entity_id": entities[0]}],
        why_now="three customer entities reached an at-risk or churn fact",
        what_changes_if_ignored=("the same path repeats for later accounts "
                                 "and the recorded cost compounds"),
        first_observed_at=AS_OF, affected_customers=entities)
    assert problem["reused"] is False

    opportunity = product.register_opportunity(
        problem["problem_id"], title="A guided first-run walkthrough",
        evidence_references=[
            {"kind": "research_conclusion", "ref_id": package_id,
             "request_id": request_id},
            {"kind": "experiment", "ref_id": experiment,
             "experiment_id": experiment, "label": "INCONCLUSIVE"},
            {"kind": "crm_fact", "ref_id": f"crm.churned:{entities[1]}",
             "crm_entity_id": entities[1]}],
        work_category="customer_work")
    product.attach_opportunity(opportunity, initiative)

    # --- the Opportunity Index is built: invariants ok, lineage resolves ----
    index = product.get_index()
    assert index.assert_invariants()["invariants"] == "ok"

    solution_set = product.open_solution_set(problem["problem_id"],
                                             name="first-value")
    proposal = product.draft_proposal(
        opportunity,
        candidate_solution="Add a guided first-run walkthrough",
        tradeoffs=["adds a surface to maintain against every later change"],
        risks=["accounts skip it and gain nothing"],
        known=["three entities reached an at-risk or churn fact",
               "the linked research conclusion is CONFLICTING"],
        unknown=["whether guidance is what changes activation",
                 "which step in the current flow dominates the stall"],
        assumptions=["time to first value is what drives the churn facts"],
        open_questions=["what counts as first value for this product"],
        work_category="customer_work", solution_set_id=solution_set,
        evidence_label="CONFLICTING")

    lineage = product.lineage(proposal)
    assert lineage["opportunity_id"] == opportunity
    assert lineage["problem_id"] == problem["problem_id"]
    assert lineage["affected_customers"] == sorted(entities)
    resolutions = [e["resolution"] for e in lineage["evidence"]]
    assert any(r.get("resolved_by") == "research_service.get_package"
               for r in resolutions if isinstance(r, dict))
    assert any(r.get("request_id") == request_id
               for r in resolutions if isinstance(r, dict))

    # --- scores ------------------------------------------------------------
    scores = product.score_proposal(proposal, as_of=AS_OF)
    dimensions = scores["dimensions"]
    assert dimensions["customer_coverage"]["inputs"][
        "distinct_crm_entity_ids"] == sorted(entities)
    assert len(dimensions["customer_coverage"]["inputs"][
        "distinct_crm_entity_ids"]) == 3
    assert "MIXED" in " ".join(dimensions["research_coverage"]["reasons"]) \
        or "CONFLICTING" in " ".join(dimensions["research_coverage"]["reasons"])
    assert "INCONCLUSIVE" in " ".join(
        dimensions["experiment_coverage"]["reasons"])
    assert dimensions["strategic_alignment"]["status"] == "UNAVAILABLE"
    composite = scores["opportunity_score"]
    assert composite["status"] == "UNAVAILABLE"
    assert composite["value"] is None
    assert any("strategic_alignment" in gap for gap in composite["gaps"])

    # uncertainty travelled from both unsettled origins
    assert scores["confidence"]["opportunity_confidence"]["value"] <= 0.4

    # --- a second, ALTERNATIVE proposal for the SAME problem ---------------
    alternative = product.draft_proposal(
        opportunity,
        candidate_solution="Send a lifecycle email sequence for the first week",
        tradeoffs=["reaches people outside the product, and may be ignored"],
        risks=["email deliverability limits who sees it"],
        known=["the same three entities are affected"],
        unknown=["whether email reaches the accounts that stall"],
        assumptions=["the stall is an attention problem, not a UI problem"],
        open_questions=["which day of the first week matters most"],
        work_category="customer_work", solution_set_id=solution_set,
        evidence_label="CONFLICTING")
    product.record_alternative(proposal, alternative,
                               reason="two routes to the same problem")
    assert product.get_index().assert_invariants()["invariants"] == "ok"

    # --- a spec draft binds to proposal v1 ---------------------------------
    spec = product.draft_spec(proposal, SPEC, evidence_label="CONFLICTING")
    debt = product.get_spec_debt(spec)
    assert debt["total"] == 2
    assert set(debt["by_kind"]) == {"need_ux", "need_customer_validation"}

    # --- founder review: accepts one, defers the alternative ---------------
    product.request_review(proposal)
    alternative_spec = product.draft_spec(alternative, SPEC,
                                          evidence_label="CONFLICTING")
    product.request_review(alternative)
    assert len(product.list_pending_reviews()) == 2

    product.record_review(proposal, disposition="accepted", actor_id="founder",
                          notes="proceeding as a candidate; review required "
                                "before any build")
    product.record_review(alternative, disposition="deferred",
                          actor_id="founder",
                          deferred_until_condition="after the walkthrough "
                                                   "result is observed")
    state = product.get_state()
    assert state.proposals[proposal]["status"] == "accepted"
    assert state.proposals[alternative]["status"] == "deferred"
    assert state.reviews[f"{alternative}:1"]["deferred_until_condition"]

    # --- the founder creates a Decision Record through DecisionService -----
    decision = decisions.create_decision("founder",
                                         idempotency_key="first-value")
    product.link_decision(proposal, decision.decision_id, actor_id="founder")
    product.mark_execution_candidate(proposal, actor_id="founder")
    assert product.list_execution_candidates() == [
        {"proposal_id": proposal, "decision_id": decision.decision_id}]

    # --- a roadmap candidate + proposed diff; ROADMAP.md byte-identical ----
    roadmap_path = REPO_ROOT / "ROADMAP.md"
    before = roadmap_path.read_bytes()
    candidate = product.draft_roadmap_candidate(
        proposal, title="A guided first-run walkthrough", size="M")
    assert candidate["status"] == "PROPOSED — REVIEW REQUIRED"
    diff = product.emit_roadmap_diff(proposal, before.decode("utf-8"))
    assert diff["applied"] is False
    assert diff["proposal_id"] == proposal and diff["spec_version"] == 1
    assert roadmap_path.read_bytes() == before

    # --- portfolio rollup reflects the initiative --------------------------
    view = product.portfolio(portfolio, as_of=AS_OF)
    entry = view["rollup"]["initiatives"][initiative]
    assert entry["opportunity_count"] == 1
    assert entry["proposal_count"] == 2
    assert entry["proposal_count_by_status"] == {"deferred": 1,
                                                 "execution_candidate": 1}
    assert entry["aggregate_research_debt"] >= 1

    # --- snapshot captured and reproducible --------------------------------
    snapshot = capture_proposal_snapshot(product, proposal, as_of=AS_OF)
    again = capture_proposal_snapshot(product, proposal, as_of=AS_OF)
    assert again["snapshot_id"] == snapshot["snapshot_id"]
    assert again["computed_at"] == snapshot["computed_at"]
    assert snapshot["versions"]["research_versions"]["evidence_index_version"]
    assert snapshot["versions"]["growth_versions"]["label_rule_version"]
    assert snapshot["versions"]["analytics_metric_versions"]

    portfolio_snapshot = capture_portfolio_snapshot(product, portfolio,
                                                    as_of=AS_OF)
    assert portfolio_snapshot["invariants"]["invariants"] == "ok"

    # --- replay: zero duplicates -------------------------------------------
    rows_before = len(product.store.read_all())
    product.intake_from_research_package(request_id=request_id,
                                         package_id=package_id, as_of=AS_OF)
    product.intake_from_growth_result(experiment, as_of=AS_OF)
    product.intake_from_crm(entities, as_of=AS_OF)
    assert len(product.store.read_all()) == rows_before
    index = product.get_index()
    assert len(index.proposals) == 2
    assert len(index.problem_index.problems) == \
        len({p["problem_id"] for p in index.problem_index.problems.values()})

    # --- the language wall over the ENTIRE serialized run -------------------
    serialized = "\n".join(row.to_json() for row in product.store.read_all())
    assert scan_banned_language(serialized) == []


# =============================================================================
# Refusal A — a feature without a problem
# =============================================================================

def test_refusal_a_feature_without_a_problem(world):
    product = world[0]
    with pytest.raises(ProductError, match="requires an indexed opportunity"):
        product.draft_proposal(
            "no-such-opportunity", candidate_solution="Add a dashboard",
            tradeoffs=["t"], risks=["r"], known=["k"], unknown=["u"],
            assumptions=["a"])
    with pytest.raises(ProductError, match="zero evidence references"):
        product.record_problem(
            statement="Something feels off in onboarding",
            evidence_references=[], why_now="a hunch",
            what_changes_if_ignored="unclear", first_observed_at=AS_OF)
    # both refusals are recordable as typed facts
    product.record_problem_rejection(
        reason="zero evidence references", statement="Something feels off")
    rejected = [r for r in product.store.read_all()
                if r.event_type == "product.problem_rejected"]
    assert rejected and rejected[0].payload["reason"]


def test_a_proposal_referencing_a_nonexistent_problem_is_rejected(world):
    product, research, growth, crm, *_ = world
    problem = product.record_problem(
        statement="New accounts stall before first value",
        evidence_references=[{"kind": "crm_fact", "ref_id": "crm.churned:E1",
                              "crm_entity_id": "E1"}],
        why_now="current", what_changes_if_ignored="repeats",
        first_observed_at=AS_OF)
    opportunity = product.register_opportunity(
        problem["problem_id"], title="A walkthrough",
        evidence_references=[{"kind": "crm_fact", "ref_id": "crm.churned:E1"}])
    with pytest.raises(ProductError, match="rejected"):
        product._record("product.proposal_drafted", actor_type="agent",
                        actor_id="a", opportunity_id=opportunity,
                        problem_id="NOT-A-PROBLEM", proposal_id="P9",
                        proposal_version=1, subject_type="proposal",
                        subject_id="P9", payload={})


# =============================================================================
# Refusal B — a confident proposal on conflicting evidence
# =============================================================================

def test_refusal_b_confidence_cannot_exceed_conflicting_evidence(world):
    product, research, *_ = world
    request_id, package_id, _ = _conflicting_research_package(research)
    problem = product.record_problem(
        statement="Activation stalls for new accounts",
        evidence_references=[{"kind": "research_conclusion",
                              "ref_id": package_id, "request_id": request_id,
                              "observed_at": AS_OF}],
        why_now="the package is current",
        what_changes_if_ignored="the stall repeats", first_observed_at=AS_OF)
    opportunity = product.register_opportunity(
        problem["problem_id"], title="A shorter first-run flow",
        evidence_references=[{"kind": "research_conclusion",
                              "ref_id": package_id, "request_id": request_id}])
    proposal = product.draft_proposal(
        opportunity, candidate_solution="Shorten the first-run flow",
        tradeoffs=["less explanation"], risks=["accounts miss a step"],
        known=["the linked conclusion is CONFLICTING"],
        unknown=["which population the conflict reflects"],
        assumptions=["the two source populations differ"],
        evidence_label="CONFLICTING")

    scores = product.score_proposal(proposal, as_of=AS_OF, record=False)
    confidence = scores["confidence"]["opportunity_confidence"]
    assert confidence["value"] <= 0.4
    assert "unsettled" in " ".join(confidence["reasons"])

    # and the language wall blocks certainty phrasing on that evidence
    with pytest.raises(ProductError, match="certainty language"):
        product.draft_proposal(
            opportunity,
            candidate_solution="Shortening the flow will definitely lift "
                               "activation",
            tradeoffs=["t"], risks=["r"], known=["k"], unknown=["u"],
            assumptions=["a"], evidence_label="CONFLICTING")


# =============================================================================
# Refusal C — the roadmap write attempt
# =============================================================================

def test_refusal_c_no_code_path_writes_the_roadmap(world):
    product = world[0]
    product_pkg = REPO_ROOT / "src/intent_engine/product"
    for source_file in sorted(product_pkg.glob("*.py")):
        text = source_file.read_text()
        assert "ROADMAP.md" not in text or "write" not in text.split(
            "ROADMAP.md")[1][:200], source_file.name
        assert ".write_text(" not in text, source_file.name
        assert not re.search(r"open\([^)]*['\"]w", text), source_file.name

    # the service has no apply, promote, or schedule surface at all
    for banned in ("apply", "promote", "schedule", "execute", "accept_",
                   "run_task"):
        assert not [m for m in dir(product)
                    if banned in m.lower() and not m.startswith("_")], banned


def test_refusal_c_the_agent_cannot_mark_a_candidate_runnable(world):
    from intent_engine.product.roadmap_diff import assert_never_runnable
    with pytest.raises(ProductError, match="does not move an item"):
        assert_never_runnable("- **Status**: RUNNABLE")


def test_refusal_c_roadmap_is_byte_identical_after_a_full_run(world):
    """Asserted over the whole arc, not just the diff call."""
    product, research, growth, crm, decisions, *_ = world
    roadmap = REPO_ROOT / "ROADMAP.md"
    before = roadmap.read_bytes()

    entities = _churned_customers(crm, 3)
    product.intake_from_crm(entities, as_of=AS_OF)
    index = product.get_index()
    opportunity_id = list(index.opportunities)[0]
    proposal = product.draft_proposal(
        opportunity_id, candidate_solution="Add a guided first run",
        tradeoffs=["t"], risks=["r"], known=["k"], unknown=["u"],
        assumptions=["a"])
    product.draft_spec(proposal, SPEC)
    product.draft_roadmap_candidate(proposal, title="Guided first run")
    product.emit_roadmap_diff(proposal, before.decode("utf-8"))
    product.portfolio(product.create_portfolio("C", actor_id="founder"),
                      as_of=AS_OF)

    assert roadmap.read_bytes() == before


# =============================================================================
# Refusal D — model overreach
# =============================================================================

def test_refusal_d_model_overreach_enters_nothing(world):
    """The fake client returns a draft carrying an invented customer id, a
    fabricated evidence reference, and a numeric priority. None of them
    enters the store, and a typed rejection is recorded."""
    product = world[0]
    client = MagicMock()
    client.call_tool.return_value = {
        "candidate_solution": "Add a guided first run",
        "crm_entity_id": "01INVENTEDCUSTOMERID0000000",
        "evidence_references": [{"kind": "evidence", "ref_id": "FABRICATED"}],
        "priority": 9,
    }
    product.llm_client = client

    with pytest.raises(ModelOverreach) as excinfo:
        product.draft_with_model("candidate_solutions", context="why")

    message = str(excinfo.value)
    assert "crm_entity_id" in message
    assert "evidence_references" in message
    assert "priority" in message

    serialized = "\n".join(row.to_json() for row in product.store.read_all())
    assert "01INVENTEDCUSTOMERID0000000" not in serialized
    assert "FABRICATED" not in serialized

    rejections = [r for r in product.store.read_all()
                  if r.event_type == "product.draft_rejected"]
    assert len(rejections) == 1
    payload = rejections[0].payload
    assert set(payload["forbidden_fields"]) == {"crm_entity_id",
                                                "evidence_references",
                                                "priority"}
    assert rejections[0].provenance["prompt_version"]
    assert rejections[0].provenance["model_version"] == "fake.v0"


def test_a_clean_model_draft_is_a_candidate_with_recorded_provenance(world):
    product = world[0]
    client = MagicMock()
    client.call_tool.return_value = {
        "candidate_solution": "Add a guided first run",
        "tradeoffs": ["adds a surface to maintain"],
        "unknown": ["whether guidance changes activation"]}
    product.llm_client = client
    result = product.draft_with_model("candidate_solutions", context="why")
    assert result["candidate"] is True
    assert result["provenance"]["prompt_version"] == \
        "product_candidate_solutions.v1"
    assert result["provenance"]["model_version"] == "fake.v0"


def test_a_model_failure_records_a_typed_fact_never_an_empty_success(world):
    product = world[0]
    client = MagicMock()
    client.call_tool.side_effect = TimeoutError("upstream timed out")
    product.llm_client = client
    with pytest.raises(TimeoutError):
        product.draft_with_model("spec_wording", context="why")
    failures = [r for r in product.store.read_all()
                if r.event_type == "product.draft_failed"]
    assert len(failures) == 1
    assert failures[0].payload["error_type"] == "TimeoutError"
    assert failures[0].provenance["model_version"] == "fake.v0"


def test_a_model_draft_carrying_an_unexpected_field_is_rejected(world):
    product = world[0]
    client = MagicMock()
    client.call_tool.return_value = {"candidate_solution": "x",
                                     "roadmap_status": "RUNNABLE"}
    product.llm_client = client
    with pytest.raises(ModelOverreach, match="roadmap_status"):
        product.draft_with_model("candidate_solutions", context="why")


# =============================================================================
# Consumer, replay, checkpoint
# =============================================================================

def test_the_consumer_creates_at_most_one_candidate_and_nothing_more(world):
    product, research, growth, crm, decisions, knowledge, bus, tmp = world
    from intent_engine.product.consumer import ProductCompanyEventConsumer

    experiment = _inconclusive_experiment(growth)
    _publish_result_labelled(bus, growth, experiment)
    consumer = ProductCompanyEventConsumer(product)
    assert consumer.consumer_name == "product"

    report = drain(bus, consumer)
    assert report.processed >= 1
    assert consumer.candidates
    state = product.get_state()
    assert state.opportunities                 # a candidate opportunity
    assert state.proposals == {}               # never a proposal
    assert state.specs == {}                   # never a spec
    assert state.roadmap_candidates == {}      # never a roadmap entry


def test_replay_creates_zero_duplicates(world):
    product, research, growth, crm, decisions, knowledge, bus, tmp = world
    from intent_engine.product.consumer import ProductCompanyEventConsumer

    experiment = _inconclusive_experiment(growth)
    _publish_result_labelled(bus, growth, experiment)
    drain(bus, ProductCompanyEventConsumer(product))
    after_first = len(product.store.read_all())
    opportunities = len(product.get_index().opportunities)

    replay(bus, ProductCompanyEventConsumer(product), from_offset=0)
    assert len(product.store.read_all()) == after_first
    assert len(product.get_index().opportunities) == opportunities


def test_a_consumer_failure_cannot_break_an_upstream_system(world):
    product, research, growth, crm, decisions, knowledge, bus, tmp = world
    from intent_engine.product.consumer import ProductCompanyEventConsumer

    experiment = _inconclusive_experiment(growth)
    _publish_result_labelled(bus, growth, experiment)
    consumer = ProductCompanyEventConsumer(product)
    consumer.svc = None                        # a broken product consumer
    try:
        drain(bus, consumer)
    except Exception:                          # noqa: BLE001
        pass
    # growth is untouched and still readable
    assert growth.get_result(experiment)["label"] == "INCONCLUSIVE"


def test_the_consumer_does_not_invent_company_event_types(world):
    """crm.churned is a CRM store fact, not a company event; adding it to
    a closed taxonomy with no producer is the drift the taxonomy
    discipline prevents."""
    from intent_engine.events import EVENT_TYPES
    from intent_engine.product.consumer import _HANDLED
    assert _HANDLED <= EVENT_TYPES
    assert "crm.churned" not in EVENT_TYPES


# =============================================================================
# Snapshots
# =============================================================================

def test_recapturing_the_same_as_of_returns_the_original(world):
    product, research, growth, crm, *_ = world
    entities = _churned_customers(crm, 2)
    product.intake_from_crm(entities, as_of=AS_OF)
    portfolio = product.create_portfolio("Company", actor_id="founder")
    first = capture_portfolio_snapshot(product, portfolio, as_of=AS_OF)
    second = capture_portfolio_snapshot(product, portfolio, as_of=AS_OF)
    assert first == second


def test_a_snapshot_records_the_watermarks_that_reproduce_it(world):
    product, research, growth, crm, *_ = world
    entities = _churned_customers(crm, 2)
    product.intake_from_crm(entities, as_of=AS_OF)
    portfolio = product.create_portfolio("Company", actor_id="founder")
    snapshot = capture_portfolio_snapshot(product, portfolio, as_of=AS_OF)
    watermarks = snapshot["source_high_watermarks"]
    assert watermarks["product_rows"] > 0
    assert watermarks["opportunities"] == len(product.get_index().opportunities)
    assert watermarks["last_event_id"]


# =============================================================================
# The language wall
# =============================================================================

def test_the_language_wall_matches_on_word_boundaries():
    """'provenance' is not 'proven'. This distinction has cost four
    sessions."""
    assert scan_banned_language("provenance is recorded") == []
    assert scan_banned_language("this is proven") == ["proven"]
    assert scan_banned_language("nevertheless") == []
    assert scan_banned_language("it never happens") == ["never"]
    assert scan_banned_language("mustard") == []
    assert scan_banned_language("we must ship") == ["must"]


def test_review_notes_pass_through_the_language_wall(world):
    product, research, growth, crm, *_ = world
    entities = _churned_customers(crm, 2)
    product.intake_from_crm(entities, as_of=AS_OF)
    opportunity = list(product.get_index().opportunities)[0]
    proposal = product.draft_proposal(
        opportunity, candidate_solution="Add a guided first run",
        tradeoffs=["t"], risks=["r"], known=["k"], unknown=["u"],
        assumptions=["a"])
    product.draft_spec(proposal, SPEC)
    product.request_review(proposal)
    with pytest.raises(ProductError, match="overclaims"):
        product.record_review(proposal, disposition="accepted",
                              actor_id="founder",
                              notes="this is obviously the best option")


# =============================================================================
# Product principles
# =============================================================================

def test_the_product_principles_are_declared_in_one_place():
    assert len(PRODUCT_PRINCIPLES) == 11
    joined = " ".join(PRODUCT_PRINCIPLES)
    for expected in ("Every proposal solves one problem",
                     "Every problem has evidence",
                     "Every opportunity is reproducible",
                     "Every score is explainable",
                     "Every roadmap suggestion is non-binding",
                     "Every unknown is explicit",
                     "Every portfolio traces to strategic themes",
                     "Nothing executes automatically"):
        assert expected in joined


# =============================================================================
# Repository invariants (standing section)
# =============================================================================

def test_repository_invariants(world):
    """Exactly one implementation of each concern, and no product code
    that writes another subsystem's store."""
    product = world[0]
    package = REPO_ROOT / "src/intent_engine/product"

    def _count(pattern):
        return sum(f.read_text().count(pattern)
                   for f in package.glob("*.py"))

    # Exactly ONE definition of each concern. Every other module imports
    # and calls it, so a second implementation would show up here as a
    # second `def`.
    assert _count("class ProductEvent") == 1
    assert _count("class ProductStore") == 1
    for one_definition in ("def fold_product(", "def build_index(",
                           "def build_graph(", "def build_problem_statement(",
                           "def build_proposal(", "def build_spec_draft(",
                           "def score_block(", "def cost_of_delay(",
                           "def portfolio_rollup(", "def balance_report(",
                           "def readiness_report(", "def executive_summary(",
                           "def build_roadmap_candidate(",
                           "def render_roadmap_diff(", "def detect_cycles(",
                           "def sequence(", "def find_forbidden_fields(",
                           "def derive_spec_debt(",
                           "def assert_graph_invariants("):
        assert _count(one_definition) == 1, one_definition
    # the one exception is the delegating service method, which is the
    # established idiom (T019 does the same for assemble_package)
    assert _count("def assemble_bundle(") == 2
    assert len(list(package.glob("cli.py"))) == 1
    assert len(list(package.glob("store.py"))) == 1
    assert len(list(package.glob("snapshots.py"))) == 1

    # no second Evidence Index, no second citation model, no second metric
    # engine, no second decision store, no second scoring implementation
    assert _count("class EvidenceIndex") == 0
    assert _count("CITATION_TYPES") == 0
    assert _count("METRIC_VERSIONS = ") == 0
    assert _count("class DecisionService") == 0
    assert _count("def compute_result(") == 0
    assert _count("def coverage_report(") == 0
    assert _count("def research_debt(") == 0
    assert _count("def health_signal(") == 0

    # product writes only its own store
    for source_file in sorted(package.glob("*.py")):
        text = source_file.read_text()
        for forbidden in ("crm.jsonl", "knowledge.jsonl", "feedback.jsonl",
                          "marketing.jsonl", "growth.jsonl", "events.jsonl",
                          "research.jsonl", "decisions.db"):
            assert forbidden not in text, f"{source_file.name}: {forbidden}"

    # and it has no execution, promotion, or approval surface
    for banned in ("promote", "validate_insight", "approve", "publish",
                   "deploy", "ticket", "assign"):
        assert not [m for m in dir(product)
                    if banned in m.lower() and not m.startswith("_")], banned


def test_all_outputs_trace_back_to_append_only_history(world):
    """Every derived artifact is recomputable from the log alone."""
    product, research, growth, crm, *_ = world
    entities = _churned_customers(crm, 2)
    product.intake_from_crm(entities, as_of=AS_OF)
    opportunity = list(product.get_index().opportunities)[0]
    proposal = product.draft_proposal(
        opportunity, candidate_solution="Add a guided first run",
        tradeoffs=["t"], risks=["r"], known=["k"], unknown=["u"],
        assumptions=["a"])

    from intent_engine.product import build_index
    rows = product.store.read_all()
    rebuilt = build_index(rows)
    assert rebuilt.proposals == product.get_index().proposals
    assert rebuilt.problem_index.problems == \
        product.get_index().problem_index.problems
    assert rebuilt.row_count == len(rows)


def test_frozen_assets_untouched(world):
    """The mechanism library is frozen (A3) and product never touches it."""
    library = REPO_ROOT / "src/intent_engine/core/data/mechanisms.json"
    before = library.read_bytes()
    product, research, growth, crm, *_ = world
    entities = _churned_customers(crm, 2)
    product.intake_from_crm(entities, as_of=AS_OF)
    product.portfolio(product.create_portfolio("C", actor_id="founder"),
                      as_of=AS_OF)
    assert library.read_bytes() == before
    assert json.loads(before)


# =============================================================================
# CLI
# =============================================================================

def test_cli_reads_and_never_writes(world, capsys, tmp_path):
    product, research, growth, crm, *_ = world
    from intent_engine.product.cli import main

    entities = _churned_customers(crm, 2)
    product.intake_from_crm(entities, as_of=AS_OF)
    opportunity = list(product.get_index().opportunities)[0]
    proposal = product.draft_proposal(
        opportunity, candidate_solution="Add a guided first run",
        tradeoffs=["t"], risks=["r"], known=["k"], unknown=["u"],
        assumptions=["a"])
    path = str(product.store.path)

    assert main(["--path", path, "pending-reviews"]) == 0
    assert main(["--path", path, "proposal-show", proposal]) == 0
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert payload["candidate_solution"] == "Add a guided first run"

    assert main(["--path", path, "opportunity-show", opportunity]) == 0
    assert main(["--path", path, "--as-of", AS_OF, "scores", proposal]) == 0
    assert main(["--path", path, "lineage", proposal]) == 0
    capsys.readouterr()

    # there is no accept, apply, or schedule command
    for absent in ("accept", "apply", "schedule", "promote"):
        with pytest.raises(SystemExit):
            main(["--path", path, absent])


def test_cli_roadmap_diff_prints_and_leaves_the_file_alone(world, capsys):
    product = world[0]
    crm = world[3]
    from intent_engine.product.cli import main

    entities = _churned_customers(crm, 2)
    product.intake_from_crm(entities, as_of=AS_OF)
    opportunity = list(product.get_index().opportunities)[0]
    proposal = product.draft_proposal(
        opportunity, candidate_solution="Add a guided first run",
        tradeoffs=["t"], risks=["r"], known=["k"], unknown=["u"],
        assumptions=["a"])
    product.draft_spec(proposal, SPEC)
    product.draft_roadmap_candidate(proposal, title="Guided first run")

    roadmap = REPO_ROOT / "ROADMAP.md"
    before = roadmap.read_bytes()
    assert main(["--path", str(product.store.path), "roadmap-diff", proposal,
                 "--roadmap", str(roadmap)]) == 0
    out = capsys.readouterr().out
    assert "emitted, not applied" in out
    assert roadmap.read_bytes() == before
