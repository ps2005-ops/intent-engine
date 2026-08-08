"""The whole founder-facing Sentry deck, as a reader sees it.

Built from Sentry's actual retrieved evidence. Live, the deck opened with
"broadening from a focused tool toward being the place a team's work is
stored" -- the tool_to_system_of_record scaffold -- while the run had
retrieved a page titled "Sentry Acquires Codecov".

Everything here asserts RENDERED CONTENT, not source strings.
"""
import re

import pytest

from intent_engine.strategic_intelligence.reasoning import (
    build_strategic_report,
)
from intent_engine.strategic_intelligence.records import StrategicObservation
from intent_engine.strategic_intelligence.slides import (
    build_slides, deck_is_presentable, render_deck,
)


def _obs(oid, title, excerpt, signals=("consolidation",)):
    return StrategicObservation(
        observation_id=oid, text=f"{title} shows a signal",
        observation_type="product_surface",
        source_refs=[{"subsystem": "company_ingestion",
                      "artifact_type": "retrieved_source",
                      "artifact_id": oid, "source_class": "company_owned"}],
        confidence="moderate", freshness="CURRENT", directly_observed=True,
        signals=tuple(signals), source_class="company_owned", excerpt=excerpt,
        source_title=title, origin=f"https://sentry.io/{oid}",
        date="2026-07-29",
        strategic_signal="positions itself as replacing several separate tools",
        relevance="context", entity="Sentry", weak=False,
        evidence_quality="strong")


# these titles are what the live run actually retrieved
#
# THE SIGNAL SET WAS MIGRATED, THE RENDERING CONTRACT WAS NOT.
# ------------------------------------------------------------------
# Everything in this file is a contract on the RENDERER: that the pattern
# library's taxonomy never reaches a reader, and that filtering it out does
# not take the honesty — the confidence sentence, the case against, the gaps —
# with it. To test any of that there has to be a reading to filter, and the
# reading this fixture produced was `tool_to_system_of_record` qualifying on
# `consolidation + multi_product`.
#
# That qualification was itself the defect, removed in
# `test_system_of_record_needs_a_mechanism`: several products and
# consolidation copy are things most B2B software companies have, and neither
# says the customer's source of truth moved. Left alone, this fixture would
# have gone quiet — three renderer contracts passing vacuously because no
# hypothesis existed to leak, and a deck dropping from four slides to two.
#
# So `obs-5` observes the mechanism the reading asserts. Note what this
# fixture is and is not: the signals here were always hand-attached rather
# than detected from the excerpts, so this is a Sentry-shaped run that clears
# the new bar, not a claim about what Sentry's own pages say today. Whether
# the real company still qualifies is a question for the live rerun, and the
# answer there is allowed to be no.
SENTRY_OBS = [
    _obs("obs-1", "About Sentry | Sentry", "Bugs aren't great."),
    _obs("obs-2", "Sentry Acquires Codecov | Sentry",
         "Find current press releases."),
    _obs("obs-3", "Application Performance Monitoring & Error Tracking "
                  "Software | Sentry",
         "Application performance monitoring for developers.",
         ("multi_product", "consolidation")),
    _obs("obs-4", "Media Resources | Sentry", "Press releases and logos."),
    _obs("obs-5", "One platform, one data model | Sentry",
         "Errors, traces and replays are written to a shared data model, so "
         "every product reads the same underlying data.",
         ("shared_data_model",)),
]


@pytest.fixture(scope="module")
def deck():
    return build_slides(build_strategic_report(company_name="Sentry",
                                               observations=SENTRY_OBS))


@pytest.fixture(scope="module")
def visible(deck):
    return " ".join(b["text"] for s in deck for b in s["bullets"])


def test_the_deck_opens_with_the_acquisition(deck):
    first = deck[0]
    assert first["kind"] == "insight"
    assert first["bullets"][0]["text"] == "Sentry acquired Codecov."


def test_the_opening_cites_the_acquisition_source(deck):
    citations = deck[0]["bullets"][0]["evidence"]
    assert "obs-2" in citations, citations


@pytest.mark.parametrize("phrase", [
    "system of record",
    "tool-to-system-of-record",
    "broadening from a focused tool",
    "strategic signal",
    "adjacent tools",
])
def test_no_taxonomy_reaches_the_reader(visible, phrase):
    assert phrase.lower() not in visible.lower(), phrase


def test_no_build_version_reaches_the_reader(deck):
    html = render_deck(deck, company="Sentry", as_of="2026-07-29",
                       analysis_version="9.9.9-internal")
    assert "9.9.9-internal" not in html
    assert "analysis version" not in html.lower()


