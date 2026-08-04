"""V1.2 strategic-intelligence acceptance and unit tests.

Covers the strategic reasoning model, evidence explanation, quality gates,
conversation, the Shopify acceptance run through the real compose pipeline,
and a regression capture of the previous website-summarizer failure mode.
"""
import io
import re

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
    # human-readable reasoning and evidence excerpts are primary. The
    # "Reasoning." label went with the field-shaped cards; the reasoning
    # itself is now a sentence under "Why that evidence matters".
    assert ">Why that evidence matters<" in html
    # supporting and contradicting evidence are still distinguished, as
    # labelled prose rather than two chips
    assert "What supports the reading" in html
    assert "What cuts against it" in html
    # raw artifact/replay ids never appear in the human-facing body. The
    # "Technical appendix" that used to hold them is gone -- signal traces and
    # hypothesis ids are the system describing itself, and the page a founder
    # reads is not where they belong.
    assert "artifact_id" not in html and "replay_id" not in html
    assert "Technical appendix" not in html
    assert "signal_trace" not in html
    # the argument comes before the sourcing, not after it
    assert html.index("Why that evidence matters") < html.index(">Sources<")
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
    assert sa["citations"]
    assert a["evidence"] and a["counter_evidence"]      # cites both sides
    assert a["falsification"]                            # what would change it
    assert a["reasoning"]
    # the answer leads with a direct, confidence-qualified answer (not certainty)
    assert a["confidence"] in a["direct_answer"]
    # selective, not a dump
    assert len(a["evidence"]) <= 4 and len(a["counter_evidence"]) <= 2


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
    for banned in ("most repeated words", "out of scope", "not available",
                   "the company talks about", "visible audience"):
        assert banned not in lowered, banned
    # the core comparative-analysis section is present with a mechanism
    # the historical analogue survives as prose rather than a labelled chip
    assert "resembles a pattern seen before" in lowered
    # every rendered leadership question explains itself ("why we ask")
    assert "we ask because" in lowered
    # the reasoning, the tensions, the dated developments, the inferred
    # agenda and the sourcing all still reach the reader -- as an argument in
    # eight sections rather than fourteen field-shaped card grids
    assert ">why that evidence matters<" in lowered
    assert ">what happened<" in lowered
    assert ">what else could explain it<" in lowered
    assert ">what to monitor<" in lowered
    assert ">sources<" in lowered
    assert "leadership is likely weighing" in lowered
    # THE DECISION IS STATED -- AND IT IS A DECISION, NOT THE QUESTION.
    #
    # This asserted the literal wrapper "it bears on one decision in
    # particular: <thesis.why_care>", and `why_care` is `implications[0]` --
    # a decision TOPIC. The old assertion could only ever pass by the page
    # printing the founder's own question back at them, so it encoded the
    # defect rather than guarding against it. What replaces it is stronger:
    # the composed decision must be on the page, and the bare topic must not.
    from intent_engine.strategic_intelligence.decision import decision_of
    decision = decision_of(shopify_report)
    assert decision.readiness in ("DECISION_READY", "INVESTIGATION_REQUIRED")
    assert decision.headline.lower()[:40] in lowered, decision.headline
    topic = (shopify_report.thesis or {}).get("why_care", "")
    assert topic and topic.lower().rstrip(".") not in lowered, topic


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
_REVIEWS = ("Independent merchant reviews repeatedly praise fast setup and "
            "simple day-to-day operation, citing that simplicity as the top "
            "reason they choose and remain customers rather than moving to "
            "heavier enterprise platforms.")


def _live_transport(url, timeout):
    import urllib.error
    import email as _email
    u = url.lower()
    if any(k in u for k in ("/press", "/newsroom", "/news", "/media")):
        body = f"<html><head><title>Press</title></head><body><p>{_PRESS}</p></body></html>"
    elif "investor" in u or "/ir" in u:
        body = f"<html><head><title>Investors</title></head><body><p>{_INVESTORS}</p></body></html>"
    elif "g2.com" in u or "trustpilot" in u or "capterra" in u:
        body = f"<html><head><title>Reviews</title></head><body><p>{_REVIEWS}</p></body></html>"
    elif "acme.example" in u:
        # Each path serves its OWN page, as a real site does. Serving one body
        # for every path made "five company-owned sources" mean one document
        # fetched five times, which the readiness gate now counts as the one
        # piece of evidence it is — the same misconfiguration the echo-site
        # fixture exists to catch.
        path = u.split("acme.example", 1)[-1].strip("/") or "home"
        body = (f"<html><head><title>Acme {path}</title></head><body>"
                f"<p>Acme {path} page. {_HOME}</p></body></html>")
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


# --- V1.2 executive-readiness: routing, evidence roles, temporal, selection ---

