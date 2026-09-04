"""Dashboard, decision story, executive brief and the action layer.

The properties under test are mostly REFUSALS: no fabricated series, no empty
section, no repeated sentence across layers, no language implying an external
action occurred.
"""
import re
import pytest

from intent_engine.founder_brief import build as B
from intent_engine.founder_brief import contract as C
from intent_engine.founder_brief import gate as G
from intent_engine.founder_brief import layers as L
from intent_engine.founder_brief import render as R
from tests import canonical_market as CM
from tests.test_founder_brief_v3 import (
    _absent_market_context, _cited_report, _market_context, _rich, _sparse,
    rendered,
)


# --- reading budget ---------------------------------------------------------
def test_the_primary_view_fits_the_reading_budget():
    """The ceiling is the real constraint -- a 60-second screen can be short.

    The floor is asserted against a REAL pipeline run in
    test_a_real_run_lands_inside_the_full_reading_budget, because this fixture
    is deliberately smaller than a live report and would fail a floor for the
    wrong reason.
    """
    main = rendered(_rich()).split('<main class="nar">')[1]
    assert L.visible_words(main) <= L.NARRATIVE_MAX


def test_a_real_run_lands_inside_the_full_reading_budget(tmp_path):
    """The budget governs FOUNDER INTELLIGENCE, not interface controls.

    A follow-up form and its suggested questions are how a founder asks for
    more. Counting them against the reading budget would force a choice
    between being answerable and being brief, which is a false trade.

    The default is now the scrollable decision narrative, so the budget it is
    held to is the narrative's. Holding the page that carries the options to
    the old teaser's 300 words would mean deleting the options.
    """
    from tests.test_strategic_intelligence import _strategic_webapp_run
    app, c, rid = _strategic_webapp_run(tmp_path)
    _, _, body = c.request("GET", f"/runs/{rid}/answer")
    main = body.split('<main class="nar">')[1]
    intelligence = L.intelligence_words(main)
    assert L.NARRATIVE_MIN <= intelligence <= L.NARRATIVE_MAX, intelligence
    # and the split is reported, so prose cannot be hidden inside a control
    assert L.visible_words(main) > intelligence


def test_the_answer_alone_is_still_a_sixty_second_read(tmp_path):
    """The whole page is budgeted for depth; the ANSWER is budgeted for speed.

    This is the half of the old 300-word budget that still has to hold. A
    founder gets the core in the first section and scrolls only if they want
    the rest, so a narrative that pushed the answer past a minute of reading
    would have moved the problem rather than fixed it.
    """
    from tests.test_strategic_intelligence import _strategic_webapp_run
    app, c, rid = _strategic_webapp_run(tmp_path)
    _, _, body = c.request("GET", f"/runs/{rid}/answer")
    answer = re.search(r'<section id="executive_answer".*?</section>', body,
                       re.S)
    assert answer, "the default page has no executive answer section"
    words = L.visible_words(answer.group(0))
    assert 0 < words <= L.ANSWER_MAX, words


def test_essential_intelligence_cannot_hide_inside_a_control():
    """The anti-gaming check for the budget split: moving the decision into
    the control block would shrink the measured intelligence while making the
    product worse."""
    html = rendered(_rich())
    assert "Why this matters" in html
    controls_only = re.search(
        r'<section[^>]*class="[^"]*ui-controls[^"]*".*?</section>', html, re.S)
    if controls_only:
        for essential in ("Why this matters", "Decision affected"):
            assert essential not in controls_only.group(0)


def test_the_sparse_primary_view_also_fits():
    main = rendered(_sparse()).split('<main class="nar">')[1]
    assert L.visible_words(main) <= L.NARRATIVE_MAX


def test_no_paragraph_exceeds_the_length_limit():
    html = rendered(_rich())
    for para in re.findall(r"<p[^>]*>(.*?)</p>", html, re.S):
        text = re.sub(r"<[^>]+>", " ", para)
        assert len(text.split()) <= L.MAX_PARAGRAPH_WORDS, text[:80]


def test_primary_order_puts_the_decision_before_the_history():
    """A reader who stops after the decision must already have the action.

    Asserted by SECTION ID: the headings are copy and get reworded, and a
    guard that fails on rewording is a guard people delete.
    """
    html = rendered(_rich())
    order = [html.index(f'id="{k}"') for k in
             ("executive_answer", "why_now", "what_changed")
             if f'id="{k}"' in html]
    assert order == sorted(order), order
    # the answer is first, whatever else rendered
    assert html.index('id="executive_answer"') == min(
        html.index(m) for m in re.findall(r'id="[a-z_]+"', html)
        if m in html and html.index(m) >= 0)


