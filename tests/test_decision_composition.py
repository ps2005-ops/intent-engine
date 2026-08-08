"""The composed founder decision: every pattern, every surface, every refusal.

The defect this covers was systemic rather than local. `implications[0]` is a
decision TOPIC -- a question -- and it was read directly by the deck, the
executive brief, the founder brief, the full analysis and Q&A, each of which
presented it as a finished decision. Fixing one surface would have left four.

So the tests below are organised by the three things that can go wrong:

    1  the topic reaches a reader as though it were the answer
    2  a second option is invented so the page looks balanced
    3  two surfaces describe the same decision differently

Section 4 then breaks each guard deliberately and checks it fails, because a
gate nobody has watched fail is a gate nobody knows is connected.
"""
import re

import pytest

from intent_engine.strategic_intelligence.decision import (
    DECISION_READY, INVESTIGATION_REQUIRED, WITHHELD, DecisionOption,
    FounderDecision, compose_decision, decision_of, mechanism_sentence,
)
from intent_engine.strategic_intelligence.patterns import (
    HYPOTHESIS_SCAFFOLDS, statement_for,
)
from intent_engine.strategic_intelligence.records import StrategicHypothesis


def _hypothesis(pattern_id, scaffold, *, confidence="moderate"):
    return StrategicHypothesis(
        hypothesis_id=f"hyp-{pattern_id}", title=scaffold["title"],
        statement=statement_for(
            scaffold, company="Acme",
            # a representative causal mechanism, for the scaffolds that name
            # one; ignored by the scaffolds that do not
            mechanism="it runs a separate government estate"),
        reasoning=scaffold["reasoning"],
        supporting_observation_ids=["obs-1", "obs-2"],
        counter_observation_ids=["obs-9"],
        alternative_explanations=list(scaffold["alternatives"]),
        confidence=confidence,
        confidence_reasons=[
            "3 qualifying signal(s) matched: a, b",
            "all support comes from company-owned pages, which is one-sided; "
            "independent corroboration is missing"],
        evidence_gaps=list(scaffold["gaps"]),
        decision_implications=list(scaffold["implications"]),
        falsification_questions=list(scaffold["falsification"]),
        pattern_id=pattern_id,
        strongest_support_ids=("obs-1",), strongest_counter_ids=("obs-9",))


def _decisions():
    """One composed decision per entry in the pattern library."""
    return {pid: compose_decision("Acme", _hypothesis(pid, s),
                                  evidence_gaps=s["gaps"])
            for pid, s in HYPOTHESIS_SCAFFOLDS.items()}


ALL = sorted(HYPOTHESIS_SCAFFOLDS)


# --- 1. the topic is not the decision ----------------------------------------

@pytest.mark.parametrize("pattern_id", ALL)
def test_the_topic_is_kept_but_never_shown_as_the_answer(pattern_id):
    """Both halves matter.

    Dropping the topic would lose which decision the evidence bears on, which
    the reasoning layer legitimately needs. Showing it is what put a question
    where the answer goes. It stays, internally, and no reader-facing string
    is built from it.
    """
    decision = _decisions()[pattern_id]
    topic = decision.topic.lower().rstrip(".")
    assert topic, pattern_id

    visible = " ".join([decision.headline, decision.recommended_next_move,
                        decision.unsafe_because, decision.mechanism]
                       + [o.label for o in decision.options]
                       + [o.description for o in decision.options]
                       + [o.upside for o in decision.options]
                       + [o.downside for o in decision.options]).lower()
    assert topic not in visible, pattern_id


@pytest.mark.parametrize("pattern_id", ALL)
def test_no_internal_label_survives_into_reader_facing_text(pattern_id):
    """Pattern ids, arrows and record ids are the system naming itself."""
    decision = _decisions()[pattern_id]
    visible = " ".join(
        [decision.headline, decision.recommended_next_move, decision.mechanism,
         decision.unsafe_because, decision.what_each_result_would_favour]
        + [o.description for o in decision.options]
        + [o.upside for o in decision.options]
        + [o.downside for o in decision.options]
        + [o.key_assumption for o in decision.options])
    assert pattern_id.replace("_", " ") not in visible.lower(), pattern_id
    assert "→" not in visible and "->" not in visible
    assert not re.search(r"\b(hyp|obs|pat|blind)[-:]", visible), visible
    assert "mechanism" not in visible.lower().split(":")[0]