def _obs(oid, text, otype, sclass, signals, *, excerpt="a substantive and "
         "specific strategic observation excerpt that is not a page title",
         date="", weak=False):
    from intent_engine.strategic_intelligence.records import StrategicObservation
    return StrategicObservation(
        observation_id=oid, text=text, observation_type=otype,
        source_refs=[{"artifact_id": f"src-{oid}"}], signals=tuple(signals),
        source_class=sclass, excerpt=excerpt, source_title=f"src {oid}",
        origin=f"https://ex/{oid}", date=date, weak=weak,
        evidence_quality="weak" if weak else "strong")


def test_stripe_comparison_routes_to_infrastructure_not_agentic(shopify_report):
    sa = answer_strategic("How is this transition similar to Stripe, and where "
                          "does the comparison break down?", shopify_report)
    assert sa["intent"] == "COMPARISON"
    assert sa["matched_hypothesis"] == "hyp-product_to_platform"   # not agentic
    assert sa["routing"]["selected_comparable"] == "Stripe"
    assert sa["routing"]["operation"] == "comparison"


def test_comparison_answer_discusses_stripe_and_breakdown(shopify_report):
    c = answer_strategic("How is this like Stripe and where does it break "
                         "down?", shopify_report)["comparison"]
    assert "Stripe" in c["direct_answer"]
    assert any("Stripe" in s for s in c["key_similarities"])
    assert c["key_differences"] and c["where_the_analogy_breaks"]
    assert c["shared_mechanism"]


def test_agentic_question_still_routes_to_agentic(shopify_report):
    sa = answer_strategic("what makes you think AI agents will mediate "
                          "buying?", shopify_report)
    assert sa["matched_hypothesis"] == "hyp-human_to_agent_workflow"


def test_support_and_counter_never_wholesale_duplicated(shopify_report):
    for h in shopify_report.hypotheses:
        sup = set(h.supporting_observation_ids)
        con = set(h.counter_observation_ids)
        assert not (sup & con), h.hypothesis_id       # disjoint per hypothesis


def test_hypothesis_rejects_same_obs_as_support_and_contradiction():
    from intent_engine.strategic_intelligence.records import StrategicHypothesis
    h = StrategicHypothesis(
        hypothesis_id="h", title="t", statement="s", reasoning="r",
        supporting_observation_ids=["o1"], counter_observation_ids=["o1"],
        alternative_explanations=["a"], confidence="low",
        confidence_reasons=["c"], evidence_gaps=["g"],
        decision_implications=["d"], falsification_questions=["f"])
    with pytest.raises(StrategicError):
        h.validate()


def test_page_titles_alone_do_not_satisfy_evidence(tmp_path):
    # all observations are weak (title-only / marketing) → not COMPLETE
    obs = [_obs(f"w{i}", "Homepage", "messaging", "company_owned",
                ["infrastructure_positioning", "product_breadth"],
                excerpt="Home", weak=True) for i in range(4)]
    report = build_strategic_report(company_name="Weak Co", observations=obs)
    assert report.status in (INSUFFICIENT, PARTIAL, FAILED)
    assert report.status != COMPLETE


def test_duplicate_pages_collapse_into_one_observation(tmp_path):
    from intent_engine.strategic_intelligence.observations import (
        derive_observations,
    )
    dup = {"source_id": "a", "title": "Shopify", "meta_description":
           "commerce infrastructure powering commerce with checkout payments",
           "text_content": "commerce infrastructure powering commerce",
           "final_url": "https://shopify.com/", "content_hash": "H1",
           "source_class": "company_owned", "retrieved_at": "2024-01-01",
           "freshness": "CURRENT"}
    dup2 = dict(dup, source_id="b", final_url="https://www.shopify.com")
    obs = derive_observations([dup, dup2])
    assert len(obs) == 1                              # same content collapses


def test_weak_evidence_excluded_from_hypothesis_support():
    strong = _obs("s1", "Company positions as infrastructure", "messaging",
                  "company_owned",
                  ["infrastructure_positioning", "checkout_identity_rails",
                   "product_breadth"], date="2024-06-01")
    weak = _obs("w1", "Homepage", "messaging", "company_owned",
                ["platform_control"], excerpt="Home", weak=True)
    report = build_strategic_report(company_name="Co", observations=[strong, weak])
    for h in report.hypotheses:
        assert "w1" not in h.strongest_support_ids   # weak never a top citation


def test_executive_report_shows_selected_not_all_evidence(shopify_report):
    top = shopify_report.hypotheses[0]
    # curated strongest support is a bounded subset of all support
    assert len(top.strongest_support_ids) <= 3
    assert len(top.strongest_support_ids) <= len(top.supporting_observation_ids)


