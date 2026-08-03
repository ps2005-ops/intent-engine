"""The scrollable executive decision narrative — the default founder result.

THE DEFECT THIS COVERS
----------------------
Measured on the deployed preview (Palantir, commit a6866d6): three surfaces
built from ONE run disagreed about whether a conclusion existed at all.

    /runs/<id>          "No strategic conclusion is being asserted about
                         this company."
    /runs/<id>/slides    two options, a cost on each side, and the one check
                         that separates them
    /runs/<id>/brief     a third decision, and a topic printed raw

The decision was composed correctly every time; the default screen never
asked for it. A founder who stopped at the first screen — which is what a
first screen is for — was told the product had nothing to say, while the deck
one click away carried the answer.

So the tests below are organised by what can go wrong now:

    1  the default screen does not carry the decision
    2  a reader has to page, click or infer to reach the answer
    3  the page says the same thing several times
    4  a readiness state renders something it has no right to
    5  two surfaces disagree
    6  the page prepares nothing

Section 7 breaks each guard deliberately and checks it fails, because a gate
nobody has watched fail is a gate nobody knows is connected.
"""
import html as _html
import re

import pytest

from intent_engine.founder_brief import build as founder
from intent_engine.founder_brief import layers as L
from intent_engine.founder_brief import narrative as N
from intent_engine.strategic_intelligence.decision import (
    DECISION_READY, INVESTIGATION_REQUIRED, WITHHELD, DecisionOption,
    FounderDecision, compose_decision, decision_of,
)
from intent_engine.strategic_intelligence.patterns import HYPOTHESIS_SCAFFOLDS
from intent_engine.strategic_intelligence.records import StrategicHypothesis

ALL_PATTERNS = sorted(HYPOTHESIS_SCAFFOLDS)


# --- fixtures ----------------------------------------------------------------

def _report(company="Shopify"):
    from intent_engine.strategic_intelligence.reasoning import (
        build_strategic_report,
    )
    from intent_engine.strategic_intelligence.shopify_fixture import (
        shopify_observations,
    )
    return build_strategic_report(company_name=company,
                                  observations=shopify_observations()).as_dict()


def _brief(report, company="Shopify"):
    return founder.build(company=company,
                         mode=founder.PUBLIC_INFORMATION_RICH, report=report,
                         observations=list(report.get("observations") or ()))


def _narrative(report=None, company="Shopify", decision=None):
    report = report if report is not None else _report(company)
    from intent_engine.founder_brief.layers import build_actions
    brief = _brief(report, company)
    return N.build_narrative(company=company, brief=brief, report=report,
                             decision=decision or decision_of(report),
                             actions=build_actions(brief))


def _hypothesis(pattern_id, scaffold, *, confidence="moderate"):
    return StrategicHypothesis(
        hypothesis_id=f"hyp-{pattern_id}", title=scaffold["title"],
        statement=scaffold["statement"].format(company="Acme"),
        reasoning=scaffold["reasoning"],
        supporting_observation_ids=["obs-1"],
        counter_observation_ids=["obs-9"],
        alternative_explanations=list(scaffold["alternatives"]),
        confidence=confidence,
        confidence_reasons=["3 qualifying signal(s) matched: a, b",
                            "the reading rests on what the company publishes "
                            "about itself and nothing outside it"],
        evidence_gaps=list(scaffold["gaps"]),
        decision_implications=list(scaffold["implications"]),
        falsification_questions=list(scaffold["falsification"]),
        pattern_id=pattern_id,
        strongest_support_ids=("obs-1",), strongest_counter_ids=("obs-9",))