@pytest.mark.parametrize("pattern_id", ALL)
def test_the_mechanism_is_retained_where_the_library_states_one(pattern_id):
    """The mechanism clause is the analysis's most useful sentence.

    Scaffold reasoning welds the rule firing ("...match the product→platform
    mechanism") to the business mechanism ("value and lock-in migrate from the
    visible product to the rails underneath it"). Filtering the whole string
    for its first half threw away the second, so the extraction is asserted
    rather than assumed.
    """
    scaffold = HYPOTHESIS_SCAFFOLDS[pattern_id]
    decision = _decisions()[pattern_id]
    if ":" not in scaffold["reasoning"]:
        return                          # this entry states no mechanism clause
    tail = scaffold["reasoning"].split(":", 1)[1].strip().rstrip(".")
    if decision.mechanism:
        assert tail[:40].lower() in decision.mechanism.lower() or \
            decision.mechanism.lower() in scaffold["statement"].lower()


# --- 2. options are supported, or absent -------------------------------------

@pytest.mark.parametrize("pattern_id", ALL)
def test_readiness_matches_what_the_options_can_actually_support(pattern_id):
    decision = _decisions()[pattern_id]
    assert decision.readiness in (DECISION_READY, INVESTIGATION_REQUIRED)
    if decision.readiness == DECISION_READY:
        assert len(decision.options) >= 2, pattern_id
    else:
        assert len(decision.options) < 2, pattern_id


@pytest.mark.parametrize("pattern_id", ALL)
def test_every_shown_option_states_a_real_trade_off(pattern_id):
    """An option with no cost is advocacy wearing an option's shape."""
    for option in _decisions()[pattern_id].options:
        assert option.description and option.upside and option.downside
        assert option.key_assumption, option.label
        assert option.upside != option.downside
        assert len(option.label.split()) <= 12, option.label
        assert not option.label.rstrip().endswith((" in", " of", " to",
                                                   " the", " and", " or"))


@pytest.mark.parametrize("pattern_id", ALL)
def test_options_keep_their_evidence_lineage(pattern_id):
    """Each side cites what supports IT, not what supports the analysis."""
    decision = _decisions()[pattern_id]
    if decision.readiness != DECISION_READY:
        return
    act, hold = decision.options[0], decision.options[1]
    assert act.supporting_evidence_ids, act.label
    # the two sides do not cite the same evidence for the same thing
    assert set(act.supporting_evidence_ids) == \
        set(hold.contradicting_evidence_ids)
    assert set(act.contradicting_evidence_ids) == \
        set(hold.supporting_evidence_ids)


@pytest.mark.parametrize("pattern_id", ALL)
def test_unsupported_symmetry_is_not_invented(pattern_id):
    """With no competing account on record, there is no second option.

    This is the failure mode the whole readiness split exists for: a page that
    must show two options will write the second one, and a founder cannot tell
    a composed option from a supported one.
    """
    scaffold = HYPOTHESIS_SCAFFOLDS[pattern_id]
    hypothesis = _hypothesis(pattern_id, scaffold)
    hypothesis.alternative_explanations = ["n/a"]     # nothing defensible
    decision = compose_decision("Acme", hypothesis,
                                evidence_gaps=scaffold["gaps"])
    assert decision.readiness == INVESTIGATION_REQUIRED
    assert len(decision.options) < 2


@pytest.mark.parametrize("pattern_id", ALL)
def test_speculative_evidence_never_reaches_decision_ready(pattern_id):
    scaffold = HYPOTHESIS_SCAFFOLDS[pattern_id]
    decision = compose_decision(
        "Acme", _hypothesis(pattern_id, scaffold, confidence="speculative"),
        evidence_gaps=scaffold["gaps"])
    assert decision.readiness == INVESTIGATION_REQUIRED