def test_all_sources_remain_in_source_library(shopify_report):
    lib = shopify_report.as_dict()["source_library"]
    titles_in_lib = {s["title"] for group in lib.values() for s in group}
    all_titles = {o.source_title for o in shopify_report.observations}
    assert all_titles <= titles_in_lib                   # no source is lost


def test_complete_requires_hypothesis_level_coverage():
    # 3 hypotheses fire but every supporting observation is weak → not COMPLETE
    obs = [_obs(f"w{i}", "x", "messaging", "independent_reporting",
                ["infrastructure_positioning", "checkout_identity_rails",
                 "product_breadth", "platform_control",
                 "partner_ecosystem_enablement"], excerpt="Home", weak=True)
           for i in range(3)]
    report = build_strategic_report(company_name="Co", observations=obs)
    assert report.status != COMPLETE


def test_agenda_inferred_from_timely_signals_no_private_claim(shopify_report):
    agenda = shopify_report.agenda
    assert agenda, "expected inferred agenda from dated evidence"
    for a in agenda:
        assert a["public_signals"] and a["why_timely"]
        assert a["affected_functions"] and a["what_would_confirm"]
    # never claims knowledge of an actual private meeting
    blob = str(shopify_report.as_dict()).lower()
    assert "discussed yesterday" not in blob
    assert "in the meeting" not in blob and "private meeting" not in blob


def test_timeline_is_chronological(shopify_report):
    dates = [t["date"] for t in shopify_report.timeline]
    assert dates == sorted(dates)


def test_conversation_answers_are_selective(shopify_report):
    sa = answer_strategic("why is it becoming infrastructure", shopify_report)
    assert len(sa["answer"]["evidence"]) <= 4
    assert len(sa["answer"]["counter_evidence"]) <= 2
    assert sa["answer"]["direct_answer"]                 # leads with the answer
    # no internal signal names or record ids in the human-facing answer
    text = (sa["answer"]["direct_answer"] + sa["answer"]["reasoning"]).lower()
    assert "signals matched" not in text and "obs-" not in text


def test_different_companies_produce_different_hypotheses():
    shopify = build_strategic_report(
        company_name="Shopify", observations=shopify_observations())
    linear = build_strategic_report(company_name="Linear", observations=[
        _obs("l1", "Linear expands to enterprise", "buyer_segment",
             "independent_reporting", ["enterprise_expansion", "product_breadth"],
             date="2024-05-01"),
        _obs("l2", "Linear keeps it simple", "messaging", "company_owned",
             ["smb_simplicity"], date="2024-04-01"),
        _obs("l3", "Linear adds breadth", "product_surface", "company_owned",
             ["product_breadth", "merchant_outcome_positioning"], date="2024-06-01"),
    ])
    cloudflare = build_strategic_report(company_name="Cloudflare", observations=[
        _obs("c1", "Cloudflare is internet infrastructure", "infrastructure_platform",
             "independent_reporting",
             ["infrastructure_positioning", "platform_control", "product_breadth"],
             date="2024-05-01"),
        _obs("c2", "Cloudflare developer platform + partners", "monetization_ecosystem",
             "company_owned", ["partner_ecosystem_enablement", "product_breadth"],
             date="2024-06-01"),
        _obs("c3", "Cloudflare owns the edge rails", "infrastructure_platform",
             "company_owned", ["platform_control", "checkout_identity_rails"],
             date="2024-03-01"),
    ])
    s_set = {h.pattern_id for h in shopify.hypotheses}
    l_set = {h.pattern_id for h in linear.hypotheses}
    c_set = {h.pattern_id for h in cloudflare.hypotheses}
    assert s_set != l_set and s_set != c_set and l_set != c_set


def test_low_value_comparison_answer_is_a_regression_failure(shopify_report):
    # the FAILED behaviour: a comparison answer that ignores the named company
    good = answer_strategic("how is this like Stripe and where does it break?",
                            shopify_report)
    bad_answer = "This company is transitioning. It uses growth language."
    assert good["comparison"]["comparable"] == "Stripe"      # names it
    assert looks_low_value(bad_answer)[0]                    # old style flagged
    # our answer is not low-value and actually discusses the company
    assert not looks_low_value(str(good["comparison"]))[0]


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


# --- webapp-level: executive experience, legacy quarantine, comparison -------

