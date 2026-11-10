"""The corpus that decides whether translation is real: measured, not asserted.

Every sentence in `fixtures/commercial_event_corpus.json` is verbatim from a
document the production ingestion path retrieved on 2026-08-05 — Palantir,
Microsoft, Caterpillar, Shopify, NVIDIA, one sparse company and one whose
retrieval failed. Nothing in it was written to make a test pass.

The measurement that matters is BOTH numbers at once. Recall alone is easy to
buy: loosen until "Palantir partners with world leading organizations" is a
partnership event, and the corpus recall goes up while the product starts
telling founders things that are not true. So the negative set is real too,
and it is the half that fails first when someone loosens a pattern.
"""
import collections
import json
import pathlib

import pytest

from intent_engine.market import event_patterns as EP
from intent_engine.market import evidence_translation as ET
from intent_engine.strategic_intelligence import evidence_text as EText

CORPUS = json.loads(
    (pathlib.Path(__file__).parent / "fixtures"
     / "commercial_event_corpus.json").read_text())

POSITIVE = CORPUS["positive"]
NEGATIVE = CORPUS["negative"]
FURNITURE = CORPUS["furniture"]


# --- the measurement ------------------------------------------------------
def _classified(entries):
    return [(e, EP.classify_sentence(e["text"])) for e in entries]


def test_recall_on_real_event_sentences():
    """Every real event sentence classifies, and as the right family."""
    misses = [(e["company"], e["expected_type"], e["text"][:80])
              for e, got in _classified(POSITIVE) if got is None]
    wrong = [(e["company"], e["expected_type"], got, e["text"][:80])
             for e, got in _classified(POSITIVE)
             if got is not None and got != e["expected_type"]]
    assert not misses, f"{len(misses)} real events went unrecognised: {misses}"
    assert not wrong, f"{len(wrong)} events got the wrong family: {wrong}"


def test_precision_on_real_non_events():
    """No real non-event sentence becomes evidence.

    A false event is worse than an honest unknown: it updates a real belief,
    with a real citation attached, so nothing downstream catches it.
    """
    fired = [(e["company"], got, e["text"][:90])
             for e, got in _classified(NEGATIVE) if got is not None]
    assert not fired, f"{len(fired)} non-events classified: {fired}"


def test_furniture_never_reaches_the_classifier():
    """Page furniture is rejected before classification, with a reason."""
    slipped = [(f["reason"], f["text"][:90]) for f in FURNITURE
               if not EText.furniture_reason(f["text"])]
    assert not slipped, f"{len(slipped)} furniture sentences slipped: {slipped}"


def test_furniture_rejection_reasons_are_stable():
    """The reason an operator is shown is the reason that fired."""
    drifted = [(f["reason"], EText.furniture_reason(f["text"]), f["text"][:60])
               for f in FURNITURE
               if EText.furniture_reason(f["text"]) != f["reason"]]
    assert not drifted, f"rejection reasons changed: {drifted[:5]}"


def test_every_event_family_in_the_corpus_is_covered():
    """The corpus exercises more than one family, and each has ≥1 example."""
    by_type = collections.Counter(p["expected_type"] for p in POSITIVE)
    assert len(by_type) >= 5, f"corpus is too narrow: {dict(by_type)}"


def test_corpus_spans_the_required_company_set():
    companies = {p["company"] for p in POSITIVE} | \
                {n["company"] for n in NEGATIVE} | \
                {f["company"] for f in FURNITURE}
    for required in ("palantir", "microsoft", "caterpillar", "shopify"):
        assert required in companies, f"{required} missing from the corpus"


def test_measured_rates_are_reported_not_assumed():
    """The numbers this suite defends, stated so a change is visible."""
    hits = sum(1 for _, got in _classified(POSITIVE) if got is not None)
    false_positives = sum(1 for _, got in _classified(NEGATIVE)
                          if got is not None)
    recall = hits / float(len(POSITIVE))
    precision = hits / float(hits + false_positives) if hits else 0.0
    assert recall == 1.0, f"recall fell to {recall:.2%}"
    assert precision == 1.0, f"precision fell to {precision:.2%}"


