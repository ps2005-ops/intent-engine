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



def _decision_payload(citation):
    return {
        "entity_scope": {"analysed_entity": "Examplecorp",
                         "is_subsidiary": False},
        "business_model": {
            "one_line": "Sells commerce infrastructure to merchants.",
            "where_profit_comes_from": "Take rate on storefront checkout.",
            "where_value_leaks": "Partner apps capture merchant workflows "
                                 "the platform does not monetise.",
            "what_customers_actually_buy": "Time to a working storefront.",
            "what_management_appears_to_optimise": "Merchant count and take "
                                                   "rate (inferred).",
        },
        "sufficient_for_strategic_analysis": True,
        "insufficiency_reason": "",
        "the_insight": {
            "sentence": "Examplecorp is taking the checkout and storefront "
                        "surfaces its own app developers built businesses "
                        "on, which raises take rate but puts partner supply "
                        "at risk.",
            "paragraph": "The commerce components sold to enterprise "
                         "merchants cover what partner apps used to.",
            "why_now": "The enterprise tier and app store are both live.",
            "tension": {"side_a": "Owning checkout captures more of each "
                                  "merchant transaction.",
                        "side_b": "Partner app developers supply the breadth "
                                  "that wins merchants in the first place.",
                        "why_it_exists": "The most valuable surfaces are the "
                                         "ones partners also want."},
            "economics": {"mechanism": "Owning checkout raises take rate per "
                                       "merchant transaction; losing partner "
                                       "apps lowers merchant retention.",
                          "levers": ["revenue_mix", "switching_costs",
                                     "retention"]},
            "consequence_chain": [
                "First-party components replace partner app functions.",
                "Partner developers see less upside and build elsewhere.",
                "Merchant breadth narrows and acquisition slows.",
            ],
            "citations": [citation],
        },
        "decisions": [{
            "decision": "Build the next merchant-facing surface first-party, "
                        "or leave it to the partner ecosystem.",
            "why_it_matters": "It sets whether breadth or take rate is the "
                              "growth engine.",
            "urgency": "this_quarter",
            "cost_of_waiting": "Partner developers commit roadmaps a quarter "
                               "ahead; waiting forfeits this cycle.",
            "what_a_competitor_may_do_first": "A rival platform courts the "
                                              "same app developers with "
                                              "better revenue share.",
            "upside": "Higher take rate per merchant.",
            "downside": "Thinner app catalogue and slower merchant growth.",
            "what_would_invalidate_it": "Partner-sourced merchant revenue "
                                        "growing faster than first-party.",
            "what_to_watch": "New listings in the partner app store.",
            "business_impact": "high",
            "reversibility": "one_way_door",
            "verdict": "do_now",
            "cheapest_experiment": "Ask ten partner developers what they are "
                                   "building next quarter.",
            "confidence": "low",
            "confidence_rationale": "Low -- company-owned pages only, with "
                                    "no partner or merchant evidence.",
            "missing_evidence": "Partner revenue share.",
            "citations": [citation],
        }],
        "assumptions": [{
            "assumption": "Partner apps still supply breadth merchants value.",
            "why_we_believe_it": "The app store is promoted as a reason to "
                                 "choose the platform.",
            "what_would_break_it": "Merchants naming first-party components "
                                   "as the reason they stay.",
            "how_load_bearing": "high",
            "confidence": "low",
        }],
        "blind_spots": {
            "everyone_is_discussing": "Take rate.",
            "almost_nobody_is_discussing": "That partner developers commit "
                                           "roadmaps a quarter ahead, so the "
                                           "damage is done before it shows.",
            "where_management_may_be_biased": "First-party revenue is easier "
                                              "to measure than partner "
                                              "breadth.",
            "where_investors_may_be_biased": "Take rate is a cleaner metric "
                                             "than ecosystem health.",
            "where_customers_may_disagree": "Merchants may not care who "
                                            "built the surface.",
        },
        "scenarios": {
            "base_case": "Partner apps thin slowly and take rate rises.",
            "upside_case": "First-party surfaces raise take rate without "
                           "losing app breadth.",
            "downside_case": "Developers leave and merchant acquisition "
                             "slows before the take rate gain lands.",
            "wild_card": "A rival platform offers developers a materially "
                         "better revenue share.",
            "leading_indicators": ["New listings in the partner app store."],
        },
        "board_questions": [
            "What share of merchant retention depends on apps we do not own?",
        ],
        "competitive": {
            "who_is_forcing_the_change": "Merchants asking for one bill.",
            "who_benefits": "Large merchants wanting fewer vendors.",
            "who_loses": "App developers whose function is absorbed.",
            "who_must_respond": "Partner app developers.",
            "who_can_ignore_this": "Merchants on bespoke stacks.",
            "if_nobody_responds": "The app catalogue thins quietly.",
        },
        "questions": [
            "If partner developers stopped building tomorrow, how long "
            "before merchants noticed?",
        ],
        "strongest_case_we_are_wrong": "Partner apps may grow faster than "
                                       "first-party components.",
        "evidence_gaps": ["No pricing disclosed."],
    }


def test_a_verified_analysis_supersedes_the_scaffolds(tmp_path):
    ci = CompanyIngestionService(tmp_path / "ci.jsonl", transport=_transport,
                                 resolver=False)
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
    from intent_engine.strategic_intelligence.observations import (
        derive_analyst_evidence,
    )
    ev = derive_analyst_evidence(list(ci.store.retrieved(rid)))
    assert ev, "fixture must yield analyst evidence"

    ci._analyst_client = RecordedClient(_decision_payload(ev[0].observation_id))
    report = ci.compose(rid, fi_service=fi)["strategic_report"]
    assert report["result_state"] == ResultState.COMPLETE
    assert report["reasoning_provenance"] == "grounded_analyst"
    analysis = report["strategic_analysis"]
    assert analysis["the_insight"]["sentence"].startswith("Examplecorp is "
                                                          "taking the checkout")
    assert analysis["decisions"][0]["cost_of_waiting"]


def test_rejected_analysis_does_not_fall_back_to_scaffolds(tmp_path):
    """A fluent but ungrounded analysis must leave the run visibly limited."""
    bad = _decision_payload("obs-does-not-exist")
    bad["the_insight"]["sentence"] = ("The company is absorbing adjacent "
                                      "tools until the work lives inside it.")
    report = _run(tmp_path, client=RecordedClient(bad))["strategic_report"]
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


def test_a_completed_run_carries_the_daily_view_and_memory(tmp_path):
    """A founder opening this wants the delta and one screen, not the same
    analysis again."""
    ci = CompanyIngestionService(tmp_path / "ci.jsonl", transport=_transport,
                                 resolver=False)
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
    from intent_engine.strategic_intelligence.observations import (
        derive_analyst_evidence,
    )
    ev = derive_analyst_evidence(list(ci.store.retrieved(rid)))
    ci._analyst_client = RecordedClient(_decision_payload(ev[0].observation_id))
    report = ci.compose(rid, fi_service=fi)["strategic_report"]

    view = report["daily_view"]
    assert view["headline"]
    assert view["biggest_threat"]
    assert view["competitor_to_watch"]
    assert view["todays_decision"]["decision"].startswith("Build the next")
    assert view["most_uncertain_assumption"]
    assert view["nobody_is_discussing"]
    # no previous run, so it must say that rather than imply nothing changed
    assert report["strategic_memory"]["first_run"] is True
    assert "first look" in view["what_changed"].lower()