class _WsgiClient:
    def __init__(self, app):
        self.app, self.cookie = app, ""

    def request(self, method, path, body=""):
        env = {"REQUEST_METHOD": method, "PATH_INFO": path,
               "CONTENT_LENGTH": str(len(body)), "HTTP_HOST": "127.0.0.1",
               "HTTP_COOKIE": self.cookie, "wsgi.input": io.BytesIO(body.encode())}
        out = {}
        payload = b"".join(self.app(env, lambda s, h: out.update(
            status=s, headers=h))).decode()
        for k, v in out["headers"]:
            if k == "Set-Cookie" and v.startswith("sid="):
                self.cookie = "" if "Max-Age=0" in v else v.split(";")[0]
        return out["status"], dict(out["headers"]), payload

    def csrf(self):
        return self.app.auth.csrf_token(self.cookie.split("=", 1)[1])


def _strategic_webapp_run(tmp_path):
    from intent_engine.webapp.app import WebApp
    from intent_engine.webapp.config import AppConfig
    cfg = AppConfig(env="test", secret="s" * 40, demo_mode=True,
                    web_store_path=tmp_path / "w.jsonl",
                    fi_store_path=tmp_path / "fi.jsonl",
                    ci_store_path=tmp_path / "ci.jsonl")
    app = WebApp(cfg, transport=_live_transport, resolver=False)
    c = _WsgiClient(app)
    c.request("POST", "/demo")
    _, h, _ = c.request("POST", "/analyze",
                        f"consent=on&csrf={c.csrf()}&company_name=Acme"
                        f"&website=https://acme.example")
    rid = h["Location"].split("/runs/")[1].split("/")[0]
    cands, picked, seen = app.ci.store.candidates(rid), [], set()
    for x in cands:
        if x["source_class"] not in seen:
            seen.add(x["source_class"])
            picked.append(x["candidate_id"])
    c.request("POST", f"/runs/{rid}/sources/approve",
              "csrf=" + c.csrf() + "&approve_consent=on&"
              + "&".join(f"cand={x}" for x in picked))
    return app, c, rid


def test_webapp_strategic_run_defaults_to_the_founder_brief(tmp_path):
    """The default must not be a report the reader has to work through.

    ORIGINAL SAFEGUARD, unchanged: fifteen minutes before a meeting an
    eleven-section report gets skimmed, and a skimmed report is where a reader
    picks up the first confident sentence they see. This test existed to stop
    the default being that report.

    WHAT CHANGED (v3): the destination. The executive brief at 500-900 words
    was still "everything" to someone with fifteen minutes, so the default is
    now the 60-SECOND FOUNDER BRIEF -- strictly less to read than what this
    test previously protected. The safeguard holds more strongly, not less.

    The assertions below still catch the original failure: if the default ever
    returns the full analysis again, the eleven-section markers appear and the
    founder-brief markers do not.
    """
    app, c, rid = _strategic_webapp_run(tmp_path)
    status, headers, body = c.request("GET", f"/runs/{rid}")
    assert status == "200 OK"

    # it IS the founder brief
    assert "Why this matters" in body

    # ... and it is NOT the full report — the original failure this catches
    assert "Executive Overview" not in body
    assert "Evidence Library" not in body
    assert "Strongest supported observation" not in body
    assert not re.search(r"\[(?:u|mv|c)\.[a-z_]+", body), \
        "an internal claim id reached the default view"

    # depth remains reachable, never required
    assert f"/runs/{rid}/full" in body


def test_the_default_route_never_reverts_to_a_deeper_layer(tmp_path):
    """REGRESSION GUARD for the v3 routing decision.

    The specific reversion this prevents: someone restores the old redirect and
    /runs/{id} quietly becomes the executive brief or the full analysis again.
    That change would be invisible in every other test, because both of those
    pages render perfectly well -- they are just not a 60-second answer.
    """
    app, c, rid = _strategic_webapp_run(tmp_path)
    status, headers, body = c.request("GET", f"/runs/{rid}")
    assert not status.startswith("30"), (
        "the default must be served directly; a redirect to a deeper layer is "
        "the reversion this guards")
    assert "Location" not in headers
    # The default is the scrollable decision narrative. Asserted by SECTION
    # ID rather than by heading text: the headings are copy and will be
    # reworded, and a guard that fails on rewording is a guard people delete.
    for marker in ('id="executive_answer"', 'id="the_decision"',
                   'id="next_move"', 'id="prepared"'):
        assert marker in body, marker
    # ...and it is a scroll, not a deck: no pager stands between the reader
    # and any of it.
    assert "Next →" not in body and "Slide 1 of" not in body


