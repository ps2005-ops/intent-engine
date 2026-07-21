"""T020 automatic opportunity intake.

Research debt, unsettled growth results, and CRM pain become candidate
opportunities that cite their origin and inherit its uncertainty.
Deterministic, idempotent, and never a roadmap entry.
0 model calls. 0 network.
"""
import pytest

from intent_engine.product import ProductError, ProductService
from intent_engine.product.intake import (
    RESEARCH_DEBT_TEMPLATES, intake_candidates_from_crm,
    intake_candidates_from_growth, intake_candidates_from_research_debt,
)
from intent_engine.research.records import DEBT_KINDS

AS_OF = "2026-07-21T00:00:00+00:00"

SIX_NAMED_KINDS = ("need_customer_interview", "need_experiment",
                   "need_primary_source", "need_replication",
                   "need_independent_corroboration", "need_newer_evidence")


def _package(kinds):
    return {"package_version": "evidence_package.v1",
            "research_debt": [{"kind": kind, "question": f"Q for {kind}",
                               "detail": "recorded by T019"}
                              for kind in kinds]}


@pytest.fixture()
def svc(tmp_path):
    return ProductService(tmp_path / "product.jsonl")


# =============================================================================
# Research debt
# =============================================================================

def test_all_six_named_research_debt_kinds_map(svc):
    candidates = intake_candidates_from_research_debt(
        _package(SIX_NAMED_KINDS), request_id="REQ1", as_of=AS_OF)
    assert len(candidates) == 6
    titles = {c["opportunity"]["title"] for c in candidates}
    assert any(t.startswith("Interview affected users about") for t in titles)
    assert any(t.startswith("Design an experiment to settle") for t in titles)
    assert any(t.startswith("Acquire a primary source for") for t in titles)
    assert any(t.startswith("Replicate the finding for") for t in titles)
    assert any(t.startswith("Seek independent corroboration for")
               for t in titles)
    assert any(t.startswith("Refresh the evidence for") for t in titles)


def test_every_debt_kind_t019_can_emit_is_mapped():
    """A kind T019 emits that product cannot map would silently drop a
    recorded gap, so the mapping covers the whole vocabulary."""
    assert DEBT_KINDS <= set(RESEARCH_DEBT_TEMPLATES)


def test_an_unmapped_debt_kind_is_refused_rather_than_dropped():
    with pytest.raises(ProductError, match="unmapped research-debt kind"):
        intake_candidates_from_research_debt(
            _package(["need_something_new"]), request_id="R", as_of=AS_OF)


def test_a_research_debt_candidate_cites_its_origin(svc):
    candidate = intake_candidates_from_research_debt(
        _package(["need_experiment"]), request_id="REQ1", as_of=AS_OF)[0]
    origin = candidate["opportunity"]["origin"]
    assert origin["kind"] == "research_package"
    assert origin["request_id"] == "REQ1"
    assert origin["debt_kind"] == "need_experiment"
    refs = candidate["opportunity"]["evidence_references"]
    assert refs[0]["kind"] == "research_debt"
    assert refs[0]["request_id"] == "REQ1"


# =============================================================================
# Growth results
# =============================================================================

@pytest.mark.parametrize("label", ["INCONCLUSIVE", "TOO FEW OBSERVATIONS",
                                   "GUARDRAIL BREACHED"])
def test_unsettled_growth_labels_become_candidates(label):
    candidates = intake_candidates_from_growth(
        {"experiment_id": "EXP1", "label": label,
         "label_rule_version": "result_label.v1", "reasons": ["because"]},
        as_of=AS_OF)
    assert len(candidates) == 1
    origin = candidates[0]["opportunity"]["origin"]
    assert origin["experiment_id"] == "EXP1"
    assert origin["label"] == label
    assert candidates[0]["opportunity"]["evidence_references"][0]["label"] \
        == label


def test_a_settled_growth_label_creates_nothing():
    assert intake_candidates_from_growth(
        {"experiment_id": "EXP1", "label": "DIFFERENCE OBSERVED"},
        as_of=AS_OF) == []


# =============================================================================
# CRM pain
# =============================================================================

def test_crm_churn_and_at_risk_facts_become_candidates():
    facts = [{"event_type": "crm.churned", "crm_entity_id": "E1"},
             {"event_type": "crm.churned", "crm_entity_id": "E2"},
             {"event_type": "crm.customer_at_risk", "crm_entity_id": "E3"},
             {"event_type": "crm.contacted", "crm_entity_id": "E4"}]
    candidates = intake_candidates_from_crm(facts, as_of=AS_OF)
    kinds = {c["opportunity"]["origin"]["event_type"] for c in candidates}
    assert kinds == {"crm.churned", "crm.customer_at_risk"}
    churn = next(c for c in candidates
                 if c["opportunity"]["origin"]["event_type"] == "crm.churned")
    assert churn["problem"]["affected_customers"] == ["E1", "E2"]
    assert {r["crm_entity_id"]
            for r in churn["opportunity"]["evidence_references"]} == {"E1", "E2"}


def test_crm_intake_respects_a_minimum_entity_count():
    facts = [{"event_type": "crm.churned", "crm_entity_id": "E1"}]
    assert intake_candidates_from_crm(facts, as_of=AS_OF,
                                      minimum_entities=3) == []
    assert len(intake_candidates_from_crm(facts, as_of=AS_OF,
                                          minimum_entities=1)) == 1


