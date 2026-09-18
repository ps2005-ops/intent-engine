"""Three real production rows, pinned as fixtures.

These are verbatim from the production learning ledger
(`intent-engine-market/reports/market/learning_ledger.jsonl`, inspected
2026-08-05). Each was reported as evidence attributed to the wrong company.
Investigating them found three DIFFERENT things, and keeping them apart is the
point of this file:

  CATERPILLAR  a real typing defect, already closed. The row was written at
               7e6b21f, whose `classify_type` matched keywords against the
               whole observation and read a share-price story as a rival
               making a move. It opened "Caterpillar Inc. faces a rival
               competing on price or capability", which reached a founder.

  NEXTERA      not a defect. NextEra IS named and IS a party to the merger the
               sentence describes. Reported as "a Dominion headline filed
               under NextEra" from a truncated view of the text.

  STRIPE       a real defect, and the one still live. Stripe IS named, so
               `subject_binding` passes — but the estimates topped and the
               forecast raised are PayPal's. Naming the subject and being the
               company an event happened to are different questions, and only
               the first was being asked.

The headlines are also kept because they document WHERE each is stopped. All
three carry a " - Publisher" suffix and are refused as `incomplete_sentence`
before reaching the classifier at all, so the ledger's own rows cannot recur.
That is not the same as the defect being fixed: the same sentence in article
body prose is a complete sentence, and the sweep ingests body prose.
"""
from __future__ import annotations

import pytest

from intent_engine.market import event_patterns as EP
from intent_engine.market import evidence_translation as ET
from intent_engine.market import micro_evidence as ME
from intent_engine.strategic_intelligence import evidence_text as EText

# --- verbatim from the production ledger ------------------------------------
CATERPILLAR_HEADLINE = ("Caterpillar Inc. stock underperforms Monday when "
                        "compared to competitors despite daily gains - "
                        "MarketWatch")
NEXTERA_HEADLINE = ("SC regulators set hearing schedule for proposed Dominion "
                    "Energy, NextEra merger - Live 5 News")
STRIPE_HEADLINE = ("PayPal tops Q2 estimates and raises full-year forecast "
                   "amid Stripe takeover bid - SiliconANGLE")

#: The same claims as complete sentences, which is the form body prose takes.
STRIPE_PROSE = ("PayPal tops Q2 estimates and raises full-year forecast amid "
                "Stripe takeover bid.")
NEXTERA_PROSE = ("Regulators set a hearing schedule for the proposed Dominion "
                 "Energy, NextEra merger.")


def translate(text, subject, aliases):
    obs = [{"text": text, "source": "https://example.com/a",
            "date": "2026-07-20", "source_class": "independent_reporting"}]
    return ET.translate(obs, subject_company=subject, as_of="2026-08-05",
                        subject_aliases=list(aliases))


# --- defect 2: a price move is not a strategic action -----------------------
def test_the_price_move_headline_no_longer_types_as_a_competitor_action():
    """The regression, pinned at the classifier.

    `COMPETITOR_ACTION` here asserted that a rival had done something. The
    sentence says the share price moved, which is not an act by anybody.
    """
    assert EP.classify_sentence(CATERPILLAR_HEADLINE) is None


@pytest.mark.parametrize("text", [
    CATERPILLAR_HEADLINE,
    "Acme shares rose 4% on Tuesday, outperforming rivals.",
    "Acme stock underperforms the sector when compared to competitors.",
])
def test_no_price_move_story_becomes_a_commercial_event(text):
    assert EP.classify_sentence(text) is None


def test_the_price_move_headline_produces_no_evidence_at_all():
    evidence, rejections = translate(
        CATERPILLAR_HEADLINE, "caterpillar", ["Caterpillar", "Caterpillar Inc."])
    assert evidence == []
    assert rejections


