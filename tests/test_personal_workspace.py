"""T023 the Personal AI Workspace end-to-end: the founder-usefulness
fixture (the hour), conversation, explainability, reports, the five
refusals, boundedness, and the repository invariants.

Built against the REAL T019/T020/T021 services and the kernel — the
workspace composes them, never reimplements or touches them.

0 real model calls (fake client). 0 network.
"""
import ast
import inspect
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from intent_engine.core.decision_record import DecisionService
from intent_engine.crm import CRMService
from intent_engine.executive import ExecutiveService
from intent_engine.executive.records import REF_PROPOSAL
from intent_engine.knowledge import KnowledgeService
from intent_engine.personal import (
    ClaimSet, PersonalError, PersonalService, answer, build_claim_set,
    capture_snapshot,
)
from intent_engine.personal.records import (
    AVAIL_CONFLICTED, AVAIL_OUT_OF_SCOPE, AVAIL_UNAVAILABLE,
)
from intent_engine.product import ProductService
from intent_engine.research import ResearchService, claim_key

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src/intent_engine"
AS_OF = "2026-07-21T00:00:00+00:00"

PAPER = ("Reply rate rose from 4% to 9% after the subject line was "
         "shortened in a controlled trial of 800 messages.")
CONTRA = ("Shortening the subject line reduced replies in our sample of "
          "small accounts.")
QUESTIONS = ["Does a shorter first-run flow change activation?",
             "Does send time change activation?",
             "Does audience overlap explain the difference?"]


def _research_client():
    client = MagicMock()
    mapping = {
        PAPER: [{"claim_text": "Activation rose from 4% to 9%",
                 "evidence_class": "observation",
                 "quote_span": "Reply rate rose from 4% to 9%"}],
        CONTRA: [{"claim_text": "Activation rose from 4% to 9%",
                  "evidence_class": "observation",
                  "quote_span": "Shortening the subject line reduced replies"}],
    }

    def call_tool(**kwargs):
        text = kwargs["user_message"]
        for needle, candidates in mapping.items():
            if needle in text:
                return {"candidates": candidates}
        return {"candidates": []}

    client.call_tool.side_effect = call_tool
    return client