def test_at_most_three_actions_render():
    b = _rich()
    b.next_actions = ("a one", "b two", "c three", "d four", "e five")
    html = rendered(b)
    assert html.count("<li>") - html.count('class="chips"') <= 6


# --- completed insight contract --------------------------------------------
def test_a_decision_without_a_tradeoff_is_rejected():
    """'Improve onboarding' is a task. A decision names an alternative."""
    with pytest.raises(C.InsightRejected) as exc:
        C.validate(C.FounderInsight(
            fact="Growth shifted toward enterprise contracts this year.",
            interpretation="Three announcements name enterprise buyers.",
            so_what="Revenue becomes lumpier and leans on fewer buyers.",
            decision="Invest in enterprise delivery capacity.",
            watch="Whether the next two wins are enterprise.",
            evidence_ids=("ev-1",)))
    assert "trade-off" in str(exc.value)


def test_generic_monitoring_advice_is_rejected():
    with pytest.raises(C.InsightRejected) as exc:
        C.validate(C.FounderInsight(
            fact="Growth shifted toward enterprise contracts this year.",
            interpretation="Three announcements name enterprise buyers.",
            so_what="Revenue becomes lumpier and leans on fewer buyers.",
            decision="Whether to fund delivery or protect self-serve.",
            watch="Monitor this closely.", evidence_ids=("ev-1",)))
    assert "generic" in str(exc.value)


def test_confidence_may_not_exceed_its_evidence():
    with pytest.raises(C.InsightRejected) as exc:
        C.validate(C.FounderInsight(
            fact="Growth shifted toward enterprise contracts this year.",
            interpretation="Three announcements name enterprise buyers.",
            so_what="Revenue becomes lumpier and leans on fewer buyers.",
            decision="Whether to fund delivery or protect self-serve.",
            watch="Whether the next two wins are enterprise.",
            confidence="high", evidence_ids=("ev-1",)))
    assert "stronger than its evidence" in str(exc.value)


def test_the_contract_exposes_the_spec_field_names():
    k = _rich().key_insight
    d = k.as_dict()
    for field in ("fact", "interpretation", "so_what", "decision_affected",
                  "next_check", "confidence", "evidence_ids", "limitations",
                  "company_mode"):
        assert field in d, field


# --- dashboard --------------------------------------------------------------
def test_the_dashboard_never_fabricates_a_financial_series():
    modules = {m.key: m for m in L.build_dashboard(_rich())}
    bt = modules["business_trajectory"]
    assert not bt.available
    assert "fabricated" in bt.unavailable_reason


def test_every_available_module_answers_the_three_questions():
    for m in L.build_dashboard(_rich(market=_market_context())):
        if m.available:
            assert m.so_what, m.key
            assert m.what_changed, m.key
            assert m.text_alternative, m.key


def test_an_unavailable_module_states_why_and_renders_no_number():
    html = R.render_dashboard(L.build_dashboard(_rich()))
    assert "Not established" in html
    # "Unavailable" is an engineering status, not intelligence:
    # six live dashboards opened with a stack of them.
    assert "Unavailable" not in html
    assert "0%" not in html
    assert "$0" not in html


def test_the_dashboard_carries_the_market_disclaimer():
    assert L.MARKET_DISCLAIMER in R.render_dashboard(L.build_dashboard(_rich()))


def test_the_decision_map_carries_a_no_regret_move():
    modules = {m.key: m for m in L.build_dashboard(_rich())}
    labels = [r["label"] for r in modules["decision_map"].rows]
    assert "No-regret move" in labels
    assert "Evidence needed next" in labels


def test_the_timeline_is_deduplicated():
    report = {"timeline": [{"date": "2026-01-01", "text": "Same event"},
                           {"date": "2026-02-01", "text": "Same event"},
                           {"date": "2026-03-01", "text": "Different event"}]}
    modules = {m.key: m for m in L.build_dashboard(_rich(), report)}
    rows = modules["strategic_timeline"].rows
    assert len({r["value"] for r in rows}) == len(rows)


def test_no_control_performance_reaches_the_dashboard(tmp_path):
    html = R.render_dashboard(L.build_dashboard(
        _rich(market=_market_context())))
    for banned in ("win rate", "sharpe", "alpha", "expectancy",
                   "paper_control", "profit factor"):
        assert banned not in html.lower()


# --- decision story ---------------------------------------------------------
def test_the_story_has_no_empty_sections():
    for section in L.build_story(_rich()):
        assert section["paragraphs"]
        assert all(p.strip() for p in section["paragraphs"])


def test_the_story_is_reachable_by_scrolling_without_next():
    html = R.render_story(L.build_story(_rich()), run_id="r1")
    assert "Next" not in html
    assert 'class="storynav"' in html          # sticky nav
    assert 'id="prog"' in html                 # progress
    for section in L.build_story(_rich()):
        assert f'id="{section["key"]}"' in html   # deep-linkable