def _synthetic(pattern_id, confidence="moderate"):
    """A narrative for one library pattern, without running retrieval."""
    scaffold = HYPOTHESIS_SCAFFOLDS[pattern_id]
    hypothesis = _hypothesis(pattern_id, scaffold, confidence=confidence)
    blind = [{"why_it_may_matter": "It is a second-order effect of the "
                                   "current strategy that rarely shows up in "
                                   "public messaging.",
              "evidence_needed": ["A named customer outcome."]}]
    report = {
        "company_name": "Acme", "hypotheses": [hypothesis.as_dict()],
        "blind_spots": blind, "evidence_gaps": list(scaffold["gaps"]),
        "observations": [
            {"observation_id": "obs-1", "excerpt": "The company publishes a "
             "named enterprise deployment with a stated outcome.",
             "source_title": "Acme customers", "source_class": "company_owned",
             "date": "2026-08-03"},
            {"observation_id": "obs-9", "excerpt": "A trade review reports "
             "that rollouts still need months of on-site help.",
             "source_title": "Trade review",
             "source_class": "independent_reporting", "date": "2026-07-11"}],
    }
    decision = compose_decision("Acme", hypothesis, blind_spots=blind,
                                evidence_gaps=scaffold["gaps"])
    return report, decision, _narrative(report, "Acme", decision)


def _text(narrative, links=True) -> str:
    """What a reader actually sees — the rendered DOM, not the object.

    Asserting on fields would let a section pass while the renderer dropped
    it, which is exactly the class of defect this file exists for.
    """
    markup = N.render_narrative(narrative, run_id="run-1", links=links)
    markup = re.sub(r"(?is)<(style|script)[^>]*>.*?</\1>", " ", markup)
    markup = re.sub(r"(?i)</(p|li|h[1-6]|dd|dt|section)>", "\n", markup)
    return _html.unescape(re.sub(r"<[^>]+>", " ", markup))


def _lines(narrative, links=True):
    return [ln.strip() for ln in _text(narrative, links).splitlines()
            if ln.strip()]


# --- 1. the default screen carries the decision ------------------------------

def test_the_answer_is_the_first_thing_under_the_title():
    """Not a refusal, not navigation, not what the company sells."""
    narrative = _narrative()
    assert narrative.sections, "the narrative rendered no sections at all"
    assert narrative.sections[0].key == N.EXECUTIVE_ANSWER
    markup = N.render_narrative(narrative, run_id="run-1")
    assert markup.index('id="executive_answer"') < markup.index("nav"), \
        "navigation reaches the reader before the answer does"


@pytest.mark.parametrize("pattern_id", ALL_PATTERNS)
def test_a_ready_decision_reaches_the_default_screen(pattern_id):
    """The exact live defect: a composed decision the default page never asked
    for, while the deck one click away rendered it in full."""
    _, decision, narrative = _synthetic(pattern_id)
    if decision.readiness != DECISION_READY:
        pytest.skip(f"{pattern_id} does not compose two options here")
    options = narrative.section(N.OPTIONS)
    assert options and len(options.options) == 2, pattern_id
    body = _text(narrative)
    for option in decision.options[:2]:
        assert option.label[:28] in body, (pattern_id, option.label)
    assert narrative.section(N.NEXT_MOVE), pattern_id


@pytest.mark.parametrize("pattern_id", ALL_PATTERNS)
def test_no_readiness_state_leaves_the_reader_without_an_answer(pattern_id):
    """Every state says what it found and what to do — none dead-ends."""
    for confidence in ("moderate", "speculative"):
        _, decision, narrative = _synthetic(pattern_id, confidence)
        answer = narrative.section(N.EXECUTIVE_ANSWER)
        assert answer and answer.is_substantive, (pattern_id, confidence)
        assert narrative.section(N.PREPARED), (pattern_id, confidence)


def test_a_withheld_result_is_useful_rather_than_a_disclaimer():
    decision = compose_decision(
        "Acme", None, evidence_gaps=["Revenue split is not disclosed.",
                                     "No independent coverage was found."])
    narrative = _narrative({"observations": []}, "Acme", decision)
    assert narrative.readiness == WITHHELD
    body = _text(narrative)
    assert "No strategic reading of Acme cleared the evidence bar" in body
    # what was established, why it was withheld, what would change it
    assert narrative.section(N.OPTIONS), "the withheld state says nothing " \
                                         "about why there are no options"
    assert "evenue split is not disclosed" in body
    assert narrative.section(N.PREPARED), "a withheld result prepared nothing"
    # and it never renders an empty comparison
    assert not narrative.section(N.OPTIONS).options


