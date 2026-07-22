"""T021 end-to-end: the golden path, the six refusals, the model boundary,
the consumer, replay, snapshots, the recommendation wall over a whole run,
and the repository invariants.

The golden path runs against the REAL T020, T019, T018, T014, and
DecisionService — not stand-ins — because the point of this subsystem is
that it reads what those already know instead of restating it.

0 real model calls (fake client). 0 network.
"""
import ast
import importlib.util
import inspect
import json
import re
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from intent_engine.core.decision_record import DecisionService
from intent_engine.crm import CRMService
from intent_engine.events import CompanyEventBus, drain, replay
from intent_engine.executive import (
    DECISION_PRINCIPLES, ExecutiveError, ExecutiveService, capture_snapshot,
    scan_banned_language,
)
from intent_engine.executive.consumer import ExecutiveCompanyEventConsumer
from intent_engine.executive.records import (
    REF_CRM_FACT, REF_EXPERIMENT, REF_OPPORTUNITY, REF_PROPOSAL,
    REF_RESEARCH_PACKAGE,
)
from intent_engine.executive.service import ModelOverreach
from intent_engine.growth import NAMESPACE_PRODUCTION, GrowthService
from intent_engine.knowledge import KnowledgeService
from intent_engine.product import ProductService
from intent_engine.research import ResearchService, claim_key

REPO_ROOT = Path(__file__).resolve().parents[1]
AS_OF = "2026-07-21T00:00:00+00:00"
LATER = "2027-07-21T00:00:00+00:00"

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


@pytest.fixture()
def world(tmp_path):
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
    executive = ExecutiveService(
        tmp_path / "executive.jsonl", product_service=product,
        research_service=research, growth_service=growth, crm_service=crm,
        decision_service=decisions, knowledge_service=knowledge,
        event_bus=bus, model_version="fake.v0")
    return (executive, product, research, growth, crm, decisions, knowledge,
            bus, tmp_path)


# =============================================================================
# Upstream fixtures — real artifacts
# =============================================================================

def _at_risk_customers(crm, count=3):
    entities = []
    for i in range(count):
        entity = crm.create_prospect(email=f"c{i}@example.com")
        for event in ("crm.qualified", "crm.opportunity_opened", "crm.won",
                      "crm.customer_activated"):
            crm.record(entity, event, actor_type="human", actor_id="founder")
        crm.record(entity, "crm.customer_at_risk", actor_type="human",
                   actor_id="founder", payload={"reason": "usage stopped"})
        entities.append(entity)
    return entities


def _conflicting_package(research):
    request = research.create_request(
        "Why do new accounts stall before activation?",
        motivation="at-risk customers", constraints=["2026-Q3"],
        scope="activation")
    rid = request["request_id"]
    research.draft_plan(
        rid, goal="explain the stall", questions=QUESTIONS,
        evidence_requirements={"minimum_sources": 2, "minimum_quality": "MEDIUM"},
        stopping_conditions={"max_sources": 12, "corroborated_per_question": 2},
        failure_definition="if no source addresses a question, say so",
        tool_allowlist=["supplied"],
        budget={"max_sources": 12, "max_model_calls": 10})
    research.submit_plan(rid)
    research.approve_plan(rid, actor_id="founder")
    session = research.start_session(rid)

    def _reg_source(cls, text, loc, **over):
        return research.register_source(
            rid, session, source_class=cls, title="A study", text=text,
            locator=loc, retrieved_at=AS_OF, acquisition_method="supplied",
            acquisition_tool="supplied", author="A", publisher="P",
            published_date="2026-07-01T00:00:00+00:00", domain="product", **over)

    paper = _reg_source("peer_reviewed", PAPER_TEXT, "https://x.example/paper")
    press = _reg_source("reputable_press", CONTRA_TEXT, "https://x.example/press",
                        population="small accounts")
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
    return rid, package_id


def _difference_experiment(growth):
    experiment = _reg.register(growth, minimum=20)
    growth.start_experiment(experiment, actor_id="founder")
    _res._populate(growth, experiment, per_arm=45, control_successes=9,
                   treatment_successes=27)
    assert growth.get_result(experiment)["label"] == "DIFFERENCE OBSERVED"
    return experiment


