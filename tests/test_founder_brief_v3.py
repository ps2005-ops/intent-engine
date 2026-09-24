"""The founder decision experience — the customer's complaints, as tests.

Most of these assert a REFUSAL: that an insight without a consequence cannot be
displayed, that a sparse company cannot dead-end, that engine trading
performance cannot appear as founder intelligence.
"""
import re
import pytest

from intent_engine.founder_brief import build as B
from intent_engine.founder_brief import contract as C
from intent_engine.founder_brief import gate as G
from intent_engine.founder_brief import render as R
from tests import canonical_market as CM


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


# --- market context, as the product actually assembles it -------------------
# `founder_brief/market.py` used to stand here: a consumer for
# `market_intel_export.v1`, the market-learning engine's own export. It is
# gone, and its unit tests with it, because the founder product no longer
# reads that contract from either end:
#
#   * `market_intel_export.v2` is produced FOUNDER-SIDE, by
#     `external_intel/market_producer.py`, from public price history. Its
#     contract module records why -- v1 guarded with a blacklist, and the
#     field that leaks is the one nobody thought of.
#   * v2 dropped `signal.state` and `opportunity.state` ON PURPOSE, as
#     INTERNAL. The v1 consumer rendered the first of them, so wiring it back
#     up would reintroduce the exact leak v2 exists to prevent.
#   * `_market_snapshot` refuses a v1 file outright, and
#     `test_market_context_wiring` pins that refusal: v1 and v2 disagree about
#     units, so reading one with the other's code turns a 2.1% move into 0.0%.
#
# What survives here is what was always the point: assertions on the SERVED
# surface. The fixture is built through the real producer and the real
# presenter, so these tests now assert against the shape production delivers
# rather than one no code path can produce. The v1 consumer's own properties
# -- version refusal, ticker mismatch, staleness, unmeasurable-is-never-zero,
# fixed disclaimer text -- are covered against v2 in
# `tests/test_market_intel_contract.py`.
def _market_context(ticker="ACME"):
    """A populated `brief.market_context`, assembled the production way.

    Deterministic rather than random: a drift plus a repeating wobble, so
    volatility and drawdown are real figures. A flat series would report 0%
    for both, and a zero is a measurement -- it would make this fixture assert
    the opposite of what the export is careful about.
    """
    import datetime
    import math

    from intent_engine.external_intel import market_contract as MC
    from intent_engine.external_intel import market_producer as MP
    from intent_engine.external_intel import pack, presenter

    as_of = "2026-07-31"

    def closes(start, drift, wobble, n=400):
        out, day, i = {}, datetime.date.fromisoformat(as_of), 0
        while len(out) < n:
            if day.weekday() < 5:
                out[day.isoformat()] = round(
                    start + drift * i + wobble * math.sin(i / 6.0)
                    + (wobble / 2) * math.sin(i / 2.3), 4)
                i += 1
            day -= datetime.timedelta(days=1)
        return out

    payload = MP.build_export(
        ticker=ticker, closes=closes(100.0, -0.05, 1.6),
        benchmark_closes=closes(400.0, -0.02, 2.0),
        as_of=as_of, exchange="NASDAQ", currency="USD")
    intel = MC.MarketIntel(available=True, ticker=ticker, payload=payload,
                           stale=False, age_days=1)
    return presenter.market_context_dict(
        pack.build_context(market=intel, as_of=as_of))


def _absent_market_context(reason="no market snapshot"):
    """The absent shape `presenter.market_context_dict` emits, verbatim."""
    return {"available": False, "reason": reason, "modules": {},
            "limitations": []}


def _market_module(market=None, footing=None):
    """The market module as a founder actually receives it.

    `render_market` used to serve this and was deleted unrouted -- market
    context reaches the page through `layers.build_dashboard`, which reads
    `brief.market_context`. Asserting here is asserting on the served surface.
    """
    from intent_engine.founder_brief import layers as L
    modules = L.build_dashboard(_rich(market=market), footing=footing or {})
    return next(m for m in modules if m.key == "market_trajectory")


def test_the_assembled_market_context_carries_an_interpretation():
    """Every module a founder is shown says what changed and why it matters."""
    context = _market_context()
    assert context["available"], context
    for name, module in context["modules"].items():
        assert module.get("what_changed"), name
        assert module.get("so_what"), name


def test_no_paper_control_performance_can_reach_the_page():
    module = _market_module(_market_context())
    text = " ".join([module.what_changed, module.so_what,
                     module.what_to_watch, module.text_alternative]
                    + [f"{r.get('label')} {r.get('value')} {r.get('so_what')}"
                       for r in module.rows]).lower()
    assert text.strip(), "the module rendered nothing to check"
    for banned in ("win rate", "sharpe", "expectancy", "alpha",
                   "paper_control", "profit factor"):
        assert banned not in text


