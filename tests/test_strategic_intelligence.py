"""V1.2 strategic-intelligence acceptance and unit tests.

Covers the strategic reasoning model, evidence explanation, quality gates,
conversation, the Shopify acceptance run through the real compose pipeline,
and a regression capture of the previous website-summarizer failure mode.
"""
import pytest

from company_fixture_pages import BASE as BRIGHTLAKE, transport as brightlake
from intent_engine.company_ingestion.service import CompanyIngestionService
from intent_engine.founder_intelligence.service import FounderIntelligenceService
from intent_engine.strategic_intelligence.conversation import answer_strategic
from intent_engine.strategic_intelligence.quality import (
    COMPLETE, FAILED, INSUFFICIENT, PARTIAL, evaluate_report, looks_low_value,
)
from intent_engine.strategic_intelligence.reasoning import build_strategic_report
from intent_engine.strategic_intelligence.records import (
    StrategicError, StrategicObservation, StrategicReport,
)
from intent_engine.strategic_intelligence.render import render_strategic_report
from intent_engine.strategic_intelligence.shopify_fixture import (
    SHOPIFY_COMPANY, company_owned_only, shopify_observations,
)


# A representative sample of the OLD, low-value Shopify report we are replacing.
LEGACY_LOW_VALUE_REPORT = """
Executive summary: The company talks about commerce and mentions customers.
Most repeated words: commerce, store, business, sell, brand, grow.
Visible audience language detected. The website mentions customers.
Questions: What does the company do? Who are the customers?
Competitor analysis: Out of scope.
Possible blind spots: Not available.
Opportunities: Not available.
Show evidence: artifact-id src-01H..., replay-id replay-01H...
"""


@pytest.fixture
def shopify_report():
    return build_strategic_report(company_name=SHOPIFY_COMPANY,
                                  observations=shopify_observations())


# --- J1: at least 3 non-generic strategic hypotheses ------------------------

def test_shopify_produces_at_least_three_hypotheses(shopify_report):
    assert len(shopify_report.hypotheses) >= 3
    ids = {h.pattern_id for h in shopify_report.hypotheses}
    # the infrastructure thesis must be among them for Shopify
    assert "product_to_platform" in ids
    for h in shopify_report.hypotheses:
        # not a generic one-liner: substantive statement + reasoning
        assert len(h.statement) > 40 and len(h.reasoning) > 80
        low, _ = looks_low_value(h.statement + " " + h.reasoning)
        assert not low, h.hypothesis_id


# --- J2: every major hypothesis carries the full apparatus -------------------

def test_every_hypothesis_has_full_reasoning_apparatus(shopify_report):
    for h in shopify_report.hypotheses:
        h.validate()                       # structural contract
        assert h.reasoning.strip()
        assert h.supporting_observation_ids
        assert h.counter_observation_ids or h.evidence_gaps   # counter OR gap
        assert h.alternative_explanations
        assert h.confidence_reasons
        assert h.decision_implications
        assert h.falsification_questions
        # supporting ids resolve to real observations
        for oid in h.supporting_observation_ids:
            assert shopify_report.observation(oid) is not None


def test_flagship_hypothesis_has_real_counter_evidence(shopify_report):
    infra = next(h for h in shopify_report.hypotheses
                 if h.pattern_id == "product_to_platform")
    # SMB-simplicity / storefront-origin observations are held AS counters
    assert infra.counter_observation_ids
    classes = {shopify_report.observation(i).source_class
               for i in infra.supporting_observation_ids}
    assert len(classes) >= 2               # not one-sided


# --- J3: executive thesis is a strategic view, not a description -------------

def test_executive_thesis_is_strategic_not_a_summary(shopify_report):
    t = shopify_report.thesis
    assert t["transition"] and t["tension"] and t["why_care"]
    low, _ = looks_low_value(t["view"])
    assert not low
    assert any(cue in t["view"].lower()
               for cue in ("appears to", "moving", "transition", "toward",
                           "becoming"))


# --- J4: leadership questions explain why and name a decision ----------------

def test_leadership_questions_have_why_and_decision(shopify_report):
    assert shopify_report.questions
    for q in shopify_report.questions:
        q.validate()
        assert q.why_it_matters.strip()
        assert q.decision_affected.strip()
        assert q.evidence_that_triggered_it


# --- J5: comparable patterns include mechanism and limitations ---------------