def test_the_story_does_not_repeat_the_primary_brief():
    """The ledger is pre-loaded with what the 60-second screen already said."""
    brief = _rich()
    ledger = L.Ledger()
    ledger.spend(brief.key_insight.fact, brief.key_insight.so_what,
                 brief.key_insight.decision)
    text = " ".join(p for s in L.build_story(brief, {}, ledger)
                    for p in s["paragraphs"])
    assert brief.key_insight.fact not in text
    assert brief.key_insight.so_what not in text


# --- executive brief --------------------------------------------------------
def test_the_executive_brief_does_not_duplicate_the_primary_brief():
    brief = _rich()
    ledger = L.Ledger()
    ledger.spend(brief.key_insight.fact, brief.key_insight.so_what,
                 brief.key_insight.decision)
    built = L.build_executive_brief(brief, {}, ledger)
    text = " ".join(p for s in built["sections"] for p in s["paragraphs"])
    assert brief.key_insight.so_what not in text


def test_the_executive_brief_omits_sections_it_cannot_support():
    built = L.build_executive_brief(_sparse(), {}, L.Ledger())
    keys = {s["key"] for s in built["sections"]}
    assert "context" not in keys          # no market data for a sparse company


def test_the_executive_brief_never_exceeds_its_ceiling():
    built = L.build_executive_brief(_rich(), {}, L.Ledger())
    assert built["words"] <= built["budget"]["max"], built["words"]


def test_a_rich_brief_below_its_floor_is_reported_as_short():
    """`within_budget` used to mean "not too long", so a rich executive brief
    that collapsed to a fraction of its promised depth reported True.

    A rich brief built from an empty report has almost nothing to say. That is
    a legitimate state for the LAYER, but it is not "within budget", and the
    release gate can only refuse a depth failure it is told about.
    """
    built = L.build_executive_brief(_rich(), {}, L.Ledger())
    assert built["budget"] == {"min": L.EXEC_RICH_MIN, "max": L.EXEC_RICH_MAX}
    assert built["words"] < L.EXEC_RICH_MIN
    assert not built["within_budget"], built["words"]


def test_the_gate_refuses_a_rich_brief_that_misses_its_depth():
    """The executive brief was built by every caller and passed to nobody, so
    a depth failure could not reach the gate at all."""
    b = _rich()
    built = L.build_executive_brief(b, {}, L.Ledger())
    html = rendered(b)
    assert G.check(b, html).passed          # unchanged without the brief
    result = G.check(b, html, executive=built)
    assert not result.passed
    assert any("depth" in f for f in result.failures), result.failures


def test_an_executive_brief_inside_its_budget_still_passes():
    """The floor must refuse short briefs, not every brief."""
    built = {"sections": [], "words": L.EXEC_RICH_MIN + 10,
             "budget": {"min": L.EXEC_RICH_MIN, "max": L.EXEC_RICH_MAX},
             "within_budget": True}
    assert G.check(_rich(), rendered(_rich()),
                   executive=built).passed


# --- action layer -----------------------------------------------------------
def test_actions_carry_every_required_field():
    for action in L.build_actions(_rich()):
        d = action.as_dict()
        for field in ("intelligence", "recommended_action", "why",
                      "expected_result", "approval_required"):
            assert d[field], field
        assert d["prepared_only"] is True


def test_actions_never_imply_an_external_action_occurred():
    html = R.render_actions(L.build_actions(_rich()))
    assert L.check_execution_language(html) == []
    assert "Approval required" in html


@pytest.mark.parametrize("phrase", list(L.FORBIDDEN_EXECUTION_LANGUAGE))
def test_execution_language_is_detected(phrase):
    assert L.check_execution_language(f"Then {phrase} the investors.") == \
        [phrase]


def test_a_sparse_company_still_gets_an_actionable_artifact():
    kinds = {a.kind for a in L.build_actions(_sparse())}
    assert "evidence_requests" in kinds or "risk_register" in kinds


def test_no_more_actions_than_the_cap():
    assert len(L.build_actions(_rich())) <= L.MAX_ACTIONS + 1


# --- cross-layer consistency ------------------------------------------------
def test_all_layers_speak_from_the_same_insight():
    """They may differ in depth; they must not contradict."""
    brief = _rich()
    k = brief.key_insight
    dash = {m.key: m for m in L.build_dashboard(brief)}
    assert dash["decision_map"].what_changed == k.fact
    assert dash["decision_map"].so_what == k.so_what
    actions = L.build_actions(brief)
    assert any(k.decision in a.recommended_action for a in actions)