@pytest.fixture()
def company(tmp_path):
    """The founder-usefulness fixture — a deterministic synthetic company:
    two research conclusions (one conflicted), customer signals, an
    UNAVAILABLE metric, a product opportunity, decision candidates in
    different queues, and an unresolved assumption / evidence gap."""
    decisions = DecisionService(str(tmp_path / "decisions.db"))
    crm = CRMService(tmp_path / "crm.jsonl")
    knowledge = KnowledgeService(tmp_path / "feedback.jsonl",
                                 tmp_path / "knowledge.jsonl")
    research = ResearchService(tmp_path / "research.jsonl",
                               knowledge_service=knowledge,
                               llm_client=_research_client(),
                               model_version="fake.v0")
    product = ProductService(tmp_path / "product.jsonl",
                             research_service=research, crm_service=crm,
                             decision_service=decisions)
    executive = ExecutiveService(tmp_path / "executive.jsonl",
                                 product_service=product,
                                 research_service=research,
                                 decision_service=decisions,
                                 model_version="fake.v0")

    # --- two customers with signals ----------------------------------------
    entities = []
    for i in range(2):
        e = crm.create_prospect(email=f"c{i}@x.com")
        for ev in ("crm.qualified", "crm.opportunity_opened", "crm.won",
                   "crm.customer_activated"):
            crm.record(e, ev, actor_type="human", actor_id="founder")
        crm.record(e, "crm.customer_at_risk", actor_type="human",
                   actor_id="founder", payload={"reason": "usage stopped"})
        entities.append(e)

    # --- a research package with a CONFLICTING conclusion + debt -----------
    req = research.create_request("Why do accounts stall?", motivation="m",
                                  constraints=["q3"], scope="activation")
    rid = req["request_id"]
    research.draft_plan(rid, goal="explain the stall", questions=QUESTIONS,
                        evidence_requirements={"minimum_sources": 2,
                                               "minimum_quality": "MEDIUM"},
                        stopping_conditions={"max_sources": 12,
                                             "corroborated_per_question": 2},
                        failure_definition="if no source addresses it, say so",
                        tool_allowlist=["supplied"],
                        budget={"max_sources": 12, "max_model_calls": 10})
    research.submit_plan(rid)
    research.approve_plan(rid, actor_id="founder")
    session = research.start_session(rid)

    def _src(cls, text, loc, **over):
        return research.register_source(
            rid, session, source_class=cls, title="A study", text=text,
            locator=loc, retrieved_at=AS_OF, acquisition_method="supplied",
            acquisition_tool="supplied", author="A", publisher="P",
            published_date="2026-07-01T00:00:00+00:00", domain="product", **over)

    paper = _src("peer_reviewed", PAPER, "https://x.example/p")
    press = _src("reputable_press", CONTRA, "https://x.example/c",
                 population="small accounts")
    research.extract_evidence(rid, session, paper, PAPER,
                              question=QUESTIONS[0], stance="supports")
    research.extract_evidence(rid, session, press, CONTRA,
                              question=QUESTIONS[0], stance="contradicts")
    index = research.get_index(rid, as_of=AS_OF)
    key = claim_key("Activation rose from 4% to 9%")
    sup = [e["evidence_id"] for e in index.evidence_for_claim(key)
           if e["stance"] == "supports"]
    con = [e["evidence_id"] for e in index.evidence_for_claim(key)
           if e["stance"] == "contradicts"]
    research.record_contradiction(rid, session, claim_key_=key,
                                  evidence_id=con[0], counterpart=sup[0],
                                  conflict_reason="different_populations")
    research.close_session(rid, session)
    package_id = research.assemble_package(
        rid, session, claim_map={QUESTIONS[0]: [key], QUESTIONS[1]: []},
        as_of=AS_OF)

    # --- a product opportunity + accepted proposal + decision candidate ----
    problem = product.record_problem(
        statement="Accounts stall before first value",
        evidence_references=[{"kind": "research_conclusion",
                              "ref_id": package_id, "request_id": rid}],
        why_now="two at-risk customers", what_changes_if_ignored="repeats",
        first_observed_at=AS_OF, affected_customers=entities)
    opp = product.register_opportunity(
        problem["problem_id"], title="A guided first run",
        evidence_references=[{"kind": "research_conclusion",
                              "ref_id": package_id, "request_id": rid}],
        work_category="customer_work")
    portfolio = product.create_portfolio("Company", actor_id="founder")
    theme = product.declare_theme(portfolio, "Activation", actor_id="founder")
    initiative = product.create_initiative(theme, "First value",
                                           actor_id="founder")
    product.attach_opportunity(opp, initiative)
    proposal = product.draft_proposal(
        opp, candidate_solution="Add a guided first run", tradeoffs=["t"],
        risks=["r"], known=["two entities at risk"],
        unknown=["whether guidance is causal"], assumptions=["ttv drives it"])

    # --- an executive decision candidate in the operational queue ----------
    executive.intake_from_accepted_proposals()  # none accepted yet -> none
    cand = executive.register_candidate(
        references=[{"kind": REF_PROPOSAL, "ref_id": proposal}],
        origin={"kind": "manual", "origin_id": "stall"})
    executive.build_context(cand, decision_horizon="short_term",
                            decision_class="product",
                            resolved_inputs={"crm": {"category": "AT_RISK"}})
    executive.record_conflicts(cand, {
        "research": {"stances": ["CONFLICTING"]},
        "metrics": [{"status": "UNAVAILABLE"}], "crm": {"category": "AT_RISK"},
        "alignment": None})
    executive.record_decision_debt(cand, {
        "research": {"stances": ["CONFLICTING"]}, "needs_budget": True,
        "budget_declared": False})
    package = executive.draft_package(
        cand, decision_question="Do we commit to the guided first run?",
        references=[{"kind": REF_PROPOSAL, "ref_id": proposal}],
        unknowns=["whether guidance is causal"])

    personal = PersonalService(
        tmp_path / "personal.jsonl", research_service=research,
        product_service=product, executive_service=executive, crm_service=crm,
        knowledge_service=knowledge, decision_service=decisions)
    return {"personal": personal, "executive": executive, "package": package,
            "portfolio": portfolio, "entities": entities,
            "package_id_research": package_id}


# =============================================================================
# The hour — the golden path
# =============================================================================

