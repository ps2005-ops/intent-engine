"""A search we stopped waiting for is not a search that never ran (§P1-2).

WHAT THIS PINS
--------------
MEASURED on cohort A, 8495b00c: project44's evidence page said

    Search coverage: no search was run

while thirteen other companies on the SAME build reported results, no
results, or a blocked channel. The independent-source search is dispatched to
a pool and then joined with a bound -- `_bounded_result` cancels the future
when no interactive budget is left, and abandons the wait when the optional
8s cap expires. Either way the producer never completes, so it writes no
account; an absent account classifies as NEVER_STARTED, and NEVER_STARTED
renders as the sentence above.

The gap WAS recorded, so the system knew. What it did not do was say so on
the page, and "we did not look" is a different sentence from "we looked and
stopped waiting". Reproduced offline at remaining=0.0 (cancelled before the
worker started) and at cap=0.30s (abandoned mid-flight): both gave
report_written=False, search_state=NEVER_STARTED, gaps=1.

THE INVARIANT. The evidence page may say a search was never run only when
none was dispatched and none was reused.
"""
from __future__ import annotations

import pathlib

import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from intent_engine.company_ingestion import relevance as REL
from intent_engine.company_ingestion.service import (
    CompanyIngestionService, _bounded_result,
)
from intent_engine.webapp.app import WebApp


class _Deadline:
    """Just enough deadline for the join to be bounded."""

    def __init__(self, remaining):
        self.remaining = remaining
        self.gaps = []

    def record_gap(self, stage, detail):
        self.gaps.append((stage, detail))

    def may_start(self, _kind):
        return True


@pytest.fixture()
def service(tmp_path):
    return CompanyIngestionService(tmp_path / "ci.jsonl", transport=None,
                                   resolver=False)


# --- the classifier ---------------------------------------------------------

def test_a_named_budget_cause_wins_even_though_a_channel_was_dispatched():
    report = {"channels_attempted": ["edgar_full_text_search"],
              "channels_successful": [],
              "rejection_reasons": {REL.SEARCH_BUDGET_SPENT: 1},
              "budget_exhausted": True}
    assert REL.search_state(report) == REL.SEARCH_BUDGET_SPENT


def test_a_channel_tried_and_unreachable_is_still_blocked():
    """The repair must not turn every unreachable channel into a budget."""
    report = {"channels_attempted": ["edgar_full_text_search"],
              "channels_successful": [],
              "rejection_reasons": {"CHANNEL_ERROR:HTTPError": 1}}
    assert REL.search_state(report) == REL.SEARCH_BLOCKED


def test_a_successful_search_that_hit_its_reading_budget_still_ran():
    """`budget_exhausted` is set by a search that FOUND things and stopped.

    Keying the budget state on that flag alone would report a successful
    search as one that never looked.
    """
    report = {"channels_attempted": ["edgar_full_text_search"],
              "channels_successful": ["edgar_full_text_search"],
              "hits_total": 47, "budget_exhausted": True}
    assert REL.search_state(report) == REL.SEARCH_RAN_WITH_RESULTS


def test_nothing_at_all_is_still_never_started():
    assert REL.search_state({}) == REL.SEARCH_NEVER_STARTED
    assert REL.search_state(None) == REL.SEARCH_NEVER_STARTED


# --- the producer -----------------------------------------------------------

def test_an_abandoned_wait_records_its_own_account(service):
    service._discovery_reports = {}
    service._record_abandoned_discovery("run-1", "project44, Inc.")
    report = service.discovery_report("run-1")
    assert report, "an abandoned search must leave an account"
    assert REL.search_state(report) == REL.SEARCH_BUDGET_SPENT
    assert report["channels_attempted"] == ["edgar_full_text_search"]
    assert report["wait_abandoned"] is True


def test_an_abandoned_wait_never_overwrites_a_real_account(service):
    """The worker is not cancellable once started; it may still arrive."""
    real = {"channels_attempted": ["edgar_full_text_search"],
            "channels_successful": ["edgar_full_text_search"],
            "hits_total": 5}
    service._discovery_reports = {"run-1": real}
    service._record_abandoned_discovery("run-1", "project44, Inc.")
    assert service.discovery_report("run-1")["hits_total"] == 5


@pytest.mark.parametrize("remaining", [0.0, 8.0])
def test_the_bound_that_abandons_the_future_leaves_nothing_behind(remaining):
    """The defect itself, reproduced: the producer does not run.

    This is what makes the account above necessary rather than decorative.
    """
    wrote = {}
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        pool.submit(lambda: time.sleep(1.5))          # occupy the one worker
        future = pool.submit(lambda: wrote.setdefault("ran", True))
        deadline = _Deadline(remaining)
        assert _bounded_result(future, deadline, "discovery", "",
                               cap_s=0.30) is None
        assert wrote == {}, "the producer never ran, so it wrote no account"
        assert deadline.gaps, "the gap is recorded -- the page was not"
    finally:
        pool.shutdown(wait=False)