# --- phrase-shape equivalence --------------------------------------------
#
# The measured defect: "was awarded a contract" classified and "announced a
# contract award" did not. These are the same fact in four grammars, and a
# classifier that recognises one shape is recognising English, not commerce.
@pytest.mark.parametrize("sentence", [
    "Caterpillar was awarded a multi-year contract by the Department of "
    "Defense.",
    "Caterpillar announced a multi-year contract award from the Department "
    "of Defense.",
    "Caterpillar secured a multi-year agreement with the Department of "
    "Defense.",
    "The Department of Defense selected Caterpillar for a new contract.",
    "Caterpillar won a five-year contract to supply generator sets.",
    "Caterpillar has been awarded a contract worth $1.2 billion.",
])
def test_contract_award_survives_rephrasing(sentence):
    assert EP.classify_sentence(sentence) == "CONTRACT_AWARD", sentence


@pytest.mark.parametrize("sentence", [
    "Shopify launched a new platform for enterprise merchants.",
    "Shopify announced the launch of a new platform for enterprise "
    "merchants.",
    "Shopify introduced a new product for enterprise merchants.",
    "Shopify unveiled a new service for enterprise merchants.",
    "A new platform launch was announced by Shopify this morning.",
])
def test_product_launch_survives_rephrasing(sentence):
    assert EP.classify_sentence(sentence) == "PRODUCT_LAUNCH", sentence


@pytest.mark.parametrize("sentence", [
    "Microsoft raised its prices for enterprise customers.",
    "Microsoft announced a price increase for enterprise customers.",
    "Microsoft increased list pricing across the enterprise tier.",
    "Microsoft reduced subscription prices for small businesses.",
    "A price cut was announced for the subscription tier.",
])
def test_pricing_signal_survives_rephrasing(sentence):
    assert EP.classify_sentence(sentence) == "PRICING_SIGNAL", sentence


@pytest.mark.parametrize("sentence", [
    "NVIDIA raised its full-year outlook.",
    "NVIDIA announced an increase to its full-year guidance.",
    "NVIDIA lowered guidance for the fourth quarter.",
    "Full-year guidance was revised upward by the company.",
])
def test_guidance_revision_survives_rephrasing(sentence):
    assert EP.classify_sentence(sentence) == "GUIDANCE_REVISION", sentence


# --- the negative controls that keep recall honest ------------------------
#
# These are the sentences a classifier reaches for when it is being pushed to
# find more events. Each one is real page furniture or real marketing prose,
# and each one must stay unclassified however much recall is wanted.
@pytest.mark.parametrize("sentence", [
    "Explore the Microsoft Store for apps and games on Windows.",
    "At Palantir, we believe that with good data and the right software, "
    "institutions can solve their hardest problems.",
    "A featured collection of the latest Palantir blog posts.",
    "Palantir partners with world leading organizations.",
    "Invent with purpose, realize cost savings, and make your organization "
    "more efficient with Microsoft Azure.",
    "We partner with the best companies in the world.",
    "Our mission is to make commerce better for everyone.",
    "Sign up for a free trial and get started in minutes.",
    "Shopify themes flex to fit every kind and size of business.",
    "Our platform can help you launch a new product in days.",
    "The company is a leading provider of enterprise software.",
    "☒ ANNUAL REPORT PURSUANT TO SECTION 13 OR 15(d) OF THE SECURITIES "
    "EXCHANGE ACT OF 1934.",
])
def test_marketing_and_furniture_never_become_events(sentence):
    """Rejected either as furniture or as an unclassifiable candidate."""
    if EText.furniture_reason(sentence):
        return                        # stopped before the classifier saw it
    assert EP.classify_sentence(sentence) is None, sentence


def test_translation_of_the_whole_corpus_is_deterministic():
    """Two runs over the same rows produce the same evidence ids."""
    rows = [{"evidence_text": p["text"], "source": "https://example.test/a",
             "published_at": "2026-08-01", "kind": "filing"}
            for p in POSITIVE]
    first, _ = ET.translate(rows, subject_company="acme", as_of="2026-08-05")
    second, _ = ET.translate(rows, subject_company="acme", as_of="2026-08-05")
    assert [e.evidence_id for e in first] == [e.evidence_id for e in second]
    assert first, "the corpus produced no evidence at all"