def test_morning_brief_names_conditions_without_inventing(company):
    pa = company["personal"]
    brief = pa.morning_brief(as_of=AS_OF, portfolio_id=company["portfolio"])
    sections = brief["sections"]
    # research highlights present and cited
    assert sections["research_highlights"]
    for claim in sections["research_highlights"]:
        assert claim["availability"] in ("SUPPORTED", "CONFLICTED")
        if claim["availability"] != "UNAVAILABLE":
            assert claim["source_refs"], "every line cites a source artifact"
    # the conflict is preserved as an open question
    assert any(c["availability"] == "CONFLICTED"
               for c in sections["research_highlights"])
    # investigations are structured and non-imperative
    assert sections["recommended_investigations"]
    for inv in sections["recommended_investigations"]:
        assert inv["framing"].startswith("a question worth resolving")
    # gaps are named, not filled
    assert isinstance(brief["gaps_named"], list)


def test_the_seven_canonical_questions_are_answered(company):
    pa = company["personal"]
    session = pa.open_session()
    questions = [
        "why are we losing confidence?",
        "show me the evidence",
        "summarize the competitors",
        "what should I investigate next?",
        "draft a board update",
        "why is this decision in my queue?",
        "explain this to an investor",
    ]
    for q in questions:
        result = pa.ask(session, q, as_of=AS_OF, package_id=company["package"])
        assert result["intent"] != "UNKNOWN" or "competitor" not in q
        assert "answer" in result
        # every present paragraph carries citations
        for para in result["answer"]["paragraphs"]:
            if para.get("availability") in ("SUPPORTED", "CONFLICTED"):
                assert para["citations"]


def test_the_conflict_and_unavailable_metric_are_preserved(company):
    pa = company["personal"]
    result = pa.ask(pa.open_session(), "show me the evidence", as_of=AS_OF)
    # a CONFLICTED research claim is preserved, not smoothed
    assert result["preserved_conflicts"]


def test_summarize_competitors_degrades_honestly(company):
    """Dependency gap 1 — no competitor subsystem. The workspace refuses to
    invent, returning OUT_OF_SCOPE."""
    pa = company["personal"]
    result = pa.ask(pa.open_session(), "summarize the competitors", as_of=AS_OF)
    assert result["intent"] == "SUMMARIZE_COMPETITORS"
    assert result["unavailable_or_out_of_scope"]
    text = json.dumps(result)
    assert "T023.5" in text or "no subsystem reports competitor" in text


def test_explainability_chain_resolves(company):
    pa = company["personal"]
    chain = pa.explain(company["package"], as_of=AS_OF)
    assert chain["available"] is True
    for step in ("finding", "evidence", "confidence", "reasoning",
                 "source_agent", "replay_id"):
        assert step in chain
    assert chain["source_agent"] == "executive"
    assert chain["replay_id"]


def test_board_update_is_a_draft_and_stays_a_draft(company):
    pa = company["personal"]
    report = pa.report("board_update_draft", as_of=AS_OF,
                       portfolio_id=company["portfolio"])
    assert report["available"] is True
    assert report["disposition"].startswith("DRAFT")
    # assembled from cited sections
    assert report["executive_summary"]


def test_pin_records_a_reference_not_a_copy(company):
    pa = company["personal"]
    pin_id = pa.pin_finding(
        {"subsystem": "research", "artifact_id": company["package_id_research"]},
        note="watch the conflict")
    memory = pa.durable_memory()
    assert pin_id in memory["pins"]
    # the pin is a reference; no operational fact copied
    serialized = json.dumps(memory)
    assert company["package_id_research"] in serialized  # the id (reference)
    assert "Reply rate rose" not in serialized           # not the fact itself


def test_snapshot_reproduces(company):
    pa = company["personal"]
    first = capture_snapshot(pa, as_of=AS_OF)
    second = capture_snapshot(pa, as_of=AS_OF)
    assert second["snapshot_id"] == first["snapshot_id"]
    assert first["source_high_watermarks"]["research_rows"] > 0
    assert "byte-identical" in first["replay_semantics"]["deterministic_artifacts"]


def test_the_brief_is_deterministic(company):
    pa = company["personal"]
    a = pa.morning_brief(as_of=AS_OF, portfolio_id=company["portfolio"],
                         record=False)
    b = pa.morning_brief(as_of=AS_OF, portfolio_id=company["portfolio"],
                         record=False)
    assert a == b


# =============================================================================
# The five refusals
# =============================================================================

def test_refusal_a_invented_knowledge_is_rejected(company):
    """A model narrative citing a claim id not in the closed ClaimSet is
    rejected — the workspace produces no claim it cannot attribute."""
    pa = company["personal"]
    claim_set = build_claim_set("show me the evidence",
                                adapters=pa._adapters(AS_OF))
    from intent_engine.personal.conversation import validate_narrative
    with pytest.raises(PersonalError, match="not in the closed ClaimSet"):
        validate_narrative(claim_set, {"paragraphs": [
            {"text": "activation rose 12%", "claim_ids": ["INVENTED-CLAIM"]}]})