# --- regressions found by real browser measurement --------------------------
def test_the_sticky_section_nav_stays_one_scrollable_line():
    """FOUND AT 390px: the nav wrapped to 213px tall — a quarter of the
    viewport permanently covering content. It must scroll, not wrap."""
    html = R.render_story(L.build_story(_rich()), run_id="r1")
    assert "flex-wrap:nowrap" in html
    assert "overflow-x:auto" in html


def test_the_decision_section_survives_deduplication():
    """FOUND IN THE BROWSER: spending the decision on the primary brief's
    ledger deleted the one section the whole narrative builds toward.

    Orientation repetition is permitted; a missing mandated section is not.
    """
    brief = _rich()
    ledger = L.Ledger()
    ledger.spend(brief.key_insight.fact, brief.key_insight.so_what)
    keys = {s["key"] for s in L.build_story(brief, {}, ledger)}
    assert "decision" in keys


def test_story_sections_are_deep_linkable_and_focusable():
    html = R.render_story(L.build_story(_rich()), run_id="r1")
    for section in L.build_story(_rich()):
        assert f'id="{section["key"]}"' in html
    assert 'tabindex="-1"' in html      # focusable for keyboard deep links


# --- the readiness gate: the most serious defect found in this pass ---------
def test_a_withheld_report_never_produces_a_founder_insight():
    """FOUND BY test_the_brief_states_its_claim_once.

    `thesis.view` can be POPULATED with a templated sentence while the report
    asserts no conclusion (`result_state = EVIDENCE_LIMITED`, "no strategic
    conclusion is asserted"). Reading `view` alone revived a claim the report
    had withheld -- on the primary screen. The founder layers now inherit the
    same readiness state the strategic brief honours.
    """
    report = {"result_state": "EVIDENCE_LIMITED",
              "result_state_detail": "No reasoning backend is configured.",
              "thesis": {"view": "The company is shifting toward a platform.",
                         "tension": "x", "why_care": "whether to invest or not"},
              "hypotheses": [{"statement": "s", "reasoning": "r",
                              "supporting_observation_ids": ["ev-1"]}]}
    b = B.build(company="Acme", mode=B.PRIVATE_COMPANY, report=report,
                observations=[{"text": "t", "date": "2026-01-01",
                               "observation_id": "ev-1"}])
    assert b.key_insight is None, "a withheld reading was revived"
    assert b.withheld_reason


@pytest.mark.parametrize("state", sorted(B._WITHHELD_STATES))
def test_every_withheld_state_is_honoured(state):
    report = {"result_state": state,
              "thesis": {"view": "A confident sounding conclusion.",
                         "tension": "t", "why_care": "whether to x or y"}}
    assert B.build(company="X", mode=B.PRIVATE_COMPANY,
                   report=report).key_insight is None


def test_a_withheld_run_still_answers_why_it_matters():
    """A withheld reading used to render NOTHING, so the page looked like the
    analysis had failed. It did not fail -- it declined, and that is the
    headline."""
    report = {"result_state": "EVIDENCE_LIMITED",
              "result_state_detail": "No reasoning backend is configured, so "
                                     "no strategic conclusion is asserted.",
              "thesis": {"view": "v", "tension": "t", "why_care": "w"}}
    b = B.build(company="Acme", mode=B.PRIVATE_COMPANY, report=report,
                observations=[{"text": "t", "date": "2026-01-01"}])
    html = rendered(b)
    # The live surface declines in its own words -- it does not go blank, and
    # it says why, which is the point this test has always made.
    assert "cleared the evidence bar" in html
    assert "Why this matters" in html


def test_no_layer_is_orphaned():
    """NOTHING IS UNREACHABLE. That is what this test has always asserted.

    It used to assert it by requiring one page to link to all six others,
    which is precisely the eight-door grid §16 removed: a reader who has just
    read a conclusion was handed a sitemap. Reachability now comes from two
    places, and BOTH are checked here, so the guarantee is unchanged while
    the shape is not.

      * the secondary surfaces are linked from this page directly;
      * the six story steps form a chain from step 1, and this page links
        into step 1.
    """
    from intent_engine.founder_brief import flow

    html = rendered(_rich())
    # Every secondary surface, directly.
    for key in flow.SECONDARY:
        assert f"/{key}" in html, key
    # ...and the way back into the story.
    assert flow.STEPS[0].suffix in html

    # The chain itself: every step reachable from the one before it.
    reached = {flow.STEPS[0].key}
    step = flow.STEPS[0]
    while True:
        nav = flow.nav("r1", step.key)
        following = flow.following(step.key)
        if following is None:
            break
        assert f"/runs/r1{following.suffix}" in nav, following.key
        reached.add(following.key)
        step = following
    assert reached == {s.key for s in flow.STEPS}


