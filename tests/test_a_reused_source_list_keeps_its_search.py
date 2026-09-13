"""A warm run inherits the sources; it used to discard the search (§14).

THE DEFECT THIS CLOSES, MEASURED 2026-09-11 cold-then-warm against the real
`discover()` rather than read off the code:

    COLD   discovery_report  coverage=DISCOVERY_EXHAUSTED hits=47 independent=1
    SNAPSHOT provenance      {'discovery': 'cold', 'run_id': 'run-cold'}
    WARM   discovery_report  {}
    WARM   page coverage     DISCOVERY_NOT_RUN
    WARM   page detail       "No discovery run is recorded for this analysis"

`discover()` returns early on a WARM snapshot -- deliberately, because
re-proposing a known source list costs 27s and learns nothing -- and
`_discovery_reports` is in-memory and keyed by run. So the account of how hard
anyone had ever looked for those sources existed for exactly one run and was
then unreachable, and every re-analysed company on the preview reported that
nobody had searched at all. Three live companies were probed and all three said
"no search was run" over source lists a real EDGAR search had produced.

The search is a property OF THE SOURCE LIST, so it is stored beside the list
and travels with it. What it is NOT is a claim that this analysis searched
anything, which is why it arrives marked `reused_from_snapshot` with the
original `searched_on` date intact.

NOTHING HERE WEAKENS AN EVIDENCE GATE. `SUPPORTS_FOUND_NONE` is untouched: a
reused account licenses "we found none" only because it records a search that
genuinely ran, over these exact sources, inside the 24h snapshot freshness
window -- and the page prints the date it ran.
"""
from __future__ import annotations

import inspect
import time

import pytest

from intent_engine.company_ingestion import relevance as REL
from intent_engine.company_ingestion import service as SVC
from intent_engine.company_ingestion import snapshot as SN

META = {"company_name": "Microsoft Corporation", "cik": "0000789019",
        "domain": "microsoft.com", "website": "https://microsoft.com"}

#: What the real producer writes on a successful EDGAR full-text search.
REAL_REPORT = {
    "contract": "third_party_discovery.v1",
    "channel": "edgar_full_text_search",
    "query": "Microsoft Corporation", "candidates": [],
    "coverage": REL.DISCOVERY_EXHAUSTED,
    "channels_attempted": ["edgar_full_text_search"],
    "channels_successful": ["edgar_full_text_search"],
    "hits_total": 47, "candidates_considered": 12, "candidates_fetched": 6,
    "rejected": [], "rejection_reasons": {"IRRELEVANT": 4},
    "independent_relevant_origins": 1, "budget_exhausted": False,
    "searched_on": "2026-09-09",
}


@pytest.fixture()
def wired(tmp_path, monkeypatch):
    """A service whose discovery is stubbed at the PRODUCER, not at `discover`.

    The stub honours the real producer's contract -- record the report under
    the run id, return candidates -- so everything between it and the dossier
    is the shipping code path.
    """
    svc = SVC.CompanyIngestionService(path=tmp_path / "ci.jsonl")

    def fake_third_party(self, meta, run_id=""):
        if not hasattr(self, "_discovery_reports"):
            self._discovery_reports = {}
        self._discovery_reports[run_id] = dict(REAL_REPORT)
        return [{"url": "https://sec.gov/other-filer-10k", "title": "",
                 "source_class": "investor_material",
                 "availability": "PROPOSED",
                 "discovery_method": "third_party_filing",
                 "why_relevant": "names the subject"}]

    monkeypatch.setattr(SVC.CompanyIngestionService,
                        "_third_party_filing_candidates", fake_third_party)
    monkeypatch.setattr(SVC.CompanyIngestionService, "_sitemap_candidates",
                        lambda self, *a, **k: [])
    monkeypatch.setattr(SVC.CompanyIngestionService, "run_meta",
                        lambda self, r: dict(META))
    monkeypatch.setattr(SVC.CompanyIngestionService, "_transition",
                        lambda self, *a, **k: None)
    monkeypatch.setattr(SVC.CompanyIngestionService, "_identity_for",
                        lambda self, *a, **k: {"entity_resolved": False})
    for name in ("discover_candidates", "propose_edgar_candidates",
                 "propose_external_candidates", "official_fallback_candidates"):
        if hasattr(SVC, name):
            monkeypatch.setattr(SVC, name, lambda *a, **k: [])
    monkeypatch.setattr(SVC, "safe_fetch",
                        lambda url, **k: {"ok": True, "body": "<html></html>",
                                          "failure_type": "",
                                          "safe_message": ""})
    return svc


