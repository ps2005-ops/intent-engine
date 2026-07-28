"""The deck a founder is actually shown.

The old deck opened by explaining the system. This one opens with what
business the company is really in, and never mentions the machinery.
"""
from intent_engine.strategic_intelligence.slides import (
    build_founder_slides, build_slides, deck_is_presentable,
)

ANALYSIS = {
    "business_model": {
        "one_line": "Sells PlayStation hardware near cost and earns on "
                    "software and subscriptions.",
        "where_profit_comes_from": "software attach and PlayStation Plus, "
                                   "not the console",
        "where_value_leaks": "first-party titles in the catalogue earn "
                             "subscription revenue instead of unit revenue",
        "what_customers_actually_buy": "access to a catalogue and the friends "
                                       "already on it",
        "the_game_they_are_playing": "Owning the only place a certain "
                                     "catalogue can be played, for as long as "
                                     "people want that catalogue.",
    },
    "mental_model": {
        "they_believe": "players choose a console for its exclusive titles",
        "they_are_protecting": "the full-price value of first-party releases",
        "they_are_sacrificing": "subscriber growth they could have bought "
                                "with day-one inclusion",
        "they_will_not_compromise_on": "owning the studios outright",
        "where_this_could_blind_them": "a generation that never expected to "
                                       "buy a game outright",
    },
    "assumptions": [{
        "assumption": "Full-price buyers and subscribers are the same people.",
        "why_we_believe_it": "Both arrive through the same console.",
        "what_would_break_it": "Subscribers skewing to players who never "
                               "bought at full price.",
        "how_load_bearing": "high", "confidence": "low",
    }],
    "scenarios": {
        "upside_case": "both compound",
        "downside_case": "matches late and loses both",
        "wild_card": "a publisher pulls its catalogue from all subscriptions",
        "leading_indicators": ["a first-party title appearing near launch"],
    },
    "blind_spots": {
        "everyone_is_discussing": "whether Game Pass is profitable",
        "almost_nobody_is_discussing": "that the catalogue depends on a "
                                       "release cadence no studio can "
                                       "guarantee every year",
    },
    "the_insight": {
        "sentence": "Withholding first-party titles from day-one PlayStation "
                    "Plus is the lever protecting the attach revenue that "
                    "subsidises hardware sold near cost.",
        "paragraph": "Hardware is a loss leader, so the catalogue is what "
                     "keeps a player paying after the console is bought.",
        "why_now": "Microsoft already places first-party titles in Game Pass "
                   "on release day.",
        "tension": {"side_a": "Day-one inclusion accelerates subscriber "
                              "growth.",
                    "side_b": "It cannibalises full-price sales of the same "
                              "titles.",
                    "why_it_exists": "The catalogue is both the draw and the "
                                     "premium product."},
        "economics": {"mechanism": "Subscription revenue is recurring where "
                                   "unit revenue is one-off.",
                      "levers": ["retention"]},
        "consequence_chain": [
            "First-party titles enter the catalogue at launch.",
            "Full-price unit revenue on those titles falls.",
            "Studio budgets are judged on subscriber months, not launch units.",
        ],
        "citations": ["obs-1", "obs-2"],
    },
    "decisions": [{
        "decision": "Put a flagship title into PlayStation Plus on release "
                    "day, or hold the line at full price.",
        "why_it_matters": "It decides whether the catalogue or the console is "
                          "the retention asset.",
        "urgency": "this_year",
        "cost_of_waiting": "Every cycle held lets a rival set subscriber "
                           "expectations.",
        "what_a_competitor_may_do_first": "Microsoft widens day-one Game Pass "
                                          "coverage.",
        "upside": "Recurring revenue and higher retention.",
        "downside": "Permanent loss of full-price unit revenue.",
        "what_would_invalidate_it": "Attach revenue growing faster than "
                                    "subscription revenue.",
        "what_to_watch": "Day-one catalogue announcements.",
        "business_impact": "high",
        "reversibility": "costly_to_reverse",
        "verdict": "do_now",
        "confidence": "moderate",
        "confidence_rationale": "Moderate -- one independent source.",
        "citations": ["obs-1"],
    }],
    "competitive": {
        "who_is_forcing_the_change": "Microsoft",
        "who_benefits": "Players buying fewer than three titles a year",
        "who_loses": "Third-party publishers relying on full-price launches",
        "who_must_respond": "PlayStation Studios leadership",
        "if_nobody_responds": "Console margin stays tied to hardware cycles.",
        "what_rivals_should_fear": "A studio roster deep enough that Sony can "
                                   "withhold day-one titles and still sell "
                                   "consoles.",
    },
    "questions": ["What happens the first year the catalogue has no flagship?"],
    "strongest_case_we_are_wrong": "Hardware cycles still drive the install "
                                   "base and subscription is additive.",
    "evidence_gaps": ["No subscriber counts disclosed."],
}


