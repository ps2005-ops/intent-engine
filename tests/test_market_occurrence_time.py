"""Retrieval time is not event time, and no date is better than a wrong one.

23 live actions shared ONE timestamp — the day we fetched them — and nothing
complained, because nothing had tried to order them yet.
"""
from __future__ import annotations

import pytest

from intent_engine.market import occurrence_time as OT

FETCHED = "2026-08-08"


# --- the defect itself ----------------------------------------------------

def test_retrieval_time_never_becomes_an_occurrence():
    got = OT.read("We rebuilt the checkout flow.", retrieved_at=FETCHED)
    assert got.occurred_at == ""
    assert got.standing == OT.UNKNOWN
    assert got.retrieved_at == FETCHED
    assert not got.orderable


def test_an_undated_page_gets_no_date_at_all():
    got = OT.read("Introducing Commerce Components.", retrieved_at=FETCHED)
    assert got.best_effort == ""
    assert "neither the text nor the page" in got.evidence


# --- the three dates are three dates --------------------------------------

def test_an_action_dated_before_its_article_keeps_both():
    """"On June 12 we launched X", published June 14, read August 8."""
    got = OT.read("On June 12, 2026, we launched Commerce Components.",
                  retrieved_at=FETCHED, published_at="2026-06-14")
    assert got.occurred_at == "2026-06-12"
    assert got.published_at == "2026-06-14"
    assert got.retrieved_at == FETCHED
    assert got.standing == OT.EXACT


def test_publication_alone_bounds_the_occurrence_from_above():
    """The thing happened at or before somebody wrote about it — usable,
    and explicitly weaker than a stated date."""
    got = OT.read("We launched Commerce Components.", retrieved_at=FETCHED,
                  published_at="2026-06-14")
    assert got.occurred_at == ""
    assert got.standing == OT.INFERRED_FROM_PUBLICATION
    assert got.best_effort == "2026-06-14"
    assert got.orderable


def test_a_stated_date_beats_the_publication_date():
    got = OT.read("On June 12, 2026, we launched X.", retrieved_at=FETCHED,
                  published_at="2026-06-14")
    assert got.best_effort == "2026-06-12"


# --- futures are not history ----------------------------------------------

@pytest.mark.parametrize("text", [
    "Starting June 1, 2026, BigCommerce is updating its plan structure.",
    "We will launch Commerce Components on June 12, 2026.",
    "Coming soon, on June 12, 2026, bundles arrive.",
])
def test_a_dated_future_commitment_is_not_an_occurrence(text):
    """The date is real and the event has not happened. Placing it on a
    history of what rivals DID would record an intention as an act."""
    got = OT.read(text, retrieved_at=FETCHED)
    assert got.is_future
    assert not got.orderable
    assert got.occurred_at == ""


def test_a_future_commitment_is_still_reported_not_discarded():
    got = OT.read("We will launch X on June 12, 2026.", retrieved_at=FETCHED)
    assert "forthcoming" in got.evidence


# --- vagueness is not a date ----------------------------------------------

@pytest.mark.parametrize("text", [
    "We recently launched Commerce Components.",
    "Last quarter we introduced bundles.",
    "Earlier this year we shipped the new checkout.",
])
def test_vague_recency_establishes_nothing(text):
    got = OT.read(text, retrieved_at=FETCHED)
    assert got.standing == OT.UNKNOWN
    assert got.occurred_at == ""


def test_vague_recency_beats_a_publication_guess_by_refusing():
    """A page that says "recently" and carries a publication date must not
    silently claim the publication date as the occurrence."""
    got = OT.read("We recently launched X.", retrieved_at=FETCHED,
                  published_at="2026-06-14")
    assert got.occurred_at == ""
    assert got.standing == OT.UNKNOWN


# --- formats --------------------------------------------------------------

def test_an_iso_changelog_date_is_read():
    got = OT.read("2026-06-12: cart attributes now supported.",
                  retrieved_at=FETCHED)
    assert got.occurred_at == "2026-06-12"


def test_an_impossible_date_is_not_a_date():
    got = OT.read("On February 31, 2026, we launched X.", retrieved_at=FETCHED)
    assert got.occurred_at == ""


# --- the corpus-level property --------------------------------------------

def test_one_distinct_date_across_a_corpus_is_not_a_timeline():
    times = [OT.read("We rebuilt checkout.", retrieved_at=FETCHED)
             for _ in range(23)]
    got = OT.summarise(times)
    assert got["orderable"] == 0
    assert got["distinct_orderable_dates"] == 0
    assert "is not a timeline" in got["note"]


# --- changelog entry markers ----------------------------------------------

def test_a_changelog_entry_marker_is_a_date():
    """Live shape: "08.03Oxygen is now available on development stores"."""
    got = OT.read("08.03Oxygen is now available on development stores.",
                  retrieved_at=FETCHED, published_at="2026-08-21")
    assert got.occurred_at == "2026-08-03"
    assert got.standing == OT.DATE_ONLY   # day stated, year borrowed
    assert got.orderable


def test_a_marker_later_than_the_publication_is_refused_not_guessed():
    """Live: shopify.dev/changelog reports modified_date 2026-07-21 while
    its newest entry is marked 08.03, so the metadata is older than the
    page's own content. Rolling the year back turned an August 2026 entry
    into August 2025 — a fabricated date on the very axis a timeline is
    ordered by."""
    got = OT.read("12.20Gift cards now support local currency.",
                  retrieved_at=FETCHED, published_at="2026-03-01")
    assert got.occurred_at == ""


def test_a_marker_with_no_publication_year_is_no_date():
    """06.17 could be any June 17 in the site's history, and guessing the
    current year is the substitution this module exists to prevent."""
    got = OT.read("06.17WhatsApp marketing consent now available.",
                  retrieved_at=FETCHED)
    assert got.occurred_at == ""
    assert got.standing == OT.UNKNOWN


def test_a_version_number_in_running_text_is_not_a_date():
    """The marker must START the entry and sit immediately before a capital."""
    got = OT.read("The SDK moved to 08.03 and adds retries.",
                  retrieved_at=FETCHED, published_at="2026-08-21")
    assert got.occurred_at == ""


def test_an_impossible_marker_is_not_a_date():
    got = OT.read("13.45Something happened.", retrieved_at=FETCHED,
                  published_at="2026-08-21")
    assert got.occurred_at == ""