def _key():
    return SN.company_key(META["company_name"], cik=META["cik"],
                          domain=META["domain"])


# --- the cold side: the positive control -------------------------------------

def test_a_cold_run_records_the_search(wired):
    """POSITIVE CONTROL. Without this the warm assertions below prove nothing:
    a pipeline that never records an account cannot lose one."""
    wired.discover("run-cold")
    report = wired.discovery_report("run-cold")
    assert report, "the cold run recorded no discovery account at all"
    assert report["coverage"] == REL.DISCOVERY_EXHAUSTED
    assert report["hits_total"] == 47
    assert REL.search_state(report) == REL.SEARCH_RAN_WITH_RESULTS


def test_the_snapshot_carries_the_search_the_cold_run_did(wired):
    """The account is stored BESIDE the source list, because it is a fact
    about that list."""
    wired.discover("run-cold")
    snap = wired.snapshots.get(_key())
    assert snap is not None, "the cold run wrote no snapshot"
    stored = (snap.provenance or {}).get("discovery_coverage")
    assert isinstance(stored, dict) and stored, (
        "the snapshot kept the sources and discarded how they were found: "
        f"provenance={snap.provenance!r}")
    assert stored["coverage"] == REL.DISCOVERY_EXHAUSTED
    assert stored["hits_total"] == 47
    assert stored["independent_relevant_origins"] == 1


def test_the_snapshot_survives_a_json_round_trip_with_its_account(wired):
    """A snapshot is read back from disk by a DIFFERENT process, so the
    account has to survive serialization -- and the store refuses any file
    whose `schema` differs, which is why this rides inside `provenance`."""
    wired.discover("run-cold")
    assert SN.SnapshotStore(
        wired.snapshots.root.parent).get(_key()) is not None
    reread = wired.snapshots.get(_key())
    assert (reread.provenance or {}).get("discovery_coverage", {}).get(
        "hits_total") == 47
    assert reread.schema == SN.SCHEMA, (
        "the account was added by changing the snapshot schema, which silently "
        "discards every snapshot already on disk")


# --- the warm side: the defect ----------------------------------------------

def test_a_warm_run_reports_the_search_it_inherited(wired, tmp_path):
    """THE DEFECT. A second service instance is the real case: the preview
    restarts on every push, and the in-memory report does not survive it."""
    wired.discover("run-cold")
    second = SVC.CompanyIngestionService(path=tmp_path / "ci.jsonl")
    warm = second.discover("run-warm")
    assert warm, "the warm run produced no candidates"
    report = second.discovery_report("run-warm")
    assert report, (
        "a warm run reported NO search over a source list that a real search "
        "produced -- every consumer reads that as DISCOVERY_NOT_RUN")
    assert report["coverage"] == REL.DISCOVERY_EXHAUSTED
    assert report["hits_total"] == 47
    assert REL.search_state(report) == REL.SEARCH_RAN_WITH_RESULTS


def test_a_warm_run_says_the_search_was_not_performed_today(wired, tmp_path):
    """The account travels, and it does NOT pretend to be fresh. Carrying the
    coverage without this marker would imply a search that did not happen."""
    wired.discover("run-cold")
    second = SVC.CompanyIngestionService(path=tmp_path / "ci.jsonl")
    second.discover("run-warm")
    report = second.discovery_report("run-warm")
    assert report.get("reused_from_snapshot") is True, (
        "an inherited search was presented as this analysis's own")
    assert report.get("searched_on") == "2026-09-09", (
        "the reused account was restamped with today's date, which is the one "
        "thing it must never do")


def test_a_warm_run_still_does_no_discovery_work(wired, tmp_path,
                                                 monkeypatch):
    """THE REASON THE WARM PATH EXISTS IS NOT TRADED AWAY. Restoring the
    account must not restore the 27s of searching it describes."""
    wired.discover("run-cold")
    second = SVC.CompanyIngestionService(path=tmp_path / "ci.jsonl")
    called = []
    monkeypatch.setattr(SVC.CompanyIngestionService,
                        "_third_party_filing_candidates",
                        lambda self, *a, **k: called.append("third_party") or [])
    monkeypatch.setattr(SVC.CompanyIngestionService, "_sitemap_candidates",
                        lambda self, *a, **k: called.append("sitemap") or [])
    second.discover("run-warm")
    assert called == [], f"the warm run performed discovery work: {called}"