def _titles(slides):
    return [s["title"] for s in slides]


def _all_text(slides):
    return " ".join(b["text"] for s in slides for b in s["bullets"]).lower()


def test_deck_opens_with_what_deserves_today():
    slides = build_founder_slides(ANALYSIS)
    assert slides[0]["kind"] == "today"
    assert "today" in slides[0]["title"].lower()


def test_deck_never_opens_with_the_method():
    kinds = [s["kind"] for s in build_founder_slides(ANALYSIS)]
    assert kinds[1] == "business_model"
    assert "evidence" not in kinds[:3]


def test_no_today_slide_when_nothing_has_earned_today():
    """Manufacturing a daily action is how a product teaches people to
    ignore it."""
    import copy
    a = copy.deepcopy(ANALYSIS)
    a["decisions"][0]["verdict"] = "wait"
    assert build_founder_slides(a)[0]["kind"] == "business_model"


def test_the_insight_is_its_own_slide():
    slides = build_founder_slides(ANALYSIS)
    insight = [s for s in slides if s["kind"] == "insight"]
    assert len(insight) == 1
    assert insight[0]["title"] == "The insight"


def test_the_story_runs_in_founder_order():
    kinds = [s["kind"] for s in build_founder_slides(ANALYSIS)]
    for earlier, later in [("business_model", "game"),
                           ("game", "insight"),
                           ("insight", "mental_model"),
                           ("mental_model", "decision"),
                           ("decision", "assumption"),
                           ("assumption", "competitive"),
                           ("competitive", "counterargument"),
                           ("counterargument", "monitor")]:
        assert kinds.index(earlier) < kinds.index(later), kinds


def test_every_deck_names_a_decision_with_its_cost_of_waiting():
    slides = build_founder_slides(ANALYSIS)
    decision_slides = [s for s in slides if s["kind"] == "decision"]
    assert decision_slides
    text = " ".join(b["text"] for b in decision_slides[0]["bullets"]).lower()
    assert "waiting costs" in text
    assert "rival may move first" in text


def test_the_five_questions_are_all_answered():
    """The whole point of the deck: a founder with five minutes gets these."""
    kinds = {s["kind"] for s in build_founder_slides(ANALYSIS)}
    assert "business_model" in kinds      # what business are they really in
    assert "game" in kinds                # what game are they playing
    assert "mental_model" in kinds        # what is leadership protecting
    assert "assumption" in kinds          # what carries the weight
    assert "competitive" in kinds         # what rivals should fear


def test_what_rivals_should_fear_reaches_the_deck():
    slides = build_founder_slides(ANALYSIS)
    threat = [s for s in slides if s["kind"] == "competitive"][0]
    assert "studio roster deep enough" in threat["bullets"][0]["text"]


def test_the_case_for_being_wrong_reaches_the_deck():
    """Audited as only 44% visible before -- among the most valuable fields
    in the analysis and the reader never saw it."""
    slides = build_founder_slides(ANALYSIS)
    wrong = [s for s in slides if s["kind"] == "counterargument"][0]
    assert wrong["bullets"][0]["text"] == ANALYSIS["strongest_case_we_are_wrong"]