def _accepted_proposal(product, research, crm, entities, request_id, package_id):
    problem = product.record_problem(
        statement="New accounts stall before reaching first value",
        evidence_references=[
            {"kind": "research_conclusion", "ref_id": package_id,
             "request_id": request_id},
            {"kind": "crm_fact", "ref_id": f"crm.customer_at_risk:{entities[0]}",
             "crm_entity_id": entities[0]}],
        why_now="three entities reached an at-risk fact",
        what_changes_if_ignored="the pattern repeats",
        first_observed_at=AS_OF, affected_customers=entities)
    opportunity = product.register_opportunity(
        problem["problem_id"], title="A guided first-run walkthrough",
        evidence_references=[{"kind": "research_conclusion", "ref_id": package_id,
                              "request_id": request_id}],
        work_category="customer_work")
    proposal = product.draft_proposal(
        opportunity, candidate_solution="Add a guided first-run walkthrough",
        tradeoffs=["a surface to maintain"], risks=["accounts skip it"],
        known=["three entities are affected"],
        unknown=["whether guidance is causal"],
        assumptions=["time to first value drives retention"])
    product.draft_spec(proposal, {
        "goals": ["reduce time to first value"], "non_goals": ["pricing"],
        "requirements": ["skippable"], "constraints": ["no signup change"],
        "acceptance_criteria": [
            "the walkthrough records a completion event for at least 1 account"],
        "unknowns": ["the UX is undecided"], "dependencies": [],
        "risks": ["skipped"], "open_questions": ["how many steps"]})
    product.request_review(proposal)
    product.record_review(proposal, disposition="accepted", actor_id="founder")
    return proposal, opportunity


# =============================================================================
# The golden path
# =============================================================================

