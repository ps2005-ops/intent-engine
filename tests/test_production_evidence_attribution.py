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