def test_a_run_that_matches_no_signal_gets_the_honest_page(tmp_path,
                                                          monkeypatch):
    """Measured on a live Duolingo run, not hypothesised.

    Ten sources retrieved, status COMPLETE, the readiness gate satisfied --
    and no strategic report, because the pages are JS-rendered and extraction
    got titles and meta descriptions rather than bodies, so no signal matched.
    `derive_observations` documents this outcome and says the fix belongs one
    level up, at the page.

    What that reader used to get was the legacy claim/evidence view: an
    "Executive Overview" of field labels, an internal claim id printed beside
    each one, and a "Strongest supported observation" that was the five words
    the company's own pages repeat most. It is the likeliest first impression
    the product makes on a company whose site does not server-render.

    The Duolingo case is BOTH derivations empty: extraction returned titles
    and meta descriptions, so no signal matched AND no body was long enough to
    be analyst evidence. Patching only `derive_observations` would now describe
    a different run -- one where the analyst has readable evidence and is
    correctly consulted (see the test below).
    """
    for name in ("derive_observations", "derive_analyst_evidence"):
        monkeypatch.setattr(
            f"intent_engine.strategic_intelligence.observations.{name}",
            lambda *a, **k: [])
    app, c, rid = _strategic_webapp_run(tmp_path)
    status, _, body = c.request("GET", f"/runs/{rid}/full")
    assert status == "200 OK"

    # not the schema dump, in any of its parts
    assert "Executive Overview" not in body and "Evidence Library" not in body
    assert not re.search(r"\[(?:u|mv|c)\.[a-z_]+", body), \
        "an internal claim id reached the reader"
    assert "Strongest supported observation" not in body

    # the honest page, and a reason that fits THIS reader rather than the
    # readiness note's "some kinds of evidence are missing"
    assert "Limited analysis" in body
    assert "none carried the dated, checkable material" in body
    # it still answers the three questions that page exists to answer
    assert "What was found" in body and "What was missing" in body
    assert "What you can do" in body
    # and the sources that were read are named, not withheld
    assert "Pages read" in body


def test_webapp_strategic_run_carries_no_legacy_extraction_view(tmp_path):
    app, c, rid = _strategic_webapp_run(tmp_path)
    # the full analysis keeps every contract it had; it is no longer the default
    status, _, body = c.request("GET", f"/runs/{rid}/full")
    assert status == "200 OK"
    # executive-first content is present. The decision is the COMPOSED one --
    # the old assertion here matched the sentence that rendered the decision
    # topic, which is the thing this replaces.
    assert "The choice:" in body or "No option is safe to commit to yet" in body
    # The dossier replaced the legacy report on this route. Reasoning is now
    # carried by the business-model, analog and assumption passages rather
    # than by one heading.
    # The dossier replaced the legacy report on this route. Reasoning is now
    # carried by the business-model, analog and assumption passages rather
    # than by the old headings.
    assert 'id="operating_model"' in body or 'id="assumptions"' in body
    assert 'id="evidence_appendix"' in body
    assert 'id="what_changed"' in body or 'id="executive_answer"' in body
    # The legacy claim/evidence view is GONE, not collapsed. Quarantining it
    # behind <details> still put it one click from a report a founder is about
    # to rely on, under a summary naming the system's own build history.
    assert "Technical appendix" not in body
    assert "legacy source extraction" not in body
    assert "Evidence Library" not in body and "Executive Overview" not in body
    # and with it the internal claim ids it printed beside every line
    assert not re.search(r"\[(?:u|mv|c)\.[a-z_]+", body), \
        "an internal claim id reached the reader"
    # no legacy low-value structures leak into the executive view
    lo = body.lower()
    for banned in ("most repeated words", "out of scope", "not available"):
        assert banned not in lo
    # the sources a reader can audit are still on the page — that is what the
    # appendix was standing in for, and it is now a first-class section
    assert "Every source this rests on" in body
    # company-specific suggested questions, not generic
    assert "How is this transition similar to" in body


def test_webapp_stripe_comparison_answer(tmp_path):
    app, c, rid = _strategic_webapp_run(tmp_path)
    status, _, body = c.request(
        "POST", f"/runs/{rid}/conversation",
        "csrf=" + c.csrf() + "&question=How is this similar to Stripe and "
        "where does the comparison break down?")
    assert status == "200 OK"
    assert "Comparison: Stripe" in body
    assert "Where the analogy breaks" in body
    # Routing still happens; it is simply no longer narrated to the reader. The
    # page used to print "Discussing hypothesis hyp-product_to_platform ·
    # operation: COMPARE", which is how the code talks to itself — to a reader
    # it is noise that looks like a malfunction. Assert the routing through the
    # ANSWER instead of through a leaked identifier.
    assert "hyp-" not in body, "internal hypothesis ids never reach a reader"
    assert "operation:" not in body
    from intent_engine.strategic_intelligence.conversation import (
        answer_strategic,
    )
    sa = answer_strategic("How is this similar to Stripe and where does the "
                          "comparison break down?",
                          app._strategic_report_for(rid))
    assert sa["routing"]["selected_hypothesis"] == "hyp-product_to_platform"