def test_golden_path(world):
    (executive, product, research, growth, crm, decisions, knowledge, bus,
     tmp) = world

    entities = _at_risk_customers(crm, 3)
    request_id, package_id = _conflicting_package(research)
    experiment = _difference_experiment(growth)
    proposal, opportunity = _accepted_proposal(
        product, research, crm, entities, request_id, package_id)
    decision = decisions.create_decision("founder", idempotency_key="first")
    product.link_decision(proposal, decision.decision_id, actor_id="founder")

    # --- intake creates a candidate from the accepted proposal -------------
    created = executive.intake_from_accepted_proposals()
    assert created
    candidate = created[0]
    index = executive.get_index()
    assert index.candidates[candidate]["origin"]["kind"] == "product_proposal"

    # --- the context carries a horizon and a class, and fingerprints -------
    executive.build_context(
        candidate, decision_horizon="short_term", decision_class="product",
        resolved_inputs={
            f"crm:{entities[0]}": {"category": "AT_RISK"},
            f"research:{package_id}": {"stance": "CONFLICTING"},
            f"experiment:{experiment}": {"label": "DIFFERENCE OBSERVED"}},
        current_assumptions=["retention is the priority this quarter"],
        external_constraints=["no new hires until Q4"])

    # --- the facts the executive reads from the real subsystems ------------
    facts = {
        "research": {"stances": ["CONFLICTING", "SUPPORTED"]},
        "references": [{"kind": REF_RESEARCH_PACKAGE, "ref_id": package_id}],
        "experiments": [{"experiment_id": experiment,
                         "label": "DIFFERENCE OBSERVED"}],
        "metrics": [{"metric_name": "activation", "status": "UNAVAILABLE"}],
        "crm": {"category": "AT_RISK"},
        "input_timestamps": ["2025-01-01T00:00:00+00:00", AS_OF],
        "product": {"spec_present": True, "spec_debt_count": 1,
                    "proposal_status": "accepted"},
        "affected_customers": entities, "downstream_decisions": [],
        "initiatives": ["I1"], "owner": "founder",
        "alignment": None, "budget": None, "needs_budget": True,
        "budget_declared": False, "decision_class": "product",
        "decision_horizon": "short_term", "open_debt": [],
        "unmet_dependencies": [],
    }

    # --- conflict summary names the disagreement, no average ---------------
    conflicts = executive.record_conflicts(candidate, facts)
    assert conflicts["total"] >= 2
    assert "evidence_conflict" in conflicts["kinds"]
    assert "metric_conflict" in conflicts["kinds"]
    assert conflicts["resolution"].startswith("none")

    debt = executive.record_decision_debt(candidate, facts)
    assert debt["total"] >= 1

    # --- six readiness dimensions; financial UNAVAILABLE, decision NO ------
    options = [{"reversibility": "moderate"}, {"reversibility": "easy"}]
    readiness = executive.compute_readiness(
        candidate, {**facts, "open_debt": debt["items"]}, options=options)
    dims = readiness["dimensions"]
    assert dims["financial_readiness"]["status"] == "UNAVAILABLE"
    assert dims["strategic_readiness"]["status"] == "UNAVAILABLE"
    assert dims["decision_readiness"]["value"] is False
    joined = " ".join(dims["decision_readiness"]["reasons"])
    assert "missing budget" in joined
    assert "missing strategy" in joined
    assert readiness["impact"]["value"] in (
        "small", "medium", "large", "transformational")
    assert readiness["reversibility"]["value"] == "moderate"

    # --- a package with three options, each with tradeoffs -----------------
    package = executive.draft_package(
        candidate, decision_question="Do we commit to the walkthrough now?",
        references=[{"kind": REF_PROPOSAL, "ref_id": proposal},
                    {"kind": REF_OPPORTUNITY, "ref_id": opportunity}],
        unknowns=["whether guidance is the cause of the stall"],
        risks=["accounts skip it"], conflict_summary=conflicts,
        decision_debt=debt["items"],
        recommended_next_review="after the next activation cohort",
        contributing=["research", "growth", "crm", "product"],
        evidence_label="CONFLICTING")
    for label, rev in (("Ship now", "moderate"),
                       ("Run one more experiment", "easy"),
                       ("Do nothing this quarter", "easy")):
        executive.add_option(package, label=label, benefits=["b"], costs=["c"],
                             risks=["r"], unknowns=["u"], reversibility=rev,
                             evidence_label="CONFLICTING")

    escalation = executive.assign_escalation(package, readiness,
                                             conflict_summary=conflicts,
                                             decision_class="product")
    assert escalation["level"] in ("needs_founder", "review_scheduled",
                                   "needs_board")

    # --- the triage queue orders the candidate -----------------------------
    queues = executive.triage_queues(as_of=AS_OF)
    op = queues["queues"]["operational"]
    assert candidate in op["order"] or any(
        candidate == u["candidate_id"] for u in op["unrankable"])

    # --- founder review: chooses B where the preference was A --------------
    executive.request_review(package)
    executive.record_review(package, disposition="accepted", actor_id="founder",
                            chosen_option_id="B",
                            notes="proceeding as a candidate; review required")
    executive.record_override(package, chosen_option_id="B",
                              preferred_option_id="A",
                              reason="the conflict is not worth the delay",
                              actor_id="founder")
    override = executive.get_state().overrides[f"{package}:1"]
    assert override["chosen_option_id"] == "B"
    assert override["preferred_option_id"] == "A"

    # --- the founder links a Decision Record; outcome; knowledge -----------
    exec_decision = decisions.create_decision("founder",
                                              idempotency_key="exec-first")
    executive.link_decision(package, exec_decision.decision_id,
                            actor_id="founder")
    executive.observe_outcome(package, observation="activation rose in cohort")
    executive.request_knowledge_candidate(
        package, content="a guided first run associates with higher activation")

    # --- lineage resolves through DecisionService --------------------------
    lineage = executive.lineage(package)
    assert lineage["decision"]["resolved_by"] == \
        "decision_service.get_current_state"
    assert lineage["candidate_id"] == candidate

    # --- traceability holds to a terminal state ----------------------------
    trace = executive.trace(package)
    assert trace["terminal"] is True
    assert trace["state"] == "accepted_linked"
    assert executive.assert_no_dead_ends()["ok"] is True

    # --- a SECOND package is rejected; the invariant STILL holds -----------
    candidate2 = executive.register_candidate(
        references=[{"kind": REF_CRM_FACT,
                     "ref_id": f"crm.customer_at_risk:{entities[1]}",
                     "crm_entity_id": entities[1]}],
        origin={"kind": "manual", "origin_id": "second"})
    executive.build_context(candidate2, decision_horizon="short_term",
                            decision_class="operational",
                            resolved_inputs={"x": {"a": 1}})
    package2 = executive.draft_package(
        candidate2, decision_question="Should we pause outreach?",
        references=[{"kind": REF_CRM_FACT,
                     "ref_id": f"crm.customer_at_risk:{entities[1]}"}],
        unknowns=["whether outreach is the cause"])
    for label in ("Pause", "Continue"):
        executive.add_option(package2, label=label, benefits=["b"], costs=["c"],
                             risks=["r"], unknowns=["u"], reversibility="easy")
    executive.request_review(package2)
    executive.record_review(package2, disposition="rejected", actor_id="founder")
    assert executive.trace(package2)["terminal"] is True
    assert executive.assert_no_dead_ends()["ok"] is True

    # --- portfolio + dashboard --------------------------------------------
    dashboard = executive.health_dashboard(as_of=AS_OF)
    assert dashboard["conflict_count"] >= 2
    assert dashboard["decision_debt"] >= 1

    # --- snapshot captured and reproducible --------------------------------
    snapshot = capture_snapshot(executive, package, as_of=AS_OF, scope="package")
    again = capture_snapshot(executive, package, as_of=AS_OF, scope="package")
    assert again["snapshot_id"] == snapshot["snapshot_id"]
    assert snapshot["versions"]["research_versions"]["evidence_index_version"]
    assert snapshot["versions"]["product_versions"]["opportunity_index_version"]
    assert snapshot["versions"]["growth_versions"]["label_rule_version"]

    # --- replay: intake adds nothing new -----------------------------------
    rows_before = len(executive.store.read_all())
    executive.intake_from_accepted_proposals()
    assert len(executive.store.read_all()) == rows_before

    # --- the recommendation wall over the ENTIRE serialized run ------------
    serialized = "\n".join(row.to_json() for row in executive.store.read_all())
    assert scan_banned_language(serialized) == []

    # --- invariants --------------------------------------------------------
    assert executive.get_index().assert_invariants()["invariants"] == "ok"


