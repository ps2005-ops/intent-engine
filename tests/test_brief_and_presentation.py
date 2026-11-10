"""The three layers: executive brief, presentation, full analysis.

The tester opened a result fifteen minutes before a meeting and met eleven
sections, four hypothesis cards, a source library and a technical appendix.
Everything needed to answer "what should I know before I walk in?" was in there
somewhere, which is not the same as being answerable.
"""
import re

import pytest

from intent_engine.strategic_intelligence.brief import (
    MAX_WORDS, MIN_WORDS, QUESTION_COUNT, SIGNAL_COUNT, brief_completeness,
    build_brief, fit_to_words,
)
from intent_engine.strategic_intelligence.slides import (
    MAX_BULLETS_PER_SLIDE, MAX_WORDS_PER_BULLET, MIN_MEANINGFUL_SLIDES,
    build_slides, deck_is_presentable, meaningful_slide_count, render_deck,
)


def _rich_report():
    """A report with real material in every section."""
    return {
        "company_name": "Brightlake",
        "thesis": {
            "view": "Brightlake appears to be moving from selling routing "
                    "software directly to distributors toward an indirect "
                    "reseller model.",
            "transition": "Direct sales motion giving way to channel "
                          "partnerships.",
            "why_care": "Whether to keep scaling the direct sales team "
                        "through Q4."},
        "hypotheses": [
            {"title": "Channel shift is underway", "confidence": "moderate",
             "statement": "Channel shift is underway",
             "strongest_support_ids": ["o1", "o2"]},
            {"title": "Pricing is being repackaged for partners",
             "confidence": "low", "statement": "Pricing repackaging",
             "strongest_support_ids": ["o3"]},
        ],
        "shifts": [{"title": "Signed first reseller agreement with Meridian "
                             "Logistics", "date": "2026-06-11",
                    "evidence": ["o4"], "source_class": "executive_statement"}],
        "surprises": [{"finding": "Direct-sales hiring continued after the "
                                  "reseller agreement",
                       "alternative_explanation": "Job posts lag strategy by "
                                                  "one to two quarters.",
                       "why_surprising": "The two motions compete for budget",
                       "decision_affected": "Q4 headcount",
                       "what_would_resolve": "A Q3 headcount disclosure",
                       "evidence_side_a": [], "evidence_side_b": []}],
        "opportunities": [{"statement": "Bundle RouteIQ with partner "
                                        "onboarding services",
                           "why_now": "Partners lack implementation capacity",
                           "asymmetry": "Low cost, high retention",
                           "downside": "Dilutes the product story",
                           "execution_difficulty": "moderate",
                           "decision_required": "Whether to fund services"}],
        "vulnerabilities": [{"exposed_layer": "Implementation services",
                             "mechanism": "Partners own the customer "
                                          "relationship after handover",
                             "why_increasing": "Channel mix rising",
                             "market_force": "channel economics",
                             "counterpoint": "Direct renewals still dominate",
                             "leading_indicator": "Partner-sourced renewals",
                             "decision_affected": "services investment"}],
        "blind_spots": [{"observed_tension": "Hiring direct sellers while "
                                             "signing resellers",
                         "why_it_may_matter": "The motions compete",
                         "counter_explanation": "Hiring lags strategy",
                         "decision_affected": "Q4 headcount"}],
        "questions": [
            {"question": "Which segment does the reseller motion target?",
             "why_it_matters": "It decides pricing", "decision_affected":
                 "Q4 pricing"},
            {"question": "What share of Q3 revenue was partner-sourced?",
             "why_it_matters": "It sizes the shift", "decision_affected":
                 "channel investment"},
            {"question": "Who owns renewal after partner handover?",
             "why_it_matters": "It decides retention ownership",
             "decision_affected": "services staffing"},
            {"question": "Which segment does the reseller motion target?",
             "why_it_matters": "duplicate", "decision_affected": "dup"},
        ],
        "observations": [
            {"observation_id": "o1", "excerpt": "Brightlake builds routing "
                                                "software for mid-market "
                                                "distributors.",
             "source_type": "homepage", "source_class": "company_owned",
             "date": "2026-05-02"},
            {"observation_id": "o2", "excerpt": "The RouteIQ platform plans "
                                                "multi-stop delivery routes.",
             "source_type": "product", "source_class": "company_owned",
             "date": ""},
            {"observation_id": "o3", "excerpt": "Northwind Freight cut "
                                                "planning time by 34%.",
             "source_type": "customers", "source_class": "customer_voice",
             "date": "2026-04-19"},
            {"observation_id": "o4", "excerpt": "Reseller agreement signed "
                                                "with Meridian Logistics.",
             "source_type": "blog", "source_class": "executive_statement",
             "date": "2026-06-11"},
        ],
        "timeline": [{"date": "2026-06-11", "event": "Meridian reseller "
                                                     "agreement announced",
                      "source_class": "executive_statement"}],
        "evidence_gaps": ["No pricing evidence for the partner tier"],
        "quality_findings": [{"message": "Only one independent source"}],
        "decision_implications": [{"decision": "Whether to fund partner "
                                               "onboarding services"}],
        "agenda": [], "underexamined_questions": [], "patterns": [],
        "mental_model": {}, "source_library": {}, "what_changed": [],
        "feed": [],
        "source_class_coverage": {"company_owned": 2, "customer_voice": 1,
                                  "executive_statement": 1},
    }