def test_interface_controls_are_excluded_from_the_intelligence_budget():
    html = ('<main class="fb"><p>' + " ".join(["word"] * 250) + "</p>"
            '<section class="ui-controls"><p>'
            + " ".join(["control"] * 200) + "</p></section></main>")
    assert L.intelligence_words(html) == 250
    assert L.visible_words(html) == 450


# --- limited executive brief: depth without padding -------------------------
def test_a_withheld_run_gets_the_limited_brief_structure():
    """168 words of nothing became 380+ words of what WAS established.

    The fix is not filler: a withheld reading has a different and genuinely
    useful structure, built from evidence rather than from a conclusion that
    does not exist.
    """
    report = {"result_state": "EVIDENCE_LIMITED",
              "result_state_detail": "No strategic conclusion is asserted.",
              "observations": [
                  {"text": "Published a pricing page listing three tiers.",
                   "date": "2026-04-02", "source_class": "company_owned"},
                  {"text": "Trade press noted a partnership.",
                   "date": "2026-03-01",
                   "source_class": "independent_reporting"}],
              "evidence_gaps": ["No customer outcome has been published."],
              "questions": ["Who is the buyer?"]}
    b = B.build(company="Acme", mode=B.PRIVATE_COMPANY, report=report,
                observations=report["observations"])
    built = L.build_executive_brief(b, report, L.Ledger())
    keys = [s["key"] for s in built["sections"]]
    assert built.get("limited") is True
    for required in ("bottom_line", "verified", "why_limited",
                     "customer_view", "decision", "could_change"):
        assert required in keys, required
    # Depth, not word count alone: every section must carry real content
    # derived from the run rather than boilerplate.
    for section in built["sections"]:
        assert all(len(p.split()) >= 5 for p in section["paragraphs"])
    verified = [s for s in built["sections"] if s["key"] == "verified"][0]
    assert "pricing page" in " ".join(verified["paragraphs"]).lower()
    assert built["words"] >= 200, built["words"]


def test_the_limited_brief_never_infers_what_it_cannot_see():
    report = {"result_state": "EVIDENCE_LIMITED", "observations": []}
    b = B.build(company="Acme", mode=B.PRIVATE_COMPANY, report=report)
    text = " ".join(p for s in L.build_executive_brief(
        b, report, L.Ledger())["sections"] for p in s["paragraphs"]).lower()
    for invented in ("market share", "unit economics", "revenue grew",
                     "customers adopted", "the board", "investors believe"):
        assert invented not in text, invented


def test_the_limited_brief_states_what_would_change_it():
    report = {"result_state": "EVIDENCE_LIMITED", "observations": [],
              "evidence_gaps": ["No customer outcome has been published."]}
    b = B.build(company="Acme", mode=B.PRIVATE_COMPANY, report=report)
    built = L.build_executive_brief(b, report, L.Ledger())
    change = [s for s in built["sections"] if s["key"] == "could_change"]
    assert change and change[0]["paragraphs"]


# --- citations --------------------------------------------------------------
def test_the_primary_view_cites_what_the_reading_rests_on():
    html = rendered(_rich(), report=_cited_report())
    assert "/runs/r1/evidence/" in html
    assert "What supports this" in html


def test_citations_cost_nothing_a_reader_has_to_open():
    """INVERTED DELIBERATELY. The old screen put citations behind a
    <details> so they could not spend the reading budget. The scrollable
    narrative shows evidence -- and counter-evidence -- in the open, because
    contradiction a reader has to click for is contradiction they do not
    weigh. What still must not happen is a wall of raw identifiers.
    """
    html = rendered(_rich())
    main = html.split('<main class="nar">')[1]
    assert "<details" not in main, "evidence was collapsed again"
    assert not re.search(r">\s*obs-[0-9a-f]{6,}\s*<", main)
    assert L.visible_words(main) <= L.NARRATIVE_MAX


def test_no_citation_is_emitted_without_a_run_to_resolve_against():
    assert "/evidence/" not in rendered(_rich(), run_id="")


# --- extended release gate --------------------------------------------------
def test_the_gate_catches_a_revived_withheld_reading():
    b = _rich()
    b.withheld_reason = "No strategic conclusion is asserted."
    result = G.check(b, rendered(b))
    assert not result.passed
    assert any("withheld" in f for f in result.failures)


def test_the_gate_catches_a_failing_citation():
    b = _rich()
    result = G.check(b, rendered(b),
                     citations={"/runs/r1/evidence/obs-9": 404})
    assert not result.passed
    assert any("404" in f for f in result.failures)


