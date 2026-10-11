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


# --- built from real resolved episodes -----------------------------------

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

