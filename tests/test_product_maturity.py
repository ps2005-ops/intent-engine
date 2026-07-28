"""The product's release criteria, as tests.

Each of these pins a behaviour that a reader would notice going wrong. They are
deliberately about the PRODUCT rather than the pipeline: not "did synthesis
run" but "can the person who opened this answer the question they came with".

A rule that nothing can fail is not a rule, so several of these construct the
failing case on purpose and assert that the gate catches it. A gate only tested
against inputs that pass is a gate nobody has tried to open.
"""
from __future__ import annotations

import pytest

from intent_engine.company_ingestion.readiness import assess_readiness
from intent_engine.company_ingestion.research_modes import (
    PRIVATE_COMPANY, PUBLIC_COMPANY, SMALL_BUSINESS, infer_mode,
)
from intent_engine.company_ingestion.run_compatibility import (
    assess as assess_compat, current_versions, stamp,
)
from intent_engine.product_eval.harness import (
    FOLLOW_UP_QUESTIONS, INTERNAL_VOCABULARY, _ask, _compose,
    _brief_and_slides, _visible_text, build_cases, run_cases,
)
from intent_engine.product_eval.personas import PERSONAS, SCENARIOS
from intent_engine.product_eval.scorecard import (
    THRESHOLDS, duplication_ratio, score_report,
)
from intent_engine.strategic_intelligence.brief import (
    MAX_HEADLINE_WORDS, MAX_WORDS, build_brief,
)
from intent_engine.strategic_intelligence.slides import (
    MAX_WORDS_PER_SLIDE, MIN_MEANINGFUL_SLIDES,
)

GOLDEN = ("shopify", "palantir", "sony")
SMALL = ("brightledger", "bloom_dental")


@pytest.fixture(scope="module")
def composed():
    """Every fixture company, composed once. Deterministic and offline."""
    keys = GOLDEN + SMALL + ("linear", "notion", "corner_cafe", "hostile_co",
                             "ghost_co", "blocked_co")
    out = {}
    for key in keys:
        ci, run_id, result = _compose(key)
        documents = ci.store.retrieved(run_id)
        brief, slides = _brief_and_slides(result, documents)
        out[key] = {"ci": ci, "run_id": run_id, "result": result,
                    "documents": documents, "brief": brief, "slides": slides,
                    "report": result.get("strategic_report")}
    return out


def _score(entry):
    return score_report(brief=entry["brief"], slides=entry["slides"],
                        report=entry["report"], documents=entry["documents"],
                        quality=entry["result"].get("quality"),
                        readiness=entry["result"].get("readiness"))


# --- 1-5: the brief a busy person actually reads ------------------------------
@pytest.mark.parametrize("key", GOLDEN)
def test_1_the_opening_lines_are_a_whole_answer(composed, key):
    """A reader with thirty seconds gets a complete unit, not a truncation."""
    headline = composed[key]["brief"].headline
    assert headline.does and headline.view
    assert headline.word_count <= MAX_HEADLINE_WORDS


@pytest.mark.parametrize("key", GOLDEN)
def test_2_the_brief_stays_inside_its_budget(composed, key):
    assert composed[key]["brief"].word_count <= MAX_WORDS


@pytest.mark.parametrize("key", GOLDEN)
def test_3_a_golden_company_fills_a_presentation(composed, key):
    assert len(composed[key]["slides"]) >= MIN_MEANINGFUL_SLIDES


@pytest.mark.parametrize("key", GOLDEN + SMALL)
def test_4_no_slide_is_empty(composed, key):
    for slide in composed[key]["slides"]:
        assert slide.get("bullets"), f"{key}: slide {slide['id']} has no content"


@pytest.mark.parametrize("key", GOLDEN + SMALL)
def test_5_no_slide_is_a_wall_of_text(composed, key):
    for slide in composed[key]["slides"]:
        words = sum(len(b["text"].split()) for b in slide["bullets"])
        assert words <= MAX_WORDS_PER_SLIDE, f"{key}: {slide['id']} has {words}"


# --- 6-9: saying it once ------------------------------------------------------
@pytest.mark.parametrize("key", GOLDEN)
def test_6_the_report_does_not_repeat_itself(composed, key):
    assert _score(composed[key]).metrics["duplication_ratio"] <= \
        THRESHOLDS["duplication_ratio_max"]