def test_confidence_and_uncertainty_survive(deck, visible):
    """Filtering the claim must not take the honesty with it."""
    assert any(s["kind"] == "gaps" for s in deck), [s["kind"] for s in deck]
    assert "lead rather than a finding" in visible


def test_the_counterargument_survives(deck):
    """Genuine counter-evidence is NOT filtered -- it legitimately names the
    mechanism being doubted."""
    assert any(s["kind"] == "counterargument" for s in deck)


def test_the_deck_is_presentable_so_slides_remains_the_default(deck):
    assert deck_is_presentable(deck)


def test_the_watch_screen_is_specific_or_honestly_absent(deck):
    """A watch item a reader cannot observe is worse than no watch screen.
    Sentry's only candidate was the pattern's own falsification question."""
    watch = [s for s in deck if s["kind"] == "monitor"]
    if not watch:
        return                              # honestly omitted
    for bullet in watch[0]["bullets"]:
        assert "system of record" not in bullet["text"].lower()


def test_no_screen_is_padded_to_reach_a_count(deck):
    for slide in deck:
        assert slide["bullets"], f"empty screen rendered: {slide['id']}"
        for bullet in slide["bullets"]:
            assert bullet["text"].strip()


# --- the brief must make the same argument as the deck ---------------------

def test_the_brief_opens_with_the_same_claim_as_the_deck(deck):
    """One company, one central claim. The brief used to select its own from
    the scaffold, so the same run opened two different ways -- and the brief's
    was the one that kept "system of record" alive on production after the
    deck was already clean."""
    from intent_engine.strategic_intelligence.brief import build_brief
    report = build_strategic_report(company_name="Sentry",
                                    observations=SENTRY_OBS)
    brief = build_brief(report, as_of="2026-07-29")
    assert brief.thesis == deck[0]["bullets"][0]["text"] == \
        "Sentry acquired Codecov."


def test_the_brief_carries_no_taxonomy_in_its_central_claim():
    from intent_engine.strategic_intelligence.brief import build_brief
    report = build_strategic_report(company_name="Sentry",
                                    observations=SENTRY_OBS)
    thesis = build_brief(report, as_of="2026-07-29").thesis.lower()
    for phrase in ("system of record", "broadening from a focused tool",
                   "adjacent tools"):
        assert phrase not in thesis, phrase


# --- all three layers, one argument ----------------------------------------

TAXONOMY = ("system of record", "tool-to-system-of-record",
            "broadening from a focused tool", "strategic signal",
            "adjacent tools")


def _report():
    return build_strategic_report(company_name="Sentry",
                                  observations=SENTRY_OBS)


def _full_html():
    from intent_engine.strategic_intelligence.render import (
        render_strategic_report,
    )
    return render_strategic_report(_report().as_dict())


def _brief_obj():
    from intent_engine.strategic_intelligence.brief import build_brief
    return build_brief(_report(), as_of="2026-07-29")


@pytest.mark.parametrize("phrase", TAXONOMY)
def test_the_full_analysis_carries_no_taxonomy(phrase):
    """Three separate sources put this on production: the pattern library's
    own entry name, the hypothesis reasoning that describes the library
    matching itself, and the hypothesis title."""
    import re
    text = re.sub(r"<[^>]+>", " ", _full_html()).lower()
    assert phrase.lower() not in text, phrase


@pytest.mark.parametrize("phrase", TAXONOMY)
def test_the_brief_carries_no_taxonomy(phrase):
    brief = _brief_obj()
    text = " ".join([brief.thesis] + list(brief.questions)
                    + [getattr(brief, "limitation", "") or ""]).lower()
    assert phrase.lower() not in text, phrase


def test_all_three_layers_share_one_factual_anchor(deck):
    """One analysis, one central claim -- not three renderers inventing three
    theses."""
    import re
    anchor = "Sentry acquired Codecov."
    assert deck[0]["bullets"][0]["text"] == anchor
    assert _brief_obj().thesis == anchor
    assert anchor.rstrip(".") in re.sub(r"<[^>]+>", " ", _full_html())


def test_the_layers_are_not_verbatim_duplicates(deck):
    """They share the argument, not the words."""
    import re
    deck_text = " ".join(b["text"] for s in deck for b in s["bullets"])
    full_text = re.sub(r"<[^>]+>", " ", _full_html())
    assert len(full_text) > len(deck_text), \
        "the full analysis carries no more detail than the deck"