# --- the page ---------------------------------------------------------------

def test_the_header_never_claims_no_search_when_one_was_dispatched():
    phrase = WebApp._coverage_phrase(REL.DISCOVERY_NOT_RUN,
                                     REL.SEARCH_BUDGET_SPENT)
    assert "no search was run" not in phrase
    assert "abandoned" in phrase


def test_the_header_still_says_no_search_when_none_was_dispatched():
    phrase = WebApp._coverage_phrase(REL.DISCOVERY_NOT_RUN,
                                     REL.SEARCH_NEVER_STARTED)
    assert phrase == "no search was run"


def test_an_earned_coverage_grade_is_still_what_the_header_reports():
    assert WebApp._coverage_phrase(
        "DISCOVERY_EXHAUSTED", REL.SEARCH_RAN_WITH_RESULTS) == \
        "exhausted — everything findable was read"


def test_every_search_state_has_words_of_its_own():
    """A classification nothing renders leaves the page unchanged."""
    for state in REL.SEARCH_STATES:
        assert state in WebApp._PLAIN_SEARCH_STATE, state
        assert WebApp._PLAIN_SEARCH_STATE[state].strip()


# --- the call site, because a repair with no caller stays green -------------

def test_the_discovery_stage_actually_records_an_abandoned_wait():
    """`_record_abandoned_discovery` is only a repair if `discover` calls it.

    Read from the RUNNING function rather than from the file, so a guard
    cannot pass by matching the comment that explains it.
    """
    import inspect

    source = inspect.getsource(CompanyIngestionService.discover)
    assert "_record_abandoned_discovery(" in source, \
        "the abandoned-wait account has no caller in the discovery stage"
    # And it is reached from the THIRD-PARTY join, which is the branch that
    # abandons the only independent-source channel we have.
    third_party = source.split("if third_party is not None:")[-1]
    assert "_record_abandoned_discovery(" in third_party, \
        "the account is recorded somewhere other than the abandoned join"
    assert "_tp is None" in third_party, \
        "the account must be recorded only when the join returned nothing"


# --- and no internal token on the same drawer ------------------------------

def test_no_exception_class_reaches_the_reader_as_a_reason():
    """MEASURED: "channel error:httperror: 1" on Nasuni's live /evidence.

    One internal token across all 107 cohort-A surfaces, and it was on the
    page whose whole job is to make a hostile reader trust the evidence.
    """
    said = WebApp._rejection_english("CHANNEL_ERROR:HTTPError")
    assert "httperror" not in said.lower()
    assert "error" not in said.lower() or said == "the channel did not answer"
    assert said == "the channel did not answer"


def test_an_unmapped_reason_still_degrades_to_words():
    assert WebApp._rejection_english("SOMETHING_NEW") == "something new"
    assert ":" not in WebApp._rejection_english("SOMETHING_NEW:ValueError")


def test_the_drawer_lists_reasons_without_their_exception_types():
    html = WebApp._discovery_detail({
        "search_state": REL.SEARCH_BLOCKED,
        "channels_attempted": ["edgar_full_text_search"],
        "channels_successful": [],
        "rejection_reasons": {"CHANNEL_ERROR:HTTPError": 1},
    })
    assert "httperror" not in html.lower()
    assert "the channel did not answer" in html


def test_every_reason_the_producer_can_write_has_english():
    """A key nothing maps is a key the reader meets as jargon.

    Read from the PRODUCER's own source, so a new rejection reason added
    there fails here rather than on a customer's screen. Cohort A printed
    five of these fifteen; mapping only what was observed is how the next one
    reaches a page.
    """
    import re
    from intent_engine.company_ingestion import third_party_filings as TPF

    source = pathlib.Path(TPF.__file__).read_text()
    keys = set(re.findall(r'"reason": "([A-Z_]+)"', source))
    keys |= set(re.findall(r'rejection_reasons"\] = \{"([A-Z_]+)"', source))
    assert len(keys) >= 5, f"the producer's keys were not found: {keys}"
    unmapped = sorted(k for k in keys
                      if k not in WebApp._REJECTION_ENGLISH)
    assert unmapped == [], f"no English for: {unmapped}"


def test_the_mapped_english_never_reads_as_a_constant():
    for key, said in WebApp._REJECTION_ENGLISH.items():
        assert said == said.lower() or said[0].isupper() is False, key
        assert "_" not in said, key
        assert said.strip(), key