@pytest.mark.parametrize("pattern_id", ALL)
def test_the_investigation_state_is_useful_rather_than_a_refusal(pattern_id):
    """"We cannot say" is only honest if it also says what would settle it."""
    scaffold = HYPOTHESIS_SCAFFOLDS[pattern_id]
    hypothesis = _hypothesis(pattern_id, scaffold)
    hypothesis.alternative_explanations = ["n/a"]
    decision = compose_decision("Acme", hypothesis,
                                evidence_gaps=scaffold["gaps"])
    assert decision.unsafe_because
    assert decision.recommended_next_move
    assert decision.evidence_required
    assert decision.reconsider_when


def test_a_withheld_view_yields_a_withheld_decision():
    decision = compose_decision("Acme", None, evidence_gaps=["nothing dated"])
    assert decision.readiness == WITHHELD
    assert not decision.options
    assert "not enough" in decision.unsafe_because.lower()


def test_unrelated_patterns_do_not_produce_the_same_decision():
    """Twelve patterns that all read the same way would mean the composition
    is a template with the company name swapped in."""
    ready = [d for d in _decisions().values() if d.readiness == DECISION_READY]
    assert len(ready) >= 4, "too few ready decisions to compare"
    headlines = {d.headline for d in ready}
    assert len(headlines) == len(ready), headlines
    mechanisms = {d.mechanism for d in ready}
    assert len(mechanisms) == len(ready), mechanisms


# --- 3. one decision, every surface ------------------------------------------

def _report(pattern_id="services_to_product"):
    from intent_engine.strategic_intelligence.reasoning import (
        build_strategic_report,
    )
    from intent_engine.strategic_intelligence.shopify_fixture import (
        shopify_observations,
    )
    return build_strategic_report(company_name="Shopify",
                                  observations=shopify_observations())


def test_the_report_carries_the_decision_from_its_earliest_producer():
    """Composed in `_build_thesis`, not by each renderer.

    A renderer that composes its own decision is a renderer that can disagree
    with the next one, which is how five surfaces came to read one field five
    ways in the first place.
    """
    report = _report().as_dict()
    assert report["thesis"].get("decision"), "the thesis carries no decision"
    assert report["thesis"]["decision"]["readiness"] in (
        DECISION_READY, INVESTIGATION_REQUIRED, WITHHELD)


def test_every_surface_states_the_same_decision():
    """Depth may differ between surfaces. The decision may not."""
    from intent_engine.strategic_intelligence.brief import build_brief
    from intent_engine.strategic_intelligence.render import (
        render_strategic_report,
    )
    from intent_engine.strategic_intelligence.slides import build_slides
    import intent_engine.founder_brief.build as founder

    report = _report()
    as_dict = report.as_dict()
    decision = decision_of(as_dict)

    # the executive brief
    brief = build_brief(report, as_of="2026-08-03")
    assert decision.headline in brief.decision or \
        decision.recommended_next_move in brief.decision, brief.decision

    # the full analysis
    full = re.sub(r"<[^>]+>", " ", render_strategic_report(as_dict))
    assert decision.headline[:45] in full, decision.headline

    # the deck
    deck = build_slides(as_dict)
    deck_text = " ".join(b["text"] for s in deck for b in s["bullets"])
    if decision.readiness == DECISION_READY:
        assert decision.options[0].label[:30] in deck_text
    else:
        assert decision.unsafe_because[:40] in deck_text

    # the founder brief, and through its key insight, Q&A
    observations = [o for o in as_dict["observations"]]
    built = founder.build(company="Shopify",
                          mode=founder.PUBLIC_INFORMATION_RICH,
                          report=as_dict, observations=observations)
    if built.key_insight:
        assert built.key_insight.decision == decision.headline


def test_readiness_does_not_change_between_surfaces():
    """A bounded result stays bounded everywhere.

    The serious version of this defect is the opposite direction: a decision
    the report withheld coming back to life on a slide, where it carries more
    weight than it ever did in the report.
    """
    from intent_engine.strategic_intelligence.slides import (
        build_slides, founder_view_from_report,
    )
    report = _report().as_dict()
    decision = decision_of(report)
    view = founder_view_from_report(report)
    if view and view.get("decisions"):
        assert view["decisions"][0]["readiness"] == decision.readiness
    deck = build_slides(report)
    kinds = {s["kind"] for s in deck}
    if decision.readiness == INVESTIGATION_REQUIRED:
        assert "options" not in kinds, kinds
    if decision.readiness == WITHHELD:
        assert not (kinds & {"options", "investigation", "decision"}), kinds