# --- the OTHER deck: real evidence, no concrete development ------------------
#
# Everything above exercises the founder deck, which only takes over when a
# concrete fact earns it. Sentry had one ("Sentry Acquires Codecov"), so these
# tests never reached `build_report_slides` -- the fallback deck for a company
# with real evidence and nothing concrete to lead with.
#
# That fallback was measured on production across five companies at f1d350c.
# Every company that produced a deck leaked into it:
#
#   Hugging Face   system of record, broadening from a focused tool,
#                  strategic signal
#   Stripe         the same three
#   CrowdStrike    two of the three
#   GitLab, Nvidia limited-evidence page, nothing to leak into
#
# The brief and the full analysis were clean for all five. The fallback deck
# was simply never filtered.

def _scaffold_report(company="Huggingface"):
    """A report whose every interpretive field is the pattern library talking:
    the thesis, the hypothesis, the blind spot, the vulnerability, the
    opportunity and the leadership question all come from one scaffold."""
    from intent_engine.strategic_intelligence.patterns import (
        HYPOTHESIS_SCAFFOLDS, statement_for,
    )
    scaffold = HYPOTHESIS_SCAFFOLDS["tool_to_system_of_record"]
    statement = statement_for(scaffold, company=company, mechanism="it runs a separate government estate")
    return {
        "company_name": company,
        "thesis": {"view": f"{company} appears to be {scaffold['title']}.",
                   "transition": statement,
                   "why_care": "Whether to keep investing in depth or in "
                               "adjacency."},
        "hypotheses": [{"title": scaffold["title"], "statement": statement,
                        "reasoning": "The signals match the "
                                     "tool-to-system-of-record mechanism.",
                        "confidence": "low",
                        "strongest_support_ids": ["obs-1"]}],
        "observations": [{"observation_id": "obs-1",
                          "excerpt": "We are helping the community work "
                                     "together.",
                          "source_class": "company_owned",
                          "date": "2026-07-01"}],
        "blind_spots": [{"observed_tension": statement}],
        "vulnerabilities": [{"exposed_layer": "the system of record",
                             "mechanism": "broadening from a focused tool"}],
        "opportunities": [{"statement": "A move toward being the system of "
                                        "record."}],
        "questions": [{"question": "How far toward a system of record do we "
                                   "go?"}],
        "surprises": [], "shifts": [], "timeline": [],
        "evidence_gaps": ["all evidence is company-published"],
        "quality_findings": [],
        "source_class_coverage": {"company_owned": 5},
    }


def _fallback_deck():
    return build_slides(_scaffold_report(), as_of="2026-07-29",
                        analysis_version="v1", documents=[])


@pytest.mark.parametrize("phrase", TAXONOMY)
def test_the_fallback_deck_carries_no_taxonomy(phrase):
    import json
    assert phrase.lower() not in json.dumps(_fallback_deck()).lower(), phrase


def test_a_deck_with_nothing_concrete_is_not_presentable():
    """The point of dropping those bullets is NOT to ship a shorter deck of
    the same generic claims -- it is to stop presenting one at all. With the
    library's sentences removed there is not enough left to present, so the
    reader is sent to the limited-analysis page that says what was and was
    not found. A padded deck would be the failure this whole programme is
    about."""
    assert deck_is_presentable(_fallback_deck()) is False


def test_the_fallback_deck_still_keeps_what_is_real():
    """Dropped, not sanitised: the company's own words survive.

    THE RETIRED EXPECTATION
    -----------------------
    This also asserted `"depth or in adjacency" in text`, which is
    `tool_to_system_of_record`'s `implications[0]` -- "Whether to keep
    investing in depth or in adjacency". That is a decision TOPIC: a question,
    phrased as a question, and the deck printed it under a decision heading as
    though the analysis had answered it. The assertion could only ever pass by
    the product handing the founder's own question back to them, so it pinned
    the defect in place rather than guarding against anything.

    What replaces it is not weaker. The topic must still be reachable
    internally, it must NOT appear verbatim anywhere a reader can see, and the
    deck must carry the composed decision in its place -- which for this
    evidence is the honest bounded state, because the scaffold's mechanism is
    the library describing itself and nothing survives to choose between.
    """
    deck = _fallback_deck()
    text = " ".join(b["text"] for s in deck for b in s["bullets"])
    assert "helping the community work together" in text

    from intent_engine.strategic_intelligence.decision import decision_of
    decision = decision_of(_scaffold_report())
    assert decision.topic or decision.readiness == "INVESTIGATION_REQUIRED"
    assert "depth or in adjacency" not in text.lower()
    assert "whether to keep investing" not in text.lower()