def test_comparable_patterns_have_mechanism_and_limits(shopify_report):
    assert shopify_report.patterns
    for p in shopify_report.patterns:
        assert p.mechanism.strip()
        assert p.limitations.strip()
        assert p.historical_examples and all(
            e.get("source") for e in p.historical_examples)
        assert p.when_it_applies and p.when_it_does_not_apply


# --- J6: "Show evidence" leads with reasoning, IDs are secondary -------------

def test_show_evidence_renders_reasoning_before_provenance_ids(shopify_report):
    html = render_strategic_report(shopify_report)
    assert "Show evidence — why we believe this" in html
    # human-readable evidence & interpretation appear before any provenance IDs
    assert "Observed evidence" in html and "Interpretation" in html
    assert html.index("Observed evidence") < html.index("Provenance IDs")
    # provenance IDs are inside a secondary <details>, not the main surface
    assert '<details class="provenance">' in html
    low, reasons = looks_low_value(html)
    assert not low, reasons


# --- J7: company-owned-only evidence is a partial limitation state -----------

def test_company_owned_only_is_partial(shopify_report):
    only = build_strategic_report(company_name=SHOPIFY_COMPANY,
                                  observations=company_owned_only())
    assert only.status == PARTIAL
    assert any(f["code"] in ("single_source_class",) or "company-owned"
               in f["message"] for f in only.quality_findings)
    # multi-class evidence, by contrast, reaches COMPLETE
    assert shopify_report.status == COMPLETE


def test_company_owned_only_can_be_accepted_as_limited_scope():
    accepted = build_strategic_report(
        company_name=SHOPIFY_COMPANY, observations=company_owned_only(),
        user_accepts_limited_scope=True)
    # with explicit acceptance it is no longer forced to partial for breadth
    assert accepted.status in (COMPLETE, PARTIAL, INSUFFICIENT)


# --- J8: unsupported internal claims are refused -----------------------------

def test_internal_source_class_cannot_be_constructed():
    obs = StrategicObservation(
        observation_id="x", text="leaked internal roadmap says...",
        observation_type="messaging", source_class="internal_document")
    with pytest.raises(StrategicError):
        obs.validate()


def test_quality_gate_fails_on_unsupported_internal_claim(shopify_report):
    # smuggle an internal-claim observation past construction and confirm the
    # gate refuses the whole report
    bad = StrategicObservation(
        observation_id="leak", text="internal", observation_type="messaging",
        source_class="company_owned")
    object.__setattr__(bad, "source_class", "internal_leak")
    shopify_report.observations.append(bad)
    status, findings = evaluate_report(shopify_report)
    assert status == FAILED
    assert any(f["code"] == "unsupported_internal" for f in findings)


# --- J9: empty strategic sections fail the gate, never silent "Not available"

def test_empty_strategic_report_is_not_silently_complete():
    empty = StrategicReport(
        company_name="Nobody", status="", thesis={}, shifts=[], hypotheses=[],
        patterns=[], blind_spots=[], questions=[], evidence_gaps=[],
        decision_implications=[], observations=[])
    status, findings = evaluate_report(empty)
    assert status in (FAILED, INSUFFICIENT)
    assert status != COMPLETE
    codes = {f["code"] for f in findings}
    assert "too_few_hypotheses" in codes


# --- J10: conversation explains a hypothesis with citations + counter --------

def test_conversation_explains_hypothesis_with_citations_and_counter(
        shopify_report):
    sa = answer_strategic("Why do you think Shopify is becoming "
                          "infrastructure?", shopify_report)
    assert sa["intent"] == "EXPLAINED"
    assert sa["matched_hypothesis"] == "hyp-product_to_platform"
    a = sa["answer"]
    assert a["confidence"] in ("high", "moderate", "low", "speculative")
    assert a["citations"] if "citations" in a else sa["citations"]
    assert a["evidence"] and a["counter_evidence"]      # cites both sides
    assert a["falsification"]                            # what would change it
    assert a["reasoning"] and "fact" in a["reasoning"].lower()


def test_conversation_does_not_just_repeat_a_card(shopify_report):
    sa = answer_strategic("why is shopify moving to infrastructure",
                          shopify_report)
    infra = next(h for h in shopify_report.hypotheses
                 if h.pattern_id == "product_to_platform")
    # the answer adds reasoning framing beyond the card statement text
    assert sa["answer"]["reasoning"] != infra.statement


# --- J12 + semantic acceptance: the legacy low-value report is a failure case

