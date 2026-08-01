"""The founder decision experience — the customer's complaints, as tests.

Most of these assert a REFUSAL: that an insight without a consequence cannot be
displayed, that a sparse company cannot dead-end, that engine trading
performance cannot appear as founder intelligence.
"""
import pytest

from intent_engine.founder_brief import build as B
from intent_engine.founder_brief import contract as C
from intent_engine.founder_brief import gate as G
from intent_engine.founder_brief import market as M
from intent_engine.founder_brief import render as R


def _insight(**kw):
    base = dict(fact="Growth shifted from self-serve to enterprise contracts.",
                interpretation="Three of four dated announcements name "
                               "enterprise buyers.",
                so_what="Revenue becomes lumpier and depends on a few long "
                        "negotiations.",
                decision="Whether to fund enterprise delivery or protect "
                         "self-serve onboarding.",
                watch="Whether the next two customer announcements are also "
                      "enterprise.",
                evidence_ids=("ev-1",))
    base.update(kw)
    return C.FounderInsight(**base)


# --- the "so what" contract -------------------------------------------------
def test_a_valid_insight_passes():
    assert C.validate(_insight())


def test_an_insight_without_a_so_what_is_rejected():
    with pytest.raises(C.InsightRejected):
        C.validate(_insight(so_what=""))


def test_an_insight_without_a_decision_is_rejected():
    with pytest.raises(C.InsightRejected):
        C.validate(_insight(decision=""))


def test_a_so_what_that_merely_restates_the_fact_is_rejected():
    """The failure a template check cannot see: the field is populated and
    teaches nothing."""
    with pytest.raises(C.InsightRejected) as exc:
        C.validate(_insight(
            fact="Revenue increased 18 percent this quarter.",
            so_what="Revenue increased by 18 percent this quarter."))
    assert "restates" in str(exc.value)


def test_a_decision_naming_no_choice_is_rejected():
    with pytest.raises(C.InsightRejected) as exc:
        C.validate(_insight(decision="This is an interesting development."))
    assert "no choice" in str(exc.value)


def test_a_major_insight_must_cite_evidence():
    with pytest.raises(C.InsightRejected):
        C.validate(_insight(evidence_ids=()))


def test_internal_vocabulary_is_rejected_from_founder_text():
    with pytest.raises(C.InsightRejected) as exc:
        C.validate(_insight(
            so_what="The strategic_report hypothesis_id was withheld, so "
                    "buyers cannot verify the claim."))
    assert "internal vocabulary" in str(exc.value)


def test_rejected_insights_are_returned_with_reasons_not_dropped_silently():
    keep, dropped = C.safe_insights([_insight(), _insight(so_what="")])
    assert len(keep) == 1 and len(dropped) == 1
    assert dropped[0]["reason"]


# --- company modes ----------------------------------------------------------
def test_mode_selection_covers_every_company_shape():
    assert B.classify_mode(is_public=True, has_financials=True,
                           evidence_count=9) == B.PUBLIC_INFORMATION_RICH
    assert B.classify_mode(evidence_count=2, independent_sources=0,
                           has_thesis=False) == B.MARKETING_ONLY
    assert B.classify_mode(evidence_count=5, independent_sources=0,
                           has_thesis=True) == B.SMALL_STARTUP
    assert B.classify_mode(evidence_count=4, independent_sources=1,
                           has_thesis=True,
                           employee_hint="local") == B.LOCAL_BUSINESS


# --- the sparse case, which is the whole complaint --------------------------
def _sparse():
    obs = [{"text": "We are the industry-leading platform for seamless "
                    "automation.", "source_class": "company_owned"},
           {"text": "Our product helps teams automate repetitive operations.",
            "source_class": "company_owned"}]
    return B.build(company="Northwind", mode=B.MARKETING_ONLY, observations=obs)


def test_a_sparse_company_is_never_a_dead_end():
    b = _sparse()
    assert b.is_useful
    assert b.verified or b.unclear
    assert len(b.next_actions) >= 1
    assert len(b.internal_questions) == 3
    assert len(b.public_proofs) == 3


def test_a_sparse_company_answers_all_seven_questions():
    result = G.comprehension(_sparse())
    assert result["passed"], result["unanswered"]


def test_marketing_superlatives_are_separated_from_checkable_statements():
    b = _sparse()
    assert any("industry-leading" in c for c in b.claimed)
    assert all("industry-leading" not in v for v in b.verified)


