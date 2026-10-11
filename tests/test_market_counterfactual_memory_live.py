"""LIVE ACCEPTANCE CHECKS -- read the real production ledger.

Split out of `test_market_counterfactual_memory.py` on 2026-10-11. These tests read
`/Users/prathamsharma/intent-engine-market` directly, so their results move
whenever a scheduled cycle appends. That makes them **monitors of production
state**, not regression tests: a legitimate new observation can turn one red
with nothing broken, and a concurrent cycle writing the ledger makes them
nondeterministic outright.

They are deliberately NOT weakened and NOT skipped. Every assertion is
unchanged and they remain runnable on demand:

    env PYTHONPATH=src python -m pytest tests/test_market_counterfactual_memory_live.py

Repository convention: live tests live in `tests/test_*_live.py` and the
pre-commit guard deselects them by filename, alongside
`test_calendar_live.py`, `test_macro_data_live.py` and the others. The
invariants stay covered in the offline suite by the 9 deterministic
tests remaining in `test_market_counterfactual_memory.py`.
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

# --- memory is only memory if it can be retrieved ------------------------

def test_recall_returns_only_the_applicable_memories():
    episodes = CM.build(rows())
    got = CM.recall(episodes, subject="nobody", family="pricing_power")
    # The two classifier lessons follow every subject; the mechanism-scoped
    # ones do not.
    assert {e.future_use_scope for e in got} == {CM.THIS_CLASSIFIER}
    assert len(got) == 2


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