def test_the_gate_catches_controls_placed_before_the_answer():
    html = ('<main class="fb"><section class="ui-controls">ask</section>'
            '<div>Why this matters</div><h1>x</h1></main>')
    result = G.check(_rich(), html)
    assert any("before the founder answer" in f for f in result.failures)


# --- market-export states: found by production-parity validation ------------
# These were written against the v1 consumer, which validated the export
# itself. That job moved: `market_intel_export.v2` is validated on the way OUT
# of the producer and refused on the way in by `market_producer.load_export`,
# so a malformed artefact never reaches a shape the layers can see. The v2
# suite pins that half -- see `test_an_export_violating_the_contract_is_not_
# shown_degraded` and `test_a_wrong_schema_version_is_refused_rather_than_
# best_efforted` in `tests/test_market_intel_contract.py`.
#
# What belongs HERE is the half those tests cannot reach: whatever made the
# market context unavailable, the dashboard has to survive it. That is the
# property the parity failure actually cost a founder -- the page went down,
# not just the tile.
@pytest.mark.parametrize("reason", [
    "the snapshot could not be read",
    "no market snapshot has been published for this company",
    "",
])
def test_an_unavailable_market_never_takes_the_dashboard_down(reason):
    """FOUND BY PARITY: a malformed `price_change` raised AttributeError and
    took the whole founder page down. "Fails closed" must mean the market
    module goes unavailable -- not that a bad upstream artefact can break a
    founder's result."""
    modules = L.build_dashboard(_rich(market=_absent_market_context(reason)))
    assert len(modules) >= 4
    html = R.render_dashboard(modules)
    assert "Not established" in html
    # "Unavailable" is an engineering status, not intelligence:
    # six live dashboards opened with a stack of them.
    assert "Unavailable" not in html
    assert ">0%<" not in html and ">$0<" not in html


def test_a_market_context_renders_only_the_modules_it_carries():
    """A module the export did not measure is omitted, never drawn empty: a
    chart axis with no line reads as "flat", which is a claim the data does
    not support."""
    context = _market_context()
    context["modules"].pop("market_risk", None)
    module = next(m for m in L.build_dashboard(_rich(market=context))
                  if m.key == "market_trajectory")
    assert module.available
    text = " ".join([module.what_changed, module.text_alternative]
                    + [str(r.get("value", "")) for r in module.rows]).lower()
    assert "volatility" not in text


# --- the withheld thesis must stay withheld in Q&A --------------------------
REVIVED = ("Yes — on balance the evidence supports that moving from selling "
           "a product toward operating the rails beneath it.")


def test_the_revived_thesis_check_can_actually_fire():
    """`qa.withheld` is set to `brief.key_insight is None` -- the same value
    the check compared it against -- so `withheld and not qa.withheld` was
    always False and this rule could never fail on ANY input.

    This is the gate half of the defence, tested against a hand-built answer
    so it keeps working even though `qa.answer` now refuses at source.
    """
    from intent_engine.founder_brief import consistency as CO
    from intent_engine.founder_brief import qa as fqa
    b = _sparse()
    assert b.key_insight is None
    a = fqa.FounderAnswer(question="What does this company do?",
                          direct_answer=REVIVED, withheld=True)
    result = CO.check(brief=b, qa=a)
    assert not result.passed
    assert any("revived" in f for f in result.failures), result.failures


def test_a_withheld_brief_refuses_the_engines_reading_at_source():
    """The engine answers from the strategic report, which still holds the
    hypothesis the brief declined to assert -- so an ordinary question was
    enough to carry it onto the page.

    A founder asking "what does this company do?" was shown "the evidence
    supports that moving from selling a product toward operating the rails
    beneath it", under a brief that had just said no conclusion was being
    asserted.
    """
    from intent_engine.founder_brief import consistency as CO
    from intent_engine.founder_brief import qa as fqa
    b = _sparse()
    a = fqa.answer("What does this company do?", b,
                   engine_answer=REVIVED, observations=[])
    assert REVIVED not in a.direct_answer
    assert CO.check(brief=b, qa=a).passed


def test_a_supported_brief_still_uses_the_engines_answer():
    """The guard must refuse revivals, not every engine answer."""
    from intent_engine.founder_brief import qa as fqa
    b = _rich()
    assert b.key_insight is not None
    a = fqa.answer("What does this company do?", b,
                   engine_answer=REVIVED, observations=[])
    assert "rails beneath it" in a.direct_answer


def test_the_refusal_itself_is_not_mistaken_for_a_revival():
    """The check must refuse revivals, not every answer on a withheld run."""
    from intent_engine.founder_brief import consistency as CO
    from intent_engine.founder_brief import qa as fqa
    b = _sparse()
    a = fqa.answer("What is the strategy here?", b, engine_answer="",
                   observations=[])
    assert CO.check(brief=b, qa=a).passed