# =============================================================================
# Refusals
# =============================================================================

def test_refusal_a_no_averaged_conflict(world):
    executive = world[0]
    package_dir = REPO_ROOT / "src/intent_engine/executive"
    text = (package_dir / "conflicts.py").read_text()
    tree = ast.parse(text)
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    names |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    for banned in ("mean", "average", "weighted", "overall_score",
                   "combined_score"):
        assert banned not in names, banned


def test_refusal_b_no_alternatives_and_no_unknowns(world):
    executive = world[0]
    candidate = executive.register_candidate(
        references=[{"kind": REF_PROPOSAL, "ref_id": "P1"}],
        origin={"kind": "manual", "origin_id": "o1"})
    executive.build_context(candidate, decision_horizon="short_term",
                            decision_class="product",
                            resolved_inputs={"x": 1})
    # no unknowns -> rejected
    with pytest.raises(ExecutiveError, match="claiming none is hiding them"):
        executive.draft_package(candidate, decision_question="q",
                                references=[{"kind": REF_PROPOSAL,
                                             "ref_id": "P1"}], unknowns=[])
    # one option -> review rejected (approve/reject is not a choice)
    package = executive.draft_package(
        candidate, decision_question="q",
        references=[{"kind": REF_PROPOSAL, "ref_id": "P1"}], unknowns=["u"])
    executive.add_option(package, label="Only", benefits=["b"], costs=["c"],
                         risks=["r"], unknowns=["u"], reversibility="easy")
    with pytest.raises(ExecutiveError, match="at least two options"):
        executive.request_review(package)


