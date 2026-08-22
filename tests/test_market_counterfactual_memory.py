"""An alternative that predicts nothing is decoration, and is refused.

The real episodes are the point. Both lessons stored below were read out of
production's ledger rather than written into these tests: Cloudflare held
`demand_strengthening` and `demand_weakening` at once, and Duolingo's
weakening belief was opened by a share-price headline.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from intent_engine.market import counterfactual_memory as CM

REAL_LEDGER = pathlib.Path(
    "/Users/prathamsharma/intent-engine-market/reports/market/"
    "learning_ledger.jsonl")


def rows():
    return [json.loads(line) for line in
            REAL_LEDGER.read_text().splitlines() if line.strip()]


def valid(**overrides):
    kwargs = dict(
        subject="acme", observed_outcome="revenue rose",
        leading="demand is strengthening",
        alternative="the figure rose on price with volume flat",
        expected_under_leading="revenue rises again on volume",
        expected_under_alternative="revenue is flat once price is stripped",
        discriminating_evidence="the next quarter's volume disclosure",
        resolution=CM.STRENGTHENED, lesson="a lesson",
        scope=CM.THIS_MECHANISM)
    kwargs.update(overrides)
    return kwargs


# --- the two refusals that are the whole contract ------------------------

def test_an_alternative_that_expects_the_same_thing_is_refused():
    with pytest.raises(CM.EpisodeRejected, match="decoration"):
        CM.episode(**valid(
            expected_under_alternative="revenue rises again on volume"))


def test_the_comparison_ignores_case_and_spacing():
    with pytest.raises(CM.EpisodeRejected):
        CM.episode(**valid(
            expected_under_alternative="  Revenue RISES again on volume  "))


def test_an_explanation_that_predicts_nothing_is_refused():
    with pytest.raises(CM.EpisodeRejected, match="cannot be wrong"):
        CM.episode(**valid(expected_under_alternative=""))


def test_an_episode_with_no_alternative_is_refused():
    with pytest.raises(CM.EpisodeRejected, match="story, not a test"):
        CM.episode(**valid(alternative="   "))


def test_an_episode_with_no_lesson_is_not_memory():
    with pytest.raises(CM.EpisodeRejected, match="not memory"):
        CM.episode(**valid(lesson=""))


def test_an_unknown_scope_is_refused():
    with pytest.raises(CM.EpisodeRejected):
        CM.episode(**valid(scope="EVERYWHERE_ALWAYS"))


# --- memory is only memory if it can be retrieved ------------------------

def test_scope_decides_what_a_later_episode_consults():
    company = CM.episode(**valid(scope=CM.THIS_COMPANY))
    assert company.applies_to(subject="acme", family="anything")
    assert not company.applies_to(subject="other", family="anything")

    mechanism = CM.episode(**valid(
        scope=CM.THIS_MECHANISM,
        provenance={"family": "demand_strengthening"}))
    assert mechanism.applies_to(subject="other",
                                family="demand_strengthening")
    assert not mechanism.applies_to(subject="acme", family="pricing_power")


def test_a_classifier_lesson_applies_to_every_subject():
    """The classifier runs on everything, so its failures follow it."""
    got = CM.episode(**valid(scope=CM.THIS_CLASSIFIER))
    assert got.applies_to(subject="anyone", family="anything")


def test_recall_returns_only_the_applicable_memories():
    """The set of scopes was a fact about the ledger, not about recall.

    This asserted `{THIS_CLASSIFIER}` and `len == 2`, which held while the
    live ledger happened to contain no mechanism-scoped episode in the
    `pricing_power` family. It does now, and that episode is CORRECTLY
    recalled: mechanism scope follows the family, not the subject -- as the
    test two above this one asserts directly.

    What recall must guarantee, at every ledger size, is that everything it
    returns applies and nothing it withholds would have.
    """
    episodes = CM.build(rows())
    got = CM.recall(episodes, subject="nobody", family="pricing_power")
    for e in got:
        assert e.applies_to(subject="nobody", family="pricing_power"), (
            f"recall returned a {e.future_use_scope} episode that does not "
            "apply to the subject and family it was asked about")
    withheld = [e for e in episodes if e not in got]
    for e in withheld:
        assert not e.applies_to(subject="nobody", family="pricing_power"), (
            f"recall withheld an applicable {e.future_use_scope} episode")
    assert got, "no memory at all was recalled for a real family"


# --- built from real resolved episodes -----------------------------------

def test_five_real_episodes_three_strengthened_two_weakened():
    got = CM.summarise(CM.build(rows()))
    assert got["episodes"] >= 5
    assert got["strengthened"] >= 3 and got["weakened"] >= 2
    # The live ledger grows, so the SET is a snapshot. The property is
    # that the episodes name real, distinct subjects.
    assert {"cloudflare", "duolingo", "honda", "shopify"} <= \
        set(got["subjects"])


def test_the_cloudflare_lesson_is_about_the_classifier_not_the_company():
    episodes = CM.build(rows())
    got = next(e for e in episodes
               if e.subject == "cloudflare" and e.resolution == CM.WEAKENED)
    assert got.future_use_scope == CM.THIS_CLASSIFIER
    assert "shared a sentence" in got.strongest_alternative
    assert "must not open a demand belief" in got.lesson
    # The belief was opened by a revenue-up / loss-widening headline.
    assert "Revenue Rises" in got.provenance["opened_by"]


def test_the_duolingo_alternative_matches_its_own_episode():
    """A price-opened belief gets the price alternative, not the cost one."""
    episodes = CM.build(rows())
    got = next(e for e in episodes
               if e.subject == "duolingo" and e.resolution == CM.WEAKENED)
    assert "SHARE-PRICE movement" in got.strongest_alternative
    assert "COST or MARGIN" not in got.strongest_alternative
    assert got.future_use_scope == CM.THIS_CLASSIFIER


def test_every_real_episode_has_two_different_expectations():
    for got in CM.build(rows()):
        assert got.expected_outcome_under_leading
        assert got.expected_outcome_under_alternative
        assert (got.expected_outcome_under_leading.lower() !=
                got.expected_outcome_under_alternative.lower())


def test_a_family_with_no_stated_alternative_produces_no_episode():
    """Silence beats a fabricated alternative."""
    made_up = [
        {"record": "reconciliation", "expectation_id": "e1",
         "hypothesis_id": "b1", "subject": "acme", "outcome": "CONFIRMED",
         "evaluated_at": "2026-08-01", "evidence_ids": []},
        {"record": "expectation", "expectation_id": "e1",
         "hypothesis_id": "b1", "metric": "leadership_transition"},
        {"record": "belief", "belief_id": "b1", "proposition": "p"},
    ]
    assert CM.build(made_up) == ()


# --- experience transfer: an analogy that can never become evidence -------

def test_a_past_episode_is_offered_against_a_new_case_of_the_same_shape():
    """The Cloudflare lesson, applied to a company it never saw.

    The shape is matched on the OPENING EVIDENCE, not on the company: a cost
    figure sharing a sentence with a revenue figure is the same shape
    whoever it happens to.
    """
    episodes = CM.build(rows())
    got = CM.apply(episodes, subject="etsy", family="demand_weakening",
                   opening_evidence=[
                       "Etsy Q3 2026: Revenue Rises 12% as Restructuring "
                       "Widens Operating Loss"])
    assert len(got) == 1
    assert got[0].from_subject == "cloudflare"
    assert got[0].to_subject == "etsy"
    assert "sharing a sentence" in got[0].shared_shape


def test_an_analogy_carries_no_evidence_and_says_so():
    episodes = CM.build(rows())
    (got,) = CM.apply(episodes, subject="etsy", family="demand_weakening",
                      opening_evidence=["Revenue Rises as Loss Widens"])
    assert got.is_evidence is False
    assert got.as_dict()["evidence_ids"] == []
    assert got.kind == CM.ANALOGY
    assert "cannot update a posterior" in got.what_it_is_not
    assert "cannot resolve an expectation" in got.what_it_is_not


def test_a_different_shape_retrieves_nothing():
    episodes = CM.build(rows())
    assert CM.apply(episodes, subject="etsy", family="demand_weakening",
                    opening_evidence=[
                        "Etsy announced a new seller fee structure"]) == ()


def test_an_episode_is_never_an_analogy_for_its_own_subject():
    """That is the same case, not a comparable one."""
    episodes = CM.build(rows())
    assert CM.apply(episodes, subject="cloudflare",
                    family="demand_weakening",
                    opening_evidence=["Revenue Rises as Loss Widens"]) == ()


def test_the_price_shape_retrieves_the_duolingo_episode():
    episodes = CM.build(rows())
    (got,) = CM.apply(episodes, subject="etsy", family="demand_weakening",
                      opening_evidence=["Etsy Stock Falls on Q3 Earnings"])
    assert got.from_subject == "duolingo"
    assert "share-price" in got.shared_shape