def test_transition_claims_are_caught_in_the_engines_own_words():
    """The literal list missed the vocabulary the engine actually emits.

    Its own `thesis.view` reads "appears to be repositioning from selling
    software toward operating the payment rails" -- which contains neither
    "is repositioning" nor "is moving toward", so it passed a check written
    to stop exactly that sentence.
    """
    from intent_engine.founder_brief.consistency import _looks_strategic
    assert _looks_strategic("Shopify appears to be repositioning from selling "
                            "software toward operating the payment rails.")
    assert _looks_strategic("moving from selling a product toward operating "
                            "the rails beneath it")
    assert _looks_strategic("The company is shifting from self-serve to "
                            "enterprise.")
    # and the honest sentences stay honest
    assert not _looks_strategic("I am not going to give you a strategic read "
                                "on this company.")
    assert not _looks_strategic("The pricing page lists three tiers and was "
                                "updated in April.")
    assert not _looks_strategic("")


# --- rich executive-brief depth --------------------------------------------
def _rich_report():
    from intent_engine.strategic_intelligence.reasoning import (
        build_strategic_report,
    )
    from intent_engine.strategic_intelligence.shopify_fixture import (
        SHOPIFY_COMPANY, shopify_observations,
    )
    # THE BUSINESS MODEL IS PART OF THE REAL CALL. A tension fires on signal
    # names, and signal names are generic enough that a chip designer's
    # partner language matched a marketplace's -- so `tension_applies` fails
    # closed on an unread model. Production supplies it; a fixture that omits
    # it is exercising the refusal rather than the brief.
    return build_strategic_report(
        company_name=SHOPIFY_COMPANY, observations=shopify_observations(),
        business_model="SUBSCRIPTION_SOFTWARE").as_dict()


def _rich_pair():
    """A rich brief plus its executive brief, built the way the app builds
    them (ledger preloaded with the 60-second screen)."""
    report = _rich_report()
    obs = [o for o in report["observations"] if isinstance(o, dict)]
    independent = sum(1 for o in obs if o.get("source_class") not in
                      ("company_owned", "executive_statement", None, ""))
    brief = B.build(company="Shopify",
                    mode=B.classify_mode(is_public=True, evidence_count=len(obs),
                                         independent_sources=independent,
                                         has_thesis=True),
                    report=report, observations=obs, market=None)
    ledger = L.Ledger()
    k = brief.key_insight
    # Mirrors _executive_brief_page exactly, including `interpretation` --
    # which the 60-second screen renders and the ledger used to omit.
    ledger.spend(k.fact, k.interpretation, k.so_what, k.decision)
    for change in (brief.what_changed or ())[:2]:
        ledger.spend(change.get("what", ""))
    ledger.spend(brief.biggest_risk, brief.biggest_unknown)
    return brief, report, L.build_executive_brief(brief, report, ledger)


def test_an_evidence_rich_brief_reaches_its_depth_budget():
    """It measured 131 words against a 500-900 budget.

    The analysis was not missing -- the hypothesis's reasoning, the mental
    model of how the business makes money, named vulnerabilities and the
    second-order surprises were all in the report, and this layer read six
    fields with `_first_text`, which returns one string from one item.
    """
    _, _, built = _rich_pair()
    assert built["budget"] == {"min": L.EXEC_RICH_MIN, "max": L.EXEC_RICH_MAX}
    assert L.EXEC_RICH_MIN <= built["words"] <= L.EXEC_RICH_MAX, built["words"]
    assert built["within_budget"]


def test_the_rich_brief_covers_the_sections_a_founder_was_promised():
    _, _, built = _rich_pair()
    keys = {s["key"] for s in built["sections"]}
    for required in ("bottom_line", "changed", "why", "decision",
                     "business", "who", "wrong", "next"):
        assert required in keys, required


def test_no_rich_section_repeats_another():
    """Depth, not length: a floor invites reaching it by saying one thing
    three times, so the floor and this check have to travel together."""
    from intent_engine.founder_brief.consistency import _overlap
    _, _, built = _rich_pair()
    paragraphs = [(s["title"], p) for s in built["sections"]
                  for p in s["paragraphs"]]
    for i, (t1, p1) in enumerate(paragraphs):
        for t2, p2 in paragraphs[i + 1:]:
            assert _overlap(p1, p2) <= 0.6, f"{t1} vs {t2}"