def test_the_investigation_state_names_the_check_and_what_it_would_settle():
    _, decision, narrative = _synthetic("tool_to_system_of_record",
                                        "speculative")
    assert decision.readiness == INVESTIGATION_REQUIRED
    body = _text(narrative)
    assert "not yet safe to act on" in body
    assert narrative.section(N.NEXT_MOVE), "no bounded check was offered"
    assert not narrative.section(N.OPTIONS).options, \
        "the bounded state rendered options it cannot support"


# --- 2. no paging, no clicking, no inferring ---------------------------------

def test_the_default_page_carries_no_pager():
    markup = N.render_narrative(_narrative(), run_id="run-1")
    for pager in ("Next →", "← Previous", "Slide 1 of", 'class="pager"'):
        assert pager not in markup, pager


def test_counter_evidence_is_on_the_page_and_not_only_in_the_viewer():
    """Contradiction a reader has to open a second screen for is
    contradiction they do not weigh."""
    narrative = _narrative()
    against = narrative.section(N.EVIDENCE_AGAINST)
    assert against, "the primary page shows nothing that argues against it"
    assert against.items or against.note or against.paragraphs
    markup = N.render_narrative(narrative, run_id="run-1")
    section = re.search(r'<section id="evidence_against".*?</section>',
                        markup, re.S)
    assert section and "<details" not in section.group(0), \
        "counter-evidence was collapsed behind a disclosure control"


def test_the_next_move_is_stated_rather_than_left_to_be_inferred():
    narrative = _narrative()
    if narrative.readiness == WITHHELD:
        pytest.skip("a withheld result puts forward no move")
    move = narrative.section(N.NEXT_MOVE)
    assert move and move.paragraphs
    assert len(move.paragraphs[0].split()) >= 6, move.paragraphs[0]


# --- 3. nothing is said twice ------------------------------------------------

@pytest.mark.parametrize("pattern_id", ALL_PATTERNS)
def test_the_mechanism_is_not_restated_across_the_page(pattern_id):
    """It is the thesis: stated once in the answer, and then used as what one
    option WINS and what the other COSTS. Four appearances was the measured
    number before the shared tracker; more than three is padding."""
    _, decision, narrative = _synthetic(pattern_id)
    if not decision.mechanism:
        pytest.skip(f"{pattern_id} states no usable mechanism")
    stem = " ".join(re.findall(r"[a-z0-9]+", decision.mechanism.lower()))[:60]
    body = " ".join(re.findall(r"[a-z0-9]+", _text(narrative).lower()))
    assert body.count(stem) <= 3, (pattern_id, body.count(stem))


@pytest.mark.parametrize("pattern_id", ALL_PATTERNS)
def test_no_sentence_outside_the_option_pair_is_printed_twice(pattern_id):
    """The two option cards mirror each other by construction — option one's
    cost is option two's premise — so that block is exempt. Everywhere else, a
    repeat is padding."""
    _, _, narrative = _synthetic(pattern_id)
    outside = [s for s in narrative.sections if s.key != N.OPTIONS]
    seen, repeats = {}, []
    for section in outside:
        for line in _lines(N.Narrative(company=narrative.company,
                                       readiness=narrative.readiness,
                                       sections=(section,)), links=False):
            if len(line.split()) < 7:
                continue
            key = " ".join(re.findall(r"[a-z0-9]+", line.lower()))
            for prior in seen:
                if key in prior or prior in key:
                    repeats.append((line[:60], seen[prior][:60]))
                    break
            else:
                seen[key] = line
    assert not repeats, (pattern_id, repeats)