def test_refusal_c_no_mirrored_decision_store(world):
    package_dir = REPO_ROOT / "src/intent_engine/executive"
    for source_file in sorted(package_dir.glob("*.py")):
        text = source_file.read_text()
        assert "decisions.db" not in text, source_file.name
        assert ".create_decision(" not in text, source_file.name
        assert "record_event(" not in text, source_file.name


def test_refusal_d_no_autonomous_execution(world):
    executive = world[0]
    for banned in ("create_decision", "start_experiment", "launch",
                   "schedule", "promote", "publish", "apply", "execute",
                   "write_roadmap", "record_prediction"):
        assert not [m for m in dir(executive)
                    if banned in m.lower() and not m.startswith("_")], banned


def test_refusal_e_model_overreach_enters_nothing(world):
    executive = world[0]
    client = MagicMock()
    client.call_tool.return_value = {
        "decision_question": "Do we ship?",
        "decision_id": "01INVENTEDDECISIONID00000000",
        "prediction_id": "01FABRICATEDPREDICTION000000",
        "decision_readiness": 0.9}
    executive.llm_client = client
    with pytest.raises(ModelOverreach) as excinfo:
        executive.draft_with_model("package_prose", context="why")
    message = str(excinfo.value)
    assert "decision_id" in message
    assert "prediction_id" in message
    assert "decision_readiness" in message
    serialized = "\n".join(r.to_json() for r in executive.store.read_all())
    assert "01INVENTEDDECISIONID00000000" not in serialized
    assert "01FABRICATEDPREDICTION000000" not in serialized
    rejections = [r for r in executive.store.read_all()
                  if r.event_type == "executive.draft_rejected"]
    assert len(rejections) == 1
    assert set(rejections[0].payload["forbidden_fields"]) == {
        "decision_id", "prediction_id", "decision_readiness"}
    assert rejections[0].provenance["model_version"] == "fake.v0"


def test_a_model_failure_records_a_typed_fact(world):
    executive = world[0]
    client = MagicMock()
    client.call_tool.side_effect = TimeoutError("upstream timed out")
    executive.llm_client = client
    with pytest.raises(TimeoutError):
        executive.draft_with_model("option_prose", context="why")
    failures = [r for r in executive.store.read_all()
                if r.event_type == "executive.draft_failed"]
    assert len(failures) == 1
    assert failures[0].payload["error_type"] == "TimeoutError"


def test_refusal_f_a_clock_does_not_expire_a_decision(world):
    executive = world[0]
    fingerprints = {"research:R1": "abc", "crm:E1": "def"}
    unchanged = executive.intake_from_expired_decision(
        "D1", recorded_fingerprints=fingerprints,
        current_fingerprints=fingerprints, as_of=LATER,
        references=[{"kind": REF_CRM_FACT, "ref_id": "crm.churned:E1"}])
    assert unchanged is None            # a year passed; nothing changed
    changed = executive.intake_from_expired_decision(
        "D1", recorded_fingerprints=fingerprints,
        current_fingerprints={**fingerprints, "research:R1": "xyz"},
        as_of=AS_OF,
        references=[{"kind": REF_CRM_FACT, "ref_id": "crm.churned:E1"}])
    assert changed is not None          # an input moved; now it expired


# =============================================================================
# Consumer, replay, checkpoint
# =============================================================================

def test_the_consumer_creates_at_most_one_candidate(world):
    executive, product, growth, *_ = (world[0], world[1], world[3],)
    crm = world[4]
    decisions = world[5]
    bus = world[7]
    decision = decisions.create_decision("founder", idempotency_key="c1")
    bus.publish("decision.resolved", subject_type="decision",
                subject_id=decision.decision_id, producer="decision_event_bridge",
                actor_type="human", actor_id="founder", source="system",
                decision_id=decision.decision_id,
                payload={"resolution": "approved"},
                idempotency_key="resolved:c1")
    consumer = ExecutiveCompanyEventConsumer(executive)
    assert consumer.consumer_name == "executive"
    report = drain(bus, consumer)
    assert report.processed >= 1
    state = executive.get_state()
    assert state.candidates            # a candidate
    assert state.packages == {}        # never a package
    assert state.outcomes == {}        # never an outcome