def test_the_rich_brief_does_not_restate_the_sixty_second_screen():
    """Paragraph against paragraph, not against the page's whole vocabulary.

    Two paragraphs about one company share its nouns -- "checkout",
    "merchants", "rails" -- without either restating the other. What must not
    happen is an executive-brief paragraph that IS a primary-brief paragraph.
    """
    from intent_engine.founder_brief.consistency import _overlap
    brief, _, built = _rich_pair()
    primary = [re.sub(r"<[^>]+>", " ", p) for p in
               re.findall(r"<p[^>]*>(.*?)</p>",
                          rendered(brief), re.S)]
    for section in built["sections"]:
        for paragraph in section["paragraphs"]:
            for shown in primary:
                assert _overlap(paragraph, shown) <= 0.6, (
                    f"{section['title']}: {paragraph[:70]!r} restates "
                    f"{shown[:70]!r}")


def test_the_gate_refuses_a_rich_brief_padded_by_duplication():
    import copy
    brief, _, built = _rich_pair()
    html = rendered(brief)
    assert G.check(brief, html, executive=built).passed
    padded = copy.deepcopy(built)
    padded["sections"][-1]["paragraphs"] = [padded["sections"][0]["paragraphs"][0]]
    result = G.check(brief, html, executive=padded)
    assert not result.passed
    assert any("twice" in f for f in result.failures), result.failures


def test_a_rich_brief_never_leaks_internal_vocabulary():
    from intent_engine.founder_brief.contract import INTERNAL_VOCABULARY
    _, _, built = _rich_pair()
    body = " ".join(p for s in built["sections"]
                    for p in s["paragraphs"]).lower()
    assert not [t for t in INTERNAL_VOCABULARY if t in body]


def test_why_it_matters_is_not_provenance_metadata():
    """`why_now` reads "Recent public signal (2024-11-01, ...) keeps this
    timely" -- provenance wearing the clothes of a reason, and it was the
    entire section until the causal fields were wired in."""
    _, _, built = _rich_pair()
    why = [s for s in built["sections"] if s["key"] == "why"]
    assert why, "the rich brief dropped 'why it matters' entirely"
    text = " ".join(why[0]["paragraphs"]).lower()
    assert "keeps this timely" not in text
    assert "recent public signal" not in text


def test_the_brief_surfaces_the_historical_analog_it_already_computed():
    """UNSURFACED INTELLIGENCE. The reasoning engine computes a comparable
    pattern -- mechanism, named analogs with sources, and the conditions under
    which it does NOT apply -- and the executive brief never read it. It was
    reachable only from the full analysis, the page a founder opens last.
    """
    _, _, built = _rich_pair()
    section = [s for s in built["sections"] if s["key"] == "pattern"]
    assert section, "the comparable pattern never reaches the brief"
    text = " ".join(section[0]["paragraphs"])
    assert "known move" in text
    # the analogy must arrive with its falsifier, or it is only flattery
    assert "stops being the right comparison" in text


def test_a_clause_split_on_a_semicolon_stays_readable():
    """SEEN LIVE: "...real infrastructure ownership language alone is not
    proof..." -- two clauses fused because the separator was dropped."""
    joined = L._sentences_of(
        "Infrastructure framing can precede real ownership; language alone "
        "is not proof.")
    assert "ownership. Language" in joined


def test_a_report_with_no_pattern_simply_omits_the_section():
    built = L.build_executive_brief(_rich(), {}, L.Ledger())
    assert not [s for s in built["sections"] if s["key"] == "pattern"]


# --- empty states must teach, measured on six live companies ----------------
def test_no_dashboard_card_is_only_the_word_unavailable():
    """MEASURED: across six live companies the dashboards showed the bare word
    "Unavailable" eleven times. That is an engineering status -- it tells a
    founder the software failed, not what is knowable about the company."""
    html = R.render_dashboard(L.build_dashboard(_sparse()))
    assert "Unavailable" not in html
    assert "Not established" in html


def test_an_absent_card_still_says_why_it_matters_and_what_would_settle_it():
    for module in L.build_dashboard(_sparse()):
        if not module.available:
            assert module.so_what, module.key
            assert module.what_to_watch, module.key


def test_the_dashboard_never_prints_the_same_row_twice(tmp_path):
    """MEASURED: business momentum and the strategic timeline printed the same
    dated developments, and the market card repeated its own headline in its
    rows -- Shopify showed one price sentence three times on one screen."""
    modules = L.build_dashboard(_rich(market=_market_context()))
    seen = set()
    for module in modules:
        for row in module.rows:
            key = L.Ledger._key(str(row.get("value", "")))
            if key:
                assert key not in seen, row
                seen.add(key)


def test_an_available_card_keeps_its_interpretation_after_deduplication(
        tmp_path):
    """Deduplication may not buy a clean screen by emptying a card: the
    release gate fails a module shown without an interpretation."""
    modules = L.build_dashboard(_rich(market=_market_context()))
    for module in modules:
        if module.available:
            assert module.so_what, module.key
