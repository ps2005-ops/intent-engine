"""Prioritisation, strategic memory, and the one screen a founder opens.

The behaviours pinned here are the ones that decide whether a founder opens
this again tomorrow: that it ranks rather than lists, that it will say
"nothing changed" when nothing changed, and that it will decline to
manufacture a decision for today when none has earned it.
"""
from intent_engine.strategic_intelligence.analyst.memory import compare
from intent_engine.strategic_intelligence.analyst.priority import (
    daily_view, leverage, rank_decisions, todays_decision, weakest_assumption,
)


def _d(name, **kw):
    base = {"decision": name, "why_it_matters": "matters",
            "urgency": "this_year", "business_impact": "medium",
            "reversibility": "easily_reversible", "verdict": "monitor",
            "cost_of_waiting": "some cost", "confidence": "moderate",
            "citations": []}
    base.update(kw)
    return base


# --- ranking ---------------------------------------------------------------

def test_a_one_way_door_outranks_a_reversible_call_of_equal_urgency():
    door = _d("one way", reversibility="one_way_door")
    easy = _d("reversible", reversibility="easily_reversible")
    assert leverage(door) > leverage(easy)


def test_high_impact_and_urgent_outranks_everything_else():
    top = _d("urgent big", business_impact="high", urgency="decide_now",
             verdict="do_now")
    other = _d("small later", business_impact="low", urgency="watch_only")
    assert rank_decisions([other, top])[0]["decision"] == "urgent big"


def test_an_ignore_verdict_cannot_float_to_the_top_on_impact_alone():
    ignore = _d("ignore me", business_impact="high", urgency="decide_now",
                verdict="ignore")
    real = _d("real one", business_impact="medium", urgency="this_quarter",
              verdict="do_now")
    assert rank_decisions([ignore, real])[0]["decision"] == "real one"


def test_ranking_is_stable_for_equal_scores():
    a, b = _d("a"), _d("b")
    assert [x["decision"] for x in rank_decisions([a, b])] == ["a", "b"]
    assert [x["rank"] for x in rank_decisions([a, b])] == [1, 2]


def test_a_decision_that_cannot_say_what_waiting_costs_ranks_lower():
    said = _d("said", cost_of_waiting="a real cost")
    silent = _d("silent", cost_of_waiting="")
    assert leverage(said) > leverage(silent)


# --- what deserves today ---------------------------------------------------

def test_todays_decision_is_the_highest_leverage_one():
    top = _d("do this", business_impact="high", urgency="decide_now",
             verdict="do_now")
    assert todays_decision([_d("later"), top])["decision"] == "do this"


def test_nothing_deserves_today_when_the_top_item_is_wait_or_ignore():
    """Manufacturing a daily action is how a product teaches people to
    ignore it."""
    assert todays_decision([_d("hold", verdict="wait"),
                            _d("skip", verdict="ignore")]) is None


# --- assumptions -----------------------------------------------------------

def test_the_weakest_assumption_is_the_least_supported_load_bearing_one():
    weak = {"assumption": "shaky", "confidence": "low",
            "how_load_bearing": "high", "what_would_break_it": "x"}
    solid = {"assumption": "solid", "confidence": "high",
             "how_load_bearing": "high", "what_would_break_it": "y"}
    assert weakest_assumption([solid, weak])["assumption"] == "shaky"


# --- strategic memory ------------------------------------------------------

INSIGHT_A = {"the_insight": {"sentence": "Attach revenue subsidises the "
                                         "console and the catalogue protects "
                                         "it."},
             "decisions": [_d("Put titles in on day one, or hold at full "
                              "price.", urgency="this_year")],
             "assumptions": [{"assumption": "Subscribers and buyers are the "
                                            "same people.",
                              "confidence": "moderate",
                              "how_load_bearing": "high",
                              "what_would_break_it": "z"}]}


def test_first_run_says_so_rather_than_implying_nothing_changed():
    m = compare(INSIGHT_A, None)
    assert m["first_run"] is True
    assert "first look" in m["summary"].lower()


def test_identical_runs_report_nothing_changed():
    """A product that cannot say 'nothing changed' will invent change to
    justify the visit."""
    m = compare(INSIGHT_A, INSIGHT_A)
    assert m["new_decisions"] == []
    assert "nothing material changed" in m["summary"].lower()


