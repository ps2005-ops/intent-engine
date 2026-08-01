"""Dashboard, decision story, executive brief and the action layer.

The properties under test are mostly REFUSALS: no fabricated series, no empty
section, no repeated sentence across layers, no language implying an external
action occurred.
"""
import re
import pytest

from intent_engine.founder_brief import build as B
from intent_engine.founder_brief import contract as C
from intent_engine.founder_brief import layers as L
from intent_engine.founder_brief import market as M
from intent_engine.founder_brief import render as R
from tests.test_founder_brief_v3 import _rich, _sparse, _export


# --- reading budget ---------------------------------------------------------
def test_the_primary_view_fits_the_reading_budget():
    """The ceiling is the real constraint -- a 60-second screen can be short.

    The floor is asserted against a REAL pipeline run in
    test_a_real_run_lands_inside_the_full_reading_budget, because this fixture
    is deliberately smaller than a live report and would fail a floor for the
    wrong reason.
    """
    main = R.render_brief(_rich(), run_id="r1").split('<main class="fb">')[1]
    assert L.visible_words(main) <= L.PRIMARY_MAX


def test_a_real_run_lands_inside_the_full_reading_budget(tmp_path):
    from tests.test_strategic_intelligence import _strategic_webapp_run
    app, c, rid = _strategic_webapp_run(tmp_path)
    _, _, body = c.request("GET", f"/runs/{rid}")
    words = L.visible_words(body.split('<main class="fb">')[1])
    assert L.PRIMARY_MIN <= words <= L.PRIMARY_MAX, words


def test_the_sparse_primary_view_also_fits():
    main = R.render_brief(_sparse(), run_id="r1").split('<main class="fb">')[1]
    assert L.visible_words(main) <= L.PRIMARY_MAX


def test_no_paragraph_exceeds_the_length_limit():
    html = R.render_brief(_rich(), run_id="r1")
    for para in re.findall(r"<p[^>]*>(.*?)</p>", html, re.S):
        text = re.sub(r"<[^>]+>", " ", para)
        assert len(text.split()) <= L.MAX_PARAGRAPH_WORDS, text[:80]


def test_primary_order_puts_the_decision_before_the_history():
    """A reader who stops after the decision must already have the action."""
    html = R.render_brief(_rich(), run_id="r1")
    order = [html.index(m) for m in
             ("The most important thing", "Why this matters",
              "Decision affected", "What I would do next", "What changed",
              "How confident is this")]
    assert order == sorted(order), order


def test_at_most_three_actions_render():
    b = _rich()
    b.next_actions = ("a one", "b two", "c three", "d four", "e five")
    html = R.render_brief(b, run_id="r1")
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
    ctx = M.consume(_export(), expected_ticker="ACME").as_dict()
    for m in L.build_dashboard(_rich(market=ctx)):
        if m.available:
            assert m.so_what, m.key
            assert m.what_changed, m.key
            assert m.text_alternative, m.key


def test_an_unavailable_module_states_why_and_renders_no_number():
    html = R.render_dashboard(L.build_dashboard(_rich()))
    assert "Unavailable" in html
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


def test_no_control_performance_reaches_the_dashboard():
    html = R.render_dashboard(L.build_dashboard(
        _rich(market=M.consume(_export(), expected_ticker="ACME").as_dict())))
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


def test_the_executive_brief_respects_its_word_budget():
    built = L.build_executive_brief(_rich(), {}, L.Ledger())
    assert built["within_budget"], built["words"]


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