def test_the_belief_that_headline_opened_can_no_longer_be_opened():
    """It is not enough that the type is refused; nothing may reach formation.

    The proposition this produced -- "faces a rival competing on price or
    capability rather than coexisting" -- was rendered to a founder from this
    one sentence.
    """
    from intent_engine.market import belief_formation as BF
    evidence, _ = translate(CATERPILLAR_HEADLINE, "caterpillar",
                            ["Caterpillar", "Caterpillar Inc."])
    candidates, _refused = BF.propose(evidence, as_of="2026-08-05")
    assert candidates == []


# --- defect 1: named is not the same as "this happened to it" ---------------
def test_the_subject_is_named_in_all_three_rows():
    """The premise that these were bound to the wrong company, checked.

    `subject_binding` is doing its job on every one of them; the reported
    mis-binding came from reading truncated text. Recorded so the guard is not
    "fixed" by someone acting on the original report.
    """
    assert ET.subject_binding(STRIPE_HEADLINE, ["Stripe"]) == ET.NAMED
    assert ET.subject_binding(NEXTERA_HEADLINE, ["NextEra"]) == ET.NAMED
    assert ET.subject_binding(
        CATERPILLAR_HEADLINE, ["Caterpillar", "Caterpillar Inc."]) == ET.NAMED


def test_results_reported_by_another_company_are_refused():
    """The live defect. Stripe is named; the results are PayPal's."""
    evidence, rejections = translate(STRIPE_PROSE, "stripe", ["Stripe"])
    assert evidence == []
    assert any("another company" in r for r in rejections)


def test_the_same_sentence_is_kept_for_the_company_it_is_about():
    """The control that makes the rule a re-attribution, not a deletion.

    If this ever fails while the test above passes, the guard has stopped
    discriminating and started refusing guidance revisions generally.
    """
    evidence, _ = translate(STRIPE_PROSE, "paypal", ["PayPal"])
    assert [e.evidence_type for e in evidence] == [ME.GUIDANCE_REVISION]


def test_a_company_reporting_its_own_results_is_unaffected():
    evidence, _ = translate(
        "Duolingo beat consensus estimates for the quarter and raised its "
        "full-year forecast.", "duolingo", ["Duolingo"])
    assert [e.evidence_type for e in evidence] == [ME.EARNINGS_SURPRISE]


def test_the_refusal_is_counted_as_a_subject_mismatch():
    """A silent drop and a refusal look identical in the output and must not
    look identical in the stats."""
    stats = ET.TranslationStats()
    obs = [{"text": STRIPE_PROSE, "source": "https://example.com/a",
            "date": "2026-07-20", "source_class": "independent_reporting"}]
    ET.translate(obs, subject_company="stripe", as_of="2026-08-05",
                 subject_aliases=["Stripe"], stats=stats)
    assert stats.subject_mismatch == 1


# --- the rule is deliberately narrow ----------------------------------------
def test_a_third_party_actor_does_not_refuse_a_non_results_family():
    """"A&O Shearman represents Sasol Limited in its bond issuance" puts the
    subject after the verb and is still real evidence about Sasol. The rule
    applies only where the actor is definitionally the company itself."""
    assert ME.PROCUREMENT_SIGNAL not in ET.OWN_RESULTS_FAMILIES
    assert ET.OWN_RESULTS_FAMILIES == {ME.EARNINGS_SURPRISE,
                                       ME.GUIDANCE_REVISION}


def test_a_subject_named_after_the_verb_is_kept_outside_the_results_families():
    evidence, _ = translate(
        "Regulators approved the merger of Dominion Energy and NextEra "
        "after a scheduled hearing.", "nextera", ["NextEra"])
    assert all(e.evidence_type not in ET.OWN_RESULTS_FAMILIES
               for e in evidence)


def test_the_rule_does_not_fire_when_no_aliases_are_known():
    """With no aliases there is no subject to position against, and inventing
    a refusal would drop evidence on a question that was never asked."""
    evidence, _ = ET.translate(
        [{"text": STRIPE_PROSE, "source": "https://example.com/a",
          "date": "2026-07-20", "source_class": "independent_reporting"}],
        subject_company="stripe", as_of="2026-08-05")
    assert evidence