def test_a_sparse_brief_never_invents_business_facts():
    b = _sparse()
    text = " ".join([b.biggest_risk, b.biggest_unknown, *b.unclear,
                     *b.next_actions, *b.public_proofs]).lower()
    for invented in ("market share", "revenue grew", "customers adopted",
                     "unit economics", "pivoted"):
        assert invented not in text


def test_a_sparse_brief_says_it_diagnoses_visibility_not_strategy():
    b = _sparse()
    assert "visible" in b.confidence_reason.lower()
    assert b.confidence.lower().startswith("low")


# --- the rich case ----------------------------------------------------------
def _rich(market=None):
    # The REAL pipeline vocabulary, not an invented one: `tension`,
    # `why_care`, `falsification_questions` and `supporting_observation_ids`
    # are the field names the strategic report actually emits. Testing against
    # the real shape is the only way this fixture stays honest.
    report = {"thesis": {
        "view": "Growth is shifting from self-serve to enterprise contracts.",
        "transition": "Acme is moving from self-serve signups to negotiated "
                      "enterprise agreements.",
        "tension": "Revenue becomes lumpier and leans on a few long deals "
                   "while the brand still promises self-serve simplicity.",
        "why_care": "Whether to fund enterprise delivery capacity or protect "
                    "self-serve onboarding spend."},
        "hypotheses": [{
            "statement": "Growth is shifting toward enterprise contracts.",
            "reasoning": "Three of four dated announcements name enterprise "
                         "buyers and the pricing page removed the top "
                         "self-serve tier.",
            "falsification_questions": [
                "Whether the next two customer announcements are also "
                "enterprise."],
            "supporting_observation_ids": ["ev-1", "ev-2"],
            "confidence": "low"}],
        "questions": ["Which segment retains revenue?"],
        "evidence_gaps": ["No disclosed revenue split by segment."]}
    obs = [{"text": "Multi-year agreement with a logistics operator.",
            "date": "2026-06-02", "source_class": "independent_reporting",
            "observation_id": "ev-1"},
           {"text": "Pricing page replaced the top tier with contact sales.",
            "date": "2026-05-11", "source_class": "company_owned",
            "observation_id": "ev-2"},
           {"text": "Trade press reported two enterprise wins.",
            "date": "2026-04-20", "source_class": "independent_reporting",
            "observation_id": "ev-3"}]
    return B.build(company="Acme", mode=B.PUBLIC_INFORMATION_RICH,
                   report=report, observations=obs, market=market)


def test_a_rich_company_answers_all_seven_questions():
    assert G.comprehension(_rich())["passed"]


def test_what_changed_lists_only_dated_developments():
    b = _rich()
    assert b.what_changed
    assert all(item["when"] for item in b.what_changed)
    assert len(b.what_changed) <= 3


def test_at_most_three_recommendations():
    assert len(_rich().next_actions) <= G.MAX_RECOMMENDATIONS


def test_confidence_always_states_what_limits_it():
    b = _rich()
    assert b.confidence and b.confidence_reason
    assert len(b.confidence_reason) > 40


# --- market export consumer -------------------------------------------------
def _export(**kw):
    base = {"export_version": "market_intel_export.v1", "ticker": "ACME",
            "latest_completed_market_date": "2026-07-31",
            "freshness": {"age_days": 1},
            "price_change": {"1m": {"value": -0.12, "status": "observed"}},
            "benchmark_relative": {"1y": {"value": -0.16,
                                          "status": "observed"}},
            "volatility": {"value": 0.42, "status": "inferred"},
            "fundamentals": {"status": "unmeasurable"},
            "signal": {"state": "quiet"}}
    base.update(kw)
    return base


def test_an_unknown_schema_version_is_refused():
    ctx = M.consume(_export(export_version="market_intel_export.v2"))
    assert not ctx.available
    assert "v1" in ctx.reason


def test_a_ticker_mismatch_is_refused():
    ctx = M.consume(_export(), expected_ticker="OTHER")
    assert not ctx.available
    assert "not OTHER" in ctx.reason


def test_a_stale_snapshot_is_flagged_not_hidden():
    ctx = M.consume(_export(), expected_ticker="ACME", today="2026-09-01")
    assert ctx.stale
    assert any("days old" in l for l in ctx.limitations)


def test_missing_fundamentals_become_a_limitation_never_a_zero():
    ctx = M.consume(_export(), expected_ticker="ACME")
    assert "fundamentals" not in (ctx.modules or {})
    assert any("verified revenue" in l for l in ctx.limitations)