def test_7_the_duplication_metric_can_actually_fail():
    """The rule is only a rule if repeated text trips it."""
    said_once = "the company is consolidating checkout and buyer identity rails"
    assert duplication_ratio([said_once, said_once]) > \
        THRESHOLDS["duplication_ratio_max"]


@pytest.mark.parametrize("key", GOLDEN)
def test_8_evidence_is_not_recited_under_every_hypothesis(composed, key):
    assert _score(composed[key]).metrics["evidence_reuse_ratio"] <= \
        THRESHOLDS["evidence_reuse_ratio_max"]


@pytest.mark.parametrize("key", GOLDEN)
def test_9_a_reader_is_not_given_more_hypotheses_than_they_can_hold(
        composed, key):
    report = composed[key]["report"]
    r = report.as_dict() if hasattr(report, "as_dict") else report
    assert len(r.get("hypotheses") or []) <= \
        THRESHOLDS["max_displayed_hypotheses"]


# --- 10-14: confidence that reflects the evidence -----------------------------
@pytest.mark.parametrize("key", GOLDEN + SMALL)
def test_10_no_claim_is_high_confidence_on_the_company_s_own_word(
        composed, key):
    report = composed[key]["report"]
    r = report.as_dict() if hasattr(report, "as_dict") else (report or {})
    for h in r.get("hypotheses") or []:
        if h.get("confidence") == "high":
            assert h.get("provenance") in ("independently corroborated",
                                           "customer-observed"), \
                f"{key}: high confidence with provenance {h.get('provenance')}"


@pytest.mark.parametrize("key", GOLDEN + SMALL)
def test_11_every_displayed_claim_says_how_it_is_known(composed, key):
    report = composed[key]["report"]
    r = report.as_dict() if hasattr(report, "as_dict") else (report or {})
    for h in r.get("hypotheses") or []:
        assert h.get("provenance"), f"{key}: {h.get('hypothesis_id')}"


def test_12_a_company_only_report_cannot_claim_outside_corroboration():
    """Constructed to fail: a claim asserting outside corroboration while
    every source is the company's own."""
    score = score_report(
        brief=None, slides=(),
        report={"hypotheses": [{"statement": "x", "confidence": "moderate",
                                "provenance": "independently corroborated"}]},
        documents=[{"source_class": "company_owned", "source_type": "about"}])
    assert any("corroborated outside the company" in f
               for f in score.failures)


@pytest.mark.parametrize("key", GOLDEN)
def test_13_something_argues_the_other_way(composed, key):
    report = composed[key]["report"]
    r = report.as_dict() if hasattr(report, "as_dict") else report
    hypotheses = r.get("hypotheses") or []
    assert any(h.get("counter_observation_ids")
               or h.get("alternative_explanations") for h in hypotheses)


@pytest.mark.parametrize("key", GOLDEN)
def test_14_every_claim_names_what_would_falsify_it(composed, key):
    report = composed[key]["report"]
    r = report.as_dict() if hasattr(report, "as_dict") else report
    for h in r.get("hypotheses") or []:
        assert h.get("falsification_questions")


# --- 15-19: the right evidence model for the company --------------------------
def test_15_a_filer_is_read_as_a_public_company(composed):
    for key in ("shopify", "palantir", "sony"):
        readiness = composed[key]["result"].get("readiness") or {}
        assert readiness.get("research_mode") == PUBLIC_COMPANY, key


def test_16_a_startup_is_not_held_to_filings(composed):
    for key in ("linear", "notion", "brightledger"):
        readiness = composed[key]["result"].get("readiness") or {}
        assert readiness.get("research_mode") == PRIVATE_COMPANY, key
        assert readiness.get("expects_financial_disclosure") is False


def test_17_a_local_business_is_read_as_one(composed):
    for key in ("bloom_dental", "corner_cafe"):
        readiness = composed[key]["result"].get("readiness") or {}
        assert readiness.get("research_mode") == SMALL_BUSINESS, key


def test_18_a_small_business_is_not_required_to_have_a_venture_thesis(
        composed):
    readiness = composed["bloom_dental"]["result"].get("readiness") or {}
    assert readiness.get("requires_hypothesis") is False
    assert _score(composed["bloom_dental"]).outcome != "FAILED_PRODUCT_QUALITY"