def test_reports_own_results_is_true_when_the_action_is_not_found():
    """Fails OPEN on a span it cannot locate, because a position test that
    cannot find the verb has not learned that the subject is the wrong one."""
    assert ET.reports_own_results("Acme raised guidance.", "", ["Acme"])
    assert ET.reports_own_results("Acme raised guidance.", "nowhere", ["Acme"])


# --- where the ledger's own rows are stopped --------------------------------
@pytest.mark.parametrize("headline", [
    CATERPILLAR_HEADLINE, NEXTERA_HEADLINE, STRIPE_HEADLINE])
def test_a_titled_headline_never_reaches_the_classifier(headline):
    """All three carry a " - Publisher" suffix and no terminal punctuation.

    This is why six of the nine production rows no longer classify at all, and
    it is a different guarantee from the two above: it stops the ROW, not the
    reasoning error inside it.
    """
    assert EText.furniture_reason(headline) == "incomplete_sentence"
    assert translate(headline, "any", ["Any"])[0] == []


# --- defect 3: a question is not an observation -----------------------------
#
# Found by manually inspecting the beliefs a corrected real-ledger backfill
# produced, which is the only place it could have been found: every gate the
# row passed was working as written.
DUOLINGO_QUESTION = ("Will Duolingo (DUOL) Beat Estimates Again in Its Next "
                     "Earnings Report? - Yahoo Finance")


def test_an_interrogative_headline_evidences_no_event():
    """It fired EARNINGS_SURPRISE on the pair "Beat"/"Estimates" and opened
    "Duolingo, Inc. is seeing demand strengthen rather than plateau" -- a
    claim about trading conditions, from a sentence that asserts nothing.

    The Caterpillar price-move failure in a different costume: event
    vocabulary present, event absent.
    """
    assert EP.classify_sentence(DUOLINGO_QUESTION) is None


@pytest.mark.parametrize("text", [
    "Will Acme beat estimates again this quarter?",
    "Is it time to buy Acme?",
    "Here's why Acme raised guidance",
    "What to expect from Acme's Q3 earnings",
])
def test_speculation_is_not_evidence(text):
    assert EP.classify_sentence(text) is None


@pytest.mark.parametrize("text", [
    "When adjusting for these items, we exceeded expectations across revenue.",
    "Acme beat consensus estimates for the quarter.",
    "Acme raised its full-year guidance.",
])
def test_the_speculation_guard_does_not_refuse_real_statements(text):
    """The narrowing that measurement forced. A first version also refused
    sentences opening "when"/"what"/"why"/"how", which killed a real Microsoft
    earnings statement in the corpus."""
    assert EP.classify_sentence(text) is not None


# --- defect 4: analyst commentary is not a company action -------------------
#
# Found in the output of a REAL production cycle run through the deployed
# launchd entrypoint, not in a fixture. One session opened two contradictory
# beliefs about one company, both from third-party price targets.
BHP_TARGET_CUT = ("BHP Group Limited Stock 12-Month Price Target Cut to "
                  "$58.5, Implies 34% Downside - TradingView.")
BHP_TARGET_RAISE = ("Argus Raises its Price Target on BHP Group (BHP) to $95 "
                    "- Yahoo Finance.")


@pytest.mark.parametrize("text", [
    BHP_TARGET_CUT,
    BHP_TARGET_RAISE,
    "Morgan Stanley upgrades Acme to Overweight from Equal-weight.",
    "Analyst initiated coverage on Acme with a Buy rating.",
    "Acme Earnings: Demand Jumps; Fair Value Estimate Increased - Morningstar.",
])
def test_analyst_commentary_is_not_a_company_action(text):
    """The object token ("Price") matched while the SUBJECT was an analyst.

    The two BHP headlines produced "is buying market share with price rather
    than protecting margin" and "is exercising pricing power rather than
    defending volume" in the same cycle. They contradict each other, which is
    what makes it obvious neither described BHP's own conduct.
    """
    assert EP.classify_sentence(text) is None