def _thin_report():
    return {"company_name": "Thinlake", "thesis": {"view": "Little is known."},
            "hypotheses": [], "shifts": [], "surprises": [],
            "opportunities": [], "vulnerabilities": [], "blind_spots": [],
            "questions": [], "observations": [], "timeline": [],
            "evidence_gaps": [], "quality_findings": [], "agenda": [],
            "underexamined_questions": [], "patterns": [], "mental_model": {},
            "source_library": {}, "what_changed": [], "feed": [],
            "decision_implications": [], "source_class_coverage": {}}


# --- the brief ---------------------------------------------------------------
def test_the_brief_has_exactly_the_promised_parts():
    brief = build_brief(_rich_report())
    c = brief_completeness(brief)
    assert c["complete"], c["missing"]
    assert len(brief.signals) == SIGNAL_COUNT
    assert len(brief.questions) == QUESTION_COUNT


def test_the_brief_stays_inside_its_word_budget():
    brief = build_brief(_rich_report())
    assert brief.word_count <= MAX_WORDS
    assert brief.within_budget


def test_a_long_report_is_trimmed_rather_than_allowed_to_sprawl():
    report = _rich_report()
    report["thesis"]["view"] = ("Brightlake is changing. " * 200).strip()
    report["thesis"]["why_care"] = ("The decision is hard. " * 200).strip()
    brief = build_brief(report)
    assert brief.word_count <= MAX_WORDS


def test_trimming_never_cuts_mid_clause():
    text = ("Revenue grew strongly. Churn in the SMB tier rose, although "
            "enterprise retention improved. A third sentence follows here.")
    trimmed = fit_to_words(text, 5)
    # either a whole sentence, or an explicitly marked cut — never a bare
    # fragment presented as complete
    assert trimmed.endswith(".") or trimmed.endswith("…")


def test_a_single_overlong_sentence_is_marked_when_cut():
    trimmed = fit_to_words("word " * 100, 10)
    assert trimmed.endswith("…")


def test_the_brief_never_drops_its_own_caveat_to_fit():
    report = _rich_report()
    report["thesis"]["view"] = ("Brightlake is changing direction. " * 200)
    brief = build_brief(report)
    assert brief.limitation, "a brief edited into confidence is worse than a " \
                             "long one"


def test_the_brief_always_carries_a_counterpoint():
    brief = build_brief(_rich_report())
    assert brief.counterpoint, "a brief with no counterpoint is advocacy"


def test_duplicate_questions_are_not_repeated_in_the_brief():
    brief = build_brief(_rich_report())
    assert len(set(brief.questions)) == len(brief.questions)


def test_a_thin_report_yields_an_honestly_incomplete_brief():
    c = brief_completeness(build_brief(_thin_report()))
    assert not c["complete"]
    assert "signals" in c["missing"]


# --- the presentation ---------------------------------------------------------
def test_a_rich_report_makes_a_presentable_deck():
    slides = build_slides(_rich_report())
    assert deck_is_presentable(slides)
    assert meaningful_slide_count(slides) >= MIN_MEANINGFUL_SLIDES


def test_no_slide_is_ever_empty():
    for slides in (build_slides(_rich_report()), build_slides(_thin_report())):
        for slide in slides:
            assert slide["bullets"], f"empty slide: {slide['id']}"