# --- rendering + accessibility ---------------------------------------------
# `render_brief` is gone: it built the primary screen from
# `FounderBrief.key_insight`, which is None whenever the thesis view is
# withheld, so it printed "No strategic conclusion is being asserted" while the
# composed decision was DECISION_READY. These contracts are real and outlived
# it, so they are asserted against the surface that actually serves them now.

def rendered(brief, run_id="r1", report=None):
    """A FounderBrief rendered through the LIVE primary surface.

    `report` matters when a test asserts anything about EVIDENCE: the
    narrative cites the report's observations, not the brief's, because the
    citation has to resolve through the real evidence route.
    """
    from intent_engine.founder_brief import narrative as N
    story = N.build_narrative(company=brief.company, brief=brief,
                              report=report or {})
    return N.render_narrative(story, run_id=run_id)


def _cited_report():
    """A minimal report whose observations are citable."""
    return {"company_name": "Acme",
            "hypotheses": [{"hypothesis_id": "h1",
                            "statement": "Growth is shifting to enterprise.",
                            "reasoning": "Enterprise buyers dominate the "
                                         "dated announcements.",
                            "supporting_observation_ids": ["ev-1"],
                            "strongest_support_ids": ["ev-1"],
                            "counter_observation_ids": ["ev-2"],
                            "alternative_explanations": [
                                "The pricing change is unrelated to segment."],
                            "confidence": "moderate",
                            "confidence_reasons": ["two dated sources agree"],
                            "evidence_gaps": ["No disclosed revenue split."],
                            "decision_implications": [
                                "Whether to fund enterprise delivery or "
                                "protect self-serve onboarding."],
                            "falsification_questions": [
                                "Whether the next two wins are self-serve."]}],
            "observations": [
                {"observation_id": "ev-1",
                 "excerpt": "A multi-year agreement with a logistics operator "
                            "was announced.",
                 "source_title": "Trade press", "date": "2026-06-02",
                 "source_class": "independent_reporting"},
                {"observation_id": "ev-2",
                 "excerpt": "The pricing page still lists a self-serve tier.",
                 "source_title": "Acme pricing", "date": "2026-05-11",
                 "source_class": "company_owned"}],
            "evidence_gaps": ["No disclosed revenue split by segment."]}


def test_the_rendered_primary_view_has_one_main_and_one_h1():
    html = rendered(_rich())
    assert html.count("<main") == 1
    assert html.count("<h1") == 1


def test_the_answer_appears_before_the_evidence_links_in_the_markup():
    """Order is the product decision: a reader who stops early still has the
    consequence."""
    html = rendered(_rich())
    # "Evidence and sources" was the grid's label for the source list; the
    # secondary nav calls it "Sources". The ORDER is the assertion and it is
    # unchanged: the answer comes before any way out of the page.
    assert html.index('id="executive_answer"') < html.index("Sources")


def test_no_internal_terms_in_rendered_output():
    for brief in (_rich(), _sparse()):
        html = rendered(brief).lower()
        for term in ("run_id", "strategic_report", "source_class",
                     "hypothesis_id", "observation_id", "blocked_by"):
            assert term not in html, term


def test_depth_is_offered_but_never_required():
    """Offered, and still never required.

    The narrative is a SECONDARY surface now, so what it offers is the other
    secondary surfaces and the way back into the six-step story -- not a grid
    of six story destinations, which is the thing §16 removed. The story's own
    steps are reachable in order from step 1, which `test_no_layer_is_orphaned`
    proves.
    """
    from intent_engine.founder_brief import flow

    html = rendered(_rich())
    for href in ("/sources", "/brief", "/xray"):
        assert href in html, href
    assert flow.STEPS[0].suffix in html


def test_absent_market_data_teaches_rather_than_saying_unavailable():
    module = _market_module(_absent_market_context("no snapshot"),
                            footing={"ticker": "ACME", "listing_exchange": ""})
    text = " ".join([module.what_changed, module.so_what,
                     module.what_to_watch])
    # "Unavailable" is an engineering status, not intelligence: six live
    # dashboards opened with a stack of them. The module has to say what is
    # not established, why, and what would settle it.
    assert "Unavailable" not in text
    assert "0%" not in text
    assert module.so_what and module.what_to_watch
    assert "ACME" in text, "the gap is reported about THIS company"


# --- the release gate -------------------------------------------------------
def test_the_gate_passes_on_a_good_rich_brief():
    b = _rich()
    assert G.check(b, rendered(b)).passed


def test_the_gate_passes_on_a_good_sparse_brief():
    b = _sparse()
    assert G.check(b, rendered(b)).passed