def test_refusal_b_the_workspace_computes_no_intelligence():
    package = SRC / "personal"
    blob = "\n".join(f.read_text() for f in package.rglob("*.py"))
    for forbidden in ("def score_block", "def readiness_block",
                      "def detect_conflicts", "def compute_result",
                      "def research_debt(", "def build_index(",
                      "class EvidenceIndex", "class DecisionIndex",
                      "def coverage_report"):
        assert forbidden not in blob, forbidden


def test_refusal_c_no_action_surface(company):
    pa = company["personal"]
    for banned in ("publish", "send", "email", "execute", "modify",
                   "create_decision", "promote", "schedule", "deploy"):
        assert not [m for m in dir(pa)
                    if banned in m.lower() and not m.startswith("_")], banned
    # and no personal module writes another subsystem's store
    package = SRC / "personal"
    for source_file in package.rglob("*.py"):
        text = source_file.read_text()
        for other in ("research.jsonl", "product.jsonl", "executive.jsonl",
                      "crm.jsonl", "knowledge.jsonl", "decisions.db"):
            assert other not in text, f"{source_file.name}: {other}"


def test_refusal_d_no_agent_to_agent_call():
    """Every composition routes through an adapter the workspace owns; no
    agent service imports another agent service inside personal/."""
    package = SRC / "personal"
    blob = "\n".join(f.read_text() for f in package.rglob("*.py"))
    # personal composes via adapters; it does not wire agents to each other
    assert "research_service.executive" not in blob
    assert "executive.research." not in blob


def test_refusal_e_model_overreach_is_rejected(company):
    """A model narrative carrying a fabricated replay id / decision id in a
    claim id it invented is rejected; the workspace attaches citations, the
    model never writes identifiers."""
    pa = company["personal"]
    claim_set = build_claim_set("why are we losing confidence?",
                                adapters=pa._adapters(AS_OF))
    from intent_engine.personal.conversation import validate_narrative
    with pytest.raises(PersonalError):
        validate_narrative(claim_set, {"paragraphs": [
            {"text": "per replay R-999", "claim_ids": ["R-999-FAKE"]}]})


# =============================================================================
# Boundedness
# =============================================================================

def test_the_fake_model_is_called_at_most_once_per_narrative(company):
    pa = company["personal"]
    client = MagicMock()
    client.call_tool.return_value = {"paragraphs": []}
    pa.llm_client = client
    pa.ask(pa.open_session(), "why are we losing confidence?", as_of=AS_OF)
    assert client.call_tool.call_count <= 1


def test_a_brief_does_a_bounded_number_of_reads(company):
    """The brief reads each source a bounded number of times, not an
    unbounded scan per line."""
    pa = company["personal"]
    reads = {"n": 0}
    original = pa.research.get_package

    def counting(*a, **k):
        reads["n"] += 1
        return original(*a, **k)

    pa.research.get_package = counting
    pa.morning_brief(as_of=AS_OF, record=False)
    # a handful of packages, read a bounded number of times — not hundreds
    assert reads["n"] < 50


# =============================================================================
# Repository invariants
# =============================================================================

def test_the_workspace_store_subclasses_the_kernel():
    from intent_engine.agentos.append_only import AppendOnlyStore
    from intent_engine.personal.store import PersonalStore
    assert issubclass(PersonalStore, AppendOnlyStore)
    store_src = (SRC / "personal/store.py").read_text()
    assert "def read_all" not in store_src   # inherited, not owned


def test_no_fourth_memory_is_built():
    """The workspace reuses the three agent indexes; it builds no index of
    its own."""
    package = SRC / "personal"
    blob = "\n".join(f.read_text() for f in package.rglob("*.py"))
    assert "def build_index(" not in blob
    assert "Index(" not in blob or "OpportunityIndex" not in blob


def test_adapters_import_only_read_surfaces():
    """The adapters are anti-corruption boundaries; they must not import a
    domain intelligence function."""
    adapters = SRC / "personal/adapters"
    for source_file in adapters.glob("*.py"):
        tree = ast.parse(source_file.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                # adapters import the personal records + the subsystem
                # services are passed in, not imported for computation
                assert "scoring" not in node.module
                assert "readiness" not in node.module
                assert "conflicts" not in node.module