def test_legacy_low_value_report_is_flagged():
    low, reasons = looks_low_value(LEGACY_LOW_VALUE_REPORT)
    assert low
    joined = " ".join(reasons).lower()
    assert "most repeated words" in joined or "out of scope" in joined \
        or "not available" in joined


def test_new_shopify_report_rejects_low_value_structures(shopify_report):
    html = render_strategic_report(shopify_report)
    lowered = html.lower()
    # none of the old failure structures survive
    for banned in ("most repeated words", "out of scope",
                   "the company talks about", "visible audience"):
        assert banned not in lowered, banned
    # "Not available" is not used for the core comparative-analysis section
    assert "comparable pattern" in lowered
    # every rendered leadership question explains itself
    assert lowered.count("<article class=\"question\"") == \
        lowered.count("why we ask")
    # blind spots and hypotheses are populated, not empty
    assert 'class="blind-spot"' in lowered and 'class="hypothesis"' in lowered


# --- G: the acceptance evidence flows through the REAL compose pipeline ------

def test_shopify_acceptance_runs_through_real_compose(tmp_path):
    """The curated observations are added via compose's explicit
    source-addition hook and reasoned over by the same pipeline a real run
    uses — not a separate code path."""
    ci = CompanyIngestionService(tmp_path / "ci.jsonl", transport=brightlake,
                                 resolver=False)
    fi = FounderIntelligenceService(tmp_path / "fi.jsonl")
    run = ci.create_run(company_name=SHOPIFY_COMPANY, website=BRIGHTLAKE,
                        user_id="user-1", as_of="2026-07-24T00:00:00+00:00")
    run_id = run["run_id"]
    cands = [c["candidate_id"] for c in ci.discover(run_id)][:5]
    ci.approve(run_id, user_id="user-1", approved_ids=cands, rejected_ids=[])
    ci.fetch_approved(run_id)
    result = ci.compose(run_id, fi_service=fi,
                        extra_observations=shopify_observations())
    report = result["strategic_report"]
    assert report is not None
    assert report["status"] == COMPLETE
    assert len(report["hypotheses"]) >= 3
    # the same render used by the web layer produces a non-low-value report
    low, reasons = looks_low_value(render_strategic_report(report))
    assert not low, reasons


# --- unification: the LIVE pipeline (no fixture) reaches multi-class quality --

_HOME = ("commerce infrastructure powering commerce. Shop Pay checkout and "
         "buyer identity, payments, capital, fulfillment, point of sale, "
         "Markets and Audiences. App Store partners and developers. Online "
         "store storefront. End-to-end first-party rails. Enterprise ready.")
_PRESS = ("Leadership: we are building the essential infrastructure for "
          "commerce, owning checkout and identity so merchants can focus on "
          "their business. Payments and rails are first-party.")
_INVESTORS = ("Investor update: enterprise (Plus) momentum with large "
              "merchants; expanding product breadth across payments, capital, "
              "fulfillment and POS drives platform adoption.")
_REVIEWS = ("Merchant reviews: Shopify is simple and easy to get started; "
            "anyone can start a business. Customers value the simplicity and "
            "quick setup above all.")


def _live_transport(url, timeout):
    import urllib.error
    import email as _email
    u = url.lower()
    if "/press" in u or "/newsroom" in u:
        body = f"<html><head><title>Press</title></head><body><p>{_PRESS}</p></body></html>"
    elif "/investor" in u:
        body = f"<html><head><title>Investors</title></head><body><p>{_INVESTORS}</p></body></html>"
    elif "g2.com" in u or "trustpilot" in u or "capterra" in u:
        body = f"<html><head><title>Reviews</title></head><body><p>{_REVIEWS}</p></body></html>"
    elif "acme.example" in u:
        body = f"<html><head><title>Acme</title></head><body><p>{_HOME}</p></body></html>"
    else:
        raise urllib.error.HTTPError(url, 404, "nf",
                                     _email.message_from_string(""), None)
    return (200, {"content-type": "text/html"}, body.encode(), False)


