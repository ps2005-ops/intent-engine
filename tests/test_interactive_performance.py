"""§39/§21/§22: the interactive performance CONTRACT, pinned architecturally.

WHAT A UNIT TEST CAN AND CANNOT PROVE HERE
------------------------------------------
It cannot prove wall-clock latency against the real internet: that is what the
live matrix is for, and a test that asserted "Apple in 30 seconds" would be a
test of somebody else's network.

What it CAN prove is the ARCHITECTURE that makes the latency possible, and
that is what fails silently. Three independent 0.4s sources that take 1.2s are
sequential; the same three taking ~0.4s are concurrent. Deterministic sleeps
make that a real assertion rather than a timing guess, and the margin is wide
enough that a loaded CI machine cannot flip it.

Every test here would have passed on the build that made a real customer wait
4m54s, EXCEPT for the ones that pin the change. That is the point.
"""
import time

import pytest

from company_fixture_pages import BASE, PAGES
from intent_engine.company_ingestion.deadline import (
    Deadline, MIN_USEFUL_FETCH_S, OPTIONAL_ENRICHMENT, REQUIRED, TIER_1,
    TIER1_HARD_S, TIER2_HARD_S, TIER_2,
)
from intent_engine.company_ingestion.records import MAX_APPROVED_SOURCES
from intent_engine.company_ingestion.service import CompanyIngestionService
from intent_engine.founder_intelligence.service import FounderIntelligenceService

AS_OF = "2026-07-23T00:00:00+00:00"
DELAY = 0.4


def _slow_transport(delay=DELAY, record=None):
    """The shared fixture transport, each response delayed deliberately.

    It DELEGATES rather than reimplementing: the fixture already encodes
    redirects, failures and MIME types, and a second copy of those rules here
    would be a different pipeline pretending to be this one.
    """
    from company_fixture_pages import transport as fixture

    def transport(url, timeout=8.0, max_bytes=None):
        if record is not None:
            record.append((url, time.monotonic()))
        time.sleep(delay)
        return fixture(url, timeout)
    return transport


@pytest.fixture
def slow_pipeline(tmp_path):
    record = []
    ci = CompanyIngestionService(tmp_path / "ci.jsonl",
                                 transport=_slow_transport(record=record),
                                 resolver=False)
    fi = FounderIntelligenceService(tmp_path / "fi.jsonl")
    run = ci.create_run(company_name="Brightlake", website=BASE,
                        user_id="u", as_of=AS_OF)
    return ci, fi, run["run_id"], record


# --- §8/§39: independent retrieval overlaps -------------------------------