def test_an_older_snapshot_says_the_account_is_OURS_to_miss(wired, tmp_path):
    """A source list written before this repair has no account. "No search was
    run" is FALSE about it -- one ran, we kept no record -- so the absence is
    stated as ours and no coverage grade is claimed."""
    wired.discover("run-cold")
    snap = wired.snapshots.get(_key())
    stripped = SN.PublicCompanySnapshot(
        **{**snap.as_dict(),
           "sources": snap.sources,
           "provenance": {"run_id": "old", "discovery": "cold"}})
    assert wired.snapshots.put(stripped)
    second = SVC.CompanyIngestionService(path=tmp_path / "ci.jsonl")
    second.discover("run-warm")
    report = second.discovery_report("run-warm")
    assert report.get("reused_from_snapshot") is True
    assert report.get("account_unavailable") is True
    assert report["coverage"] == REL.DISCOVERY_NOT_RUN, (
        "a coverage grade was claimed over a search we have no record of")
    assert report["independent_relevant_origins"] == 0, (
        "an unrecorded search was credited with independent origins")


def test_a_rerun_of_a_reused_run_recovers_the_account(wired, tmp_path):
    """The other early return. `discover()` short-circuits on stored
    candidates, so a process restart mid-run lands here, not on the warm
    branch."""
    wired.discover("run-cold")
    second = SVC.CompanyIngestionService(path=tmp_path / "ci.jsonl")
    second.discover("run-warm")
    third = SVC.CompanyIngestionService(path=tmp_path / "ci.jsonl")
    assert third.discover("run-warm"), "stored candidates were not returned"
    report = third.discovery_report("run-warm")
    assert report, "the short-circuit path reported no search at all"
    assert report["hits_total"] == 47
    assert report.get("reused_from_snapshot") is True


def test_a_cold_rerun_is_not_credited_with_a_search_it_lost(wired, tmp_path):
    """THE ATTRIBUTION LIMIT. Candidates discovered cold, whose report was
    lost to a restart, get NO substitute account: they were not reused from
    the snapshot, and crediting them would claim a search this run cannot
    evidence. The honest answer is the empty one."""
    wired.discover("run-cold")
    second = SVC.CompanyIngestionService(path=tmp_path / "ci.jsonl")
    # `run-cold`'s stored candidates are third_party_filing, not snapshot_reuse
    assert second.discover("run-cold"), "stored candidates were not returned"
    assert second.discovery_report("run-cold") == {}, (
        "a cold run's lost account was silently replaced by another run's "
        "search")


# --- the five states --------------------------------------------------------

@pytest.mark.parametrize("report,expected", [
    ({}, REL.SEARCH_NEVER_STARTED),
    (None, REL.SEARCH_NEVER_STARTED),
    ({"budget_exhausted": True, "channels_attempted": [],
      "rejection_reasons": {"INTERACTIVE_BUDGET_SPENT": 1},
      "coverage": REL.DISCOVERY_NOT_RUN}, REL.SEARCH_BUDGET_SPENT),
    ({"coverage": REL.DISCOVERY_BLOCKED,
      "channels_attempted": ["edgar_full_text_search"],
      "channels_successful": []}, REL.SEARCH_BLOCKED),
    ({"coverage": REL.DISCOVERY_PARTIAL, "channels_attempted": ["e"],
      "channels_successful": []}, REL.SEARCH_BLOCKED),
    ({"coverage": REL.DISCOVERY_ADEQUATE, "channels_attempted": ["e"],
      "channels_successful": ["e"], "hits_total": 0},
     REL.SEARCH_RAN_WITH_NO_RESULTS),
    ({"coverage": REL.DISCOVERY_EXHAUSTED, "channels_attempted": ["e"],
      "channels_successful": ["e"], "hits_total": 47},
     REL.SEARCH_RAN_WITH_RESULTS),
])
def test_the_five_states_are_distinguished(report, expected):
    assert REL.search_state(report) == expected


def test_all_five_states_are_reachable():
    """A vocabulary with an unreachable member is a vocabulary with a bug."""
    reached = {
        REL.search_state(r) for r in (
            {},
            {"budget_exhausted": True, "channels_attempted": []},
            {"coverage": REL.DISCOVERY_BLOCKED, "channels_attempted": ["e"],
             "channels_successful": []},
            {"channels_attempted": ["e"], "channels_successful": ["e"],
             "hits_total": 0},
            {"channels_attempted": ["e"], "channels_successful": ["e"],
             "hits_total": 3},
        )}
    assert reached == set(REL.SEARCH_STATES), (
        f"unreachable states: {set(REL.SEARCH_STATES) - reached}")


def test_a_blocked_channel_never_licenses_found_none():
    """THE GATE THIS REPAIR MUST NOT WEAKEN."""
    assert REL.DISCOVERY_BLOCKED not in REL.SUPPORTS_FOUND_NONE
    assert REL.DISCOVERY_NOT_RUN not in REL.SUPPORTS_FOUND_NONE
    blocked = REL.zero_reading(independent_relevant=0,
                              coverage=REL.DISCOVERY_BLOCKED)
    assert blocked["reading"] == REL.FAILED_TO_FIND