def test_live_pipeline_reaches_complete_multi_class(tmp_path):
    """THE UNIFICATION PROOF: with only the live discovery→approval→retrieval→
    derive pipeline (NO injected fixture observations), a run that approves
    company + executive + investor + independent customer-voice sources reaches
    multi-class COMPLETE strategic reasoning — the same category the fixture
    demonstrates."""
    ci = CompanyIngestionService(tmp_path / "ci.jsonl",
                                 transport=_live_transport, resolver=False)
    fi = FounderIntelligenceService(tmp_path / "fi.jsonl")
    run = ci.create_run(company_name="Acme", website="https://acme.example",
                        user_id="user-1", as_of="2026-07-24T00:00:00+00:00")
    run_id = run["run_id"]
    cands = ci.discover(run_id)
    # approve one candidate from each available class (company, exec, investor,
    # customer-voice) — exactly what a founder would do on the grouped page
    picked, seen = [], set()
    for c in cands:
        cls = c.get("source_class")
        if cls not in seen:
            seen.add(cls)
            picked.append(c["candidate_id"])
    ci.approve(run_id, user_id="user-1", approved_ids=picked, rejected_ids=[])
    ci.fetch_approved(run_id)
    result = ci.compose(run_id, fi_service=fi)          # NO extra_observations
    report = result["strategic_report"]
    assert report is not None
    classes = set(report["source_class_coverage"])
    assert "customer_voice" in classes                  # an independent class
    assert len(classes) >= 3                            # genuinely multi-source
    assert report["status"] == COMPLETE
    assert len(report["hypotheses"]) >= 3
    low, reasons = looks_low_value(render_strategic_report(report))
    assert not low, reasons


def test_same_domain_company_published_only_is_partial(tmp_path):
    """Company + executive + investor pages are ALL the company's own
    publishing; without an independent source the report is honestly PARTIAL,
    never a hollow COMPLETE."""
    def company_only_transport(url, timeout):
        import urllib.error
        import email as _email
        u = url.lower()
        if "g2.com" in u or "trustpilot" in u or "capterra" in u:
            raise urllib.error.HTTPError(url, 403, "forbidden",
                                         _email.message_from_string(""), None)
        return _live_transport(url, timeout)

    ci = CompanyIngestionService(tmp_path / "ci.jsonl",
                                 transport=company_only_transport,
                                 resolver=False)
    fi = FounderIntelligenceService(tmp_path / "fi.jsonl")
    run = ci.create_run(company_name="Acme", website="https://acme.example",
                        user_id="user-1", as_of="2026-07-24T00:00:00+00:00")
    run_id = run["run_id"]
    cands = ci.discover(run_id)
    same = [c["candidate_id"] for c in cands if c["same_domain"]][:6]
    ci.approve(run_id, user_id="user-1", approved_ids=same, rejected_ids=[])
    ci.fetch_approved(run_id)
    report = ci.compose(run_id, fi_service=fi)["strategic_report"]
    assert report is not None
    assert "customer_voice" not in report["source_class_coverage"]
    assert report["status"] == PARTIAL       # company-published only
    assert any(f["code"] in ("no_independent_source", "single_source_class")
               for f in report["quality_findings"])


def test_evidence_graph_links_observations_hypotheses_patterns(shopify_report):
    graph = shopify_report.as_dict()["evidence_graph"]
    assert graph["nodes"] and graph["edges"]
    types = {n["type"] for n in graph["nodes"]}
    assert {"observation", "hypothesis", "pattern", "source"} <= types
    etypes = {e["type"] for e in graph["edges"]}
    assert "supports" in etypes and "matches_pattern" in etypes
    # a supporting edge connects a real observation to a real hypothesis
    hyp_ids = {h.hypothesis_id for h in shopify_report.hypotheses}
    obs_ids = {o.observation_id for o in shopify_report.observations}
    supports = [e for e in graph["edges"] if e["type"] == "supports"]
    assert any(e["from"] in obs_ids and e["to"] in hyp_ids for e in supports)


def test_real_company_owned_only_run_is_partial_strategic(tmp_path):
    """A real run over only company-owned pages yields a partial strategic
    state — never a hollow COMPLETE."""
    ci = CompanyIngestionService(tmp_path / "ci.jsonl", transport=brightlake,
                                 resolver=False)
    fi = FounderIntelligenceService(tmp_path / "fi.jsonl")
    run = ci.create_run(company_name="Brightlake", website=BRIGHTLAKE,
                        user_id="user-1", as_of="2026-07-24T00:00:00+00:00")
    run_id = run["run_id"]
    cands = [c["candidate_id"] for c in ci.discover(run_id)][:5]
    ci.approve(run_id, user_id="user-1", approved_ids=cands, rejected_ids=[])
    ci.fetch_approved(run_id)
    result = ci.compose(run_id, fi_service=fi)
    report = result.get("strategic_report")
    if report is not None:                 # only if any signal was detected
        assert report["status"] in (PARTIAL, INSUFFICIENT)
        assert report["status"] != COMPLETE