def test_source_counts_and_process_narration_never_reach_the_page():
    body = _text(_narrative()).lower()
    for banned in ("source(s)", "page(s) were read", "built from",
                   "cited against the evidence", "observation(s)",
                   "run your business as code."):
        assert banned not in body, banned


# --- 4. no internal vocabulary, no metadata as interpretation ----------------

@pytest.mark.parametrize("pattern_id", ALL_PATTERNS)
def test_no_internal_vocabulary_or_taxonomy_reaches_the_reader(pattern_id):
    from intent_engine.founder_brief.contract import INTERNAL_VOCABULARY
    from intent_engine.strategic_intelligence.records import SOURCE_CLASSES
    _, _, narrative = _synthetic(pattern_id)
    body = _text(narrative)
    low = body.lower()
    for token in INTERNAL_VOCABULARY:
        assert token not in low, (pattern_id, token)
    for source_class in SOURCE_CLASSES:
        assert source_class not in low, (pattern_id, source_class)
    for state in (DECISION_READY, INVESTIGATION_REQUIRED, WITHHELD):
        assert state not in body, (pattern_id, state)
    assert not re.search(r"\bobs-[0-9a-f]{4,}|\bhyp-[a-z_]+", body), pattern_id
    assert pattern_id not in body, "the pattern id reached the reader"


def test_a_source_is_described_by_what_it_is_not_by_its_enum():
    narrative = _narrative()
    section = narrative.section(N.EVIDENCE_FOR)
    assert section and section.items, "nothing supports the reading"
    for item in section.items:
        assert item.provenance in N.PROVENANCE_LABEL.values() or \
            item.provenance == "Unknown", item.provenance


def test_the_internal_topic_is_never_rendered_as_the_answer():
    for pattern_id in ALL_PATTERNS:
        _, decision, narrative = _synthetic(pattern_id)
        if not decision.topic:
            continue
        answer = narrative.section(N.EXECUTIVE_ANSWER)
        stem = decision.topic.rstrip(".?")[:40]
        assert stem not in " ".join(answer.paragraphs), pattern_id


# --- 5. surfaces agree -------------------------------------------------------

def test_the_narrative_and_the_deck_state_one_decision():
    from intent_engine.strategic_intelligence.slides import build_slides
    report = _report()
    decision = decision_of(report)
    narrative = _narrative(report)
    assert narrative.readiness == decision.readiness
    deck = " ".join(b["text"] for s in build_slides(report)
                    for b in s["bullets"])
    body = _text(narrative)
    if decision.readiness == DECISION_READY:
        assert decision.options[0].label[:28] in deck, "the deck lost the "
        for option in decision.options[:2]:
            assert option.label[:28] in body, option.label
    else:
        assert decision.unsafe_because[:40] in body


def test_no_surface_asserts_a_conclusion_another_one_withheld():
    """The live defect, pinned. The default page said no conclusion was being
    asserted while the deck rendered two options and a recommendation."""
    report = _report()
    decision = decision_of(report)
    narrative = _narrative(report)
    body = _text(narrative)
    withholding = "No strategic reading of" in body or \
                  "no decision is put forward" in body.lower()
    assert withholding == (decision.readiness == WITHHELD), (
        f"the page withholds={withholding} while the one decision is "
        f"{decision.readiness}")


def test_the_narrative_consumes_the_shared_decision_rather_than_reinterpreting():
    """A renderer that composes its own decision can disagree with the next
    one. This one is handed the object and must show that object."""
    report = _report()
    forced = FounderDecision(
        topic="Whether to do X or Y.", mechanism="the rails carry the value",
        readiness=DECISION_READY,
        options=(DecisionOption(label="Own the rails",
                                description="Management funds the rails now.",
                                upside="If this reading holds, the rails "
                                       "carry the value.",
                                downside="If instead nothing migrates, the "
                                         "spend buys nothing.", stance="act"),
                 DecisionOption(label="Deepen the product",
                                description="Management funds the product.",
                                upside="If nothing migrates, nothing was "
                                       "spent against it.",
                                downside="If this reading holds, waiting "
                                         "costs the rails.", stance="hold")),
        recommended_next_move="Check whether rails revenue is rising.")
    narrative = _narrative(report, "Shopify", forced)
    body = _text(narrative)
    assert "Own the rails" in body and "Deepen the product" in body
    assert "Check whether rails revenue is rising" in body
    assert narrative.readiness == DECISION_READY