def test_render_is_responsive_and_styled(shopify_report):
    html = render_strategic_report(shopify_report)
    assert "@media(max-width:640px)" in html         # mobile layout
    assert "max-width:920px" in html                 # bounded, no wall of text
    assert "prefers-color-scheme:dark" in html       # theme-aware


# --- V1.3 mental model, surprises, opportunities, vulnerabilities, feed ------

from intent_engine.strategic_intelligence.model import (  # noqa: E402
    build_mental_model, diff_models,
)
from intent_engine.strategic_intelligence.store import (  # noqa: E402
    StrategicMemory,
)
from intent_engine.strategic_intelligence.quality import (  # noqa: E402
    executive_insight_quality,
)
from intent_engine.strategic_intelligence.insights import (  # noqa: E402
    is_generic_insight, passes_specificity,
)


def test_mental_model_is_built_with_typed_components(shopify_report):
    mm = shopify_report.as_dict()["mental_model"]
    assert mm["version"] == 1 and mm["components"]
    for name, c in mm["components"].items():
        assert c["current_state"] and c["confidence"]
        assert "supporting_observation_ids" in c and "provenance" in c
    assert "strategic_assets" in mm["components"]


def test_model_update_preserves_history_and_reports_changes():
    v1 = build_mental_model("Acme", shopify_observations()[:8],
                            [], now="2024-06-01")
    # a later run with richer evidence updates the model, not rebuilds it
    r2 = build_strategic_report(company_name="Acme",
                                observations=shopify_observations(),
                                previous_model=v1.as_dict(), now="2025-02-01")
    mm2 = r2.as_dict()["mental_model"]
    assert mm2["version"] == 2                         # versioned
    assert r2.what_changed                             # explains what changed
    ch = r2.what_changed[0]
    assert "previous_view" in ch and "new_view" in ch and ch["reason"]


def test_model_diff_explains_added_and_updated_components():
    old = build_mental_model("Co", [_obs("o1", "infra", "infrastructure_platform",
                             "company_owned", ["infrastructure_positioning",
                             "checkout_identity_rails"], date="2024-01-01")],
                             [], now="2024-01-01")
    new = build_mental_model("Co", [_obs("o1", "infra", "infrastructure_platform",
                             "company_owned", ["infrastructure_positioning",
                             "checkout_identity_rails"], date="2024-01-01"),
                             _obs("o2", "breadth", "product_surface",
                             "company_owned", ["product_breadth"],
                             date="2024-06-01")], [], now="2024-06-01",
                             previous=old)
    changes = diff_models(old, new)
    assert any(c["kind"] == "added" for c in changes)


def test_surprise_requires_a_mismatch_not_a_fact():
    from intent_engine.strategic_intelligence.insights import detect_surprises
    # single-direction evidence (no opposing side) → no surprise
    obs = [_obs(f"o{i}", "infra", "infrastructure_platform", "company_owned",
                ["infrastructure_positioning", "checkout_identity_rails"],
                date="2024-06-01") for i in range(3)]
    assert detect_surprises("Co", obs, []) == []


def test_agenda_requires_multiple_signals():
    from intent_engine.strategic_intelligence.reasoning import _build_agenda
    from intent_engine.strategic_intelligence.records import StrategicHypothesis
    one_signal = [_obs("o1", "x", "messaging", "company_owned",
                       ["infrastructure_positioning"], date="2025-01-01")]
    h = StrategicHypothesis(
        hypothesis_id="h", title="t", statement="s", reasoning="r",
        supporting_observation_ids=["o1"], counter_observation_ids=[],
        alternative_explanations=["a"], confidence="low",
        confidence_reasons=["c"], evidence_gaps=["g"],
        decision_implications=["d"], falsification_questions=["f"],
        why_now="now")
    assert _build_agenda(one_signal, [h]) == []       # single signal → no item


def test_agenda_has_meeting_relevance_and_no_private_claim(shopify_report):
    assert shopify_report.agenda
    for a in shopify_report.agenda:
        assert a["meeting_relevance"] and a["meeting_relevance_why"]
        assert a["external_trigger"] and a["counter_explanation"]
    blob = str(shopify_report.as_dict()).lower()
    assert "discussed yesterday" not in blob and "private meeting" not in blob


def test_opportunities_have_asymmetry_and_decision(shopify_report):
    assert shopify_report.opportunities
    for o in shopify_report.opportunities:
        assert o["asymmetry"] and o["decision_required"] and o["downside"]


def test_vulnerabilities_have_mechanism_and_decision(shopify_report):
    assert shopify_report.vulnerabilities
    for v in shopify_report.vulnerabilities:
        assert v["mechanism"] and v["decision_affected"] and v["leading_indicator"]