def test_rewording_is_not_reported_as_change():
    reworded = {
        "the_insight": {"sentence": "The catalogue protects the attach "
                                    "revenue that subsidises the console."},
        "decisions": [_d("Hold titles at full price, or put them in on day "
                         "one.")],
        "assumptions": INSIGHT_A["assumptions"]}
    m = compare(reworded, INSIGHT_A)
    assert m["insight_changed"] is False
    assert m["new_decisions"] == []


def test_a_genuinely_new_decision_is_surfaced():
    later = dict(INSIGHT_A)
    later["decisions"] = INSIGHT_A["decisions"] + [
        _d("Price the console closer to cost, or keep subsidising it.")]
    m = compare(later, INSIGHT_A)
    assert len(m["new_decisions"]) == 1
    assert "1 new decision" in m["summary"]


def test_a_weakened_belief_is_surfaced_and_moves_the_trend():
    later = {"the_insight": INSIGHT_A["the_insight"],
             "decisions": INSIGHT_A["decisions"],
             "assumptions": [dict(INSIGHT_A["assumptions"][0],
                                  confidence="low")]}
    m = compare(later, INSIGHT_A)
    assert m["assumptions_weakened"]
    assert m["confidence_trend"] == "weakening"
    assert any("weakened" in s.lower() for s in m["surprises"])


def test_escalating_urgency_is_a_surprise_worth_reporting():
    later = {"the_insight": INSIGHT_A["the_insight"],
             "decisions": [dict(INSIGHT_A["decisions"][0],
                                urgency="decide_now")],
             "assumptions": INSIGHT_A["assumptions"]}
    m = compare(later, INSIGHT_A)
    assert m["escalated"]
    assert any("more urgent" in s.lower() for s in m["surprises"])


def test_a_changed_central_reading_is_the_headline():
    later = {"the_insight": {"sentence": "Cloud streaming breaks the link "
                                         "between install base and revenue "
                                         "entirely."},
             "decisions": INSIGHT_A["decisions"],
             "assumptions": INSIGHT_A["assumptions"]}
    m = compare(later, INSIGHT_A)
    assert m["insight_changed"] is True
    assert "central reading changed" in m["summary"].lower()
    assert m["previous_insight"]


def test_evidence_added_is_counted_not_guessed():
    m = compare(INSIGHT_A, INSIGHT_A, evidence_count=9,
                previous_evidence_count=5)
    assert m["evidence_added"] == 4


# --- the daily view --------------------------------------------------------

FULL = dict(INSIGHT_A, **{
    "competitive": {"who_is_forcing_the_change": "Microsoft"},
    "scenarios": {"base_case": "holds", "upside_case": "both compound",
                  "downside_case": "matches late and loses both",
                  "wild_card": "a publisher pulls its catalogue",
                  "leading_indicators": ["a first-party title near launch"]},
    "blind_spots": {"almost_nobody_is_discussing": "release cadence no studio "
                                                   "can guarantee"},
    "decisions": [
        _d("Put titles in on day one, or hold.", business_impact="high",
           urgency="decide_now", verdict="do_now"),
        _d("Rework the tier names.", verdict="ignore"),
    ],
})


def test_daily_view_answers_the_morning_questions():
    v = daily_view(FULL)
    assert v["headline"]
    assert v["biggest_opportunity"] == "both compound"
    assert v["biggest_threat"] == "matches late and loses both"
    assert v["competitor_to_watch"] == "Microsoft"
    assert v["most_uncertain_assumption"]
    assert v["nobody_is_discussing"]
    assert v["todays_decision"]["decision"].startswith("Put titles in")


def test_daily_view_says_what_can_be_ignored():
    assert "Rework the tier names." in daily_view(FULL)["safe_to_ignore"]


def test_daily_view_without_memory_does_not_imply_nothing_changed():
    assert "first look" in daily_view(FULL)["what_changed"].lower()


def test_daily_view_carries_the_memory_summary_when_there_is_one():
    v = daily_view(FULL, memory=compare(FULL, FULL, evidence_count=6,
                                        previous_evidence_count=4))
    assert "nothing material changed" in v["what_changed"].lower()
    assert v["evidence_added"] == 2