def test_replay_creates_zero_duplicates(world):
    executive = world[0]
    decisions = world[5]
    bus = world[7]
    decision = decisions.create_decision("founder", idempotency_key="c1")
    bus.publish("decision.resolved", subject_type="decision",
                subject_id=decision.decision_id, producer="decision_event_bridge",
                actor_type="human", actor_id="founder", source="system",
                decision_id=decision.decision_id, payload={},
                idempotency_key="resolved:c1")
    drain(bus, ExecutiveCompanyEventConsumer(executive))
    after_first = len(executive.store.read_all())
    replay(bus, ExecutiveCompanyEventConsumer(executive), from_offset=0)
    assert len(executive.store.read_all()) == after_first


def test_a_consumer_failure_cannot_break_upstream(world):
    executive = world[0]
    decisions = world[5]
    bus = world[7]
    decision = decisions.create_decision("founder", idempotency_key="c1")
    bus.publish("decision.resolved", subject_type="decision",
                subject_id=decision.decision_id, producer="decision_event_bridge",
                actor_type="human", actor_id="founder", source="system",
                decision_id=decision.decision_id, payload={},
                idempotency_key="resolved:c1")
    consumer = ExecutiveCompanyEventConsumer(executive)
    consumer.svc = None
    try:
        drain(bus, consumer)
    except Exception:                  # noqa: BLE001
        pass
    # the decision store is untouched and still readable
    assert decisions.get_decision(decision.decision_id) is not None


def test_the_consumer_only_handles_taxonomy_event_types(world):
    from intent_engine.events import EVENT_TYPES
    from intent_engine.executive.consumer import _HANDLED
    assert _HANDLED <= EVENT_TYPES


# =============================================================================
# Decision principles
# =============================================================================

def test_the_decision_principles_are_declared_in_one_place():
    assert len(DECISION_PRINCIPLES) == 12
    joined = " ".join(DECISION_PRINCIPLES)
    for expected in ("Every recommendation has alternatives",
                     "Every recommendation exposes disagreement",
                     "Every recommendation is replayable",
                     "Every recommendation is reversibility-aware",
                     "Every recommendation cites evidence",
                     "Nothing executes automatically",
                     "Declining to recommend is a legitimate outcome"):
        assert expected in joined


# =============================================================================
# Repository invariants
# =============================================================================

def test_repository_invariants(world):
    executive = world[0]
    package = REPO_ROOT / "src/intent_engine/executive"

    def _count(pattern):
        return sum(f.read_text().count(pattern) for f in package.glob("*.py"))

    assert _count("class ExecutiveEvent") == 1
    assert _count("class ExecutiveStore") == 1
    # Exactly one DEFINITION of each concern. `build_context` and
    # `build_package` are the established definition + delegating-service-
    # method idiom (T020 does the same for assemble_package), so they
    # appear twice: the pure function and the ExecutiveService method that
    # wraps it.
    for one_def in ("def fold_executive(", "def build_index(",
                    "def build_graph(", "def build_package(",
                    "def build_option(", "def detect_conflicts(",
                    "def conflict_summary(", "def readiness_block(",
                    "def decision_impact(", "def derive_decision_debt(",
                    "def build_queues(", "def find_forbidden_fields(",
                    "def executive_portfolio(", "def trace_package(",
                    "def expiry_check("):
        assert _count(one_def) == 1, one_def
    for definition_plus_method in ("def build_context(", "def assign_escalation(",
                                   "def assert_no_dead_ends(",
                                   "def health_dashboard("):
        assert _count(definition_plus_method) == 2, definition_plus_method
    assert len(list(package.glob("cli.py"))) == 1
    assert len(list(package.glob("store.py"))) == 1

    # no second Evidence Index, Opportunity Index, citation model, metric
    # engine, decision store, or scoring/readiness implementation
    assert _count("class EvidenceIndex") == 0
    assert _count("class OpportunityIndex") == 0
    assert _count("CITATION_TYPES") == 0
    assert _count("METRIC_VERSIONS = ") == 0
    assert _count("class DecisionService") == 0
    assert _count("def score_block(") == 0        # T020's scoring, not copied
    assert _count("def portfolio_rollup(") == 0   # T020's rollup, read not rebuilt

    for source_file in sorted(package.glob("*.py")):
        text = source_file.read_text()
        for forbidden in ("crm.jsonl", "knowledge.jsonl", "feedback.jsonl",
                          "marketing.jsonl", "growth.jsonl", "product.jsonl",
                          "research.jsonl", "decisions.db"):
            assert forbidden not in text, f"{source_file.name}: {forbidden}"

    for banned in ("promote", "approve_", "publish", "deploy", "ticket",
                   "create_decision", "record_prediction"):
        assert not [m for m in dir(executive)
                    if banned in m.lower() and not m.startswith("_")], banned