def test_independent_sources_are_fetched_concurrently(slow_pipeline):
    """N independent sources must cost about one source, not N of them.

    This is the defect that produced the 4m54s stall: `fetch_approved`
    iterated fourteen approved URLs one at a time, each paying its own
    timeout and its own retries, and nothing anywhere bounded the sum.
    """
    ci, _, run_id, _record = slow_pipeline
    candidates = ci.discover(run_id)
    approved = [c["candidate_id"] for c in candidates
                if c["url"] in PAGES][:MAX_APPROVED_SOURCES]
    assert len(approved) >= 4, "need several real sources to prove overlap"
    ci.approve(run_id, user_id="u", approved_ids=approved,
               rejected_ids=[c["candidate_id"] for c in candidates
                             if c["candidate_id"] not in approved])
    began = time.monotonic()
    out = ci.fetch_approved(run_id)
    elapsed = time.monotonic() - began

    serial = DELAY * len(approved)
    assert len(out["ok"]) >= 4, "concurrency may not cost us documents"
    # EVERY FIXTURE URL IS ONE HOST, so the per-host cap — not the global
    # cap — is what bounds this: N same-host sources cost ceil(N/k) waves.
    # The first draft of this test asserted half the serial time and failed
    # at 1.22s against a correct 1.20s expectation, which would have been a
    # test defect reported as a product defect.
    waves = -(-len(approved) // CompanyIngestionService._FETCH_PER_HOST)
    expected = DELAY * waves
    assert elapsed < expected * 1.6, (
        f"{len(approved)} independent sources took {elapsed:.2f}s; "
        f"{waves} concurrent waves should cost about {expected:.2f}s")
    assert elapsed < serial * 0.75, (
        f"{elapsed:.2f}s against {serial:.2f}s serial — no overlap at all")


def test_concurrency_is_bounded_per_host(slow_pipeline):
    """Overlap may not become a burst at one publisher (§48/§49)."""
    ci, _, run_id, record = slow_pipeline
    candidates = ci.discover(run_id)
    approved = [c["candidate_id"] for c in candidates
                if c["url"] in PAGES][:MAX_APPROVED_SOURCES]
    ci.approve(run_id, user_id="u", approved_ids=approved,
               rejected_ids=[c["candidate_id"] for c in candidates
                             if c["candidate_id"] not in approved])
    record.clear()
    ci.fetch_approved(run_id)
    # Every fixture URL is one host. Requests that START inside one delay
    # window were in flight together; more than the per-host cap of them at
    # once is a burst, whatever the global cap says.
    starts = sorted(t for _u, t in record)
    for i, t0 in enumerate(starts):
        overlapping = sum(1 for t in starts if t0 <= t < t0 + DELAY * 0.9)
        # A LITERAL, NOT THE CONSTANT. Asserting `<= _FETCH_PER_HOST + 1`
        # reads the very number the guard sets, so raising the cap to 64 also
        # raised the assertion and the proof reported NOT_CAUGHT. A bound the
        # product cannot move is the only kind that bounds it.
        assert overlapping <= 3, (
            f"{overlapping} concurrent requests to one host at index {i}; "
            f"at most 2 in flight plus one starting is the contract")
    assert CompanyIngestionService._FETCH_PER_HOST == 2, (
        "the per-host cap is part of the contract this test measures")


def test_a_host_that_dies_mid_pass_stops_being_dialled(tmp_path):
    """The breaker has to trip WITHIN one concurrent pass (§20).

    TWO GUARDS, AND ONLY ONE OF THEM IS REACHABLE HERE. `_prefetch` skips a
    host the breaker had already killed BEFORE the pass, and separately
    refuses a host that dies DURING it. A test that only sets up the first
    case leaves the second unproven — the break proof said so, reporting
    NOT_CAUGHT because removing either guard left the other one standing.

    This is the second case: every request to the host times out, and the
    candidates still queued behind the first wave must be abandoned rather
    than each paying its own timeout. That is the difference between a
    bounded pass and the ten-timeout runs that motivated the breaker.
    """
    requested = []

    def dead_host(url, timeout=8.0, max_bytes=None):
        requested.append(url)
        raise TimeoutError("the read operation timed out")

    ci = CompanyIngestionService(tmp_path / "ci.jsonl", transport=dead_host,
                                 resolver=False)
    run = ci.create_run(company_name="Brightlake", website=BASE,
                        user_id="u", as_of=AS_OF)
    rid = run["run_id"]
    candidates = {f"cand-{i:012x}": {
        "url": f"{BASE}/page-{i}", "source_type": "product",
        "discovery_method": "known_path", "same_domain": True,
        "source_class": "company_owned"} for i in range(6)}
    requested.clear()
    ci._prefetch(list(candidates), candidates, run_id=rid, already={},
                 host_failures={})

    distinct = {u for u in requested}
    assert len(distinct) <= CompanyIngestionService._FETCH_PER_HOST, (
        f"{len(distinct)} of 6 candidates were dialled on a host that had "
        f"already timed out twice; the breaker did not trip inside the pass")
    assert distinct, "the first wave must actually be attempted"


def test_prefetch_does_not_dial_a_host_the_breaker_already_killed(
        slow_pipeline):
    """Overlap may not resurrect a dead host (§20).

    The serial loop stopped dialling a host after two host-level failures —
    "not dialled again for eight seconds" is most of what kept a bad run
    bounded. Dispatching concurrently is exactly where that is easy to lose,
    because the skip now has to happen before the work is queued rather than
    when the loop reaches it.
    """
    ci, _, run_id, record = slow_pipeline
    candidates = {c["candidate_id"]: c for c in ci.discover(run_id)}
    targets = [cid for cid, c in candidates.items() if c["url"] in PAGES]
    assert len(targets) >= 2

    from urllib.parse import urlparse
    host = urlparse(candidates[targets[0]]["url"]).hostname
    record.clear()
    out = ci._prefetch(targets, candidates, run_id=run_id, already={},
                       host_failures={host: CompanyIngestionService
                                      ._DEAD_HOST_AFTER})
    assert out == {}, "a host that already refused twice was dialled again"
    assert not [u for u, _t in record if urlparse(u).hostname == host], (
        f"{len(record)} requests were made to {host}, which the breaker "
        f"had already taken out of this run")


def test_concurrent_fetch_preserves_documents_and_order(tmp_path):
    """Concurrency may change WHEN a source arrives, never WHICH ones do.

    The decision loop is deliberately still sequential; only the network
    moved. If that ever stops being true the admitted set, or its order in
    the ledger, will differ from the serial build — so both are pinned.
    """
    from company_fixture_pages import transport as fast

    def build(concurrency):
        ci = CompanyIngestionService(tmp_path / f"ci{concurrency}.jsonl",
                                     transport=fast, resolver=False)
        ci._FETCH_CONCURRENCY = concurrency
        run = ci.create_run(company_name="Brightlake", website=BASE,
                            user_id="u", as_of=AS_OF)
        rid = run["run_id"]
        cands = ci.discover(rid)
        approved = [c["candidate_id"] for c in cands
                    if c["url"] in PAGES][:MAX_APPROVED_SOURCES]
        ci.approve(rid, user_id="u", approved_ids=approved,
                   rejected_ids=[c["candidate_id"] for c in cands
                                 if c["candidate_id"] not in approved])
        out = ci.fetch_approved(rid)
        return ([r["original_url"] for r in out["ok"]],
                [f["failure_type"] for f in out["failed"]],
                out["status"])

    # `_prefetch` returns early below two candidates, so concurrency=1 with a
    # single-slot pool is the serial path through the same code.
    serial = build(1)
    concurrent = build(6)
    assert serial == concurrent, (
        "concurrent retrieval admitted a different set, order or status "
        "than serial retrieval")


# --- §21/§22: the budget ---------------------------------------------------

def test_deadline_bounds_acquisition_and_records_the_gap(slow_pipeline):
    """An expired budget stops ACQUIRING and says what it did not reach."""
    ci, _, run_id, _r = slow_pipeline
    candidates = ci.discover(run_id)
    approved = [c["candidate_id"] for c in candidates
                if c["url"] in PAGES][:MAX_APPROVED_SOURCES]
    ci.approve(run_id, user_id="u", approved_ids=approved,
               rejected_ids=[c["candidate_id"] for c in candidates
                             if c["candidate_id"] not in approved])
    spent = Deadline(total_s=0.05)            # nothing can finish in this
    began = time.monotonic()
    out = ci.fetch_approved(run_id, deadline=spent)
    elapsed = time.monotonic() - began

    # NOT `expired`: the budget is refused BEFORE it runs out, because a call
    # that cannot finish inside what is left buys a guaranteed timeout and
    # nothing else. Asserting `expired` here would require the run to burn
    # the budget first, which is the behaviour being removed.
    assert not spent.may_start()
    assert spent.gaps, "an unspent source must be recorded as a gap"
    assert all(g["stage"] == "evidence" for g in spent.gaps)
    # It must not have sat there fetching everything anyway.
    assert elapsed < DELAY, (
        f"an exhausted budget still spent {elapsed:.2f}s on the network")
    # And it is still an honest partial rather than a crash.
    assert out["status"] in ("PARTIAL", "FAILED", "COMPLETE")
    # The unreached sources are RECORDED as unreached, with a failure type
    # that says whose fault it was: ours, and retryable.
    kinds = {f["failure_type"] for f in out["failed"]}
    assert "deadline_exceeded" in kinds, kinds
    assert all(f.get("retryable") for f in out["failed"]
               if f["failure_type"] == "deadline_exceeded")


def test_budget_is_shared_not_per_call():
    """A class share caps the class, not each call inside it."""
    d = Deadline.for_tier(TIER_1)
    assert d.budget_for(8.0, source_class=OPTIONAL_ENRICHMENT) > 0
    d.spend(TIER1_HARD_S, OPTIONAL_ENRICHMENT)
    assert d.budget_for(8.0, source_class=OPTIONAL_ENRICHMENT) == 0.0
    # A required source is untouched by an optional class exhausting itself.
    assert d.budget_for(8.0, source_class=REQUIRED) > 0


def test_reserved_view_shares_one_clock():
    """Acquisition and composition are one wall clock seen twice."""
    d = Deadline.for_tier(TIER_1)
    view = d.reserving(20.0)
    assert view.total_s == TIER1_HARD_S - 20.0
    assert view.started_at == d.started_at
    view.record_gap("evidence", "unreached")
    assert d.gaps == view.gaps, "a gap recorded in the view must be visible " \
                                "to the run that owns the budget"


def test_no_call_is_started_that_cannot_finish():
    """Below the useful floor the budget refuses rather than pretends.

    TWO CASES, because one of them was covered by a different guard. A tiny
    TOTAL budget is also a tiny class share, so removing the remaining-time
    check still returned 0.0 through the share check and the mutation went
    undetected. A large budget almost entirely elapsed isolates the check
    that actually matters: plenty of share, no time.
    """
    d = Deadline(total_s=MIN_USEFUL_FETCH_S / 2)
    assert d.budget_for(8.0) == 0.0
    assert not d.may_start()

    nearly_spent = Deadline(total_s=100.0,
                            started_at=time.monotonic() - 99.5)
    assert nearly_spent.remaining < MIN_USEFUL_FETCH_S
    assert nearly_spent.budget_for(8.0) == 0.0, (
        "0.5s left is not enough to start an 8s call, however much of the "
        "class share is unspent")
    assert not nearly_spent.may_start()


def test_batch_callers_are_not_held_to_an_interactive_budget():
    """§2 is an INTERACTIVE contract; batch work has no customer waiting."""
    d = Deadline.unbounded()
    assert not d.expired and d.budget_for(8.0) == 8.0
    assert d.reserving(20.0) is d


def test_tier_budgets_are_frozen():
    """The target may not be moved to meet the measurement (§2)."""
    assert (TIER1_HARD_S, TIER2_HARD_S) == (60.0, 120.0)
    assert Deadline.for_tier(TIER_1).total_s == TIER1_HARD_S
    assert Deadline.for_tier(TIER_2).total_s == TIER2_HARD_S


# --- §3: the quality wall --------------------------------------------------

def test_phrase_prefilter_changes_no_answer():
    """The 91%-miss scan skip is a speed change with no semantic content.

    `owned_match` was 32% of a cold Apple analysis. It is now skipped when the
    phrase provably cannot occur — and "provably" has to be exactly true, or
    the product quietly loses evidence to go faster, which §3 forbids.
    """
    from intent_engine.strategic_intelligence import observations as O

    def unfiltered(text, phrases, company=""):
        for phrase in phrases:
            for n, m in enumerate(O._phrase_pattern(phrase).finditer(text)):
                if n >= O._MAX_OCCURRENCES:
                    break
                if not O._foreign_match(text, m, company):
                    return m
        return None

    texts = [
        "We provide a system of record for customer data. Acme Corp sells "
        "point-of-sale terminals to retailers. Our platform is a system of "
        "record.",
        "Revenue grew 12%. The Company operates in one segment. Competitors "
        "include point of sale vendors and system-of-record suppliers.",
        # the folds `str.lower` does not perform but `re.I` does
        "The ſystem of record claim. A KKelvin reading.",
        "nothing relevant here at all, only ordinary prose about weather",
    ]
    tables = (O._NEUTRAL_SIGNAL_KEYWORDS, O._SIGNAL_KEYWORDS,
              O._OUTSIDE_ONLY_PHRASES)
    compared = 0
    for text in texts:
        for table in tables:
            for _signal, phrases in table.items():
                for company in ("Acme Corp", ""):
                    want = unfiltered(text, phrases, company)
                    got = O.owned_match(text, phrases, company)
                    compared += 1
                    assert (want is None) == (got is None)
                    if want is not None:
                        assert (want.start(), want.end(), want.group()) == \
                               (got.start(), got.end(), got.group())
    assert compared > 100, "the comparison must actually cover the tables"


def test_prefilter_probe_is_a_necessary_condition():
    """Every word the pattern requires is a word the probe tests for."""
    from intent_engine.strategic_intelligence import observations as O
    for phrase in ("system of record", "point of sale", "gross margin",
                   "self-serve", "land and expand"):
        probes = O._phrase_probe(phrase)
        assert probes, f"no probe derived for {phrase!r}"
        words = {w.casefold() for w in phrase.split()}
        for word in words:
            assert word in probes
        # AND NOTHING ELSE. A probe the pattern does not require is not a
        # necessary condition, so testing for it excludes documents that
        # would have matched — evidence lost to go faster. Without this
        # clause a probe set with an invented word passed every assertion.
        assert set(probes) <= words, (
            f"{set(probes) - words} is tested for but not required by "
            f"the pattern for {phrase!r}")
        # THE POSITIVE CONTROL. A text that DOES contain the phrase must
        # never be excluded; an over-eager filter is only visible here.
        assert not O._cannot_contain(f"we offer a {phrase} today.", phrase)
        # A text missing any required word is provably not a match.
        for word in phrase.split():
            without = phrase.replace(word, "zzz")
            assert O._cannot_contain(without, phrase) or \
                word.casefold() in without.casefold()


# --- §18: discovery is inside the budget too -------------------------------

def test_discovery_optional_branches_are_bounded(slow_pipeline):
    """A spent budget skips ENRICHMENT discovery and says it did.

    Retrieval was bounded first and discovery was not, which left half the
    acquisition path outside the budget: `discover` makes SEC full-text
    search and sitemap requests of its own, so a slow regulator could consume
    the whole interactive window before one approved source was fetched.
    """
    ci, _, _rid, record = slow_pipeline
    run = ci.create_run(company_name="Brightlake", website=BASE,
                        user_id="u", as_of=AS_OF)
    spent = Deadline(total_s=0.05)
    record.clear()
    candidates = ci.discover(run["run_id"], deadline=spent)

    assert candidates, "discovery must still produce the required candidates"
    assert any(g["stage"] == "discovery" for g in spent.gaps), (
        "skipping enrichment without recording it leaves the reader to infer "
        f"the absence: {spent.gaps}")
    # The company's own homepage is REQUIRED and is never skipped — without it
    # there is no analysis to bound.
    assert any(u == BASE for u, _t in record), (
        "the homepage is required, not enrichment, and must still be read")


def test_discovery_budget_does_not_bind_when_there_is_time(slow_pipeline):
    """The positive control: a healthy budget skips nothing.

    Without this, a filter that refused everything would satisfy the test
    above and quietly delete the enrichment path on every run.
    """
    ci, _, _rid, record = slow_pipeline
    run = ci.create_run(company_name="Brightlake", website=BASE,
                        user_id="u", as_of=AS_OF)
    healthy = Deadline.for_tier(TIER_1)
    with_budget = ci.discover(run["run_id"], deadline=healthy)

    run2 = ci.create_run(company_name="Brightlake", website=BASE,
                         user_id="u2", as_of=AS_OF)
    unbounded = ci.discover(run2["run_id"], deadline=None)
    assert [c["url"] for c in with_budget] == [c["url"] for c in unbounded], (
        "a budget with time left changed the candidate set")
    assert not [g for g in healthy.gaps if g["stage"] == "discovery"]
