"""The behavioural adapter: parsing, vintage, and the shape of its failures.

WHY THIS USES AN INJECTED RESPONSE
----------------------------------
The BLS public API has a per-day quota that the macro adapter already spends,
so the live call fails with REQUEST_NOT_PROCESSED most of the time. That is a
quota fact, not an adapter fact, and a test that skipped on it would leave the
parsing and the vintage arithmetic unproven forever. So the response SHAPE is
injected and the adapter is exercised in full; the live path is exercised by
the cycle, which reports its failures by name.
"""
from __future__ import annotations

import pytest

from intent_engine.econ import vocabulary as V
from intent_engine.market import behavioral_ingest as BI

_BODY = {
    "status": "REQUEST_SUCCEEDED",
    "Results": {"series": [
        {"seriesID": "JTS000000000000000QUR",
         "data": [{"year": "2026", "period": "M06", "value": "2.1"},
                  {"year": "2026", "period": "M05", "value": "2.0"},
                  {"year": "2026", "period": "M13", "value": "2.4"},
                  {"year": "2026", "period": "M04", "value": "-"}]},
        {"seriesID": "LNS11300000",
         "data": [{"year": "2026", "period": "M06", "value": "62.4"}]},
        {"seriesID": "NOT_ONE_WE_ASKED_FOR",
         "data": [{"year": "2026", "period": "M06", "value": "99.9"}]},
    ]}}


def _poster(url, payload):
    assert "bls.gov" in url
    assert set(payload["seriesid"]) == set(BI.BLS_BEHAVIOURAL)
    return _BODY


def test_the_adapter_produces_behavioral_nodes_not_macro_ones():
    nodes = BI.bureau_of_labor_statistics(retrieved_at="2026-08-27",
                                          fetcher=_poster)
    assert nodes
    assert {n.node_class for n in nodes} == {V.BEHAVIORAL}, (
        "if these arrived as MACRO the collective layer would be reading the "
        "same rows the economic layer already used, and every incremental-"
        "value comparison would be a model against itself")


def test_unparseable_and_unrequested_rows_are_dropped_not_guessed():
    nodes = BI.bureau_of_labor_statistics(retrieved_at="2026-08-27",
                                          fetcher=_poster)
    values = {n.value for n in nodes}
    assert 99.9 not in values, "a series nobody asked for was ingested"
    assert len(nodes) == 3, (
        "expected 2 quits + 1 participation; the 'M13' period and the '-' "
        f"value must be dropped, got {[(n.kind, n.value) for n in nodes]}")


def test_availability_is_after_the_reference_period_not_on_it():
    """`replay.assert_vintage` reads available_at. A figure dated to its own
    reference period is knowable before it was published, which leaks
    hindsight into every historical comparison."""
    nodes = BI.bureau_of_labor_statistics(retrieved_at="2026-08-27",
                                          fetcher=_poster)
    for n in nodes:
        assert n.available_at > n.occurred_at, (
            f"{n.kind} for {n.occurred_at} claims to have been knowable at "
            f"{n.available_at}")


def test_publication_lag_differs_per_series():
    """JOLTS runs about a month behind the household survey; one constant
    for both would date one of them wrongly."""
    nodes = BI.bureau_of_labor_statistics(retrieved_at="2026-08-27",
                                          fetcher=_poster)
    same_period = {n.kind: n.available_at for n in nodes
                   if n.occurred_at == "2026-06-01"}
    assert same_period["quits"] != same_period["labour_participation"]


def test_every_node_names_its_publisher_and_document():
    nodes = BI.bureau_of_labor_statistics(retrieved_at="2026-08-27",
                                          fetcher=_poster)
    for n in nodes:
        assert n.provenance.publisher
        assert n.provenance.document_id in BI.BLS_BEHAVIOURAL


def test_a_refusing_publisher_raises_rather_than_returning_nothing():
    def refuse(url, payload):
        return {"status": "REQUEST_NOT_PROCESSED", "message": ["quota"]}
    with pytest.raises(RuntimeError):
        BI.bureau_of_labor_statistics(retrieved_at="2026-08-27",
                                      fetcher=refuse)


def test_collect_reports_failure_rather_than_looking_empty():
    """A broken feed and a quiet population must never look alike."""
    def refuse(url, payload):
        raise RuntimeError("quota exhausted")
    out = BI.collect(retrieved_at="2026-08-27", poster=refuse)
    assert out["collected"] == 0
    assert out["sources_failed"], "a failing source reported no failure"
    assert out["empty_because"] == "every source failed"


def test_collect_succeeds_and_counts_by_kind():
    out = BI.collect(retrieved_at="2026-08-27", poster=_poster)
    assert out["collected"] == 3
    assert out["by_kind"] == {"quits": 2, "labour_participation": 1}
    assert out["empty_because"] == ""
    assert not out["sources_failed"]


def test_declared_kinds_are_in_the_behavioral_vocabulary():
    for kind, _, _, lag in BI.BLS_BEHAVIOURAL.values():
        assert kind in V.NODE_KINDS[V.BEHAVIORAL]
        assert lag > 0, "a zero publication lag is a hindsight leak"


def test_every_live_series_is_read_by_some_adapter():
    """A series declared LIVE that no adapter reads is a coverage figure that
    is a promise rather than a measurement.

    TWO adapters now serve behavioural series: this BLS one, and
    `market.alfred`, which routes most of them through ALFRED for vintage
    correctness. The guard checks the UNION -- an earlier version compared
    against the BLS adapter alone and failed the moment a second adapter was
    added, which is the guard working, not the guard being wrong.
    """
    from intent_engine.econ import series as S
    from intent_engine.market import alfred as AL

    live = {s.key for s in S.BEHAVIOURAL if s.availability == S.LIVE}
    served = set(BI.BLS_BEHAVIOURAL) | set(AL.BEHAVIOURAL_IDS)
    orphans = live - served
    assert not orphans, (
        f"{sorted(orphans)} are declared LIVE and no adapter reads them")


def test_no_adapter_reads_a_series_nobody_declared():
    """The other direction: coverage computed from a different set than the
    one that runs."""
    from intent_engine.econ import series as S
    from intent_engine.market import alfred as AL

    declared = {s.key for s in S.BEHAVIOURAL}
    served = set(BI.BLS_BEHAVIOURAL) | set(AL.BEHAVIOURAL_IDS)
    undeclared = served - declared
    assert not undeclared, (
        f"{sorted(undeclared)} are fetched and not declared in econ.series")