def test_the_new_traceability_invariant_holds_across_the_repo(world):
    """Every recommendation traces to a terminal state; the invariant is
    stated over TERMINAL, so rejected and deferred are legitimate."""
    executive = world[0]
    report = executive.assert_no_dead_ends()
    assert "rejected" in report["terminal_states"]
    assert "deferred" in report["terminal_states"]
    assert report["ok"] is True        # empty is trivially ok


def test_readiness_and_scoring_are_not_duplication():
    """T020's scoring and T021's readiness both exist; this states, in the
    test, why that is not a duplicated implementation — they answer
    different questions over different inputs, so a future audit does not
    flag the pair.

    T020 scoring: is a PROPOSAL worth building, from product evidence.
    T021 readiness: could a DECISION be made now, from cross-system state.
    Different subjects, different inputs, different outputs (a composite
    score vs six independent statuses). Neither imports the other.
    """
    import intent_engine.executive.readiness as exec_readiness
    import intent_engine.product.scoring as product_scoring
    exec_src = inspect.getsource(exec_readiness)
    assert "from intent_engine.product.scoring" not in exec_src
    assert "score_block" not in exec_src
    # and the product scorer does not import the executive readiness
    product_src = inspect.getsource(product_scoring)
    assert "executive" not in product_src


# =============================================================================
# Frozen assets + CLI
# =============================================================================

def test_frozen_assets_untouched(world):
    library = REPO_ROOT / "src/intent_engine/core/data/mechanisms.json"
    before = library.read_bytes()
    executive = world[0]
    executive.register_candidate(references=[{"kind": REF_PROPOSAL,
                                              "ref_id": "P1"}],
                                 origin={"kind": "manual", "origin_id": "o1"})
    executive.health_dashboard(as_of=AS_OF)
    assert library.read_bytes() == before


def test_roadmap_is_byte_identical_after_a_run(world):
    roadmap = REPO_ROOT / "ROADMAP.md"
    before = roadmap.read_bytes()
    executive = world[0]
    cand = executive.register_candidate(
        references=[{"kind": REF_PROPOSAL, "ref_id": "P1"}],
        origin={"kind": "manual", "origin_id": "o1"})
    executive.build_context(cand, decision_horizon="short_term",
                            decision_class="product", resolved_inputs={"x": 1})
    executive.triage_queues(as_of=AS_OF)
    assert roadmap.read_bytes() == before


def test_cli_reads_and_never_writes(world, capsys):
    executive = world[0]
    from intent_engine.executive.cli import main
    cand = executive.register_candidate(
        references=[{"kind": REF_PROPOSAL, "ref_id": "P1"}],
        origin={"kind": "manual", "origin_id": "o1"})
    path = str(executive.store.path)
    assert main(["--path", path, "--as-of", AS_OF, "queue"]) == 0
    assert main(["--path", path, "--as-of", AS_OF, "dashboard"]) == 0
    assert main(["--path", path, "candidate-show", cand]) == 0
    capsys.readouterr()
    for absent in ("accept", "apply", "schedule", "promote"):
        with pytest.raises(SystemExit):
            main(["--path", path, absent])