@pytest.mark.parametrize("text", [
    "Acme raised list prices by 5% across its enterprise tier.",
    "Acme cut prices on its entry-level plan to win share.",
])
def test_a_real_pricing_action_still_classifies(text):
    """The control. Real pricing actions say "prices" or "list prices"; an
    analyst note says "price target". Refusing both would delete the family."""
    assert EP.classify_sentence(text) == ME.PRICING_SIGNAL


def test_no_belief_can_be_opened_from_an_analyst_price_target():
    from intent_engine.market import belief_formation as BF
    evidence, _ = translate(BHP_TARGET_CUT, "bhp", ["BHP", "BHP Group"])
    candidates, _refused = BF.propose(evidence, as_of="2026-08-05")
    assert candidates == []


# --- defect 5: an analyst hypothetical is not a company action --------------
#
# Found in the output of a REAL production cycle run through the deployed
# launchd entrypoint against live research, not in a fixture. One belief in
# thirty-six rested on an analyst's argument that a result was reachable:
#
#   "Toyota: Struggling Through Macro Tensions, But There's A Path To EPS
#    Growth (NYSE:TM) - Seeking Alpha."
#     -> action "Growth" / object "EPS" -> EARNINGS_RESULT
#     -> "toyota is seeing demand strengthen rather than plateau"
#
# Toyota reported nothing. This is the third costume of one failure -- event
# vocabulary present, event absent -- after the Caterpillar price move and the
# analyst price target, so it is refused by construction rather than by
# company name.
TOYOTA_PATH_TO = ("Toyota: Struggling Through Macro Tensions, But There's A "
                  "Path To EPS Growth (NYSE:TM) - Seeking Alpha.")


@pytest.mark.parametrize("text", [
    TOYOTA_PATH_TO,
    "New enterprise contracts could drive revenue growth next year.",
    "There is potential for margin expansion in the second half.",
    "We expect revenue to accelerate through fiscal 2027.",
    "We estimate fair value at $95 per share.",
    "Our bull case assumes 20% subscriber growth.",
    "Our bear case sees margins compressing to 12%.",
    "Upside exists if the restructuring completes on schedule.",
    "There is room for further buybacks given the cash balance.",
    "The company is likely to expand capacity in Asia.",
    "Margins should improve as freight costs normalise.",
    "The firm is poised to benefit from the data center cycle.",
])
def test_an_analyst_hypothetical_is_not_a_company_action(text):
    """An argument that something COULD happen is not a record that it did."""
    assert EP.classify_sentence(text) is None


@pytest.mark.parametrize("text,expected", [
    # Company guidance IS a company action and must survive. A company
    # issuing guidance names itself in the third person and states a figure;
    # an analyst forecasts in the first person.
    ("GUIDANCE: (LIN) Linde Plc Expects Q3 Adjusted EPS Range $4.45 - $4.55 "
     "- Moomoo.", ME.GUIDANCE_REVISION),
    ("Canadian National Railway Raises 2026 Volume Outlook - WSJ.",
     ME.GUIDANCE_REVISION),
    ("Toyota Motor Corporation Revises Consolidated Earnings Forecast for "
     "the Fiscal Year Ending March 31, 2027.", ME.GUIDANCE_REVISION),
    ("Infosys Limited Provides Earnings Guidance for the Fiscal Year 2027.",
     ME.GUIDANCE_REVISION),
    ("Honda Motor Earnings, Revenue Rise; Raises Annual Guidance.",
     ME.GUIDANCE_REVISION),
])
def test_real_company_guidance_still_classifies(text, expected):
    """The control. Refusing the forecasting voice outright would delete the
    GUIDANCE_REVISION family, which is a real company action -- every one of
    these is verbatim from the production ledger."""
    assert EP.classify_sentence(text) == expected


def test_no_belief_can_be_opened_from_an_analyst_hypothetical():
    from intent_engine.market import belief_formation as BF
    evidence, _ = translate(TOYOTA_PATH_TO, "toyota",
                            ["Toyota", "Toyota Motor Corporation"])
    candidates, _refused = BF.propose(evidence, as_of="2026-08-05")
    assert candidates == []