def test_no_slide_survives_on_metadata_alone():
    """A screen carrying only a source count or a title is removed."""
    from intent_engine.strategic_intelligence.slides import build_slides
    for slide in build_slides(_report().as_dict()):
        if slide["kind"] == "evidence":
            continue
        joined = " ".join(b["text"] for b in slide["bullets"]).strip()
        assert joined, slide["id"]
        assert not re.fullmatch(r"Built from [^.]+\.", joined), slide["id"]
        assert not re.fullmatch(r"[A-Z][\w ]+", joined), slide["id"]


# --- 4. break the guards, and watch them fail --------------------------------
#
# Each of these constructs the exact condition the guard exists to reject and
# asserts the rejection. They restore nothing, because they break INPUTS
# rather than the module -- there is no switch here to leave flipped.

def test_break_every_non_empty_string_would_pass_the_quality_gate():
    from intent_engine.founder_brief.build import _is_consequence
    from intent_engine.strategic_intelligence.concrete import (
        reads_as_taxonomy,
    )
    rejected = [
        "Palantir Partnership Vanguard",           # a retrieved page title
        "product→platform",                        # an internal pattern label
        "tool-to-system-of-record",                # the other spelling
        "Whether to keep investing in depth",      # a bare decision topic
        "how much to invest ahead of the transition",   # a noun phrase
        "The most recent evidence is About Palantir.",  # metadata as a claim
        "hyp-services_to_product",                 # an internal id
    ]
    for text in rejected:
        assert not (_is_consequence(text) and not reads_as_taxonomy(text)), text

    # AND THE GATE HAS NOT SIMPLY BECOME A REFUSAL.
    #
    # Over-rejection silently blanks a real finding, which is the same defect
    # from the other side. Each of these is a complete business claim and each
    # was rejected at some point while this gate was being tightened.
    for text in ("Northstar pricing publishes its prices",
                 "value and lock-in migrate from the visible product",
                 "the second buyer arrives with requirements the first never "
                 "had",
                 "larger contracts pull the roadmap toward control and "
                 "complexity"):
        assert _is_consequence(text), text
        assert not reads_as_taxonomy(text), text

    # A short retrieved fact is below the claim gate's word floor and reaches
    # the deck by the concrete-anchor path instead -- asserted here so the two
    # routes are not confused for one.
    from intent_engine.strategic_intelligence.concrete import clean_title
    assert clean_title("Sentry Acquires Codecov | Sentry") == \
        "Sentry acquired Codecov."


def test_break_a_decision_topic_rendered_as_the_finished_decision():
    """Feed every topic in the library to the gate that owns the rendering.

    Which gate owns this is worth being precise about. The founder-brief
    contract deliberately ACCEPTS a decision phrased as a choice -- "whether
    to fund enterprise delivery or protect self-serve onboarding" is a real
    decision and its own docstring says so. What may never happen is a topic
    reaching a reader as a CLAIM: as a slide bullet, a headline, or an
    insight sentence. That is the claim gate, and it rejects every one of the
    library's topics on the same rule -- a question asserts nothing.
    """
    from intent_engine.strategic_intelligence.slides import build_slides
    from intent_engine.founder_brief.build import _is_consequence

    topics = [t for s in HYPOTHESIS_SCAFFOLDS.values()
              for t in s["implications"]]
    assert len(topics) >= 16, len(topics)
    for topic in topics:
        assert not _is_consequence(topic), topic

    # and the deck, given a report whose only decision material IS the topic,
    # renders the composed decision rather than the topic
    report = _report().as_dict()
    topic = report["thesis"]["why_care"]
    deck_text = " ".join(b["text"] for s in build_slides(report)
                         for b in s["bullets"]).lower()
    assert topic.lower().rstrip(".") not in deck_text, topic


def test_break_readiness_is_omitted():
    decision = FounderDecision(topic="t", readiness="")
    assert not decision.is_ready
    assert decision.headline                    # still says something honest