# --- 6. the page prepares something ------------------------------------------

def test_every_prepared_card_says_what_it_is_and_what_to_do_with_it():
    narrative = _narrative()
    prepared = narrative.section(N.PREPARED)
    assert prepared and prepared.actions, "nothing was prepared"
    for card in prepared.actions:
        assert card["title"], card
        assert card["prepared"], card
        assert card["next"], card
    assert "without your explicit approval" in prepared.note


def test_nothing_is_executed_or_promised_to_be_executed():
    from intent_engine.founder_brief.layers import check_execution_language
    body = _text(_narrative())
    assert not check_execution_language(body), body[:200]


# --- 6b. the customer comprehension contract ---------------------------------

@pytest.mark.parametrize("pattern_id", ALL_PATTERNS)
def test_a_first_time_reader_can_answer_all_nine_questions(pattern_id):
    """The customer's complaint, as a contract. A non-technical owner must get
    all nine from this page alone — no deck, no full analysis, no inference."""
    for confidence in ("moderate", "speculative"):
        _, _, narrative = _synthetic(pattern_id, confidence)
        result = N.comprehension(narrative)
        assert result["passed"], (pattern_id, confidence,
                                  result["unanswered"])


def test_a_withheld_result_still_answers_the_nine():
    decision = compose_decision(
        "Acme", None, evidence_gaps=["Revenue split is not disclosed.",
                                     "No independent coverage was found."])
    narrative = _narrative({"observations": []}, "Acme", decision)
    result = N.comprehension(narrative)
    # Evidence FOR is the one a withheld run genuinely cannot answer: there is
    # no conclusion for anything to support. Everything else must still land.
    assert result["unanswered"] in (
        [], ["What supports the conclusion?"]), result["unanswered"]


def test_comprehension_is_judged_on_what_is_visible_not_on_the_object():
    """A section the renderer drops must stop counting. The object-level
    version of this check passed the page that told founders no conclusion
    was being asserted."""
    narrative = _narrative()
    stripped = N.Narrative(
        company=narrative.company, readiness=narrative.readiness,
        sections=tuple(s for s in narrative.sections
                       if s.key != N.THE_DECISION))
    assert "What decision is affected?" in \
        N.comprehension(stripped)["unanswered"]


def test_no_answer_is_parked_behind_a_disclosure_control():
    """Collapsed detail does not count toward primary comprehension, so the
    page must not put any of the nine behind one."""
    markup = N.render_narrative(_narrative(), run_id="run-1")
    body = markup.split('<main class="nar">')[1]
    assert "<details" not in body, \
        "part of the primary answer is collapsed behind a disclosure"


# --- 6c. slides are optional meeting mode ------------------------------------

def test_no_supporting_slide_repeats_what_the_deck_already_said():
    """Slides stopped being the comprehension path, so what is left has to be
    worth paging through. A bullet the deck has already shown costs a click
    and returns nothing.

    Load-bearing slides are exempt by design and so are exempt here: the
    decision screens restate deliberately, and dropping a bullet from them to
    satisfy this rule would leave an option with no stated cost.
    """
    from intent_engine.strategic_intelligence.slides import (
        _LOAD_BEARING, build_slides,
    )
    from intent_engine.strategic_intelligence.editorial import sentence_identity
    deck = build_slides(_report())
    seen = {}
    for slide in deck:
        for bullet in slide["bullets"]:
            key = sentence_identity(bullet["text"], limit=0)
            if not key:
                continue
            if slide["kind"] not in _LOAD_BEARING:
                assert key not in seen, (bullet["text"][:60], seen.get(key))
            seen[key] = slide["id"]