def test_a_thin_report_does_not_pretend_to_be_a_deck():
    slides = build_slides(_thin_report())
    assert not deck_is_presentable(slides)


def test_the_evidence_slide_cannot_carry_a_thin_deck_to_the_floor():
    """Otherwise a deck reaches five on disclaimers alone."""
    report = _thin_report()
    report["evidence_gaps"] = [f"Gap number {i}" for i in range(9)]
    report["source_class_coverage"] = {"company_owned": 1}
    slides = build_slides(report)
    assert not deck_is_presentable(slides)


def test_no_slide_becomes_a_wall_of_text():
    slides = build_slides(_rich_report())
    for slide in slides:
        assert len(slide["bullets"]) <= MAX_BULLETS_PER_SLIDE
        for bullet in slide["bullets"]:
            assert len(bullet["text"].split()) <= MAX_WORDS_PER_BULLET + 1


def test_slides_follow_the_narrative_order():
    """This fixture reports no concrete company development -- no acquisition,
    launch, funding or pricing change -- so it stays on the existing path,
    which is the rule that protects thin and adversarial companies. The
    founder deck's own order is asserted in test_one_presentation_contract,
    against a fixture that earns the takeover.
    """
    ids = [s["id"] for s in build_slides(_rich_report())]
    # The decision screens sit directly after the central view, because "so
    # what do I do about it" is the question a reader has the moment they have
    # the view -- not after four screens of supporting material. Which screens
    # appear depends on readiness: `decision` plus `option-*` and `next-*` when
    # the evidence supports two courses of action, `investigate-*` when it does
    # not, and none at all when no view was formed.
    # "<Company> in one minute" now sits AFTER the decision rather than
    # opening the deck. Measured live: it opened the Palantir presentation
    # with "At Palantir, we believe that with good data and the right
    # software, institutions can solve hard problems and change the world for
    # the better." -- the company's values statement, on the first screen
    # someone walks a room through. It is honest context and it is not the
    # answer, so the deck opens on the reading and the choice, and it follows.
    expected = ["view", "decision", "option-1-1", "option-1-2",
                "next-1", "investigate-1", "company", "changed", "market",
                "signals", "tension", "opportunity", "questions", "evidence"]
    assert ids == [i for i in expected if i in ids], ids
    if "company" in ids and "decision" in ids:
        assert ids.index("decision") < ids.index("company")


def test_the_decision_screens_follow_the_view_not_the_evidence():
    """The deck's answer to "what do I do" may not be buried behind context.

    Asserted separately from the order above so that adding a context screen
    later cannot quietly push the decision down the deck without a failure.
    """
    ids = [s["id"] for s in build_slides(_rich_report())]
    decisions = [i for i in ids if i.startswith(("decision", "option-",
                                                 "next-", "investigate-"))]
    assert decisions, ids
    assert ids.index(decisions[0]) <= ids.index("view") + 1, ids


def test_evidence_is_not_repeated_across_slides():
    slides = build_slides(_rich_report())
    seen = {}
    for slide in slides:
        for bullet in slide["bullets"]:
            for citation in bullet["evidence"]:
                seen[citation] = seen.get(citation, 0) + 1
    # a citation may legitimately support two different subjects, but the same
    # block must not be reprinted under every slide
    # A citation may legitimately support two different screens; reprinting
    # the same evidence block under nearly every screen is the padding this
    # guards against. An absolute bound, because the deck is now deliberately
    # short and a relative one tightens as it shortens.
    assert not any(count > 3 for count in seen.values()), seen


# --- the rendered deck ---------------------------------------------------------
def _deck_html():
    slides = build_slides(_rich_report())
    return render_deck(slides, company="Brightlake", as_of="2026-07-27",
                       analysis_version="1.5.0", run_id="run-1",
                       csrf="tok", full_analysis_url="/runs/run-1/full")


def test_the_deck_has_previous_and_next_on_every_slide():
    html = _deck_html()
    total = len(build_slides(_rich_report()))
    assert html.count('rel="prev"') == total
    assert html.count('rel="next"') == total


def test_the_deck_shows_progress():
    assert "Slide 1 of" in _deck_html()


def test_the_deck_works_without_javascript():
    """`:target` switching plus focusable links — the accessible baseline, not
    a fallback."""
    html = _deck_html()
    assert ".slide:target{display:block}" in html.replace("\n", "")
    # and the first slide is visible with no fragment at all
    assert ".slide:first-of-type{display:block}" in html.replace("\n", "")