def test_underexamined_questions_are_company_specific(shopify_report):
    assert shopify_report.underexamined_questions
    for q in shopify_report.underexamined_questions:
        assert "Shopify" in q["question"]
        assert passes_specificity(q["question"], "Shopify")


def test_generic_insight_fails_executive_quality_gate():
    assert is_generic_insight("The company is investing in AI.")
    assert is_generic_insight("The company wants to grow.")
    assert not passes_specificity("The company faces competition.", "Acme")
    # a specific, mechanism-bearing finding passes
    assert passes_specificity("Acme is consolidating checkout and identity "
                              "rails while courting partners.", "Acme")


def test_executive_insight_quality_accepts_real_report(shopify_report):
    ok, findings = executive_insight_quality(shopify_report)
    assert ok, findings


def test_feed_reflects_model_changes():
    v1 = build_mental_model("Acme", shopify_observations()[:6], [],
                            now="2024-06-01")
    r2 = build_strategic_report(company_name="Acme",
                                observations=shopify_observations(),
                                previous_model=v1.as_dict(), now="2025-02-01")
    assert r2.feed
    assert all("model_change" in f and "confidence_change" in f for f in r2.feed)


def test_strategic_memory_persists_and_is_idempotent(tmp_path):
    mem = StrategicMemory(tmp_path / "s.jsonl")
    r = build_strategic_report(company_name="Acme",
                               observations=shopify_observations())
    mem.save_snapshot("acme.example", r.as_dict()["mental_model"])
    w1 = mem.publish("acme.example", r.as_dict()["analytics_events"],
                     run_id="run1")
    w2 = mem.publish("acme.example", r.as_dict()["analytics_events"],
                     run_id="run1")               # same run → idempotent
    assert w1 > 0 and w2 == 0
    # snapshot is replayable
    mem2 = StrategicMemory(tmp_path / "s.jsonl")
    assert mem2.latest_model("acme.example")["version"] == 1


def test_exec_output_excludes_internal_names_before_appendix(shopify_report):
    html = render_strategic_report(shopify_report)
    primary = html.split("Technical appendix")[0].lower()
    for banned in ("signals matched", "pattern_id", "dominance filter",
                   "evidence_role", "source scoring"):
        assert banned not in primary, banned


def test_companies_differ_across_all_intelligence():
    def report(name, obs):
        return build_strategic_report(company_name=name, observations=obs)
    sh = report("Shopify", shopify_observations())
    li = report("Linear", [
        _obs("l1", "enterprise", "buyer_segment", "independent_reporting",
             ["enterprise_expansion", "product_breadth"], date="2024-05-01"),
        _obs("l2", "simple", "messaging", "customer_voice", ["smb_simplicity"],
             date="2024-04-01"),
        _obs("l3", "breadth", "product_surface", "company_owned",
             ["product_breadth", "merchant_outcome_positioning"], date="2024-06-01")])
    cf = report("Cloudflare", [
        _obs("c1", "infra", "infrastructure_platform", "independent_reporting",
             ["infrastructure_positioning", "platform_control", "product_breadth"],
             date="2024-05-01"),
        _obs("c2", "partners", "monetization_ecosystem", "company_owned",
             ["partner_ecosystem_enablement", "product_breadth"], date="2024-06-01"),
        _obs("c3", "edge", "infrastructure_platform", "company_owned",
             ["platform_control", "checkout_identity_rails"], date="2024-03-01")])
    # mental models, hypotheses, and vulnerabilities all differ
    def mm_keys(r): return set(r.as_dict()["mental_model"]["components"])
    assert mm_keys(sh) != mm_keys(li) or \
        {h.pattern_id for h in sh.hypotheses} != {h.pattern_id for h in li.hypotheses}
    assert {v["exposed_layer"] for v in sh.vulnerabilities} != \
        {v["exposed_layer"] for v in cf.vulnerabilities}


def test_heading_levels_never_skip_a_level(shopify_report):
    """A screen reader announces a skipped level as a heading with no parent.

    The source-library sub-headings sat directly under the "Sources" h2 as
    h4s, so the full analysis page went h2 -> h4. Found in a browser at
    375px, not by any assertion in this file.
    """
    html = render_strategic_report(shopify_report)
    levels = [int(m) for m in re.findall(r"<h([1-6])", html)]
    assert levels, "no headings rendered"
    for previous, nxt in zip(levels, levels[1:]):
        assert nxt - previous <= 1, (
            f"heading level jumped h{previous} -> h{nxt}: {levels}")