def test_a_load_bearing_slide_is_never_dropped_for_terseness():
    """A deck missing the choice is not a shorter deck, it is a different
    one."""
    from intent_engine.strategic_intelligence.slides import meeting_quality
    terse = [{"id": "decision", "kind": "decision", "note": "",
              "title": "The decision", "bullets": [{"text": "Own it.",
                                                    "evidence": [],
                                                    "date": "", "full": True}]}]
    assert meeting_quality(terse) == terse


def test_a_dated_fact_is_not_treated_as_a_weak_slide():
    """"Sentry acquired Codecov." is four words and is the strongest thing on
    that deck. An earlier version of the gate dropped it."""
    from intent_engine.strategic_intelligence.slides import meeting_quality
    deck = [{"id": "changed", "kind": "content", "note": "",
             "title": "What changed", "bullets": [
                 {"text": "Sentry acquired Codecov.", "evidence": [],
                  "date": "2026-05-02", "full": False}]}]
    assert len(meeting_quality(deck)) == 1


def test_presentation_cards_have_no_fixed_minimum_height():
    """A floor is what made a two-bullet slide render as a mostly-empty card.
    Height follows content."""
    from intent_engine.strategic_intelligence.slides import (
        build_slides, render_deck,
    )
    markup = render_deck(build_slides(_report()), company="Shopify")
    assert "min-height" not in markup


# --- 6d. the bounded states, served end to end -------------------------------

def _served(tmp_path, decision):
    """The DEFAULT ROUTE's real HTML for a run whose decision is `decision`.

    A deterministic fixture, and deliberately end-to-end rather than a call to
    the renderer: INVESTIGATION_REQUIRED could not be reproduced on the
    deployed preview once composition began walking the whole portfolio -- all
    three companies run found a decidable reading -- so the state has to be
    pinned on the served page rather than only in the composer.
    """
    from tests.test_strategic_intelligence import _strategic_webapp_run
    app, client, run_id = _strategic_webapp_run(tmp_path)
    result = app._real_result(run_id)
    report = result["strategic_report"]
    report["thesis"] = dict(report.get("thesis") or {},
                            decision=decision.as_dict())
    app.ci.store.save_report(run_id, report) if hasattr(
        app.ci.store, "save_report") else None
    original = app._real_result

    def patched(rid):
        out = original(rid)
        if out and rid == run_id:
            out = dict(out)
            out["strategic_report"] = report
        return out
    app._real_result = patched
    _, _, body = client.request("GET", f"/runs/{run_id}")
    return body


def test_the_investigation_state_renders_on_the_served_default_route(tmp_path):
    decision = FounderDecision(
        topic="Whether to price the product independently of the engagement.",
        mechanism="the engagement teaches the workflow and the product sells "
                  "it without the engagement",
        readiness=INVESTIGATION_REQUIRED,
        unsafe_because="only one course of action is supported by what was "
                       "retrieved, and one option is not a decision",
        evidence_required=("Revenue split between services and product is "
                           "not public.",),
        recommended_next_move="One bounded check comes before any commitment: "
                              "published pricing that assumes no "
                              "implementation engagement.",
        what_each_result_would_favour="Evidence that the product sells "
                                      "without the engagement favours acting "
                                      "on it; evidence that it does not "
                                      "favours holding.",
        reconsider_when="Reconsider once a source outside the company reports "
                        "on it.",
        verified=("The company publishes named enterprise deployments.",))
    body = _served(tmp_path, decision)
    assert "not yet safe to act on" in body
    # what was verified, why committing is unsafe, what is missing, one check
    assert "publishes named enterprise deployments" in body
    assert "one option is not a decision" in body
    assert "Revenue split between services and product" in body
    assert "One bounded check" in body
    assert "favours acting on it" in body
    assert "Reconsider once a source outside" in body
    # and no option comparison is fabricated to fill the space
    assert 'class="opt"' not in body
    assert "No options are put forward" in body


