"""End-to-end: which result state a run reaches, and what it is allowed to say.

The rule these pin down is the one that matters for trust: when the reasoning
backend is unavailable or its output fails verification, the product says so.
It does not quietly present the pattern library's scaffolds as findings about
the company.
"""
from intent_engine.company_ingestion.service import CompanyIngestionService
from intent_engine.founder_intelligence.service import FounderIntelligenceService
from intent_engine.strategic_intelligence.analyst import ResultState

_HOME = ("Examplecorp builds commerce infrastructure for merchants. Sellers "
         "use our commerce platform, storefront tools and point of sale to "
         "sell online across every channel, with checkout built in.")
_PRESS = ("Examplecorp announced commerce components for enterprise "
          "merchants, extending its commerce infrastructure to large "
          "merchants who previously built their own storefront and checkout.")
_INVESTORS = ("Examplecorp reports revenue from merchant subscriptions and "
              "merchant solutions. Our merchants and sellers use the commerce "
              "platform, and take rate on storefront checkout drives the "
              "merchant solutions line.")
_REVIEWS = ("Independent merchant reviews praise how quickly sellers can "
            "launch a storefront, citing that as the reason they stay on the "
            "commerce platform rather than moving to heavier alternatives.")


def _transport(url, timeout):
    import email as _email
    import urllib.error
    u = url.lower()
    if any(k in u for k in ("/press", "/newsroom", "/news", "/media")):
        title, body = "Press", _PRESS
    elif "investor" in u or "/ir" in u:
        title, body = "Investors", _INVESTORS
    elif "g2.com" in u or "trustpilot" in u or "capterra" in u:
        title, body = "Reviews", _REVIEWS
    elif "example.test" in u:
        path = u.split("example.test", 1)[-1].strip("/") or "home"
        title, body = f"Examplecorp {path}", f"Examplecorp {path}. {_HOME}"
    else:
        raise urllib.error.HTTPError(url, 404, "nf",
                                     _email.message_from_string(""), None)
    html = (f"<html><head><title>{title}</title></head>"
            f"<body><p>{body}</p></body></html>")
    return (200, {"content-type": "text/html"}, html.encode(), False)


class RecordedClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def call_tool(self, **kwargs):
        self.calls += 1
        return self.payload


def _run(tmp_path, client):
    ci = CompanyIngestionService(tmp_path / "ci.jsonl", transport=_transport,
                                 resolver=False, analyst_client=client)
    fi = FounderIntelligenceService(tmp_path / "fi.jsonl")
    run = ci.create_run(company_name="Examplecorp",
                        website="https://example.test", user_id="u1",
                        as_of="2026-07-24T00:00:00+00:00")
    rid = run["run_id"]
    cands = ci.discover(rid)
    ci.approve(rid, user_id="u1",
               approved_ids=[c["candidate_id"] for c in cands][:14],
               rejected_ids=[])
    ci.fetch_approved(rid)
    return ci.compose(rid, fi_service=fi)


def test_without_a_backend_the_run_is_evidence_limited_not_confident(tmp_path):
    """No key configured. The scaffolds must not be sold as conclusions."""
    result = _run(tmp_path, client=None)
    report = result["strategic_report"]
    assert report is not None
    assert report["result_state"] == ResultState.EVIDENCE_LIMITED
    assert report["reasoning_provenance"] == "pattern_library"
    assert report["strategic_analysis"] is None
    assert "no strategic conclusion is asserted" in \
        report["result_state_detail"].lower()