def test_the_case_against_is_argued_not_omitted():
    slides = build_founder_slides(ANALYSIS)
    against = [s for s in slides if s["kind"] == "counterargument"]
    assert against
    assert "hardware cycles still drive" in \
        " ".join(b["text"] for b in against[0]["bullets"]).lower()


def test_no_slide_talks_about_the_system():
    """The tell that a founder is reading software rather than advice."""
    text = _all_text(build_founder_slides(ANALYSIS))
    for phrase in ("hypothesis", "observation", "signal", "pattern library",
                   "affected function", "supporting evidence",
                   "decision affected", "confidence badge"):
        assert phrase not in text, f"deck says {phrase!r} to the reader"


def test_the_insight_sentence_is_never_truncated():
    """It is the one sentence chosen to be remembered. Trimming it to the
    bullet budget cut '...is not conservatism' off the end -- keeping the
    setup and deleting the point."""
    slides = build_founder_slides(ANALYSIS)
    insight = [s for s in slides if s["kind"] == "insight"][0]
    assert insight["bullets"][0]["text"] == ANALYSIS["the_insight"]["sentence"]
    assert "…" not in insight["bullets"][0]["text"]


def test_trimming_ends_on_a_finished_thought():
    from intent_engine.strategic_intelligence.slides import _shorten
    long = ("Every cycle that Sony holds this line while a competitor does "
            "the opposite is a live comparison the market can observe and "
            "react to; waiting does not preserve optionality, it just delays "
            "finding out whether the approach still protects revenue.")
    out = _shorten(long)
    assert not out.endswith("the…")
    assert out.endswith(".")


def test_trimming_never_stops_inside_a_bracket():
    from intent_engine.strategic_intelligence.slides import _shorten
    out = _shorten("Access to an exclusive catalogue of first-party titles "
                   "and the network (multiplayer, cloud streaming, discounts) "
                   "that keeps every player inside the ecosystem for years.")
    assert out.count("(") == out.count(")"), out


def test_prefixed_fragments_read_as_clauses():
    slides = build_founder_slides(ANALYSIS)
    text = _all_text(slides)
    assert "what customers are really buying: access" in text
    # the bug this pins: "Customers are really buying Access to..."
    assert "really buying Access" not in text


def test_no_empty_slides():
    for s in build_founder_slides(ANALYSIS):
        assert s["bullets"], f"empty slide: {s['id']}"


def test_deck_is_presentable():
    assert deck_is_presentable(build_founder_slides(ANALYSIS))


def test_build_slides_prefers_the_founder_deck_when_an_analysis_exists():
    report = {"company_name": "Sony Interactive Entertainment",
              "strategic_analysis": ANALYSIS}
    assert build_slides(report)[0]["kind"] == "today"


def test_build_slides_falls_back_when_there_is_no_analysis():
    """No analysis means no founder deck -- and the old deck must still work
    rather than the page going blank."""
    report = {"company_name": "Acme", "strategic_analysis": None,
              "observations": [], "hypotheses": [], "thesis": {}}
    assert isinstance(build_slides(report), list)


def test_identical_dates_are_not_repeated_on_every_bullet():
    """Every bullet carried the same retrieval date, which read as chronology
    that was not there."""
    from intent_engine.strategic_intelligence.slides import render_deck
    slides = [{"id": "s1", "title": "T", "kind": "insight", "note": "",
               "bullets": [{"text": "one", "evidence": [], "date": "2026-07-28",
                            "full": False},
                           {"text": "two", "evidence": [], "date": "2026-07-28",
                            "full": False}]}]
    assert "2026-07-28" not in render_deck(slides, company="X")


def test_genuinely_different_dates_are_still_shown():
    from intent_engine.strategic_intelligence.slides import render_deck
    slides = [{"id": "s1", "title": "T", "kind": "insight", "note": "",
               "bullets": [{"text": "one", "evidence": [], "date": "2026-07-28",
                            "full": False},
                           {"text": "two", "evidence": [], "date": "2025-01-02",
                            "full": False}]}]
    html = render_deck(slides, company="X")
    assert "2026-07-28" in html and "2025-01-02" in html