def test_the_deck_degrades_rather_than_blanking_without_has_support():
    """The deck no longer depends on :has() at all — it was Safari 15.4+ and
    the only browser-version dependency in the product. What must survive is
    the degradation it was chosen for: with no script and no :has, the first
    slide stays visible rather than the deck rendering blank."""
    css = _deck_html().replace("\n", "")
    assert ":has(" not in re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    assert ".slide{display:none}" in css
    assert ".slide:first-of-type{display:block}" in css


def test_the_deck_supports_keyboard_navigation():
    html = _deck_html()
    assert "ArrowRight" in html and "ArrowLeft" in html
    assert "js-next" in html and "js-prev" in html


def test_the_deck_is_print_friendly():
    html = _deck_html()
    assert "@media print" in html
    assert ".deck .slide{display:block!important" in html.replace("\n", "")


def test_the_deck_is_responsive():
    assert "@media (max-width:600px)" in _deck_html()


def test_every_slide_offers_ask_about_this_slide():
    html = _deck_html()
    total = len(build_slides(_rich_report()))
    assert html.count("Ask about this slide") == total


def test_every_slide_is_dated_but_carries_no_build_version():
    """The date tells a reader how current the reading is. The build version
    answers a question no reader has, and was printed under every screen of a
    deck meant to be shown in a meeting."""
    html = render_deck(build_slides(_rich_report()), company="Acme",
                       as_of="2026-07-29",
                       analysis_version="9.9.9-internal-build")
    assert "2026-07-29" in html
    assert "9.9.9-internal-build" not in html
    assert "analysis version" not in html.lower()


def test_the_deck_links_to_the_full_analysis():
    assert "View full analysis" in _deck_html()


def test_citations_are_reachable_but_not_expanded():
    html = _deck_html()
    assert "Evidence behind this slide" in html
    # available, not shouted: no slide opens its citation drawer by default
    assert "<details class=\"cites\" open" not in html


def test_the_deck_exposes_no_internal_identifiers_as_prose():
    html = _deck_html()
    for internal in ("observation_id", "source_class", "hypothesis_id",
                     "READY_FOR", "EVIDENCE_"):
        assert internal not in html


# --- through the real web app -------------------------------------------------
def _webapp_run(tmp_path):
    from test_strategic_intelligence import _strategic_webapp_run
    return _strategic_webapp_run(tmp_path)


def test_the_guest_default_is_the_founder_brief_not_the_full_report(tmp_path):
    """ORIGINAL SAFEGUARD unchanged: the default must not be the full report.

    v3 pointed the default at the 60-second founder brief. v5 points it at
    STEP 1 of the six-step story, which is less to read again and is the
    first page of a narrative rather than a standalone summary -- so the
    default is now a redirect and the test follows it.

    THE ASSERTION THIS TEST HAS ALWAYS MADE IS UNCHANGED: whatever the guest
    lands on must not be the full analysis. That is still checked below, on
    the page they actually reach.
    """
    app, c, rid = _webapp_run(tmp_path)
    status, headers, _body = c.request("GET", f"/runs/{rid}")
    assert status == "303 See Other"
    assert headers["Location"] == f"/runs/{rid}/intro"
    status, _headers, body = c.request("GET", headers["Location"])
    assert status == "200 OK"
    # Step 1 answers "what is this company and what is the argument about",
    # which is what "Why this matters" was standing in for.
    assert "The strategic read" in body
    assert "What matters now" in body
    assert "Executive Overview" not in body
    assert "Evidence Library" not in body


def test_the_brief_page_reads_as_a_brief(tmp_path):
    app, c, rid = _webapp_run(tmp_path)
    status, _, body = c.request("GET", f"/runs/{rid}/brief")
    assert status == "200 OK"
    assert "Executive brief" in body
    # short enough to be a brief: the visible prose, not the markup
    # v3 layout marker: the executive brief is now rendered by the founder
    # renderer (<main class="fb">). The safeguard below -- a brief must not
    # become the report -- is unchanged and still the point of this test.
    # v4: the brief is the DECISION MEMO and renders <main class="dos">. It
    # is deliberately longer than the old 396-word page -- that page was
    # shallower than the 60-second summary above it -- but it must still stop
    # well short of the dossier, which is the point this test has always made.
    prose = re.sub(r"<[^>]+>", " ", body.split('<main class="dos">')[1])
    _, _, full = c.request("GET", f"/runs/{rid}/full")
    # `/full` renders the dossier as a <div>: that route already opens its own
    # <main>, and two main landmarks on one page is an accessibility defect.
    full_prose = re.sub(r"<[^>]+>", " ", full.split('<div class="dos">')[1])
    assert len(prose.split()) < len(full_prose.split()), \
        "the brief must not become the report"
    assert len(prose.split()) < 1200


