"""A dimension that scores full marks on two shared words cannot fail.

MEASURED across 19 live companies on 589518f. Three separate defects met in
`score_dimension`, and together they moved the reported numbers in BOTH
directions, which is why the matrix could not be read as it stood.
"""
from __future__ import annotations

import pytest

from intent_engine.pre100 import quality as Q


LONG_PAGE = "x " * 1200          # every real surface is longer than 1500 chars


# --- D1: substantiation is about the passage, not the page ----------------

def test_a_long_page_does_not_substantiate_a_two_word_passage():
    """`substantial = len(passage) >= 90 or len(text) >= 1500`.

    `text` is the WHOLE SURFACE, so the second clause was true on every real
    page and the passage length never mattered.
    """
    row = Q.score_dimension(
        "history", "history", r"(better strategy)",
        text="Better strategy " + LONG_PAGE, company="Alphabet Inc.")
    assert row["score"] < 10, row


def test_a_substantial_passage_still_substantiates():
    """The control: the repair must not make 10 unreachable."""
    passage = ("margin is decided by Alphabet's infrastructure and compute "
               "per user served, where content moderation and trust "
               "operations scale with usage rather than with revenue")
    row = Q.score_dimension("margin_drivers", "story",
                            r"(margin is decided by)[^.]{0,300}",
                            text=passage + ". " + LONG_PAGE,
                            company="Alphabet Inc.")
    assert row["score"] == 10, row
    assert len(row["passage"]) >= 90


# --- D2: a capital letter is not a name -----------------------------------

@pytest.mark.parametrize("passage", [
    "Better strategy",
    "The choice: Commit to the reading now versus hold and verify first",
    "Which market moved against them",
])
def test_sentence_initial_capitals_are_not_proper_nouns(passage):
    assert not Q._specific(passage, "Alphabet Inc."), passage


@pytest.mark.parametrize("passage,company", [
    ("its position is contested by Adobe and Salesforce", "Cloudflare, Inc."),
    ("the capacity is pre-sold to Amazon under long-term agreements",
     "Intel Corporation"),
])
def test_a_real_rival_name_is_still_specific(passage, company):
    """The control: real names must keep counting."""
    assert Q._specific(passage, company), passage


def test_the_companys_own_name_is_still_specific():
    assert Q._specific("NVIDIA Corporation sells accelerators", "NVIDIA Corporation")


# --- D3: cues must capture content, not only their anchor -----------------

@pytest.mark.parametrize("key", ["intro", "history"])
def test_every_cue_captures_trailing_content(key):
    """Both of these matched an anchor and stopped, so the passage WAS the
    anchor -- "— introduction" and "Better strategy" -- identical for all
    nineteen companies, on dimensions nothing could move."""
    cue = next(c for k, _s, c in Q.DIMENSIONS if k == key)
    assert "[^.]{0," in cue, f"{key} captures no trailing content"


def test_no_dimension_cue_is_anchor_only():
    """The guard over the whole table, because the defect was two of them."""
    bare = [k for k, _s, c in Q.DIMENSIONS
            if c != "." and "[^.]{0," not in c and "{0," not in c]
    assert not bare, f"cues capture only their own anchor: {bare}"


# --- the corpus pass ------------------------------------------------------

def _row(company, dimension, passage, score=10):
    return (company, {"company": company, "dimensions": [
        {"dimension": dimension, "surface": "s", "score": score,
         "why": "company-specific and substantiated", "passage": passage}]})


def test_a_passage_repeated_across_the_corpus_is_capped():
    rows = [_row(f"C{i}", "history", "Better strategy") for i in range(10)]
    out = Q.rescore_corpus(rows)
    for _name, row in out:
        dim = row["dimensions"][0]
        assert dim["score"] == Q.SHARED_PASSAGE_CAP
        assert "identical passage on 10 of 10" in dim["why"]


def test_a_unique_passage_keeps_its_score():
    """THE CONTROL THAT MATTERS. A repair that lowered everything would be
    indistinguishable from one that found something."""
    rows = [_row(f"C{i}", "history", f"company {i} did something distinct")
            for i in range(10)]
    out = Q.rescore_corpus(rows)
    assert all(row["dimensions"][0]["score"] == 10 for _n, row in out)


def test_two_companies_may_share_a_sentence():
    """A sector shares language legitimately; a third of the universe does
    not. Below the floor nothing is capped."""
    rows = [_row(f"C{i}", "margin_drivers", "foundry cost and yield")
            for i in range(2)]
    rows += [_row(f"D{i}", "margin_drivers", f"unique {i}") for i in range(8)]
    out = Q.rescore_corpus(rows)
    assert all(row["dimensions"][0]["score"] == 10 for _n, row in out)


def test_a_company_scored_alone_is_unchanged():
    rows = [_row("Solo", "history", "Better strategy")]
    out = Q.rescore_corpus(rows)
    assert out[0][1]["dimensions"][0]["score"] == 10


def test_core_mean_is_recomputed_after_capping():
    rows = [(f"C{i}", {"dimensions": [
        {"dimension": "history", "score": 10, "passage": "same words"},
        {"dimension": "qa", "score": 10, "passage": f"unique {i}"},
    ]}) for i in range(10)]
    out = Q.rescore_corpus(rows)
    row = out[0][1]
    assert row["core_min"] == Q.SHARED_PASSAGE_CAP
    assert row["core_mean"] == round((6 + 10) / 2, 2)