def test_crm_intake_references_entities_and_copies_nothing():
    facts = [{"event_type": "crm.churned", "crm_entity_id": "E1",
              "name": "Acme Ltd", "email": "ops@acme.example"}]
    candidate = intake_candidates_from_crm(facts, as_of=AS_OF)[0]
    serialized = repr(candidate)
    assert "Acme" not in serialized
    assert "acme.example" not in serialized
    assert "E1" in serialized


# =============================================================================
# Determinism, idempotency, and the candidate disposition
# =============================================================================

def test_intake_is_deterministic(tmp_path):
    package = _package(["need_experiment", "need_primary_source"])
    first = intake_candidates_from_research_debt(package, request_id="R",
                                                 as_of=AS_OF)
    second = intake_candidates_from_research_debt(package, request_id="R",
                                                  as_of=AS_OF)
    assert first == second


def test_absorbing_the_same_candidates_twice_creates_no_duplicates(svc):
    candidates = intake_candidates_from_research_debt(
        _package(["need_experiment"]), request_id="REQ1", as_of=AS_OF)
    first = svc._absorb_candidates(candidates, actor_id="product_intake")
    second = svc._absorb_candidates(candidates, actor_id="product_intake")
    assert first[0]["opportunity_id"] == second[0]["opportunity_id"]
    assert first[0]["problem_id"] == second[0]["problem_id"]
    assert second[0]["problem_reused"] is True
    index = svc.get_index()
    assert len(index.opportunities) == 1
    assert len(index.problem_index.problems) == 1


def test_an_intake_candidate_enters_the_index_and_the_review_queue_only(svc):
    candidates = intake_candidates_from_growth(
        {"experiment_id": "EXP1", "label": "INCONCLUSIVE", "reasons": []},
        as_of=AS_OF)
    svc._absorb_candidates(candidates, actor_id="product_intake")
    state = svc.get_state()
    assert state.opportunities                      # it is in the index
    assert state.proposals == {}                    # no proposal
    assert state.specs == {}                        # no spec
    assert state.roadmap_candidates == {}           # and no roadmap entry
    scanned = [r for r in svc.store.read_all()
               if r.event_type == "product.intake_scanned"]
    assert scanned[0].payload["candidate"] is True


def test_every_intake_created_opportunity_records_its_origin(svc):
    svc._absorb_candidates(
        intake_candidates_from_growth(
            {"experiment_id": "EXP1", "label": "INCONCLUSIVE", "reasons": []},
            as_of=AS_OF), actor_id="product_intake")
    opportunity = list(svc.get_index().opportunities.values())[0]
    assert opportunity["origin"]["kind"] == "growth_result"
    assert opportunity["origin"]["experiment_id"] == "EXP1"
    assert opportunity["origin"]["label"] == "INCONCLUSIVE"


def test_origin_uncertainty_travels_into_the_score(svc):
    """An INCONCLUSIVE origin cannot yield a confidently-scored
    opportunity: the cap is applied and the reason names the origin."""
    created = svc._absorb_candidates(
        intake_candidates_from_growth(
            {"experiment_id": "EXP1", "label": "INCONCLUSIVE", "reasons": []},
            as_of=AS_OF), actor_id="product_intake")
    proposal = svc.draft_proposal(
        created[0]["opportunity_id"],
        candidate_solution="Re-register the experiment with a larger sample",
        tradeoffs=["costs another cycle"], risks=["the result repeats"],
        known=["the prior run stopped without settling the question"],
        unknown=["whether a larger sample settles it"],
        assumptions=["the metric is the one that matters"])
    block = svc.score_proposal(proposal, as_of=AS_OF, record=False)
    confidence = block["confidence"]
    assert confidence["opportunity_confidence"]["value"] <= 0.4
    assert confidence["proposal_confidence"]["value"] <= 0.4
    reasons = " ".join(confidence["opportunity_confidence"]["reasons"])
    assert "INCONCLUSIVE" in reasons


def test_a_settled_origin_is_not_capped(svc):
    """The cap is a consequence of the origin, not a blanket ceiling."""
    problem = svc.record_problem(
        statement="Setup takes longer than the documented path suggests",
        evidence_references=[{"kind": "crm_fact", "ref_id": "crm.churned:E1",
                              "crm_entity_id": "E1"}],
        why_now="the fact is current", what_changes_if_ignored="cost repeats",
        first_observed_at=AS_OF, affected_customers=["E1", "E2", "E3"])
    opportunity = svc.register_opportunity(
        problem["problem_id"], title="A shorter documented path",
        evidence_references=[{"kind": "crm_fact", "ref_id": "crm.churned:E1",
                              "crm_entity_id": "E1"}])
    proposal = svc.draft_proposal(
        opportunity, candidate_solution="Shorten the documented setup path",
        tradeoffs=["less detail"], risks=["some users need the detail"],
        known=["three entities churned"], unknown=["which step dominates"],
        assumptions=["setup length matters"])
    block = svc.score_proposal(proposal, as_of=AS_OF, record=False)
    assert block["confidence"]["problem_confidence"]["value"] > 0.4