def test_the_brief_states_its_claim_once(tmp_path):
    """OBSERVED LIVE on Sentry: the brief said "Sentry acquired Codecov." in
    the headline block and again, ten words below, under "The central view".

    `headline.view` IS the thesis's first sentence, so a one-sentence thesis
    was printed twice in a 250-500 word brief whose stated design rule is that
    nothing gets a second slot. This asserted the heading was PRESENT, which
    was the duplication rather than a defence against it."""
    app, c, rid = _webapp_run(tmp_path)
    _, _, body = c.request("GET", f"/runs/{rid}/brief")
    prose = re.sub(r"\s+", " ",
                   re.sub(r"<[^>]+>", " ",
                          body.split('<main class="dos">')[1]))
    # v4: the brief renders the SHARED decision, so the claim it must state
    # exactly once is that decision's headline -- not the legacy brief's own,
    # which was a second conclusion this page is no longer allowed to reach.
    from intent_engine.strategic_intelligence.decision import decision_of
    decision = decision_of(app._strategic_report_for(rid))
    claim = " ".join(decision.headline.split())
    assert claim, "no central claim to check"
    assert prose.count(claim) == 1, \
        f"the brief states its central claim {prose.count(claim)} times"


def test_the_central_view_survives_when_it_adds_something():
    """Suppression is for the DUPLICATE only. A thesis carrying more than its
    first sentence must still reach the reader -- dropping the whole section
    whenever a headline exists would lose real content."""
    from intent_engine.webapp.app import central_view_after_headline as after

    lead = "Sentry acquired Codecov."
    # nothing beyond the headline -> the section disappears
    assert after(lead, lead) == ""
    assert after("  Sentry acquired   Codecov. ", lead) == ""
    # a real second sentence survives, without its duplicated opener
    assert after(f"{lead} The buyer was the smaller of the two.", lead) == \
        "The buyer was the smaller of the two."
    # a thesis that does NOT open with the headline is left alone
    assert after("Something else entirely.", lead) == \
        "Something else entirely."
    # no headline shown -> the thesis is the only place the claim appears
    assert after(lead, "") == lead


def test_all_three_layers_are_reachable_from_each_other(tmp_path):
    """Each layer still serves, and each still offers a way onward.

    It used to be checked by requiring all three names on all three pages,
    which is the grid. Two of these three are STEPS now and carry the
    sequential nav; one is a secondary surface and carries the way back. Both
    shapes are checked, so a page that offered no exit at all still fails.
    """
    app, c, rid = _webapp_run(tmp_path)
    for path, expected in ((f"/runs/{rid}/brief", "Other views"),
                           (f"/runs/{rid}/slides", "Step 2 of 6"),
                           (f"/runs/{rid}/full", "Step 3 of 6")):
        status, _, body = c.request("GET", path)
        assert status == "200 OK", path
        assert expected in body, (path, expected)
        assert f"/runs/{rid}" in body, path


def test_the_presentation_renders_for_a_real_run(tmp_path):
    app, c, rid = _webapp_run(tmp_path)
    status, _, body = c.request("GET", f"/runs/{rid}/slides")
    assert status == "200 OK"
    assert "Slide 1 of" in body or "Not enough for a presentation" in body


def test_the_full_analysis_still_contains_everything(tmp_path):
    app, c, rid = _webapp_run(tmp_path)
    status, _, body = c.request("GET", f"/runs/{rid}/full")
    assert status == "200 OK"
    # "Everything" means the full argument and its provenance -- not the
    # legacy extraction view, which was a <details> of internal claim ids and
    # is gone. The Sources section is what a reader auditing the report needs.
    # The legacy report is gone: it restated the dossier that now leads this
    # page, so every sentence appeared twice. Its one unique element -- the
    # provenance list -- is the dossier's evidence appendix.
    assert "Technical appendix" not in body
    assert "Every source this rests on" in body
    assert 'id="evidence_appendix"' in body