def test_every_market_module_carries_an_interpretation():
    ctx = M.consume(_export(), expected_ticker="ACME")
    for name, module in ctx.modules.items():
        assert module.get("so_what"), name
        assert module.get("what_changed"), name


def test_the_market_disclaimer_is_always_present():
    ctx = M.consume(_export(), expected_ticker="ACME")
    assert "not an investment recommendation" in ctx.disclaimer


def test_the_signal_module_describes_the_signal_not_the_company():
    ctx = M.consume(_export(), expected_ticker="ACME")
    assert "describes the signal, not the company" in \
        ctx.modules["signal"]["so_what"]


def test_no_paper_control_performance_can_reach_the_page():
    ctx = M.consume(_export(), expected_ticker="ACME")
    html = R.render_market(ctx.as_dict()).lower()
    for banned in ("win rate", "sharpe", "expectancy", "alpha",
                   "paper_control", "profit factor"):
        assert banned not in html


# --- rendering + accessibility ---------------------------------------------
def test_the_rendered_brief_has_one_main_and_one_h1():
    html = R.render_brief(_rich(), run_id="r1")
    assert html.count("<main") == 1
    assert html.count("<h1") == 1


def test_so_what_appears_before_evidence_links_in_the_markup():
    """Order is the product decision: a reader who stops early still has the
    consequence."""
    html = R.render_brief(_rich(), run_id="r1")
    assert html.index("Why this matters") < html.index("Evidence and sources")


def test_no_internal_terms_in_rendered_output():
    for brief in (_rich(), _sparse()):
        html = R.render_brief(brief, run_id="r1").lower()
        for term in ("run_id", "strategic_report", "source_class",
                     "hypothesis_id", "observation_id", "blocked_by"):
            assert term not in html, term


def test_depth_is_offered_but_never_required():
    html = R.render_brief(_rich(), run_id="r1")
    for href in ("/story", "/brief", "/sources", "/full"):
        assert href in html


def test_unavailable_market_data_renders_unavailable_not_a_number():
    html = R.render_market(M.unavailable("no snapshot").as_dict())
    assert "Unavailable" in html
    assert "0%" not in html


# --- the release gate -------------------------------------------------------
def test_the_gate_passes_on_a_good_rich_brief():
    b = _rich()
    assert G.check(b, R.render_brief(b, run_id="r1")).passed


def test_the_gate_passes_on_a_good_sparse_brief():
    b = _sparse()
    assert G.check(b, R.render_brief(b, run_id="r1")).passed


def test_the_gate_fails_when_a_major_insight_loses_its_so_what():
    """THE GATE PROOF — a real rule deliberately broken."""
    b = _rich()
    object.__setattr__(b.key_insight, "so_what", "")
    result = G.check(b, R.render_brief(b, run_id="r1"))
    assert not result.passed
    assert any("so what" in f for f in result.failures)


def test_the_gate_fails_when_a_sparse_company_dead_ends():
    b = _sparse()
    b.verified = (); b.unclear = (); b.public_proofs = ()
    b.customer_can_see = (); b.internal_questions = ()
    result = G.check(b, "")
    assert not result.passed
    assert any("refusal" in f for f in result.failures)


def test_the_gate_fails_on_more_than_three_recommendations():
    b = _rich()
    b.next_actions = ("a", "b", "c", "d")
    assert not G.check(b, "").passed


def test_the_gate_fails_when_trading_performance_is_presented():
    b = _rich()
    result = G.check(b, "<main><h1>x</h1>Our win rate is 61%</main>")
    assert not result.passed
    assert any("trading performance" in f for f in result.failures)


def test_the_gate_fails_on_investment_recommendation_language():
    b = _rich()
    result = G.check(b, "<main><h1>x</h1>The shares look undervalued.</main>")
    assert not result.passed


def test_the_gate_fails_on_unapproved_execution_copy():
    b = _rich()
    result = G.check(b, "<main><h1>x</h1>We will email your investors.</main>")
    assert not result.passed
    assert any("unapproved execution" in f for f in result.failures)


def test_the_gate_reports_every_failure_not_just_the_first():
    b = _rich()
    b.next_actions = ("a", "b", "c", "d")
    result = G.check(b, "<main><h1>x</h1>win rate 61% undervalued</main>")
    assert len(result.failures) >= 3
