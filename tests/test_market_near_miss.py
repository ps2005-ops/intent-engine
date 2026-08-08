"""A refusal is a record, and the two reasons for it have opposite remedies.

The property worth holding: a sentence that is not an action at all must not
be counted as a missing buyer. If it is, every measurement says "improve the
extractor" and the extractor was already right to refuse.
"""
from __future__ import annotations

import json
import pathlib

from intent_engine.market import near_miss as NM

ACQUIRED = pathlib.Path(__file__).resolve().parents[1] / \
    "reports/market/strategic/wave9_acquisition.json"
LABELS = pathlib.Path(__file__).resolve().parents[1] / \
    "reports/market/strategic/wave9_near_miss_labels.json"


def miss(**kw):
    base = dict(action_id="a1", actor="Shopify", source_family="release_notes",
                action_type="PRODUCT_LAUNCH", span="Introducing X.",
                dimensions_present=(), missing_dimensions=(),
                cluster=NM.NO_WHAT_OR_WHO)
    base.update(kw)
    return NM.NearMiss(**base)


# --- the distinction the module exists for --------------------------------

def test_a_non_action_is_not_counted_as_a_missing_buyer():
    got = NM.summarise([
        miss(adjudication=NM.WRONG_DOCUMENT),
        miss(adjudication=NM.WRONG_DOCUMENT),
        miss(adjudication=NM.EXTRACTION_RECOVERABLE),
        miss(adjudication=NM.SOURCE_MISSING_INFORMATION),
    ])
    # Two of four are not actions; the rate is over the OTHER two.
    assert got["not_an_action"] == 2
    assert got["real_actions_adjudicated"] == 2
    assert got["recoverable_object_rate"] == 0.5


def test_an_unadjudicated_refusal_is_not_a_source_failure():
    """"Nobody has looked" and "we looked and it was absent" are different
    states, and collapsing them reports a low recoverable rate for work that
    was never done."""
    got = NM.summarise([miss(), miss(), miss(adjudication=NM.EXTRACTION_RECOVERABLE)])
    assert got["unadjudicated"] == 2
    assert got["real_actions_adjudicated"] == 1
    assert got["recoverable_object_rate"] == 1.0


def test_a_rate_with_no_adjudicated_actions_is_none_not_zero():
    got = NM.summarise([miss(), miss()])
    assert got["recoverable_object_rate"] is None
    assert got["not_an_action_rate"] is None


def test_truncated_context_counts_as_recoverable_and_stays_visible():
    """The remedy is the same kind — read more of the document already
    retrieved — but the two must not silently merge."""
    got = NM.summarise([miss(adjudication=NM.TRUNCATED_CONTEXT),
                        miss(adjudication=NM.EXTRACTION_RECOVERABLE)])
    assert got["recoverable"] == 2
    assert got["by_adjudication"][NM.TRUNCATED_CONTEXT] == 1
    assert got["by_adjudication"][NM.EXTRACTION_RECOVERABLE] == 1


# --- labels must actually attach ------------------------------------------

def test_a_curly_quote_does_not_lose_a_label():
    """A label that misses on punctuation reads as "nobody adjudicated
    this", which is the one state the corpus exists to distinguish."""
    typed = "We're providing unthrottled API calls for our newly launched X."
    stored = "We’re providing unthrottled API calls for our newly launched X."
    assert NM.label_key(typed) == NM.label_key(stored)


def test_whitespace_and_case_do_not_lose_a_label():
    assert NM.label_key("  Introducing   Commerce  Components. ") == \
        NM.label_key("introducing commerce components.")


def test_an_established_object_is_not_a_near_miss():
    actions = [{"action_id": "a1", "span": "x", "actor": "Shopify",
                "source_family": "release_notes", "action_type": "MARKET_ENTRY"}]
    objects = {"a1": {"standing": "ESTABLISHED", "dimensions_present": ["WHAT", "WHERE"],
                      "missing": []}}
    assert NM.collect(actions, objects) == ()


# --- against the real corpus ----------------------------------------------

def test_the_live_corpus_is_fully_adjudicated():
    """An unadjudicated row is a claim nobody checked. The wave-9 pool is
    small enough to read completely, so it was read completely."""
    d = json.loads(ACQUIRED.read_text())
    labels = json.loads(LABELS.read_text())["labels"]
    misses = NM.collect(d["actions"], d["objects"], labels)
    got = NM.summarise(misses)
    assert got["unadjudicated"] == 0, \
        [m.span[:70] for m in misses if not m.is_adjudicated]
    assert got["near_misses"] == len(misses)


def test_most_of_the_live_pool_is_not_an_action_at_all():
    """The wave-9 finding, pinned. The pool wave 8 handed forward as
    "near misses" is majority sentences that announce nothing, so the
    dominant defect is the ACTION detector's precision and not the object
    extractor's recall."""
    d = json.loads(ACQUIRED.read_text())
    labels = json.loads(LABELS.read_text())["labels"]
    got = NM.summarise(NM.collect(d["actions"], d["objects"], labels))
    assert got["not_an_action_rate"] > 0.5
    # And of the real actions, a substantial minority ARE recoverable, so
    # extraction work is worth doing second — not instead, and not first.
    assert 0.2 < got["recoverable_object_rate"] < 0.8