# --- the seam ---------------------------------------------------------------

def test_the_account_reaches_the_dossier_the_page_reads():
    """END TO END over the real contract. The repair is worthless if the
    account stops at the bridge, which is where this product has shipped
    inert repairs before."""
    from intent_engine.demo_dossier import (assemble, market_unavailable,
                                            read_founder_snapshot)
    from intent_engine.external_intel import founder_demo_snapshot as fds

    payload = fds.build_payload(
        run_id="r1", company_id="acme", canonical_name="Acme Inc",
        domain="acme.com", report={"observations": []},
        discovery=dict(REAL_REPORT, reused_from_snapshot=True))
    snap = read_founder_snapshot(payload)
    assert not snap.unknown_fields, (
        f"the new fields are refused by the contract: {snap.unknown_fields}")
    dossier = assemble(market_unavailable("none", company_id="acme"), snap,
                       now="2026-09-11")
    block = (dossier.founder_block or {}).get("discovery_coverage") or {}
    assert block.get("coverage") == REL.DISCOVERY_EXHAUSTED
    assert block.get("hits_total") == 47
    assert block.get("search_state") == REL.SEARCH_RAN_WITH_RESULTS
    assert block.get("reused_from_snapshot") is True
    assert block.get("searched_on") == "2026-09-09"


# --- the surface ------------------------------------------------------------

def _render(report):
    import html
    import re
    from intent_engine.webapp.app import WebApp
    return html.unescape(
        re.sub(r"<[^>]+>", " ", WebApp._discovery_detail(report)))


def test_the_five_states_read_differently_to_a_human():
    """Five outcomes, five sentences. This page printed one sentence for all
    of them, which is how a reused search came to read as no search."""
    rendered = {
        "never": _render({}),
        "budget": _render({"budget_exhausted": True, "channels_attempted": [],
                           "rejection_reasons": {"INTERACTIVE_BUDGET_SPENT": 1}}),
        "blocked": _render({"coverage": REL.DISCOVERY_BLOCKED,
                            "channels_attempted": ["e"],
                            "channels_successful": []}),
        "empty": _render({"channels_attempted": ["e"],
                          "channels_successful": ["e"], "hits_total": 0}),
        "found": _render(dict(REAL_REPORT)),
    }
    assert len(set(rendered.values())) == 5, (
        "two of the five outcomes render the same sentence: "
        f"{ {k: v[:60] for k, v in rendered.items()} }")
    assert "did not look" in rendered["budget"]
    assert "could not reach" in rendered["blocked"]
    assert "the record is empty" in rendered["empty"]
    assert "47" in rendered["found"]
    assert "not a finding about the company" in rendered["never"]


def test_a_reused_search_prints_the_date_it_ran():
    """A reader who cannot tell today's search from last night's cannot judge
    how current the answer is."""
    out = _render(dict(REAL_REPORT, reused_from_snapshot=True))
    assert "2026-09-09" in out, f"the reuse date is not shown: {out}"
    assert "searched nothing again" in out


def test_a_reused_list_without_an_account_claims_no_coverage():
    out = _render({"coverage": REL.DISCOVERY_NOT_RUN,
                   "channels_attempted": [], "channels_successful": [],
                   "reused_from_snapshot": True, "account_unavailable": True})
    assert "was not recorded" in out
    assert "claim no coverage" in out
    assert "No independent-source search is recorded" not in out, (
        "a reused list was reported as though nothing had ever been searched")


# --- structure: the repair has to be ON the path ----------------------------

def test_the_warm_branch_itself_restores_the_account(wired):
    """Reads the SHIPPING function, not a copy. Every behavioural test above
    passes if the restore is performed by a helper nothing on the warm path
    calls -- which is how this product has shipped a repair inert before."""
    src = inspect.getsource(SVC.CompanyIngestionService.discover)
    assert "_reuse_discovery_account" in src, (
        "`discover` does not restore the account; a behavioural pass here "
        "means some other caller does it")
    assert "_restore_discovery_for_stored" in src, (
        "the stored-candidates short circuit does not recover the account")


def test_the_snapshot_writer_is_given_the_account(wired):
    src = inspect.getsource(SVC.CompanyIngestionService.discover)
    assert "discovery=self.discovery_report(run_id)" in src, (
        "`_write_snapshot` accepts an account that its only caller never "
        "passes -- the optional-parameter failure this product has shipped "
        "before")