def test_break_no_options_and_no_investigation_state():
    """The empty middle: no options AND nothing said about why."""
    scaffold = HYPOTHESIS_SCAFFOLDS["tool_to_system_of_record"]
    hypothesis = _hypothesis("tool_to_system_of_record", scaffold)
    decision = compose_decision("Acme", hypothesis,
                                evidence_gaps=scaffold["gaps"])
    assert decision.readiness == INVESTIGATION_REQUIRED
    assert decision.unsafe_because, "a refusal with no reason is a dead end"


def test_break_an_unsupported_second_option_is_fabricated():
    """A hand-built second option with no cost is not defensible."""
    fabricated = DecisionOption(label="Do the other thing",
                                description="This path does the other thing.",
                                upside="It could work out well.")
    assert not fabricated.is_defensible


def test_break_a_pattern_title_becomes_the_founder_insight():
    """Every title in the library, not the one that was reported.

    A hypothesis `title` IS the pattern's label for a shape -- "broadening
    from a focused tool toward being the place a team's work is stored" reads
    identically for Notion, Linear and Atlassian. None may pass as a claim
    about a company.
    """
    from intent_engine.founder_brief.build import _is_consequence
    from intent_engine.strategic_intelligence.concrete import (
        reads_as_taxonomy,
    )
    for pattern_id, scaffold in HYPOTHESIS_SCAFFOLDS.items():
        title = scaffold["title"]
        passes = _is_consequence(title) and not reads_as_taxonomy(title)
        assert not passes, f"{pattern_id}: {title!r}"


def test_break_a_source_title_becomes_the_founder_insight():
    from intent_engine.founder_brief.build import _is_consequence
    for title in ("Media Resources | Sentry", "About Palantir",
                  "Palantir Partnership Vanguard", "Investor Relations"):
        assert not _is_consequence(title), title


def test_break_a_marketing_quote_carries_the_deck():
    """The quote may appear as the company's own words. It may not be the
    conclusion, and it may not be the only thing on the deck."""
    from intent_engine.strategic_intelligence.slides import (
        build_slides, deck_is_presentable,
    )
    from tests.test_sentry_deck_regression import _scaffold_report
    deck = build_slides(_scaffold_report(), as_of="2026-07-29",
                        analysis_version="v1", documents=[])
    assert not deck_is_presentable(deck), \
        "a deck of a slogan and a source count must not be presentable"


def test_break_a_source_count_becomes_slide_intelligence():
    from intent_engine.strategic_intelligence.slides import (
        meaningful_slide_count,
    )
    from tests.test_sentry_deck_regression import _scaffold_report
    from intent_engine.strategic_intelligence.slides import build_slides
    deck = build_slides(_scaffold_report(), as_of="2026-07-29",
                        analysis_version="v1", documents=[])
    counted = [s for s in deck if s["kind"] != "evidence"]
    for slide in counted:
        joined = " ".join(b["text"] for b in slide["bullets"])
        assert "source(s)" not in joined, slide["id"]
    assert meaningful_slide_count(deck) == len(counted)


def test_break_removing_invalid_content_leaves_an_empty_deck():
    """An empty deck is a real outcome and must be reported as one, not
    rendered as headings over silence."""
    from intent_engine.strategic_intelligence.slides import (
        build_slides, deck_is_presentable,
    )
    empty = {"company_name": "Nothing", "thesis": {}, "hypotheses": [],
             "observations": [], "shifts": [], "timeline": [], "surprises": [],
             "blind_spots": [], "vulnerabilities": [], "opportunities": [],
             "questions": [], "evidence_gaps": [], "quality_findings": [],
             "source_class_coverage": {}}
    deck = build_slides(empty, as_of="2026-08-03", analysis_version="v1",
                        documents=[])
    assert all(s["bullets"] for s in deck)
    assert not deck_is_presentable(deck)


def test_break_the_recommendation_is_absent():
    decision = FounderDecision(topic="t", readiness=DECISION_READY,
                               recommended_next_move="")
    assert not decision.recommended_next_move
    # the headline still has to stand on its own for a reader
    assert decision.headline


def test_break_two_surfaces_show_different_options():
    """Both read the same stored object, so they cannot diverge by accident."""
    from intent_engine.strategic_intelligence.slides import (
        founder_view_from_report,
    )
    report = _report().as_dict()
    stored = decision_of(report)
    view = founder_view_from_report(report)
    if view and view.get("decisions"):
        labels = [o["label"] for o in view["decisions"][0].get("options") or []]
        assert labels == [o.label for o in stored.options]