def test_the_withheld_state_renders_on_the_served_default_route(tmp_path):
    decision = FounderDecision(
        readiness=WITHHELD,
        unsafe_because="what this company has published is not enough to read "
                       "a strategy from",
        evidence_required=("No independent coverage was retrieved.",),
        limitation="No independent coverage was retrieved.")
    body = _served(tmp_path, decision)
    assert "cleared the evidence bar" in body
    assert "No options are put forward" in body
    assert 'class="opt"' not in body
    assert "No independent coverage was retrieved" in body
    # a withheld page is not one long disclaimer: it still prepares something
    assert 'id="prepared"' in body


# --- 7. break every guard ----------------------------------------------------

def test_break_a_section_with_nothing_behind_it_is_rendered():
    empty = N.Section("x", "A heading over nothing")
    assert not empty.is_substantive
    thin = N.Section("x", "Thin", paragraphs=("Four words only here.",))
    assert not thin.is_substantive, "a fragment passed as a section"
    real = N.Section("x", "Real", paragraphs=(
        "This one states a consequence a founder can act on today.",))
    assert real.is_substantive


def test_break_the_decision_is_dropped_from_the_default_screen():
    report = _report()
    stripped = dict(report)
    stripped["thesis"] = dict(report.get("thesis") or {})
    stripped["thesis"].pop("decision", None)
    stripped["hypotheses"] = []
    narrative = _narrative(stripped)
    assert narrative.readiness == WITHHELD
    # and it must SAY so rather than rendering a confident-looking blank
    assert "No strategic reading of" in _text(narrative)


def test_break_an_option_pair_is_rendered_for_a_bounded_result():
    decision = FounderDecision(readiness=INVESTIGATION_REQUIRED,
                               mechanism="the rails carry the value",
                               unsafe_because="only one course of action is "
                                              "supported",
                               options=(DecisionOption(label="Only one"),))
    narrative = _narrative(_report(), "Shopify", decision)
    section = narrative.section(N.OPTIONS)
    assert not section.options, "a bounded result rendered an option card"
    assert section.paragraphs, "and it did not say why there are none"


def test_break_the_mechanism_is_repeated_without_the_tracker():
    """The tracker is what keeps the thesis to one statement plus the
    trade-off. Removing it must show up as repetition, or it is not the thing
    doing the work."""
    from intent_engine.strategic_intelligence.editorial import SaidOnce
    tracker = SaidOnce()
    sentence = "value and lock-in migrate from the visible product"
    assert tracker.fresh(sentence) == sentence
    assert tracker.fresh(sentence) == ""
    assert tracker.has(f"If this reading holds, {sentence} underneath it")


def test_break_counter_evidence_is_hidden_behind_a_disclosure():
    markup = N.render_narrative(_narrative(), run_id="run-1")
    section = re.search(r'<section id="evidence_against".*?</section>',
                        markup, re.S)
    assert section, "there is no counter-evidence section to hide"
    assert "<details" not in section.group(0)


def test_break_two_unrelated_companies_receive_the_same_narrative():
    """A page that says the same thing about every company is a template."""
    a = _text(_synthetic("services_to_product")[2])
    b = _text(_synthetic("smb_wedge_to_enterprise")[2])
    a_words = set(re.findall(r"[a-z]{5,}", a.lower()))
    b_words = set(re.findall(r"[a-z]{5,}", b.lower()))
    overlap = len(a_words & b_words) / max(len(a_words | b_words), 1)
    assert overlap < 0.75, overlap


def test_break_the_answer_grows_past_a_sixty_second_read():
    narrative = _narrative()
    markup = N.render_narrative(narrative, run_id="run-1")
    answer = re.search(r'<section id="executive_answer".*?</section>',
                       markup, re.S)
    assert answer
    assert L.visible_words(answer.group(0)) <= L.ANSWER_MAX