def test_the_gate_fails_when_a_major_insight_loses_its_so_what():
    """THE GATE PROOF — a real rule deliberately broken."""
    b = _rich()
    object.__setattr__(b.key_insight, "so_what", "")
    result = G.check(b, rendered(b))
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


# --- one screen, one sentence, once -----------------------------------------
def test_the_primary_screen_never_prints_one_sentence_three_times():
    """SEEN LIVE on Palantir, not in any assertion.

    `risks` and `questions` were both empty, so `biggest_risk`,
    `biggest_unknown` and a "Find out:" action all fell back to the same first
    evidence gap. One sentence, three headings, one screen.
    """
    gap = "every source here is published by the company itself"
    report = {"observations": [
        {"text": "Acme sells three products.", "date": "2026-05-01",
         "source_class": "company_owned", "observation_id": "ev-1"}],
        "evidence_gaps": [gap], "risks": [], "questions": []}
    b = B.build(company="Acme", mode=B.MARKETING_ONLY, report=report,
                observations=report["observations"])
    rendered = " ".join(filter(None, [
        b.biggest_risk, b.biggest_unknown, *b.next_actions]))
    assert rendered.lower().count(gap) <= 1, rendered


def test_what_changed_does_not_list_the_same_development_twice():
    """SEEN LIVE: two observations carried the same derived sentence and both
    were printed under "What changed", with the same date."""
    same = "Acme sells several distinct products rather than one."
    report = {"observations": [
        {"text": same, "date": "2026-08-02", "source_class": "company_owned",
         "observation_id": "ev-1"},
        {"text": same, "date": "2026-08-02", "source_class": "company_owned",
         "observation_id": "ev-2"}]}
    b = B.build(company="Acme", mode=B.MARKETING_ONLY, report=report,
                observations=report["observations"])
    assert len(b.what_changed) <= 1, b.what_changed


def test_an_action_repeating_the_risk_is_dropped_despite_its_prefix():
    """"Find out: X" and "X" are the same sentence to a reader."""
    gap = "Whether customers moved their source of truth is not observable."
    report = {"observations": [
        {"text": "Acme sells software.", "date": "2026-05-01",
         "source_class": "company_owned", "observation_id": "ev-1"}],
        "evidence_gaps": [gap], "risks": [], "questions": []}
    b = B.build(company="Acme", mode=B.MARKETING_ONLY, report=report,
                observations=report["observations"])
    joined = " ".join(b.next_actions).lower()
    if b.biggest_risk:
        assert gap.lower() not in joined, b.next_actions


def test_a_label_never_runs_into_the_sentence_it_labels():
    """SEEN LIVE: "Biggest riskevery source here is..." -- a bare <span> is
    inline, so the label and the sentence ran together in the rendered text.

    The old primary screen that produced it is gone; the construct is not.
    Every label the live surface renders is a block-level element or carries
    its own boundary, so the two can never abut as raw text.
    """
    html = rendered(_rich())
    # a chip or a term is always closed before its value begins
    assert not re.search(r'<span class="prov">[^<]*</span>[A-Za-z]', html)
    assert not re.search(r"</dt><dd[^>]*>\s*</dd>", html)
    for label, value in re.findall(r"<dt[^>]*>(.*?)</dt><dd[^>]*>(.*?)</dd>",
                                   html, re.S):
        assert label.strip() and value.strip(), (label, value)


def test_the_live_surface_never_shows_a_confidence_grade_alone():
    """MEASURED on six live companies: five briefs opened "Low." A founder
    reads that as a verdict on the COMPANY, not a statement about the evidence
    behind it. A grade cannot tell anyone what to do.

    The primary screen no longer prints a grade at all -- it states the
    limitation instead, which is the actionable half. This asserts the grade
    has not crept back in as a bare word; `confidence_sentence` itself is
    unit-tested in test_confidence_language.py.
    """
    html = rendered(_rich())
    text = re.sub(r"<[^>]+>", " ", html)
    for para in re.split(r"(?<=[.!?])\s+", text):
        assert not R.is_bare_grade(para), para


def test_every_confidence_reason_says_what_would_move_it():
    """The only actionable part of a confidence statement is what would change
    it. Each reason is also written to survive the renderer's word clip --
    a longer sentence was being truncated exactly at that clause."""
    from intent_engine.founder_brief.build import _confidence
    k = _rich().key_insight
    for observations in ([{"source_class": "company_owned"}] * 10,
                         [{"source_class": "independent_reporting",
                           "date": "2026-01-01"}] * 4,
                         [{"source_class": "independent_reporting"}]):
        label, reason = _confidence(observations, {}, k)
        assert len(reason.split()) <= 40, (label, len(reason.split()))
        assert any(cue in reason.lower() for cue in
                   ("would move", "would confirm", "would settle")), reason