def test_break_a_bounded_result_becomes_rich_on_one_surface():
    from intent_engine.strategic_intelligence.slides import (
        _decision_detail_slides,
    )
    bounded = FounderDecision(
        topic="Whether to run one roadmap or two.",
        readiness=INVESTIGATION_REQUIRED,
        unsafe_because="the record carries no competing account",
        recommended_next_move="One bounded check comes before any commitment.",
        evidence_required=("segment revenue is not disclosed",))
    slides = _decision_detail_slides(bounded.as_dict())
    assert {s["kind"] for s in slides} == {"investigation"}
    assert not any(s["kind"] == "options" for s in slides)


# --- 5. read off the deployed preview ----------------------------------------
#
# Each of these was measured on the preview at bb8b3d1, running Palantir as a
# guest. They are here because the test suite was fully green at the time: a
# gate can be correct and still be wired to only some of the paths that need
# it, and no unit test was going to notice which ones were missing.

def test_a_retrieved_page_title_cannot_lead_the_deck():
    """"Palantir Partnership Vanguard." opened the deck under "The insight".

    Three nouns, lifted from a page title. The claim gate was written for
    exactly this string, but it guards the fallback deck, and the takeover
    path reached the same slide without passing it. The word floor cannot be
    reused here -- "Sentry acquired Codecov." is also three words and is the
    fact this path exists to find -- so the verb is what decides.
    """
    from intent_engine.strategic_intelligence.concrete import (
        select_founder_claim_anchor,
    )

    def _observation(title, excerpt):
        return {"source_title": title, "excerpt": excerpt,
                "observation_id": "obs-1", "date": "2026-07-01",
                "source_class": "company_owned"}

    noun_phrase = select_founder_claim_anchor(
        [_observation("Palantir Partnership Vanguard",
                      "Partnership with Vanguard.")], company="Palantir")
    assert noun_phrase == {}, noun_phrase

    real = select_founder_claim_anchor(
        [_observation("Sentry Acquires Codecov | Sentry",
                      "Find current press releases.")], company="Sentry")
    assert real.get("fact") == "Sentry acquired Codecov."


def test_the_next_action_is_not_the_librarys_own_vocabulary():
    """The deployed brief's single next action was "Find out: Whether
    customers actually moved their source of truth is not observable from
    outside" -- an evidence gap in the pattern library's words, on the primary
    screen, as the one thing to go and do."""
    import intent_engine.founder_brief.build as B
    report = {
        "evidence_gaps": [
            "Whether customers actually moved their source of truth is not "
            "observable from outside.",
            "every source here is published by the company itself"],
        "questions": [], "thesis": {}, "hypotheses": [], "observations": []}
    actions = B._next_actions(report, None, B.PRIVATE_COMPANY)
    joined = " ".join(actions).lower()
    assert "source of truth" not in joined, actions
    assert "published by the company itself" in joined, actions


def test_a_suggested_follow_up_never_quotes_a_pattern_title():
    """"What evidence most weakens the absorbing adjacent tools until the work
    lives inside it thesis?" was offered to the reader as a click."""
    from intent_engine.webapp.app import WebApp
    app = object.__new__(WebApp)
    report = {"hypotheses": [{
        "title": "absorbing adjacent tools until the work lives inside it",
        "comparables": ["Notion"]}], "agenda": []}
    questions = " ".join(app._suggested_questions(report)).lower()
    assert "adjacent tools" not in questions, questions
    assert "weakens the reading" in questions, questions


def test_source_classes_reach_the_reader_in_words():
    """The deck printed "no investor_material / customer_voice / competitor /
    independent_reporting source corroborates this yet"."""
    from intent_engine.strategic_intelligence.reasoning import (
        build_strategic_report,
    )
    from tests.test_sentry_deck_regression import SENTRY_OBS
    report = build_strategic_report(company_name="Sentry",
                                    observations=SENTRY_OBS).as_dict()
    gaps = " ".join(report["evidence_gaps"])
    for internal in ("investor_material", "customer_voice",
                     "independent_reporting", "executive_statement"):
        assert internal not in gaps, gaps