def test_the_fallback_deck_states_a_bounded_position_not_a_slogan():
    """The sparse deck has to be USEFUL, not merely clean.

    Filtering the library's sentences left this deck reading, in full: "We are
    helping the community work together." and "Built from 5 company owned
    source(s)." -- a marketing quote and a source count. Neither is
    intelligence. A reader given those two lines learned nothing, which is the
    same failure as the pattern label, one step further along.
    """
    deck = _fallback_deck()
    investigation = [s for s in deck if s["kind"] == "investigation"]
    assert investigation, [s["kind"] for s in deck]
    bullets = " ".join(b["text"] for b in investigation[0]["bullets"])

    # why committing is unsafe, and what would close it -- both present
    assert "not the mechanism behind it" in bullets
    assert "company-published" in bullets

    # and the two non-answers may not be carrying the deck
    lead = deck[0]["bullets"][0]["text"].lower()
    assert "source(s)" not in lead
    for slide in deck:
        if slide["kind"] == "evidence":
            continue
        joined = " ".join(b["text"] for b in slide["bullets"])
        assert joined.strip(), f"empty screen rendered: {slide['id']}"
        assert not re.fullmatch(r"Built from [^.]+\.", joined.strip()), joined


def test_the_topic_never_renders_as_the_finished_decision():
    """Across the WHOLE library, not just the pattern that was reported.

    `implications[0]` is the decision topic for every scaffold there is, and
    the defect was systemic: one field, read directly by every surface. A test
    that only pinned `tool_to_system_of_record` would let the next eleven
    through.
    """
    from intent_engine.strategic_intelligence.decision import compose_decision
    from intent_engine.strategic_intelligence.patterns import (
        HYPOTHESIS_SCAFFOLDS, statement_for,
    )
    from intent_engine.strategic_intelligence.records import (
        StrategicHypothesis,
    )
    for pattern_id, scaffold in HYPOTHESIS_SCAFFOLDS.items():
        hypothesis = StrategicHypothesis(
            hypothesis_id=f"hyp-{pattern_id}", title=scaffold["title"],
            statement=statement_for(scaffold, company="Acme", mechanism="it runs a separate government estate"),
            reasoning=scaffold["reasoning"],
            supporting_observation_ids=["obs-1"], counter_observation_ids=[],
            alternative_explanations=list(scaffold["alternatives"]),
            confidence="moderate", confidence_reasons=["r"],
            evidence_gaps=list(scaffold["gaps"]),
            decision_implications=list(scaffold["implications"]),
            falsification_questions=list(scaffold["falsification"]),
            pattern_id=pattern_id)
        decision = compose_decision("Acme", hypothesis,
                                    evidence_gaps=scaffold["gaps"])
        topic = decision.topic.lower().rstrip(".")

        # the topic stays available internally ...
        assert topic, pattern_id
        # ... and is never what a reader is shown as the decision
        assert topic not in decision.headline.lower(), pattern_id
        assert topic not in decision.recommended_next_move.lower(), pattern_id
        for option in decision.options:
            assert topic not in option.label.lower(), pattern_id
            assert topic not in option.description.lower(), pattern_id


def test_a_dropped_library_question_is_replaced_by_a_checkable_one():
    """Linear's ONLY leadership question was "Customers describing it as a
    companion to a system of record rather than the record itself" -- the
    pattern's own falsification question. Filtering it left a reader preparing
    for a meeting with nothing to investigate, and the persona harness caught
    it. It had been PASSING on that sentence, so the answer was never really
    there.

    The replacement is drawn from the run's own dated findings, so it names
    something actually retrieved -- not the library's question reworded, and
    not the limitations list promoted to look like an action."""
    report = _scaffold_report()
    report["shifts"] = [{"title": "Northstar pricing publishes its prices",
                         "date": "2026-07-01", "observation_id": "obs-1"}]
    deck = build_slides(report, as_of="2026-07-29", analysis_version="v1",
                        documents=[])
    questions = [s for s in deck if s["id"] == "questions"]
    assert questions, "nothing left for a reader to investigate"
    text = questions[0]["bullets"][0]["text"]
    assert "Northstar pricing publishes its prices" in text
    assert "system of record" not in text.lower()
    # the company name keeps its capital -- an earlier version lowercased the
    # whole sentence and shipped "northstar pricing publishes its prices"
    assert "northstar" not in text