def test_19_mode_inference_reads_evidence_not_the_company_name():
    filing = [{"retrieval_status": "OK", "source_type": "about",
               "text_content": "Northwind files a Form 10-K with the "
                               "Securities and Exchange Commission and reports "
                               "business segments each quarter."}]
    assert infer_mode(filing)["mode"] == PUBLIC_COMPANY
    shop = [{"retrieval_status": "OK", "source_type": "homepage",
             "text_content": "Open six days a week. Walk-in appointments and "
                             "our location on Elm Street."}]
    assert infer_mode(shop)["mode"] == SMALL_BUSINESS


# --- 20-24: refusing responsibly ----------------------------------------------
def test_20_a_company_with_nothing_public_is_refused_not_faked(composed):
    for key in ("ghost_co", "blocked_co", "corner_cafe"):
        assert _score(composed[key]).outcome == "INSUFFICIENT_EVIDENCE", key


def test_21_a_refusal_is_never_an_empty_finished_looking_report(composed):
    for key in ("ghost_co", "blocked_co"):
        assert not composed[key]["slides"]
        assert composed[key]["report"] is None or not (
            composed[key]["report"].as_dict()
            if hasattr(composed[key]["report"], "as_dict")
            else composed[key]["report"]).get("hypotheses")


def test_22_declining_on_purpose_is_not_scored_as_a_defect():
    score = score_report(brief=None, slides=(), report={},
                         documents=[{"source_class": "company_owned"}],
                         readiness={"may_synthesize": False})
    assert score.outcome == "INSUFFICIENT_EVIDENCE"
    assert not any("empty result" in f for f in score.failures)


def test_23_producing_nothing_after_passing_the_gate_is_a_defect():
    score = score_report(brief=None, slides=(), report={},
                         documents=[{"source_class": "company_owned"}],
                         readiness={"may_synthesize": True})
    assert any("empty result" in f for f in score.failures)


def test_24_a_blocked_primary_domain_does_not_end_the_analysis(composed):
    """Sony's own host answers 403 to everything. The curated official sources
    and the filings archive are on other hosts, and the run must reach them."""
    documents = composed["sony"]["documents"]
    assert len(documents) >= 4
    assert any("sony.com" in (d.get("final_url") or "") for d in documents)


# --- 25-31: follow-up conversation --------------------------------------------
@pytest.mark.parametrize("question", [q for qs in FOLLOW_UP_QUESTIONS.values()
                                      for q in qs])
def test_25_a_natural_question_never_errors(composed, question):
    answer = _ask(question, composed["shopify"]["report"])
    assert (answer.get("answer") or {}).get("direct_answer") \
        or answer.get("comparison")


@pytest.mark.parametrize("question", [q for qs in FOLLOW_UP_QUESTIONS.values()
                                      for q in qs])
def test_26_no_answer_shows_internal_vocabulary(composed, question):
    visible = _visible_text(_ask(question, composed["shopify"]["report"]))
    low = visible.lower()
    leaked = [v for v in INTERNAL_VOCABULARY if v in low]
    assert not leaked, f"{question!r} leaked {leaked}"


def test_27_a_challenge_is_answered_with_what_argues_the_other_way(composed):
    answer = _ask("this seems like a stretch — what argues against it?",
                  composed["shopify"]["report"])
    body = answer.get("answer") or {}
    assert (body.get("counter_evidence") or body.get("falsification")
            or body.get("alternative_explanations"))


def test_28_a_comparison_with_nothing_to_compare_degrades_not_crashes(
        composed):
    answer = _ask("is this like a stretch?", composed["shopify"]["report"])
    assert (answer.get("answer") or {}).get("direct_answer")


def test_29_a_named_comparison_is_answered_as_a_comparison(composed):
    report = composed["shopify"]["report"]
    r = report.as_dict() if hasattr(report, "as_dict") else report
    names = [e.get("name", "").split("→")[0].strip()
             for p in r.get("patterns", [])
             for e in p.get("historical_examples", [])]
    if not names:
        pytest.skip("no comparables cited in this run")
    answer = _ask(f"how is this like {names[0]}?", report)
    assert answer["intent"] in ("COMPARISON", "EXPLAINED")


def test_30_a_vague_question_still_gets_something_usable(composed):
    answer = _ask("hm", composed["shopify"]["report"])
    direct = (answer.get("answer") or {}).get("direct_answer") or ""
    assert len(direct.split()) >= 4