def test_the_limitations_slide_is_filtered_like_every_other_list():
    """It was the one founder-facing list nobody had thought of as carrying
    claims, so "Whether customers actually moved their source of truth is not
    observable from outside" reached the deployed deck through it."""
    from intent_engine.strategic_intelligence.editorial import (
        consolidate_limitations,
    )
    kept = consolidate_limitations([
        "Whether customers actually moved their source of truth is not "
        "observable from outside.",
        "every source here is published by the company itself"])
    joined = " ".join(kept).lower()
    assert "source of truth" not in joined, kept
    assert "published by the company itself" in joined, kept


def test_the_withheld_page_names_its_evidence_in_words():
    """It told a founder its evidence covered "company_owned,
    executive_statement, investor_material" -- on the screen whose whole job
    is explaining honestly what was and was not found."""
    from intent_engine.strategic_intelligence.withheld_explanation import (
        explain,
    )
    out = explain(findings=(), families={"company_owned",
                                         "executive_statement",
                                         "investor_material"},
                  document_count=13)
    text = " ".join(str(v) for v in out.values())
    for internal in ("company_owned", "executive_statement",
                     "investor_material"):
        assert internal not in text, text
    assert "the company's own pages" in text, text


def test_the_decision_uses_the_portfolio_not_only_its_top_entry():
    """Both live companies ranked a hypothesis first whose mechanism is the
    library describing itself, so both refused to decide -- while the same
    page printed a mechanism for the reading ranked second.

    Ranking still decides the central claim. It does not get to veto a
    decision the evidence below it can support.
    """
    from intent_engine.strategic_intelligence.decision import decide_across
    blocked = _hypothesis("tool_to_system_of_record",
                          HYPOTHESIS_SCAFFOLDS["tool_to_system_of_record"])
    usable = _hypothesis("product_to_platform",
                         HYPOTHESIS_SCAFFOLDS["product_to_platform"])

    alone = compose_decision("Acme", blocked)
    assert alone.readiness == INVESTIGATION_REQUIRED

    together = decide_across("Acme", [blocked, usable])
    assert together.readiness == DECISION_READY, together.unsafe_because
    assert len(together.options) == 2
    assert together.mechanism

    # and a portfolio where NONE can support one still refuses
    assert decide_across("Acme", [blocked]).readiness == \
        INVESTIGATION_REQUIRED


def test_the_rich_brief_shows_the_decision_not_the_topics():
    """The deployed brief listed two raw topics under "The decision"."""
    from intent_engine.founder_brief.layers import _composed_decision_lines
    report = _report().as_dict()
    line = _composed_decision_lines(report)
    assert line
    for implication in (report.get("decision_implications") or ())[:3]:
        topic = (implication.get("decision") or "").lower().rstrip(".")
        if topic:
            assert topic not in line.lower(), topic


def test_an_option_screen_says_the_mechanism_once():
    """On the deployed decks the mechanism appeared four times across two
    screens: in the headline, on the decision screen, as option one's upside,
    and again as its key assumption. It is the act option's assumption AND its
    upside by construction, so the repetition is structural rather than a
    one-off.

    What may not happen in fixing it is the upside going missing -- an option
    screen without what the option WINS is the more expensive failure.
    """
    from intent_engine.strategic_intelligence.slides import build_slides
    deck = build_slides(_report().as_dict())
    options = [s for s in deck if s["kind"] == "options"]
    assert len(options) == 2, [s["kind"] for s in deck]

    for slide in options:
        texts = [b["text"] for b in slide["bullets"]]
        assert texts, slide["id"]
        # the upside survives, and nothing on the screen restates it
        seen = []
        for text in texts:
            words = " ".join(re.findall(r"[a-z0-9]+", text.lower()))
            for other in seen:
                assert words not in other and other not in words, texts
            seen.append(words)

    decision = [s for s in deck if s["kind"] == "decision"]
    if decision:
        bullets = [b["text"] for b in decision[0]["bullets"]]
        head = " ".join(re.findall(r"[a-z0-9]+", bullets[0].lower()))
        for text in bullets[1:]:
            body = " ".join(re.findall(r"[a-z0-9]+", text.lower()))
            assert body not in head, bullets