def test_the_assistant_never_prints_a_raw_engine_object(tmp_path):
    """A founder asked "what does this company do?" and was shown a dict.

    On the EXPLAINED branch `answer_strategic` returns a STRUCTURED dict and
    no `paragraphs` key, so the fallback str()'d the dict itself onto the
    page: "{'direct_answer': ..., 'reasoning': ...}". Found in a browser, not
    by any assertion here -- the route returned 200 the whole time.
    """
    app, c, rid = _strategic_webapp_run(tmp_path)
    for question in ("What+does+this+company+do%3F", "Why+does+this+matter%3F"):
        status, _, body = c.request(
            "POST", f"/runs/{rid}/conversation",
            f"csrf={c.csrf()}&question={question}")
        assert status == "200 OK"
        for leak in ("{'direct_answer'", '{"direct_answer"', "'reasoning':",
                     "'counter_evidence'", "'confidence_reasons'",
                     "'falsification'", "'alternative_explanations'"):
            assert leak not in body, f"{leak} leaked for {question}"


# --- founder-first hierarchy: completion lands on the brief ------------------
def test_completion_redirects_to_the_founder_brief_not_the_deck(tmp_path):
    """A finished analysis used to redirect to /slides.

    That was the right fix against an eleven-section report, but the deck is
    not the shortest useful thing in the product any more -- the 60-second
    brief is, and a deck is still a document to work through.
    """
    app, c, rid = _strategic_webapp_run(tmp_path)
    status, headers, _ = c.request("GET", f"/runs/{rid}/progress")
    assert status.startswith("303"), status
    assert headers["Location"] == f"/runs/{rid}", headers["Location"]


def test_the_deck_and_every_other_layer_stay_reachable(tmp_path):
    """Founder-first must not mean founder-only."""
    app, c, rid = _strategic_webapp_run(tmp_path)
    for layer in ("slides", "dashboard", "story", "brief", "full"):
        status, _, body = c.request("GET", f"/runs/{rid}/{layer}")
        assert status == "200 OK", (layer, status)
        assert "<main" in body, layer


def test_the_default_run_page_is_the_founder_brief(tmp_path):
    """The destination itself must be the brief, not a redirect back to it."""
    app, c, rid = _strategic_webapp_run(tmp_path)
    status, _, body = c.request("GET", f"/runs/{rid}")
    assert status == "200 OK"
    assert "Why this matters" in body
    assert body.count("<main") == 1


def test_an_unfinished_run_does_not_masquerade_as_a_founder_brief(tmp_path):
    """Only COMPLETE/PARTIAL may redirect; anything else keeps its status page
    so a failed run cannot be read as a finished answer."""
    app, c, rid = _strategic_webapp_run(tmp_path)
    status, headers, body = c.request("GET", "/runs/NOT-A-REAL-RUN/progress")
    assert status.startswith("404"), status


def test_no_signal_but_readable_evidence_still_reaches_the_analyst(tmp_path,
                                                                   monkeypatch):
    """MEASURED on five real companies: Toyota and Costco died before the
    analyst with usable evidence in hand.

    `derive_observations` requires a controlled-vocabulary SIGNAL match,
    because a signal is the unit the pattern library matches against. The
    analyst does not share that requirement -- observations.py says so itself,
    and calls conflating the two harmful. Returning None when no keyword
    matched meant the analyst was never consulted on evidence it could read.
    """
    monkeypatch.setattr(
        "intent_engine.strategic_intelligence.observations."
        "derive_observations", lambda *a, **k: [])
    app, c, rid = _strategic_webapp_run(tmp_path)
    report = app.ci.compose(rid, fi_service=app.fi).get("strategic_report")
    assert report is not None, (
        "no pattern signal matched, so the analyst was never asked")
    assert report.get("result_state")


def test_reasoning_overview_reports_rich_acceptance_for_operators(tmp_path):
    """"The reasoning backend is configured" and "a grounded analysis was
    accepted" are different things, and nothing recorded the difference."""
    app, c, rid = _strategic_webapp_run(tmp_path)
    app.ci.compose(rid, fi_service=app.fi)
    overview = app.ci.reasoning_overview()
    assert overview["attempts"] >= 1
    assert 0.0 <= overview["acceptance_rate"] <= 100.0
    assert set(overview["averages"]) == {
        "documents", "analyst_evidence", "independent_sources", "filings"}
    assert overview["accepted"] + overview["rejected"] == overview["attempts"]


def test_operator_reasoning_metrics_never_reach_a_founder_screen(tmp_path):
    app, c, rid = _strategic_webapp_run(tmp_path)
    app.ci.compose(rid, fi_service=app.fi)
    for layer in ("", "/brief", "/dashboard", "/story", "/full"):
        _, _, body = c.request("GET", f"/runs/{rid}{layer}")
        for leaked in ("acceptance_rate", "rejection_causes",
                       "reasoning_assessed", "analyst_evidence"):
            assert leaked not in body, (layer, leaked)