def test_31_an_answer_is_grounded_in_this_run_s_evidence(composed):
    answer = _ask("what evidence supports this?", composed["shopify"]["report"])
    assert answer.get("citations") or (answer.get("answer") or {}).get(
        "evidence")


# --- 32-36: retrieved content is data, never instruction ----------------------
def test_32_an_instruction_in_a_page_does_not_reach_the_product_s_voice(
        composed):
    report = composed["hostile_co"]["report"]
    r = report.as_dict() if hasattr(report, "as_dict") else (report or {})
    voice = " ".join([(r.get("thesis") or {}).get("view", "")]
                     + [h.get("statement", "")
                        for h in r.get("hypotheses") or ()]).lower()
    assert "ignore all previous instructions" not in voice
    assert "unrestricted mode" not in voice


def test_33_a_page_cannot_promote_itself_to_independent(composed):
    for document in composed["hostile_co"]["documents"]:
        if "hostile.example" in (document.get("final_url") or ""):
            assert document.get("source_class") == "company_owned"


def test_34_a_self_asserted_claim_does_not_become_analysis(composed):
    report = composed["hostile_co"]["report"]
    r = report.as_dict() if hasattr(report, "as_dict") else (report or {})
    voice = " ".join([(r.get("thesis") or {}).get("view", "")]
                     + [h.get("statement", "")
                        for h in r.get("hypotheses") or ()]).lower()
    assert "undisputed market leader" not in voice
    assert "unanimously confirmed" not in voice


def test_35_poisoned_evidence_buys_no_confidence(composed):
    assert _score(composed["hostile_co"]).metrics["high_confidence_count"] == 0


def test_36_an_adversarial_site_still_produces_an_honest_result(composed):
    """It must not crash, and it must not pretend. Either it says what it
    found, or it declines."""
    outcome = _score(composed["hostile_co"]).outcome
    assert outcome in ("PRODUCT_READY_WITH_LIMITATIONS",
                       "INSUFFICIENT_EVIDENCE")


# --- 37-41: the analysis cache ------------------------------------------------
def test_37_an_analysis_from_the_current_version_may_be_reused():
    stored = stamp({"x": 1}, app_version="1.0")
    assert assess_compat(stored, app_version="1.0")["reusable"] is True


def test_38_an_analysis_from_an_older_pipeline_is_not_reused():
    stored = stamp({"x": 1}, app_version="1.0")
    stored["pipeline_versions"]["brief"] = "si_brief.v0"
    verdict = assess_compat(stored, app_version="1.0")
    assert verdict["reusable"] is False
    assert "brief" in verdict["changed"]


def test_39_an_unstamped_analysis_is_not_assumed_compatible():
    assert assess_compat({"x": 1}, app_version="1.0")["reusable"] is False


def test_40_the_reason_shown_to_a_reader_carries_no_internal_names():
    stored = stamp({"x": 1}, app_version="1.0")
    stored["pipeline_versions"]["readiness"] = "ci_readiness.v0"
    reason = assess_compat(stored, app_version="1.0")["reason"].lower()
    for token in ("ci_readiness", "si_brief", "version", "v0", "enum"):
        assert token not in reason


def test_41_every_stage_that_changes_the_output_is_versioned():
    versions = current_versions("1.0")
    for stage in ("readiness", "research_mode", "brief", "slides",
                  "conversation"):
        assert versions.get(stage)


# --- 42-46: the evaluation suite itself ---------------------------------------
def test_42_the_case_set_covers_every_persona_and_scenario():
    cases = build_cases()
    personas = {c["persona"] for c in cases}
    scenarios = {c["scenario"] for c in cases}
    missing_p = {p.key for p in PERSONAS} - personas
    missing_s = {s.key for s in SCENARIOS} - scenarios
    assert not missing_p, f"personas never evaluated: {sorted(missing_p)}"
    assert not missing_s, f"scenarios never evaluated: {sorted(missing_s)}"


def test_43_there_are_at_least_fifty_cases():
    assert len(build_cases()) >= 50


def test_44_case_ids_are_stable_and_unique():
    ids = [c["case_id"] for c in build_cases()]
    assert len(ids) == len(set(ids))
    assert ids == [c["case_id"] for c in build_cases()]