def test_a_verified_analysis_supersedes_the_scaffolds(tmp_path):
    good = {
        "entity_scope": {"analysed_entity": "Examplecorp",
                         "is_subsidiary": False},
        "business_model": "Sells commerce infrastructure to merchants.",
        "sufficient_for_strategic_analysis": True,
        "insufficiency_reason": "",
        "evidence_gaps": ["No pricing disclosed."],
        "insights": [{
            "headline": "Examplecorp is taking the checkout and storefront "
                        "surfaces its own app developers built businesses on, "
                        "which raises take rate but puts partner supply at "
                        "risk.",
            "what_is_changing": "First-party commerce components now cover "
                                "what partner apps did.",
            "why_now": "The enterprise tier and app store are both live.",
            "tension": {"side_a": "Owning checkout captures more of each "
                                  "merchant transaction.",
                        "side_b": "Partner app developers supply the breadth "
                                  "that wins merchants in the first place.",
                        "why_it_exists": "The most valuable surfaces are the "
                                         "ones partners also want.",
                        "decision_owner": "Platform leadership",
                        "what_would_resolve_it": "Disclosure of partner-app "
                                                 "revenue share."},
            "economics": {"mechanism": "Owning checkout raises take rate per "
                                       "merchant transaction; losing partner "
                                       "apps lowers merchant retention.",
                          "levers": ["revenue_mix", "switching_costs",
                                     "retention"]},
            "competitive": {"compared_to": ["Adobe Commerce"],
                            "how_this_company_differs": "It sells storefront "
                                                        "and point of sale "
                                                        "together rather than "
                                                        "licensing software.",
                            "likely_responder": "Adobe Commerce",
                            "second_order_effect": "Partner app developers "
                                                   "hedge onto competing "
                                                   "commerce platforms."},
            "counterargument": {"strongest_case_against": "Partner apps may "
                                                          "grow faster than "
                                                          "first-party "
                                                          "components.",
                                "what_would_disprove_this": "Rising "
                                                            "partner-sourced "
                                                            "merchant "
                                                            "revenue."},
            "decision_affected": "Whether to build or partner for the next "
                                 "merchant-facing surface.",
            "monitor": ["Partner app store listings"],
            "confidence": "low",
            "confidence_rationale": "Low -- three company-owned pages only, "
                                    "with no partner or merchant evidence.",
            "citations": [],
        }],
    }
    ci = CompanyIngestionService(tmp_path / "ci.jsonl", transport=_transport,
                                 resolver=False)
    fi = FounderIntelligenceService(tmp_path / "fi.jsonl")
    run = ci.create_run(company_name="Examplecorp",
                        website="https://example.test", user_id="u1",
                        as_of="2026-07-24T00:00:00+00:00")
    rid = run["run_id"]
    cands = ci.discover(rid)
    ci.approve(rid, user_id="u1",
               approved_ids=[c["candidate_id"] for c in cands][:14], rejected_ids=[])
    ci.fetch_approved(rid)
    # cite whatever the pipeline actually derived, so the citation resolves
    from intent_engine.strategic_intelligence.observations import (
        derive_analyst_evidence,
    )
    docs = list(ci.store.retrieved(rid))
    ev = derive_analyst_evidence(docs)
    assert ev, "fixture must yield analyst evidence"
    good["insights"][0]["citations"] = [ev[0].observation_id]

    ci._analyst_client = RecordedClient(good)
    result = ci.compose(rid, fi_service=fi)
    report = result["strategic_report"]
    assert report["result_state"] == ResultState.COMPLETE
    assert report["reasoning_provenance"] == "grounded_analyst"
    assert report["strategic_analysis"]["insights"][0]["headline"].startswith(
        "Examplecorp is taking the checkout")


def test_rejected_analysis_does_not_fall_back_to_scaffolds(tmp_path):
    """A fluent but ungrounded analysis must leave the run visibly limited."""
    bad = {
        "entity_scope": {"analysed_entity": "Examplecorp",
                         "is_subsidiary": False},
        "business_model": "Sells software.",
        "sufficient_for_strategic_analysis": True,
        "insufficiency_reason": "",
        "evidence_gaps": [],
        "insights": [{
            "headline": "The company is absorbing adjacent tools until the "
                        "work lives inside it.",
            "what_is_changing": "Breadth is growing.",
            "why_now": "Now.",
            "tension": {"side_a": "depth", "side_b": "breadth",
                        "why_it_exists": "focus",
                        "what_would_resolve_it": "disclosure"},
            "economics": {"mechanism": "switching cost rises",
                          "levers": ["switching_costs"]},
            "competitive": {"compared_to": ["Someone"],
                            "how_this_company_differs": "broader",
                            "second_order_effect": "rivals respond"},
            "counterargument": {"strongest_case_against": "integrations",
                                "what_would_disprove_this": "churn"},
            "decision_affected": "depth or adjacency",
            "confidence": "moderate",
            "confidence_rationale": "Moderate on company pages alone.",
            "citations": ["obs-does-not-exist"],
        }],
    }
    result = _run(tmp_path, client=RecordedClient(bad))
    report = result["strategic_report"]
    assert report["result_state"] == ResultState.STRATEGICALLY_INSUFFICIENT
    assert report["strategic_analysis"] is None
    assert report["reasoning_provenance"] == "pattern_library"
    checks = {f["check"] for f in report["critic_findings"]}
    assert "citation_unresolvable" in checks
    assert "generic_headline" in checks


def test_result_states_each_explain_themselves():
    for state in ResultState.ALL:
        assert ResultState.EXPLANATION[state].strip()
    # only COMPLETE may render a strategic presentation
    assert ResultState.PRESENTABLE == (ResultState.COMPLETE,)