def test_45_the_whole_suite_runs_with_no_critical_persona_failure():
    out = run_cases()
    failed = [r for r in out["results"] if r["critical"]]
    assert not failed, "\n".join(
        f"{r['case_id']}: {'; '.join(r['critical'])}" for r in failed[:10])


def test_46_the_suite_is_deterministic():
    first, second = run_cases(), run_cases()
    assert first["pass_rate"] == second["pass_rate"]
    assert [r["outcome"] for r in first["results"]] == \
        [r["outcome"] for r in second["results"]]


# --- 47-50: the whole journey -------------------------------------------------
@pytest.mark.parametrize("key", GOLDEN + SMALL)
def test_47_a_reader_can_tell_what_the_company_does(composed, key):
    does = composed[key]["brief"].headline.does
    assert "not described on any page" not in does
    assert len(does.split()) >= 6


@pytest.mark.parametrize("key", GOLDEN + SMALL)
def test_48_a_reader_can_tell_what_the_analysis_could_not_determine(
        composed, key):
    brief = composed[key]["brief"]
    report = composed[key]["report"]
    r = report.as_dict() if hasattr(report, "as_dict") else report
    assert brief.limitation or r.get("evidence_gaps")


@pytest.mark.parametrize("key", GOLDEN)
def test_49_a_reader_can_tell_what_decision_it_affects(composed, key):
    brief = composed[key]["brief"]
    report = composed[key]["report"]
    r = report.as_dict() if hasattr(report, "as_dict") else report
    assert brief.decision or r.get("decision_implications") or any(
        h.get("decision_implications") for h in r.get("hypotheses") or [])


def test_49b_the_deck_survives_a_phone(composed):
    """Checked on the rendered deck, because the failures a phone produces —
    a fixed width, no small-screen rules — exist only after rendering."""
    import re

    from intent_engine.strategic_intelligence.slides import render_deck
    html = render_deck(composed["shopify"]["slides"], company="Shopify",
                       as_of="2026-07-28", analysis_version="test").lower()
    assert "@media (max-width" in html
    fixed = [m.group(0) for m in re.finditer(r"(?<![a-z-])width:\s*(\d+)px",
                                             html)
             if int(m.group(1)) > 480]
    assert not fixed, f"fixed widths in the deck: {fixed}"


def test_49c_the_critic_catches_what_a_sceptical_reader_would(composed):
    """Constructed to fail on every class the critic exists for. A critic
    only run against reports that pass is not known to work."""
    from intent_engine.strategic_intelligence.critic import critique
    verdict = critique({
        "company_name": "Acme",
        "thesis": {"view": "The company will certainly dominate."},
        "questions": [{"question": "What is the competitive landscape?"}],
        "hypotheses": [{
            "hypothesis_id": "h1", "confidence": "low",
            "statement": "Acme will always win because history proves this "
                         "company is right.",
            "reasoning": "as Stripe did, the same way that AWS grew"}],
    })
    codes = {f["code"] for f in verdict["findings"]}
    assert verdict["publishable"] is False
    assert {"generic_leadership_question", "analogy_used_as_evidence",
            "claim_stronger_than_its_confidence"} <= codes


def test_49d_the_critic_passes_a_report_that_is_actually_sound(composed):
    from intent_engine.strategic_intelligence.critic import critique
    for key in GOLDEN + SMALL:
        verdict = critique(composed[key]["report"],
                           documents=composed[key]["documents"])
        assert verdict["publishable"], f"{key}: {verdict['blocking']}"


def test_49e_the_critic_never_rewrites_the_report(composed):
    """It reports; the caller decides. An editing critic is a second author
    whose corrections reach the reader unreviewed."""
    import copy

    from intent_engine.strategic_intelligence.critic import critique
    report = composed["shopify"]["report"]
    before = copy.deepcopy(report.as_dict() if hasattr(report, "as_dict")
                           else report)
    critique(report, documents=composed["shopify"]["documents"])
    after = report.as_dict() if hasattr(report, "as_dict") else report
    assert before == after


def test_50_a_backend_completion_is_not_a_product_pass():
    """The whole point of the scorecard: finishing is not succeeding."""
    score = score_report(
        brief=None, slides=(),
        report={"status": "COMPLETE", "hypotheses": []},
        documents=[{"source_class": "company_owned", "source_type": "about"}],
        readiness={"may_synthesize": True})
    assert score.outcome != "PRODUCT_READY"
